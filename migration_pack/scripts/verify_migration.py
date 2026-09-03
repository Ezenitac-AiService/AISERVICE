#!/usr/bin/env python3
"""AISERVICE migration verifier.

실제 수용 검사는 별도 ``aiservice-probe`` 컨테이너에서 fixture 계약의 내부
DNS endpoint를 검사한다.  ``--mock``는 계약 테스트용 명시적 fixture 경로이고,
운영 보고서에서 실제 evidence로 간주되지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
AISERVICE_ROOT = SCRIPT_DIR.parents[1]
PACK_ROOT = AISERVICE_ROOT / "migration_pack"
REPO_ROOT = AISERVICE_ROOT.parent
DEFAULT_FIXTURE_PATH = REPO_ROOT / "specs" / "001-aiservice-platform-migration" / "contracts" / "probe-endpoint-fixture.md"
DEFAULT_SCHEMA_PATH = REPO_ROOT / "specs" / "001-aiservice-platform-migration" / "contracts" / "healthcheck-report-schema.json"

EXACT_NINE_CHECK_IDS = [
    "portal",
    "ateam_pilos",
    "bteam_oliview",
    "bteam_chata",
    "bteam_chatb",
    "model_gateway_llm",
    "model_gateway_embedding",
    "model_gateway_rerank",
    "redis",
]
ENDPOINTS = EXACT_NINE_CHECK_IDS
CATEGORY_BY_ID = {
    **{check_id: "PUBLIC_WEB" for check_id in EXACT_NINE_CHECK_IDS[:5]},
    **{check_id: "MODEL_GATEWAY" for check_id in EXACT_NINE_CHECK_IDS[5:8]},
    "redis": "REDIS",
}
PORTAL_SUBCHECK_IDS = ["portal_root", "portal_changelog", "portal_changelog_data", "portal_static_assets"]
TARGET_PATTERN = re.compile(r"^\|\s*`(?P<id>[^`]+)`\s*\|\s*(?P<target>[^|]+)\|")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_probe_fixture(fixture_path: Path = DEFAULT_FIXTURE_PATH) -> list[tuple[str, str, str]]:
    """Markdown fixture에서 probe ID·category·target을 읽는다."""
    entries: list[tuple[str, str, str]] = []
    for line in fixture_path.read_text(encoding="utf-8").splitlines():
        match = TARGET_PATTERN.match(line.strip())
        if not match:
            continue
        check_id = match.group("id")
        if check_id in EXACT_NINE_CHECK_IDS:
            entries.append((check_id, CATEGORY_BY_ID[check_id], match.group("target").strip().strip("`")))
    if [entry[0] for entry in entries] != EXACT_NINE_CHECK_IDS:
        raise ValueError("probe-endpoint-fixture.md가 정확히 9개 정본 check를 정의하지 않습니다")
    return entries


def _probe_http(target: str, timeout: float = 3.0) -> tuple[bool, int | None, bytes]:
    request = Request(target, headers={"User-Agent": "AISERVICE-Probe/1.0"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        return response.status in (200, 204), response.status, body


def _probe_redis(target: str, timeout: float = 2.0) -> tuple[bool, str | None]:
    host, port_text = target.rsplit(":", 1)
    with socket.create_connection((host, int(port_text)), timeout=timeout) as connection:
        connection.sendall(b"PING\r\n")
        response = connection.recv(128).decode("ascii", errors="replace")
    return response.startswith("+PONG"), "+PONG" if response.startswith("+PONG") else response[:32]


class _AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        candidate = attrs_map.get("src") if tag in {"script", "img", "source"} else attrs_map.get("href")
        if candidate and not candidate.startswith(("data:", "mailto:", "javascript:")):
            self.urls.append(candidate)


def _portal_subchecks(target: str, body: bytes, timeout: float) -> list[dict[str, Any]]:
    parsed = urlparse(target)
    base = f"{parsed.scheme}://{parsed.netloc}"
    checks: list[dict[str, Any]] = []
    for subcheck_id, path in (
        ("portal_root", "/"),
        ("portal_changelog", "/changelog"),
        ("portal_changelog_data", "/changelog_data.json"),
    ):
        try:
            ok, status, response_body = _probe_http(urljoin(base, path), timeout)
            if subcheck_id == "portal_changelog_data" and ok:
                json.loads(response_body.decode("utf-8"))
            checks.append({"id": subcheck_id, "status": "PASS" if ok else "FAIL", "status_code": status or 503})
        except (OSError, ValueError, TypeError):
            checks.append({"id": subcheck_id, "status": "FAIL", "status_code": 503, "error_code": "ERR_PROBE"})

    parser = _AssetParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    asset_failures = 0
    for resource in sorted(set(parser.urls)):
        resource_url = urljoin(base + "/", resource)
        if urlparse(resource_url).netloc != parsed.netloc:
            continue
        try:
            ok, _status, _body = _probe_http(resource_url, timeout)
            asset_failures += 0 if ok else 1
        except OSError:
            asset_failures += 1
    checks.append({
        "id": "portal_static_assets",
        "status": "PASS" if asset_failures == 0 else "FAIL",
        "status_code": 200 if asset_failures == 0 else 502,
        **({} if asset_failures == 0 else {"error_code": "ERR_STATIC_ASSET"}),
    })
    return checks


def run_single_probe(
    check_id: str,
    category: str,
    target: str,
    use_mock: bool = False,
) -> dict[str, Any]:
    """정본 endpoint 하나를 검사하고 본문은 버린다."""
    started = time.perf_counter()
    checked_at = _now()
    if use_mock:
        result: dict[str, Any] = {
            "id": check_id,
            "category": category,
            "target": target,
            "status": "PASS",
            "checked_at": checked_at,
            "status_code_or_ping": "+PONG" if category == "REDIS" else 200,
            "latency_ms": 0.1,
        }
        if check_id == "portal":
            result["subchecks"] = [{"id": subcheck_id, "status": "PASS", "status_code": 200} for subcheck_id in PORTAL_SUBCHECK_IDS]
        return result

    status = "FAIL"
    status_code: int | str | None = None
    error_code: str | None = None
    subchecks: list[dict[str, Any]] | None = None
    try:
        if category == "REDIS":
            ok, status_code = _probe_redis(target)
        else:
            ok, status_code, body = _probe_http(target)
            if check_id == "portal" and (not body or not body.strip()):
                ok = False
            if check_id.startswith("model_gateway_") and ok:
                try:
                    parsed = json.loads(body.decode("utf-8"))
                    ok = isinstance(parsed, dict)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    ok = False
            if check_id == "portal":
                subchecks = _portal_subchecks(target, body, 3.0)
                ok = ok and all(subcheck["status"] == "PASS" for subcheck in subchecks)
        status = "PASS" if ok else "FAIL"
    except (OSError, ValueError, TypeError) as exc:
        error_code = "ERR_PROBE_TIMEOUT" if isinstance(exc, TimeoutError) else "ERR_PROBE_CONNECT"

    if check_id == "portal" and subchecks is None:
        subchecks = [
            {"id": subcheck_id, "status": "FAIL", "status_code": 503, "error_code": error_code or "ERR_PROBE"}
            for subcheck_id in PORTAL_SUBCHECK_IDS
        ]

    result = {
        "id": check_id,
        "category": category,
        "target": target,
        "status": status,
        "checked_at": checked_at,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if status_code is not None:
        result["status_code_or_ping"] = status_code
    if error_code:
        result["error_code"] = error_code
    if subchecks is not None:
        result["subchecks"] = subchecks
    return result


def test_endpoint(target: str, timeout: float = 3.0) -> bool:
    """기존 호출부 호환용 단일 HTTP probe helper."""
    del timeout
    parsed = urlparse(target)
    category = "REDIS" if parsed.scheme == "" and ":" in target else "PUBLIC_WEB"
    check_id = "redis" if category == "REDIS" else "portal"
    return run_single_probe(check_id, category, target)["status"] == "PASS"


def _file_evidence(path: Path) -> tuple[int, int, str]:
    from manifest_utils import calculate_path_evidence

    return calculate_path_evidence(path)


def build_asset_integrity(pack_root: Path = PACK_ROOT) -> dict[str, Any]:
    manifest_path = pack_root / "asset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets: list[dict[str, Any]] = []
    missing: list[str] = []
    mismatches: list[str] = []
    for entry in manifest.get("assets", []):
        asset_id = str(entry["asset_id"])
        target = (AISERVICE_ROOT / str(entry["path"]).rstrip("/")).resolve()
        observed: str | None = None
        size = 0
        file_count = 0
        application_open = False
        if target.is_file() or target.is_dir():
            size, file_count, observed = _file_evidence(target)
            application_open = target.is_dir() and (target / "chroma.sqlite3").is_file() if entry["application_validation"] == "rag_open" else target.read_bytes()[:4] == b"GGUF"
        else:
            missing.append(asset_id)
        hash_match = observed == entry.get("sha256") and size == entry.get("size_bytes") and file_count == entry.get("file_count")
        if not hash_match:
            mismatches.append(asset_id)
        assets.append(
            {
                "asset_id": asset_id,
                "path": entry["path"],
                "hash_scope": entry["hash_scope"],
                "size_bytes": size,
                "file_count": file_count,
                "expected_sha256": entry.get("sha256"),
                "observed_sha256": observed,
                "hash_match": hash_match,
                "application_open": application_open,
                "status": "PASS" if hash_match and application_open else "FAIL",
            }
        )
    verified = sum(1 for item in assets if item["status"] == "PASS")
    return {
        "manifest_file": "asset_manifest.json",
        "assets_verified": verified == 6 and not missing and not mismatches,
        "required_asset_count": 6,
        "verified_asset_count": verified,
        "missing_assets": missing,
        "unexpected_assets": [],
        "hash_mismatches": mismatches,
        "assets": assets,
    }


def build_gpu_evidence() -> tuple[dict[str, Any], dict[str, Any]]:
    """NVML과 runtime fingerprint를 수집한다. 없는 장치는 성공으로 추정하지 않는다."""
    device = os.environ.get("GPU_DEVICE_NAME", "")
    vram_mb = 0
    if shutil_which("nvidia-smi"):
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                text=True,
                timeout=5,
            ).strip().splitlines()[0]
            name, memory = [item.strip() for item in output.split(",", 1)]
            device = name
            vram_mb = int(float(memory))
        except (OSError, IndexError, ValueError, subprocess.SubprocessError):
            pass
    runtime_fingerprint = os.environ.get("LLAMA_RUNTIME_BUILD_FINGERPRINT", "")
    verified = bool(device and vram_mb >= 11000 and runtime_fingerprint)
    hardware = {
        "profile_id": "dev-rtx3060",
        "cpu_model": os.environ.get("CPU_MODEL", "unknown"),
        "avx2": "avx2" in Path("/proc/cpuinfo").read_text(errors="ignore").lower() if Path("/proc/cpuinfo").is_file() else False,
        "gpu_model": device or "unavailable",
        "vram_mb": vram_mb,
        "compute_capability": os.environ.get("GPU_COMPUTE_CAPABILITY", "unknown"),
        "backend": os.environ.get("LLAMA_RUNTIME_BACKEND", "llama.cpp-cuda"),
        "gpu_acceleration_verified": verified,
    }
    evidence = {
        "source": "nvml+llama_runtime",
        "device": device or "unavailable",
        "build_fingerprint": runtime_fingerprint or "unavailable",
        "sample_set_id": os.environ.get("GPU_SAMPLE_SET_ID", "unverified_runtime"),
        "all_requests_verified": False,
        "samples": [
            {"workload": workload, "request_count": 0, "evidence_count": 0, "coverage_percent": 0.0}
            for workload in ("chat_llm", "embedding", "rerank")
        ],
    }
    return hardware, evidence


def shutil_which(command: str) -> str | None:
    import shutil

    return shutil.which(command)


def build_rag_grounding_report() -> dict[str, Any]:
    scenarios = []
    for scenario_id in ("zero_search", "evidence_insufficient", "invalid_citation", "prompt_injection"):
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "response_status": "failed",
                "model_invoked": False,
                "factual_claim_count": 0,
                "cited_claim_count": 0,
                "unsupported_claim_count": 0,
                "citation_coverage_percent": None,
                "claim_ids": [],
                "citations": [],
            }
        )
    scenarios.append(
        {
            "scenario_id": "valid_evidence",
            "response_status": "failed",
            "model_invoked": False,
            "factual_claim_count": 0,
            "cited_claim_count": 0,
            "unsupported_claim_count": 0,
            "citation_coverage_percent": None,
            "claim_ids": [],
            "citations": [],
        }
    )
    return {
        "scenario_results": scenarios,
        "factual_claim_count": 0,
        "cited_claim_count": 0,
        "unsupported_claim_count": 0,
        "citation_coverage_percent": None,
        "raw_content_logged": False,
    }


def run_probe_container(
    compose_file: Path,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
) -> list[dict[str, Any]]:
    """GPU/privileged/host port 없는 one-shot probe 컨테이너에서 9개 check를 실행한다."""
    specs = load_probe_fixture(fixture_path)
    payload = json.dumps(specs, ensure_ascii=False)
    runner = """
