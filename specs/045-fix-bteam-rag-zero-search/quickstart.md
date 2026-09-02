# Quickstart & E2E Verification Guide: Oliview B-Team RAG 복구 검증 (Feature 045)

**Feature Branch**: `045-fix-bteam-rag-zero-search`
**Date**: 2026-09-02
**Status**: Completed

## 1. 사전 요구사항 (Prerequisites)

- Docker 및 NVIDIA GPU 컨테이너 가동 상태 (`docker ps`)
- 모델 게이트웨이 컨테이너 (`vllm-serv-gateway`) 가동 중
- Oliview 챗봇 A 컨테이너 (`oliview_chatbot_a`), 챗봇 B 컨테이너 (`oliview_chatbot_b`), MySQL DB (`bteam_db`) 가동 중

---

## 2. 검증 시나리오 1: MySQL DB 메타데이터 조회 검증

```bash
docker exec oliview_chatbot_a python -c "
from oliview_core.db import fetch_review_metadata
meta = fetch_review_metadata([1, 2, 3, 4, 5])
print('Metadata count:', len(meta))
assert len(meta) > 0, 'Metadata fetch failed!'
print('Sample item:', list(meta.values())[0])
"
```
**기대 결과**: SQL 에러 없이 `Metadata count > 0` 정상 반환.

---

## 3. 검증 시나리오 2: 리랭커 `None` 반환 시 안전 Fallback 검증

```bash
docker exec oliview_chatbot_a python -c "
from oliview_core.rerank import BGEReranker
reranker = BGEReranker()
idx, scores, fb = reranker.rerank('테스트 질문', ['문서 1', '문서 2'], top_k=2)
print('Ranked indices:', idx)
print('Scores:', scores)
print('Fallback used:', fb)
assert len(idx) == 2, 'Fallback ranking failed!'
"
```
**기대 결과**: `TypeError` 크래시 없이 `Fallback used: True`로 2건 정상 정렬 반환.

---

## 4. 검증 시나리오 3: 64K q8_0 KV 캐시 양자화 인자 및 OOM 방지 검증

```bash
docker exec vllm-serv-gateway ps -ef | grep llama_cpp.server
```
**기대 결과**: `llama_cpp.server` 구동 옵션에 `--type_k q8_0 --type_v q8_0`가 포함되고, 지속적인 추론 요청 시에도 프로세스 OOM Kill(Exit 137) 없이 상주 유지.

---

## 5. 검증 시나리오 4: 챗봇 A 및 챗봇 B E2E RAG 생성 검증

1. **챗봇 A 테스트 ("브링그린 클렌징 제품 모공 세정 효과 알려줘")**:
   - 0건 부재 고지 없이 세정력 및 자극성 분석 답변과 참고 리뷰 인라인 인용 출력 확인.
2. **챗봇 B 테스트 ("여름철 기름기 잡고 모공 커버 잘되는 매트한 파운데이션 추천해줘")**:
   - 0건 부재 고지 없이 추천 제품명과 근거 리뷰 텍스트 스트리밍 출력 확인.
