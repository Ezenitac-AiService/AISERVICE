# AISERVICE: 통합 AI 서비스 공인 HTTPS 단일 진입 게이트웨이 및 보안 격리 플랫폼

> A-Team 및 B-Team의 데이터 분석 대시보드, 자동화 수집·분석 워커, 대화형 AI 챗봇 서비스를 공인 DDNS HTTPS 도메인(`https://ezenitac.duckdns.org`, Let's Encrypt 자동 발급) 및 단일 사설 도커 네트워크(`aiservice-network`)로 통합한 AI 서비스 플랫폼입니다.

---

## 🏛️ 통합 아키텍처 개요

```
                       [ 외부 공인 클라이언트 (인터넷) ]
                                      │
              ┌───────────────────────┴───────────────────────┐
              │ (HTTP 80 ➔ 301 자동 전환)                      │ (HTTPS 443 SSL/TLS)
              ▼                                               ▼
    ┌───────────────────┐                           ┌───────────────────┐
    │  Traefik (HTTP)   │                           │  Traefik (HTTPS)  │
    └─────────┬─────────┘                           └─────────┬─────────┘
              └─────────────────────► ◄───────────────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │ gateway-svc (K8s Ingress) │
                        └─────────────┬─────────────┘
                                      │ (Port 8080)
                                      ▼
                  ┌───────────────────────────────────────────┐
                  │       aiservice-gateway (Nginx 1.25)      │
                  └─────┬──────────────┬──────────────┬───────┘
                        │              │              │
         ┌──────────────┴───┐          │          ┌───┴──────────────┐
         │  B-Team Services │          │          │  A-Team Services │
         ├──────────────────┤          │          ├──────────────────┤
         │ oliview_frontend │          │          │ pilos-web        │
         │ oliview_backend  │          │          │ pilos-worker     │
         │ oliview_chatbot_a│          │          │ pilos-db (MySQL) │
         │ oliview_chatbot_b│          │          └──────────────────┘
         │ bteam_db (MySQL) │          │
         └──────────────┬───┘          │
                        │              ▼
                        │   ┌────────────────────────────────┐
                        └──►│ vllm-serv-gateway (vLLM Engine)│
                            │ - Resident LLM: qwen3.5-4b     │
                            │ - Embedding: bge-m3 (8090)     │
                            │ - Reranker: bge-reranker (8091)│
                            └────────────────────────────────┘
                            [ 내부 aiservice-network 격리 ]
```

---

## 🌐 단일 진입 URL 라우팅 맵

| 서비스 명 | 서브 URL 경로 | 백엔드 기술 스택 | 설명 |
|---|---|---|---|
| **통합 포털 랜딩** | `https://ezenitac.duckdns.org/` | Nginx Static HTML/CSS | 4대 AI 서비스 바로가기 카드 대시보드 |
| **B-Team Oliview** | `https://ezenitac.duckdns.org/bteam/oliview` | React Vite + Flask/Gunicorn | 화장품 리뷰 감정 분석 & 대시보드 |
| **B-Team 올리챗** | `https://ezenitac.duckdns.org/bteam/chata` | Streamlit + HTTP BGE-M3 | 실시간 뷰티 상담 챗봇 |
| **B-Team 올원챗** | `https://ezenitac.duckdns.org/bteam/chatb` | FastAPI / Uvicorn + RAG | 하이브리드 RAG 질의응답 챗봇 |
| **A-Team Pilos** | `https://ezenitac.duckdns.org/ateam/pilos` | Flask / Gunicorn | 주식 감정지수 분석 & 내장 챗봇 |
| **A-Team Worker** | *(Internal Daemon)* | Python Background Scheduler | 7단계 수집·분석·LLM 리포트 주기 실행 |

---

## 🚀 빠른 시작 (Quickstart)

### 1. 환경 설정 파일 준비
```bash
cp .env.example .env
```

### 2. 전체 시스템 원클릭 기동 (10개 마이크로서비스)

- **Windows 환경**:
  ```cmd
  run_all_services.bat up
  ```

- **Linux / WSL 환경**:
  ```bash
  chmod +x run_all_services.sh
  ./run_all_services.sh up
  ```

- **A-Team 파이프라인 즉시 수동 트리거**:
  ```bash
  docker exec -it pilos-worker python -m pilos.jobs.run_service_pipeline
  ```

---

## 🛡️ 핵심 보안 및 운영 가드레일

1. **Let's Encrypt HTTPS (443) 및 80 ➔ 301 자동 리다이렉트**:
   - Traefik ACME를 통해 인증서 자동 갱신 및 모든 웹 트래픽 암호화 전송을 보장합니다.
2. **사설 인프라 포트 100% 외부 차단**:
   - MySQL DBMS (3306) 및 vLLM 서빙 게이트웨이 (8081, 8090, 8091)는 내부 도커 브리지에만 바인딩되어 외부 공격을 원천 방어합니다.
3. **HTTP Embedding 원격 통합**:
   - 컨테이너별 무거운 가중치 직접 로딩을 제거하고 `vllm-serv-gateway:8090`의 BGE-M3 HTTP API로 일원화했습니다.
4. **대용량 DB 자동 초기화 & 헬스체크**:
   - `pilos_v2.sql` (2.69GB) 및 `oliview_project_backup_0813.sql` (1.26GB) 덤프의 무결 복원 완료 후 웹 백엔드가 안전하게 기동됩니다.
