import unittest

from datetime import date
from decimal import Decimal

from pilos.analysis.llm_report import (
    MOVING_AVERAGE_LABEL,
    build_deterministic_commentary,
    build_flask_daily_signal_response,
    build_report_json,
    build_report_messages,
    build_signal_evidence,
    calculate_report_input_hash,
    classify_supply_state,
    detect_direct_causality,
    should_request_llm_commentary,
    validate_market_commentary_response,
)
from pilos.dto.comment_signal_dto import CommentSignalHistory
from pilos.dto.llm_report_dto import (
    EVIDENCE_SCHEMA_VERSION,
    PROMPT_VERSION,
    REPORT_SCHEMA_VERSION,
    LlmMarketCommentary,
    LlmSignalEvidence,
    ReportGenerationRequest,
    ReportGenerationResult,
)


def make_evidence(**changes):
    values = {
        "actual_supply_index": 0.1951,
        "supply_direction": "BUY",
        "signal_status": "ready",
        "comment_signal_score": 84,
        "signal_level": "매우 높음",
        "comment_count": 1830,
        "previous_signal_score": 57,
        "signal_change": 27,
        "signal_ma5": 49,
    }
    values.update(changes)
    return LlmSignalEvidence(**values)


def make_request(*, evidence=None, **changes):
    evidence = evidence or make_evidence()
    values = {
        "daily_document_id": 10,
        "positive_result_id": 20,
        "negative_result_id": 21,
        "stock_id": 1,
        "stock_code": "000660",
        "stock_name": "SK하이닉스",
        "model_date": date(2026, 8, 7),
        "comment_count": evidence.comment_count,
        "supply_state": classify_supply_state(evidence.actual_supply_index),
        "active_model_variant": (
            None if evidence.signal_status == "no_direction" else "positive"
        ),
        "predicted_score": 0.42,
        "recognized_feature_count": 120,
        "evidence": evidence,
        "model_name": "ridge_supply",
        "model_version": 4,
        "artifact_schema_version": 2,
        "calibration_schema_version": 1,
        "provider": "academy",
        "model": "qwen3.5-4b",
    }
    values.update(changes)
    return ReportGenerationRequest(**values)


def valid_commentary(**changes):
    values = {
        "market_commentary": (
            "SK하이닉스는 개인투자자 매수 우위입니다. "
            "댓글 수급 신호는 84점으로 매우 높음 수준입니다. "
            "직전 거래일보다 27포인트 상승했고, "
            "직전 5거래일 평균 49점보다도 높습니다."
        ),
        "conclusion": (
            "SK하이닉스는 개인투자자 매수 우위이며 댓글 수급 신호는 "
            "84점으로 매우 높음 수준입니다."
        ),
    }
    values.update(changes)
    return LlmMarketCommentary(**values)


class SupplyStateTest(unittest.TestCase):
    def test_accepts_database_decimal_value(self):
        state = classify_supply_state(Decimal("0.05"))

        self.assertEqual(state.actual_supply_index, 0.05)
        self.assertEqual(state.active_regime, "positive")
        self.assertEqual(state.supply_direction, "BUY")

    def test_strength_boundaries_and_directions(self):
        cases = (
            (0, "수급 균형", "NEUTRAL"),
            (0.0025, "거의 균형에 가까운 소폭 매수 우위", "BUY"),
            (-0.0499, "거의 균형에 가까운 소폭 매도 우위", "SELL"),
            (0.05, "다소 매수 우위", "BUY"),
            (-0.15, "매도 우위", "SELL"),
            (0.30, "뚜렷한 매수 우위", "BUY"),
        )
        for value, expected_label, expected_direction in cases:
            with self.subTest(value=value):
                state = classify_supply_state(value)
                self.assertEqual(state.state_label, expected_label)
                self.assertEqual(state.supply_direction, expected_direction)


