# Contract: Nginx Gateway Routing & Protocol Specification

**Feature**: `001-unified-services-gateway`

**Version**: 1.0.0

**Protocol**: HTTP/1.1, WebSocket (RFC 6455), Server-Sent Events (SSE)

---

## 1. Gateway Entry Points & Routing Map

| External URL Path | Upstream Container | Protocol | Header Transformations & Rewrites |
|---|---|:---:|---|
| `GET /` | `gateway (local static)` | HTTP | Serves `gateway/html/index.html` directly with `Cache-Control: no-cache` |
| `/bteam/oliview/api/(.*)` | `http://oliview_backend:5050/api/$1` | HTTP | `proxy_pass http://oliview_backend:5050/api/;`, `proxy_set_header Host $http_host;`, `proxy_redirect off;` |
| `/bteam/oliview/(.*)` | `http://oliview_frontend:5173/` | HTTP/WS | `proxy_pass http://oliview_frontend:5173;`, `try_files $uri $uri/ /bteam/oliview/index.html;`, WS upgrade for Vite HMR |
| `/bteam/chata/(.*)` | `http://oliview_chatbot_a:8501/bteam/chata/$1` | HTTP/WS | `proxy_pass http://oliview_chatbot_a:8501;`, `Upgrade $http_upgrade`, `Connection "upgrade"`, `proxy_read_timeout 300s;` |
| `/bteam/chatb/(.*)` | `http://oliview_chatbot_b:8002/$1` | HTTP | `proxy_pass http://oliview_chatbot_b:8002/;`, `X-Forwarded-Prefix /bteam/chatb`, `proxy_read_timeout 300s;` |
| `/ateam/pilos/(.*)` | `http://pilos-web:5000/$1` | HTTP | `proxy_pass http://pilos-web:5000/;`, `X-Forwarded-Prefix /ateam/pilos`, `proxy_read_timeout 300s;` |

---

## 2. Standardized Proxy Headers Contract

All reverse-proxied requests MUST include the following headers transmitted to upstream containers:

```nginx
# Host & Origin Transparency
proxy_set_header Host $http_host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Port $server_port;

# Tracing Header
proxy_set_header X-Request-ID $request_id;

# WebSocket Protocol Upgrade
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;

# Streaming & Buffer Control
proxy_http_version 1.1;
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 300s;
proxy_send_timeout 300s;
```

---

## 3. Error Handling & Fallback Contracts

| Status Code | Scenario | Gateway Behavior |
|---|---|---|
| `502 Bad Gateway` | Upstream container cold-booting or restarting | Returns structured JSON or branded HTML: `{"error": "SERVICE_UNAVAILABLE", "message": "해당 AI 서비스가 준비 중이거나 초기화 중입니다. 잠시 후 다시 시도해주세요."}` |
| `504 Gateway Timeout` | Heavy LLM inference exceeding 300s | Returns `{"error": "GATEWAY_TIMEOUT", "message": "요청 처리 시간이 초과되었습니다."}` |
| `404 Not Found` | React SPA sub-route refresh | Intercepted by `try_files` to return SPA `index.html` for client-side routing. |
