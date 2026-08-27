# B-Team 복구 및 checksum 절차

이 절차는 Blue 운영 자산을 읽기 전용으로 기준선화하고 Green 검증용 복제본을 만드는 방법이다.

1. `inventory.json`을 먼저 생성하고 secret 파일은 파일명·키 이름·redacted 여부·SHA-256만 기록한다. 값, SQL dump 내용, Chroma 문서, Redis payload는 기록하지 않는다.
2. 원본 소스·설정·모델은 `build_manifest.py`로 파일별 SHA-256을 계산한다. `.venv`, `node_modules`, `__pycache__`, `.pytest_cache`, `dist`, `build`는 manifest에서 제외하고 제외 목록을 artifact에 남긴다.
3. DB는 Blue volume을 attach하거나 dump를 덮어쓰지 않고 별도 Green MySQL에 복원한다. 복원 후 schema/table count와 주요 FK를 검증하고 Green endpoint가 Blue endpoint와 다름을 기록한다.
4. Chroma v1 snapshot은 `oliview_review_sentences`를 read-only로 보존한다. citation용 Green v2는 별도 `oliview_review_sentences_v2` collection으로 생성하며 v1 파일을 수정하지 않는다.
5. Redis는 Blue 인스턴스에 `FLUSHDB`, 전역 wildcard 삭제, production `KEYS`/`SCAN`을 실행하지 않는다. Green validation은 격리 Redis를 사용하고 legacy key는 inventory 분류 결과에 따라 exact target 또는 bypass/isolated 정책으로만 다룬다.
6. 복구 검증 실패 시 Green을 중지하고 artifact를 보존한다. Blue 원본·컨테이너·network·volume은 변경하지 않는다.
7. cutover와 decommission은 외부 변경 권한자의 승인 artifact가 없으면 실행하지 않는다. 승인 전에는 이 절차가 Blue를 archive하거나 삭제하지 않는다.
