import unittest

from unittest.mock import Mock, patch

from pilos.dto.keyword_contribution_dto import KeywordContributionDTO
from pilos.dto.single_comment_inference_dto import (
    SingleCommentAnalysisDTO,
    SingleCommentInferenceDTO,
)
from pilos.service.single_comment_service import (
    SingleCommentInputError,
    SingleCommentServiceError,
    get_single_comment_analysis,
)
from pilos.web.app import app


def make_analysis() -> SingleCommentAnalysisDTO:
    positive = SingleCommentInferenceDTO(
        comment_text="추가 매수한다",
        processed_text="추가 매수한다",
        text_score=0.3,
        recognized_feature_count=2,
        positive_keywords=(
            KeywordContributionDTO(keyword="매수", contribution=0.3),
        ),
        negative_keywords=(),
    )
    negative = SingleCommentInferenceDTO(
        comment_text="추가 매수한다",
        processed_text="추가 매수한다",
        text_score=-0.1,
        recognized_feature_count=1,
        positive_keywords=(),
        negative_keywords=(
            KeywordContributionDTO(keyword="추가", contribution=-0.1),
        ),
    )
    return SingleCommentAnalysisDTO(
        comment_text="추가 매수한다",
        processed_text="추가 매수한다",
        token_count=2,
        positive=positive,
        negative=negative,
    )


class SingleCommentServiceTest(unittest.TestCase):
    @patch("pilos.service.single_comment_service.analyze_single_comment")
    def test_loads_both_models_and_returns_analysis(self, analyze):
        expected = make_analysis()
        analyze.return_value = expected
        context_loader = Mock(
            return_value=Mock(
                positive_model_artifacts={"model_variant": "positive"},
                negative_model_artifacts={"model_variant": "negative"},
            )
        )
        tokenizer = object()

        result = get_single_comment_analysis(
            "추가 매수한다",
            context_loader=context_loader,
            tokenizer=tokenizer,
        )

        self.assertIs(result, expected)
        context_loader.assert_called_once_with()
        analyze.assert_called_once()

    def test_model_loading_failure_becomes_service_error(self):
        context_loader = Mock(side_effect=FileNotFoundError("missing"))

        with self.assertRaises(SingleCommentServiceError):
            get_single_comment_analysis(
                "추가 매수한다",
                context_loader=context_loader,
                tokenizer=object(),
            )

    @patch("pilos.service.single_comment_service.analyze_single_comment")
    def test_unanalyzable_text_becomes_input_error(self, analyze):
        analyze.side_effect = ValueError("전처리 후 분석할 문자열이 없습니다.")
        context_loader = Mock(
            return_value=Mock(
                positive_model_artifacts={"model": object()},
                negative_model_artifacts={"model": object()},
            )
        )

        with self.assertRaisesRegex(SingleCommentInputError, "전처리 후"):
            get_single_comment_analysis(
                "😀😀",
                context_loader=context_loader,
                tokenizer=object(),
            )


class SingleCommentRouteTest(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("pilos.web.app.get_single_comment_analysis")
    def test_analysis_is_jsonified_with_both_models(self, get_analysis):
        get_analysis.return_value = make_analysis()

        response = self.client.post(
            "/api/inference/single-comment",
            json={"comment_text": "추가 매수한다"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(
            set(payload),
            {
                "comment_text",
                "processed_text",
                "token_count",
                "positive_model",
                "negative_model",
                "notice",
            },
        )
        self.assertEqual(payload["positive_model"]["text_score"], 0.3)
        self.assertEqual(payload["negative_model"]["text_score"], -0.1)
        self.assertNotIn("comment_signal_score", str(payload))

    def test_json_object_is_required(self):
        response = self.client.post("/api/inference/single-comment")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {
                "status": "invalid_request",
                "message": "JSON 요청 본문이 필요합니다.",
            },
        )

    def test_non_empty_comment_text_is_required(self):
        response = self.client.post(
            "/api/inference/single-comment",
            json={"comment_text": "   "},
        )

        self.assertEqual(response.status_code, 400)

    @patch("pilos.web.app.get_single_comment_analysis")
    def test_analysis_input_error_is_json_400(self, get_analysis):
        get_analysis.side_effect = SingleCommentInputError(
            "전처리 후 분석할 문자열이 없습니다."
        )

        response = self.client.post(
            "/api/inference/single-comment",
            json={"comment_text": "😀😀"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("전처리 후", response.get_json()["message"])

    @patch("pilos.web.app.get_single_comment_analysis")
    def test_service_error_is_json_500(self, get_analysis):
        get_analysis.side_effect = SingleCommentServiceError("failed")

        with patch.object(app.logger, "exception"):
            response = self.client.post(
                "/api/inference/single-comment",
                json={"comment_text": "추가 매수한다"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.get_json(),
            {
                "status": "internal_error",
                "message": "단일 댓글을 분석하지 못했습니다.",
            },
        )


if __name__ == "__main__":
    unittest.main()
