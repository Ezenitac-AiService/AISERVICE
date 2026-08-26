# 429 오류 개선

# 상품 조회
#  → 최신순 수집
#  → 도움순 수집
#  → 평점 높은순 수집
#  → 평점 낮은순 수집
#  → review_id 중복 제거
#  → 신규 리뷰만 DB 저장
#  → 상품 단위 커밋

# 증분수집도 최신순·도움순·평점 높은순·평점 낮은순 4개 정렬을 전부 순회
# 최신순에서만 기존 review_id가 발견되면 다음 페이지로 더 내려가지 않고 종료
# 최신순 종료 후에는 pass처럼 도움순 수집으로 계속 진행
# 도움순·평점 높은순·평점 낮은순은 기존 리뷰가 나와도 최대 페이지까지 계속 수집
# 상품 30개 처리 후 긴 휴식도 유지

import random
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

# 상품별 자동 수집 모드
# - DB에 기존 리뷰가 있으면: 증분수집(최신순만 조회)
# - DB에 기존 리뷰가 없으면: 최초수집(4개 정렬 조회)
COLLECTION_MODE = "auto_incremental"

# 한 상품에서 허용할 최대 페이지 수
MAX_PAGES_INCREMENTAL = 5
MAX_PAGES_FULL = 10  # 4개 정렬 각각 최대 10페이지(정렬별 최대 100개)

# 최신순 증분수집에서 기존 리뷰가 나온 페이지가 이 횟수만큼 연속되면 종료
STOP_AFTER_EXISTING_PAGES = 1

# 요청 사이 대기 시간: 429 재발 방지를 위해 기존보다 충분히 늘림
# 일반 요청 사이 대기
REQUEST_DELAY_MIN = 2.0
REQUEST_DELAY_MAX = 4.0

# 리뷰 정렬 변경 후 대기
SORT_DELAY_MIN = 3.0
SORT_DELAY_MAX = 5.0

# 다음 상품 처리 전 대기
PRODUCT_DELAY_MIN = 5.0
PRODUCT_DELAY_MAX = 8.0

# 상품 30개 처리 후 긴 휴식
PRODUCT_BATCH_SIZE = 30
LONG_BREAK_MIN = 90.0    # 1분 30초
LONG_BREAK_MAX = 150.0   # 2분 30초

# 429는 같은 실행에서 재시도하지 않고 즉시 전체 중단합니다.
# 반복 재시도가 제한 시간을 연장할 수 있기 때문입니다.
STOP_IMMEDIATELY_ON_429 = True

# 연결 끊김·일시적 5xx만 제한적으로 재시도
MAX_TRANSIENT_RETRIES = 2
TRANSIENT_BASE_WAIT = 15.0
TRANSIENT_JITTER_MAX = 10.0

INCREMENTAL_SORT_TYPES = {
    "최신순": "DATETIME_DESC",
}

FULL_SORT_TYPES = {
    "최신순": "DATETIME_DESC",
    "도움순": "RECOMMENDED_DESC",
    "평점높은순": "RATING_DESC",
    "평점낮은순": "RATING_ASC",
}


# ============================================================
# 공통 함수
# ============================================================


class ReviewRateLimitError(RuntimeError):
    """리뷰 API 요청 제한이 반복될 때 발생시키는 예외입니다."""


def sleep_random(min_seconds: float, max_seconds: float, label: str) -> None:
    """지정 범위 안에서 임의 시간 동안 대기합니다."""

    wait_seconds = random.uniform(min_seconds, max_seconds)
    print(f"{label}: {wait_seconds:.1f}초 대기합니다.")
    time.sleep(wait_seconds)


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
) -> list[dict[str, Any]]:
    """
    review_checked_at이 NULL이거나 오늘 이전인 활성 상품을
    product_id 순서로 전체 조회합니다.
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
    """

    db.execute(sql)
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


