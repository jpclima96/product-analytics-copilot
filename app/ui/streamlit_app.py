"""Front Streamlit do Product Analytics Copilot.

Uso (com a API rodando em ``PAC_API_URL``, default http://localhost:8000):

    streamlit run app/ui/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run` só adiciona a pasta do script ao sys.path; garante a raiz do
# repositório para que `import app...` funcione.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app.ui import client  # noqa: E402

EXAMPLES = [
    "Qual a taxa de ativação?",
    "Mostre o funil de onboarding",
    "Como está a retenção D7?",
    "Quais features são mais usadas?",
]

st.set_page_config(
    page_title="Product Analytics Copilot", page_icon="📊", layout="wide"
)


@st.cache_data(ttl=300, show_spinner=False)
def load_metrics() -> list[dict]:
    return client.fetch_metrics()


def render_sidebar() -> None:
    st.sidebar.header("Métricas disponíveis")
    try:
        metrics = load_metrics()
    except client.ApiError as exc:
        st.sidebar.error(str(exc))
        return
    for m in metrics:
        with st.sidebar.expander(m["title"]):
            st.caption(f"`{m['name']}`")
            st.write(m["definition"])
            st.caption("Exemplos de termos: " + ", ".join(m["synonyms"][:4]))
    st.sidebar.caption(
        "Respostas vêm só de SQL parametrizado e read-only sobre dados sintéticos. "
        "Perguntas fora destas métricas não são respondidas."
    )


def metric_title(name: str) -> str:
    try:
        titles = {m["name"]: m["title"] for m in load_metrics()}
    except client.ApiError:
        return name
    return titles.get(name, name)


def render_response(resp: dict) -> None:
    if not resp["matched"]:
        st.warning(resp["answer"])
        st.caption(f"Confiança do roteamento: {resp['confidence']:.0%}")
        return

    st.success(resp["answer"])
    st.caption(
        f"Métrica: `{resp['metric']}` · confiança do roteamento: "
        f"{resp['confidence']:.0%}"
    )

    chart = resp["chart"]
    is_kpi = bool(chart) and chart["data"][0].get("type") == "indicator"
    if resp["value"] is not None and not is_kpi:
        st.metric(metric_title(resp["metric"]), f"{resp['value']:.1%}")
    if chart:
        st.plotly_chart(go.Figure(chart), width="stretch")

    tab_table, tab_def, tab_sql = st.tabs(["Tabela", "Definição", "SQL executado"])
    with tab_table:
        st.dataframe(pd.DataFrame(resp["table"]), hide_index=True, width="stretch")
    with tab_def:
        st.write(resp["definition"])
    with tab_sql:
        st.code(resp["sql"], language="sql")


def main() -> None:
    st.title("📊 Product Analytics Copilot")
    st.caption(
        "Pergunte em linguagem natural sobre ativação, onboarding, retenção D7 "
        "e adoção de features."
    )
    render_sidebar()

    st.write("Exemplos:")
    cols = st.columns(len(EXAMPLES))
    for col, example in zip(cols, EXAMPLES, strict=True):
        if col.button(example, width="stretch"):
            st.session_state["question"] = example
            st.session_state["submit"] = True

    with st.form("ask"):
        question = st.text_input(
            "Sua pergunta",
            key="question",
            max_chars=500,
            placeholder="Ex.: qual a taxa de ativação?",
        )
        submitted = st.form_submit_button("Perguntar", type="primary")

    if submitted or st.session_state.pop("submit", False):
        if not question.strip():
            st.info("Digite uma pergunta.")
            return
        try:
            with st.spinner("Consultando…"):
                resp = client.ask(question)
        except client.ApiError as exc:
            st.error(str(exc))
            return
        render_response(resp)


main()
