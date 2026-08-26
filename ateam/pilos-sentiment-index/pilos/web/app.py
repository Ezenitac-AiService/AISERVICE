import json
import os
from datetime import date
from flask import Flask, Response, jsonify, render_template, request
from dotenv import load_dotenv
load_dotenv()

from pilos.service.sentiment_index_service import(
    SentimentIndexServiceError,
    get_main_sentiment_indexes,
    get_stock_detail_sentiment_indexes,
)

from pilos.dto.single_comment_inference_dto import (
    single_comment_analysis_to_dict,
)
from pilos.service.single_comment_service import (
    SingleCommentInputError,
    SingleCommentServiceError,
    get_single_comment_analysis,
)

from pilos.service.llm_report_service import(
    get_llm_report_for_display,
    LLMReportGenerationPendingError,
    LLMReportInferencePendingError,
    LLMReportNotFoundError,
    LLMReportServiceError,
)
from pilos.service.chatbot_service import (
    CHAT_BLOCK_DEFINITIONS,
    ChatbotService,
    get_chat_block_definition,
)
from pilos.service.pipeline_status_service import (
    PipelineStatusServiceError,
    get_latest_pipeline_status_for_display,
)

from pilos.dto.chat_dto import (
    CHAT_ACTIONS,
    CHAT_METRICS,
    ChatRequestDTO,
    ChatResponseDTO,
)


def chat_response_to_json(
    response: ChatResponseDTO,) -> dict:
    """챗봇 DTO를 사용자에게 공개할 JSON으로 변환한다."""

    return {
        "status": response.status,
        "answer": response.answer,
        "route": response.route,
        "session_id": response.session_id,
        "stock_code": response.stock_code,
        "as_of": (
            response.as_of.isoformat()
            if response.as_of is not None
            else None
        ),
        "sources": [
            {
                "type": source.type,
                "label": source.label,
                "version": source.version,
                "stock_code": source.stock_code,
                "model_date": (
                    source.model_date.isoformat()
                    if source.model_date is not None
                    else None
                ),
            }
            for source in response.sources
        ],
        "warnings": list(response.warnings),
    }


def get_chatbot_service() -> ChatbotService:
    """웹 요청을 처리할 챗봇 서비스를 만든다."""
    return ChatbotService()



def model_result_to_json(model):
    if model is None:
        return None

    return {
        "model_variant": model.model_variant,
        "supply_demand_association_score": (model.supply_demand_association_score),
        "intercept": model.intercept,
        "text_score": model.text_score,
        "comment_count_contribution": (model.comment_count_contribution),
        "recognized_feature_count": model.recognized_feature_count,
        "unique_token_count": model.unique_token_count,
        "vocabulary_coverage": model.vocabulary_coverage,
        "inference_status": (
            model.inference_status
            if model.inference_status is not None
            else "unknown"
        ),
        "positive_keywords": [
            {
                "keyword": item.keyword,
                "contribution": item.contribution,
            }
            for item in model.positive_keywords
        ],
        "negative_keywords": [
            {
                "keyword": item.keyword,
                "contribution": item.contribution,
            }
            for item in model.negative_keywords
        ],
    }


def sentiment_index_to_json(item):
    return {
        "stock_code": item.stock_code,
        "stock_name": item.stock_name,
        "model_date": item.model_date.isoformat() if item.model_date is not None else None,
        "comment_count": item.comment_count,
        "analysis_status": item.analysis_status,
        "positive_model": model_result_to_json(item.positive_model),
        "negative_model": model_result_to_json(item.negative_model),
        "actual_supply_demand_index": item.actual_supply_demand_index,
        "actual_buy_volume": item.actual_buy_volume,
        "actual_sell_volume": item.actual_sell_volume,
        "supply_data_status": item.supply_data_status,
        "supply_observed_at": (
            item.supply_observed_at.isoformat()
            if item.supply_observed_at is not None
            else None
        ),
    }


def error_response(status: str, message: str, http_status: int):
    return jsonify({"status": status, "message": message}), http_status

from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.secret_key = os.environ.get("FLASK_SECRET_KEY")


