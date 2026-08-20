# Phase 0 Research: 028-cross-platform-migration-pack

**Feature**: [spec.md](file:///c:/AISERVICE/specs/028-cross-platform-migration-pack/spec.md)  
**Date**: 2026-08-20  
**Status**: Completed  

---

## 1. 데이터베이스 덤프 및 복원 최적화 (Database Dump & Restore)

### Decision 1: MySQL 8.0 대용량 무손실 덤프 파이프라인
- **결정 (Chosen)**:
  `mysqldump`를 컨테이너 내부(`pilos-db`, `bteam_db`)에서 직접 실행하며, `--single-transaction --quick --routines --triggers --events --hex-blob --default-character-set=utf8mb4 --max_allowed_packet=512M` 옵션과 `gzip -9` 압축 파이프라인을 적용합니다.
- **근거 (Rationale)**:
  - `pilos_v2`는 약 3.4GB (434만 건의 토큰화 댓글), `oliview_project`는 약 950MB (5.7만 건의 1024차원 BGE-M3 임베딩 벡터)입니다.
  - `--single-transaction` 및 `--quick`을 통해 덤프 중에도 서비스 락(Lock)을 최소화하고 OOM을 방지합니다.
  - `--hex-blob`은 `review_aspect_sentences` 테이블의 바이너리/JSON 임베딩 벡터 데이터가 문자열 치환 과정에서 손상되는 것을 완벽히 방지합니다.
  - `gzip -9` 압축 시 전체 4.35GB의 원본 데이터베이스가 약 **460MB** 내외로 압축되어 네트워크 전송 및 아카이빙 효율을 90% 이상 극대화합니다.
- **대안 비교 (Alternatives Evaluated)**:
  - *물리적 데이터 디렉터리(`/var/lib/mysql`) 원시 복사*: MySQL 버전/OS 파일시스템(NTFS vs ext4) 간 호환성 문제 및 데이터 깨짐 위험이 높아 기각.
  - *CSV/JSON 데이터만 추출*: 뷰(View), 저장 프로시저, 인덱스, 트리거 구조 복구에 수작업이 소요되므로 기각.

---

## 2. 크로스 플랫폼 스크립트 아키텍처 (Cross-Platform Scripting)

### Decision 2: Dual-Platform (Bash & Batch/PowerShell) 자동화 지원
- **결정 (Chosen)**:
  - Linux/macOS/WSL2 타겟: POSIX 호환 Shell Script (`export_databases.sh`, `bootstrap_restore.sh`, `pack_archive.sh`)
  - Windows 호스트 타겟: Windows Batch/PowerShell 호환 Script (`export_databases.bat`, `bootstrap_restore.bat`, `pack_archive.bat`)
  - 통합 검증기: Python 3 표준 라이브러리(`urllib.request`, `json`, `hashlib`) 기반의 `verify_migration.py`
- **근거 (Rationale)**:
  - 현재 소스 호스트가 Windows 환경이고, 이전 대상 호스트가 Linux(Ubuntu 22.04/24.04, AWS EC2, GCP) 또는 또 다른 Windows 서버일 수 있습니다.
  - 타겟 플랫폼에 추가 툴 설치(Python 서드파티 패키지 등) 요구를 최소화하여 원클릭 실행성을 보장합니다.

---

## 3. 환경 변수 및 시크릿 주입 전략 (Environment & Secrets Strategy)

### Decision 3: 다중 환경 템플릿 및 자동 프로파일러
- **결정 (Chosen)**:
  `migration_pack/config/.env.migration.template`을 정의하고, 부트스트랩 스크립트 실행 시 타겟 서버의 환경(호스트 IP, 도메인, 게이트웨이 포트, GPU 지원 모드)을 자동 감지하거나 대화형으로 입력받아 루트 `.env`, `ateam/.env`, `bteam/.env`, `model_gateway/.env`에 일괄 동기화 주입합니다.
- **근거 (Rationale)**:
  - 타겟 서버의 포트(80 vs 8080)나 IP 주소가 다를 때 발생하는 프록시 불일치를 사전에 방지합니다.
  - 비밀키(DB 패스워드, Flask Secret, API 토큰 등)가 안전하게 유지되도록 마스킹 및 템플릿 분리를 적용합니다.

---

## 4. AI 모델 가중치 배포 및 오프라인 전략 (Model Strategy)

### Decision 4: 경량 팩 기본 + 폐쇄망용 오프라인 번들러 (Hybrid Model Packaging)
- **결정 (Chosen)**:
  - **기본 팩 (Default)**: 모델 가중치 파일을 제외하고 DB 덤프와 코드/설정만 묶어 약 500MB 미만의 경량 팩으로 배포. 타겟 서버 기동 시 HuggingFace 캐시 또는 온라인 모델 다운로더를 통해 자동 캐싱.
  - **폐쇄망 도구 (Offline Tool)**: 인터넷이 차단된 환경을 위해 소스 서버의 모델 가중치(`/root/.cache/huggingface` 또는 로컬 모델 경로)를 아카이브로 추출하는 `export_offline_models.sh/.bat` 도구 별도 제공.
- **근거 (Rationale)**:
  - 일반적인 클라우드/개발 서버 이전 시 8GB에 달하는 모델 가중치를 전송하는 대역폭 낭비를 줄이고, 특수 폐쇄망 요구사항까지 동시에 완벽 지원합니다.

---

## 5. 엔드포인트 무결성 검증 아키텍처 (Verification Architecture)

### Decision 5: 11개 엔드포인트 E2E 자동 검증기 (`verify_migration.py`)
- **결정 (Chosen)**:
  복원 직후 다음 11개 엔드포인트를 순차 테스트하여 JSON 결과 리포트를 발행합니다.
  1. `aiservice-gateway` (HTTP 80 / 8080)
  2. `vllm-serv-gateway` 헬스체크 (`8081/health`)
  3. `vllm-serv-gateway` 모델 목록 (`8081/v1/models`)
  4. Qwen LLM Chat 추론 (`8081/v1/chat/completions`)
  5. BGE-M3 텍스트 임베딩 (`8090/v1/embeddings`)
  6. BGE-Reranker-v2-m3 (`8091/v1/rerank`)
  7. A-Team Pilos Web 대시보드 (`5000/`)
  8. B-Team Oliview Backend (`5050/health`)
  9. B-Team Oliview Frontend (`5173/`)
  10. B-Team 올리챗 A (`8501/`)
  11. B-Team 올리뷰챗 B (`8002/`)
  - 추가: `pilos_v2` 및 `oliview_project` DB 테이블 레코드 수 일치율 검사.
