# Quickstart Validation Guide: 029-analytics-driven-refactoring

본 가이드는 리팩토링 변경사항이 의도대로 동작하는지 End-to-End로 검증하기 위한 시나리오입니다.

---

## 1. 사전 요구사항 (Prerequisites)

- AISERVICE 도커 컨테이너 전체 실행 상태 (`docker ps`)
- Nginx Gateway (`aiservice-gateway`), Pilos Web (`pilos-web`), Oliview Backend (`oliview_backend`)

---

## 2. 검증 시나리오 및 실행 명령

### 시나리오 1: 주식 종목 로고 404 에러 해결 및 정적 서빙 검증

1. **로고 이미지 HTTP 요청 테스트**:
   ```bash
   curl -I http://localhost/static/images/stock-logos/000660.png
   curl -I http://localhost/static/images/stock-logos/005930.png
   curl -I http://localhost/static/images/stock-logos/247540.png
   ```
2. **예상 결과**:
   - HTTP 상태 코드 `200 OK`
   - `Content-Type: image/png`
   - `Cache-Control: public, max-age=86400` 헤더 포함

---

### 시나리오 2: 모바일 뷰포트 및 Open Graph 메타태그 검증

1. **각 서비스 HTML 헤더 검증**:
   ```bash
   # 포털 메타태그
   curl -s http://localhost/ | grep -E "og:title|og:image|viewport-fit"
   
   # Pilos 메타태그
   curl -s http://localhost/ateam/pilos/ | grep -E "og:title|og:image"
   
   # Oliview 메타태그
   curl -s http://localhost/bteam/oliview/ | grep -E "og:title|og:image"
   ```
2. **예상 결과**:
   - `viewport-fit=cover` 설정 확인
   - 각 서비스별 고유의 `og:title`, `og:description`, `og:image` 메타태그 정상 출력

---

### 시나리오 3: 통합 포털 비동기 큐레이션 위젯 렌더링 검증

1. **브라우저 접속**: `http://localhost/` 접속
2. **예상 결과**:
   - 메인 화면에 "🔥 실시간 주식 수급 감정 핫 종목" 및 "💄 실시간 뷰티 핫 키워드" 위젯이 비동기로 부드럽게 로드됨
   - 각 위젯 카드 클릭 시 `/ateam/pilos/` 또는 `/bteam/oliview/`로 정확히 네비게이션 동작

---

### 시나리오 4: B-Team 백엔드 API Graceful Fallback 검증

1. **미등록 브랜드 상품/카테고리 호출**:
   ```bash
   curl -s http://localhost/bteam/oliview/api/brands/999999/products
   curl -s http://localhost/bteam/oliview/api/brands/999999/categories
   ```
2. **예상 결과**:
   - HTTP 500 서버 크래시가 발생하지 않고 `200 OK`와 `{"success": true, "products": []}` 반환
