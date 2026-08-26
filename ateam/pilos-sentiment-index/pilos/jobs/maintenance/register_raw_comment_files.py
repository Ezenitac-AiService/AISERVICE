"""원본 JSONL(raw) 파일들의 메타데이터를 source_comment_file 테이블에 일괄 등록한다.

이미 수집돼 있는 data/raw 의 until_*/from_* 파일을 훑어, 파일명에 든 종목명으로
stock_id 를 찾아 source 로 등록한다(초기 적재/보정용). 멱등(UPSERT).

실행: uv run python -m pilos.jobs.maintenance.register_raw_comment_files
"""
import sys
from pathlib import Path

from pilos.storage.comment_db import (
    CommentDBUnavailableError,
    require_connection,
)

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "raw"
INPUT_PATTERNS = ["until_*.jsonl", "from_*.jsonl"]


def input_to_db(input_dir: str | Path, input_patterns: list[str]) -> int:
    """input_dir 에서 패턴에 맞는 원본 파일을 찾아 source 로 등록하고, 등록 성공 건수를 반환한다."""
    db_connecter = require_connection()
    stocks = db_connecter.select_stock()   # (stock_id, stock_name, subject_id) 목록
    # 여러 패턴을 모아 중복 제거 후 정렬한다(glob 은 단일 패턴만 받으므로 패턴별로 모은다).
    input_paths = sorted({
        p for pattern in input_patterns for p in Path(input_dir).glob(pattern)
    })

    inserted = 0
    for input_path in input_paths:
        try:
            file_str = input_path.name
            # 절대경로 대신 프로젝트 기준 상대경로로 저장한다(예: "data/raw"). as_posix 로 슬래시 통일.
            file_path = input_path.parent.relative_to(DATA_DIR).as_posix()
            file_name = file_str.split(".")[0]
            file_ext = file_str.split(".")[1] if "." in file_str else ""

            # 파일명 토큰(_ 구분) 중에 종목명이 정확히 있으면 그 종목으로 본다(부분일치 오매칭 방지).
            tokens = file_name.split("_")
            match = next(((sid, sname) for sid, sname, _ in stocks if sname in tokens), None)
            if match is None:
                print(f"[건너뜀] 매칭되는 종목 없음: {file_str}")
                continue
            stock_id, _stock_name = match

            file_source = {
                "stock_id": stock_id,
                "file_path": file_path,
                "file_name": file_name,
                "file_ext": file_ext,
                "platform": "TOSS",
            }
            db_connecter.insert_source(file_source)
            inserted += 1
        except Exception as e:  # noqa: BLE001
            print(f"[오류] {input_path.name}: {e}")

    return inserted


if __name__ == "__main__":
    try:
        count = input_to_db(INPUT_DIR, INPUT_PATTERNS)
    except CommentDBUnavailableError as e:
        print(f"[중단] DB 접속 실패로 source 등록을 시작하지 못했습니다: {e}")
        sys.exit(1)
    print(f"source 등록 완료: {count}건")
