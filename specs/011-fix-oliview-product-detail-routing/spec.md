# Feature Specification: Oliview 상품 상세 조회 404 경로 오류 해결 및 라우팅 정상화 (011-fix-oliview-product-detail-routing)

**Feature Branch**: `011-fix-oliview-product-detail-routing`

**Created**: 2026-08-18

**Status**: Draft

**Input**: User description: "Oliview 웹 포털에서 상품 클릭 시 상품 상세 및 감성 분석 리포트 API가 404(Not Found) 오류 및 SyntaxError JSON 파싱 오류를 발생시키며 상품 정보가 나타나지 않는 현상 해결"

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 내 브랜드 및 타사 브랜드 상품 상세/분석 리포트 정상 조회 (Priority: P1)

브랜드 담당자 및 일반 사용자는 Oliview 웹 포털(`https://ezenitac.duckdns.org/bteam/oliview/` 또는 `http://localhost:8080/bteam/oliview/`)의 '내 브랜드' 또는 '타사 브랜드' 페이지에서 특정 상품 카드를 클릭했을 때, 404 오류 없이 상품 기본 정보, 옵션, 속성별 레이더 차트, 유지할 점/개선점 감성 분석 리포트를 즉시 열람할 수 있어야 한다.

**Why this priority**: Oliview 서비스의 핵심 가치인 화장품 리뷰 감성 분석 대시보드를 사용자가 실제로 확인하고 활용하기 위한 가장 핵심적인 기본 기능(MVP)입니다.

**Independent Test**: Nginx 게이트웨이를 통해 브라우저에서 '내 브랜드' 접속 후 '헤라 블랙쿠션' 또는 임의의 상품을 클릭했을 때, 상품 이미지와 옵션, 속성별 분석 요약 및 리뷰 원문이 브라우저 콘솔 에러 없이 100% 렌더링되는지 확인합니다.

**Acceptance Scenarios**:

1. **Given** 로그인된 브랜드 담당자가 내 브랜드 상품 목록을 조회 중일 때, **When** 특정 상품(예: ID 7) 카드를 클릭하면, **Then** 화면이 상품 상세 페이지로 전환되며 상품명, 브랜드명, 상품 이미지, 옵션 목록이 정상 출력된다.
2. **Given** 상품 상세 페이지가 활성화되었을 때, **When** 백엔드로부터 감성 분석 리포트 API가 응답하면, **Then** 속성별 긍정/부정 비율 레이더 차트와 AI 종합 분석 요약 텍스트가 렌더링된다.
3. **Given** 사용자가 상세 페이지 조회를 완료했을 때, **When** 상단의 '← 상품 목록으로' 버튼을 클릭하면, **Then** 이전 상품 목록 그리드로 오류 없이 복귀한다.

---

### User Story 2 - Nginx 및 프론트엔드 API Base URL 전역 경로 일관성 보장 (Priority: P2)

프론트엔드의 모든 컴포넌트는 API 호출 시 Nginx 역방향 프록시의 전용 서브 경로인 `/bteam/oliview/api/*`로 요청을 전송하여, A-Team PILOS의 `/api/*` 경로와의 충돌 및 404 응답을 원천 방지해야 한다.

**Why this priority**: API 엔드포인트 경로가 일치하지 않으면 Nginx가 엉뚱한 마이크로서비스(PILOS)로 요청을 전달하여 404 HTML 응답 및 프론트엔드 JSON 파싱 에러를 유발합니다.

**Independent Test**: 브라우저 네트워크 탭에서 상품 클릭 시 발생하는 모든 XHR/Fetch 요청 URL이 `https://ezenitac.duckdns.org/bteam/oliview/api/products/*` 형태로 전송되고 200 OK를 수신하는지 확인합니다.

**Acceptance Scenarios**:

1. **Given** 프론트엔드 컴포넌트가 마운트될 때, **When** `apiBaseUrl` 프로퍼티가 비어있거나 undefined인 경우, **Then** 자동으로 전역 기본값 `'/bteam/oliview'`로 폴백되어 올바른 백엔드 URL로 요청이 전송된다.
2. **Given** Nginx 역방향 프록시가 가동 중일 때, **When** 클라이언트가 `/bteam/oliview/api/products/7`로 요청을 보내면, **Then** Nginx는 `oliview_backend:5050/api/products/7`로 정상 전달하여 200 OK 응답을 반환한다.

---

### User Story 3 - 백엔드 데이터 직렬화 안전성 및 핫리로드 볼륨 마운트 보장 (Priority: P3)

Flask 백엔드 API는 데이터베이스로부터 조회한 다양한 데이터 타입(`datetime`, `Decimal` 등)을 안전하게 JSON으로 직렬화하여 클라이언트에 500 에러 없이 반환하고, Docker 환경에서 소스 코드 변경 시 실시간 반영되어야 한다.

**Why this priority**: 데이터베이스 조회 결과의 포맷 문제로 인한 500 에러를 사전에 방어하고 유지보수성을 극대화합니다.

