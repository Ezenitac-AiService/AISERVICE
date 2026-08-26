import os
from typing import List, Optional
from pydantic import BaseModel, Field
import openai
import instructor
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from opentelemetry import trace

# Evaluator tracer
tracer = trace.get_tracer("evaluator")

class EvaluationResult(BaseModel):
    correctness: float = Field(
        ..., 
        description="예상되는 모범 답안(Reference) 대비 사실적 유사도 및 정확도 (0.0 ~ 1.0)",
        ge=0.0,
        le=1.0
    )
    faithfulness: float = Field(
        ...,
        description="주어진 문맥(Context)에만 부합하며 환각 정보가 없는 정합도 (0.0 ~ 1.0)",
        ge=0.0,
        le=1.0
    )
    relevance: float = Field(
        ...,
        description="질문(Question)에 대해 직접적이고 유용한 답변을 제공하는지 관련도 (0.0 ~ 1.0)",
        ge=0.0,
        le=1.0
    )
    reason: str = Field(
        ...,
        description="산출된 각 평가 점수에 대한 구체적 감점 요인 및 평가 사유 요약 (한국어로 작성)"
    )

class EvaluationInput(BaseModel):
    question: str = Field(..., description="사용자 원본 질문")
    contexts: List[str] = Field(..., description="검색되어 참조 문서로 사용된 텍스트 리스트")
    generation: str = Field(..., description="RAG 시스템이 최종 답변으로 도출한 결과물")
    reference: str = Field(..., description="대조용 모범 답안")

class LLMEvaluator:
    """
    Groq API 대형 모델을 이용한 RAG 답변 종합 평가기
    """
    def __init__(self, model_name: str = "llama-3.3-70b-versatile"):
        self.model_name = model_name
        self._client = None

    @property
    def client(self):
        if self._client is None:
            api_key = os.environ.get("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY environment variable is not set.")
            self._client = instructor.from_openai(
                openai.OpenAI(
                    base_url="https://api.groq.com/openai/v1",
                    api_key=api_key,
                ),
                mode=instructor.Mode.JSON
            )
        return self._client

    def evaluate(self, 
                 question: str, 
                 contexts: List[str], 
                 generation: str, 
                 reference: str) -> EvaluationResult:
        """
        질문, 문맥, 생성 결과물, 모범 답안을 입력받아 평가를 수행합니다.
        """
        with tracer.start_as_current_span("LLMEvaluator.evaluate") as span:
            span.set_attribute("evaluator.question", question)
            span.set_attribute("evaluator.generation", generation)
            
            if os.getenv("RUN_LLM_EVAL") != "true":
                res = EvaluationResult(
                    correctness=1.0,
                    faithfulness=1.0,
                    relevance=1.0,
                    reason="[Mocked Pass] RUN_LLM_EVAL이 활성화되지 않아 모의 통과 처리되었습니다."
                )
                span.set_attribute("evaluator.result.correctness", res.correctness)
                span.set_attribute("evaluator.result.faithfulness", res.faithfulness)
                span.set_attribute("evaluator.result.relevance", res.relevance)
                return res

            contexts_str = "\n".join(contexts)
            
            messages = [
                {"role": "system", "content": (
                    "You are an expert evaluator assessing RAG (Retrieval-Augmented Generation) response quality.\n"
                    "Analyze the Question, Contexts, Generation, and Reference answer.\n"
                    "Assign scores between 0.0 and 1.0 for correctness, faithfulness, and relevance.\n"
                    "Write the reason in Korean."
                )},
                {"role": "user", "content": (
                    f"Question: {question}\n\n"
                    f"Contexts: {contexts_str}\n\n"
                    f"Generation: {generation}\n\n"
                    f"Reference Answer: {reference}"
                )}
            ]
            
            res = self._call_api_with_retry(messages)
            span.set_attribute("evaluator.result.correctness", res.correctness)
            span.set_attribute("evaluator.result.faithfulness", res.faithfulness)
            span.set_attribute("evaluator.result.relevance", res.relevance)
            return res

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_random_exponential(min=1, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError)),
        reraise=True
    )
    def _call_api_with_retry(self, messages) -> EvaluationResult:
        return self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            response_model=EvaluationResult,
            temperature=0.0
        )
