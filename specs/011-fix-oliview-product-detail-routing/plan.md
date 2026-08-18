# Implementation Plan: Oliview 상품 상세 조회 404 경로 오류 해결 및 라우팅 정상화

**Branch**: `011-fix-oliview-product-detail-routing` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/011-fix-oliview-product-detail-routing/spec.md`

---

## Summary

Oliview 웹 포털에서 상품 카드 클릭 시 발생하는 404(Not Found) 라우팅 오류 및 `SyntaxError: Unexpected token '<'` JSON 파싱 실패를 원천 해결하기 위해, 프론트엔드 컴포넌트의 `apiBaseUrl` 전역 폴백(`/bteam/oliview`) 정규화, React Props/State 양방향 라이프사이클 동기화, Flask 백엔드의 `datetime`/`Decimal` JSON 안전 직렬화, 도커 실시간 핫리로드 볼륨 마운트 설정을 일관되게 적용하고 자동화된 회귀 테스트로 검증합니다.

---

## Technical Context

**Language/Version**: Python 3.12 (백엔드 Flask), JavaScript ES2022 (프론트엔드 React 18 / Vite)

**Primary Dependencies**: React 18, Vite 5, Flask 3.0, PyMySQL, Gunicorn, Nginx 1.25

**Storage**: MySQL 8.0 (`bteam_db` / `oliview_project` 스키마)

**Testing**: Python `unittest`, `urllib` 표준 라이브러리 기반 통합 회귀 테스트

**Target Platform**: Docker 컨테이너 환경 (Linux / Windows WSL2), Nginx Ingress (포트 8080/80/443)

**Project Type**: Full-stack Web Service (React Vite Frontend + Flask REST API + Nginx Reverse Proxy)

**Performance Goals**: 상품 상세 정보 및 AI 감성 분석 리포트 응답 속도 < 1.0s, 브라우저 콘솔 에러 0건

**Constraints**: `aiservice-network` 내부 도커 브리지 격리, `proxy_buffering off` 및 300초 타임아웃 유지

**Scale/Scope**: Oliview 프론트엔드 4개 핵심 컴포넌트, Flask 백엔드 4개 엔드포인트, Docker Compose 설정

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 헌법 원칙 (Principle) | 준수 여부 (Status) | 설계 검증 및 준수 증거 |
|---|:---:|---|
| **I. 한국어 소통 및 문서화 정책** | **PASS** | 모든 설계 산출물(`research.md`, `data-model.md`, `quickstart.md`, `plan.md`) 및 코드 주석 100% 한국어 작성 |
| **II. 계약 기반 테스트 주도 개발 (TDD)** | **PASS** | `tests/test_multi_chatbot_regression.py`에 상품 상세 및 리포트 API 계약 검증 테스트 포함 |
| **III. 서비스 모듈성 및 환경 격리** | **PASS** | `oliview_backend`, `oliview_frontend` 독립 컨테이너 유지 및 `aiservice-network` 사설 격리 |
| **IV. 관측 가능성 및 구조화된 로깅** | **PASS** | Nginx JSON 액세스 로그 및 백엔드 `traceback.print_exc()` 구조화 로깅 적용 |
| **V. 단순성과 점진적 진화 (YAGNI)** | **PASS** | 추가 프레임워크나 복잡한 미들웨어 도입 없이 표준 헬퍼 함수와 Props 정규화로 최소 침습적 해결 |

---

## Project Structure

### Documentation (this feature)

```text
specs/011-fix-oliview-product-detail-routing/
├── spec.md              # 기능 명세서
├── plan.md              # 구현 계획서 (본 문서)
├── research.md          # 기술 의사결정 및 대안 분석 (Phase 0)
├── data-model.md        # 데이터 모델 및 UI 상태 전이도 (Phase 1)
├── quickstart.md        # 종단간 빠른 검증 가이드 (Phase 1)
├── contracts/           # API 인터페이스 계약 문서 (Phase 1)
│   └── oliview-product-api-contract.md
├── checklists/          # 명세 품질 검증 체크리스트
│   └── requirements.md
└── tasks.md             # 세부 작업 분해 목록 (Phase 2 - /speckit-tasks 생성)
```

### Source Code (repository root)

```text
bteam/Oliview_Project/
├── frontend/
│   ├── Dockerfile
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       ├── BaseProductDetail.jsx       # [수정] baseUrl 폴백 정규화
│       ├── ProductDetailPage.jsx       # [수정] propProductId 지원 및 동기화
│       ├── CompetitorProductDetailPage.jsx # [수정] propProductId 지원 및 동기화
│       ├── MyBrandpage.jsx             # [수정] apiBaseUrl 및 prop 전달
│       └── CompetitorDashboardPage.jsx # [수정] apiBaseUrl 정규화
└── backend/
    ├── Dockerfile
    ├── app.py                          # [수정] serialize_row 헬퍼 및 엔드포인트 직렬화 안전성 보장
    └── db_helper.py

gateway/
└── nginx.conf                          # [유지] /bteam/oliview/api/ 프록시 및 타임아웃 유지

docker-compose.yml                      # [수정] oliview_backend / frontend 소스 볼륨 마운트 추가

tests/
└── test_multi_chatbot_regression.py     # [수정] Oliview 상품 상세 계약 검증 테스트 확장
```

---

## Implementation Phases

### Phase 0: Outline & Research (Completed)
- 프론트엔드 URL 폴백 구조, Nginx 서브 경로 매핑, Flask JSON 직렬화, Docker 핫리로드 전략 수립 완료 (`research.md`).

### Phase 1: Design & Contracts (Completed)
- 데이터 모델 엔티티 및 상태 전이도 정의 (`data-model.md`).
- Oliview 상품 상세 API 계약 정의 (`contracts/oliview-product-api-contract.md`).
- 종단간 UI/API 수동 및 자동 검증 가이드 작성 (`quickstart.md`).

### Phase 2: Tasks & Implementation (/speckit-tasks 예정)
- 세부 작업 분해(`tasks.md`) 생성 후 순차적 코드 적용 및 자동화 회귀 테스트 검증.
