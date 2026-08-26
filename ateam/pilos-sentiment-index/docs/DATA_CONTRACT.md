# 데이터 계약

> 정본 범위: 영역 사이에서 전달되는 데이터의 필드, 형식, 의미와 변경 규칙
>
> 상태: 현재 기준
>
> 최초 적용일: 2026-07-22
>
> 마지막 갱신: 2026-08-10

---

# 1. 문서 목적

이 문서는 프로젝트에서 사용하는 데이터의 공통 형식을 정의합니다.

데이터 계약의 목적은 모든 단계에서 같은 객체를 사용하도록 강제하는 것이 아닙니다.

다음과 같은 경계에서 데이터의 의미가 달라지지 않도록 하는 것이 목적입니다.

- 수집 결과를 저장할 때
- 저장된 원본을 분석 영역이 불러올 때
- 전처리 결과를 다음 분석 단계로 전달할 때
- 분석 결과를 저장할 때
- 분석 결과를 웹 서비스에 전달할 때

각 영역은 내부 구현에 적합한 자료형을 자유롭게 사용할 수 있습니다.

다만 다른 영역으로 데이터를 전달할 때는 이 문서에서 합의한 필드명과 의미를 따릅니다.

---

# 2. 기본 원칙

데이터 계약은 다음 원칙을 따릅니다.

- 원본 데이터는 가능한 한 수집 당시 형태를 보존합니다.
- 분석용 데이터는 일관된 이름과 형식으로 정리합니다.
- 같은 의미의 필드는 모든 영역에서 같은 이름을 사용합니다.
- 하나의 필드에는 하나의 의미만 부여합니다.
- 값이 없다는 의미와 빈 문자열을 구분합니다.
- 시간 형식과 종목코드 형식을 통일합니다.
- 분석 중간 결과를 필요 이상으로 공통 계약에 포함하지 않습니다.
- 계약을 변경할 때는 생산자와 소비자를 함께 확인합니다.

---

# 3. 데이터 단계

댓글 데이터는 현재 다음 단계로 구분합니다.

```text
외부 응답

↓

수집 원본

↓

전처리 완료 데이터

↓

토큰화·벡터화 등 분석 중간 결과

↓

모델 입력 및 분석 결과

↓

저장 또는 웹 제공 데이터
```

각 단계는 목적이 다릅니다.

| 단계 | 목적 |
|---|---|
| 외부 응답 | 외부 서비스가 반환한 실제 응답 |
| 수집 원본 | 외부 응답을 손실 없이 보존 |
| 전처리 완료 데이터 | 분석에 사용할 표준 댓글 데이터 |
| 분석 중간 결과 | 토큰화·일별 문서·벡터화·특성 생성 |
| 모델 입력 | 일별 문서와 수급 라벨을 결합한 학습 Dataset |
| 분석 결과 | 학습된 모델과 단일 댓글·일별 집계 추론 결과 |
| 제공 데이터 | DB에 저장된 추론 결과 또는 영역 사이의 DTO |

---

# 4. 수집 원본 계약

## 목적

수집 원본은 외부 응답을 가능한 한 그대로 보존하기 위한 데이터입니다.

원본은 향후 다음 용도로 사용합니다.

- 수집 오류 확인
- 전처리 로직 재실행
- 누락 필드 확인
- 외부 응답 구조 변경 확인
- 분석 결과 재현

원본 저장은 `storage`가 담당합니다.

`collection`은 외부 응답을 가져와 반환하며 직접 저장하지 않습니다.

---

## 원본 보존 원칙

원본 단계에서는 다음 변환을 최소화합니다.

- 필드명 변경
- 시간 형식 변경
- 종목코드 변경
- 결측값 제거
- 중복 제거
- 텍스트 병합
- 분석에 불필요하다고 판단한 필드 삭제

외부 응답의 필드가 중첩 구조라면 원본에도 해당 구조를 유지할 수 있습니다.

예시

```json
{
  "commentId": "123456",
  "message": {
    "title": "제목",
    "message": "댓글 내용"
  },
  "board": {
    "stockCode": "A000660"
  },
  "statistic": {
    "likeCount": 3
  },
  "parentId": null,
  "createdAt": "2026-07-24T13:10:00+09:00",
  "updatedAt": "2026-07-24T13:10:00+09:00"
}
```

원본 구조는 외부 서비스에 따라 달라질 수 있으므로 프로젝트의 고정된 분석 계약으로 사용하지 않습니다.

분석은 원본 구조에 직접 의존하지 않고 전처리 단계에서 표준 구조로 변환합니다.

---

# 5. 전처리 완료 데이터 계약

전처리 완료 데이터는 댓글 분석에서 사용하는 표준 데이터입니다.

기본 단위는 댓글 한 건입니다.

한 행은 댓글 한 건을 의미합니다.

---

## 표준 컬럼

| 컬럼 | 자료형 | 필수 여부 | 설명 |
|---|---|---:|---|
| comment_id | string | 필수 | 댓글 고유 식별자 |
| title | string | 선택 | 댓글 제목 |
| message | string | 선택 | 댓글 본문 |
| text | string | 필수 | 분석에 사용하는 최종 텍스트 |
| stock_code | string | 필수 | 표준화된 종목코드 |
| like_count | integer 또는 null | 선택 | 좋아요 수. 외부 응답 의미 확인 전 결측을 0으로 바꾸지 않음 |
| parent_id | string 또는 null | 선택 | 부모 댓글 식별자 |
| created_at | datetime | 필수 | 댓글 생성 시각 |
| updated_at | datetime | 필수 | 댓글 수정 시각 |

현재 표준 계약은 위 컬럼을 기준으로 합니다.

구현 과정에서 새로운 컬럼이 필요하면 바로 계약에 추가하지 않고 사용 목적과 소비자를 먼저 확인합니다.

---

# 6. 필드별 규칙

## comment_id

댓글 한 건을 구분하는 고유 식별자입니다.

```text
comment_id
```

기본 자료형은 문자열입니다.

외부 응답에서 숫자로 제공되더라도 식별자 자체를 계산에 사용하지 않으므로 문자열로 통일합니다.

전처리 완료 데이터에는 같은 `comment_id`가 두 번 이상 존재하지 않아야 합니다.

중복 댓글이 존재하면 다음 기준을 적용합니다.

1. 동일한 `comment_id`인지 확인합니다.
2. 생성·수정 시각 또는 내용이 동일한지 확인합니다.
3. 기본적으로 마지막으로 확인된 한 건만 유지합니다.
4. 다른 내용이 존재하면 수집 또는 원본 데이터를 확인합니다.

중복 제거 기준을 변경할 경우 전처리 코드와 본 문서를 함께 수정합니다.

---

## title

댓글 또는 게시글의 제목입니다.

```text
title
```

제목이 존재하지 않을 수 있으므로 선택 필드입니다.

값이 없으면 `null` 또는 빈 문자열이 들어올 수 있습니다.

전처리 과정에서는 분석에 사용하기 전에 빈 값을 일관되게 처리합니다.

제목만 없고 본문이 존재한다면 해당 행을 제거하지 않습니다.

---

## message

댓글의 본문입니다.

```text
message
```

본문이 존재하지 않을 수 있으므로 원본 변환 직후에는 선택 필드로 취급합니다.

다만 `title`과 `message`를 결합한 최종 `text`가 비어 있다면 분석 대상에서 제외합니다.

---

## text

모델과 텍스트 분석에 사용하는 최종 텍스트입니다.

```text
text
```

기본 생성 규칙은 다음과 같습니다.

```text
title + message
```

제목과 본문 사이에는 공백을 한 칸 둡니다.

예시

```python
text = f"{title} {message}".strip()
```

