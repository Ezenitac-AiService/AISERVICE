# tests/test_chatb_noise_filter.py
"""
올원챗 B (FastAPI / Web UI) 상품명 노이즈 정제 및 올리브영 URL 유효성 검증
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "bteam" / "Oliview_chatbot_b"))

from bteam.Oliview_chatbot_b.common import (
    clean_product_name_for_search,
    build_oliveyoung_search_url,
)


def test_chatb_noise_filter_variations():
    cases = [
        (
            "[단독기획] 컬러그램 탕후루 탱글 꿀로스 2종 기획세트 (+미니글로스 증정)",
            "컬러그램",
            "컬러그램 탕후루 탱글 꿀로스 2종",
        ),
        (
            "[1+1기획] 식물나라 산소수 워터프루프 선크림 60ml 더블기획",
            "식물나라",
            "식물나라 산소수 워터프루프 선크림",
        ),
        (
            "헤라 블랙쿠션 SPF34 PA++ 본품 15g + 리필 15g [21호]",
            "헤라",
            "헤라 블랙쿠션 SPF34 PA",
        ),
    ]

    for raw, brand, expected_prefix in cases:
        cleaned = clean_product_name_for_search(raw, brand)
        assert expected_prefix in cleaned, f"Expected '{expected_prefix}' in '{cleaned}'"
        assert "기획세트" not in cleaned
        assert "증정" not in cleaned
        assert "1+1" not in cleaned

        url = build_oliveyoung_search_url(raw, brand)
        assert "https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query=" in url
        print(f"[PASS] Noise clean verified for: {raw[:30]}... -> {cleaned}")


if __name__ == "__main__":
    test_chatb_noise_filter_variations()
    print("[SUCCESS] All test_chatb_noise_filter.py tests passed!")
