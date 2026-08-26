"""common.py - Oliview Chatbot B 공통 헬퍼 모듈

로컬 LLM Gateway (127.0.0.1:8081 / vllm-serv-gateway) 연동, 헬스체크, <think> 정제 및 HTTP 클라이언트를 제공합니다.
"""

import os
import sys
import json
import time
import re
import datetime
from pathlib import Path
from typing import Optional, List, Any
import httpx
from pydantic import BaseModel, Field
from openai import OpenAI

NO_THINK_SYSTEM_PROMPT = "당신은 IT 및 AI 기술 전문 어시스턴트입니다. 생각 과정(<think>, Thinking Process, Draft/Identify 등)을 절대 작성하지 마시고, 첫 글자부터 즉시 최종 한국어 답변만 작성하세요."


class FastChatRequest(BaseModel):
    query: str = Field(..., description="사용자 일반 대화 질의", min_length=1)
    max_tokens: int = Field(default=2048, description="최대 생성 토큰 예산 (기본 2K)")
    temperature: float = Field(default=0.7, ge=0.0, le=1.0, description="생성 다양성")


class FastChatResponse(BaseModel):
    answer: str = Field(..., description="LLM 생성 답변")
    latency_sec: float = Field(..., description="응답 소요 시간 (초)")
    model: str = Field(default="qwen3.5-4b", description="실제 사용된 모델 ID")


class RecommendedProduct(BaseModel):
    rank: int = 1
    product_name: str = ""
    brand_name: str = ""
    category: str = ""
    review_score: float = 5.0
    separated_sentence: str = ""
    display_name: str = ""
    sentiment_label: str = ""
    cosine_similarity: float = 0.0
    rerank_score: float = 0.0


HANJA_TO_HANGUL_MAP = {
    # 핵심 분석/추천/품질 용어
    "結果": "결과", "推薦": "추천", "效果": "효과", "成分": "성분",
    "皮膚": "피부", "使用": "사용", "分析": "분석", "製品": "제품",
    "價格": "가격", "滿足": "만족", "總評": "총평", "結論": "결론",
    "優點": "장점", "缺點": "단점", "特徵": "특징", "評價": "평가",
    "容量": "용량", "適合": "적합", "機能": "기능", "改善": "개선",

    # 화장품 속성 및 제형 용어
    "保濕": "보습", "水分": "수분", "彈力": "탄력", "敏感": "민감",
    "塗抹": "발림", "油分": "유분", "吸水": "흡수", "鎭靜": "진정",
    "鎮靜": "진정", "乾燥": "건조", "滋潤": "촉촉함", "補水": "수분 공급",
    "溫和": "순함", "角質": "각질", "美白": "미백", "皺紋": "주름",
    "潔面": "클렌징", "精華": "에센스", "乳液": "로션", "面霜": "크림",
    "防曬": "선케어", "遮瑕": "커버", "持久": "지속력", "香氣": "향",
    "刺痛": "따가움", "清爽": "산뜻함", "黏膩": "끈적임", "狀態": "상태",
    "肌膚": "피부", "質地": "제형", "吸收": "흡수", "保濕力": "보습력",
    "清潔": "클렌징", "洗面": "세안", "護膚": "스킨케어", "問題": "문제",
    "毛孔": "모공", "皮脂": "피지", "問題性": "트러블성", "舒緩": "진정"
}


def clean_hanja_and_artifacts(text: str) -> str:
    """LLM 출력 텍스트에서 한자(CJK)를 탐지하여 한글로 치환하고 잔여 한자를 정제합니다."""
    if not text:
        return ""

    cleaned = text
    # 1. 상용 복합 한자어 치환
    for hanja, hangul in HANJA_TO_HANGUL_MAP.items():
        cleaned = cleaned.replace(hanja, hangul)

    # 2. 잔여 단일 CJK 한자 탐지 및 제거
    cleaned = re.sub(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]", "", cleaned)

    # 3. 불필요한 연속 공백 정돈
    cleaned = re.sub(r" +", " ", cleaned)
    return cleaned.strip()


