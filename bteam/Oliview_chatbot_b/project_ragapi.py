import os
import time
import json
import httpx
import pymysql
import numpy as np
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles  # ⭕ 정적 파일 시스템 모듈 장착

# common 모듈 임포트
from common import (
    load_sample_config,
    clean_think_tags,
    clean_hanja_and_artifacts,
    NO_THINK_SYSTEM_PROMPT,
    get_fast_model,
    get_synthesis_model,
    budget_context_documents,
    RAG_STOPWORDS,
    get_active_brands_cached,
    extract_brand_entity,
    is_dummy_name,
    is_valid_product_name,
    PipelinePhase,
    StepEvent,
    ReferenceReview,
    RagExecutionMetadata,
    FallbackRecommendation,
    clean_product_name_for_search,
    build_oliveyoung_search_url,
)

try:
    from oliview_core.session import session_store
    from oliview_core.guardrail import PromptInjectionGuardrail, EarlyIntentGuardrail
    from oliview_core.config import get_settings
    from oliview_core.graph_orchestrator import MultiTargetGraphOrchestrator
except ImportError:
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from oliview_core.session import session_store
    from oliview_core.guardrail import PromptInjectionGuardrail, EarlyIntentGuardrail
    from oliview_core.config import get_settings
    from oliview_core.graph_orchestrator import MultiTargetGraphOrchestrator


# ==============================================================================
# 1. ⚙️ 전역 환경 설정 및 모델/엔드포인트 토폴로지 동적 구성
# ==============================================================================
config = load_sample_config()
SERVER_HOST = os.getenv("SERVER_HOST", config["server_host"])
MAIN_PORT = os.getenv("MAIN_PORT", str(config.get("main_port", 8081)))
EMBED_PORT = os.getenv("EMBEDDING_PORT", os.getenv("EMBED_PORT", str(config.get("embed_port", 8090))))
RERANK_PORT = os.getenv("RERANK_PORT", str(config.get("rerank_port", 8091)))

if not SERVER_HOST.startswith("http://") and not SERVER_HOST.startswith("https://"):
    BASE_URL = f"http://{SERVER_HOST}"
else:
    BASE_URL = SERVER_HOST

EMBEDDING_SERVER_URL = f"{BASE_URL}:{EMBED_PORT}/v1/embeddings"
RERANK_SERVER_URL = f"{BASE_URL}:{RERANK_PORT}/v1/embeddings"
LLM_SERVER_URL = f"{BASE_URL}:{MAIN_PORT}/v1/chat/completions"  
MODEL_NAME = config["default_model"]
FAST_MODEL_NAME = get_fast_model()
SYNTHESIS_MODEL_NAME = get_synthesis_model()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "bteam_db"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "gp123"),
    "password": os.getenv("DB_PASSWORD", "GP123!"),
    "database": os.getenv("DB_NAME", os.getenv("DB_NAME3", "oliview_project")),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

app = FastAPI(
    title="Oliview Production RAG Engine API",
    description="하이브리드 리랭킹 검색 결과와 8081 생성 LLM을 결합한 완결형 검색 증강 생성 API",
    version="3.0.0",
    root_path=os.getenv("FASTAPI_ROOT_PATH", "/bteam/chatb")
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# 2. 🧠 Pydantic v2 웹 입출력 패킷 스키마 정의
# ==============================================================================
class SearchRequest(BaseModel):
    query: str = Field(description="사용자 질문 자연어 문장")
    brand: Optional[str] = Field(default=None)
    sentiment: Optional[str] = Field(default=None)
    keyword: Optional[str] = Field(default=None)
    fetch_k: int = Field(default=20)
    top_n: int = Field(default=3)
    model: Optional[str] = Field(default=None, description="합성 LLM 모델 선택 (qwen3.5-4b, qwen3.5-9b 등)")
    session_id: Optional[str] = Field(default=None, description="Redis 영속 멀티턴 대화 세션 ID")

class FastChatRequest(BaseModel):
    query: str = Field(description="일반 질문 또는 의도 분류용 질의")
    max_tokens: int = Field(default=512)
    session_id: Optional[str] = Field(default=None, description="Redis 영속 멀티턴 대화 세션 ID")

class FastChatResponse(BaseModel):
    model: str
    answer: str
    latency_sec: float

class RecommendedProduct(BaseModel):
    rank: int
    product_name: str
    brand_name: str
    category: str
    review_score: int
    separated_sentence: str
    display_name: str
    sentiment_label: str
    cosine_similarity: Optional[float] = 0.0
    rerank_score: Optional[float] = 0.0

class RagSearchResponse(BaseModel):
    llm_answer: str
    search_results: List[RecommendedProduct]
    model_used: Optional[str] = None

# ==============================================================================
# 3. 🔬 수학 및 벡터/AI 인퍼런스 보조 함수
# ==============================================================================
def get_query_embedding(query_text: str):
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                EMBEDDING_SERVER_URL,
                json={"model": config.get("embedding_model", "bge-m3"), "input": [query_text]},
                headers={"Connection": "close"}
            )
            resp.raise_for_status()
            res_json = resp.json()
            return res_json["data"][0]["embedding"]
    except Exception as e:
        print(f"⚠️ 1단계 질문 텍스트 임베딩 실패: {e}")
        return None

def get_rerank_scores(query_text: str, documents: List[str]):
    try:
        with httpx.Client(timeout=5.0) as client:
            # 질문 벡터 획득
            r_q = client.post(
                RERANK_SERVER_URL,
                json={"input": query_text},
                headers={"Connection": "close"}
            ).json()
            raw_q = np.asarray(r_q["data"][0]["embedding"], dtype=np.float32)
            if raw_q.ndim == 2:
                q_vec = np.mean(raw_q, axis=0)
            else:
                q_vec = raw_q.flatten()

            # 후보 문장들 벡터 일괄 획득
            r_docs = client.post(
                RERANK_SERVER_URL,
                json={"input": documents},
                headers={"Connection": "close"}
            ).json()
            doc_datas = r_docs["data"]

            scores = []
            for d in doc_datas:
                raw_d = np.asarray(d["embedding"], dtype=np.float32)
                if raw_d.ndim == 2:
                    d_vec = np.mean(raw_d, axis=0)
                else:
                    d_vec = raw_d.flatten()
                dot = np.dot(q_vec, d_vec)
                norm1 = np.linalg.norm(q_vec)
                norm2 = np.linalg.norm(d_vec)
                sim = float(dot / (norm1 * norm2)) if (norm1 * norm2) > 0 else 0.0
                scores.append(sim)
            return scores
    except Exception as e:
        print(f"⚠️ 2단계 리랭커 연산 실패: {e}")
        return None


