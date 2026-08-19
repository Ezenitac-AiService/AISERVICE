# Research Document: 026-stabilize-2b-llm-chatbot

## 1. Mode Toggle Architecture (`SINGLE_MODEL_MODE`)

### Decision
`model_gateway`에 `SINGLE_MODEL_MODE` (기본값 `true`) 환경변수 및 라우팅 가드를 도입하여, 8GB VRAM 환경에서는 모든 클라이언트 요청의 모델명을 상주 모델 `qwen3.5-2b`로 강제 매핑/고정하고 프로세스 킬/스와핑(`load_model_with_download`)을 우회한다.

### Rationale
- Pilos(2B)와 챗봇(4B)이 서로 다른 모델을 요청할 때마다 `model_gateway`가 기존 `llama-server` 프로세스를 kill하고 새 모델을 로딩하는 '스와핑 핑퐁' 및 8GB VRAM 초과(OOM) 크래시를 원천 방지함.
- 기존의 다중 모델 카탈로그(`qwen3.5-4b`, `qwen3.5-9b` 등) 및 핫스왑 코드를 파괴하지 않고 보존하므로, 향후 고용량 GPU(24GB+ RTX 4090/A100)로 이전 시 `SINGLE_MODEL_MODE=false` 플래그 전환만으로 즉시 복원 가능.

### Alternatives Considered
- **4B 및 다중 모델 코드 영구 삭제**: 향후 GPU 확장 시 이전 코드를 다시 작성해야 하는 기술 부채 발생으로 기각.
- **클라이언트별 코드 하드코딩 수정만 진행**: 게이트웨이 자체 방어벽이 없으면 외부 API 호출이나 새 스크립트 실행 시 언제든 핫스왑 핑퐁이 재발할 수 있어 게이트웨이 레벨 가드 도입 결정.

---

## 2. 3단계 하이브리드 토큰 예산 & 16K 컨텍스트 윈도우

### Decision
- 서빙 백엔드(`qwen3.5-2b`)는 `n_ctx = 16384` (16K)로 가동.
- 작업 성격에 따른 3단계 `max_tokens` 하이브리드 예산 채택:
  1. **Tier 1 (Fast Intent / Preprocessing)**: `max_tokens = 512`
  2. **Tier 2 (Standard Interactive RAG)**: `max_tokens = 2048`
  3. **Tier 3 (In-depth Comparison / Market Report)**: `max_tokens = 4096`

### Rationale
- `Qwen3.5-2B`는 GQA(Grouped Query Attention) 구조로 16K 컨텍스트에서도 KV 캐시 점유량이 ~900MB 수준으로 매우 가벼움.
- 기존 512~1024 토큰에서 발생하던 문장 절단(`...모공 커버가`)을 완전히 해소하며, 1,000~1,500자의 완결된 뷰티 솔루션을 3~5초 내에 초고속 생성 가능.

### Alternatives Considered
- **전체 일괄 4096 적용**: 단순 의도분류나 짧은 대화에서도 최대 토큰 버퍼가 과도하게 잡혀 비정상 무한 루프 시 지연시간이 길어질 위험이 있어 작업별 하이브리드 분기 채택.

---

## 3. GPU VRAM 토폴로지 & CPU 가드레일 분리

### Decision
- **VRAM 상주 (총 3개 모델, ~5.1GB VRAM)**:
  1. `bge-m3` (포트 8090): ~1.2 GB
  2. `bge-reranker-v2-m3` (포트 8091): ~1.2 GB
  3. `qwen3.5-2b` (포트 8089/8081, n_ctx=16K): ~2.7 GB
- **CPU 상주 (0MB VRAM)**:
  - `PromptInjectionGuardrail`, `EarlyIntentGuardrail`: 순수 Python/ReDoS-safe 정규식 및 카나리 토큰 엔진.

### Rationale
- Windows OS 기본 점유 2.1GB와 결합 시 총 7.2GB / 8.0GB로, GTX 1070의 8GB VRAM 한계 내에서 100% OOM 없는 완전 상주 서빙 달성.

---

## 4. 보안 가드레일 정밀도 개선 (False-Positive 제거)

### Decision
`oliview_core/guardrail.py` 내의 `_RE_PROMPT_LEAK` 및 `SYSTEM_PROMPT_LEAK_OUTPUT` 정규식에서 '지침/성분/추출/분석' 등 화장품 리뷰 및 제품 설명에 빈번히 등장하는 일반 명사가 시스템 프롬프트 유출로 오탐되지 않도록 문맥 경계(Context Boundary) 조건을 강화.

### Rationale
- Chatbot A 로그에서 식물나라/브링그린 리뷰 텍스트가 `SYSTEM_PROMPT_LEAK_OUTPUT`에 의해 차단되던 결함을 완벽히 해결하여 정상 텍스트 응답 보장.
