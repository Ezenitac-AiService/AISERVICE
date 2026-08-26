"""
Domain Sanitizer, Noise Filter & Olive Young URL Builder for Oliview Core.
"""

import re
import urllib.parse
from typing import Dict, List, Optional, Tuple

# Supported Brands & Canonical Names
SUPPORTED_BRANDS: Dict[str, List[str]] = {
    "차앤박": ["차앤박", "cnp", "씨앤피", "프로폴리스"],
    "헤라": ["헤라", "hera", "블랙쿠션", "센슈얼"],
    "식물나라": ["식물나라", "티트리", "제주탄산수"],
    "브링그린": ["브링그린", "bringgreen", "사철쑥", "징크테카"],
    "컬러그램": ["컬러그램", "colorgram", "탕후루", "쥬시퐁당"],
}

# Standard Category Attributes
CATEGORY_ATTRIBUTES: Dict[str, List[str]] = {
    "스킨케어": ["기능/효과", "발림성", "수분감", "자극성", "향", "흡수력"],
    "클렌징": ["거품력", "기능/효과", "세정력", "수분감", "자극성", "향"],
    "선케어": ["기능/효과", "눈시림", "발림성", "백탁현상", "수분감", "자극성", "지속력", "톤업효과", "향"],
    "립메이크업": ["각질부각", "발색력", "발림성", "수분감", "착색력", "촉촉함", "향"],
    "베이스메이크업": ["가루날림", "감촉", "결점커버", "기능/효과", "밀착력", "발림성", "수분감", "유분감", "지속력", "촉촉함", "피부톤"],
    "아이메이크업": ["가루날림", "고정력", "눈시림", "번짐", "선명도", "자극성", "지속력"],
}

# Olive Young Search URL mapping
BRAND_OY_URLS: Dict[str, str] = {
    "차앤박": "https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query=%EC%B0%A8%EC%95%A4%EB%B0%95",
    "헤라": "https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query=%ED%97%A4%EB%9D%BC",
    "식물나라": "https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query=%EC%8B%9D%EB%AC%BC%EB%82%98%EB%9D%BC",
    "브링그린": "https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query=%EB%B8%8C%EB%A7%81%EA%B7%B8%EB%A6%B0",
    "컬러그램": "https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query=%EC%BB%AC%EB%9F%AC%EA%B7%B8%EB%9E%A8",
}


def build_oliveyoung_url(product_name: str, brand: Optional[str] = None) -> str:
    """Builds search URL for Olive Young online mall."""
    if not product_name and brand and brand in BRAND_OY_URLS:
        return BRAND_OY_URLS[brand]
    clean_kw = re.sub(r"\[.*?\]|\(.*?\)", "", product_name or "").strip()
    encoded = urllib.parse.quote(clean_kw or product_name or "화장품")
    return f"https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query={encoded}"


def clean_review_noise(text: str) -> str:
    """Removes HTML artifacts, delivery noise, and excessive punctuation."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"배송[^\n\.]*?(빨라요|좋아요|느려요)", "", text)
    text = re.sub(r"체험단[^\n\.]*?작성", "", text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_brand_and_category(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Detects brand name and cosmetic category from user query."""
    text_lower = text.lower()
    matched_brand = None
    for brand, aliases in SUPPORTED_BRANDS.items():
        for alias in aliases:
            if alias.lower() in text_lower:
                matched_brand = brand
                break
        if matched_brand:
            break

    matched_cat = None
    for cat in CATEGORY_ATTRIBUTES.keys():
        if cat in text:
            matched_cat = cat
            break

    return matched_brand, matched_cat


# ────────────────────────────────────────────────────────────────────────────
# Spec 017: Korean Markdown Bold Rendering Normalization
# CommonMark Right-flanking Delimiter 충돌 자동 보정 유틸리티
# ────────────────────────────────────────────────────────────────────────────

# 사전 컴파일 정규식 (싱글톤, ReDoS 방어: 비탐욕 + 문자 클래스 제한)
# 패턴 1: **"텍스트"**조사 또는 **'텍스트'**조사
_RE_QUOTE_BOLD_POSTPOS = re.compile(
    r'\*\*(["\'])([^"\'\*\n]+?)\1\*\*([가-힣]+)'
)
# 패턴 2: **텍스트**조사 (일반 볼드 뒤에 한국어 조사가 바로 결합)
_RE_BOLD_POSTPOS = re.compile(
    r'\*\*([^\*\n]+?)\*\*([가-힣]+)'
)


def normalize_korean_markdown(text: Optional[str]) -> str:
    """한국어 CommonMark Right-flanking 파싱 충돌을 자동 보정합니다.

    CommonMark 사양에서 닫는 **의 앞이 구두점(따옴표 등)이고 뒤에 한국어
    조사(라는, 이라고, 은, 는, 이, 가, 을, 를, 에서, 으로 등)가 공백 없이
    결합하면 파서가 닫는 강조 태그를 인식하지 못하여 별표가 그대로 노출됩니다.

    이 함수는 해당 패턴만 선택적으로 <strong> HTML 태그로 치환하여
    원본 마크다운 구조를 최대한 보존하면서 렌더링 무결성을 보장합니다.

    Args:
        text: LLM 생성 마크다운 텍스트 (None 허용)

    Returns:
        정규화된 마크다운 텍스트 (별표 노출 결함 0건 보장)
    """
    if not text:
        return ""

    # Step 1: **"텍스트"**조사 → <strong>"텍스트"</strong>조사
    result = _RE_QUOTE_BOLD_POSTPOS.sub(
        r'<strong>\1\2\1</strong>\3', text
    )

    # Step 2: **텍스트**조사 → <strong>텍스트</strong>조사
    result = _RE_BOLD_POSTPOS.sub(
        r'<strong>\1</strong>\2', result
    )

    return result