@app.get("/api/pipeline/status")
def pipeline_status_api():
    """최상위 자동화의 최신 실행 상태를 반환한다."""
    try:
        result = get_latest_pipeline_status_for_display()
    except PipelineStatusServiceError:
        app.logger.exception("파이프라인 상태 조회 실패")
        return error_response(
            "internal_error",
            "파이프라인 상태를 불러오지 못했습니다.",
            500,
        )
    return jsonify(result), 200

@app.post("/api/inference/single-comment")
def single_comment_inference():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return error_response("invalid_request", "JSON 요청 본문이 필요합니다.", 400)

    comment_text = payload.get("comment_text")
    if not isinstance(comment_text, str) or not comment_text.strip():
        return error_response(
            "invalid_request",
            "comment_text는 비어 있지 않은 문자열이어야 합니다.",
            400,
        )

    try:
        result = get_single_comment_analysis(comment_text=comment_text)
    except SingleCommentInputError as exc:
        return error_response("invalid_request", str(exc), 400)
    except SingleCommentServiceError:
        app.logger.exception("단일 댓글 분석 실패")
        return error_response("internal_error", "단일 댓글을 분석하지 못했습니다.", 500)

    return jsonify(single_comment_analysis_to_dict(result)), 200
    

def _chat_api_response(fixed_stock_code: str | None = None):
    """공용 또는 종목 고정 챗봇 요청을 공개 응답으로 변환한다."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({
            "status": "invalid_request",
            "answer": None,
            "error": "JSON 요청 본문이 필요합니다.",
        }), 400

    allowed_fields = {
        "block_key",
        "action",
        "message",
        "metric",
        "session_id",
        "stock_code",
        "model_date",
        "stream",
    }
    if set(payload) - allowed_fields:
        return jsonify({
            "status": "invalid_request",
            "answer": None,
            "error": "허용된 질문 블록 외의 요청 필드가 포함되어 있습니다.",
        }), 400

    block_key = payload.get("block_key")
    action = payload.get("action")
    message = payload.get("message")
    metric = payload.get("metric")

    if block_key is not None:
        if not isinstance(block_key, str) or not block_key.strip():
            return jsonify({
                "status": "invalid_request",
                "answer": None,
                "error": "block_key는 비어 있지 않은 문자열이어야 합니다.",
            }), 400

        normalized_block_key = block_key.strip()
        definition = get_chat_block_definition(normalized_block_key)
        if definition is None:
            return jsonify({
                "status": "invalid_request",
                "answer": None,
                "error": "허용되지 않은 질문 블록입니다.",
                "allowed_block_keys": sorted(CHAT_BLOCK_DEFINITIONS),
            }), 400
        resolved_message = definition.message
        resolved_action = definition.action
        resolved_metric = definition.metric
        needs_stock = definition.needs_stock
    else:
        normalized_block_key = None
        if action is not None:
            if action not in CHAT_ACTIONS:
                return jsonify({
                    "status": "invalid_request",
                    "answer": None,
                    "error": "허용되지 않은 action입니다.",
                    "allowed_actions": sorted(CHAT_ACTIONS),
                }), 400
            resolved_action = action
        else:
            resolved_action = None

        if metric is not None:
            if metric not in CHAT_METRICS:
                return jsonify({
                    "status": "invalid_request",
                    "answer": None,
                    "error": "허용되지 않은 metric입니다.",
                    "allowed_metrics": sorted(CHAT_METRICS),
                }), 400
            resolved_metric = metric
        else:
            resolved_metric = None

        if not isinstance(message, str) or not message.strip():
            return jsonify({
                "status": "invalid_request",
                "answer": None,
                "error": "message는 비어 있지 않은 문자열이어야 합니다.",
            }), 400
        resolved_message = message.strip()
        needs_stock = False

    session_id = payload.get("session_id")
    if (session_id is not None and not isinstance(session_id, str)):
        return jsonify({
            "status": "invalid_request",
            "answer": None,
            "error": "session_id는 문자열이어야 합니다.",
        }), 400

    if fixed_stock_code is not None:
        normalized_fixed_code = fixed_stock_code.strip()
        if (
            not normalized_fixed_code.isdigit()
            or len(normalized_fixed_code) > 6
        ):
            return jsonify({
                "status": "invalid_request",
                "answer": None,
                "error": "stock_code는 최대 6자리 숫자여야 합니다.",
            }), 400
        stock_code = normalized_fixed_code.zfill(6)
    else:
        stock_code = payload.get("stock_code")
        if stock_code is not None and not isinstance(stock_code, str):
            return jsonify({
                "status": "invalid_request",
                "answer": None,
                "error": "stock_code는 문자열이어야 합니다.",
            }), 400

        if isinstance(stock_code, str) and stock_code.strip() and (
            not stock_code.strip().isdigit() or len(stock_code.strip()) > 6
        ):
            return jsonify({
                "status": "invalid_request",
                "answer": None,
                "error": "stock_code는 최대 6자리 숫자여야 합니다.",
            }), 400

    model_date_text = payload.get("model_date")
    parsed_model_date = None

    if model_date_text is not None:
        if not isinstance(model_date_text, str):
            return jsonify({
                "status": "invalid_request",
                "answer": None,
                "error": (
                    "model_date는 YYYY-MM-DD "
                    "문자열이어야 합니다."
                ),
            }), 400

        try:
            parsed_model_date = date.fromisoformat(model_date_text)
        except ValueError:
            return jsonify({
                "status": "invalid_request",
                "answer": None,
                "error": (
                    "model_date는 YYYY-MM-DD "
                    "형식이어야 합니다."
                ),
            }), 400

    normalized_stock_code = (
        stock_code.strip().zfill(6)
        if isinstance(stock_code, str) and stock_code.strip()
        else None
    )
    if needs_stock and (
        normalized_stock_code is None or parsed_model_date is None
    ):
        return jsonify({
            "status": "invalid_request",
            "answer": None,
            "error": "이 질문 블록에는 stock_code와 model_date가 필요합니다.",
        }), 400

    chat_request = ChatRequestDTO(
        block_key=normalized_block_key,
        message=resolved_message,
        action=resolved_action,
        metric=resolved_metric,
        session_id=(
            session_id.strip()
            if isinstance(session_id, str) and session_id.strip()
            else None
        ),
        stock_code=normalized_stock_code,
        model_date=parsed_model_date,
    )

    is_stream = (
        payload.get("stream") is True
        or request.headers.get("Accept") == "text/event-stream"
        or request.args.get("stream") == "true"
    )

    if is_stream:
        def generate_events():
            try:
                chat_response = get_chatbot_service().answer(chat_request)
                text = chat_response.answer or ""
                chunk_size = 8
                for i in range(0, len(text), chunk_size):
                    token = text[i:i + chunk_size]
                    yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"

                done_payload = chat_response_to_json(chat_response)
                done_payload["type"] = "done"
                yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except (RuntimeError, ValueError):
                app.logger.exception("챗봇 외부 서비스 호출 실패")
                error_payload = {
                    "type": "error",
                    "status": "unavailable",
                    "error": "현재 챗봇 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해주세요.",
                }
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception:
                app.logger.exception("예상하지 못한 챗봇 오류")
                error_payload = {
                    "type": "error",
                    "status": "failed",
                    "error": "챗봇 요청 처리에 실패했습니다.",
                }
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

        return Response(
            generate_events(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    try:
        chat_response = (get_chatbot_service().answer(chat_request))
    except (RuntimeError, ValueError):
        app.logger.exception("챗봇 외부 서비스 호출 실패")

        return jsonify({
            "error": (
                "현재 챗봇 서비스를 사용할 수 없습니다. "
                "잠시 후 다시 시도해주세요."
            ),
        }), 503
    except Exception:
        app.logger.exception("예상하지 못한 챗봇 오류")
        return jsonify({
            "error": "챗봇 요청 처리에 실패했습니다.",
        }), 500

    return jsonify(
        chat_response_to_json(chat_response)
    ), 200


@app.post("/api/chat")
@app.post("/api/v1/chat/stream")
def chat_api():
    """사용자의 공용 챗봇 질문을 받아 공개 응답을 반환한다."""
    return _chat_api_response()


@app.post("/api/stocks/<stock_code>/chat")
@app.post("/api/stocks/<stock_code>/chat/stream")
def stock_chat_api(stock_code):
    """URL의 종목코드로 조회 대상을 고정한 챗봇 응답을 반환한다."""
    return _chat_api_response(fixed_stock_code=stock_code)


@app.get("/api/stocks/<stock_code>/llm-reports")
def stock_llm_report_api(stock_code):
    model_date = request.args.get("model_date")

    if not model_date:
        return error_response("invalid_request", "model_date가 필요합니다.", 400)
    
    try:
        model_date = date.fromisoformat(model_date)
    except ValueError:
        return error_response(
            "invalid_request", "model_date는 YYYY-MM-DD 형식이어야 합니다.", 400
        )
    
    try:
        result = get_llm_report_for_display(stock_code, model_date)

    except LLMReportInferencePendingError:
        return error_response(
            "inference_pending",
            "최신 문서의 활성 모델 추론이 아직 완료되지 않았습니다.",
            202,
        )

    except LLMReportGenerationPendingError:
        return error_response(
            "report_pending",
            "활성 모델 추론은 완료됐지만 보고서 생성이 대기 중입니다.",
            202,
        )
    
    except LLMReportNotFoundError:
        return error_response("not_found", "해당 날짜의 리포트가 없습니다.", 404)
    
    except LLMReportServiceError:
        app.logger.exception("LLM 리포트 조회 실패")
        return error_response("internal_error", "리포트를 불러오지 못했습니다.", 500)
    
    return jsonify(result), 200


@app.get("/api/stocks/<stock_code>")
def stock_detail_api(stock_code):
    try:
        results = get_stock_detail_sentiment_indexes(stock_code)
    except SentimentIndexServiceError:
        app.logger.exception("종목 상세 조회 실패")
        return error_response("internal_error", "데이터를 불러올 수 없습니다.", 500)

    if not results:
        return error_response("not_found", "해당 종목의 일별문서가 없습니다.", 404)
    
    return jsonify({
        "stock_code": results[0].stock_code,
        "stock_name": results[0].stock_name,
        "latest": sentiment_index_to_json(results[0]),
        "history":[sentiment_index_to_json(item) for item in results]
    })

@app.get("/api/stocks")
def stock_list_api():
    try:
        results = get_main_sentiment_indexes()
    except SentimentIndexServiceError:
        app.logger.exception("종목 목록 조회 실패")
        return error_response("internal_error", "데이터를 불러올 수 없습니다.", 500)

    return jsonify([
        sentiment_index_to_json(item)
        for item in results])

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/stocks/<stock_code>")
def stock_detail(stock_code):
    return render_template("detail.html",code=stock_code)

@app.get("/about")
def about():
    return render_template("about.html")


# ==============================================================================
# 5. ⚡ Redis Async Job Queue Endpoints (Spec 019 / FR-004, US3)
# ==============================================================================
from pilos.core.redis_queue import pilos_job_queue, RedisLock
import time

@app.post("/api/jobs/enqueue")
def enqueue_job_api():
    """Spec 019 / FR-004: 비동기 감정 분석 작업 인큐 엔드포인트."""
    payload = request.get_json(silent=True) or {}
    review_id = payload.get("review_id", f"rev_{int(time.time()*1000)}")
    lock = RedisLock(f"job:{review_id}", ttl_seconds=10)
    if not lock.acquire():
        return jsonify({"status": "duplicate", "message": "이미 진행 중인 작업입니다.", "review_id": review_id}), 409

    pilos_job_queue.enqueue(payload)
    lock.release()
    return jsonify({
        "status": "queued",
        "job_id": payload.get("job_id"),
        "pending_jobs": pilos_job_queue.length()
    }), 202


@app.get("/api/jobs/status")
def queue_status_api():
    """Spec 019 / FR-004: 비동기 큐 대기 상태 조회 엔드포인트."""
    return jsonify({
        "queue_name": pilos_job_queue.queue_name,
        "pending_jobs_count": pilos_job_queue.length(),
        "status": "active"
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
