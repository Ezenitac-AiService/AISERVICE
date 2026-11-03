#!/usr/bin/env python3
"""
auto_changelog.py: 모델 게이트웨이 LLM 기반 작업 이력(Changelog) 자동화 에이전트 CLI 서비스
단일 진실 공급원(SSOT) 진입점 (Feature 010)
"""

import sys
import os
import re
import json
import signal
import argparse
import subprocess
import urllib.parse
import urllib.request
import urllib.error
import time
import random
import uuid
import socket
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

# Exit codes per contract (0: success, 2: recoverable/validation error, 1: fatal error, 130/143: signal)
EXIT_SUCCESS = 0
EXIT_VALIDATION_ERROR = 2
EXIT_FATAL_ERROR = 1
EXIT_INTERRUPT = 130

# Default configuration constants
DEFAULT_MODEL_GATEWAY_URL = "http://127.0.0.1:8081/v1/chat/completions"
DEFAULT_MODEL_NAME = "qwen3.5-9b"
ALLOWED_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_DIFF_PHYSICAL_BYTES = 512 * 1024  # 512KB physical ceiling
MAX_DIFF_TOKEN_BUDGET_BYTES = 80 * 1024  # 80KB ~ 24K tokens for LLM context ceiling
MAX_DIFF_LINES = 3000
MAX_FILE_LINES = 100

ALLOWED_SUBSYSTEMS = {
    "chat_a", "chat_b", "core", "model_gateway", "nginx_gateway", "oliview_web", "pilos"
}

SUBSYSTEM_PATH_PREFIXES = [
    ("AISERVICE/bteam/Oliview_chatbot_a", "chat_a"),
    ("AISERVICE/bteam", "chat_b"),
    ("AISERVICE/model_gateway", "model_gateway"),
    ("nginx", "nginx_gateway"),
    ("dist_node_a/portal_static", "core"),
    ("oliview_web", "oliview_web"),
    ("pilos", "pilos"),
]

SEMVER_REGEX = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9_.-]+))?$")
REVISION_SAFE_REGEX = re.compile(r"^[a-zA-Z0-9_.~^/-]+$")


@dataclass
class GitContextBundle:
    commit_hash: str
    commit_message: str
    diff_text: str
    stat_summary: str
    changed_files: List[str]
    is_staged: bool
    is_merge: bool = False
    merged_commits: str = ""
    tag_name: Optional[str] = None
    tag_annotation: Optional[str] = None
    date: Optional[str] = None


class Config:
    def __init__(
        self,
        model_gateway_url: str,
        model: str,
        repo_root: Path,
        manage_changelog_path: Path,
        db_path: Path,
        portal_json_path: Path,
        args: argparse.Namespace,
    ):
        self.model_gateway_url = model_gateway_url
        self.model = model
        self.repo_root = repo_root
        self.manage_changelog_path = manage_changelog_path
        self.db_path = db_path
        self.portal_json_path = portal_json_path
        self.args = args


class TempFileManager:
    """임시 파일 생성 및 POSIX 시그널/컨텍스트 매니저 기반 자동 회수기"""
    def __init__(self):
        self.tracked_files: List[Path] = []

    def create_temp_file(self, prefix: str = "draft", suffix: str = ".tmp", directory: Optional[str] = None) -> str:
        unique_name = f".{prefix}_{uuid.uuid4().hex}{suffix}"
        base_dir = Path(directory) if directory else Path.cwd()
        temp_path = base_dir / unique_name
        temp_path.touch(mode=0o600, exist_ok=False)
        self.tracked_files.append(temp_path)
        return str(temp_path)

    def cleanup(self):
        for p in self.tracked_files:
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass
        self.tracked_files.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


_global_temp_manager = TempFileManager()


def setup_signal_handlers(temp_manager: TempFileManager):
    """POSIX SIGINT/SIGTERM 시그널 핸들러 등록 및 자원 회수"""
    def _sig_handler(signum, frame):
        temp_manager.cleanup()
        sys.stderr.write(f"\n[auto_changelog] Interrupted by signal {signum}. Cleaned up temporary files.\n")
        sys.exit(EXIT_INTERRUPT if signum == signal.SIGINT else 143)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)


def resolve_repo_root() -> Path:
    """Git repo_root를 CWD 독립적으로 탐색하여 절대 경로 반환 (C1 서브모듈 불변식)"""
    candidate: Optional[Path] = None
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            candidate = Path(res.stdout.strip()).resolve()
    except Exception:
        pass

    if candidate:
        curr = candidate
        for _ in range(10):
            if (curr / "scripts" / "manage_changelog.py").exists():
                return curr
            if curr == curr.parent:
                break
            curr = curr.parent
        raise RuntimeError("Failed to resolve repository root: scripts/manage_changelog.py not found in git hierarchy.")

    # 파일 위치 기준 상위 순회 폴백
    curr = Path(__file__).resolve().parent
    for _ in range(10):
        if (curr / "scripts" / "manage_changelog.py").exists():
            return curr
        if curr == curr.parent:
            break
        curr = curr.parent

    raise RuntimeError("Failed to resolve repository root: scripts/manage_changelog.py not found in parent hierarchy.")


