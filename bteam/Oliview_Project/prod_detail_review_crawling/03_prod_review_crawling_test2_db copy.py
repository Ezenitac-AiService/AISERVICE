# 리뷰 미수집 또는 오늘 미확인 활성 상품 최대 3개 조회
# 상품별 4개 정렬 기준(최신순/도움순/평점높은순/평점낮은순) 리뷰 수집 후 review_id 중복 제거
# DB에 없는 신규 리뷰만 저장
# 상품별 리뷰 저장과 review_checked_at 갱신을 하나의 트랜잭션으로 처리
# 성공 시 COMMIT, 실패 시 해당 상품만 ROLLBACK
# 같은 날 수집 완료된 상품은 재실행 대상에서 제외


import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


# ============================================================
# 프로젝트 경로 설정
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from common.db_manager3 import DBManager


# ============================================================
# 기본 설정
# ============================================================

# 테스트할 상품 수
PRODUCT_LIMIT = 3

API_URL = "https://m.oliveyoung.co.kr/review/api/v2/reviews/cursor"

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

# API 한 번 호출 시 가져올 리뷰 수
PAGE_SIZE = 10

# 비로그인 상태에서 정렬별 최대 수집 개수
MAX_REVIEWS_PER_SORT = 100

# 요청 사이 대기 시간
REQUEST_DELAY = 1.0
SORT_DELAY = 2.0
PRODUCT_DELAY = 3.0

SORT_TYPES = {
    "최신순": "DATETIME_DESC",
    "도움순": "RECOMMENDED_DESC",
    "평점높은순": "RATING_DESC",
    "평점낮은순": "RATING_ASC",
}


# ============================================================
# 공통 함수
# ============================================================

def normalize_text(value: Any) -> str:
    """
    None을 빈 문자열로 바꾸고
    연속된 공백과 줄바꿈을 정리합니다.
    """

    if value is None:
        return ""

    return " ".join(str(value).split()).strip()


def parse_review_date(value: Any) -> str | None:
    """
    API의 리뷰 작성일을 MySQL DATE 형식인
    YYYY-MM-DD 문자열로 변환합니다.
    """

    if value is None or value == "":
        return None

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
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )

        return parsed.strftime("%Y-%m-%d")

    except ValueError:
        print(f"리뷰 작성일 형식을 해석하지 못했습니다: {text}")
        return None


# ============================================================
# DB 조회 함수
# ============================================================

def get_target_products(
    db: DBManager,
    limit: int = PRODUCT_LIMIT,
) -> list[dict[str, Any]]:
    """
    review_checked_at이 NULL이거나 오늘 이전인 활성 상품을
    product_id 순서로 최대 3개 조회합니다.
    """

    sql = """
        SELECT
            product_id,
            product_code,
            product_name,
            review_checked_at
        FROM products
        WHERE is_active = 1
          AND (
              review_checked_at IS NULL
              OR review_checked_at < CURDATE()
          )
          AND product_code IS NOT NULL
          AND TRIM(product_code) <> ''
        ORDER BY product_id
        LIMIT %s
    """

    db.execute(sql, (limit,))
    return db.fetchall()


def get_option_id_map(
    db: DBManager,
    product_id: int,
) -> dict[str, int]:
    """
    해당 상품의 옵션 정보를 조회하여

    option_number -> product_option_id

    형태의 딕셔너리로 반환합니다.
    """

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
        str(row["option_number"]).strip():
            int(row["product_option_id"])
        for row in rows
        if row.get("option_number") is not None
    }


def get_existing_review_ids(
    db: DBManager,
    product_id: int,
) -> set[int]:
    """
    해당 상품에 이미 저장된 review_id를 조회하여 set으로 반환합니다.
    """

    sql = """
        SELECT review_id
        FROM reviews
        WHERE product_id = %s
    """

    db.execute(sql, (product_id,))
    rows = db.fetchall()

    return {
        int(row["review_id"])
        for row in rows
        if row.get("review_id") is not None
    }


# ============================================================
# 리뷰 API 호출
# ============================================================

def request_review_page(
    session: requests.Session,
    goods_number: str,
    sort_type: str,
    cursor_id: int | None = None,
    cursor_score: float | None = None,
    cursor_count: int | None = None,
) -> dict[str, Any]:
    """
    올리브영 리뷰 API를 한 번 호출합니다.
    """

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

    response = session.post(
        API_URL,
        json=payload,
        timeout=30,
    )

    if response.status_code != 200:
        print(f"상태 코드: {response.status_code}")
        print(f"요청 Payload: {payload}")
        print(f"서버 응답: {response.text[:1000]}")

    response.raise_for_status()

    result = response.json()

    if result.get("status") != "SUCCESS":
        raise RuntimeError(
            f"API 실패: "
            f"{result.get('code')} / "
            f"{result.get('message')}"
        )

    return result


