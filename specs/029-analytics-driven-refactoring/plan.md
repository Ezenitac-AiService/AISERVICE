# Implementation Plan: 분석 보고서 기반 서비스 및 시스템 최적화 리팩토링 (029-analytics-driven-refactoring)

**Branch**: `029-analytics-driven-refactoring` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/029-analytics-driven-refactoring/spec.md`

---

## Summary

실제 접속 로그 1.3만 건 분석 보고서(`docs/service_access_analytics_report.md`)에서 도출된 핵심 병목 및 기회 요소를 해결하기 위해, **(1) 주식 종목 로고 정적 라우팅 복구 및 프론트엔드 동적 아바타 폴백(404 에러 42% 완전 제거)**, **(2) 카카오톡 인앱(19.3%) 및 모바일(27%) 맞춤 뷰포트 반응형 스타일 & 서비스별 맞춤 Open Graph 메타태그 적용**, **(3) 통합 포털 랜딩(`/`)의 비동기 실시간 큐레이션 위젯 추가를 통한 전환율 개선**, **(4) B-Team 백엔드 API Graceful Fallback(500 에러 방지)**, **(5) Nginx 정적 자원 캐싱 정책 강화**를 단계별로 구현합니다.

---

## Technical Context

**Language/Version**: HTML5, CSS3, Vanilla JavaScript (ES6+), Python 3.12 (Flask, FastAPI, Streamlit), Nginx 1.25  
**Primary Dependencies**: Nginx Reverse Proxy, Flask, FastAPI, React 18 / Vite, Bootstrap / Pretendard Font  
**Storage**: MySQL 8.0 (`oliview_project`, `pilos_v2`), Redis 7, Local Static Files  
**Testing**: pytest (백엔드 API Fallback 검증), curl 및 브라우저 기반 E2E 정적 라우팅 및 렌더링 검증  
**Target Platform**: Docker 컨테이너 오케스트레이션 환경 (Linux/Windows WSL2), 공인 HTTPS 단일 도메인 (`https://ezenitac.duckdns.org`)  
**Project Type**: 엔터프라이즈 멀티 서비스 통합 게이트웨이 및 웹/모바일 프론트엔드/백엔드 플랫폼  
**Performance Goals**: Nginx 정적 로고/자원 응답 지연시간 < 5ms (304/캐시 적용), 포털 큐레이션 비동기 로딩 < 100ms, 404/500 에러율 0% 유지  
**Constraints**: 기존 5만 건 이상의 리뷰 데이터 및 주식 분석 DB 무결성 100% 보존 (비파괴적 수정)  
**Scale/Scope**: 5개 주요 파일 수정 (`gateway/nginx.conf`, `gateway/html/index.html`, `pilos/web/static/js/common.js`, `pilos/web/templates/`, `bteam/Oliview_Project/backend/app.py`), 4대 통합 검증 시나리오  

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **I. 언어 및 커뮤니케이션 정책**: 모든 문서, 명세서, 계획서 및 코드 주석을 한국어로 작성함. (Passed)
- [x] **II. TDD 및 테스트 우선주의**: E2E 시나리오 및 curl/pytest 기반 검증 스위트 정의 완료. (Passed)
- [x] **III. 서비스 모듈화 및 격리**: 게이트웨이, A-Team, B-Team의 컨테이너 격리 및 DB 무결성을 완벽히 보존함. (Passed)
- [x] **IV. 관측 가능성 및 로깅**: 404 에러 2,600여 건을 원천 차단하여 액세스 로그 가독성 및 관측 가능성을 극대화함. (Passed)
- [x] **V. 단순성 및 점진적 진화 (YAGNI)**: 복잡한 프레임워크 도입 없이 웹 표준 및 Nginx 라우팅/Vanilla JS 비동기 Fetch로 가장 단순하고 직관적인 해결책 채택. (Passed)

---

## Project Structure

### Documentation (this feature)

```text
specs/029-analytics-driven-refactoring/
├── spec.md              # 요구사항 명세서 및 명확화 결과
├── plan.md              # 본 구현 계획서
├── research.md          # Phase 0 기술 조사 및 아키텍처 결정
├── data-model.md        # Phase 1 메타데이터 및 큐레이션 엔터티 모델
├── quickstart.md        # Phase 1 E2E 검증 가이드
├── contracts/           # Phase 1 인터페이스 계약 (JSON Schema)
│   └── portal_curation.json
└── checklists/
    └── requirements.md  # 명세 품질 검증 체크리스트
```

### Source Code Modifications

```text
gateway/
├── nginx.conf                                # [MODIFY] /static/ 프록시 라우팅 및 정적 캐시 설정 추가
└── html/
    └── index.html                            # [MODIFY] OG 메타태그, 모바일 뷰포트, 실시간 큐레이션 위젯 추가

ateam/pilos-sentiment-index/pilos/web/
├── static/js/common.js                       # [MODIFY] 종목 로고 onerror 이니셜 컬러 아바타 폴백 핸들러
└── templates/index.html                      # [MODIFY] Pilos 맞춤 Open Graph 메타태그 적용

bteam/Oliview_Project/
├── backend/app.py                            # [MODIFY] brands products/categories API 500 방지 Graceful Fallback
└── frontend/index.html                       # [MODIFY] Oliview 맞춤 Open Graph 메타태그 적용
```

---

## Phase 0: Outline & Research

- [x] 주식 종목 로고 정적 서빙 및 404 해결 방안 확정 (`research.md`)
- [x] 모바일/카카오톡 인앱(19.3%) 맞춤 UX 및 Open Graph 메타태그 설계 (`research.md`)
- [x] 통합 포털 랜딩 실시간 큐레이션 비동기 Fetch 아키텍처 확정 (`research.md`)
- [x] B-Team 백엔드 API 500 에러 방지 핸들러 설계 (`research.md`)

---

## Phase 1: Design & Contracts

- [x] 엔터티 모델 정의 (`data-model.md`)
- [x] 포털 큐레이션 인터페이스 스키마 정의 (`contracts/portal_curation.json`)
- [x] E2E 검증 시나리오 및 명령어 작성 (`quickstart.md`)
- [x] Constitution Check 재검토 및 품질 게이트 통과 확인