다만 제목과 본문이 실질적으로 같은 내용이라면 제목을 중복해서 붙이지 않습니다.

예시

```text
title   = "SK하이닉스 오른다"
message = "SK하이닉스 오른다"
```

결과

```text
SK하이닉스 오른다
```

제목이 본문에 이미 포함되어 있거나 두 값이 동일한 경우 중복 여부를 확인한 뒤 한 번만 사용합니다.

최종 `text`는 다음 조건을 만족해야 합니다.

- 문자열이어야 합니다.
- 앞뒤 공백이 제거되어야 합니다.
- 공백만 존재해서는 안 됩니다.
- 분석에 사용할 실제 내용이 있어야 합니다.

`text`가 비어 있는 행은 분석 대상에서 제외합니다.

---

## stock_code

댓글이 연결된 종목의 코드입니다.

```text
stock_code
```

자료형은 문자열입니다.

외부 응답에서 다음과 같이 접두사 `A`가 붙어 올 수 있습니다.

```text
A000660
```

분석과 저장 단계에서는 접두사를 제거한 표준 종목코드를 사용합니다.

```text
000660
```

표준화 규칙은 다음과 같습니다.

1. 문자열로 변환합니다.
2. 앞뒤 공백을 제거합니다.
3. 맨 앞의 `A` 접두사만 제거합니다.
4. 숫자 형태의 문자열을 유지합니다.
5. 앞자리의 `0`을 제거하지 않습니다.

예시

| 입력 | 표준 결과 |
|---|---|
| A000660 | 000660 |
| 000660 | 000660 |
| ` A000660 ` | 000660 |

다음과 같이 정수로 변환해서는 안 됩니다.

```python
int("000660")
```

정수로 변환하면 앞자리 `0`이 사라져 종목코드의 의미가 훼손됩니다.

---

## like_count

댓글의 좋아요 수입니다.

```text
like_count
```

값이 존재할 때 자료형은 정수입니다.

값이 없고 외부 응답상 좋아요가 없다는 의미가 명확하면 `0`으로 처리할 수 있습니다.

다만 다음 두 상태를 구분해야 합니다.

```text
좋아요가 실제로 0개
외부 응답에서 값을 제공하지 않음
```

두 상태의 의미가 다르면 결측값을 임의로 `0`으로 바꾸지 않습니다.

현재 전처리는 `like_count`의 존재나 정수 변환을 강제하지 않습니다. 외부 응답에서 값이 누락될 수 있는지 확인한 뒤 필수 여부를 확정합니다.

---

## parent_id

답글이 참조하는 부모 댓글의 식별자입니다.

```text
parent_id
```

부모 댓글이 없으면 `null`입니다.

자료형은 문자열 또는 `null`입니다.

현재 수집 데이터에서 모든 값이 `null`이더라도 컬럼 자체를 바로 제거하지 않습니다.

외부 서비스가 답글 관계를 제공할 가능성이 있고, 향후 대화 구조 분석에 사용할 수 있기 때문입니다.

다만 실제 분석과 저장에서 장기간 사용하지 않는 것이 확인되면 제거 여부를 다시 논의합니다.

---

## created_at

댓글이 최초 생성된 시각입니다.

```text
created_at
```

외부 응답 예시

```text
2026-07-24T13:10:00+09:00
```

전처리 후 표준 표현

```text
2026-07-24 13:10:00
```

프로젝트에서는 한국 주식시장과 한국 사용자 댓글을 대상으로 하므로 현재 시각 기준은 KST로 통일합니다.

UTC로 변환하지 않습니다.

Python 내부에서는 다음 KST 시각을 초 단위 datetime으로 다룹니다.

```text
YYYY-MM-DD HH:MM:SS
```

로컬 JSONL 검수 산출물은 `date_format="iso"`로 ISO 8601 문자열을
생성합니다. 정식 전처리 실행기는 정규화된 Python `datetime`을
`preprocessed_comment` 저장 경계에 전달합니다. DB 물리 자료형은 DB
스키마가 관리하며 JSONL 표현을 DB 계약으로 사용하지 않습니다.

---

## updated_at

댓글이 마지막으로 수정된 시각입니다.

```text
updated_at
```

`created_at`과 동일한 규칙을 사용합니다.

외부 응답 예시

```text
2026-07-24T13:15:00+09:00
```

전처리 후 표준 표현

```text
2026-07-24 13:15:00
```

현재 프로젝트는 KST를 기준으로 사용하며 시간대 표기는 제거합니다.

시간대 표기를 제거한다는 것은 시간대를 무시한다는 의미가 아닙니다.

외부 값이 KST인지 확인한 뒤 KST 시각을 유지한 상태에서 프로젝트 표준 형식으로 변환합니다.

---

# 7. 시간 처리 원칙

현재 댓글 데이터는 `+09:00` 시간대를 포함한 ISO 8601 형식으로 수집됩니다.

예시

```text
2026-07-24T13:10:00+09:00
```

전처리 단계에서는 이를 datetime 객체로 변환하고 KST 기준을 유지합니다.

Python 내부 표준 표현은 다음과 같습니다.

```text
2026-07-24 13:10:00
```

현재 JSONL 중간 산출물은 ISO 8601 문자열로 직렬화합니다.

```text
datetime 객체로 변환하고 KST 기준으로 통일합니다.
JSONL 저장 시에는 ISO 8601 문자열로 직렬화합니다.
```

다음과 같이 실제 값에 마이크로초가 없는데 마이크로초를 필수로 지정하지 않습니다.

```text
%Y-%m-%dT%H:%M:%S.%f%z
```

입력 형식에 마이크로초가 포함될 수도 있고 포함되지 않을 수도 있다면 자동 파싱 또는 두 형식을 모두 처리할 수 있는 방식을 사용합니다.

---

# 8. 결측값 처리

결측값은 모든 컬럼에서 같은 방식으로 제거하지 않습니다.

컬럼의 의미에 따라 처리합니다.

| 컬럼 | 결측 처리 |
|---|---|
| comment_id | 행 제외 |
| title | 빈 문자열로 처리 가능 |
| message | title 존재 여부와 함께 판단 |
| text | 비어 있으면 행 제외 |
| stock_code | 행 제외 또는 원본 재확인 |
| like_count | 외부 의미 확인 후 0 또는 결측 유지 |
| parent_id | null 허용 |
| created_at | 원본 재확인 후 분석 대상 제외 검토 |
| updated_at | created_at 사용 가능 여부를 별도 판단 |

특정 컬럼 하나가 비어 있다는 이유만으로 모든 행을 일괄 삭제하지 않습니다.

예를 들어 `title`이 없더라도 `message`가 있다면 분석할 수 있습니다.

반대로 `title`과 `message`가 모두 비어 최종 `text`를 만들 수 없다면 해당 행은 분석 대상에서 제외합니다.

---

# 9. 중복 처리

현재 댓글의 기본 중복 판별 키는 다음과 같습니다.

```text
comment_id
```

동일한 `comment_id`가 여러 번 나타나면 한 건만 유지합니다.

중복 제거는 원본 저장 이후 전처리 단계에서 수행합니다.

원본 데이터에서는 중복도 수집 당시 상태의 일부이므로 보존할 수 있습니다.

```text
수집 원본
- 중복 보존 가능

전처리 완료 데이터
- comment_id 중복 제거
```

URL이나 텍스트만으로 댓글 중복을 판단하지 않습니다.

서로 다른 사용자가 같은 내용을 작성할 수 있기 때문입니다.

---

# 10. DataFrame 자료형

전처리 완료 DataFrame은 가능한 한 다음 자료형을 사용합니다.

