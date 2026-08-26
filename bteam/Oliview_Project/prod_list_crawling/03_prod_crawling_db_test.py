# 설치
# uv add playwright beautifulsoup4 mysql-connector-python
# uv run playwright install chromium

import random
import re
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


# ============================================================
# 프로젝트 경로 설정
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.db_manager3 import DBManager


# ============================================================
# 테스트 설정
# ============================================================

BASE_URL = (
    "https://www.oliveyoung.co.kr/store/display/getMCategoryList.do"
    "?dispCatNo={category_code}"
)

# is_target=1 카테고리 중 앞의 2개만 테스트
TEST_CATEGORY_LIMIT = 2

PAGE_TIMEOUT = 30_000
PRODUCT_LIST_TIMEOUT = 20_000
FILTER_RELOAD_TIMEOUT = 20_000
MAX_PAGES_PER_CATEGORY = 100

BROWSER_PROFILE_DIR = (
    PROJECT_ROOT / ".playwright" / "oliveyoung_product_csv_test_profile"
)

CLOUDFLARE_KEYWORDS = [
    "잠시만 기다려 주세요",
    "접속 정보를 확인 중이에요",
    "Cloudflare 보안 챌린지",
    "challenges.cloudflare.com",
    "cf-turnstile-response",
    "__cf_chl_",
]


class RobotVerificationDetectedError(RuntimeError):
    pass


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def normalize_brand_key(value: Any) -> str:
    """브랜드명 매칭용: 공백 제거 + 소문자 변환."""
    return re.sub(r"\s+", "", normalize_text(value)).lower()


def normalize_url(value: Any) -> str:
    url = normalize_text(value)
    if not url or url.startswith("data:image"):
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"https://www.oliveyoung.co.kr{url}"
    return url


# ============================================================
# DB 조회
# ============================================================


def get_test_categories(connection) -> list[dict]:
    sql = """
        SELECT
            category_id,
            category_code,
            category_name
        FROM categories
        WHERE is_target = 1
        ORDER BY category_id
        LIMIT %s
    """

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, (TEST_CATEGORY_LIMIT,))
        return cursor.fetchall()
    finally:
        cursor.close()


def get_target_brands(connection) -> list[dict]:
    sql = """
        SELECT
            brand_id,
            brand_code,
            brand_name
        FROM brands
        WHERE is_target = 1
        ORDER BY brand_id
    """

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql)
        return cursor.fetchall()
    finally:
        cursor.close()


# ============================================================
# 페이지 상태/대기
# ============================================================


def raise_if_cloudflare(page: Page) -> None:
    html = page.content()
    if any(keyword in html for keyword in CLOUDFLARE_KEYWORDS):
        raise RobotVerificationDetectedError(
            "Cloudflare/로봇 인증 화면이 감지되어 실행을 중단합니다."
        )


def get_product_signature(page: Page) -> str:
    """목록 갱신 감지용: 첫 상품코드 + 상품 개수."""
    items = page.locator("ul.cate_prd_list > li")
    count = items.count()

    first_code = ""
    if count > 0:
        first = items.nth(0).locator("[data-ref-goodsno]").first
        if first.count() > 0:
            first_code = normalize_text(first.get_attribute("data-ref-goodsno"))

    return f"{first_code}|{count}"


def wait_for_product_list(page: Page) -> None:
    page.wait_for_selector(
        "ul.cate_prd_list",
        timeout=PRODUCT_LIST_TIMEOUT,
    )
    page.wait_for_timeout(700)


def wait_for_list_change(page: Page, previous_signature: str) -> None:
    """체크박스/페이지 클릭 후 상품목록이 다시 그려질 때까지 기다립니다."""
    started_at = time.time()

    while (time.time() - started_at) * 1000 < FILTER_RELOAD_TIMEOUT:
        raise_if_cloudflare(page)

        try:
            current_signature = get_product_signature(page)
            if current_signature and current_signature != previous_signature:
                page.wait_for_timeout(700)
                return
        except Exception:
            # AJAX 갱신 중 DOM이 잠깐 사라지는 경우
            pass

        page.wait_for_timeout(300)

    # 상품 수/첫 상품이 우연히 동일할 수도 있으므로 타임아웃 자체는 치명 오류로 보지 않음
    page.wait_for_timeout(1_000)


