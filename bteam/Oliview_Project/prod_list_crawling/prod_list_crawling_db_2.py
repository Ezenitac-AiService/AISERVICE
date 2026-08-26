# uv add playwright beautifulsoup4 mysql-connector-python
# uv run playwright install chromium

# 한 상품이 여러 카테고리에 저장 되도록 반영함
# 현재코드는 상품목록페이지의 브랜드명을 brands테이블의 brand_name과 매치후 brand_id가져옴
# 한계 : 동명이인의 브랜드 명이 존재!!!
# prod_list_crawling_db_3.py에서 개선하겠음

import sys
import random
import time
from pathlib import Path
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


# =========================================================
# 프로젝트 경로 및 DBManager 불러오기
# =========================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.db_manager import DBManager


# =========================================================
# 설정
# =========================================================
BASE_URL = (
    "https://www.oliveyoung.co.kr/store/display/"
    "getCategoryShop.do?dispCatNo={category_code}"
)

BATCH_SIZE = 500
DEACTIVATE_AFTER_DAYS = 3

PAGE_TIMEOUT = 30_000
PRODUCT_LIST_TIMEOUT = 20_000

# 상품이 없는 페이지에서 표시될 수 있는 문구
NO_PRODUCT_MESSAGES = [
    "등록된 상품이 없습니다",
    "현재 등록된 상품이 없습니다",
    "상품이 없습니다",
    "검색 결과가 없습니다",
    "조회된 상품이 없습니다",
    "판매 중인 상품이 없습니다",
]


# =========================================================
# 문자열 정리
# =========================================================
def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).split()).strip()


# =========================================================
# DB 조회
# =========================================================
def get_target_categories(
    connection,
) -> list[dict[str, Any]]:
    """
    is_target = 1인 카테고리를 조회합니다.

    category_id:
        product_categories.category_id에 저장할 내부 PK

    category_code:
        올리브영 URL의 dispCatNo에 사용할 코드
    """

    sql = """
        SELECT
            category_id,
            category_code,
            category_name
        FROM categories
        WHERE is_target = 1
        ORDER BY category_id
    """

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(sql)
        return cursor.fetchall()

    finally:
        cursor.close()


def get_brand_mapping(
    connection,
) -> tuple[dict[str, int], set[str]]:
    """
    브랜드명 → brand_id 매핑을 생성합니다.

    같은 브랜드명이 여러 개 존재하면 정확한 brand_id를
    알 수 없으므로 ambiguous_brand_names에 따로 저장합니다.
    """

    sql = """
        SELECT
            brand_id,
            brand_name
        FROM brands
        WHERE is_active = 1
    """

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(sql)
        rows = cursor.fetchall()

    finally:
        cursor.close()

    brand_ids_by_name: dict[str, list[int]] = {}

    for row in rows:
        brand_name = normalize_text(
            row["brand_name"]
        )

        if not brand_name:
            continue

        brand_ids_by_name.setdefault(
            brand_name,
            [],
        ).append(
            int(row["brand_id"])
        )

    brand_mapping: dict[str, int] = {}
    ambiguous_brand_names: set[str] = set()

    for brand_name, brand_ids in brand_ids_by_name.items():
        unique_brand_ids = list(
            set(brand_ids)
        )

        if len(unique_brand_ids) == 1:
            brand_mapping[brand_name] = (
                unique_brand_ids[0]
            )
        else:
            ambiguous_brand_names.add(
                brand_name
            )

    return (
        brand_mapping,
        ambiguous_brand_names,
    )


# =========================================================
# HTML 데이터 추출
# =========================================================
def extract_brand_name(
    item,
    button,
) -> str:
    """
    상품 목록에서 브랜드명을 가져옵니다.
    """

    candidates = [
        button.get("data-ref-goodsbrand"),
        button.get("data-ref-goodsrnd"),
    ]

    for value in candidates:
        brand_name = normalize_text(value)

        if brand_name:
            return brand_name

    brand_tag = item.select_one(
        "span.tx_brand, "
        ".tx_brand, "
        "p.tx_brand"
    )

    if brand_tag:
        return normalize_text(
            brand_tag.get_text(
                " ",
                strip=True,
            )
        )

    return ""


def extract_image_url(item) -> str:
    """
    상품 대표 이미지 URL을 가져옵니다.
    """

    img_tag = item.select_one(
        ".prd_thumb img"
    )

    if not img_tag:
        return ""

    candidates = [
        img_tag.get("src"),
        img_tag.get("data-src"),
        img_tag.get("data-original"),
        img_tag.get("data-lazy-src"),
    ]

    for value in candidates:
        image_url = normalize_text(value)

        if not image_url:
            continue

        if image_url.startswith("data:image"):
            continue

        if image_url.startswith("//"):
            return f"https:{image_url}"

        return image_url

    return ""