def crawl_one_sort(
    session: requests.Session,
    goods_number: str,
    sort_name: str,
    sort_type: str,
) -> dict[int, dict[str, Any]]:
    """
    정렬 기준 하나에 대해 최대 100개의 리뷰를 수집합니다.

    같은 정렬 안에서는 review_id로 중복을 제거합니다.
    """

    cursor_id = None
    cursor_score = None
    cursor_count = None

    reviews_by_id: dict[int, dict[str, Any]] = {}
    seen_cursors: set[tuple[Any, Any, Any]] = set()

    request_count = 0

    while len(reviews_by_id) < MAX_REVIEWS_PER_SORT:
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
                print(
                    f"[{sort_name}] "
                    f"잘못된 reviewId 발견: {review_id}"
                )
                continue

            # 관련 상품 리뷰가 섞여 있을 수 있으므로
            # 현재 상품 번호와 같은 리뷰만 사용합니다.
            review_goods_number = (
                (review.get("goodsDto") or {})
                .get("goodsNumber")
            )

            if str(review_goods_number) != str(goods_number):
                continue

            if review_id not in reviews_by_id:
                reviews_by_id[review_id] = review
                new_count += 1

            # 정렬별 최대 100개까지만 저장
            if len(reviews_by_id) >= MAX_REVIEWS_PER_SORT:
                break

        print(
            f"[{sort_name}] "
            f"요청 {request_count}회 | "
            f"응답 {len(reviews)}개 | "
            f"현재 상품 신규 {new_count}개 | "
            f"정렬 내 고유 리뷰 {len(reviews_by_id)}개"
        )

        if len(reviews_by_id) >= MAX_REVIEWS_PER_SORT:
            print(
                f"[{sort_name}] "
                f"최대 {MAX_REVIEWS_PER_SORT}개 수집 완료"
            )
            break

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
            print(
                f"[{sort_name}] "
                "리뷰 목록이 비어 있어 종료합니다."
            )
            break

        next_cursor = (
            data.get("nextCursorId"),
            data.get("nextCursorScore"),
            data.get("nextCursorCount"),
        )

        if next_cursor in seen_cursors:
            print(
                f"[{sort_name}] "
                f"동일 커서가 반복되어 종료합니다: {next_cursor}"
            )
            break

        seen_cursors.add(next_cursor)

        cursor_id, cursor_score, cursor_count = next_cursor

        if cursor_id is None:
            print(
                f"[{sort_name}] "
                "nextCursorId가 없어 종료합니다."
            )
            break

        time.sleep(REQUEST_DELAY)

    return reviews_by_id


def crawl_product_reviews(
    session: requests.Session,
    goods_number: str,
) -> dict[int, dict[str, Any]]:
    """
    상품 하나에 대해 4개 정렬 기준의 리뷰를 수집합니다.

    4개 정렬에서 같은 리뷰가 반복되어도
    review_id 기준으로 최종 중복 제거합니다.
    """

    all_reviews_by_id: dict[int, dict[str, Any]] = {}

    for sort_name, sort_type in SORT_TYPES.items():
        print()
        print("-" * 70)
        print(f"{sort_name} 수집 시작: {sort_type}")
        print("-" * 70)

        sort_reviews = crawl_one_sort(
            session=session,
            goods_number=goods_number,
            sort_name=sort_name,
            sort_type=sort_type,
        )

        before_count = len(all_reviews_by_id)

        for review_id, review in sort_reviews.items():
            all_reviews_by_id.setdefault(
                review_id,
                review,
            )

        added_count = (
            len(all_reviews_by_id) - before_count
        )

        print(
            f"[{sort_name}] 전체 결과에 새로 추가 "
            f"{added_count}개 | "
            f"상품 누적 고유 리뷰 "
            f"{len(all_reviews_by_id)}개"
        )

        time.sleep(SORT_DELAY)

    return all_reviews_by_id


# ============================================================
# 리뷰 데이터 변환
# ============================================================

