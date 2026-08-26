# oliview_test DB 이용
# 활성 상품 10개만 옵션 크롤링 후 test_output 폴더에 CSV 저장
# DB에는 INSERT/UPDATE/COMMIT하지 않음

import csv
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    Locator,
    Page,
    Response,
    sync_playwright,
)
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


# =========================================================
# 프로젝트 경로 설정
# =========================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.db_manager3 import DBManager


# =========================================================
# 기본 설정
# =========================================================
PRODUCT_DETAIL_URL = (
    "https://www.oliveyoung.co.kr/store/goods/"
    "getGoodsDetail.do?goodsNo={product_code}"
)

PROFILE_DIR = (
    PROJECT_ROOT
    / "browser_profile"
    / "oliveyoung_product_options"
)

TEST_OUT_DIR = PROJECT_ROOT / "test_output"

MAX_PRODUCTS = 10
PAGE_TIMEOUT = 30_000
OPTION_JSON_TIMEOUT = 25_000
REVIEW_TAB_TIMEOUT = 10_000

MIN_WAIT_SECONDS = 1.5
MAX_WAIT_SECONDS = 3.0

CLOUDFLARE_KEYWORDS = [
    "잠시만 기다려 주세요",
    "접속 정보를 확인 중이에요",
    "Cloudflare 보안 챌린지",
    "challenges.cloudflare.com",
    "cf-turnstile-response",
    "__cf_chl_",
    "로봇이 아닙니다",
    "사람인지 확인",
    "verify you are human",
    "checking your browser",
]


# =========================================================
# 사용자 정의 예외
# =========================================================
class CloudflareChallengeError(RuntimeError):
    """Cloudflare 또는 로봇 인증 화면이 감지된 경우."""


class OptionJsonNotFoundError(RuntimeError):
    """상품 옵션 JSON을 찾지 못한 경우."""


class InvalidOptionJsonError(RuntimeError):
    """옵션 JSON 구조가 올바르지 않은 경우."""


class ReviewTabNotFoundError(RuntimeError):
    """리뷰 탭을 찾거나 클릭하지 못한 경우."""


# =========================================================
# 공통 함수
# =========================================================
def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).split()).strip()


def is_cloudflare_page(page: Page) -> bool:
    try:
        check_text = f"{page.url}\n{page.content()}".lower()

        return any(
            keyword.lower() in check_text
            for keyword in CLOUDFLARE_KEYWORDS
        )

    except Exception:
        return False


def raise_if_cloudflare(page: Page) -> None:
    if is_cloudflare_page(page):
        raise CloudflareChallengeError(
            "Cloudflare 또는 로봇 인증 화면이 감지되었습니다."
        )


# =========================================================
# 활성 상품 10개 조회
# =========================================================
def get_target_products(db: DBManager) -> list[dict]:
    sql = """
        SELECT
            product_id,
            product_code
        FROM products
        WHERE is_active = 1
          AND product_code IS NOT NULL
          AND TRIM(product_code) <> ''
        ORDER BY product_id
        LIMIT %s
    """

    db.execute(sql, (MAX_PRODUCTS,))

    return db.fetchall() or []