def get_existing_review_codes(
    db: DBManager,
) -> set[str]:
    """
    reviews 테이블 전체에 이미 저장된 review_code를 조회합니다.

    최신순 증분수집에서는 현재 상품의 product_id에 한정하지 않고,
    DB 전체의 review_code와 비교하여 기존 리뷰가 하나라도 나오면
    최신순의 다음 페이지 요청을 중단합니다.
    """

    sql = """
        SELECT review_code
        FROM reviews
    """

    db.execute(sql)
    rows = db.fetchall()

    return {
        str(row["review_code"]).strip()
        for row in rows
        if row.get("review_code") is not None
        and str(row["review_code"]).strip()
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

    429 또는 차단 안내 응답은 재시도하지 않고 즉시 중단합니다.
    연결 오류와 일시적인 5xx 응답만 제한적으로 재시도합니다.
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

    for attempt in range(1, MAX_TRANSIENT_RETRIES + 2):
        # 첫 요청도 바로 보내지 않고 대기합니다.
        sleep_random(
            REQUEST_DELAY_MIN,
            REQUEST_DELAY_MAX,
            "API 요청 전",
        )

        try:
            response = session.post(
                API_URL,
                json=payload,
                timeout=(10, 30),
            )
        except (requests.Timeout, requests.ConnectionError) as error:
            if attempt > MAX_TRANSIENT_RETRIES:
                raise

            wait_seconds = (
                TRANSIENT_BASE_WAIT * attempt
                + random.uniform(0, TRANSIENT_JITTER_MAX)
            )
            print(
                f"일시적 네트워크 오류({attempt}/"
                f"{MAX_TRANSIENT_RETRIES + 1}): {error}"
            )
            print(f"{wait_seconds:.1f}초 후 재시도합니다.")
            time.sleep(wait_seconds)
            continue

        content_type = response.headers.get(
            "Content-Type",
            "",
        ).lower()
        response_text = response.text

        is_rate_limited = (
            response.status_code == 429
            or "잠시만 기다려 주세요" in response_text
            or "Too Many Requests" in response_text
        )

        if is_rate_limited:
            retry_after = response.headers.get("Retry-After")
            print(f"상태 코드: {response.status_code}")
            print(f"요청 Payload: {payload}")
            print(f"Retry-After: {retry_after or '없음'}")
            print(f"서버 응답: {response_text[:500]}")

            message = (
                "리뷰 API 요청 제한이 감지되었습니다. "
                "같은 실행에서는 재시도하지 않고 전체 수집을 중단합니다."
            )
            if retry_after:
                message += f" 서버 권장 대기값: {retry_after}"
            raise ReviewRateLimitError(message)

        # 500, 502, 503, 504 같은 일시적 서버 오류만 재시도
        if response.status_code in {500, 502, 503, 504}:
            if attempt > MAX_TRANSIENT_RETRIES:
                response.raise_for_status()

            wait_seconds = (
                TRANSIENT_BASE_WAIT * attempt
                + random.uniform(0, TRANSIENT_JITTER_MAX)
            )
            print(
                f"일시적 서버 오류 {response.status_code} "
                f"({attempt}/{MAX_TRANSIENT_RETRIES + 1})"
            )
            print(f"{wait_seconds:.1f}초 후 재시도합니다.")
            time.sleep(wait_seconds)
            continue

        if response.status_code != 200:
            print(f"상태 코드: {response.status_code}")
            print(f"요청 Payload: {payload}")
            print(f"서버 응답: {response_text[:500]}")

        response.raise_for_status()

        if "application/json" not in content_type:
            raise RuntimeError(
                "리뷰 API가 JSON이 아닌 응답을 반환했습니다. "
                f"Content-Type={content_type or 'unknown'}"
            )

        try:
            result = response.json()
        except requests.JSONDecodeError as error:
            raise RuntimeError(
                "리뷰 API JSON 응답을 해석하지 못했습니다."
            ) from error

        if result.get("status") != "SUCCESS":
            raise RuntimeError(
                f"API 실패: "
                f"{result.get('code')} / "
                f"{result.get('message')}"
            )

        return result

    raise RuntimeError("리뷰 API 호출 재시도 횟수를 초과했습니다.")

def crawl_one_sort(
    session: requests.Session,
    goods_number: str,
    sort_name: str,
    sort_type: str,
    existing_review_codes: set[str],
    stop_on_existing: bool,
) -> dict[int, dict[str, Any]]:
    """
    정렬 기준 하나의 리뷰를 수집합니다.

    stop_on_existing=True인 정렬에서는 기존 리뷰가 포함된 페이지를
    만나면 즉시 종료하여 불필요한 API 호출을 줄입니다.
    """

    cursor_id = None
    cursor_score = None
    cursor_count = None

    reviews_by_code: dict[int, dict[str, Any]] = {}
    seen_cursors: set[tuple[Any, Any, Any]] = set()

    request_count = 0
    consecutive_existing_pages = 0
    # 4개 정렬 모두 정렬별 최대 페이지 수는 동일하게 유지합니다.
    # 최신순은 기존 리뷰를 만나면 최대 페이지 전에 조기 종료됩니다.
    max_pages = MAX_PAGES_FULL

    while request_count < max_pages:
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
        existing_count = 0

        for review in reviews:
            review_code = str(review.get("reviewId") or "").strip()

            if not review_code:
                print(
                    f"[{sort_name}] "
                    "비어 있는 reviewId를 발견하여 제외합니다."
                )
                continue

            review_goods_number = (
                (review.get("goodsDto") or {})
                .get("goodsNumber")
            )

            if str(review_goods_number) != str(goods_number):
                continue

            if review_code in existing_review_codes:
                existing_count += 1
                continue

            if review_code not in reviews_by_code:
                reviews_by_code[review_code] = review
                new_count += 1

        print(
            f"[{sort_name}] "
            f"요청 {request_count}/{max_pages}회 | "
            f"응답 {len(reviews)}개 | "
            f"신규 {new_count}개 | "
            f"기존 {existing_count}개 | "
            f"누적 신규 {len(reviews_by_code)}개"
        )

        if stop_on_existing and existing_count > 0:
            consecutive_existing_pages += 1
        else:
            consecutive_existing_pages = 0

        if (
            stop_on_existing
            and consecutive_existing_pages >= STOP_AFTER_EXISTING_PAGES
        ):
            print(
                f"[{sort_name}] 기존 리뷰가 확인되어 "
                "더 오래된 페이지 요청을 중단합니다."
            )
            break

        if login_required:
            print(
                f"[{sort_name}] 비로그인 제한 도달 | "
                f"현재까지 신규 {len(reviews_by_code)}개"
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
            print(
                f"[{sort_name}] "
                f"동일 커서가 반복되어 종료합니다: {next_cursor}"
            )
            break

        seen_cursors.add(next_cursor)
        cursor_id, cursor_score, cursor_count = next_cursor

        if cursor_id is None:
            print(f"[{sort_name}] nextCursorId가 없어 종료합니다.")
            break

    if request_count >= max_pages:
        print(
            f"[{sort_name}] 안전 제한인 최대 {max_pages}페이지에 "
            "도달하여 종료합니다."
        )

    return reviews_by_code

def crawl_product_reviews(
    session: requests.Session,
    goods_number: str,
    existing_review_codes: set[str],
) -> dict[int, dict[str, Any]]:
    """
    상품 하나의 리뷰를 4개 정렬 기준으로 모두 수집합니다.

    기존 리뷰가 있는 증분수집 상품이라도
    최신순·도움순·평점높은순·평점낮은순을 모두 순회합니다.
    단, 최신순에서만 기존 review_code가 발견되면
    더 오래된 페이지 요청을 즉시 중단합니다.
    """

    has_existing_reviews = bool(existing_review_codes)
    sort_types = FULL_SORT_TYPES

    if has_existing_reviews:
        print(
            "기존 리뷰가 있어 증분수집으로 진행합니다: "
            "4개 정렬 모두 조회, 최신순만 기존 리뷰 발견 시 조기 종료"
        )
    else:
        print("기존 리뷰가 없어 최초수집으로 진행합니다: 4개 정렬 조회")

    all_reviews_by_code: dict[int, dict[str, Any]] = {}

    for sort_index, (sort_name, sort_type) in enumerate(
        sort_types.items(),
        start=1,
    ):
        print()
        print("-" * 70)
        print(f"{sort_name} 수집 시작: {sort_type}")
        print("-" * 70)

        # 기존 리뷰가 있는 상품의 '최신순'에만 조기 종료를 적용합니다.
        # 도움순·평점높은순·평점낮은순은 기존 리뷰가 나와도 계속 순회합니다.
        stop_on_existing = (
            has_existing_reviews
            and sort_type == "DATETIME_DESC"
        )

        sort_reviews = crawl_one_sort(
            session=session,
            goods_number=goods_number,
            sort_name=sort_name,
            sort_type=sort_type,
            existing_review_codes=existing_review_codes,
            stop_on_existing=stop_on_existing,
        )

        before_count = len(all_reviews_by_code)

        for review_code, review in sort_reviews.items():
            all_reviews_by_code.setdefault(review_code, review)

        added_count = len(all_reviews_by_code) - before_count

        print(
            f"[{sort_name}] 전체 결과에 새로 추가 "
            f"{added_count}개 | "
            f"상품 누적 신규 리뷰 "
            f"{len(all_reviews_by_code)}개"
        )

        if sort_index < len(sort_types):
            sleep_random(
                SORT_DELAY_MIN,
                SORT_DELAY_MAX,
                "다음 정렬 수집 전",
            )

    return all_reviews_by_code


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

    review_code = str(review.get("reviewId") or "").strip()

    if not review_code:
        print("review_code가 비어 있어 제외합니다.")
        return None

    try:
        review_score = int(review.get("reviewScore"))
    except (TypeError, ValueError):
        print("review_score가 올바르지 않아 제외합니다.")
        return None

    review_content = normalize_text(
        review.get("content")
    )

    if not review_content:
        print(
            f"review_code={review_code}: "
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
        review_code,
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

    사전에 DB 기존 review_code를 제외한 행만 전달받습니다.
    INSERT IGNORE는 동시 실행 등 예외 상황을 위한 마지막 안전장치입니다.

    반환값:
        시도한 리뷰 수, 실제 신규 저장 수
    """

    if not review_rows:
        return 0, 0

    sql = """
        INSERT IGNORE INTO reviews (
            review_code,
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

        products = get_target_products(db=db)

        if not products:
            print(
                "review_checked_at이 NULL이거나 오늘 이전인 "
                "활성 상품을 찾지 못했습니다."
            )
            return

        print()
        print("=" * 70)
        print("리뷰 증분수집 시작")
        print(f"수집 모드: {COLLECTION_MODE}")
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
                # 2. DB 기존 review_code 조회
                # ------------------------------------------------

                existing_review_codes = get_existing_review_codes(
                    db=db,
                )

                print(
                    f"DB 전체 기존 review_code 수: "
                    f"{len(existing_review_codes)}개"
                )

                # ------------------------------------------------
                # 3. 리뷰 API 수집
                # ------------------------------------------------

                raw_reviews = crawl_product_reviews(
                    session=session,
                    goods_number=goods_number,
                    existing_review_codes=existing_review_codes,
                )

                collected_at = datetime.now()

                review_rows: list[tuple[Any, ...]] = []
                option_unmatched_count = 0

                # ------------------------------------------------
                # 4. DB에 없는 리뷰만 저장 형태로 변환
                # ------------------------------------------------

                skipped_existing_count = 0

                for review_code, raw_review in raw_reviews.items():
                    if review_code in existing_review_codes:
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

                insert_ignored_count = (
                    attempted_count - inserted_count
                )

                print()
                print("-" * 70)
                print("상품 DB 저장 완료")
                print(
                    f"수집한 고유 리뷰      : "
                    f"{len(raw_reviews)}개"
                )
                print(
                    f"수집리뷰 중 DB 중복 리뷰         : "
                    f"{skipped_existing_count}개"
                )
                print(
                    f"신규 저장 대상       : "
                    f"{attempted_count}개"
                )
                print(
                    f"신규 저장 완료       : "
                    f"{inserted_count}개"
                )
                print(
                    f"INSERT 시 중복 제외  : "
                    f"{insert_ignored_count}개"
                )
                print(
                    f"옵션 미연결(NULL)    : "
                    f"{option_unmatched_count}개"
                )
                print(
                    "products.review_checked_at 갱신 완료"
                )
                print("-" * 70)

            except ReviewRateLimitError as error:
                rollback_transaction(db)
                failed_product_count += 1

                print()
                print(
                    f"상품 {goods_number} 요청 제한 오류: {error}"
                )
                print(
                    "해당 상품의 리뷰 저장과 "
                    "review_checked_at 갱신을 롤백했습니다."
                )
                print(
                    "요청 제한이 계속되고 있으므로 "
                    "이번 리뷰 수집 전체를 중단합니다."
                )
                raise

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
                # 상품 30개마다 10~15분간 긴 휴식을 갖습니다.
                if index % PRODUCT_BATCH_SIZE == 0:
                    sleep_random(
                        LONG_BREAK_MIN,
                        LONG_BREAK_MAX,
                        f"상품 {index}개 처리 완료 - 긴 휴식",
                    )
                else:
                    sleep_random(
                        PRODUCT_DELAY_MIN,
                        PRODUCT_DELAY_MAX,
                        "다음 상품 처리 전",
                    )

        print()
        print("=" * 70)
        print("리뷰 증분수집 완료")
        print(f"조회 대상 상품      : {len(products)}개")
        print(f"성공 상품           : {success_product_count}개")
        print(f"실패 상품           : {failed_product_count}개")
        print(
            f"전체 신규 저장 대상 : "
            f"{total_collected_count}개"
        )
        print(
            f"전체 신규 저장 완료 : "
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