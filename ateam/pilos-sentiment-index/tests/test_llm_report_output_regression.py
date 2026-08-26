import unittest

from datetime import date

from pilos.analysis.llm_report import (
    _SUPPLY_DIRECTION_SENTENCES,
    ALLOWED_MOVING_AVERAGE_LABELS,
    MOVING_AVERAGE_LABEL,
    build_deterministic_commentary,
    classify_supply_state,
    describe_signal_level,
    describe_signal_pattern,
    validate_market_commentary_response,
)
from pilos.dto.llm_report_dto import (
    LlmMarketCommentary,
    LlmSignalEvidence,
    ReportGenerationRequest,
)


# market_commentary_v8 실출력 검토(10종목)에서 사용한 입력값이다.
# 신호 계산 결과는 변경하지 않고 표현 계약만 v9로 강화했으므로
# 같은 입력으로 회귀를 고정한다.
STOCK_FIXTURES = (
    {
        "stock_name": "삼성전자",
        "stock_code": "005930",
        "supply_direction": "BUY",
        "actual_supply_index": 0.1951,
        "comment_signal_score": 87,
        "signal_level": "매우 높음",
        "previous_signal_score": 56,
        "signal_change": 31,
        "signal_ma5": 66,
        "comment_count": 1830,
    },
    {
        "stock_name": "SK하이닉스",
        "stock_code": "000660",
        "supply_direction": "BUY",
        "actual_supply_index": 0.1204,
        "comment_signal_score": 75,
        "signal_level": "높음",
        "previous_signal_score": 53,
        "signal_change": 22,
        "signal_ma5": 59,
        "comment_count": 1420,
    },
    {
        "stock_name": "LG에너지솔루션",
        "stock_code": "373220",
        "supply_direction": "BUY",
        "actual_supply_index": 0.0812,
        "comment_signal_score": 70,
        "signal_level": "높음",
        "previous_signal_score": 60,
        "signal_change": 10,
        "signal_ma5": 65,
        "comment_count": 610,
    },
    {
        "stock_name": "NAVER",
        "stock_code": "035420",
        "supply_direction": "SELL",
        "actual_supply_index": -0.1033,
        "comment_signal_score": 21,
        "signal_level": "낮음",
        "previous_signal_score": 30,
        "signal_change": -9,
        "signal_ma5": 28,
        "comment_count": 480,
    },
    {
        "stock_name": "카카오",
        "stock_code": "035720",
        "supply_direction": "SELL",
        "actual_supply_index": -0.0721,
        "comment_signal_score": 33,
        "signal_level": "낮음",
        "previous_signal_score": 41,
        "signal_change": -8,
        "signal_ma5": 37,
        "comment_count": 990,
    },
    {
        "stock_name": "현대차",
        "stock_code": "005380",
        "supply_direction": "BUY",
        "actual_supply_index": 0.0402,
        "comment_signal_score": 43,
        "signal_level": "보통",
        "previous_signal_score": 50,
        "signal_change": -7,
        "signal_ma5": 48,
        "comment_count": 720,
    },
    {
        "stock_name": "기아",
        "stock_code": "000270",
        "supply_direction": "BUY",
        "actual_supply_index": 0.0955,
        "comment_signal_score": 58,
        "signal_level": "보통",
        "previous_signal_score": 58,
        "signal_change": 0,
        "signal_ma5": 58,
        "comment_count": 430,
    },
    {
        "stock_name": "포스코홀딩스",
        "stock_code": "005490",
        "supply_direction": "SELL",
        "actual_supply_index": -0.1877,
        "comment_signal_score": 39,
        "signal_level": "낮음",
        "previous_signal_score": 9,
        "signal_change": 30,
        "signal_ma5": 55,
        "comment_count": 1150,
    },
    {
        "stock_name": "셀트리온",
        "stock_code": "068270",
        "supply_direction": "SELL",
        "actual_supply_index": -0.0288,
        "comment_signal_score": 12,
        "signal_level": "매우 낮음",
        "previous_signal_score": 24,
        "signal_change": -12,
        "signal_ma5": 19,
        "comment_count": 260,
    },
    {
        "stock_name": "KB금융",
        "stock_code": "105560",
        "supply_direction": "BUY",
        "actual_supply_index": 0.3120,
        "comment_signal_score": 92,
        "signal_level": "매우 높음",
        "previous_signal_score": 88,
        "signal_change": 4,
        "signal_ma5": 92,
        "comment_count": 340,
    },
)


def build_fixture_request(fixture: dict) -> ReportGenerationRequest:
    evidence = LlmSignalEvidence(
        actual_supply_index=fixture["actual_supply_index"],
        supply_direction=fixture["supply_direction"],
        signal_status="ready",
        comment_signal_score=fixture["comment_signal_score"],
        signal_level=fixture["signal_level"],
        comment_count=fixture["comment_count"],
        previous_signal_score=fixture["previous_signal_score"],
        signal_change=fixture["signal_change"],
        signal_ma5=fixture["signal_ma5"],
    )
    return ReportGenerationRequest(
        daily_document_id=1,
        positive_result_id=1,
        negative_result_id=2,
        stock_id=1,
        stock_code=fixture["stock_code"],
        stock_name=fixture["stock_name"],
        model_date=date(2026, 8, 7),
        comment_count=fixture["comment_count"],
        supply_state=classify_supply_state(fixture["actual_supply_index"]),
        active_model_variant=(
            "positive" if fixture["supply_direction"] == "BUY" else "negative"
        ),
        predicted_score=0.42,
        recognized_feature_count=120,
        evidence=evidence,
        model_name="ridge_supply",
        model_version=4,
        artifact_schema_version=2,
        calibration_schema_version=1,
        provider="academy",
        model="qwen3.5-4b",
    )


