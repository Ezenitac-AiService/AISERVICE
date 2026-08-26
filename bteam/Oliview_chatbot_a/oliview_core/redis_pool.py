"""
Global Redis ConnectionPool Singleton & Single-flight Lock (Spec 030 FR-014/FR-024).
전역 커넥션 풀 싱글톤, socket_timeout=0.2s Fail-Fast, L1 캐시 스탬피드 방어 뮤텍스.
"""

import time
import hashlib
import json
from typing import Optional, Any

from .config import get_settings
from .logger import get_logger, get_trace_id

logger = get_logger("oliview.redis")

# ──────────────────────────────────────────────────────────────────────────────
# Global Connection Pool Singleton
# ──────────────────────────────────────────────────────────────────────────────
_pool = None
_client = None


def get_redis_client():
    """
    전역 Redis 클라이언트 싱글톤을 반환합니다.
    ConnectionPool 기반으로 모든 요청이 풀을 공유하며,
    socket_timeout=0.2s Fail-Fast 적용 (Spec 030 FR-024).
    """
    global _pool, _client
    if _client is not None:
        return _client

    try:
        import redis as redis_lib
    except ImportError:
        logger.warning("redis 패키지 미설치. pip install redis 필요.")
        return None

    settings = get_settings()
    try:
        _pool = redis_lib.ConnectionPool(
            host=settings.redis_host,
            port=settings.redis_port,
            db=0,
            socket_timeout=settings.redis_socket_timeout,   # 0.2s Fail-Fast
            socket_connect_timeout=1.0,
            decode_responses=True,
            max_connections=20,
            retry_on_timeout=False,  # 타임아웃 시 즉시 실패 (재시도 없음)
        )
        _client = redis_lib.Redis(connection_pool=_pool)
        # 연결 테스트
        _client.ping()
        logger.info(
            f"Redis ConnectionPool 싱글톤 생성 완료 "
            f"({settings.redis_host}:{settings.redis_port}, "
            f"socket_timeout={settings.redis_socket_timeout}s)",
            extra={"trace_id": get_trace_id()},
        )
    except Exception as e:
        logger.warning(
            f"Redis 연결 실패 (인메모리 폴백 전환): {e}",
            extra={"trace_id": get_trace_id(), "error_type": type(e).__name__},
        )
        _client = None

    return _client


# ──────────────────────────────────────────────────────────────────────────────
# Cache Helpers (L1~L3 공통)
# ──────────────────────────────────────────────────────────────────────────────

def cache_get(key: str) -> Optional[Any]:
    """Redis에서 캐시 값을 조회합니다. 실패 시 None 반환."""
    client = get_redis_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


def cache_set(key: str, value: Any, ttl: int = 3600) -> bool:
    """Redis에 캐시 값을 저장합니다. 실패 시 False 반환."""
    client = get_redis_client()
    if client is None:
        return False
    try:
        client.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Single-flight Lock (L1 캐시 스탬피드 방어)
# ──────────────────────────────────────────────────────────────────────────────

class SingleFlightLock:
    """
    L1 검색 풀 캐시 스탬피드 방어용 분산 뮤텍스.
    동일 타겟에 대한 동시 DB 쿼리를 1회로 병합합니다.
    """

    LOCK_TTL = 10  # 10초 잠금 (최대 대기 시간)

    @staticmethod
    def acquire(target_slug: str) -> bool:
        """분산 락 획득을 시도합니다. 성공 시 True."""
        client = get_redis_client()
        if client is None:
            return True  # Redis 미사용 시 항상 허용
        lock_key = f"lock:rag:pool:{target_slug}"
        try:
            return bool(client.set(lock_key, "1", nx=True, ex=SingleFlightLock.LOCK_TTL))
        except Exception:
            return True  # 실패 시 안전하게 허용

    @staticmethod
    def release(target_slug: str) -> None:
        """분산 락을 해제합니다."""
        client = get_redis_client()
        if client is None:
            return
        lock_key = f"lock:rag:pool:{target_slug}"
        try:
            client.delete(lock_key)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Cache Key Builders
