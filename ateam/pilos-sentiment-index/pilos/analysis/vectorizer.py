from sklearn.feature_extraction.text import TfidfVectorizer



def tokens_to_tfidf_text(
    tokens: list[dict[str, str]] | None
) -> str:
    """토큰별로 구분된 토큰들을 하나의 문자열로 변환한다."""
    # None 또는 빈 토큰 목록은 TF-IDF 입력용 빈 문서로 변환한다
    if not tokens:
        return ""
    # 형태소 form 내부의 공백이 토큰 경계로 해석되지 않도록
    # 공백을 "_"로 치환한 뒤 각 토큰을 공백으로 연결한다
    return " ".join(
        token["form"].replace(" ", "_")
        for token in tokens
    )


def create_tfidf_vectorizer(
    *,
    lowercase: bool = True,
    ngram_range: tuple[int, int] = (1, 1),
    min_df: int | float = 1,
    max_df: int | float = 1.0,
    max_features: int | None = None,
    sublinear_tf: bool = False,
) -> TfidfVectorizer:
    """전달받은 설정으로 형태소 토큰용 TF-IDF 벡터라이저를 생성한다."""
    return TfidfVectorizer(
        # 공백으로 구분한 형태소를 그대로 사용하고 sklearn 기본 토큰 패턴은 비활성화한다
        tokenizer=str.split,
        token_pattern=None,
        lowercase=lowercase,
        ngram_range=ngram_range,
        min_df=min_df,
        max_df=max_df,
        max_features=max_features,
        sublinear_tf=sublinear_tf,
    )
