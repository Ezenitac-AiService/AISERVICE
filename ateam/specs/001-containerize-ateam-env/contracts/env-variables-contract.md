# Environment Variables Contract: `.env`

## 1. 개요

본 문서는 A-Team 컨테이너 애플리케이션 및 DBMS 서비스가 요구하는 환경 변수 계약을 정의합니다. `pilos-sentiment-index/.env.example`을 기반으로 컨테이너 내부 환경에 맞게 확장된 설정 규격입니다.

---

## 2. 필수 및 선택 환경변수 목록

```ini
# ==========================================
# 1. Host Port Configuration (B-Team 충돌 방지)
# ==========================================
WEB_PORT=8080
DB_PORT=3307

# ==========================================
# 2. Flask Web Application Configuration
# ==========================================
FLASK_SECRET_KEY=dev_secret_key_change_in_prod
PORT=5000

# ==========================================
# 3. Database Connection Configuration (Internal Container Network)
# ==========================================
DB_HOST=db
DB_PORT=3306
DB_USER=root
DB_PASSWORD=pilos_password
DB_NAME=pilos_v2
DB_ROOT_PASSWORD=pilos_root_pass

# ==========================================
# 4. De-identification Salts (보안 해시 솔트)
# ==========================================
SECRET_SALT=pilos_salt_1
SECRET_SALT2=pilos_salt_2

# ==========================================
# 5. LLM Container Connection Configuration (aiservice-network)
# ==========================================
LLM_PROVIDER=openai
LLM_BASE_URL=http://llm-server:8000/v1
LLM_API_KEY=EMPTY

# Chatbot LLM
CHAT_LLM_MODEL=qwen2.5-14b-instruct
CHAT_LLM_TIMEOUT_SECONDS=30

# LLM Report Generation
REPORT_LLM_MODEL=qwen2.5-14b-instruct
REPORT_LLM_OUTPUT_MODE=json_object
REPORT_LLM_TIMEOUT_SECONDS=60

# ==========================================
# 6. Embedding & Reranker Configuration
# ==========================================
EMBEDDING_BASE_URL=http://llm-server:8000/v1
EMBEDDING_API_KEY=EMPTY
EMBEDDING_MODEL=bge-m3
EMBEDDING_TIMEOUT_SECONDS=120

RERANK_BASE_URL=http://llm-server:8000
RERANK_API_KEY=EMPTY
RERANK_MODEL=bge-reranker-v2-m3
RERANK_TIMEOUT_SECONDS=120

SERVICE_KNOWLEDGE_VERSION=1.0
```

---

## 3. 보안 및 거버넌스 준수 사항 (Security Rules)

1. `.env` 파일은 절대로 Git 저장소에 커밋되지 않아야 합니다(`.gitignore` 등록 필수).
2. 실제 LLM API 키 또는 데이터베이스 비밀번호는 배포 시점에 주입받아야 합니다.
