# Research: 분석 보고서 기반 시스템 최적화 리팩토링 (029-analytics-driven-refactoring)

## Phase 0 Research & Technical Decisions

### 1. 주식 종목 로고 정적 서빙 및 404 오류 해결 방안

- **현황 분석**:
  - Pilos 프론트엔드에서 `/static/images/stock-logos/{code}.png` 경로로 10대 종목 로고를 요청함.
  - 게이트웨이(`gateway/nginx.conf`)에 `/static/` 라우팅 규칙이 없어 Nginx의 기본 루트(`/usr/share/nginx/html/`)를 조회하면서 총 2,608건의 404 에러 발생 (SK하이닉스 116건, 삼성전자 106건 등).
  - 실제 로고 이미지 96종은 `ateam/pilos-sentiment-index/pilos/web/static/images/stock-logos/`에 완벽히 구비되어 있으며 `pilos-web` 컨테이너(포트 5000)에서 서빙 가능함.
- **결정 (Decision)**:
  1. `gateway/nginx.conf`에 `location /static/` 및 `location /static/images/` 프록시 패스를 추가하여 `pilos-web:5000/static/`으로 직접 라우팅하고 캐시 헤더(`Cache-Control: public, max-age=86400`) 부여.
  2. Pilos 프론트엔드 JavaScript(`pilos/web/static/js/common.js` 또는 `index.html`)에 `onerror` 핸들러를 추가하여, 이미지 로딩 실패 시 종목명 첫 글자 기반의 동적 SVG/CSS 원형 컬러 아바타로 즉시 대체 표시.
- **대안 검토**:
  - Nginx 게이트웨이 컨테이너에 이미지 파일을 직접 복사하는 방안: 이미지 갱신 시 게이트웨이 재빌드가 필요하므로 기각. 프록시 패스 및 캐싱 방식 채택.

---

### 2. 모바일 및 카카오톡 인앱 브라우저(19.3%) 맞춤 UX 및 Open Graph 메타태그

- **현황 분석**:
  - 접속 로그 분석 결과, 전체 트래픽의 27%가 모바일이며 특히 **카카오톡 인앱 브라우저(`KakaoTalk In-App`) 점유율이 19.3%(2,481건)**에 달함.
  - 현재 게이트웨이 랜딩(`/index.html`) 및 서브 서비스 HTML에 `viewport-fit=cover` 미적용 및 Open Graph(`og:title`, `og:image`, `og:description`) 태그 누락.
- **결정 (Decision)**:
  1. **Open Graph(OG) 메타태그 개별화**:
     - 통합 포털 (`/index.html`): `AISERVICE 통합 AI 포털`, 4대 AI 서비스 소개 및 메인 썸네일
     - A-Team Pilos (`templates/index.html`): `Pilos 주식 수급 감정지수 AI`, 실시간 종목 감정 리포트 소개
     - B-Team Oliview (`index.html`): `Oliview 화장품 리뷰 감정분석`, 5만 건 올리브영 리뷰 분석 대시보드
     - B-Team 올리챗 A (`06.02_chatbot_frontend.py`): `올리챗 초보자 맞춤 뷰티 가이드 AI`
  2. **모바일 뷰포트 & Safe-Area 스타일링**:
     - `meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"`
     - CSS `padding-top: env(safe-area-inset-top)`, `padding-bottom: env(safe-area-inset-bottom)` 및 모바일 터치 타겟(최소 44px) 최적화.

---

### 3. 통합 포털 랜딩(`/`) 실시간 큐레이션 위젯 설계

- **현황 분석**:
  - 포털 진입 비중이 2.4%(309건)로 낮고, 랜딩 후 서브 서비스로의 유입을 유도하는 능동적인 컨텐츠 부족.
- **결정 (Decision)**:
  - 포털 메인 카드 영역 상단에 **"🔥 실시간 주식 수급 감정 핫 종목"** (SK하이닉스, 삼성전자 등 실시간 감정 상태)과 **"💄 실시간 뷰티 리뷰 인기 키워드"** (수분크림, 민감성 등) 위젯을 추가.
  - 클라이언트 사이드에서 비동기 `fetch('/api/stocks')` 및 `fetch('/bteam/oliview/api/brands')`를 호출하여 백엔드 부하 없이 논블로킹(Non-blocking)으로 렌더링.
  - 클릭 시 해당 종목 상세 또는 리뷰 대시보드로 즉시 딥링크 연결.

---

### 4. B-Team 백엔드 API 안정성 및 Graceful Fallback 처리

- **현황 분석**:
  - `/bteam/oliview/api/brands/<brand_id>/products` 및 `categories` 엔드포인트에서 44건의 500 에러 발생.
  - 원인: DB 커넥션 예외 또는 빈 결과셋 처리 시 예외 전파.
- **결정 (Decision)**:
  - Flask `app.py`의 엔드포인트에 방어적 쿼리 실행 및 `try...except` 세분화.
  - 데이터가 없거나 DB 일시 오류 시 500 크래시 대신 `{"success": true, "products": [], "categories": [], "fallback": true}`와 `200 OK` 또는 적절한 상태 코드를 반환하여 프론트엔드가 크래시되지 않도록 보장.
