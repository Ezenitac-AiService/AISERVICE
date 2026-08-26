import unittest

from unittest.mock import Mock

import numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge

from pilos.analysis.single_comment_inference import (
    analyze_single_comment,
)
from pilos.analysis.tokenizer import create_kiwi
from pilos.analysis.tokenizer_settings import USER_DICTIONARY
from pilos.model_config import ACTIVE_SERVICE_MODEL_VERSION
from pilos.dto.single_comment_inference_dto import (
    SingleCommentAnalysisDTO,
    SingleCommentInferenceDTO,
)
from pilos.jobs.analyze_single_comment import (
    build_single_comment_response,
    run_single_comment_analysis,
)


TRAINING_DOCUMENTS = (
    "매수 추가 하락 저점",
    "매도 상승 고점 정리",
    "매수 매도 하락 상승",
    "추가 저점 매수 대기",
    "고점 정리 매도 대기",
)


def make_artifacts(*, model_variant, seed):
    """실제 학습 경로와 같은 객체 종류로 작은 검증용 bundle을 만든다."""
    vectorizer = TfidfVectorizer()
    features = vectorizer.fit_transform(TRAINING_DOCUMENTS)
    generator = np.random.default_rng(seed)
    targets = generator.normal(size=features.shape[0])
    ridge_model = Ridge(alpha=1.0, solver="lsqr")
    ridge_model.fit(features, targets)
    return {
        "artifact_schema_version": 2,
        "model_name": "ridge_supply",
        "model_variant": model_variant,
        "model_version": 4,
        "feature_mode": "text_only",
        "tokenizer_version": "kiwi_ver1",
        "vectorizer": vectorizer,
        "ridge_model": ridge_model,
    }


class SingleCommentAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokenizer = create_kiwi(user_dictionary=USER_DICTIONARY)
        cls.positive_artifacts = make_artifacts(
            model_variant="positive",
            seed=42,
        )
        cls.negative_artifacts = make_artifacts(
            model_variant="negative",
            seed=43,
        )

    def analyze(self, text="오늘 더 떨어지면 추가 매수한다"):
        return analyze_single_comment(
            comment_text=text,
            tokenizer=self.tokenizer,
            positive_model_artifacts=self.positive_artifacts,
            negative_model_artifacts=self.negative_artifacts,
        )

    def test_both_models_return_results(self):
        analysis = self.analyze()

        self.assertIsInstance(analysis, SingleCommentAnalysisDTO)
        self.assertIsInstance(analysis.positive, SingleCommentInferenceDTO)
        self.assertIsInstance(analysis.negative, SingleCommentInferenceDTO)
        self.assertEqual(
            analysis.result_for("positive"),
            analysis.positive,
        )
        self.assertEqual(
            analysis.result_for("negative"),
            analysis.negative,
        )

    def test_existing_preprocessing_path_is_used(self):
        analysis = self.analyze("오늘 더 떨어지면 추가 매수한다 ㅋㅋㅋ")

        self.assertIn("소셜웃음", analysis.processed_text)
        self.assertNotIn("ㅋㅋㅋ", analysis.processed_text)
        self.assertGreater(analysis.token_count, 0)

    def test_recognized_feature_count_is_reported_per_variant(self):
        analysis = self.analyze()

        self.assertGreaterEqual(analysis.positive.recognized_feature_count, 1)
        self.assertGreaterEqual(analysis.negative.recognized_feature_count, 1)

    def test_text_score_equals_sum_of_contributions(self):
        analysis = self.analyze()

        for result in (analysis.positive, analysis.negative):
            with self.subTest(result=result):
                contribution_sum = sum(
                    keyword.contribution
                    for keyword in (
                        *result.positive_keywords,
                        *result.negative_keywords,
                    )
                )
                self.assertAlmostEqual(
                    result.text_score,
                    contribution_sum,
                    places=9,
                )

    def test_two_models_can_disagree(self):
        analysis = self.analyze()

        self.assertNotEqual(
            analysis.positive.text_score,
            analysis.negative.text_score,
        )

    def test_result_has_no_daily_signal_fields(self):
        analysis = self.analyze()
        payload = build_single_comment_response(analysis)

        for forbidden in (
            "comment_signal_score",
            "signal_level",
            "signal_status",
            "supply_direction",
            "percentile",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, str(payload))

        self.assertIn("일별 댓글 수급 신호", payload["notice"])

    def test_empty_input_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "비어 있습니다"):
            self.analyze("   ")

    def test_text_without_analyzable_token_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "전처리 후"):
            self.analyze("\U0001F600\U0001F600\U0001F600")


class SingleCommentJobTest(unittest.TestCase):
    def test_job_loads_both_registered_models(self):
        artifacts = {
            "positive": make_artifacts(model_variant="positive", seed=42),
            "negative": make_artifacts(model_variant="negative", seed=43),
        }
        load_artifacts = Mock(
            side_effect=lambda *, model_variant, model_version: (
                {"artifact_id": 1, "model_variant": model_variant},
                artifacts[model_variant],
            )
        )
        analysis = run_single_comment_analysis(
            comment_text="오늘 더 떨어지면 추가 매수한다",
            load_artifacts=load_artifacts,
            tokenizer=create_kiwi(user_dictionary=USER_DICTIONARY),
        )

        self.assertEqual(load_artifacts.call_count, 2)
        self.assertEqual(
            sorted(
                call.kwargs["model_variant"]
                for call in load_artifacts.call_args_list
            ),
            ["negative", "positive"],
        )
        self.assertTrue(
            all(
                call.kwargs["model_version"]
                == ACTIVE_SERVICE_MODEL_VERSION
                for call in load_artifacts.call_args_list
            )
        )
        self.assertIsInstance(analysis, SingleCommentAnalysisDTO)


if __name__ == "__main__":
    unittest.main()
