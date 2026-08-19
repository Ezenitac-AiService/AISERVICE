"""
Unit Tests for Korean Markdown Normalization (normalize_korean_markdown).
Spec 017: 한국어 마크다운 볼드 렌더링 최적화 및 프롬프트 고도화

Tests validate that CommonMark right-flanking delimiter collisions
caused by Korean postpositions (조사) are properly sanitized.
"""

import time
import unittest
import sys
import os

# Ensure oliview_core is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "bteam")))

from oliview_core.sanitizer import normalize_korean_markdown


class TestNormalizeKoreanMarkdownQuoteBoldPostposition(unittest.TestCase):
    """Test Case 1: **"인용구"**조사 패턴 → <strong> 또는 공백 보정"""

    def test_double_quote_with_raneun(self):
        """**"자극 느껴져요"**라는 → 볼드 정상 렌더링"""
        inp = '**"자극 느껴져요"**라는 피드백'
        out = normalize_korean_markdown(inp)
        self.assertNotIn('**"', out)
        self.assertIn("자극 느껴져요", out)
        self.assertIn("라는", out)

    def test_double_quote_with_irago(self):
        """**"효과는 일반 토너랑 비슷함"**이라고 → 볼드 정상 렌더링"""
        inp = '**"효과는 일반 토너랑 비슷함"**이라고 평했습니다'
        out = normalize_korean_markdown(inp)
        self.assertNotIn('**"', out)
        self.assertIn("이라고", out)

    def test_single_quote_with_neun(self):
        """**'오일리한 토너에요'**라는 → 볼드 정상 렌더링"""
        inp = "**'오일리한 토너에요'**라는 평이 나왔습니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**'", out)
        self.assertIn("라는", out)


class TestNormalizeKoreanMarkdownBoldPostposition(unittest.TestCase):
    """Test Case 2: **텍스트**조사 패턴 → <strong> 또는 공백 보정"""

    def test_bold_with_eun(self):
        """**수분감**은 → 볼드 정상 렌더링"""
        inp = "**수분감**은 좋은 편입니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**수분감**은", out)
        self.assertIn("수분감", out)
        self.assertIn("은", out)

    def test_bold_with_i(self):
        """**발림성**이 → 볼드 정상 렌더링"""
        inp = "**발림성**이 좋습니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**발림성**이", out)
        self.assertIn("발림성", out)

    def test_bold_with_ga(self):
        """**지속력**가 → 볼드 정상 렌더링"""
        inp = "**지속력**가 아쉽습니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**지속력**가", out)

    def test_bold_with_eul(self):
        """**흡수력**을 → 볼드 정상 렌더링"""
        inp = "**흡수력**을 테스트했습니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**흡수력**을", out)

    def test_bold_with_reul(self):
        """**톤업효과**를 → 볼드 정상 렌더링"""
        inp = "**톤업효과**를 확인했습니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**톤업효과**를", out)

    def test_bold_with_eseo(self):
        """**스킨케어**에서 → 볼드 정상 렌더링"""
        inp = "**스킨케어**에서 인기가 많습니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**스킨케어**에서", out)

    def test_bold_with_euro(self):
        """**성분**으로 → 볼드 정상 렌더링"""
        inp = "**성분**으로 구성되어 있습니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**성분**으로", out)

    def test_bold_with_ro(self):
        """**보습제**로 → 볼드 정상 렌더링"""
        inp = "**보습제**로 추천합니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**보습제**로", out)

    def test_bold_with_wa(self):
        """**수분감**과 → 볼드 정상 렌더링"""
        inp = "**수분감**과 **발림성**은 좋습니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**수분감**과", out)
        self.assertNotIn("**발림성**은", out)

    def test_bold_with_do(self):
        """**자극성**도 → 볼드 정상 렌더링"""
        inp = "**자극성**도 낮은 편입니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**자극성**도", out)

    def test_bold_with_man(self):
        """**향**만 → 볼드 정상 렌더링"""
        inp = "**향**만 아쉽습니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**향**만", out)

    def test_bold_with_buteo(self):
        """**기초**부터 → 볼드 정상 렌더링"""
        inp = "**기초**부터 사용하세요"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**기초**부터", out)

    def test_bold_with_kkaji(self):
        """**마무리**까지 → 볼드 정상 렌더링"""
        inp = "**마무리**까지 촉촉합니다"
        out = normalize_korean_markdown(inp)
        self.assertNotIn("**마무리**까지", out)


class TestNormalizeKoreanMarkdownSafePatterns(unittest.TestCase):
    """Test Case 3: 정상 마크다운은 변경하지 않아야 함 (Safe Patterns Preserved)"""

    def test_standard_label_colon_format(self):
        """- **수분감:** 촉촉합니다 → 변경 없음"""
        inp = "- **수분감:** 촉촉합니다"
        out = normalize_korean_markdown(inp)
        self.assertIn("**수분감:**", out)

    def test_standalone_bold(self):
        """**좋습니다** → 변경 없음 (뒤에 공백 또는 없음)"""
        inp = "이 제품은 **좋습니다** 라고 합니다"
        out = normalize_korean_markdown(inp)
        self.assertIn("**좋습니다**", out)

    def test_plain_text_unchanged(self):
        """일반 텍스트 → 변경 없음"""
        inp = "일반 텍스트 문장입니다."
        out = normalize_korean_markdown(inp)
        self.assertEqual(inp, out)

    def test_empty_string(self):
        """빈 문자열 → 빈 문자열 반환"""
        self.assertEqual(normalize_korean_markdown(""), "")

    def test_none_input(self):
        """None 입력 → 빈 문자열 반환"""
        self.assertEqual(normalize_korean_markdown(None), "")

    def test_code_block_not_affected(self):
        """코드 블록 내 ** → 변경 없음"""
        inp = "`**코드**`는 정상입니다"
        out = normalize_korean_markdown(inp)
        # 코드 블록 내부의 별표는 변경되면 안 됨
        self.assertIn("`", out)

    def test_bold_with_space_after(self):
        """**텍스트** 조사 (공백 있음) → 정상 유지"""
        inp = "**텍스트** 는 좋습니다"
        out = normalize_korean_markdown(inp)
        self.assertIn("**텍스트**", out)


class TestNormalizeKoreanMarkdownPerformance(unittest.TestCase):
    """Test Case 4: 정규화 처리 오버헤드 1ms 미만 보장"""

    def test_performance_under_1ms(self):
        """1000자 텍스트 정규화 속도 < 1ms"""
        sample = '**"자극 느껴져요"**라는 피드백. ' * 50
        start = time.perf_counter()
        for _ in range(100):
            normalize_korean_markdown(sample)
        elapsed_avg_ms = ((time.perf_counter() - start) / 100) * 1000
        self.assertLess(elapsed_avg_ms, 1.0, f"평균 {elapsed_avg_ms:.3f}ms > 1ms 초과!")
        print(f"[PERF] Average normalization time: {elapsed_avg_ms:.4f}ms (under 1ms PASS)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
