# Interface Contract: Ingress Gateway Routing & Proxy Map

---

## 1. 개요
단일 통합 진입점(`http://localhost:8080` / `aiservice-gateway`)을 통한 모든 서브도메인 웹 및 API 라우팅 계약서이다.

---

## 2. 라우팅 매핑 규칙 (Routing Table)

| 진입 경로 (URL Path) | 프로토콜 | 백엔드 대상 (Upstream Target) | 특수 설정 (Proxy Directives) |
|---|---|---|---|
| `/` | HTTP | `static html (index.html)` | 통합 포털 랜딩 페이지, No-Cache |
| `/bteam/oliview/api/` | HTTP | `oliview_backend:5050/api/` | CORS 전체 허용, `proxy_buffering off`, 300s 타임아웃 |
| `/bteam/oliview/` | HTTP / WS | `oliview_frontend:5173/` | React Vite Web UI, HMR WebSocket Upgrade |
| `/bteam/chata/` | HTTP / WS | `oliview_chatbot_a:8501/` | Streamlit Web UI, WebSocket Upgrade, 300s 타임아웃 |
| `/bteam/chata/_stcore/stream` | WebSocket | `oliview_chatbot_a:8501/...` | Streamlit Core WebSocket, 86400s 타임아웃 |
| `/bteam/chatb/` | HTTP | `oliview_chatbot_b:8002/` | FastAPI Web UI & API (`X-Forwarded-Prefix: /bteam/chatb`) |
| `/ateam/pilos/` | HTTP | `pilos-web:5000/` | PILOS 대시보드 Web UI (`X-Forwarded-Prefix: /ateam/pilos`) |
| `/api/` | HTTP | `pilos-web:5000/api/` | PILOS 메인 API 및 챗봇(`/api/chat`) 엔드포인트 |
| `/stocks/`, `/about` | HTTP | `pilos-web:5000/...` | PILOS 서브 웹 라우트 |

---

## 3. 프록시 공통 헤더 및 정책

- **헤더 주입**:
  - `Host: $http_host`
  - `X-Real-IP: $remote_addr`
  - `X-Forwarded-For: $proxy_add_x_forwarded_for`
  - `X-Forwarded-Proto: $forwarded_proto`
  - `X-Request-ID: $request_id`
- **로깅**:
  - JSON 구조화 로그 (`/var/log/nginx/access.log`)
  - 필드: `time_local`, `remote_addr`, `request_id`, `request_method`, `request_uri`, `status`, `request_time`, `upstream_response_time`, `upstream_addr`
