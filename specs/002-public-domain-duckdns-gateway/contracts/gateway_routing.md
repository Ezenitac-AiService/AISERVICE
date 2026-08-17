# Contract: Gateway Reverse Proxy Routing & HTTPS Protocol Specifications

**Component**: `aiservice-gateway` (Nginx) & Traefik Ingress (K3s)  
**Spec Reference**: [spec.md](file:///c:/AISERVICE/specs/002-public-domain-duckdns-gateway/spec.md) (FR-001 ~ FR-007)

---

## 1. External Inbound Gateway Ports & URLs

- **Primary HTTPS (SSL/TLS)**: `https://ezenitac.duckdns.org/` (Let's Encrypt, Port 443)
- **HTTP Redirect (301)**: `http://ezenitac.duckdns.org/` (Port 80 ➔ 301 HTTPS)
- **Alternate Direct Port**: `http://ezenitac.duckdns.org:8080/` or `http://localhost:8080/`

---

## 2. Inbound Routing Map

| Request URI Path | Upstream Container | Protocol & Port | Purpose | Key Proxy Directives |
|---|---|---|---|---|
| `/` | `aiservice-gateway` (Local) | Static HTML | Unified Portal Landing | `try_files /index.html =404;` |
| `/bteam/oliview/` | `oliview_frontend` | HTTP/WS (Port 5173) | B-Team React Vite SPA | `proxy_http_version 1.1; Upgrade & Connection` |
| `/bteam/oliview/api/` | `oliview_backend` | HTTP (Port 5050) | B-Team Flask Backend API | `proxy_pass http://oliview_backend:5050/api/;` |
| `/bteam/chata/` | `oliview_chatbot_a` | HTTP/WSS (Port 8501) | Streamlit 올리챗 | `Upgrade & Connection; proxy_buffering off;` |
| `/bteam/chatb/` | `oliview_chatbot_b` | HTTP (Port 8002) | FastAPI 올원챗 RAG | `proxy_set_header X-Forwarded-Prefix /bteam/chatb;` |
| `/ateam/pilos/` | `pilos-web` | HTTP (Port 5000) | A-Team Flask 대시보드 | `proxy_set_header X-Forwarded-Prefix /ateam/pilos;` |

---

## 3. Proxy Header Contracts (All Upstreams)

```nginx
proxy_set_header Host $http_host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Port $server_port;
proxy_set_header X-Request-ID $request_id;
proxy_redirect off;
port_in_redirect off;
```
