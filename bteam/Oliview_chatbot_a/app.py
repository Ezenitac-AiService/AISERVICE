"""Compatibility runner for Oliview ChatA (FastAPI Cutover).

Forwarder script to support legacy runners while redirecting execution to FastAPI main.py.
"""
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    import streamlit as st
    st.set_page_config(page_title="Oliview ChatA - FastAPI Cutover", page_icon="🌿")
    st.title("🌿 Oliview ChatA - FastAPI 전환 완료")
    st.success("Oliview ChatA 서비스가 Uvicorn 기반 FastAPI 웹 서비스(`main.py`)로 정상 전환되었습니다.")
    st.markdown("""
    - **웹 접속**: [http://localhost:8501/](http://localhost:8501/) 또는 [/bteam/chata/](/bteam/chata/)
    - **컨테이너 적용**: `docker compose up -d --force-recreate oliview_chatbot_a`
    """)
except Exception:
    import uvicorn
    from main import app
    port = int(os.environ.get("PORT", 8501))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
