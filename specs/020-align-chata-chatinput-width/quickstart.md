# Quickstart & Verification Guide

**Feature**: `020-align-chata-chatinput-width` (Oliview Chatbot A 대화 입력창 가로 너비 정렬 최적화)

## 1. Prerequisites

- Python 가상환경 및 Streamlit 설치 확인
- Chatbot A 소스코드: `bteam/Oliview_chatbot_a/app.py`

## 2. Verification Steps

### Step 1: CSS 스타일 계약 반영 확인
`bteam/Oliview_chatbot_a/app.py` 파일의 Custom CSS 블록에 `stBottomBlockContainer`, `stBottom`, `stChatInput` 관련 1200px 최대 너비 및 중앙 정렬, 블러 효과가 정의되었는지 확인합니다.

### Step 2: 로컬 Streamlit 실행 및 UI 확인
```bash
cd C:\AISERVICE\bteam\Oliview_chatbot_a
streamlit run app.py --server.port 8501 --server.headless true
```

### Step 3: 해상도별 정렬 검증 (Acceptance Criteria)
1. **와이드 데스크톱 (1920x1080 / QHD / 4K)**:
   - 상단 `.block-container`의 좌우 경계선과 하단 `st.chat_input`의 좌우 경계선이 정확히 일치하는지 확인 (1200px 중앙 정렬).
2. **태블릿 / 노트북 (1024px, 768px)**:
   - 브라우저 창 크기를 줄였을 때 입력창과 본문 컨텐츠가 동일한 비율로 부드럽게 축소되는지 확인.
3. **모바일 (360px ~ 480px)**:
   - 좌우 0.75rem 패딩이 적용되어 화면 잘림 및 가로 스크롤 없이 풀 와이드로 표시되는지 확인.
4. **스크롤 블러 효과 (Backdrop Blur)**:
   - 질문을 여러 번 전송하여 대화 스크롤이 발생할 때, 하단 입력창 뒤로 지나가는 메시지가 반투명 블러 처리되어 가독성이 유지되는지 확인.
