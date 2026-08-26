# uv run python brand_crawling/brand_crawling_DB.py

import csv
import sys
from pathlib import Path


# 프로젝트 루트 경로 등록
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from common.db_manager import DBManager


# 현재 Python 파일과 같은 폴더에 있는 CSV 파일
CSV_FILE = Path(__file__).resolve().parent / "Brand_ID.csv"


def create_brands_table(db: DBManager):
    """brands 테이블 생성"""

    sql = """
    CREATE TABLE IF NOT EXISTS brands (
        brand_id BIGINT AUTO_INCREMENT PRIMARY KEY,
        brand_code VARCHAR(30) NOT NULL UNIQUE,
        brand_name VARCHAR(20) NOT NULL,
        is_target BOOLEAN NOT NULL DEFAULT FALSE
    )
    """

    db.execute(sql)
    db.commit()

    print("brands 테이블 준비 완료")


def read_brand_csv(csv_file: Path) -> list[tuple[str, str]]:
    """Brand_ID.csv 파일 읽기"""

    brand_rows = []

    with csv_file.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.reader(file)

        # CSV 첫 번째 줄이 헤더일 때만 사용
        next(reader, None)

        # 실제 데이터는 CSV의 2번째 행부터 시작
        for row_number, row in enumerate(reader, start=2):

            # 빈 행 제외
            if not row:
                continue

            # 컬럼이 2개보다 적으면 제외
            if len(row) < 2:
                print(f"{row_number}행 제외: 컬럼 부족 → {row}")
                continue

            brand_code = row[0].strip()
            brand_name = row[1].strip()

            # 빈 값이 있으면 제외
            if not brand_code or not brand_name:
                print(f"{row_number}행 제외: 빈 값 존재 → {row}")
                continue

            # 컬럼 길이 검증
            if len(brand_code) > 30:
                print(
                    f"{row_number}행 제외: "
                    f"brand_code 30자 초과 → {brand_code}"
                )
                continue

            if len(brand_name) > 20:
                print(
                    f"{row_number}행 제외: "
                    f"brand_name 20자 초과 → {brand_name}"
                )
                continue

            brand_rows.append(
                (
                    brand_code,
                    brand_name,
                )
            )

    return brand_rows


def insert_brands(
    db: DBManager,
    brand_rows: list[tuple[str, str]],
):
    """brands 테이블에 브랜드 저장"""

    if not brand_rows:
        print("저장할 브랜드 데이터가 없습니다.")
        return

    sql = """
    INSERT INTO brands (
        brand_code,
        brand_name
    )
    VALUES (%s, %s)
    ON DUPLICATE KEY UPDATE
        brand_name = VALUES(brand_name)
    """

    db.executemany(sql, brand_rows)
    db.commit()

    print(f"브랜드 CSV 데이터 {len(brand_rows)}개 처리 완료")


def main():
    db = DBManager()

    try:
        if not CSV_FILE.exists():
            raise FileNotFoundError(
                f"CSV 파일을 찾을 수 없습니다: {CSV_FILE}"
            )

        db.connect()

        create_brands_table(db)

        brand_rows = read_brand_csv(CSV_FILE)

        print(f"CSV에서 읽은 브랜드 수: {len(brand_rows)}개")

        insert_brands(db, brand_rows)

    except Exception as error:
        db.rollback()
        print(f"오류 발생: {error}")

    finally:
        db.close()


if __name__ == "__main__":
    main()