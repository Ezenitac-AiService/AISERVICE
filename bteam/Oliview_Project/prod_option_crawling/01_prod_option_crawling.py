#0727 --> 복사본 프로젝트에서 실행중,,
# 브라우저 프로필을 저장해서 쿠키·세션 재사용
# Cloudflare/로봇 인증 화면 감지
# 인증 화면이 뜨면 즉시 전체 실행 중단
# 활성·미확인 상품을 50개씩 반복 처리
# 각 50개 묶음이 성공할 때마다 DB 저장 및 COMMIT

import random
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Response, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


# =========================================================
# 프로젝트 경로 설정
# =========================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.db_manager import DBManager


# =========================================================
# 기본 설정
# =========================================================
PRODUCT_DETAIL_URL = (
    "https://www.oliveyoung.co.kr/store/goods/"
    "getGoodsDetail.do?goodsNo={product_code}"
)

# 브라우저 쿠키와 세션이 저장되는 폴더
PROFILE_DIR = (
    PROJECT_ROOT
    / "browser_profile"
    / "oliveyoung_product_options"
)

PAGE_TIMEOUT = 30_000

# 리뷰 탭 클릭 및 스크롤 후 JSON을 찾기 위한 설정
INITIAL_PAGE_WAIT_MS = 1_500
AFTER_REVIEW_CLICK_WAIT_MS = 1_500
SCROLL_WAIT_MS = 1_000
FINAL_WAIT_MS = 2_000
MAX_SCROLL_ATTEMPTS = 12

MIN_WAIT_SECONDS = 1.5
MAX_WAIT_SECONDS = 3.0

# 한 묶음에서 처리할 상품 수
BATCH_SIZE = 50

# 한 묶음 저장 완료 후 다음 묶음까지 대기 시간
BATCH_MIN_WAIT_SECONDS = 20.0
BATCH_MAX_WAIT_SECONDS = 40.0


# 화면에 실제로 표시되는 경우에만 인증 화면으로 판단할 문구
VISIBLE_CHALLENGE_TEXTS = [
    "잠시만 기다려 주세요",
    "접속 정보를 확인 중이에요",
    "cloudflare 보안 챌린지",
    "로봇이 아닙니다",
    "사람인지 확인",
    "verify you are human",
    "checking your browser",
    "just a moment",
]

CHALLENGE_TITLE_TEXTS = [
    "잠시만 기다려 주세요",
    "just a moment",
    "attention required",
    "security check",
]


# =========================================================
# 사용자 정의 예외
# =========================================================
class CloudflareChallengeError(RuntimeError):
    """Cloudflare 또는 로봇 인증 화면이 감지된 경우."""


class OptionJsonNotFoundError(RuntimeError):
    """옵션 JSON 응답 자체를 찾지 못한 경우."""


class InvalidOptionJsonError(RuntimeError):
    """옵션 JSON 구조가 올바르지 않은 경우."""


# =========================================================
# 공통 함수
# =========================================================
def normalize_text(value: Any) -> str:
    """
    문자열 앞뒤 공백과 연속된 공백을 정리합니다.

    예:
        " 하이퍼   콜라겐 8+1매 "
        -> "하이퍼 콜라겐 8+1매"
    """

    if value is None:
        return ""

    return " ".join(str(value).split()).strip()


