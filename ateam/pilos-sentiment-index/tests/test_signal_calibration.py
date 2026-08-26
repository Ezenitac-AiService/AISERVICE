import json
import tempfile
import unittest

from datetime import date
from decimal import Decimal
from pathlib import Path

from pilos.analysis.signal_calibration import (
    SIGNAL_CALIBRATION_SCHEMA_VERSION,
    build_comment_signal_history,
    build_daily_comment_signal,
    build_variant_calibration,
    calculate_comment_signal_score,
    resolve_model_variant,
    resolve_signal_level,
    resolve_supply_direction,
    verify_calibration_matches_artifact,
)
from pilos.dto.comment_signal_dto import SignalCalibration
from pilos.storage.signal_calibration_store import (
    load_signal_calibration,
    resolve_calibration_path,
    save_signal_calibration,
)


POSITIVE_ARTIFACT_ID = 11
NEGATIVE_ARTIFACT_ID = 12


def positive_scores():
    """0.00부터 1.99까지 균등한 재추론 분포를 흉내 낸 표본이다."""
    return [index / 100.0 for index in range(200)]


def negative_scores():
    """-1.99부터 0.00까지 균등한 재추론 분포를 흉내 낸 표본이다."""
    return [-index / 100.0 for index in range(200)]


def make_calibration() -> SignalCalibration:
    return SignalCalibration(
        calibration_schema_version=SIGNAL_CALIBRATION_SCHEMA_VERSION,
        generated_at="2026-08-07T09:00:00+09:00",
        source_scope="training_dataset_reinference_until_2026-07-24",
        source_row_count=400,
        model_name="ridge_supply",
        model_version=4,
        artifact_type="ridge_text_grouped_random_bundle",
        artifact_schema_version=2,
        tokenizer_version="kiwi_ver1",
        vectorizer_name="TfidfVectorizer",
        scaler_name="not_used",
        dataset_start_date="2025-01-02",
        dataset_end_date="2026-07-24",
        variants=(
            build_variant_calibration(
                model_variant="positive",
                artifact_id=POSITIVE_ARTIFACT_ID,
                predicted_scores=positive_scores(),
            ),
            build_variant_calibration(
                model_variant="negative",
                artifact_id=NEGATIVE_ARTIFACT_ID,
                predicted_scores=negative_scores(),
            ),
        ),
    )


def make_results(
    *,
    positive_score=0.5,
    negative_score=-0.5,
    positive_features=8,
    negative_features=7,
    positive_status="ready",
    negative_status="ready",
):
    return {
        "positive": {
            "sentiment_index_result_id": 20,
            "artifact_id": POSITIVE_ARTIFACT_ID,
            "supply_demand_association_score": positive_score,
            "recognized_feature_count": positive_features,
            "unique_token_count": 10,
            "vocabulary_coverage": 0.8,
            "inference_status": positive_status,
        },
        "negative": {
            "sentiment_index_result_id": 21,
            "artifact_id": NEGATIVE_ARTIFACT_ID,
            "supply_demand_association_score": negative_score,
            "recognized_feature_count": negative_features,
            "unique_token_count": 10,
            "vocabulary_coverage": 0.7,
            "inference_status": negative_status,
        },
    }


def make_signal(
    *,
    actual_supply_index=0.19,
    model_date=date(2026, 8, 7),
    calibration=None,
    **result_changes,
):
    return build_daily_comment_signal(
        stock_id=1,
        stock_code="000660",
        stock_name="SK하이닉스",
        model_date=model_date,
        daily_document_id=10,
        comment_count=1830,
        actual_supply_index=actual_supply_index,
        results_by_variant=make_results(**result_changes),
        calibration=calibration or make_calibration(),
    )