# ==============================================================================
# 🟢 [브랜드 엔티티 감지 및 불용어 필터링 가드레일 (006-rag-brand-guardrail)]
# ==============================================================================
RAG_STOPWORDS = {
    "하루", "종일", "스킨", "케어", "스킨케어", "화장품", "제품", "추천", "추천해줘", "추천해", "알려줘",
    "분석해줘", "분석해", "비교해줘", "좋은", "어떤게", "인기", "순위", "리뷰", "사용기", "모음",
    "베스트", "어때", "어때요", "골라줘", "관련", "라인", "세트", "앰플", "크림", "토너", "로션",
    "에센스", "세럼", "미스트", "클렌징", "선크림", "선케어", "마스크", "팩", "보습", "수분",
    "진정", "미백", "주름", "탄력", "각질", "피지", "모공", "트러블", "여드름", "속건조",
    "건성", "지성", "복합성", "민감성", "순한", "촉촉한", "있나요", "있어", "있을까", "있나요?",
    "안나고", "안나", "안나는", "붉은", "붉은기", "매트", "매트한", "순하면서", "커버", "잘되는",
    "잡아주는", "쿠션", "파운데이션", "브랜드", "어떤가요", "사용", "발림성", "촉촉", "뽀송",
    "유분기", "피부", "성분", "순해", "효과", "바르면", "써도", "쓰면", "자극", "없는", "안나는",
    "터블", "화이트", "비비안", "피지", "알리"
}

_BRAND_CACHE = []
_BRAND_CACHE_TIME = 0.0


