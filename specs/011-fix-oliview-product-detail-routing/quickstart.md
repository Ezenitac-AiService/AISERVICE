# Quickstart: Oliview 상품 상세 조회 및 라우팅 검증 가이드

**Feature**: `011-fix-oliview-product-detail-routing` | **Date**: 2026-08-18

---

## 1. 사전 조건 (Prerequisites)

- 전체 Docker 마이크로서비스 기동 완료 (`aiservice-gateway`, `oliview_backend`, `oliview_frontend`, `bteam_db`)
- Python 3.10+ 및 `unittest` 가용

---

## 2. 빠른 서비스 재기동 (핫리로드 볼륨 마운트 적용)

```bash
docker-compose up -d --build oliview_backend oliview_frontend
```

---

## 3. 자동화된 계약 검증 테스트 실행

```bash
# 통합 회귀 테스트 스위트 실행 (Python 표준 라이브러리)
python tests/test_multi_chatbot_regression.py
```

### 예상 출력 (Expected Output)
```text
[PASS] Model Gateway Embedding (8090): 0.045s (Dim: 1024)
[PASS] PILOS Knowledge Cache: 15.2ms
[PASS] AllOneChat RAG API Endpoint: Status 200 (1.10s)
[PASS] OllyChat Streamlit Portal: Status 200 OK
[PASS] Multi-Chatbot Concurrency Isolation: All 200 OK
[PASS] Oliview Web Portal Routing: Status 200 OK
[PASS] PILOS Web Portal Routing: Status 200 OK

----------------------------------------------------------------------
Ran 7 tests in 2.150s

OK
```

---

## 4. 수동 UI 종단간(E2E) 브라우저 검증 시나리오

1. 브라우저에서 `https://ezenitac.duckdns.org/bteam/oliview/` 접속
2. 좌측 메뉴에서 **'내 브랜드'** 클릭 (헤라 브랜드)
3. 상품 그리드에서 **'블랙 쿠션'** (또는 등록된 임의의 상품) 카드 클릭
4. **검증 지점**:
   - 화면 중앙 상단에 상품명, 브랜드명, 상품 이미지, 옵션 목록이 정상 노출되는지 확인
   - 하단 '속성별 유지/개선점 분석' 탭에서 오각형/방사형 레이더 차트 및 긍정/개선점 분석 요약 카드가 렌더링되는지 확인
   - 브라우저 개발자 도구 (F12) 콘솔(Console)에 `404 (Not Found)` 또는 `SyntaxError: Unexpected token '<'` 에러가 **0건**인지 확인
5. 상단 **'← 상품 목록으로'** 클릭 시 목록 화면으로 즉시 정상 복귀하는지 확인