class SignalEvidenceContractTest(unittest.TestCase):
    def test_ready_requires_score_and_level(self):
        with self.assertRaisesRegex(ValueError, "신호 점수와 강도"):
            make_evidence(comment_signal_score=None, signal_level=None)

    def test_non_ready_must_not_carry_score(self):
        with self.assertRaisesRegex(ValueError, "ready가 아닌 상태"):
            make_evidence(
                signal_status="insufficient_features",
                comment_signal_score=84,
                signal_level="매우 높음",
            )

    def test_signal_change_must_match_difference(self):
        with self.assertRaisesRegex(ValueError, "signal_change"):
            make_evidence(signal_change=10)

    def test_signal_change_requires_previous_score(self):
        with self.assertRaisesRegex(ValueError, "직전 신호가 없으면"):
            make_evidence(previous_signal_score=None, signal_change=5)

    def test_request_rejects_direction_mismatch(self):
        with self.assertRaisesRegex(ValueError, "수급 방향이 다릅니다"):
            make_request(
                supply_state=classify_supply_state(-0.2),
            )

    def test_no_direction_request_has_no_active_model(self):
        evidence = make_evidence(
            actual_supply_index=0.0,
            supply_direction="NEUTRAL",
            signal_status="no_direction",
            comment_signal_score=None,
            signal_level=None,
            previous_signal_score=None,
            signal_change=None,
            signal_ma5=None,
        )
        request = make_request(evidence=evidence)
        self.assertIsNone(request.active_model_variant)


class SignalEvidenceBuilderTest(unittest.TestCase):
    def test_non_ready_signal_drops_history_values(self):
        from tests.test_signal_calibration import make_signal

        signal = make_signal(
            actual_supply_index=0.1,
            positive_features=0,
            positive_status="insufficient_features",
        )
        evidence = build_signal_evidence(
            daily_signal=signal,
            history=CommentSignalHistory(
                previous_signal_score=57,
                signal_change=3,
                signal_ma5=49,
                history_size=5,
            ),
        )
        self.assertEqual(evidence.signal_status, "insufficient_features")
        self.assertIsNone(evidence.comment_signal_score)
        self.assertIsNone(evidence.previous_signal_score)
        self.assertIsNone(evidence.signal_ma5)