def find_fixture(stock_name: str) -> dict:
    for fixture in STOCK_FIXTURES:
        if fixture["stock_name"] == stock_name:
            return fixture

    raise KeyError(stock_name)


def request_for(stock_name: str) -> ReportGenerationRequest:
    return build_fixture_request(find_fixture(stock_name))


class V8OutputRegressionTest(unittest.TestCase):
    """
    v8 실출력 검토에서 확인된 오류를 v9 검증이 차단하는지 고정한다.

    실제 LLM 서버 응답을 재현할 수 없으므로 관측된 출력 문장을 그대로
    fixture로 사용한다.
    """

    def assert_rejected(self, *, stock_name, market_commentary, conclusion):
        request = request_for(stock_name)
        response = LlmMarketCommentary(
            market_commentary=market_commentary,
            conclusion=conclusion,
        )
        with self.assertRaises(ValueError) as caught:
            validate_market_commentary_response(
                request=request,
                response=response,
            )
        return str(caught.exception)

    def test_samsung_change_anchored_to_moving_average(self):
        message = self.assert_rejected(
            stock_name="삼성전자",
            market_commentary=(
                "삼성전자는 개인투자자 매수 우위입니다. "
                "직전 5거래일 평균 66점을 기준으로 현재는 31포인트 "
                "상승한 87점의 매우 높음 수준입니다."
            ),
            conclusion=(
                "삼성전자는 매수 우위이며 오늘 신호는 매우 높음 수준입니다."
            ),
        )
        self.assertIn("평균으로 서술했습니다", message)

    def test_samsung_past_average_alias(self):
        message = self.assert_rejected(
            stock_name="삼성전자",
            market_commentary=(
                "삼성전자는 개인투자자 매수 우위입니다. "
                "과거 평균 신호 수준인 66점을 기준으로 현재는 매우 높음 "
                "수준입니다."
            ),
            conclusion=(
                "삼성전자는 매수 우위이며 오늘 신호는 매우 높음 수준입니다."
            ),
        )
        self.assertIn("다른 통계처럼", message)

    def test_lg_energy_conclusion_turns_high_into_neutral(self):
        message = self.assert_rejected(
            stock_name="LG에너지솔루션",
            market_commentary=(
                "LG에너지솔루션은 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 70점으로 높음 수준입니다. "
                "직전 거래일보다 10포인트 상승했습니다."
            ),
            conclusion=(
                "댓글 수급 신호가 중립 수준으로 조정된 하루였습니다."
            ),
        )
        self.assertIn("중립", message)

    def test_naver_low_becomes_very_low(self):
        message = self.assert_rejected(
            stock_name="NAVER",
            market_commentary=(
                "NAVER는 개인투자자 매도 우위입니다. "
                "댓글 수급 신호는 21점으로 매우 낮은 수준입니다. "
                "직전 거래일보다 9포인트 하락했습니다."
            ),
            conclusion=(
                "NAVER는 매도 우위이며 오늘 신호는 낮음 수준입니다."
            ),
        )
        self.assertIn("다른 등급으로 표현했습니다", message)

    def test_posco_merges_opposite_relations(self):
        message = self.assert_rejected(
            stock_name="포스코홀딩스",
            market_commentary=(
                "포스코홀딩스는 개인투자자 매도 우위입니다. "
                "댓글 수급 신호는 39점으로 낮음 수준입니다. "
                "직전 거래일 대비 30포인트 상승하여 과거 평균보다 "
                "약화되었습니다."
            ),
            conclusion=(
                "포스코홀딩스는 매도 우위이며 오늘 신호는 낮음 수준입니다."
            ),
        )
        self.assertIn("다른 통계처럼", message)

    def test_hyundai_normal_becomes_low_with_price_pressure(self):
        message = self.assert_rejected(
            stock_name="현대차",
            market_commentary=(
                "현대차는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 43점으로 낮은 수준이며 주가 상승 "
                "압력이 약화되었습니다."
            ),
            conclusion=(
                "현대차는 매수 우위이며 오늘 신호는 보통 수준입니다."
            ),
        )
        self.assertIn("주가 상승", message)

    def test_supply_direction_stated_in_reverse(self):
        message = self.assert_rejected(
            stock_name="카카오",
            market_commentary=(
                "카카오는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 33점으로 낮음 수준입니다."
            ),
            conclusion=(
                "카카오는 매도 우위이며 오늘 신호는 낮음 수준입니다."
            ),
        )
        self.assertIn("실제 수급 방향과 반대로", message)

    def test_stiff_wording_is_no_longer_rejected(self):
        # v11부터 문체는 검증하지 않는다. 사실이 맞으면 통과한다.
        validate_market_commentary_response(
            request=request_for("카카오"),
            response=LlmMarketCommentary(
                market_commentary=(
                    "카카오의 수급 방향은 매도 우위로 설정되어 있습니다. "
                    "댓글 수급 신호는 33점으로 낮음 수준입니다."
                ),
                conclusion=(
                    "카카오는 개인투자자 매도 우위이며 오늘 신호는 "
                    "낮음 수준입니다."
                ),
            ),
        )


