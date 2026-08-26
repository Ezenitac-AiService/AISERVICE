# Quickstart: ChatA 모바일 레이아웃 최적화 검증 가이드

**Feature**: `040-chata-mobile-header-and-layout-optimization`  
**Date**: 2026-08-26  

---

## 1. 실시간 모바일 뷰포트 검증 방법

### 방법 1: Chrome DevTools 모바일 에뮬레이터
1. 브라우저에서 `https://ezenitac.duckdns.org/bteam/chata/` 접속
2. `F12` (개발자 도구) 열기 $\rightarrow$ `Ctrl + Shift + M` (디바이스 툴바 전환)
3. 디바이스 선택: `iPhone 14 Pro (393 x 852)` 또는 `Samsung Galaxy S20 (360 x 800)`
4. 최상단으로 스크롤하여 **"🌿 Oliview" 로고 및 타이틀의 상단 잘림이 전혀 없는지 확인** (0px Clipping).
5. 카테고리 선택 영역이 **3열 2행(3x2 컴팩트 그리드)**으로 배치되어 6개 버튼이 높이 90px 이내로 깔끔하게 정렬되는지 확인.

### 방법 2: 실제 스마트폰 브라우저 접속
1. 모바일 기기에서 `https://ezenitac.duckdns.org/bteam/chata/` 접속
2. 상단 노치/다이나믹 아일랜드 영역과 타이틀 간섭 여부 및 하단 홈 바 Safe-Area 확인.
3. 1클릭 질문 예시 탭 시 즉시 하단 대화 생성 시작 및 스트리밍 확인.

---

## 2. 자동화 테스트 실행

```bash
# ChatA 테스트 스위트 실행
cd c:\AISERVICE\bteam\Oliview_chatbot_a
uv run python -m pytest tests/test_feature_039_zero_search.py -v
```
