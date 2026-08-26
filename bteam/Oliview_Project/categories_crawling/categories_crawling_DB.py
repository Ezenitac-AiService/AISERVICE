# uv add mysql-connector-python python-dotenv
# uv run python categories_crawling/categories_crawling_DB.py

import csv
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent

# 프로젝트 루트를 Python 모듈 검색 경로에 추가
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from common.db_manager import DBManager


CSV_FILE = CURRENT_DIR / "Categories_ID.csv"


def insert_category(
    db: DBManager,
    category_code: str,
    parent_category_id: int | None,
    category_name: str,
    category_level: int,
) -> int:
    """
    카테고리를 저장하고 category_id를 반환합니다.

    동일한 category_code가 이미 존재하면
    상위 카테고리, 이름, 레벨을 갱신합니다.

    is_target은 수정하지 않습니다.
    """
    query = """
        INSERT INTO categories (
            category_code,
            parent_category_id,
            category_name,
            category_level
        )
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            parent_category_id = VALUES(parent_category_id),
            category_name = VALUES(category_name),
            category_level = VALUES(category_level)
    """

    db.execute(
        query,
        (
            category_code,
            parent_category_id,
            category_name,
            category_level,
        ),
    )

    db.execute(
        """
        SELECT category_id
        FROM categories
        WHERE category_code = %s
        """,
        (category_code,),
    )

    result = db.fetchone()

    if result is None:
        raise RuntimeError(
            f"category_id 조회 실패: {category_code}"
        )

    # dictionary=True 커서인 경우
    if isinstance(result, dict):
        return result["category_id"]

    # 일반 커서인 경우
    return result[0]


def save_categories() -> None:
    if not CSV_FILE.exists():
        raise FileNotFoundError(
            f"CSV 파일을 찾을 수 없습니다: {CSV_FILE}"
        )

    # category_code -> category_id
    category_map: dict[str, int] = {}

    with DBManager() as db:
        with open(
            CSV_FILE,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            reader = csv.DictReader(file)

            required_columns = {
                "Major_Category",
                "Major_Category_ID",
                "Intermediate_Category",
                "Intermediate_Category_ID",
                "Sub_Category",
                "Sub_Category_ID",
            }

            if reader.fieldnames is None:
                raise ValueError("CSV 헤더가 없습니다.")

            missing_columns = required_columns - set(reader.fieldnames)

            if missing_columns:
                raise ValueError(
                    f"CSV에 필요한 컬럼이 없습니다: "
                    f"{', '.join(sorted(missing_columns))}"
                )

            for row_number, row in enumerate(reader, start=2):
                major_name = row["Major_Category"].strip()
                major_code = row["Major_Category_ID"].strip()

                middle_name = row["Intermediate_Category"].strip()
                middle_code = row["Intermediate_Category_ID"].strip()

                sub_name = row["Sub_Category"].strip()
                sub_code = row["Sub_Category_ID"].strip()

                try:
                    if not major_code or not major_name:
                        raise ValueError(
                            "대분류 코드 또는 이름이 비어 있습니다."
                        )

                    if not middle_code or not middle_name:
                        raise ValueError(
                            "중분류 코드 또는 이름이 비어 있습니다."
                        )

                    # 1. 대분류 저장
                    if major_code not in category_map:
                        major_id = insert_category(
                            db=db,
                            category_code=major_code,
                            parent_category_id=None,
                            category_name=major_name,
                            category_level=1,
                        )

                        category_map[major_code] = major_id

                    # 2. 중분류 저장
                    if middle_code not in category_map:
                        middle_id = insert_category(
                            db=db,
                            category_code=middle_code,
                            parent_category_id=category_map[major_code],
                            category_name=middle_name,
                            category_level=2,
                        )

                        category_map[middle_code] = middle_id

                    # 3. '전체'는 별도 카테고리로 저장하지 않음
                    if sub_name == "전체":
                        continue

                    if not sub_code or not sub_name:
                        raise ValueError(
                            "소분류 코드 또는 이름이 비어 있습니다."
                        )

                    # 4. 소분류 저장
                    if sub_code not in category_map:
                        sub_id = insert_category(
                            db=db,
                            category_code=sub_code,
                            parent_category_id=category_map[middle_code],
                            category_name=sub_name,
                            category_level=3,
                        )

                        category_map[sub_code] = sub_id

                except Exception as error:
                    raise RuntimeError(
                        f"CSV {row_number}행 처리 실패: {error}"
                    ) from error

    print(f"카테고리 저장 완료: {len(category_map)}개")


if __name__ == "__main__":
    save_categories()