class DeterministicOutputRegressionTest(unittest.TestCase):
    """10종목 deterministic 출력이 v9 표현 계약을 모두 만족하는지 본다."""

    def test_every_fixture_passes_its_own_validation(self):
        for fixture in STOCK_FIXTURES:
            with self.subTest(stock_name=fixture["stock_name"]):
                request = build_fixture_request(fixture)
                validate_market_commentary_response(
                    request=request,
                    response=build_deterministic_commentary(request),
                )

    def test_every_fixture_states_input_level_verbatim(self):
        for fixture in STOCK_FIXTURES:
            with self.subTest(stock_name=fixture["stock_name"]):
                request = build_fixture_request(fixture)
                commentary = build_deterministic_commentary(request)

                self.assertIn(
                    f"{fixture['comment_signal_score']}점으로 "
                    f"{describe_signal_level(fixture['signal_level'])}",
                    commentary.market_commentary,
                )

    def test_every_fixture_separates_both_comparisons(self):
        for fixture in STOCK_FIXTURES:
            with self.subTest(stock_name=fixture["stock_name"]):
                request = build_fixture_request(fixture)
                text = build_deterministic_commentary(
                    request
                ).market_commentary
                change = fixture["signal_change"]

                if change > 0:
                    self.assertIn(f"어제보다 {change}점 높아졌", text)
                elif change < 0:
                    self.assertIn(f"어제보다 {abs(change)}점 낮아졌", text)
                else:
                    self.assertIn("어제와 같은 수준", text)

                self.assertIn(EASY_MOVING_AVERAGE_LABEL, text)

    def test_opposite_relations_are_not_merged(self):
        # 전일 대비 상승이지만 5거래일 평균보다는 낮은 사례다.
        request = request_for("포스코홀딩스")
        text = build_deterministic_commentary(request).market_commentary

        self.assertIn("어제보다 30점 높아졌지만", text)
        self.assertIn(
            f"{EASY_MOVING_AVERAGE_LABEL} 55점보다는 낮습니다",
            text,
        )
        self.assertIn(
            "어제보다는 올라왔지만 최근 5일 평균보다는 아직 낮은",
            text,
        )
        for merged in ("강화", "약화", "때문", "따라서"):
            with self.subTest(merged=merged):
                self.assertNotIn(merged, text)

    def test_equal_comparisons_are_stated_as_same_level(self):
        request = request_for("기아")
        text = build_deterministic_commentary(request).market_commentary

        self.assertIn("어제와 같은 수준이고", text)
        self.assertIn(
            f"{EASY_MOVING_AVERAGE_LABEL} 58점과 비슷한 수준입니다",
            text,
        )

    def test_topic_particle_follows_korean_pronunciation(self):
        cases = {
            "삼성전자": "삼성전자는",
            "NAVER": "NAVER는",
            "LG에너지솔루션": "LG에너지솔루션은",
            "셀트리온": "셀트리온은",
            "KB금융": "KB금융은",
        }
        for stock_name, expected in cases.items():
            with self.subTest(stock_name=stock_name):
                text = build_deterministic_commentary(
                    request_for(stock_name)
                ).market_commentary

                self.assertTrue(text.startswith(expected))

    def test_no_price_direction_or_stiff_wording(self):
        forbidden = (
            "상승 신호",
            "하락 신호",
            "주가",
            "중립",
            "관측",
            "설정",
            "평가",
        )
        for fixture in STOCK_FIXTURES:
            request = build_fixture_request(fixture)
            commentary = build_deterministic_commentary(request)
            narrative = (
                f"{commentary.market_commentary} {commentary.conclusion}"
            )

            for phrase in forbidden:
                with self.subTest(
                    stock_name=fixture["stock_name"],
                    phrase=phrase,
                ):
                    self.assertNotIn(phrase, narrative)


if __name__ == "__main__":
    unittest.main()


# market_commentary_v10 검토용 추가 종목이다. 실제 수급은 매수 우위지만
# 댓글 신호는 매우 낮은 상반 조합을 확인하기 위해 넣었다.
DOOSAN_FIXTURE = {
    "stock_name": "두산에너빌리티",
    "stock_code": "034020",
    "supply_direction": "BUY",
    "actual_supply_index": 0.1102,
    "comment_signal_score": 1,
    "signal_level": "매우 낮음",
    "previous_signal_score": 70,
    "signal_change": -69,
    "signal_ma5": 48,
    "comment_count": 880,
}

# deterministic 요약이 v12에서 쓰는 쉬운 평균 명칭이다.
EASY_MOVING_AVERAGE_LABEL = ALLOWED_MOVING_AVERAGE_LABELS[3]

VALID_CONCLUSION = (
    "오늘 댓글 수급 신호의 핵심 관계를 한 문장으로 정리했습니다."
)