class SupplyDirectionTest(unittest.TestCase):
    def test_sign_decides_direction(self):
        self.assertEqual(resolve_supply_direction(0.1951), "BUY")
        self.assertEqual(resolve_supply_direction(Decimal("-0.02")), "SELL")
        self.assertEqual(resolve_supply_direction(0), "NEUTRAL")

    def test_neutral_has_no_model_variant(self):
        self.assertIsNone(resolve_model_variant("NEUTRAL"))
        self.assertEqual(resolve_model_variant("BUY"), "positive")
        self.assertEqual(resolve_model_variant("SELL"), "negative")


class SignalLevelTest(unittest.TestCase):
    def test_bands_cover_full_range_without_sentiment_words(self):
        cases = (
            (0, "매우 낮음"),
            (19, "매우 낮음"),
            (20, "낮음"),
            (40, "보통"),
            (59, "보통"),
            (60, "높음"),
            (80, "매우 높음"),
            (100, "매우 높음"),
        )
        for score, expected in cases:
            with self.subTest(score=score):
                self.assertEqual(resolve_signal_level(score), expected)

    def test_out_of_range_score_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_signal_level(101)


class CalibrationDirectionTest(unittest.TestCase):
    def setUp(self):
        self.calibration = make_calibration()
        self.positive = self.calibration.variant("positive")
        self.negative = self.calibration.variant("negative")

    def test_positive_signal_never_decreases_as_raw_score_increases(self):
        previous = -1
        for raw in [index / 50.0 for index in range(0, 100)]:
            score = calculate_comment_signal_score(
                calibration=self.positive,
                predicted_score=raw,
            )
            self.assertGreaterEqual(score, previous)
            previous = score

    def test_negative_signal_increases_as_raw_score_becomes_more_negative(self):
        weaker = calculate_comment_signal_score(
            calibration=self.negative,
            predicted_score=-0.2,
        )
        stronger = calculate_comment_signal_score(
            calibration=self.negative,
            predicted_score=-1.8,
        )
        self.assertGreater(stronger, weaker)

    def test_scores_stay_within_range(self):
        for variant in (self.positive, self.negative):
            for raw in (-50.0, -1.0, 0.0, 1.0, 50.0):
                with self.subTest(variant=variant.model_variant, raw=raw):
                    score = calculate_comment_signal_score(
                        calibration=variant,
                        predicted_score=raw,
                    )
                    self.assertGreaterEqual(score, 0)
                    self.assertLessEqual(score, 100)

    def test_distribution_median_maps_near_fifty(self):
        positive_median = self.positive.quantile_scores[50]
        negative_median = self.negative.quantile_scores[50]
        self.assertAlmostEqual(
            calculate_comment_signal_score(
                calibration=self.positive,
                predicted_score=positive_median,
            ),
            50,
            delta=1,
        )
        self.assertAlmostEqual(
            calculate_comment_signal_score(
                calibration=self.negative,
                predicted_score=negative_median,
            ),
            50,
            delta=1,
        )

    def test_values_outside_distribution_are_clamped(self):
        self.assertEqual(
            calculate_comment_signal_score(
                calibration=self.positive,
                predicted_score=-99.0,
            ),
            0,
        )
        self.assertEqual(
            calculate_comment_signal_score(
                calibration=self.positive,
                predicted_score=99.0,
            ),
            100,
        )
        self.assertEqual(
            calculate_comment_signal_score(
                calibration=self.negative,
                predicted_score=-99.0,
            ),
            100,
        )
        self.assertEqual(
            calculate_comment_signal_score(
                calibration=self.negative,
                predicted_score=99.0,
            ),
            0,
        )

    def test_calibration_requires_enough_samples(self):
        with self.assertRaisesRegex(ValueError, "표본"):
            build_variant_calibration(
                model_variant="positive",
                artifact_id=POSITIVE_ARTIFACT_ID,
                predicted_scores=[0.1, 0.2, 0.3],
            )


