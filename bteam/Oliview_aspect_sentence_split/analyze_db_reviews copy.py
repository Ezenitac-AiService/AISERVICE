from __future__ import annotations

import argparse
import os
from itertools import groupby
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv

from predict import AspectSentenceSplitter


ROOT = Path(__file__).resolve().parent

# 실행 개수 설정
# True: 전체 처리 / False: DEFAULT_LIMIT만큼 처리
PROCESS_ALL = True
DEFAULT_LIMIT = 100

CATEGORY_ASPECT_SQL = """
SELECT
    analysis_category_id,
    model_attribute_name,
    display_name
FROM analysis_category_attributes
ORDER BY
    analysis_category_id,
    display_order
"""

TARGET_REVIEW_SQL = """
WITH RECURSIVE category_ancestors AS (
    SELECT
        pc.product_id,
        c.category_id,
        c.parent_category_id,
        c.category_name,
        0 AS depth
    FROM product_categories pc
    JOIN categories c
        ON c.category_id = pc.category_id

    UNION ALL

    SELECT
        ca.product_id,
        parent.category_id,
        parent.parent_category_id,
        parent.category_name,
        ca.depth + 1
    FROM category_ancestors ca
    JOIN categories parent
        ON parent.category_id = ca.parent_category_id
    WHERE ca.parent_category_id IS NOT NULL
      AND ca.depth < 20
),

target_categories AS (
    SELECT DISTINCT
        ca.product_id,
        ca.category_id AS analysis_category_id,
        ca.category_name AS analysis_category_name
    FROM category_ancestors ca
    JOIN (
        SELECT DISTINCT analysis_category_id
        FROM analysis_category_attributes
    ) configured_category
        ON configured_category.analysis_category_id = ca.category_id
),

candidate_reviews AS (
    SELECT
        r.review_id,
        r.product_id,
        rp.cleaned_content
    FROM reviews r
    JOIN review_preprocessing rp
        ON rp.review_id = r.review_id
    WHERE r.preprocessed_at IS NOT NULL
      AND r.aspect_split_at IS NULL
      AND rp.cleaned_content IS NOT NULL
      AND TRIM(rp.cleaned_content) <> ''
      AND EXISTS (
          SELECT 1
          FROM target_categories tc
          WHERE tc.product_id = r.product_id
      )
    ORDER BY r.review_id
    LIMIT %s
)

SELECT
    cr.review_id,
    cr.cleaned_content,
    tc.analysis_category_id,
    tc.analysis_category_name
FROM candidate_reviews cr
JOIN target_categories tc
    ON tc.product_id = cr.product_id
ORDER BY
    cr.review_id,
    tc.analysis_category_id
"""

DELETE_RESULT_SQL = """
DELETE FROM review_aspect_sentences
WHERE review_id = %s
  AND analysis_category_id = %s
"""

INSERT_RESULT_SQL = """
INSERT INTO review_aspect_sentences (
    review_id,
    analysis_category_id,
    model_attribute_name,
    sequence_no,
    separated_sentence,
    sentence_start,
    sentence_end,
    confidence_score
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""

# 문장 분리가 새로 진행되면 감성 완료 시각을 NULL로 변경
UPDATE_ASPECT_SPLIT_AT_SQL = """
UPDATE reviews
SET
    aspect_split_at = CURRENT_TIMESTAMP,
    sentiment_analyzed_at = NULL
