# bteam/Oliview_chatbot_a/common/step_callback.py
"""
Oliview 챗봇 RAG 파이프라인 수명 주기 이벤트 및 콜백 프로토콜 정의
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class PipelinePhase(str, Enum):
    """RAG 파이프라인 단계 열거형"""
    INTENT_ANALYSIS = "INTENT_ANALYSIS"   # Phase 1: 질문 의도 및 화장품 속성 분석
    HYBRID_SEARCH = "HYBRID_SEARCH"       # Phase 2: 리뷰 하이브리드 검색 (BM25 + BGE-M3)
    RERANKING = "RERANKING"               # Phase 3: BGE-Reranker 순위 재정렬
    LLM_SYNTHESIS = "LLM_SYNTHESIS"       # Phase 4: LLM 심층 분석 및 맞춤 답변 생성
    COMPLETED = "COMPLETED"               # Phase 5: 종합 분석 완료
    ERROR = "ERROR"                       # 에러/장애 상태


@dataclass
class StepEvent:
    """실시간 단계 진행 상태 이벤트 데이터"""
    phase: PipelinePhase
    label: str
    status: str = "running"  # "running" | "complete" | "warning" | "error"
    elapsed_sec: float = 0.0
    progress_percent: int = 0
    message: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None


@dataclass
class ReferenceReview:
    """답변 근거 상위 선별 리뷰 원문"""
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
    """RAG 파이프라인 최종 실행 메타데이터"""
    total_latency_sec: float
    searched_review_count: int
    selected_review_count: int
    model_used: str
    fallback_triggered: bool = False
    reference_reviews: List[ReferenceReview] = field(default_factory=list)


@dataclass
class FallbackRecommendation:
    """0건 검색 또는 에러 시 복구용 추천 칩 데이터"""
    retry_query: str
    suggested_chips: List[str]
    error_message: str


@runtime_checkable
class StepCallbackProtocol(Protocol):
    """RAG 파이프라인 단계별 이벤트 수신 프로토콜"""

    def on_step(self, event: StepEvent) -> None:
        """새로운 단계 진입 또는 상태 변경 시 호출"""
        ...

    def on_token(self, token: str) -> None:
        """4단계 LLM 답변 토큰 생성 시 실시간 호출"""
        ...

    def on_complete(self, metadata: RagExecutionMetadata) -> None:
        """전체 RAG 파이프라인 완료 시 메타데이터와 함께 호출"""
        ...

    def on_error(self, error_event: StepEvent, recommendation: Optional[FallbackRecommendation] = None) -> None:
        """예외 또는 검색 0건 발생 시 호출"""
        ...


import re
import urllib.parse


def clean_product_name_for_search(raw_name: str, brand_name: str = "") -> str:
    """
    올리브영 공식몰 검색 정확도 극대화를 위해 기획/증정/용량/색상 등 프로모션 노이즈를 정규식으로 제거하고
    [브랜드명 + 핵심 상품명]을 추출합니다.
    """
    if not raw_name:
        return (brand_name or "").strip()

    text = raw_name
    # 1. 대괄호 및 소괄호 내 프로모션 문구 제거: [단독기획], [1+1], (증정...), (미니...)
    text = re.sub(r"\[.*?\]", " ", text)
    text = re.sub(r"\(.*?\)", " ", text)

    # 2. 기획세트, 리필, 한정판, 대용량, 증정 등의 단어 제거
    noise_patterns = [
        r"\b\d+\+\d+\b",            # 1+1, 2+1
        r"\b\d+(ml|g|EA|매|입|개)\b", # 50ml, 100g, 2EA
        r"\b\d+호\b",                # 01호, 21호
        r"기획세트|단독기획|스페셜기획|리필기획|증정기획",
        r"본품|리필|더블기획|트리플기획|한정판",
        r"대용량|미니|샘플|파우치증정",
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    # 3. 특수문자 및 연속 공백 정리
    text = re.sub(r"[^\w\s가-힣a-zA-Z0-9]", " ", text)
    text = " ".join(text.split()).strip()

    # 4. 브랜드명이 포함되지 않은 경우 브랜드명 접두
    if brand_name and brand_name.strip():
        b_clean = brand_name.strip()
        if not text.startswith(b_clean):
            text = f"{b_clean} {text}"

    return text.strip() or ((brand_name or "").strip() if brand_name else (raw_name or "").strip())


def build_oliveyoung_search_url(product_name: str, brand_name: str = "") -> str:
    """올리브영 공식몰 정밀 검색 URL 생성"""
    clean_query = clean_product_name_for_search(product_name, brand_name)
    encoded = urllib.parse.quote_plus(clean_query)
    return f"https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query={encoded}"

