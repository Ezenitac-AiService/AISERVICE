# 설치
# uv add playwright beautifulsoup4 mysql-connector-python
# uv run playwright install chromium


# 브라우저 프로필을 저장해서 쿠키·세션 재사용
# Cloudflare/로봇 인증 화면 감지
# 인증 화면이 뜨면 즉시 전체 실행 중단
# 전체 크롤링 완료 전이면 DB 저장하지 않음
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


# ============================================================
# 프로젝트 경로 설정
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.db_manager import DBManager


# ============================================================
# 기본 설정
# ============================================================

BASE_URL = (
    "https://www.oliveyoung.co.kr/store/display/getMCategoryList.do"
    "?dispCatNo={category_code}"
    "&fltDispCatNo="
    "&prdSort=01"
    "&pageIdx={page_idx}"
    "&rowsPerPage={rows_per_page}"
    "&searchTypeSort=btn_thumb"
    "&plusButtonFlag=N"
)

ROWS_PER_PAGE = 24

# 무한 페이지 접근 방지용
MAX_PAGES_PER_CATEGORY = 500

# 페이지별 재시도 횟수
MAX_PAGE_RETRIES = 3

# DB 처리 배치 크기
BATCH_SIZE = 500

# 마지막 확인 후 비활성화 기준
DEACTIVATE_AFTER_DAYS = 3

# Playwright 타임아웃
PAGE_TIMEOUT = 30_000
PRODUCT_LIST_TIMEOUT = 20_000

# 상품 개수가 안정됐다고 판단하기 위한 설정
PRODUCT_COUNT_CHECK_INTERVAL = 500
PRODUCT_COUNT_STABLE_ROUNDS = 3
PRODUCT_COUNT_WAIT_TIMEOUT = 10_000

# 실패 HTML 저장 폴더
LOG_DIR = PROJECT_ROOT / "logs" / "product_crawling"

# Chromium 사용자 프로필(쿠키/세션) 저장 폴더
# 한 번 정상 접속한 세션을 다음 실행에서도 재사용합니다.
BROWSER_PROFILE_DIR = PROJECT_ROOT / ".playwright" / "oliveyoung_product_profile"


NO_PRODUCT_MESSAGES = [
    "등록된 상품이 없습니다",
    "현재 등록된 상품이 없습니다",
    "상품이 없습니다",
    "검색 결과가 없습니다",
    "조회된 상품이 없습니다",
    "판매 중인 상품이 없습니다",
]


CLOUDFLARE_KEYWORDS = [
    "잠시만 기다려 주세요",
    "접속 정보를 확인 중이에요",
    "Cloudflare 보안 챌린지",
    "challenges.cloudflare.com",
    "cf-turnstile-response",
    "__cf_chl_",
]


# ============================================================
# 공통 함수
# ============================================================


class RobotVerificationDetectedError(RuntimeError):
    """Cloudflare/로봇 인증 화면 감지 시 전체 실행을 중단하기 위한 예외입니다."""


def normalize_text(value: Any) -> str:
    """
    None을 빈 문자열로 바꾸고,
    여러 개의 공백과 줄바꿈을 하나의 공백으로 정리합니다.
    """

    if value is None:
        return ""

    return " ".join(str(value).split()).strip()


def normalize_url(value: Any) -> str:
    """
    이미지 URL 등을 절대 URL 형태로 정리합니다.
    """

    url = normalize_text(value)

    if not url:
        return ""

    if url.startswith("data:image"):
        return ""

    if url.startswith("//"):
        return f"https:{url}"

    if url.startswith("/"):
        return f"https://www.oliveyoung.co.kr{url}"

    return url


def safe_filename(value: str) -> str:
    """
    로그 파일명에 사용할 수 없는 문자를 제거합니다.
    """

    value = normalize_text(value)
    value = re.sub(r'[\\/:*?"<>|]', "_", value)

    return value[:100] or "unknown"


# ============================================================
# DB 조회
# ============================================================