import json, socket, sys, time, urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

class Assets(HTMLParser):
    def __init__(self):
        super().__init__(); self.urls=[]
    def handle_starttag(self, tag, attrs):
        values=dict(attrs); key='src' if tag in ('script','img','source') else 'href'
        value=values.get(key)
        if value and not value.startswith(('data:', 'mailto:', 'javascript:')): self.urls.append(value)

def http(url):
    with urllib.request.urlopen(url, timeout=3) as response:
        return response.status, response.read()

def subcheck(sub_id, url, validator=None):
    try:
        code, body=http(url); valid=code == 200 and (validator(body) if validator else True)
        return {'id': sub_id, 'status': 'PASS' if valid else 'FAIL', 'status_code': code}
    except Exception:
        return {'id': sub_id, 'status': 'FAIL', 'status_code': 503, 'error_code': 'ERR_PROBE_SUBCHECK'}

specs=json.loads(sys.argv[1]); out=[]
for cid, cat, target in specs:
    started=time.perf_counter(); ok=False; code=None; err=None; subchecks=None
    try:
        if cat == 'REDIS':
            host, port=target.rsplit(':',1)
            with socket.create_connection((host,int(port)),2) as connection:
                connection.sendall(b'PING\\r\\n'); code=connection.recv(64).decode()
            ok=code.startswith('+PONG')
        else:
            code, body=http(target); ok=code in (200,204) and bool(body.strip())
            if cid.startswith('model_gateway_') and ok:
                try: ok=isinstance(json.loads(body.decode('utf-8')), dict)
                except Exception: ok=False
            if cid == 'portal':
                base=f'{urlparse(target).scheme}://{urlparse(target).netloc}'
                subchecks=[
                    subcheck('portal_root', urljoin(base, '/')),
                    subcheck('portal_changelog', urljoin(base, '/changelog')),
                    subcheck('portal_changelog_data', urljoin(base, '/changelog_data.json'), lambda value: isinstance(json.loads(value.decode('utf-8')), dict)),
                ]
                parser=Assets(); parser.feed(body.decode('utf-8', errors='replace')); failures=0
                for asset in sorted(set(parser.urls)):
                    try:
                        asset_code, _=http(urljoin(base+'/', asset)); failures += 0 if 200 <= asset_code < 300 else 1
                    except Exception: failures += 1
                subchecks.append({'id':'portal_static_assets','status':'PASS' if failures == 0 else 'FAIL','status_code':200 if failures == 0 else 502})
                ok=ok and all(item['status']=='PASS' for item in subchecks)
    except Exception:
        err='ERR_PROBE_CONNECT'
    item={'id':cid,'category':cat,'target':target,'status':'PASS' if ok else 'FAIL','checked_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'latency_ms':round((time.perf_counter()-started)*1000,2)}
    if code is not None: item['status_code_or_ping']=code
    if err: item['error_code']=err
    if subchecks is not None: item['subchecks']=subchecks
    out.append(item)
print(json.dumps(out))
"""
    command = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "--profile",
        "probe",
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python3",
        "aiservice-probe",
        "-c",
        runner,
        payload,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
    if completed.returncode:
        raise RuntimeError("aiservice-probe container 실행 실패")
    for line in reversed(completed.stdout.splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return parsed
    raise RuntimeError("probe container가 JSON 결과를 반환하지 않았습니다")


def _empty_data_integrity() -> dict[str, Any]:
    return {
        "checksum_verified": False,
        "databases_verified": [],
        "rollback_tested": False,
    }


def build_data_integrity(pack_root: Path = PACK_ROOT) -> dict[str, Any]:
    """Verify dump checksums without claiming staging/rollback evidence."""
    try:
        from bootstrap_restore import verify_checksums
        checksum_verified = verify_checksums(pack_root=pack_root)
    except (ImportError, OSError, ValueError):
        checksum_verified = False
    return {
        "checksum_verified": checksum_verified,
        "databases_verified": ["pilos_v2", "oliview_project"] if checksum_verified else [],
        "rollback_tested": False,
    }


def build_verification_report(
    use_mock: bool = False,
    *,
    probe_mode: bool = False,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    pack_root: Path = PACK_ROOT,
) -> dict[str, Any]:
    specs = load_probe_fixture(fixture_path)
    if probe_mode:
        checks = run_probe_container(AISERVICE_ROOT / "docker-compose.yml", fixture_path)
        checks_by_id = {entry["id"]: entry for entry in checks}
        checks = [checks_by_id[check_id] for check_id, _category, _target in specs]
    else:
        checks = [run_single_probe(check_id, category, target, use_mock=use_mock) for check_id, category, target in specs]

    hardware, gpu_evidence = build_gpu_evidence()
    asset_integrity = build_asset_integrity(pack_root)
    passed_count = sum(1 for check in checks if check.get("status") == "PASS")
    rag_grounding = build_rag_grounding_report()
    data_integrity = build_data_integrity(pack_root)
    all_evidence = bool(
        passed_count == 9
        and hardware["gpu_acceleration_verified"]
        and asset_integrity["assets_verified"]
        and gpu_evidence["all_requests_verified"]
        and rag_grounding["citation_coverage_percent"] == 100
        and data_integrity["checksum_verified"]
        and data_integrity["rollback_tested"]
    )
    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "checked_at": _now(),
        "mode": "DEMO",
        "status": "PASS" if all_evidence else "FAIL",
        "total_checks": 9,
        "passed_checks": passed_count,
        "failed_checks": 9 - passed_count,
        "checks": checks,
        "hardware": hardware,
        "gpu_evidence": gpu_evidence,
        "asset_integrity": asset_integrity,
        "rag_grounding": rag_grounding,
        "data_integrity": data_integrity,
    }
    if report["status"] != "PASS":
        report["degraded_reason"] = "실제 probe 또는 필수 evidence가 아직 수용 기준을 충족하지 않음"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AISERVICE 9-check migration verifier")
    parser.add_argument("--report", "-r", type=Path, default=PACK_ROOT / "verification_report.json")
    parser.add_argument("--manifest", type=Path, default=PACK_ROOT / "migration_manifest.json")
    parser.add_argument("--probe", "--probe-container", action="store_true", help="aiservice-probe container에서 실제 내부 DNS 검사")
    parser.add_argument("--mock", action="store_true", help="계약 테스트용 mock check; 운영 evidence로 사용하지 않음")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    args = parser.parse_args(argv)
    report = build_verification_report(
        use_mock=args.mock,
        probe_mode=args.probe,
        fixture_path=args.fixture,
        pack_root=args.manifest.resolve().parent,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"verification report: {report['status']} ({report['passed_checks']}/9 checks)")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
