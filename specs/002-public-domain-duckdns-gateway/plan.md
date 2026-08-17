# Implementation Plan: 공인 DDNS HTTPS(`https://ezenitac.duckdns.org`) 및 8080 게이트웨이 연동, 내부 백엔드·DB·LLM 연결 정상화 및 A-Team 파이프라인 워커 활성화

**Branch**: `002-public-domain-duckdns-gateway` | **Date**: 2026-08-17 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/002-public-domain-duckdns-gateway/spec.md)

**Input**: Feature specification from `/specs/002-public-domain-duckdns-gateway/spec.md`

---

## Summary

공인 DDNS HTTPS 도메인(`https://ezenitac.duckdns.org`, Let's Encrypt 자동 발급) 및 Traefik Ingress / Nginx 게이트웨이를 기반으로 통합 AI 플랫폼의 4대 서브 서비스를 안전하게 외부에 노출하고, 내부 백엔드·데이터베이스(`cosmetic_db`, `pilos_v2`)·추론 엔진(`vllm-serv-gateway:8081/8090/8091`) 간의 통신 장애를 전면 해소합니다. B-Team 챗봇의 로컬 가중치 의존성을 HTTP 임베딩 API 원격 호출로 리팩토링하고, A-Team의 7단계 수집·분석 파이프라인을 전용 워커(`pilos_worker`) 컨테이너로 상시 스케줄링하여 대시보드 상태 동기화를 완결합니다.

---

## Technical Context

**Language/Version**: Python 3.12 (A-Team, B-Team 백엔드/챗봇, Model Gateway), TypeScript/JavaScript (React Vite 프론트엔드), SQL (MySQL 8.0)  
**Primary Dependencies**: Traefik Ingress (K3s, Let's Encrypt), Nginx 1.25+, Docker Compose v2, FastAPI, Flask, Streamlit, SQLAlchemy, PyMySQL, Kiwi-NLP, ChromaDB, llama-server/vLLM  
**Storage**: MySQL 8.0 (`cosmetic_db`, `pilos_v2`), 영속 Docker Volumes (`bteam_mysql_data`, `ateam_db_data`), Chroma Vector DB  
**Testing**: pytest, curl/httpx 통합 엔드포인트 검증, PowerShell 포트 격리 검증 (`Test-NetConnection`), Docker/K3s Healthcheck  
**Target Platform**: Linux Container on WSL2 / Windows 11 Docker Host + K3s Ingress, 공인 인터넷망 (SK broadband 유동 IP + DuckDNS + Let's Encrypt HTTPS)  
**Project Type**: Multi-service Microservices Orchestration (Ingress + Gateway + Web Apps + DBs + ML Serving + Worker Daemon)  
**Performance Goals**: 통합 포털 HTTPS 로딩 <3초, 챗봇 첫 스트리밍 토큰 <5초, 4096 토큰 완결 응답, 파이프라인 주기 실행 <120초  
**Constraints**: HTTPS 443 표준 포트 및 80 ➔ 301 자동 리다이렉트, 8080 대체 포트 지원, 외부 공인망으로부터 DB(3306/3307) 및 LLM(8081/8090) 100% 격리, 대용량 DB(2.69GB) 적재 헬스체크 300초 보장  
**Scale/Scope**: 총 10개 컨테이너 서비스 오케스트레이션 및 4개 서브도메인 웹/API 연동  

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I. 언어 및 커뮤니케이션 정책**: 모든 대화, 명세서, 계획서, 주석, 산출물 한국어 작성 준수 (PASS)
- **Principle II. TDD 및 테스트 우선주의**: E2E 시나리오 및 단위/통합 계약 검증 절차 수립 (PASS)
- **Principle III. 서비스 모듈화 및 격리**: 10개 컨테이너 간 사설 네트워크(`aiservice-network`) 분리 및 독립 실행 구조 보장 (PASS)
- **Principle IV. 관측 가능성 및 구조화된 로깅**: Nginx JSON 액세스 로그, 파이프라인 실행 상태 DB(`service_pipeline_run`) 기록 (PASS)
- **Principle V. 단순성 및 점진적 진화 (YAGNI)**: HTTPS 인증서(Traefik ACME) 인프라를 활용하여 Nginx 설정 단순화 유지 (PASS)

---

## Project Structure

### Documentation (this feature)

```text
specs/002-public-domain-duckdns-gateway/
├── plan.md              # 본 계획서 (/speckit-plan 결과물)
├── research.md          # 기술 의사결정 및 대안 분석 (/speckit-plan 결과물)
├── data-model.md        # 데이터 모델 및 DTO 스펙 (/speckit-plan 결과물)
├── quickstart.md        # 배포 및 E2E 검증 가이드 (/speckit-plan 결과물)
├── contracts/           # 인터페이스 계약 규격
│   ├── gateway_routing.md
│   ├── model_gateway_api.md
│   └── pilos_worker_api.md
└── tasks.md             # 작업 분해 목록 (/speckit-tasks 생성 대상)
```

### Source Code (repository root)

```text
.
├── docker-compose.yml                     # 10대 서비스 통합 오케스트레이션
├── run_all_services.bat                   # Windows 통합 제어기
├── run_all_services.sh                    # Linux/WSL 통합 제어기
├── ddns/
│   ├── ingress-ezenitac.yaml              # Kubernetes HTTPS Ingress & gateway-svc
│   └── traefik-acme-config.yaml           # Let's Encrypt ACME 설정
├── gateway/                               # aiservice-gateway
│   ├── Dockerfile
│   ├── nginx.conf                         # 80/8080 듀얼 바인딩 및 서브경로 라우팅
│   └── html/index.html                    # 통합 포털 단일 진입 랜딩
├── model_gateway/                         # vllm-serv-gateway
│   ├── src/api/server.py                  # LLM(8081) & Embedding(8090) & Reranker(8091)
│   └── models/                            # bge-m3, qwen3.5-4b 등
├── bteam/                                 # B-Team 뷰티 AI 도메인
│   ├── oliview_project_backup_0813.sql    # 1.26GB DB 백업
│   ├── Oliview_Project/
│   │   ├── backend/                       # oliview_backend (Flask 5050)
│   │   └── frontend/                      # oliview_frontend (Vite React 5173)
│   ├── Oliview_chatbot_a/                 # oliview_chatbot_a (Streamlit 8501)
│   │   ├── common/embedding_client.py     # HTTP Embedding Client (BGE-M3 8090)
│   │   └── 06.app.py                      # 챗봇 진입점
│   └── Oliview_chatbot_b/                 # oliview_chatbot_b (FastAPI 8002)
│       ├── index.html                     # API URL 게이트웨이 정규화 (/bteam/chatb/api/v1/search)
│       └── project_ragapi.py              # FastAPI RAG 엔드포인트
└── ateam/                                 # A-Team 주식 수급 감정 지수 도메인
    ├── pilos_v2.sql                       # 2.69GB DB 덤프
    └── pilos-sentiment-index/
        ├── Dockerfile                     # pilos-web 및 pilos-worker 베이스
        └── pilos/
            ├── storage/db.py              # MySQL 커넥션 풀 관리
            ├── jobs/
            │   ├── run_service_pipeline.py# 7단계 순차 파이프라인
            │   └── worker_daemon.py       # 주기적 스케줄러 데몬
            └── web/app.py                 # Flask 대시보드 및 /api/pipeline/status
```
