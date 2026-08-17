# Quickstart & Verification Guide: 공인 DDNS HTTPS(`https://ezenitac.duckdns.org`) 및 통합 AI 마이크로서비스

**Feature Branch**: `002-public-domain-duckdns-gateway`  
**Date**: 2026-08-17  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/002-public-domain-duckdns-gateway/spec.md)

---

## 1. 사전 준비 및 환경 구성 (Prerequisites)

1. **도커 & K3s 환경 활성화**: Docker Desktop / WSL2 및 Kubernetes(K3s) Ingress Traefik 가동 확인
2. **환경 변수 파일 점검**:
   - 루트 `.env` 파일 존재 확인 (`copy .env.example .env`)
   - `BTEAM_DB_NAME=cosmetic_db`, `PILOS_DB_NAME=pilos_v2`
3. **대용량 DB 덤프 파일 확인**:
   - `ateam/pilos_v2.sql` (2.69GB)
   - `bteam/oliview_project_backup_0813.sql` (1.26GB)

---

## 2. 통합 서비스 일괄 기동 (Start All Services)

```powershell
# Windows PowerShell - Docker Compose 기동
.\run_all_services.bat up

# Kubernetes Ingress 및 gateway-svc 배포
kubectl apply -f ddns/ingress-ezenitac.yaml
```

### 기동 상태 확인
```powershell
docker compose ps
kubectl get ingress,svc -n default
```
총 10개 컨테이너가 `Up (healthy)` 상태이며, `ezenitac-ingress`가 200 OK 라우팅을 제공하는지 확인합니다.

---

## 3. 기능 검증 시나리오 (End-to-End Validation)

### 시나리오 1: 공인 HTTPS 포털 및 서브 서비스 접속 검증
1. 브라우저에서 `https://ezenitac.duckdns.org/` 접속 ➔ Let's Encrypt SSL 인증서와 함께 통합 포털 카드가 200 OK 렌더링되는지 확인
2. 브라우저에서 `http://ezenitac.duckdns.org/` (80 포트) 접속 ➔ `https://ezenitac.duckdns.org/`로 301 자동 리다이렉트 확인
3. 각 카드 클릭 시 `/bteam/oliview`, `/bteam/chata`, `/bteam/chatb`, `/ateam/pilos`로 정상 이동하는지 확인

### 시나리오 2: B-Team 올리챗(chata) 및 올원챗(chatb) HTTPS RAG 정상화 검증
1. `https://ezenitac.duckdns.org/bteam/chata` 접속 후 "진정 토너 추천해줘" 질의 전송 ➔ WSS 웹소켓 스트리밍 및 `vllm-serv-gateway:8090` 임베딩, 8081 LLM 답변 정상 출력 확인 (FileNotFoundError 해결)
2. `https://ezenitac.duckdns.org/bteam/chatb` 접속 후 "순한 쿠션팩트 추천" 질의 전송 ➔ `/bteam/chatb/api/v1/search` 200 OK 수신 및 맞춤 솔루션 카드 렌더링 확인 (404 오류 해결)

### 시나리오 3: A-Team Pilos 대시보드 및 파이프라인 워커 상태 검증
1. `https://ezenitac.duckdns.org/ateam/pilos` 접속
2. 상단 "서비스 데이터 갱신 상태" 카드가 `running` 또는 `completed`로 표시되고 세부 단계별 소요 시간이 노출되는지 확인 ("DB 실행 상태를 불러오지 못했습니다" 오류 해결)
3. 주식 종목 카드 목록이 `pilos_v2` DB로부터 정상 렌더링되는지 확인

### 시나리오 4: 수동 파이프라인 즉시 트리거 검증
```powershell
docker exec pilos-worker python -m pilos.jobs.run_service_pipeline
```
로그 출력과 함께 7단계가 완료되고 대시보드 상태가 갱신되는지 확인.

---

## 4. 보안 격리 검증 (Security Verification)

```powershell
# 외부 공인 IP/도메인에서 사설 DB 및 추론 포트 차단 검증
Test-NetConnection -ComputerName ezenitac.duckdns.org -Port 3306 # TcpTestSucceeded: False
Test-NetConnection -ComputerName ezenitac.duckdns.org -Port 8081 # TcpTestSucceeded: False
Test-NetConnection -ComputerName ezenitac.duckdns.org -Port 8090 # TcpTestSucceeded: False
```
