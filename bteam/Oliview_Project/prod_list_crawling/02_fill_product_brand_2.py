# 브라우저 프로필을 저장해서 쿠키·세션 재사용
# Cloudflare/로봇 인증 화면 감지
# 인증 화면이 뜨면 즉시 전체 실행 중단
# 전체 크롤링 완료 전이면 DB 저장하지 않음

import random
import sys
import time

from datetime import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.db_manager import DBManager


# ============================================================
# 기본 설정
# ============================================================

PRODUCT_DETAIL_URL = (
    "https://www.oliveyoung.co.kr/store/goods/"
    "getGoodsDetail.do?goodsNo={product_code}"
)

MAX_PRODUCTS_PER_RUN = 50
MAX_RETRIES = 2

PAGE_TIMEOUT = 30_000
PRODUCT_DETAIL_TIMEOUT = 20_000

# 브라우저 쿠키·세션 등을 저장할 폴더
BROWSER_PROFILE_DIR = PROJECT_ROOT / "browser_profile" / "product_brand"

CLOUDFLARE_KEYWORDS = [
    "잠시만 기다려 주세요",
    "접속 정보를 확인 중이에요",
    "Cloudflare 보안 챌린지",
    "challenges.cloudflare.com",
    "cf-turnstile-response",
    "__cf_chl_",
    "로봇이 아닙니다",
    "사람인지 확인",
]


class CloudflareChallengeError(RuntimeError):
    """Cloudflare 또는 로봇 인증 화면이 나타났을 때 발생하는 예외"""

    pass


def normalize_text(value: Any) -> str:
    """
    None은 빈 문자열로 변환하고,
    문자열 내부의 불필요한 공백을 정리합니다.
    """

    if value is None:
        return ""

    return " ".join(str(value).split()).strip()


# ============================================================
# DB 조회 함수
# ============================================================

def get_unmapped_products(
    connection,
    limit: int,
    after_product_id: int = 0,
) -> list[dict]:
    """
    brand_id가 아직 매핑되지 않은 활성 상품을
    product_id 순서대로 최대 limit개 조회합니다.

    after_product_id보다 큰 상품만 조회하므로,
    이번 실행에서 실패한 상품이 있어도 같은 상품을
    무한 반복하지 않고 다음 50개 묶음으로 넘어갑니다.
    """

    sql = """
        SELECT
            product_id,
            product_code,
            product_name
        FROM products
        WHERE brand_id IS NULL
          AND is_active = 1
          AND product_id > %s
        ORDER BY product_id
        LIMIT %s
    """

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(sql, (after_product_id, limit))
        return cursor.fetchall()

    finally:
        cursor.close()


def count_unmapped_products(connection) -> int:
    """
    brand_id가 NULL인 활성 상품 수를 조회합니다.
    """

    sql = """
        SELECT COUNT(*) AS cnt
        FROM products
        WHERE brand_id IS NULL
          AND is_active = 1
    """

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(sql)
        row = cursor.fetchone()

        return int(row["cnt"])

    finally:
        cursor.close()


def get_brand_mapping(connection) -> dict[str, int]:
    """
    brands 테이블의 브랜드 코드를 기준으로
    {브랜드 코드: brand_id} 형태의 딕셔너리를 만듭니다.
    """

    sql = """
        SELECT
            brand_id,
            brand_code
        FROM brands
        WHERE is_active = 1
          AND brand_code IS NOT NULL
          AND TRIM(brand_code) <> ''
    """

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(sql)
        rows = cursor.fetchall()

    finally:
        cursor.close()

    mapping = {}

    for row in rows:
        brand_code = normalize_text(row["brand_code"])

        if brand_code:
            mapping[brand_code] = int(row["brand_id"])

    return mapping


# ============================================================
# Cloudflare 감지
# ============================================================

