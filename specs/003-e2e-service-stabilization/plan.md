# Implementation Plan: E2E 서비스 안정화 및 서브서비스 종합 점검 (003-e2e-service-stabilization)

**Branch**: `003-e2e-service-stabilization` | **Date**: 2026-08-17 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/003-e2e-service-stabilization/spec.md)

**Input**: Feature specification from `/specs/003-e2e-service-stabilization/spec.md`

---

## Summary

본 구현 계획은 AI 서비스 포털의 4대 핵심 서브시스템(A-Team Pilos, B-Team Oliview, 올리챗 Streamlit, 올원챗 FastAPI)에 존재하는 네비게이션 404, 모델 가중치 경로 오류, 브랜드 조회 누락, SMTP 이메일 인증 설정을 전면 정비하고, 단일 실행 가능한 자동화 E2E 종합 검증 스위트(`verify_e2e_services.ps1`)를 구축하여 시스템의 무결성을 확보합니다.

---

## Technical Context

**Language/Version**: Python 3.12 (백엔드, 모델 게이트웨이, 챗봇), JavaScript / Node.js 20+ (React SPA, Vite), Nginx 1.25+  
**Primary Dependencies**: Flask, FastAPI, Streamlit, PyMySQL, LangChain, ChromaDB, smtplib, httpx, React, Vite  
**Storage**: MySQL 8.0 (`pilos_v2`, `oliview_project`), ChromaDB (로컬 벡터 스토어)  
**Testing**: PowerShell E2E 자동화 스크립트 (`verify_e2e_services.ps1`), pytest (단위/통합 테스트)  
**Target Platform**: Linux Container (Docker Compose) / Host Bridge Network (`aiservice-network`)  
**Project Type**: Multi-Service Web Application & AI Model Serving Gateway  
**Performance Goals**:
- Pilos 종목 상세 조회 < 1.5초
- Oliview 3,062개 브랜드 로딩 < 1.0초
- 올리챗/올원챗 RAG LLM 응답 생성 < 10.0초
- 시스템 GPU VRAM 점유율 < 4.0GB 유지
**Constraints**:
- 무중단 서빙 및 기존 DB 볼륨/모델 가중치 비파괴 보존
- Gmail SMTP 포트 587 STARTTLS 보안 통신
- 서브경로(`/ateam/pilos/`, `/bteam/oliview/`, `/bteam/chata/`, `/bteam/chatb/`) 및 루트 경로 양방향 호환
**Scale/Scope**: 4개 서브도메인 서비스, 1개 공통 모델 게이트웨이, 1개 Nginx 게이트웨이, 3,062개 브랜드, 10개 주식 종목

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **I. 언어 및 커뮤니케이션 정책**: 모든 사용자 문서, 계획서, API 계약서 및 검증 가이드가 한국어로 작성됨.
- [x] **II. TDD 및 테스트 우선주의**: E2E 자동화 테스트 스위트(`verify_e2e_services.ps1`) 및 API 계약 명세를 선행 수립하여 구현 전/후 검증 체계 확립.
- [x] **III. 서비스 모듈화 및 격리**: A-Team, B-Team, Model Gateway, Ingress Nginx의 독립 컨테이너 환경 유지 및 기존 영속 DB 볼륨 파괴 방지.
- [x] **IV. 관측 가능성 및 구조화된 로깅**: Nginx JSON 접근 로그 및 백엔드 에러 스택트레이스 로깅, 민감정보(비밀번호/SMTP 토큰) 마스킹 보장.
- [x] **V. 단순성 및 점진적 진화 (YAGNI)**: 복잡한 별도 서비스 도입 없이 표준 환경변수 주입, REST API 일원화, Nginx 프록시 매핑을 통한 가장 간결한 해결책 채택.

---

## Project Structure

### Documentation (this feature)

```text
specs/003-e2e-service-stabilization/
├── spec.md                  # 명세서 (기능 요구사항, 사용자 시나리오, 성공 기준)
├── plan.md                  # 본 구현 계획서
├── research.md              # Phase 0 기술 결정 및 아키텍처 분석
├── data-model.md            # Phase 1 데이터 모델 및 DTO 정의
├── quickstart.md            # Phase 1 종합 실행 및 검증 가이드
├── contracts/               # Phase 1 인터페이스 계약
│   ├── pilos-api.md         # Pilos 웹/API 엔드포인트 계약
│   ├── oliview-backend-api.md # Oliview 백엔드/브랜드/SMTP API 계약
│   ├── oliview-chatb-api.md   # 올원챗 RAG 검색 API 계약
│   └── gateway-routing.md   # 게이트웨이 역방향 프록시 토폴로지
├── checklists/
│   └── requirements.md      # 명세 품질 체크리스트 (16/16 통과)
└── scripts/
    └── verify_e2e_services.ps1 # E2E 종합 자동화 검증 스크립트
```

### Source Code (repository root)

```text
ateam/
└── pilos-sentiment-index/
    └── pilos/web/
        └── static/js/
            ├── index.js      # [MODIFY] 동적 베이스 경로(/ateam/pilos) 자동 감지
            └── detail.js     # [MODIFY] 종목 상세 상대/절대 경로 동기화

bteam/
├── Oliview_Project/
│   └── backend/
│       └── app.py            # [MODIFY] GET /api/brands 구현, send-auth-code 400 에러 처리, TTL
├── Oliview_chatbot_a/
│   ├── 06.02.app.py          # [MODIFY] HttpBgeM3Embeddings 표준 호출 단일화
│   └── common/
│       └── embedding_client.py # [VERIFY] 원격 8090 임베딩 클라이언트 보장
└── Oliview_chatbot_b/
    └── project_ragapi.py     # [MODIFY] root_path 및 RAG 검색 폴백 강화

gateway/
└── nginx.conf                # [MODIFY] /stocks/, /about 라우팅 추가 및 서브경로 정렬

docker-compose.yml            # [MODIFY] oliview_backend SMTP 환경변수 통합 주입
.env.example                  # [MODIFY] SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD 표준화
```

**Structure Decision**: 기존 멀티 컨테이너 독립 구조를 완벽히 유지하면서 변경이 필요한 프론트엔드 라우팅, 백엔드 API 계약, Nginx 프록시 설정만을 최소 침습적으로 수정하는 점진적 안정화 구조를 채택함.

---

## Complexity Tracking

> **Constitution Check 위반 사항 없음 (No Violations)**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| 없음 | 해당 사항 없음 | 표준 아키텍처 및 YAGNI 원칙 100% 준수 |
