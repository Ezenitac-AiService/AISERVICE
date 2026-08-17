# Implementation Plan: 올원챗 푸터 클린업 및 프롬프트 고도화·한자 차단 가드레일 (005-chatb-footer-cleanup)

**Branch**: `005-chatb-footer-cleanup` | **Date**: 2026-08-17 | **Spec**: [spec.md](file:///c:/AISERVICE/specs/005-chatb-footer-cleanup/spec.md)

**Input**: Feature specification from `specs/005-chatb-footer-cleanup/spec.md`

---

## Summary

올원챗(ChatB)의 프로덕션 완성도를 높이기 위해 다음 2가지 개선을 일괄 적용합니다:
1. **푸터 클린업**: `bteam/Oliview_chatbot_b/index.html` 416~417행의 개발 테스트용 잔여 주소 문자열(`# http://localhost:8000/...`)을 완전히 제거하고 유효한 HTML5 구조로 정제합니다.
2. **프롬프트 고도화 및 한자(漢字) 원천 차단 이중 가드레일**:
   - `project_ragapi.py`의 RAG 시스템/사용자 프롬프트를 고도화하여 친절하고 전문적인 AI 뷰티 가이드 페르소나를 구축하고, 순수 한글(No Hanja) 작성을 강력하게 지시합니다.
   - `common.py` 및 `project_ragapi.py`에 `clean_hanja_and_artifacts` 후처리 함수를 구현하여 LLM이 출력한 한자어(例: `結果`→`결과`, `推薦`→`추천`, `效果`→`효과`, `保濕`→`보습`)를 한글로 자동 치환하고 잔여 CJK 한자를 100% 제거합니다.

---

## Technical Context

- **Language/Version**: Python 3.12, HTML5, Vanilla JavaScript
- **Primary Dependencies**: FastAPI, Uvicorn, httpx, pymysql, regex
- **Storage**: MySQL (`oliview_project` DB)
- **Testing**: RAG 자연어 질의응답 검증, `verify_e2e_services.ps1` 전체 체크포인트 검증
- **Target Platform**: Docker 컨테이너 (`oliview_chatbot_b:8002`, `gateway:8080/8443`)
- **Project Type**: Web Application UI & AI RAG Text Post-Processing Guardrail
- **Performance Goals**: 후처리 지연 0.5ms 이하, 한자 잔존율 0.0%
- **Constraints**: 기존 RAG 검색/리랭킹 파이프라인 및 응답 스키마 100% 보존

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle I (Language Requirement)**: 모든 명세, 설계, 프롬프트, 한자 치환 사전 한국어 완벽 대응 (PASS).
- **Principle II (Test-Driven Discipline)**: 자연어 질의 검증 시나리오 및 E2E 스위트 정합성 완비 (PASS).
- **Principle III (Service Modularity & Isolation)**: `bteam/Oliview_chatbot_b/` 내부 변경에 국한 (PASS).
- **Principle IV (Observability & Production Safeguards)**: 한자 정제 로깅 및 오류 방어 (PASS).
- **Principle V (YAGNI & Scope Economy)**: 요청된 푸터 텍스트 제거 및 한자 차단/프롬프트 고도화에 집중 (PASS).

---

## Project Structure

### Documentation (this feature)

```text
specs/005-chatb-footer-cleanup/
├── spec.md              # Feature specification
├── plan.md              # Implementation plan (this file)
├── research.md          # Phase 0 research & technical decisions
├── data-model.md        # Phase 1 Hanja dictionary & schemas
├── quickstart.md        # Phase 1 validation guide
├── contracts/
│   └── chatb-rag-response.md # Phase 1 API response contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 task decomposition (/speckit-tasks)
```

### Source Code Touched

```text
bteam/Oliview_chatbot_b/
├── index.html           # Web interface (footer cleanup)
├── project_ragapi.py    # RAG pipeline (prompt enhancement & guardrail integration)
└── common.py            # Common helper (clean_hanja_and_artifacts function)
```

---

## Implementation Steps & Phases

### Phase 1: 푸터 잔여 텍스트 삭제
- `bteam/Oliview_chatbot_b/index.html` 416~417행의 잔여 `# http://localhost:8000/...` 라인 삭제.

### Phase 2: 한자 정제 헬퍼 함수 구현
- `bteam/Oliview_chatbot_b/common.py`에 `clean_hanja_and_artifacts(text)` 함수 구현:
  - 50여 종 도메인 상용 한자어 매핑 치환
  - CJK 정규식 `[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]` 잔여 문자 제거

### Phase 3: 프롬프트 고도화 및 파이프라인 연동
- `bteam/Oliview_chatbot_b/project_ragapi.py` 내 시스템/사용자 프롬프트 개선:
  - 친절한 전문 뷰티 가이드 페르소나 정립
  - 100% 순수 현대 한국어 한글 작성 지침 주입
- `generate_llm_rag_answer`의 후처리 파이프라인에 `clean_hanja_and_artifacts` 적용.

### Phase 4: 컨테이너 갱신 및 종합 검증
- `oliview_chatbot_b` 컨테이너 재기동.
- "차앤박 프로폴리스 앰플 수분감을 분석해줘" 등 자연어 질의 검증.
- `verify_e2e_services.ps1` 실행하여 10/10 PASS 유지 확인.