class SignalPatternTest(unittest.TestCase):
    """교차 관계 판정이 두 비교를 하나로 합치지 않는지 본다."""

    def test_four_patterns_are_distinguished(self):
        cases = (
            ("삼성전자", "어제보다도 최근 5일 평균보다도 높은 상태"),
            ("NAVER", "어제보다도 최근 5일 평균보다도 낮은 상태"),
            (
                "포스코홀딩스",
                "어제보다는 올라왔지만 최근 5일 평균보다는 아직 낮은 상태",
            ),
        )
        for stock_name, expected in cases:
            with self.subTest(stock_name=stock_name):
                self.assertEqual(
                    describe_signal_pattern(request_for(stock_name)),
                    expected,
                )

    def test_fall_but_still_above_average_is_kept_as_two_relations(self):
        fixture = {
            **find_fixture("현대차"),
            "comment_signal_score": 55,
            "signal_level": "보통",
            "previous_signal_score": 62,
            "signal_change": -7,
            "signal_ma5": 48,
        }
        self.assertEqual(
            describe_signal_pattern(build_fixture_request(fixture)),
            "어제보다는 낮아졌지만 최근 5일 평균보다는 여전히 높은 상태",
        )


class V10AllowedExpressionTest(unittest.TestCase):
    """
    v10에서 새로 허용한 관계 종합 표현이 통과하는지 고정한다.

    지시서 §12의 권장 출력을 그대로 fixture로 사용한다.
    """

    def assert_accepted(self, *, request, market_commentary, conclusion):
        validate_market_commentary_response(
            request=request,
            response=LlmMarketCommentary(
                market_commentary=market_commentary,
                conclusion=conclusion,
            ),
        )

    def test_samsung_synthesis_is_allowed(self):
        self.assert_accepted(
            request=request_for("삼성전자"),
            market_commentary=(
                "삼성전자는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 87점으로 매우 높으며, 전일보다 "
                "31포인트 올라 최근 5거래일 평균 66점도 크게 웃돌고 "
                "있습니다."
            ),
            conclusion=(
                "삼성전자는 개인투자자 매수 우위에서 댓글 수급 신호가 "
                "전일과 최근 평균을 모두 크게 웃돕니다."
            ),
        )

    def test_posco_crossed_relation_is_allowed(self):
        self.assert_accepted(
            request=request_for("포스코홀딩스"),
            market_commentary=(
                "포스코홀딩스는 개인투자자 매도 우위입니다. "
                "댓글 수급 신호는 39점으로 낮지만 전일보다 30포인트 크게 "
                "회복했습니다. 다만 최근 5거래일 평균 55점에는 아직 못 "
                "미쳐, 최근 흐름과 비교하면 신호 강도는 낮은 편입니다."
            ),
            conclusion=(
                "포스코홀딩스는 개인투자자 매도 우위이며, 댓글 신호는 "
                "전일보다 크게 회복했지만 최근 평균에는 아직 못 미칩니다."
            ),
        )

    def test_doosan_opposite_combination_is_allowed(self):
        self.assert_accepted(
            request=build_fixture_request(DOOSAN_FIXTURE),
            market_commentary=(
                "두산에너빌리티는 개인투자자 매수 우위지만 댓글 수급 "
                "신호는 1점으로 매우 낮습니다. 전일보다 69포인트 급감했고 "
                "최근 5거래일 평균 48점에도 크게 못 미쳐, 현재 매수 우위 "
                "방향의 댓글 신호는 최근보다 상당히 약한 상태입니다."
            ),
            conclusion=(
                "두산에너빌리티는 개인투자자 매수 우위이지만 댓글 수급 "
                "신호는 1점으로 매우 낮은 수준입니다."
            ),
        )

    def test_previous_absolute_score_wording_is_allowed(self):
        self.assert_accepted(
            request=request_for("삼성전자"),
            market_commentary=(
                "삼성전자는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 87점으로 매우 높으며, 전일 56점에서 "
                "현재 87점까지 올랐습니다. 최근 5거래일 평균 66점도 "
                "웃돕니다."
            ),
            conclusion=(
                "삼성전자는 개인투자자 매수 우위이며 댓글 신호가 전일과 "
                "최근 평균을 모두 웃돕니다."
            ),
        )

    def test_recent_label_variant_is_allowed(self):
        self.assert_accepted(
            request=request_for("NAVER"),
            market_commentary=(
                "NAVER는 개인투자자 매도 우위입니다. 댓글 수급 신호는 "
                "21점으로 낮으며, 전일보다 9포인트 내려 최근 5거래일 "
                "평균 28점에도 못 미칩니다."
            ),
            conclusion=(
                "NAVER는 개인투자자 매도 우위이며 댓글 신호가 전일과 최근 "
                "평균에 모두 못 미칩니다."
            ),
        )

    def test_small_change_can_be_called_maintained(self):
        fixture = {
            **find_fixture("기아"),
            "comment_signal_score": 58,
            "previous_signal_score": 56,
            "signal_change": 2,
            "signal_ma5": 57,
        }
        self.assert_accepted(
            request=build_fixture_request(fixture),
            market_commentary=(
                "기아는 개인투자자 매수 우위입니다. 댓글 수급 신호는 "
                "58점으로 보통 수준을 유지했고, 직전 거래일보다 2포인트 "
                "올랐습니다."
            ),
            conclusion=(
                "기아는 개인투자자 매수 우위이며 댓글 신호가 보통 수준에 "
                "머물렀습니다."
            ),
        )