def is_cloudflare_page(page: Page) -> bool:
    """
    실제 Cloudflare/로봇 인증 화면만 감지합니다.

    정상 상품 페이지 안에 숨겨진 문구나 스크립트가 있어도
    인증 화면으로 오인하지 않도록 다음 조건을 사용합니다.

    1. 현재 URL이 실제 Cloudflare challenge 경로인지 확인
    2. 페이지 제목이 challenge 전용 제목과 정확히 가까운지 확인
    3. 화면에 실제로 보이는 인증 관련 요소가 있는지 확인
    """

    try:
        current_url = page.url.lower()

        challenge_url_keywords = [
            "/cdn-cgi/challenge-platform/",
            "/cdn-cgi/challenge/",
            "challenges.cloudflare.com",
        ]

        if any(
            keyword in current_url
            for keyword in challenge_url_keywords
        ):
            print(
                f"   [인증 감지 근거] challenge URL: {page.url}"
            )
            return True

        title = normalize_text(page.title()).lower()

        challenge_titles = {
            "just a moment...",
            "just a moment",
            "잠시만 기다려 주세요",
            "attention required! | cloudflare",
        }

        if title in challenge_titles:
            print(
                f"   [인증 감지 근거] challenge 제목: {title}"
            )
            return True

        visible_challenge_selectors = [
            "iframe[src*='challenges.cloudflare.com']",
            "iframe[src*='turnstile']",
            "input[name='cf-turnstile-response']",
            ".cf-turnstile",
            "#challenge-stage",
            "#cf-challenge-running",
            "[data-sitekey][data-callback]",
        ]

        for selector in visible_challenge_selectors:
            locator = page.locator(selector)

            try:
                count = locator.count()

                for index in range(count):
                    target = locator.nth(index)

                    if target.is_visible(timeout=300):
                        print(
                            "   [인증 감지 근거] "
                            f"표시 중인 인증 요소: {selector}"
                        )
                        return True

            except Exception:
                continue

        visible_texts = [
            "로봇이 아닙니다",
            "사람인지 확인",
            "verify you are human",
            "checking your browser",
            "cloudflare 보안 챌린지",
        ]

        for text in visible_texts:
            locator = page.get_by_text(
                text,
                exact=False,
            )

            try:
                count = min(locator.count(), 5)

                for index in range(count):
                    target = locator.nth(index)

                    if target.is_visible(timeout=300):
                        print(
                            "   [인증 감지 근거] "
                            f"화면에 보이는 문구: {text}"
                        )
                        return True

            except Exception:
                continue

        return False

    except Exception as error:
        print(
            "   인증 화면 검사 중 오류가 발생했지만 "
            f"정상 페이지로 계속 진행합니다: {error}"
        )
        return False


def raise_if_cloudflare(page: Page) -> None:
    """
    인증 화면이 감지되면 즉시 예외를 발생시킵니다.
    """

    if is_cloudflare_page(page):
        raise CloudflareChallengeError(
            "Cloudflare 또는 로봇 인증 화면이 감지되었습니다."
        )


# =========================================================
# products 테이블에서 전체 상품 조회
# =========================================================
def get_target_products(db: DBManager) -> list[dict]:
    """
    옵션 확인이 필요한 활성 상품을 최대 BATCH_SIZE개 조회합니다.

    우선순위:
        1. option_checked_at이 NULL인 미확인 상품
        2. product_id가 작은 상품

    한 번 정상 확인된 상품은 option_checked_at이 기록되므로
    다음 실행에서는 다시 선택되지 않습니다.
    """

    sql = """
        SELECT
            product_id,
            product_code
        FROM products
        WHERE is_active = 1
          AND option_checked_at IS NULL
          AND product_code IS NOT NULL
          AND TRIM(product_code) <> ''
        ORDER BY product_id
        LIMIT %s
    """

    db.execute(sql, (BATCH_SIZE,))

    return db.fetchall() or []


# =========================================================
# 옵션 JSON 구조 확인
# =========================================================
def is_option_count_json(payload: Any) -> bool:
    """
    다음 구조를 가진 옵션 count JSON인지 확인합니다.

    data
    └── productItemReviewCountList
    """

    if not isinstance(payload, dict):
        return False

    data = payload.get("data")

    if not isinstance(data, dict):
        return False

    return isinstance(
        data.get("productItemReviewCountList"),
        list,
    )


