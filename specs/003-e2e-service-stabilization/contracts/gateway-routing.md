# Contract: Gateway Reverse Proxy & Routing Topology

**Component**: Gateway (`gateway:8080`, `gateway/nginx.conf`)  
**Public Host**: `https://ezenitac.duckdns.org`  
**Local Host**: `http://localhost:8080`

---

## Routing Table

| URL Pattern | Target Upstream | Description | Buffering / Features |
|---|---|---|---|
| `/` (Exact) | Local `/usr/share/nginx/html/index.html` | 통합 포털 랜딩 페이지 | Cache-Control: no-cache |
| `/ateam/pilos/` | `http://pilos-web:5000/` | Pilos 메인 대시보드 | `proxy_set_header X-Forwarded-Prefix /ateam/pilos` |
| `/stocks/` | `http://pilos-web:5000/stocks/` | Pilos 종목 상세 화면 | 404 방지 프록시 |
| `/about` | `http://pilos-web:5000/about` | Pilos 어바웃 페이지 | 404 방지 프록시 |
| `/api/` | `http://pilos-web:5000/api/` | Pilos 프론트엔드 API | `proxy_read_timeout 300s` |
| `/bteam/oliview/api/` | `http://oliview_backend:5050/api/` | Oliview REST 백엔드 API | `^~` 최우선 순위, CORS 헤더 |
| `/bteam/oliview/` | `http://oliview_frontend:5173` | Oliview React SPA 프론트엔드 | WebSocket HMR 프록시 |
| `/bteam/chata/` | `http://oliview_chatbot_a:8501` | 올리챗 Streamlit 대시보드 | `_stcore/stream` WS 업그레이드 |
| `/bteam/chatb/` | `http://oliview_chatbot_b:8002/` | 올원챗 FastAPI + 정적 UI | `proxy_buffering off` |