| 컬럼 | 권장 pandas dtype |
|---|---|
| comment_id | string |
| title | string |
| message | string |
| text | string |
| stock_code | string |
| like_count | Int64 또는 변환 전 수치형 |
| parent_id | string |
| created_at | datetime64 |
| updated_at | datetime64 |

`like_count`에 결측값이 존재할 가능성이 있으면 pandas의 nullable integer인 `Int64`를 사용할 수 있습니다.

문자열 컬럼은 가능하면 `object`보다 pandas의 `string` dtype을 사용합니다.

단, 라이브러리 호환성 문제로 자료형 변환이 필요하면 분석 영역 내부에서 변환할 수 있습니다.

---

# 11. 분석 내부 데이터

전처리, 토큰화, 벡터화처럼 `analysis` 내부에서 이어지는 단계에는 DTO를 강제하지 않습니다.

다음 자료형을 사용할 수 있습니다.

- pandas DataFrame
- pandas Series
- list
- dict
- NumPy 배열
- SciPy 희소행렬
- 라이브러리별 모델 입력 객체

예시

```text
DataFrame
    ↓
토큰 list 컬럼 추가
    ↓
TF-IDF 희소행렬 생성
    ↓
모델 학습
```

분석 내부의 자료형은 해당 작업을 구현하기에 적합한 형태를 선택합니다.

중요한 것은 내부 자료형을 통일하는 것이 아니라 영역 경계를 넘을 때 의미가 유지되는 것입니다.

---

# 12. 토큰화 중간 산출물

현재 분석 실행 기준선은 전처리 완료 댓글의 토큰화 결과를
`tokenized_comment`에 저장합니다.

- 생산자: 토큰화 실행기
- 소비자: 일별 문서 생성과 TF-IDF 검수
- 정식 저장 형식: MySQL `tokenized_comment.kiwi_tokens`
- 선택적 검수 형식: 로컬 JSONL
- 서비스 모델 입력: `tokenizer_version=kiwi_ver1`의 `form`을 사용해
  `tfidf_text` 생성

로컬 JSONL은 분석 검수용 중간 산출물이다. 서비스 모델은 DB에 적재된
토큰화 결과로 만든 `daily_document.tfidf_text`를 사용하며 로컬 JSONL
경로에 의존하지 않는다.

현재 확인된 구조는 다음과 같습니다.

```text
kiwi_tokens: list
  - form: string
  - tag: string
```

현재 모델 기준선은 Kiwi와 현재 설정된 품사 필터·포함 표현·불용어·사용자 사전을 사용합니다. 설정값을 변경하면 기존 모델과 같은 입력 계약으로 간주하지 않습니다.

다음 운영 기준은 비교·검증 후 확정합니다.

- 최종 품사 범위
- 불용어 처리
- 사용자 사전과 버전 관리

토큰 선택 결과가 없는 댓글은 빈 `kiwi_tokens`를 가질 수 있습니다. 일별 문서의 댓글 활동량을 계산할 때는 토큰 존재 여부와 별개로 집계에 포함된 댓글 한 건으로 계산합니다.

`kiwi_tokens`는 전처리 완료 기본 계약에 포함하지 않습니다. 전처리 완료 데이터와 토큰화 중간 산출물을 별도 단계로 관리합니다.

---

# 13. TF-IDF 입력과 벡터화 결과

`tfidf_text`는 형태소 토큰을 TF-IDF 벡터라이저에 전달하기 위한 문자열입니다.

생성 규칙은 다음과 같습니다.

1. 각 토큰의 `form`을 사용합니다.
2. 하나의 `form` 내부 공백은 `_`로 치환합니다.
3. 토큰 사이를 공백 한 칸으로 연결합니다.
4. 토큰이 없으면 빈 문자열을 사용합니다.

예시

```text
젠슨 황, 반도체
→ 젠슨_황 반도체
```

벡터라이저는 공백으로 구분된 형태소를 그대로 토큰으로 사용합니다.

TF-IDF 희소행렬 자체는 공통 행 단위 저장 계약에 포함하지 않습니다.

벡터화 결과는 일반적인 표 형태와 다를 수 있습니다.

예시

- SciPy 희소행렬
- NumPy 배열
- 특성명 목록
- 학습된 vectorizer 객체
- 문서 key와 행 위치의 매핑

벡터화 결과를 저장해야 한다면 다음 정보를 함께 관리해야 합니다.

- 사용한 전처리 기준
- 토크나이저 설정
- 사용자 사전 버전
- 불용어 목록
- vectorizer 설정
- vocabulary
- 행 순서와 `stock_code + model_date`의 연결
- 생성 시각 또는 버전

현재 TF-IDF 희소행렬은 파일로 저장하지 않습니다. 학습된 vectorizer는 모델 아티팩트에 포함하여 저장합니다.

훈련 데이터에는 `fit_transform`, 검증·추론 데이터에는 학습된 vectorizer의 `transform`만 사용합니다.

---

# 14. 종목·날짜별 일별 문서

현재 모델의 기본 문서 단위는 댓글 한 건이 아니라 종목·날짜별 댓글 집계입니다.

- 생산자: 일별 문서 생성 단계
- 소비자: 모델 학습, 일별 집계 추론과 TF-IDF 검수
- 기본 key: `stock_code + model_date`

| 필드 | 자료형 | 필수 여부 | 설명 |
|---|---|---:|---|
| stock_code | string | 필수 | 6자리 표준 종목코드 |
| model_date | date | 필수 | 댓글을 집계한 KST 기준일 |
| tfidf_text | string | 필수 | 해당 종목·날짜의 토큰을 연결한 TF-IDF 입력 |
| comment_count | integer | 필수 | 해당 일별 문서에 포함된 댓글 수 |

현재 집계 규칙은 다음과 같습니다.

1. 입력 댓글은 `created_at` 오름차순이어야 합니다.
2. 같은 종목과 같은 날짜의 댓글 토큰을 하나의 문서로 연결합니다.
3. KST 기준 15시 30분 미만에 생성된 댓글만 포함합니다.
4. 15시 30분 이후 댓글은 현재 일별 문서에서 제외합니다.
5. 토큰 목록이 비어 있어도 포함 조건을 만족한 댓글은 `comment_count`에 포함합니다.
6. `comment_count`는 0 이상의 정수입니다.

15시 30분 기준을 변경하면 일별 문서, 학습 Dataset, 모델 재학습과 추론 결과에 모두 영향을 줍니다.

---

# 15. 수급 레코드와 학습 Dataset

## 개인투자자 수급 레코드

현재 일별 댓글 문서와 결합하는 개인투자자 수급 레코드는 다음 필드를 사용합니다.

| 필드 | 자료형 | 필수 여부 | 설명 |
|---|---|---:|---|
| stock_code | string | 필수 | 6자리 표준 종목코드 |
| trade_date | date | 필수 | 수급 값의 거래일 |
| buy_volume | 수치형 | 필수 | 해당 거래일의 개인투자자 매수 거래량 |
| sell_volume | 수치형 | 필수 | 해당 거래일의 개인투자자 매도 거래량 |
| supply_demand_index | 수치형 | 필수 | 개인투자자 매수·매도량으로 생성한 일별 거래우위 모델 목표값 |
| data_status | string | 필수 | 현재값의 상태. `estimated` 또는 `confirmed` |
| observed_at | datetime | 필수 | 현재값을 관측한 KST 시각 |
| source_api | string | 필수 | 현재값을 생산한 키움 API 식별자 |

`supply_demand_index`는 결측값과 유한하지 않은 값을 허용하지 않으며 모델 학습 시 실수형 배열로 변환합니다.

`buy_volume`과 `sell_volume`은 시장 전체나 기관·외국인의 거래량이 아니라 개인투자자 거래량을 의미합니다.