def get_product_item_goods_numbers(
    payload: dict,
) -> set[str]:
    """
    productItemReviewCountList 안에 들어 있는
    goodsNumber 목록을 반환합니다.

    relatedProductReviewCountList는 확인하지 않습니다.
    """

    data = payload.get("data")

    if not isinstance(data, dict):
        return set()

    raw_options = data.get(
        "productItemReviewCountList"
    )

    if not isinstance(raw_options, list):
        return set()

    goods_numbers: set[str] = set()

    for raw_option in raw_options:
        if not isinstance(raw_option, dict):
            continue

        goods_number = normalize_text(
            raw_option.get("goodsNumber")
        )

        if goods_number:
            goods_numbers.add(goods_number)

    return goods_numbers


def contains_current_product(
    payload: dict,
    product_code: str,
) -> bool:
    """
    productItemReviewCountList에 현재 크롤링 중인
    product_code가 포함되어 있는지 확인합니다.
    """

    goods_numbers = get_product_item_goods_numbers(
        payload
    )

    return product_code in goods_numbers


# =========================================================
# 리뷰 영역 작동 유도
# =========================================================
def click_review_tab(page: Page) -> bool:
    """
    리뷰 관련 버튼 또는 탭을 찾아 클릭합니다.

    클릭에 성공하면 True,
    클릭할 수 있는 요소가 없으면 False를 반환합니다.
    """

    review_tab_selectors = [
        "button:has-text('리뷰')",
        "a:has-text('리뷰')",
        "[data-attr*='리뷰']",
    ]

    for selector in review_tab_selectors:
        locator = page.locator(selector).first

        try:
            if not locator.is_visible(timeout=1_000):
                continue

            print(
                f"   리뷰 탭 클릭: {selector}"
            )

            locator.click(timeout=3_000)

            return True

        except Exception:
            continue

    print(
        "   클릭 가능한 리뷰 탭을 찾지 못했습니다."
    )

    return False


