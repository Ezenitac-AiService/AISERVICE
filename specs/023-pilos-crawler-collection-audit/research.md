# Technical Research: A-Team Pilos 댓글 크롤러 결손 분석 및 수집 정상화

**Feature**: `023-pilos-crawler-collection-audit`
**Date**: 2026-08-20

---

## 1. 토스 증권 커뮤니티 API 응답 구조 및 필터링 결손 분석

### Decision
`comment_crawler.py`의 `_select_page()` 내 불필요한 메타데이터 필터링(`if profile_id is None or nickname is None... continue`)을 전면 제거하고, 모든 유효 댓글(최상위 댓글 및 대댓글/답글)을 온전히 수집하도록 파싱 로직을 개선한다.

### Rationale
- **기존 버그 분석**:
  ```python
  # 기존 코드 (comment_crawler.py L98-L104)
  author = comment.get('author') or {}
  profile_id = author.get('userProfileId')
  nickname = author.get('nickname')
  profile_id_2 = comment.get('authorUserProfileId')

  if cid is None or profile_id is None or nickname is None or profile_id_2 is None:
      continue  # 🚨 치명적 결함: authorUserProfileId가 없거나 비정형인 댓글이 통째로 버려짐!
  ```
  토스 API v4의 일부 댓글(익명 작성자, 탈퇴 회원, 시스템 공지, 또는 최신 버전 대댓글)은 `authorUserProfileId`가 최상위에 없거나 `author` 객체 내부 키 명칭이 다를 수 있다. 이때 기존 코드는 해당 댓글을 폐기할 뿐만 아니라, `last_cursor = cid` 갱신마저 건너뛰어 페이지네이션 중복 및 조기 중단(Cursor Stuck)을 유발했다.
- **개선 방안**:
  - `cid = comment.get('commentId')`만 존재하면 유효한 댓글로 인정.
  - `profile_id`가 없으면 `"ANONYMOUS_USER"`, `nickname`이 없으면 `"익명"`으로 안전 fallback.
  - `author` 객체 내 `userProfileId`와 최상위 `authorUserProfileId` 모두에 안전한 비식별화 해시를 부여.

### Alternatives Considered
- *대안 1: 비정형 댓글을 완전히 제외하고 로그만 기록* -> 수만 건의 실제 시장 여론이 누락되어 감성지수 왜곡 발생 (기각).
- *대안 2: commentId 기반 가상 UUID 생성* -> 기존 사용자 해시 체계와 불일치 발생 (기각).

---

## 2. 대댓글/답글(Nested Sub-Comments) 수집 구조

### Decision
토스 커뮤니티 API 응답에 포함된 대댓글(답글) 리스트(`subComments`, `replies` 또는 `nestedComments`)를 평탄화(Flatten)하여 각각 독립된 고유 레코드로 원본 JSONL에 기록하고 전처리 파이프라인에 투입한다.

### Rationale
- 종목 토론방 특성상 핵심 토론과 찬반 논쟁, 감성 표현은 부모 댓글보다 대댓글에 활발히 분포함.
- 부모 댓글과 자식 댓글 모두 고유한 `commentId`와 `createdAt`을 가지므로, `DatePartitionedAppender`를 통해 작성일별로 정확하게 라우팅 저장 가능.

---

## 3. 18일~19일 결손 데이터 소급 재수집(Catch-up Backfill) 전략

### Decision
`pilos.jobs.backfill_comments`에 2026-08-18 00:00(KST)을 목표 하한으로 지정하여 10개 전 종목을 일괄 수집한 뒤, 중복 레코드는 `comment_store`의 파일 단위 dedup 및 DB의 `INSERT IGNORE`로 완벽히 흡수한다.

### Rationale
- 2026-08-18 00:00(KST)을 `--until-date 2026-08-18`로 설정하여 백필을 실행하면, 8월 18일 및 19일에 누락되었던 모든 댓글이 작성일별 JSONL 파일(`from_20260818_*.jsonl`, `from_20260819_*.jsonl`)에 안전하게 append된다.
- DB 적재 시 기존 레코드는 `INSERT IGNORE`로 100% 보존되며, 신규 유입된 결손 댓글만 새로 insert된다.

---

## 4. Rate Limiting 및 지연 시간 정책 (0.5s ± 0.2s Jitter)

### Decision
`BASE_TIME = 0.5`초로 설정하고 `random.uniform(-0.2, 0.2)`의 지터를 부여하며, HTTP 429 수신 시 `Retry-After` 헤더 값을 100% 준수하는 지수 백오프를 유지한다.

### Rationale
- 토스 API의 서버 부담을 최소화하면서도 10개 종목의 백필을 수 분 내에 신속히 완료할 수 있는 최적의 속도-안정성 밸런스.
- 429 발생 시 최대 3회 재시도 및 `Retry-After` 대기 처리로 IP 차단 위험 원천 차단.

---

## 5. 다운스트림 7단계 파이프라인 엔드투엔드 연쇄 트리거

### Decision
소급 백필 및 전처리 완료 즉시 다음 단계를 연속 실행한다:
1. `preprocess_comments.run_preprocessing_for_files()`
2. `tokenize_comments.run_pending_comment_tokenization()`
3. `build_daily_documents.run_daily_document_building()`
4. `collect_supply_demand.run_supply_demand_collection()`
5. `predict_model.run_database_inference()`
6. `generate_llm_reports.run_pending_llm_report_generation()`

### Rationale
- 원본 댓글이 복원되어도 후속 단계가 갱신되지 않으면 사용자에게 노출되는 웹 대시보드 리포트와 감성지표가 과거 상태로 남게 됨.
- 엔드투엔드 파이프라인 연쇄 실행으로 18일~19일 일별 감성지수와 LLM 보고서를 즉시 최신화.
