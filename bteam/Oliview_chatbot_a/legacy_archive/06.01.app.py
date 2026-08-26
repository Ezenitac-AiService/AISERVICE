# Streamlit : "Python 코드만으로 웹사이트를 만들 수 있는 라이브러리"
# 실행: uv run --active streamlit run 06.01.app.py --server.fileWatcherType none

"""
06.app.py
================================================================================
[06단계] Oliview Streamlit 웹 챗봇
================================================================================

역할
    1. Streamlit으로 Oliview 챗봇 웹 화면을 구성합니다.
    2. 05.chatbot.py를 동적으로 불러옵니다.
    3. 임베딩 모델, ChromaDB, BM25, 리랭커, LLM을 한 번만 초기화합니다.
    4. 사용자의 질문을 05.chatbot.py에 전달합니다.
    5. 생성된 답변을 채팅 화면에 출력합니다.

실행 명령어
    uv run --active streamlit run 06.app.py

주의
    1. 05.chatbot.py와 06.app.py는 같은 폴더에 둡니다.
    2. 05.chatbot.py에 다음 함수가 있어야 합니다.
       - create_chatbot()
       - generate_chatbot_answer(chatbot, question)
    3. GPU 서버의 LLM API가 실행 중이어야 합니다.
================================================================================
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import streamlit as st


# =============================================================================
# [1] Streamlit 페이지 기본 설정
# =============================================================================

st.set_page_config(
    page_title="OliChat",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# [2] 프로젝트 경로 설정
# =============================================================================

ROOT_DIR = Path(__file__).resolve().parent
CHATBOT_FILE_PATH = ROOT_DIR / "05.01.chatbot_list_memory.py"


# =============================================================================
# [2-1] 카테고리별 분석 가능 속성
# =============================================================================

CATEGORY_ATTRIBUTES: dict[str, list[str]] = {
    "스킨케어": ["기능/효과", "발림성", "수분감", "자극성", "향", "흡수력"],
    "클렌징": ["기능/효과", "사용감", "수분감", "자극성", "제형", "향"],
    "선케어": ["기능/효과", "발림성", "사용감", "자극성", "지속력", "피부표현"],
    "립메이크업": ["발림성", "발색력", "수분감", "자극성", "지속력", "향"],
    "베이스메이크업": ["밀착력", "발림성", "수분감", "자극성", "지속력", "커버력"],
    "아이메이크업": ["밀착력", "발림성", "발색력", "자극성", "지속력"],
}

CATEGORY_ICONS: dict[str, str] = {
    "스킨케어": "🧴",
    "클렌징": "🧼",
    "선케어": "☀️",
    "립메이크업": "💋",
    "베이스메이크업": "🧴",
    "아이메이크업": "👁️",
}

ATTRIBUTE_ICONS: dict[str, str] = {
    "기능/효과": "💫",
    "발림성": "🖐️",
    "수분감": "💧",
    "자극성": "💥",
    "향": "🌸",
    "흡수력": "💦",
    "사용감": "🤲",
    "제형": "🥛",
    "지속력": "⏱️",
    "피부표현": "🌟",
    "발색력": "🎨",
    "밀착력": "🧲",
    "커버력": "🩹",
}


# =============================================================================
# [3] 05.chatbot.py 동적 로드
# =============================================================================

@st.cache_resource
def load_chatbot_module() -> ModuleType:
    """숫자와 점이 포함된 05.chatbot.py를 동적으로 불러옵니다."""

    if not CHATBOT_FILE_PATH.is_file():
        raise FileNotFoundError(
            "05.chatbot.py를 찾지 못했습니다.\n"
            f"확인 경로: {CHATBOT_FILE_PATH}"
        )

    module_name = "oliview_chatbot"
    spec = importlib.util.spec_from_file_location(module_name, CHATBOT_FILE_PATH)

    if spec is None or spec.loader is None:
        raise ImportError("05.chatbot.py의 모듈 정보를 생성하지 못했습니다.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# =============================================================================
# [4] 챗봇 구성요소 초기화
# =============================================================================

@st.cache_resource(show_spinner=False)
def initialize_chatbot() -> tuple[ModuleType, Any]:
    """검색 및 LLM 구성요소를 한 번만 초기화합니다."""

    chatbot_module = load_chatbot_module()

    if not hasattr(chatbot_module, "create_chatbot"):
        raise AttributeError("05.chatbot.py에 create_chatbot() 함수가 없습니다.")

    if not hasattr(chatbot_module, "generate_chatbot_answer"):
        raise AttributeError(
            "05.chatbot.py에 generate_chatbot_answer() 함수가 없습니다."
        )

    chatbot = chatbot_module.create_chatbot()
    return chatbot_module, chatbot


# =============================================================================
# [5] 세션 상태 초기화
# =============================================================================

if "selected_category" not in st.session_state:
    st.session_state.selected_category = "스킨케어"

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "안녕하세요!\n\n"
                "궁금한 제품의 브랜드명, 상품명, 분석하고 싶은 속성을 함께 입력해 주세요.\n\n"
                "예: **컬러그램 탕후루 탱글 꿀로스의 발림성 장단점을 분석해줘**"
            ),
        }
    ]


if "pending_question" not in st.session_state:
    st.session_state.pending_question = None

if "is_generating" not in st.session_state:
    st.session_state.is_generating = False


# =============================================================================
# [6] 화면 디자인
# =============================================================================
st.markdown(
    """
    <style>
    :root {
        --olive-green: #2f9e44;
        --olive-green-dark: #237a35;
        --olive-green-soft: #f3faf4;
        --olive-green-softer: #f8fcf8;
        --olive-border: #dbe8de;
        --line: #e7e9ed;
        --text-main: #18212f;
        --text-sub: #667085;
        --surface: #ffffff;
        --sidebar: #f7f7f8;
    }

    html, body, [class*="css"] {
        font-family: "Pretendard", "Noto Sans KR", "Malgun Gothic", sans-serif;
    }

    .stApp {
        background: #ffffff;
        color: var(--text-main);
    }

    /* 메인 전체 폭과 여백은 기존 배치를 유지합니다. */
    .block-container {
        max-width: 1180px;
        padding-top: 3.1rem;
        padding-bottom: 9rem;
    }

    header[data-testid="stHeader"] {
        background: rgba(255, 255, 255, 0.92);
        backdrop-filter: blur(10px);
    }

    /* =========================================================
       Sidebar — ChatGPT처럼 단순하고 조용한 보조 영역
    ========================================================= */

  section[data-testid="stSidebar"] {
    width: 320px !important;
    background: var(--sidebar);
    border-right: 1px solid #e4e6ea;
    }

    section[data-testid="stSidebar"] > div {
        width: 320px !important;
    }

    section[data-testid="stSidebar"] .block-container {
        padding-top: 3.2rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }

    .sidebar-beta-card {
        padding: 15px 12px 12px;
        border: none;
        border-radius: 12px;
        background: transparent;
        box-shadow: none;
    }

    .beta-label {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        margin-bottom: 14px;
        color: #20262f;
        font-size: 17px;
        font-weight: 850;
        letter-spacing: -0.2px;
    }

    .beta-copy {
        margin-bottom: 16px;
        color: #525b67;
        font-size: 14px;
        line-height: 1.8;
    }

    .feature-list {
        margin-top: 15px;
        padding-top: 15px;
        border-top: 1px solid #dedfe3;
        color: #3f4752;
        font-size: 14px;
        font-weight: 700;
        line-height: 2;
    }

    section[data-testid="stSidebar"] .stButton {
        margin-top: 10px;
    }

    section[data-testid="stSidebar"] .stButton > button {
        min-height: 42px;
        border: 1px solid #d9dce1;
        border-radius: 10px;
        background: #ffffff;
        color: #4c5561;
        font-size: 12px;
        font-weight: 700;
        box-shadow: none;
        transition: background 0.15s ease, border-color 0.15s ease;
    }

    section[data-testid="stSidebar"] .stButton > button:hover {
        border-color: #b9d9c0;
        color: var(--olive-green-dark);
        background: #f8fcf9;
    }

    /* =========================================================
       제목 — 서비스 로고처럼, 과도한 카드감 없이
    ========================================================= */

    .oliview-title {
        text-align: center;
        margin: 0 0 7px;
        color: #151c2a;
        font-size: clamp(39px, 4.3vw, 48px);
        line-height: 1;
        font-weight: 900;
        letter-spacing: -1.8px;
    }

    .oliview-subtitle {
        text-align: center;
        margin-bottom: 28px;
        color: #485467;
        font-size: 14px;
        font-weight: 550;
    }

    /* =========================================================
       분석 안내 — 내용과 배치는 그대로, 시각적 무게만 정돈
    ========================================================= */

    .panel-title {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 18px;
        color: #202938;
        font-size: 16px;
        font-weight: 850;
        letter-spacing: -0.2px;
    }

    .section-label {
        margin: 15px 0 9px;
        color: #5c6675;
        font-size: 12px;
        font-weight: 750;
    }

    .brand-box {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 19px;
    }

    .brand-chip {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 32px;
        padding: 6px 12px;
        border: 1px solid #dce8df;
        border-radius: 999px;
        background: #f7fbf8;
        color: #347343;
        font-size: 13.5px;
        font-weight: 750;
    }

    /* =========================================================
       카테고리 버튼 — 도구 버튼보다 대화 제안 버튼처럼
    ========================================================= */

    div[data-testid="stHorizontalBlock"] .stButton > button {
        width: 100%;
        min-height: 46px;
        padding: 8px 10px;
        border: 1px solid #e0e3e7;
        border-radius: 13px;
        background: #ffffff;
        color: #3b4450;
        font-size: 12.5px;
        font-weight: 750;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.025);
        white-space: nowrap;
        transition: all 0.15s ease;
    }

    div[data-testid="stHorizontalBlock"] .stButton > button:hover {
        border-color: #b8dcbf;
        color: var(--olive-green-dark);
        background: #f8fcf9;
        transform: translateY(-1px);
        box-shadow: 0 4px 10px rgba(27, 68, 37, 0.05);
    }

    div[data-testid="stHorizontalBlock"] .stButton > button[kind="primary"] {
        border: 1.5px solid var(--olive-green);
        background: #eef8f0;
        color: var(--olive-green-dark);
        box-shadow: 0 0 0 3px rgba(47, 158, 68, 0.07);
    }

    /* =========================================================
       속성 영역 — 박스는 유지하되 카드 느낌을 약하게
    ========================================================= */

    .attribute-card {
        margin-top: 26px;
        padding: 17px 17px 16px;
        border: 1px solid #e0e9e2;
        border-radius: 14px;
        background: var(--olive-green-softer);
        box-shadow: none;
    }

    .attribute-card-title {
        margin-bottom: 13px;
        color: #2a3530;
        font-size: 13.5px;
        font-weight: 850;
    }

    .attribute-box {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
    }

    .attribute-chip {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 7px;
        min-height: 33px;
        padding: 6px 11px;
        border: 1px solid #dce8df;
        border-radius: 999px;
        background: #ffffff;
        color: #354039;
        font-size: 12px;
        font-weight: 750;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.025);
    }

    .attribute-chip-icon {
        font-size: 14px;
        line-height: 1;
    }

    .brand-name {
    color: #2F9E44;
    font-weight: 800;
    }

    .example-tag{
    display:inline-block;
    margin-bottom:4px;
    padding:2px 6px;
    border-radius:999px;
    background:#FFF4D6;
    color:#9A6700;
    font-size:10px;
    font-weight:700;
    }
    /* =========================================================
       질문 예시 — 오른쪽 배치는 유지, 카드 중첩만 완화
    ========================================================= */

    .top-card {
        height: auto;
        min-height: auto;
        padding: 18px 15px;
        border: 1px solid #e1e4e8;
        border-radius: 16px;
        background: #ffffff;
        box-shadow: 0 8px 24px rgba(16, 24, 40, 0.045);
    }

    .top-card .panel-title {
        margin-bottom: 12px;
    }

    .example-item {
        padding: 10px 10px;
        margin-bottom: 4px;
        border: 1px solid transparent;
        border-radius: 10px;
        background: transparent;
        color: #535d6a;
        font-size: 11.8px;
        line-height: 1.5;
        transition: background 0.15s ease, border-color 0.15s ease;
    }

    .example-item:hover {
        border-color: #e4ece6;
        background: #f7faf8;
    }

    .example-item strong {
        color: #202b24;
        font-weight: 800;
    }

    .example-item:last-child {
        margin-bottom: 0;
    }

    /* =========================================================
       채팅 — 실제 대화 메시지처럼 보이도록
    ========================================================= */

    hr {
        margin: 22px 0 18px !important;
        border-color: #e5e7eb !important;
    }

    /* AI 메시지 카드 제거 */
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
        margin: 0 0 10px;
        padding: 0;
        border: none;
        border-radius: 0;
        background: transparent;
        box-shadow: none;
    }

    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
        margin-left: 9%;
        background: #f1f8f3;
        border-color: #dce9df;
    }

    [data-testid="stChatMessageContent"] {
        color: #303a49;
        font-size: 13.5px;
        line-height: 1.72;
    }

    [data-testid="stChatMessageContent"] p:last-child {
        margin-bottom: 0;
    }

    /* =========================================================
    Chat Input
    ========================================================= */

    [data-testid="stChatInput"] {
        position: fixed;
        left: calc(320px + (100vw - 320px) / 2);
        transform: translateX(-50%);
        bottom: clamp(28px, 4vh, 40px);

        width: 980px;
        max-width: calc(100vw - 360px);
        z-index: 999;
    }

    /* 입력창 가장 바깥 테두리 */
    [data-testid="stChatInput"] > div {
        min-height: 56px !important;
        height: 56px !important;
        padding: 0 !important;

        border: 1px solid #dfe3e8;
        border-radius: 14px;
        background: #ffffff;

        box-shadow:
            0 10px 30px rgba(16, 24, 40, 0.09),
            0 2px 8px rgba(16, 24, 40, 0.04);

        overflow: hidden;
    }

    /* Streamlit 내부 가로 컨테이너 */
    [data-testid="stChatInput"] [data-baseweb="textarea"] {
        min-height: 50px !important;
        height: 50px !important;
        padding: 0 !important;
        margin: 0 !important;
    }

    /* data-baseweb 안쪽 wrapper */
    [data-testid="stChatInput"] [data-baseweb="textarea"] > div {
        min-height: 44px !important;
        height: 44px !important;
        padding: 0 !important;
        margin: 0 !important;
    }

    /* 실제 입력 영역 */
    [data-testid="stChatInput"] textarea {
        min-height: 50px !important;
        height: 50px !important;
        max-height: 50px !important;

        padding: 15px 54px 11px 18px !important;
        margin: 0 !important;

        border: none !important;
        color: #273140;
        font-size: 14px !important;
        line-height: 20px !important;

        resize: none !important;
        overflow-y: hidden !important;
        box-sizing: border-box !important;
    }

    /* 전송 버튼 영역 */
    
     /* 기본(입력 없을 때 회색) */
    button[data-testid="stChatInputSubmitButton"] {
        width: 42px !important;
        height: 42px !important;

        background: #d1d5db !important;
        color: white !important;

        border: none !important;
        border-radius: 10px !important;

        /* 추가 */
        transform: translateX(-6px) translateY(2px) !important;;

        transition: background 0.2s ease;
    }

    /* 입력하면 초록 */
    [data-testid="stChatInput"]:has(textarea:not(:placeholder-shown))
    button[data-testid="stChatInputSubmitButton"] {
        background: #2F9E44 !important;
    }

    /* 입력했을 때 hover */
    [data-testid="stChatInput"]:has(textarea:not(:placeholder-shown))
    button[data-testid="stChatInputSubmitButton"]:hover {
        background: #237A35 !important;
    }

    /* 클릭 */
    [data-testid="stChatInput"]:has(textarea:not(:placeholder-shown))
    button[data-testid="stChatInputSubmitButton"]:active {
        background: #1B5E20 !important;
    }

    button[data-testid="stChatInputSubmitButton"] svg {
    color: white !important;
    fill: white !important;
    }

    [data-testid="stChatInputSubmitButton"] svg {
        transform: translateY(2px);
     }

    /* 포커스 */
    [data-testid="stChatInput"] > div:focus-within {
        border-color: #9ccfa7;
        box-shadow:
            0 0 0 4px rgba(47, 158, 68, 0.08),
            0 12px 32px rgba(16, 24, 40, 0.10);
    }

    [data-testid="stChatInput"] textarea::placeholder {
        color: #9aa2ad;
    }

    @media (max-width: 900px) {
        .block-container {
            padding-top: 1rem;
            padding-bottom: 8rem;
        }

        .top-card {
            min-height: auto;
            margin-bottom: 12px;
        }

        [data-testid="stChatInput"] {
            left: 50%;
            width: calc(100vw - 28px);
            max-width: none;
        }

        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
            margin-left: 0;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)



