# Quickstart Guide: 통합 시스템 아키텍처 검증 가이드 (010-refactor-unified-system-architecture)

---

## 1. 개요
본 가이드는 AISERVICE 3대 챗봇(PILOS, 올리챗, 올원챗), 공용 모델 게이트웨이, 및 Nginx 통합 역방향 프록시가 요구사항(FR-001 ~ FR-008, SC-001 ~ SC-005)에 따라 정상 동작하는지 종단간(End-to-End) 검증하는 실행 절차를 제공한다.

---

## 2. 사전 준비 (Prerequisites)

- Docker 및 Docker Compose 구동 환경
- Python 3.10+ (단위/통합 테스트 실행용)
- 단일 GPU (NVIDIA GTX 1070 8GB VRAM) 또는 CPU 폴백 지원 환경

---

## 3. 서비스 실행 및 헬스체크 (Start & Healthcheck)

### 3.1 전체 컨테이너 기동
```bash
# 통합 docker-compose 기동
docker compose up -d
```

### 3.2 핵심 컨테이너 상태 점검
```bash
docker compose ps
```
- `aiservice-gateway` (Port 80, 8080) - `Up`
- `vllm-serv-gateway` (Port 8081, 8090, 8091) - `Up`
- `bteam_db`, `pilos-db` - `Up (healthy)`
- `pilos-web`, `pilos-worker` - `Up`
- `oliview_backend`, `oliview_frontend`, `oliview_chatbot_a`, `oliview_chatbot_b` - `Up`

---

## 4. 통합 자동화 회귀 테스트 실행 (Regression Suite)

표준 파이썬 테스트 러너를 사용하여 전체 챗봇 격리 및 지연 시간 회귀 테스트를 수행한다.

```bash
python tests/test_multi_chatbot_regression.py
```

### 기대 결과 (Expected Outcomes)
- `test_01_embedding_gateway_endpoint`: BGE-M3 1024차원 임베딩 응답 (< 5.0s) `[PASS]`
- `test_02_pilos_chatbot_cache_speed`: PILOS 정본 지식 캐시 초고속 응답 (< 500ms) `[PASS]`
- `test_03_allonechat_rag_api_endpoint`: 올원챗 200 OK 및 추천 솔루션 반환 `[PASS]`
- `test_04_ollychat_web_portal_health`: 올리챗 Streamlit 웹 포털 200 OK `[PASS]`
- `test_05_multi_chatbot_concurrency_isolation`: 동시 질의 시 핫스왑 없이 전 요청 200 OK `[PASS]`

---

## 5. 수동 UI 및 엔드포인트 검증 (Manual Verification)

1. **통합 포털 랜딩 페이지**: `http://localhost:8080/` 접속 확인
2. **PILOS 대시보드 및 챗봇**: `http://localhost:8080/ateam/pilos/` 접속 후 질문 전송
3. **올리챗 뷰티 분석 챗봇**: `http://localhost:8080/bteam/chata/` 접속 후 리뷰 질의
4. **올원챗 맞춤 추천 챗봇**: `http://localhost:8080/bteam/chatb/` 접속 후 질의
5. **Oliview 메인 웹 대시보드**: `http://localhost:8080/bteam/oliview/` 접속 및 상품 클릭 상세 리포트 확인

---

## 6. 관련 문서 링크
- [데이터 모델 (`data-model.md`)](file:///c:/AISERVICE/specs/010-refactor-unified-system-architecture/data-model.md)
- [모델 게이트웨이 계약서 (`model-gateway-contract.md`)](file:///c:/AISERVICE/specs/010-refactor-unified-system-architecture/contracts/model-gateway-contract.md)
- [Nginx 라우팅 계약서 (`ingress-routing-contract.md`)](file:///c:/AISERVICE/specs/010-refactor-unified-system-architecture/contracts/ingress-routing-contract.md)
- [3대 챗봇 API 계약서 (`chatbot-api-contracts.md`)](file:///c:/AISERVICE/specs/010-refactor-unified-system-architecture/contracts/chatbot-api-contracts.md)
- [Oliview 프론트엔드 API 계약서 (`oliview-frontend-contract.md`)](file:///c:/AISERVICE/specs/010-refactor-unified-system-architecture/contracts/oliview-frontend-contract.md)
