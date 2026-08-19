# Implementation Plan: 027-update-readme-project-docs

**Branch**: `027-update-readme-project-docs` | **Date**: 2026-08-20 | **Spec**: [`specs/027-update-readme-project-docs/spec.md`](file:///c:/AISERVICE/specs/027-update-readme-project-docs/spec.md)

## Summary

`README.md`를 **개요, 전체 아키텍처 다이어그램, 4대 서비스 라우팅 맵, 1-Click 빠른 시작, 상세 기술문서 목차/링크, MIT 라이센스**의 6대 핵심 섹션으로 간결하고 직관적으로 재구성하고, 서브모듈별 세부 기술 명세를 `docs/` 하위 5개 독립 마크다운 문서(`architecture.md`, `model_gateway.md`, `bteam_oliview.md`, `ateam_pilos.md`, `security_guardrails.md`) 및 `LICENSE` 파일로 모듈화하여 체계적인 엔터프라이즈급 AI 서비스 문서 시스템을 구축한다.

---

## Technical Context

- **Documentation Stack**: Markdown (GitHub Flavored Markdown), ASCII Architecture Art
- **Language**: 한국어 (주요 기술 용어 및 모델명 영문 병기)
- **Target Files**:
  - `README.md` (메인 포털)
  - `LICENSE` (MIT 라이센스)
  - `docs/architecture.md` (인프라 & 네트워크 아키텍처)
  - `docs/model_gateway.md` (2B 상주 서빙, 16K ctx, SINGLE_MODEL_MODE)
  - `docs/bteam_oliview.md` (Oliview 뷰티 리뷰 분석 & 챗봇 A/B)
  - `docs/ateam_pilos.md` (Pilos 주식 수급 감정분석 & 7단계 배치 워커)
  - `docs/security_guardrails.md` (4단계 CPU 가드레일 & 3단계 토큰 정책)
- **Validation**: Python 문서 실존 및 마크다운 링크 무결성 검증 스크립트

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **언어 및 커뮤니케이션 정책**: 사용자 산출물 및 전 문서 한국어 표준 준수.
- [x] **모듈화 및 격리**: `README.md` 슬림화 및 `docs/` 하위 모듈별 심층 문서화.
- [x] **단순성 및 YAGNI**: 과도한 중복 기술 배제, 명확한 목차와 상대 링크 제공.
- [x] **정확성 및 관측 가능성**: 8GB VRAM 실측치(~4.1GB) 및 3개 모델 상주 상태와 100% 일치.

---

## Project Structure

```text
c:/AISERVICE/
├── README.md                  # [MODIFY] 메인 총괄 대시보드 문서
├── LICENSE                    # [NEW] MIT 라이센스 전문
└── docs/                      # [NEW] 상세 기술문서 디렉토리
    ├── architecture.md        # [NEW] 전체 인프라, K8s Ingress, Nginx, 네트워크
    ├── model_gateway.md       # [NEW] vLLM/llama.cpp, 2B 상주, SINGLE_MODEL_MODE, 16K
    ├── bteam_oliview.md       # [NEW] Oliview React/Flask, 챗봇 A, 챗봇 B
    ├── ateam_pilos.md         # [NEW] Pilos 주식 감정지수, 7단계 배치 워커 데몬
    └── security_guardrails.md # [NEW] 4단계 CPU 가드레일, 3단계 하이브리드 토큰 정책
```

---

## Phase 0: Outline & Research

- [x] 문서 모듈화 구조 설계 및 서브 도메인 분리 방안 확정 (`research.md`)
- [x] MIT 라이센스 채택 및 라이센스 고지 방침 확정 (`research.md`)
- [x] 최신 실측 사양(2B 상주, VRAM 4.1GB, 4단계 가드레일) 정합성 확인 (`research.md`)

---

## Phase 1: Design & Contracts

- [x] 문서 파일 트리 및 섹션 스키마 정의 완료 ([`data-model.md`](file:///c:/AISERVICE/specs/027-update-readme-project-docs/data-model.md))
- [x] 상대 링크 계약 명세 정의 완료 ([`contracts/documentation_contract.md`](file:///c:/AISERVICE/specs/027-update-readme-project-docs/contracts/documentation_contract.md))
- [x] 문서 유효성 검증 가이드 작성 완료 ([`quickstart.md`](file:///c:/AISERVICE/specs/027-update-readme-project-docs/quickstart.md))
