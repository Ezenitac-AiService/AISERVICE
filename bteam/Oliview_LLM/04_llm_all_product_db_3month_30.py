# 이 코드는 products 테이블의 분석 대상 상품을 기준으로,
# 속성별 문장단위 감성분석 결과를 이용해
# 속성별 요약과 상품 전체 종합보고서를 생성하여 DB에 저장합니다.


# [속성별 문장 선택 기준]
# - 각 속성의 긍정 문장과 부정 문장을 구분하여 처리합니다.
# - 중복 문장은 제거한 뒤, 최근 3개월 문장을 최신순으로 우선 선택합니다.
# - 최근 3개월 문장이 부족하면 3개월 이전 문장으로 보충합니다.
# - 속성 하나당 긍정 문장 최대 30개,
#   부정 문장 최대 30개를 LLM에 전달합니다.
# - 따라서 속성 하나당 최대 60개의 문장이 분석에 사용됩니다.


# [리뷰 문장이 없는 경우]
# - 특정 속성의 긍정 문장이 0개이면
# "해당 속성에 대한 긍정 의견이 없습니다."를 저장합니다.
# - 특정 속성의 부정 문장이 0개이면
# "해당 속성에 대한 부정 의견이 없습니다."를 저장합니다.
# - 특정 속성의 긍정·부정 문장이 모두 0개여도
# 해당 속성 결과는 DB에 저장합니다.


# [상품 전체 문장이 없는 경우]
# - vw_llm_analysis_source에 나타나지 않는 리뷰 없는 상품도
# products 테이블에 존재하고 분석 속성이 설정된 카테고리에
# 연결되어 있으면 분석 대상에 포함합니다.
# - 상품 전체에 긍정·부정 문장이 모두 0개이면
# LLM을 호출하지 않고 기본 안내 문구를 저장합니다.
# - 이 경우에도 카테고리에 설정된 전체 속성을 생성하여
# 속성별 결과와 상품 전체 결과를 모두 DB에 저장합니다.


# [저장 테이블]
# - llm_product_reports
# : 상품 전체 유지·개선·종합 보고서 저장
# - llm_product_attribute_reports
# : 상품별 전체 속성의 긍정·부정 요약 저장


# 저장이 모두 성공한 경우에만
# products.llm_analyzed_at을 현재 시각으로 갱신합니다.

# ============================================================
# 0. 코드 전체 흐름
# ============================================================
# products 테이블
#    ↓
# 오늘 아직 LLM 분석하지 않은 상품 조회
#    ↓
# 상품 1개씩 반복
#    ↓
# 상품 기본 정보 조회
#    ↓
# 상품에 적용되는 분석 카테고리 조회
#    ↓
# 카테고리에 설정된 전체 속성 조회
#    ↓
# vw_llm_analysis_source에서
# 속성별 리뷰 문장 + 감성 결과 조회
#    ↓
# 속성별로 그룹화
#    ├─ 긍정
#    ├─ 부정
#    ├─ 중립
#    └─ unknown
#    ↓
# 각 속성의 긍정·부정 문장 중복 제거
#    ↓
# 각 속성
#    ├─ 최근 3개월 리뷰 우선
#    ├─ 부족하면 과거 리뷰 보충
#    ├─ 긍정 최대 30개
#    └─ 부정 최대 30개
#    ↓
# LLM 속성별 요약
#    ├─ positive_summary
#    └─ negative_summary
#    ↓
# 모든 속성 요약을 다시 LLM에 전달
#    ↓
# 상품 전체 보고서
#    ├─ keep_summary
#    ├─ improvement_summary
#    └─ overall_summary
#    ↓
# DB 저장
#    ├─ llm_product_reports
#    └─ llm_product_attribute_reports
#    ↓
# 모두 성공
#    ↓
# products.llm_analyzed_at = NOW()



import json  # LLM이 반환한 JSON 문자열을 Python 딕셔너리로 변환할 때 사용
import os    # .env에 저장된 DB 환경변수를 읽일 때 사용
import re    #  LLM 응답에서 ```json 같은 마크다운이나 JSON 부분을 정규표현식으로 찾아낼 때 사용
from datetime import date, datetime  # 리뷰날짜와 오늘날짜를 비교하기 위해 사용
from typing import Any               # 환경 매개변수가 여러 자료형을 받을 수 있음을 타입힌트로 표현

import pymysql  # Python에서 MySQL에 접속하기 위한 라이브러리

import calendar # 특정 연/월의 마지막 날짜가 며칠인지 알아낼때 사용
                # 예: 2026년 2월 -> 28일

# 공통기능을 common.py에서 가져옴
from common import (
    clean_think_tags,       # LLM응답의 <think>...</think> 같은 추론 태그 제거
    get_openai_client,      # LLM 서버에 요청을 보내기 위한 OpenAI 호환 client 생성
    load_sample_config,     # 사용할 모델명 등의 설정조회
    NO_THINK_SYSTEM_PROMPT, # LLM이 생각과정 등을 출력하지 않도록 전달하는 시스템 프롬프트
)


# ============================================================
# 1. 테스트 설정
# ============================================================

# 전체 상품 분석 설정
# 0보다 큰 값이면 해당 개수만 테스트 실행, None이면 전체 실행
PRODUCT_LIMIT = None

# 속성 하나에서 LLM에 전달할 최대 문장 수
# 문장이 너무 많으면 모델의 입력 길이를 초과할 수 있어서 제한합니다.
MAX_POSITIVE_SENTENCES = 30  # 속성 하나당 긍정문장 최대 30개
MAX_NEGATIVE_SENTENCES = 30  # 속성 하나당 부정문장 최대 30개

# 분석할 문장이 없을 때 저장할 공통 안내 문구
NO_ATTRIBUTE_POSITIVE = "해당 속성에 대한 긍정 의견이 없습니다."
NO_ATTRIBUTE_NEGATIVE = "해당 속성에 대한 부정 의견이 없습니다."
NO_OVERALL_KEEP = "유지할 만한 긍정 의견이 확인되지 않았습니다."
NO_OVERALL_IMPROVEMENT = "우선적으로 개선이 필요한 부정 의견이 확인되지 않았습니다."
NO_OVERALL_SUMMARY = "종합 평가를 생성할 수 있는 긍정·부정 의견이 충분하지 않습니다."


