# Phase 1 Data Model & Manifest Schema: 028-cross-platform-migration-pack

**Feature**: [spec.md](file:///c:/AISERVICE/specs/028-cross-platform-migration-pack/spec.md)  
**Date**: 2026-08-20  
**Status**: Completed  

---

## 1. 마이그레이션 대상 데이터베이스 명세 (Database Inventory)

### 1.1 `pilos_v2` (A-Team Pilos Sentiment & Report Database)
- **DBMS**: MySQL 8.0 (`utf8mb4_unicode_ci`, Timezone: `Asia/Seoul`)
- **총 데이터 크기**: 약 **3,415 MB (3.4 GB)**
- **총 레코드 수**: 약 **12,830,000+ 행**
- **주요 테이블 및 볼륨**:
  | 테이블명 (Table) | 행 수 (Rows) | 크기 (Size MB) | 핵심 역할 및 무결성 제약 |
  | :--- | :--- | :--- | :--- |
  | `tokenized_comment` | 4,343,818 | 1,425.69 MB | Kiwi 형태소 분석 토큰 시계열 인덱스 |
  | `preprocessed_comment` | 3,783,829 | 1,181.14 MB | 비식별화/마스킹 및 정제된 댓글 원천 |
  | `daily_document_comment` | 4,682,382 | 615.64 MB | 일별 종목별 댓글 매핑 다대다 관계 |
  | `daily_document` | 9,831 | 169.06 MB | 10개 종목 일별 집계 문서 정본 |
  | `llm_report` | 1,098 | 11.88 MB | Qwen LLM 시장 코멘터리 및 JSON 보고서 |
  | `sentiment_index_result`| 1,676 | 4.69 MB | Ridge v4 긍/부정 감정지수 추론 결과 |
  | `service_pipeline_run` | 321 | 3.53 MB | 7단계 정기 파이프라인 실행 이력 |
  | `source_comment_file` | 7,856 | 3.22 MB | 네이버/토스 원천 크롤링 파일 메타데이터 |
  | `supply_demand` | 3,918 | 1.89 MB | 개인/외인/기관 수급 거래량 및 지수 |
  | `artifacts` | 8 | 0.03 MB | ML 모델 가중치 및 설정 메타데이터 |
  | `stock` | 10 | 0.03 MB | 10대 코스피/코스닥 대상 종목 마스터 |

---

### 1.2 `oliview_project` (B-Team Oliview Beauty RAG Database)
- **DBMS**: MySQL 8.0 (`utf8mb4_unicode_ci`, Timezone: `Asia/Seoul`)
- **총 데이터 크기**: 약 **950 MB**
- **총 레코드 수**: 약 **175,000+ 행**
- **주요 테이블 및 볼륨**:
  | 테이블명 (Table) | 행 수 (Rows) | 크기 (Size MB) | 핵심 역할 및 무결성 제약 |
  | :--- | :--- | :--- | :--- |
  | `review_aspect_sentences`| 57,033 | 911.09 MB | **1024차원 BGE-M3 밀집 임베딩 벡터**, 속성/극성 문장 |
  | `reviews` | 51,888 | 25.13 MB | 올리브영 원천 화장품 리뷰 본문 및 별점 |
  | `aspect_sentiment_results`| 58,024 | 4.03 MB | KcELECTRA 딥러닝 10대 화장품 속성 분석 결과 |
  | `llm_product_attribute_reports`| 3,520 | 3.14 MB | 상품 속성별 LLM 종합 분석 리포트 |
  | `llm_product_reports` | 604 | 1.53 MB | 상품별 총평 및 장단점 LLM 요약 |
  | `brands` | 3,062 | 0.30 MB | 올리브영 등록 브랜드 마스터 |
  | `products` | 262 | 0.14 MB | 뷰티 화장품 상품 마스터 및 카테고리 |
  | `categories` | 451 | 0.09 MB | 올리브영 3단계 카테고리 분류 체계 |
  | *뷰 (Views)* | 10개 뷰 | - | `vw_target_brands`, `vw_chroma_review_sentences` 등 |

---

## 2. 마이그레이션 매니페스트 스키마 (`migration_manifest.json`)

마이그레이션 팩의 무결성 검증 및 추적을 위해 패키지 루트에 생성되는 JSON 메타데이터 스키마입니다.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "MigrationManifest",
  "type": "object",
  "required": [
    "manifest_version",
    "exported_at",
    "source_environment",
    "databases",
    "checksums"
  ],
  "properties": {
    "manifest_version": {
      "type": "string",
      "example": "1.0.0"
    },
    "exported_at": {
      "type": "string",
      "format": "date-time"
    },
    "source_environment": {
      "type": "object",
      "properties": {
        "os": { "type": "string" },
        "docker_version": { "type": "string" },
        "compose_version": { "type": "string" }
      }
    },
    "databases": {
      "type": "object",
      "properties": {
        "pilos_v2": {
          "type": "object",
          "properties": {
            "dump_file": { "type": "string" },
            "compressed_size_bytes": { "type": "integer" },
            "table_counts": { "type": "object" },
            "sha256": { "type": "string" }
          }
        },
        "oliview_project": {
          "type": "object",
          "properties": {
            "dump_file": { "type": "string" },
            "compressed_size_bytes": { "type": "integer" },
            "table_counts": { "type": "object" },
            "sha256": { "type": "string" }
          }
        }
      }
    },
    "checksums": {
      "type": "object",
      "additionalProperties": { "type": "string" }
    }
  }
}
```

---

## 3. 체크섬 매니페스트 포맷 (`checksums.sha256`)

```text
a1b2c3d4e5f6...  database/pilos_v2.sql.gz
f6e5d4c3b2a1...  database/oliview_project.sql.gz
1234567890ab...  docker-compose.yml
abcdef123456...  config/.env.migration.template
```
