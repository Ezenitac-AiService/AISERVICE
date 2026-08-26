# 기능 명세 관리 규칙

## 목적

`specs`는 기능 단위의 구현 계약과 진행 이력을 관리한다. 코드 폴더별
설명이 아니라 사용자가 인식할 수 있는 하나의 기능을 기준으로 작성한다.

기능 명세는 다음 내용을 팀원과 에이전트가 빠르게 확인하도록 돕는다.

- 무엇을 구현하고 무엇을 제외했는가
- 입력과 출력은 무엇인가
- 어느 실행기가 어떤 순서로 호출되는가
- 실패와 재실행을 호출자가 어떻게 판단하는가
- 무엇을 검증했고 아직 무엇을 검증하지 않았는가
- 현재 기능 브랜치와 `develop` 중 어디까지 반영됐는가

## `docs` 정본과의 관계

`specs`는 프로젝트 공통 정본을 대체하지 않는다.

| 판단 대상 | 확인할 문서 |
|---|---|
| 폴더·파일 배치와 의존 방향 | [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) |
| 데이터 의미·라벨·상태·필드 | [`docs/DATA_CONTRACT.md`](../docs/DATA_CONTRACT.md) |
| Git 작업 방식 | [`docs/GIT_WORKFLOW.md`](../docs/GIT_WORKFLOW.md) |
| 효력이 생긴 기술 결정 | [`docs/DECISIONS.md`](../docs/DECISIONS.md) |
| 개별 기능의 범위·실행·실패·검증 상태 | `specs/*.md` |

기능 명세에서 공통 구조나 데이터 의미를 새로 확정하지 않는다. 구현 중
공통 계약 변경이 필요하면 팀장에게 보고하고 해당 `docs` 정본을 함께
갱신한다. 정본과 기능 명세가 충돌하면 임의로 한쪽을 선택하지 않는다.

## 파일 기준

1. 기능 단위로 Markdown 파일 하나를 작성한다.
2. 파일명은 소문자 kebab-case를 사용한다.
3. 코드 폴더별로 명세 파일을 분리하지 않는다.
4. 하나의 기능이 여러 영역을 사용하면 한 문서 안에서 영역별로 정리한다.
5. 첫 실제 구현 파일과 소비자가 확인된 뒤 명세를 만든다.
6. Notebook, ERD와 로컬 검수 산출물을 기능 계약의 정본으로 사용하지 않는다.

예시

```text
comment-preprocessing.md
comment-tokenization-daily-document.md
sentiment-inference-storage.md
```

## 필수 구성

기능 성격에 맞지 않는 항목은 생략할 수 있지만 다음 순서를 기본으로 한다.

1. 상태
2. 목적
3. 포함 범위와 제외 범위
4. 입력과 출력
5. 실행 흐름
6. 핵심 처리 규칙
7. 실패와 재실행 계약
8. 검증 내용과 검증하지 않은 내용
9. 후속 소비자 또는 영향
10. 관련 코드와 정본

함수명과 필드명은 실제 구현을 확인해 작성한다. 코드에 없는 기능이나
실행하지 않은 검증을 완료로 기록하지 않는다.

## 상태 작성 기준

상태는 한 단어로 합치지 않고 다음 세 가지를 구분한다.

- 구현 상태: 코드가 존재하는지와 완료 범위
- 검증 상태: 자동 테스트, 비DB 스모크, 실제 DB 실행 등 확인한 범위
- 통합 상태: 기능 브랜치 구현인지 `develop` 병합 완료인지

공통 상태 표현은 다음을 사용한다.

| 상태 | 의미 |
|---|---|
| 논의 중 | 범위나 계약이 확정되지 않음 |
| 합의됨·반영 중 | 계약은 정해졌지만 구현 또는 통합이 진행 중 |
| 적용 완료 | 필요한 구현·검증·대상 브랜치 반영이 완료됨 |
| 대체됨 | 더 최신 기능이나 결정으로 교체됐으며 이력만 유지함 |

기능 브랜치 구현 완료와 `develop` 병합 완료를 혼용하지 않는다. PR 병합
후에는 통합 상태를 `develop` 적용 완료로 갱신한다.

## 작성과 갱신 흐름

```text
관련 정본 확인
→ 실제 코드의 입력·출력·호출자 확인
→ 기능 브랜치에서 구현과 명세 작성
→ 검증한 범위와 미검증 범위 기록
→ Pull Request 검토
→ develop 병합
→ 통합 상태 갱신
→ 공통 계약 변경이 있으면 팀장이 docs 정본 갱신
```

기능 담당자는 구현과 함께 명세를 갱신한다. 팀원 에이전트도 명세만 보고
추측하지 않고 관련 정본과 실제 코드를 먼저 확인한다.

## 현재 기능 명세

| 기능 | 문서 | 통합 상태 |
|---|---|---|
| 댓글 수집(크롤링) | [`comment-crawling.md`](comment-crawling.md) | `main` 반영 완료 |
| 댓글 전처리 | [`comment-preprocessing.md`](comment-preprocessing.md) | `main` 반영 완료 |
| 댓글 토큰화·일별 문서 | [`comment-tokenization-daily-document.md`](comment-tokenization-daily-document.md) | `main` 반영 완료 |
| 키움 개인 수급 수집 | [`supply-demand-collection.md`](supply-demand-collection.md) | `main` 반영 완료 |
| 수급 연관성 모델 v4 | [`sentiment-model-v4.md`](sentiment-model-v4.md) | `main` 반영 완료 |
| 수급 연관성 추론·결과 적재 | [`sentiment-inference-storage.md`](sentiment-inference-storage.md) | `main` 반영 완료 |
| Flask·프론트엔드 서비스 연동 | [`sentiment-flask-web-integration.md`](sentiment-flask-web-integration.md) | `main` 반영 완료 |
| 댓글 수급 신호·일별 LLM 브리핑 | [`comment-signal-daily-report.md`](comment-signal-daily-report.md) | `main` 반영 완료 |
| 근거 기반 챗봇 | [`chatbot-service.md`](chatbot-service.md) | `main` 반영 완료·공개 계약 conflict |
| 서비스 최상위 자동화 | [`service-pipeline-automation.md`](service-pipeline-automation.md) | `main` 반영 완료 |

정본에 반영된 뒤에도 기능 범위와 검증 이력 확인을 위해 specs 문서는
유지한다.

2026-08-11의 `main@f80fdc2`에는 수집부터 v13 생성까지의 최상위 자동화,
Flask·프론트엔드와 질문 블록 기반 챗봇 연결이 반영돼 있다. 전체 테스트는
437개 중 11 failures, 88 errors, 4 skips이며, 구 챗봇 입력 테스트와 현행
`block_key` 구현의 drift가 남아 있다. `test_chat*` 파일을 제외한 375개는
통과했다. 발표에서는
[`docs/work/PRESENTATION_FEATURE_BRIEF.md`](../docs/work/PRESENTATION_FEATURE_BRIEF.md)를
기능 요약 기준으로 사용하고, 세부 계약은 위 기능 명세와 `docs` 정본에서
확인한다.