def is_cloudflare_challenge(page: Page) -> bool:
    """
    현재 페이지가 Cloudflare 또는 로봇 인증 페이지인지 확인합니다.
    """

    try:
        current_url = page.url.lower()
    except Exception:
        current_url = ""

    try:
        html = page.content()
    except Exception:
        html = ""

    try:
        body_text = normalize_text(
            page.locator("body").inner_text(timeout=3_000)
        )
    except Exception:
        body_text = ""

    combined_text = f"{current_url}\n{html}\n{body_text}".lower()

    return any(
        keyword.lower() in combined_text
        for keyword in CLOUDFLARE_KEYWORDS
    )


# ============================================================
# 상품 상세페이지 브랜드 코드 추출
# ============================================================

def extract_brand_code(page: Page, product_code: str) -> str:
    """
    상품 상세페이지의 meta 태그에서 브랜드 코드를 추출합니다.

    Cloudflare 인증 화면이 나타나면 즉시
    CloudflareChallengeError를 발생시킵니다.
    """

    url = PRODUCT_DETAIL_URL.format(product_code=product_code)

    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(random.uniform(2.5, 5.0))

        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT,
            )

            # 페이지 이동 직후 인증 화면 검사
            if is_cloudflare_challenge(page):
                raise CloudflareChallengeError(
                    f"Cloudflare 인증 화면 감지: {product_code}"
                )

            page.wait_for_selector(
                'meta[property="eg:brandId"]',
                state="attached",
                timeout=PRODUCT_DETAIL_TIMEOUT,
            )

            # meta 태그 대기 이후 다시 인증 화면 검사
            if is_cloudflare_challenge(page):
                raise CloudflareChallengeError(
                    f"Cloudflare 인증 화면 감지: {product_code}"
                )

            soup = BeautifulSoup(page.content(), "html.parser")

            meta = soup.select_one(
                'meta[property="eg:brandId"]'
            )

            brand_code = (
                normalize_text(meta.get("content"))
                if meta
                else ""
            )

            if brand_code:
                return brand_code

            print(
                f"    ⚠️ 브랜드 코드가 없습니다: "
                f"{product_code}"
            )

        except CloudflareChallengeError:
            # Cloudflare는 재시도하지 않고 즉시 상위 함수로 전달
            raise

        except PlaywrightTimeoutError:
            # 타임아웃 이후 페이지가 인증 화면인지 다시 검사
            if is_cloudflare_challenge(page):
                raise CloudflareChallengeError(
                    f"Cloudflare 인증 화면 감지: {product_code}"
                )

            print(
                f"    ⚠️ 로딩 실패 "
                f"{attempt}/{MAX_RETRIES}: {product_code}"
            )

        except Exception as error:
            # 일반 오류처럼 보이더라도 인증 화면인지 다시 검사
            if is_cloudflare_challenge(page):
                raise CloudflareChallengeError(
                    f"Cloudflare 인증 화면 감지: {product_code}"
                )

            print(
                f"    ⚠️ 상세페이지 오류 "
                f"{attempt}/{MAX_RETRIES}: "
                f"{product_code} / {error}"
            )

        if attempt < MAX_RETRIES:
            wait_seconds = random.uniform(8.0, 15.0)

            print(
                f"    ⏳ {wait_seconds:.1f}초 후 재시도"
            )

            time.sleep(wait_seconds)

    return ""


# ============================================================
# DB 일괄 저장
# ============================================================
def save_product_brand_mappings(
    connection,
    mappings: list[tuple[int, int]],
) -> int:
    if not mappings:
        return 0

    sql = """
        UPDATE products
        SET brand_id = %s
        WHERE product_id = %s
          AND brand_id IS NULL
    """

    update_values = [
        (brand_id, product_id)
        for product_id, brand_id in mappings
    ]

    cursor = connection.cursor()

    try:
        cursor.executemany(
            sql,
            update_values,
        )

        updated_count = cursor.rowcount

        connection.commit()

        return updated_count

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()

# ============================================================
# 메인 실행
# ============================================================

