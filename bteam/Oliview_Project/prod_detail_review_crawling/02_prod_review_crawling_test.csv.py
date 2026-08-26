# products 테이블에서 활성 상품 3개 조회
# 상품 상세페이지에는 접속하지 않고 product_code로 리뷰 API(JSON)를 직접 호출
# 최초 테스트 수집: 최신순/도움순/평점높은순/평점낮은순 각각 최대 100개
# review_id 기준으로 중복 제거 후 reviews 테이블과 같은 컬럼 구조의 CSV로 저장

import csv
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.db_manager3 import DBManager


PRODUCT_LIMIT = 3

API_URL = "https://m.oliveyoung.co.kr/review/api/v2/reviews/cursor"

OUTPUT_DIR = PROJECT_ROOT / "test_output"
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "review_test_3_products.csv"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/json",
    "Origin": "https://www.oliveyoung.co.kr",
    "Referer": "https://www.oliveyoung.co.kr/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
}

PAGE_SIZE = 10
REQUEST_DELAY = 1.0
SORT_DELAY = 2.0
PRODUCT_DELAY = 3.0

SORT_TYPES = {
    "최신순": "DATETIME_DESC",
    "도움순": "RECOMMENDED_DESC",
    "평점높은순": "RATING_DESC",
    "평점낮은순": "RATING_ASC",
}

CSV_COLUMNS = [
    "review_id",
    "product_id",
    "product_option_id",
    "review_content",
    "review_score",
    "review_date",
    "collected_at",
]


def normalize_text(value: Any) -> str:
    """None과 불필요한 공백을 정리합니다."""
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def parse_review_date(value: Any) -> str:
    """API 날짜를 CSV용 YYYY-MM-DD 문자열로 변환합니다."""
    if value is None or value == "":
        return ""

    text = str(value).strip()

    date_formats = (
        "%Y.%m.%d",
        "%Y-%m-%d",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    )

    for date_format in date_formats:
        try:
            parsed = datetime.strptime(text, date_format)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        print(f"리뷰 작성일 형식을 해석하지 못했습니다: {text}")
        return ""


def get_target_products(db: DBManager, limit: int = PRODUCT_LIMIT) -> list[dict[str, Any]]:
    """products 테이블에서 활성 상품을 product_id 순으로 최대 3개 조회합니다."""
    sql = """
        SELECT
            product_id,
            product_code,
            product_name
        FROM products
        WHERE is_active = 1
          AND product_code IS NOT NULL
          AND TRIM(product_code) <> ''
        ORDER BY product_id
        LIMIT %s
    """

    db.execute(sql, (limit,))
    return db.fetchall()


def get_option_id_map(db: DBManager, product_id: int) -> dict[str, int]:
    """product_options의 option_number -> product_option_id 매핑을 조회합니다."""
    sql = """
        SELECT
            product_option_id,
            option_number
        FROM product_options
        WHERE product_id = %s
    """

    db.execute(sql, (product_id,))
    rows = db.fetchall()

    return {
        str(row["option_number"]).strip(): int(row["product_option_id"])
        for row in rows
        if row.get("option_number") is not None
    }


def request_review_page(
    session: requests.Session,
    goods_number: str,
    sort_type: str,
    cursor_id: int | None = None,
    cursor_score: float | None = None,
    cursor_count: int | None = None,
) -> dict[str, Any]:
    """리뷰 API를 한 번 호출합니다."""
    if cursor_id is None:
        payload = {
            "goodsNumber": goods_number,
            "page": 0,
            "size": PAGE_SIZE,
            "sortType": sort_type,
            "reviewType": "ALL",
        }
    else:
        payload = {
            "goodsNumber": goods_number,
            "size": PAGE_SIZE,
            "sortType": sort_type,
            "reviewType": "ALL",
            "cursorId": cursor_id,
            "cursorScore": cursor_score,
            "cursorCount": cursor_count,
        }

    response = session.post(API_URL, json=payload, timeout=30)

    if response.status_code != 200:
        print("상태 코드:", response.status_code)
        print("요청 Payload:", payload)
        print("서버 응답:", response.text[:1000])

    response.raise_for_status()
    result = response.json()

    if result.get("status") != "SUCCESS":
        raise RuntimeError(
            f"API 실패: {result.get('code')} / {result.get('message')}"
        )

    return result