class PromptAndHashTest(unittest.TestCase):
    def test_prompt_contains_only_structured_numeric_evidence(self):
        request = make_request()
        messages = build_report_messages(request)
        prompt = messages[1]["content"]

        self.assertIn('"comment_signal_score":84', prompt)
        self.assertIn('"supply_direction":"BUY"', prompt)
        self.assertIn('"signal_ma5":49', prompt)
        for forbidden in (
            "key_expressions",
            "used_comment_refs",
            "representative_comments",
            "matched_words",
            "positive_contribution_keywords",
            "negative_contribution_keywords",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, prompt)

    def test_system_prompt_keeps_fact_contract_and_opens_expression(self):
        system_prompt = build_report_messages(make_request())[0]["content"]

        self.assertIn("데이터 해설자", system_prompt)
        self.assertIn("애널리스트가 아니라 설명자", system_prompt)
        self.assertIn("signal_level은 이미 결정된 등급", system_prompt)
        self.assertIn("생략해도 되지만", system_prompt)
        self.assertIn("변화량의 기준으로 삼지 않습니다", system_prompt)
        self.assertIn("평균은 비교 기준이지 변화의 대상이 아닙니다", system_prompt)
        self.assertIn("댓글 수급 신호를 대상으로 할 때만", system_prompt)
        self.assertIn("방향에 점수를 붙이지 마세요", system_prompt)
        self.assertIn(MOVING_AVERAGE_LABEL, system_prompt)
        self.assertIn("2~4문장", system_prompt)

    def test_system_prompt_prefers_plain_wording(self):
        system_prompt = build_report_messages(make_request())[0]["content"]

        self.assertIn("현재는 개인투자자의 매수가 더 많습니다", system_prompt)
        self.assertIn("현재는 개인투자자의 매도가 더 많습니다", system_prompt)
        self.assertIn("어제보다 15점 낮아졌습니다", system_prompt)

        # 과거형 문체와 기계적인 등급 표현을 명시적으로 금지한다.
        self.assertIn("이미 끝난 사건으로 서술하지 마세요", system_prompt)
        self.assertIn("'높음 편'이 아니라 '높은 편'", system_prompt)
        self.assertIn(
            "같은 순서와 같은 표현으로 반복할 필요는 없습니다",
            system_prompt,
        )

        # 금융 보고서 페르소나를 강제하지 않는다.
        for persona in ("전문 금융 애널리스트", "증권사 리서치", "시장 전략가"):
            with self.subTest(persona=persona):
                self.assertNotIn(persona, system_prompt)

    def test_prompt_pins_signal_level_and_moving_average_names(self):
        prompt = build_report_messages(make_request())[1]["content"]

        self.assertIn("등급은 '매우 높음'입니다", prompt)
        self.assertIn("84점으로 매우 높은 편", prompt)
        self.assertIn("5일 평균", prompt)

    def test_prompt_gives_comparison_facts_not_sentences(self):
        prompt = build_report_messages(make_request())[1]["content"]

        self.assertIn("어제(직전 거래일)와 비교: 27점 높아짐", prompt)
        self.assertIn("최근 5일 평균과 비교: 현재가 더 높음", prompt)
        self.assertIn("문장 표현은 직접 정하세요", prompt)
        self.assertIn("문장 구조를 고정하지 마세요", prompt)

    def test_prompt_names_crossed_relation(self):
        crossed = make_request(
            evidence=make_evidence(
                comment_signal_score=39,
                signal_level="낮음",
                previous_signal_score=9,
                signal_change=30,
                signal_ma5=55,
            )
        )
        prompt = build_report_messages(crossed)[1]["content"]

        self.assertIn("종합하면:", prompt)
        self.assertIn("올라왔지만", prompt)

    def test_prompt_reflects_downward_and_equal_comparisons(self):
        lower = make_request(
            evidence=make_evidence(
                comment_signal_score=40,
                signal_level="보통",
                previous_signal_score=57,
                signal_change=-17,
                signal_ma5=55,
            )
        )
        prompt = build_report_messages(lower)[1]["content"]

        self.assertIn("어제(직전 거래일)와 비교: 17점 낮아짐", prompt)
        self.assertIn("최근 5일 평균과 비교: 현재가 더 낮음", prompt)

    def test_missing_history_is_not_sent_as_null(self):
        request = make_request(
            evidence=make_evidence(
                previous_signal_score=None,
                signal_change=None,
                signal_ma5=None,
            )
        )
        prompt = build_report_messages(request)[1]["content"]

        self.assertNotIn('"previous_signal_score"', prompt)
        self.assertNotIn('"signal_ma5"', prompt)
        self.assertIn("비교할 과거 신호가 없으므로", prompt)

    def test_hash_is_reproducible_and_changes_with_signal(self):
        request = make_request()
        self.assertEqual(
            calculate_report_input_hash(request),
            calculate_report_input_hash(request),
        )
        changed = request.model_copy(
            update={
                "evidence": make_evidence(
                    comment_signal_score=60,
                    signal_change=3,
                )
            }
        )
        self.assertNotEqual(
            calculate_report_input_hash(request),
            calculate_report_input_hash(changed),
        )


class LlmCallDecisionTest(unittest.TestCase):
    def test_ready_signal_with_history_uses_llm(self):
        self.assertTrue(should_request_llm_commentary(make_request()))

    def test_ready_signal_without_history_stays_deterministic(self):
        request = make_request(
            evidence=make_evidence(
                previous_signal_score=None,
                signal_change=None,
                signal_ma5=None,
            )
        )
        self.assertFalse(should_request_llm_commentary(request))

    def test_no_direction_stays_deterministic(self):
        evidence = make_evidence(
            actual_supply_index=0.0,
            supply_direction="NEUTRAL",
            signal_status="no_direction",
            comment_signal_score=None,
            signal_level=None,
            previous_signal_score=None,
            signal_change=None,
            signal_ma5=None,
        )
        self.assertFalse(
            should_request_llm_commentary(make_request(evidence=evidence))
        )