개인투자자 수급지수의 원천과 계산식이 변경되면 같은 라벨 계약으로 간주하지 않습니다.

현재 키움 수집은 하나의 종목·거래일 행에 장중 추정과 장마감 확정 근거를
구분해 보존합니다.

| 상태 | 원천 | 의미 |
|---|---|---|
| `estimated` | `ka10063_residual` | 외국인·기관·기타법인 수급과 기준 누적거래량의 잔차로 계산한 장중 추정값 |
| `confirmed` | `ka10060` | 개인투자자 매수·매도 확정 조회값 |

추정 이력은 `estimated_individual_buy_volume`,
`estimated_individual_sell_volume`, `estimated_supply_demand_index`,
`estimated_observed_at`, `estimated_source_api`, `estimation_version`에
보존합니다. 확정 이력은 `confirmed_individual_buy_volume`,
`confirmed_individual_sell_volume`, `confirmed_supply_demand_index`,
`confirmed_observed_at`, `confirmed_source_api`에 보존합니다.

`buy_volume`, `sell_volume`, `supply_demand_index`, `observed_at`,
`source_api`는 현재 유효값입니다. 확정값이 들어오면 현재 유효값도 확정값으로
교체하며, 이후 장중 추정 적재가 확정 행을 `estimated`로 낮추지 않습니다.
수급지수는 다음 관계를 만족하고 `-1.0` 이상 `1.0` 이하여야 합니다.

```text
supply_demand_index = (buy_volume - sell_volume) / (buy_volume + sell_volume)
```

매수량과 매도량이 모두 0이면 지수를 만들지 않고 오류로 처리합니다.
모델 학습 Dataset은 `data_status='confirmed'` 행만 사용합니다. 일별 추론
대상 조회와 LLM 보고서 대상 조회는 수급 행의 존재만 확인하고 상태를 필터링하지
않습니다. D-018에 따라 v13 보고서는 생성 당시 `data_status`와 `observed_at`을
보존하고, 같은 생성 identity에서는 `estimated→confirmed` 또는 더 최신 estimated
관측에만 갱신합니다. Flask와 화면은 저장 당시 상태와 현재 상태를 함께 비교해
보고서 갱신 대기를 표시합니다. 챗봇의 정확 수치 경로는 confirmed 행만 사용합니다.

## 학습 Dataset

일별 문서와 수급 레코드는 다음 key로 결합합니다.

```text
daily document: stock_code + model_date
supply record: stock_code + trade_date
```

결합 규칙은 다음과 같습니다.

1. 양쪽의 `stock_code`를 6자리 문자열로 통일합니다.
2. `model_date`와 `trade_date`를 날짜로 변환합니다.
3. 양쪽에 모두 존재하는 종목·날짜만 내부 결합합니다.
4. 양쪽 key는 각각 중복되지 않아야 하며 일대일 관계를 검증합니다.
5. 결합 후 중복 날짜 컬럼인 `trade_date`는 제거합니다.
6. 결과를 `model_date`, `stock_code` 순서로 정렬합니다.

모델의 목표값은 `supply_demand_index`이며 학습·검증 분리는 `model_date`를 기준으로 수행합니다.

---

# 16. 모델 입력 특성

현재 Ridge 모델의 한 행은 하나의 종목·날짜별 일별 문서입니다.

서비스 모델 v4의 입력은 다음 CSR 희소행렬입니다.

```text
TF-IDF 특성 열들
```

`stock_code`, `model_date`, `comment_count`와 실제 `supply_demand_index`는
입력 특성에 포함하지 않습니다. `comment_count`는 일별문서 metadata와
품질 판단에 사용할 수 있지만 v4 Ridge 계수는 존재하지 않습니다.

현재 v4 설정은 unigram `(1, 1)`, `min_df=5`, `max_df=0.95`,
`max_features=None`, `sublinear_tf=True`, Ridge `alpha=1`입니다. 이 값은
v4 재현 계약이며 후속 모델 버전의 비교 실험을 제한하지 않습니다.

---

# 17. 모델 아티팩트

서비스 모델 객체는 pickle bundle 스키마 2로 저장합니다.

| key | 값 | 설명 |
|---|---|---|
| artifact_schema_version | integer | bundle 구조 버전. 현재 값은 `2` |
| model_name | string | 현재 `ridge_supply` |
| model_variant | string | `positive` 또는 `negative` |
| model_version | integer | 서비스 모델 버전. 현재 `4` |
| feature_mode | string | 현재 `text_only` |
| tokenizer_version | string | 학습 일별문서 토큰 계약 버전 |
| dataset_start_date | date | 전체 최종학습 Dataset 시작일 |
| dataset_end_date | date | 전체 최종학습 Dataset 종료일 |
| vectorizer | TfidfVectorizer | 학습된 vocabulary와 IDF |
| ridge_model | Ridge | 학습된 회귀 모델 |

v4 bundle에는 댓글 수 Scaler를 포함하지 않습니다. vectorizer와 Ridge는
같은 전체 Dataset 학습에서 생성된 묶음이어야 하며 서로 다른 학습의
객체를 조합하지 않습니다.

Pickle은 Python 객체를 복원하므로 프로젝트가 직접 생성한 신뢰할 수 있는 파일만 로드합니다.

DB `artifacts`에는 저장소 상대경로, 모델 식별자, Dataset 기간, 전체학습
지표와 공식 검증 지표를 기록합니다. 추론 시 DB 행과 bundle의 스키마·
모델명·방향·버전·토크나이저·Dataset 기간이 모두 일치해야 합니다.

기존 검증 환경에서는 Positive v4가 artifact 7, Negative v4가 artifact
8로 등록됐습니다. 이 값은 해당 환경의 실행 이력 식별자이며 다른 환경의
공통 계약이나 고정값이 아닙니다. 모델 버전은 기존 파일이나 DB 행을
덮어쓰지 않고 증가시킵니다. 공식 검증값은 월별 층화 날짜 그룹 80:20
분할을 시드 42~46으로 반복한 지표 평균이며, 최종 bundle은
2026-07-24까지 전체 Dataset으로 별도 재학습한 객체입니다.

---

# 18. 단일 댓글 추론 전달 계약

단일 댓글 추론은 사용자가 입력한 댓글 하나에서 텍스트가 학습된 수급 방향에 기여하는 정도를 분석합니다.

현재 영역 사이의 전달 객체는 `SingleCommentInferenceDTO`입니다.

| 필드 | 자료형 | 설명 |
|---|---|---|
| comment_text | string | 사용자가 입력한 원문 |
| processed_text | string | 학습과 같은 규칙으로 전처리한 문자열 |
| text_score | float | 인식된 단어 기여도의 합 |
| recognized_feature_count | integer | vectorizer vocabulary에서 인식된 특성 수 |
| positive_keywords | tuple[KeywordContributionDTO, ...] | 양수 방향 주요 키워드 |
| negative_keywords | tuple[KeywordContributionDTO, ...] | 음수 방향 주요 키워드 |

`KeywordContributionDTO`는 다음 필드를 가집니다.

| 필드 | 자료형 | 설명 |
|---|---|---|
| keyword | string | 웹에 전달할 특성명 |
| contribution | float | 해당 특성의 수급 방향 기여도 |

단일 댓글에는 종목·날짜별 댓글 수가 없으므로 현재 `text_score`만 제공합니다. 일별 댓글 수 특성, 모델 절편과 전체 수급지수 예측값을 단일 댓글 결과인 것처럼 합산하지 않습니다.

전처리 후 분석할 문자열이 없으면 추론 결과 대신 오류로 처리합니다.

## 두 방향 모델 결과 묶음

