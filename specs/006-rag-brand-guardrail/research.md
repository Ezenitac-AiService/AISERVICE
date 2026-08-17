# Phase 0 Research: RAG 브랜드 엔티티 인식 및 데이터 결측치 배제·올리뷰 브랜드 조회 정규화 (006-rag-brand-guardrail)

**Feature**: `006-rag-brand-guardrail`  
**Date**: 2026-08-17  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/006-rag-brand-guardrail/spec.md)

---

## 1. 프론트엔드 Double `/api/` 404 버그 및 정규화 방안

### Decision 1: `App.jsx`의 `API_BASE_URL` 기본값을 `'/bteam/oliview'`로 변경
- **현상**: `App.jsx`에서 `API_BASE_URL` 기본값이 `'/bteam/oliview/api'`로 지정되어, 각 컴포넌트(`LoginPage.jsx`, `RegisterPage.jsx` 등)에서 `${baseUrl}/api/search-brands`를 호출할 때 `/bteam/oliview/api/api/search-brands`로 이중 결합되어 Nginx 404가 발생함.
- **해결 방안**:
  ```javascript
  // bteam/Oliview_Project/frontend/src/App.jsx
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/bteam/oliview';
  ```
- **결정 근거**: 모든 하위 컴포넌트의 `${baseUrl}/api/...` 호출 규격과 100% 일치하며, `LoginPage`의 "헤라" 검색 시 `GET /bteam/oliview/api/search-brands?keyword=헤라` (200 OK, `헤라 ID: 68`)가 즉시 정상 동작함.

---

## 2. RAG 데이터베이스 결측치 원천 배제 방안 (SQL Guardrail)

### Decision 2: RAG 후보군 조회 시 유효 브랜드명 및 상품명 필수 조건 강제
- **현상**: `review_aspect_sentences` 테이블의 59,407건 중 56.6%(33,603건)가 `brand_name` 또는 `product_name`이 `NULL` 또는 빈 문자열(`''`)인 결측치 데이터임.
- **해결 방안**:
  ```sql
  WHERE embedding_vector IS NOT NULL
    AND brand_name IS NOT NULL AND TRIM(brand_name) != '' AND brand_name != '미분류 브랜드'
    AND product_name IS NOT NULL AND TRIM(product_name) != '' AND product_name != '미분류 상품'
  ```
- **결정 근거**: 결측치 및 더미 데이터가 1단계 RAG 후보군으로 유입되는 것을 원천 차단하여 `[익명]` 또는 `미분류 브랜드` 환각의 발생 소지를 100% 제거함.

---

## 3. 질의 불용어(Stopwords) 제거 및 브랜드 엔티티 감지 방안

### Decision 3: 불용어 사전 필터링 및 3,062개 활성 브랜드 사전 매칭
- **선택된 방안**:
  1. **불용어(Stopwords) 필터링**:
     - `STOPWORDS = {"스킨케어", "화장품", "제품", "추천", "추천해줘", "추천해", "알려줘", "분석해줘", "분석해", "비교해줘", "좋은", "어떤게", "인기", "순위", "리뷰", "사용기"}`
     - 사용자 질문에서 불용어를 제외한 유의미한 키워드만 SQL LIKE 토큰으로 활용하여 검색 오염 방지.
  2. **브랜드 엔티티(Entity) 감지**:
     - 질의 텍스트에서 3,062개 등록 브랜드명을 최장 일치(Longest Match) 방식으로 감지.
     - 감지된 브랜드가 `review_aspect_sentences`에 리뷰 데이터가 0건인 경우(예: '헤라', '샤넬'), 무관한 타사 제품을 검색하지 않고 즉시 **"죄송합니다. 현재 '[브랜드명]' 브랜드의 등록 상품 및 리뷰 데이터가 올리뷰에 존재하지 않습니다. 올리브영에 등록된 다른 브랜드명으로 검색해 주세요."** 표준 안내문을 반환 (0-결과 폴백).
     - 감지된 브랜드가 DB에 리뷰가 있는 경우, `request_body.brand = detected_brand`로 자동 승격하여 해당 브랜드 제품만 정밀 검색.
- **결정 근거**: 사용자의 명시적 브랜드 질의 의도를 100% 보존하고, 부재 브랜드 질의 시 엉뚱한 제품 추천을 완벽히 차단.

---

## 4. 프롬프트 네거티브 가드레일 강화

### Decision 4: 타사 브랜드 및 [익명] 브랜드 지어내기 절대 금지 지침 주입
- **선택된 방안**:
  - `project_ragapi.py` 내 `system_prompt`에 다음 제약 추가:
    - "제공된 [실시간 화장품 리뷰 검색 결과 데이터]에 명시된 실제 브랜드명과 상품명만 사용하십시오."
    - "질문과 일치하지 않는 타사 브랜드를 질문의 브랜드인 것처럼 설명하거나, [익명] 브랜드 또는 미분류 브랜드로 표현하는 것을 절대 금지합니다."
- **결정 근거**: LLM이 컨텍스트 외부의 정보를 임의로 상상하여 답변하는 환각을 완벽 차단.
