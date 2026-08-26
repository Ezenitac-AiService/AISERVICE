"""
Brand & Product Alias Dictionary with Space-insensitive Normalization (Spec 030 FR-022).
올리브영 50대 주요 브랜드 영문 약칭 → 한국어 정식명 매핑 및 N-gram 공백 정규화.
"""

import re
from typing import Optional, Dict, List, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# 브랜드 영문 약칭 → 한국어 정식 브랜드명 매핑 사전
# ──────────────────────────────────────────────────────────────────────────────
BRAND_ALIAS_MAP: Dict[str, str] = {
    # 스킨케어 & 기초
    "cnp": "차앤박",
    "c&p": "차앤박",
    "차앤팍": "차앤박",
    "차엔박": "차앤박",
    "drg": "닥터지",
    "dr.g": "닥터지",
    "닥터쥐": "닥터지",
    "dr g": "닥터지",
    "laneige": "라네즈",
    "라네쥬": "라네즈",
    "sulwhasoo": "설화수",
    "innisfree": "이니스프리",
    "이니스": "이니스프리",
    "amorepacific": "아모레퍼시픽",
    "ap": "아모레퍼시픽",
    "sk2": "에스케이투",
    "sk-2": "에스케이투",
    "skii": "에스케이투",
    "sk-ii": "에스케이투",
    "medicube": "메디큐브",
    "메큐": "메디큐브",
    "numbuzin": "넘버즈인",
    "넘버즌": "넘버즈인",
    "넘버진": "넘버즈인",
    "torriden": "토리든",
    "cosrx": "코스알엑스",
    "roundlab": "라운드랩",
    "round lab": "라운드랩",
    "라운드렙": "라운드랩",
    "anua": "아누아",
    "beplain": "비플레인",
    "isntree": "이즈앤트리",

    # 메이크업
    "hera": "헤라",
    "clio": "클리오",
    "peripera": "페리페라",
    "romand": "롬앤",
    "rom&nd": "롬앤",
    "rom&": "롬앤",
    "espoir": "에스쁘아",
    "colorgram": "컬러그램",
    "bringgreen": "브링그린",
    "bring green": "브링그린",
    "merzy": "머지",
    "tirtir": "티르티르",
    "amuse": "어뮤즈",
    "wakemake": "웨이크메이크",

    # 클렌징 & 바디
    "banilaco": "바닐라코",
    "banila co": "바닐라코",
    "ma:nyo": "마녀공장",
    "manyo": "마녀공장",
    "마녀": "마녀공장",
    "cerave": "세라비",
    "bioderma": "바이오더마",
    "goodal": "구달",
    "abib": "아비브",

    # 선케어
    "isntree": "이즈앤트리",
    "beauty of joseon": "조선미녀",
    "boj": "조선미녀",
    "조선미인": "조선미녀",

    # 헤어 & 바디
    "moremo": "모레모",
    "mise en scene": "미쟝센",
    "미장센": "미쟝센",
    "aestura": "에스트라",

    # 약국 브랜드
    "ato": "아토팜",
    "atopalm": "아토팜",
    "eucerin": "유세린",
    "larocheposay": "라로슈포제",
    "la roche posay": "라로슈포제",
    "라로슈": "라로슈포제",
    "avene": "아벤느",

    # 자연주의 브랜드
    "식물나라": "식물나라",
}


# ──────────────────────────────────────────────────────────────────────────────
# 공백/특수문자 정규화 및 별칭 해소 함수
# ──────────────────────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """
    공백 불일치 및 특수문자를 정규화합니다.
    예: "차 앤 박" → "차앤박", "Dr. G" → "drg"
    """
    # 소문자 변환
    t = text.strip().lower()
    # 특수문자 제거 (한글/영문/숫자만 보존)
    t = re.sub(r"[^a-z0-9가-힣]", "", t)
    return t


def resolve_brand_alias(input_text: str) -> Optional[str]:
    """
    입력 텍스트에서 브랜드 별칭을 감지하여 정식 한국어 브랜드명을 반환합니다.
    감지 실패 시 None을 반환합니다.

    Examples:
        resolve_brand_alias("CNP") → "차앤박"
        resolve_brand_alias("Dr.G") → "닥터지"
        resolve_brand_alias("차 앤 박") → "차앤박"
        resolve_brand_alias("없는브랜드") → None
    """
    norm = normalize_text(input_text)

    # 1. 정규화된 키로 직접 매칭
    if norm in BRAND_ALIAS_MAP:
        return BRAND_ALIAS_MAP[norm]

    # 2. 원본 소문자로 매칭 (공백 포함 키 지원)
    lower = input_text.strip().lower()
    if lower in BRAND_ALIAS_MAP:
        return BRAND_ALIAS_MAP[lower]

    # 3. 정식 브랜드명 직접 입력인 경우 그대로 반환
    canonical_names = set(BRAND_ALIAS_MAP.values())
    for name in canonical_names:
        if normalize_text(name) == norm:
            return name

    return None


def normalize_query_brands(query: str) -> Tuple[str, List[str]]:
    """
    질의 텍스트에서 모든 브랜드 별칭을 정식 한국어명으로 치환합니다.

    Returns:
        (정규화된 질의 문자열, 감지된 브랜드명 리스트)

    Example:
        normalize_query_brands("CNP 앰플이랑 Dr.G 크림 비교해줘")
        → ("차앤박 앰플이랑 닥터지 크림 비교해줘", ["차앤박", "닥터지"])
    """
    detected_brands: List[str] = []
    result = query

    # 긴 별칭부터 우선 매칭 (greedy matching)
    sorted_aliases = sorted(BRAND_ALIAS_MAP.keys(), key=len, reverse=True)

    for alias in sorted_aliases:
        # 대소문자 무시 패턴 매칭
        pattern = re.compile(re.escape(alias), re.IGNORECASE)
        if pattern.search(result):
            canonical = BRAND_ALIAS_MAP[alias]
            if canonical not in detected_brands:
                detected_brands.append(canonical)
            result = pattern.sub(canonical, result)

    return result, detected_brands