class DailyCommentSignalTest(unittest.TestCase):
    def test_buy_direction_uses_positive_model(self):
        signal = make_signal(actual_supply_index=0.1951)
        self.assertEqual(signal.supply_direction, "BUY")
        self.assertEqual(signal.active_model_variant, "positive")
        self.assertEqual(signal.signal_status, "ready")
        self.assertEqual(signal.predicted_score, 0.5)
        self.assertIsNotNone(signal.comment_signal_score)
        self.assertEqual(
            signal.signal_level,
            resolve_signal_level(signal.comment_signal_score),
        )

    def test_sell_direction_uses_negative_model(self):
        signal = make_signal(actual_supply_index=-0.1951)
        self.assertEqual(signal.supply_direction, "SELL")
        self.assertEqual(signal.active_model_variant, "negative")
        self.assertEqual(signal.predicted_score, -0.5)

    def test_zero_supply_index_is_no_direction(self):
        signal = make_signal(actual_supply_index=0)
        self.assertEqual(signal.supply_direction, "NEUTRAL")
        self.assertIsNone(signal.active_model_variant)
        self.assertIsNone(signal.comment_signal_score)
        self.assertIsNone(signal.signal_level)
        self.assertEqual(signal.signal_status, "no_direction")

    def test_db_inference_status_is_used_without_feature_rejudgment(self):
        signal = make_signal(
            actual_supply_index=0.1951,
            positive_features=0,
            positive_status="ready",
        )
        self.assertEqual(signal.signal_status, "ready")
        self.assertIsNotNone(signal.comment_signal_score)
        self.assertEqual(signal.predicted_score, 0.5)

    def test_inactive_direction_features_do_not_block_signal(self):
        signal = make_signal(
            actual_supply_index=0.1951,
            negative_features=0,
        )
        self.assertEqual(signal.signal_status, "ready")

    def test_artifact_mismatch_is_rejected(self):
        results = make_results()
        results["positive"]["artifact_id"] = 999
        with self.assertRaisesRegex(ValueError, "artifact_id"):
            build_daily_comment_signal(
                stock_id=1,
                stock_code="000660",
                stock_name="SK하이닉스",
                model_date=date(2026, 8, 7),
                daily_document_id=10,
                comment_count=10,
                actual_supply_index=0.1,
                results_by_variant=results,
                calibration=make_calibration(),
            )


class SignalHistoryTest(unittest.TestCase):
    def setUp(self):
        self.calibration = make_calibration()

    def _signal(self, *, day, positive_score, features=8, status="ready"):
        return make_signal(
            actual_supply_index=0.1,
            model_date=date(2026, 8, day),
            calibration=self.calibration,
            positive_score=positive_score,
            positive_features=features,
            positive_status=status,
        )

    def test_history_uses_previous_trading_days_only(self):
        current = self._signal(day=7, positive_score=1.7)
        previous = [
            self._signal(day=3, positive_score=0.2),
            self._signal(day=4, positive_score=0.4),
            self._signal(day=5, positive_score=0.6),
            self._signal(day=6, positive_score=1.0),
            self._signal(day=7, positive_score=1.7),
        ]
        history = build_comment_signal_history(
            current_signal=current,
            previous_signals=previous,
        )
        self.assertEqual(history.history_size, 4)
        self.assertEqual(
            history.previous_signal_score,
            self._signal(day=6, positive_score=1.0).comment_signal_score,
        )
        self.assertEqual(
            history.signal_change,
            current.comment_signal_score - history.previous_signal_score,
        )

    def test_history_window_is_capped_at_five_days(self):
        current = self._signal(day=20, positive_score=1.9)
        previous = [
            self._signal(day=day, positive_score=day / 20.0)
            for day in range(1, 20)
        ]
        history = build_comment_signal_history(
            current_signal=current,
            previous_signals=previous,
        )
        self.assertEqual(history.history_size, 5)

    def test_days_without_signal_are_excluded(self):
        current = self._signal(day=7, positive_score=1.7)
        previous = [
            self._signal(
                day=6,
                positive_score=1.0,
                features=0,
                status="insufficient_features",
            ),
        ]
        history = build_comment_signal_history(
            current_signal=current,
            previous_signals=previous,
        )
        self.assertEqual(history.history_size, 0)
        self.assertIsNone(history.previous_signal_score)
        self.assertIsNone(history.signal_change)
        self.assertIsNone(history.signal_ma5)


