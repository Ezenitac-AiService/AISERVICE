# Quickstart & Verification Guide: A-Team 컨테이너 환경

## 1. 사전 요구사항 (Prerequisites)

* Windows 11 호스트 머신에 **WSL2** 및 **Rancher Desktop**(Docker CLI / Compose 활성화 상태)이 실행 중이어야 합니다.
* 루트 디렉터리에 2.69GB DB 덤프 파일(`pilos_v2.sql`)이 위치해야 합니다.
* LLM 컨테이너가 동일 머신 또는 접근 가능한 컨테이너 환경에 구동 중이어야 합니다.

---

## 2. 단계별 실행 절차 (Step-by-Step Guide)

### 1단계: 공유 Docker 브리지 네트워크 생성

A-Team, B-Team 및 LLM 컨테이너가 공통으로 상호 작용할 수 있도록 외부 네트워크를 생성합니다.

```powershell
docker network create aiservice-network
```

### 2단계: 환경 설정 파일 준비

`pilos-sentiment-index/.env.example`을 복사하여 `.env`를 생성하고 내부 엔드포인트를 설정합니다.

```powershell
Copy-Item pilos-sentiment-index\.env.example pilos-sentiment-index\.env
```

`.env` 파일 내 주요 설정 확인:
* `WEB_PORT=8080` (A-Team 웹 포트)
* `DB_PORT=3307` (A-Team MySQL 포트)
* `DB_HOST=db` (컨테이너 간 내부 접속 호스트)
* `LLM_BASE_URL=http://llm-server:8000/v1`

### 3단계: DBMS 컨테이너 기동 및 1회성 덤프 적재

MySQL 컨테이너를 먼저 기동한 후 `pilos_v2.sql`을 안전하게 복원합니다.

```powershell
# 1. DB 서비스 기동
docker compose up -d db

# 2. DB 기동 및 초기 헬스체크 대기 (약 10~20초)
docker compose ps

# 3. 2.69GB 덤프 파일 스트리밍 복원 (1회성 수행)
docker exec -i pilos-db mysql -uroot -ppilos_root_pass pilos_v2 < pilos_v2.sql
```

### 4단계: Web 서비스 빌드 및 전체 컨테이너 구동

웹 애플리케이션 이미지를 빌드하고 전체 서비스를 실행합니다.

```powershell
# 이미지 빌드 및 컨테이너 백그라운드 기동
docker compose up -d --build
```

---

## 3. 검증 시나리오 (Verification Scenarios)

### 시나리오 1: 웹 서비스 및 대시보드 렌더링 검증 (SC-002)

브라우저 또는 curl을 통해 A-Team 전용 포트(`8080`)로 서비스가 정상 응답하는지 확인합니다.

```powershell
# HTTP 상태 코드 200 확인
curl -I http://localhost:8080/
```

* **기대 결과**: HTTP 200 OK 응답 및 메인 페이지 렌더링.

### 시나리오 2: 마이그레이션된 DB 데이터 조회 검증 (SC-001)

복원된 주식 감성 분석 데이터가 웹 API를 통해 정상 반환되는지 확인합니다.

```powershell
curl -s http://localhost:8080/api/stocks | Select-String -Pattern "stock_code"
```

* **기대 결과**: 마이그레이션된 주식 종목 리스트와 감성 지수 데이터 JSON 정상 반환.

### 시나리오 3: LLM 컨테이너 연동 챗봇 질의 검증 (SC-004)

공통 네트워크를 통한 LLM 질의 응답을 확인합니다.

```powershell
curl -X POST http://localhost:8080/api/chat `
  -H "Content-Type: application/json" `
  -d '{"message": "삼성전자 최근 감성 지수 어때?", "session_id": "test_session"}'
```

* **기대 결과**: LLM 컨테이너로부터 분석된 답변이 포함된 정상 JSON 반환.

### 시나리오 4: B-Team과의 포트 충돌 여부 확인 (SC-003)

B-Team 서비스(예: `80` 또는 `5000`)와 A-Team 서비스(`8080`)가 독립적으로 바인딩되었는지 확인합니다.

```powershell
netstat -ano | findstr "8080"
netstat -ano | findstr "3307"
```

* **기대 결과**: `0.0.0.0:8080` 및 `0.0.0.0:3307`이 충돌 없이 LISTENING 상태.