# =========================================================
# 옵션 count JSON 판별
# =========================================================
def is_option_count_json(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False

    data = payload.get("data")

    if not isinstance(data, dict):
        return False

    return isinstance(
        data.get("productItemReviewCountList"),
        list,
    )


# =========================================================
# 리뷰 탭 클릭 및 스크롤
# =========================================================
def find_visible_locator(
    page: Page,
    selectors: list[str],
) -> Locator | None:
    """
    여러 선택자를 순서대로 확인하여
    화면에 표시되는 첫 번째 요소를 반환합니다.
    """

    for selector in selectors:
        try:
            locator = page.locator(selector)

            count = locator.count()

            for index in range(count):
                candidate = locator.nth(index)

                if candidate.is_visible():
                    return candidate

        except Exception:
            continue

    return None


def click_review_tab_and_scroll(page: Page) -> None:
    """
    리뷰 탭을 클릭한 뒤 리뷰 영역이 로딩되도록 아래로 스크롤합니다.

    올리브영 페이지 구조가 상품별로 조금 달라도 대응할 수 있도록
    구체적인 선택자부터 텍스트 기반 선택자까지 순서대로 확인합니다.
    """

    review_tab_selectors = [
        # 자주 사용되는 ID/링크 형태
        'a[href="#reviewInfo"]',
        'a[href*="reviewInfo"]',
        '#reviewInfoTab',
        '#reviewTab',
        '[data-tab="review"]',

        # data-attr에 리뷰가 포함된 탭
        'a[data-attr*="리뷰"]',
        'button[data-attr*="리뷰"]',

        # 탭 영역 안의 리뷰 텍스트
        '.goods_tab a:has-text("리뷰")',
        '.tab_list a:has-text("리뷰")',
        '[role="tab"]:has-text("리뷰")',

        # 최후의 텍스트 기반 대체 선택자
        'a:has-text("리뷰")',
        'button:has-text("리뷰")',
    ]

    review_tab = find_visible_locator(
        page,
        review_tab_selectors,
    )

    if review_tab is None:
        raise ReviewTabNotFoundError(
            "리뷰 탭을 찾지 못했습니다."
        )

    try:
        review_tab.scroll_into_view_if_needed(
            timeout=REVIEW_TAB_TIMEOUT
        )

        page.wait_for_timeout(500)

        review_tab.click(
            timeout=REVIEW_TAB_TIMEOUT,
            force=True,
        )

        print("   리뷰 탭 클릭 완료")

    except PlaywrightTimeoutError as error:
        raise ReviewTabNotFoundError(
            "리뷰 탭 클릭 시간이 초과되었습니다."
        ) from error

    # 탭 클릭 직후 첫 번째 로딩 대기
    page.wait_for_timeout(1_000)
    raise_if_cloudflare(page)

    # 리뷰 영역으로 내려가면서 지연 로딩 요청 발생
    for scroll_amount in (900, 1200, 1500):
        page.mouse.wheel(0, scroll_amount)
        page.wait_for_timeout(800)
        raise_if_cloudflare(page)

    # 리뷰 영역 요소가 있으면 한 번 더 해당 위치로 이동
    review_area_selectors = [
        '#reviewInfo',
        '#reviewInfoArea',
        '.review_wrap',
        '.goods_reputation',
        '[class*="review"]',
    ]

    review_area = find_visible_locator(
        page,
        review_area_selectors,
    )

    if review_area is not None:
        try:
            review_area.scroll_into_view_if_needed(
                timeout=5_000
            )
            page.wait_for_timeout(1_000)
        except Exception:
            pass


# =========================================================
# 상품 상세페이지에서 옵션 JSON 수집
# =========================================================
def capture_option_json(
    page: Page,
    product_code: str,
) -> dict:
    """
    1. 응답 감시 시작
    2. 상품 상세페이지 접속
    3. 리뷰 탭 클릭
    4. 리뷰 영역까지 스크롤
    5. productItemReviewCountList JSON 포착
    """

    captured: dict[str, Any] = {
        "payload": None,
        "response_url": None,
    }

    def handle_response(response: Response) -> None:
        if captured["payload"] is not None:
            return

        try:
            content_type = response.headers.get(
                "content-type",
                "",
            ).lower()

            if "json" not in content_type:
                return

            payload = response.json()

            if is_option_count_json(payload):
                captured["payload"] = payload
                captured["response_url"] = response.url

        except Exception:
            return

    # 반드시 페이지 이동 및 리뷰 탭 클릭 전에 응답 감시를 등록
    page.on("response", handle_response)

    detail_url = PRODUCT_DETAIL_URL.format(
        product_code=product_code,
    )

    try:
        page.goto(
            detail_url,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT,
        )

        raise_if_cloudflare(page)

        # 상세페이지 기본 렌더링 대기
        page.wait_for_timeout(1_000)

        # 리뷰 탭 클릭 및 아래로 스크롤해야 옵션 count JSON 발생
        click_review_tab_and_scroll(page)

        waited_ms = 0

        while waited_ms < OPTION_JSON_TIMEOUT:
            raise_if_cloudflare(page)

            if captured["payload"] is not None:
                break

            # 리뷰 데이터가 추가 스크롤에서 늦게 발생하는 경우 대응
            if waited_ms in (3_000, 7_000, 12_000):
                page.mouse.wheel(0, 800)

            page.wait_for_timeout(500)
            waited_ms += 500

        raise_if_cloudflare(page)

        if captured["payload"] is None:
            raise OptionJsonNotFoundError(
                f"리뷰 탭 클릭 및 스크롤 후에도 "
                f"옵션 JSON을 찾지 못했습니다: {product_code}"
            )

        print(
            f"   옵션 JSON 발견: {captured['response_url']}"
        )

        return captured["payload"]

    finally:
        page.remove_listener(
            "response",
            handle_response,
        )


# =========================================================
# 현재 상품의 옵션만 추출
# =========================================================
def extract_current_product_options(
    payload: dict,
    product_code: str,
) -> list[dict]:
    """
    productItemReviewCountList에서 현재 상품의 goodsNumber만 사용합니다.

    is_active:
        JSON에서 오늘 확인된 옵션이므로 항상 1

    is_discontinued:
        optionName이 '판매종료' 또는 'X'인 경우 1
    """

    data = payload.get("data")

    if not isinstance(data, dict):
        raise InvalidOptionJsonError(
            f"JSON의 data 구조가 올바르지 않습니다: "
            f"{product_code}"
        )

    raw_options = data.get(
        "productItemReviewCountList"
    )

    if not isinstance(raw_options, list):
        raise InvalidOptionJsonError(
            "productItemReviewCountList가 "
            f"목록이 아닙니다: {product_code}"
        )

    collected_options: dict[str, dict] = {}

    for raw_option in raw_options:
        if not isinstance(raw_option, dict):
            continue

        goods_number = normalize_text(
            raw_option.get("goodsNumber")
        )

        if goods_number != product_code:
            continue

        option_number = normalize_text(
            raw_option.get("itemNumber")
        )

        option_name = normalize_text(
            raw_option.get("optionName")
        )

        if not option_number:
            print(
                f"   옵션번호가 없어 제외합니다: {raw_option}"
            )
            continue

        if not option_name:
            print(
                f"   옵션명이 없어 제외합니다: "
                f"{product_code}/{option_number}"
            )
            continue

        raw_review_count = raw_option.get(
            "reviewCount",
            0,
        )

        try:
            review_count = max(
                int(raw_review_count or 0),
                0,
            )

        except (TypeError, ValueError):
            review_count = 0

        normalized_status = option_name.replace(" ", "").upper()

        is_discontinued = (
            1
            if normalized_status in {"판매종료", "X"}
            else 0
        )

        collected_options[option_number] = {
            "option_number": option_number,
            "option_name": option_name,
            "review_count": review_count,
            "is_discontinued": is_discontinued,
            # 오늘 JSON에서 실제로 확인된 옵션이므로 활성
            "is_active": 1,
        }

    return list(collected_options.values())


# =========================================================
# CSV 행 생성
# =========================================================
def flatten_csv_rows(
    collected_products: list[dict],
) -> list[dict]:
    rows: list[dict] = []

    collected_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    for product_result in collected_products:
        product_id = product_result["product_id"]
        product_code = product_result["product_code"]
        options = product_result["options"]

        if not options:
            # 옵션 없는 단일 상품도 테스트 결과에서 확인할 수 있도록
            # CSV에 상태 확인용 행을 남깁니다.
            rows.append(
                {
                    "product_id": product_id,
                    "product_code": product_code,
                    "option_number": "",
                    "option_name": "",
                    "review_count": "",
                    "is_discontinued": "",
                    "is_active": "",
                    "crawl_result": "NO_OPTION",
                    "collected_at": collected_at,
                }
            )
            continue

        for option in options:
            rows.append(
                {
                    "product_id": product_id,
                    "product_code": product_code,
                    "option_number": option["option_number"],
                    "option_name": option["option_name"],
                    "review_count": option["review_count"],
                    "is_discontinued": option["is_discontinued"],
                    "is_active": option["is_active"],
                    "crawl_result": "SUCCESS",
                    "collected_at": collected_at,
                }
            )

    return rows


def save_csv(rows: list[dict]) -> Path:
    TEST_OUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_path = (
        TEST_OUT_DIR
        / f"product_options_test_{timestamp}.csv"
    )

    fieldnames = [
        "product_id",
        "product_code",
        "option_number",
        "option_name",
        "review_count",
        "is_discontinued",
        "is_active",
        "crawl_result",
        "collected_at",
    ]

    # Excel에서 한글이 깨지지 않도록 utf-8-sig 사용
    with output_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

    return output_path


# =========================================================
# 메인 실행
# =========================================================
def main() -> None:
    db = DBManager()
    collected_products: list[dict] = []

    try:
        # DBManager 객체 생성 후 반드시 연결
        db.connect()

        products = get_target_products(db)

        if not products:
            print("옵션을 수집할 활성 상품이 없습니다.")
            return

        print("=" * 70)
        print(
            f"CSV 테스트 대상: 활성 상품 {len(products)}개"
        )
        print(
            f"브라우저 프로필 경로: {PROFILE_DIR}"
        )
        print("DB 저장: 하지 않음")
        print("=" * 70)

        PROFILE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        with sync_playwright() as playwright:
            context = (
                playwright.chromium
                .launch_persistent_context(
                    user_data_dir=str(PROFILE_DIR),
                    headless=False,
                    locale="ko-KR",
                    viewport={
                        "width": 1400,
                        "height": 900,
                    },
                )
            )

            try:
                if context.pages:
                    page = context.pages[0]
                else:
                    page = context.new_page()

                page.set_default_timeout(
                    PAGE_TIMEOUT
                )

                for index, product in enumerate(
                    products,
                    start=1,
                ):
                    product_id = product["product_id"]

                    product_code = normalize_text(
                        product["product_code"]
                    )

                    print()
                    print("=" * 70)
                    print(
                        f"[{index}/{len(products)}] "
                        f"{product_code}"
                    )
                    print(f"product_id: {product_id}")

                    payload = capture_option_json(
                        page=page,
                        product_code=product_code,
                    )

                    options = extract_current_product_options(
                        payload=payload,
                        product_code=product_code,
                    )

                    collected_products.append(
                        {
                            "product_id": product_id,
                            "product_code": product_code,
                            "options": options,
                        }
                    )

                    print(
                        f"   메모리 수집 완료: "
                        f"{len(options)}개 옵션"
                    )

                    for option in options:
                        status_text = (
                            "판매종료"
                            if option["is_discontinued"] == 1
                            else "판매중"
                        )

                        print(
                            "      - "
                            f"{option['option_number']} / "
                            f"{option['option_name']} / "
                            f"리뷰 {option['review_count']}개 / "
                            f"{status_text}"
                        )

                    if not options:
                        print("      - 옵션 없는 단일 상품")

                    if index < len(products):
                        wait_seconds = random.uniform(
                            MIN_WAIT_SECONDS,
                            MAX_WAIT_SECONDS,
                        )

                        print(
                            f"   다음 상품까지 "
                            f"{wait_seconds:.1f}초 대기"
                        )

                        time.sleep(wait_seconds)

            finally:
                context.close()

        csv_rows = flatten_csv_rows(
            collected_products
        )

        output_path = save_csv(csv_rows)

        print()
        print("=" * 70)
        print("상품 옵션 CSV 테스트 완료")
        print(
            f"처리 상품 수: "
            f"{len(collected_products)}개"
        )
        print(
            f"CSV 행 수: {len(csv_rows)}개"
        )
        print(f"저장 위치: {output_path}")
        print("DB 데이터는 변경하지 않았습니다.")
        print("=" * 70)

    except CloudflareChallengeError as error:
        print()
        print("=" * 70)
        print("Cloudflare/로봇 인증 화면 감지")
        print(f"오류 내용: {error}")
        print("실행을 중단했습니다.")
        print("DB 데이터는 변경하지 않았습니다.")
        print("=" * 70)

    except (
        PlaywrightTimeoutError,
        ReviewTabNotFoundError,
        OptionJsonNotFoundError,
        InvalidOptionJsonError,
    ) as error:
        print()
        print("=" * 70)
        print("상품 옵션 수집 실패")
        print(f"오류 내용: {error}")
        print("실행을 중단했습니다.")
        print("DB 데이터는 변경하지 않았습니다.")
        print("=" * 70)

    except Exception as error:
        print()
        print("=" * 70)
        print("예상하지 못한 오류가 발생했습니다.")
        print(f"오류 유형: {type(error).__name__}")
        print(f"오류 내용: {error}")
        print("DB 데이터는 변경하지 않았습니다.")
        print("=" * 70)
        raise

    finally:
        if hasattr(db, "close"):
            db.close()


if __name__ == "__main__":
    main()