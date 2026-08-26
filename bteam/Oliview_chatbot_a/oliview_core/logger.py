"""
Structured JSON Logger with Trace ID Propagation (Spec 030 FR-028).
엔드투엔드 분산 추적을 위한 요청별 trace_id 발급 및 단계별 레이턴시 로깅.
"""

import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Optional, Dict, Any

# ──────────────────────────────────────────────────────────────────────────────
# 요청별 Trace ID Context Variable (async-safe)
# ──────────────────────────────────────────────────────────────────────────────
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def generate_trace_id() -> str:
    """요청별 고유 분산 추적 식별자를 생성합니다. (예: req_a1b2c3d4)"""
    return f"req_{uuid.uuid4().hex[:8]}"


def set_trace_id(trace_id: str) -> None:
    """현재 비동기 컨텍스트에 trace_id를 바인딩합니다."""
    _trace_id_var.set(trace_id)


def get_trace_id() -> str:
    """현재 비동기 컨텍스트의 trace_id를 반환합니다."""
    return _trace_id_var.get()


# ──────────────────────────────────────────────────────────────────────────────
# Structured JSON Formatter
# ──────────────────────────────────────────────────────────────────────────────

class StructuredJsonFormatter(logging.Formatter):
    """JSON 구조화 로그 포맷터. trace_id 자동 전파 및 민감 데이터 마스킹."""

    MASKED_KEYS = {"api_key", "password", "token", "secret", "authorization"}

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "") or get_trace_id(),
        }

        # 추가 구조화 필드 (step_id, latency_ms 등)
        for attr in ("step_id", "latency_ms", "target_id", "cache_hit",
                      "fallback", "error_type", "doc_count"):
            val = getattr(record, attr, None)
            if val is not None:
                log_entry[attr] = val

        # 민감 데이터 마스킹 (Constitution Principle IV)
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            masked = {}
            for k, v in record.extra_data.items():
                if k.lower() in self.MASKED_KEYS:
                    masked[k] = "***MASKED***"
                else:
                    masked[k] = v
            log_entry["data"] = masked

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])

        return json.dumps(log_entry, ensure_ascii=False, default=str)


# ──────────────────────────────────────────────────────────────────────────────
# Logger Factory
# ──────────────────────────────────────────────────────────────────────────────

def get_logger(name: str = "oliview.rag") -> logging.Logger:
    """구조화된 JSON 로거 싱글톤을 반환합니다."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


# ──────────────────────────────────────────────────────────────────────────────
# Step Latency Logger (편의 유틸리티)
# ──────────────────────────────────────────────────────────────────────────────

class StepTimer:
    """LangGraph 노드 단계별 레이턴시 측정 컨텍스트 매니저."""

    def __init__(self, step_id: str, logger: Optional[logging.Logger] = None,
                 trace_id: Optional[str] = None, **extra):
        self.step_id = step_id
        self.logger = logger or get_logger()
        self.trace_id = trace_id or get_trace_id()
        self.extra = extra
        self.start_time: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed_ms = (time.perf_counter() - self.start_time) * 1000
        self.logger.info(
            f"[{self.step_id}] 완료: {self.elapsed_ms:.1f}ms",
            extra={
                "trace_id": self.trace_id,
                "step_id": self.step_id,
                "latency_ms": round(self.elapsed_ms, 1),
                **self.extra,
            },
        )
        return False  # 예외 전파


# 기본 로거 인스턴스
rag_logger = get_logger("oliview.rag")