# ============================================================
# 2. DB 연결
# ============================================================

def get_db_connection():
    """
    .env 파일의 MySQL 접속 정보를 사용합니다.
    """

    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "GP"),
        password=os.getenv("DB_PASSWORD", "GP123!"),
        database=os.getenv("DB_NAME", "oliview_project"),
        charset="utf8mb4",                       # 한글과 이모지 등을 정상적으로 처리 
        cursorclass=pymysql.cursors.DictCursor,  # 조회결과를 튜플이 아닌, 딕셔너리로 받음
        autocommit=False,  # INSERT할때 자동 commit하지 않음
    )


# ============================================================
# 3. 상품 1개의 속성 문장 조회
# ============================================================

# 1) 상품 1개의 리뷰 분석결과 조회
def get_product_analysis_rows(
    connection,
    product_id: int,
) -> list[dict]:
    """
    상품 1개의 속성별 문장단위 감성분석 결과를
    최신 리뷰 순으로 조회합니다.
    """

    sql = """
        SELECT
            product_id,
            product_name,
            brand_name,
            category,
            analysis_category_id,
            display_name,
            aspect_sentence_id,
            separated_sentence,
            sentiment_label,
            review_date
        FROM vw_llm_analysis_source
        WHERE product_id = %s
        ORDER BY
            analysis_category_id,
            display_name,
            review_date DESC,
            aspect_sentence_id DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, (product_id,))  # %s에 product_id를 전달하여 실행
        return cursor.fetchall()            # 조회된 모든 행을 반환


# 2) 카테고리 전체 속성 조회
# 카테고리에 설정된 모든속성을 가져옴
def get_analysis_category_attributes(
    connection,
    analysis_category_ids: list[int],
) -> list[dict]:
    """
    상품에 연결된 분석 카테고리의 전체 속성을 표시 순서대로 조회합니다.

    실제 리뷰 문장이 없는 속성도 빠지지 않도록
    vw_llm_analysis_attributes를 기준으로 속성 목록을 가져옵니다.
    """

    # analysis_category_id의 중복을 제거
    category_ids = list(dict.fromkeys(
        int(category_id)
        for category_id in analysis_category_ids
        if category_id is not None
    ))

    # 분석 카테고리가 하나도 없다면 빈리스트 반환
    if not category_ids:
        return []

    placeholders = ", ".join(["%s"] * len(category_ids))

    sql = f"""
        SELECT
            analysis_category_id,
            display_name,
            display_order
        FROM vw_llm_analysis_attributes
        WHERE analysis_category_id IN ({placeholders})
        ORDER BY
            analysis_category_id,
            display_order,
            display_name
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, tuple(category_ids))
        return cursor.fetchall()

# ============================================================
# 3-1. 상품 기본 정보 및 분석 카테고리 조회
# ============================================================
# 1) 상품 기본정보 조회
# vw_llm_analysis_source가 아니라 products를 기준으로 상품 정보를 가져옴
def get_product_base_info(
    connection,
    product_id: int,
) -> dict | None:
    """
    문장단위 감성분석 결과가 0건이어도 상품 분석을 진행할 수 있도록
    products, brands, product_categories, categories에서 상품 정보를 조회합니다.

    카테고리 표시는 기존 분석 뷰와 동일하게
    메이크업은 중분류, 그 외는 대분류를 사용합니다.
    """

    sql = """
        SELECT
            p.product_id,
            p.product_name,
            b.brand_name,
            GROUP_CONCAT(
                DISTINCT CASE
                    WHEN c1.category_name = '메이크업'
                        THEN c2.category_name
                    ELSE c1.category_name
                END
                ORDER BY CASE
                    WHEN c1.category_name = '메이크업'
                        THEN c2.category_name
                    ELSE c1.category_name
                END
                SEPARATOR ', '
            ) AS category
        FROM products p
        INNER JOIN brands b
            ON b.brand_id = p.brand_id
        LEFT JOIN product_categories pc
            ON pc.product_id = p.product_id
        LEFT JOIN categories c3
            ON c3.category_id = pc.category_id
        LEFT JOIN categories c2
            ON c2.category_id = c3.parent_category_id
        LEFT JOIN categories c1
            ON c1.category_id = c2.parent_category_id
        WHERE p.product_id = %s
        GROUP BY
            p.product_id,
            p.product_name,
            b.brand_name
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, (product_id,))
        row = cursor.fetchone() # 상품 하나만 가져옴

    # 상품 자체가 없으면 종료
    if not row:
        return None

    # 카테고리가 NULL이면 "미분류"
    row["category"] = str(row.get("category") or "미분류")
    return row

# 2) 상품의 analysis_category_id 찾기
def get_product_analysis_category_ids(
    connection,
    product_id: int,
) -> list[int]:
    """
    상품에 연결된 카테고리를 기준으로 실제 LLM 분석에 사용할
    analysis_category_id 목록을 조회합니다.

    메이크업은 중분류 category_id, 그 외는 대분류 category_id를 사용하며,
    vw_llm_analysis_attributes에 실제 속성이 설정된 카테고리만 반환합니다.
    """

    sql = """
        SELECT DISTINCT
            CASE
                WHEN c1.category_name = '메이크업'
                    THEN c2.category_id
                ELSE c1.category_id
            END AS analysis_category_id
        FROM product_categories pc
        INNER JOIN categories c3
            ON c3.category_id = pc.category_id
        INNER JOIN categories c2
            ON c2.category_id = c3.parent_category_id
        INNER JOIN categories c1
            ON c1.category_id = c2.parent_category_id
        INNER JOIN vw_llm_analysis_attributes attr
            ON attr.analysis_category_id = CASE
                WHEN c1.category_name = '메이크업'
                    THEN c2.category_id
                ELSE c1.category_id
            END
        WHERE pc.product_id = %s
        ORDER BY analysis_category_id
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, (product_id,))
        rows = cursor.fetchall()

    return [
        int(row["analysis_category_id"])
        for row in rows
        if row.get("analysis_category_id") is not None
    ]