def get_target_categories(connection) -> list[dict]:
    """
    is_target=1인 카테고리만 조회합니다.
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


# ============================================================
# 페이지 상태 확인
# ============================================================

def is_cloudflare_page(page: Page) -> bool:
    """
    현재 페이지가 Cloudflare 또는 로봇 확인 화면인지 확인합니다.
    """

    try:
        html = page.content()
    except Exception:
        return False

    return any(keyword in html for keyword in CLOUDFLARE_KEYWORDS)


def raise_if_cloudflare(page: Page) -> None:
    """
    Cloudflare 또는 로봇 인증 화면이 감지되면 우회하거나 기다리지 않고
    현재 실행을 즉시 중단합니다.

    크롤링 결과는 전체 수집이 완료된 뒤에만 DB에 저장되므로,
    이 예외가 발생하면 이번 실행의 불완전한 결과는 DB에 반영되지 않습니다.
    """

    if not is_cloudflare_page(page):
        return

    raise RobotVerificationDetectedError(
        "Cloudflare/로봇 인증 화면이 감지되어 실행을 중단합니다. "
        "인증을 자동 우회하지 않습니다. 저장된 브라우저 프로필의 세션이 "
        "만료되었을 수 있습니다."
    )


def is_no_product_page(soup: BeautifulSoup) -> bool:
    """
    상품이 없는 카테고리인지 확인합니다.
    """

    text = normalize_text(soup.get_text(" ", strip=True))

    if any(message in text for message in NO_PRODUCT_MESSAGES):
        return True

    selectors = [
        ".no_data",
        ".no-data",
        ".nodata",
        ".no_result",
        ".no-result",
        ".search_no_data",
        ".cate_no_data",
    ]

    for selector in selectors:
        element = soup.select_one(selector)

        if not element:
            continue

        element_text = normalize_text(element.get_text(" ", strip=True))

        if any(message in element_text for message in NO_PRODUCT_MESSAGES):
            return True

    return False


def wait_for_product_count_stable(page: Page) -> int:
    """
    상품 li 개수가 일정 시간 동안 증가하지 않을 때까지 기다립니다.

    ul만 먼저 생성되고 상품 li가 늦게 만들어지는 경우를 방지합니다.
    """

    locator = page.locator("ul.cate_prd_list > li")

    started_at = time.time()
    previous_count = -1
    stable_rounds = 0
    current_count = 0

    while (time.time() - started_at) * 1_000 < PRODUCT_COUNT_WAIT_TIMEOUT:
        current_count = locator.count()

        if current_count > 0 and current_count == previous_count:
            stable_rounds += 1
        else:
            stable_rounds = 0

        if stable_rounds >= PRODUCT_COUNT_STABLE_ROUNDS:
            return current_count

        previous_count = current_count
        page.wait_for_timeout(PRODUCT_COUNT_CHECK_INTERVAL)

    return current_count


# ============================================================
# 상품 정보 추출
# ============================================================

def extract_product_code_from_href(href: str) -> str:
    """
    상품 상세 URL의 goodsNo 파라미터에서 상품번호를 추출합니다.
    """

    href = normalize_text(href)

    if not href:
        return ""

    # 일반적인 URL 형태
    try:
        parsed = urlparse(href)
        query = parse_qs(parsed.query)

        goods_numbers = query.get("goodsNo")

        if goods_numbers:
            return normalize_text(goods_numbers[0])

    except Exception:
        pass

    # JavaScript 또는 비표준 URL에 goodsNo가 들어 있는 경우
    match = re.search(
        r"goodsNo(?:=|%3D|['\"\s,:]+)(A\d+)",
        href,
        flags=re.IGNORECASE,
    )

    if match:
        return normalize_text(match.group(1))

    # URL 안에서 상품번호 패턴 자체를 탐색
    match = re.search(r"\bA\d{10,}\b", href)

    if match:
        return normalize_text(match.group(0))

    return ""


def extract_product_code(item) -> str:
    """
    상품번호를 여러 위치에서 순서대로 탐색합니다.

    1. li 자체의 data-ref-goodsno
    2. 내부 요소의 data-ref-goodsno
    3. 상품 링크 href의 goodsNo
    4. JavaScript 또는 HTML 문자열의 상품번호 패턴
    """

    # 1. li 자체
    code = normalize_text(item.get("data-ref-goodsno"))

    if code:
        return code

    # 2. 내부 data 속성
    elements = item.select("[data-ref-goodsno]")

    for element in elements:
        code = normalize_text(element.get("data-ref-goodsno"))

        if code:
            return code

    # 3. 상품 상세 링크
    links = item.select('a[href*="goodsNo"], a[href*="goodsno"]')

    for link in links:
        code = extract_product_code_from_href(link.get("href", ""))

        if code:
            return code

    # 4. 모든 링크 확인
    for link in item.select("a[href]"):
        code = extract_product_code_from_href(link.get("href", ""))

        if code:
            return code

    # 5. HTML 안의 상품번호 패턴
    item_html = str(item)

    match = re.search(r"\bA\d{10,}\b", item_html)

    if match:
        return normalize_text(match.group(0))

    return ""


def extract_product_name(item) -> str:
    """
    상품명을 여러 위치에서 순서대로 탐색합니다.

    1. data-ref-goodsnm
    2. 상품명 표시 요소의 텍스트
    3. title 속성
    4. 이미지 alt 속성
    """

    # 1. li 자체의 data-ref-goodsnm
    name = normalize_text(item.get("data-ref-goodsnm"))

    if name:
        return name

    # 2. 내부 data-ref-goodsnm
    for element in item.select("[data-ref-goodsnm]"):
        name = normalize_text(element.get("data-ref-goodsnm"))

        if name:
            return name

    # 3. 화면에 표시되는 상품명
    selectors = [
        ".prd_info .tx_name",
        ".tx_name",
        ".prd_name",
        ".product_name",
        ".goods_name",
        ".prd_info a",
        "p.tx_name",
    ]

    for selector in selectors:
        element = item.select_one(selector)

        if not element:
            continue

        name = normalize_text(element.get_text(" ", strip=True))

        if name:
            return name

    # 4. title 속성
    for element in item.select("[title]"):
        title = normalize_text(element.get("title"))

        if not title:
            continue

        if title in {"새창", "찜하기", "장바구니", "상품 보기"}:
            continue

        return title

    # 5. 이미지 alt
    for image in item.select("img[alt]"):
        alt = normalize_text(image.get("alt"))

        if not alt:
            continue

        if alt in {"올리브영", "상품 이미지", "이미지"}:
            continue

        return alt

    return ""


def extract_image_url(item) -> str:
    """
    상품 이미지 URL을 여러 속성에서 탐색합니다.
    """

    selectors = [
        ".prd_thumb img",
        ".prd_img img",
        ".product_image img",
        "img",
    ]

    image = None

    for selector in selectors:
        image = item.select_one(selector)

        if image:
            break

    if not image:
        return ""

    attributes = [
        "src",
        "data-src",
        "data-original",
        "data-lazy-src",
        "data-original-src",
    ]

    for attribute in attributes:
        url = normalize_url(image.get(attribute))

        if url:
            return url

    # srcset이 존재하는 경우 첫 번째 이미지 사용
    srcset = normalize_text(image.get("srcset"))

    if srcset:
        first_url = srcset.split(",")[0].strip().split(" ")[0]
        return normalize_url(first_url)

    return ""


def is_real_product_item(item) -> bool:
    """
    광고, 빈 li, 레이아웃용 li 등을 상품으로 잘못 세는 것을 줄입니다.
    """

    if item.select_one("[data-ref-goodsno]"):
        return True

    if item.select_one('a[href*="goodsNo"], a[href*="goodsno"]'):
        return True

    item_html = str(item)

    if re.search(r"\bA\d{10,}\b", item_html):
        return True

    return False


def extract_products_from_soup(
    soup: BeautifulSoup,
    category_id: int,
) -> tuple[list[dict], list[dict], int]:
    """
    BeautifulSoup 객체에서 상품 정보를 추출합니다.

    반환값:
        products
        skipped_items
        real_item_count
    """

    raw_items = soup.select("ul.cate_prd_list > li")

    real_items = [
        item
        for item in raw_items
        if is_real_product_item(item)
    ]

    products_by_code: dict[str, dict] = {}
    skipped_items: list[dict] = []

    for index, item in enumerate(real_items, start=1):
        code = extract_product_code(item)
        name = extract_product_name(item)
        image_url = extract_image_url(item)

        missing_fields = []

        if not code:
            missing_fields.append("product_code")

        if not name:
            missing_fields.append("product_name")

        if missing_fields:
            skipped_items.append(
                {
                    "index": index,
                    "reason": ", ".join(missing_fields),
                    "html": str(item),
                }
            )
            continue

        product = {
            "product_code": code,
            "category_id": category_id,
            "product_name": name,
            "product_image_url": image_url,
        }

        existing = products_by_code.get(code)

        if existing is None:
            products_by_code[code] = product

        else:
            # 같은 페이지에서 중복 등장한 경우,
            # 비어 있지 않은 최신 정보로 보완합니다.
            if name:
                existing["product_name"] = name

            if image_url:
                existing["product_image_url"] = image_url

    return (
        list(products_by_code.values()),
        skipped_items,
        len(real_items),
    )


# ============================================================
# 로그 저장
# ============================================================

def save_failed_item_log(
    category_name: str,
    category_code: str,
    page_idx: int,
    skipped_items: list[dict],
) -> None:
    """
    상품번호 또는 상품명을 찾지 못한 li HTML을 파일로 저장합니다.
    """

    if not skipped_items:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    filename = (
        f"{timestamp}_"
        f"{safe_filename(category_name)}_"
        f"{category_code}_"
        f"page_{page_idx}_skipped.html"
    )

    log_path = LOG_DIR / filename

    lines = [
        "<!DOCTYPE html>",
        '<html lang="ko">',
        "<head>",
        '<meta charset="UTF-8">',
        "<title>상품 추출 실패 로그</title>",
        "</head>",
        "<body>",
        f"<h1>{category_name} ({category_code})</h1>",
        f"<h2>pageIdx={page_idx}</h2>",
    ]

    for skipped in skipped_items:
        lines.extend(
            [
                "<hr>",
                f"<h3>항목 번호: {skipped['index']}</h3>",
                f"<p>누락 사유: {skipped['reason']}</p>",
                skipped["html"],
            ]
        )

    lines.extend(
        [
            "</body>",
            "</html>",
        ]
    )

    log_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(f"    📝 누락 HTML 저장: {log_path}")


def save_page_html_log(
    page: Page,
    category_name: str,
    category_code: str,
    page_idx: int,
    reason: str,
) -> None:
    """
    페이지 자체를 처리하지 못한 경우 전체 HTML을 저장합니다.
    """

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    filename = (
        f"{timestamp}_"
        f"{safe_filename(category_name)}_"
        f"{category_code}_"
        f"page_{page_idx}_error.html"
    )

    log_path = LOG_DIR / filename

    try:
        html = page.content()
    except Exception:
        html = "<html><body>페이지 HTML을 읽지 못했습니다.</body></html>"

    header = (
        f"<!-- 오류 사유: {reason} -->\n"
        f"<!-- 저장 시각: {datetime.now():%Y-%m-%d %H:%M:%S} -->\n"
    )

    log_path.write_text(
        header + html,
        encoding="utf-8",
    )

    print(f"    📝 오류 페이지 저장: {log_path}")


# ============================================================
# 페이지 크롤링
# ============================================================

def crawl_product_page(
    page: Page,
    category: dict,
    page_idx: int,
) -> tuple[list[dict], int]:
    """
    카테고리의 특정 pageIdx를 수집합니다.

    반환값:
        추출된 상품 목록
        실제 상품 li 개수
    """

    category_id = int(category["category_id"])
    category_code = str(category["category_code"])
    category_name = str(category["category_name"])

    url = BASE_URL.format(
        category_code=category_code,
        page_idx=page_idx,
        rows_per_page=ROWS_PER_PAGE,
    )

    last_error: Exception | None = None

    for attempt in range(1, MAX_PAGE_RETRIES + 1):
        try:
            if attempt > 1:
                print(
                    f"    🔄 {page_idx}페이지 재시도 "
                    f"({attempt}/{MAX_PAGE_RETRIES})"
                )

            time.sleep(random.uniform(1.0, 2.0))

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT,
            )

            raise_if_cloudflare(page)

            try:
                page.wait_for_selector(
                    "ul.cate_prd_list",
                    timeout=PRODUCT_LIST_TIMEOUT,
                )

            except PlaywrightTimeoutError:
                soup = BeautifulSoup(
                    page.content(),
                    "html.parser",
                )

                if is_no_product_page(soup):
                    return [], 0

                raise RuntimeError(
                    f"{category_name} {page_idx}페이지에서 "
                    "상품 목록 영역을 찾지 못했습니다."
                )

            # 이미지 lazy-loading과 내부 요소 생성을 위해 아래로 이동
            page.evaluate(
                "window.scrollTo(0, document.body.scrollHeight)"
            )
            page.wait_for_timeout(1_000)

            rendered_count = wait_for_product_count_stable(page)

            soup = BeautifulSoup(
                page.content(),
                "html.parser",
            )

            products, skipped_items, real_item_count = (
                extract_products_from_soup(
                    soup=soup,
                    category_id=category_id,
                )
            )

            if not products:
                if is_no_product_page(soup):
                    return [], 0

                raise RuntimeError(
                    f"{category_name} {page_idx}페이지에서 "
                    f"상품 li는 {rendered_count}개 확인됐지만 "
                    "추출된 상품이 없습니다."
                )

            if skipped_items:
                print(
                    f"    ⚠️ 상품 정보 추출 실패: "
                    f"{len(skipped_items)}개"
                )

                for skipped in skipped_items[:5]:
                    print(
                        f"       - li {skipped['index']}: "
                        f"{skipped['reason']}"
                    )

                if len(skipped_items) > 5:
                    print(
                        f"       - 외 {len(skipped_items) - 5}개"
                    )

                save_failed_item_log(
                    category_name=category_name,
                    category_code=category_code,
                    page_idx=page_idx,
                    skipped_items=skipped_items,
                )

            print(
                f"    ✅ {page_idx}페이지: "
                f"상품 영역 {real_item_count}개 / "
                f"추출 {len(products)}개"
            )

            return products, real_item_count

        except RobotVerificationDetectedError:
            # 인증 화면은 반복 접근하지 않고 즉시 전체 실행을 중단합니다.
            raise

        except Exception as error:
            last_error = error

            print(
                f"    ⚠️ {page_idx}페이지 수집 실패 "
                f"({attempt}/{MAX_PAGE_RETRIES}): {error}"
            )

            if attempt < MAX_PAGE_RETRIES:
                page.wait_for_timeout(
                    int(random.uniform(1.5, 3.0) * 1_000)
                )

    save_page_html_log(
        page=page,
        category_name=category_name,
        category_code=category_code,
        page_idx=page_idx,
        reason=str(last_error),
    )

    raise RuntimeError(
        f"{category_name} ({category_code}) "
        f"{page_idx}페이지 수집에 최종 실패했습니다."
    ) from last_error


# ============================================================
# 카테고리 전체 페이지 크롤링
# ============================================================

def crawl_category(
    page: Page,
    category: dict,
) -> list[dict]:
    """
    한 카테고리의 모든 pageIdx를 순회합니다.
    """

    category_code = str(category["category_code"])
    category_name = str(category["category_name"])

    print()
    print(f"📂 크롤링 중: {category_name} ({category_code})")

    category_products_by_code: dict[str, dict] = {}

    for page_idx in range(1, MAX_PAGES_PER_CATEGORY + 1):
        page_products, real_item_count = crawl_product_page(
            page=page,
            category=category,
            page_idx=page_idx,
        )

        # 첫 페이지부터 상품이 없는 정상 카테고리
        if not page_products:
            if page_idx == 1:
                print("  ✅ 수집 완료: 0개")

            break

        new_product_count = 0

        for product in page_products:
            code = product["product_code"]

            if code not in category_products_by_code:
                category_products_by_code[code] = product
                new_product_count += 1

            else:
                existing = category_products_by_code[code]

                if product["product_name"]:
                    existing["product_name"] = product["product_name"]

                if product["product_image_url"]:
                    existing["product_image_url"] = (
                        product["product_image_url"]
                    )

        # 다음 페이지인데 전부 이전 페이지와 동일한 상품이면
        # 잘못된 pageIdx 반복 또는 마지막 페이지 초과로 판단
        if page_idx > 1 and new_product_count == 0:
            print(
                f"    ℹ️ {page_idx}페이지에서 신규 상품이 없어 "
                "페이지 순회를 종료합니다."
            )
            break

        # 정상적으로 마지막 페이지는 보통 24개보다 적습니다.
        if real_item_count < ROWS_PER_PAGE:
            print(
                f"    ℹ️ 마지막 페이지 판단: "
                f"{real_item_count}개 < {ROWS_PER_PAGE}개"
            )
            break

    else:
        raise RuntimeError(
            f"{category_name} 카테고리가 "
            f"최대 페이지 제한({MAX_PAGES_PER_CATEGORY})을 초과했습니다."
        )

    result = list(category_products_by_code.values())

    print(
        f"  ✅ 카테고리 전체 수집 완료: "
        f"{len(result)}개"
    )

    return result


# ============================================================
# 전체 카테고리 크롤링
# ============================================================

def crawl_all_products(
    categories: list[dict],
) -> list[dict]:
    """
    모든 대상 카테고리를 수집하고,
    상품코드 기준으로 중복을 제거합니다.

    같은 상품이 여러 카테고리에 등장하면 category_ids에 모두 저장합니다.
    """

    products_by_code: dict[str, dict] = {}

    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        # persistent_context를 사용하면 쿠키, 로컬 스토리지, 세션 등의
        # 브라우저 프로필이 디스크에 보존되어 다음 실행에서 재사용됩니다.
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=False,
            locale="ko-KR",
            viewport={
                "width": 1400,
                "height": 900,
            },
        )

        page = context.pages[0] if context.pages else context.new_page()

        try:
            for index, category in enumerate(
                categories,
                start=1,
            ):
                print()
                print(
                    f"[{index}/{len(categories)}]",
                    end=" ",
                )

                category_products = crawl_category(
                    page=page,
                    category=category,
                )

                for product in category_products:
                    code = product["product_code"]
                    category_id = int(product["category_id"])

                    existing = products_by_code.get(code)

                    if existing is None:
                        products_by_code[code] = {
                            "product_code": code,
                            "product_name": product["product_name"],
                            "product_image_url": (
                                product["product_image_url"]
                            ),
                            "category_ids": {
                                category_id
                            },
                        }

                    else:
                        existing["category_ids"].add(
                            category_id
                        )

                        if product["product_name"]:
                            existing["product_name"] = (
                                product["product_name"]
                            )

                        if product["product_image_url"]:
                            existing["product_image_url"] = (
                                product["product_image_url"]
                            )

        finally:
            context.close()

    products = list(products_by_code.values())

    for product in products:
        product["category_ids"] = sorted(
            product["category_ids"]
        )

    return products


# ============================================================
# DB 저장
# ============================================================

def save_products(
    connection,
    products: list[dict],
    target_category_ids: list[int],
    collected_at: datetime,
) -> None:
    """
    products와 product_categories를 하나의 트랜잭션으로 저장합니다.

    전체 수집이 완료된 경우에만 이 함수가 실행됩니다.
    """

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
            NULL,
            %(product_name)s,
            %(product_image_url)s,
            %(collected_at)s,
            %(collected_at)s,
            1
        )
        ON DUPLICATE KEY UPDATE
            -- 상품명이 실제로 달라졌을 때만 새 값으로 교체합니다.
            product_name = CASE
                WHEN NOT (product_name <=> VALUES(product_name))
                THEN VALUES(product_name)
                ELSE product_name
            END,

            -- 새 이미지 URL이 비어 있지 않고 기존 값과 다를 때만 교체합니다.
            -- 수집 실패로 빈 문자열이 들어온 경우에는 기존 이미지를 유지합니다.
            product_image_url = CASE
                WHEN VALUES(product_image_url) IS NOT NULL
                 AND TRIM(VALUES(product_image_url)) <> ''
                 AND NOT (
                     product_image_url <=> VALUES(product_image_url)
                 )
                THEN VALUES(product_image_url)
                ELSE product_image_url
            END,

            -- 상품 정보가 바뀌지 않아도 오늘 확인했다는 사실은 기록합니다.
            last_seen_at = VALUES(last_seen_at),

            -- 비활성 상품이 다시 발견된 경우 1로 복구합니다.
            is_active = 1
    """

    relation_sql = """
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
              < %s - INTERVAL {DEACTIVATE_AFTER_DAYS} DAY
    """

    product_params = [
        {
            "product_code": product["product_code"],
            "product_name": product["product_name"],
            "product_image_url": (
                product["product_image_url"] or ""
            ),
            "collected_at": collected_at,
        }
        for product in products
    ]

    cursor = connection.cursor(dictionary=True)

    try:
        # 이전에 열려 있던 트랜잭션이 있다면 정리
        connection.commit()
        connection.start_transaction()

        # ----------------------------------------------------
        # 1. products INSERT 또는 UPDATE
        # ----------------------------------------------------

        for start in range(
            0,
            len(product_params),
            BATCH_SIZE,
        ):
            batch = product_params[
                start:start + BATCH_SIZE
            ]

            cursor.executemany(
                product_sql,
                batch,
            )

        # ----------------------------------------------------
        # 2. 상품코드에 해당하는 product_id 조회
        # ----------------------------------------------------

        code_to_id: dict[str, int] = {}

        product_codes = [
            product["product_code"]
            for product in products
        ]

        for start in range(
            0,
            len(product_codes),
            BATCH_SIZE,
        ):
            batch = product_codes[
                start:start + BATCH_SIZE
            ]

            placeholders = ",".join(
                ["%s"] * len(batch)
            )

            select_sql = f"""
                SELECT
                    product_id,
                    product_code
                FROM products
                WHERE product_code IN ({placeholders})
            """

            cursor.execute(
                select_sql,
                tuple(batch),
            )

            for row in cursor.fetchall():
                code_to_id[row["product_code"]] = int(
                    row["product_id"]
                )

        missing_product_ids = [
            code
            for code in product_codes
            if code not in code_to_id
        ]

        if missing_product_ids:
            raise RuntimeError(
                "product_id를 조회하지 못한 상품이 있습니다: "
                + ", ".join(missing_product_ids[:10])
            )

        # ----------------------------------------------------
        # 3. 현재 대상 카테고리의 기존 연결 삭제
        # ----------------------------------------------------

        for start in range(
            0,
            len(target_category_ids),
            BATCH_SIZE,
        ):
            batch = target_category_ids[
                start:start + BATCH_SIZE
            ]

            placeholders = ",".join(
                ["%s"] * len(batch)
            )

            delete_sql = f"""
                DELETE FROM product_categories
                WHERE category_id IN ({placeholders})
            """

            cursor.execute(
                delete_sql,
                tuple(batch),
            )

        # ----------------------------------------------------
        # 4. 현재 수집 결과로 카테고리 연결 재생성
        # ----------------------------------------------------

        relations = []

        for product in products:
            product_id = code_to_id[
                product["product_code"]
            ]

            for category_id in product["category_ids"]:
                relations.append(
                    {
                        "product_id": product_id,
                        "category_id": int(category_id),
                    }
                )

        for start in range(
            0,
            len(relations),
            BATCH_SIZE,
        ):
            batch = relations[
                start:start + BATCH_SIZE
            ]

            cursor.executemany(
                relation_sql,
                batch,
            )

        # ----------------------------------------------------
        # 5. 일정 기간 미확인 상품 비활성화
        # ----------------------------------------------------

        cursor.execute(
            deactivate_sql,
            (collected_at,),
        )

        deactivated_count = cursor.rowcount

        connection.commit()

        print()
        print(
            f"✅ products 저장 완료: "
            f"{len(products)}개"
        )
        print(
            f"✅ product_categories 저장 완료: "
            f"{len(relations)}개 연결"
        )
        print(
            f"⛔ {DEACTIVATE_AFTER_DAYS}일 이상 "
            f"미확인 상품 비활성화: "
            f"{deactivated_count}개"
        )

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
    print(
        f"상품목록 크롤링 시작: "
        f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    )
    print("=" * 60)

    db = DBManager()

    try:
        db.connect()

        connection = db.connection

        if connection is None:
            raise RuntimeError("DB 연결 실패")

        categories = get_target_categories(
            connection
        )

        if not categories:
            print("⚠️ 대상 카테고리가 없습니다.")
            return

        print(
            f"📌 대상 카테고리: "
            f"{len(categories)}개"
        )

        products = crawl_all_products(
            categories
        )

        if not products:
            raise RuntimeError(
                "전체 카테고리에서 수집된 상품이 없습니다."
            )

        collected_at = datetime.now()

        target_category_ids = [
            int(category["category_id"])
            for category in categories
        ]

        save_products(
            connection=connection,
            products=products,
            target_category_ids=target_category_ids,
            collected_at=collected_at,
        )

    except KeyboardInterrupt:
        print()
        print("⚠️ 사용자가 작업을 중단했습니다.")
        print("⚠️ DB 저장 전이라면 수집 결과는 반영되지 않습니다.")

    except Exception as error:
        print()
        print(f"❌ 작업 실패: {error}")

    finally:
        db.close()

    print("=" * 60)
    print(
        f"작업 종료: "
        f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()