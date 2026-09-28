"""Hybrid Cascaded Query Normalizer & Entity Decoupler (Spec 037 FR-001, FR-002).

Stage 1: Kiwi Morphological Fast-Path (<3ms) with Greedy Backward Stripping & Longest Prefix Matching.
Stage 2: Qwen 2B SLM Arbiter Fallback (<60ms) for ambiguous / complex edge cases.
Stage 3: Catalog Grounding validation.
"""

import re
import json
import logging
from typing import Optional, List, Dict, Any, Tuple
from ..models.citation_models import NormalizedQueryEntity, QueryIntentEnum
from ..models.aspect_lexicon import NEGATIVE_ASPECT_TERMS, NEGATIVE_ASPECT_LEXICON
from ..alias_dictionary import BRAND_ALIAS_MAP
from ..tools.search_tools import tool_search_series_candidates

logger = logging.getLogger(__name__)

# 공통 뷰티 속성 키워드 (부정 속성 사전 포함)
BEAUTY_ASPECT_KEYWORDS = [
    "발림성", "지속력", "수분감", "보습력", "흡수력", "장단점", "커버력", "밀착력", "트러블", 
    "붉은기", "진정", "쿨링감", "촉촉함", "유분기", "다크닝", "각질부각",
    "요철부각", "들뜸", "밀림", "뭉침", "가루날림", "건조함", "번짐",
    "향", "자극", "자극성", "가성비", "순함", "모공", "피지", "미백", "주름"
]

# 대표적 화장품 라인/시리즈 키워드
BEAUTY_SERIES_KEYWORDS = [
    "센슈얼", "프로폴리스", "쥬시", "글래스팅", "비벨벳", "블랙쿠션", "레드쿠션",
    "클린잇제로", "그린티", "자작나무", "시카플라스트", "워터뱅크", "하이드라",
    "세라마이딘", "더마", "어드밴스드", "비타민c", "레티놀", "골든카밍"
]

# 공통 뷰티 카테고리 키워드
BEAUTY_CATEGORY_KEYWORDS = {
    "쿠션팩트": ["쿠션팩트", "쿠션", "팩트", "쿠션파데"],
    "립틴트": ["립틴트", "틴트", "워터틴트", "벨벳틴트", "글로시틴트"],
    "립글로스": ["립글로스", "꿀로스", "글로스", "립오일", "플럼퍼"],
    "립스틱": ["립스틱", "립밤", "컬러립밤", "누드밤"],
    "선크림": ["선크림", "선블록", "선스크린", "선로션", "자외선차단제"],
    "토너": ["토너", "스킨", "토너패드", "패드"],
    "앰플": ["앰플", "세럼", "에센스"],
    "수분크림": ["수분크림", "보습크림", "진정크림", "영양크림", "시카크림", "크림"],
    "클렌징폼": ["클렌징폼", "폼클렌징", "클렌저", "클렌징오일", "클렌징워터"],
    "마스크팩": ["마스크팩", "시트마스크", "팩"]
}


# 후방 서술어 및 요청구 제거 정규식 패턴 (Greedy Backward Stripping)
TRAILING_CONVERSATIONAL_PATTERNS = [
    r"(?:의\s*)?(?:발림성|지속력|수분감|장단점|커버력|밀착력|효과|부작용|가격|후기|성분|색상|특징|촉촉함|각질부각|요철부각|들뜸|밀림|다크닝|뭉침|가루날림|건조함|번짐)\s*(?:장단점|어때|추천해줘|분석해줘|알려줘|있나요|좋아\??|어떤가요|비교해줘|평가해줘|후기\s*알려줘).*",
    r"\s*(?:장단점\s*)?(?:분석해줘|추천해줘|알려줘|어때\??|있나요\??|어떤가요\??|비교해줘|평가해줘|어떻습니까\??|골라줘|써보신분|어떤게\s*좋아\??).*",
    r"(?:의\s*)?(?:장단점|발림성|지속력|수분감|커버력|밀착력|순함|효과|촉촉함|각질부각)\s*$",
    r"\s*(?:에\s*대해|에\s*관해|관련해서|대해서)\s*.*$"
]