def transform_review(
    review: dict[str, Any],
    product_id: int,
    option_id_map: dict[str, int],
    collected_at: datetime,
) -> tuple[Any, ...] | None:
    """
    API 리뷰 데이터를 reviews 테이블 INSERT용 튜플로 변환합니다.
    """

    try:
        review_id = int(review.get("reviewId"))
        review_score = int(review.get("reviewScore"))

    except (TypeError, ValueError):
        print(
            "review_id 또는 review_score가 "
            "올바르지 않아 제외합니다."
        )
        return None

    review_content = normalize_text(
        review.get("content")
    )

    if not review_content:
        print(
            f"review_id={review_id}: "
            "리뷰 내용이 없어 제외합니다."
        )
        return None

    goods_dto = review.get("goodsDto") or {}

    # API의 itemNumber가
    # product_options.option_number에 대응합니다.
    option_number = goods_dto.get("itemNumber")

    product_option_id = None

    if option_number is not None:
        product_option_id = option_id_map.get(
            str(option_number).strip()
        )

    review_date = parse_review_date(
        review.get("createdDateTime")
    )

    return (
        review_id,
        product_id,
        product_option_id,
        review_content,
        review_score,
        review_date,
        collected_at,
    )


# ============================================================
# DB 저장 함수
# ============================================================

def insert_reviews(
    db: DBManager,
    review_rows: list[tuple[Any, ...]],
) -> tuple[int, int]:
    """
    리뷰를 reviews 테이블에 저장합니다.

    사전에 DB 기존 review_id를 제외한 행만 전달받습니다.
    INSERT IGNORE는 동시 실행 등 예외 상황을 위한 마지막 안전장치입니다.

    반환값:
        시도한 리뷰 수, 실제 신규 저장 수
    """

    if not review_rows:
        return 0, 0

    sql = """
        INSERT IGNORE INTO reviews (
            review_id,
            product_id,
            product_option_id,
            review_content,
            review_score,
            review_date,
            collected_at
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
    """

    inserted_count = 0

    for row in review_rows:
        db.execute(sql, row)

        # INSERT IGNORE에서 신규 INSERT가 이루어진 경우
        # rowcount가 일반적으로 1입니다.
        rowcount = getattr(db.cursor, "rowcount", 0)

        if rowcount == 1:
            inserted_count += 1

    return len(review_rows), inserted_count


def update_review_checked_at(
    db: DBManager,
    product_id: int,
) -> None:
    """
    해당 상품의 리뷰 확인 완료 시각을 갱신합니다.
    """

    sql = """
        UPDATE products
        SET review_checked_at = NOW()
        WHERE product_id = %s
    """

    db.execute(sql, (product_id,))


def commit_transaction(db: DBManager) -> None:
    """
    현재 DB 트랜잭션을 커밋합니다.
    """

    if db.connection is None:
        raise RuntimeError(
            "DB 연결이 없어 commit할 수 없습니다."
        )

    db.connection.commit()


def rollback_transaction(db: DBManager) -> None:
    """
    현재 DB 트랜잭션을 롤백합니다.
    """

    if db.connection is not None:
        db.connection.rollback()


# ============================================================
# 메인 실행
# ============================================================