def is_no_product_page(
    soup: BeautifulSoup,
) -> bool:
    """
    정상적으로 열린 페이지가 상품 0개 상태인지 확인합니다.
    """

    page_text = normalize_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    for message in NO_PRODUCT_MESSAGES:
        if message in page_text:
            return True

    # 상품 없음 영역에서 자주 사용되는 선택자 확인
    no_data_selectors = [
        ".no_data",
        ".no-data",
        ".nodata",
        ".no_result",
        ".no-result",
        ".search_no_data",
        ".cate_no_data",
    ]

    for selector in no_data_selectors:
        no_data_element = soup.select_one(
            selector
        )

        if no_data_element:
            element_text = normalize_text(
                no_data_element.get_text(
                    " ",
                    strip=True,
                )
            )

            if any(
                message in element_text
                for message in NO_PRODUCT_MESSAGES
            ):
                return True

    return False


# =========================================================
# 카테고리 하나 크롤링
# =========================================================
def crawl_category(
    page: Page,
    category: dict[str, Any],
    brand_mapping: dict[str, int],
    ambiguous_brand_names: set[str],
) -> list[dict[str, Any]]:

    category_id = int(
        category["category_id"]
    )
    category_code = str(
        category["category_code"]
    )
    category_name = str(
        category["category_name"]
    )

    url = BASE_URL.format(
        category_code=category_code
    )

    print(
        f"\n📂 크롤링 중: "
        f"{category_name} ({category_code})"
    )

    time.sleep(
        random.uniform(1.5, 3.0)
    )

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT,
    )

    # -----------------------------------------------------
    # 상품 목록이 나타날 때까지 기다림
    # 상품이 없는 정상 페이지라면 빈 리스트 반환
    # -----------------------------------------------------
    try:
        page.wait_for_selector(
            "ul.cate_prd_list",
            timeout=PRODUCT_LIST_TIMEOUT,
        )

    except PlaywrightTimeoutError:
        html = page.content()
        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        if is_no_product_page(soup):
            print(
                "  ℹ️ 현재 등록된 상품이 없는 "
                "카테고리입니다."
            )
            print(
                "  ✅ 수집 완료: 0개"
            )

            return []

        print(
            f"  ❌ 상품 목록 로딩 실패"
        )
        print(
            f"  URL: {page.url}"
        )
        print(
            f"  페이지 제목: {page.title()}"
        )

        # 상품 없음이 아니라 실제 오류이므로
        # 전체 크롤링 실패로 전달
        raise

    # -----------------------------------------------------
    # 지연 로딩 이미지와 상품 불러오기
    # -----------------------------------------------------
    previous_height = 0

    for _ in range(10):
        current_height = page.evaluate(
            "document.body.scrollHeight"
        )

        if current_height == previous_height:
            break

        previous_height = current_height

        page.evaluate(
            "window.scrollTo("
            "0, document.body.scrollHeight"
            ")"
        )

        page.wait_for_timeout(800)

    html = page.content()
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    product_items = soup.select(
        "ul.cate_prd_list > li"
    )

    # ul은 존재하지만 li 상품이 없는 경우
    if not product_items:
        if is_no_product_page(soup):
            print(
                "  ℹ️ 현재 등록된 상품이 없는 "
                "카테고리입니다."
            )
            print(
                "  ✅ 수집 완료: 0개"
            )

            return []

        raise RuntimeError(
            f"{category_name} 페이지에 상품 목록 영역은 "
            "있지만 상품 항목을 찾지 못했습니다."
        )

    category_products: list[
        dict[str, Any]
    ] = []

    for item in product_items:
        button = item.select_one(
            "button.btn_zzim"
        )

        if not button:
            continue

        product_code = normalize_text(
            button.get(
                "data-ref-goodsno"
            )
        )

        product_name = normalize_text(
            button.get(
                "data-ref-goodsnm"
            )
        )

        brand_name = extract_brand_name(
            item,
            button,
        )

        product_image_url = (
            extract_image_url(item)
        )

        if not product_code:
            continue

        if not product_name:
            print(
                f"  ⚠️ 상품명 없음: "
                f"{product_code}"
            )
            continue

        if not brand_name:
            print(
                f"  ⚠️ 브랜드명 없음: "
                f"{product_code} / "
                f"{product_name}"
            )
            continue

        # 같은 브랜드명이 DB에 여러 개 존재
        if (
            brand_name
            in ambiguous_brand_names
        ):
            print(
                f"  ⚠️ DB에 같은 브랜드명이 "
                f"여러 개 있음: "
                f"{brand_name} / "
                f"{product_code}"
            )
            continue

        brand_id = brand_mapping.get(
            brand_name
        )

        # 브랜드 테이블에 브랜드명이 없음
        if brand_id is None:
            print(
                f"  ⚠️ 브랜드 테이블에서 "
                f"찾지 못함: "
                f"{brand_name} / "
                f"{product_code}"
            )
            continue

        if not product_image_url:
            print(
                f"  ⚠️ 이미지 URL 없음: "
                f"{product_code} / "
                f"{product_name}"
            )

        category_products.append(
            {
                "product_code": (
                    product_code
                ),
                "brand_id": brand_id,

                # URL 검색에 사용한 카테고리의
                # DB 내부 category_id
                "category_id": (
                    category_id
                ),

                "product_name": (
                    product_name
                ),
                "product_image_url": (
                    product_image_url
                ),
            }
        )

    print(
        f"  ✅ 수집 완료: "
        f"{len(category_products)}개"
    )

    return category_products


