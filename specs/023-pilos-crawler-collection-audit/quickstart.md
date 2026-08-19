# Quickstart & Verification Guide: A-Team Pilos 댓글 크롤러 정합성 복원

**Feature**: `023-pilos-crawler-collection-audit`
**Date**: 2026-08-20

---

## 1. Unit Test Verification

단위 테스트를 통해 비정형 작성자 댓글 및 대댓글 파싱 무결성을 검증합니다.

```bash
# 크롤러 파싱 및 비식별화 단위 테스트 실행
uv run python -m unittest discover -s ateam/pilos-sentiment-index/pilos/collection/test -p "test_*.py"
```

---

## 2. Catch-up Backfill Execution (18~19일 데이터 소급 수집)

10개 전 종목을 대상으로 2026-08-18 00:00(KST)까지 백필 수집을 실행합니다.

```bash
# 10개 전 종목 18일 하한 소급 백필 실행
docker compose exec pilos_worker python -m pilos.jobs.backfill_comments --until-date 2026-08-18 --target all
```

---

## 3. End-to-End Pipeline Cascade Execution

수집 완료 후 7단계 파이프라인(전처리 -> 토큰화 -> 일별문서 -> 수급 -> Ridge -> LLM 리포트)을 연쇄 구동합니다.

```bash
# 전체 서비스 파이프라인 1회 강제 실행
docker compose exec pilos_worker python -m pilos.jobs.run_service_pipeline
```

---

## 4. Verification Assertions (DB 데이터 정합성 확인)

MySQL 데이터베이스에서 18일 및 19일 댓글 수집량이 정상 복원되었는지 검증합니다.

```bash
# 날짜별 적재 건수 집계 쿼리
docker compose exec pilos_db mysql -upilos_user -ppilos_password pilos_v2 -e "
SELECT DATE(created_at) AS c_date, COUNT(*) AS cnt 
FROM preprocessed_comment 
WHERE created_at >= '2026-08-18' 
GROUP BY DATE(created_at) 
ORDER BY c_date DESC;
"
```

- **기대 결과**:
  - 2026-08-19: 35,000건 이상
  - 2026-08-18: 26,000건 이상
  - 결손 누락 종목(현대차, NAVER, 두산에너빌리티, 카카오 등)의 수집량이 원본 프로젝트 대비 정상 수준으로 완전 일치.
