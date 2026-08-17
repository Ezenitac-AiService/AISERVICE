# Quickstart: 올원챗 푸터 및 한자 차단 검증 가이드 (005-chatb-footer-cleanup)

**Feature**: `005-chatb-footer-cleanup`  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/005-chatb-footer-cleanup/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/005-chatb-footer-cleanup/plan.md)

---

## 1. 개요 및 테스트 방법

올원챗(ChatB)의 하단 개발용 잔여 주소 텍스트 제거 및 LLM 뷰티 가이드 답변의 한자(漢字) 차단/정제 가드레일을 검증합니다.

---

## 2. 검증 시나리오

### 시나리오 1: 웹 UI 최하단 푸터 클린업 확인
1. 브라우저에서 `https://ezenitac.duckdns.org/bteam/chatb/` 접속
2. 페이지 최하단으로 스크롤 이동
3. 저작권 문구(`© 2026 Oliview Production RAG Engine...`) 아래에 `# http://localhost:8000/...` 텍스트가 완전히 사라졌는지 확인

### 시나리오 2: 뷰티 가이드 자연어 질문 및 한자 차단 확인
1. 검색창에 "차앤박 프로폴리스 앰플 수분감을 분석해줘" 입력 후 [분석 요청] 클릭
2. 생성된 `AI 전문 뷰티 가이드의 맞춤 솔루션` 답변 텍스트 확인
3. `結果`, `推薦` 등의 한자가 전혀 포함되지 않고 순수 한글(`결과`, `추천`)로 자연스럽게 출력되는지 확인

### 시나리오 3: E2E 서비스 무결성 검증
```powershell
powershell -ExecutionPolicy Bypass -File specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1 -Mode Local
```
10개 체크포인트 전체 PASS 확인.
