"""
Hybrid Search Engine with Feature Discovery & Polarity Split (Spec 030).
ChromaDB Dense Vector Search + BM25 Sparse Index + Redis L1 Cache.
"""

import os
import sys
import time
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

from .client import AiGatewayClient
from .config import get_settings
from .sanitizer import detect_brand_and_category, clean_review_noise
from .redis_pool import cache_get, cache_set, build_l1_key, SingleFlightLock
from .logger import get_logger, get_trace_id, StepTimer

logger = get_logger("oliview.retrieval")


def resolve_chroma_dir() -> str:
    """Finds ChromaDB directory across various runtime environments."""
    settings = get_settings()
    if settings.faiss_index_dir and os.path.exists(settings.faiss_index_dir):
        return settings.faiss_index_dir

    candidates = [
        os.path.join(os.getcwd(), "bteam", "Oliview_chatbot_a", "chroma_db_oliview"),
        os.path.join(os.getcwd(), "Oliview_chatbot_a", "chroma_db_oliview"),
        os.path.join(os.getcwd(), "chroma_db_oliview"),
        "/app/chroma_db_oliview",
        "/bteam/Oliview_chatbot_a/chroma_db_oliview",
    ]
    for p in candidates:
        if os.path.exists(os.path.join(p, "chroma.sqlite3")):
            return p
    return candidates[0]