**Independent Test**: `python tests/test_multi_chatbot_regression.py` 및 단위 테스트를 실행하여 `/bteam/oliview/api/products/1` 조회가 200 OK 및 올바른 JSON 구조를 반환하는지 확인합니다.

**Acceptance Scenarios**:

1. **Given** 데이터베이스 상품 및 리뷰 테이블에 날짜/시간 필드가 포함되어 있을 때, **When** 백엔드가 상품 상세 데이터를 반환하면, **Then** 날짜 필드가 안전한 문자열(`YYYY-MM-DD`)로 직렬화되어 200 OK를 반환한다.
2. **Given** 개발자가 프론트엔드나 백엔드 코드를 수정했을 때, **When** 컨테이너가 실행 중이면, **Then** 볼륨 마운트를 통해 컨테이너 재빌드 없이 변경 사항이 즉시 반영된다.

---

### Edge Cases

- **비정상/누락된 상품 ID**: `sessionStorage`나 Props에 `productId`가 존재하지 않을 경우 "상품 ID를 찾을 수 없습니다. 다시 시도해주세요." 안내 문구 및 목록 이동 버튼 제공.
- **리뷰/옵션 데이터가 없는 신규 상품**: 옵션이나 분석 리포트가 없는 경우 차트 및 옵션 영역에 "등록된 데이터가 없습니다" 플레이스홀더를 표시하여 화면 깨짐 방지.
- **네트워크 단절 또는 백엔드 장애**: 백엔드 응답 실패 시 브라우저 콘솔 크래시 없이 "상품 정보를 불러오는 중입니다..." 또는 오류 메시지를 표시하고 로딩 상태 해제.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 시스템은 Oliview 프론트엔드의 모든 백엔드 호출이 `/bteam/oliview/api/*` 경로를 사용하도록 보장해야 한다.
- **FR-002**: 시스템은 `BaseProductDetail`, `ProductDetailPage`, `CompetitorProductDetailPage`, `MyBrandpage` 컴포넌트 간 `productId` 및 `apiBaseUrl` 프롭스 전달과 React 상태 동기화를 보장해야 한다.
- **FR-003**: Nginx 게이트웨이는 `/bteam/oliview/api/*` 요청을 `oliview_backend:5050/api/*`로 누락 없이 프록시하고, 공용 `/api/*` 경로(PILOS 전용)와 엄격히 격리해야 한다.
- **FR-004**: 백엔드 Flask API는 상품 상세, 카테고리, 속성별 감성 분석 리포트, 리뷰 상세 조회 응답 시 날짜 및 Decimal 타입을 안전하게 JSON으로 직렬화(Serialization)해야 한다.
- **FR-005**: `docker-compose.yml`은 프론트엔드 및 백엔드 소스 파일 변경 사항이 컨테이너에 즉시 동기화되도록 볼륨 마운트 구성을 유지해야 한다.
- **FR-006**: 통합 회귀 테스트 스위트에 Oliview 상품 상세 조회 및 감성 분석 리포트 API 응답 계약 검증 테스트를 포함해야 한다.

---

### Key Entities

- **ProductDetail**: 상품 식별자(`product_id`), 브랜드명(`brand_name`), 상품명(`product_name`), 상품 이미지 URL(`product_image_url`), 옵션 목록(`options`), 리뷰 데이터(`reviews`).
- **AttributeSentimentReport**: 분석 카테고리 속성명(`attribute_name`), 총 문장 수(`total_count`), 긍정/부정/중립 문장 수, 긍정 비율 점수(`score`), AI 강점 분석 요약(`positive_summary`), AI 개선점 분석 요약(`negative_summary`).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 사용자가 Oliview 포털에서 임의의 상품 클릭 시 404/500 에러 없이 1.0초 이내에 상세 페이지와 감성 분석 차트가 100% 정상 렌더링된다.
- **SC-002**: 브라우저 개발자 도구 콘솔에서 `SyntaxError: Unexpected token '<'` 또는 `GET /api/products/... 404 (Not Found)` 오류 발생 횟수가 0건으로 유지된다.
- **SC-003**: 상품 상세 및 분석 리포트 조회 엔드포인트 자동화 계약 검증 테스트 성공률 100%를 달성한다.

---

## Assumptions

- Oliview 웹 포털은 React 18 / Vite 기반 SPA 구조로 구동되며 기본 URL 경로는 `/bteam/oliview/`이다.
- Oliview 백엔드는 Flask / Gunicorn 기반으로 구동되며 컨테이너 내부 포트는 5050이다.
- 게이트웨이 Nginx는 단일 도메인 및 포트(`8080`, `80`, `443`)를 통해 모든 서비스로 역방향 라우팅을 수행한다.
- 데이터베이스에는 사전에 구축된 상품, 리뷰, 감성 분석 통계 데이터가 정상 적재되어 있다.
