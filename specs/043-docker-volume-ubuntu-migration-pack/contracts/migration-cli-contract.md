# Contract: Migration CLI (`make_migration_pack.py`)

**Component**: `make_migration_pack.py`  
**Purpose**: Windows 소스 환경에서 DB 덤프, 볼륨 아카이브, 소스 번들링, 매니페스트 생성을 관장하는 CLI 도구

---

## 1. CLI Usage & Flags

```bash
python make_migration_pack.py [OPTIONS]
```

| Flag | Type | Default | Description |
|:---|:---:|:---:|:---|
| `--output-dir` | Path | `./dist` | 패키징 산출물이 저장될 디렉터리 경로 |
| `--include-volumes` | Flag | `True` | Docker named volume 물리 데이터 포함 여부 |
| `--include-models` | Flag | `False` | 대용량 모델 가중치 파일 번들 포함 여부 |
| `--target-os` | String | `ubuntu` | 타겟 OS 플랫폼 (`ubuntu`, `linux`, `generic`) |
| `--target-cpu` | String | `i7-930` | 타겟 CPU 아키텍처 (`i7-930`, `avx2`, `native`) |
| `--target-gpu` | String | `gtx1070` | 타겟 GPU 아키텍처 (`gtx1070`, `sm_61`, `sm_80`, `sm_89`, `none`) |
| `--skip-gpu` | Flag | `False` | GPU 설치·JIT·GPU Compose 경로를 생략하고 manifest에 CPU-only 모드 기록 |
| `--format` | String | `tar.gz` | 아카이브 형식 (`tar.gz`, `zip`, `both`). `both`는 두 형식을 병렬 생성 |
| `--key-file` | Path | `MIGRATION_PACK_KEY_FILE` | 아카이브 암호화 키 경로. 키는 결과 아카이브에 포함하지 않음 |
| `--dry-run` | Flag | `False` | 실제 압축 없이 사전 요구사항, DB 연결, 볼륨 크기, 디스크 공간 점검 |
| `--force` | Flag | `False` | 기존 아카이브 덮어쓰기 및 비대화형 강제 실행 |

---

## 2. Exit Codes

- `0`: 패키징 완료 및 무결성 체크섬 생성 성공.
- `1`: 필수 환경변수(`.env`) 누락 또는 설정 오류.
- `2`: MySQL 컨테이너 연결 실패 또는 덤프 생성 에러.
- `3`: Docker 볼륨 아카이빙 실패.
- `4`: 디스크 공간 부족 (최소 25GB 미만).
- `5`: SHA-256 해시 생성 불일치.
- `6`: 아카이브 암호화 또는 외부 키 경로 검증 실패.

---

## 3. Standard Output Format

```text
[INFO] =======================================================
[INFO] AISERVICE Ubuntu Migration Pack Builder v2.0
[INFO] Source: Windows 11 (WSL2/Docker) -> Target: Ubuntu 24.04 LTS
[INFO] Target Profile: Intel Core i7-930 (SSE4.2) / GTX 1070 8GB (sm_61)
[INFO] =======================================================
[INFO] [1/5] Exporting MySQL Databases (InnoDB Safe Flush)...
[INFO]   - pilos_v2: 3,421,890 rows -> database/pilos_v2.sql.gz (SHA256: e3b0c442...)
[INFO]   - oliview_project: 48,210 rows -> database/oliview_project.sql.gz (SHA256: 7f83b165...)
[INFO] [2/5] Exporting Docker Named Volumes (Sparse Mode)...
[INFO]   - ateam_db_data -> volumes/ateam_db_data.tar.gz
[INFO]   - bteam_bteam_mysql_data -> volumes/bteam_bteam_mysql_data.tar.gz
[INFO]   - green_mysql_data -> volumes/green_mysql_data.tar.gz
[INFO]   - green_chroma_data -> volumes/green_chroma_data.tar.gz (WAL Checkpointed)
[INFO]   - aiservice_redis_data -> volumes/aiservice_redis_data.tar.gz (BGSAVE Complete)
[INFO] [3/5] Assembling Clean Source Bundle (Encrypted Zero-Config .env)...
[INFO]   - Bundled root .env and ddns/.env inside the encrypted archive
[INFO]   - Excluded .git, .venv, node_modules, __pycache__ (0 cached items)
[INFO] [4/5] Generating Manifest v2.0 & Checksums...
[INFO]   - migration_manifest.json (v2.0.0, bundle service inventory recorded)
[INFO]   - checksums.sha256 generated
[INFO] [5/5] Compressing Final Migration Archive...
[INFO] Archive Created: dist/AISERVICE_Migration_Pack_20260828_163500.tar.gz.enc
[INFO] Status: SUCCESS (Exit Code 0)
```
