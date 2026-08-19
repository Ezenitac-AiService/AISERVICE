# Quickstart & Validation Guide: Pilos 일별 문서 증분 집계 및 보고서 자동 갱신 동기화

## 1. 사전 조건 (Prerequisites)
- Docker 컨테이너 실행 중 (`pilos-db`, `pilos-worker`, `vllm-serv-gateway`, `pilos-web`)
- MySQL 데이터베이스에 8월 19일 및 8월 20일치 `preprocessed_comment` 적재 상태

---

## 2. 수동 검증 절차 (Manual Verification Steps)

### Step 1: 대상 판정 쿼리 단위 테스트 실행
```bash
docker exec pilos-worker python -m unittest tests/test_daily_document_db.py
```
- **기대 결과**: 미매핑 토큰이 존재하는 종목·날짜가 정상적으로 pending targets로 조회됨.

### Step 2: 일별 문서 빌드 및 파이프라인 1회 수동 실행
```bash
docker exec pilos-worker python -m pilos.jobs.run_service_pipeline --target all
```
- **기대 결과**:
  1. `daily_document` 단계에서 8월 19일 및 8월 20일 대상 문서들이 성공적으로 빌드됨.
  2. `model_inference` 단계에서 최신 스냅샷에 대해 Ridge 감성 추론 완료.
  3. `llm_report` 단계에서 최신 지표 기반 보고서 갱신 완료.
  4. 전체 상태 `status=completed` 출력.

### Step 3: MySQL 데이터베이스 적재 수치 확인
```bash
docker exec pilos-db mysql --default-character-set=utf8mb4 -upilos_user -ppilos_password pilos_v2 -e "
SELECT s.stock_name, d.model_date, d.comment_count, d.created_at
FROM daily_document d
JOIN stock s ON d.stock_id = s.stock_id
WHERE d.model_date >= '2026-08-19'
ORDER BY d.model_date DESC, d.stock_id ASC;
"
```
- **기대 결과**: SK하이닉스 10,000+건, 삼성전자 6,900+건 등 장 마감 전 전체 수집 댓글 수치로 갱신된 스냅샷 확인.

### Step 4: 웹 대시보드 UI 확인
- 브라우저에서 `http://ezenitac.duckdns.org/ateam/pilos/` 접속.
- 각 종목 카드의 최신 적재 정보에 실제 누적 댓글 수와 분석 상태가 정확히 표시되는지 확인.