# =========================================================
# 전체 카테고리 크롤링
# =========================================================
def crawl_all_products(
    categories: list[dict[str, Any]],
    brand_mapping: dict[str, int],
    ambiguous_brand_names: set[str],
) -> list[dict[str, Any]]:
    """
    모든 대상 카테고리를 크롤링합니다.

    동일한 product_code가 여러 카테고리에서 발견되면
    상품 정보는 한 번만 유지하고, category_ids에는
    발견된 모든 category_id를 누적합니다.

    실제 페이지 로딩 오류가 발생하면 예외를 발생시켜
    DB 저장 단계로 넘어가지 않습니다.
    """

    products_by_code: dict[
        str,
        dict[str, Any],
    ] = {}

    user_agents = [
        (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0.0.0 "
            "Safari/537.36"
        ),
        (
            "Mozilla/5.0 "
            "(Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/119.0.0.0 "
            "Safari/537.36"
        ),
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
        )

        context = browser.new_context(
            locale="ko-KR",
            user_agent=random.choice(user_agents),
            viewport={
                "width": 1400,
                "height": 900,
            },
        )

        page = context.new_page()

        try:
            total_categories = len(categories)

            for index, category in enumerate(
                categories,
                start=1,
            ):
                print(
                    f"\n[{index}/{total_categories}]",
                    end=" ",
                )

                category_products = crawl_category(
                    page=page,
                    category=category,
                    brand_mapping=brand_mapping,
                    ambiguous_brand_names=(
                        ambiguous_brand_names
                    ),
                )

                for product in category_products:
                    product_code = product[
                        "product_code"
                    ]
                    category_id = int(
                        product["category_id"]
                    )

                    existing = products_by_code.get(
                        product_code
                    )

                    if existing is None:
                        # products 테이블에 저장할 상품 정보와
                        # product_categories에 저장할 카테고리 목록 분리
                        products_by_code[product_code] = {
                            "product_code": product_code,
                            "brand_id": product["brand_id"],
                            "product_name": (
                                product["product_name"]
                            ),
                            "product_image_url": (
                                product[
                                    "product_image_url"
                                ]
                            ),
                            "category_ids": {
                                category_id
                            },
                        }
                        continue

                    # 동일 상품이 다른 카테고리에서도 발견되면
                    # 기존 상품을 버리지 않고 카테고리만 추가
                    if (
                        category_id
                        not in existing["category_ids"]
                    ):
                        existing["category_ids"].add(
                            category_id
                        )

                        print(
                            "  ℹ️ 다른 카테고리에도 노출됨: "
                            f"{product_code} "
                            f"-> category_id={category_id}"
                        )

                    # 동일 상품의 brand_id는 최초 매칭값을 유지합니다.
                    # 상품명과 이미지만 가장 최근 정상 수집값으로 갱신합니다.
                    existing["product_name"] = product[
                        "product_name"
                    ]

                    if product["product_image_url"]:
                        existing["product_image_url"] = (
                            product[
                                "product_image_url"
                            ]
                        )

        finally:
            context.close()
            browser.close()

    products = list(products_by_code.values())

    # DB 파라미터로 사용하기 쉽도록 set을 정렬된 list로 변환
    for product in products:
        product["category_ids"] = sorted(
            product["category_ids"]
        )

    return products