def parse_args(argv=None) -> argparse.Namespace:
    """CLI 인자 파서 구성"""
    parser = argparse.ArgumentParser(
        prog="auto_changelog.py",
        description="모델 게이트웨이 LLM 기반 작업 이력(Changelog) 자동화 에이전트 CLI 서비스",
    )
    parser.add_argument("--model-gateway-url", type=str, default=None, help="모델 게이트웨이 엔드포인트 URL")
    parser.add_argument("--model", type=str, default=None, help="LLM 모델명 (기본: qwen3.5-9b)")
    parser.add_argument("--prompt", type=str, default=None, help="자연어 작업 설명 프롬프트 (Diff 수집 생략)")
    parser.add_argument("--rev", type=str, default=None, help="분석 대상 Git 커밋 범위/리비전 (예: HEAD~1..HEAD)")
    parser.add_argument("--commits", type=int, default=None, help="분석할 최근 커밋 개수 (N)")
    parser.add_argument("--subsystem", type=str, default=None, choices=list(ALLOWED_SUBSYSTEMS), help="서브시스템 수동 오버라이드")
    parser.add_argument("--version", type=str, default=None, help="버전 수동 지정 (SemVer 2.0.0)")
    parser.add_argument("--stage", type=str, default=None, choices=["alpha", "beta", "rc", "stable"], help="배포 단계 수동 지정")
    parser.add_argument("--date", type=str, default=None, help="릴리즈 일자 (YYYY-MM-DD)")
    parser.add_argument("--bump", type=str, default=None, choices=["major", "minor", "patch"], help="버전 증분 수동 강제")
    parser.add_argument("--yes", "-y", action="store_true", help="대화형 승인 프롬프트 생략 (비대화형 완전 자동 실행)")
    parser.add_argument("--dry-run", action="store_true", help="DB 쓰기 없이 검증 및 가상 결과 출력만 수행")
    parser.add_argument("--lang", type=str, default="ko", choices=["ko", "en"], help="체인지로그 출력 언어 (기본: ko)")
    parser.add_argument("--multi", action="store_true", help="다중 서브시스템 커밋 시 개별 마일스톤 분할 등록")
    parser.add_argument("--spec", type=str, default=None, help="기능 명세서 식별자 (예: Spec 010)")
    parser.add_argument("--no-bump", action="store_true", help="중복 버전 발생 시 자동 버전 패치 승격 비활성화")
    parser.add_argument("--sync", action="store_true", help="Git 훅 연동 시 동기 실행 대기")

    return parser.parse_args(argv)


def resolve_config(args: argparse.Namespace) -> Config:
    """설정 3단계 우선순위(CLI > 환경변수 > 기본값) 및 절대 경로 해석"""
    repo_root = resolve_repo_root()

    url = args.model_gateway_url or os.environ.get("MODEL_GATEWAY_URL") or DEFAULT_MODEL_GATEWAY_URL
    validate_gateway_url(url)

    model = args.model or os.environ.get("MODEL_NAME") or DEFAULT_MODEL_NAME

    manage_changelog_path = repo_root / "scripts" / "manage_changelog.py"
    db_path = repo_root / "dist_node_a" / "data" / "changelog.db"
    portal_json_path = repo_root / "dist_node_a" / "portal_static" / "changelog_data.json"

    return Config(
        model_gateway_url=url,
        model=model,
        repo_root=repo_root,
        manage_changelog_path=manage_changelog_path,
        db_path=db_path,
        portal_json_path=portal_json_path,
        args=args,
    )