class V10ForbiddenExpressionTest(unittest.TestCase):
    """v10에서 새로 막은 표현이 차단되는지 고정한다."""

    def assert_rejected(self, *, request, market_commentary):
        response = LlmMarketCommentary(
            market_commentary=market_commentary,
            conclusion=VALID_CONCLUSION,
        )
        with self.assertRaises(ValueError) as caught:
            validate_market_commentary_response(
                request=request,
                response=response,
            )
        return str(caught.exception)

    def test_moving_average_trend_claim_is_rejected(self):
        cases = (
            "최근 5거래일 평균도 상승했습니다.",
            "5거래일 평균이 강화됐습니다.",
            "직전 5거래일 평균도 올랐습니다.",
        )
        for text in cases:
            with self.subTest(text=text):
                message = self.assert_rejected(
                    request=request_for("삼성전자"),
                    market_commentary=(
                        "삼성전자는 개인투자자 매수 우위입니다. "
                        "댓글 수급 신호는 87점으로 매우 높으며 "
                        f"{text}"
                    ),
                )
                self.assertIn("평균 자체의 변화", message)

    def test_trend_wording_on_other_subjects_is_rejected(self):
        cases = (
            "매수세가 크게 강해졌습니다.",
            "저가 매수 심리가 회복됐습니다.",
            "투자 심리가 악화됐습니다.",
        )
        for text in cases:
            with self.subTest(text=text):
                message = self.assert_rejected(
                    request=request_for("삼성전자"),
                    market_commentary=(
                        "삼성전자는 개인투자자 매수 우위입니다. "
                        "댓글 수급 신호는 87점으로 매우 높으며 "
                        f"{text}"
                    ),
                )
                self.assertIn(
            ("수급 강도의 변화" if "매수세" in text or "매도세" in text
             else "확인할 수 없는 대상"),
            message,
        )

    def test_maintained_wording_is_allowed_after_large_move(self):
        """v13은 상태가 이어진다는 서술을 '유지' 단어만으로 막지 않는다."""
        request = request_for("삼성전자")
        validate_market_commentary_response(
            request=request,
            response=LlmMarketCommentary(
                market_commentary=(
                    "삼성전자는 현재 개인투자자의 매수가 더 많습니다. "
                    "댓글 수급 신호는 87점으로 매우 높은 수준을 "
                    "유지하고 있습니다."
                ),
                conclusion=VALID_CONCLUSION,
            ),
        )

    def test_unchanged_score_claim_is_rejected(self):
        message = self.assert_rejected(
            request=request_for("삼성전자"),
            market_commentary=(
                "삼성전자는 현재 개인투자자의 매수가 더 많습니다. "
                "댓글 수급 신호는 87점으로 어제와 같은 점수입니다."
            ),
        )
        self.assertIn("그대로라고 서술했습니다", message)

    def test_regime_change_wording_is_rejected(self):
        message = self.assert_rejected(
            request=request_for("삼성전자"),
            market_commentary=(
                "삼성전자는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 87점으로 매우 높은 등급으로 "
                "전환됐습니다."
            ),
        )
        self.assertIn("전환 여부를 확인할 수 없습니다", message)

    def test_price_expectation_is_still_rejected(self):
        cases = (
            "주가 상승 가능성이 높습니다.",
            "반등 가능성이 있습니다.",
            "상승세가 이어질 것으로 보입니다.",
            "저가 매수 심리 덕분에 올랐습니다.",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assert_rejected(
                    request=request_for("삼성전자"),
                    market_commentary=(
                        "삼성전자는 개인투자자 매수 우위입니다. "
                        "댓글 수급 신호는 87점으로 매우 높으며 "
                        f"{text}"
                    ),
                )


class V10DeterministicStyleTest(unittest.TestCase):
    """deterministic 요약이 필드 낭독에서 벗어났는지 본다."""

    def test_aligned_case_uses_two_sentences(self):
        text = build_deterministic_commentary(
            request_for("삼성전자")
        ).market_commentary
        sentences = [part for part in text.split(". ") if part.strip()]

        self.assertEqual(len(sentences), 2)

    def test_crossed_case_states_both_relations(self):
        text = build_deterministic_commentary(
            request_for("포스코홀딩스")
        ).market_commentary

        self.assertIn("높아졌지만", text)
        self.assertIn("보다는 낮습니다", text)
        self.assertIn("올라왔지만", text)

    def test_conclusion_prefers_crossed_relation(self):
        conclusion = build_deterministic_commentary(
            request_for("포스코홀딩스")
        ).conclusion

        self.assertIn(
            "어제보다는 올라왔지만 최근 5일 평균보다는 아직 낮은",
            conclusion,
        )

    def test_doosan_opposite_combination_passes_validation(self):
        request = build_fixture_request(DOOSAN_FIXTURE)
        commentary = build_deterministic_commentary(request)

        validate_market_commentary_response(
            request=request,
            response=commentary,
        )
        self.assertIn(
            "현재 개인투자자의 매수가 더 많고",
            commentary.market_commentary,
        )
        self.assertIn("1점으로 매우 낮은 편", commentary.market_commentary)


# market_commentary_v12 작업 지시서 §27의 문장 계약이다.
# 표현은 쉬운 쪽으로 열되 사실 모순은 그대로 막는지 고정한다.
V12_BASE_FIXTURE = {
    "stock_name": "삼성전자",
    "stock_code": "005930",
    "comment_count": 1830,
}


def v12_request(
    *,
    supply_direction: str,
    comment_signal_score: int,
    signal_level: str,
    previous_signal_score: int,
    signal_change: int,
    signal_ma5: int,
) -> ReportGenerationRequest:
    return build_fixture_request(
        {
            **V12_BASE_FIXTURE,
            "supply_direction": supply_direction,
            "actual_supply_index": (
                0.21 if supply_direction == "BUY" else -0.21
            ),
            "comment_signal_score": comment_signal_score,
            "signal_level": signal_level,
            "previous_signal_score": previous_signal_score,
            "signal_change": signal_change,
            "signal_ma5": signal_ma5,
        }
    )


V12_CONCLUSION = "어제와 최근 평균을 함께 보면 관계가 분명히 드러납니다."


class V12PlainWordingTest(unittest.TestCase):
    """쉬운 표현을 문체만으로 폐기하지 않는지 고정한다."""

    def assert_accepted(self, request, market_commentary, conclusion=None):
        validate_market_commentary_response(
            request=request,
            response=LlmMarketCommentary(
                market_commentary=market_commentary,
                conclusion=conclusion or V12_CONCLUSION,
            ),
        )

    def assert_rejected(self, request, market_commentary, conclusion=None):
        with self.assertRaises(ValueError):
            validate_market_commentary_response(
                request=request,
                response=LlmMarketCommentary(
                    market_commentary=market_commentary,
                    conclusion=conclusion or V12_CONCLUSION,
                ),
            )

    def test_plain_sentences_are_accepted(self):
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=70,
            signal_level="높음",
            previous_signal_score=60,
            signal_change=10,
            signal_ma5=62,
        )
        for sentence in (
            "최근 평균보다 높은 편입니다.",
            "오늘은 개인투자자의 매도가 더 많았습니다.",
            "어제보다 10점 높아졌습니다.",
        ):
            with self.subTest(sentence=sentence):
                self.assert_accepted(
                    request,
                    "댓글 신호는 70점으로 높은 편입니다. " + sentence,
                )

    def test_plain_downward_sentences_are_accepted(self):
        request = v12_request(
            supply_direction="BUY",
            comment_signal_score=30,
            signal_level="낮음",
            previous_signal_score=45,
            signal_change=-15,
            signal_ma5=52,
        )
        for sentence in (
            "최근 평균보다 낮은 편입니다.",
            "어제보다 15점 낮아졌습니다.",
            "오늘은 개인투자자의 매수가 더 많았습니다.",
        ):
            with self.subTest(sentence=sentence):
                self.assert_accepted(
                    request,
                    "댓글 신호는 30점으로 낮은 편입니다. " + sentence,
                )

    def test_style_words_alone_do_not_reject(self):
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=10,
            signal_level="매우 낮음",
            previous_signal_score=19,
            signal_change=-9,
            signal_ma5=15,
        )
        for sentence in (
            "댓글 신호는 10점으로 약세를 보입니다.",
            "댓글 신호는 10점으로 매우 낮은 수준을 유지했습니다.",
            "최근 5일 평균 15점을 하회합니다.",
            "종합적으로 낮은 흐름입니다.",
        ):
            with self.subTest(sentence=sentence):
                self.assert_accepted(
                    request,
                    "오늘은 개인투자자의 매도가 더 많았습니다. " + sentence,
                )

    def test_same_level_maintenance_is_allowed(self):
        """등급 구간이 같으면 '유지'와 '이어지고'는 사실과 어긋나지 않는다."""
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=10,
            signal_level="매우 낮음",
            previous_signal_score=19,
            signal_change=-9,
            signal_ma5=15,
        )
        self.assert_accepted(
            request,
            "오늘은 개인투자자의 매도가 더 많았습니다. "
            "댓글 신호는 10점으로 매우 낮은 수준을 유지했습니다.",
            conclusion="낮은 수준이 계속 이어지고 있는 모습입니다.",
        )