사용자가 화면에서 모델 반응을 확인할 때는 Positive와 Negative 두 모델의 결과를 함께 전달합니다. 이때 사용하는 전달 객체는 `SingleCommentAnalysisDTO`입니다.

| 필드 | 자료형 | 설명 |
|---|---|---|
| comment_text | string | 사용자가 입력한 원문 |
| processed_text | string | 학습과 같은 규칙으로 전처리한 문자열 |
| token_count | integer | 선택 조건을 통과한 토큰 수 |
| positive | SingleCommentInferenceDTO | Positive 모델 반응 |
| negative | SingleCommentInferenceDTO | Negative 모델 반응 |

`recognized_feature_count`는 방향마다 vectorizer가 다르므로 각 `SingleCommentInferenceDTO` 안에서만 제공하고 묶음 수준에서 중복 제공하지 않습니다.

단일 댓글 결과에는 §29의 일별 `comment_signal_score` calibration을 적용하지 않습니다. Ridge는 일별 댓글 집합(document) 단위로 학습됐으므로 단일 댓글 결과를 0~100 신호로 바꾸어 표현하지 않습니다.

## Flask 전달 계약

`POST /api/inference/single-comment`는 JSON 객체의 `comment_text`를 입력으로
받고 다음 구조를 반환합니다.

```json
{
  "comment_text": "추가 매수한다",
  "processed_text": "추가 매수한다",
  "token_count": 2,
  "positive_model": {
    "text_score": 0.3,
    "recognized_feature_count": 2,
    "positive_keywords": [{"keyword": "매수", "contribution": 0.3}],
    "negative_keywords": []
  },
  "negative_model": {
    "text_score": -0.1,
    "recognized_feature_count": 1,
    "positive_keywords": [],
    "negative_keywords": [{"keyword": "추가", "contribution": -0.1}]
  },
  "notice": "..."
}
```

JSON 객체·비어 있지 않은 문자열이 아니거나 전처리 후 분석할 특성이 없으면
HTTP 400입니다. 모델 등록·파일 로딩이나 내부 분석 준비 실패는 HTTP 500으로
처리합니다. 입력 원문과 모델 파일을 DB에 저장하지 않습니다.

---

# 19. 일별 집계 추론 저장 계약

정식 서비스 추론 결과는 MySQL `sentiment_index_result`에 저장합니다.
한 행은 한 일별문서를 하나의 정확한 모델 아티팩트로 추론한 결과입니다.
같은 최신 일별문서라도 Positive와 Negative의 `artifact_id`가 다르므로
방향별 결과가 각각 한 행씩 생성됩니다.

| DB 필드 | 자료형 | 설명 |
|---|---|---|
| daily_document_id | integer | 추론한 최신 일별문서 식별자 |
| artifact_id | integer | 사용한 정확한 방향·버전의 모델 아티팩트 |
| supply_demand_association_score | number | Ridge 모델의 수급 연관성 점수 |
| intercept | number | Ridge 절편 |
| text_score | number | 단어별 기여도의 합 |
| comment_count_contribution | number | text-only v4에서는 `0.0` |
| recognized_feature_count | number | 현재 문서에서 인식된 TF-IDF 특성 수 |
| unique_token_count | number | 현재 문서의 중복 제거 토큰 수 |
| vocabulary_coverage | number | `recognized_feature_count / unique_token_count`, 0~1 |
| inference_status | string | `ready` 또는 `insufficient_features`; 과거 NULL은 API에서만 `unknown` |
| positive_contribution_keywords | JSON array | 양수 방향 주요 키워드 |
| negative_contribution_keywords | JSON array | 음수 방향 주요 키워드 |

각 키워드 객체는 다음 필드를 가집니다.

| 필드 | JSON 자료형 | 설명 |
|---|---|---|
| rank | number | 같은 방향 안에서 기여도 순위 |
| word | string | vectorizer 특성명 |
| tfidf | number | 현재 문서의 TF-IDF 값 |
| coefficient | number | 학습된 Ridge 단어 계수 |
| contribution | number | `tfidf × coefficient` |

점수는 다음 관계를 만족해야 합니다.

```text
supply_demand_association_score
= intercept
+ text_score
+ comment_count_contribution
```

부동소수점 계산 오차 범위 안에서 위 합이 모델 예측값과 일치하는지
검증합니다. `(daily_document_id, artifact_id)`는 고유하며 기존 결과를
UPDATE하거나 Upsert하지 않습니다.

추론 대상은 지정 기간의 최신 `daily_document` 중 같은 종목·날짜의
`supply_demand`가 존재하는 문서입니다. INNER JOIN을 서비스 가능
조건으로 사용하므로 휴장일과 수급 미수집일은 결과를 만들지 않습니다.
실제 `supply_demand_index`는 text-only 추론 입력으로 사용하지 않습니다.

`recognized_feature_count`, `unique_token_count`, `vocabulary_coverage`,
`inference_status`는 신규 추론 결과에 함께 저장하는 품질 계약입니다.
기존 품질값 NULL 행을 운영 실행에서 UPDATE하지 않습니다. Flask는 NULL을
DB에 새 상태로 저장하지 않고 응답에서만 `unknown`으로 표현합니다.

## 웹 통합 상태

모델이 생산해 `sentiment_index_result`에 저장한 필드를 현재 일별 추론
결과 계약의 기준으로 사용합니다.

현재 Flask 조회 경로는 `supply_demand_association_score`를
그 이름 그대로 제공하고, 기여 키워드의 `word`를 웹 DTO의 `keyword`로
변환합니다. 실제 수급은 별도 필드로 제공합니다.

```text
actual_supply_demand_index
actual_buy_volume
actual_sell_volume
```

모델이 생산하지 않는 `prediction_error`는 제공하지 않습니다. Flask 영역은
저장 결과를 DTO로 변환할 수 있지만 모델 생산 필드의 의미를 바꾸지 않습니다.

현재 수급 결과 조회 서비스는 `ACTIVE_SERVICE_MODEL_VERSION=4`와 방향을
기준으로 DB의 활성 Positive·Negative artifact를 조회하고 로컬 bundle identity와
교차검증합니다. 기존 환경의 artifact ID `7`·`8`은 검증 이력일 뿐 코드 상수나
다른 환경의 고정 계약이 아닙니다.

## 기여 키워드 컬럼의 현재 소비자

`positive_contribution_keywords`와 `negative_contribution_keywords`는 추론 산출물이자 검수용 데이터로 계속 저장합니다.

일별 LLM 보고서는 2026-08-07 개편 이후 이 두 컬럼을 소비하지 않습니다. 보고서가 소비하지 않는 것과 추론 산출물 자체를 삭제하는 것은 별개이며, 이 저장 계약은 변경하지 않습니다.

---

# 20. 임시 파생값

분석 검수나 데이터 분포 확인을 위해 임시 파생값을 계산할 수 있습니다. 임시 파생값은 저장·모델·DB·API 공통 계약에 자동으로 포함되지 않습니다.

`length`는 현재 전처리 코드가 생성하는 표준 컬럼이 아닙니다.

> 댓글 길이는 데이터 분포 검수 시 `text.str.len()` 등으로 계산할 수 있는 임시 파생값이며, 저장·모델·DB·API 공통 계약에는 포함하지 않습니다.

과거 로컬 JSONL에 `length`가 남아 있어도 Git 비추적 산출물은 현재 계약의 근거로 사용하지 않습니다. 길이에 따른 제외·절단 정책도 현재 존재하지 않습니다.

새 파생값을 공통 계약으로 추가하려면 다음 조건을 모두 확인합니다.