class MarketCommentaryValidationTest(unittest.TestCase):
    def test_valid_response_is_accepted(self):
        validate_market_commentary_response(
            request=make_request(),
            response=valid_commentary(),
        )

    def test_direct_causality_is_rejected(self):
        self.assertTrue(detect_direct_causality("매도세가 주가 하락을 주도했습니다."))
        with self.assertRaisesRegex(ValueError, "직접 인과"):
            validate_market_commentary_response(
                request=make_request(),
                response=valid_commentary(
                    market_commentary=(
                        "댓글 수급 신호는 84점으로 매우 높음 수준입니다. "
                        "개인 매도세가 하락을 주도하고 있습니다."
                    )
                ),
            )

    def test_invented_number_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "없는 숫자"):
            validate_market_commentary_response(
                request=make_request(),
                response=valid_commentary(
                    market_commentary=(
                        "SK하이닉스는 개인투자자 매수 우위입니다. "
                        "댓글 수급 신호는 84점으로 매우 높음 수준이며 "
                        "73점보다 높습니다."
                    )
                ),
            )

    def test_percent_sign_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "백분율"):
            validate_market_commentary_response(
                request=make_request(),
                response=valid_commentary(
                    conclusion=(
                        "매수 우위 구간에서 댓글 신호는 84% 수준으로 "
                        "매우 높음 상태입니다."
                    )
                ),
            )

    def test_decimal_value_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "소수 수치"):
            validate_market_commentary_response(
                request=make_request(),
                response=valid_commentary(
                    conclusion=(
                        "실제 수급지수 0.1951을 기준으로 매수 우위이며 "
                        "신호는 매우 높음 수준입니다."
                    )
                ),
            )

    def test_probability_and_prediction_words_are_rejected(self):
        for phrase, text in (
            (
                "긍정 확률",
                (
                    "댓글 수급 신호 84점은 매우 높음 수준이며 "
                    "긍정 확률이 높다는 뜻입니다."
                ),
            ),
            (
                "수급 예측",
                (
                    "댓글 수급 신호 84점은 매우 높음 수준이며 "
                    "이를 근거로 수급 예측을 제시합니다."
                ),
            ),
            (
                "매수 추천",
                (
                    "SK하이닉스는 개인투자자 매수 우위입니다. "
                    "댓글 수급 신호 84점은 매우 높음 수준이며 "
                    "매수 추천 의견을 유지합니다."
                ),
            ),
        ):
            with self.subTest(phrase=phrase):
                with self.assertRaisesRegex(ValueError, "주가 방향·투자 권유·확률"):
                    validate_market_commentary_response(
                        request=make_request(),
                        response=valid_commentary(market_commentary=text),
                    )

    def test_unexpected_chinese_character_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "중국어 문자"):
            validate_market_commentary_response(
                request=make_request(),
                response=valid_commentary(
                    conclusion=(
                        "매수 우위 구간에서 매우 높음 수준의 中립적인 "
                        "신호가 나타났습니다."
                    )
                ),
            )


