# Quickstart: 브랜드 가드레일 및 조회 검증 가이드 (006-rag-brand-guardrail)

**Feature**: `006-rag-brand-guardrail`  
**Spec**: [spec.md](file:///c:/AISERVICE/specs/006-rag-brand-guardrail/spec.md) | **Plan**: [plan.md](file:///c:/AISERVICE/specs/006-rag-brand-guardrail/plan.md)

---

## 1. 개요 및 테스트 방법

올리뷰 프론트엔드 브랜드 고유번호 조회 404 해결 및 챗봇 RAG 부재 브랜드 환각 차단 가드레일을 검증합니다.

---

## 2. 검증 시나리오

### 시나리오 1: 올리뷰 로그인 페이지 브랜드 고유번호 조회
1. 브라우저에서 `https://ezenitac.duckdns.org/bteam/oliview/` 접속
2. [조회하기] 버튼 클릭
3. "헤라" 입력 후 [검색] 클릭
4. `헤라 (ID: 68)`가 정상 표시되고, 클릭 시 입력창에 `68`이 자동 입력되는지 확인

### 시나리오 2: 올원챗 부재 브랜드("헤라", "샤넬") 질의 가드레일 확인
1. `https://ezenitac.duckdns.org/bteam/chatb/` 접속
2. "헤라 스킨케어 제품 추천해줘" 입력 후 [분석 요청] 클릭
3. `[익명]` 추천이나 엉뚱한 제품 카드 없이, "죄송합니다. 현재 '헤라' 브랜드의 등록 상품 및 리뷰 데이터가 올리뷰에 존재하지 않습니다." 표준 안내 메시지가 나오는지 확인

### 시나리오 3: 올원챗 정상 브랜드("차앤박") 질의 확인
1. "차앤박 프로폴리스 앰플 수분감 분석해줘" 질의
2. 차앤박 실제 제품 3개 카드 및 고품질 솔루션 답변 정상 출력 확인

### 시나리오 4: E2E 서비스 무결성 검증
```powershell
powershell -ExecutionPolicy Bypass -File specs/003-e2e-service-stabilization/scripts/verify_e2e_services.ps1 -Mode Local
```
10개 체크포인트 전체 PASS 확인.
