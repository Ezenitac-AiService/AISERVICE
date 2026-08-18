# Interface Contract: Oliview Frontend & Backend API Routes (FR-008)

---

## 1. 개요
Oliview React 프론트엔드(`bteam/Oliview_Project/frontend`)와 백엔드(`bteam/Oliview_Project/backend`) 간의 API 통신 규격 및 전역 `apiBaseUrl` 폴백 계약서이다.

---

## 2. API Base URL 계약

- **기본 접두사 (Default Base URL)**: `/bteam/oliview`
- **백엔드 프록시 매핑**: `/bteam/oliview/api/*` → `http://oliview_backend:5050/api/*`

---

## 3. 프론트엔드 라우트 및 컴포넌트 호출 규격

| 컴포넌트 | 요청 엔드포인트 | Method | 목적 |
|---|---|---|---|
| `MyBrandpage.jsx` | `/bteam/oliview/api/products` | GET | 로그인 브랜드의 등록 상품 목록 조회 |
| `BaseProductDetail.jsx` | `/bteam/oliview/api/products/:id` | GET | 상품 기본 정보 및 옵션 조회 |
| `ProductDetailPage.jsx` | `/bteam/oliview/api/analysis/report/:id` | GET | AI 감성 분석 리포트 및 키워드 조회 |
| `CompetitorProductDetailPage.jsx` | `/bteam/oliview/api/competitor/products/:id` | GET | 경쟁사 비교 상품 데이터 조회 |

---

## 4. 프론트엔드 안전성 보장 규칙

1. 모든 컴포넌트는 `props.apiBaseUrl`이 전달되지 않거나 빈 값인 경우 기본값 `'/bteam/oliview'`로 자동 폴백한다.
2. 절대 경로 `/api/...`로의 직접 호출은 전면 금지하며, 반드시 `${apiBaseUrl}/api/...` 형식을 준수한다.
