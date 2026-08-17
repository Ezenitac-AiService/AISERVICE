<!--
Sync Impact Report:
- Version Change: 0.0.0 (Template) → 1.0.0
- Modified Principles:
  - PRINCIPLE_1: I. 언어 및 커뮤니케이션 정책 (Language & Communication Policy)
  - PRINCIPLE_2: II. TDD 및 테스트 우선주의 (Test-First & Contract Verification)
  - PRINCIPLE_3: III. 서비스 모듈화 및 격리 (Service Modularity & Environment Isolation)
  - PRINCIPLE_4: IV. 관측 가능성 및 구조화된 로깅 (Observability & Structured Logging)
  - PRINCIPLE_5: V. 단순성 및 점진적 진화 (Simplicity & Incremental Evolution - YAGNI)
- Added Sections:
  - 기술 제약 및 보안 표준 (Technical Constraints & Security Standards)
  - 개발 워크플로우 및 품질 게이트 (Development Workflow & Quality Gates)
- Removed Sections: None
- Deferred Items / TODOs: None
-->

# AISERVICE Constitution

## Core Principles

### I. 언어 및 커뮤니케이션 정책 (Language & Communication Policy)
- **대화 및 문서화(Korean)**: 사용자 대상의 모든 대화, 질문, 답변, 설명 및 산출물(문서, 명세서, 계획서, 작업 목록, 코드 주석 등)은 한국어로 작성한다. 기술 표준 용어는 의미 전달을 위해 원어를 병기할 수 있다.
- **사고 및 추론(English)**: 에이전트의 내부 사고 과정, 논리 추론, 분석(thinking, reasoning, reflection)은 영어로 수행한다.
- **근거(Rationale)**: 한국어 사용자 환경에서의 소통 정확도와 산출물 가독성을 극대화하는 동시에, 대규모 모델의 기술적 추론 및 논리 분석 성능을 최상으로 유지하기 위함이다.

### II. TDD 및 테스트 우선주의 (Test-First & Contract Verification)
- **테스트 선행 원칙**: 모든 신규 기능, 인터페이스 변경, 버그 수정은 테스트 코드를 먼저 작성하고 사용자 승인 및 실패 검증(Red)을 거친 후 구현(Green-Refactor)해야 한다.
- **계약 검증**: 통합 게이트웨이(Model Gateway) 및 서브 도메인 서비스(A-Team, B-Team) 간의 API 통신, 데이터 스키마 변환, 서비스 인터페이스에 대해 단위 및 통합 테스트를 필수로 구축한다.
- **근거(Rationale)**: 멀티 서비스 통합 환경에서 안정성을 확보하고 회귀 버그를 사전에 방지하기 위함이다.

### III. 서비스 모듈화 및 격리 (Service Modularity & Environment Isolation)
- **독립적 서브프로젝트 구조**: A-Team, B-Team, Model Gateway 등 각 도메인/서비스는 독립적으로 실행, 빌드, 테스트가 가능하도록 컨테이너 및 런타임 환경을 격리한다.
- **비파괴적 무결성 보존**: 기존 환경에 구축된 유효 바이너리(CUDA/GPU 가속 패키지), 모델 가중치, DB 스키마 및 설정 파일은 임의로 덮어쓰거나 파괴하지 않고 최우선 보존한다.
- **근거(Rationale)**: 복합 AI 서비스 생태계에서 개별 서브시스템 간의 결합도를 낮추고 의존성 및 환경 충돌을 방지하기 위함이다.

### IV. 관측 가능성 및 구조화된 로깅 (Observability & Structured Logging)
- **구조화된 로깅**: 서비스 간 호출 흐름, 지연 시간(Latency), 에러 추적 및 모델 호출 트래픽은 구조화된 포맷(JSON 등)으로 기록한다.
- **보안 및 개인정보 보호**: API 키, 인증 토큰, 민감 데이터는 로그 및 외부 전송 데이터에서 무조건 마스킹 처리한다.
- **근거(Rationale)**: 분산 환경에서의 장애 원인 분석 및 성능 병목 감지를 신속히 수행하고 보안 규격을 준수하기 위함이다.

### V. 단순성 및 점진적 진화 (Simplicity & Incremental Evolution - YAGNI)
- **YAGNI 원칙**: 불필요한 과도한 추상화와 조기 최적화를 엄격히 지양하며, 현재 요구사항에 부합하는 가장 단순하고 직관적인 설계를 채택한다.
- **점진적 통합**: 기능 확장은 독립 모듈 단위로 점진적으로 진행하며, 의존성 충돌을 사전에 관리한다.
- **근거(Rationale)**: 시스템 복잡도를 통제하고 지속 가능한 유지보수성을 확보하기 위함이다.

## 기술 제약 및 보안 표준

- **기술 스택 및 인프라**: Python 기반 AI/ML 백엔드, FastAPI/vLLM 모델 서빙 게이트웨이, 감정 분석/챗봇 파이프라인, 관계형 데이터베이스 및 Docker 기반 컨테이너 인프라를 표준으로 한다.
- **보안 및 환경 통제**: 환경 변수(`.env`) 기반 설정 관리, API Key 및 인증 토큰 보호, 컨테이너 네트워크 접근 제어를 철저히 적용한다.

## 개발 워크플로우 및 품질 게이트

- **Spec-Kit 기반 개발 주기**: 모든 기능 및 서브시스템 개발은 `Specify -> Plan -> Tasks -> Implement -> Verify`의 체계적인 Spec-Kit 수명 주기를 엄격히 준수한다.
- **품질 게이트**: 모든 코드 변경은 자동화된 테스트 스위트 통과, 정적 분석(Linter/Type Checker) 무결점, 본 헌법에 대한 적합성 검토를 거쳐야 한다.
- **산출물 동기화**: 명세서(`spec.md`), 계획서(`plan.md`), 작업 목록(`tasks.md`)은 한국어로 최신화되고 일관성을 유지해야 한다.

## Governance

- **헌법의 최고성**: 본 헌법은 프로젝트의 모든 코딩 관행, 아키텍처 결정, 개발 프로세스보다 최상위 권위를 갖는다.
- **개정 절차**:
  - **MAJOR (주요 변경)**: 기존 원칙의 근본적 재정의, 제거 또는 하위 호환성을 깨는 거버넌스 규칙 변경.
  - **MINOR (기능/원칙 추가)**: 새로운 원칙이나 섹션의 추가 또는 실질적인 가이드라인 확장.
  - **PATCH (경미한 수정)**: 문구 수정, 명확화, 오탈자 교정 등 비시맨틱 정제.
- **준수성 검증**: 모든 기여(PR, 커밋, 에이전트 태스크)는 본 헌법에 명시된 원칙 및 품질 게이트를 준수하는지 정기적으로 검증되어야 한다.

**Version**: 1.0.0 | **Ratified**: 2026-08-17 | **Last Amended**: 2026-08-17
