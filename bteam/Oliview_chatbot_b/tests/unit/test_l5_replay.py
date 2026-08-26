"""
Unit & Contract Test for L5 Cache Streaming Replay (Spec 032).
Tests Word-Boundary token stream generation, chunk delay, and full text fidelity.
"""

import pytest
import asyncio
import time
from oliview_core.redis_pool import replay_cached_stream


@pytest.mark.asyncio
async def test_replay_cached_stream_fidelity():
    payload = {
        "response_text": (
            "### 🌿 차앤박 프로폴리스 에너지 액티브 앰플 분석\n\n"
            "- **주요 효능**: 고농축 프로폴리스 추출물이 함유되어 지친 피부에 풍부한 영양과 꿀광 보습을 공급합니다.\n"
            "- **사용감 및 제형**: 끈적임 없이 쫀쫀하게 밀착 흡수되어 메이크업 전 속건조 개선에 탁월합니다."
        )
    }

    collected = []
    t0 = time.perf_counter()
    async for chunk in replay_cached_stream(payload, chunk_delay_s=0.005):
        collected.append(chunk)
    elapsed = time.perf_counter() - t0

    reassembled = "".join(collected)
    assert reassembled == payload["response_text"], "Replay된 전체 텍스트가 원문과 100% 일치해야 함"
    assert len(collected) > 1, f"단어 단위로 여러 청크로 분할되어야 함 (현재 {len(collected)}개)"
    assert elapsed >= 0.005 * (len(collected) - 1), "청크 딜레이가 정상 반영되어야 함"
