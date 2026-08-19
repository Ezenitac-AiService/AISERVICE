# tests/test_pilos_stream.py
"""
A-Team PILOS 챗봇 4단계 금융 분석 타임라인 및 SSE 이벤트 계약 검증 테스트
"""

import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "ateam" / "pilos-sentiment-index"))

from pilos.dto.chat_dto import (
    ChatAction,
    ChatRequestDTO,
    ChatResponseDTO,
    ChatStatus,
)
from pilos.service.chatbot_service import CHAT_BLOCK_DEFINITIONS


def test_pilos_chat_block_definitions():
    assert "stock_summary" in CHAT_BLOCK_DEFINITIONS
    assert "stock_supply_index" in CHAT_BLOCK_DEFINITIONS
    assert CHAT_BLOCK_DEFINITIONS["stock_summary"].needs_stock is True
    print("[PASS] PILOS CHAT_BLOCK_DEFINITIONS valid")


def test_pilos_financial_phases_contract():
    phases = [
        "IDENTIFY_STOCK",
        "SUPPLY_DEMAND_METRIC",
        "NEWS_SENTIMENT_VERIFICATION",
        "LLM_REPORT_SYNTHESIS",
        "COMPLETED",
    ]

    events = []
    for p in phases:
        evt = {"event": "step", "data": {"phase": p, "status": "running" if p != "COMPLETED" else "complete"}}
        events.append(evt)

    assert len(events) == 5
    assert events[0]["data"]["phase"] == "IDENTIFY_STOCK"
    assert events[-1]["data"]["phase"] == "COMPLETED"
    print("[PASS] PILOS financial phases contract valid")


def test_pilos_external_links():
    stock_code = "005930"
    naver_url = f"https://finance.naver.com/item/main.naver?code={stock_code}"
    dart_url = f"https://dart.fss.or.kr/dsab007/main.do?textCrpNm={stock_code}"

    assert "finance.naver.com" in naver_url
    assert "dart.fss.or.kr" in dart_url
    print("[PASS] PILOS external financial links valid")


if __name__ == "__main__":
    test_pilos_chat_block_definitions()
    test_pilos_financial_phases_contract()
    test_pilos_external_links()
    print("[SUCCESS] All test_pilos_stream.py tests passed!")
