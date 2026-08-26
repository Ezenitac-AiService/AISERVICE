# oliview_test DB 이용
# 활성 상품(is_active = 1)의 옵션을 크롤링하여 product_options 테이블에 저장
# 상품 10개 단위로 DB 반영 후 COMMIT
#
# 실행 흐름
# 1. products.is_active = 1인 상품 조회
# 2. 상품 10개 옵션을 먼저 메모리에 수집
# 3. 10개가 모두 정상 수집되면 product_options UPSERT
# 4. 각 상품의 products.option_checked_at 갱신
# 5. 상품 10개 단위 COMMIT
#
# 판매 상태
# - is_active = 1: 현재 옵션 JSON에서 확인되었거나 3일 이내 확인된 옵션
# - is_active = 0: 마지막 확인 후 3일 이상 지난 옵션
# - is_sale_available = 1: 판매 가능 옵션
# - is_sale_available = 0: option_name이 X 또는 판매종료인 옵션

# 5:00~
import random
import sys
import time
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
    "getGoodsDetail.do?goodsNo={product_code}&tab=review"
)

PROFILE_DIR = (
    PROJECT_ROOT
    / "browser_profile"
    / "oliveyoung_product_options"
)

BATCH_SIZE = 10

PAGE_TIMEOUT = 30_000
OPTION_JSON_TIMEOUT = 25_000
REVIEW_TAB_TIMEOUT = 10_000

MIN_WAIT_SECONDS = 1.5
MAX_WAIT_SECONDS = 3.0

DEACTIVATE_AFTER_DAYS = 3

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


def chunked(
    values: list[dict],
    size: int,
) -> list[list[dict]]:
    """목록을 size개 단위로 나눕니다."""

    return [
        values[index:index + size]
        for index in range(0, len(values), size)
    ]