# ============================================================
# 브랜드 체크박스
# ============================================================


def read_brand_checkbox_map(page: Page) -> dict[str, dict]:
    """
    현재 페이지 체크박스에서
    브랜드명 → brand_code 매핑을 만듭니다.
    """
    soup = BeautifulSoup(page.content(), "html.parser")
    result: dict[str, dict] = {}

    for checkbox in soup.select('input[name="searchOnlBrndCdArr"]'):
        brand_code = normalize_text(checkbox.get("value"))
        brand_name = normalize_text(checkbox.get("data-brndnm"))

        if not brand_name:
            checkbox_id = normalize_text(checkbox.get("id"))
            if checkbox_id:
                label = soup.select_one(f'label[for="{checkbox_id}"]')
                if label:
                    brand_name = normalize_text(label.get_text(" ", strip=True))

        if brand_code and brand_name:
            result[normalize_brand_key(brand_name)] = {
                "brand_code": brand_code,
                "brand_name": brand_name,
            }

    return result


def select_target_brands(
    page: Page,
    target_brands: list[dict],
) -> tuple[dict[str, dict], list[dict]]:
    """
    현재 카테고리에 존재하는 대상 브랜드만 한 개씩 클릭합니다.

    반환값:
      1) 브랜드명 키 → DB 브랜드 정보 매핑
      2) 실제 선택된 브랜드 목록
    """
    checkbox_map = read_brand_checkbox_map(page)
    selected: list[dict] = []
    selected_by_name: dict[str, dict] = {}

    for brand in target_brands:
        brand_code = str(brand["brand_code"])
        selector = (
            'input[name="searchOnlBrndCdArr"]'
            f'[value="{brand_code}"]'
        )
        checkbox = page.locator(selector)

        if checkbox.count() == 0:
            print(
                f"    ℹ️ 현재 카테고리에 없음: "
                f"{brand['brand_name']} ({brand_code})"
            )
            continue

        checkbox = checkbox.first

        # 이미 체크되어 있다면 다시 클릭하지 않음
        if not checkbox.is_checked():
            previous_signature = get_product_signature(page)

            print(
                f"    ☑ 브랜드 선택: "
                f"{brand['brand_name']} ({brand_code})"
            )

            checkbox.click()
            page.wait_for_function(
                """code => {
                    const el = document.querySelector(
                        `input[name="searchOnlBrndCdArr"][value="${code}"]`
                    );
                    return Boolean(el && el.checked);
                }""",
                arg=brand_code,
                timeout=FILTER_RELOAD_TIMEOUT,
            )
            wait_for_list_change(page, previous_signature)

        key = normalize_brand_key(brand["brand_name"])
        selected_by_name[key] = {
            "brand_id": int(brand["brand_id"]),
            "brand_code": brand_code,
            "brand_name": normalize_text(brand["brand_name"]),
        }
        selected.append(brand)

    # 체크박스 표기명과 DB 표기명이 조금 다를 때도 연결 가능하도록 보완
    for checkbox_key, checkbox_brand in checkbox_map.items():
        checkbox_code = checkbox_brand["brand_code"]
        matching_db_brand = next(
            (
                brand
                for brand in selected
                if str(brand["brand_code"]) == checkbox_code
            ),
            None,
        )
        if matching_db_brand:
            selected_by_name[checkbox_key] = {
                "brand_id": int(matching_db_brand["brand_id"]),
                "brand_code": str(matching_db_brand["brand_code"]),
                "brand_name": normalize_text(matching_db_brand["brand_name"]),
            }

    return selected_by_name, selected


# ============================================================
# 상품 추출
# ============================================================


