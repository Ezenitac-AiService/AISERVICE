# AISERVICE 비밀 환경변수 및 DDNS 마이그레이션 팩 가이드

GitHub 정책(`.gitignore`)상 원격 저장소에 커밋되지 않는 **비밀 환경변수(`.env`)** 및 **DuckDNS XML 설정(`ddns/duckdns-config.xml`)**을 안전하게 추출(Pack)하여 새 서버로 원클릭 복원(Restore)하는 가이드입니다.

---

## 1. 마이그레이션 대상 파일 구성 (총 11개)

1. **전역 및 인프라 `.env`**:
   - `/.env` (MySQL Root/App 암호, DuckDNS 토큰, 게이트웨이 포트)
   - `model_gateway/.env` (GPU VRAM 및 슬롯 파라미터)
   - `ddns/.env` (DuckDNS 갱신 토큰)
2. **A-Team PILOS `.env`**:
   - `ateam/pilos-sentiment-index/.env` (뉴스 크롤러 API 키 및 DB 계정)
3. **B-Team Oliview `.env`**:
   - `bteam/.env` (DB URL, Redis 포트, Chat Bearer Secret)
   - `bteam/Oliview_chatbot_a/.env`
   - `bteam/Oliview_Project/.env`
   - `bteam/Oliview_LLM/.env`
   - `bteam/Oliview_aspect_sentence_split/.env`
   - `bteam/Oliview_aspect_sentiment/.env`
4. **DDNS 자동 갱신 XML**:
   - `ddns/duckdns-config.xml`

---

## 2. 소스 서버에서 패키징 (Pack)

소스 서버 터미널(Git Bash, PowerShell 또는 Linux Shell)에서 아래 명령어를 실행합니다.

```bash
# Linux / macOS / Git Bash
./scripts/pack_secrets.sh

# Windows CMD / PowerShell
.\scripts\pack_secrets.bat

# 또는 uv 직접 실행
uv run --project bteam python scripts/pack_secrets.py
```

- **생성 파일**: `dist/secrets_pack.tar.gz` (내부에 무결성 검증용 `secrets_manifest.json` 자동 포함)

---

## 3. 타겟 서버로 전송 (Transfer)

안전한 채널(SCP, SFTP, 암호화 USB 등)을 통해 `dist/secrets_pack.tar.gz` 파일을 타겟 서버로 복사합니다.

```bash
# SCP 전송 예시
scp dist/secrets_pack.tar.gz user@target-server:/path/to/AISERVICE/dist/
```

---

## 4. 타겟 서버에서 복원 (Restore)

타겟 서버에서 코드를 `git clone`한 후, 프로젝트 루트에서 복원 스크립트를 실행합니다.

```bash
# 1. 드라이런 (실제 쓰기 없이 무결성 및 파일 목록 사전 확인)
./scripts/restore_secrets.sh --dry-run

# 2. 원클릭 실제 복원 (기존 파일이 있을 경우 .bak 백업 자동 생성)
./scripts/restore_secrets.sh

# Windows 환경 복원
.\scripts\restore_secrets.bat
```

### 복원 주요 특징:
- **SHA-256 무결성 검증**: 아카이브 내부 파일이 변조되었을 경우 복원을 즉시 중단하고 에러 발생.
- **권한 자동 보호 (Linux/macOS)**: 복원된 모든 `.env` 파일에 `chmod 600` (소유자 읽기/쓰기 전용)을 자동 적용.
- **안전 백업**: 기존 파일이 존재할 경우 `*.bak.<timestamp>`로 자동 백업 후 복원.

---

## 5. 복원 후 서비스 기동 검증

```bash
# 도커 컨테이너 기동
docker compose up -d

# 게이트웨이 및 서비스 응답 확인
curl -I http://localhost/
curl -I http://localhost/changelog
```