class SignalLevelPreservationTest(unittest.TestCase):
    """signal_level은 코드가 결정한 값이며 LLM의 판단 대상이 아니다."""

    def commentary(self, *, level, score, text, conclusion=None):
        request = make_request(
            evidence=make_evidence(
                comment_signal_score=score,
                signal_level=level,
                previous_signal_score=score,
                signal_change=0,
                signal_ma5=score,
            )
        )
        response = valid_commentary(
            market_commentary=text,
            conclusion=conclusion
            or (
                "SK하이닉스는 개인투자자 매수 우위이며 오늘 신호를 "
                f"{level} 수준으로 정리했습니다."
            ),
        )
        return request, response

    def test_low_must_not_become_very_low(self):
        request, response = self.commentary(
            level="낮음",
            score=21,
            text=(
                "SK하이닉스는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 21점으로 매우 낮은 수준입니다."
            ),
            conclusion="오늘 댓글 신호는 낮음 수준으로 정리됩니다.",
        )
        with self.assertRaisesRegex(ValueError, "다른 등급으로 표현했습니다"):
            validate_market_commentary_response(
                request=request,
                response=response,
            )

    def test_normal_must_not_become_low(self):
        request, response = self.commentary(
            level="보통",
            score=43,
            text=(
                "SK하이닉스는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 43점으로 낮은 수준입니다."
            ),
            conclusion="오늘 댓글 신호는 보통 수준으로 정리됩니다.",
        )
        with self.assertRaisesRegex(ValueError, "다른 등급으로 표현했습니다"):
            validate_market_commentary_response(
                request=request,
                response=response,
            )

    def test_conclusion_must_not_reclassify_level(self):
        request, response = self.commentary(
            level="높음",
            score=70,
            text=(
                "SK하이닉스는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 70점으로 높음 수준입니다."
            ),
            conclusion=(
                "오늘 댓글 수급 신호는 70점으로 보통 수준에 머물렀습니다."
            ),
        )
        with self.assertRaisesRegex(ValueError, "conclusion"):
            validate_market_commentary_response(
                request=request,
                response=response,
            )

    def test_matching_level_is_accepted(self):
        request, response = self.commentary(
            level="보통",
            score=43,
            text=(
                "SK하이닉스는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 43점으로 보통 수준입니다."
            ),
            conclusion="오늘 댓글 신호는 보통 수준으로 정리됩니다.",
        )
        validate_market_commentary_response(
            request=request,
            response=response,
        )

    def test_average_comparison_is_not_treated_as_level(self):
        # "평균 49점보다 낮습니다"는 강도 재분류가 아니라 비교 문장이다.
        request = make_request(
            evidence=make_evidence(
                comment_signal_score=45,
                signal_level="보통",
                previous_signal_score=40,
                signal_change=5,
                signal_ma5=49,
            )
        )
        validate_market_commentary_response(
            request=request,
            response=valid_commentary(
                market_commentary=(
                    "SK하이닉스는 개인투자자 매수 우위입니다. "
                    "댓글 수급 신호는 45점으로 보통 수준입니다. "
                    "직전 거래일보다 5포인트 상승했지만, "
                    "직전 5거래일 평균 49점보다는 낮습니다."
                ),
                conclusion=(
                    "SK하이닉스는 매수 우위이며 오늘 신호는 보통 "
                    "수준입니다."
                ),
            ),
        )


class MovingAverageLanguageTest(unittest.TestCase):
    """signal_ma5는 직전 5거래일 평균이며 다른 통계와 구분한다."""

    def response(self, text):
        return valid_commentary(
            market_commentary=(
                "SK하이닉스는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 84점으로 매우 높음 수준입니다. "
                f"{text}"
            ),
            conclusion=(
                "SK하이닉스는 매수 우위이며 오늘 신호는 매우 높음 "
                "수준입니다."
            ),
        )

    def test_forbidden_aliases_are_rejected(self):
        cases = (
            "과거 평균 49점보다 높습니다.",
            "과거 분포의 중간 수준인 49점보다 높습니다.",
            "이동평균 49점보다 높습니다.",
            "직전 거래일 평균 49점보다 높습니다.",
        )
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "다른 통계처럼"):
                    validate_market_commentary_response(
                        request=make_request(),
                        response=self.response(text),
                    )

    def test_correct_name_is_accepted(self):
        validate_market_commentary_response(
            request=make_request(),
            response=self.response(
                f"{MOVING_AVERAGE_LABEL} 49점보다 높습니다."
            ),
        )


