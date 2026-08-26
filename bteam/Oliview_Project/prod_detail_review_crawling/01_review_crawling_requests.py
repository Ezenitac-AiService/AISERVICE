# 비로그인 - 리뷰 API(JSON) 크롤링
# 립메이크업 - 립틴트 - 헤라 - 제품1개 페이지 - 최신순/도움순/평점높은순/평점낮은순 API(JSON)리뷰 크롤링
# 결과저장 : oliveyoung_A000000202425_raw_reviews.json 

import json
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests


PRODUCT_URL = (
    "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do"
    "?goodsNo=A000000202425"
    "&dispCatNo=1000001000200060003"
)

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

PAGE_SIZE = 10
REQUEST_DELAY = 1.0

# 평점 정렬값은 Network Payload에서 확인한 실제 값으로 교체
SORT_TYPES = {
    "최신순": "DATETIME_DESC",
    "도움순": "RECOMMENDED_DESC",
    "평점높은순": "RATING_DESC",
    "평점낮은순": "RATING_ASC",
}


def extract_goods_number(product_url: str) -> str:
    query = parse_qs(urlparse(product_url).query)

    if "goodsNo" not in query:
        raise ValueError("URL에 goodsNo가 없습니다.")

    return query["goodsNo"][0]


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

    response = session.post(
        API_URL,
        json=payload,
        timeout=30,
    )

    if response.status_code != 200:
        print("상태 코드:", response.status_code)
        print("요청 Payload:", payload)
        print("서버 응답:", response.text[:1000])

    response.raise_for_status()

    result = response.json()

    if result.get("status") != "SUCCESS":
        raise RuntimeError(
            f"API 실패: {result.get('code')} / "
            f"{result.get('message')}"
        )

    return result


def crawl_one_sort(
    session: requests.Session,
    goods_number: str,
    sort_name: str,
    sort_type: str,
) -> dict[int, dict[str, Any]]:
    """정렬 기준 하나를 커서가 끝날 때까지 수집합니다."""

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

        # 반환받은 리뷰를 먼저 저장
        if reviews:
            new_count = 0

            for review in reviews:
                review_id = review.get("reviewId")

                if review_id is None:
                    print(f"[{sort_name}] reviewId 없는 리뷰 발견")
                    continue

                if review_id not in reviews_by_id:
                    reviews_by_id[review_id] = review
                    new_count += 1

            print(
                f"[{sort_name}] 요청 {request_count}회 | "
                f"응답 {len(reviews)}개 | "
                f"신규 {new_count}개 | "
                f"정렬 내 고유 리뷰 {len(reviews_by_id)}개"
            )

        # 비로그인 제한에 도달
        if login_required:
            print(
                f"[{sort_name}] 비로그인 리뷰 제한에 도달했습니다. "
                f"현재까지 {len(reviews_by_id)}개 수집"
            )
            break

        # 서버가 마지막 리뷰라고 표시
        if not has_next:
            print(
                f"[{sort_name}] 모든 리뷰를 수집했습니다. "
                f"총 {len(reviews_by_id)}개"
            )
            break

        # 비정상 응답 방어
        if not reviews:
            print(
                f"[{sort_name}] hasNext=True이지만 "
                f"리뷰 목록이 비어 있어 종료합니다."
            )
            print(
                f"[{sort_name}] "
                f"nextCursorId={data.get('nextCursorId')}, "
                f"nextCursorScore={data.get('nextCursorScore')}, "
                f"nextCursorCount={data.get('nextCursorCount')}"
            )
            break

        next_cursor = (
            data.get("nextCursorId"),
            data.get("nextCursorScore"),
            data.get("nextCursorCount"),
        )

        # 동일 커서 반복 방지
        if next_cursor in seen_cursors:
            print(
                f"[{sort_name}] 동일 커서가 반복되어 종료합니다: "
                f"{next_cursor}"
            )
            break

        seen_cursors.add(next_cursor)

        cursor_id, cursor_score, cursor_count = next_cursor

        if cursor_id is None:
            print(
                f"[{sort_name}] hasNext=True이지만 "
                f"nextCursorId가 없어 종료합니다."
            )
            break

        time.sleep(REQUEST_DELAY)

    return reviews_by_id