- 생성하는 생산자가 명확한가
- 사용하는 소비자가 명확한가
- 계산 기준과 자료형이 정해졌는가
- 결측 처리 기준이 있는가
- 지속적인 저장 또는 전달이 필요한가

---

# 21. DTO 사용 기준

DTO는 모든 함수 사이에서 사용하지 않습니다.

DTO는 서로 다른 영역이 데이터를 주고받고, 그 구조를 명확히 고정할 필요가 있을 때 사용합니다.

예시

```text
analysis
    ↓
jobs 또는 service

storage
    ↓
service

service
    ↓
web
```

DTO를 추가하려면 다음 조건을 확인합니다.

- 데이터를 만드는 생산자가 명확합니다.
- 데이터를 사용하는 소비자가 명확합니다.
- 전달할 필드가 합의되었습니다.
- 같은 구조를 둘 이상의 영역에서 사용합니다.
- DataFrame 자체를 그대로 넘기는 것보다 계약 객체가 유리합니다.

다음 흐름에서는 DTO를 강제하지 않습니다.

```text
preprocess
    ↓
tokenize
    ↓
vectorize
```

위 단계는 모두 `analysis` 내부이므로 DataFrame이나 라이브러리 객체를 직접 사용할 수 있습니다.

---

# 22. 현재 저장 형식

댓글 전처리·토큰화 검수에는 JSONL을 사용할 수 있고, 정식 학습·추론
흐름에서는 MySQL과 모델 pickle bundle을 사용합니다.

| 논리 자료형 | Python | 저장 표현 |
|---|---|---|
| 문자열 | str | JSON string |
| 정수 | int | JSON number |
| 실수 | float | JSON number |
| 결측값 | None / pd.NA | JSON null |
| 날짜·시각 | date / datetime | ISO 8601 string |
| 토큰·키워드 목록 | list[dict] | JSON object array |
| 모델 구성요소 묶음 | dict | Pickle |

| 저장 대상 | 저장 위치 | 식별 기준 |
|---|---|---|
| 수집 원본 파일 정보 | MySQL `source_comment_file` | `source_comment_file_id` |
| 전처리 완료 댓글 | MySQL `preprocessed_comment` | `preprocessed_comment_id` |
| 토큰화 댓글 | MySQL `tokenized_comment` | `tokenized_comment_id`와 토크나이저 버전 |
| 종목·거래일별 토큰 문서 | MySQL `daily_document` | `daily_document_id` |
| 일별 문서 구성 댓글 | MySQL `daily_document_comment` | 일별문서와 토큰화 댓글 매핑 |
| 일별 수급지수 | MySQL `supply_demand` | 종목과 거래일 |
| 모델 메타데이터·평가 지표 | MySQL `artifacts` | `artifact_id` |
| 모델 객체 | 저장소 `artifacts/*.pkl` | DB `saved_path` |
| 일별문서 추론 결과 | MySQL `sentiment_index_result` | 일별문서와 아티팩트 |
| 신호 calibration | 저장소 `artifacts/calibration/*.json` | 모델명과 모델 버전 |
| 일별 LLM 보고서 | MySQL `llm_report` | 방향별 추론 결과와 생성 버전 |

DB 조회 DTO와 v13 보고서 생산 계약, Flask service 변환과 JavaScript 상세 화면
소비 경로가 구현돼 있습니다. Flask는 저장된 `report_json`을
`build_flask_daily_signal_response()`로 검증·변환하고, 화면은 현재 v13 공개 필드와
`report_refresh_status`를 소비합니다.

---

# 23. 컬럼명 규칙

Python과 저장 데이터의 컬럼명은 `snake_case`를 사용합니다.

외부 응답

```text
commentId
stockCode
likeCount
createdAt
```

프로젝트 표준

```text
comment_id
stock_code
like_count
created_at
```

외부 API의 필드명을 프로젝트 전체로 전파하지 않습니다.

외부 구조를 표준 구조로 바꾸는 작업은 저장 매체와 내부 계약의 경계 adapter에서 수행할 수 있습니다.

같은 의미의 컬럼을 여러 이름으로 사용하지 않습니다.

피해야 하는 예시

```text
stock_code
stockCode
code
ticker
stock_id
```

프로젝트에서 종목코드를 뜻하는 표준 이름은 다음과 같습니다.

```text
stock_code
```

---

# 24. 계약 변경 절차

데이터 계약을 변경할 때는 컬럼 하나만 수정하지 않습니다.

다음 내용을 함께 확인합니다.

1. 누가 이 필드를 생성하는가
2. 누가 이 필드를 사용하는가
3. 기존 데이터와 호환되는가
4. 전처리 코드가 변경되는가
5. 저장 형식이 변경되는가
6. 모델 입력이 변경되는가
7. 웹 또는 API 응답이 변경되는가
8. 기존 테스트와 문서를 수정해야 하는가

변경 예시

```text
text 컬럼 생성 기준 변경
```

함께 확인할 대상

```text
analysis 전처리
토크나이저 입력
모델 학습 데이터
저장 파일
DB 컬럼
웹 표시
테스트
```

---

# 25. 계약 변경 기록

확정된 데이터 계약 변경은 본 문서를 먼저 또는 같은 작업에서 수정합니다.

설계상 중요한 변경 이유는 `DECISIONS.md`에 기록합니다.

예시

```text
title과 message를 별도 모델 입력으로 사용하지 않고
중복 제거 후 text로 결합하기로 결정
```

기능 구현과 데이터 계약 변경이 함께 이루어지는 경우 작업 브랜치와 Pull Request를 사용합니다.

단순 오탈자나 이미 합의된 표현의 최신화는 팀장이 `develop`에서 직접 수정할 수 있습니다.

---

# 26. 현재 확정된 댓글 전처리 결과

현재 전처리 완료 댓글 데이터는 다음 조건을 만족해야 합니다.

- 한 행은 댓글 한 건입니다.
- `comment_id`는 문자열이며 중복되지 않습니다.
- `title`과 `message`는 원본 값에 따라 문자열 또는 `null`일 수 있으며, `text`를 만들 때 결측을 빈 문자열로 처리합니다.
- `text`는 제목과 본문을 중복 없이 결합한 최종 분석 문자열입니다.
- `text`가 비어 있는 행은 존재하지 않습니다.
- `stock_code`는 문자열입니다.
- `stock_code` 앞의 `A` 접두사는 제거됩니다.
- 종목코드 앞자리의 `0`은 유지됩니다.
- `like_count`는 값이 있으면 정수이며, 현재 구현은 결측을 임의로 `0`으로 바꾸지 않습니다.
- `parent_id`는 문자열 또는 `null`입니다.
- `created_at`과 `updated_at`은 KST 기준입니다.
- Python 내부 시각은 KST 기준 초 단위 datetime이며, 로컬 JSONL 검수
  산출물은 ISO 8601 문자열로 직렬화합니다.

표준 컬럼 순서는 다음과 같습니다.

```text
comment_id
title
message
text
stock_code
like_count
parent_id
created_at
updated_at
```

`length`와 `kiwi_tokens`는 위 전처리 완료 기본 계약에 포함하지 않습니다. `kiwi_tokens`는 토큰화 중간 산출물에서만 추가됩니다.

컬럼 순서는 데이터의 의미 자체를 결정하지는 않습니다.

다만 파일 확인, 테스트와 팀 협업의 편의를 위해 위 순서를 기본값으로 사용합니다.

---

# 27. 아직 확정하지 않은 계약

다음 내용은 구현과 실험을 거친 뒤 확정합니다.

- 최종 품사 범위
- 사용자 사전의 버전 관리 방식
- 불용어 목록 관리 방식
- 개인투자자 수급 원천과 `supply_demand_index` 계산식 변경 관리
- 모델 재학습·평가·버전 승격 기준
- 실시간 갱신 주기와 집계 범위
- 실제 수급값과 예측 오차의 서비스 제공 여부
- DB 테이블별 DTO

