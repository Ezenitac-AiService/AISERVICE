# oliview_test DB이용

# 브라우저 프로필을 저장해서 쿠키·세션 재사용
# Cloudflare/로봇 인증 화면 감지
# 인증 화면이 뜨면 즉시 전체 실행 중단
# 전체 크롤링 완료 전이면 DB 저장하지 않음


# product_option_crawling/collect_product_options.py

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

from common.db_manager2 import DBManager


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
OPTION_JSON_TIMEOUT = 20_000

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


# =========================================================
# 공통 함수
# =========================================================
def normalize_text(value: Any) -> str:
    """
    문자열의 앞뒤 공백과 연속된 공백을 정리합니다.

    예:
        " 하이퍼   콜라겐 8+1매 "
        -> "하이퍼 콜라겐 8+1매"
    """

    if value is None:
        return ""

    return " ".join(str(value).split()).strip()


def is_cloudflare_page(page: Page) -> bool:
    """
    현재 페이지가 Cloudflare 또는 로봇 인증 화면인지 확인합니다.
    """

    try:
        check_text = (
            f"{page.url}\n{page.content()}"
        ).lower()

        return any(
            keyword.lower() in check_text
            for keyword in CLOUDFLARE_KEYWORDS
        )

    except Exception:
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
    products 테이블의 모든 상품을 조회합니다.

    상품 크롤링이 먼저 실행되었다면 신규 상품도
    products 테이블에 들어 있으므로 자동으로 포함됩니다.
    """

    sql = """
        SELECT
            product_id,
            product_code
        FROM products
        WHERE product_code IS NOT NULL
          AND TRIM(product_code) <> ''
        ORDER BY product_id
    """

    db.execute(sql)

    return db.fetchall() or []


# =========================================================
# 옵션 count JSON 판별
# =========================================================
def is_option_count_json(payload: Any) -> bool:
    """
    아래 구조를 가진 옵션 count JSON인지 확인합니다.

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


