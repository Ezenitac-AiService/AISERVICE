# 설치
# uv add playwright beautifulsoup4 mysql-connector-python
# uv run playwright install chromium

# <추가기능>
# Cloudflare/로봇 인증 화면 감지
# 브라우저 프로필(쿠키/세션)을 디스크에 저장하여 다음 실행에서 재사용
# 인증 화면이 다시 나타나면 우회하지 않고 해당 실행을 중단
import random
import sys
import time
from datetime import datetime
from pathlib import Path
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

from common.db_manager import DBManager


# ============================================================
# 기본 설정
# ============================================================

BASE_URL = (
    "https://www.oliveyoung.co.kr/store/display/"
    "getMCategoryList.do?dispCatNo={category_code}"
)

PAGE_TIMEOUT = 30_000
BRAND_LIST_TIMEOUT = 20_000

MAX_CATEGORY_RETRIES = 3
CLOUDFLARE_WAIT_SECONDS = 180

MIN_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 2.5

DEACTIVATE_AFTER_DAYS = 3

# Playwright 쿠키·로컬스토리지 등 브라우저 세션을 보존할 폴더입니다.
# 최초 1회 수동 인증이 완료된 프로필을 이후 매일 실행에서 재사용합니다.
BROWSER_PROFILE_DIR = PROJECT_ROOT / ".playwright_oliveyoung_profile"


CLOUDFLARE_KEYWORDS = [
    "잠시만 기다려 주세요",
    "접속 정보를 확인 중이에요",
    "사람인지 확인하십시오",
    "Cloudflare 보안 챌린지",
    "challenges.cloudflare.com",
    "cf-turnstile-response",
    "__cf_chl_",
]


NO_BRAND_MESSAGES = [
    "등록된 브랜드가 없습니다",
    "브랜드가 없습니다",
    "검색 결과가 없습니다",
]


# ============================================================
# 공통 함수
# ============================================================

def normalize_text(value: Any) -> str:
    """
    None을 빈 문자열로 바꾸고,
    여러 공백과 줄바꿈을 하나의 공백으로 정리합니다.
    """

    if value is None:
        return ""

    return " ".join(str(value).split()).strip()


# ============================================================
# DB 조회
# ============================================================

def get_category_codes(db: DBManager) -> list[str]:
    """
    categories 테이블에서 브랜드 수집에 사용할 카테고리 코드를 조회합니다.

    현재는 모든 카테고리 코드를 조회합니다.
    특정 대상 카테고리만 사용하려면 WHERE is_target = 1을 추가하면 됩니다.
    """

    sql = """
        SELECT DISTINCT category_code
        FROM categories
        WHERE category_code IS NOT NULL
          AND is_target = 1
          AND TRIM(category_code) <> ''
        ORDER BY category_code
    """

    db.execute(sql)
    rows = db.fetchall()

    return [
        normalize_text(row.get("category_code"))
        for row in rows
        if normalize_text(row.get("category_code"))
    ]


# ============================================================
# Cloudflare 감지 및 대기
# ============================================================

def is_cloudflare_page(page: Page) -> bool:
    """
    현재 페이지가 Cloudflare 또는 로봇 인증 화면인지 확인합니다.
    """

    try:
        html = page.content()
        current_url = page.url
    except Exception:
        return False

    combined = f"{current_url}\n{html}"

    return any(
        keyword.lower() in combined.lower()
        for keyword in CLOUDFLARE_KEYWORDS
    )


def ensure_not_cloudflare(page: Page) -> None:
    """
    저장된 브라우저 프로필을 사용했는데도 Cloudflare/로봇 인증 화면이
    나타나면 자동 우회를 시도하지 않고 현재 실행을 중단합니다.

    체크박스를 단순 클릭하는 것만으로는 인증이 완료되지 않으며,
    인증 토큰을 자동 생성하거나 우회하는 코드는 사용하지 않습니다.
    """

    if not is_cloudflare_page(page):
        return

    raise RuntimeError(
        "Cloudflare/로봇 인증 화면이 감지되었습니다. "
        "저장된 브라우저 세션이 만료되었거나 추가 인증이 필요합니다. "
        "작업 스케줄러 실행을 중단하고, 동일한 프로필로 브라우저를 열어 "
        "수동 인증을 한 번 완료한 뒤 다시 실행해 주세요."
    )


# ============================================================
# 브랜드 목록 상태 확인
# ============================================================

def is_no_brand_page(soup: BeautifulSoup) -> bool:
    """
    실제로 브랜드 목록이 없는 페이지인지 확인합니다.
    """

    text = normalize_text(
        soup.get_text(" ", strip=True)
    )

    return any(
        message in text
        for message in NO_BRAND_MESSAGES
    )


def wait_for_brand_list(page: Page) -> None:
    """
    브랜드 필터 영역 또는 브랜드 체크박스가 나타날 때까지 기다립니다.
    """

    try:
        page.wait_for_selector(
            'ul.brand_list, input[name="searchOnlBrndCdArr"]',
            timeout=BRAND_LIST_TIMEOUT,
        )

    except PlaywrightTimeoutError:
        soup = BeautifulSoup(
            page.content(),
            "html.parser",
        )

        if is_no_brand_page(soup):
            return

        raise RuntimeError(
            "브랜드 목록 영역을 찾지 못했습니다."
        )


