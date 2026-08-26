"""A-Team Background Service Pipeline Worker Daemon.

Periodically runs the 7-stage service pipeline (comment collection -> preprocessing ->
tokenization -> daily documents -> supply/demand -> Ridge inference -> LLM report)
and updates the service_pipeline_run table in MySQL.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()

from pilos.jobs.run_service_pipeline import (
    PipelineAlreadyRunningError,
    acquire_pipeline_lock,
    configure_pipeline_file_logging,
    run_tracked_service_pipeline,
)

logger = logging.getLogger("pilos.worker_daemon")
KST = ZoneInfo("Asia/Seoul")

_STOP_REQUESTED = False


def _signal_handler(signum, frame):
    global _STOP_REQUESTED
    logger.info(f"종료 시그널 수신 (Signal: {signum}). 현재 작업 완료 후 데몬을 정상 종료합니다.")
    _STOP_REQUESTED = True


def run_daemon_loop():
    """주기적으로 서비스 파이프라인을 실행하는 메인 데몬 루프."""
    global _STOP_REQUESTED

    interval_seconds = int(os.getenv("PIPELINE_INTERVAL_SECONDS", "600"))
    initial_delay = int(os.getenv("PIPELINE_INITIAL_DELAY_SECONDS", "10"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    configure_pipeline_file_logging()

    logger.info("================================================================")
    logger.info("  A-Team Pilos Background Pipeline Worker Daemon Started")
    logger.info(f"  - Execution Interval: {interval_seconds}s ({interval_seconds // 60}m)")
    logger.info(f"  - Initial Boot Delay: {initial_delay}s")
    logger.info(f"  - DB Target: {os.getenv('DB_HOST', 'pilos-db')}:{os.getenv('DB_PORT', '3306')}/{os.getenv('DB_NAME', 'pilos_v2')}")
    logger.info("================================================================")

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    if initial_delay > 0:
        logger.info(f"초기 DB 안정화를 위해 {initial_delay}초 대기 후 첫 배치를 실행합니다...")
        time.sleep(initial_delay)

    run_count = 0
    while not _STOP_REQUESTED:
        run_count += 1
        now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"\n[Run #{run_count} @ {now_str}] 서비스 파이프라인 정기 실행 시작...")

        try:
            with acquire_pipeline_lock():
                summary = run_tracked_service_pipeline(target=None)
                logger.info(
                    f"[Run #{run_count}] 파이프라인 완료: 상태={summary.status}, "
                    f"소요시간={summary.elapsed_seconds:.2f}초, 완료단계수={len(summary.stages)}"
                )
        except PipelineAlreadyRunningError as e:
            logger.warning(f"[Run #{run_count}] 이전 파이프라인 작업이 아직 진행 중입니다. 이번 주기를 건너뜁니다: {e}")
        except Exception as e:
            logger.exception(f"[Run #{run_count}] 파이프라인 실행 중 예외 발생: {e}")

        if _STOP_REQUESTED:
            break

        logger.info(f"다음 실행까지 {interval_seconds}초 대기합니다...")
        # Check stop signal in 1-second chunks for responsive shutdown
        for _ in range(interval_seconds):
            if _STOP_REQUESTED:
                break
            time.sleep(1)

    logger.info("A-Team Pilos Worker Daemon이 정상적으로 종료되었습니다.")


if __name__ == "__main__":
    run_daemon_loop()