def extract_products(
    page: Page,
    category: dict,
    selected_brand_map: dict[str, dict],
) -> list[dict]:
    soup = BeautifulSoup(page.content(), "html.parser")
    products: list[dict] = []

    for item in soup.select("ul.cate_prd_list > li"):
        product_link = item.select_one("[data-ref-goodsno]")
        if not product_link:
            continue

        product_code = normalize_text(product_link.get("data-ref-goodsno"))

        name_element = item.select_one("p.tx_name")
        brand_element = item.select_one("span.tx_brand")
        image_element = item.select_one("a.prd_thumb img") or item.select_one("img")

        product_name = normalize_text(
            name_element.get_text(" ", strip=True) if name_element else ""
        )
        brand_name = normalize_text(
            brand_element.get_text(" ", strip=True) if brand_element else ""
        )
        image_url = normalize_url(
            image_element.get("src") if image_element else ""
        )

        brand_info = selected_brand_map.get(normalize_brand_key(brand_name))

        if not product_code or not product_name:
            print("    ⚠️ 상품코드/상품명 누락 항목 건너뜀")
            continue

        if not brand_info:
            print(
                f"    ⚠️ 브랜드 매칭 실패: {brand_name} / "
                f"{product_code}"
            )
            continue

        products.append(
            {
                "product_code": product_code,
                "brand_id": brand_info["brand_id"],
                "brand_code": brand_info["brand_code"],
                "brand_name": brand_name,
                "product_name": product_name,
                "product_image_url": image_url,
                "category_id": int(category["category_id"]),
                "category_code": str(category["category_code"]),
                "category_name": normalize_text(category["category_name"]),
            }
        )

    return products


# ============================================================
# 페이지 순회
# ============================================================


def get_current_page_number(page: Page) -> int:
    current = page.locator('.pageing strong[title="현재 페이지"]')
    if current.count() == 0:
        return 1

    text = normalize_text(current.first.inner_text())
    return int(text) if text.isdigit() else 1


def go_to_next_page(page: Page, current_page: int) -> bool:
    next_page = current_page + 1
    selector = f'.pageing a[data-page-no="{next_page}"]'
    link = page.locator(selector)

    if link.count() == 0:
        return False

    previous_signature = get_product_signature(page)
    link.first.click()

    try:
        page.wait_for_function(
            """expected => {
                const el = document.querySelector(
                    '.pageing strong[title="현재 페이지"]'
                );
                return el && el.textContent.trim() === String(expected);
            }""",
            arg=next_page,
            timeout=FILTER_RELOAD_TIMEOUT,
        )
    except PlaywrightTimeoutError:
        # 현재 페이지 숫자가 늦게 바뀌더라도 목록 변경을 한 번 더 확인
        pass

    wait_for_list_change(page, previous_signature)
    return True


def crawl_category(
    page: Page,
    category: dict,
    target_brands: list[dict],
) -> list[dict]:
    category_code = str(category["category_code"])
    category_name = normalize_text(category["category_name"])
    url = BASE_URL.format(category_code=category_code)

    print()
    print(f"📂 카테고리 접속: {category_name} ({category_code})")

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT,
    )
    raise_if_cloudflare(page)
    wait_for_product_list(page)

    selected_brand_map, selected_brands = select_target_brands(
        page=page,
        target_brands=target_brands,
    )

    if not selected_brands:
        print("  ℹ️ 현재 카테고리에 대상 브랜드가 없어 건너뜁니다.")
        return []

    print(f"  ✅ 실제 선택 브랜드: {len(selected_brands)}개")

    category_products_by_code: dict[str, dict] = {}

    for _ in range(MAX_PAGES_PER_CATEGORY):
        current_page = get_current_page_number(page)
        page_products = extract_products(
            page=page,
            category=category,
            selected_brand_map=selected_brand_map,
        )

        for product in page_products:
            category_products_by_code[product["product_code"]] = product

        print(
            f"    ✅ {current_page}페이지: "
            f"추출 {len(page_products)}개"
        )

        if not go_to_next_page(page, current_page):
            break

        time.sleep(random.uniform(0.8, 1.5))
    else:
        raise RuntimeError(
            f"{category_name}: 최대 페이지 제한을 초과했습니다."
        )

    result = list(category_products_by_code.values())
    print(f"  ✅ 카테고리 수집 완료: {len(result)}개")
    return result


# ============================================================
# DB 저장
# ============================================================


