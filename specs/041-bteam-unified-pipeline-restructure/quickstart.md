# Quickstart: Oliview B-Team 통합 파이프라인 및 서비스 실행 가이드

**Feature**: `041-bteam-unified-pipeline-restructure`  
**Date**: 2026-08-26  

---

## 1. 전주기 데이터 파이프라인 CLI 실행 (`pipeline_runner.py`)

### 전체 E2E 파이프라인 원클릭 실행 (크롤링 -> 문장분리 -> 감성분석 -> 보고서 -> 벡터인덱싱)
```bash
cd c:\AISERVICE\bteam
uv run python pipelines/pipeline_runner.py --steps all
```

### 특정 단계별 독립 실행
```bash
# 1. 크롤링만 실행
uv run python pipelines/pipeline_runner.py --steps crawl

# 2. 문장 분리 & 감성 분석만 실행
uv run python pipelines/pipeline_runner.py --steps split,sentiment

# 3. LLM 개선 제안 보고서 생성만 실행
uv run python pipelines/pipeline_runner.py --steps report

# 4. ChromaDB 증분 벡터 인덱싱만 실행
uv run python pipelines/pipeline_runner.py --steps index
```

---

## 2. 통합 도커 서비스 기동 및 상태 확인

```bash
cd c:\AISERVICE\bteam

# 1. 도커 컨테이너 일괄 빌드 및 백그라운드 구동
docker compose up -d --build

# 2. 컨테이너 헬스체크 확인
docker compose ps
```

---

## 3. 웹 서비스 및 게이트웨이 접속 확인

- **메인 프론트엔드 대시보드**: `https://ezenitac.duckdns.org/bteam/oliview/`
- **백엔드 REST API**: `https://ezenitac.duckdns.org/bteam/oliview/api/health`
- **ChatA (Streamlit)**: `https://ezenitac.duckdns.org/bteam/chata/`
- **ChatB (FastAPI)**: `https://ezenitac.duckdns.org/bteam/chatb/`