# =========================================================
# 상품 DB 저장
# =========================================================
def save_products(
    connection,
    products: list[dict[str, Any]],
    target_category_ids: list[int],
    collected_at: datetime,
) -> None:
    """
    products와 product_categories를 하나의 트랜잭션으로 저장합니다.

    1. products UPSERT
    2. 저장된 product_code로 product_id 조회
    3. 이번 실행 대상 카테고리의 기존 연결 삭제
    4. product_categories 연결 재등록
    5. 오래 확인되지 않은 상품 비활성화

    모든 SQL 성공:
        COMMIT

    하나라도 실패:
        전체 ROLLBACK
    """

    product_upsert_sql = """
        INSERT INTO products (
            product_code,
            brand_id,
            product_name,
            product_image_url,
            first_collected_at,
            last_seen_at,
            is_active
        )
        VALUES (
            %(product_code)s,
            %(brand_id)s,
            %(product_name)s,
            %(product_image_url)s,
            %(collected_at)s,
            %(collected_at)s,
            1
        )
        ON DUPLICATE KEY UPDATE
            product_name = VALUES(product_name),
            product_image_url =
                VALUES(product_image_url),
            last_seen_at =
                VALUES(last_seen_at),
            is_active = 1
    """

    category_insert_sql = """
        INSERT INTO product_categories (
            product_id,
            category_id
        )
        VALUES (
            %(product_id)s,
            %(category_id)s
        )
        ON DUPLICATE KEY UPDATE
            category_id = VALUES(category_id)
    """

    deactivate_sql = f"""
        UPDATE products
        SET is_active = 0
        WHERE is_active = 1
          AND last_seen_at
              < %s
                - INTERVAL
                  {DEACTIVATE_AFTER_DAYS} DAY
    """

    product_parameters = [
        {
            "product_code": product[
                "product_code"
            ],
            "brand_id": product["brand_id"],
            "product_name": product[
                "product_name"
            ],
            "product_image_url": product[
                "product_image_url"
            ],
            "collected_at": collected_at,
        }
        for product in products
    ]

    cursor = connection.cursor(
        dictionary=True
    )

    try:
        # 앞에서 실행한 SELECT 트랜잭션 정리
        connection.commit()
        connection.start_transaction()

        # -------------------------------------------------
        # 1. products 테이블 UPSERT
        # -------------------------------------------------
        total_batches = (
            len(product_parameters)
            + BATCH_SIZE
            - 1
        ) // BATCH_SIZE

        for batch_number, start in enumerate(
            range(
                0,
                len(product_parameters),
                BATCH_SIZE,
            ),
            start=1,
        ):
            batch = product_parameters[
                start:start + BATCH_SIZE
            ]

            cursor.executemany(
                product_upsert_sql,
                batch,
            )

            print(
                f"💾 products 저장 배치: "
                f"{batch_number}/{total_batches} "
                f"({len(batch)}개)"
            )

        # -------------------------------------------------
        # 2. product_code → product_id 매핑 조회
        # -------------------------------------------------
        product_id_by_code: dict[str, int] = {}
        product_codes = [
            product["product_code"]
            for product in products
        ]

        for start in range(
            0,
            len(product_codes),
            BATCH_SIZE,
        ):
            code_batch = product_codes[
                start:start + BATCH_SIZE
            ]

            placeholders = ", ".join(
                ["%s"] * len(code_batch)
            )

            select_sql = f"""
                SELECT
                    product_id,
                    product_code
                FROM products
                WHERE product_code IN (
                    {placeholders}
                )
            """

            cursor.execute(
                select_sql,
                tuple(code_batch),
            )

            for row in cursor.fetchall():
                product_id_by_code[
                    row["product_code"]
                ] = int(row["product_id"])

        missing_codes = [
            code
            for code in product_codes
            if code not in product_id_by_code
        ]

        if missing_codes:
            raise RuntimeError(
                "product_id 조회 실패 상품이 있습니다: "
                + ", ".join(missing_codes[:10])
            )

        # -------------------------------------------------
        # 3. 이번 크롤링 대상 카테고리의 기존 연결 초기화
        # -------------------------------------------------
        # 전체 대상 카테고리가 성공적으로 크롤링된 뒤에만
        # 이 함수가 실행되므로, 현재 수집 결과와 정확히 동기화합니다.
        if target_category_ids:
            for start in range(
                0,
                len(target_category_ids),
                BATCH_SIZE,
            ):
                category_batch = (
                    target_category_ids[
                        start:start + BATCH_SIZE
                    ]
                )

                placeholders = ", ".join(
                    ["%s"] * len(category_batch)
                )

                delete_sql = f"""
                    DELETE FROM product_categories
                    WHERE category_id IN (
                        {placeholders}
                    )
                """

                cursor.execute(
                    delete_sql,
                    tuple(category_batch),
                )

        # -------------------------------------------------
        # 4. product_categories 연결 저장
        # -------------------------------------------------
        relation_parameters: list[
            dict[str, int]
        ] = []

        for product in products:
            product_id = product_id_by_code[
                product["product_code"]
            ]

            for category_id in product[
                "category_ids"
            ]:
                relation_parameters.append(
                    {
                        "product_id": product_id,
                        "category_id": int(
                            category_id
                        ),
                    }
                )

        relation_total_batches = (
            len(relation_parameters)
            + BATCH_SIZE
            - 1
        ) // BATCH_SIZE

        for batch_number, start in enumerate(
            range(
                0,
                len(relation_parameters),
                BATCH_SIZE,
            ),
            start=1,
        ):
            batch = relation_parameters[
                start:start + BATCH_SIZE
            ]

            cursor.executemany(
                category_insert_sql,
                batch,
            )

            print(
                f"🔗 product_categories 저장 배치: "
                f"{batch_number}/"
                f"{relation_total_batches} "
                f"({len(batch)}개)"
            )

        # -------------------------------------------------
        # 5. 오래 확인되지 않은 상품 비활성화
        # -------------------------------------------------
        cursor.execute(
            deactivate_sql,
            (collected_at,),
        )

        deactivated_count = cursor.rowcount

        connection.commit()

        print(
            f"\n✅ products 저장 완료: "
            f"{len(products)}개"
        )
        print(
            f"✅ product_categories 저장 완료: "
            f"{len(relation_parameters)}개 연결"
        )
        print(
            f"⛔ {DEACTIVATE_AFTER_DAYS}일 이상 "
            f"미확인 상품 비활성화: "
            f"{deactivated_count}개"
        )

    except Exception:
        connection.rollback()

        print(
            "\n❌ DB 저장 실패: "
            "products와 product_categories "
            "전체 트랜잭션 ROLLBACK"
        )

        raise

    finally:
        cursor.close()