# =============================================================================
# [7] 화면 제목# =============================================================================
# [7] 화면 제목
# =============================================================================

st.markdown('<div class="oliview-title">OliChat</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="oliview-subtitle">올리브영 리뷰 기반 화장품 분석 챗봇</div>',
    unsafe_allow_html=True,
)


# =============================================================================
# [8] 왼쪽 Sidebar - Beta Service
# =============================================================================

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-beta-card">
            <div class="beta-label">🧪 Beta Service</div>
            <div class="beta-copy">
                현재 일부 브랜드를 대상으로<br>
                올리브영 리뷰 기반 AI 분석 서비스를 제공합니다.<br><br>
                지원 범위는 지속적으로 확대될 예정입니다.
            </div>
            <div class="feature-list">
                ✔ 장점·개선점 분석<br>
                ✔ 속성별 리뷰 분석<br>
                ✔ 상품 목록 조회 <br>
                ✔ 리뷰 기반 제품 추천 <br>
                ✔ 최근 대화 기억 <br>
                ✔ 리뷰 기반 AI 답변(RAG)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "🗑 대화 내용 초기화",
        use_container_width=True,
        disabled=st.session_state.is_generating,
    ):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "안녕하세요!\n\n"
                    "브랜드명, 상품명, 궁금한 속성을 포함하여 질문해주세요.\n\n"
                ),
            }
        ]
        st.session_state.pending_question = None
        st.session_state.is_generating = False
        st.rerun()


