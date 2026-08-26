"""
Oliview ChatA - Modernized Streamlit Web Application (06.app.py)
Powered by bteam.oliview_core Unified RAG Engine.
"""

import sys
import os
import time
import urllib.parse
import streamlit as st

# [1] Ensure oliview_core and parent directories are accessible
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BTEAM_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
WORKSPACE_DIR = os.path.abspath(os.path.join(BTEAM_DIR, ".."))

for p in [CURRENT_DIR, BTEAM_DIR, WORKSPACE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from oliview_core.pipeline import prepare_pipeline_stream
from oliview_core.callback import StreamlitStepCallback
from oliview_core.session import session_store
from oliview_core.sanitizer import (
    SUPPORTED_BRANDS,
    CATEGORY_ATTRIBUTES,
    BRAND_OY_URLS,
    build_oliveyoung_url,
    clean_review_noise,
)
from oliview_core.types import StepEvent, StepCode, RagExecutionMetadata

# [2] Streamlit Page Configuration
st.set_page_config(
    page_title="Oliview - 올리브영 화장품 리뷰 분석 챗봇",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# [3] Custom CSS (Design System & Auto Line-Wrap Button Optimization)
st.markdown(
    """
    <style>
    /* Global & Typography */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Apple SD Gothic Neo", sans-serif;
    }

    /* Main Container Padding */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 5rem !important;
        max-width: 1200px !important;
        margin: 0 auto !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    /* Spec 020: Bottom Fixed Wrapper Styling & Backdrop Blur */
    [data-testid="stBottom"],
    div[data-testid="stBottom"] {
        background: rgba(255, 255, 255, 0.88) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border-top: 1px solid rgba(220, 232, 224, 0.6) !important;
    }

    /* Spec 020: Bottom Block Container (Input Box Container) Max-Width & Center Alignment */
    [data-testid="stBottomBlockContainer"],
    .stBottomBlockContainer,
    div[data-testid="stBottom"] > div {
        max-width: 1200px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        box-sizing: border-box !important;
        width: 100% !important;
    }

    /* Spec 020: Chat Input Widget Constraints */
    [data-testid="stChatInput"],
    .stChatInput {
        max-width: 1200px !important;
        margin: 0 auto !important;
    }

    /* Spec 020: Mobile & Tablet Responsive Optimization */
    @media (max-width: 768px) {
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 4.5rem !important;
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }
        [data-testid="stBottomBlockContainer"],
        .stBottomBlockContainer {
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }
    }

    /* Title Section */
    .app-header {
        text-align: center;
        margin-bottom: 24px;
    }
    .app-title {
        font-size: 32px;
        font-weight: 800;
        color: #1a2e1d;
        letter-spacing: -0.5px;
        margin-bottom: 4px;
    }
    .app-subtitle {
        font-size: 14px;
        color: #5a7060;
        font-weight: 500;
    }

    /* Panel Headers */
    .panel-title {
        font-size: 16px;
        font-weight: 700;
        color: #213527;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .section-label {
        font-size: 12px;
        font-weight: 700;
        color: #496350;
        margin-top: 10px;
        margin-bottom: 6px;
    }

    /* Brand Chips */
    .brand-box {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 14px;
    }
    .brand-chip {
        display: inline-block;
        padding: 5px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        color: #2b6e3f;
        background-color: #ebf5ee;
        border: 1px solid #c7e6cf;
    }

    /* Attribute Card */
    .attribute-card {
        background: #f7faf8;
        border: 1px solid #e0ebe3;
        border-radius: 10px;
        padding: 12px 14px;
        margin-top: 14px;
    }
    .attribute-card-title {
        font-size: 13px;
        font-weight: 700;
        color: #213527;
        margin-bottom: 8px;
    }
    .attribute-box {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
    }
    .attribute-chip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px 10px;
        border-radius: 16px;
        font-size: 12px;
        font-weight: 600;
        background: #ffffff;
        color: #2c4233;
        border: 1px solid #d4e3d8;
    }

    /* FR-012 / T014a: 1-Click Example Query Button Layout & Auto-Wrap CSS */
    div[data-testid="column"]:nth-of-type(2) .stButton > button {
        height: auto !important;
        min-height: 48px !important;
        white-space: normal !important;
        word-break: keep-all !important;
        text-align: left !important;
        padding: 8px 14px !important;
        line-height: 1.4 !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        border: 1px solid #dce8e0 !important;
        background-color: #ffffff !important;
        color: #2a3d30 !important;
        transition: all 0.2s ease !important;
        margin-bottom: 6px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02) !important;
    }
    div[data-testid="column"]:nth-of-type(2) .stButton > button:hover {
        border-color: #2E9E44 !important;
        background-color: #f6fbf7 !important;
        color: #2E9E44 !important;
        transform: translateY(-1px) !important;
    }

    /* Chat Messages */
    [data-testid="stChatMessage"] {
        padding: 6px 0 !important;
    }

    /* Accordion Customization */
    .stAccordion {
        margin-top: 10px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# [4] Category Example Queries Mapping
CATEGORY_EXAMPLE_QUERIES = {
    "스킨케어": [
        ("차앤박 앰플 수분감", "차앤박 프로폴리스 앰플 수분감과 흡수력 알려줘"),
        ("식물나라 토너 자극성", "식물나라 토너 자극성과 기능/효과 분석해줘"),
        ("브링그린 세럼 진정", "브링그린 티트리 세럼 진정 효과와 사용감 어때?"),
        ("스킨케어 수분 앰플", "스킨케어에서 수분감 좋은 인기 앰플 추천해줘"),
    ],
    "클렌징": [
        ("식물나라 클렌징 세정력", "식물나라 클렌징폼 세정력과 거품력 어때?"),
        ("순한 클렌징폼 추천", "자극 없이 순한 클렌징 제품 분석해줘"),
        ("브링그린 딥클렌징", "브링그린 클렌징 제품 모공 세정 효과 알려줘"),
        ("클렌징 수분감/당김", "세안 후 당김 없는 클렌징폼 추천해줘"),
    ],
    "선케어": [
        ("식물나라 선크림 백탁", "식물나라 선크림 백탁현상과 발림성 알려줘"),
        ("눈시림 없는 선크림", "눈시림 없고 순한 선케어 제품 추천해줘"),
        ("헤라 선크림 톤업", "헤라 선크림 톤업효과와 지속력 분석해줘"),
        ("브링그린 선세럼 촉촉함", "브링그린 선세럼 백탁 없이 촉촉한지 알려줘"),
    ],
    "립메이크업": [
        ("컬러그램 틴트 발색력", "컬러그램 탕후루 틴트 발색력과 착색력 어때?"),
        ("헤라 센슈얼 립 촉촉함", "헤라 센슈얼 립 촉촉함과 각질부각 분석해줘"),
        ("컬러그램 꿀로스 발림성", "컬러그램 탕후루 탱글 꿀로스의 발림성 장단점을 분석해줘"),
        ("지속력 좋은 틴트", "각질부각 없고 지속력 좋은 립 제품 추천해줘"),
    ],
    "베이스메이크업": [
        ("헤라 블랙쿠션 커버력", "헤라 블랙쿠션 커버력과 밀착력 지속력 어때?"),
        ("컬러그램 쿠션 피부톤", "컬러그램 쿠션 피부톤 보정과 다크닝 알려줘"),
        ("건성 베이스 촉촉함", "건성 피부에 촉촉하고 들뜸 없는 쿠션 추천해줘"),
        ("지성 유분감 밀착력", "유분감 적고 밀착력 높은 베이스 메이크업 제품 알려줘"),
    ],
    "아이메이크업": [
        ("컬러그램 아이라이너 번짐", "컬러그램 아이라이너 번짐과 지속력 분석해줘"),
        ("눈시림 없는 마스카라", "눈시림이나 가루날림 없는 아이메이크업 추천해줘"),
        ("선명한 아이라이너", "선명도 높고 고정력 좋은 제품 알려줘"),
        ("아이메이크업 가루날림", "가루날림 없이 깔끔하게 유지되는 제품 추천해줘"),
    ],
}

ATTRIBUTE_ICONS = {
    "기능/효과": "✨",
    "발림성": "🖐️",
    "수분감": "💧",
    "자극성": "🌿",
    "향": "🌸",
    "흡수력": "〰️",
    "거품력": "🫧",
    "세정력": "🧼",
    "눈시림": "👁️",
    "백탁현상": "☀️",
    "지속력": "⏱️",
    "톤업효과": "💡",
    "각질부각": "👄",
    "발색력": "🎨",
    "착색력": "💄",
    "촉촉함": "🍯",
    "가루날림": "💨",
    "감촉": "🧤",
    "결점커버": "🎯",
    "밀착력": "🧲",
    "유분감": "🧴",
    "피부톤": "🪞",
    "고정력": "🔒",
    "번짐": "🛡️",
    "선명도": "👁️‍🗨️",
}

# [5] Session State & Redis Persistence Initialization
import uuid
if "session_id" not in st.session_state:
    st.session_state.session_id = f"chata_user_{uuid.uuid4().hex[:12]}"
    st.session_state.chat_history = session_store.get_messages(st.session_state.session_id)
elif "chat_history" not in st.session_state:
    st.session_state.chat_history = session_store.get_messages(st.session_state.session_id)

if "selected_category" not in st.session_state:
    st.session_state.selected_category = "스킨케어"
if "pending_query" not in st.session_state:
    st.session_state.pending_query = None

# [6] Header Title
st.markdown(
    """
    <div class="app-header">
        <div class="app-title">🌿 Oliview</div>
        <div class="app-subtitle">올리브영 리뷰 기반 화장품 분석 챗봇</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# [7] Main 2-Column Grid (FR-012: Ratio [1.6, 1.4] for Perfect Button Alignment)
col_settings, col_examples = st.columns([1.6, 1.4], gap="large", vertical_alignment="top")

with col_settings:
    st.markdown('<div class="panel-title">🔍 분석 설정</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-label">지원 브랜드</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="brand-box">
            <span class="brand-chip">차앤박</span>
            <span class="brand-chip">헤라</span>
            <span class="brand-chip">식물나라</span>
            <span class="brand-chip">브링그린</span>
            <span class="brand-chip">컬러그램</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-label">카테고리 선택</div>', unsafe_allow_html=True)
    cat_list = list(CATEGORY_ATTRIBUTES.keys())
    row1 = cat_list[:3]
    row2 = cat_list[3:]

    for r_idx, row in enumerate((row1, row2)):
        cols = st.columns(len(row), gap="small")
        for c_idx, c_name in enumerate(row):
            is_sel = st.session_state.selected_category == c_name
            with cols[c_idx]:
                if st.button(
                    c_name,
                    key=f"cat_btn_{r_idx}_{c_name}",
                    type="primary" if is_sel else "secondary",
                    use_container_width=True,
                ):
                    st.session_state.selected_category = c_name
                    st.rerun()

    sel_cat = st.session_state.selected_category
    attributes = CATEGORY_ATTRIBUTES.get(sel_cat, [])
    attr_chips = "".join(
        f'<span class="attribute-chip"><span>{ATTRIBUTE_ICONS.get(a, "•")}</span><span>{a}</span></span>'
        for a in attributes
    )

    st.markdown(
        f"""
        <div class="attribute-card">
            <div class="attribute-card-title">✨ <strong style="color:#2E9E44;">{sel_cat}</strong>에서 분석 가능한 속성</div>
            <div class="attribute-box">{attr_chips}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_examples:
    st.markdown('<div class="panel-title">💡 질문 예시 (1클릭 실행)</div>', unsafe_allow_html=True)
    examples = CATEGORY_EXAMPLE_QUERIES.get(sel_cat, CATEGORY_EXAMPLE_QUERIES["스킨케어"])
    for idx, (short_label, q_text) in enumerate(examples):
        if st.button(
            f"✨ {q_text}",
            key=f"ex_btn_{sel_cat}_{idx}",
            use_container_width=True,
        ):
            st.session_state.pending_query = q_text
            st.rerun()

st.divider()

# [8] Render Chat History
for message in st.session_state.chat_history:
    role = message.get("role", "user")
    content = message.get("content", "")
    meta = message.get("meta")

    if role == "user":
        with st.chat_message("user", avatar="🙂"):
            st.markdown(content)
    else:
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(content)
            if meta and hasattr(meta, "reference_reviews") and meta.reference_reviews:
                with st.expander(f"📚 참조 리뷰 원문 ({len(meta.reference_reviews)}건 선별)"):
                    for idx, ref in enumerate(meta.reference_reviews, start=1):
                        p_name = getattr(ref, "product_name", "올리브영 상품")
                        p_url = getattr(ref, "product_url", "#")
                        r_text = getattr(ref, "clean_text", "")
                        st.markdown(
                            f"**{idx}. [{p_name}]({p_url})**  \n"
                            f"> {r_text}"
                        )

# [9] Handle User Input or Pending Query
user_input = st.chat_input("브랜드명, 상품명, 궁금한 속성을 입력하여 질문해주세요. (예: 컬러그램 탕후루 탱글 꿀로스 발림성 어때?)")

question_to_process = None
if st.session_state.pending_query:
    question_to_process = st.session_state.pending_query
    st.session_state.pending_query = None
elif user_input:
    question_to_process = user_input.strip()

if question_to_process:
    # 1. Append & Display User Message
    st.session_state.chat_history.append({"role": "user", "content": question_to_process})
    session_store.append_message(st.session_state.session_id, "user", question_to_process)
    with st.chat_message("user", avatar="🙂"):
        st.markdown(question_to_process)

    # 2. Assistant Response with Real-Time 4-Stage Status Container
    with st.chat_message("assistant", avatar="🤖"):
        with st.status("🔍 질문 의도 및 화장품 속성 분석 중...", expanded=True) as status_box:
            callback = StreamlitStepCallback(status_box)
            status_box.write("- 🔍 질문 의도 및 화장품 속성 분석 중...")
            try:
                token_stream, exec_meta = prepare_pipeline_stream(
                    question=question_to_process,
                    callback=callback,
                    category_hint=st.session_state.selected_category,
                )
                status_box.update(
                    label=f"✅ 리뷰 분석 및 검색 완료 ({exec_meta.total_latency_sec:.1f}초, {exec_meta.selected_review_count}건 선별)",
                    state="complete",
                    expanded=False,
                )
            except Exception as error:
                status_box.update(label="⚠️ 파이프라인 초기화 오류", state="error")
                raise error

        # 3. Stream LLM Answer Tokens
        try:
            answer = st.write_stream(token_stream)
            if not answer or not str(answer).strip():
                answer = "답변을 생성하지 못했습니다. 질문을 조금 더 구체적으로 입력해주세요."

            # 4. Display Reference Reviews Accordion
            if exec_meta and exec_meta.reference_reviews:
                with st.expander(f"📚 참조 리뷰 원문 ({len(exec_meta.reference_reviews)}건 선별)"):
                    for idx, ref in enumerate(exec_meta.reference_reviews, start=1):
                        p_name = getattr(ref, "product_name", "올리브영 상품")
                        p_url = getattr(ref, "product_url", "#")
                        r_text = getattr(ref, "clean_text", "")
                        st.markdown(
                            f"**{idx}. [{p_name}]({p_url})**  \n"
                            f"> {r_text}"
                        )

            # 5. Save to History & Redis
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": answer,
                "meta": exec_meta,
            })
            session_store.append_message(st.session_state.session_id, "assistant", answer)
        except Exception as e:
            st.error(f"답변 스트리밍 중 오류가 발생했습니다: {e}")