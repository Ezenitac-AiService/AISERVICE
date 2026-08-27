# Green snapshot/recovery dry-run

이 문서는 운영 Blue에 쓰지 않는 별도 절차다.

1. `oliview_project_backup_0813.sql`의 SHA-256과 크기를 inventory에 기록한다.
2. MySQL dump를 Green 전용 MySQL volume에 복구하고 row-count/checksum 검증을 저장한다.
3. Blue Chroma `chroma_db_oliview/chroma.sqlite3`를 Green 전용 persistence로 복제하고 v1 collection을 read-only로 확인한다.
4. Green Redis는 빈 전용 volume으로 시작한다. legacy hash key를 `SCAN`, `KEYS`, `FLUSHDB`하지 않는다.
5. `MYSQL_WRITE_ENDPOINT`, `CHROMA_WRITE_ENDPOINT`, `REDIS_ENDPOINT`가 Blue endpoint와 다름을 연결 manifest로 검증한다.
6. 실패 시 Green volume만 폐기하고 snapshot은 보존한다. Blue container/network/volume/bind mount는 변경하지 않는다.

실제 복구 결과는 `migration/artifacts/`에 operator가 저장하며, `DATA_MIGRATION_READY` 없이는 운영 endpoint를 바꾸지 않는다.