def cosine_similarity(v1, v2):
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return float(dot_product / (norm_v1 * norm_v2))

def generate_llm_rag_answer(query_text: str, search_results: List[RecommendedProduct], model_override: Optional[str] = None) -> tuple[str, str]:
    """RAG 문맥 기반 고품질 최종 답변 합성 함수 (9B 2K 컨텍스트 가드레일 & Spec 021 프롬프트 인젝션 가드레일 내장)."""
    # Spec 021: Tier 1 Prompt Injection Guardrail
    detection = PromptInjectionGuardrail.detect_injection(query_text)
    if detection.is_blocked:
        return PromptInjectionGuardrail.SAFE_BLOCKED_RESPONSE, "guardrail-blocked"

    target_model = model_override or get_synthesis_model()
    
    # 9B 2K 컨텍스트 초과 방어 가드레일 적용
    budgeted_results = budget_context_documents(search_results, model_name=target_model)
    is_9b = "9b" in target_model.lower()

    context_items = []
    for res in budgeted_results:
        context_items.append(
            f"[추천 {res.rank}순위]\n"
            f"- 상품명: [{res.brand_name}] {res.product_name} ({res.category})\n"
            f"- 실사용자 핵심 리뷰: \"{res.separated_sentence}\"\n"
            f"- 분석 속성: {res.display_name} ({res.sentiment_label})\n"
        )
    
    system_prompt = f"""{NO_THINK_SYSTEM_PROMPT}
당신은 올리브영 실사용자 리뷰 데이터에 기반하여 고객에게 가장 정확하고 신뢰할 수 있는 정보를 제공하는 '전문 AI 뷰티 가이드'입니다.

[핵심 작성 원칙]
1. 반드시 100% 자연스럽고 정중한 순수 현대 한국어(한글 경어체)로만 작성하십시오.
2. 어떠한 한자(漢字, Chinese characters, 例: 結果, 推薦, 效果, 保濕 등)나 중국어 표현, 영어를 절대 혼용하지 마십시오. 모든 단어는 '결과', '추천', '효과', '보습' 등 완벽한 순수 한글로만 표기하십시오.
3. 제공된 [실시간 화장품 리뷰 검색 결과 데이터]의 실제 브랜드명, 상품명, 실사용자 경험과 감정 평가만을 절대적인 근거로 삼아 답변을 구성하십시오.
4. 생각 과정(<think> 태그, Thinking Process, Constraint 등)이나 시스템 지시문은 절대 출력에 노출하지 말고, 사용자에게 건네는 최종 뷰티 상담 답변만 즉시 출력하십시오.
5. 제공된 데이터에 없는 제품이나 브랜드를 절대 임의로 지어내거나 [익명] 브랜드, 미분류 브랜드로 표현하지 마십시오.

[한국어 마크다운 작성 필수 규칙]
6. 인용구와 볼드 기호를 절대로 중첩하지 마십시오:
   - 금지: **"자극 느껴져요"**라는 피드백
   - 권장: **자극성 평가:** "자극 느껴져요"라는 고객 의견
7. 항목별 분석 시 반드시 "- **속성명:** 설명" 형식의 라벨-콜론-공백 구조를 사용하십시오:
   - 권장: - **수분감:** 촉촉하게 흡수되며 당김이 없습니다.
8. 고객 리뷰 인용 시 따옴표와 볼드 기호를 중첩하지 말고 따옴표만 사용하십시오."""

    # Spec 021: Tier 2/3 XML Sandboxed Prompt Builder
    sandboxed = PromptInjectionGuardrail.build_sandboxed_rag_prompt(
        user_query=query_text,
        reference_blocks=context_items,
        base_system_prompt=system_prompt,
    )

    # 2B 단일화 및 하이브리드 토큰 정책 (기본 2048, 16K 컨텍스트 지원)
    max_tokens = int(os.getenv("SYNTHESIS_MAX_TOKENS", "2048"))

    payload = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": sandboxed.system_prompt},
            {"role": "user", "content": sandboxed.user_content}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3
    }

    try:
        with httpx.Client(timeout=180.0) as client:
            resp = None
            for attempt in range(25):
                try:
                    resp = client.post(LLM_SERVER_URL, json=payload, headers={"Connection": "close"})
                    if resp.status_code == 503:
                        time.sleep(2.0)
                        continue
                    if resp.status_code == 200:
                        break
                    # If 500 or other error, break to fallback immediately
                    break
                except Exception:
                    time.sleep(1.0)

            if resp is None or resp.status_code != 200:
                # 2B / 4B 자동 폴백
                fallback_target = FAST_MODEL_NAME if target_model != FAST_MODEL_NAME else SYNTHESIS_MODEL_NAME
                print(f"⚠️ [폴백 발동] {target_model} 호출 실패({getattr(resp, 'status_code', 'error')})로 {fallback_target}로 자동 전환")
                payload["model"] = fallback_target
                payload["max_tokens"] = 2048
                try:
                    resp_fallback = client.post(LLM_SERVER_URL, json=payload, headers={"Connection": "close"})
                    if resp_fallback.status_code == 200:
                        res = resp_fallback.json()
                        raw_answer = res["choices"][0]["message"]["content"] or ""
                        clean_answer = clean_hanja_and_artifacts(clean_think_tags(raw_answer, show_think=False))
                        is_safe, final_answer = PromptInjectionGuardrail.verify_output_safety(clean_answer, canary_token=sandboxed.canary_token)
                        return final_answer.strip(), f"{fallback_target}-fallback"
                except Exception as fb_err:
                    print(f"❌ [폴백 실행 실패]: {fb_err}")
                return "⚠️ LLM 서빙 백엔드가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도해주세요.", target_model

            res = resp.json()
            raw_answer = res["choices"][0]["message"]["content"] or ""
            clean_answer = clean_think_tags(raw_answer, show_think=False)
            clean_answer = clean_hanja_and_artifacts(clean_answer)

            # Spec 021: Tier 4 Output Guardrail & Canary Check
            is_safe, final_answer = PromptInjectionGuardrail.verify_output_safety(clean_answer, canary_token=sandboxed.canary_token)
            return final_answer.strip(), target_model

    except Exception as e:
        return f"⚠️ [RAG 생성 실패] LLM 서버와의 통신 중 장애가 발생했습니다: {e}", target_model