class V12FactContradictionTest(unittest.TestCase):
    """문체를 열어도 사실 모순은 계속 막는지 고정한다."""

    def assert_rejected(self, request, market_commentary):
        with self.assertRaises(ValueError):
            validate_market_commentary_response(
                request=request,
                response=LlmMarketCommentary(
                    market_commentary=market_commentary,
                    conclusion=V12_CONCLUSION,
                ),
            )

    def test_supply_direction_reversal_is_rejected(self):
        sell = v12_request(
            supply_direction="SELL",
            comment_signal_score=70,
            signal_level="높음",
            previous_signal_score=60,
            signal_change=10,
            signal_ma5=62,
        )
        self.assert_rejected(
            sell,
            "오늘은 개인투자자의 매수가 더 많았습니다. "
            "댓글 신호는 70점으로 높은 편입니다.",
        )

        buy = v12_request(
            supply_direction="BUY",
            comment_signal_score=30,
            signal_level="낮음",
            previous_signal_score=45,
            signal_change=-15,
            signal_ma5=52,
        )
        self.assert_rejected(
            buy,
            "오늘은 개인투자자의 매도가 더 많았습니다. "
            "댓글 신호는 30점으로 낮은 편입니다.",
        )

    def test_average_relation_reversal_is_rejected(self):
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=39,
            signal_level="낮음",
            previous_signal_score=9,
            signal_change=30,
            signal_ma5=55,
        )
        self.assert_rejected(
            request,
            "오늘은 개인투자자의 매도가 더 많았습니다. "
            "최근 5일 평균 55점보다 높은 수준입니다.",
        )

    def test_change_direction_reversal_is_rejected(self):
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=40,
            signal_level="보통",
            previous_signal_score=60,
            signal_change=-20,
            signal_ma5=45,
        )
        self.assert_rejected(
            request,
            "오늘은 개인투자자의 매도가 더 많았습니다. "
            "어제보다 20점 올랐습니다.",
        )

    def test_direction_and_score_confusion_is_rejected(self):
        sell = v12_request(
            supply_direction="SELL",
            comment_signal_score=62,
            signal_level="높음",
            previous_signal_score=55,
            signal_change=7,
            signal_ma5=58,
        )
        self.assert_rejected(sell, "오늘 개인투자자 매도 우위가 62점입니다.")
        self.assert_rejected(
            sell,
            "오늘은 개인투자자의 매도가 더 많아 62점입니다.",
        )

        buy = v12_request(
            supply_direction="BUY",
            comment_signal_score=65,
            signal_level="높음",
            previous_signal_score=60,
            signal_change=5,
            signal_ma5=61,
        )
        self.assert_rejected(buy, "오늘 개인투자자 매수 우위가 65점입니다.")

    def test_invented_price_fact_is_rejected(self):
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=70,
            signal_level="높음",
            previous_signal_score=60,
            signal_change=10,
            signal_ma5=62,
        )
        self.assert_rejected(
            request,
            "오늘은 개인투자자의 매도가 더 많았습니다. "
            "주가 상승을 이끌었습니다.",
        )

    def test_maintenance_across_levels_is_rejected(self):
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=40,
            signal_level="보통",
            previous_signal_score=60,
            signal_change=-20,
            signal_ma5=45,
        )
        self.assert_rejected(
            request,
            "오늘은 개인투자자의 매도가 더 많았습니다. "
            "높은 수준을 유지했습니다.",
        )

    def test_direction_switch_claim_is_rejected(self):
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=70,
            signal_level="높음",
            previous_signal_score=60,
            signal_change=10,
            signal_ma5=62,
        )
        self.assert_rejected(
            request,
            "오늘은 개인투자자의 매도가 더 많았습니다. 매도로 전환됐습니다.",
        )

    def test_level_reclassification_is_still_rejected(self):
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=30,
            signal_level="낮음",
            previous_signal_score=45,
            signal_change=-15,
            signal_ma5=52,
        )
        self.assert_rejected(
            request,
            "오늘은 개인투자자의 매도가 더 많았습니다. "
            "댓글 신호는 30점으로 매우 낮은 수준입니다.",
        )