class HybridEntityNormalizer:
    """하이브리드 캐스케이디드 질의 정규화 및 엔티티 추출기."""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._kiwi = None
        self._init_kiwi()

    def _init_kiwi(self):
        try:
            from kiwipiepy import Kiwi
            self._kiwi = Kiwi()
            # Register brands, series, beauty aspects and categories to prevent morphological fragmentation
            for b in set(BRAND_ALIAS_MAP.values()):
                try:
                    self._kiwi.add_user_word(b, tag="NNP", score=10.0)
                except Exception:
                    pass
            for a in BRAND_ALIAS_MAP.keys():
                try:
                    self._kiwi.add_user_word(a, tag="NNP", score=10.0)
                except Exception:
                    pass
            for s in BEAUTY_SERIES_KEYWORDS:
                try:
                    self._kiwi.add_user_word(s, tag="NNP", score=5.0)
                except Exception:
                    pass
            for word in BEAUTY_ASPECT_KEYWORDS:
                try:
                    self._kiwi.add_user_word(word, tag="NNG", score=5.0, user_value="ASPECT")
                except Exception:
                    try:
                        self._kiwi.add_user_word(word, tag="NNG", score=5.0)
                    except Exception:
                        pass
            for cat_list in BEAUTY_CATEGORY_KEYWORDS.values():
                for word in cat_list:
                    try:
                        self._kiwi.add_user_word(word, tag="NNG", score=5.0)
                    except Exception:
                        pass
        except ImportError:
            logger.warning("kiwipiepy not installed, falling back to regex tokenization")
            self._kiwi = None

    def normalize(self, query: str) -> NormalizedQueryEntity:
        """사용자 질의를 정규화하여 순수 브랜드, 상품명, 카테고리, 속성 및 의도를 추출합니다."""
        raw_query = query.strip()
        if not raw_query:
            return NormalizedQueryEntity(raw_query="")

        # 1. Stage 1: Fast-Path Rule & Morphology Extraction
        fast_result = self._fast_path_normalize(raw_query)

        # 2. 신뢰도 평가: 단일 상품명이 명확히 추출되었거나 확실한 카테고리 발굴 질의인 경우
        if fast_result.catalog_confidence >= 0.85:
            return fast_result

        # 3. Stage 2: SLM Fallback & Disambiguation (모호하거나 0건인 복잡한 질의)
        if self.llm_client:
            try:
                slm_result = self._slm_fallback_normalize(raw_query, fast_result)
                if slm_result:
                    return slm_result
            except Exception as e:
                logger.warning(f"SLM Fallback normalization failed: {e}")

        return fast_result

    def _fast_path_normalize(self, query: str) -> NormalizedQueryEntity:
        """Stage 1: Kiwi + 2-Pass 형태소/구문 기반 초고속 정규화 (<3ms)."""
        extracted_aspects: List[str] = []
        extracted_category: Optional[str] = None
        extracted_brand: Optional[str] = None

        # 1) Kiwi Morphology Tokenization (Stage 1 Fast-Path)
        tokens = self._kiwi.tokenize(query) if self._kiwi else []

        # 2) 브랜드 매핑 (BRAND_ALIAS_MAP 사전 검사 - 후방 서술어 정제보다 엄격히 선행 배치하여 복합 표기 보호)
        for alias_key, canon_brand in BRAND_ALIAS_MAP.items():
            pattern = rf"(?:\b|^|\s){re.escape(alias_key)}(?:\b|\$|\s)"
            if re.search(pattern, query, re.IGNORECASE) or alias_key.lower() in query.lower():
                extracted_brand = canon_brand
                break

        # 3) 형태소 기반 속성 키워드 감지 및 [Aspect] + JC + [Aspect] 다중 속성 구문 분석
        has_aspect_coordination = False
        if tokens:
            # Multi-aspect noun phrase coordination ([Aspect] + JC + [Aspect])
            for i in range(len(tokens) - 2):
                t1, t2, t3 = tokens[i], tokens[i + 1], tokens[i + 2]
                if t2.tag == "JC" and t1.form in BEAUTY_ASPECT_KEYWORDS and t3.form in BEAUTY_ASPECT_KEYWORDS:
                    has_aspect_coordination = True
                    if t1.form not in extracted_aspects:
                        extracted_aspects.append(t1.form)
                    if t3.form not in extracted_aspects:
                        extracted_aspects.append(t3.form)

            for t in tokens:
                if t.form in BEAUTY_ASPECT_KEYWORDS and t.form not in extracted_aspects:
                    extracted_aspects.append(t.form)

        # Fallback keyword extraction for aspects
        for aspect in BEAUTY_ASPECT_KEYWORDS:
            if aspect in query and aspect not in extracted_aspects:
                extracted_aspects.append(aspect)

        # 4) 카테고리 키워드 감지
        for cat_name, aliases in BEAUTY_CATEGORY_KEYWORDS.items():
            for alias in aliases:
                if any(t.form == alias for t in tokens) or alias in query:
                    extracted_category = cat_name
                    break
            if extracted_category:
                break

        # 5) 타겟 상품명 정제 (형태소 경계 분석으로 후방 서술어/조사/속성구 제거)
        target_candidate = query
        if tokens:
            all_cat_words = {w for cl in BEAUTY_CATEGORY_KEYWORDS.values() for w in cl}
            cutoff = len(query)
            for i, t in enumerate(tokens):
                # '의' (JKG) or '로/에' (JKB)
                if t.tag == "JKG" and i > 0:
                    cutoff = min(cutoff, t.start)
                    break
                if t.tag == "JKB" and i > 0 and i < len(tokens) - 1:
                    cutoff = min(cutoff, t.start)
                    break
                # 속성 키워드 (카테고리 수식어가 아닌 경우 분리)
                if t.form in BEAUTY_ASPECT_KEYWORDS:
                    is_followed_by_cat = (i + 1 < len(tokens) and tokens[i + 1].form in all_cat_words)
                    if not is_followed_by_cat:
                        cutoff = min(cutoff, t.start)
                        break
                # 서술형 동사/형용사
                if t.tag in ("VV", "VA") and t.form in ("알리", "추천", "비교", "어떻", "분석", "평가"):
                    cutoff = min(cutoff, t.start)
                    break
                # 상품 간 연결 접속조사 ('이랑', '과', '와')
                if t.tag == "JC" and i > 0:
                    cutoff = min(cutoff, t.start)
                    break

            target_candidate = query[:cutoff].strip()
        else:
            for pattern in TRAILING_CONVERSATIONAL_PATTERNS:
                target_candidate = re.sub(pattern, "", target_candidate, flags=re.IGNORECASE).strip()

            # Iteratively strip trailing aspects and conjunction particles until stable (T013)
            changed = True
            while changed:
                changed = False
                cleaned = re.sub(r"\s*(?:과|와|랑|하고|및|의)\s*$", "", target_candidate).strip()
                if cleaned != target_candidate:
                    target_candidate = cleaned
                    changed = True
                for aspect in BEAUTY_ASPECT_KEYWORDS:
                    cleaned = re.sub(rf"(?:의\s*)?{re.escape(aspect)}\s*$", "", target_candidate).strip()
                    if cleaned != target_candidate:
                        target_candidate = cleaned
                        changed = True

        if extracted_brand:
            for alias_key in BRAND_ALIAS_MAP.keys():
                if BRAND_ALIAS_MAP[alias_key] == extracted_brand and alias_key.lower() in target_candidate.lower():
                    target_candidate = re.sub(re.escape(alias_key), extracted_brand, target_candidate, count=1, flags=re.IGNORECASE).strip()
                    break

        # 6) 비교 질문 여부 검사 (Kiwi JC vs JKB 및 2-Pass 구문 분석)
        has_comparison_predicate = bool(re.search(r"(?:비교|차이점|차이|대비|vs\b|versus|어느\s*게\s*더|어떤\s*게\s*더|뭐가\s*더)", query, re.IGNORECASE))

        # Check count of distinct brands in query
        detected_brand_count = 0
        for alias_key in set(BRAND_ALIAS_MAP.values()):
            if alias_key in query:
                detected_brand_count += 1

        is_comparison = False
        if has_comparison_predicate:
            is_comparison = True
        elif detected_brand_count >= 2:
            is_comparison = True
        elif has_aspect_coordination:
            # [Aspect] + JC + [Aspect] coordinated noun phrase: preserve SINGLE_TARGET
            is_comparison = False

        # 6) 카테고리 탐색(Discovery) vs 단일 상품 분류
        is_discovery = False
        intent = QueryIntentEnum.SINGLE_TARGET

        has_discovery_intent = bool(re.search(r"(?:추천|있나요|어떤가요|좋은|순한|진정|인기|골라줘|써보신분)", query, re.IGNORECASE))

        if is_comparison:
            intent = QueryIntentEnum.COMPARISON
        elif extracted_category:
            # 브랜드가 명시되지 않았고 카테고리가 포함되어 있는 경우, 또는 탐색 질의인 경우
            if not extracted_brand:
                is_discovery = True
                intent = QueryIntentEnum.FEATURE_DISCOVERY
            elif has_discovery_intent and (not target_candidate or target_candidate == extracted_brand):
                is_discovery = True
                intent = QueryIntentEnum.FEATURE_DISCOVERY
            elif not target_candidate or target_candidate == extracted_category or target_candidate in extracted_aspects:
                is_discovery = True
                intent = QueryIntentEnum.FEATURE_DISCOVERY
        elif not target_candidate and extracted_aspects:
            is_discovery = True
            intent = QueryIntentEnum.FEATURE_DISCOVERY
        elif not extracted_brand and has_discovery_intent and extracted_category:
            is_discovery = True
            intent = QueryIntentEnum.FEATURE_DISCOVERY

        # 6.5) 시리즈/라인명 퍼지 매칭 검사 (Spec 038 FR-001)
        is_series_query = False
        series_keyword = None
        series_candidates: List[Dict[str, Any]] = []

        # 시리즈 키워드 탐지
        detected_series_token = None
        for sk in BEAUTY_SERIES_KEYWORDS:
            if sk in query:
                detected_series_token = sk
                break

        if not detected_series_token and target_candidate and extracted_brand:
            # 브랜드명을 제외한 나머지 단어가 시리즈명일 가능성 검사
            rem = target_candidate.replace(extracted_brand, "").strip()
            # 카테고리 단어 제거 (예: "센슈얼 립" -> "센슈얼")
            for cat_aliases in BEAUTY_CATEGORY_KEYWORDS.values():
                for alias in cat_aliases:
                    if rem.endswith(alias) or rem.startswith(alias):
                        rem = rem.replace(alias, "").strip()
            if len(rem) >= 2:
                detected_series_token = rem

        if detected_series_token:
            candidates = tool_search_series_candidates(
                series_keyword=detected_series_token,
                brand=extracted_brand,
                category=extracted_category,
                limit=3,
            )
            if len(candidates) >= 2:
                is_series_query = True
                series_keyword = detected_series_token
                series_candidates = candidates
                intent = QueryIntentEnum.COMPARISON

        # 7) 축약 식별명(Short Target Name) 생성
        short_name = None
        if target_candidate:
            words = target_candidate.split()
            if len(words) >= 3:
                # e.g. "컬러그램 탕후루 탱글 꿀로스" -> "컬러그램 꿀로스"
                short_name = f"{words[0]} {words[-1]}"
            else:
                short_name = target_candidate

        confidence = 0.90 if target_candidate and len(target_candidate) >= 3 else 0.60
        if is_discovery or is_series_query:
            confidence = 0.95

        return NormalizedQueryEntity(
            raw_query=query,
            extracted_brand=extracted_brand,
            extracted_product=target_candidate if target_candidate and not is_discovery else None,
            extracted_category=extracted_category,
            extracted_aspects=extracted_aspects,
            short_target_name=short_name,
            intent=intent,
            is_discovery=is_discovery,
            is_series_query=is_series_query,
            series_keyword=series_keyword,
            series_candidates=series_candidates,
            parsing_source="KIWI_FAST_PATH",
            catalog_confidence=confidence,
        )


    def _slm_fallback_normalize(self, query: str, fast_result: NormalizedQueryEntity) -> Optional[NormalizedQueryEntity]:
        """Stage 2: Qwen 2B SLM 구조화 파싱 Fallback (<60ms)."""
        prompt = (
            f"다음 화장품 관련 질문에서 브랜드명, 상품명, 카테고리, 질문 속성을 JSON으로 추출하세요.\n"
            f"질문: \"{query}\"\n"
            f"반드시 JSON 형식으로만 답하세요:\n"
            f'{{"brand": "브랜드명 또는 null", "product_name": "순수 상품명 또는 null", "category": "카테고리명 또는 null", "aspects": ["속성1", "속성2"], "is_discovery": true_or_false}}'
        )

        stream = self.llm_client.generate_stream(
            prompt=prompt,
            system_prompt="당신은 한국어 화장품 질의 엔티티 추출 전문 파서입니다. 오직 유효한 JSON만 반환하세요.",
            max_tokens=256,
            temperature=0.0,
        )
        response_text = "".join(stream).strip()

        # JSON 파싱
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            brand = data.get("brand")
            product = data.get("product_name")
            category = data.get("category") or fast_result.extracted_category
            aspects = data.get("aspects") or fast_result.extracted_aspects
            is_disc = data.get("is_discovery", fast_result.is_discovery)

            intent = QueryIntentEnum.FEATURE_DISCOVERY if is_disc else QueryIntentEnum.SINGLE_TARGET

            short_name = None
            if product:
                w = product.split()
                short_name = f"{w[0]} {w[-1]}" if len(w) >= 3 else product

            return NormalizedQueryEntity(
                raw_query=query,
                extracted_brand=brand,
                extracted_product=product,
                extracted_category=category,
                extracted_aspects=aspects,
                short_target_name=short_name,
                intent=intent,
                is_discovery=is_disc,
                parsing_source="SLM_ARBITER_FALLBACK",
                catalog_confidence=0.95,
            )
        return None


_normalizer_instance: Optional[HybridEntityNormalizer] = None


def get_entity_normalizer(llm_client=None) -> HybridEntityNormalizer:
    """Returns or initializes singleton HybridEntityNormalizer instance."""
    global _normalizer_instance
    if _normalizer_instance is None:
        _normalizer_instance = HybridEntityNormalizer(llm_client=llm_client)
    return _normalizer_instance

