from __future__ import annotations

import argparse
import os
from itertools import groupby
from pathlib import Path

import pymysql
import torch
from dotenv import load_dotenv
from pymysql.cursors import DictCursor
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parent

# 한 번 실행할 때 처리할 리뷰 수
PROCESS_ALL = True
DEFAULT_LIMIT = 100
MAX_LENGTH = 64

TARGET_SENTENCE_SQL = """
SELECT pending_review.review_id, ras.aspect_sentence_id, ras.model_attribute_name, ras.separated_sentence 
FROM ( SELECT review_id 
        FROM reviews
        WHERE aspect_split_at IS NOT NULL
        AND sentiment_analyzed_at IS NULL
        ORDER BY review_id
        LIMIT %s) pending_review
LEFT JOIN review_aspect_sentences ras
ON ras.review_id = pending_review.review_id
ORDER BY pending_review.review_id, ras.aspect_sentence_id
"""

INSERT_SENTIMENT_SQL = """
INSERT INTO aspect_sentiment_results (
    aspect_sentence_id,
    sentiment_label,
    confidence_score
)
VALUES (%s, %s, %s)
ON DUPLICATE KEY UPDATE
    sentiment_label = VALUES(sentiment_label),
    confidence_score = VALUES(confidence_score)
"""

UPDATE_SENTIMENT_AT_SQL = """
UPDATE reviews
SET sentiment_analyzed_at = CURRENT_TIMESTAMP
WHERE review_id = %s
"""

def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f".env에 {name} 값이 필요합니다.")
    return value

def connect_database():
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT.parent / ".env")

    host = os.getenv("DB_HOST") or os.getenv("host") or "127.0.0.1"
    port = int(os.getenv("DB_PORT", 3306))
    user = os.getenv("DB_USER") or os.getenv("ID") or "GP"
    password = os.getenv("DB_PASSWORD") or os.getenv("PW") or "GP123!"
    db_name = os.getenv("DB_NAME") or os.getenv("DBName") or os.getenv("DB_NAME3") or "oliview_project"

    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=DictCursor,
    )

class SentimentAnalyzer:
    def __init__(self, model_dir: Path):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_dir
        ).to(self.device)
        self.model.eval()

    @torch.inference_mode()
    def predict_many(self, sentences: list[dict]) -> list[dict]:
        if not sentences:
            return []

        model_inputs = [
            f"[속성] {row['model_attribute_name']} "
            f"[문장] {row['separated_sentence']}"
            for row in sentences
        ]
        encoded = self.tokenizer(
            model_inputs,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_LENGTH,
            padding=True,
        )
        encoded = {
            name: value.to(self.device)
            for name, value in encoded.items()
        }

        probabilities = torch.softmax(self.model(**encoded).logits, dim=-1)
        predicted_ids = probabilities.argmax(dim=-1)

        results = []
        for row, row_probabilities, predicted_id in zip(
            sentences,
            probabilities,
            predicted_ids,
        ):
            label_id = int(predicted_id)
            results.append(
                {
                    "aspect_sentence_id": row["aspect_sentence_id"],
                    "sentiment_label": self.model.config.id2label[label_id],
                    "confidence_score": round(
                        float(row_probabilities[label_id]),
                        7,
                    ),
                }
            )

        return results


def fetch_pending_sentences(db, batch_size: int) -> list[dict]:
    cursor = db.cursor()
    try:
        cursor.execute(TARGET_SENTENCE_SQL, (batch_size,))
        return cursor.fetchall()
    finally:
        cursor.close()


def process_review(
    db,
    analyzer: SentimentAnalyzer,
    review_id: int,
    review_rows: list[dict],
    dry_run: bool,
) -> int:
    # LEFT JOIN 때문에 문장 없는 리뷰는 aspect_sentence_id가 NULL
    sentences = [
        row
        for row in review_rows
        if row["aspect_sentence_id"] is not None
    ]
    results = analyzer.predict_many(sentences)

    if dry_run:
        print("=" * 80)
        print(f"review_id: {review_id}")
        if not results:
            print("감성분석할 문장: 없음")
        for sentence, result in zip(sentences, results):
            print(
                f"- {sentence['model_attribute_name']} / "
                f"{sentence['separated_sentence']} / "
                f"{result['sentiment_label']} / "
                f"confidence={result['confidence_score']:.4f}"
            )
        return len(results)

    # 감성 결과와 리뷰 완료 시각을 한 번에 저장
    cursor = db.cursor()
    try:
        for result in results:
            cursor.execute(
                INSERT_SENTIMENT_SQL,
                (
                    result["aspect_sentence_id"],
                    result["sentiment_label"],
                    result["confidence_score"],
                ),
            )

        cursor.execute(UPDATE_SENTIMENT_AT_SQL, (review_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        cursor.close()

    return len(results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="속성별 분리 문장을 감성분석하여 DB에 저장"
    )
    parser.add_argument("--limit", type=int, help="한 배치에서 처리할 리뷰 수(기본값: DEFAULT_LIMIT)", )
    parser.add_argument("--all", action="store_true", help="미처리 리뷰가 없을 때까지 배치 반복", )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument( "--model-dir", type=Path, default=ROOT / "models" / "sentiment", )
    args = parser.parse_args()

    batch_size = args.limit if args.limit is not None else DEFAULT_LIMIT
    process_all = args.all or PROCESS_ALL

    if batch_size < 1:
        parser.error("--limit은 1 이상이어야 합니다.")
    if args.dry_run and process_all:
        parser.error("--dry-run과 --all은 함께 사용할 수 없습니다.")

    analyzer = SentimentAnalyzer(args.model_dir)
    db = connect_database()

    try:
        total_review_count = 0
        total_sentence_count = 0

        while True:
            rows = fetch_pending_sentences(db, batch_size)
            if not rows:
                print("감성분석할 미처리 리뷰가 없습니다.")
                break

            batch_review_count = len({row["review_id"] for row in rows})
            print(
                f"이번 배치 {batch_review_count}건 / "
                f"device={analyzer.device}"
            )

            for review_id, grouped_rows in groupby(rows, key=lambda row: row["review_id"], ):
                result_count = process_review(
                    db,
                    analyzer,
                    review_id,
                    list(grouped_rows),
                    args.dry_run,
                )
                total_review_count += 1
                total_sentence_count += result_count
                print( f"처리 완료: review_id={review_id}, "f"sentences={result_count}")

            if not process_all or args.dry_run:
                break

        print(f"전체 처리 완료: 리뷰 {total_review_count}건 / " f"문장 {total_sentence_count}건")
    finally:
        db.close()


if __name__ == "__main__":
    main()