# =========================================================
# 상품 상세페이지에서 현재 상품 옵션 JSON 수집
# =========================================================
def capture_option_json(
    page: Page,
    product_code: str,
) -> dict:
    """
    상품 상세페이지에 접속한 뒤 리뷰 탭을 클릭하고
    단계적으로 스크롤하면서 옵션 count JSON을 찾습니다.

    조건:
        productItemReviewCountList 구조를 가진 JSON 중
        현재 product_code가 실제로 포함된 JSON만 채택합니다.

    다른 상품번호만 들어 있는 JSON은 무시하고
    다음 네트워크 응답을 계속 기다립니다.
    """

    captured: dict[str, Any] = {
        "payload": None,
        "response_url": None,
    }

    detected_json_count = 0

    def handle_response(response: Response) -> None:
        """
        페이지의 JSON 응답을 확인합니다.

        현재 상품코드가 productItemReviewCountList에
        포함된 경우에만 최종 옵션 JSON으로 확정합니다.
        """

        nonlocal detected_json_count

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

            if not is_option_count_json(payload):
                return

            detected_json_count += 1

            goods_numbers = (
                get_product_item_goods_numbers(
                    payload
                )
            )

            print(
                "   count JSON 감지 "
                f"#{detected_json_count}: "
                f"현재={product_code}, "
                f"JSON 상품={sorted(goods_numbers)}"
            )

            # productItemReviewCountList가 빈 목록이면
            # 옵션이 없는 단일 상품일 수 있으므로 정상 JSON으로 채택합니다.
            # 목록에 값이 있다면 현재 상품코드가 포함된 JSON만 채택합니다.
            if goods_numbers and not contains_current_product(
                payload=payload,
                product_code=product_code,
            ):
                print(
                    "   현재 상품과 다른 count JSON이므로 "
                    "무시합니다."
                )
                return

            captured["payload"] = payload
            captured["response_url"] = (
                response.url
            )

            print(
                "   현재 상품의 count JSON을 "
                "확정했습니다."
            )

        except Exception:
            # JSON 파싱 불가 응답 등은 무시
            return

    page.on(
        "response",
        handle_response,
    )

    detail_url = PRODUCT_DETAIL_URL.format(
        product_code=product_code,
    )

    try:
        # 이전 상품의 스크롤 위치와 관계없이 새 페이지 접속
        page.goto(
            detail_url,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT,
        )

        # 1. 접속 직후 인증 화면 확인
        raise_if_cloudflare(page)

        # 2. 기본 페이지 로딩 대기
        page.wait_for_timeout(
            INITIAL_PAGE_WAIT_MS
        )

        # 초기 로딩 중 이미 현재 상품 JSON이 잡힌 경우
        if captured["payload"] is not None:
            print(
                f"   옵션 JSON 발견: "
                f"{captured['response_url']}"
            )

            return captured["payload"]

        # 3. 리뷰 탭 클릭 시도
        review_clicked = click_review_tab(page)

        if review_clicked:
            page.wait_for_timeout(
                AFTER_REVIEW_CLICK_WAIT_MS
            )

        # 리뷰 버튼 클릭 후 인증 화면 검사
        raise_if_cloudflare(page)

        if captured["payload"] is not None:
            print(
                f"   옵션 JSON 발견: "
                f"{captured['response_url']}"
            )

            return captured["payload"]

        # 4. 단계적으로 스크롤하면서 지연 로딩 유도
        for scroll_attempt in range(
            1,
            MAX_SCROLL_ATTEMPTS + 1,
        ):
            raise_if_cloudflare(page)

            if captured["payload"] is not None:
                break

            print(
                f"   현재 상품 옵션 JSON 대기 중: "
                f"스크롤 {scroll_attempt}/"
                f"{MAX_SCROLL_ATTEMPTS}"
            )

            page.evaluate(
                """
                () => {
                    window.scrollBy({
                        top: window.innerHeight * 0.8,
                        behavior: "smooth"
                    });
                }
                """
            )

            page.wait_for_timeout(
                SCROLL_WAIT_MS
            )

        # 5. 그래도 없으면 페이지 맨 아래로 이동
        if captured["payload"] is None:
            print(
                "   페이지 하단으로 이동해 "
                "마지막으로 확인합니다."
            )

            page.evaluate(
                """
                () => {
                    window.scrollTo({
                        top: document.body.scrollHeight,
                        behavior: "smooth"
                    });
                }
                """
            )

            page.wait_for_timeout(
                FINAL_WAIT_MS
            )

        raise_if_cloudflare(page)

        if captured["payload"] is None:
            raise OptionJsonNotFoundError(
                "옵션 count JSON 응답을 찾지 못했습니다: "
                f"{product_code}"
            )

        print(
            f"   옵션 JSON 발견: "
            f"{captured['response_url']}"
        )

        return captured["payload"]

    finally:
        # 다음 상품에서 이전 이벤트 리스너가 실행되지 않도록 제거
        page.remove_listener(
            "response",
            handle_response,
        )