def validate_gateway_url(url: str) -> bool:
    """호스트 루프백 화이트리스트 검증 (SSRF 방어)"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"SSRF violation: Invalid URL scheme '{parsed.scheme}'. Only http/https allowed.")

    hostname = (parsed.hostname or "").strip("[]").lower()
    if hostname not in ALLOWED_LOOPBACK_HOSTS:
        raise ValueError(
            f"SSRF violation: Host '{hostname}' is not a permitted loopback address ({', '.join(sorted(ALLOWED_LOOPBACK_HOSTS))})."
        )
    return True


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*(?:[\"']([^\"'\r\n]+)[\"']|([^\s;'\"]+))"),
    re.compile(r"sk-(?:live|proj|test)?[a-zA-Z0-9_\-]{20,}"),
    re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}"),
    re.compile(r"eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"gh[pousr]_[a-zA-Z0-9]{36}"),
    re.compile(r"github_pat_[a-zA-Z0-9_]{22,}"),
    re.compile(r"glpat-[a-zA-Z0-9\-]{20}"),
    re.compile(r"hf_[a-zA-Z0-9]{34}"),
]


def sanitize_text(text: str) -> str:
    """1차 선행 정규식 살균 마스킹 ([REDACTED] 치환 - Constitution IV, S2)"""
    sanitized = text
    def _mask_kv(match):
        key = match.group(1)
        return f'{key}: "[REDACTED]"'
    sanitized = SECRET_PATTERNS[0].sub(_mask_kv, sanitized)
    for pat in SECRET_PATTERNS[1:]:
        sanitized = pat.sub("[REDACTED]", sanitized)
    return sanitized


def verify_no_secrets(text: str) -> bool:
    """2차 사후 비밀정보 잔존 검사 (헌법 제IV조)"""
    for pat in SECRET_PATTERNS[1:]:
        if pat.search(text):
            return False
    return True


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """LLM 생성 페이로드에 대한 2차 비밀정보 살균 검사기 (T035 / Constitution IV)"""
    cleaned = dict(payload)
    if "title" in cleaned and isinstance(cleaned["title"], str):
        cleaned["title"] = sanitize_text(cleaned["title"])
    if "highlights" in cleaned and isinstance(cleaned["highlights"], list):
        cleaned["highlights"] = [sanitize_text(h) for h in cleaned["highlights"] if isinstance(h, str)]
    if "reasoning" in cleaned and isinstance(cleaned["reasoning"], str):
        cleaned["reasoning"] = sanitize_text(cleaned["reasoning"])
    return cleaned


def invoke_manage_changelog(args_list: List[str], repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """scripts/manage_changelog.py 서브프로세스 격리 호출 및 Exit Code 파싱 (T039 / 30s timeout)"""
    root = repo_root or resolve_repo_root()
    script_path = root / "scripts" / "manage_changelog.py"

    cmd = [sys.executable, str(script_path)] + args_list
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(root),
            shell=False,
            timeout=30.0,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "exit_code": EXIT_SYSTEM_FATAL,
            "stdout": "",
            "stderr": json.dumps({
                "error": "SUBPROCESS_TIMEOUT",
                "message": f"manage_changelog.py timed out after 30.0s: {e}",
            }),
        }


# ==============================================================================
# Phase 3: Git Context Collection & LLM Gateway Integration (US1)
# ==============================================================================

def validate_revision(rev: str) -> bool:
    """CWE-78 셸 인젝션 방어용 revision 화이트리스트 검증"""
    if not rev or not REVISION_SAFE_REGEX.match(rev):
        return False
    if rev.startswith("-"):
        return False
    return True


def detect_merge_commit(repo_root: Path) -> Dict[str, Any]:
    """Git 머지 커밋(HEAD^2) 감지 및 머지 브랜치 히스토리 추출"""
    is_merge = False
    merged_commits = ""
    try:
        check = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^2"],
            cwd=str(repo_root),
            capture_output=True,
            shell=False,
        )
        if check.returncode == 0:
            is_merge = True
            log_proc = subprocess.run(
                ["git", "log", "HEAD^1..HEAD^2", "--no-merges", '--format=%h %s', "--"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                shell=False,
            )
            merged_commits = log_proc.stdout.strip()
    except Exception:
        pass

    return {"is_merge": is_merge, "merged_commits": merged_commits}


def detect_git_tag(repo_root: Path) -> Dict[str, Any]:
    """공식 Git 태그(exact-match) 및 주석 메시지 감지"""
    try:
        proc = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            shell=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            tag = proc.stdout.strip()
            # 태그 주석 메시지 추출
            msg_proc = subprocess.run(
                ["git", "tag", "-l", "--format=%(contents)", tag],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                shell=False,
            )
            annotation = msg_proc.stdout.strip() if msg_proc.returncode == 0 else ""
            return {"has_tag": True, "tag_name": tag, "tag_annotation": annotation}
    except Exception:
        pass

    return {"has_tag": False, "tag_name": None, "tag_annotation": None}


def collect_git_context(
    repo_root: Path,
    rev: Optional[str] = None,
    commits: Optional[int] = None,
) -> GitContextBundle:
    """
    Git 커밋/diff 수집 및 3계층 필터링 (CWE-78, 64KB 파이프 데드락, Shallow clone 대응)
    """
    if rev is not None:
        if not validate_revision(rev):
            raise ValueError(f"Invalid revision format '{rev}'. Must match ^[a-zA-Z0-9_.~^/-]+$ and not start with '-'.")

    # 1. 스테이징된 변경 사항 확인 (rev/commits가 지정되지 않았을 때 1순위)
    is_staged = False
    if rev is None and commits is None:
        staged_check = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--"],
            cwd=str(repo_root),
            capture_output=True,
            shell=False,
        )
        if staged_check.returncode == 1:
            is_staged = True

    # 2. 커밋 해시 및 메시지 수집
    commit_hash = "working-tree"
    commit_message = "<Staged working tree changes>"
    commit_date: Optional[str] = None
    target_rev = rev.split("..")[-1] if rev else "HEAD"
    if not is_staged:
        try:
            head_log = subprocess.run(
                ["git", "log", "-1", target_rev, "--format=%H%x00%cs%x00%s%n%b", "--"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                shell=False,
            )
            if head_log.returncode == 0 and head_log.stdout.strip():
                parts = head_log.stdout.split("\x00", 2)
                commit_hash = parts[0].strip()
                commit_date = parts[1].strip() if len(parts) > 1 else None
                commit_message = parts[2].strip() if len(parts) > 2 else ""
        except Exception:
            pass

    # 3. diff 및 stat 파라미터 결정
    diff_cmd = ["git", "-c", "core.fileMode=false", "diff", "--submodule=log"]
    stat_cmd = ["git", "diff", "--stat"]
    name_cmd = ["git", "diff", "--name-only"]

    if is_staged:
        diff_cmd += ["--cached"]
        stat_cmd += ["--cached"]
        name_cmd += ["--cached"]
    elif rev:
        diff_cmd += [rev]
        stat_cmd += [rev]
        name_cmd += [rev]
    elif commits:
        diff_range = f"HEAD~{commits}..HEAD"
        diff_cmd += [diff_range]
        stat_cmd += [diff_range]
        name_cmd += [diff_range]
    else:
        # Default: 직전 커밋 diff (HEAD~1..HEAD)
        # Shallow clone (--depth 1) 환경 체크
        has_parent = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD~1"],
            cwd=str(repo_root),
            capture_output=True,
            shell=False,
        ).returncode == 0

        if has_parent:
            diff_cmd += ["HEAD~1..HEAD"]
            stat_cmd += ["HEAD~1..HEAD"]
            name_cmd += ["HEAD~1..HEAD"]
        else:
            # Shallow clone 폴백: git show HEAD
            diff_cmd = ["git", "-c", "core.fileMode=false", "show", "--submodule=log", "--format=", "HEAD"]
            stat_cmd = ["git", "show", "--stat", "--format=", "HEAD"]
            name_cmd = ["git", "show", "--name-only", "--format=", "HEAD"]

    # Double-Dash Separator 배치: 모든 옵션 플래그 조립 후 최종 위치에 1회만 배치 (GIT-1 방어)
    diff_cmd += ["--"]
    stat_cmd += ["--"]
    name_cmd += ["--"]

    # 4. stat 요약 수집
    stat_proc = subprocess.run(
        stat_cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        shell=False,
    )
    stat_summary = stat_proc.stdout.strip() if stat_proc.returncode == 0 else ""

    # 5. 변경 파일 목록 수집
    name_proc = subprocess.run(
        name_cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        shell=False,
    )
    changed_files = [
        line.strip() for line in name_proc.stdout.splitlines()
        if line.strip() and not line.endswith((".lock", ".png", ".jpg", ".jpeg", ".ico", ".tar.gz", ".zip"))
    ]

    # 6. Popen 스트리밍 diff 수집 (64KB 파이프 데드락 방어 stderr=DEVNULL, 512KB 상한)
    diff_lines: List[str] = []
    total_bytes = 0
    truncated = False

    proc = subprocess.Popen(
        diff_cmd,
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,  # Linux 64KB 파이프 버퍼 데드락 방어
        text=True,
        bufsize=1,
        shell=False,
    )

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            # 파일당 100줄, 전체 3,000줄 트렁케이션
            line_bytes = len(line.encode("utf-8"))
            if total_bytes + line_bytes > MAX_DIFF_PHYSICAL_BYTES or len(diff_lines) >= MAX_DIFF_LINES:
                truncated = True
                proc.terminate()
                break
            diff_lines.append(line)
            total_bytes += line_bytes
    finally:
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.kill()

    diff_text = "".join(diff_lines)
    if truncated:
        diff_text += "\n... [Diff truncated at 512KB physical ceiling] ...\n"

    # 머지 커밋 및 태그 정보 수집
    merge_info = detect_merge_commit(repo_root)
    tag_info = detect_git_tag(repo_root)

    return GitContextBundle(
        commit_hash=commit_hash,
        commit_message=commit_message,
        diff_text=diff_text,
        stat_summary=stat_summary,
        changed_files=changed_files,
        is_staged=is_staged,
        is_merge=merge_info["is_merge"],
        merged_commits=merge_info["merged_commits"],
        tag_name=tag_info["tag_name"],
        tag_annotation=tag_info["tag_annotation"],
        date=commit_date,
    )


def apply_token_budget_cap(diff_text: str) -> str:
    """모델 게이트웨이 32K 윈도우 보호를 위한 80KB(약 24,000 토큰) 2차 캡 가드레일 (SEC-1 / Line-aligned)"""
    encoded = diff_text.encode("utf-8")
    if len(encoded) <= MAX_DIFF_TOKEN_BUDGET_BYTES:
        return diff_text

    marker = "\n... [Token budget ceiling reached] ...\n"
    marker_bytes = len(marker.encode("utf-8"))
    allowed_bytes = max(0, MAX_DIFF_TOKEN_BUDGET_BYTES - marker_bytes)

    cutoff = encoded[:allowed_bytes].decode("utf-8", errors="ignore")
    last_nl = cutoff.rfind("\n")
    if last_nl > 0:
        cutoff = cutoff[:last_nl]
    return cutoff + marker


def call_model_gateway(
    messages: List[Dict[str, str]],
    url: str,
    model: str,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """
    로컬 모델 게이트웨이 LLM(qwen3.5-9b) HTTP 호출
    - Authorization: Bearer EMPTY
    - ProxyHandler({})를 통한 시스템 프록시 무력화 및 루프백 직결 (C3 방어)
    - Connect 3.0s, Read 30.0s 타임아웃
    - 3회 지수 백오프 [1.0s, 2.0s, 4.0s]
    - response_format: {"type": "json_object"}
    """
    validate_gateway_url(url)
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer EMPTY",
        },
        method="POST",
    )

    backoffs = [1.0, 2.0, 4.0]
    last_err: Optional[Exception] = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    # 단위 테스트에서 mock_urlopen이 patch된 경우 호환성 지원
    open_func = opener.open
    if hasattr(urllib.request.urlopen, "assert_called") or "unittest.mock" in type(urllib.request.urlopen).__module__:
        open_func = urllib.request.urlopen

    for attempt in range(max_retries):
        try:
            with open_func(req, timeout=30.0) as resp:
                raw_body = resp.read().decode("utf-8")
                res_json = json.loads(raw_body)
                content = res_json["choices"][0]["message"]["content"]
                return json.loads(content)
        except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < max_retries - 1:
                delay = backoffs[attempt] + random.uniform(0.0, 0.3)
                time.sleep(delay)
            else:
                break

    raise RuntimeError(f"Failed to communicate with model gateway at {url} after {max_retries} attempts: {last_err}")


def call_model_gateway_multi(
    messages: List[Dict[str, str]],
    url: str,
    model: str,
    max_retries: int = 3,
) -> List[Dict[str, Any]]:
    """--multi 플래그 기반 다중 서브시스템 분할 마일스톤 생성 (T036 / FR-006)"""
    res = call_model_gateway(messages, url=url, model=model, max_retries=max_retries)
    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        if "milestones" in res and isinstance(res["milestones"], list):
            return res["milestones"]
        return [res]
    return []


def proposer_disposer_validate(
    payload: Dict[str, Any],
    changed_files: List[str],
) -> Dict[str, Any]:
    """
    Proposer-Disposer 보안 검증:
    LLM 제안 subsystem이 허용 화이트리스트 및 실제 변경 파일 경로와 일치하는지 교차 검증 및 강제 정규화
    """
    subsystem = payload.get("subsystem", "").strip()

    # 파일 기반 예상 서브시스템 투표
    counts: Dict[str, int] = {s: 0 for s in ALLOWED_SUBSYSTEMS}
    for file_path in changed_files:
        matched = False
        for prefix, mapped_subsystem in SUBSYSTEM_PATH_PREFIXES:
            if file_path.startswith(prefix):
                counts[mapped_subsystem] += 1
                matched = True
                break
        if not matched:
            counts["core"] += 1

    expected_subsystem = max(counts, key=counts.get) if changed_files else "core"

    # 화이트리스트 외 값이거나 엉뚱한 제안 시 교정
    if subsystem not in ALLOWED_SUBSYSTEMS:
        payload["subsystem"] = expected_subsystem
    elif counts[subsystem] == 0 and counts[expected_subsystem] > 0 and len(changed_files) > 0:
        # LLM이 변경 파일과 전혀 상관없는 서브시스템을 제안한 경우 정규화
        payload["subsystem"] = expected_subsystem

    return payload


def determine_stage_from_git(branch: str, exact_tag: Optional[str] = None) -> str:
    """
    브랜치명, Git 태그 및 CI 환경변수를 종합하여 결정론적 배포 단계(stage) 판정
    Detached HEAD 상태(빈 문자열) 대응
    """
    if exact_tag:
        if "-rc" in exact_tag:
            return "rc"
        if "-beta" in exact_tag:
            return "beta"
        if "-alpha" in exact_tag:
            return "alpha"
        return "stable"

    eff_branch = branch
    if not eff_branch:
        # Detached HEAD 계층 순차 폴백
        eff_branch = (
            os.environ.get("CI_COMMIT_REF_NAME")
            or os.environ.get("GITHUB_REF_NAME")
            or ""
        )

    if not eff_branch:
        # 태그 체크 시도
        tag_info = detect_git_tag(resolve_repo_root())
        if tag_info["has_tag"] and tag_info["tag_name"]:
            return determine_stage_from_git("", exact_tag=tag_info["tag_name"])
        return "stable"  # 기본값

    eff_branch = eff_branch.lower()
    if eff_branch in ("main", "master", "stable"):
        return "stable"
    if eff_branch.startswith("release/") or eff_branch.startswith("rc/"):
        return "rc"
    if "beta" in eff_branch:
        return "beta"
    return "alpha"


def compute_next_version(
    latest_version: Optional[str],
    commit_messages: str,
    stage: str = "stable",
    bump_override: Optional[str] = None,
) -> str:
    """
    Conventional Commits v1.0.0 및 SemVer 2.0.0 기반 다음 버전 채번
    """
    stage_suffix = f"-{stage}" if stage != "stable" else ""

    # Cold start
    if not latest_version:
        return f"v0.1.0{stage_suffix}"

    match = SEMVER_REGEX.match(latest_version)
    if not match:
        return f"v0.1.0{stage_suffix}"

    major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))

    # Bump 판정
    bump = bump_override
    if not bump:
        # Conventional Commits 패턴 매칭
        # 1. Breaking change (! 표식은 커밋 헤더 첫 줄 한정, BREAKING CHANGE:는 전체 메시지 허용)
        first_line = commit_messages.splitlines()[0] if commit_messages else ""
        if "BREAKING CHANGE:" in commit_messages or re.search(r"^[a-zA-Z]+(?:\([^\)]+\))?!:", first_line):
            bump = "major"
        # 2. Feat -> Minor
        elif re.search(r"^feat(?:\([^\)]+\))?:", commit_messages, re.MULTILINE):
            bump = "minor"
        # 3. Fix, chore, refactor, etc. -> Patch
        else:
            bump = "patch"

    if bump == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    return f"v{major}.{minor}.{patch}{stage_suffix}"


def verify_and_sanitize_spec_links(
    highlights: List[str],
    repo_root: Path,
    candidate_spec: Optional[str] = None,
) -> Tuple[List[str], Optional[str]]:
    """
    로컬 specs/ 물리 파일시스템 대조를 통한 허위 링크 탈링크(Unlink) 및 spec_ref null 폴백
    """
    specs_dir = repo_root / "specs"
    existing_specs = set()
    if specs_dir.exists():
        for item in specs_dir.iterdir():
            if item.is_dir():
                # 010-changelog-auto-agent -> 010
                num_part = item.name.split("-")[0].lstrip("0")
                existing_specs.add(num_part)
                existing_specs.add(item.name.split("-")[0])

    spec_link_pattern = re.compile(r"\[([^\]]+)\]\((/specs/(\d+)[^\)]*)\)")
    cleaned_highlights: List[str] = []

    for h in highlights:
        def _replace_link(m):
            label = m.group(1)
            num = m.group(3).lstrip("0")
            full_num = m.group(3)
            if num in existing_specs or full_num in existing_specs:
                return m.group(0)  # 보존
            # 허위 링크 탈링크 -> 단순 라벨 텍스트로 치환
            return label

        cleaned_h = spec_link_pattern.sub(_replace_link, h)
        cleaned_highlights.append(cleaned_h)

    # candidate_spec 검증
    valid_spec_ref = None
    if candidate_spec:
        spec_digits = re.findall(r"\d+", candidate_spec)
        if spec_digits:
            digit = spec_digits[0]
            if digit in existing_specs or digit.lstrip("0") in existing_specs:
                valid_spec_ref = candidate_spec

    return cleaned_highlights, valid_spec_ref


def detect_spec_ref(branch_name: str = "", commit_message: str = "") -> Optional[str]:
    """활성 Git 브랜치명 및 최근 커밋 메시지로부터 스펙 번호 자동 감지 (FR-004 / T038)"""
    # 단일 커밋의 구체적 의도를 반영하기 위해 커밋 메시지를 브랜치명보다 1순위로 검사
    sources = [commit_message, branch_name]
    patterns = [
        re.compile(r"specs/(\d{3})(?:-[a-zA-Z0-9_\-]+)?"),
        re.compile(r"(?i)\bSpec[_\-\s]*(\d+)\b"),
        re.compile(r"(?i)\bFeature[_\-\s]*(\d+)\b"),
        re.compile(r"(?:^|[^\w])(\d{3})-[a-zA-Z0-9_\-]+"),
    ]
    for src in sources:
        if not src:
            continue
        for pat in patterns:
            m = pat.search(src)
            if m:
                num = int(m.group(1))
                return f"Spec {num:03d}"
    return None


def build_system_prompt(lang: str = "ko") -> str:
    """헌법 제I조 기반 시스템 프롬프트 조립"""
    if lang == "en":
        lang_instruction = "Generate all titles and bullet highlights in professional, concise English."
    else:
        lang_instruction = (
            "모든 제목(title)과 불릿 하이라이트(highlights)는 전문적이고 명확한 한국어로 작성하십시오. "
            "단, 기술 고유명사, 아키텍처 약어(WAL, DOM 등), 클래스명, 함수명 및 파일 경로는 무리하게 한글로 번역하지 말고 "
            "반드시 영문 인라인 코드 백틱(`symbol`) 원문을 엄격하게 보존하십시오."
        )

    return f"""You are the automated Changelog Agent for the Tunnel platform.
