# uv run python test_kiwi.py

from kiwipiepy import Kiwi


ALLOWED_TAGS = {
    "NNG",  # 일반 명사
    "NNP",  # 고유 명사
    "SL",   # 영어
    "SN",   # 숫자
    "VA",   # 형용사
    "VV",   # 동사
}


def extract_keywords(text: str, kiwi: Kiwi) -> list[str]:
    """현재 03.01.hybrid_search.py와 비슷한 방식으로 키워드를 추출합니다."""

    tokens = kiwi.tokenize(text)
    keywords: list[str] = []

    for token in tokens:
        if token.tag not in ALLOWED_TAGS:
            continue

        word = token.form.strip().lower()

        if not word:
            continue

        if len(word) == 1 and token.tag in {"NNG", "NNP"}:
            continue

        keywords.append(word)

    return keywords


def print_token_analysis(text: str, kiwi: Kiwi) -> None:
    print("\n" + "=" * 100)
    print(f"[테스트 문장] {text}")
    print("=" * 100)

    tokens = kiwi.tokenize(text)

    print("\n[Kiwi 전체 형태소 분석]")
    print("-" * 100)

    for index, token in enumerate(tokens, start=1):
        allowed = "포함" if token.tag in ALLOWED_TAGS else "제외"

        print(
            f"{index:>2}. "
            f"form={token.form!r:<15} "
            f"tag={token.tag:<8} "
            f"start={token.start:<3} "
            f"len={token.len:<3} "
            f"키워드={allowed}"
        )

    keywords = extract_keywords(text, kiwi)

    print("\n[최종 추출 키워드]")
    print("-" * 100)
    print(", ".join(keywords) if keywords else "추출된 키워드가 없습니다.")


def main() -> None:
    kiwi = Kiwi()

    test_sentences = [
        "촉촉한 썬크림 추천",
        "촉촉한 썬크림 추천해줘",
        "매트한 쿠션 추천해줘",
        "순한 선크림 추천해줘",
        "산뜻한 토너 추천해줘",
        "보습력이 좋은 토너 추천해줘",
    ]

    for sentence in test_sentences:
        print_token_analysis(sentence, kiwi)

    print("\n" + "=" * 100)
    print("[직접 입력 테스트]")
    print("종료하려면 exit, quit, q 또는 종료를 입력하세요.")
    print("=" * 100)

    exit_commands = {"exit", "quit", "q", "종료"}

    while True:
        text = input("\n테스트 문장: ").strip()

        if text.lower() in exit_commands:
            print("테스트를 종료합니다.")
            break

        if not text:
            print("[WARNING] 문장을 입력해주세요.")
            continue

        print_token_analysis(text, kiwi)


if __name__ == "__main__":
    main()