확정되지 않은 내용을 예상만으로 계약에 추가하지 않습니다.

실제 생산자와 소비자가 생기고 재사용 필요성이 확인된 뒤 문서를 확장합니다.

---

# 28. 판단이 어려운 경우

다음 상황에서는 임의로 컬럼을 추가하거나 제거하지 않고 팀장과 논의합니다.

- 같은 의미의 컬럼명이 여러 개 존재하는 경우
- 외부 응답의 필드 의미가 불명확한 경우
- 결측값을 `0` 또는 빈 문자열로 바꿔도 되는지 불명확한 경우
- 시간대가 KST인지 확인되지 않는 경우
- 종목코드 형식이 기존 데이터와 다른 경우
- 토큰이나 벡터를 저장해야 하는 경우
- 기존 계약 컬럼을 제거하려는 경우
- 모델 입력 때문에 데이터 의미가 달라지는 경우
- DB와 분석 코드가 서로 다른 형식을 요구하는 경우

데이터 계약의 목적은 모든 데이터를 미리 고정하는 것이 아닙니다.

현재 확정된 데이터의 의미를 팀 전체가 동일하게 이해하고, 변경이 발생했을 때 영향을 추적할 수 있도록 하는 것입니다.

---

# 29. 댓글 수급 신호 계약

댓글 수급 신호는 기존 Ridge v4의 raw 출력값을 같은 모델의 과거 출력 분포에 상대화한 0~100 값입니다.

이 값은 새 모델의 출력이 아니라 기존 `sentiment_index_result.supply_demand_association_score`를 표현 방식만 바꾼 파생값입니다.

## 의미

> 온라인 투자자 댓글의 언어 패턴과 실제 개인투자자 수급 사이에서 학습된 관계를 기반으로, 현재 댓글에 대한 모델 반응이 과거 동일 수급 방향 대비 어느 정도 수준인지 수치화한 값입니다.

짧게 표현할 때는 `댓글 기반 수급 연계 신호`를 사용합니다.

다음 표현은 코드와 문서에서 사용하지 않습니다.

```text
감성 확률
긍정 확률
부정 확률
상승 확률
하락 확률
미래 수급 예측
```

`50`은 감성 중립이 아니라 과거 동일 모델 출력 분포의 중간 수준입니다.

방향 판단은 신호가 하지 않습니다. 실제 개인투자자 수급 데이터가 결정한 `supply_direction`이 담당합니다.

## 전달 객체

영역 사이의 전달 객체는 `DailyCommentSignal`입니다.

| 필드 | 자료형 | 설명 |
|---|---|---|
| stock_id | integer | 종목 식별자 |
| stock_code | string | 6자리 종목코드 |
| stock_name | string | 종목명 |
| model_date | date | 거래일 |
| daily_document_id | integer | 신호 계산에 사용한 최신 일별문서 |
| comment_count | integer | 이날 집계된 댓글 수 |
| actual_supply_index | float | 실제 개인 수급지수 |
| supply_direction | string | `BUY`, `SELL`, `NEUTRAL` |
| active_model_variant | string \| null | `positive`, `negative` |
| active_result_id | integer \| null | 사용한 `sentiment_index_result_id` |
| active_artifact_id | integer \| null | 사용한 `artifact_id` |
| predicted_score | float \| null | Ridge raw 출력값 |
| recognized_feature_count | integer \| null | 활성 모델이 인식한 특성 수 |
| comment_signal_score | integer \| null | 0 이상 100 이하 |
| signal_level | string \| null | 상대 강도 문구 |
| signal_status | string | `ready`, `insufficient_features`, `no_direction` |
| model_name / model_version / artifact_schema_version | - | 모델 식별 |
| calibration_schema_version | integer | 사용한 calibration 스키마 |

`predicted_score`는 내부 추적·검증용입니다. 화면과 API에 노출하지 않습니다.

## 상태와 결측 기준

| 조건 | signal_status | comment_signal_score |
|---|---|---|
| `actual_supply_index == 0` | `no_direction` | `null` |
| 선택된 활성 결과의 DB `inference_status != ready` | `insufficient_features` | `null` |
| 그 외 | `ready` | 0 이상 100 이하 |

`signal_status`가 `ready`가 아니면 `comment_signal_score`와 `signal_level`은 `null`입니다. 결측을 `0`이나 `50`으로 바꾸지 않습니다.

수급지수가 정확히 0일 때 positive 또는 negative 모델 중 하나를 임의로 선택하지 않습니다.

## 상대 강도 문구

| 구간 | signal_level |
|---|---|
| 0 ~ 19 | 매우 낮음 |
| 20 ~ 39 | 낮음 |
| 40 ~ 59 | 보통 |
| 60 ~ 79 | 높음 |
| 80 ~ 100 | 매우 높음 |

방향은 `supply_direction`이 담당하므로 `긍정`, `부정` 계열 표현을 사용하지 않습니다.

## 비교값

`CommentSignalHistory`는 당일 신호와 비교할 값을 전달합니다.

| 필드 | 자료형 | 설명 |
|---|---|---|
| previous_signal_score | integer \| null | 당일보다 앞선 거래일 중 가장 최근의 `ready` 신호 |
| signal_change | integer \| null | `comment_signal_score - previous_signal_score` |
| signal_ma5 | integer \| null | 당일을 제외한 직전 최대 5거래일 `ready` 신호 평균 |
| history_size | integer | 평균 계산에 사용한 표본 수 |

`signal_ma5`는 당일 값을 포함하지 않습니다. 당일 신호와 비교하는 기준선으로 사용합니다.

신호가 계산되지 않은 날은 비교와 평균에서 제외합니다. 비교 가능한 과거 신호가 없으면 세 값 모두 `null`입니다.

비교값은 신규 테이블 없이 기존 `sentiment_index_result`의 저장된 raw 점수에 같은 calibration을 적용해 계산합니다.

## Flask 전달 계약

Flask 영역은 백분위, 모델 방향 판단, `signal_level`, 모델 artifact 해석을 직접 계산하지 않습니다.

```json
{
  "stock_code": "000660",
  "stock_name": "SK하이닉스",
  "model_date": "2026-08-07",
  "supply_direction": "BUY",
  "actual_supply_index": 0.1951,
  "comment_signal_score": 84,
  "signal_level": "매우 높음",
  "signal_status": "ready",
  "signal_change": 27,
  "signal_ma5": 50,
  "comment_count": 1830,
  "market_commentary": "...",
  "conclusion": "...",
  "notice": "..."
}
```

화면에서 `84 / 100`은 감성 긍정 84점이 아닙니다. 설명이 필요하면 `notice` 문구를 사용합니다.

위 JSON은 v13 보고서 생산자가 제공하는 현재 전달 계약입니다.
`pilos.analysis.llm_report.build_flask_daily_signal_response()`가 같은 필드를
선별합니다. Flask는 백분위 변환이나 신호 등급 계산을 다시 하지 않습니다.

현재 Flask API는 service에서 `build_flask_daily_signal_response()`를 적용한 뒤
저장 당시의 `report_supply_data_status`, `report_supply_observed_at`, 현재 수급의
`current_supply_data_status`, `current_supply_observed_at`과
`report_refresh_status`를 함께 제공합니다. 저장 JSON의 필수 키가 빠지면 HTTP
500으로 처리하고 누락값을 임의로 채우지 않습니다. `detail.js`는 이 v13 필드를
직접 소비하며 과거 `scores`, `narrative`, `representative_comments`에 의존하지
않습니다.

