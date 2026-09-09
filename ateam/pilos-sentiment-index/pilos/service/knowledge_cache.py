"""PILOS 정적 서비스 지식(15개 질문 블록)에 대한 인메모리 정본 캐시."""

from typing import Any, Final

_SERVICE_DOC_SOURCE: Final[dict[str, str]] = {
    "type": "service_document",
    "label": "PILOS 서비스 문서",
    "version": "1.0",
}

SERVICE_KNOWLEDGE_CACHE: Final[dict[str, dict[str, Any]]] = {
    "service_overview": {
        "status": "ready",
        "answer": (
            "**PILOS 서비스 개요**\n\n"
            "PILOS(Platform for Investor Sentiment & Order-flow Study)는 온라인 종목 토론방의 "
            "투자자 감성(댓글 표현)과 실제 개인투자자의 시장 수급(매수·매도·수급지수) 간의 연관성을 "
            "통계 및 머신러닝 모델로 분석하고 연구하는 금융 인공지능 연구 플랫폼입니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "service_research_target": {
        "status": "ready",
        "answer": (
            "**PILOS 연구 대상**\n\n"
            "PILOS는 네이버 종목 토론방 등에서 수집된 비정형 댓글 텍스트 데이터와 "
            "한국거래소 및 키움증권의 확정 개인투자자 일별 수급 데이터(매수량, 매도량, 수급지수)를 "
            "연결하여 연구합니다. 투자자들의 언어적 감성 표현이 실제 시장 참여자의 수급 행동으로 "
            "어떻게 이어지는지 그 연관 강도를 규명하는 것이 핵심 연구 목적입니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "service_models": {
        "status": "ready",
        "answer": (
            "**두 방향 분석 모델 (Positive / Negative)**\n\n"
            "PILOS는 시장 심리의 비대칭성을 정확히 포착하기 위해 **Positive 모델**과 **Negative 모델**의 "
            "두 방향 모델을 독립적으로 운영합니다.\n\n"
            "- **Positive 모델**: 긍정적 어휘 및 상승 기대 표현이 개인 순매수 수급에 미치는 영향 분석\n"
            "- **Negative 모델**: 부정적 어휘 및 하락 공포 표현이 개인 순매도 수급에 미치는 영향 분석\n\n"
            "이를 통해 단순한 긍/부정 단일 점수로는 설명하기 어려운 시장의 다면적 반응을 정밀하게 분리해 제시합니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "service_positive_model": {
        "status": "ready",
        "answer": (
            "**Positive 모델**\n\n"
            "Positive 모델은 종목 토론방의 댓글 중 상승 기대, 매수 유입, 호재성 표현 등 "
            "긍정적인 어휘들이 개인투자자의 실제 매수 수급에 미친 기여도와 연관 강도를 분석합니다. "
            "개인투자자들의 적극적인 매수 심리 반응을 확인하는 데 활용됩니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "service_negative_model": {
        "status": "ready",
        "answer": (
            "**Negative 모델**\n\n"
            "Negative 모델은 종목 토론방 댓글의 하락 우려, 손절매, 악재성 공포 표현 등 "
            "부정적인 어휘들이 개인투자자의 실제 매도 수급에 미친 기여도와 연관 강도를 분석합니다. "
            "시장 내 위험 회피 및 매도 심리의 분출 강도를 측정하는 지표입니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "service_model_difference": {
        "status": "ready",
        "answer": (
            "**두 모델의 차이점**\n\n"
            "1. **분석 대상 수급**: Positive 모델은 매수량 및 긍정 연관성을, Negative 모델은 매도량 및 부정 연관성을 각각 독립적으로 학습합니다.\n"
            "2. **시장 심리의 비대칭성 반영**: 일반적인 주식 시장에서는 호재에 대한 매수 반응과 악재에 대한 매도 반응의 강도와 속도가 다릅니다. PILOS는 두 모델을 분리하여 호재와 악재에 대한 반응 차이를 명확히 비교할 수 있습니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "service_score_calculation": {
        "status": "ready",
        "answer": (
            "**점수 계산 방식**\n\n"
            "PILOS의 모델 점수는 다음과 같은 승인된 요소를 결합하여 계산됩니다:\n\n"
            "1. **댓글 어휘 기여도**: 수집된 댓글 내 단어들의 TF-IDF 및 사전 가중치 기여도 합산\n"
            "2. **분석 댓글 수 보정**: 표본 크기에 따른 신뢰도 보정\n"
            "3. **모델 절편(Intercept)**: 기본 기준선 반영\n"
            "4. **정규화**: 이상치 왜곡을 방지한 최종 정규화 지수 산출"
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "service_interpretation": {
        "status": "ready",
        "answer": (
            "**분석 결과 해석 방법**\n\n"
            "PILOS의 분석 지표는 과거 및 현재 시점의 댓글 표현과 실제 개인 수급 데이터 간의 "
            "통계적 연관성을 보여주는 연구 지표입니다.\n\n"
            "> **[유의사항]**: 본 서비스는 특정 종목의 미래 주가 상승/하락을 보장하거나 매수·매도를 추천하는 "
            "투자 권유가 아닙니다. 시장 참여자들의 심리적 동향과 수급 흐름을 입체적으로 이해하기 위한 "
            "보조 연구 참고자료로 활용하시기 바랍니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "service_columns": {
        "status": "ready",
        "answer": (
            "**주요 데이터 항목 안내**\n\n"
            "- **분석 기준일**: 분석 대상이 되는 시장 거래일\n"
            "- **댓글 표현 점수**: 텍스트 분석을 통해 산출된 감성 표현 강도\n"
            "- **분석 댓글 수**: 해당 일자에 수집되어 분석에 반영된 유효 댓글 수\n"
            "- **수급지수**: 개인투자자 매수/매도 균형을 나타내는 정규화 지표\n"
            "- **개인 매수량**: 해당 일자의 확정 개인투자자 총 매수 체결량(주)\n"
            "- **개인 매도량**: 해당 일자의 확정 개인투자자 총 매도 체결량(주)"
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "service_cautions": {
        "status": "ready",
        "answer": (
            "**분석 시 유의사항**\n\n"
            "1. **투자 자문 아님**: PILOS의 모든 분석 수치는 과거 데이터에 기반한 통계적 연구 결과이며, 미래 수익을 보장하지 않습니다.\n"
            "2. **데이터 한계**: 비정형 텍스트의 특성상 비유나 반어법, 봇 댓글 등에 의해 실제 감성과 오차가 발생할 수 있습니다.\n"
            "3. **독립적 판단**: 투자에 관한 최종 결정과 책임은 전적으로 투자자 본인에게 있습니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "column_model_date": {
        "status": "ready",
        "answer": (
            "**분석 기준일**\n\n"
            "댓글 수집 및 개인투자자 수급 집계의 기준이 되는 특정 주식 시장 거래일(YYYY-MM-DD)을 의미합니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "column_text_score": {
        "status": "ready",
        "answer": (
            "**댓글 표현 점수**\n\n"
            "기준일 토론방 댓글 텍스트에 나타난 긍정 또는 부정 감성 어휘의 강도를 모델 알고리즘으로 수치화한 점수입니다. "
            "미래 주가 예측 확률이 아닌, 해당일 투자자들의 언어적 표현 강도를 나타냅니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "column_comment_count": {
        "status": "ready",
        "answer": (
            "**분석 댓글 수**\n\n"
            "해당 거래일에 수집되어 데이터 정제 과정을 거친 후 감성 분석 모델에 실제로 입력된 유효 댓글의 총 개수입니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "column_supply_index": {
        "status": "ready",
        "answer": (
            "**수급지수**\n\n"
            "확정된 개인투자자의 매수량과 매도량을 바탕으로 계산된 상대적 수급 균형 지표입니다. "
            "값이 클수록 매수세 우위를, 작을수록 매도세 우위를 나타냅니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "column_buy_volume": {
        "status": "ready",
        "answer": (
            "**개인 매수량**\n\n"
            "한국거래소에서 공시된 해당 거래일 개인투자자의 총 매수 체결 주식 수(주)입니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
    "column_sell_volume": {
        "status": "ready",
        "answer": (
            "**개인 매도량**\n\n"
            "한국거래소에서 공시된 해당 거래일 개인투자자의 총 매도 체결 주식 수(주)입니다."
        ),
        "route": "service_knowledge",
        "sources": [_SERVICE_DOC_SOURCE],
        "warnings": [],
    },
}


def is_cached_service_block(block_key: str | None) -> bool:
    """주어진 질문 키가 정본 지식 캐시에 존재하는지 확인한다."""
    if not block_key:
        return False
    return block_key in SERVICE_KNOWLEDGE_CACHE


def get_cached_service_knowledge(block_key: str) -> dict[str, Any] | None:
    """정본 지식 캐시에서 질문 블록에 대응하는 정본 응답을 반환한다."""
    entry = SERVICE_KNOWLEDGE_CACHE.get(block_key)
    if entry is None:
        return None
    # 반환 객체의 불변성을 보장하기 위해 얕은 복사본 반환
    return {
        "status": entry["status"],
        "answer": entry["answer"],
        "route": entry["route"],
        "sources": list(entry["sources"]),
        "warnings": list(entry["warnings"]),
    }
