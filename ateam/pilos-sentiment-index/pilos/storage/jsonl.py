import json
from collections.abc import Iterator
from pathlib import Path


def iter_jsonl_records(
    jsonl_path: str | Path,
    start_after_line: int = 0,
) -> Iterator[dict]:
    """JSONL 파일을 한 줄씩 읽어 프로젝트 표준 댓글 레코드로 변환하여 반환한다.

    start_after_line: 이 물리적 줄 번호 이하는 파싱하지 않고 건너뛴다(증분 전처리 watermark).
    0(기본)이면 파일 전체를 읽는다. raw 파일은 append-only 이고 각 레코드의
    raw_line_number 가 물리적 줄 번호와 일치하므로, 이미 전처리된 최대 줄번호를
    넘겨주면 새로 추가된 줄만 읽는다.
    """
    # 문자열 또는 Path 입력을 동일한 Path 객체로 변환
    path = Path(jsonl_path)
    # UTF-8 BOM이 있는 파일과 없는 파일을 모두 읽을 수 있도록 utf-8-sig 사용
    with path.open("r", encoding="utf-8-sig") as file:
        for line_number, line in enumerate(file, start=1):
            # [변경 2026-08-03] start_after_line 파라미터 신설.
            # 이전: 항상 파일 전체를 파싱. 이후: watermark 이하 줄은 JSON 파싱 없이
            # 건너뛴다(증분 전처리에서 이미 처리한 앞부분을 매번 다시 안 읽도록).
            if line_number <= start_after_line:
                continue
            # 공백과 개행을 제거한 뒤 빈 줄은 제외
            stripped_line = line.strip()
            if not stripped_line:
                continue
            # 문법적으로 잘못된 json은 예외처리한다
            try:
                # JSON 문자열을 Python 객체로 파싱한다
                record = json.loads(stripped_line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    "JSONL 파싱에 실패했습니다. "
                    f"파일={path}, 줄={line_number}"
                ) from error
            # 변환된 레코드가 dict가 아니라면 예외를 발생시킨다
            if not isinstance(record, dict):
                raise ValueError(
                    "JSONL 레코드는 JSON 객체여야 합니다. "
                    f"파일={path}, 줄={line_number}"
                )
            record.setdefault(
                "raw_line_number",
                line_number,
            )
            # 최종적으로 처리된 레코드 하나를 반환한다
            yield record