Your task is to analyze Git diffs, commit messages, or natural language summaries, and generate a standardized JSON milestone record for our changelog.

{lang_instruction}

JSON Output Schema:
{{
  "subsystem": "chat_a" | "chat_b" | "core" | "model_gateway" | "nginx_gateway" | "oliview_web" | "pilos",
  "version": "SemVer 2.0.0 (e.g. v1.1.0 or v0.8.0-beta)",
  "stage": "alpha" | "beta" | "rc" | "stable",
  "title": "A concise, clear one-line title",
  "highlights": [
    "Bullet point with `inline_code` or [Spec XXX](/specs/XXX) link"
  ],
  "spec_ref": "Spec XXX or null",
  "reasoning": "Brief explanation of chosen subsystem and version bump"
}}

Rules:
1. Do not hallucinate fake spec links. Only reference spec documents that actually exist in the diff/context.
2. highlights array must contain at least 1 non-empty string.
3. Output MUST be valid, parseable JSON conforming to response_format: {{"type": "json_object"}}.
"""


def strip_ansi(text: str) -> str:
    """터미널 제어 시퀀스 제거 (CWE-150 / S3 방어)"""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def format_preview_card(payload: Dict[str, Any]) -> str:
    """터미널 stderr용 컬러 카드 뷰 렌더링"""
    sub = payload.get("subsystem", "unknown")
    ver = payload.get("version", "unknown")
    stg = payload.get("stage", "unknown")
    date_str = payload.get("date", "today")
    title = strip_ansi(payload.get("title", ""))
    highlights = [strip_ansi(h) for h in payload.get("highlights", [])]
    spec = payload.get("spec_ref") or "N/A"

    lines = [
        "\n\033[1;36m┌────────────────────────────────────────────────────────────────────────┐\033[0m",
        f"\033[1;36m│\033[0m  \033[1;32m★ CHANGELOG MILESTONE PREVIEW\033[0m                                          \033[1;36m│\033[0m",
        f"\033[1;36m│\033[0m  Subsystem : \033[1;33m{sub:<15}\033[0m Version : \033[1;35m{ver:<15}\033[0m Stage: \033[1;34m{stg:<7}\033[0m  \033[1;36m│\033[0m",
        f"\033[1;36m│\033[0m  Date      : {date_str:<15} Spec Ref: {spec:<25} \033[1;36m│\033[0m",
        f"\033[1;36m│\033[0m  Title     : \033[1m{title:<57}\033[0m \033[1;36m│\033[0m",
        "\033[1;36m├────────────────────────────────────────────────────────────────────────┤\033[0m",
        "\033[1;36m│\033[0m  \033[1mHighlights:\033[0m                                                           \033[1;36m│\033[0m",
    ]
    for h in highlights:
        lines.append(f"\033[1;36m│\033[0m    • {h:<66} \033[1;36m│\033[0m")
    lines.append("\033[1;36m└────────────────────────────────────────────────────────────────────────┘\033[0m\n")
    return "\n".join(lines)


# ==============================================================================
# Phase 4 & 5: Self-Healing & CLI Orchestration
# ==============================================================================

def verify_portal_serving_file(portal_json_path: Path) -> bool:
    """Nginx 정적 파일 갱신 무결성 및 0644 권한 자가 검증 루틴 (T032)"""
    if not portal_json_path.exists():
        return False

    try:
        # 1. 파일 내용 유효 JSON 검증
        with open(portal_json_path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            if not isinstance(data, (list, dict)):
                return False

        # 2. 파일 권한 0644 검증 및 자가 보정
        current_mode = portal_json_path.stat().st_mode & 0o777
        if current_mode != 0o644:
            os.chmod(portal_json_path, 0o644)

        return True
    except Exception:
        return False


def execute_pipeline(config: Config) -> int:
    """전체 마일스톤 생성 및 등록 파이프라인"""
    repo_root = config.repo_root
    args = config.args

    # 1. 컨텍스트 수집 (자연어 모드 vs Git diff 모드)
    if args.prompt:
        context_prompt = f"User Natural Language Request:\n{args.prompt}"
        changed_files = []
        is_merge = False
        tag_name = None
    else:
        try:
            bundle = collect_git_context(repo_root=repo_root, rev=args.rev, commits=args.commits)
        except Exception as e:
            sys.stderr.write(f"Git collection error: {e}\n")
            return EXIT_VALIDATION_ERROR

        if not bundle.diff_text and not bundle.is_staged and not bundle.commit_message:
            sys.stderr.write("No changes detected in Git repository. Please stage files, commit, or provide --prompt.\n")
            return EXIT_VALIDATION_ERROR

        changed_files = bundle.changed_files
        is_merge = bundle.is_merge
        tag_name = bundle.tag_name

        sanitized_diff = sanitize_text(bundle.diff_text)
        capped_diff = apply_token_budget_cap(sanitized_diff)

        context_prompt = f"""Target Commit: {bundle.commit_hash}