class ChangeComparisonTest(unittest.TestCase):
    """signal_change는 직전 거래일과의 차이이며 평균과 결합하지 않는다."""

    def response(self, text):
        return valid_commentary(
            market_commentary=(
                "SK하이닉스는 개인투자자 매수 우위입니다. "
                "댓글 수급 신호는 84점으로 매우 높음 수준입니다. "
                f"{text}"
            ),
            conclusion=(
                "SK하이닉스는 매수 우위이며 오늘 신호는 매우 높음 "
                "수준입니다."
            ),
        )

    def test_change_anchored_to_moving_average_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "평균으로 서술했습니다"):
            validate_market_commentary_response(
                request=make_request(),
                response=self.response(
                    f"{MOVING_AVERAGE_LABEL} 49점을 기준으로 "
                    "27포인트 상승했습니다."
                ),
            )

    def test_change_value_must_equal_signal_change(self):
        with self.assertRaisesRegex(ValueError, "signal_change와 다릅니다"):
            validate_market_commentary_response(
                request=make_request(),
                response=self.response(
                    "직전 거래일보다 57포인트 상승했습니다."
                ),
            )

    def test_previous_day_anchor_is_accepted(self):
        for prefix in ("직전 거래일보다", "전 거래일보다", "전일보다"):
            with self.subTest(prefix=prefix):
                validate_market_commentary_response(
                    request=make_request(),
                    response=self.response(f"{prefix} 27포인트 상승했습니다."),
                )

    def test_opposite_relations_can_be_stated_together(self):
        request = make_request(
            evidence=make_evidence(
                comment_signal_score=39,
                signal_level="낮음",
                previous_signal_score=9,
                signal_change=30,
                signal_ma5=55,
            )
        )
        validate_market_commentary_response(
            request=request,
            response=valid_commentary(
                market_commentary=(
                    "SK하이닉스는 개인투자자 매수 우위입니다. "
                    "댓글 수급 신호는 39점으로 낮음 수준입니다. "
                    "직전 거래일보다 30포인트 상승했지만, "
                    "직전 5거래일 평균 55점보다는 낮습니다."
                ),
                conclusion=(
                    "SK하이닉스는 매수 우위이며 오늘 신호는 낮음 "
                    "수준이지만 직전 거래일보다 30포인트 올랐습니다."
                ),
            ),
        )


class PriceInterpretationTest(unittest.TestCase):
    """댓글 수급 신호를 주가 방향이나 투자 판단으로 확대하지 않는다."""

    def test_price_and_investment_words_are_rejected(self):
        cases = (
            "강한 상승 신호가 나타났습니다.",
            "주가 상승 압력이 약화됐습니다.",
            "매수 신호로 볼 수 있습니다.",
            "추세 전환 가능성이 있습니다.",
        )
        for text in cases:
            # 어떤 규칙이 먼저 걸리는지가 아니라 차단 여부가 계약이다.
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    validate_market_commentary_response(
                        request=make_request(),
                        response=valid_commentary(
                            market_commentary=(
                                "댓글 수급 신호는 84점으로 매우 높음 "
                                f"수준입니다. {text}"
                            )
                        ),
                    )

    def test_supply_direction_wording_is_allowed(self):
        validate_market_commentary_response(
            request=make_request(),
            response=valid_commentary(
                market_commentary=(
                    "SK하이닉스는 개인투자자 매수 우위입니다. "
                    "댓글 수급 신호는 84점으로 매우 높음 수준이며 "
                    "매수 우위 수급이 이어졌습니다."
                )
            ),
        )