# =========================================================
# 현재 상품 옵션 추출
# =========================================================
def extract_current_product_options(
    payload: dict,
    product_code: str,
) -> list[dict]:
    """
    data.productItemReviewCountList만 사용합니다.

    relatedProductReviewCountList는 사용하지 않습니다.

    goodsNumber가 현재 product_code와 같은 옵션만 추출합니다.

    optionName이 정확히 "판매종료"이면:
        is_active = 0

    그 외 옵션명이 있으면:
        is_active = 1
    """

    data = payload.get("data")

    if not isinstance(data, dict):
        raise InvalidOptionJsonError(
            "JSON의 data 구조가 올바르지 않습니다: "
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

    # 현재 상품번호에 해당하는 옵션이 실제로 있었는지 확인합니다.
    current_product_option_found = False

    # option_number 기준으로 중복 제거
    collected_options: dict[str, dict] = {}

    for raw_option in raw_options:
        if not isinstance(raw_option, dict):
            continue

        goods_number = normalize_text(
            raw_option.get("goodsNumber")
        )

        # 현재 상품과 다른 상품은 제외
        if goods_number != product_code:
            continue

        current_product_option_found = True

        option_number = normalize_text(
            raw_option.get("itemNumber")
        )

        option_name = normalize_text(
            raw_option.get("optionName")
        )

        if not option_number:
            print(
                "   옵션번호가 없어 제외합니다: "
                f"{raw_option}"
            )
            continue

        if not option_name:
            print(
                "   옵션명이 없어 제외합니다: "
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

        # optionName이 "판매종료" 또는 "X"이면 비활성 처리
        is_active = (
            0
            if option_name in {"판매종료", "X"}
            else 1
        )

        collected_options[option_number] = {
            "option_number": option_number,
            "option_name": option_name,
            "review_count": review_count,
            "is_active": is_active,
        }

    # productItemReviewCountList가 비어 있으면 옵션 없는 상품으로 처리합니다.
    if not raw_options:
        print(
            f"   옵션이 없는 상품입니다: {product_code}"
        )
        return []

    # 목록에 다른 상품 옵션만 있고 현재 상품 옵션은 없다면
    # 잘못된 JSON을 확정한 것이므로 오류로 처리합니다.
    if not current_product_option_found:
        raise InvalidOptionJsonError(
            "확정한 JSON에 현재 상품 옵션이 없습니다: "
            f"{product_code}"
        )

    # 현재 상품 옵션 행은 있었지만 필수값 누락으로 모두 제외된 경우는
    # 데이터 구조 이상이므로 기존처럼 오류 처리합니다.
    if not collected_options:
        raise InvalidOptionJsonError(
            "현재 상품 옵션은 발견했지만 저장 가능한 "
            f"옵션이 없습니다: {product_code}"
        )

    return list(
        collected_options.values()
    )


# =========================================================
# 전체 옵션 일괄 저장
# =========================================================
def save_all_product_options(
    db: DBManager,
    collected_products: list[dict],
) -> tuple[int, int]:
    """
    이번 묶음의 모든 상품 수집이 성공한 뒤에만 실행합니다.

    1. 옵션이 있으면 product_options에 INSERT/UPDATE
    2. 옵션 유무와 관계없이 products.option_checked_at을 NOW()로 갱신
    3. 호출한 쪽에서 모든 작업 성공 후 한 번만 COMMIT

    반환값:
        (저장·갱신한 옵션 수, 확인 완료 상품 수)
    """

    option_sql = """
        INSERT INTO product_options (
            product_id,
            option_number,
            option_name,
            review_count,
            first_collected_at,
            last_seen_at,
            is_active
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            NOW(),
            NOW(),
            %s
        )
        ON DUPLICATE KEY UPDATE
            option_name = VALUES(option_name),
            review_count = VALUES(review_count),
            last_seen_at = NOW(),
            is_active = VALUES(is_active)
    """

    checked_sql = """
        UPDATE products
        SET option_checked_at = NOW()
        WHERE product_id = %s
    """

    saved_option_count = 0
    checked_product_count = 0

    for product_result in collected_products:
        product_id = product_result["product_id"]
        options = product_result["options"]

        for option in options:
            db.execute(
                option_sql,
                (
                    product_id,
                    option["option_number"],
                    option["option_name"],
                    option["review_count"],
                    option["is_active"],
                ),
            )
            saved_option_count += 1

        # 옵션이 없는 상품도 정상 확인을 마쳤으므로 갱신합니다.
        db.execute(checked_sql, (product_id,))
        checked_product_count += 1

    return saved_option_count, checked_product_count


# =========================================================
# 메인 실행
# =========================================================
def main() -> None:
    """
    실행 순서:

    1. DB 연결
    2. 활성·옵션 미확인 상품을 최대 50개 조회
    3. 해당 묶음의 옵션 JSON을 모두 수집
    4. 50개 묶음이 모두 성공하면 옵션 저장 및
       option_checked_at 갱신
    5. 묶음 단위로 COMMIT
    6. 일정 시간 대기 후 다음 50개를 다시 조회
    7. 미확인 활성 상품이 없으면 종료

    한 묶음에서 오류가 발생하면 그 묶음만 ROLLBACK합니다.
    이전 묶음에서 이미 COMMIT한 데이터는 유지됩니다.
    """

    db = DBManager()

    try:
        db.connect()

        PROFILE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        print("=" * 70)
        print(f"묶음당 처리 상품 수: {BATCH_SIZE}개")
        print(f"브라우저 프로필 경로: {PROFILE_DIR}")
        print(
            "DB 저장 방식: "
            f"{BATCH_SIZE}개 묶음별 저장 및 COMMIT"
        )
        print("=" * 70)

        with sync_playwright() as playwright:
            # 브라우저 하나를 계속 사용하여 쿠키와 세션을 재사용합니다.
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

                page.set_default_timeout(PAGE_TIMEOUT)

                batch_number = 0
                total_product_count = 0
                total_option_count = 0
                total_without_option_count = 0

                while True:
                    # 직전 묶음의 DB 조회 결과가 남지 않도록
                    # 묶음마다 새로 대상 상품을 조회합니다.
                    products = get_target_products(db)

                    if not products:
                        print()
                        print("=" * 70)
                        print("옵션을 확인할 활성·미확인 상품이 없습니다.")
                        print("전체 옵션 크롤링을 종료합니다.")
                        print(f"총 처리 상품 수: {total_product_count}개")
                        print(f"총 저장·갱신 옵션 수: {total_option_count}개")
                        print(
                            "총 옵션 없는 상품 수: "
                            f"{total_without_option_count}개"
                        )
                        print("=" * 70)
                        break

                    batch_number += 1

                    # 묶음마다 메모리 목록을 새로 생성합니다.
                    collected_products: list[dict] = []
                    products_without_options: list[dict] = []

                    print()
                    print("=" * 70)
                    print(
                        f"{batch_number}번째 묶음 시작: "
                        f"{len(products)}개 상품"
                    )
                    print("=" * 70)

                    try:
                        for index, product in enumerate(
                            products,
                            start=1,
                        ):
                            product_id = product["product_id"]

                            product_code = normalize_text(
                                product["product_code"]
                            )

                            print()
                            print("-" * 70)
                            print(
                                f"[{batch_number}번째 묶음 "
                                f"{index}/{len(products)}] "
                                f"{product_code}"
                            )
                            print(f"product_id: {product_id}")

                            payload = capture_option_json(
                                page=page,
                                product_code=product_code,
                            )

                            options = (
                                extract_current_product_options(
                                    payload=payload,
                                    product_code=product_code,
                                )
                            )

                            collected_products.append(
                                {
                                    "product_id": product_id,
                                    "product_code": product_code,
                                    "options": options,
                                }
                            )

                            if options:
                                print(
                                    "   메모리 수집 완료: "
                                    f"{len(options)}개 옵션"
                                )
                            else:
                                print(
                                    "   메모리 수집 완료: 옵션 없음"
                                )
                                products_without_options.append(
                                    {
                                        "product_code": product_code,
                                    }
                                )

                            for option in options:
                                status_text = (
                                    "비활성"
                                    if option["is_active"] == 0
                                    else "활성"
                                )

                                print(
                                    "      - "
                                    f"{option['option_number']} / "
                                    f"{option['option_name']} / "
                                    f"리뷰 "
                                    f"{option['review_count']}개 / "
                                    f"{status_text}"
                                )

                            if index < len(products):
                                wait_seconds = random.uniform(
                                    MIN_WAIT_SECONDS,
                                    MAX_WAIT_SECONDS,
                                )

                                print(
                                    "   다음 상품까지 "
                                    f"{wait_seconds:.1f}초 대기"
                                )

                                time.sleep(wait_seconds)

                        print()
                        print("=" * 70)
                        print(
                            f"{batch_number}번째 묶음 수집 성공"
                        )
                        print(
                            f"{batch_number}번째 묶음 DB 저장 시작"
                        )
                        print("=" * 70)

                        saved_count, checked_count = (
                            save_all_product_options(
                                db=db,
                                collected_products=(
                                    collected_products
                                ),
                            )
                        )

                        # 현재 묶음의 모든 DB 작업이 성공한 뒤 커밋합니다.
                        db.commit()

                        total_product_count += checked_count
                        total_option_count += saved_count
                        total_without_option_count += len(
                            products_without_options
                        )

                        print()
                        print("=" * 70)
                        print(
                            f"{batch_number}번째 묶음 COMMIT 완료"
                        )
                        print(
                            f"처리 상품 수: {checked_count}개"
                        )
                        print(
                            "저장·갱신 옵션 수: "
                            f"{saved_count}개"
                        )
                        print(
                            "옵션 없는 상품 수: "
                            f"{len(products_without_options)}개"
                        )
                        print("=" * 70)

                        if products_without_options:
                            print("옵션이 없는 상품 코드:")
                            for product in products_without_options:
                                print(
                                    f"  - "
                                    f"{product['product_code']}"
                                )

                    except Exception:
                        # 현재 묶음에서 발생한 미커밋 DB 작업만 취소합니다.
                        db.rollback()
                        raise

                    # 마지막 묶음이 BATCH_SIZE보다 작았다면
                    # 다음 조회에서 대상이 없을 가능성이 높지만,
                    # 신규 데이터가 동시에 들어올 수도 있으므로
                    # 다시 한 번 DB를 조회하도록 반복합니다.
                    batch_wait_seconds = random.uniform(
                        BATCH_MIN_WAIT_SECONDS,
                        BATCH_MAX_WAIT_SECONDS,
                    )

                    print()
                    print(
                        f"다음 {BATCH_SIZE}개 처리 전 "
                        f"{batch_wait_seconds:.1f}초 대기"
                    )

                    time.sleep(batch_wait_seconds)

            finally:
                context.close()

    except CloudflareChallengeError as error:
        db.rollback()

        print()
        print("=" * 70)
        print("Cloudflare/로봇 인증 화면 감지")
        print(f"오류 내용: {error}")
        print("현재 묶음 실행을 즉시 중단했습니다.")
        print(
            "현재 묶음의 product_options와 "
            "option_checked_at은 변경되지 않았습니다."
        )
        print(
            "이전에 COMMIT 완료된 묶음은 그대로 유지됩니다."
        )
        print("=" * 70)

    except (
        PlaywrightTimeoutError,
        OptionJsonNotFoundError,
        InvalidOptionJsonError,
    ) as error:
        db.rollback()

        print()
        print("=" * 70)
        print("상품 옵션 수집 실패")
        print(f"오류 내용: {error}")
        print("현재 묶음 실행을 중단했습니다.")
        print(
            "현재 묶음의 product_options와 "
            "option_checked_at은 변경되지 않았습니다."
        )
        print(
            "이전에 COMMIT 완료된 묶음은 그대로 유지됩니다."
        )
        print("=" * 70)

    except KeyboardInterrupt:
        db.rollback()

        print()
        print("=" * 70)
        print("사용자가 실행을 중단했습니다.")
        print("현재 처리 중이던 묶음은 ROLLBACK했습니다.")
        print(
            "이전에 COMMIT 완료된 묶음은 그대로 유지됩니다."
        )
        print("=" * 70)

    except Exception as error:
        db.rollback()

        print()
        print("=" * 70)
        print("예상하지 못한 오류가 발생했습니다.")
        print(f"오류 유형: {type(error).__name__}")
        print(f"오류 내용: {error}")
        print("현재 묶음의 작업을 ROLLBACK했습니다.")
        print(
            "이전에 COMMIT 완료된 묶음은 그대로 유지됩니다."
        )
        print("=" * 70)

        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()