class V13PresentTenseTest(unittest.TestCase):
    """
    develop 통합 baseline의 문체 계약이다.

    수급 방향은 해당 거래일의 현재 상태이므로 현재형으로 보고하고,
    등급은 자연스러운 한국어로 풀어 쓴다.
    """

    def test_direction_sentences_are_present_tense(self):
        for direction, expected in (
            ("BUY", "현재는 개인투자자의 매수가 더 많습니다"),
            ("SELL", "현재는 개인투자자의 매도가 더 많습니다"),
        ):
            with self.subTest(direction=direction):
                self.assertEqual(
                    _SUPPLY_DIRECTION_SENTENCES[direction],
                    expected,
                )

    def test_deterministic_avoids_past_tense_direction(self):
        for fixture in STOCK_FIXTURES:
            with self.subTest(stock_name=fixture["stock_name"]):
                commentary = build_deterministic_commentary(
                    build_fixture_request(fixture)
                )
                narrative = (
                    f"{commentary.market_commentary} {commentary.conclusion}"
                )

                self.assertIn("현재 개인투자자의", narrative)
                for past in (
                    "많았습니다",
                    "많았고",
                    "우위였습니다",
                    "오늘은",
                ):
                    with self.subTest(past=past):
                        self.assertNotIn(past, narrative)

    def test_deterministic_uses_natural_level_wording(self):
        for fixture in STOCK_FIXTURES:
            with self.subTest(stock_name=fixture["stock_name"]):
                text = build_deterministic_commentary(
                    build_fixture_request(fixture)
                ).market_commentary

                self.assertIn(
                    describe_signal_level(fixture["signal_level"]),
                    text,
                )
                for mechanical in (
                    "높음 편",
                    "낮음 편",
                    "매우 높음 편",
                    "매우 낮음 편",
                    "보통 편",
                ):
                    with self.subTest(mechanical=mechanical):
                        self.assertNotIn(mechanical, text)

    def test_natural_level_map_covers_every_band(self):
        expected = {
            "매우 높음": "매우 높은 편",
            "높음": "높은 편",
            "보통": "보통 수준",
            "낮음": "낮은 편",
            "매우 낮음": "매우 낮은 편",
        }
        for label, natural in expected.items():
            with self.subTest(label=label):
                self.assertEqual(describe_signal_level(label), natural)

    def test_present_tense_wording_passes_validation(self):
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=48,
            signal_level="보통",
            previous_signal_score=37,
            signal_change=11,
            signal_ma5=52,
        )
        for commentary in (
            "현재는 개인투자자의 매도가 더 많습니다. "
            "댓글 수급 신호는 48점으로 보통 수준입니다.",
            "현재 개인투자자는 매도 쪽이 더 많습니다. "
            "댓글 신호는 48점으로 보통 수준입니다.",
        ):
            with self.subTest(commentary=commentary):
                validate_market_commentary_response(
                    request=request,
                    response=LlmMarketCommentary(
                        market_commentary=commentary,
                        conclusion=V12_CONCLUSION,
                    ),
                )