# ============================================================
# 브랜드 추출
# ============================================================

def extract_brand_name(brand_input) -> str:
    # 1순위: label의 브랜드명
    label = brand_input.find_next_sibling("label")

    if label:
        brand_name = normalize_text(
            label.get_text(" ", strip=True)
        )

        if brand_name:
            return brand_name

    # 2순위: label이 없을 때만 data-brndnm
    brand_name = normalize_text(
        brand_input.get("data-brndnm")
    )

    if brand_name:
        return brand_name

    return ""

def extract_brands_from_soup(
    soup: BeautifulSoup,
) -> dict[str, str]:
    """
    페이지 HTML에서 브랜드 코드와 브랜드명을 추출합니다.
    """

    unique_brands: dict[str, str] = {}

    selectors = [
        'ul.brand_list input[type="checkbox"]',
        'input[name="searchOnlBrndCdArr"]',
        'input[id^="searchOnlBrndCdArr"]',
    ]

    brand_inputs = []

    for selector in selectors:
        found = soup.select(selector)

        if found:
            brand_inputs.extend(found)

    # 같은 input이 여러 selector에 중복될 수 있으므로 id 기반 중복 제거
    seen_inputs: set[str] = set()
    deduplicated_inputs = []

    for brand_input in brand_inputs:
        key = (
            normalize_text(brand_input.get("id"))
            or normalize_text(brand_input.get("value"))
            or str(brand_input)
        )

        if key in seen_inputs:
            continue

        seen_inputs.add(key)
        deduplicated_inputs.append(brand_input)

    for brand_input in deduplicated_inputs:
        brand_code = normalize_text(
            brand_input.get("value")
        )

        brand_name = extract_brand_name(
            brand_input
        )

        if not brand_code or not brand_name:
            continue

        unique_brands[brand_code] = brand_name

    return unique_brands


# ============================================================
# 카테고리별 브랜드 크롤링
# ============================================================

def crawl_category_brands(
    page: Page,
    category_code: str,
) -> dict[str, str]:
    """
    한 카테고리에서 브랜드 목록을 수집합니다.
    """

    url = BASE_URL.format(
        category_code=category_code
    )

    last_error: Exception | None = None

    for attempt in range(
        1,
        MAX_CATEGORY_RETRIES + 1,
    ):
        try:
            if attempt > 1:
                print(
                    f"    🔄 재시도 "
                    f"({attempt}/{MAX_CATEGORY_RETRIES})"
                )

            time.sleep(
                random.uniform(
                    MIN_DELAY_SECONDS,
                    MAX_DELAY_SECONDS,
                )
            )

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT,
            )

            ensure_not_cloudflare(page)

            wait_for_brand_list(page)

            page.wait_for_timeout(1_000)

            soup = BeautifulSoup(
                page.content(),
                "html.parser",
            )

            brands = extract_brands_from_soup(
                soup
            )

            if brands:
                return brands

            if is_no_brand_page(soup):
                return {}

            raise RuntimeError(
                "브랜드 체크박스는 확인되지 않았고 "
                "브랜드 없음 안내도 찾지 못했습니다."
            )

        except Exception as error:
            last_error = error

            print(
                f"    ⚠️ 카테고리 수집 실패 "
                f"({attempt}/{MAX_CATEGORY_RETRIES}): "
                f"{error}"
            )

            if attempt < MAX_CATEGORY_RETRIES:
                page.wait_for_timeout(
                    int(
                        random.uniform(
                            1.5,
                            3.0,
                        )
                        * 1_000
                    )
                )

    raise RuntimeError(
        f"카테고리 {category_code} 브랜드 수집에 최종 실패했습니다."
    ) from last_error


# ============================================================
# 전체 브랜드 크롤링
# ============================================================

def crawl_unique_brands(
    category_codes: list[str],
) -> tuple[dict[str, str], list[str]]:
    """
    카테고리 페이지를 순회하며 브랜드를 수집합니다.

    반환값:
        unique_brands:
            브랜드 코드 기준 중복 제거 결과

        failed_categories:
            최종 실패한 카테고리 코드 목록
    """

    unique_brands: dict[str, str] = {}
    failed_categories: list[str] = []

    total_count = len(category_codes)

    print("=" * 70)
    print(
        f"🌿 총 {total_count}개 카테고리에서 "
        "브랜드 수집을 시작합니다."
    )
    print("=" * 70)

    with sync_playwright() as playwright:
        BROWSER_PROFILE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        # persistent context는 쿠키·로컬스토리지·Cloudflare 세션을
        # BROWSER_PROFILE_DIR에 저장하고 다음 실행에서 그대로 재사용합니다.
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=False,
            locale="ko-KR",
            viewport={
                "width": 1920,
                "height": 1080,
            },
        )

        pages = context.pages
        page = pages[0] if pages else context.new_page()

        page.set_default_timeout(
            15_000
        )

        try:
            for index, category_code in enumerate(
                category_codes,
                start=1,
            ):
                print()
                print(
                    f"[{index}/{total_count}] "
                    f"카테고리 {category_code} 탐색 중..."
                )

                try:
                    category_brands = (
                        crawl_category_brands(
                            page=page,
                            category_code=category_code,
                        )
                    )

                    for brand_code, brand_name in (
                        category_brands.items()
                    ):
                        unique_brands[
                            brand_code
                        ] = brand_name

                    print(
                        f"    └ 현재 카테고리 브랜드: "
                        f"{len(category_brands)}개"
                    )
                    print(
                        f"    └ 누적 고유 브랜드: "
                        f"{len(unique_brands)}개"
                    )

                except Exception as error:
                    failed_categories.append(
                        category_code
                    )

                    print(
                        f"    ❌ 카테고리 처리 최종 실패: "
                        f"{category_code}"
                    )
                    print(
                        f"       오류 내용: {error}"
                    )

        finally:
            # persistent context를 닫으면 현재 쿠키와 세션이 프로필 폴더에 저장됩니다.
            context.close()

    return (
        unique_brands,
        failed_categories,
    )


