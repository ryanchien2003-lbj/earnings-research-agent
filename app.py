"""Streamlit interface for the earnings research agent."""
import os
from urllib.error import URLError

import streamlit as st

from agent import chat_completion, investigate

st.set_page_config(page_title="Earnings Research Agent", page_icon="📊", layout="centered")
st.caption("FINANCE ANALYTICS  /  TOOL-CALLING DEMO")
st.title("Earnings Research Agent")
st.write("Ask about Microsoft earnings. Inspect the source, calculation, and tool calls behind each result.")
st.caption("Coverage · Microsoft FY24 Q4 and FY25 Q4 financials, plus selected FY25 Q4 call topics.")

examples = [
    "Compare Microsoft FY25 Q4 revenue and operating margin year over year.",
    "What did Microsoft say about Azure growth and capex in FY25 Q4?",
    "What did Microsoft say about datacenter capacity in FY25 Q4?",
]
sample = st.selectbox("Try an example", examples)
question = st.text_input("Or enter your own question", max_chars=600)
modes = ["Offline planner", "OpenAI planner"] if os.getenv("OPENAI_API_KEY") else ["Offline planner"]
mode = st.radio("Planner", modes, horizontal=True)
if mode == "OpenAI planner":
    st.caption("This mode sends the question and selected tool results to the OpenAI API.")
if st.button("Run research", type="primary"):
    try:
        st.session_state.pop("report", None)
        st.session_state["report"] = investigate(
            question.strip() or sample, chat_completion if mode == "OpenAI planner" else None
        )
    except (URLError, TimeoutError, ValueError, KeyError) as error:
        st.error(f"Research could not complete ({type(error).__name__}). Check the API configuration or use offline mode.")

report = st.session_state.get("report")
if report:
    if report["message"]:
        st.info(report["message"])
    for result in report["results"]:
        with st.container(border=True):
            st.write(result["text"])
            if result.get("calculation"):
                st.caption(result["calculation"])
            for source in result["sources"]:
                st.markdown(f"[{source['id']} · {source['section']}]({source['url']})")
    if report["trace"]:
        with st.expander("View tool calls and evidence"):
            st.json(report["trace"])
