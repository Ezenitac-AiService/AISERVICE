from collections.abc import Iterable
import re
import pandas as pd


# 반복형 소셜 표현을 감성 의미 토큰으로 변환하는 규칙
_SOCIAL_EXPRESSION_PATTERNS = (
    (r"ㅋ{2,}", "소셜웃음"),
    (r"[ㅠㅜ]{2,}", "소셜울음"),
    (r"ㅡ{2,}", "소셜짜증"),
    (r"ㄷ{2,}", "소셜놀람"),
)
# 결측값이 있으면 해당 행을 제거할 컬럼
_NON_NULL_COLUMNS = (
    "comment_id",
    "stock_code",
    "text",
    "created_at",
    "updated_at",
)
# 전처리를 시작하기 전에 존재해야 하는 입력 컬럼
_PREPROCESS_INPUT_COLUMNS = (
    "comment_id",
    "title",
    "message",
    "stock_code",
    "created_at",
    "updated_at",
    "raw_line_number"
)
# 원본 댓글 레코드에서 구성할 표준 컬럼과 순서
_COMMENT_COLUMNS = (
    "comment_id",
    "title",
    "message",
    "stock_code",
    "like_count",
    "parent_id",
    "created_at",
    "updated_at",
    "raw_line_number",
)
# Kiwi에서 UTF-16 경계 오류를 일으킬 수 있는 비-BMP 문자 전체
_NON_BMP_PATTERN = re.compile(
    r"[\U00010000-\U0010FFFF]+"
)

# BMP 영역에 존재하는 이모지·기호 및 이모지 조합 문자
_BMP_EMOJI_PATTERN = re.compile(
    r"["
    r"\u2300-\u23ff"
    r"\u2600-\u26ff"
    r"\u2700-\u27bf"
    r"\u2b00-\u2bff"
    r"\u200b-\u200d"  # ZERO WIDTH SPACE/NON-JOINER/JOINER
    r"\u2060"  # WORD JOINER
    r"\ufe0e"  # VARIATION SELECTOR-15
    r"\ufe0f"  # VARIATION SELECTOR-16
    r"\ufeff"  # ZERO WIDTH NO-BREAK SPACE
    r"\u20e3"  # COMBINING ENCLOSING KEYCAP
    r"]+"
)

# 일반 개행과 다르게 동작하는 유니코드 줄 구분자
_UNICODE_SEPARATOR_PATTERN = re.compile(
    r"[\u0085\u2028\u2029]+"
)

def _map_comment_record(record: dict) -> dict:
    """
    크롤링 응답의 중첩 필드에서 필요한 값을 꺼내
    프로젝트 표준 댓글 레코드로 변환한다.
    """
    # 중첩 객체가 없거나 None이면 하위 키를 조회할 수 있도록
    # 빈 딕셔너리를 사용한다
    message_data = record.get("message") or {}
    board_data = record.get("board") or {}
    statistic_data = record.get("statistic") or {}
    # 중첩 객체와 최상위 객체에서 필요한 값을 꺼내
    # snake_case 키를 사용하는 평탄한 댓글 레코드로 구성한다
    return {
        "comment_id": record.get("commentId"),
        "title": message_data.get("title"),
        "message": message_data.get("message"),
        "stock_code": board_data.get("stockCode"),
        "like_count": statistic_data.get("likeCount"),
        "parent_id": record.get("parentId"),
        "created_at": record.get("createdAt"),
        "updated_at": record.get("updatedAt"),
        "raw_line_number": record.get("raw_line_number"),
    }

def records_to_comment_dataframe(
    records: Iterable[dict],
) -> pd.DataFrame:
    """
    원본 댓글 레코드를 프로젝트 표준 컬럼의 DataFrame으로 변환한다.
    """
    # 원본 레코드를 하나씩 평탄한 표준 댓글 레코드로 변환하여 모은다
    rows = [ _map_comment_record(record) for record in records ]
    # 지정된 표준 컬럼 순서로 DataFrame을 구성한다
    df= pd.DataFrame(
        rows,
        columns=_COMMENT_COLUMNS,
    )

    return df


def _clean_text(value: object) -> str:
    """
    결측값을 빈 문자열로 바꾸고 연속된 공백을 하나로 정리한다.
    """
    if pd.isna(value):
        return ""

    return re.sub(r"\s+", " ", str(value)).strip()

