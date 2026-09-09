"""러너(진입점) 공용 로깅 설정 (P3-5/P3-6).

라이브러리 모듈(collection/storage/*)은 `logging.getLogger(__name__)`만 두고, 실제
핸들러 설정은 실행기 main 에서 이 함수를 한 번만 호출한다. 로그는 소스 폴더가 아니라
data/raw/logs 아래 실행 날짜별 파일과 콘솔에 함께 남긴다.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pilos.storage.json_io import get_logs_dir

KST = ZoneInfo("Asia/Seoul")


def setup_logging(level=logging.INFO):
    """콘솔 + data/raw/logs/crawl_YYYYMMDD.log 로 로깅을 설정한다(중복 설정 방지)."""
    root = logging.getLogger()
    if root.handlers:                       # 이미 설정됐으면 재설정하지 않음
        return
    date_key = datetime.now(KST).strftime("%Y%m%d")
    log_file = get_logs_dir() / f"crawl_{date_key}.log"
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),        # 콘솔에도 출력
        ],
    )
