# Data Model: Oliview B-Team RAG 파이프라인 데이터 모델 및 스키마 명세 (Feature 045)

**Feature Branch**: `045-fix-bteam-rag-zero-search`
**Date**: 2026-09-02
**Status**: Completed

## 1. MySQL Review Sentence View Schema (`vw_chroma_review_sentences`)

ChromaDB와 MySQL 하이브리드 검색 및 메타데이터 조회의 단일 진실 공급원(SSOT) 뷰 구조입니다.

| Field Name | Type | Description | Mapping in Oliview Core |
|:---|:---|:---|:---|
| `sentence_id` | `BIGINT UNSIGNED` | 문장 고유 ID (PK) | `review_id` |
| `sentence_text` | `TEXT` | 전처리된 리뷰 문장 본문 | `review_clean_text`, `review_text` |
| `product_id` | `INT` | 상품 고유 ID | `product_id` |
| `product_name` | `VARCHAR(300)` | 올리브영 상품 정식 명칭 | `product_name` |
| `brand_id` | `INT` | 브랜드 고유 ID | `brand_id` |
| `brand_name` | `VARCHAR(100)` | 브랜드 명칭 (차앤박, 브링그린 등) | `brand` |
| `analysis_category_id` | `INT` | 뷰티 카테고리 ID | `analysis_category_id` |
| `analysis_category_name` | `VARCHAR(100)` | 카테고리 명칭 (클렌징, 스킨케어 등) | `category` |
| `attribute_name` | `VARCHAR(100)` | 화장품 평가 속성 (자극성, 세정력 등) | `attribute` |
| `sentiment` | `VARCHAR(10)` | 감성 분석 라벨 (POSITIVE/NEGATIVE/NEUTRAL) | `sentiment` |
| `review_date` | `DATE` | 고객 리뷰 작성 일자 | `review_date` |

---

## 2. Review Metadata Dict Entity (`fetch_review_metadata` 반환값)

```python
{
    12345: {
        "review_id": 12345,
        "product_id": 101,
        "product_name": "브링그린 티트리 시카 포어 클렌징 오일",
        "brand": "브링그린",
        "category": "클렌징",
        "product_url": "https://www.oliveyoung.co.kr/...",
        "review_clean_text": "모공 피지 세정력이 좋고 순해서 자극 없이 클렌징돼요.",
        "review_text": "모공 피지 세정력이 좋고 순해서 자극 없이 클렌징돼요.",
        "sentiment": "POSITIVE"
    }
}
```

---

## 3. Llama.cpp Command Arguments Entity (64K q8_0 KV Cache)

```python
[
    "/app/.venv/bin/python3",
    "-m", "llama_cpp.server",
    "--model", "/app/models/qwen3.5-2b/Qwen3.5-2B-Q4_K_M.gguf",
    "--n_ctx", "65536",
    "--host", "0.0.0.0",
    "--port", "8089",
    "--n_gpu_layers", "999",
    "--n_batch", "512",
    "--type_k", "q8_0",
    "--type_v", "q8_0"
]
```