# ============================================================
# 3-2. 전체 분석 대상 상품 ID 조회
# ============================================================
# 오늘 분석할 상품 찾기
def get_target_product_ids(
    connection,
    limit: int | None = None,
) -> list[int]:
    """
    문장단위 감성분석 결과의 존재 여부와 관계없이,
    오늘 아직 LLM 분석에 성공하지 않은 상품 ID를 조회합니다.

    분석 속성이 설정된 카테고리에 연결된 상품만 대상으로 하며,
    llm_analyzed_at이 NULL이거나 오늘보다 이전 날짜인 상품을 가져옵니다.
    """

    params = []

    limit_sql = ""
    if limit is not None and limit > 0:
        limit_sql = " LIMIT %s"
        params.append(limit)

    sql = f"""
        SELECT DISTINCT p.product_id
        FROM products p
        INNER JOIN product_categories pc
            ON pc.product_id = p.product_id
        INNER JOIN categories c3
            ON c3.category_id = pc.category_id
        INNER JOIN categories c2
            ON c2.category_id = c3.parent_category_id
        INNER JOIN categories c1
            ON c1.category_id = c2.parent_category_id
        INNER JOIN vw_llm_analysis_attributes attr
            ON attr.analysis_category_id = CASE
                WHEN c1.category_name = '메이크업'
                    THEN c2.category_id
                ELSE c1.category_id
            END
        WHERE
            p.llm_analyzed_at IS NULL
            OR DATE(p.llm_analyzed_at) < CURDATE()
        ORDER BY p.product_id
        {limit_sql}
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()

    return [int(row["product_id"]) for row in rows]


# ============================================================
# 4. 감성 라벨 통일
# ============================================================

def normalize_sentiment(label: Any) -> str:
    """
    DB의 감성 라벨을 positive, negative, neutral로 통일합니다.

    DB에 저장된 값이
    긍정/부정, POSITIVE/NEGATIVE, pos/neg 등이어도 처리합니다.
    """

    value = str(label or "").strip().lower()

    if value in {
        "positive",
        "pos",
        "긍정",
        "긍정적",
        "1",
    }:
        return "positive"

    if value in {
        "negative",
        "neg",
        "부정",
        "부정적",
        "0",
    }:
        return "negative"

    if value in {
        "neutral",
        "neu",
        "중립",
        "중립적",
    }:
        return "neutral"

    return "unknown"


# ============================================================
# 5. 최근 3개월 우선 문장 선택
# ============================================================

def is_within_recent_months(
    review_date: Any,
    months: int = 3,
) -> bool:
    """
    리뷰 작성일이 오늘 기준 최근 N개월 이내인지 확인합니다.

    예:
    오늘이 2026-08-05이고 months=3이면
    2026-05-05 이후 리뷰를 최근 3개월 리뷰로 판단합니다.

    이전 달에 같은 날짜가 존재하지 않으면
    해당 월의 마지막 날짜로 자동 보정합니다.
    """

    if review_date is None:
        return False

    # 리뷰 날짜 형식 통일
    if isinstance(review_date, datetime):
        target_date = review_date.date()

    elif isinstance(review_date, date):
        target_date = review_date

    else:
        value = str(review_date).strip()

        if not value:
            return False

        try:
            target_date = datetime.fromisoformat(value).date()

        except ValueError:
            try:
                target_date = datetime.strptime(
                    value[:10],
                    "%Y-%m-%d",
                ).date()

            except ValueError:
                return False

    today = date.today()

    # 오늘 기준 N개월 전의 연도와 월 계산
    total_months = (
        today.year * 12
        + today.month
        - 1
        - months
    )

    cutoff_year = total_months // 12
    cutoff_month = total_months % 12 + 1

    # 해당 월의 마지막 날짜
    last_day = calendar.monthrange(
        cutoff_year,
        cutoff_month,
    )[1]

    # 오늘 날짜가 해당 월의 마지막 날짜보다 크면 월말로 보정
    cutoff_day = min(today.day, last_day)

    cutoff_date = date(
        cutoff_year,
        cutoff_month,
        cutoff_day,
    )

    return target_date >= cutoff_date


def select_recent_first_sentences(
    sentence_rows: list[dict],
    limit: int,
) -> list[str]:
    """
    최근 3개월 문장을 최신순으로 우선 선택하고,
    limit을 채우지 못하면 3개월 이전 문장으로 보충합니다.

    sentence_rows는 SQL에서 이미 review_date DESC, aspect_sentence_id DESC로
    정렬된 순서를 그대로 유지합니다.
    """

    recent_sentences = []
    older_sentences = []
    seen = set()

    for item in sentence_rows:
        sentence = str(item.get("sentence") or "").strip()
        if not sentence or sentence in seen:
            continue

        seen.add(sentence)

        if is_within_recent_months(item.get("review_date"), months=3):
            recent_sentences.append(sentence)
        else:
            older_sentences.append(sentence)

    selected = recent_sentences[:limit]

    remaining_count = limit - len(selected)
    if remaining_count > 0:
        selected.extend(older_sentences[:remaining_count])

    return selected


# ============================================================
# 6. 상품 데이터를 속성별로 묶기
# ============================================================

def group_rows_by_attribute(
    rows: list[dict],
    all_attributes: list[dict],
) -> dict:
    """
    분석 카테고리에 설정된 전체 속성을 먼저 생성한 뒤,
    실제 문장단위 감성분석 결과를 속성별로 묶습니다.

    따라서 리뷰 문장이 없는 속성도 빈 목록 상태로 결과에 포함됩니다.
    """

    def empty_sentiment_data() -> dict:
        return {
            "positive": [],
            "negative": [],
            "neutral": [],
            "unknown": [],
        }

    grouped = {}

    # 1) 기준 속성 테이블의 전체 속성을 표시 순서대로 먼저 생성
    for attribute in all_attributes:
        key = (
            attribute["analysis_category_id"],
            attribute["display_name"],
        )
        grouped[key] = empty_sentiment_data()

    # 2) 실제 리뷰 문장을 해당 속성에 추가
    for row in rows:
        key = (
            row["analysis_category_id"],
            row["display_name"],
        )

        # 기준 속성 뷰에 없는 예외 속성도 유실되지 않도록 추가
        if key not in grouped:
            grouped[key] = empty_sentiment_data()

        sentence = str(
            row["separated_sentence"] or ""
        ).strip()

        if not sentence:
            continue

        sentiment = normalize_sentiment(
            row["sentiment_label"]
        )

        grouped[key][sentiment].append(
            {
                "sentence": sentence,
                "review_date": row.get("review_date"),
            }
        )

    return grouped


# ============================================================
# 6-1. 중복 문장 제거 및 기본값 처리
# ============================================================

def remove_duplicate_sentences(
    sentences: list[str],
) -> list[str]:
    """
    동일한 문장이 반복되면 한 번만 사용합니다.
    """

    return list(dict.fromkeys(sentences))


def value_or_default(
    value: Any,
    default_text: str,
) -> str:
    """
    None, 빈 문자열, 공백 문자열을 지정한 기본 문구로 바꿉니다.
    """

    if value is None:
        return default_text

    normalized = str(value).strip()
    return normalized if normalized else default_text


# ============================================================
# 7. JSON 응답 추출
# ============================================================

def parse_json_response(response_text: str) -> dict:
    """
    LLM 응답에서 JSON 객체를 추출합니다.
    """

    cleaned = clean_think_tags(response_text or "")
    cleaned = cleaned.strip()

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    )

    try:
        return json.loads(cleaned)

    except json.JSONDecodeError:
        # 응답 앞뒤에 설명이 붙었을 경우
        json_match = re.search(
            r"\{.*\}",
            cleaned,
            flags=re.DOTALL,
        )

        if json_match:
            try:
                return json.loads(
                    json_match.group()
                )
            except json.JSONDecodeError:
                pass

    raise ValueError(
        "LLM 응답을 JSON으로 변환하지 못했습니다.\n\n"
        f"[실제 응답]\n{cleaned}"
    )


# ============================================================
# 8. 속성별 프롬프트
# ============================================================

def build_attribute_prompt(
    product_info: dict,
    analysis_category_id: int,
    attribute_name: str,
    sentiment_data: dict,
) -> str:
    """
    속성 하나의 긍정·부정 문장을 전달하는 프롬프트입니다.
    """

    positive_sentences = select_recent_first_sentences(
        sentence_rows=sentiment_data["positive"],
        limit=MAX_POSITIVE_SENTENCES,
    )

    negative_sentences = select_recent_first_sentences(
        sentence_rows=sentiment_data["negative"],
        limit=MAX_NEGATIVE_SENTENCES,
    )

    positive_text = "\n".join(
        f"- {sentence}"
        for sentence in positive_sentences
    )

    negative_text = "\n".join(
        f"- {sentence}"
        for sentence in negative_sentences
    )

    if not positive_text:
        positive_text = "- 해당 문장 없음"

    if not negative_text:
        negative_text = "- 해당 문장 없음"

    return f"""
