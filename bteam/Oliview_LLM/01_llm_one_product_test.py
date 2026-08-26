import json
import os
import re
from collections import defaultdict
from typing import Any

import pymysql

from common import (
    clean_think_tags,
    get_openai_client,
    load_sample_config,
    NO_THINK_SYSTEM_PROMPT,
)


# ============================================================
# 1. 테스트 설정
# ============================================================

# 실제 분석할 상품 ID로 변경하세요.
TEST_PRODUCT_ID = 1

# 속성 하나에서 LLM에 전달할 최대 문장 수
# 문장이 너무 많으면 모델의 입력 길이를 초과할 수 있어서 제한합니다.
MAX_POSITIVE_SENTENCES = 20
MAX_NEGATIVE_SENTENCES = 20


# ============================================================
# 2. DB 연결
# ============================================================

def get_db_connection():
    """
    .env 파일의 MySQL 접속 정보를 사용합니다.
    """

    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", ""),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


# ============================================================
# 3. 상품 1개의 속성 문장 조회
# ============================================================

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
            model_attribute_name,
            aspect_sentence_id,
            separated_sentence,
            aspect_confidence,
            sentiment_label,
            sentiment_confidence,
            review_date
        FROM vw_llm_analysis_source
        WHERE product_id = %s
        ORDER BY
            analysis_category_id,
            model_attribute_name,
            review_date DESC,
            aspect_sentence_id DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, (product_id,))
        return cursor.fetchall()

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
# 5. 상품 데이터를 속성별로 묶기
# ============================================================

def group_rows_by_attribute(
    rows: list[dict],
) -> dict:
    """
    analysis_category_id와 model_attribute_name을 기준으로 묶습니다.
    """

    grouped = defaultdict(
        lambda: {
            "positive": [],
            "negative": [],
            "neutral": [],
            "unknown": [],
        }
    )

    for row in rows:
        key = (
            row["analysis_category_id"],
            row["model_attribute_name"],
        )

        sentence = str(
            row["separated_sentence"] or ""
        ).strip()

        if not sentence:
            continue

        sentiment = normalize_sentiment(
            row["sentiment_label"]
        )

        grouped[key][sentiment].append(sentence)

    return dict(grouped)


# ============================================================
# 6. 중복 문장 제거
# ============================================================

def remove_duplicate_sentences(
    sentences: list[str],
) -> list[str]:
    """
    동일한 문장이 반복되면 한 번만 사용합니다.
    """

    return list(dict.fromkeys(sentences))


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

    positive_sentences = remove_duplicate_sentences(
        sentiment_data["positive"]
    )[:MAX_POSITIVE_SENTENCES]

    negative_sentences = remove_duplicate_sentences(
        sentiment_data["negative"]
    )[:MAX_NEGATIVE_SENTENCES]

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
모델 속성명: {attribute_name}

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

12. JSON 객체만 반환하세요.

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
    sentences: list[str],
) -> str | None:
    """
    LLM이 JSON으로 응답하지 못했을 때 사용할 간단한 fallback 요약입니다.
    """

    unique_sentences = remove_duplicate_sentences(
        [str(sentence).strip() for sentence in sentences if str(sentence).strip()]
    )

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

    prompt = build_attribute_prompt(
        product_info=product_info,
        analysis_category_id=analysis_category_id,
        attribute_name=attribute_name,
        sentiment_data=sentiment_data,
    )

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

    try:
        result = parse_json_response(raw_text)

    except Exception:
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
        result["positive_summary"] = "관련 리뷰가 없습니다."

    if negative_count == 0:
        result["negative_summary"] = "관련 리뷰가 없습니다."

    return {
        "analysis_category_id": analysis_category_id,
        "model_attribute_name": attribute_name,
        "positive_summary": result.get("positive_summary"),
        "negative_summary": result.get("negative_summary"),
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
            else "긍정 의견 없음"
        )

        negative_summary = (
            report["negative_summary"]
            if report["negative_summary"]
            else "부정 의견 없음"
        )

        block = f"""
        [속성: {report["model_attribute_name"]}]
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
- 두 번째 문장은 그다음으로 많이 언급된 핵심 의견을 작성하세요.
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
15. JSON 객체만 반환하세요.

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
    """

    prompt = build_overall_prompt(
        product_info=product_info,
        attribute_reports=attribute_reports,
    )

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

    raw_text = (
        response.choices[0].message.content
        or ""
    )

    result = parse_json_response(raw_text)

    return {
        "keep_summary": result.get(
            "keep_summary"
        ),
        "improvement_summary": result.get(
            "improvement_summary"
        ),
        "overall_summary": result.get(
            "overall_summary"
        ),
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
        rows = get_product_analysis_rows(
            connection=connection,
            product_id=product_id,
        )

    finally:
        connection.close()

    if not rows:
        print(
            f"product_id={product_id}에 대한 "
            "속성별 문장단위 감성분석 결과가 없습니다."
        )
        return None

    first_row = rows[0]

    product_info = {
        "product_id": first_row["product_id"],
        "product_name": first_row["product_name"],
        "brand_name": first_row["brand_name"],
        "category": first_row["category"],
    }

    grouped_data = group_rows_by_attribute(rows)

    config = load_sample_config()
    client = get_openai_client()
    model_name = config["default_model"]

    print("=" * 80)
    print("[상품 LLM 분석 시작]")
    print(f"상품 ID   : {product_info['product_id']}")
    print(f"상품명    : {product_info['product_name']}")
    print(f"브랜드명  : {product_info['brand_name']}")
    print(f"카테고리  : {product_info['category']}")
    print(f"사용 모델 : {model_name}")
    print(f"전체 문장 : {len(rows)}개")
    print(f"속성 개수 : {len(grouped_data)}개")
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
        print(
            f"[{index}/{len(grouped_data)}] "
            f"{attribute_name} 분석 중..."
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
            print(f"  ✗ 속성 분석 실패: {error}")

    if not attribute_reports:
        print(
            "성공적으로 생성된 속성별 보고서가 없습니다."
        )
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
# 13. 결과 출력
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
            f"{report['model_attribute_name']}"
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
# 14. 실행
# ============================================================

def main():
    result = analyze_one_product(
        product_id=TEST_PRODUCT_ID,
    )

    if result is not None:
        print_final_result(result)


if __name__ == "__main__":
    main()