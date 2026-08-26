# 키움 개인 수급 수집 기능 명세

## 상태

- 구현 상태: 장중 추정, 장마감 확정, 과거 확정 백필, 상태 보존 DB 적재
  실행기 구현 완료
- 검증 상태: analysis·collection·job·storage 자동 테스트와 실제 최상위 실행
  확인. 2026-08-10 실행에서 대상 10종목의 확정 상태를 확인
- 통합 상태: `main@f80fdc2` 반영 완료 (PR #6, #17)

## 목적

종목·거래일별 개인투자자 매수량, 매도량과 수급지수를 수집해
`supply_demand`에 저장한다. 장중에는 추정값을 제공하고 장마감 이후에는
확정값으로 승격하되 두 원천의 이력을 모두 보존한다.

## 포함 범위

- 키움 접근 토큰 발급과 인증 만료 1회 재시도
- 장중 `ka10063` 외국인·기관·기타법인 데이터 수집
- 장중 개인 수급 잔차 추정과 품질 진단값 계산
- 장마감 `ka10060` 개인 매수·매도 확정값 수집
- 과거 기간 확정값 백필
- `estimated`·`confirmed` 상태와 원천별 필드 저장
- 확정 행의 추정 상태 강등 방지
- KST 시각에 따른 auto 실행 판정
- 명시적인 DB 쓰기 안전장치

다음은 제외한다.

- 댓글 수집과 전처리
- 모델 학습·추론
- Flask HTTP 요청 중 키움 API 호출
- 키움 실시간 체결 WebSocket `0B`
- 스케줄러와 전체 파이프라인 자동화

## 실행 진입점

```powershell
uv run python -m pilos.jobs.collect_supply_demand --action auto
uv run python -m pilos.jobs.collect_supply_demand --action estimate
uv run python -m pilos.jobs.collect_supply_demand --action confirm
uv run python -m pilos.jobs.collect_supply_demand --action backfill --start-date YYYYMMDD --end-date YYYYMMDD
```

`auto`는 KST와 환경설정 시각을 기준으로 동작한다.

| 구간 | 동작 |
|---|---|
| 주말·장 시작 전 | skip |
| 장중 시작~15:30 | estimate |
| 장 마감 후~확정 수집 시각 전 | skip |
| 기본 15:50 이후 | confirm |

시각은 `KIWOOM_MARKET_OPEN_TIME`, `KIWOOM_MARKET_CLOSE_TIME`,
`KIWOOM_FINAL_COLLECTION_TIME`으로 설정할 수 있다.

## 장중 추정

`ka10063`에서 다음 세 투자자 분류의 매수·매도량과 원천 누적거래량을
수집한다.

```text
foreigner
institution
other_corporation
```

세 요청의 원천 누적거래량 중앙값을 추정 기준 거래량으로 사용한다. 개인
매수·매도량은 기준 거래량에서 세 비개인 분류의 합을 뺀 잔차다.

```text
individual_buy = estimation_base_trade_volume - non_individual_buy
individual_sell = estimation_base_trade_volume - non_individual_sell
```

음수 잔차, 0인 기준 거래량, 누락 투자자 분류와 종목 불일치는 오류다.
원천 거래량의 최소·최대·차이·차이 비율을 함께 저장해 추정 품질을 추적한다.

## 장마감 확정과 백필

`ka10060`을 매수(`trade_type=1`)와 매도(`trade_type=2`)로 각각 호출해
개인투자자 확정값을 수집한다. 확정 실행은 이미 `confirmed`인 종목을
제외하고, 데이터가 아직 비어 있으면 설정된 횟수만큼 재시도한다.

백필은 KST 기준 오늘 이전 기간만 허용한다. 시작일이 종료일보다 늦거나
종료일이 오늘 이상이면 실행하지 않는다.

## 수급지수

매수·매도량은 0 이상의 정수이며 지수는 다음과 같다.

```text
supply_demand_index = (buy_volume - sell_volume) / (buy_volume + sell_volume)
```

결과 범위는 `-1.0~1.0`이다. 두 거래량이 모두 0이면 지수를 만들지 않는다.

## 저장과 재실행

- `SUPPLY_DEMAND_DB_WRITE_ENABLED=true`가 아니면 DB 쓰기를 거부한다.
- 종목코드는 `stock` 테이블에 존재해야 한다.
- 종목·거래일 고유키를 기준으로 추정값은 갱신할 수 있다.
- 추정 적재는 이미 확정된 현재 유효값과 `data_status`를 낮추지 않는다.
- 확정 적재는 확정 전용 필드와 현재 유효 필드를 함께 갱신한다.
- 추정·확정 원천 필드는 서로 덮어쓰지 않는다.
- API 성공이나 적재 대상 없음은 `skipped` 사유로 구분하고, 수집·계산·
  저장 오류는 CLI 종료 코드 1로 전달한다.

## 후속 소비자 계약

- 모델 학습은 `data_status='confirmed'`만 사용한다.
- 현재 모델 추론은 수급 행의 존재를 거래일 eligibility로 사용하고 상태를
  필터링하지 않는다.
- LLM 보고서는 현재 수급 방향이 선택한 활성 추론 결과를 사용하고,
  `data_status`·`observed_at`을 v13 요청과 저장 결과에 전달한다.
- Flask 화면은 `estimated`·`confirmed`와 관측 시각을 표시한다.
- 같은 v13 보고서는 추정→확정 또는 더 최신 추정 관측에서만 갱신하며,
  확정→추정 강등을 금지한다.

## 검증

현재 저장소에는 다음 자동 테스트가 있다.

- `tests/test_supply_demand_analysis.py`
- `tests/test_supply_demand_collection.py`
- `tests/test_supply_demand_job.py`
- `tests/test_supply_demand_storage.py`

테스트는 계산식, API 응답 변환, 시각 판정, 확정 강등 방지 SQL,
`confirmed` 학습 필터와 DB 쓰기 안전장치를 검증한다. 전체 테스트와 실제
최상위 실행 결과는 발표 기준서에 함께 기록한다.

## 관련 코드와 정본

- [`pilos/jobs/collect_supply_demand.py`](../pilos/jobs/collect_supply_demand.py)
- [`pilos/collection/kiwoom_supply_demand.py`](../pilos/collection/kiwoom_supply_demand.py)
- [`pilos/analysis/supply_demand.py`](../pilos/analysis/supply_demand.py)
- [`pilos/storage/supply_demand_db.py`](../pilos/storage/supply_demand_db.py)
- [`pilos/dto/supply_demand_dto.py`](../pilos/dto/supply_demand_dto.py)
- [`docs/DATA_CONTRACT.md`](../docs/DATA_CONTRACT.md)
- [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
- [`docs/DECISIONS.md`](../docs/DECISIONS.md)
