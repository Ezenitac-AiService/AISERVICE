# Research & Technical Decisions: 선제적 하이브리드 의도 게이트 및 Llama Prompt Guard 2 (86M)

**Feature Branch**: `022-early-intent-injection-gate`
**Date**: 2026-08-19

## Technical Decisions

### 1. 2-Tier 하이브리드 선제적 차단 아키텍처
- **Decision**: `Tier 1A` (<1ms ReDoS-safe 규칙 엔진) + `Tier 1B` (~15ms Llama Prompt Guard 2 86M 로컬 모델) 폭포수(Waterfall) 구조 채택.
- **Rationale**:
  - `Tier 1A`가 명백한 코딩/게임/탈옥/수학/번역 질의를 0.1ms 이내에 즉각 걸러내어 86M 모델 추론 비용마저 90% 이상 절감.
  - `Tier 1B`가 미묘하거나 다국어로 우회된 적대적 공격 페이로드를 86M 전용 분류기로 15ms 내에 정밀 판별.
- **Alternatives Considered**:
  - *Qwen 3.5 2B 생성 모델을 의도 분류기로 활용*: 200~300ms 소요 및 4~5GB VRAM 낭비로 기각.
  - *순수 정규식 블랙리스트만 활용*: 변형된 다국어 탈옥 및 은닉형 인젝션을 놓치는 결함이 있어 단독 사용 기각.

### 2. Llama Prompt Guard 2 (86M) 로컬 서빙 방식
- **Decision**: 외부 API 종속성 없는 `transformers` Pipeline / PyTorch `torch.inference_mode()` 기반 로컬 인메모리 싱글톤 구동 + ONNX Runtime INT8 어댑터 지원.
- **Rationale**:
  - 86M 파라미터는 약 300MB(ONNX 80MB)로 CPU 메모리나 GPU VRAM 부담이 전무함.
  - 외부 클라우드 통신 장애나 API 비용 없이 100% 온프레미스/오프라인 환경에서 완벽 자립 가동.
  - `threading.Lock()` 및 `run_in_threadpool`을 적용하여 멀티스레드/비동기 동시성 레이스 컨디션 방지.
- **Alternatives Considered**:
  - *Groq API 클라우드 연동*: 외부 네트워크 통신 및 API 키 종속성으로 인해 로컬 기본 탑재 후 옵션으로만 지원.

### 3. 은유적 표현 오탐 방지 (Contextual Whitelist Engine)
- **Decision**: 비도메인 단어(코딩, 게임 등)가 포함되더라도, 올리브영 등록 브랜드명/화장품 품목/피부 고민 키워드가 목적어로 결합된 경우 `Allow-list` 규칙이 우선 적용되어 정상 통과.
- **Rationale**:
  - "코딩하느라 주름 생겼는데 아이크림 추천해줘", "피부 뒤집어져서 인생 게임 오버될 것 같은데 진정 크림 추천"과 같은 실제 뷰티 상담 사용자의 일상 언어 경험 보호.

### 4. Zero-Connection Early Exit & Session Isolation
- **Decision**:
  - 가드레일 판정은 `pymysql.connect()` 또는 Faiss/Redis 커넥션 획득 이전에 실행 (DB 커넥션 0개 점유).
  - 차단된 공격 질의는 Redis 대화 히스토리 저장을 건너뛰어 다음 턴 History Poisoning 원천 차단.
- **Rationale**:
  - 대량 인젝션 공격 유입 시 커넥션 풀 고갈(Pool Starvation) 장애 방어 및 다단계 탈옥 원천 차단.
