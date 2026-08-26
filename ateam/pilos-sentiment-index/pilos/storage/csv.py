from pathlib import Path

import pandas as pd


def save_csv_records(
    *,
    records: list[dict],
    output_path: Path,
) -> int:
    """
    동일한 필드 구조의 dict 목록을 검수용 CSV 파일로 저장한다.

    입력:
    - records: 각 dict가 CSV 한 행을 나타내는 비어 있지 않은 목록이다.
      첫 행의 key 순서를 CSV 열 순서로 사용하며 모든 행은 같은 key를
      가져야 한다.
    - output_path: 생성할 .csv 파일 경로다. 부모 폴더가 없으면 만든다.

    출력:
    - 헤더를 제외하고 실제 저장한 데이터 행 수를 반환한다.

    Excel에서 한글을 바로 열어도 깨지지 않도록 UTF-8 BOM 인코딩을
    사용한다. DataFrame index는 저장하지 않는다.
    """
    output_path = Path(output_path)

    if output_path.suffix.lower() != ".csv":
        raise ValueError(
            "output_path의 확장자는 .csv여야 합니다."
        )

    if not records:
        raise ValueError(
            "CSV로 저장할 records가 비어 있습니다."
        )

    expected_columns = tuple(records[0].keys())

    if not expected_columns:
        raise ValueError(
            "CSV 첫 행에 저장할 필드가 없습니다."
        )

    expected_column_set = set(expected_columns)

    for row_number, record in enumerate(
        records,
        start=1,
    ):
        if set(record.keys()) != expected_column_set:
            raise ValueError(
                "CSV 행마다 필드가 같아야 합니다: "
                f"row={row_number}"
            )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    dataframe = pd.DataFrame.from_records(
        records,
        columns=expected_columns,
    )
    dataframe.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
        float_format="%.12g",
        date_format="%Y-%m-%d",
        lineterminator="\n",
    )

    return len(dataframe)