class V13FalsePositiveTest(unittest.TestCase):
    """v12 실적재에서 오탐으로 걸렀던 정상 문장을 통과시킨다."""

    def setUp(self):
        # 현재 48 / 어제 37 / 변화 +11 / 5일 평균 52
        self.request = v12_request(
            supply_direction="SELL",
            comment_signal_score=48,
            signal_level="보통",
            previous_signal_score=37,
            signal_change=11,
            signal_ma5=52,
        )

    def accept(self, market_commentary, conclusion=None):
        validate_market_commentary_response(
            request=self.request,
            response=LlmMarketCommentary(
                market_commentary=market_commentary,
                conclusion=conclusion or V12_CONCLUSION,
            ),
        )

    def test_change_and_average_in_one_sentence(self):
        self.accept(
            "현재는 개인투자자의 매도가 더 많습니다. "
            "어제보다 11점 높아졌지만 최근 5거래일 평균인 52점보다는 "
            "낮습니다."
        )

    def test_average_clause_first_is_not_treated_as_change_baseline(self):
        self.accept(
            "현재는 개인투자자의 매도가 더 많습니다. "
            "최근 5거래일 평균인 52점보다는 낮지만 어제보다 11점 "
            "높아졌습니다."
        )

    def test_abstract_maintenance_wording_is_allowed(self):
        for sentence in (
            "보통 수준을 유지하고 있습니다.",
            "비슷한 수준이 이어지고 있습니다.",
        ):
            with self.subTest(sentence=sentence):
                self.accept(
                    "현재는 개인투자자의 매도가 더 많습니다. " + sentence
                )


class V13SemanticErrorTest(unittest.TestCase):
    """v12가 놓쳤던 의미 오류를 차단한다."""

    def reject(self, request, market_commentary):
        with self.assertRaises(ValueError) as caught:
            validate_market_commentary_response(
                request=request,
                response=LlmMarketCommentary(
                    market_commentary=market_commentary,
                    conclusion=V12_CONCLUSION,
                ),
            )
        return str(caught.exception)

    def test_average_comparison_subject_inversion(self):
        # 현재 48 / 평균 81 — 평균이 현재보다 낮다는 서술은 반대다.
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=48,
            signal_level="보통",
            previous_signal_score=52,
            signal_change=-4,
            signal_ma5=81,
        )
        message = self.reject(
            request,
            "현재는 개인투자자의 매도가 더 많습니다. "
            "최근 5일 평균인 81점이 오늘보다 훨씬 낮습니다.",
        )
        self.assertIn("비교 주어가 뒤바뀌었습니다", message)

    def test_correct_average_comparison_still_passes(self):
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=48,
            signal_level="보통",
            previous_signal_score=52,
            signal_change=-4,
            signal_ma5=81,
        )
        validate_market_commentary_response(
            request=request,
            response=LlmMarketCommentary(
                market_commentary=(
                    "현재는 개인투자자의 매도가 더 많습니다. "
                    "현재 48점은 최근 5일 평균인 81점보다 낮습니다."
                ),
                conclusion=V12_CONCLUSION,
            ),
        )

    def test_change_value_used_as_previous_score(self):
        # 현재 87 / 직전 56 / 변화 +31 — 31은 직전 점수가 아니다.
        request = v12_request(
            supply_direction="BUY",
            comment_signal_score=87,
            signal_level="매우 높음",
            previous_signal_score=56,
            signal_change=31,
            signal_ma5=66,
        )
        message = self.reject(
            request,
            "현재는 개인투자자의 매수가 더 많습니다. "
            "직전 거래일의 31점보다 높습니다.",
        )
        self.assertIn("직전 거래일 점수 자리", message)

    def test_correct_number_roles_still_pass(self):
        request = v12_request(
            supply_direction="BUY",
            comment_signal_score=87,
            signal_level="매우 높음",
            previous_signal_score=56,
            signal_change=31,
            signal_ma5=66,
        )
        validate_market_commentary_response(
            request=request,
            response=LlmMarketCommentary(
                market_commentary=(
                    "현재는 개인투자자의 매수가 더 많습니다. "
                    "직전 거래일의 56점보다 31점 높아졌습니다."
                ),
                conclusion=V12_CONCLUSION,
            ),
        )

    def test_supply_pressure_change_is_rejected(self):
        sell = v12_request(
            supply_direction="SELL",
            comment_signal_score=48,
            signal_level="보통",
            previous_signal_score=37,
            signal_change=11,
            signal_ma5=52,
        )
        for sentence in (
            "매도 압력이 커졌습니다.",
            "매도세가 강화됐습니다.",
            "매도 압력이 완화됐습니다.",
        ):
            with self.subTest(sentence=sentence):
                message = self.reject(
                    sell,
                    "현재는 개인투자자의 매도가 더 많습니다. " + sentence,
                )
                self.assertIn("수급 강도의 변화", message)

    def test_unchanged_score_claim_after_real_move(self):
        request = v12_request(
            supply_direction="SELL",
            comment_signal_score=48,
            signal_level="보통",
            previous_signal_score=37,
            signal_change=11,
            signal_ma5=52,
        )
        for sentence in (
            "점수가 그대로 유지됐습니다.",
            "어제와 같은 점수입니다.",
            "점수에 변화가 없습니다.",
        ):
            with self.subTest(sentence=sentence):
                message = self.reject(
                    request,
                    "현재는 개인투자자의 매도가 더 많습니다. " + sentence,
                )
                self.assertIn("그대로라고 서술했습니다", message)
