"""
Test for Feature 047 (User Story 3):
Verify L5 cache poison prevention gate and review text bracket sanitization.
"""

import pytest
from oliview_core.nodes.synthesis_node import is_valid_synthesis_response
from oliview_core.sanitizer import clean_review_sentence


def test_is_valid_synthesis_response_blocks_error_messages():
    """Verify that error messages and timeout tokens are strictly blocked from L5 caching."""
    # 1. Error messages
    assert not is_valid_synthesis_response("\n[답변 생성 오류: timed out]")
    assert not is_valid_synthesis_response("Error: Connection closed unexpectedly by peer")
    assert not is_valid_synthesis_response("Exception occurred during inference: CUDA OOM")
    assert not is_valid_synthesis_response("Traceback (most recent call last): line 45")
    assert not is_valid_synthesis_response("[답변 생성 오류: 504 Gateway Timeout]")

    # 2. Too short / truncated responses
    assert not is_valid_synthesis_response("안녕하세요")
    assert not is_valid_synthesis_response("")
    assert not is_valid_synthesis_response(None)


def test_is_valid_synthesis_response_allows_legitimate_answers():
    """Verify that legitimate comprehensive answers pass the validation gate."""
    valid_answer = (
        "### 🌿 1. 차앤박(CNP) 프로폴리스 에너지 액티브 앰플\n"
        "- **수분감 및 영양 공급**: 끈적임 없이 피부 속 깊은 곳까지 촉촉하게 수분을 채워주며 "
        "피부 진정에도 뛰어난 효과가 있습니다 [차앤박 프로폴리스 앰플 리뷰 1].\n"
        "- **사용감**: 흡수가 빠르고 산뜻하여 메이크업 전 사용하기 좋습니다 [차앤박 프로폴리스 앰플 리뷰 2]."
    )
    assert is_valid_synthesis_response(valid_answer)


def test_clean_review_sentence_strips_leading_bracket_and_tags():
    """Verify that leading brackets, dangling ']' and promo category tags are cleanly removed."""
    # Case 1: Raw sentence with category prefix tag
    raw1 = "[스킨케어] 차앤박 앰플 수분감과 흡수력이 정말 좋아요!"
    assert clean_review_sentence(raw1) == "차앤박 앰플 수분감과 흡수력이 정말 좋아요!"

    # Case 2: Raw sentence with promo package and dangling bracket
    raw2 = "브링그린 알로에 97% 수딩젤 (2입/쿨러/단품)] 여름을 겪은 지친 피부에 도움 되는 느낌"
    assert clean_review_sentence(raw2) == "여름을 겪은 지친 피부에 도움 되는 느낌"

    # Case 3: Dangling leading bracket
    raw3 = "] 피부 진정과 보습에 최고입니다."
    assert clean_review_sentence(raw3) == "피부 진정과 보습에 최고입니다."

    # Case 4: Pure text without brackets
    raw4 = "순하고 자극 없이 촉촉해서 매일 사용하고 있어요."
    assert clean_review_sentence(raw4) == "순하고 자극 없이 촉촉해서 매일 사용하고 있어요."
