<!--
Sync Impact Report:
- Version change: 0.0.0 → 1.0.0
- Modified principles: N/A (Initial ratification)
- Added sections:
  - I. Language and Communication Governance (언어 및 커뮤니케이션 원칙)
  - II. Canonical Authority & Team Lead Priority (정본 권위 및 팀장 지시 우선)
  - III. Contract-First & Simplicity (계약 우선 및 단순성 원칙)
  - IV. Test-First & Empirical Validation (테스트 우선 및 실증 검증)
  - V. Strict Security & Privacy Compliance (엄격한 보안 및 개인정보 보호)
  - Technical Constraints & Standards (기술 제약 및 표준)
  - Development Workflow & Quality Gates (개발 워크플로우 및 품질 게이트)
  - Governance (거버넌스)
- Removed sections: N/A
- Follow-up TODOs: None
-->

# PILOS Sentiment Index Project Constitution

## Core Principles

### I. Language and Communication Governance (언어 및 커뮤니케이션 원칙)
모든 대화, 질문, 답변, 산출물 및 공식 문서 작성(스펙, 구현 계획, 작업 목록, README, 코드 주석 등)은 반드시 한국어로 작성해야 합니다(MUST). 반면 내부적인 추론, 사고, 분석 과정(Thinking / Reasoning Process)은 논리적 정밀성과 성능 최적화를 위해 반드시 영어(English)로 수행해야 합니다(MUST).

### II. Canonical Authority & Team Lead Priority (정본 권위 및 팀장 지시 우선)
모든 작업 착수 전 해당 영역의 정본 문서(`docs/ARCHITECTURE.md`, `docs/DATA_CONTRACT.md`, `docs/GIT_WORKFLOW.md`, `docs/DECISIONS.md`, 기획안 등)를 최우선으로 확인해야 합니다(MUST). 정본 간 충돌이 발생하면 임의 판단을 금지하고 팀장에게 보고해야 하며, 팀장의 명시적 지시가 최우선 권위를 가집니다.

### III. Contract-First & Simplicity (계약 우선 및 단순성 원칙)
공통 데이터 상태, 스키마, 라벨, 시간 형식 및 입력·출력 계약을 임의로 변경하지 않아야 합니다(MUST NOT). 실제 중복이나 구체적 요구사항이 발생하기 전까지 범용 유틸리티, 팩토리, 추상 계층이나 미래용 빈 디렉터리를 선제적으로 생성하지 않는 YAGNI 원칙을 엄격히 준수합니다(MUST).

### IV. Test-First & Empirical Validation (테스트 우선 및 실증 검증)
모든 기능 및 파이프라인 개발은 테스트 주도 원칙과 명확한 검증 기준을 갖추어야 합니다(MUST). 가짜 샘플 생성에 의존하지 않고, 합의된 데이터 계약과 실제 수집 데이터를 활용한 수직 통합 테스트를 통해 기능과 모델 신뢰성을 검증해야 합니다(MUST).

### V. Strict Security & Privacy Compliance (엄격한 보안 및 개인정보 보호)
`.env`, API 키, 데이터베이스 계정, 개인정보 및 인증 자격증명을 코드에 하드코딩하거나 저장소에 커밋해서는 안 됩니다(MUST NOT). 민감정보 노출 또는 보안 위험 감지 시 즉시 작업을 멈추고 영향 범위를 보고해야 합니다(MUST).

## Technical Constraints & Standards

프로젝트는 Python 환경 기반으로 동작하며 패키지 관리 및 가상환경 격리를 철저히 유지해야 합니다. 모든 설정값은 환경변수를 통해 주입받으며, 데이터 파이프라인과 모델 서빙 간 경계는 사전에 정의된 데이터 계약(Data Contract)을 준수해야 합니다.

## Development Workflow & Quality Gates

모든 작업은 Spec Kit 기반 개발 라이프사이클(Specify → Plan → Tasks → Implement → Verify)을 따르며, 코드 변경 전 영향 범위를 명확히 식별해야 합니다. 작업 완료 후에는 변경 파일, 테스트/검증 결과, 미검증 항목 및 후속 결정 사항을 명확히 보고해야 합니다. `README.md`, `AGENTS.md`, `docs/*.md` 등의 문서는 팀장의 명시적 승인 하에 최신 상태로 유지됩니다.

## Governance

본 헌장(Constitution)은 프로젝트 내의 모든 개발, 협업 및 설계 관행보다 최우선하는 기준입니다. 헌장 수정은 명확한 변경 사유, 영향도 분석, 팀장 승인을 거쳐 시맨틱 버저닝(Semantic Versioning) 규칙에 따라 개정됩니다. 모든 기능 명세서, 구현 계획, 코드 리뷰는 본 헌장 및 핵심 원칙에 대한 준수 여부를 검증해야 합니다.

**Version**: 1.0.0 | **Ratified**: 2026-08-17 | **Last Amended**: 2026-08-17
