# 🎓 vllm_serv AI 서비스 개발자 양성과정 교육용 예제 실습 가이드

본 폴더(`sample/`)는 **AI 서비스 개발자 양성과정 비전공자 훈련생**을 위해 준비된 **httpx REST API & OpenAI 파이썬 공식 SDK 1:1 대칭 모듈형 실습 수트 (총 11단계, 22종)**입니다.

모든 실습 스크립트는 **각 파일당 50~70라인 이하의 초슬림/초집중 구조**로 작성되어 훈련생이 단 하나의 핵심 개념만 직관적으로 학습할 수 있으며, **하드코딩 0%, 목업 0%, 우회 로직 0%**의 엄격한 4대 개발 원칙을 준수하여 100% 라이브 서버로 동작합니다.

---

## 🖥️ GTX 1070 (8GB) 3종 동시 서빙 VRAM 산출 및 가용 모델 규격

본 실습 환경은 **NVIDIA GeForce GTX 1070 (8.0 GB VRAM)** 한 대에서 **LLM 대화(8081), BGE-M3 임베딩(8090), BGE-Reranker v2(8091) 3개 데몬을 동시에 가동**하는 분배 구조로 운용됩니다.

### 📊 3종 데몬 동시 서빙 VRAM 분배표
- **GPU 전체 VRAM**: **8,192 MB (8.0 GB)**
- **임베딩 데몬 (`bge-m3`, 8090 포트)**: 약 **1,500 MB** 점유
- **리랭커 데몬 (`bge-reranker-v2-m3`, 8091 포트)**: 약 **1,500 MB** 점유
- **LLM 메인 데몬 (8081 포트 가용 잔여 VRAM)**: **약 5,192 MB (약 5.1 GB)**

### 🎯 모델별 정밀 안전 맥락 한계 (Safe Context Window)

| 모델명 (Model ID) | VRAM 가용 상한선 | 안전 맥락 윈도우 (`max_safe_n_ctx`) | 비고 / 서비스 상태 |
| :--- | :---: | :---: | :--- |
| **`qwen3.5-4b`** (메인) | ~4.5 GB | **`4096` (4K)** | 메인 대화 모델 (4K 안전 맥락) |
| **`qwen3.5-2b`** (경량) | ~3.0 GB | **`6144` (6K)** | 초경량 모델 (6K 여유 맥락) |
| **`qwen3.5-9b`** (대형) | > 5.0 GB (상한 초과) | **`2048` (2K CAP)** | VRAM 제한 모드 (2K 제한 가동) |
| **`gemma4-e2b`** (경량) | ~3.2 GB | **`6144` (6K)** | Gemma 소형 모델 (6K 안전 맥락) |
| **`gemma4-e4b`** (중형) | ~4.6 GB | **`4096` (4K)** | Gemma 중형 모델 (4K 안전 맥락) |
| **`bge-m3`** (임베딩) | ~1.5 GB | **`8192` (8K)** | 임베딩 전용 (독립 포트 8090) |
| **`bge-reranker-v2-m3`** (리랭커) | ~1.5 GB | **`8192` (8K)** | 리랭킹 전용 (독립 포트 8091) |

---

## 📦 가상환경 원클릭 복원 (`uv sync`)

본 실습 팩에는 용량 오염을 방지하기 위해 `.venv` 디렉토리가 포함되어 있지 않습니다.  
실습을 시작하기 전, 다음 명령어 **단 한 번으로** 의존성 패키지를 100% 즉시 원복하세요:

```bash
# 1. 가상환경 의존성 자동 동기화 및 원복
uv sync

# 2. 패키지 원복 정상 작동 확인
uv run python -c "import openai, httpx, pydantic; print('✅ uv 가상환경 복원 성공!')"
```

---

## ⚙️ 동적 설정 관리 (`config.json`)

서버 IP 주소(`192.168.0.80`), 포트번호, 모델명, 벤치마크 스펙은 `config.json`에서 동적으로 로드됩니다.

```json
{
  "server_host": "http://192.168.0.80",
  "main_port": 8081,
  "embedding_port": 8090,
  "rerank_port": 8091,
  "default_model": "qwen3.5-4b"
}
```

---

## 🚀 11단계 초슬림 1:1 대칭 실습 예제 수트 (총 22종)

모든 실습 스크립트는 가상환경 격리 표준인 `uv run python ...`으로 실행합니다.

### 1단계: 기본 대화 (Chat Completions) 호출 기초
```bash
uv run python sample_01_chat_basic.py      # httpx REST API
uv run python openai_01_chat_basic.py      # OpenAI 공식 SDK
```

### 2단계: 추론 ON (<think> 포함) vs 추론 OFF (즉시 답변) 속도/품질 비교
```bash
uv run python sample_02_reasoning_control.py
uv run python openai_02_reasoning_control.py
```

### 3단계: 실시간 스트리밍 & TTFT(첫 토큰 지연시간), TPS(생성 속도) 측정
```bash
uv run python sample_03_streaming.py
uv run python openai_03_streaming.py
```

### 4단계: [실측] 다중 모델 라이브 변경 (`qwen3.5 2B/4B/9B`, `gemma4 2B/4B`) 호출
```bash
uv run python sample_04_model_switch.py
uv run python openai_04_model_switch.py
```

### 5단계: [실측] 컨텍스트 윈도우 토큰 한도(`64`, `512`, `2048`) 라이브 호출 및 정지 사유 비교
```bash
uv run python sample_05_context_window.py
uv run python openai_05_context_window.py
```

### 6단계: Temperature (0.0 결정론적 vs 0.8 창의적) 파라미터 비교
```bash
uv run python sample_06_temperature.py
uv run python openai_06_temperature.py
```

### 7단계: Stop Sequence (`===STOP===`) 조기 감지 및 자동 중단
```bash
uv run python sample_07_stop_sequence.py
uv run python openai_07_stop_sequence.py
```

### 8단계: BGE M3 1024차원 수치 벡터 변환 (8090 포트)
```bash
uv run python sample_08_embedding.py
uv run python openai_08_embedding.py
```

### 9단계: BGE Reranker v2 질문-문서 관련도 점수(Relevance Score) 측정 (8091 포트)
```bash
uv run python sample_09_reranking.py
uv run python openai_09_reranking.py
```

### 10단계: Pydantic v2 Strict JSON Schema 단일 구조화된 출력 2026 트렌드
```bash
uv run python sample_10_structured_output.py
uv run python openai_10_structured_output.py
```

### 11단계: Pydantic v2 배치(Batch) 멀티 댓글 일괄 구조화된 출력 2026 트렌드
```bash
uv run python sample_11_structured_batch.py
uv run python openai_11_structured_batch.py
```