def main() -> None:
    goods_number = extract_goods_number(PRODUCT_URL)

    session = requests.Session()
    session.headers.update(HEADERS)

    # 네 정렬 결과를 reviewId 기준으로 합침
    all_reviews_by_id: dict[int, dict[str, Any]] = {}

    # 어떤 정렬 기준에서 발견됐는지 별도로 기록
    sort_sources_by_review_id: dict[int, set[str]] = {}

    sort_statistics: dict[str, dict[str, int]] = {}

    for sort_name, sort_type in SORT_TYPES.items():
        print()
        print("=" * 70)
        print(f"{sort_name} 수집 시작: {sort_type}")
        print("=" * 70)

        try:
            sort_reviews = crawl_one_sort(
                session=session,
                goods_number=goods_number,
                sort_name=sort_name,
                sort_type=sort_type,
            )

        except requests.RequestException as error:
            print(f"[{sort_name}] 네트워크 오류:", error)
            continue

        except Exception as error:
            print(f"[{sort_name}] 수집 오류:", error)
            continue

        before_count = len(all_reviews_by_id)

        for review_id, review in sort_reviews.items():
            if review_id not in all_reviews_by_id:
                # API 리뷰 객체를 가공하지 않고 그대로 보관
                all_reviews_by_id[review_id] = review

            sort_sources_by_review_id.setdefault(
                review_id,
                set(),
            ).add(sort_name)

        after_count = len(all_reviews_by_id)

        sort_statistics[sort_name] = {
            "정렬_내_고유_리뷰수": len(sort_reviews),
            "전체에_새로_추가된_리뷰수": after_count - before_count,
            "전체_누적_고유_리뷰수": after_count,
        }

        print(
            f"[{sort_name}] 정렬 내 {len(sort_reviews)}개 | "
            f"새로 추가 {after_count - before_count}개 | "
            f"전체 누적 {after_count}개"
        )

        time.sleep(2)

    final_reviews = []

    for review_id, review in all_reviews_by_id.items():
        # 원본 리뷰 객체를 수정하지 않도록 얕은 복사
        review_copy = review.copy()

        # 크롤링 검증용 메타데이터만 추가
        review_copy["_crawlMeta"] = {
            "collectedSortTypes": sorted(
                sort_sources_by_review_id.get(review_id, set())
            )
        }

        final_reviews.append(review_copy)

    final_reviews.sort(
        key=lambda review: review.get("reviewId", 0),
        reverse=True,
    )

    output = {
        "crawlInfo": {
            "category": "립메이크업 > 립틴트",
            "brand": "헤라",
            "productUrl": PRODUCT_URL,
            "goodsNumber": goods_number,
            "sortTypes": SORT_TYPES,
            "sortStatistics": sort_statistics,
            "uniqueReviewCount": len(final_reviews),
        },
        "reviews": final_reviews,
    }

    output_filename = (
        f"oliveyoung_{goods_number}_raw_reviews.json"
    )

    with open(
        output_filename,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print("=" * 70)
    print("전체 수집 완료")
    print("상품번호:", goods_number)
    print("정렬별 통계:", sort_statistics)
    print("중복 제거 후 고유 리뷰:", len(final_reviews))
    print("저장 파일:", output_filename)
    print("=" * 70)


if __name__ == "__main__":
    main()


# ======================================================================
# 최신순 수집 시작: DATETIME_DESC
# ======================================================================
# [최신순] 요청 1회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 10개
# [최신순] 요청 2회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 20개
# [최신순] 요청 3회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 30개
# [최신순] 요청 4회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 40개
# [최신순] 요청 5회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 50개
# [최신순] 요청 6회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 60개
# [최신순] 요청 7회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 70개
# [최신순] 요청 8회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 80개
# [최신순] 요청 9회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 90개
# [최신순] 요청 10회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 100개
# [최신순] 비로그인 리뷰 제한에 도달했습니다. 현재까지 100개 수집
# [최신순] 정렬 내 100개 | 새로 추가 100개 | 전체 누적 100개

# ======================================================================
# 도움순 수집 시작: RECOMMENDED_DESC
# ======================================================================
# [도움순] 요청 1회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 10개
# [도움순] 요청 2회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 20개
# [도움순] 요청 3회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 30개
# [도움순] 요청 4회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 40개
# [도움순] 요청 5회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 50개
# [도움순] 요청 6회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 60개
# [도움순] 요청 7회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 70개
# [도움순] 요청 8회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 80개
# [도움순] 요청 9회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 90개
# [도움순] 요청 10회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 100개
# [도움순] 비로그인 리뷰 제한에 도달했습니다. 현재까지 100개 수집
# [도움순] 정렬 내 100개 | 새로 추가 87개 | 전체 누적 187개

# ======================================================================
# 평점높은순 수집 시작: RATING_DESC
# ======================================================================
# [평점높은순] 요청 1회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 10개
# [평점높은순] 요청 2회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 20개
# [평점높은순] 요청 3회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 30개
# [평점높은순] 요청 4회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 40개
# [평점높은순] 요청 5회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 50개
# [평점높은순] 요청 6회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 60개
# [평점높은순] 요청 7회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 70개
# [평점높은순] 요청 8회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 80개
# [평점높은순] 요청 9회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 90개
# [평점높은순] 요청 10회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 100개
# [평점높은순] 비로그인 리뷰 제한에 도달했습니다. 현재까지 100개 수집
# [평점높은순] 정렬 내 100개 | 새로 추가 15개 | 전체 누적 202개

# ======================================================================
# 평점낮은순 수집 시작: RATING_ASC
# ======================================================================
# [평점낮은순] 요청 1회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 10개
# [평점낮은순] 요청 2회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 20개
# [평점낮은순] 요청 3회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 30개
# [평점낮은순] 요청 4회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 40개
# [평점낮은순] 요청 5회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 50개
# [평점낮은순] 요청 6회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 60개
# [평점낮은순] 요청 7회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 70개
# [평점낮은순] 요청 8회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 80개
# [평점낮은순] 요청 9회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 90개
# [평점낮은순] 요청 10회 | 응답 10개 | 신규 10개 | 정렬 내 고유 리뷰 100개
# [평점낮은순] 비로그인 리뷰 제한에 도달했습니다. 현재까지 100개 수집
# [평점낮은순] 정렬 내 100개 | 새로 추가 67개 | 전체 누적 269개

# ======================================================================
# 전체 수집 완료
# 상품번호: A000000202425
# 정렬별 통계: {'최신순': {'정렬_내_고유_리뷰수': 100, '전체에_새로_추가된_리뷰수': 100, '전체_누적_고유_리뷰수': 100}, '도움순': {'정렬_내_고유_리뷰수': 100, '전체에_새로_추가된_리뷰수': 87, '전체_누적_고유_리뷰수': 187}, '평점높은순': {'정렬_내_고유_리뷰수': 100, '전체에_새로_추가된_리뷰수': 15, '전체_누적_고유_리뷰수': 202}, '평점낮은순': {'정렬_내_고유_리뷰수': 100, '전체에_새로_추가된_리뷰수': 67, '전체_누적_고유_리뷰수': 269}}
# 중복 제거 후 고유 리뷰: 269
# 저장 파일: oliveyoung_A000000202425_raw_reviews.json
# ======================================================================