def get_active_brands_cached(connection_getter_or_conn) -> list[str]:
    """실제 리뷰 임베딩이 존재하는 활성 뷰티 브랜드 목록을 1시간 단위로 메모리 캐싱하여 반환합니다."""
    global _BRAND_CACHE, _BRAND_CACHE_TIME
    now = time.time()
    if _BRAND_CACHE and (now - _BRAND_CACHE_TIME < 3600):
        return _BRAND_CACHE

    try:
        conn = connection_getter_or_conn() if callable(connection_getter_or_conn) else connection_getter_or_conn
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT r.brand_name 
            FROM review_aspect_sentences r 
            INNER JOIN brands b ON r.brand_name = b.brand_name 
            WHERE r.embedding_vector IS NOT NULL 
              AND b.is_active = 1 
              AND r.brand_name IS NOT NULL 
              AND TRIM(r.brand_name) != '' 
              AND r.brand_name NOT LIKE '%미분류%' 
              AND r.brand_name NOT LIKE '%화장품%' 
              AND r.brand_name NOT LIKE '%익명%' 
              AND r.brand_name NOT LIKE '%추정%' 
              AND r.brand_name NOT LIKE '%불명%'
            GROUP BY r.brand_name 
            HAVING COUNT(*) >= 3
            """
        )
        rows = cursor.fetchall()
        brands = []
        for r in rows:
            b_name = r.get("brand_name") if isinstance(r, dict) else r[0]
            if b_name and len(b_name.strip()) >= 2:
                name_clean = b_name.strip()
                if name_clean not in RAG_STOPWORDS:
                    brands.append(name_clean)
        # 길이 내림차순 정렬 (긴 브랜드명 우선 매칭)
        brands.sort(key=len, reverse=True)
        _BRAND_CACHE = brands
        _BRAND_CACHE_TIME = now
        cursor.close()
        if callable(connection_getter_or_conn) and conn and conn.open:
            conn.close()
        return _BRAND_CACHE
    except Exception as e:
        print(f"⚠️ [브랜드 캐시 로드 오류]: {e}")
        return _BRAND_CACHE


def extract_brand_entity(query_text: str, active_brands: list[str]) -> tuple[Optional[str], list[str]]:
    """
    사용자 자연어 질의에서 활성 브랜드 엔티티를 우선 탐지하고,
    불용어를 제외한 유효 검색 토큰 목록을 분리 반환합니다.
    """
    if not query_text:
        return None, []

    q_clean = query_text.strip()
    detected_brand = None

    # 1. 브랜드 사전 최장 일치 탐지 (단어/조사 경계 검증)
    for b in active_brands:
        if not b or len(b) < 2 or b in RAG_STOPWORDS:
            continue
        # 한국어 조사 경계 및 공백 경계 패턴 매칭
        pattern = rf"(?:^|[\s,./?!~])({re.escape(b)})(?:[\s,./?!~]|의|에서|은|는|이|가|을|를|도|에|로|으로|$)"
        if re.search(pattern, q_clean, re.IGNORECASE):
            detected_brand = b
            break

    # 2. 토큰 분리 및 불용어/감지된 브랜드 제거
    raw_tokens = [w.strip() for w in re.split(r"[\s,./?!~]+", q_clean) if len(w.strip()) >= 2]
    filtered_tokens = []
    for tok in raw_tokens:
        if tok in RAG_STOPWORDS:
            continue
        if detected_brand and (tok.lower() == detected_brand.lower() or tok in detected_brand):
            continue
        filtered_tokens.append(tok)

    return detected_brand, filtered_tokens


DUMMY_NAME_PATTERNS = [
    "익명", "미분류", "불가", "불명", "미상", "알 수 없음", "없음", "추정",
    "추론", "식별", "비정형", "구분 불가", "구체적 명칭 없음", "이해불가", "정보 부족",
    "브랜드 X", "브랜드 Y", "브랜드 Z", "A 브랜드", "B 브랜드", "브랜드명", "가상의 브랜드"
]


def is_dummy_name(text: str) -> bool:
    """브랜드명 또는 상품명이 결측/더미/익명 문자열인지 검사합니다."""
    if not text or len(text.strip()) < 2:
        return True
    s = text.strip()
    return any(pat in s for pat in DUMMY_NAME_PATTERNS)


DUMMY_PRODUCT_EXACT = {
    "이 제품", "화장품", "제품", "상품", "일반 상품", "미용제", "화장품 상품명",
    "상세 정보 없음", "정보 없음", "미분류", "미분류 상품", "재구매 가능한 제품",
    "지속력이 강한 화장품", "발림성 좋은 제품", "일반 상품 (스킨케어)"
}

DUMMY_PRODUCT_SUBSTRINGS = [
    "추정", "미상", "불가", "불명", "미분류", "알 수 없음", "없음", "제공 필요",
    "일반 상품", "상품명 (", "브랜드 (", "가상", "식별", "구분 불가", "브랜드 X",
    "브랜드명", "상품명", "무명", "가상의"
]


def is_valid_product_name(name: str) -> bool:
    """상품명이 결측/더미/추정/문장형 문자열인지 엄격히 검증합니다."""
    if not name or len(name.strip()) < 2:
        return False
    s = name.strip()
    if s in DUMMY_PRODUCT_EXACT:
        return False
    if any(pat in s for pat in DUMMY_PRODUCT_SUBSTRINGS):
        return False
    if re.search(r"[,.!?~]|(좋아|좋고|있습|합니|되었|해서|쓰기|지속|뽀드득|구매|사용|바르|느낌|발림)", s):
        return False
    return True


def clean_think_tags(text: str, show_think: bool = False) -> str:
    """<think>...</think> 태그 및 CoT 고찰 블록, 한자를 세척합니다."""
    if not text:
        return ""

    think_part = ""
    answer_part = text

    if "<think>" in text and "</think>" in text:
        parts = text.split("</think>", 1)
        think_part = parts[0].replace("<think>", "").strip()
        answer_part = parts[1].strip()
    elif "</think>" in text:
        parts = text.split("</think>", 1)
        think_part = parts[0].replace("<think>", "").strip()
        answer_part = parts[1].strip()

    cot_patterns = [
        r"Thinking Process:",
        r"Drafting:",
        r"Drafting the Definition:",
        r"Identify Key Concepts:",
        r"Draft Potential Answers:",
        r"Analyze the Request:",
        r"Draft Potential:",
        r"Final Polish:",
        r"Internal Monologue:"
    ]

    is_cot_present = any(re.search(pat, answer_part, re.IGNORECASE) for pat in cot_patterns) or ("Analyze" in answer_part and "Draft" in answer_part)

    if is_cot_present:
        lines = answer_part.splitlines()
        think_lines = []
        answer_lines = []
        is_in_cot_block = False

        for line in lines:
            if any(re.search(pat, line, re.IGNORECASE) for pat in cot_patterns):
                is_in_cot_block = True
                think_lines.append(line)
            elif is_in_cot_block:
                if line.startswith("#") or (line.strip() and not line.startswith("*") and not line.startswith("-") and ":" not in line and len(line) > 20):
                    is_in_cot_block = False
                    answer_lines.append(line)
                else:
                    think_lines.append(line)
            else:
                answer_lines.append(line)

        if not think_part and think_lines:
            think_part = "\n".join(think_lines).replace("<think>", "").replace("</think>", "").strip()

        if answer_lines:
            answer_part = "\n".join(answer_lines).replace("<think>", "").replace("</think>", "").strip()
        else:
            answer_part = text.replace("<think>", "").replace("</think>", "").strip()

    answer_part = answer_part.replace("<think>", "").replace("</think>", "").strip()
    # 🟢 CJK 한자 치환 및 잔여 한자 정제 가드레일 적용
    answer_part = clean_hanja_and_artifacts(answer_part)

    if show_think and think_part:
        return f"🧠 [AI 생각 과정 <think>]:\n{think_part}\n\n💬 [AI 최종 답변]:\n{answer_part}"
    
    return answer_part


def load_sample_config() -> dict:
    """환경변수 및 설정에서 로컬 게이트웨이 및 모델 토폴로지 설정을 로드합니다."""
    host = os.getenv("SERVER_HOST") or os.getenv("MODEL_GATEWAY_HOST") or "http://vllm-serv-gateway"
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"

    main_port = int(os.getenv("MAIN_PORT", os.getenv("MODEL_GATEWAY_PORT", 8081)))
    embed_port = int(os.getenv("EMBED_PORT", os.getenv("EMBEDDING_PORT", 8090)))
    rerank_port = int(os.getenv("RERANK_PORT", 8091))
    default_model = os.getenv("DEFAULT_MODEL", "qwen3.5-4b")

    config = {
        "server_host": host,
        "main_port": main_port,
        "embed_port": embed_port,
        "embedding_port": embed_port,
        "rerank_port": rerank_port,
        "default_model": default_model,
        "fast_model": os.getenv("FAST_LLM_MODEL", "qwen3.5-4b"),
        "synthesis_model": os.getenv("SYNTHESIS_LLM_MODEL", "qwen3.5-4b"),
        "synthesis_model_alt": os.getenv("SYNTHESIS_LLM_MODEL_ALT", "qwen3.5-9b"),
        "max_9b_budget": int(os.getenv("MAX_9B_CONTEXT_BUDGET", "1500")),
        "embedding_model": os.getenv("EMBEDDING_MODEL", "bge-m3"),
        "rerank_model": os.getenv("RERANK_MODEL", "bge-reranker-v2-m3"),
        "default_temperature": 0.3,
        "default_max_tokens": 1024
    }
    return config


def get_fast_model() -> str:
    """일반/전처리/의도분류용 모델(qwen3.5-2b)을 반환합니다."""
    return os.getenv("FAST_LLM_MODEL", "qwen3.5-2b")


def get_synthesis_model(use_alt_9b: bool = False) -> str:
    """최종 RAG 문서 합성용 고품질 모델(qwen3.5-4b)을 반환합니다."""
    if use_alt_9b or os.getenv("USE_9B_MODEL", "0") == "1":
        return os.getenv("SYNTHESIS_LLM_MODEL_ALT", "qwen3.5-9b")
    return os.getenv("SYNTHESIS_LLM_MODEL", os.getenv("DEFAULT_MODEL", "qwen3.5-4b"))


def budget_context_documents(
    products: list, 
    model_name: str = "qwen3.5-4b", 
    max_budget_chars: int = 1500, 
    max_sentence_len: int = 150,
    max_total_chars: Optional[int] = None,
    **kwargs
) -> list:
    """
    RAG 프롬프트에 주입할 검색 문서의 길이를 모델 컨텍스트 윈도우에 맞게 트리밍하는 가드레일 (FR-016).
    - qwen3.5-4b (2K~4K n_ctx): 총 1,500자/토큰 이내로 엄격 제한하여 컨텍스트 오버플로우 방어
    """
    if "is_9b" in kwargs:
        is_9b = bool(kwargs["is_9b"])
    else:
        is_9b = "9b" in str(model_name).lower()

    custom_budget = kwargs.get("budget") or max_total_chars or max_budget_chars
    default_budget = int(os.getenv("MAX_9B_CONTEXT_BUDGET", "1500")) if is_9b else 3500
    budget = custom_budget or default_budget
    if max_budget_chars and max_budget_chars < budget:
        budget = max_budget_chars

    budgeted_products = []
    current_length = 0

    for p in products:
        # 객체 또는 딕셔너리 지원
        if hasattr(p, "separated_sentence"):
            sentence = getattr(p, "separated_sentence", "") or ""
            p_name = getattr(p, "product_name", "") or ""
            rank = getattr(p, "rank", 1)
            brand = getattr(p, "brand_name", "")
            cat = getattr(p, "category", "")
            disp = getattr(p, "display_name", "")
            sent = getattr(p, "sentiment_label", "")
            cos = getattr(p, "cosine_similarity", 0.0)
            rerank = getattr(p, "rerank_score", 0.0)
        elif isinstance(p, dict):
            sentence = p.get("separated_sentence", "") or ""
            p_name = p.get("product_name", "") or ""
            rank = p.get("rank", 1)
            brand = p.get("brand_name", "")
            cat = p.get("category", "")
            disp = p.get("display_name", "")
            sent = p.get("sentiment_label", "")
            cos = p.get("cosine_similarity", 0.0)
            rerank = p.get("rerank_score", 0.0)
        else:
            sentence = str(p)
            p_name = ""
            rank, brand, cat, disp, sent, cos, rerank = 1, "", "", "", "", 0.0, 0.0

        # 9B 모델인 경우 개별 문장도 150자 이내로 간결화
        if is_9b and len(sentence) > max_sentence_len:
            sentence = sentence[:max_sentence_len - 3] + "..."

        entry_len = len(sentence) + len(p_name) + 30
        if current_length + entry_len > budget and budgeted_products:
            # 예산 초과 시 상위 문서만 채택하고 중단
            break

        if isinstance(p, RecommendedProduct):
            trimmed_p = RecommendedProduct(
                rank=rank, product_name=p_name, brand_name=brand, category=cat,
                separated_sentence=sentence, display_name=disp, sentiment_label=sent,
                cosine_similarity=cos, rerank_score=rerank
            )
            budgeted_products.append(trimmed_p)
        elif isinstance(p, dict):
            trimmed_dict = dict(p)
            trimmed_dict["separated_sentence"] = sentence
            budgeted_products.append(trimmed_dict)
        else:
            budgeted_products.append(p)

        current_length += entry_len

    return budgeted_products


def check_server_health(base_url: str = None) -> bool:
    """서버 헬스체크를 수행합니다."""
    if not base_url:
        cfg = load_sample_config()
        base_url = f"{cfg['server_host']}:{cfg['main_port']}"
    try:
        r = httpx.get(f"{base_url}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def get_httpx_client(timeout: float = 30.0) -> httpx.Client:
    """표준 httpx 클라이언트를 생성합니다."""
    return httpx.Client(timeout=timeout)


def print_section_header(title: str):
    print(f"\n{'='*60}\n{title}\n{'='*60}")


def print_performance_summary(duration_sec: float, token_count: int = 0):
    print(f"⏱️ 소요 시간: {duration_sec:.2f}초 | 토큰: {token_count}")


# ==============================================================================
# 🟢 [실시간 RAG 파이프라인 진행 상태 및 SSE 이벤트 스키마]
# ==============================================================================
from enum import Enum
from dataclasses import dataclass, field


class PipelinePhase(str, Enum):
    INTENT_ANALYSIS = "INTENT_ANALYSIS"   # Phase 1: 질문 의도 및 화장품 속성 분석
    HYBRID_SEARCH = "HYBRID_SEARCH"       # Phase 2: 리뷰 하이브리드 검색 (BM25 + BGE-M3)
    RERANKING = "RERANKING"               # Phase 3: BGE-Reranker 순위 재정렬
    LLM_SYNTHESIS = "LLM_SYNTHESIS"       # Phase 4: LLM 심층 분석 및 맞춤 답변 생성
    COMPLETED = "COMPLETED"               # Phase 5: 종합 분석 완료
    ERROR = "ERROR"                       # 에러/장애 상태


@dataclass
class StepEvent:
    phase: PipelinePhase
    label: str
    status: str = "running"  # "running" | "complete" | "warning" | "error"
    elapsed_sec: float = 0.0
    progress_percent: int = 0
    message: Optional[str] = None
    extra_data: Optional[dict] = None


@dataclass
class ReferenceReview:
    rank: int
    product_name: str
    brand_name: str
    category: str
    review_score: int
    attribute_tag: str
    sentiment_label: str
    separated_sentence: str
    rerank_score: float = 0.0


@dataclass
class RagExecutionMetadata:
    total_latency_sec: float
    searched_review_count: int
    selected_review_count: int
    model_used: str
    fallback_triggered: bool = False
    reference_reviews: List[ReferenceReview] = field(default_factory=list)


@dataclass
class FallbackRecommendation:
    retry_query: str
    suggested_chips: List[str]
    error_message: str


def clean_product_name_for_search(raw_name: str, brand_name: str = "") -> str:
    """
    올리브영 공식몰 검색 정확도 극대화를 위해 기획/증정/용량/색상 등 프로모션 노이즈를 정규식으로 제거하고
    [브랜드명 + 핵심 상품명]을 추출합니다.
    """
    import re
    if not raw_name:
        return (brand_name or "").strip()

    text = raw_name
    text = re.sub(r"\[.*?\]", " ", text)
    text = re.sub(r"\(.*?\)", " ", text)

    noise_patterns = [
        r"\b\d+\+\d+\b",
        r"\b\d+(ml|g|EA|매|입|개)\b",
        r"\b\d+호\b",
        r"기획세트|단독기획|스페셜기획|리필기획|증정기획",
        r"본품|리필|더블기획|트리플기획|한정판",
        r"대용량|미니|샘플|파우치증정",
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    text = re.sub(r"[^\w\s가-힣a-zA-Z0-9]", " ", text)
    text = " ".join(text.split()).strip()

    if brand_name and brand_name.strip():
        b_clean = brand_name.strip()
        if not text.startswith(b_clean):
            text = f"{b_clean} {text}"

    return text.strip() or ((brand_name or "").strip() if brand_name else (raw_name or "").strip())


def build_oliveyoung_search_url(product_name: str, brand_name: str = "") -> str:
    """올리브영 공식몰 정밀 검색 URL 생성"""
    import urllib.parse
    clean_query = clean_product_name_for_search(product_name, brand_name)
    encoded = urllib.parse.quote_plus(clean_query)
    return f"https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query={encoded}"