def crawl_one_sort(
    session: requests.Session,
    goods_number: str,
    sort_name: str,
    sort_type: str,
) -> dict[int, dict[str, Any]]:
    """정렬 기준 하나를 비로그인 제한 또는 마지막 페이지까지 수집합니다."""
    cursor_id = None
    cursor_score = None
    cursor_count = None

    reviews_by_id: dict[int, dict[str, Any]] = {}
    seen_cursors: set[tuple[Any, Any, Any]] = set()
    request_count = 0

    while True:
        result = request_review_page(
            session=session,
            goods_number=goods_number,
            sort_type=sort_type,
            cursor_id=cursor_id,
            cursor_score=cursor_score,
            cursor_count=cursor_count,
        )

        request_count += 1
        data = result.get("data") or {}
        reviews = data.get("goodsReviewList") or []
        login_required = data.get("loginRequired", False)
        has_next = data.get("hasNext", False)
        new_count = 0

        for review in reviews:
            review_id = review.get("reviewId")

            try:
                review_id = int(review_id)
            except (TypeError, ValueError):
                print(f"[{sort_name}] 잘못된 reviewId 발견: {review_id}")
                continue

            # 관련 상품 리뷰가 섞일 경우 현재 상품 리뷰만 저장합니다.
            review_goods_number = (
                (review.get("goodsDto") or {}).get("goodsNumber")
            )
            if review_goods_number != goods_number:
                continue

            if review_id not in reviews_by_id:
                reviews_by_id[review_id] = review
                new_count += 1

        print(
            f"[{sort_name}] 요청 {request_count}회 | "
            f"응답 {len(reviews)}개 | "
            f"현재 상품 신규 {new_count}개 | "
            f"정렬 내 고유 리뷰 {len(reviews_by_id)}개"
        )

        if login_required:
            print(
                f"[{sort_name}] 비로그인 제한 도달 | "
                f"현재까지 {len(reviews_by_id)}개 수집"
            )
            break

        if not has_next:
            print(f"[{sort_name}] 마지막 페이지 도달")
            break

        if not reviews:
            print(f"[{sort_name}] 리뷰 목록이 비어 있어 종료합니다.")
            break

        next_cursor = (
            data.get("nextCursorId"),
            data.get("nextCursorScore"),
            data.get("nextCursorCount"),
        )

        if next_cursor in seen_cursors:
            print(f"[{sort_name}] 동일 커서 반복으로 종료: {next_cursor}")
            break

        seen_cursors.add(next_cursor)
        cursor_id, cursor_score, cursor_count = next_cursor

        if cursor_id is None:
            print(f"[{sort_name}] nextCursorId가 없어 종료합니다.")
            break

        time.sleep(REQUEST_DELAY)

    return reviews_by_id


def crawl_product_reviews(
    session: requests.Session,
    goods_number: str,
) -> dict[int, dict[str, Any]]:
    """상품 하나에 대해 4개 정렬 리뷰를 수집하고 review_id로 합칩니다."""
    all_reviews_by_id: dict[int, dict[str, Any]] = {}

    for sort_name, sort_type in SORT_TYPES.items():
        print()
        print("-" * 70)
        print(f"{sort_name} 수집 시작: {sort_type}")
        print("-" * 70)

        try:
            sort_reviews = crawl_one_sort(
                session=session,
                goods_number=goods_number,
                sort_name=sort_name,
                sort_type=sort_type,
            )
        except requests.RequestException as error:
            print(f"[{sort_name}] 네트워크 오류: {error}")
            continue
        except Exception as error:
            print(f"[{sort_name}] 수집 오류: {error}")
            continue

        before_count = len(all_reviews_by_id)

        for review_id, review in sort_reviews.items():
            all_reviews_by_id.setdefault(review_id, review)

        print(
            f"[{sort_name}] 전체에 새로 추가 "
            f"{len(all_reviews_by_id) - before_count}개 | "
            f"상품 누적 {len(all_reviews_by_id)}개"
        )

        time.sleep(SORT_DELAY)

    return all_reviews_by_id