def generate_llm_rag_answer_stream(query: str, retrieved_docs: list, model_override: str = None):
    """
    8081 vLLM 생성 서버와 통신하여 실시간 토큰을 yield하는 스트리밍 제너레이터 (Spec 021 가드레일 내장).
    """
    # Spec 021: Tier 1 Prompt Injection Guardrail Pre-check
    detection = PromptInjectionGuardrail.detect_injection(query)
    if detection.is_blocked:
        yield PromptInjectionGuardrail.SAFE_BLOCKED_RESPONSE
        return

    target_model = model_override or SYNTHESIS_MODEL_NAME
    is_9b = ("9b" in target_model.lower())

    # 2B 단일화 및 하이브리드 토큰 정책 (기본 2048, 16K 컨텍스트 지원)
    max_tokens = int(os.getenv("SYNTHESIS_MAX_TOKENS", "2048"))
    system_prompt = NO_THINK_SYSTEM_PROMPT

    if is_9b:
        budgeted_docs = budget_context_documents(retrieved_docs, budget=1500, is_9b=True)
    else:
        budgeted_docs = retrieved_docs

    context_blocks = []
    for item in budgeted_docs:
        if isinstance(item, RecommendedProduct):
            context_blocks.append(f"[{item.brand_name}] {item.product_name} ({item.category} / {item.display_name} / {item.sentiment_label}): {item.separated_sentence}")
        elif isinstance(item, dict):
            context_blocks.append(f"[{item.get('brand_name')}] {item.get('product_name')} ({item.get('category')} / {item.get('display_name')} / {item.get('sentiment_label')}): {item.get('separated_sentence')}")

    # Spec 021: Tier 2/3 XML Sandboxing & Canary Token
    sandboxed = PromptInjectionGuardrail.build_sandboxed_rag_prompt(
        user_query=query,
        reference_blocks=context_blocks,
        base_system_prompt=system_prompt,
    )

    payload = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": sandboxed.system_prompt},
            {"role": "user", "content": sandboxed.user_content}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "stream": True,
    }

    try:
        with httpx.Client(timeout=180.0) as client:
            with client.stream("POST", LLM_SERVER_URL, json=payload, headers={"Connection": "close"}) as response:
                if response.status_code != 200:
                    fb_ans, fb_mod = generate_llm_rag_answer(query, retrieved_docs, model_override=FAST_MODEL_NAME)
                    yield fb_ans
                    return

                buffer = ""
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_part = line[6:].strip()
                        if data_part == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_part)
                            token = chunk["choices"][0]["delta"].get("content", "")
                            if token:
                                buffer += token
                                # Spec 021: Tier 4 Output Guardrail & Canary Verification
                                is_safe, _ = PromptInjectionGuardrail.verify_output_safety(buffer, canary_token=sandboxed.canary_token)
                                if not is_safe:
                                    yield PromptInjectionGuardrail.SAFE_BLOCKED_RESPONSE
                                    return
                                yield token
                        except Exception:
                            continue
    except Exception as e:
        yield f" [통신 오류: {e}]"