# =============================================================================
# [9] 메인 2열 - 분석 안내 · 질문 예시
# =============================================================================

center_column, right_column = st.columns(
    [3.0, 1.05],
    gap="large",
    vertical_alignment="top",
)

with center_column:
    st.markdown(
        '<div class="panel-title">🔍 분석 안내</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-label">지원 브랜드</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="brand-box">
            <span class="brand-chip">브링그린</span>
            <span class="brand-chip">식물나라</span>
            <span class="brand-chip">차앤박</span>
            <span class="brand-chip">컬러그램</span>
            <span class="brand-chip">헤라</span>     
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
    """
    <div class="section-label">
        카테고리 선택
        <span style="
            font-size:11px;
            color:#8A94A6;
            font-weight:500;
            margin-left:6px;
        ">
            (클릭하여 지원 속성 확인)
        </span>
    </div>
    """,
    unsafe_allow_html=True,
    )

    category_names = list(CATEGORY_ATTRIBUTES.keys())
    first_row = category_names[:3]
    second_row = category_names[3:]

    for row_index, row_categories in enumerate((first_row, second_row)):
        category_columns = st.columns(len(row_categories), gap="small")

        for index, category_name in enumerate(row_categories):
            is_selected = st.session_state.selected_category == category_name

            with category_columns[index]:
                if st.button(
                    f"{CATEGORY_ICONS.get(category_name, '•')} {category_name}",
                    key=f"category_button_{row_index}_{category_name}",
                    type="primary" if is_selected else "secondary",
                    use_container_width=True,
                    disabled=st.session_state.is_generating,
                ):
                    st.session_state.selected_category = category_name
                    st.rerun()

    selected_category = st.session_state.selected_category
    selected_attributes = CATEGORY_ATTRIBUTES[selected_category]

    attribute_html = "".join(
        f'<span class="attribute-chip">'
        f'<span class="attribute-chip-icon">'
        f'{ATTRIBUTE_ICONS.get(attribute_name, "•")}'
        f'</span>'
        f'<span>{attribute_name}</span>'
        f'</span>'
        for attribute_name in selected_attributes
    )

    st.markdown(
        f"""
    <div class="attribute-card">
        <div class="attribute-card-title">
            ✨ <strong style="color:#2E9E44;">{selected_category}</strong>에서 분석 가능한 속성
        </div>
        <div class="attribute-box">{attribute_html}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

with right_column:
    st.markdown(
        """
        <div class="top-card">
            <div class="panel-title">💡 질문 예시</div>
            <div class="example-item"><strong><span class="brand-name">브링그린</span> 징크테카 파이토 선 젤</strong><br>사용감 분석해줘</div>           
            <div class="example-item"><strong><span class="brand-name">식물나라</span> 어린녹차 클렌징밤</strong><br>부정리뷰 분석해줘</div>
            <div class="example-item"><strong><span class="brand-name">차앤박</span> 프로폴리스 앰플</strong><br>수분감을 분석해줘</div>
            <div class="example-item"><strong><span class="brand-name">컬러그램</span> 탕후루 탱글 꿀로스</strong><br>발색력 장단점 알려줘</div>
            <div class="example-item"><strong><span class="brand-name">헤라</span> 실키스테이 롱웨어 파운데이션</strong><br>장점과 부정의견 알려줘</div>
            <div class="example-item"><span class="example-tag">번외</span><br><strong><span class="brand-name">헤라</span> 스킨케어</strong> 제품 추천해줘</div>
            <div class="example-item"><span class="example-tag">번외</span><br><strong>립틴트</strong> 발색력이 좋은 제품 추천해줘</div>

        </div>
        """,
        unsafe_allow_html=True,
    )

st.divider()


# =============================================================================
# [10] 기존 대화 기록 출력
# =============================================================================

for message in st.session_state.messages:
    avatar = "🤖" if message["role"] == "assistant" else "🙂"
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])


# =============================================================================
# [11] 사용자 질문 입력 및 답변 생성
# =============================================================================

question = st.chat_input(
    "상품명과 궁금한 내용을 입력하세요.",
    disabled=st.session_state.is_generating,
)

# 새 질문이 전송되면 먼저 세션 상태에 보관합니다.
# 이후 Streamlit이 재실행되더라도 pending_question을 이용해 답변 생성을 이어갑니다.
if question:
    cleaned_question = question.strip()

    if not cleaned_question:
        st.warning("질문을 입력해주세요.")
        st.stop()

    st.session_state.pending_question = cleaned_question
    st.session_state.messages.append(
        {"role": "user", "content": cleaned_question}
    )
    st.session_state.is_generating = True
    st.rerun()


# 처리할 질문이 남아 있으면 답변을 생성합니다.
if st.session_state.pending_question:
    pending_question = st.session_state.pending_question

    with st.chat_message("assistant", avatar="🤖"):
        try:
            with st.spinner("검색 모델과 LLM을 불러오고 답변을 생성하고 있습니다..."):
                chatbot_module, chatbot = initialize_chatbot()
                answer = chatbot_module.generate_chatbot_answer(
                    chatbot=chatbot,
                    question=pending_question,
                    history=st.session_state.messages[:-1],
                )

            if not answer or not str(answer).strip():
                answer = (
                    "답변을 생성하지 못했습니다. "
                    "질문을 조금 더 구체적으로 입력해주세요."
                )

        except Exception as error:
            answer = (
                "답변을 생성하는 중 오류가 발생했습니다.\n\n"
                f"- 오류 종류: `{type(error).__name__}`\n"
                f"- 오류 내용: `{error}`\n\n"
                "`05.chatbot.py`와 현재 앱 파일이 같은 폴더에 있는지 확인해주세요."
            )

        st.markdown(answer)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer}
    )

    # 답변 생성이 끝난 후 대기 상태를 해제합니다.
    st.session_state.pending_question = None
    st.session_state.is_generating = False
    st.rerun()