class CalibrationArtifactTest(unittest.TestCase):
    def test_round_trip_preserves_quantiles(self):
        calibration = make_calibration()
        with tempfile.TemporaryDirectory() as directory:
            path = resolve_calibration_path(
                model_name="ridge_supply",
                model_version=4,
                calibration_dir=Path(directory),
            )
            save_signal_calibration(
                calibration=calibration,
                output_path=path,
            )
            loaded = load_signal_calibration(path)

        self.assertEqual(loaded.model_name, calibration.model_name)
        self.assertEqual(loaded.model_version, calibration.model_version)
        self.assertEqual(
            loaded.variant("positive").quantile_scores,
            calibration.variant("positive").quantile_scores,
        )
        self.assertEqual(
            loaded.variant("negative").artifact_id,
            NEGATIVE_ARTIFACT_ID,
        )

    def test_existing_artifact_is_not_overwritten(self):
        calibration = make_calibration()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            save_signal_calibration(
                calibration=calibration,
                output_path=path,
            )
            with self.assertRaises(FileExistsError):
                save_signal_calibration(
                    calibration=calibration,
                    output_path=path,
                )

    def test_non_monotonic_quantiles_are_rejected(self):
        calibration = make_calibration()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            save_signal_calibration(
                calibration=calibration,
                output_path=path,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["variants"]["positive"]["quantile_scores"][10] = 999.0
            path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "비내림차순"):
                load_signal_calibration(path)


class CalibrationArtifactMatchTest(unittest.TestCase):
    def artifact_record(self, **changes):
        record = {
            "artifact_id": POSITIVE_ARTIFACT_ID,
            "artifact_type": "ridge_text_grouped_random_bundle",
            "model_name": "ridge_supply",
            "model_variant": "positive",
            "model_version": 4,
            "artifact_schema_version": 2,
            "tokenizer_version": "kiwi_ver1",
            "vectorizer_name": "TfidfVectorizer",
            "scaler_name": "not_used",
            "dataset_start_date": date(2025, 1, 2),
            "dataset_end_date": date(2026, 7, 24),
        }
        record.update(changes)
        return record

    def test_matching_artifact_passes(self):
        verify_calibration_matches_artifact(
            calibration=make_calibration(),
            artifact_record=self.artifact_record(),
        )

    def test_model_version_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "model_version"):
            verify_calibration_matches_artifact(
                calibration=make_calibration(),
                artifact_record=self.artifact_record(model_version=5),
            )

    def test_tokenizer_version_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "tokenizer_version"):
            verify_calibration_matches_artifact(
                calibration=make_calibration(),
                artifact_record=self.artifact_record(
                    tokenizer_version="kiwi_ver2"
                ),
            )

    def test_artifact_type_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "artifact_type"):
            verify_calibration_matches_artifact(
                calibration=make_calibration(),
                artifact_record=self.artifact_record(
                    artifact_type="ridge_bundle"
                ),
            )

    def test_dataset_period_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "dataset_end_date"):
            verify_calibration_matches_artifact(
                calibration=make_calibration(),
                artifact_record=self.artifact_record(
                    dataset_end_date=date(2026, 6, 30)
                ),
            )

    def test_artifact_date_is_compared_as_iso_text(self):
        verify_calibration_matches_artifact(
            calibration=make_calibration(),
            artifact_record=self.artifact_record(
                dataset_start_date="2025-01-02",
                dataset_end_date="2026-07-24",
            ),
        )

    def test_artifact_id_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "artifact_id"):
            verify_calibration_matches_artifact(
                calibration=make_calibration(),
                artifact_record=self.artifact_record(artifact_id=999),
            )


if __name__ == "__main__":
    unittest.main()
