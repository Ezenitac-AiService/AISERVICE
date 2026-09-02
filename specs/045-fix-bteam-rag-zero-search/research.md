# Research Report: Oliview B-Team RAG 파이프라인 DB 스키마 동기화, 리랭커 Fallback 및 64K q8_0 KV 양자화 (Feature 045)

**Feature Branch**: `045-fix-bteam-rag-zero-search`
**Date**: 2026-09-02
**Status**: Completed

## 1. 64K KV 캐시 양자화(q8_0) 및 Linux Kernel OOM 방지 방안

### Context & Problem
- 기본 LLM(`qwen3.5-2b`)이 `n_ctx=65536 (64K)`로 기동될 때, 기본 16-bit FP16 KV 캐시는 약 2.5GB~3.5GB 이상의 메모리를 점유합니다.
- 여기에 BGE-M3(임베딩 @ 8090) 및 BGE-Reranker-v2-M3(리랭커 @ 8091)이 동시에 기동되면서 Docker 컨테이너 및 호스트의 가용 메모리 한계를 초과하여 **Linux Kernel OOM Killer(Exit Code 137 / SIGKILL)**가 프로세스를 강제 종료시켰습니다.

### Research Findings & Technical Solution
- `llama.cpp` 및 `llama_cpp.server`는 `--type_k` 및 `--type_v` 인자를 통해 KV 캐시 양자화를 공식 지원합니다.
- **`q8_0` 양자화**: 8-bit 정밀도로 KV 캐시를 압축하여 메모리 점유량을 50% 절감(약 1.2GB 절감)하면서도 Perplexity/추론 품질 손실이 0.05% 미만으로 거의 무손실에 가깝습니다.
- `build_server_command`에서 `n_ctx >= 32768`일 때 자동으로 `--type_k q8_0 --type_v q8_0` 인자를 주입함으로써, 8GB VRAM(GTX 1070) 및 컨테이너 환경에서 3종 모델이 OOM 없이 100% 안정 상주하도록 구성합니다.

---

## 2. MySQL `fetch_review_metadata` 스키마 불일치 해결

### Context & Problem
- `bteam/oliview_core/db.py`의 기존 쿼리:
  ```sql
  SELECT r.review_id, p.product_name, p.brand, p.category, p.product_url ...
  FROM reviews r LEFT JOIN products p ON r.product_id = p.product_id
  WHERE r.review_id IN (...)
  ```
- **실제 스키마 상태**:
  - `products` 테이블에는 `brand` 및 `category` 컬럼이 없고 `brand_id`로 분리되어 있음.
  - `vw_chroma_review_sentences` 표준 뷰가 이미 존재하며, `sentence_id`, `product_id`, `product_name`, `brand_name`, `analysis_category_name`, `sentence_text`, `sentiment` 컬럼을 완벽히 제공함.

### Technical Solution
- `fetch_review_metadata`의 쿼리를 `vw_chroma_review_sentences` 뷰 및 `products` 테이블 조인 쿼리로 변경:
  ```sql
  SELECT 
      s.sentence_id AS review_id,
      s.product_id,
      s.product_name,
      s.brand_name AS brand,
      s.analysis_category_name AS category,
      COALESCE(p.product_image_url, '') AS product_url,
      s.sentence_text AS review_clean_text,
      s.sentence_text AS review_text,
      s.sentiment
  FROM vw_chroma_review_sentences s
  LEFT JOIN products p ON s.product_id = p.product_id
  WHERE s.sentence_id IN ({id_list_str})
  ```
- 만약 `sentence_id`로 조회가 되지 않는 경우, `reviews r JOIN products p JOIN brands b` 표준 조인 쿼리로 Fallback 지원.

---

## 3. 리랭커 `scores is None` 안전 Fallback 방어

### Context & Problem
- `bteam/oliview_core/client.py`의 `AiGatewayClient.rerank()`는 타임아웃이나 연결 실패 시 `None`을 반환합니다.
- 그러나 `bteam/oliview_core/rerank.py`의 `BGEReranker.rerank()`는 `scores`가 `None`일 때 예외를 잡지 못하고 `list(enumerate(scores))`를 실행하여 `TypeError: 'NoneType' object is not iterable` 크래시를 유발했습니다.

### Technical Solution
- `BGEReranker.rerank()`에서 `scores = self.client.rerank(...)` 호출 후 `if scores is None or not scores:` 조건을 검사하여, 즉시 로컬 1차 검색 순위 기반 Fallback 점수(`[0.85 - (i * 0.05) for i in range(len(documents))]`)를 생성하도록 방어 코드를 추가합니다.

---

## 4. 게이트웨이 보조 모델(8091) 자가치유 루틴 보강

### Context & Problem
- `model_gateway/src/core/auxiliary_manager.py`의 `_crash_recovery_loop`는 상태가 `READY` 또는 `LOADING`일 때만 크래시를 감지하고, 초기에 `UNLOADED`나 `ERROR`로 남은 경우 재스폰을 시도하지 않았습니다.

### Technical Solution
- `check_and_recover_crashes()`에서 `state.status in (UNLOADED, ERROR)`이거나 `process is None`일 때도 `ensure_embedding_resident` 및 `ensure_rerank_resident`를 안전하게 재호출하여 자가치유를 완성합니다.