당신은 화장품 VOC 분석 전문가입니다.

아래 자료는 상품 리뷰 전체가 아니라,
이미 속성별로 분리되고 문장단위 감성분석까지 완료된 결과입니다.

[상품 정보]
상품명: {product_info["product_name"]}
브랜드명: {product_info["brand_name"]}
상품 카테고리: {product_info["category"]}

[분석 속성]
분석 카테고리 ID: {analysis_category_id}
분석 속성명: {attribute_name}

[긍정으로 분류된 속성 문장]
{positive_text}

[부정으로 분류된 속성 문장]
{negative_text}

다음 규칙에 따라 분석하세요.

작성 규칙

1. 제공된 분석 결과만 근거로 작성하고, 없는 내용은 추측하지 마세요.

2. 긍정 요약과 부정 요약은 각각 반드시 2문장으로 작성하세요.
- 첫 번째 문장은 가장 대표적인 핵심 의견을 작성하세요.
- 두 번째 문장은 그다음으로 많이 언급된 핵심 의견을 작성하세요.

3. 하나의 문장에는 하나의 핵심 의견만 작성하세요.
여러 의견을 쉼표나 "및", "과 함께", "또는", "~거나" 등으로 묶어 나열하지 마세요.

4. 하나의 요약에는 핵심 의견을 최대 2개까지만 포함하세요.
계절, 사용 시간, 사용 부위, 레이어링 등 세부 사례는 반복적으로 언급된 경우에만 포함하세요.

5. "사용자는", "소비자는", "리뷰어는"과 같은 주어를 사용하지 마세요.

6. 모든 문장은 VOC 분석 보고서 문체로 작성하세요.
문장 종결은 반드시 아래 표현 중 하나를 사용하세요.
- "~의견이 많았습니다."
- "~의견이 있었습니다."
- "~반응이 있었습니다."
- "~반응도 있었습니다."

7. 제품을 추천하거나 효과를 단정하는 표현은 사용하지 마세요.
다음 표현은 사용하지 마세요.
- 안심하고 사용할 수 있습니다.
- 추천합니다.
- 효과적입니다.
- 우수합니다.
- 예방합니다.
- 도움이 됩니다.
- 제공합니다.
- 충족시킵니다.
- 부담 없이 사용할 수 있습니다.

8. "확인되었습니다", "평가받았습니다", "보고되었습니다", "입증되었습니다" 등 논문체·기사체 표현은 사용하지 마세요.

9. 리뷰 문장을 그대로 인용하거나 구어체 표현("솔직히", "진짜", "완전", "너무" 등)은 사용하지 말고, 의미만 객관적으로 자연스럽게 요약하세요.

10. 같은 의미를 반복하지 말고 핵심 의견만 간결하게 작성하세요.
11.리뷰에 포함된 줄임말이나 비표준 표현(예: 화잘먹, 인생템 등)은
의미를 자연스러운 한국어로 바꾸어 작성하세요.