# ──────────────────────────────────────────────────────────────────────────────

def build_l1_key(target_slug: str, attr_slug: str = "default") -> str:
    """L1 검색 풀 캐시 키를 생성합니다."""
    return f"v1:rag:pool:{target_slug}:{attr_slug}"


def build_l2_key(text: str) -> str:
    """L2 임베딩 벡터 캐시 키를 생성합니다."""
    norm = " ".join(text.strip().lower().split())
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return f"emb:bge-m3:{h}"


def build_l3_key(query: str, docs_str: str) -> str:
    """L3 리랭킹 교차 점수 캐시 키를 생성합니다."""
    q_hash = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()
    docs_hash = hashlib.sha256(docs_str.encode("utf-8")).hexdigest()
    return f"rerank:{q_hash}:{docs_hash}"


# ──────────────────────────────────────────────────────────────────────────────
# Spec 032: L5 LLM Response Cache Engine
# ──────────────────────────────────────────────────────────────────────────────

import re
import random
import asyncio
import unicodedata
from typing import List, AsyncGenerator, Tuple, Iterator, Optional, Any


def compute_doc_ids_hash(doc_ids: List[str]) -> str:
    """선별된 문서 ID 목록을 정렬하여 16자리 SHA-256 해시를 반환합니다."""
    if not doc_ids:
        return "empty_docs"
    sorted_ids = sorted(str(d).strip() for d in doc_ids if str(d).strip())
    raw_str = ",".join(sorted_ids)
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]


def build_l5_key(
    tenant_id: str,
    rewritten_query: str,
    doc_ids: List[str],
    model_id: str = "qwen3.5-2b",
    prompt_version: str = "v1.0",
) -> str:
    """
    Spec 032 FR-001 / FR-009:
    탈맥락화 질의(NFKC 정규화) + 정렬된 문서 ID 해시 + 프롬프트 버전 + 모델 ID + 테넌트 ID
    조합으로 L5 캐시 키를 생성합니다.
    형식: olliview:l5:{tenant_id}:{hash_32}
    """
    # 1. Unicode NFKC 및 다중 공백 정규화
    cleaned_q = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", rewritten_query or "")).strip().lower()
    doc_hash = compute_doc_ids_hash(doc_ids)
    tenant = (tenant_id or "chata").strip().lower()

    raw_payload = f"{tenant}:{cleaned_q}:{doc_hash}:{model_id}:{prompt_version}"
    key_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()[:32]
    return f"olliview:l5:{tenant}:{key_hash}"


# FR-004: Cache Poisoning 차단 시그니처 목록
_DENY_LIST_PATTERNS = [
    "죄송합니다",
    "답변할 수 없습니다",
    "지침 변경이나 관련 없는 요청",
    "일시적인 오류",
    "시스템 에러",
    "모델 게이트웨이 연결에 실패",
    "unauthorized",
    "internal server error",
]


def is_poisoned_or_invalid_response(response_text: str) -> bool:
    """
    Spec 032 FR-004:
    20자 미만의 불완전 답변 또는 에러/거부 문구가 포함된 경우 캐시 저장을 차단(True)합니다.
    """
    if not response_text or len(response_text.strip()) < 20:
        return True
    text_lower = response_text.lower()
    for deny_pat in _DENY_LIST_PATTERNS:
        if deny_pat.lower() in text_lower:
            return True
    return False


def calculate_l5_ttl(base_ttl: int = 43200, jitter: int = 3600) -> int:
    """
    Spec 032 FR-005:
    기본 TTL(12시간)에 무작위 Jitter(±1시간)를 부여하여 대량 동시 만료를 방지합니다.
    """
    offset = random.randint(-abs(jitter), abs(jitter))
    return max(60, base_ttl + offset)


def get_l5_response(key: str) -> Optional[dict]:
    """
    Spec 032 FR-002 / FR-008:
    L5 캐시를 조회합니다. 킬스위치 꺼짐 또는 실패 시 None 반환 (Fail-Fast 0.2s).
    """
    settings = get_settings()
    if not settings.enable_l5_cache:
        return None

    client = get_redis_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.debug(f"[L5 Cache Lookup Fail-Fast] {e}")
    return None


