# Technical Research & Architecture Decisions: Oliview 상품 상세 조회 404 경로 오류 해결

**Feature**: `011-fix-oliview-product-detail-routing` | **Date**: 2026-08-18

---

## 1. 프론트엔드 API Base URL 전역 폴백 및 Props/State 동기화

### Decision
`BaseProductDetail.jsx`, `ProductDetailPage.jsx`, `CompetitorProductDetailPage.jsx`, `MyBrandpage.jsx` 전 컴포넌트에서 `apiBaseUrl`이 비어있거나 `undefined`일 때 강제로 `'/bteam/oliview'`로 폴백하도록 설정하고, `ProductDetailPage` 및 `CompetitorProductDetailPage`가 부모로부터 전달받은 `productId` prop을 수신하여 `useEffect`로 동기화하도록 구현한다.

### Rationale
- 사용자의 브라우저 오류 화면 콘솔 로그(`GET https://ezenitac.duckdns.org/api/products/7 404 (Not Found)`)에서 보듯, `baseUrl`이 빈 문자열(`""`)로 평가되어 Nginx의 공용 `/api/` (PILOS 전용)로 요청이 잘못 라우팅되었습니다.
- 컴포넌트 내부 기본값을 `apiBaseUrl || '/bteam/oliview'`로 보장하면 어떤 렌더링 컨텍스트에서도 `/bteam/oliview/api/products/{id}`로 정규화되어 Nginx가 `oliview_backend:5050`으로 정확히 전달합니다.

### Alternatives Considered
- **Vite 환경변수(`import.meta.env.VITE_API_BASE_URL`)에만 의존**: 빌드 시 환경변수가 누락되거나 SSR/정적 배포 시 빈 값이 전달될 위험이 있어 코드 레벨 전역 폴백을 병행하는 것이 안전합니다.
- **Window 전역 변수(`window.__API_BASE__`) 사용**: React의 단방향 데이터 흐름을 위반하고 테스트 격리가 어려우므로 배제했습니다.

---

## 2. Nginx 역방향 프록시 서브 경로 라우팅 격리

### Decision
`gateway/nginx.conf`의 `location ^~ /bteam/oliview/api/` 규칙을 통해 `http://oliview_backend:5050/api/`로 프록시 패스하고, `proxy_buffering off` 및 `proxy_read_timeout 300s`를 유지한다.

### Rationale
- Oliview 프론트엔드는 `/bteam/oliview/` 서브 경로에 호스팅되므로, 백엔드 API 호출 시 `/bteam/oliview/api/...`를 호출하면 Nginx가 `/bteam/oliview/api/` 접두사를 `/api/`로 변환하여 내부 백엔드(`oliview_backend:5050`)로 완벽히 포워딩합니다.
- 최상위 `/api/`는 A-Team PILOS Flask 서버(`pilos-web:5000`)에 할당되어 있으므로, Oliview 요청이 최상위 `/api/`로 새어 나가지 않도록 완전 격리합니다.

### Alternatives Considered
- **모든 API를 `/api/oliview/...` 형태로 변경**: 기존 프론트엔드/백엔드 코드베이스 전체의 라우트 데코레이터를 대규모 수정해야 하므로 변경 범위를 최소화하는 `/bteam/oliview/api/` 프록시를 채택했습니다.

---

## 3. 백엔드 Flask 데이터 직렬화(Serialization) 무결성 보장

### Decision
`bteam/Oliview_Project/backend/app.py`에 `serialize_val`, `serialize_row`, `serialize_rows` 직렬화 헬퍼를 구축하여 DB 조회 결과의 `datetime`, `Decimal` 등을 안전하게 변환한 후 `jsonify()`에 전달한다.

### Rationale
- PyMySQL `DictCursor`를 사용할 때 DB의 `DATETIME`, `TIMESTAMP`, `DECIMAL` 타입이 Python `datetime.datetime` 및 `decimal.Decimal` 인스턴스로 반환됩니다.
- 구형 Flask/Werkzeug 또는 복합 중첩 JSON 직렬화 시 `TypeError: Object of type Decimal is not JSON serializable` 오류가 발생하여 500 에러를 유발할 수 있으므로, 응답 전 계층에서 안전하게 변환합니다.

### Alternatives Considered
- **Flask 커스텀 `JSONProvider` 등록**: 일부 라이브러리 함수나 직접 직렬화 시 우회될 수 있으므로 엔드포인트 반환 계층에서 명시적 헬퍼 함수를 적용하는 것이 가장 직관적이고 안전합니다.

---

## 4. Docker 실시간 핫리로드 볼륨 마운트

### Decision
`docker-compose.yml`에서 `oliview_backend`에 `./bteam/Oliview_Project/backend:/app`, `oliview_frontend`에 `./bteam/Oliview_Project/frontend:/app` 볼륨 마운트를 지정한다.

### Rationale
- 개발 및 운영 환경에서 코드 수정 시 컨테이너를 매번 `docker-compose build`하지 않고도 파일 변경 사항이 실시간으로 컨테이너에 반영되어 빠른 검증과 안정적인 디버깅이 가능합니다.

---

## 5. 자동화된 계약 검증 및 회귀 테스트 확장

### Decision
`tests/test_multi_chatbot_regression.py`에 Oliview 상품 상세 조회(`GET /bteam/oliview/api/products/1`), 감성 분석 리포트(`GET /bteam/oliview/api/products/1/analysis-report`), 리뷰 상세 조회(`GET /bteam/oliview/api/products/1/reviews-detail`) 계약 검증 테스트 케이스를 추가한다.

### Rationale
- 표준 라이브러리(`urllib.request`, `unittest`) 기반으로 Nginx 8080 포트를 통한 실제 프록시 라우팅과 백엔드 JSON 응답 형식을 자동으로 검증하여 향후 회귀 오류를 방지합니다.
