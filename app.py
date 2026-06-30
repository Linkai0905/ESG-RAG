from __future__ import annotations

import json
import shutil
from pathlib import Path

import streamlit as st
from chromadb.api.client import SharedSystemClient

from config import DEFAULT_COMPANY, DEFAULT_ANCHOR_DATE, RUNS_DIR, make_run_id
from graph import build_graph


st.set_page_config(
    page_title="ESG Monthly Report Agent",
    layout="wide",
)


@st.cache_resource
def get_graph():
    return build_graph()


def read_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")


def read_json(path: str):
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def reset_run_dir(run_dir: Path) -> None:
    SharedSystemClient.clear_system_cache()
    shutil.rmtree(run_dir)


st.title("中国神华 ESG 月度监测")

with st.sidebar:
    st.header("参数")

    company = st.text_input("公司名称", DEFAULT_COMPANY)

    anchor_date = st.text_input(
        "基准日期",
        DEFAULT_ANCHOR_DATE,
        help="报告周期为基准日期前一个月，例如 2026-06-29 对应 2026-05-29 至 2026-06-29",
    )

    reset = st.checkbox("清理同周期历史产物", value=False)

    run_button = st.button("运行工作流", type="primary")


if run_button:
    run_id = make_run_id(company, anchor_date)
    run_dir = RUNS_DIR / run_id

    if reset and run_dir.exists():
        reset_run_dir(run_dir)
        st.session_state.pop("result", None)

    graph = get_graph()

    with st.spinner("工作流运行中：召回、抓取、解析、入库、检索、评估、写作"):
        result = graph.invoke({
            "company": company,
            "anchor_date": anchor_date,
        })

    st.session_state["result"] = result


result = st.session_state.get("result")

if not result:
    st.info("在左侧设置参数后运行工作流。")
    st.stop()


st.success("工作流完成")

metrics = result.get("metrics", {})
output_paths = result.get("output_paths", {})
errors = result.get("errors", [])

col1, col2, col3, col4 = st.columns(4)
col1.metric("URL 候选", metrics.get("url_candidate_count", 0))
col2.metric("URL队列", metrics.get("url_queue_count", 0))
col3.metric("Chunk数量", metrics.get("chunk_count", 0))
col4.metric("Evidence 数量", metrics.get("evidence_count", 0))

col5, col6, col7, col8 = st.columns(4)
col5.metric("抓取成功", metrics.get("fetch_success_count", 0))
col6.metric("解析成功", metrics.get("parsed_success_count", 0))
col7.metric("影响评估", metrics.get("impact_assessment_count", 0))
col8.metric("报告长度", metrics.get("report_length", 0))

tabs = st.tabs([
    "月报",
    "证据",
    "影响评估",
    "指标",
    "错误日志",
])

with tabs[0]:
    report_path = output_paths.get("report", "")
    report_text = read_text(report_path)

    if report_text:
        st.markdown(report_text)

        st.download_button(
            label="下载 report.md",
            data=report_text,
            file_name="中国神华_ESG月报.md",
            mime="text/markdown",
        )
    else:
        st.warning("报告文件不存在。")


with tabs[1]:
    evidence_path = output_paths.get("evidence", "")
    evidence = read_json(evidence_path)

    if evidence:
        st.dataframe(evidence, use_container_width=True)

        st.download_button(
            label="下载 evidence.json",
            data=json.dumps(evidence, ensure_ascii=False, indent=2),
            file_name="evidence.json",
            mime="application/json",
        )
    else:
        st.warning("evidence.json 不存在。")


with tabs[2]:
    assessment_path = output_paths.get("assessments", "")
    assessments = read_json(assessment_path)

    if assessments:
        st.dataframe(assessments, use_container_width=True)

        st.download_button(
            label="下载 impact_assessments.json",
            data=json.dumps(assessments, ensure_ascii=False, indent=2),
            file_name="impact_assessments.json",
            mime="application/json",
        )
    else:
        st.warning("impact_assessments.json 不存在。")


with tabs[3]:
    st.json(metrics)


with tabs[4]:
    if errors:
        st.json(errors)
    else:
        st.success("本次运行未记录错误。")