WHERE review_id = %s
"""

def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f".env에 {name} 값이 필요합니다.")
    return value


def connect_database():
    load_dotenv(ROOT / ".env")
    return pymysql.connect(
        host=required_env("host"),
        user=required_env("ID"),
        password=required_env("PW"),
        db=required_env("DBName"),
        charset="utf8mb4",
        autocommit=False,
        cursorclass=DictCursor,
    )


def load_category_aspects(db) -> dict[int, dict[str, str]]:
    # DB 설정을 predict.py 형식으로 변환
    # {카테고리 ID: {화면 표시명: 모델 학습 속성명}}
    cursor = db.cursor()
    try:
        cursor.execute(CATEGORY_ASPECT_SQL)
        rows = cursor.fetchall()
    finally:
        cursor.close()

    category_aspects: dict[int, dict[str, str]] = {}
    for row in rows:
        category_id = row["analysis_category_id"]
        category_aspects.setdefault(category_id, {})[
            row["display_name"]
        ] = row["model_attribute_name"]

    return category_aspects


def print_dry_run(review: dict, extracted: list[dict]) -> None:
    print("=" * 80)
    print(f"review_id: {review['review_id']}")
    print(
        f"category: {review['analysis_category_name']} "
        f"({review['analysis_category_id']})"
    )
    print(f"cleaned_content: {review['cleaned_content']}")
    if not extracted:
        print("분리 결과: 없음")
        return
    for item in extracted:
        print(
            f"- 표시명={item['aspect']} / "
            f"모델 속성명={item['model_aspect']} / "
            f"구절={item['aspect_phrase']} "
            f"[{item['start']}:{item['end']}] "
            f"confidence={item['confidence']:.4f}"
        )


def save_category_results(cursor, review: dict, extracted: list[dict]) -> None:
    cursor.execute(
        DELETE_RESULT_SQL,
        (review["review_id"], review["analysis_category_id"]),
    )

    # 전처리 리뷰에서 구절이 나타난 위치순으로 번호 부여
    sorted_results = sorted(
        extracted,
        key=lambda item: (
            item["start"],
            item["end"],
            item["model_aspect"],
        ),
    )
    for sequence_no, item in enumerate(sorted_results, start=1):
        cursor.execute(
            INSERT_RESULT_SQL,
            (
                review["review_id"],
                review["analysis_category_id"],
                item["model_aspect"],
                sequence_no,
                item["aspect_phrase"],
                item["start"],
                item["end"],
                item["confidence"],
            ),
        )


def fetch_pending_reviews(db, batch_size: int) -> list[dict]:
    cursor = db.cursor()
    try:
        cursor.execute(TARGET_REVIEW_SQL, (batch_size,))
        return cursor.fetchall()
    finally:
        cursor.close()


def process_review(
    db,
    splitter: AspectSentenceSplitter,
    category_aspects: dict[int, dict[str, str]],
    review_categories: list[dict],
    dry_run: bool,
) -> int:
    # 같은 리뷰에 연결된 모든 카테고리를 먼저 분석
    analyzed_categories: list[tuple[dict, list[dict]]] = []
    total_results = 0

    for review in review_categories:
        category_id = review["analysis_category_id"]
        aspect_mapping = category_aspects.get(category_id)
        if not aspect_mapping:
            raise RuntimeError(
                "DB에 속성이 등록되지 않은 분석 카테고리입니다: "
                f"{review['analysis_category_name']}({category_id})"
            )

        extracted = splitter.extract(
            review["cleaned_content"],
            aspect_mapping=aspect_mapping,
        )
        analyzed_categories.append((review, extracted))
        total_results += len(extracted)

        if dry_run:
            print_dry_run(review, extracted)

    if dry_run:
        return total_results

    # 결과 저장과 완료 시각 기록을 한 번에 처리
    cursor = db.cursor()
    try:
        for review, extracted in analyzed_categories:
            save_category_results(cursor, review, extracted)

        cursor.execute(
            UPDATE_ASPECT_SPLIT_AT_SQL,
            (review_categories[0]["review_id"],),
        )

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        cursor.close()

    return total_results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="전처리 리뷰를 속성별로 분리하여 DB에 저장"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="한 배치에서 처리할 리뷰 수(기본값: DEFAULT_LIMIT)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="미처리 리뷰가 없을 때까지 배치 반복",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confidence-threshold", type=float, default=0.7)
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=ROOT / "models" / "aspect_span_extractor",
    )
    args = parser.parse_args()

    batch_size = args.limit if args.limit is not None else DEFAULT_LIMIT
    process_all = args.all or PROCESS_ALL

    if batch_size < 1:
        parser.error("--limit은 1 이상이어야 합니다.")
    if not 0 <= args.confidence_threshold <= 1:
        parser.error("--confidence-threshold는 0에서 1 사이여야 합니다.")
    if args.dry_run and process_all:
        parser.error("--dry-run과 --all은 함께 사용할 수 없습니다.")

    splitter = AspectSentenceSplitter(
        args.model_dir,
        confidence_threshold=args.confidence_threshold,
    )
    db = connect_database()
    category_aspects = load_category_aspects(db)
    if not category_aspects:
        db.close()
        raise RuntimeError("analysis_category_attributes 테이블에 속성 설정이 없습니다.")

    try:
        total_review_count = 0

        while True:
            reviews = fetch_pending_reviews(db, batch_size)
            if not reviews:
                print("문장 분리할 미처리 리뷰가 없습니다.")
                break

            batch_review_count = len({row["review_id"] for row in reviews})
            print(
                f"이번 배치 {batch_review_count}건 / "
                f"device={splitter.device} / "
                f"threshold={args.confidence_threshold}"
            )

            for review_id, grouped_rows in groupby(
                reviews,
                key=lambda row: row["review_id"],
            ):
                review_categories = list(grouped_rows)
                result_count = process_review(
                    db,
                    splitter,
                    category_aspects,
                    review_categories,
                    args.dry_run,
                )
                total_review_count += 1
                print(
                    f"처리 완료: review_id={review_id}, "
                    f"results={result_count}"
                )

            if not process_all or args.dry_run:
                break

        print(f"전체 처리 완료: 리뷰 {total_review_count}건")
    finally:
        db.close()


if __name__ == "__main__":
    main()