class DeterministicCommentaryTest(unittest.TestCase):
    def test_ready_signal_states_score_and_comparison(self):
        commentary = build_deterministic_commentary(make_request())

        self.assertIn(
            "현재 개인투자자의 매수가 더 많고",
            commentary.market_commentary,
        )
        self.assertIn("84점으로 매우 높은 편", commentary.market_commentary)
        self.assertIn(
            "어제보다 27점 높아졌고",
            commentary.market_commentary,
        )
        self.assertIn(
            "최근 5일 평균 49점보다도 높습니다",
            commentary.market_commentary,
        )

    def test_crossed_relation_is_kept_as_two_relations(self):
        crossed = make_request(
            evidence=make_evidence(
                comment_signal_score=39,
                signal_level="낮음",
                previous_signal_score=9,
                signal_change=30,
                signal_ma5=55,
            )
        )
        text = build_deterministic_commentary(crossed).market_commentary

        self.assertIn("어제보다 30점 높아졌지만", text)
        self.assertIn("55점보다는 낮습니다", text)
        self.assertIn("올라왔지만", text)

    def test_aligned_relation_does_not_repeat_summary(self):
        text = build_deterministic_commentary(
            make_request()
        ).market_commentary

        self.assertNotIn("현재 댓글 신호는", text)

    def test_ready_signal_avoids_stiff_expressions(self):
        commentary = build_deterministic_commentary(make_request())
        narrative = f"{commentary.market_commentary} {commentary.conclusion}"

        for phrase in ("관측됐습니다", "기록됐습니다", "설정", "평가됩니다"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, narrative)

    def test_sentence_count_stays_within_four(self):
        commentary = build_deterministic_commentary(make_request())
        sentences = [
            part
            for part in commentary.market_commentary.split(". ")
            if part.strip()
        ]

        self.assertLessEqual(len(sentences), 4)
        self.assertGreaterEqual(len(sentences), 2)

    def test_no_direction_does_not_claim_a_signal(self):
        evidence = make_evidence(
            actual_supply_index=0.0,
            supply_direction="NEUTRAL",
            signal_status="no_direction",
            comment_signal_score=None,
            signal_level=None,
            previous_signal_score=None,
            signal_change=None,
            signal_ma5=None,
        )
        commentary = build_deterministic_commentary(
            make_request(evidence=evidence)
        )
        self.assertIn(
            "현재 개인투자자의 매수와 매도가 비슷합니다",
            commentary.market_commentary,
        )
        self.assertIn("계산하지 않았습니다", commentary.market_commentary)

    def test_insufficient_features_explains_missing_signal(self):
        evidence = make_evidence(
            signal_status="insufficient_features",
            comment_signal_score=None,
            signal_level=None,
            previous_signal_score=None,
            signal_change=None,
            signal_ma5=None,
        )
        commentary = build_deterministic_commentary(
            make_request(evidence=evidence)
        )
        self.assertIn("인식한", commentary.market_commentary)

    def test_deterministic_output_passes_response_validation(self):
        request = make_request()
        validate_market_commentary_response(
            request=request,
            response=build_deterministic_commentary(request),
        )


class FinalReportTest(unittest.TestCase):
    def test_report_json_carries_signal_contract(self):
        request = make_request()
        result = ReportGenerationResult(
            commentary=valid_commentary(),
            provider_response_id="response-1",
            input_tokens=10,
            output_tokens=20,
        )
        report = build_report_json(
            request=request,
            status="ready",
            generation_result=result,
        )

        self.assertEqual(report["prompt_version"], PROMPT_VERSION)
        self.assertEqual(
            report["report_schema_version"],
            REPORT_SCHEMA_VERSION,
        )
        self.assertEqual(
            report["evidence_schema_version"],
            EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(report["commentary_source"], "llm")
        self.assertEqual(report["supply_direction"], "BUY")
        self.assertEqual(report["comment_signal_score"], 84)
        self.assertEqual(report["signal_level"], "매우 높음")
        self.assertEqual(report["signal_change"], 27)
        self.assertEqual(report["signal_ma5"], 49)
        self.assertEqual(report["details"]["predicted_score"], 0.42)
        self.assertIn("rendered_text", report["display_report"])

    def test_report_json_has_no_keyword_or_comment_evidence(self):
        report = build_report_json(
            request=make_request(),
            status="insufficient_evidence",
            generation_result=None,
        )
        serialized = str(report)

        self.assertEqual(report["commentary_source"], "deterministic")
        for forbidden in (
            "key_expressions",
            "used_comment_refs",
            "representative_comments",
            "matched_words",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_flask_response_contains_only_finished_values(self):
        report = build_report_json(
            request=make_request(),
            status="ready",
            generation_result=ReportGenerationResult(
                commentary=valid_commentary()
            ),
        )
        response = build_flask_daily_signal_response(report)

        self.assertEqual(
            set(response.keys()),
            {
                "status",
                "commentary_source",
                "stock_code",
                "stock_name",
                "model_date",
                "supply_direction",
                "actual_supply_index",
                "comment_signal_score",
                "signal_level",
                "signal_status",
                "report_supply_data_status",
                "report_supply_observed_at",
                "signal_change",
                "signal_ma5",
                "comment_count",
                "market_commentary",
                "conclusion",
                "notice",
            },
        )
        self.assertEqual(response["signal_level"], "매우 높음")


if __name__ == "__main__":
    unittest.main()