# =========================================================
# 실행
# =========================================================
def main() -> None:
    started_at = datetime.now()

    print("=" * 55)
    print(
        f"상품 크롤링 시작: "
        f"{started_at:%Y-%m-%d %H:%M:%S}"
    )
    print("=" * 55)

    db = DBManager()

    try:
        # DB 연결
        db.connect()

        connection = db.connection

        if connection is None:
            raise RuntimeError(
                "DB 연결 객체를 생성하지 못했습니다."
            )

        # 1. is_target = 1인 카테고리 조회
        categories = get_target_categories(
            connection
        )

        if not categories:
            print(
                "⚠️ is_target = 1인 "
                "카테고리가 없습니다."
            )
            return

        # 2. 브랜드명 → brand_id 매핑
        (
            brand_mapping,
            ambiguous_brand_names,
        ) = get_brand_mapping(
            connection
        )

        print(
            f"크롤링 대상 카테고리: "
            f"{len(categories)}개"
        )

        print(
            f"정상 브랜드 매핑: "
            f"{len(brand_mapping)}개"
        )

        if ambiguous_brand_names:
            print(
                f"⚠️ 중복된 브랜드명: "
                f"{len(ambiguous_brand_names)}개"
            )

        # 3. 전체 카테고리 크롤링
        products = crawl_all_products(
            categories=categories,
            brand_mapping=brand_mapping,
            ambiguous_brand_names=(
                ambiguous_brand_names
            ),
        )

        if not products:
            raise RuntimeError(
                "전체 카테고리에서 수집된 "
                "상품이 없어 DB 저장을 중단합니다."
            )

        print(
            f"\n📦 전체 고유 상품 수: "
            f"{len(products)}개"
        )

        # 4. 모든 크롤링 성공 후 DB 저장
        collected_at = datetime.now()

        target_category_ids = [
            int(category["category_id"])
            for category in categories
        ]

        save_products(
            connection=connection,
            products=products,
            target_category_ids=(
                target_category_ids
            ),
            collected_at=collected_at,
        )

    except PlaywrightTimeoutError as error:
        print(
            f"\n❌ 페이지 로딩 실패: "
            f"{error}"
        )
        print(
            "상품 없음 상태가 아닌 실제 "
            "페이지 로딩 오류입니다."
        )
        print(
            "DB 저장 단계로 넘어가지 않았습니다."
        )

    except Exception as error:
        print(
            f"\n❌ 작업 실패: {error}"
        )
        print(
            "작업 전체를 중단했습니다."
        )

    finally:
        db.close()

    print("=" * 55)
    print(
        f"작업 종료: "
        f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    )
    print("=" * 55)


if __name__ == "__main__":
    main()