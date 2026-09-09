import hashlib
import json

from collections.abc import Iterator,Iterable

from datetime import date, datetime, time

from pilos.analysis.vectorizer import tokens_to_tfidf_text

MARKET_CLOSE_TIME = time(15, 30)

def create_daily_document_hash(
    *,
    stock_id: int,
    model_date: date,
    tokenizer_version: str,
    tfidf_text: str,
    comment_count: int,
    tokenized_comment_ids: list[int],
) -> str:
    """일별 모델 입력과 구성 댓글로 SHA-256 해시를 생성한다."""
    payload = {
        "stock_id": stock_id,
        "model_date": model_date.isoformat(),
        "tokenizer_version": tokenizer_version,
        "tfidf_text": tfidf_text,
        "comment_count": comment_count,
        "tokenized_comment_ids": tokenized_comment_ids,
    }

    serialized_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized_payload.encode("utf-8")
    ).hexdigest()

def create_daily_document_data(
    *,
    stock_id: int,
    model_date: date,
    tokenizer_version: str,
    records: list[dict],
) -> tuple[dict, list[dict]]:
    """하루치 토큰화 댓글을 일별 문서와 매핑 데이터로 변환한다."""
    if not records:
        raise ValueError(
            "일별 문서를 만들 토큰화 댓글이 없습니다."
        )

    daily_tokens = []
    mapping_records = []

    for sequence_number, record in enumerate(
        records,
        start=1,
    ):
        daily_tokens.extend(
            record["kiwi_tokens"]
        )

        mapping_records.append(
            {
                "tokenized_comment_id": (
                    record["tokenized_comment_id"]
                ),
                "sequence_number": sequence_number,
            }
        )

    tfidf_text = tokens_to_tfidf_text(
        daily_tokens
    )

    tokenized_comment_ids = [
        record["tokenized_comment_id"]
        for record in mapping_records
    ]

    comment_count = len(records)

    document_hash = create_daily_document_hash(
        stock_id=stock_id,
        model_date=model_date,
        tokenizer_version=tokenizer_version,
        tfidf_text=tfidf_text,
        comment_count=comment_count,
        tokenized_comment_ids=tokenized_comment_ids,
    )

    daily_document_data = {
        "stock_id": stock_id,
        "model_date": model_date,
        "tokenizer_version": tokenizer_version,
        "tfidf_text": tfidf_text,
        "comment_count": comment_count,
        "document_hash": document_hash,
    }

    return (
        daily_document_data,
        mapping_records,
    )



def iter_daily_documents(
    records: Iterable[dict],
) -> Iterator[dict]:
    """
    한 종목의 created_at 오름차순 토큰화 댓글 레코드를 받아,
    15:30 미만 댓글의 토큰을 날짜별 TF-IDF 입력 문서로 만들어
    하나씩 반환한다.
    """
    # 현재 집계 중인 종목·날짜와 누적값
    current_key: tuple[str, date] | None = None
    current_tokens: list[dict[str, str]] = []
    current_comment_count = 0
    # 입력 레코드의 시간순 정렬 검증값
    previous_created_at = None
    # 전달받은 댓글 레코드를 순서대로 순회
    for record in records:
        # 저장 경계에서 정규화된 댓글 생성시각만 분석 입력으로 허용한다
        created_at = record["created_at"]

        if not isinstance(created_at, datetime):
            raise ValueError(
                "created_at은 정규화된 datetime이어야 합니다."
            )
        # 이전 댓글보다 생성시각이 빠르면 정렬 오류로 처리
        if (
            previous_created_at is not None
            and created_at < previous_created_at
        ):
            raise ValueError(
            "댓글 레코드는 created_at 오름차순이어야 합니다."
        )

        previous_created_at = created_at
        # 장 마감 시각 이후 댓글은 일별 학습 문서에서 제외 (상수로 설정)
        if created_at.time() >= MARKET_CLOSE_TIME:
            continue
        # 종목·날짜별 집계 단위를 구성
        key = (
            record["stock_code"],
            created_at.date(),
        )
        # 첫 유효 댓글의 종목·날짜를 현재 집계 단위로 설정
        if current_key is None:
            current_key = key
        # 종목 또는 날짜가 변경되면 이전 집계 문서를 반환
        elif key != current_key:
            stock_code, model_date = current_key

            yield {
                "stock_code": stock_code,
                "model_date": model_date,
                "tfidf_text": tokens_to_tfidf_text(
                    current_tokens
                ),
                "comment_count": current_comment_count,
            }
            # 다음 요청에서 새 집계를 시작하도록 누적값 초기화
            current_key = key
            current_tokens = []
            current_comment_count = 0
        # 현재 댓글의 토큰을 현재 집계 문서에 추가
        current_tokens.extend(
            record["kiwi_tokens"]
        )
        # 현재 종목·날짜에 포함된 댓글 수 누적
        current_comment_count += 1
    # 다음 날짜가 없어 반환되지 않은 마지막 집계 문서를 반환
    if current_key is not None:
        stock_code, model_date = current_key

        yield {
            "stock_code": stock_code,
            "model_date": model_date,
            "tfidf_text": tokens_to_tfidf_text(
                current_tokens
            ),
            "comment_count": current_comment_count,
        }
