from datetime import date
from typing import Final, Literal


ModelVariant = Literal["positive", "negative"]

SERVICE_MODEL_NAME: Final = "ridge_supply"
ACTIVE_SERVICE_MODEL_VERSION: Final = 4
SERVICE_MODEL_VARIANTS: Final[tuple[ModelVariant, ModelVariant]] = ("positive", "negative")
SERVICE_MODEL_ARTIFACT_SCHEMA_VERSION: Final = 2
REQUIRED_TOKENIZER_VERSION: Final = "kiwi_ver1"

SERVICE_INFERENCE_START_DATE: Final = date(2026, 7, 25)
MIN_RECOGNIZED_FEATURE_COUNT: Final = 5
MIN_VOCABULARY_COVERAGE: Final = 0.6