`llm_report.status`의 저장값은 `ready`와 `insufficient_evidence`입니다.
`not_ready`, `not_found`, `failed`는 DB 저장 상태가 아니라 HTTP 조회 결과
상태입니다. 보고서 조회는 최신 `daily_document_id`에 연결된 최신 행만
반환하고 과거 문서 보고서를 현재 보고서로 대체하지 않습니다.

---

# 30. 신호 calibration 아티팩트 계약

calibration은 방향별 Ridge 모델의 과거 출력 분포를 백분위로 보관한 메타데이터입니다.

재추론 원본이 아니라 모델 artifact 성격의 데이터이므로 운영 DB에 적재하지 않습니다. 재추론 전체 행을 저장하는 테이블도 만들지 않습니다.

## 저장 위치

```text
artifacts/calibration/<model_name>_v<model_version>_signal_calibration.json
```

`artifacts`는 Git으로 추적하지 않는 실행 산출물 경로입니다.

## 필드

| 필드 | 자료형 | 설명 |
|---|---|---|
| calibration_schema_version | integer | 현재 `1` |
| generated_at | string | 생성 시각 (Asia/Seoul ISO 8601) |
| source_scope | string | 재추론 범위 식별 문자열 |
| source_row_count | integer | 재추론 CSV 행 수 |
| model_name | string | 모델명 |
| model_version | integer | 모델 버전 |
| artifact_type | string | 아티팩트 종류 |
| artifact_schema_version | integer | 아티팩트 스키마 버전 |
| tokenizer_version | string | 토크나이저 버전 |
| vectorizer_name | string | vectorizer 종류 |
| scaler_name | string | scaler 종류. text-only v4는 `not_used` |
| dataset_start_date | string | 학습 Dataset 시작일 |
| dataset_end_date | string | 학습 Dataset 종료일 |
| variants.positive | object | 양수 방향 백분위 |
| variants.negative | object | 음수 방향 백분위 |

방향별 항목은 다음을 가집니다.

| 필드 | 자료형 | 설명 |
|---|---|---|
| artifact_id | integer | 재추론에 사용한 정확한 아티팩트 |
| sample_count | integer | 재추론 표본 수 |
| quantile_levels | array | `0`부터 `100`까지 1단위 백분위 지점 101개 |
| quantile_scores | array | 각 지점의 실제 `predicted_score` |

`quantile_scores`는 비내림차순이어야 합니다. 로딩 시 길이와 단조성을 검증합니다.

## 생성과 사용 기준

calibration 값은 반드시 실제 재추론 결과에서 산출합니다. 예시값이나 합성값을 production calibration으로 사용하지 않습니다.

calibration은 특정 모델 버전과 1:1로 연결됩니다. 추론에 사용하는 아티팩트와 다음이 하나라도 다르면 신호를 계산하지 않고 오류로 중단합니다.

- `model_name`, `model_version`, `artifact_type`, `artifact_schema_version`
- `tokenizer_version`, `vectorizer_name`, `scaler_name`
- `dataset_start_date`, `dataset_end_date`
- 방향별 `artifact_id`

식별 필드는 모두 `artifacts` 테이블에 실제로 존재하는 컬럼입니다. 테이블에 없는 이름을 식별 값으로 사용하면 값이 항상 비어 검증이 무력화됩니다.

모델을 재학습하면 기존 calibration을 덮어쓰지 않고 새 `model_version` 경로에 저장합니다.

## 방향별 변환 규칙

```text
positive → signal_score = percentile
negative → signal_score = 100 - percentile
```

negative 모델은 더 강한 음수가 해당 방향의 강한 반응이므로 백분위 방향을 뒤집습니다.

분포 최솟값보다 작으면 `0`, 최댓값보다 크면 `100`으로 clamp합니다.

---

# 31. 근거 기반 챗봇 공개 계약

`POST /api/chat`은 자유 문장에서 핵심 식별값을 추측하지 않고 화면에서 선택한
`action`, `metric`, `stock_code`, `model_date`를 받습니다.

| action | 필수 문맥 | 근거 |
|---|---|---|
| `stock_analysis` | 종목·기준일 | 저장된 현재 v13 보고서 |
| `stock_metric` | 종목·기준일·metric | MySQL confirmed 수급 수치 |
| `service_knowledge` | 질문 | 승인 서비스 문서 Chroma RAG |

허용 metric은 `supply_demand_index`, `individual_buy_volume`,
`individual_sell_volume`입니다. 응답은 `status`, `answer`, `route`, `session_id`,
`stock_code`, `as_of`, `sources`, `warnings`를 제공합니다. 공개 source type은
`mysql_metric`, `llm_report`, `service_document`뿐입니다.

`status`는 `ready`, `needs_clarification`, `not_ready`, `not_found`,
`unavailable`, `failed` 중 하나입니다. 투자 지시·미래 수익 보장·비밀정보 요청은
서버 안전 검사에서 `restricted` route로 전환할 수 있으며 오류가 아닌 제한 안내로
반환합니다. 내부 chunk ID·검색 점수·Chroma 경로·프롬프트·API 키는 공개하지
않습니다.

> **CONFLICT — 2026-08-11 구현 감사:** 위 계약과 D-021은 화면이
> `action`·`metric`을 명시적으로 전달한다고 정했지만, 현재 `main@f80fdc2`의
> `pilos/web/app.py`는 공개 요청에서 `action`, `metric`, `message`를 허용하지
> 않습니다. 현재 구현은 다음 두 endpoint에서 서버 allowlist의 `block_key`를
> 필수로 받고, 서버가 해당 블록의 `action`·`metric`·`message`를 채웁니다.
>
> ```text
> POST /api/chat
> POST /api/stocks/<stock_code>/chat
> ```
>
> 허용된 body 필드는 `block_key`, `session_id`, `stock_code`, `model_date`입니다.
> 종목 수치·분석 블록에는 `stock_code`와 `model_date`가 필요하며, 종목 상세
> endpoint에서는 URL의 종목코드를 사용합니다. 현재 공개 블록이 연결하는 route는
> `stock_metric`, `stock_analysis`, `service_knowledge`뿐입니다. 코드에 남은
> `general`, `restricted`와 수급 순위 처리는 공개 블록에서 도달할 수 없습니다.
> 기존 계약을 `block_key`로 대체한다는 결정 기록이 없으므로 이 감사에서는 계약을
> 변경하지 않고 구현 drift를 병기합니다.

---

# 32. 서비스 파이프라인 실행 상태 계약

`service_pipeline_run`의 한 행은 최상위 자동화 한 번의 실행을 나타냅니다.

| 필드 | 의미 |
|---|---|
| status | `running`, `completed`, `failed` |
| target | `all`, `sk`, `others` |
| tokenizer_version / operation_start_date | 실행 계약 식별 |
| started_at / finished_at / elapsed_seconds | KST 실행 시각과 소요시간 |
| stopped_stage / failure_type / failure_message | 실패 위치와 내부 운영 진단 |
| stage_summary | 단계별 상태·시간·내부 실행 요약 JSON |

시작 시 신규 `running` 행을 INSERT하고 종료 시 같은 실행 ID의 running 행만
`completed` 또는 `failed`로 UPDATE합니다. 이 UPDATE는 신규 추론 결과나 기존
보고서를 수정하는 backfill이 아니라 동일 파이프라인 실행 상태를 마감하는 계약입니다.

`GET /api/pipeline/status`는 가장 최근 실행을 반환합니다. 실행 이력이 없으면
`{"status":"not_started"}`이며, 일반 화면에는 원본 내부 결과·파일 경로·원본 오류
문구를 노출하지 않고 단계 상태와 소요시간 및 안전한 실패 문구만 제공합니다.