# =========================================================
# 활성 상품 조회
# =========================================================
def get_target_products(db: DBManager) -> list[dict]:
    """
    오늘 옵션 크롤링을 완료하지 않은 활성 상품만 조회합니다.

    대상:
    - option_checked_at이 NULL인 상품
    - option_checked_at이 오늘보다 이전인 상품

    오늘 이미 정상적으로 COMMIT된 상품은 재실행 시 제외됩니다.
    """

    sql = """
        SELECT
            product_id,
            product_code,
            option_checked_at
        FROM products
        WHERE is_active = 1
          AND product_code IS NOT NULL
          AND TRIM(product_code) <> ''
          AND (
              option_checked_at IS NULL
              OR option_checked_at < CURDATE()
          )
        ORDER BY
            option_checked_at IS NULL DESC,
            option_checked_at ASC,
            product_id ASC
    """

    db.execute(sql)
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
    이미 리뷰 탭 URL로 접속한 상태에서
    리뷰 영역으로 이동하고 스크롤합니다.
    """

    page.wait_for_timeout(1_500)
    raise_if_cloudflare(page)

    review_area_selectors = [
        "#reviewInfo",
        "#reviewInfoTab",
        ".review_cont",
        ".review_wrap",
        "[id*='reviewInfo']",
    ]

    review_area = find_visible_locator(
        page,
        review_area_selectors,
    )

    if review_area is not None:
        review_area.scroll_into_view_if_needed(
            timeout=REVIEW_TAB_TIMEOUT
        )

        print("   리뷰 영역 이동 완료")

    else:
        print("   리뷰 영역을 찾지 못해 직접 스크롤합니다.")

    for scroll_amount in (900, 1200, 1500, 1800):
        page.mouse.wheel(0, scroll_amount)
        page.wait_for_timeout(800)
        raise_if_cloudflare(page)

# =========================================================
# 상품 상세페이지에서 옵션 JSON 수집
# =========================================================
def capture_option_json(
    page: Page,
    product_code: str,
) -> dict:
    """
    네트워크 응답 감시를 먼저 등록한 후:

    상세페이지 접속
    → 리뷰 탭 클릭
    → 아래로 스크롤
    → productItemReviewCountList JSON 포착
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
        page.wait_for_timeout(1_000)

        click_review_tab_and_scroll(page)

        waited_ms = 0

        while waited_ms < OPTION_JSON_TIMEOUT:
            raise_if_cloudflare(page)

            if captured["payload"] is not None:
                break

            if waited_ms in (3_000, 7_000, 12_000):
                page.mouse.wheel(0, 800)

            page.wait_for_timeout(500)
            waited_ms += 500

        raise_if_cloudflare(page)

        if captured["payload"] is None:
            raise OptionJsonNotFoundError(
                "리뷰 탭 클릭 및 스크롤 후에도 "
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
    data.productItemReviewCountList만 사용하고,
    goodsNumber가 현재 product_code와 같은 옵션만 추출합니다.

    JSON에서 오늘 확인된 옵션:
        is_active = 1

    option_name이 X 또는 판매종료:
        is_sale_available = 0
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

        normalized_status = (
            option_name
            .replace(" ", "")
            .upper()
        )

        is_sale_available = (
            0
            if normalized_status in {"X", "판매종료"}
            else 1
        )

        collected_options[option_number] = {
            "option_number": option_number,
            "option_name": option_name,
            "review_count": review_count,
            "is_active": 1,
            "is_sale_available": is_sale_available,
        }

    return list(collected_options.values())


# =========================================================
# product_options 저장
# =========================================================
def upsert_product_options(
    db: DBManager,
    product_id: int,
    options: list[dict],
) -> int:
    """
    신규 옵션은 INSERT하고, 기존 옵션은 갱신합니다.

    first_collected_at:
        기존 옵션에서는 변경하지 않습니다.

    last_seen_at:
        오늘 JSON에서 확인된 옵션만 NOW()로 갱신합니다.
    """

    sql = """
        INSERT INTO product_options (
            product_id,
            option_number,
            option_name,
            review_count,
            first_collected_at,
            last_seen_at,
            is_active,
            is_sale_available
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            NOW(),
            NOW(),
            1,
            %s
        )
        ON DUPLICATE KEY UPDATE
            option_name = VALUES(option_name),
            review_count = VALUES(review_count),
            last_seen_at = NOW(),
            is_active = 1,
            is_sale_available = VALUES(is_sale_available)
    """

    saved_count = 0

    for option in options:
        db.execute(
            sql,
            (
                product_id,
                option["option_number"],
                option["option_name"],
                option["review_count"],
                option["is_sale_available"],
            ),
        )

        saved_count += 1

    return saved_count


def deactivate_stale_options(
    db: DBManager,
    product_id: int,
) -> None:
    """
    해당 상품의 옵션 JSON을 오늘 정상적으로 확인한 경우에만 실행합니다.

    마지막 확인 후 3일 이상 지난 옵션을 is_active = 0으로 변경합니다.
    X/판매종료 옵션이라도 JSON에서 계속 확인되면 last_seen_at이 갱신되므로
    is_active는 1로 유지됩니다.
    """

    sql = f"""
        UPDATE product_options
        SET is_active = 0
        WHERE product_id = %s
          AND is_active = 1
          AND last_seen_at < NOW() - INTERVAL {DEACTIVATE_AFTER_DAYS} DAY
    """

    db.execute(sql, (product_id,))


def update_option_checked_at(
    db: DBManager,
    product_id: int,
) -> None:
    """
    옵션 JSON을 정상적으로 읽고 DB 반영까지 수행한 상품만
    option_checked_at을 현재 시각으로 갱신합니다.
    """

    sql = """
        UPDATE products
        SET option_checked_at = NOW()
        WHERE product_id = %s
    """

    db.execute(sql, (product_id,))


def save_batch(
    db: DBManager,
    batch_results: list[dict],
) -> int:
    """
    한 배치의 모든 크롤링이 성공한 후 DB 작업을 실행합니다.

    호출한 쪽에서 성공 시 COMMIT,
    실패 시 ROLLBACK합니다.
    """

    saved_option_count = 0

    for result in batch_results:
        product_id = result["product_id"]
        options = result["options"]

        saved_option_count += upsert_product_options(
            db=db,
            product_id=product_id,
            options=options,
        )

        # 옵션이 0개인 단일 상품도 JSON 정상 확인 결과이므로
        # 기존 옵션이 있었다면 3일 기준 비활성화 대상이 됩니다.
        deactivate_stale_options(
            db=db,
            product_id=product_id,
        )

        update_option_checked_at(
            db=db,
            product_id=product_id,
        )

    return saved_option_count


# =========================================================
# 메인 실행
# =========================================================
def main() -> None:
    db = DBManager()

    committed_product_count = 0
    saved_option_count = 0

    try:
        db.connect()

        products = get_target_products(db)

        if not products:
            print("옵션을 수집할 활성 상품이 없습니다.")
            return

        product_batches = chunked(
            products,
            BATCH_SIZE,
        )

        print("=" * 70)
        print(
            f"전체 옵션 수집 대상: {len(products)}개 상품"
        )
        print(
            f"COMMIT 단위: 상품 {BATCH_SIZE}개"
        )
        print(
            f"전체 배치 수: {len(product_batches)}개"
        )
        print(
            f"브라우저 프로필 경로: {PROFILE_DIR}"
        )
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

                for batch_index, product_batch in enumerate(
                    product_batches,
                    start=1,
                ):
                    print()
                    print("#" * 70)
                    print(
                        f"배치 {batch_index}/"
                        f"{len(product_batches)} 시작"
                    )
                    print(
                        f"이번 배치 상품 수: "
                        f"{len(product_batch)}개"
                    )
                    print("#" * 70)

                    # 현재 배치는 DB에 쓰기 전에 모두 크롤링
                    batch_results: list[dict] = []

                    for item_index, product in enumerate(
                        product_batch,
                        start=1,
                    ):
                        product_id = product["product_id"]

                        product_code = normalize_text(
                            product["product_code"]
                        )

                        global_index = (
                            committed_product_count
                            + item_index
                        )

                        print()
                        print("=" * 70)
                        print(
                            f"[{global_index}/{len(products)}] "
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

                        batch_results.append(
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
                            sale_text = (
                                "판매 가능"
                                if option["is_sale_available"] == 1
                                else "판매 불가"
                            )

                            print(
                                "      - "
                                f"{option['option_number']} / "
                                f"{option['option_name']} / "
                                f"리뷰 {option['review_count']}개 / "
                                f"{sale_text}"
                            )

                        if not options:
                            print("      - 옵션 없는 단일 상품")

                        is_last_product = (
                            batch_index == len(product_batches)
                            and item_index == len(product_batch)
                        )

                        if not is_last_product:
                            wait_seconds = random.uniform(
                                MIN_WAIT_SECONDS,
                                MAX_WAIT_SECONDS,
                            )

                            print(
                                f"   다음 상품까지 "
                                f"{wait_seconds:.1f}초 대기"
                            )

                            time.sleep(wait_seconds)

                    # 배치 전체 크롤링 성공 후 DB 반영
                    try:
                        current_saved_count = save_batch(
                            db=db,
                            batch_results=batch_results,
                        )

                        db.commit()

                    except Exception:
                        db.rollback()
                        raise

                    committed_product_count += len(
                        batch_results
                    )

                    saved_option_count += (
                        current_saved_count
                    )

                    print()
                    print("-" * 70)
                    print(
                        f"배치 {batch_index} COMMIT 완료"
                    )
                    print(
                        f"이번 배치 처리 상품: "
                        f"{len(batch_results)}개"
                    )
                    print(
                        f"이번 배치 저장·갱신 옵션: "
                        f"{current_saved_count}개"
                    )
                    print(
                        f"누적 COMMIT 상품: "
                        f"{committed_product_count}개"
                    )
                    print("-" * 70)

            finally:
                context.close()

        print()
        print("=" * 70)
        print("상품 옵션 크롤링 완료")
        print(
            f"처리 및 COMMIT 상품 수: "
            f"{committed_product_count}개"
        )
        print(
            f"저장·갱신 옵션 수: "
            f"{saved_option_count}개"
        )
        print("=" * 70)

    except CloudflareChallengeError as error:
        db.rollback()

        print()
        print("=" * 70)
        print("Cloudflare/로봇 인증 화면 감지")
        print(f"오류 내용: {error}")
        print("현재 미완료 배치는 저장하지 않았습니다.")
        print(
            f"이전 COMMIT 완료 상품 수: "
            f"{committed_product_count}개"
        )
        print("=" * 70)

    except (
        PlaywrightTimeoutError,
        ReviewTabNotFoundError,
        OptionJsonNotFoundError,
        InvalidOptionJsonError,
    ) as error:
        db.rollback()

        print()
        print("=" * 70)
        print("상품 옵션 수집 실패")
        print(f"오류 내용: {error}")
        print("현재 미완료 배치는 저장하지 않았습니다.")
        print(
            f"이전 COMMIT 완료 상품 수: "
            f"{committed_product_count}개"
        )
        print("=" * 70)

    except Exception as error:
        db.rollback()

        print()
        print("=" * 70)
        print("예상하지 못한 오류가 발생했습니다.")
        print(f"오류 유형: {type(error).__name__}")
        print(f"오류 내용: {error}")
        print("현재 미완료 배치는 ROLLBACK했습니다.")
        print(
            f"이전 COMMIT 완료 상품 수: "
            f"{committed_product_count}개"
        )
        print("=" * 70)

        raise

    finally:
        if hasattr(db, "close"):
            db.close()


if __name__ == "__main__":
    main()