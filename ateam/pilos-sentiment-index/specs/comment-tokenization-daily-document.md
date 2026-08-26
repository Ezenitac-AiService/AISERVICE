# 댓글 토큰화·일별 문서 기능 명세

## 상태

- 구현 상태: 구현 완료
- 검증 상태: 비DB 실행 계약 테스트와 실제 최상위 실행 확인. 2026-08-10
  토큰화 14,227건·일별 문서 10건, 다음 증분 토큰화 384건·신규 문서 0건
- 통합 상태: `main@f80fdc2` 반영 완료 (PR #3, #17)

## 목적

전처리 댓글을 Kiwi 형태소 토큰으로 변환하고, 같은 종목·날짜의 장 마감
전 댓글을 TF-IDF 입력용 일별 문서로 집계한다.

## 범위

- `kiwi_ver1` 토크나이저 생성과 사용자 사전 적용
- 품사·포함 표현·불용어 기준의 토큰 선택
- 미토큰화 댓글의 배치 조회와 DB 적재
- 토큰 `form`을 TF-IDF 입력 문자열로 변환
- 종목·날짜별 일별 문서와 구성 댓글 순서 생성
- 문서 내용과 구성 댓글을 포함한 SHA-256 해시 생성
- 일별 문서와 댓글 매핑의 트랜잭션 적재

토크나이저 후보 비교, 실시간 실행 주기, 모델 학습과 추론은 제외한다.

## 토큰화 입력과 출력

정식 실행 입력은 DB의 다음 값이다.

```text
preprocessed_comment_id
text
```

출력 `kiwi_tokens`는 다음 객체 목록이다.

```json
[
  {"form": "반도체", "tag": "NNG"}
]
```

현재 기본 품사 범위는 명사 계열, 동사, 형용사, 외국어와 어근이다. 별도
포함 표현은 부정·강조·전망·커뮤니티 표현을 보존하고, 불용어와 원문의
`-잖-`이 `않/VX`으로 잘못 분석된 경우를 제거한다. 정확한 목록은
`tokenizer_settings.py`가 실행 기준이다.

## 토큰화 실행 흐름

```text
Kiwi와 사용자 사전 1회 생성
→ 현재 tokenizer_version 결과가 없는 전처리 댓글 2,000건 조회
→ text 일괄 토큰화
→ kiwi_tokens JSON 직렬화
→ tokenized_comment 분할 INSERT
→ 마지막 preprocessed_comment_id 이후 배치 반복
```

`run_pending_comment_tokenization()`은 전체 신규 적재 수를 반환한다.
조회·토큰화·적재 실패 또는 입력 수와 적재 수 불일치는 예외를 호출자에게
전달한다.

## TF-IDF 입력 문자열

- 토큰의 `form`만 사용하고 `tag`는 feature 문자열에 넣지 않는다.
- 한 `form` 내부의 공백은 `_`로 치환한다.
- 토큰 사이는 공백 한 칸으로 연결한다.
- 토큰이 없으면 빈 문자열을 반환한다.

예를 들어 `젠슨 황/NNP`, `반도체/NNG`는 `젠슨_황 반도체`가 된다.
이 문자열은 이미 계산된 TF-IDF 벡터가 아니라 Vectorizer 입력이다.

## 일별 문서 규칙

- 분석 함수는 저장 경계에서 정규화된 `datetime`만 입력으로 받는다.
- KST 의미의 `created_at`이 15시 30분 미만인 댓글만 포함한다.
- 같은 `stock_id`, `model_date`, `tokenizer_version`의 댓글을 순서대로
  하나의 `tfidf_text`로 연결한다.
- 토큰이 없는 댓글도 포함 조건을 만족하면 `comment_count`에 포함한다.
- `sequence_number`는 조회된 댓글 순서대로 1부터 부여한다.
- 문서 해시는 종목, 날짜, 토크나이저 버전, TF-IDF 문자열, 댓글 수와
  구성 `tokenized_comment_id` 목록을 정렬된 JSON으로 직렬화해 만든다.

`create_daily_document_data()`는 일별 문서 dict와 댓글 매핑 목록을
반환한다. `insert_daily_document_with_comments()`는 두 결과를 한
트랜잭션으로 저장한다.

## 실패와 재실행

- 토큰화 실행은 오류를 다시 발생시켜 후속 실행을 중단할 수 있게 한다.
- 일별 문서 실행은 대상 하나의 오류를 기록하고 다음 대상을 계속 처리한
  뒤 `(성공 수, 실패 수)`를 반환한다.
- 호출자는 일별 문서 실패 수가 0보다 크면 후속 추론을 시작하지 않아야
  한다.
- 독립 `build_daily_documents.main()`은 실패 수를 로그로 남긴다. 운영 최상위
  실행기는 반환된 실패 수를 직접 검사해 추론 단계 진입 여부를 결정한다.
- 조회 결과가 빈 일별 대상은 저장하지 않으며 실패 수에도 포함하지 않는다.
- 토큰화 대상과 일별 문서 대상은 기존 결과가 없는 레코드를 조회해
  재실행 범위를 정한다.

## 검증

비DB `unittest`에서 다음을 확인했다.

- 토큰화 대상 없음은 `0` 반환
- 여러 배치의 적재 수 합산
- 조회·토큰화·적재 오류 전파
- 일별 문서 성공·실패 수와 실패 후 다음 대상 처리
- 빈 대상 저장 방지
- `form`과 내부 공백 보존 규칙
- 정규화되지 않은 `created_at` 거부
- 15시 30분 이후 제외와 빈 토큰 댓글 수 반영

검증 명령은 다음과 같다.

```powershell
uv run python -m unittest discover -s tests -p "test_*.py"
```

## 관련 코드와 정본

- [`pilos/analysis/tokenizer.py`](../pilos/analysis/tokenizer.py)
- [`pilos/analysis/tokenizer_settings.py`](../pilos/analysis/tokenizer_settings.py)
- [`pilos/analysis/vectorizer.py`](../pilos/analysis/vectorizer.py)
- [`pilos/analysis/daily_dataset.py`](../pilos/analysis/daily_dataset.py)
- [`pilos/jobs/tokenize_comments.py`](../pilos/jobs/tokenize_comments.py)
- [`pilos/jobs/build_daily_documents.py`](../pilos/jobs/build_daily_documents.py)
- [`docs/DATA_CONTRACT.md`](../docs/DATA_CONTRACT.md)
- [`docs/DECISIONS.md`](../docs/DECISIONS.md)