def transform_review(
    review: dict[str, Any],
    product_id: int,
    option_id_map: dict[str, int],
    collected_at: str,
) -> dict[str, Any] | None:
    """API 리뷰를 reviews 테이블과 동일한 CSV 컬럼으로 변환합니다."""
    try:
        review_id = int(review.get("reviewId"))
        review_score = int(review.get("reviewScore"))
    except (TypeError, ValueError):
        return None

    review_content = normalize_text(review.get("content"))
    if not review_content:
        print(f"review_id={review_id}: 리뷰 내용이 없어 제외합니다.")
        return None

    goods_dto = review.get("goodsDto") or {}

    # 리뷰 API의 itemNumber가 product_options.option_number와 대응합니다.
    # 옵션명(optionName)으로 문자열 매칭하지 않고 옵션번호로 정확히 연결합니다.
    option_number = goods_dto.get("itemNumber")

    product_option_id = None
    if option_number is not None:
        product_option_id = option_id_map.get(str(option_number).strip())

    return {
    "review_id": review_id,
    "product_id": product_id,
    "product_option_id": (
        product_option_id if product_option_id is not None else ""
    ),
    "review_content": review_content,
    "review_score": review_score,
    "review_date": parse_review_date(review.get("createdDateTime")),
    "collected_at": collected_at,
}


def save_csv(rows: list[dict[str, Any]], output_file: Path) -> None:
    """Excel에서도 한글이 깨지지 않도록 UTF-8 BOM CSV로 저장합니다."""
    with output_file.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    db = DBManager()
    all_csv_rows: list[dict[str, Any]] = []

    try:
        db.connect()
        products = get_target_products(db)

        if not products:
            print("products 테이블에서 수집 대상 상품을 찾지 못했습니다.")
            return

        print(f"DB에서 상품 {len(products)}개를 조회했습니다.")

        session = requests.Session()
        session.headers.update(HEADERS)

        for index, product in enumerate(products, start=1):
            product_id = int(product["product_id"])
            goods_number = str(product["product_code"])
            product_name = product.get("product_name") or ""

            print()
            print("=" * 70)
            print(f"상품 {index}/{len(products)} 수집 시작")
            print(f"product_id: {product_id}")
            print(f"product_code: {goods_number}")
            print(f"product_name: {product_name}")
            print("=" * 70)

            try:
                option_id_map = get_option_id_map(db, product_id)
                raw_reviews = crawl_product_reviews(session, goods_number)

                collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                product_rows: list[dict[str, Any]] = []

                for raw_review in raw_reviews.values():
                    transformed = transform_review(
                        review=raw_review,
                        product_id=product_id,
                        option_id_map=option_id_map,
                        collected_at=collected_at,
                    )
                    if transformed is not None:
                        product_rows.append(transformed)

                all_csv_rows.extend(product_rows)

                option_unmatched_count = sum(
                    1
                    for row in product_rows
                    if row["product_option_id"] == ""
                )

                print(f"상품 고유 리뷰 수: {len(raw_reviews)}")
                print(f"CSV 변환 완료: {len(product_rows)}")
                print(f"옵션 미연결(NULL): {option_unmatched_count}")

            except Exception as error:
                print(f"상품 {goods_number} 수집 실패: {error}")
                print("이 상품은 건너뛰고 다음 상품을 계속 처리합니다.")

            if index < len(products):
                time.sleep(PRODUCT_DELAY)

        # 서로 다른 상품 정렬 결과에서도 같은 review_id가 중복될 가능성에 대비합니다.
        unique_rows_by_review_id: dict[int, dict[str, Any]] = {}
        for row in all_csv_rows:
            unique_rows_by_review_id.setdefault(int(row["review_id"]), row)

        final_rows = sorted(
            unique_rows_by_review_id.values(),
            key=lambda row: (int(row["product_id"]), -int(row["review_id"])),
        )

        save_csv(final_rows, OUTPUT_FILE)

        print()
        print("=" * 70)
        print("CSV 저장 완료")
        print(f"대상 상품 수: {len(products)}")
        print(f"최종 고유 리뷰 수: {len(final_rows)}")
        print(f"저장 경로: {OUTPUT_FILE}")
        print("DB의 reviews 테이블에는 저장하지 않았습니다.")
        print("=" * 70)

    finally:
        if hasattr(db, "close"):
            db.close()


if __name__ == "__main__":
    main()