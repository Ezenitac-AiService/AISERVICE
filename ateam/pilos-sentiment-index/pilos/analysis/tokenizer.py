from collections.abc import Iterable

import pandas as pd
from kiwipiepy import Kiwi, Token

from pilos.analysis.tokenizer_settings import INCLUDE_FORMS, POS_TAGS, STOPWORDS, USER_DICTIONARY


def create_kiwi(
    *,
    user_dictionary: dict[str, str] | None = None,
    num_workers: int | None = None,
) -> Kiwi:
    """실행 옵션과 사용자 사전이 적용된 Kiwi 객체를 생성한다."""
    # 실행기가 지정한 worker 수를 적용하여 Kiwi 객체를 생성한다
    kiwi = Kiwi(
        num_workers=num_workers
    )

    # 사용자 사전이 있으면 단어와 품사 태그를 Kiwi 객체에 등록한다
    if user_dictionary:
        for word, tag in user_dictionary.items():
            kiwi.add_user_word(word, tag)

    return kiwi


def create_current_kiwi(*, num_workers: int | None = None) -> Kiwi:
    return create_kiwi(user_dictionary=USER_DICTIONARY, num_workers=num_workers)


def _is_janha_false_anh(
    *,
    text: str,
    token: Token,
) -> bool:
    """
    확인·강조 어미 '-잖-'이 '않/VX'으로 분석된 경우를 찾는다.
    """
    # 형태와 품사 중 하나라도 '않/VX'와 다르면 검사 대상이 아니다
    if token.form != "않" or token.tag != "VX":
        return False

    # Kiwi가 제공한 원문상의 시작 위치와 토큰 길이로
    # 확인할 문자열 범위를 계산한다
    start = token.start
    end = start + max(token.len, 1)

    # 시작 위치가 원문 범위를 벗어나면 표면형을 확인할 수 없다
    if start < 0 or start >= len(text):
        return False

    # 계산한 토큰 범위를 원문 길이 안에서 잘라 실제 표면형을 확인한다
    source_text = text[
        start:min(end, len(text))
    ]

    # 분석형은 '않/VX'이지만 원문이 '잖'이면
    # 실제 부정이 아닌 확인·강조 표현이다
    return source_text.startswith("잖")


def _select_comment_tokens(
    *,
    text: str,
    tokens: Iterable[Token],
    pos_tags: tuple[str, ...] | None = None,
    include_forms: set[str] | None = None,
    stopwords: set[str] | None = None,
) -> list[dict[str, str]]:
    """
    Kiwi 형태소 분석 결과에서
    프로젝트 선택 조건을 통과한 토큰을 반환한다.
    """
    # 선택 조건을 통과한 형태와 품사를 저장할 목록을 만든다
    result: list[dict[str, str]] = []

    # Kiwi의 형태소 분석 결과를 하나씩 확인한다
    for token in tokens:
        # 허용 품사가 아니면서 별도 포함 표현에도 없는 토큰은 제외한다
        if (
            pos_tags
            and not token.tag.startswith(pos_tags)
            and not (
                include_forms
                and token.form in include_forms
            )
        ):
            continue

        # 확인·강조 표현인 '-잖-'이 '않/VX'으로 분석된 토큰은 제외한다
        if _is_janha_false_anh(
            text=text,
            token=token,
        ):
            continue

        # 불용어로 지정된 형태는 제외한다
        if stopwords and token.form in stopwords:
            continue

        # 모든 선택 조건을 통과한 토큰의 형태와 품사를 결과에 추가한다
        result.append(
            {
                "form": token.form,
                "tag": token.tag,
            }
        )

    return result


def tokenize_comment(
    *,
    text: str,
    tokenizer: Kiwi,
    pos_tags: tuple[str, ...] | None = None,
    include_forms: set[str] | None = None,
    stopwords: set[str] | None = None,
) -> list[dict[str, str]]:
    """
    댓글 하나를 형태소 단위로 분석하고,
    프로젝트 선택 조건을 통과한 토큰을 반환한다.
    """
    # 입력값이 문자열이 아니면 토큰화하지 않는다
    if not isinstance(text, str):
        return []

    # 댓글 앞뒤의 불필요한 공백을 제거한다
    text = text.strip()

    # 공백 제거 후 빈 문자열이면 토큰화하지 않는다
    if not text:
        return []

    # Kiwi로 댓글 하나를 형태소 단위로 분석한다
    tokens = tokenizer.tokenize(text)

    # 공통 토큰 선택 함수에 원문과 형태소 분석 결과를 전달한다
    return _select_comment_tokens(
        text=text,
        tokens=tokens,
        pos_tags=pos_tags,
        include_forms=include_forms,
        stopwords=stopwords,
    )


