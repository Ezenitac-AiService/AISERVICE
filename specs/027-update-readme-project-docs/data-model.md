# Data Model & Documentation Structure: 027-update-readme-project-docs

## 1. Documentation File Tree Structure

```text
c:/AISERVICE/
├── README.md                  # [메인] 총괄 포털 (개요, 아키텍처 다이어그램, 서비스 맵, 퀵스타트, 목차링크, MIT)
├── LICENSE                    # [라이센스] MIT License 전문
└── docs/                      # [상세 기술문서 디렉토리]
    ├── architecture.md        # 전체 인프라, 네트워크 격리, K8s Ingress / Traefik / Nginx 게이트웨이
    ├── model_gateway.md       # vLLM/llama.cpp 서빙, 2B 상주 체제, SINGLE_MODEL_MODE, 16K ctx, VRAM 실측
    ├── bteam_oliview.md       # Oliview React/Flask 플랫폼, 챗봇 A(Streamlit), 챗봇 B(FastAPI RAG)
    ├── ateam_pilos.md         # Pilos 주식 수급 감정분석, 7단계 배치 워커 데몬, 대시보드
    └── security_guardrails.md # 4단계 CPU 보안 가드레일, 3단계 하이브리드 토큰 예산 정책
```

---

## 2. Document Schema & Mandatory Section Specifications

### A. Main `README.md` Schema
1. **Title & Executive Summary**: 프로젝트 한 줄 정의 및 가치
2. **Architecture Diagram**: 통합 시스템 및 네트워크 흐름도 (ASCII / Mermaid)
3. **Public Service Routing Map**: 4대 서비스 바로가기 링크 및 기술 스택 테이블
4. **Quickstart Guide**: Windows / Linux 원클릭 기동 명령어
5. **Detailed Documentation TOC**: `docs/*.md` 5대 상세 문서 목차 및 상대 경로 링크
6. **License**: MIT License 고지

### B. Sub-documents (`docs/*.md`) Schema
- **Title & Overview**: 해당 서브 도메인의 역할과 목적
- **Architecture & Component Diagram**: 서브 도메인 내부 컴포넌트 구조
- **Key Features & Workflows**: 핵심 기능, API 명세 및 처리 흐름
- **Configuration & Environment Variables**: 관련 `.env` 환경변수 목록
- **Troubleshooting & Operations**: 장애 대응 및 검증 방법