def _remove_emojis(
    series: pd.Series,
) -> pd.Series:
    """
    Kiwi 토큰화에서 사용하지 않는 이모지와 비-BMP 문자를 제거한다.

    앞뒤 문자열이 합쳐지지 않도록 빈 문자열이 아닌 공백으로 치환한다.
    """
    cleaned = (
        series
        .astype("string")
        .str.replace(
            _NON_BMP_PATTERN,
            " ",
            regex=True,
        )
        .str.replace(
            _BMP_EMOJI_PATTERN,
            " ",
            regex=True,
        )
        .str.replace(
            _UNICODE_SEPARATOR_PATTERN,
            " ",
            regex=True,
        )
    )

    return (
        cleaned
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

def _merge_title_message(
    title: object,
    message: object,
) -> str:
    """
    제목과 메시지를 병합하되,
    동일하거나 한쪽이 다른 쪽의 시작 부분이면 중복을 제거한다.
    """
    title_text = _clean_text(title)
    message_text = _clean_text(message)

    # 제목이 비어 있으면 메시지만 사용한다
    if not title_text:
        return message_text

    # 메시지가 비어 있으면 제목만 사용한다
    if not message_text:
        return title_text

    # 제목과 메시지가 같으면 하나만 사용한다
    if title_text == message_text:
        return title_text

    # 메시지가 제목으로 시작하면 제목이 이미 포함된 메시지만 사용한다
    if message_text.startswith(title_text):
        return message_text

    # 제목이 메시지로 시작하면 메시지가 이미 포함된 제목만 사용한다
    if title_text.startswith(message_text):
        return title_text

    # 중복 관계가 없으면 제목과 메시지를 공백으로 연결한다
    return f"{title_text} {message_text}"


def _normalize_social_expressions(
    series: pd.Series,
) -> pd.Series:
    """
    반복형 소셜 표현을 감성 의미 토큰으로 정규화한다.
    """
    normalized = series.astype("string")

    for pattern, replacement in _SOCIAL_EXPRESSION_PATTERNS:
        normalized = normalized.str.replace(
            pattern,
            f" {replacement} ",
            regex=True,
        )

    return (
        normalized
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def preprocess_comment_text(
    text: str,
) -> str:
    """
    단일 댓글 문자열을 학습 데이터와 같은 규칙으로 전처리한다.
    """
    if not isinstance(text, str):
        raise ValueError(
            "댓글 원문은 문자열이어야 합니다."
        )

    # 일괄 전처리와 동일한 Series 기반 정규화 함수를 사용하여
    # 단일 댓글에서도 이모지와 소셜 표현 처리 기준을 유지한다
    text_series = pd.Series(
        [text],
        dtype="string",
    )
    text_series = _remove_emojis(
        text_series
    )
    text_series = _normalize_social_expressions(
        text_series
    )

    return str(text_series.iloc[0])



def preprocess_comments(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    프로젝트 규칙으로 정규화된 댓글 DataFrame을
    모델 처리 가능한 형태로 전처리한다.
    """
    # 전처리에 필요한 입력 컬럼이 모두 존재하는지 확인한다
    missing_columns = [
        column
        for column in _PREPROCESS_INPUT_COLUMNS
        if column not in dataframe.columns
    ]
    # 필요한 컬럼이 하나라도 없으면 누락된 컬럼명과 함께 예외를 발생시킨다
    if missing_columns:
        raise ValueError(
            f"전처리에 필요한 컬럼이 없습니다: {missing_columns}"
        )
    # 호출자가 전달한 원본 DataFrame을 변경하지 않도록 복사한다
    processed = dataframe.copy()
    # 각 행의 제목과 메시지를 병합하여 모델 입력용 text 컬럼을 만든다
    processed["text"] = [
        _merge_title_message(title, message)
        for title, message in zip(
            processed["title"],
            processed["message"],
        )
    ]
    # 토큰화에 사용하지 않는 이모지와 특수 문자를 제거한다
    processed["text"] = _remove_emojis(
        processed["text"]
    )

    # 반복형 소셜 표현을 감성 의미 토큰으로 변환한다
    processed["text"] = _normalize_social_expressions(
        processed["text"]
    )
    # 필수 값이 결측인 행을 제거한다
    processed = processed.dropna(
        subset=_NON_NULL_COLUMNS
    )
    # 제목과 메시지를 병합한 결과가 빈 문자열인 행을 제외한다
    processed = processed.loc[
        processed["text"].str.strip().ne("")
    ]
    # 같은 댓글 ID가 여러 번 수집되었다면 가장 최근 수정본만 남기고,
    # 최종 결과를 댓글 작성 시각과 댓글 ID 순으로 정렬한다
    processed = (
        processed
        .sort_values(
            ["updated_at", "created_at"],
            kind="stable",
        )
        .drop_duplicates(
            subset=["comment_id"],
            keep="last",
        )
        .sort_values(
            ["created_at", "comment_id"],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    return processed
