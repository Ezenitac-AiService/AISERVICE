
# uv add playwright beautifulsoup4 mysql-connector-python
# uv run playwright install chromium
import sys
from pathlib import Path
from datetime import datetime

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from common.db_manager import DBManager


BASE_URL = (
    "https://www.oliveyoung.co.kr/store/display/"
    "getMCategoryList.do?dispCatNo={category_code}"
)


def get_category_codes(db: DBManager) -> list[str]:
    """
    categories 테이블에 저장된 모든 카테고리 코드를 조회합니다.
    """

    sql = """
        SELECT DISTINCT category_code
        FROM categories
        WHERE category_code IS NOT NULL
          AND TRIM(category_code) <> ''
        ORDER BY category_code
    """

    db.execute(sql)
    rows = db.fetchall()

    # DBManager가 dictionary=True cursor를 사용하므로
    # 각 행은 딕셔너리 형태입니다.
    category_codes = [
        str(row["category_code"]).strip()
        for row in rows
        if row.get("category_code")
    ]

    return category_codes


def crawl_unique_brands(
    category_codes: list[str],
) -> tuple[dict[str, str], list[str]]:
    """
    카테고리 페이지를 순회하며 브랜드를 크롤링합니다.

    반환값:
        unique_brands: 브랜드 코드 기준 중복 제거 결과
        failed_categories: 크롤링 실패 카테고리 코드 목록
    """

    unique_brands: dict[str, str] = {}
    failed_categories: list[str] = []

    total_count = len(category_codes)

    print("=" * 70)
    print(f"🌿 총 {total_count}개 카테고리에서 브랜드 수집을 시작합니다.")
    print("=" * 70)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
        )

        page = browser.new_page(
            locale="ko-KR",
            viewport={
                "width": 1920,
                "height": 1080,
            },
        )

        page.set_default_timeout(15_000)

        for index, category_code in enumerate(
            category_codes,
            start=1,
        ):
            url = BASE_URL.format(
                category_code=category_code,
            )

            print(
                f"\n[{index}/{total_count}] "
                f"카테고리 {category_code} 탐색 중..."
            )

            try:
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )

                page.wait_for_timeout(1500)

                html = page.content()
                soup = BeautifulSoup(
                    html,
                    "html.parser",
                )

                brand_inputs = soup.select(
                    'ul.brand_list > li > input[type="checkbox"]'
                )

                category_brand_count = 0

                for brand_input in brand_inputs:
                    brand_code = brand_input.get("value")
                    brand_name = brand_input.get("data-brndnm")

                    if not brand_code or not brand_name:
                        continue

                    brand_code = str(brand_code).strip()
                    brand_name = str(brand_name).strip()

                    if not brand_code or not brand_name:
                        continue

                    # brand_code를 key로 사용하여 중복 제거
                    unique_brands[brand_code] = brand_name
                    category_brand_count += 1

                print(
                    f"    └ 현재 카테고리 브랜드: "
                    f"{category_brand_count}개"
                )
                print(
                    f"    └ 누적 고유 브랜드: "
                    f"{len(unique_brands)}개"
                )

            except PlaywrightTimeoutError:
                failed_categories.append(category_code)

                print(
                    f"    ⚠️ 페이지 로딩 시간 초과: "
                    f"{category_code}"
                )

            except Exception as error:
                failed_categories.append(category_code)

                print(
                    f"    ⚠️ 카테고리 처리 오류: "
                    f"{category_code}"
                )
                print(f"       오류 내용: {error}")

        browser.close()

    return unique_brands, failed_categories


def save_brands_to_db(
    db: DBManager,
    brands: dict[str, str],
    collected_at: datetime,
) -> int:
    """
    신규 브랜드는 INSERT하고,
    기존 브랜드는 last_seen_at과 브랜드 정보를 갱신합니다.
    """

    if not brands:
        print("⚠️ DB에 저장할 브랜드가 없습니다.")
        return 0

    sql = """
        INSERT INTO brands (
            brand_code,
            brand_name,
            first_collected_at,
            last_seen_at,
            is_active
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            1
        )
        ON DUPLICATE KEY UPDATE
            brand_name = VALUES(brand_name),
            last_seen_at = VALUES(last_seen_at),
            is_active = 1
    """

    brand_data = [
        (
            brand_code,
            brand_name,
            collected_at,
            collected_at,
        )
        for brand_code, brand_name in brands.items()
    ]

    db.executemany(
        sql,
        brand_data,
    )

    db.commit()

    return len(brand_data)


def deactivate_missing_brands(db: DBManager) -> int:
    """
    마지막 확인 시각이 3일 이상 지난 브랜드를 비활성화합니다.
    """

    sql = """
        UPDATE brands
        SET is_active = 0
        WHERE is_active = 1
          AND last_seen_at < NOW() - INTERVAL 3 DAY
    """

    db.execute(sql)

    # DBManager의 cursor를 통해 변경된 행 수 확인
    affected_rows = db.cursor.rowcount

    db.commit()

    return affected_rows


def main():
    db = DBManager()

    try:
        # DBManager 객체 생성 후 반드시 connect() 실행
        db.connect()

        collected_at = datetime.now()

        # 1. 카테고리 코드 조회
        category_codes = get_category_codes(db)

        if not category_codes:
            print(
                "⚠️ categories 테이블에서 "
                "category_code를 찾지 못했습니다."
            )
            return

        print(
            f"✅ categories 테이블에서 "
            f"{len(category_codes)}개의 카테고리 코드를 조회했습니다."
        )

        # 2. 브랜드 크롤링 및 중복 제거
        unique_brands, failed_categories = crawl_unique_brands(
            category_codes
        )

        if not unique_brands:
            print(
                "❌ 크롤링된 브랜드가 없어 "
                "DB 저장을 중단합니다."
            )
            return

        print("\n" + "=" * 70)
        print(
            f"🌿 최종 고유 브랜드 수: "
            f"{len(unique_brands)}개"
        )
        print(
            f"⚠️ 실패한 카테고리 수: "
            f"{len(failed_categories)}개"
        )
        print("=" * 70)

        # 3. 신규 추가 및 기존 브랜드 갱신
        saved_count = save_brands_to_db(
            db=db,
            brands=unique_brands,
            collected_at=collected_at,
        )

        print(
            f"✅ 브랜드 {saved_count}개의 "
            "신규 추가 또는 확인 시각 갱신 완료"
        )

        # 4. 모든 카테고리가 성공한 경우에만 비활성화
        if not failed_categories:
            deactivated_count = deactivate_missing_brands(db)

            print(
                f"✅ 3일 이상 확인되지 않은 브랜드 "
                f"{deactivated_count}개 비활성화"
            )

        else:
            print()
            print(
                "⚠️ 일부 카테고리 크롤링이 실패하여 "
                "비활성화 작업을 생략했습니다."
            )
            print(
                "   실패로 인해 실제 입점 브랜드가 "
                "잘못 비활성화되는 것을 방지하기 위한 처리입니다."
            )
            print(
                "   실패 카테고리:",
                ", ".join(failed_categories),
            )

        print("\n🌿 브랜드 동기화 작업이 완료되었습니다.")

    except Exception as error:
        db.rollback()

        print("\n❌ 브랜드 동기화 작업 중 오류가 발생했습니다.")
        print(f"오류 내용: {error}")

    finally:
        db.close()


if __name__ == "__main__":
    main()