def main() -> None:
    db = DBManager()
    session = requests.Session()
    session.headers.update(HEADERS)

    total_collected_count = 0
    total_inserted_count = 0
    success_product_count = 0
    failed_product_count = 0

    try:
        db.connect()

        products = get_target_products(
            db=db,
            limit=PRODUCT_LIMIT,
        )

        if not products:
            print(
                "review_checked_at이 NULL이거나 오늘 이전인 "
                "활성 상품을 찾지 못했습니다."
            )
            return

        print()
        print("=" * 70)
        print("리뷰 DB 저장 테스트 시작")
        print(f"대상 상품 수: {len(products)}개")
        print("=" * 70)

        for index, product in enumerate(
            products,
            start=1,
        ):
            product_id = int(product["product_id"])
            goods_number = str(product["product_code"])
            product_name = (
                product.get("product_name") or ""
            )

            print()
            print("=" * 70)
            print(
                f"상품 {index}/{len(products)} 수집 시작"
            )
            print(f"product_id   : {product_id}")
            print(f"product_code : {goods_number}")
            print(f"product_name : {product_name}")
            print("=" * 70)

            try:
                # ------------------------------------------------
                # 1. 상품 옵션 매핑 조회
                # ------------------------------------------------

                option_id_map = get_option_id_map(
                    db=db,
                    product_id=product_id,
                )

                print(
                    f"등록된 상품 옵션 수: "
                    f"{len(option_id_map)}개"
                )

                # ------------------------------------------------
                # 2. DB 기존 review_id 조회
                # ------------------------------------------------

                existing_review_ids = get_existing_review_ids(
                    db=db,
                    product_id=product_id,
                )

                print(
                    f"DB 기존 리뷰 수: "
                    f"{len(existing_review_ids)}개"
                )

                # ------------------------------------------------
                # 3. 리뷰 API 수집
                # ------------------------------------------------

                raw_reviews = crawl_product_reviews(
                    session=session,
                    goods_number=goods_number,
                )

                collected_at = datetime.now()

                review_rows: list[tuple[Any, ...]] = []
                option_unmatched_count = 0

                # ------------------------------------------------
                # 4. DB에 없는 리뷰만 저장 형태로 변환
                # ------------------------------------------------

                skipped_existing_count = 0

                for review_id, raw_review in raw_reviews.items():
                    if review_id in existing_review_ids:
                        skipped_existing_count += 1
                        continue

                    transformed = transform_review(
                        review=raw_review,
                        product_id=product_id,
                        option_id_map=option_id_map,
                        collected_at=collected_at,
                    )

                    if transformed is None:
                        continue

                    review_rows.append(transformed)

                    # 튜플 세 번째 값이 product_option_id
                    if transformed[2] is None:
                        option_unmatched_count += 1

                # ------------------------------------------------
                # 5. reviews 테이블 INSERT
                # ------------------------------------------------

                attempted_count, inserted_count = (
                    insert_reviews(
                        db=db,
                        review_rows=review_rows,
                    )
                )

                # ------------------------------------------------
                # 6. 상품 리뷰 확인 시각 갱신
                # ------------------------------------------------

                update_review_checked_at(
                    db=db,
                    product_id=product_id,
                )

                # ------------------------------------------------
                # 7. 상품 단위 커밋
                # ------------------------------------------------

                commit_transaction(db)

                success_product_count += 1
                total_collected_count += attempted_count
                total_inserted_count += inserted_count

                duplicate_count = (
                    skipped_existing_count
                    + attempted_count
                    - inserted_count
                )

                print()
                print("-" * 70)
                print("상품 DB 저장 완료")
                print(
                    f"수집한 고유 리뷰: "
                    f"{len(raw_reviews)}개"
                )
                print(
                    f"저장 시도 리뷰: "
                    f"{attempted_count}개"
                )
                print(
                    f"신규 저장 리뷰: "
                    f"{inserted_count}개"
                )
                print(
                    f"기존 중복 리뷰: "
                    f"{duplicate_count}개"
                )
                print(
                    f"옵션 미연결(NULL): "
                    f"{option_unmatched_count}개"
                )
                print(
                    "products.review_checked_at 갱신 완료"
                )
                print("-" * 70)

            except requests.RequestException as error:
                rollback_transaction(db)
                failed_product_count += 1

                print()
                print(
                    f"상품 {goods_number} "
                    f"네트워크 오류: {error}"
                )
                print(
                    "해당 상품의 리뷰 저장과 "
                    "review_checked_at 갱신을 롤백했습니다."
                )

            except Exception as error:
                rollback_transaction(db)
                failed_product_count += 1

                print()
                print(
                    f"상품 {goods_number} "
                    f"처리 실패: {error}"
                )
                print(
                    "해당 상품의 리뷰 저장과 "
                    "review_checked_at 갱신을 롤백했습니다."
                )

            if index < len(products):
                print(
                    f"다음 상품 처리 전 "
                    f"{PRODUCT_DELAY}초 대기합니다."
                )
                time.sleep(PRODUCT_DELAY)

        print()
        print("=" * 70)
        print("리뷰 DB 저장 테스트 종료")
        print(f"조회 대상 상품: {len(products)}개")
        print(f"성공 상품: {success_product_count}개")
        print(f"실패 상품: {failed_product_count}개")
        print(
            f"전체 저장 시도 리뷰: "
            f"{total_collected_count}개"
        )
        print(
            f"전체 신규 저장 리뷰: "
            f"{total_inserted_count}개"
        )
        print("=" * 70)

    except Exception as error:
        rollback_transaction(db)

        print()
        print(f"전체 작업 실패: {error}")

    finally:
        session.close()

        if hasattr(db, "close"):
            db.close()

        print("DB 연결과 HTTP 세션을 종료했습니다.")


if __name__ == "__main__":
    main()