def tokenize_comments(
    *,
    dataframe: pd.DataFrame,
    tokenizer: Kiwi,
    pos_tags: tuple[str, ...] | None = None,
    include_forms: set[str] | None = None,
    stopwords: set[str] | None = None,
) -> pd.DataFrame:
    """
    전처리된 댓글 DataFrame의 text 컬럼을 일괄 분석하고,
    kiwi_tokens 컬럼이 추가된 복사본을 반환한다.
    """
    # 호출자가 전달한 원본 DataFrame을 변경하지 않도록 복사한다
    tokenized_df = dataframe.copy()

    # 원본 행 위치별 결과를 저장한다
    # 각 행이 서로 다른 빈 리스트를 갖도록 컴프리헨션을 사용한다
    selected_tokens: list[list[dict[str, str]]] = [
        []
        for _ in range(len(tokenized_df))
    ]

    # 문자열이며 공백 제거 후 내용이 있는 댓글만
    # 원본 행 위치와 함께 Kiwi 일괄 분석 대상으로 준비한다
    prepared_texts: list[tuple[int, str]] = []

    # enumerate로 DataFrame 행 순서와 text 값을 함께 순회한다
    for position, value in enumerate(
        tokenized_df["text"]
    ):
        # 문자열이 아닌 값은 초기 빈 리스트를 결과로 유지한다
        if not isinstance(value, str):
            continue

        text = value.strip()

        # 공백 제거 후 빈 문자열인 값도 초기 빈 리스트를 유지한다
        if not text:
            continue

        # 일괄 분석 후 원래 행에 결과를 되돌릴 수 있도록
        # 행 위치와 정리한 텍스트를 함께 저장한다
        prepared_texts.append(
            (position, text)
        )

    # 토큰화할 유효한 텍스트가 있을 때만 Kiwi를 호출한다
    if prepared_texts:
        # Kiwi에 전달할 텍스트만 원래 행 순서대로 꺼낸다
        texts = [
            text
            for _, text in prepared_texts
        ]

        # 문자열 목록을 한 번에 전달하여
        # Kiwi 내부 worker가 형태소 분석을 분배하도록 한다
        token_groups = tokenizer.tokenize(
            texts
        )

        # Kiwi가 입력 순서대로 반환한 결과를 원래 행 위치와 연결한다
        for (
            (position, text),
            tokens,
        ) in zip(
            prepared_texts,
            token_groups,
        ):
            # 댓글 한 건 처리와 동일한 선택 조건을 적용한 뒤
            # 원본 DataFrame의 행 위치에 결과를 저장한다
            selected_tokens[position] = (
                _select_comment_tokens(
                    text=text,
                    tokens=tokens,
                    pos_tags=pos_tags,
                    include_forms=include_forms,
                    stopwords=stopwords,
                )
            )

    # 원본 행 순서에 맞춘 토큰 목록을 새 컬럼으로 추가한다
    tokenized_df["kiwi_tokens"] = (
        selected_tokens
    )

    return tokenized_df


def tokenize_comment_for_current_model(*, text: str, tokenizer: Kiwi) -> list[dict[str, str]]:
    return tokenize_comment(
        text=text,
        tokenizer=tokenizer,
        pos_tags=POS_TAGS,
        include_forms=INCLUDE_FORMS,
        stopwords=STOPWORDS,
    )


def tokenize_comments_for_current_model(*, dataframe: pd.DataFrame, tokenizer: Kiwi) -> pd.DataFrame:
    return tokenize_comments(
        dataframe=dataframe,
        tokenizer=tokenizer,
        pos_tags=POS_TAGS,
        include_forms=INCLUDE_FORMS,
        stopwords=STOPWORDS,
    )
