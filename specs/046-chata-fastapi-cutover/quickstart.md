# Quickstart & Verification Guide (Feature 046)

**Feature**: [spec.md](./spec.md) (Oliview ChatA FastAPI 웹 서비스 완전 전환 및 Uvicorn 단일 엔트리포인트 일원화)

---

## 1. Prerequisites

- Python 3.12+
- `uv` 패키지 매니저
- Model Gateway (Port 8081) 또는 목 서버 기동

---

## 2. Automated Test Execution

ChatA FastAPI 웹 스트리밍 및 헬스체크 회귀 테스트 실행:

```powershell
uv run --project bteam/Oliview_chatbot_a python -m pytest bteam/Oliview_chatbot_a/tests/test_fastapi_web_stream.py -v
```

---

## 3. Local Web Server Launch

FastAPI ChatA 단일 메인 서버 실행:

```powershell
$env:PYTHONPATH="bteam;bteam/Oliview_chatbot_a"
uv run --project bteam/Oliview_chatbot_a python -m uvicorn bteam.Oliview_chatbot_a.main:app --host 0.0.0.0 --port 8501 --reload
```

---

## 4. Manual Verification Steps

1. **브라우저 접속**: `http://localhost:8501/` 열기
   - 데스크탑: 좌측 설정(브랜드, 카테고리, 속성)과 우측 1클릭 질문 예시 2열 배치 확인
   - 브라우저 창 축소 (모바일 $\le 768\text{px}$): 카테고리가 3열 2행(3x2) 컴팩트 그리드로 반응형 전환되는지 확인
2. **질문 전송 테스트**:
   - 1클릭 예시 질문(예: "차앤박 프로폴리스 앰플 수분감 어때?") 클릭
   - 4단계 상태 표시기 실시간 진행 및 답변 텍스트 부드러운 스트리밍 확인
3. **참조 리뷰 확인**:
   - 답변 하단 "📚 참조 리뷰 원문" 아코디언 클릭하여 올리브영 상품 링크 및 본문 인용 정상 노출 확인
4. **새로고침 테스트**:
   - 브라우저 `F5` 새로고침 후 이전 대화 내역이 복원되는지 확인