12. 최종 작성 후 전체 문장을 다시 검토하여 자연스러운 한국어 보고서 문체로 다듬으세요.
- 의미를 변경하거나 새로운 내용을 추가하지 마세요.
- 제공된 분석 결과만 근거로 작성하세요.
- 문법이나 어색한 표현만 수정하세요.
- 같은 표현이나 종결어미가 반복되면 의미를 유지한 채 자연스럽게 조정하세요.
13. JSON 객체만 반환하세요.

좋은 예시
긍정 요약
피부 진정 효과를 느꼈다는 의견이 많았습니다.
트러블이 줄었다는 반응도 있었습니다.

부정 요약
피부가 건조해졌다는 의견이 있었습니다.
일부에서는 자극을 느꼈다는 반응도 있었습니다.


반환 형식:

{{
  "positive_summary": "첫 번째 긍정 요약 문장입니다. 두 번째 긍정 요약 문장입니다.",
  "negative_summary": "첫 번째 부정 요약 문장입니다. 두 번째 부정 요약 문장입니다."
}}
""".strip()


# ============================================================
# 9. 속성별 LLM 요약
# ============================================================

def build_fallback_summary(
    sentences: list[Any],
) -> str | None:
    """
    LLM이 JSON으로 응답하지 못했을 때 사용할 간단한 fallback 요약입니다.
    """

    normalized_sentences = []

    for item in sentences:
        if isinstance(item, dict):
            sentence = str(item.get("sentence") or "").strip()
        else:
            sentence = str(item or "").strip()

        if sentence:
            normalized_sentences.append(sentence)

    unique_sentences = remove_duplicate_sentences(normalized_sentences)

    if not unique_sentences:
        return None

    selected = unique_sentences[:2]
    return " ".join(selected)


def generate_attribute_report(
    client,
    model_name: str,
    product_info: dict,
    analysis_category_id: int,
    attribute_name: str,
    sentiment_data: dict,
) -> dict:
    """
    속성 하나의 positive_summary와 negative_summary를 생성합니다.
    """

    # 긍정·부정 문장 개수를 먼저 계산
    positive_count = len(sentiment_data["positive"])
    negative_count = len(sentiment_data["negative"])

    # 해당 속성에 긍정·부정 문장이 모두 없으면 LLM을 호출하지 않고
    # 명시적인 기본 문구를 바로 저장합니다.
    if positive_count == 0 and negative_count == 0:
        return {
            "analysis_category_id": analysis_category_id,
            "display_name": attribute_name,
            "positive_summary": NO_ATTRIBUTE_POSITIVE,
            "negative_summary": NO_ATTRIBUTE_NEGATIVE,
            "positive_count": 0,
            "negative_count": 0,
        }

    prompt = build_attribute_prompt(
        product_info=product_info,
        analysis_category_id=analysis_category_id,
        attribute_name=attribute_name,
        sentiment_data=sentiment_data,
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        NO_THINK_SYSTEM_PROMPT
                        + "\n반드시 유효한 JSON 객체만 반환하세요."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=500,
        )

        raw_text = response.choices[0].message.content or ""
        result = parse_json_response(raw_text)

    except Exception:
        # LLM 호출 또는 JSON 파싱이 실패해도 해당 속성을 누락하지 않습니다.
        result = {
            "positive_summary": build_fallback_summary(
                sentiment_data["positive"]
            ),
            "negative_summary": build_fallback_summary(
                sentiment_data["negative"]
            ),
        }

    # 문장이 0개인 경우 LLM 결과와 관계없이 강제로 변경
    if positive_count == 0:
        result["positive_summary"] = NO_ATTRIBUTE_POSITIVE

    if negative_count == 0:
        result["negative_summary"] = NO_ATTRIBUTE_NEGATIVE

    return {
        "analysis_category_id": analysis_category_id,
        "display_name": attribute_name,
        "positive_summary": value_or_default(
            result.get("positive_summary"),
            NO_ATTRIBUTE_POSITIVE,
        ),
        "negative_summary": value_or_default(
            result.get("negative_summary"),
            NO_ATTRIBUTE_NEGATIVE,
        ),
        "positive_count": positive_count,
        "negative_count": negative_count,
    }
# ============================================================
# 10. 상품 전체 요약 프롬프트
# ============================================================

def build_overall_prompt(
    product_info: dict,
    attribute_reports: list[dict],
) -> str:
    """
    앞에서 생성한 속성별 요약을 이용해 상품 전체 보고서를 만듭니다.
    """

    report_blocks = []

    for report in attribute_reports:
        positive_summary = (
            report["positive_summary"]
            if report["positive_summary"]
            else NO_ATTRIBUTE_POSITIVE
        )

        negative_summary = (
            report["negative_summary"]
            if report["negative_summary"]
            else NO_ATTRIBUTE_NEGATIVE
        )

        block = f"""
        [속성: {report["display_name"]}]
        긍정 요약: {positive_summary}
        부정 요약: {negative_summary}
        """.strip()

        report_blocks.append(block)

    attribute_report_text = "\n\n".join(
        report_blocks
    )

    return f"""
당신은 화장품 브랜드를 위한 VOC 분석 전문가입니다.

아래 내용은 상품별 리뷰 원문이 아니라,
속성별 문장단위 감성분석 결과를 먼저 요약한 자료입니다.

[상품 정보]
상품명: {product_info["product_name"]}
브랜드명: {product_info["brand_name"]}
카테고리: {product_info["category"]}

[속성별 분석 결과]
{attribute_report_text}

위 속성별 분석 결과만 사용하여 상품 전체 보고서를 작성하세요.

작성 항목:

1. keep_summary
소비자 반응이 긍정적이므로 현재 상태를 유지하거나 강화할 만한 요소를 작성하세요.

2. improvement_summary
부정 의견을 바탕으로 우선 개선해야 할 요소를 작성하세요.

3. overall_summary
상품의 전반적인 강점과 약점을 종합적으로 평가하세요.