def main():
    print("=" * 60)
    print(
        f"상품 브랜드 자동 매핑 시작: "
        f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    )
    print("=" * 60)

    db = DBManager()

    playwright = None
    context = None

    total_updated = 0
    total_failed: list[tuple[str, str, str]] = []
    completed_batches = 0
    cloudflare_detected = False

    try:
        # ----------------------------------------------------
        # 1. DB 연결 및 초기 상태 확인
        # ----------------------------------------------------
        db.connect()
        connection = db.connection

        if connection is None:
            raise RuntimeError("DB 연결 실패")

        initial_count = count_unmapped_products(connection)

        print(
            f"📌 현재 brand_id 미매핑 활성 상품: "
            f"{initial_count}개"
        )
        print(
            f"📦 처리 단위: 최대 "
            f"{MAX_PRODUCTS_PER_RUN}개씩 자동 반복"
        )

        if initial_count == 0:
            print("✅ 매핑할 상품이 없습니다.")
            return

        brand_mapping = get_brand_mapping(connection)

        print(
            f"📌 활성 브랜드 코드: "
            f"{len(brand_mapping)}개"
        )

        # ----------------------------------------------------
        # 2. 브라우저 실행
        # ----------------------------------------------------
        BROWSER_PROFILE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        print(
            f"📁 브라우저 프로필: "
            f"{BROWSER_PROFILE_DIR}"
        )

        playwright = sync_playwright().start()

        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=False,
            locale="ko-KR",
            viewport={
                "width": 1400,
                "height": 900,
            },
        )

        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()

        # 마지막으로 확인한 product_id입니다.
        # 실패 상품도 다음 묶음에서 반복 조회되지 않도록 사용합니다.
        last_product_id = 0
        batch_number = 0

        # ----------------------------------------------------
        # 3. 200개씩 자동 반복
        # ----------------------------------------------------
        while True:
            products = get_unmapped_products(
                connection,
                MAX_PRODUCTS_PER_RUN,
                after_product_id=last_product_id,
            )

            if not products:
                break

            batch_number += 1
            batch_start_id = int(products[0]["product_id"])
            batch_end_id = int(products[-1]["product_id"])

            print()
            print("=" * 60)
            print(
                f"📦 {batch_number}번째 묶음 시작: "
                f"{len(products)}개 "
                f"(product_id {batch_start_id}~{batch_end_id})"
            )
            print("=" * 60)

            pending_updates: list[tuple[int, int]] = []
            batch_failed: list[tuple[str, str, str]] = []
            batch_completed = True

            for index, product in enumerate(products, start=1):
                product_id = int(product["product_id"])
                product_code = str(product["product_code"])
                product_name = normalize_text(
                    product["product_name"]
                )

                # 실패 여부와 관계없이 이번 실행에서는
                # 이 product_id 다음 상품으로 진행합니다.
                last_product_id = product_id

                print(
                    f"\n[{index}/{len(products)}] "
                    f"{product_code} / {product_name}"
                )

                try:
                    brand_code = extract_brand_code(
                        page,
                        product_code,
                    )

                except CloudflareChallengeError:
                    cloudflare_detected = True
                    batch_completed = False

                    print()
                    print("🛑 Cloudflare/로봇 인증 화면이 감지되었습니다.")
                    print("🛑 자동 반복을 즉시 중단합니다.")
                    print(
                        "🛑 현재 처리 중인 묶음의 결과는 "
                        "DB에 저장하지 않습니다."
                    )
                    break

                if not brand_code:
                    failure = (
                        product_code,
                        "",
                        "brand_code 없음",
                    )
                    batch_failed.append(failure)
                    total_failed.append(failure)

                    print(
                        f"  ❌ {product_code} / "
                        f"브랜드 코드 없음"
                    )
                    continue

                brand_id = brand_mapping.get(brand_code)

                if brand_id is None:
                    failure = (
                        product_code,
                        brand_code,
                        "brands 테이블 미등록",
                    )
                    batch_failed.append(failure)
                    total_failed.append(failure)

                    print(
                        f"  ⚠️ {product_code} "
                        f"→ {brand_code} "
                        f"(brands 테이블 미등록)"
                    )
                    continue

                pending_updates.append(
                    (product_id, brand_id)
                )

                print(
                    f"  ✅ {product_code} "
                    f"→ {brand_code} "
                    f"→ brand_id={brand_id}"
                )

            # Cloudflare로 묶음이 중단되면 해당 묶음은 폐기합니다.
            if not batch_completed:
                discarded_count = len(pending_updates)
                pending_updates.clear()

                print()
                print("=" * 60)
                print("⛔ 현재 묶음 DB 저장 취소")
                print(
                    f"⛔ 폐기된 임시 매핑 결과: "
                    f"{discarded_count}개"
                )
                print(
                    "✅ 앞에서 저장을 완료한 묶음은 "
                    "DB에 그대로 유지됩니다."
                )
                print("=" * 60)
                break

            # 묶음을 끝까지 확인한 경우에만 묶음 단위 저장
            print()
            print(
                f"💾 {batch_number}번째 묶음 저장 예정: "
                f"{len(pending_updates)}개"
            )

            updated_count = save_product_brand_mappings(
                connection,
                pending_updates,
            )

            total_updated += updated_count
            completed_batches += 1

            remaining_count = count_unmapped_products(connection)

            print(
                f"✅ {batch_number}번째 묶음 DB 업데이트: "
                f"{updated_count}개"
            )
            print(
                f"⚠️ {batch_number}번째 묶음 일반 실패: "
                f"{len(batch_failed)}개"
            )
            print(
                f"📌 현재 DB의 미매핑 활성 상품: "
                f"{remaining_count}개"
            )

            # 서버에 연속 요청이 몰리지 않도록 묶음 사이 휴식
            if len(products) == MAX_PRODUCTS_PER_RUN:
                batch_wait = random.uniform(15.0, 30.0)
                print(
                    f"⏳ 다음 200개 처리 전 "
                    f"{batch_wait:.1f}초 대기"
                )
                time.sleep(batch_wait)

        # ----------------------------------------------------
        # 4. 전체 결과 출력
        # ----------------------------------------------------
        final_count = count_unmapped_products(connection)

        print()
        print("=" * 60)
        print("📊 자동 매핑 실행 결과")
        print(f"✅ 저장 완료 묶음: {completed_batches}개")
        print(f"✅ DB 업데이트 합계: {total_updated}개")
        print(f"⚠️ 일반 실패 합계: {len(total_failed)}개")
        print(f"📌 DB에 남은 미매핑 활성 상품: {final_count}개")
        print("=" * 60)

        if total_failed:
            print()
            print("📋 실패 상품 일부")

            for row in total_failed[:20]:
                print(
                    f"  - {row[0]} / "
                    f"{row[1] or '-'} / "
                    f"{row[2]}"
                )

            print()
            print(
                "ℹ️ 위 실패 상품은 이번 실행에서 무한 반복하지 않고 "
                "건너뛰었습니다. 원인을 보완한 뒤 프로그램을 다시 "
                "실행하면 다시 처리됩니다."
            )

        if cloudflare_detected:
            print()
            print(
                "💡 브라우저 프로필은 유지됩니다. "
                "인증을 완료한 뒤 프로그램을 다시 실행하면 "
                "중단된 상품부터 다시 처리됩니다."
            )
        elif final_count == 0:
            print()
            print(
                "🎉 모든 활성 상품의 "
                "브랜드 매핑이 완료되었습니다."
            )
        else:
            print()
            print(
                "⚠️ 남아 있는 상품은 브랜드 코드가 없거나 "
                "brands 테이블에 등록되지 않은 실패 상품입니다."
            )

    except Exception as error:
        print()
        print(f"❌ 작업 실패: {error}")
        print(
            "❌ 처리 중이던 묶음의 완료되지 않은 결과는 "
            "DB에 저장되지 않습니다."
        )
        print(
            "✅ 이전에 저장 완료된 200개 묶음은 "
            "DB에 유지됩니다."
        )

    finally:
        if context is not None:
            try:
                context.close()
            except Exception as error:
                print(
                    f"⚠️ 브라우저 종료 오류: {error}"
                )

        if playwright is not None:
            try:
                playwright.stop()
            except Exception as error:
                print(
                    f"⚠️ Playwright 종료 오류: {error}"
                )

        try:
            db.close()
        except Exception as error:
            print(
                f"⚠️ DB 종료 오류: {error}"
            )

    print("=" * 60)
    print(
        f"작업 종료: "
        f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()