# ============================================================
# DB 저장
# ============================================================

def save_brands_to_db(
    db: DBManager,
    brands: dict[str, str],
    collected_at: datetime,
) -> int:
    """
    신규 브랜드는 INSERT하고,
    기존 브랜드는 브랜드명, last_seen_at, is_active를 갱신합니다.
    """

    if not brands:
        print(
            "⚠️ DB에 저장할 브랜드가 없습니다."
        )
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
        for brand_code, brand_name
        in brands.items()
    ]

    db.executemany(
        sql,
        brand_data,
    )

    db.commit()

    return len(brand_data)


def deactivate_missing_brands(
    db: DBManager,
) -> int:
    """
    마지막 확인 시각이 지정 기간 이상 지난 브랜드를 비활성화합니다.
    """

    sql = f"""
        UPDATE brands
        SET is_active = 0
        WHERE is_active = 1
          AND last_seen_at
              < NOW() - INTERVAL {DEACTIVATE_AFTER_DAYS} DAY
    """

    db.execute(sql)

    affected_rows = db.cursor.rowcount

    db.commit()

    return affected_rows


# ============================================================
# main
# ============================================================

def main() -> None:
    db = DBManager()

    try:
        db.connect()

        collected_at = datetime.now()

        # ----------------------------------------------------
        # 1. 카테고리 코드 조회
        # ----------------------------------------------------

        category_codes = get_category_codes(
            db
        )

        if not category_codes:
            print(
                "⚠️ categories 테이블에서 "
                "category_code를 찾지 못했습니다."
            )
            return

        print(
            f"✅ categories 테이블에서 "
            f"{len(category_codes)}개의 "
            "카테고리 코드를 조회했습니다."
        )

        # ----------------------------------------------------
        # 2. 브랜드 수집
        # ----------------------------------------------------

        unique_brands, failed_categories = (
            crawl_unique_brands(
                category_codes
            )
        )

        if not unique_brands:
            print(
                "❌ 크롤링된 브랜드가 없어 "
                "DB 저장을 중단합니다."
            )
            return

        print()
        print("=" * 70)
        print(
            f"🌿 최종 고유 브랜드 수: "
            f"{len(unique_brands)}개"
        )
        print(
            f"⚠️ 실패한 카테고리 수: "
            f"{len(failed_categories)}개"
        )
        print("=" * 70)

        # ----------------------------------------------------
        # 3. 브랜드 DB 저장
        # ----------------------------------------------------

        saved_count = save_brands_to_db(
            db=db,
            brands=unique_brands,
            collected_at=collected_at,
        )

        print(
            f"✅ 브랜드 {saved_count}개의 "
            "신규 추가 또는 확인 시각 갱신 완료"
        )

        # ----------------------------------------------------
        # 4. 전체 카테고리 성공 시에만 비활성화
        # ----------------------------------------------------

        if not failed_categories:
            deactivated_count = (
                deactivate_missing_brands(
                    db
                )
            )

            print(
                f"✅ {DEACTIVATE_AFTER_DAYS}일 이상 "
                f"확인되지 않은 브랜드 "
                f"{deactivated_count}개 비활성화"
            )

        else:
            print()
            print(
                "⚠️ 일부 카테고리 크롤링이 실패하여 "
                "비활성화 작업을 생략했습니다."
            )
            print(
                "   실패 때문에 실제 입점 브랜드가 "
                "잘못 비활성화되는 것을 방지합니다."
            )
            print(
                "   실패 카테고리:",
                ", ".join(failed_categories),
            )

        print()
        print(
            "🌿 브랜드 동기화 작업이 완료되었습니다."
        )

    except KeyboardInterrupt:
        db.rollback()

        print()
        print(
            "⚠️ 사용자가 작업을 중단했습니다."
        )

    except Exception as error:
        db.rollback()

        print()
        print(
            "❌ 브랜드 동기화 작업 중 "
            "오류가 발생했습니다."
        )
        print(
            f"오류 내용: {error}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()