def save_to_db(connection, all_rows: list[dict]) -> None:
    """
    수집 결과를 products와 product_categories에 하나의 트랜잭션으로 저장합니다.

    - products: product_code 기준 INSERT 또는 UPDATE
    - product_categories: (product_id, category_id) 중복 없이 INSERT
    - 테스트가 2개 카테고리만 대상으로 하므로 미수집 상품 비활성화는 하지 않습니다.
    """
    collected_at = datetime.now()

    products_by_code: dict[str, dict] = {}
    relations: set[tuple[str, int]] = set()

    for row in all_rows:
        code = row["product_code"]

        products_by_code[code] = {
            "product_code": code,
            "brand_id": int(row["brand_id"]),
            "product_name": row["product_name"],
            "product_image_url": row["product_image_url"] or None,
            "collected_at": collected_at,
        }

        relations.add((code, int(row["category_id"])))

    product_sql = """
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
            brand_id = VALUES(brand_id),
            product_name = VALUES(product_name),
            product_image_url = CASE
                WHEN VALUES(product_image_url) IS NOT NULL
                 AND TRIM(VALUES(product_image_url)) <> ''
                THEN VALUES(product_image_url)
                ELSE product_image_url
            END,
            last_seen_at = VALUES(last_seen_at),
            is_active = 1
    """

    relation_sql = """
        INSERT IGNORE INTO product_categories (
            product_id,
            category_id
        )
        VALUES (
            %(product_id)s,
            %(category_id)s
        )
    """

    cursor = connection.cursor(dictionary=True)

    try:
        connection.commit()
        connection.start_transaction()

        cursor.executemany(
            product_sql,
            list(products_by_code.values()),
        )

        product_codes = list(products_by_code)
        placeholders = ",".join(["%s"] * len(product_codes))

        cursor.execute(
            f"""
                SELECT product_id, product_code
                FROM products
                WHERE product_code IN ({placeholders})
            """,
            tuple(product_codes),
        )

        code_to_id = {
            row["product_code"]: int(row["product_id"])
            for row in cursor.fetchall()
        }

        missing_codes = [
            code for code in product_codes
            if code not in code_to_id
        ]
        if missing_codes:
            raise RuntimeError(
                "product_id를 찾지 못한 상품이 있습니다: "
                + ", ".join(missing_codes[:10])
            )

        relation_params = [
            {
                "product_id": code_to_id[product_code],
                "category_id": category_id,
            }
            for product_code, category_id in sorted(
                relations,
                key=lambda row: (row[1], row[0]),
            )
        ]

        cursor.executemany(relation_sql, relation_params)
        connection.commit()

        print()
        print(f"✅ products 저장/갱신 완료: {len(products_by_code)}개")
        print(f"✅ product_categories 연결 처리 완료: {len(relations)}개")
        print("ℹ️ 테스트 실행이므로 상품 비활성화 처리는 하지 않았습니다.")

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()


# ============================================================
# main
# ============================================================


def main() -> None:
    print("=" * 60)
    print("상품/상품카테고리 DB 저장 테스트 시작")
    print("=" * 60)

    db = DBManager()

    try:
        db.connect()
        connection = db.connection

        if connection is None:
            raise RuntimeError("DB 연결 실패")

        categories = get_test_categories(connection)
        target_brands = get_target_brands(connection)

        if not categories:
            raise RuntimeError("is_target=1인 테스트 카테고리가 없습니다.")

        if not target_brands:
            raise RuntimeError("is_target=1인 대상 브랜드가 없습니다.")

        print(f"📌 테스트 카테고리: {len(categories)}개")
        print(f"📌 대상 브랜드: {len(target_brands)}개")

        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        all_rows: list[dict] = []

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_PROFILE_DIR),
                headless=False,
                locale="ko-KR",
                viewport={"width": 1400, "height": 900},
            )

            page = context.pages[0] if context.pages else context.new_page()

            try:
                for index, category in enumerate(categories, start=1):
                    print()
                    print(f"[{index}/{len(categories)}]")
                    rows = crawl_category(
                        page=page,
                        category=category,
                        target_brands=target_brands,
                    )
                    all_rows.extend(rows)
            finally:
                context.close()

        if not all_rows:
            raise RuntimeError("수집된 상품이 없습니다.")

        save_to_db(connection, all_rows)

    except KeyboardInterrupt:
        print("\n⚠️ 사용자가 작업을 중단했습니다.")

    except Exception as error:
        print(f"\n❌ 작업 실패: {error}")
        raise

    finally:
        db.close()

    print("=" * 60)
    print("작업 종료")
    print("=" * 60)


if __name__ == "__main__":
    main()