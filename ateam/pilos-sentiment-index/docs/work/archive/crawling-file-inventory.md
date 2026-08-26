# 댓글 수집 파일 정리 이력

> 상태: 2026-08-10 저장소 정리 반영 완료. 현재 계약은
> [`specs/comment-crawling.md`](../../../specs/comment-crawling.md)와
> [`specs/comment-preprocessing.md`](../../../specs/comment-preprocessing.md)를 우선한다.

## 유지한 운영 경로

| 역할 | 현재 파일 |
|---|---|
| 증분 수집 | [`pilos/jobs/incremental_comments.py`](../../../pilos/jobs/incremental_comments.py) |
| 백필 수집 | [`pilos/jobs/backfill_comments.py`](../../../pilos/jobs/backfill_comments.py) |
| 전처리 단일 진입점 | [`pilos/jobs/preprocess_comments.py`](../../../pilos/jobs/preprocess_comments.py) |
| 최상위 자동화 | [`pilos/jobs/run_service_pipeline.py`](../../../pilos/jobs/run_service_pipeline.py) |
| 댓글 수집 엔진 | [`pilos/collection/comment_crawler.py`](../../../pilos/collection/comment_crawler.py) |
| 비식별화 | [`pilos/collection/data_masking.py`](../../../pilos/collection/data_masking.py) |
| 원본 파일 저장 | [`pilos/storage/comment_store.py`](../../../pilos/storage/comment_store.py) |
| 매니페스트 | [`pilos/storage/manifest.py`](../../../pilos/storage/manifest.py) |
| 원본 파일 DB 등록 | [`pilos/storage/comment_db.py`](../../../pilos/storage/comment_db.py) |
| 전처리 DB 적재 | [`pilos/storage/preprocess_db.py`](../../../pilos/storage/preprocess_db.py) |

## 유지보수 도구로 분리한 파일

- [`register_raw_comment_files.py`](../../../pilos/jobs/maintenance/register_raw_comment_files.py):
  기존 원본 파일의 `source_comment_file` 등록
- [`initialize_comment_data.py`](../../../pilos/jobs/maintenance/initialize_comment_data.py):
  초기 원본 등록 후 백필을 포함한 미처리 댓글 전처리
- [`rebuild_comment_manifest.py`](../../../pilos/jobs/maintenance/rebuild_comment_manifest.py):
  기존 원본 파일 기준 매니페스트 재작성
- [`anonymize_legacy_comments.py`](../../../pilos/jobs/maintenance/anonymize_legacy_comments.py):
  인라인 마스킹 도입 전 과거 원본의 일회성 보정

이 도구들은 주기적으로 실행하는 서비스 파이프라인에 포함하지 않는다.

## 제거한 중복·구버전 경로

- `collection/comment_preprocessing.py`, `jobs/today_preprocess_comments.py`:
  `jobs/preprocess_comments.py`로 통합
- `jobs/incremental_and_preprocess.py`, `jobs/backfill_and_preprocess.py`:
  최상위 실행기가 공식 `run_*` 함수를 직접 조합하므로 제거
- `collection/load_comments_to_db.py`와 `CommentDB.insert()`:
  현재 `stock_id` 기반 적재 계약과 다른 legacy DB 경로라 제거
- `collection/refine_json.py`: 현재 매니페스트 구현과 중복돼 제거
- `storage/kiwoomapi.py`: 현재 수급 수집 실행 경로와 무관한 구버전 독립 구현이라 제거

삭제 파일의 과거 구현과 판단 근거는 Git 이력에서 복원할 수 있다.
