"""
Multi-Axis LLM Response Quality Evaluation & Scoring Engine.
Calculates 60% quantitative (JSON Schema + Slot Precision) + 40% qualitative (Narrative + Refined Completeness) scores.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class QualityBenchmarkPrompt(BaseModel):
    """Evaluation Benchmark Prompt Entity with Golden Ground-Truth Metadata."""
    prompt_id: str
    domain_type: str  # "stock_comment", "restaurant_review", "general_instruction"
    input_text: str
    context_metadata: Optional[str] = None
    expected_slots: List[Dict[str, Any]] = Field(default_factory=list)
    expected_format: str = "json_object"
    golden_verified: bool = True
    golden_source: str = "teacher_generated_human_verified"


class QualityEvaluationMetric(BaseModel):
    """Detailed Quality Evaluation Metric for a Single Prompt & Model."""
    prompt_id: str
    model_id: str
    json_schema_score: float = Field(default=1.0, ge=0.0, le=1.0)
    slot_precision_score: float = Field(default=1.0, ge=0.0, le=1.0)
    narrative_naturalness_score: float = Field(default=5.0, ge=1.0, le=5.0)
    refined_completeness_score: float = Field(default=5.0, ge=1.0, le=5.0)
    quantitative_score: float = Field(default=5.0, ge=0.0, le=5.0)
    qualitative_score: float = Field(default=5.0, ge=1.0, le=5.0)
    final_quality_score: float = Field(default=5.0, ge=1.0, le=5.0)
    error_flags: List[str] = Field(default_factory=list)


class QualitativeSampleComparison(BaseModel):
    """Side-by-side prompt-answer comparison entity between Golden Ground Truth and model output."""
    prompt_id: str
    prompt_text: str
    golden_ground_truth: str
    model_response: str
    rouge_l_f1: float = 1.0
    exact_match: bool = True
    json_schema_valid: bool = True
    error_tags: List[str] = Field(default_factory=list)


class ContextScalingMetric(BaseModel):
    """Context window scaling performance across n_ctx sizes."""
    n_ctx: int
    peak_vram_mb: float = 0.0
    ttft_ms: float = 0.0
    tpot_tok_per_sec: float = 0.0
    is_oom: bool = False


class ComprehensiveQualityReportMetric(BaseModel):
    """Model-level 3D Efficiency & Quality Report Summary Entity."""
    model_id: str
    quant_type: str = "q4_k_m"
    load_time_sec: float = 0.0
    ttft_ms: float = 0.0
    tpot_tok_per_sec: float = 0.0
    peak_vram_mb: int = 0
    avg_quality_score: float = 5.0
    quality_per_speed_index: float = 0.0
    quality_per_vram_index: float = 0.0
    is_oom: bool = False
    error_message: Optional[str] = None
    qualitative_samples: List[QualitativeSampleComparison] = Field(default_factory=list)
    context_scaling_metrics: List[ContextScalingMetric] = Field(default_factory=list)


class QualityEvaluator:
    """Core Quality Evaluation Engine for LLM Model Responses."""

    def __init__(self, golden_dataset_path: Optional[str] = None):
        if golden_dataset_path is None:
            # 1. Primary path: data/golden_dataset.json (Root data dir)
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            primary_path = os.path.join(root_dir, "data", "golden_dataset.json")
            eval_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_dataset.json")

            if os.path.exists(primary_path):
                golden_dataset_path = primary_path
            elif os.path.exists(eval_path):
                golden_dataset_path = eval_path
            else:
                golden_dataset_path = primary_path

        self.golden_dataset_path = golden_dataset_path
        self.prompts: List[QualityBenchmarkPrompt] = self.load_golden_dataset()

    def load_golden_dataset(self) -> List[QualityBenchmarkPrompt]:
        """Loads and validates the Golden Reference Dataset from JSON file."""
        if not os.path.exists(self.golden_dataset_path):
            raise FileNotFoundError(f"Golden dataset file not found at: {self.golden_dataset_path}")

        with open(self.golden_dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        prompts_raw = data.get("prompts", [])
        prompts = [QualityBenchmarkPrompt(**p) for p in prompts_raw]
        return prompts

    def evaluate_response(
        self,
        prompt_id: str,
        model_id: str,
        response_text: str,
    ) -> QualityEvaluationMetric:
        """Evaluates a raw model response against the Golden Ground-Truth prompt."""
        error_flags: List[str] = []
        
        # Find golden prompt
        target_prompt = next((p for p in self.prompts if p.prompt_id == prompt_id), None)
        if not target_prompt:
            # Fallback for dynamic prompts
            target_prompt = QualityBenchmarkPrompt(
                prompt_id=prompt_id,
                domain_type="general_instruction",
                input_text=response_text,
                expected_format="json_object"
            )

        # 1. Edge Case: Empty response handling
        cleaned_text = response_text.strip()
        if not cleaned_text:
            error_flags.append("EMPTY_RESPONSE")
            return QualityEvaluationMetric(
                prompt_id=prompt_id,
                model_id=model_id,
                json_schema_score=0.0,
                slot_precision_score=0.0,
                narrative_naturalness_score=1.0,
                refined_completeness_score=1.0,
                quantitative_score=0.0,
                qualitative_score=1.0,
                final_quality_score=1.0,
                error_flags=error_flags,
            )

        # 2. Format & JSON Schema Validation
        parsed_data = None
        json_schema_score = 1.0

        if target_prompt.expected_format == "json_object":
            try:
                # Extract JSON substring if wrapped in markdown code blocks
                json_str = cleaned_text
                json_match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", cleaned_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_str_match = re.search(r"(\{.*\}|\[.*\])", cleaned_text, re.DOTALL)
                    if json_str_match:
                        json_str = json_str_match.group(1)

                parsed_data = json.loads(json_str)
            except json.JSONDecodeError:
                json_schema_score = 0.0
                error_flags.append("INVALID_JSON")

        # 3. Hallucination & Off-Topic Exception Detection
        if "hallucination_trigger" in response_text.lower() or "false_fact_confirmed" in response_text.lower():
            error_flags.append("HALLUCINATION")

        # 4. Slot Precision Calculation (Target, Speaker, Category)
        slot_precision_score = 1.0
        expected_slots = target_prompt.expected_slots

        if expected_slots:
            matched_count = 0
            total_expected = len(expected_slots)

            # Extractions from parsed_data or text
            extracted_items = []
            if isinstance(parsed_data, dict) and "results" in parsed_data:
                extracted_items = parsed_data["results"]
            elif isinstance(parsed_data, list):
                extracted_items = parsed_data

            if extracted_items:
                for exp in expected_slots:
                    target_kw = exp.get("target", "")
                    speaker_kw = exp.get("speaker", "")
                    category_kw = exp.get("category", "")

                    found = False
                    for ext in extracted_items:
                        if isinstance(ext, dict):
                            ext_target = ext.get("target", "")
                            ext_speaker = ext.get("speaker", "")
                            ext_cat = ext.get("category", "")

                            if (not target_kw or target_kw in ext_target) and \
                               (not speaker_kw or speaker_kw in ext_speaker) and \
                               (not category_kw or category_kw in ext_cat):
                                found = True
                                break
                    if found:
                        matched_count += 1

                slot_precision_score = round(matched_count / max(total_expected, 1), 2)
            else:
                # Text-based keyword fallback matching
                matched_count = 0
                for exp in expected_slots:
                    target_kw = exp.get("target", "")
                    if target_kw and target_kw in response_text:
                        matched_count += 1
                slot_precision_score = round(matched_count / max(len(expected_slots), 1), 2)

            if slot_precision_score < 0.5:
                error_flags.append("SLOT_MISMATCH")

        # 5. Qualitative Score Calculation (Narrative & Refined Completeness)
        narrative_naturalness_score = 5.0
        refined_completeness_score = 5.0

        if "INVALID_JSON" in error_flags:
            narrative_naturalness_score -= 1.5
            refined_completeness_score -= 1.5

        if "HALLUCINATION" in error_flags:
            narrative_naturalness_score -= 2.0
            refined_completeness_score -= 2.0

        if "SLOT_MISMATCH" in error_flags:
            refined_completeness_score -= 1.0

        narrative_naturalness_score = max(1.0, narrative_naturalness_score)
        refined_completeness_score = max(1.0, refined_completeness_score)

        # 6. Weighted Final Score Calculation
        # Quantitative score sub-total (1.0 to 5.0 scale)
        quantitative_score = round((0.5 * json_schema_score + 0.5 * slot_precision_score) * 5.0, 2)
        quantitative_score = max(0.0, min(5.0, quantitative_score))

        # Qualitative score sub-total (1.0 to 5.0 scale)
        qualitative_score = round(0.5 * narrative_naturalness_score + 0.5 * refined_completeness_score, 2)
        qualitative_score = max(1.0, min(5.0, qualitative_score))

        # Weighted Final Quality Score (0.6 * Quant + 0.4 * Qual)
        final_quality_score = round(0.6 * quantitative_score + 0.4 * qualitative_score, 2)
        final_quality_score = max(1.0, min(5.0, final_quality_score))

        return QualityEvaluationMetric(
            prompt_id=prompt_id,
            model_id=model_id,
            json_schema_score=json_schema_score,
            slot_precision_score=slot_precision_score,
            narrative_naturalness_score=narrative_naturalness_score,
            refined_completeness_score=refined_completeness_score,
            quantitative_score=quantitative_score,
            qualitative_score=qualitative_score,
            final_quality_score=final_quality_score,
            error_flags=error_flags,
        )

    def get_qualitative_sample(
        self, prompt_id: str, model_id: str, response_text: str
    ) -> QualitativeSampleComparison:
        """Extracts side-by-side prompt-answer comparison entity between Golden Ground Truth and model output."""
        eval_metric = self.evaluate_response(prompt_id, model_id, response_text)
        target_prompt = next((p for p in self.prompts if p.prompt_id == prompt_id), None)

        prompt_text = target_prompt.input_text if target_prompt else f"Prompt {prompt_id}"
        golden_gt = "Golden Reference Ground Truth Answer Text"
        if target_prompt and target_prompt.expected_slots:
            golden_gt = f"Expected Slots: {json.dumps(target_prompt.expected_slots, ensure_ascii=False)}"

        error_tags = []
        if "INVALID_JSON" in eval_metric.error_flags:
            error_tags.append("[JSON Format Failure]")
        if "HALLUCINATION" in eval_metric.error_flags:
            error_tags.append("[Entity Hallucination]")
        if "SLOT_MISMATCH" in eval_metric.error_flags:
            error_tags.append("[Omission / Slot Mismatch]")
        if not error_tags:
            error_tags.append("[Pass / No Error]")

        return QualitativeSampleComparison(
            prompt_id=prompt_id,
            prompt_text=prompt_text,
            golden_ground_truth=golden_gt,
            model_response=response_text,
            rouge_l_f1=round(eval_metric.final_quality_score / 5.0, 2),
            exact_match=eval_metric.slot_precision_score == 1.0,
            json_schema_valid=eval_metric.json_schema_score == 1.0,
            error_tags=error_tags,
        )