def set_l5_response(
    key: str,
    payload: dict,
    ttl_base: int = 43200,
    jitter: int = 3600,
) -> bool:
    """
    Spec 032 FR-004 / FR-005:
    Deny-List 검증 후 TTL Jitter를 적용하여 Redis L5 캐시에 저장합니다.
    """
    settings = get_settings()
    if not settings.enable_l5_cache:
        return False

    resp_text = payload.get("response_text", "")
    if is_poisoned_or_invalid_response(resp_text):
        logger.warning(f"[L5 Cache Poisoning Blocked] Invalid/error response skipped from caching: {key}")
        return False

    client = get_redis_client()
    if client is None:
        return False

    ttl = calculate_l5_ttl(base_ttl=ttl_base, jitter=jitter)
    try:
        client.set(key, json.dumps(payload, ensure_ascii=False, default=str), ex=ttl)
        logger.info(f"[L5 Cache SET] Saved key={key}, ttl={ttl}s, len={len(resp_text)}")
        return True
    except Exception as e:
        logger.warning(f"[L5 Cache SET Failed] {e}")
        return False


async def replay_cached_stream(
    cached_payload: dict,
    chunk_delay_s: float = 0.025,
) -> AsyncGenerator[str, None]:
    """
    Spec 032 FR-003:
    캐시된 전체 응답 텍스트를 단어/공백 경계 단위(4~10자)로 분할하여 20~30ms 간격으로 비동기 스트리밍 Replay합니다.
    """
    text = cached_payload.get("response_text", "")
    if not text:
        return

    # 공백 및 구두점 기준 단어 단위 분할 (연속 스트리밍 유지)
    words = re.findall(r"\S+\s*|\s+", text)
    if not words:
        words = [text]

    buffer = ""
    for w in words:
        buffer += w
        if len(buffer) >= 6 or w.endswith(("\n", ".", "!", "?", " ")):
            yield buffer
            buffer = ""
            if chunk_delay_s > 0:
                await asyncio.sleep(chunk_delay_s)

    if buffer:
        yield buffer


def replay_cached_stream_sync(
    cached_payload: dict,
    chunk_delay_s: float = 0.025,
) -> Iterator[str]:
    """
    Spec 032 FR-003 (Sync version):
    동기 제너레이터 환경(Streamlit / FastAPI generator)용 고속 스트리밍 Replay.
    """
    text = cached_payload.get("response_text", "")
    if not text:
        return

    words = re.findall(r"\S+\s*|\s+", text)
    if not words:
        words = [text]

    buffer = ""
    for w in words:
        buffer += w
        if len(buffer) >= 6 or w.endswith(("\n", ".", "!", "?", " ")):
            yield buffer
            buffer = ""
            if chunk_delay_s > 0:
                time.sleep(chunk_delay_s)

    if buffer:
        yield buffer


class L5SingleFlightLock:
    """
    Spec 032 FR-007:
    동일 캐시 키에 대한 동시 다발 LLM GPU 추론 요청을 1회로 병합하고
    나머지 요청은 캐시 생성을 대기하는 분산 락.
    """
    LOCK_TTL = 8  # 8초 잠금 (GPU 추론 최대 예상 시간)

    @staticmethod
    def acquire(cache_key: str) -> bool:
        """락 획득 시도 (True: 최초 실행자, False: 대기자)"""
        client = get_redis_client()
        if client is None:
            return True
        lock_key = f"lock:l5:{cache_key}"
        try:
            return bool(client.set(lock_key, "1", nx=True, ex=L5SingleFlightLock.LOCK_TTL))
        except Exception:
            return True

    @staticmethod
    def release(cache_key: str) -> None:
        """락 해제"""
        client = get_redis_client()
        if client is None:
            return
        lock_key = f"lock:l5:{cache_key}"
        try:
            client.delete(lock_key)
        except Exception:
            pass
