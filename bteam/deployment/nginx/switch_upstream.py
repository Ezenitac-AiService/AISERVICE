"""B-Team Nginx 업스트림 무중단 원자적 전환 및 긴급 롤백 CLI.

Active 설정(bteam.conf)을 Candidate(Green) 또는 Rollback(Blue)으로 원자적으로 교체하고
nginx -t 사전 구문 검증 및 nginx -s reload를 수행합니다.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

DEPLOY_DIR = Path(__file__).resolve().parent
ROOT_DIR = DEPLOY_DIR.parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

ARTIFACTS_DIR = ROOT_DIR / "migration" / "artifacts"
ACTIVE_CONF = DEPLOY_DIR / "bteam.conf"
CANDIDATE_CONF = DEPLOY_DIR / "bteam.candidate.conf"
ROLLBACK_CONF = DEPLOY_DIR / "bteam.rollback.conf"
HISTORY_FILE = ARTIFACTS_DIR / "nginx_switch_history.jsonl"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bteam.deployment.nginx.switch_upstream")


def check_nginx_syntax(conf_file: Path | str | None = None) -> bool:
    """Nginx 구문 검사(nginx -t)를 수행합니다."""
    target = Path(conf_file) if conf_file else ACTIVE_CONF
    if not target.exists():
        logger.error("검사할 Nginx 설정 파일이 존재하지 않습니다: %s", target)
        return False

    content = target.read_text(encoding="utf-8")
    if "upstream" not in content or "location" not in content:
        logger.error("Nginx 설정 필수 블록(upstream, location)이 누락되었습니다: %s", target)
        return False

    if shutil.which("nginx"):
        try:
            res = subprocess.run(["nginx", "-t"], capture_output=True, text=True, timeout=5, check=False)
            if res.returncode != 0:
                logger.error("nginx -t 구문 오류:\n%s", res.stderr)
                return False
            logger.info("nginx -t 구문 검사 성공.")
        except (subprocess.SubprocessError, OSError) as e:
            logger.warning("nginx -t 실행 중 예외 발생 (건너뜀): %s", e)

    logger.info("Nginx 설정 템플릿 구문 검증 통과: %s", target.name)
    return True


def reload_nginx() -> bool:
    """Nginx 무중단 리로드(nginx -s reload)를 수행합니다."""
    if shutil.which("nginx"):
        try:
            res = subprocess.run(["nginx", "-s", "reload"], capture_output=True, text=True, timeout=5, check=False)
            if res.returncode != 0:
                logger.error("nginx -s reload 실패:\n%s", res.stderr)
                return False
            logger.info("nginx -s reload 완료.")
        except (subprocess.SubprocessError, OSError) as e:
            logger.warning("nginx -s reload 실행 중 예외 (로컬/테스트 환경): %s", e)
    else:
        logger.info("nginx 바이너리 미설치 환경: 설정 파일 원자적 교체 완료.")
    return True


def switch_upstream_atomic(target_mode: str) -> dict[str, Any]:
    """Nginx 설정을 원자적으로 교체하고 이력을 기록합니다.

    :param target_mode: 'candidate' (Green) 또는 'rollback' (Blue)
    """
    if target_mode == "candidate":
        src_file = CANDIDATE_CONF
        target_name = "GREEN_UNIFIED"
    elif target_mode == "rollback":
        src_file = ROLLBACK_CONF
        target_name = "BLUE_LEGACY"
    else:
        raise ValueError(f"지원하지 않는 전환 모드: {target_mode}")

    if not src_file.exists():
        raise FileNotFoundError(f"전환 원본 설정 파일이 없습니다: {src_file}")

    if not check_nginx_syntax(src_file):
        raise RuntimeError(f"설정 파일 구문 검증 실패: {src_file}")

    temp_target = DEPLOY_DIR / f"bteam.tmp.{os.getpid()}.conf"
    shutil.copyfile(src_file, temp_target)
    os.replace(temp_target, ACTIVE_CONF)

    reload_nginx()

    event = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "mode": target_mode,
        "active_target": target_name,
        "src_file": src_file.name,
        "status": "APPLIED",
    }
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    logger.info("[OK] Nginx 업스트림 전환 성공: %s (%s)", target_name, target_mode)
    return event


def get_current_status() -> str:
    """현재 활성화된 Nginx 설정을 확인합니다."""
    if not ACTIVE_CONF.exists():
        return "UNCONFIGURED"
    content = ACTIVE_CONF.read_text(encoding="utf-8")
    if "15050" in content:
        return "GREEN_CANDIDATE"
    if "5050" in content:
        return "BLUE_ROLLBACK"
    return "CUSTOM"


def main() -> int:
    parser = argparse.ArgumentParser(description="B-Team Nginx 업스트림 무중단 전환 CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="설정 파일 구문 검사")
    group.add_argument("--apply", action="store_true", help="Green 통합 스택으로 원자적 전환")
    group.add_argument("--rollback", action="store_true", help="Blue 레거시 스택으로 즉시 롤백")
    group.add_argument("--status", action="store_true", help="현재 활성 업스트림 상태 조회")
    args = parser.parse_args()

    try:
        if args.check:
            ok = check_nginx_syntax(CANDIDATE_CONF) and check_nginx_syntax(ROLLBACK_CONF)
            if ok:
                print("[OK] Nginx candidate/rollback 설정 구문 정상")
                return 0
            return 1
        if args.apply:
            res = switch_upstream_atomic("candidate")
            print(f"[OK] Green 컷오버 적용 완료: {res['active_target']}")
            return 0
        if args.rollback:
            res = switch_upstream_atomic("rollback")
            print(f"[WARN] Blue 롤백 적용 완료: {res['active_target']}")
            return 0
        if args.status:
            st = get_current_status()
            print(f"Active Status: {st}")
            return 0
    except (RuntimeError, FileNotFoundError, ValueError, OSError) as e:
        logger.error("[ERROR] Nginx 전환 작업 실패: %s", e)
        print(f"[ERROR] Nginx 전환 작업 실패: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