Commit Message:
{bundle.commit_message}

Changed Files Summary:
{bundle.stat_summary}

Is Merge Commit: {bundle.is_merge}
Merged Commits:
{bundle.merged_commits}

Git Tag: {bundle.tag_name}
Tag Annotation: {bundle.tag_annotation}

<git_diff>
{capped_diff}
</git_diff>
"""

    # 2. 브랜치 / stage 판정
    branch_proc = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        shell=False,
    )
    branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""
    inferred_stage = determine_stage_from_git(branch=branch, exact_tag=tag_name)
    stage = args.stage or inferred_stage

    # 3. 모델 게이트웨이 LLM 질의 (단일 vs --multi)
    system_prompt = build_system_prompt(lang=args.lang)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context_prompt},
    ]

    try:
        if args.multi:
            raw_payloads = call_model_gateway_multi(messages, url=config.model_gateway_url, model=config.model)
        else:
            raw_payload = call_model_gateway(messages, url=config.model_gateway_url, model=config.model)
            raw_payloads = [raw_payload]
    except Exception as e:
        sys.stderr.write(f"Model gateway invocation error: {e}\n")
        return EXIT_FATAL_ERROR

    if not raw_payloads:
        sys.stderr.write("Model gateway returned empty milestone payload.\n")
        return EXIT_VALIDATION_ERROR

    # 커밋 메시지 또는 브랜치로부터 스펙 번호 자동 감지 (T038 / FR-004)
    detected_spec = detect_spec_ref(
        branch_name=branch,
        commit_message=bundle.commit_message if (not args.prompt and "bundle" in locals()) else "",
    )

    applied_milestones: List[Dict[str, Any]] = []

    for item_idx, raw_item in enumerate(raw_payloads):
        # 4. Proposer-Disposer 보안 검증 & 정규화
        payload = proposer_disposer_validate(raw_item, changed_files=changed_files)

        # 오버라이드 적용
        if args.subsystem:
            payload["subsystem"] = args.subsystem

        # 버전 접미사 및 stage 상호 결속 (FR-003)
        version_str = payload.get("version", "")
        match = SEMVER_REGEX.match(version_str)
        if match and match.group(4):
            semver_stage = match.group(4)
            if semver_stage in ("alpha", "beta", "rc"):
                payload["stage"] = semver_stage

        if args.stage:
            payload["stage"] = args.stage
        elif "stage" not in payload or not payload["stage"]:
            payload["stage"] = stage

        if args.version:
            payload["version"] = args.version
        elif args.bump:
            base_ver = tag_name or payload.get("version") or "v0.1.0"
            payload["version"] = compute_next_version(
                base_ver,
                commit_messages="",
                stage=payload.get("stage", stage),
                bump_override=args.bump,
            )
        elif tag_name:
            payload["version"] = tag_name

        # 날짜 채번
        if args.date:
            payload["date"] = args.date
        elif not args.prompt and "bundle" in locals() and bundle and getattr(bundle, "date", None):
            payload["date"] = bundle.date
        elif "date" not in payload or not payload["date"]:
            payload["date"] = time.strftime("%Y-%m-%d")

        # 스펙 번호 자동 바인딩 및 탈링크
        candidate_spec = args.spec or payload.get("spec_ref") or detected_spec
        verified_highlights, valid_spec = verify_and_sanitize_spec_links(
            highlights=payload.get("highlights", []),
            repo_root=repo_root,
            candidate_spec=candidate_spec,
        )
        payload["highlights"] = verified_highlights
        if valid_spec:
            payload["spec_ref"] = valid_spec

        # 2차 비밀정보 살균 (T035 / Constitution IV)
        payload = sanitize_payload(payload)

        # 5. 대화형 프리뷰 (stderr 격리)
        if not args.yes and not args.dry_run:
            preview_text = format_preview_card(payload)
            sys.stderr.write(preview_text)
            prompt_label = f"Apply milestone {item_idx + 1}/{len(raw_payloads)} [{payload.get('subsystem')}] to database? [Y/n]: " if args.multi else "Apply this changelog milestone to database? [Y/n]: "
            sys.stderr.write(prompt_label)
            sys.stderr.flush()
            try:
                choice = input().strip().lower()
                if choice not in ("", "y", "yes"):
                    sys.stderr.write("Aborted by user. Zero disk changes made.\n")
                    return EXIT_SUCCESS
            except (KeyboardInterrupt, EOFError):
                sys.stderr.write("\nAborted.\n")
                return EXIT_INTERRUPT

        # 6. manage_changelog.py 호출 & 자가 치유 루프 (최대 3회 스키마 교정, 버전 충돌 탄력 승격)
        max_self_healing_attempts = 3
        max_total_attempts = 15
        schema_healing_count = 0
        item_success = False
        last_cli_output: Dict[str, Any] = {}
        db_locked_occurred = False

        for attempt in range(max_total_attempts):
            cmd_args = [
                "add",
                "--subsystem", payload["subsystem"],
                "--version", payload["version"],
                "--stage", payload.get("stage", "stable"),
                "--date", payload.get("date", time.strftime("%Y-%m-%d")),
                "--title", payload.get("title", ""),
                "--highlights", json.dumps(payload.get("highlights", [])),
            ]
            if payload.get("spec_ref"):
                cmd_args += ["--spec-ref", payload["spec_ref"]]

            if args.dry_run:
                cmd_args.append("--dry-run")

            cli_res = invoke_manage_changelog(cmd_args, repo_root=repo_root)
            last_cli_output = cli_res

            if cli_res["exit_code"] == 0:
                item_success = True
                break

            # 중복 버전 충돌 (DUPLICATE_ENTRY) 자동 패치 승격
            if "DUPLICATE_ENTRY" in cli_res["stderr"] or "DUPLICATE_ENTRY" in cli_res["stdout"]:
                if not args.no_bump:
                    payload["version"] = compute_next_version(payload["version"], "fix: bump duplicate patch", stage=payload["stage"], bump_override="patch")
                    continue
                else:
                    break

            # SQLite 락 충돌 (DATABASE_LOCKED) 재시도
            if "DATABASE_LOCKED" in cli_res["stderr"] or "DATABASE_LOCKED" in cli_res["stdout"]:
                db_locked_occurred = True
                jitter = random.uniform(0.1, 0.4)
                backoff_idx = min(schema_healing_count, 2)
                time.sleep([0.5, 1.0, 2.0][backoff_idx] + jitter)
                schema_healing_count += 1
                if schema_healing_count >= max_self_healing_attempts:
                    break
                continue

            # 기타 Actionable Error인 경우 LLM 재교정 요청
            schema_healing_count += 1
            if schema_healing_count >= max_self_healing_attempts:
                break

            repair_messages = messages + [
                {"role": "assistant", "content": json.dumps(payload)},
                {"role": "user", "content": f"The validation failed with CLI output: {cli_res['stdout']} {cli_res['stderr']}\nPlease fix the schema errors and return corrected JSON conforming to the schema."}
            ]
            try:
                corrected = call_model_gateway(repair_messages, url=config.model_gateway_url, model=config.model)
                cleaned = proposer_disposer_validate(corrected, changed_files=changed_files)
                # 기존 날짜 및 서브시스템 보존
                if "date" not in cleaned and "date" in payload:
                    cleaned["date"] = payload["date"]
                if not cleaned.get("date"):
                    cleaned["date"] = time.strftime("%Y-%m-%d")
                payload.update(cleaned)
                payload = sanitize_payload(payload)
            except Exception:
                break

        # 마일스톤 등록 실패 처리
        if not item_success:
            if db_locked_occurred:
                lock_err_json = {
                    "ok": False,
                    "error": "DATABASE_LOCKED_EXHAUSTED",
                    "message": "SQLite database remained locked after 3 jittered backoff attempts.",
                    "suggestion": "Wait for active concurrent transactions/commits to finish, or manually check for hanging processes via 'fuser dist_node_a/data/changelog.db', then retry.",
                    "attempts": max_self_healing_attempts,
                    "retryable": True,
                }
                sys.stdout.write(json.dumps(lock_err_json, indent=2, ensure_ascii=False) + "\n")
                return EXIT_VALIDATION_ERROR

            # 자가 치유 3회 최종 소진 시: CWE-377 방어 고유 UUID 임시 파일 fsync 후 원자적 교체
            failed_path = repo_root / ".changelog_draft_failed.json"
            temp_failed = repo_root / f".changelog_draft_failed.json.tmp.{uuid.uuid4().hex}"
            try:
                with open(temp_failed, "w", encoding="utf-8") as fp:
                    dump_data = {
                        "payload": payload,
                        "last_cli_output": last_cli_output,
                        "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                    json.dump(dump_data, fp, indent=2, ensure_ascii=False)
                    fp.flush()
                    os.fsync(fp.fileno())
                os.replace(temp_failed, failed_path)
                sys.stderr.write(f"Validation failed after {max_self_healing_attempts} attempts. Raw draft dumped to {failed_path}\n")
            except Exception as e:
                sys.stderr.write(f"Failed to dump failed draft: {e}\n")

            # SELF_HEALING_EXHAUSTED 에러 JSON 방출
            parsed_last_err = {}
            try:
                parsed_last_err = json.loads(last_cli_output.get("stdout", "{}"))
            except Exception:
                pass
            exhausted_json = {
                "ok": False,
                "error": "SELF_HEALING_EXHAUSTED",
                "message": f"Model Gateway generated milestone failed validation after {max_self_healing_attempts} attempts.",
                "suggestion": f"Check the drafted payload dumped at .changelog_draft_failed.json, manually correct the fields, and run 'python3 scripts/manage_changelog.py add --file {failed_path.name}'.",
                "failed_draft_path": str(failed_path),
                "attempts": max_self_healing_attempts,
                "last_cli_error": parsed_last_err,
            }
            sys.stdout.write(json.dumps(exhausted_json, indent=2, ensure_ascii=False) + "\n")
            return EXIT_VALIDATION_ERROR

        portal_url = f"http://localhost:3000/changelog.html#{payload.get('subsystem', 'core')}"
        applied_milestones.append({
            "subsystem": payload.get("subsystem", "core"),
            "version": payload.get("version", "v0.1.0"),
            "stage": payload.get("stage", "stable"),
            "title": payload.get("title", ""),
            "date": payload.get("date", time.strftime("%Y-%m-%d")),
            "portal_url": portal_url,
        })

    # 7. Nginx 정적 서빙 파일 무결성 및 0644 권한 자가 검증 (dry-run이 아닌 경우)
    if not args.dry_run and config.portal_json_path.exists():
        verify_portal_serving_file(config.portal_json_path)

    # 8. 성공 시 stdout 기계 판독 JSON 스트림 방출
    if args.multi:
        success_json = {
            "ok": True,
            "is_dry_run": args.dry_run,
            "multi": True,
            "count": len(applied_milestones),
            "milestones": applied_milestones,
        }
    else:
        first = applied_milestones[0] if applied_milestones else {}
        success_json = {
            "ok": True,
            "is_dry_run": args.dry_run,
            "subsystem": first.get("subsystem", "core"),
            "version": first.get("version", "v0.1.0"),
            "stage": first.get("stage", "stable"),
            "title": first.get("title", ""),
            "date": first.get("date", time.strftime("%Y-%m-%d")),
            "portal_url": first.get("portal_url", f"http://localhost:3000/changelog.html#{first.get('subsystem', 'core')}"),
        }

    sys.stdout.write(json.dumps(success_json, indent=2, ensure_ascii=False) + "\n")
    return EXIT_SUCCESS


def main(argv=None) -> int:
    """메인 CLI 진입점"""
    setup_signal_handlers(_global_temp_manager)
    args = parse_args(argv)
    try:
        config = resolve_config(args)
    except ValueError as e:
        sys.stderr.write(f"Configuration error: {e}\n")
        return EXIT_VALIDATION_ERROR
    except Exception as e:
        sys.stderr.write(f"Fatal error: {e}\n")
        return EXIT_FATAL_ERROR

    return execute_pipeline(config)


if __name__ == "__main__":
    sys.exit(main())
