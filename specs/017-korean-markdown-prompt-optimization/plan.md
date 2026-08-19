# Implementation Plan: 017-korean-markdown-prompt-optimization (한국어 마크다운 볼드 렌더링 최적화 및 프롬프트 고도화)

**Branch**: `017-korean-markdown-prompt-optimization`
**Feature Spec**: [spec.md](./spec.md)
**Created**: 2026-08-19
**Status**: In Progress

---

## 1. Technical Context

- **LLM Prompting Layer**: `bteam/oliview_core/pipeline.py` (Oliview RAG answer prompt), `bteam/Oliview_chatbot_b/common.py` (ChatB prompt), `ateam/pilos-sentiment-index/pilos/llm/prompts/` (PILOS RAG prompt)
- **Normalization Layer**: `bteam/oliview_core/sanitizer.py` (`normalize_korean_markdown()`)
- **Frontend Markdown Renderers**:
  - `bteam/Oliview_chatbot_a/app.py` (Streamlit `st.markdown` & `st.write_stream`)
  - `bteam/Oliview_chatbot_b/project_ragapi.py` / Static web UI
  - `ateam/pilos-sentiment-index/pilos/web/static/js/chat.js` (`renderMarkdown()`)
- **Core Technology Stack**: Python 3.12, Vanilla JS, Streamlit, FastAPI, Flask, CommonMark / GFM Parser

---

## 2. Constitution Check

- [x] **I. 언어 및 커뮤니케이션 정책**: 모든 프롬프트 가이드라인, 마크다운 주석, 테스트 코드 설명을 한국어로 일관되게 작성.
- [x] **II. TDD 및 테스트 우선주의**: 비정상 볼드 패턴(`**"..."**조사`) 변환 단위 테스트를 선행 작성 후 구현.
- [x] **III. 서비스 모듈화 및 격리**: `normalize_korean_markdown` 함수를 `oliview_core.sanitizer`에 순수 함수로 구현하여 독립적 테스트 및 재사용 보장.
- [x] **IV. 관측 가능성 및 로깅**: 마크다운 정규화 처리 시 오버헤드 1ms 미만 유지 및 예외 발생 시 원본 텍스트 안전 반환.
- [x] **V. 단순성 및 점진적 진화 (YAGNI)**: 복잡한 외부 파서 종속성 없이 정밀 정규식 및 프롬프트 규칙 조합으로 단순하게 해결.

---

## 3. Proposed Changes & Architecture

### Phase 0: Research & Normalization Specification
- [research.md](./research.md): CommonMark Right-flanking 규격 분석, 한국어 조사 결합 패턴 정규식 설계, Few-Shot 프롬프트 포맷 도출.

### Phase 1: Design & Contract Definition
- [data-model.md](./data-model.md): 마크다운 정규화 데이터 모델 및 프롬프트 템플릿 스키마.
- [contracts/markdown_normalization_contract.md](./contracts/markdown_normalization_contract.md): 정규화 인터페이스 입출력 계약.
- [quickstart.md](./quickstart.md): 단위 테스트 및 실시간 스트리밍 검증 가이드.

### Phase 2: Core Implementation
1. `bteam/oliview_core/sanitizer.py`: `normalize_korean_markdown(text: str) -> str` 구현.
2. `bteam/oliview_core/pipeline.py`: 시스템 프롬프트에 한국어 마크다운 안전 생성 지침 주입 및 토큰 스트림 정규화 적용.
3. `bteam/Oliview_chatbot_a/app.py`, `06.02.app.py`, `06.app.py`: 마크다운 출력 시 `normalize_korean_markdown()` 적용.
4. `ateam/pilos-sentiment-index/pilos/web/static/js/chat.js`: 클라이언트 마크다운 파서에 CJK 볼드 패턴 치환 정규식 탑재.
