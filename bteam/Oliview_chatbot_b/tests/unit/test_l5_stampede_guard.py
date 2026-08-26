"""
Unit Test Suite for User Story 3 (Spec 032):
SingleFlight Concurrency Stampede Protection & Poisoning Deny-List.
"""

import pytest
import time
from oliview_core.redis_pool import (
    L5SingleFlightLock,
    is_poisoned_or_invalid_response,
    set_l5_response,
    get_l5_response,
    build_l5_key,
)


def test_single_flight_lock_lifecycle():
    """US3: 1개 워커가 락을 획득하면 동시 요청자는 락 획득 실패 검증"""
    cache_key = "test_q_12345"

    # 1. First worker acquires lock
    acquired_1 = L5SingleFlightLock.acquire(cache_key)
    assert acquired_1 is True, "첫 번째 워커는 락을 성공적으로 획득해야 함"

    # 2. Second concurrent worker tries to acquire same lock
    acquired_2 = L5SingleFlightLock.acquire(cache_key)
    assert acquired_2 is False, "동시 인입된 두 번째 워커는 락 획득에 실패해야 함"

    # 3. Release lock
    L5SingleFlightLock.release(cache_key)

    # 4. Third worker can acquire after release
    acquired_3 = L5SingleFlightLock.acquire(cache_key)
    assert acquired_3 is True, "해제 후 신규 요청자는 락 획득이 가능해야 함"
    L5SingleFlightLock.release(cache_key)


def test_cache_poisoning_rejection():
    """US3: 에러 및 불완전 응답은 set_l5_response에서 커밋 거부됨을 검증"""
    key = build_l5_key("chata", "테스트 인젝션 질의", ["doc1"])

    error_payload = {
        "response_text": "일시적인 오류가 발생하여 답변을 생성할 수 없습니다.",
        "model_id": "qwen3.5-2b",
        "created_at": time.time(),
    }
    result = set_l5_response(key, error_payload)
    assert result is False, "에러성 응답은 Redis에 저장되지 않아야 함"

    cached = get_l5_response(key)
    assert cached is None, "저장 실패 후 조회 시 None이어야 함"