# ==============================================================================
# 4. 🚀 FastAPI REST API 엔드포인트 라우터 (RAG 파이프라인 탑재)
# ==============================================================================
@app.post("/api/v1/search", response_model=RagSearchResponse, tags=["AI RAG Search"])
def search_products_with_rag(request_body: SearchRequest):
    # Spec 022: Step 0 Early Intent & Security Gate (Before DB Connection!)
    decision = EarlyIntentGuardrail.evaluate_gate(request_body.query)
    if decision.is_blocked:
        return RagSearchResponse(
            llm_answer=decision.refusal_message,
            search_results=[],
            model_used="guardrail-early-blocked"
        )

    rerank_scores = []
    
    # 🟢 1. 활성 브랜드 사전 매칭 및 불용어 제거 (006-rag-brand-guardrail)
    active_brands = get_active_brands_cached(lambda: pymysql.connect(**DB_CONFIG))
    detected_brand, filtered_tokens = extract_brand_entity(request_body.query, active_brands)
    target_brand = request_body.brand or detected_brand
    
    raw_query_vector = get_query_embedding(request_body.query)
    if raw_query_vector is None:
        raise HTTPException(status_code=500, detail="AI 임베딩 서버 통신 실패로 질문 벡터를 생성하지 못했습니다.")
    
    query_vector = np.asarray(raw_query_vector, dtype=np.float32).flatten()
    
    # [가드레일 변수 초기화] 외부 except 블록에서 참조할 수 있도록 미리 선언
    connection = None
    
    try:
        connection = pymysql.connect(**DB_CONFIG)

        # 🟢 2. 특정 브랜드 질의 시 리뷰 데이터 존재 여부 선행 검증 (부재 브랜드 방어)
        if target_brand:
            with connection.cursor() as check_cursor:
                check_cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt 
                    FROM `review_aspect_sentences` 
                    WHERE `brand_name` = %s 
                      AND `embedding_vector` IS NOT NULL 
                      AND `brand_name` IS NOT NULL AND TRIM(`brand_name`) != '' AND `brand_name` != '미분류 브랜드'
                      AND `product_name` IS NOT NULL AND TRIM(`product_name`) != '' AND `product_name` != '미분류 상품'
                    """,
                    (target_brand,)
                )
                row_cnt = check_cursor.fetchone()
                cnt = row_cnt.get("cnt", 0) if isinstance(row_cnt, dict) else (row_cnt[0] if row_cnt else 0)
                if cnt == 0:
                    if not request_body.brand:
                        # Auto-detected brand had 0 reviews -> fallback to searching all brands!
                        target_brand = None
                    else:
                        if connection and connection.open:
                            connection.close()
                        return RagSearchResponse(
                            llm_answer=f"죄송합니다. 현재 '{target_brand}' 브랜드의 등록 상품 및 리뷰 데이터가 올리뷰에 존재하지 않습니다. 올리브영에 등록된 다른 브랜드명으로 검색해 주세요.",
                            search_results=[],
                            model_used="brand-guardrail"
                        )

        # 🟢 3. 데이터베이스 쿼리 레벨 공식 활성 브랜드 INNER JOIN 및 결측치 원천 배제
        candidates = []
        with connection.cursor() as cursor:
            sql_select = """
                SELECT 
                    r.`aspect_sentence_id`, r.`separated_sentence`, r.`embedding_vector`,
                    r.`product_name`, r.`brand_name`, r.`category`,
                    r.`display_name`, r.`sentiment_label`
                FROM `review_aspect_sentences` r
                INNER JOIN `brands` b ON r.`brand_name` = b.`brand_name`
                WHERE r.`embedding_vector` IS NOT NULL
                  AND b.`is_active` = 1
                  AND r.`brand_name` IS NOT NULL AND TRIM(r.`brand_name`) != ''
                  AND r.`product_name` IS NOT NULL AND TRIM(r.`product_name`) != ''
            """
            
            params = []
            if target_brand:
                sql_select += " AND r.`brand_name` = %s"
                params.append(target_brand)
            
            if request_body.sentiment:
                sql_select += " AND r.`sentiment_label` = %s"
                params.append(request_body.sentiment)
                
            if request_body.keyword:
                sql_select += " AND (r.`product_name` LIKE %s OR r.`category` LIKE %s OR r.`separated_sentence` LIKE %s)"
                like_pattern = f"%{request_body.keyword}%"
                params.extend([like_pattern, like_pattern, like_pattern])
            elif filtered_tokens:
                token_clauses = ["(r.`separated_sentence` LIKE %s OR r.`product_name` LIKE %s OR r.`category` LIKE %s)"] * len(filtered_tokens[:3])
                sql_select += f" AND ({' OR '.join(token_clauses)})"
                for tok in filtered_tokens[:3]:
                    p = f"%{tok}%"
                    params.extend([p, p, p])

            sql_select += " ORDER BY r.`aspect_sentence_id` DESC LIMIT 2000"
            cursor.execute(sql_select, params)
            candidates = cursor.fetchall()

            # If token filter yielded no matches, fallback to broader candidate pool
            if not candidates:
                fallback_sql = """
                    SELECT 
                        r.`aspect_sentence_id`, r.`separated_sentence`, r.`embedding_vector`,
                        r.`product_name`, r.`brand_name`, r.`category`,
                        r.`display_name`, r.`sentiment_label`
                    FROM `review_aspect_sentences` r
                    INNER JOIN `brands` b ON r.`brand_name` = b.`brand_name`
                    WHERE r.`embedding_vector` IS NOT NULL
                      AND b.`is_active` = 1
                      AND r.`brand_name` IS NOT NULL AND TRIM(r.`brand_name`) != ''
                      AND r.`product_name` IS NOT NULL AND TRIM(r.`product_name`) != ''
                """
                fallback_params = []
                if target_brand:
                    fallback_sql += " AND r.`brand_name` = %s"
                    fallback_params.append(target_brand)
                fallback_sql += " ORDER BY r.`aspect_sentence_id` DESC LIMIT 2000"
                cursor.execute(fallback_sql, fallback_params)
                candidates = cursor.fetchall()
            
        # 🟢 조회 직후 의도적으로 연결을 먼저 해제하여 Cursor Closed 현상 방지
        if connection and connection.open:
            connection.close()

        # 4. 순수 파이썬 데이터 상태에서 1단계 벡터 유사도 계산 진행
        if not candidates:
            return RagSearchResponse(llm_answer="🔍 조건에 부합하는 매칭 데이터가 없어 답변을 생성할 수 없습니다.", search_results=[])
            
        stage1_results = []
        for row in candidates:
            try:
                target_vector = np.asarray(json.loads(row["embedding_vector"]), dtype=np.float32).flatten()
                if target_vector.size != 1024: 
                    continue
            except Exception: 
                continue
            
            sim_score = cosine_similarity(query_vector, target_vector)
            stage1_results.append({**row, "cosine_sim": sim_score})

        stage1_results.sort(key=lambda x: x["cosine_sim"], reverse=True)
        subset_candidates = stage1_results[:request_body.fetch_k]
        
        if not subset_candidates:
            return RagSearchResponse(llm_answer="🔍 1단계 스크리닝 결과 만족하는 매칭 데이터가 없어 답변을 생성할 수 없습니다.", search_results=[])
        
        # 5. 리랭커 통신 및 예외 처리 가드레일 (인덱스 에러 철저 방어)
        rerank_docs = [row["separated_sentence"] for row in subset_candidates]
        fetched_scores = get_rerank_scores(request_body.query, rerank_docs)
        
        if not fetched_scores or len(fetched_scores) != len(subset_candidates):
            rerank_scores = [row["cosine_sim"] for row in subset_candidates]
        else:
            rerank_scores = fetched_scores
            
        # 6. 최종 결과 패킷 구조화 (결측치 2차 방어 및 더미/익명 브랜드/추정 상품명 원천 차단)
        final_reranked_results = []
        for i, row in enumerate(subset_candidates):
            p_name = str(row.get("product_name") or "").strip()
            b_name = str(row.get("brand_name") or "").strip()
            if is_dummy_name(b_name) or not is_valid_product_name(p_name):
                continue

            final_reranked_results.append({
                "product_name": p_name,
                "brand_name": b_name,
                "category": str(row.get("category") or "화장품"),
                "review_score": 5, 
                "separated_sentence": str(row.get("separated_sentence") or ""),
                "display_name": str(row.get("display_name") or "일반 속성"),
                "sentiment_label": str(row.get("sentiment_label") or "중립"),
                "cosine_similarity": row["cosine_sim"],
                "rerank_score": rerank_scores[i]
            })

        final_reranked_results.sort(key=lambda x: x["rerank_score"], reverse=True)
        
        web_response_list = []
        seen_products = set()
        rank_counter = 1
        
        for res in final_reranked_results:
            p_name = res["product_name"]
            if p_name in seen_products:
                continue
            seen_products.add(p_name)
            
            web_response_list.append(
                RecommendedProduct(
                    rank=rank_counter,
                    product_name=res["product_name"],
                    brand_name=res["brand_name"],
                    category=res["category"],
                    review_score=res["review_score"],
                    separated_sentence=res["separated_sentence"],
                    display_name=res["display_name"],
                    sentiment_label=res["sentiment_label"]
                )
            )
            rank_counter += 1
            if len(web_response_list) == request_body.top_n:
                break

        if not web_response_list:
            fallback_msg = f"죄송합니다. 현재 '{target_brand}' 브랜드의 등록 상품 및 리뷰 데이터가 올리뷰에 존재하지 않습니다. 올리브영에 등록된 다른 브랜드명으로 검색해 주세요." if target_brand else "관련 리뷰 데이터를 찾을 수 없습니다. 올리브영 등록 상품명으로 다시 검색해주세요."
            return RagSearchResponse(
                llm_answer=fallback_msg,
                search_results=[],
                model_used="fallback-system"
            )

        # 5. 메인 생성 LLM 가동 및 오류 격리
        print(f"🧠 [RAG 가동] 상위 검색 팩트를 결합하여 8081 LLM({request_body.model or SYNTHESIS_MODEL_NAME}) 실시간 본문 추론 생성 중...")
        model_used = request_body.model or SYNTHESIS_MODEL_NAME
        try:
            t_llm_start = time.time()
            final_llm_answer, model_used = generate_llm_rag_answer(
                request_body.query,
                web_response_list,
                model_override=request_body.model
            )
            t_llm_end = time.time()
            print(f"📡 [RAG 응답 생성 완료 ({model_used})] 생성 소요 시간: {t_llm_end - t_llm_start:.2f}초")
        except Exception as llm_err:
            print(f"❌ [LLM 생성 단계 에러]: {llm_err}")
            final_llm_answer = "추천 답변을 생성하는 외부 LLM 연동 중 내부 포맷 오류가 발생했습니다."

        # 함수 스코프 안의 정상 실행 루트에서 유일하게 결과를 반환하는 창구
        return RagSearchResponse(
            llm_answer=final_llm_answer,
            search_results=web_response_list,
            model_used=model_used
        )

    # 🟢 거대한전체 파이프라인의 에러를 잡는 통합 예외 처리부 (들여쓰기 정렬 완료)
    except Exception as api_err:
        print(f"❌ [치명적 RAG API 에러]: {api_err}")
        raise HTTPException(
            status_code=500,
            detail=f"하이브리드 RAG 엔진 연산 중 내부 오류 발생: {str(api_err)}"
        )
    finally:
        # 혹시 위에서 조기 종료되지 않고 남아있을 커넥션의 안전 폐쇄 유도
        if connection and connection.open:
            connection.close()


@app.post("/api/v1/search/stream", tags=["AI RAG Search Stream"])
async def search_products_with_rag_stream(request_body: SearchRequest, request: Request = None):
    """
    실시간 4단계 파이프라인 수명 주기 이벤트 및 LLM 토큰 스트리밍 SSE 엔드포인트
    Spec 030: LangGraph StateGraph 엔진 및 클라이언트 연결 단절 즉시 취소 가드 (T031, T035)
    """
    settings = get_settings()

    # ── Spec 030: LangGraph StateGraph Orchestrator (Hot-swap Feature Flag) ──
    if settings.feature_langgraph_rag:
        async def langgraph_sse_generator():
            orchestrator = MultiTargetGraphOrchestrator()
            session_id = getattr(request_body, "session_id", "") or ""
            phase_map = {
                "INTENT": PipelinePhase.INTENT_ANALYSIS.value,
                "SEARCH": PipelinePhase.HYBRID_SEARCH.value,
                "RERANK": PipelinePhase.RERANKING.value,
                "SYNTHESIS": PipelinePhase.LLM_SYNTHESIS.value,
            }
            for event in orchestrator.stream_rag(
                query=request_body.query,
                session_id=session_id,
                tenant_id="chatb",
            ):
                if request and await request.is_disconnected():
                    # FR-019 / T035: 클라이언트 탭 닫힘 시 GPU 연산 즉시 중단
                    break

                event_type = event.get("event_type", "step_update")

                # Web UI 4단계 타임라인 호환성 브릿지
                if event_type == "step_update":
                    step_id = event.get("step_id", "")
                    phase = phase_map.get(step_id, step_id)
                    status = event.get("status", "running")
                    step_evt = {
                        "phase": phase,
                        "label": event.get("step_name", ""),
                        "status": status,
                    }
                    yield f"event: step\ndata: {json.dumps(step_evt, ensure_ascii=False)}\n\n"

                # Spec 031 FR-006: GPU 큐 대기 상태 브릿지 (Web UI 대기 순번 뱃지)
                elif event_type == "queue_waiting":
                    queue_evt = {
                        "queue_position": event.get("queue_position", 0),
                        "estimated_wait_sec": event.get("estimated_wait_sec", 0),
                        "status": event.get("status", "QUEUED"),
                        "ticket_id": event.get("ticket_id", ""),
                    }
                    yield f"event: queue_status\ndata: {json.dumps(queue_evt, ensure_ascii=False)}\n\n"
                    continue  # queue_waiting는 기본 이벤트로 중복 전송하지 않음

                # 기본 이벤트 전송 (token, complete, fallback_alert, step_update)
                yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(langgraph_sse_generator(), media_type="text/event-stream")

    # ── Legacy Fallback Pipeline ──
    async def sse_event_generator():
        t_start = time.time()

        # Spec 022: Step 0 Early Intent & Security Gate
        decision = EarlyIntentGuardrail.evaluate_gate(request_body.query)
        if decision.is_blocked:
            token_evt = {"token": decision.refusal_message}
            yield f"event: token\ndata: {json.dumps(token_evt, ensure_ascii=False)}\n\n"
            done_evt = {
                "phase": PipelinePhase.DONE.value,
                "label": "완료",
                "status": "completed",
                "model_used": "guardrail-early-blocked",
                "total_latency_sec": round(decision.latency_ms / 1000.0, 4),
                "search_results": [],
            }
            yield f"event: done\ndata: {json.dumps(done_evt, ensure_ascii=False)}\n\n"
            return

        # Step 1: INTENT_ANALYSIS
        step1_evt = {
            "phase": PipelinePhase.INTENT_ANALYSIS.value,
            "label": "🔍 질문 의도 및 화장품 속성 분석 중...",
            "status": "running",
            "elapsed_sec": round(time.time() - t_start, 2),
            "progress_percent": 25,
        }
        yield f"event: step\ndata: {json.dumps(step1_evt, ensure_ascii=False)}\n\n"

        active_brands = get_active_brands_cached(lambda: pymysql.connect(**DB_CONFIG))
        detected_brand, filtered_tokens = extract_brand_entity(request_body.query, active_brands)
        target_brand = request_body.brand or detected_brand

        raw_query_vector = get_query_embedding(request_body.query)
        if raw_query_vector is None:
            err_evt = {
                "phase": PipelinePhase.ERROR.value,
                "label": "❌ 임베딩 서버 통신 실패",
                "error_message": "AI 임베딩 서버와 통신할 수 없습니다.",
                "retry_query": request_body.query,
                "suggested_chips": ["컬러그램", "식물나라", "수분감"],
            }
            yield f"event: error\ndata: {json.dumps(err_evt, ensure_ascii=False)}\n\n"
            return

        query_vector = np.asarray(raw_query_vector, dtype=np.float32).flatten()

        # Step 2: HYBRID_SEARCH
        step2_evt = {
            "phase": PipelinePhase.HYBRID_SEARCH.value,
            "label": "📚 리뷰 하이브리드 검색 중 (BGE-M3 밀집 벡터 + 속성 필터)...",
            "status": "running",
            "elapsed_sec": round(time.time() - t_start, 2),
            "progress_percent": 50,
        }
        yield f"event: step\ndata: {json.dumps(step2_evt, ensure_ascii=False)}\n\n"

        connection = None
        candidates = []
        try:
            connection = pymysql.connect(**DB_CONFIG)

            if target_brand:
                with connection.cursor() as check_cursor:
                    check_cursor.execute(
                        """
                        SELECT COUNT(*) AS cnt 
                        FROM `review_aspect_sentences` 
                        WHERE `brand_name` = %s 
                          AND `embedding_vector` IS NOT NULL 
                          AND `brand_name` IS NOT NULL AND TRIM(`brand_name`) != '' AND `brand_name` != '미분류 브랜드'
                          AND `product_name` IS NOT NULL AND TRIM(`product_name`) != '' AND `product_name` != '미분류 상품'
                        """,
                        (target_brand,)
                    )
                    row_cnt = check_cursor.fetchone()
                    cnt = row_cnt.get("cnt", 0) if isinstance(row_cnt, dict) else (row_cnt[0] if row_cnt else 0)
                    if cnt == 0:
                        if not request_body.brand:
                            # Auto-detected brand had 0 reviews -> fallback to searching all brands!
                            target_brand = None
                        else:
                            err_evt = {
                                "phase": PipelinePhase.ERROR.value,
                                "label": "⚠️ 일치하는 브랜드 데이터 없음",
                                "error_message": f"현재 '{target_brand}' 브랜드의 등록 상품 및 리뷰 데이터가 존재하지 않습니다.",
                                "retry_query": request_body.query,
                                "suggested_chips": ["컬러그램", "식물나라", "브링그린", "라운드랩"],
                            }
                            yield f"event: error\ndata: {json.dumps(err_evt, ensure_ascii=False)}\n\n"
                            return

            with connection.cursor() as cursor:
                sql_select = """
                    SELECT 
                        r.`aspect_sentence_id`, r.`separated_sentence`, r.`embedding_vector`,
                        r.`product_name`, r.`brand_name`, r.`category`,
                        r.`display_name`, r.`sentiment_label`
                    FROM `review_aspect_sentences` r
                    INNER JOIN `brands` b ON r.`brand_name` = b.`brand_name`
                    WHERE r.`embedding_vector` IS NOT NULL
                      AND b.`is_active` = 1
                      AND r.`brand_name` IS NOT NULL AND TRIM(r.`brand_name`) != ''
                      AND r.`product_name` IS NOT NULL AND TRIM(r.`product_name`) != ''
                """
                params = []
                if target_brand:
                    sql_select += " AND r.`brand_name` = %s"
                    params.append(target_brand)
                if request_body.sentiment:
                    sql_select += " AND r.`sentiment_label` = %s"
                    params.append(request_body.sentiment)
                if request_body.keyword:
                    sql_select += " AND (r.`product_name` LIKE %s OR r.`category` LIKE %s OR r.`separated_sentence` LIKE %s)"
                    like_p = f"%{request_body.keyword}%"
                    params.extend([like_p, like_p, like_p])
                elif filtered_tokens:
                    token_clauses = ["(r.`separated_sentence` LIKE %s OR r.`product_name` LIKE %s OR r.`category` LIKE %s)"] * len(filtered_tokens[:3])
                    sql_select += f" AND ({' OR '.join(token_clauses)})"
                    for tok in filtered_tokens[:3]:
                        p = f"%{tok}%"
                        params.extend([p, p, p])

                sql_select += " ORDER BY r.`aspect_sentence_id` DESC LIMIT 2000"
                cursor.execute(sql_select, tuple(params))
                candidates = cursor.fetchall()

                # If token filter yielded no matches, fallback to broader candidate pool for semantic vector search
                if not candidates:
                    fallback_sql = """
                        SELECT 
                            r.`aspect_sentence_id`, r.`separated_sentence`, r.`embedding_vector`,
                            r.`product_name`, r.`brand_name`, r.`category`,
                            r.`display_name`, r.`sentiment_label`
                        FROM `review_aspect_sentences` r
                        INNER JOIN `brands` b ON r.`brand_name` = b.`brand_name`
                        WHERE r.`embedding_vector` IS NOT NULL
                          AND b.`is_active` = 1
                          AND r.`brand_name` IS NOT NULL AND TRIM(r.`brand_name`) != ''
                          AND r.`product_name` IS NOT NULL AND TRIM(r.`product_name`) != ''
                    """
                    fallback_params = []
                    if target_brand:
                        fallback_sql += " AND r.`brand_name` = %s"
                        fallback_params.append(target_brand)
                    if request_body.sentiment:
                        fallback_sql += " AND r.`sentiment_label` = %s"
                        fallback_params.append(request_body.sentiment)
                    fallback_sql += " ORDER BY r.`aspect_sentence_id` DESC LIMIT 2000"
                    cursor.execute(fallback_sql, tuple(fallback_params))
                    candidates = cursor.fetchall()
        finally:
            if connection and connection.open:
                connection.close()

        if not candidates:
            err_evt = {
                "phase": PipelinePhase.ERROR.value,
                "label": "⚠️ 조건에 일치하는 리뷰 없음 (0건)",
                "error_message": "검색 조건에 일치하는 리뷰 데이터가 없습니다.",
                "retry_query": request_body.query,
                "suggested_chips": ["컬러그램 꿀로스", "식물나라 선크림", "수분감 좋은 토너", "발림성 장단점"],
            }
            yield f"event: error\ndata: {json.dumps(err_evt, ensure_ascii=False)}\n\n"
            return

        matrix_list = []
        valid_indices = []
        for i, row in enumerate(candidates):
            raw_v = row.get("embedding_vector")
            if isinstance(raw_v, (bytes, bytearray)):
                v = np.frombuffer(raw_v, dtype=np.float32)
            elif isinstance(raw_v, str):
                v = np.array(json.loads(raw_v), dtype=np.float32)
            else:
                continue
            if v.shape == query_vector.shape:
                matrix_list.append(v)
                valid_indices.append(i)

        if not matrix_list:
            err_evt = {
                "phase": PipelinePhase.ERROR.value,
                "label": "⚠️ 벡터 비교 대상 없음",
                "error_message": "유효한 임베딩 벡터가 존재하지 않습니다.",
                "retry_query": request_body.query,
                "suggested_chips": ["식물나라", "컬러그램"],
            }
            yield f"event: error\ndata: {json.dumps(err_evt, ensure_ascii=False)}\n\n"
            return

        embed_matrix = np.vstack(matrix_list)
        q_norm = np.linalg.norm(query_vector) + 1e-10
        m_norms = np.linalg.norm(embed_matrix, axis=1) + 1e-10
        similarities = np.dot(embed_matrix, query_vector) / (m_norms * q_norm)

        for sim_idx, cand_idx in enumerate(valid_indices):
            candidates[cand_idx]["cosine_sim"] = float(similarities[sim_idx])

        candidates.sort(key=lambda x: x.get("cosine_sim", -1.0), reverse=True)
        subset_candidates = candidates[:request_body.fetch_k]

        # Step 3: RERANKING
        step3_evt = {
            "phase": PipelinePhase.RERANKING.value,
            "label": "⚖️ BGE-Reranker 순위 재정렬 중 (교차 인코더 상위 선별)...",
            "status": "running",
            "elapsed_sec": round(time.time() - t_start, 2),
            "progress_percent": 75,
        }
        yield f"event: step\ndata: {json.dumps(step3_evt, ensure_ascii=False)}\n\n"

        rerank_docs = [row["separated_sentence"] for row in subset_candidates]
        fetched_scores = get_rerank_scores(request_body.query, rerank_docs)
        if not fetched_scores or len(fetched_scores) != len(subset_candidates):
            rerank_scores = [row["cosine_sim"] for row in subset_candidates]
        else:
            rerank_scores = fetched_scores

        final_reranked_results = []
        for i, row in enumerate(subset_candidates):
            p_name = str(row.get("product_name") or "").strip()
            b_name = str(row.get("brand_name") or "").strip()
            if is_dummy_name(b_name) or not is_valid_product_name(p_name):
                continue
            final_reranked_results.append({
                "product_name": p_name,
                "brand_name": b_name,
                "category": str(row.get("category") or "화장품"),
                "review_score": 5,
                "separated_sentence": str(row.get("separated_sentence") or ""),
                "display_name": str(row.get("display_name") or "일반 속성"),
                "sentiment_label": str(row.get("sentiment_label") or "중립"),
                "cosine_similarity": row.get("cosine_sim", 0.0),
                "rerank_score": rerank_scores[i],
            })

        final_reranked_results.sort(key=lambda x: x["rerank_score"], reverse=True)

        web_response_list = []
        seen_products = set()
        rank_counter = 1
        for res in final_reranked_results:
            p_name = res["product_name"]
            if p_name in seen_products:
                continue
            seen_products.add(p_name)
            web_response_list.append(
                RecommendedProduct(
                    rank=rank_counter,
                    product_name=res["product_name"],
                    brand_name=res["brand_name"],
                    category=res["category"],
                    review_score=res["review_score"],
                    separated_sentence=res["separated_sentence"],
                    display_name=res["display_name"],
                    sentiment_label=res["sentiment_label"],
                    cosine_similarity=res["cosine_similarity"],
                    rerank_score=res["rerank_score"],
                )
            )
            rank_counter += 1
            if len(web_response_list) == request_body.top_n:
                break

        if not web_response_list:
            err_evt = {
                "phase": PipelinePhase.ERROR.value,
                "label": "⚠️ 유효한 추천 상품 없음",
                "error_message": "필터링 후 유효한 리뷰를 찾지 못했습니다.",
                "retry_query": request_body.query,
                "suggested_chips": ["컬러그램", "식물나라", "올리브영 인기상품"],
            }
            yield f"event: error\ndata: {json.dumps(err_evt, ensure_ascii=False)}\n\n"
            return

        # Step 4: LLM_SYNTHESIS
        target_model = request_body.model or SYNTHESIS_MODEL_NAME
        step4_evt = {
            "phase": PipelinePhase.LLM_SYNTHESIS.value,
            "label": f"🧠 LLM 심층 분석 및 맞춤 답변 생성 중 ({target_model})...",
            "status": "running",
            "elapsed_sec": round(time.time() - t_start, 2),
            "progress_percent": 90,
        }
        yield f"event: step\ndata: {json.dumps(step4_evt, ensure_ascii=False)}\n\n"

        for token in generate_llm_rag_answer_stream(request_body.query, web_response_list, model_override=request_body.model):
            yield f"event: token\ndata: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

        # Step 5: COMPLETED
        ref_reviews = [
            {
                "rank": p.rank,
                "product_name": p.product_name,
                "brand_name": p.brand_name,
                "category": p.category,
                "review_score": int(p.review_score),
                "attribute_tag": p.display_name,
                "sentiment_label": p.sentiment_label,
                "separated_sentence": p.separated_sentence,
                "rerank_score": round(getattr(p, "rerank_score", 0.0) or 0.0, 4),
                "clean_product_name": clean_product_name_for_search(p.product_name, p.brand_name),
                "oliveyoung_search_url": build_oliveyoung_search_url(p.product_name, p.brand_name),
            }
            for p in web_response_list
        ]

        complete_payload = {
            "phase": PipelinePhase.COMPLETED.value,
            "label": "✅ 리뷰 종합 분석 완료",
            "total_latency_sec": round(time.time() - t_start, 2),
            "searched_review_count": len(candidates),
            "selected_review_count": len(web_response_list),
            "model_used": target_model,
            "fallback_triggered": False,
            "reference_reviews": ref_reviews,
        }
        yield f"event: complete\ndata: {json.dumps(complete_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")


@app.post("/api/v1/chat/fast", response_model=FastChatResponse, tags=["Fast General Chat"])
def fast_chat_with_qwen2b(request_body: FastChatRequest):
    """
    일반 로직 및 전처리 / 의도 분류를 위한 qwen3.5-2b 초경량 초고속 대화 엔드포인트.
    """
    t_start = time.time()
    payload = {
        "model": FAST_MODEL_NAME,
        "messages": [
            {"role": "system", "content": NO_THINK_SYSTEM_PROMPT},
            {"role": "user", "content": request_body.query}
        ],
        "max_tokens": request_body.max_tokens
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = None
            for attempt in range(25):
                resp = client.post(LLM_SERVER_URL, json=payload, headers={"Connection": "close"})
                if resp.status_code == 503:
                    time.sleep(2.0)
                    continue
                resp.raise_for_status()
                break
            
            if resp is None or resp.status_code != 200:
                raise HTTPException(status_code=503, detail=f"Fast LLM ({FAST_MODEL_NAME}) 서빙 준비 중입니다.")

            res = resp.json()
            raw_text = res["choices"][0]["message"]["content"] or ""
            clean_text = clean_think_tags(raw_text, show_think=False)
            latency = time.time() - t_start

            # Spec 019: Session persistence
            if request_body.session_id:
                try:
                    session_store.append_message(request_body.session_id, "user", request_body.query)
                    session_store.append_message(request_body.session_id, "assistant", clean_text.strip())
                except Exception:
                    pass

            return FastChatResponse(
                model=FAST_MODEL_NAME,
                answer=clean_text.strip(),
                latency_sec=round(latency, 3)
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fast LLM ({FAST_MODEL_NAME}) 통신 오류: {e}")


# ==============================================================================
# 5. 💬 Redis Distributed Session Endpoints (Spec 019 / FR-003, US2)
# ==============================================================================
@app.get("/api/session/{session_id}/history", tags=["Session"])
def get_session_history_endpoint(session_id: str, max_messages: int = 20):
    """Spec 019 / FR-003: 멀티턴 대화 히스토리 복원 엔드포인트."""
    messages = session_store.get_messages(session_id, max_messages=max_messages)
    return {"session_id": session_id, "messages": messages, "count": len(messages)}


@app.delete("/api/session/{session_id}", tags=["Session"])
def clear_session_endpoint(session_id: str):
    """Spec 019 / FR-003: 대화 세션 초기화 엔드포인트."""
    session_store.clear_session(session_id)
    return {"session_id": session_id, "status": "cleared"}


@app.post("/api/queue/cancel", tags=["Queue"])
async def cancel_queue_endpoint(request: Request):
    """Spec 031 FR-008: Chat B 웹 프론트엔드용 GPU 대기 취소 프록시 엔드포인트."""
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{BASE_URL}:{MAIN_PORT}/v1/queue/cancel", json=body)
            return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"큐 취소 요청 실패: {e}")


@app.get("/", tags=["UI"])
async def serve_index():
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(index_path, media_type="text/html")


@app.get("/index.html", tags=["UI"])
async def serve_index_html():
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(index_path, media_type="text/html")