class HybridRetriever:
    """Combines ChromaDB Dense Vector Search with BM25 Sparse Keyword Search & Redis L1 Cache."""

    def __init__(self, client: Optional[AiGatewayClient] = None, chroma_dir: Optional[str] = None):
        self.client = client or AiGatewayClient()
        self.settings = get_settings()
        self.chroma_dir = chroma_dir or resolve_chroma_dir()
        self.collection = None
        self.all_documents: List[str] = []
        self.all_metadatas: List[Dict[str, Any]] = []
        self.bm25 = None
        self._load_chroma()

    def _load_chroma(self):
        """Loads ChromaDB persistent client and initializes BM25 corpus."""
        try:
            import chromadb
            if os.path.exists(self.chroma_dir):
                client = chromadb.PersistentClient(path=self.chroma_dir)
                cols = [c.name for c in client.list_collections()]
                target_col = "oliview_review_sentences" if "oliview_review_sentences" in cols else (cols[0] if cols else None)
                if target_col:
                    self.collection = client.get_collection(target_col)
                    # Load metadata for BM25
                    data = self.collection.get(include=["documents", "metadatas"], limit=5000)
                    self.all_documents = data.get("documents") or []
                    self.all_metadatas = data.get("metadatas") or []
                    
                    try:
                        from rank_bm25 import BM25Okapi
                        corpus = [doc.split() for doc in self.all_documents]
                        if corpus:
                            self.bm25 = BM25Okapi(corpus)
                    except Exception:
                        self.bm25 = None
        except Exception as e:
            logger.warning(f"ChromaDB 로드 실패: {e}", extra={"trace_id": get_trace_id()})

    def search(
        self,
        query: str,
        top_k: int = 25,
        brand_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        auto_detect_filter: bool = True,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Performs dense vector search + metadata filtering with Redis L1 Cache (T029).
        """
        trace_id = get_trace_id()

        # 1. L1 캐시 조회 (T029)
        cache_key = None
        if use_cache:
            import re
            b_slug = re.sub(r"[^a-zA-Z0-9가-힣]", "_", (brand_filter or "all").lower())
            q_slug = re.sub(r"[^a-zA-Z0-9가-힣]", "_", query[:30].lower())
            cache_key = build_l1_key(b_slug, q_slug)
            cached = cache_get(cache_key)
            if cached is not None:
                logger.info(f"L1 검색 풀 캐시 히트: {len(cached)}건", extra={"trace_id": trace_id, "cache_hit": True})
                return cached[:top_k]

        # 2. Detect filters if enabled and not specified
        if auto_detect_filter and (not brand_filter or not category_filter):
            d_brand, d_cat = detect_brand_and_category(query)
            brand_filter = brand_filter or d_brand
            category_filter = category_filter or d_cat

        if not self.collection:
            results = self._search_mysql(
                query=query,
                top_k=top_k,
                brand_filter=brand_filter,
                category_filter=category_filter,
            )
            if cache_key and results:
                cache_set(cache_key, results, self.settings.redis_ttl_search_pool)
            return results[:top_k]

        # 3. Build Chroma Where clause
        where_conditions = []
        if brand_filter:
            where_conditions.append({"brand_name": {"$eq": brand_filter}})
        if category_filter:
            where_conditions.append({"analysis_category_name": {"$eq": category_filter}})

        where_clause = None
        if len(where_conditions) == 1:
            where_clause = where_conditions[0]
        elif len(where_conditions) > 1:
            where_clause = {"$and": where_conditions}

        # 4. Dense Vector Search via BGE-M3 embeddings
        q_embs = self.client.embed([query], trace_id=trace_id)
        results: List[Dict[str, Any]] = []

        if self.collection:
            try:
                if q_embs:
                    query_kwargs = {
                        "query_embeddings": q_embs,
                        "n_results": min(top_k * 2, max(1, self.collection.count())),
                        "include": ["documents", "metadatas", "distances"],
                    }
                    if where_clause:
                        try:
                            res = self.collection.query(where=where_clause, **query_kwargs)
                        except Exception:
                            res = self.collection.query(**query_kwargs)
                    else:
                        res = self.collection.query(**query_kwargs)

                    docs = res.get("documents", [[]])[0]
                    metas = res.get("metadatas", [[]])[0]
                    dists = res.get("distances", [[]])[0] if "distances" in res else [0.0] * len(docs)

                    for doc, meta, dist in zip(docs, metas, dists):
                        score = 1.0 - float(dist) if dist is not None else 0.5
                        results.append({
                            "review_id": meta.get("review_id", 0),
                            "product_name": meta.get("product_name", "올리브영 화장품"),
                            "brand": meta.get("brand_name", brand_filter or ""),
                            "category": meta.get("analysis_category_name", category_filter or ""),
                            "clean_text": doc,
                            "review_text": doc,
                            "sentiment": meta.get("sentiment", "NEUTRAL"),
                            "dense_score": score,
                        })
            except Exception as e:
                logger.warning(f"Chroma 쿼리 실행 실패: {e}", extra={"trace_id": trace_id})

        # Fallback to MySQL review_aspect_sentences if ChromaDB returned 0 results or is unavailable
        if not results:
            results = self._search_mysql(
                query=query,
                top_k=top_k,
                brand_filter=brand_filter,
                category_filter=category_filter,
                q_embs=q_embs,
            )

        final_results = results[:top_k]

        # 5. L1 캐시 저장 (TTL 12h)
        if cache_key and final_results:
            cache_set(cache_key, final_results, self.settings.redis_ttl_search_pool)

        return final_results

    def _search_mysql(
        self,
        query: str,
        top_k: int = 25,
        brand_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        q_embs: Optional[List[List[float]]] = None,
    ) -> List[Dict[str, Any]]:
        """MySQL review_aspect_sentences 59,407건 기반 하이브리드 벡터 검색 (ChromaDB 미가용 시 자동 실행)."""
        import pymysql
        import numpy as np
        import json

        if not q_embs:
            q_embs = self.client.embed([query])
        if not q_embs:
            return []

        q_vec = np.asarray(q_embs[0], dtype=np.float32).flatten()

        db_config = {
            "host": os.getenv("DB_HOST", "bteam_db"),
            "port": int(os.getenv("DB_PORT", 3306)),
            "user": os.getenv("BTEAM_DB_USER", os.getenv("DB_USER", "gp123")),
            "password": os.getenv("BTEAM_DB_PASSWORD", os.getenv("DB_PASSWORD", "GP123!")),
            "database": os.getenv("BTEAM_DB_NAME", os.getenv("DB_NAME", "oliview_project")),
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
            "connect_timeout": 5,
        }

        candidates = []
        try:
            conn = pymysql.connect(**db_config)
            with conn.cursor() as cur:
                sql = """
                    SELECT
                        ras.aspect_sentence_id,
                        ras.separated_sentence,
                        ras.embedding_vector,
                        p.product_name,
                        COALESCE(b.brand_name, ras.brand_name, '올리브영 브랜드') AS brand_name,
                        COALESCE(ac.category_name, ras.category, '화장품') AS category,
                        aca.display_name AS attribute_name,
                        asr.sentiment_label
                    FROM review_aspect_sentences ras
                    JOIN reviews r ON r.review_id = ras.review_id
                    JOIN products p ON p.product_id = r.product_id
                    LEFT JOIN brands b ON b.brand_id = p.brand_id
                    LEFT JOIN categories ac ON ac.category_id = ras.analysis_category_id
                    LEFT JOIN analysis_category_attributes aca ON aca.analysis_category_id = ras.analysis_category_id AND aca.model_attribute_name = ras.model_attribute_name
                    LEFT JOIN aspect_sentiment_results asr ON asr.aspect_sentence_id = ras.aspect_sentence_id
                    WHERE ras.embedding_vector IS NOT NULL
                """
                params = []
                if brand_filter:
                    sql += " AND (b.brand_name = %s OR p.product_name LIKE %s)"
                    params.extend([brand_filter, f"%{brand_filter}%"])
                if category_filter:
                    sql += " AND (ac.category_name = %s OR ras.category = %s)"
                    params.extend([category_filter, category_filter])

                sql += " ORDER BY ras.aspect_sentence_id DESC LIMIT 1500"
                cur.execute(sql, tuple(params))
                candidates = cur.fetchall()
            conn.close()
        except Exception as e:
            logger.warning(f"MySQL 리뷰 검색 실패: {e}")
            return []

        if not candidates:
            return []

        # 코사인 유사도 벡터 연산
        matrix_list = []
        valid_indices = []
        for i, row in enumerate(candidates):
            raw_v = row.get("embedding_vector")
            try:
                if isinstance(raw_v, (bytes, bytearray)):
                    v = np.frombuffer(raw_v, dtype=np.float32)
                elif isinstance(raw_v, str):
                    v = np.array(json.loads(raw_v), dtype=np.float32)
                else:
                    continue
                if v.shape == q_vec.shape:
                    matrix_list.append(v)
                    valid_indices.append(i)
            except Exception:
                continue

        if not matrix_list:
            return []

        embed_matrix = np.vstack(matrix_list)
        q_norm = np.linalg.norm(q_vec) + 1e-10
        m_norms = np.linalg.norm(embed_matrix, axis=1) + 1e-10
        sims = np.dot(embed_matrix, q_vec) / (m_norms * q_norm)

        results = []
        for sim_idx, cand_idx in enumerate(valid_indices):
            row = candidates[cand_idx]
            results.append({
                "review_id": row.get("aspect_sentence_id", 0),
                "product_name": row.get("product_name", "올리브영 화장품"),
                "brand": row.get("brand_name", brand_filter or ""),
                "category": row.get("category", category_filter or ""),
                "clean_text": row.get("separated_sentence", ""),
                "review_text": row.get("separated_sentence", ""),
                "sentiment": row.get("sentiment_label", "NEUTRAL"),
                "dense_score": float(sims[sim_idx]),
            })

        results.sort(key=lambda x: x["dense_score"], reverse=True)
        return results[:top_k]

    # ─────────────────────────────────────────────────────────────────────────
    # Feature Discovery: 속성/기능 만족도 상위 Top-N 제품 자동 발굴 (T023)
    # ─────────────────────────────────────────────────────────────────────────

    def discover_top_products_by_feature(
        self,
        feature_query: str,
        top_n: int = 3,
        candidate_pool_size: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        속성/기능 키워드 기반으로 만족도 및 리뷰 밀도가 높은 대표 제품 Top-N을 선별합니다. (Spec 030 FR-004)
        """
        raw_candidates = self.search(
            query=feature_query,
            top_k=candidate_pool_size,
            auto_detect_filter=False,
        )

        if not raw_candidates:
            return []

        # 제품별 빈도 및 평균 유사도 집계
        product_scores: Dict[str, List[float]] = {}
        product_brands: Dict[str, str] = {}

        for r in raw_candidates:
            p_name = r.get("product_name") or r.get("brand")
            if not p_name:
                continue
            if p_name not in product_scores:
                product_scores[p_name] = []
                product_brands[p_name] = r.get("brand", "")
            product_scores[p_name].append(r.get("dense_score", 0.5))

        # 순위 산정: (리뷰 수 * 0.4) + (평균 유사도 * 0.6)
        ranked = []
        for p_name, scores in product_scores.items():
            avg_score = sum(scores) / len(scores)
            composite_score = (len(scores) / candidate_pool_size * 0.4) + (avg_score * 0.6)
            ranked.append({
                "product_name": p_name,
                "brand_name": product_brands[p_name],
                "score": composite_score,
                "review_count": len(scores),
            })

        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked[:top_n]

    # ─────────────────────────────────────────────────────────────────────────
    # Aspect / Pros-Cons Polarity Split Search (T026)
    # ─────────────────────────────────────────────────────────────────────────

    def search_aspect_polarity(
        self,
        query: str,
        target_name: str,
        brand_name: Optional[str] = None,
        top_k: int = 10,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        단일 제품의 긍정(장점)과 부정/주의점 리뷰를 분할 하이브리드 검색합니다. (Spec 030 FR-005)
        Returns:
            {"pros": [긍정 리뷰 목록], "cons": [주의점/부정 리뷰 목록]}
        """
        # 1. 긍정 장점 검색
        pros_query = f"{target_name} 장점 좋은 점 효과 만족"
        pros_results = self.search(
            query=pros_query,
            top_k=top_k // 2,
            brand_filter=brand_name,
            auto_detect_filter=False,
        )

        # 2. 부정/주의점 검색
        cons_query = f"{target_name} 단점 아쉬운 점 부작용 주의점 자극 트러블"
        cons_results = self.search(
            query=cons_query,
            top_k=top_k // 2,
            brand_filter=brand_name,
            auto_detect_filter=False,
        )

        return {
            "pros": pros_results,
            "cons": cons_results,
        }