작성 규칙
1. 제공된 속성별 분석 결과만 근거로 작성하고, 없는 내용은 추측하지 마세요.
2. keep_summary, improvement_summary, overall_summary는 각각 반드시 2문장으로 작성하세요.
- 첫 번째 문장은 가장 대표적인 핵심 의견을 작성하세요.
- 두 번째 문장은 그 다음으로 많이 언급된 핵심 의견을 작성하세요.
3. 하나의 문장에는 하나의 핵심 의견만 작성하고, 여러 의견을 쉼표나 "및", "과 함께", "또는", "~거나" 등으로 묶어 나열하지 마세요.
4. 하나의 summary에는 핵심 의견을 최대 2개까지만 포함하세요.
세부 사용 상황(계절, 사용 시간, 사용 부위, 레이어링 등)은 포함하지 마세요.
5. "사용자는", "소비자는", "리뷰어는"과 같은 주어를 사용하지 마세요.
6. 최종 보고서에서는 속성명(예: 기능/효과, 보습력/수분감, 자극성, 향, 흡수력 등)을 직접 작성하지 말고 자연스럽게 종합하세요.
7. keep_summary는 소비자가 만족한 핵심 장점을 자연스럽게 요약하세요.
8. improvement_summary는 반복적으로 언급된 핵심 불편사항만 요약하세요.
9. overall_summary는 장점과 개선점을 균형 있게 종합하세요.
긍정 또는 부정을 단정하지 마세요.
10. 모든 문장은 자연스러운 VOC 분석 보고서 문체로 작성하세요.
의견과 반응을 요약하는 과거형 문장으로 작성하고, 광고 문구나 단정적인 표현은 사용하지 마세요.
11. 제품을 추천하거나 효과를 단정하는 표현은 사용하지 마세요.
다음 표현은 사용하지 마세요.
- 안심하고 사용할 수 있습니다.
- 추천합니다.
- 효과적입니다.
- 우수합니다.
- 예방합니다.
- 도움이 됩니다.
- 제공합니다.
- 충족시킵니다.
- 부담 없이 사용할 수 있습니다.
12. "확인되었습니다", "평가받았습니다", "보고되었습니다", "입증되었습니다"와 같은 논문체·기사체 표현은 사용하지 마세요.
13. 리뷰 문장을 그대로 인용하거나 구어체 표현("솔직히", "진짜", "완전", "너무" 등)은 사용하지 말고, 객관적인 분석 문장으로 자연스럽게 작성하세요.
14. 같은 의미를 반복하지 말고 핵심 의견만 간결하게 작성하세요.
15. 최종 작성 후 전체 문장을 다시 검토하여 자연스러운 한국어 보고서 문체로 다듬으세요.
- 의미를 변경하거나 새로운 내용을 추가하지 마세요.
- 제공된 분석 결과만 근거로 작성하세요.
- 문법이나 어색한 표현만 수정하세요.
- 같은 표현이나 종결어미가 반복되면 의미를 유지한 채 자연스럽게 조정하세요.
16. JSON 객체만 반환하세요.

좋은 예시
[keep_summary]
피부 진정과 수분감에 대한 만족도가 높았습니다.
가벼운 사용감과 빠른 흡수력에도 긍정적인 반응이 있었습니다.

[improvement_summary]
일부에서는 피부 자극을 느꼈다는 의견이 있었습니다.
향의 강도에 대한 호불호도 나타났습니다.

[overall_summary]
피부 진정과 사용감에는 긍정적인 의견이 많았습니다.
피부 타입과 향에 따라 만족도가 달라진다는 의견도 있었습니다.


반환 형식:

{{
  "keep_summary": "첫 번째 유지 권장 문장입니다. 두 번째 유지 권장 문장입니다.",
  "improvement_summary": "첫 번째 개선 우선 문장입니다. 두 번째 개선 우선 문장입니다.",
  "overall_summary": "첫 번째 종합 평가 문장입니다. 두 번째 종합 평가 문장입니다."
}}
""".strip()


# ============================================================
# 11. 상품 전체 LLM 요약
# ============================================================

def generate_overall_report(
    client,
    model_name: str,
    product_info: dict,
    attribute_reports: list[dict],
) -> dict:
    """
    속성별 요약을 종합하여 상품 전체 보고서를 생성합니다.

    긍정·부정 의견이 모두 없으면 LLM을 호출하지 않습니다.
    한쪽 감성만 없으면 해당 항목에는 안내 문구를 강제로 저장합니다.
    """

    total_positive_count = sum(
        int(report.get("positive_count") or 0)
        for report in attribute_reports
    )
    total_negative_count = sum(
        int(report.get("negative_count") or 0)
        for report in attribute_reports
    )

    has_positive = total_positive_count > 0
    has_negative = total_negative_count > 0

    # 상품 전체에 긍정·부정 분석 문장이 하나도 없으면
    # 불필요한 LLM 호출 없이 명시적인 안내 문구를 저장합니다.
    if not has_positive and not has_negative:
        return {
            "keep_summary": NO_OVERALL_KEEP,
            "improvement_summary": NO_OVERALL_IMPROVEMENT,
            "overall_summary": NO_OVERALL_SUMMARY,
        }

    prompt = build_overall_prompt(
        product_info=product_info,
        attribute_reports=attribute_reports,
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        NO_THINK_SYSTEM_PROMPT
                        + "\n반드시 유효한 JSON 객체만 반환하세요."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=700,
        )

        raw_text = response.choices[0].message.content or ""
        result = parse_json_response(raw_text)

    except Exception:
        # 호출 또는 JSON 파싱이 실패해도 NULL이나 빈 문자열을 저장하지 않습니다.
        result = {}

    keep_summary = value_or_default(
        result.get("keep_summary"),
        NO_OVERALL_KEEP,
    )
    improvement_summary = value_or_default(
        result.get("improvement_summary"),
        NO_OVERALL_IMPROVEMENT,
    )
    overall_summary = value_or_default(
        result.get("overall_summary"),
        NO_OVERALL_SUMMARY,
    )

    # 실제 긍정/부정 문장이 없는 항목은 LLM 응답과 관계없이 고정 문구로 처리합니다.
    if not has_positive:
        keep_summary = NO_OVERALL_KEEP

    if not has_negative:
        improvement_summary = NO_OVERALL_IMPROVEMENT

    return {
        "keep_summary": keep_summary,
        "improvement_summary": improvement_summary,
        "overall_summary": overall_summary,
    }


# ============================================================
# 12. 상품 하나 전체 분석
# ============================================================
def analyze_one_product(
    product_id: int,
) -> dict | None:
    """
    상품 하나의 모든 속성과 최종 종합보고서를 생성합니다.
    """

    connection = get_db_connection()

    try:
        # 문장단위 감성분석 결과는 0건일 수 있습니다.
        rows = get_product_analysis_rows(
            connection=connection,
            product_id=product_id,
        )

        # 상품 정보는 분석 뷰의 첫 행에 의존하지 않고 상품 테이블에서 별도로 조회합니다.
        product_info = get_product_base_info(
            connection=connection,
            product_id=product_id,
        )

        if product_info is None:
            print(f"product_id={product_id}의 상품 정보를 찾을 수 없습니다.")
            return None

        # 실제 문장이 있으면 문장에 포함된 분석 카테고리를 우선 사용하고,
        # 문장이 0건이면 상품 카테고리 연결을 기준으로 분석 카테고리를 조회합니다.
        analysis_category_ids = list(dict.fromkeys(
            row["analysis_category_id"]
            for row in rows
            if row.get("analysis_category_id") is not None
        ))

        if not analysis_category_ids:
            analysis_category_ids = get_product_analysis_category_ids(
                connection=connection,
                product_id=product_id,
            )

        all_attributes = get_analysis_category_attributes(
            connection=connection,
            analysis_category_ids=analysis_category_ids,
        )

    finally:
        connection.close()

    if not rows:
        print(
            f"product_id={product_id}에 대한 "
            "속성별 문장단위 감성분석 결과가 없습니다. "
            "전체 속성에 기본 안내 문구를 저장합니다."
        )

    grouped_data = group_rows_by_attribute(
        rows=rows,
        all_attributes=all_attributes,
    )

    if not grouped_data:
        print(
            f"product_id={product_id}에 연결된 분석 속성이 없습니다. "
            "속성별 보고서를 만들 수 없어 저장을 건너뜁니다."
        )
        return None

    config = load_sample_config()
    model_name = config["default_model"]

    # 실제 감성분석 문장이 하나라도 있을 때만 LLM 클라이언트를 생성합니다.
    # 모든 문장이 0건이면 외부 LLM을 호출하지 않고 고정 안내 문구만 저장합니다.
    has_analyzable_sentences = any(
        row.get("sentiment_label") is not None
        and str(row.get("separated_sentence") or "").strip()
        for row in rows
    )
    client = get_openai_client() if has_analyzable_sentences else None

    print("=" * 80)
    print("[상품 LLM 분석 시작]")
    print(f"상품 ID   : {product_info['product_id']}")
    print(f"상품명    : {product_info['product_name']}")
    print(f"브랜드명  : {product_info['brand_name']}")
    print(f"카테고리  : {product_info['category']}")
    print(f"사용 모델 : {model_name}")
    print(f"전체 문장 : {len(rows)}개")
    print(f"전체 속성 : {len(grouped_data)}개")
    print("=" * 80)

    attribute_reports = []

    for index, (
        attribute_key,
        sentiment_data,
    ) in enumerate(
        grouped_data.items(),
        start=1,
    ):
        analysis_category_id = attribute_key[0]
        attribute_name = attribute_key[1]

        print()
        has_review_sentences = any(
            sentiment_data[label]
            for label in ("positive", "negative", "neutral", "unknown")
        )

        print(
            f"[{index}/{len(grouped_data)}] "
            f"{attribute_name} "
            + (
                "분석 중..."
                if has_review_sentences
                else "- 관련 문장 없음"
            )
        )

        try:
            report = generate_attribute_report(
                client=client,
                model_name=model_name,
                product_info=product_info,
                analysis_category_id=analysis_category_id,
                attribute_name=attribute_name,
                sentiment_data=sentiment_data,
            )

            attribute_reports.append(report)
            print("  ✓ 완료")

        except Exception as error:
            # 예상하지 못한 오류가 발생해도 해당 속성 행은 반드시 저장합니다.
            print(f"  ✗ 속성 분석 실패, 기본 문구로 대체: {error}")
            attribute_reports.append(
                {
                    "analysis_category_id": analysis_category_id,
                    "display_name": attribute_name,
                    "positive_summary": value_or_default(
                        build_fallback_summary(sentiment_data["positive"]),
                        NO_ATTRIBUTE_POSITIVE,
                    ),
                    "negative_summary": value_or_default(
                        build_fallback_summary(sentiment_data["negative"]),
                        NO_ATTRIBUTE_NEGATIVE,
                    ),
                    "positive_count": len(sentiment_data["positive"]),
                    "negative_count": len(sentiment_data["negative"]),
                }
            )

    if not attribute_reports:
        print("생성된 속성별 보고서가 없어 저장을 건너뜁니다.")
        return None

    print()
    print("[상품 전체 종합보고서 생성 중...]")

    overall_report = generate_overall_report(
        client=client,
        model_name=model_name,
        product_info=product_info,
        attribute_reports=attribute_reports,
    )

    return {
        "product_info": product_info,
        "attribute_reports": attribute_reports,
        "overall_report": overall_report,
    }




# ============================================================
# 13. LLM 보고서 DB 저장
# ============================================================

def save_llm_reports(
    connection,
    result: dict,
) -> int:
    """
    상품 종합보고서와 속성별 보고서를 하나의 트랜잭션으로 저장합니다.

    반환값:
        새로 생성된 llm_product_report_id
    """

    product_info = result["product_info"]
    overall_report = result["overall_report"]
    attribute_reports = result["attribute_reports"]

    product_id = product_info["product_id"]

    # DB에는 NULL이나 빈 문자열 대신 명시적인 안내 문구가 저장되도록 보정합니다.
    overall_report = {
        "keep_summary": value_or_default(
            overall_report.get("keep_summary"),
            NO_OVERALL_KEEP,
        ),
        "improvement_summary": value_or_default(
            overall_report.get("improvement_summary"),
            NO_OVERALL_IMPROVEMENT,
        ),
        "overall_summary": value_or_default(
            overall_report.get("overall_summary"),
            NO_OVERALL_SUMMARY,
        ),
    }

    for report in attribute_reports:
        report["positive_summary"] = value_or_default(
            report.get("positive_summary"),
            NO_ATTRIBUTE_POSITIVE,
        )
        report["negative_summary"] = value_or_default(
            report.get("negative_summary"),
            NO_ATTRIBUTE_NEGATIVE,
        )

    insert_overall_sql = """
        INSERT INTO llm_product_reports
        (
            product_id,
            keep_summary,
            improvement_summary,
            overall_summary
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s
        )
    """

    insert_attribute_sql = """
        INSERT INTO llm_product_attribute_reports
        (
            llm_product_report_id,
            product_id,
            analysis_category_id,
            display_name,
            positive_summary,
            negative_summary
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
    """

    with connection.cursor() as cursor:
        # 1) 상품 종합보고서 저장
        cursor.execute(
            insert_overall_sql,
            (
                product_id,
                overall_report.get("keep_summary"),
                overall_report.get("improvement_summary"),
                overall_report.get("overall_summary"),
            ),
        )

        # 방금 INSERT된 AUTO_INCREMENT PK
        llm_product_report_id = cursor.lastrowid

        # 2) 동일 보고서 ID를 참조하도록 속성별 보고서 저장
        attribute_values = [
            (
                llm_product_report_id,
                product_id,
                report["analysis_category_id"],
                report["display_name"],
                report.get("positive_summary"),
                report.get("negative_summary"),
            )
            for report in attribute_reports
        ]

        if attribute_values:
            cursor.executemany(
                insert_attribute_sql,
                attribute_values,
            )

        # 3) 보고서 저장이 모두 성공한 상품만 분석 완료 시각 갱신
        cursor.execute(
            """
            UPDATE products
            SET llm_analyzed_at = NOW()
            WHERE product_id = %s
            """,
            (product_id,),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "products.llm_analyzed_at 갱신 실패: "
                f"product_id={product_id}, rowcount={cursor.rowcount}"
            )

    # 종합보고서, 속성별 보고서, 분석 완료 시각을 함께 확정
    connection.commit()

    return llm_product_report_id


# ============================================================
# 14. 결과 출력
# ============================================================

def print_final_result(
    result: dict,
) -> None:
    """
    상품 전체 분석 결과를 보기 좋게 출력합니다.
    """

    product_info = result["product_info"]
    attribute_reports = result["attribute_reports"]
    overall_report = result["overall_report"]

    print()
    print("=" * 90)
    print("[상품별 속성 분석 결과]")
    print("=" * 90)

    for index, report in enumerate(
        attribute_reports,
        start=1,
    ):
        print()
        print(
            f"{index}. "
            f"{report['display_name']}"
        )
        print(
            f"   긍정 요약: "
            f"{report['positive_summary']}"
        )
        print(
            f"   부정 요약: "
            f"{report['negative_summary']}"
        )

    print()
    print("=" * 90)
    print("[상품 전체 종합보고서]")
    print("=" * 90)
    print(f"상품명: {product_info['product_name']}")

    print()
    print("[유지 권장 사항]")
    print(overall_report["keep_summary"])

    print()
    print("[개선 우선사항]")
    print(overall_report["improvement_summary"])

    print()
    print("[상품 전체 종합 평가]")
    print(overall_report["overall_summary"])
    print("=" * 90)


# ============================================================
# 15. 실행
# ============================================================

def main():
    connection = get_db_connection()

    try:
        product_ids = get_target_product_ids(
            connection=connection,
            limit=PRODUCT_LIMIT,
        )
    finally:
        connection.close()

    if not product_ids:
        print("분석할 상품이 없습니다.")
        return

    total_count = len(product_ids)
    success_count = 0
    skipped_count = 0
    failed_count = 0
    failed_products = []

    print("=" * 90)
    print("[전체 상품 LLM 분석 시작]")
    print(f"분석 대상 상품 수: {total_count}개")
    print("분석 기준: 오늘 아직 성공하지 않은 상품(문장 0건 포함)")
    print("=" * 90)

    for product_index, product_id in enumerate(
        product_ids,
        start=1,
    ):
        print()
        print("#" * 90)
        print(
            f"[전체 진행률 {product_index}/{total_count}] "
            f"product_id={product_id}"
        )
        print("#" * 90)

        try:
            result = analyze_one_product(product_id=product_id)

            if result is None:
                skipped_count += 1
                print("분석 결과가 없어 건너뜁니다.")
                continue

            print_final_result(result)

            save_connection = get_db_connection()

            try:
                llm_product_report_id = save_llm_reports(
                    connection=save_connection,
                    result=result,
                )

                success_count += 1

                print()
                print("=" * 90)
                print("[LLM 분석 보고서 DB 저장 완료]")
                print(
                    f"llm_product_report_id: "
                    f"{llm_product_report_id}"
                )
                print(
                    f"속성별 보고서 저장 수: "
                    f"{len(result['attribute_reports'])}개"
                )
                print("products.llm_analyzed_at 갱신 완료")
                print("=" * 90)

            except Exception:
                save_connection.rollback()
                raise

            finally:
                save_connection.close()

        except KeyboardInterrupt:
            print()
            print("사용자 중단으로 전체 분석을 종료합니다.")
            break

        except Exception as error:
            failed_count += 1
            failed_products.append(
                {
                    "product_id": product_id,
                    "error": str(error),
                }
            )

            print()
            print("=" * 90)
            print("[상품 분석 또는 저장 실패]")
            print(f"product_id: {product_id}")
            print(f"오류 내용: {error}")
            print("다음 상품 분석을 계속합니다.")
            print("=" * 90)

    print()
    print("=" * 90)
    print("[전체 상품 LLM 분석 종료]")
    print(f"전체 대상: {total_count}개")
    print(f"성공: {success_count}개")
    print(f"건너뜀: {skipped_count}개")
    print(f"실패: {failed_count}개")

    if failed_products:
        print()
        print("[실패 상품 목록]")
        for item in failed_products:
            print(
                f"- product_id={item['product_id']}: "
                f"{item['error']}"
            )

    print("=" * 90)


if __name__ == "__main__":
    main()