# Quickstart Validation Guide: E2E 서비스 안정화 및 서브서비스 종합 점검 (003-e2e-service-stabilization)

**Feature Branch**: `003-e2e-service-stabilization`  
**Created**: 2026-08-17  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/003-e2e-service-stabilization/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/003-e2e-service-stabilization/plan.md)

---

## 1. 사전 준비 (Prerequisites)

- Docker & Docker Compose 환경 구동 (WSL2 / Linux / Windows)
- 루트 `.env` 파일에 SMTP 설정 확인 (`SMTP_USER`, `SMTP_PASSWORD`)
- `vllm-serv-gateway` (8081, 8090, 8091), `pilos-web` (5000), `oliview_backend` (5050), `oliview_frontend` (5173), `oliview_chatbot_a` (8501), `oliview_chatbot_b` (8002), `gateway` (8080) 컨테이너 기동 상태

```powershell
# 서비스 전체 기동
docker compose up -d
```

---

## 2. E2E 종합 자동화 검증 스크립트 실행

단일 스크립트 실행으로 5개 서비스(랜딩, Pilos, Oliview, 올리챗, 올원챗)의 정상 동작을 일괄 진단합니다.

### 1) 기본 검증 (공인 도메인 대상: https://ezenitac.duckdns.org)
```powershell
powershell -ExecutionPolicy Bypass -File specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1
```

### 2) 로컬 검증 (Docker 포트 대상: http://localhost:8080)
```powershell
powershell -ExecutionPolicy Bypass -File specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1 -Mode Local
```

---

## 3. 개별 시나리오별 수동 검증 단계

### 시나리오 1: Pilos 종목 클릭 및 리포트 조회
1. 브라우저에서 `https://ezenitac.duckdns.org/ateam/pilos/` 접속.
2. 메인 화면에서 삼성전자(`005930`) 카드 클릭.
3. 404 오류 없이 `/stocks/005930` 또는 `/ateam/pilos/stocks/005930` 화면이 로드되고 과거 감성 지수 차트가 표시되는지 확인.
4. 종목 리포트 챗봇 블록에서 최신 분석 보고서가 정상 출력되는지 확인.

### 시나리오 2: Oliview 로그인 및 브랜드 검색
1. 브라우저에서 `https://ezenitac.duckdns.org/bteam/oliview/login` 접속.
2. 브랜드 선택 모달에서 "구달" 입력 후 검색 시 브랜드 코드 및 고유 번호가 즉시 조회되는지 확인 (`GET /bteam/oliview/api/brands?keyword=구달`).
3. 3,062개 전체 브랜드가 누락 없이 반환되는지 확인 (`GET /bteam/oliview/api/brands`).

### 시나리오 3: 올리챗 (ChatA) LLM & BGE-M3 연동
1. 브라우저에서 `https://ezenitac.duckdns.org/bteam/chata/` 접속.
2. 채팅창에 "컬러그램 탕후루 탱글 꿀로스의 발림성 장단점을 분석해줘" 입력.
3. `FileNotFoundError` 없이 원격 임베딩(8090) 및 Qwen LLM(8081) 분석 답변이 정상 생성되는지 확인.

### 시나리오 4: 올원챗 (ChatB) 정적 웹 및 RAG 검색
1. 브라우저에서 `https://ezenitac.duckdns.org/bteam/chatb/` 접속.
2. 404 에러 없이 올원챗 웹 인터페이스가 렌더링되는지 확인.
3. 검색창에 "건성 피부 보습 앰플" 입력 후 검색 결과 및 AI 요약 답변이 표시되는지 확인.

### 시나리오 5: Oliview 회원가입 이메일 인증 발송
1. 브라우저에서 `https://ezenitac.duckdns.org/bteam/oliview/register` 접속.
2. 담당자 이메일 입력 후 "인증번호 발송" 클릭 시 3초 이내에 200 OK 응답 및 실제 Gmail 인증 메일이 발송되는지 확인.
