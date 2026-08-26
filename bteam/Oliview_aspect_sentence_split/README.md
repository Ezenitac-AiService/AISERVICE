# 속성별 리뷰 구절 분리 모델

AI Hub 화장품 리뷰의 `RawText`, `Aspect`, `SentimentText`를 이용해 리뷰에서
속성별 원문 구절을 추출합니다.

## 모델 방식

- 모델은 하나만 학습합니다.
- 입력은 `속성명 + 리뷰 원문`입니다.
- 출력은 해당 속성에 속하는 원문의 모든 구간입니다.
- 속성별 조건부 BIO 태깅을 사용하므로 서로 겹치는 속성 구간도 학습할 수 있습니다.
- 학습 라벨은 기존 `aspect_sentiment` 프로젝트에서 정규화한 이름을 그대로 사용합니다.

## 데이터 준비

기본 설정은 기존 프로젝트의 다음 파일을 읽습니다.

```text
../aspect_sentiment/data/aspect/train.csv
../aspect_sentiment/data/aspect/validation.csv
../aspect_sentiment/data/aspect/test.csv
```

```bash
python scripts/prepare_data.py
```

생성 결과:

- `data/train.jsonl`
- `data/validation.jsonl`
- `data/test.jsonl`
- `data/labels.json`
- `data/reports/*_unmatched.csv`
- `data/reports/summary.json`

## 학습

설명과 함께 단계별로 실행하려면 다음 노트북을 사용

```text
notebooks/01_aspect_span_training.ipynb
```

바로 학습

```bash
python scripts/train.py
```

기본 모델은 `klue/roberta-base`, 저장 위치는
`models/aspect_span_extractor`입니다. 경로와 설정은 `config.json`에서 변경

## 추론

```bash
python predict.py --text "촉촉하지만 지속력이 짧고 모공에 끼어요."
```

출력 예:

```json
[
  {
    "aspect": "보습력/수분감",
    "aspect_phrase": "촉촉하지만"
  },
  {
    "aspect": "지속력/유지력",
    "aspect_phrase": "지속력이 짧고"
  }
]
```

서비스에서 속성 이름을 바꿀 때는 모델을 다시 학습하지 않고 출력 단계에서
`보습력/수분감`을 `수분감`처럼 매핑