# =========================================================
# 상품 상세페이지에서 옵션 JSON 수집
# =========================================================
def capture_option_json(
    page: Page,
    product_code: str,
) -> dict:
    """
    상품 상세페이지에 접속하고 네트워크 응답에서
    productItemReviewCountList가 들어 있는 JSON을 찾습니다.
    """

    captured: dict[str, Any] = {
        "payload": None,
        "response_url": None,
    }

    def handle_response(response: Response) -> None:
        """
        상세페이지에서 발생하는 네트워크 응답을 확인합니다.
        """

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
            # JSON이 아니거나 읽을 수 없는 응답은 무시
            return

    page.on(
        "response",
        handle_response,
    )

    detail_url = PRODUCT_DETAIL_URL.format(
        product_code=product_code,
    )

    try:
        page.goto(
            detail_url,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT,
        )

        # 페이지 진입 직후 인증 화면 확인
        raise_if_cloudflare(page)

        waited_ms = 0

        while waited_ms < OPTION_JSON_TIMEOUT:
            # 기다리는 도중 인증 화면이 생기는 경우도 확인
            raise_if_cloudflare(page)

            if captured["payload"] is not None:
                break

            page.wait_for_timeout(500)
            waited_ms += 500

        # 옵션 JSON 확인 직전 마지막 검사
        raise_if_cloudflare(page)

        if captured["payload"] is None:
            raise OptionJsonNotFoundError(
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
    data.productItemReviewCountList만 사용합니다.

    relatedProductReviewCountList는 사용하지 않습니다.

    goodsNumber가 현재 product_code와 같은 옵션만 사용합니다.

    optionName이 "판매종료"이면:
        is_active = 0

    그 외 옵션명이 있으면:
        is_active = 1
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

    # option_number를 기준으로 중복 제거
    collected_options: dict[str, dict] = {}

    for raw_option in raw_options:
        if not isinstance(raw_option, dict):
            continue

        goods_number = normalize_text(
            raw_option.get("goodsNumber")
        )

        # 현재 크롤링 중인 상품과 다른 상품은 제외
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

        # 옵션명이 정확히 "판매종료"이면 비활성
        is_active = (
            0
            if option_name == "판매종료"
            else 1
        )

        collected_options[option_number] = {
            "option_number": option_number,
            "option_name": option_name,
            "review_count": review_count,
            "is_active": is_active,
        }

    return list(
        collected_options.values()
    )


# =========================================================
# 전체 옵션 일괄 저장
# =========================================================
def save_all_product_options(
    db: DBManager,
    collected_products: list[dict],
) -> int:
    """
    모든 상품 옵션 수집에 성공한 후에만 실행됩니다.

    신규 옵션:
        신규 행 INSERT

    기존 옵션:
        option_name 갱신
        review_count 갱신
        last_seen_at 갱신
        is_active 갱신

    first_collected_at:
        기존 옵션에서는 최초 수집 시각 유지
    """

    sql = """
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

    saved_count = 0

    for product_result in collected_products:
        product_id = product_result["product_id"]
        options = product_result["options"]

        for option in options:
            db.execute(
                sql,
                (
                    product_id,
                    option["option_number"],
                    option["option_name"],
                    option["review_count"],
                    option["is_active"],
                ),
            )

            saved_count += 1

    return saved_count


# =========================================================
# 메인 실행
# =========================================================
def main() -> None:
    """
    실행 순서:

    1. products 전체 상품 조회
    2. 모든 상품의 옵션을 메모리에 수집
    3. 하나라도 실패하면 전체 실행 중단
    4. 모든 상품 수집 성공 후 DB 저장 시작
    5. 신규 옵션 INSERT
    6. 기존 옵션 UPDATE
    7. 전체 DB 작업 성공 후 한 번만 COMMIT
    """

    db = DBManager()

    # 크롤링 도중에는 DB에 저장하지 않고 메모리에 보관
    collected_products: list[dict] = []

    try:
        products = get_target_products(db)

        if not products:
            print("옵션을 수집할 상품이 없습니다.")
            return

        print("=" * 70)
        print(
            f"전체 옵션 수집 대상: {len(products)}개 상품"
        )
        print(
            f"브라우저 프로필 경로: {PROFILE_DIR}"
        )
        print(
            "DB 저장 방식: 전체 크롤링 성공 후 일괄 저장"
        )
        print("=" * 70)

        PROFILE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        with sync_playwright() as playwright:
            # 브라우저 프로필을 저장해 쿠키와 세션을 재사용
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
                    print(
                        f"product_id: {product_id}"
                    )

                    payload = capture_option_json(
                        page=page,
                        product_code=product_code,
                    )

                    options = extract_current_product_options(
                        payload=payload,
                        product_code=product_code,
                    )

                    # 아직 DB에는 저장하지 않고 메모리에 누적
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
                            if option["is_active"] == 0
                            else "판매중"
                        )

                        print(
                            "      - "
                            f"{option['option_number']} / "
                            f"{option['option_name']} / "
                            f"리뷰 {option['review_count']}개 / "
                            f"{status_text}"
                        )

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

        # 이 지점까지 왔으면 전체 상품 옵션 수집 성공
        print()
        print("=" * 70)
        print("전체 상품 옵션 수집 성공")
        print("DB 일괄 저장을 시작합니다.")
        print("=" * 70)

        saved_count = save_all_product_options(
            db=db,
            collected_products=collected_products,
        )

        # 모든 INSERT/UPDATE가 성공한 뒤 한 번만 커밋
        db.commit()

        print()
        print("=" * 70)
        print("상품 옵션 크롤링 완료")
        print(
            f"처리 상품 수: "
            f"{len(collected_products)}개"
        )
        print(
            f"저장·갱신 옵션 수: {saved_count}개"
        )
        print("전체 COMMIT 완료")
        print("=" * 70)

    except CloudflareChallengeError as error:
        db.rollback()

        print()
        print("=" * 70)
        print("Cloudflare/로봇 인증 화면 감지")
        print(f"오류 내용: {error}")
        print("전체 실행을 즉시 중단했습니다.")
        print("product_options 테이블은 변경되지 않았습니다.")
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
        print("전체 실행을 중단했습니다.")
        print("product_options 테이블은 변경되지 않았습니다.")
        print("=" * 70)

    except Exception as error:
        db.rollback()

        print()
        print("=" * 70)
        print("예상하지 못한 오류가 발생했습니다.")
        print(f"오류 유형: {type(error).__name__}")
        print(f"오류 내용: {error}")
        print("전체 작업을 ROLLBACK했습니다.")
        print("=" * 70)

        raise

    finally:
        if hasattr(db, "close"):
            db.close()


if __name__ == "__main__":
    main()