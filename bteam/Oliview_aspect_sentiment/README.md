# Aspect Sentiment

화장품 리뷰의 속성과 감성을 분류하는 프로젝트입니다.

## 현재 속성 데이터 정책

- 원본 서비스 속성 29개를 기준으로 합니다.
- 모든 카테고리(스킨케어, 메이크업/뷰티소품, 헤어/바디케어, 남성화장품)를 읽습니다.
- 다른 카테고리 전용 속성은 추가하지 않고, 기존 29개 속성에 해당하는 문장만 사용합니다.
- `기능/효과`는 제외하지 않습니다.
- 의미가 중복되는 네 그룹만 통합합니다.
  - `보습력/수분감/쿨링감` → `보습력/수분감`
  - `용량/개수` → `용량`
  - `지속력` → `지속력/유지력`
  - `탄력` → `탄력/주름 개선`
- 최종 모델 출력 라벨은 26개입니다.

## 데이터 준비

```bash
python scripts/prepare_aspect_data.py
```

원본 `data/raw/train.json`, `data/raw/validation.json`에서 다음 파일을 생성합니다.

- `data/aspect/train.csv`
- `data/aspect/validation.csv`
- `data/aspect/test.csv`
- `data/aspect/label2id.json`, `id2label.json`
- 전처리 요약과 라벨 변경·충돌 보고서

Validation과 Test는 원본 Validation을 리뷰 단위로 분리하므로 같은 리뷰가 두 분할에 섞이지 않습니다.

## 학습과 서비스 테스트

- `notebooks/03_train_aspect_classifier.ipynb`: 속성 모델 학습·평가
- `notebooks/04_prepare_service_aspects.ipynb`: 실제 리뷰 속성·감성 테스트
- 새 속성 모델 저장 위치: `models/aspect_26_all_categories/`

라벨 정책과 경로는 루트의 `aspect_labels.json`에서 관리합니다.
