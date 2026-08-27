# Phase 1 Red Test Result

기준선 실행 시각: 2026-08-27 (Asia/Seoul)

실행 명령:

```text
C:\AISERVICE\bteam\Oliview_chatbot_a\.venv\Scripts\pytest.exe tests\characterization tests\unit tests\contract tests\security -q
```

구현 전 결과: **8개 collection error**.

- `pipelines.pipeline_selection`이 아직 존재하지 않아 selector 계약을 수집하지 못함
- `oliview_core.retry`, `config`, `db.models`, `gateway`, `db.lease`, `reports`, `logging`이 아직 존재하지 않아 Core 계약을 수집하지 못함
- 실패는 구현 부재에 의한 의도된 Red이며, Blue characterization 파일 자체의 assertion failure가 아님

구현 후 기준선:

- Core/pipeline/DB/gateway/report/logging 계약 및 characterization: `19 passed`
- Frontend locked install: `npm ci` 성공
- Frontend lint/build: `npm run lint`, `npm run build` 성공

이 artifact는 테스트 fixture를 구현 결과에 맞춰 변경하지 않고, 구현 전 Red와 구현 후 Green을 구분하기 위해 보존한다.

