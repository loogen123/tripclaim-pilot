from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st


API_BASE = os.getenv("TRIPCLAIM_API_BASE", "http://127.0.0.1:8765")
HTTP = requests.Session()
HTTP.trust_env = False


def render() -> None:
    st.set_page_config(page_title="交通费审批台", layout="wide")
    _inject_css()
    if "folder_path" not in st.session_state:
        st.session_state["folder_path"] = r"D:\GitProgram\TripClaim Pilot\报销材料"
    if "event_logs" not in st.session_state:
        st.session_state["event_logs"] = []

    api_ok, api_msg = _check_api()
    _render_top_bar(api_ok, api_msg)

    left_col, center_col, right_col = st.columns([1.05, 3.2, 1.15], gap="small")

    with left_col:
        st.markdown("### 资料控制台")
        st.caption("选择目录并发起自动校验")
        c1, c2 = st.columns([5, 2])
        with c1:
            folder_path = st.text_input("资料文件夹路径", st.session_state["folder_path"])
        with c2:
            st.write("")
            if st.button("选择文件夹", use_container_width=True):
                picked = _pick_folder_dialog(st.session_state["folder_path"])
                if picked:
                    st.session_state["folder_path"] = picked
                    _push_log(f"已选择目录: {picked}")
                    st.rerun()
        st.session_state["folder_path"] = folder_path

        st.markdown(
            '<div class="mode-card active"><b>自动校验模式</b><br/>按硬核十条规则逐文件核验</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="mode-card"><b>人工复核模式</b><br/>自动结果基础上可改判并留痕</div>',
            unsafe_allow_html=True,
        )

    folder_path = st.session_state["folder_path"]
    files = _list_files(folder_path)

    case_id = st.session_state.get("case_id")
    data = st.session_state.get("last_case_data")
    if case_id and not data:
        loaded, err = _fetch_case(int(case_id))
        if loaded:
            st.session_state["last_case_data"] = loaded
            data = loaded
        elif err:
            _push_log(f"结果加载失败: {err}")

    result = (data or {}).get("result") or {}
    file_checks = result.get("file_checks", [])
    bad_rows = [row for row in file_checks if row.get("status") in {"不合规", "待复核"}]
    decision = (data or {}).get("decision", "STANDBY")
    status_name = _display_decision("STANDBY" if not data else str(decision))

    with center_col:
        st.markdown("### 审批流状态机")
        st.caption("实时展示当前审批阶段")
        _render_state_machine(data)
        b1, b2, b3 = st.columns([1.2, 1.2, 1.0])
        with b1:
            if st.button("开始校验", type="primary", use_container_width=True):
                _start_audit(folder_path)
                st.rerun()
        with b2:
            if st.button("刷新结果", use_container_width=True):
                _refresh_case()
                st.rerun()
        with b3:
            if st.button("清空日志", use_container_width=True):
                st.session_state["event_logs"] = []
                st.rerun()

        st.markdown(
            f'<div class="status-line"><span class="status-dot"></span>当前阶段：<b>{status_name}</b> | 防伪分：<b>{result.get("fraud_score_total", 0)}</b></div>',
            unsafe_allow_html=True,
        )
        st.markdown("#### 审导日志")
        logs = st.session_state.get("event_logs", [])
        if logs:
            st.markdown(_render_logs_html(logs[-20:]), unsafe_allow_html=True)
        else:
            st.info("暂无日志")

        global_issues = result.get("global_issues", [])
        if global_issues:
            for gi in global_issues:
                st.error(f"🔴 **全局问题**：{gi['message']}")

        st.markdown("#### 有问题文件")
        if bad_rows:
            st.dataframe(
                [{"文件": r["file"], "状态": r["status"], "原因": r["reasons"]} for r in bad_rows],
                width="stretch",
            )
        else:
            st.success("当前案例无问题文件")

        with st.expander("全部文件校验明细", expanded=False):
            if file_checks:
                st.dataframe(file_checks, width="stretch")
            else:
                st.write("暂无数据")

    with right_col:
        st.markdown("### 审批工作区")
        st.caption("结果总览与人工复核")
        total = len(files)
        checked = len(file_checks)
        bad = len(bad_rows)
        progress = int((checked / total) * 100) if total else 0
        st.markdown(
            f"""
<div class="work-card">
  <div class="metric-row">
    <span class="metric-pill">状态：{status_name}</span>
    <span class="metric-pill">进度：{checked}/{total}</span>
    <span class="metric-pill">问题：{bad} 个</span>
  </div>
  <div class="progress-track"><div class="progress-bar" style="width:{progress}%"></div></div>
  <div class="progress-text">{progress}%</div>
</div>
""",
            unsafe_allow_html=True,
        )
        st.markdown("**文件列表**")
        if files:
            st.dataframe(files, width="stretch")
        else:
            st.info("暂无文件")

        st.markdown("**人工复核**")
        reviewer = st.text_input("审核人", "财务老师")
        manual_decision = st.selectbox("改判结论", ["通过", "驳回", "转人工"])
        comment = st.text_area("复核备注", "")
        if st.button("提交人工复核", use_container_width=True):
            if not case_id:
                st.error("请先开始校验")
            else:
                resp = HTTP.post(
                    f"{API_BASE}/cases/{case_id}/manual-review",
                    json={"reviewer": reviewer, "decision": manual_decision, "comment": comment},
                    timeout=30,
                )
                if resp.ok:
                    _push_log(f"人工复核提交成功: {manual_decision}")
                    st.success("提交成功")
                else:
                    st.error(_resp_error(resp))

    if data:
        with st.expander("人工复核记录", expanded=False):
            reviews = data.get("manual_reviews", [])
            if reviews:
                st.dataframe(reviews, width="stretch")
            else:
                st.write("暂无人工复核记录")


def _fetch_case(case_id: int) -> tuple[dict | None, str | None]:
    try:
        resp = HTTP.get(f"{API_BASE}/cases/{case_id}", timeout=30)
        if not resp.ok:
            return None, _resp_error(resp)
        return resp.json(), None
    except Exception as e:
        return None, str(e)


def _check_api() -> tuple[bool, str]:
    try:
        resp = HTTP.get(f"{API_BASE}/docs", timeout=5)
        if resp.ok:
            return True, "ok"
        return False, f"http {resp.status_code}"
    except Exception as e:
        return False, str(e)


def _start_audit(folder_path: str) -> None:
    try:
        resp = HTTP.post(
            f"{API_BASE}/cases",
            json={"folder_path": folder_path},
            timeout=30,
        )
        if not resp.ok:
            _push_log(f"创建案例失败: {_resp_error(resp)}")
            return
        case_id = resp.json()["case_id"]
        _push_log(f"案例创建成功: case_id={case_id}")
        run_resp = HTTP.post(f"{API_BASE}/cases/{case_id}/run", timeout=180)
        if not run_resp.ok:
            _push_log(f"自动校验失败: {_resp_error(run_resp)}")
            return
        payload = run_resp.json()
        st.session_state["case_id"] = case_id
        st.session_state["last_case_data"] = {
            "id": case_id,
            "status": "auto_reviewed",
            "decision": payload.get("decision"),
            "folder_path": folder_path,
            "result": payload.get("result"),
            "manual_reviews": [],
        }
        _push_log(f"校验完成: {payload.get('decision')}")
    except Exception as e:
        _push_log(f"校验失败: {e}")


def _refresh_case() -> None:
    case_id = st.session_state.get("case_id")
    if not case_id:
        _push_log("无可刷新的案例")
        return
    data, err = _fetch_case(int(case_id))
    if data:
        st.session_state["last_case_data"] = data
        _push_log("结果已刷新")
    else:
        _push_log(f"刷新失败: {err or '未查询到案例'}")


def _push_log(text: str) -> None:
    st.session_state["event_logs"].append(
        {"time": datetime.now().strftime("%H:%M:%S"), "text": text}
    )


def _render_top_bar(api_ok: bool, api_msg: str) -> None:
    left, right = st.columns([3.5, 2.2])
    with left:
        st.markdown("## 交通费自动审批台")
        st.caption("学生硬核十条自动审单系统")
    with right:
        api_badge = "已连接" if api_ok else f"未连接 ({api_msg})"
        case_id = st.session_state.get("case_id", "--")
        decision = (
            (st.session_state.get("last_case_data") or {}).get("decision")
            if st.session_state.get("last_case_data")
            else "待命"
        )
        decision = _display_decision(str(decision))
        st.markdown(
            f"""
<div class="badge-row">
  <span class="badge {'green' if api_ok else 'red'}">后端: {api_badge}</span>
  <span class="badge blue">案例: {case_id}</span>
  <span class="badge blue">结论: {decision}</span>
</div>
""",
            unsafe_allow_html=True,
        )


def _render_state_machine(data: dict | None) -> None:
    steps = ["待命", "创建案例", "读取资料", "材料识别", "规则校验", "结论生成", "已完成"]
    active_index = 0 if not data else len(steps) - 1
    html = ['<div class="step-row">']
    for i, step in enumerate(steps):
        cls = "step active" if i <= active_index else "step"
        html.append(f'<div class="{cls}">{step}</div>')
        if i < len(steps) - 1:
            html.append('<div class="arrow">→</div>')
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _display_decision(value: str) -> str:
    mapping = {
        "STANDBY": "待命",
        "PASS": "通过",
        "REJECT": "驳回",
        "MANUAL_REVIEW": "转人工",
        "待命": "待命",
        "通过": "通过",
        "驳回": "驳回",
        "转人工": "转人工",
    }
    return mapping.get(value, value)


def _render_logs_html(logs: list[dict]) -> str:
    lines = []
    for item in reversed(logs):
        ts = item.get("time", "")
        text = str(item.get("text", ""))
        lines.append(
            f'<div class="log-line"><span class="log-time">{ts}</span><span class="log-text">{text}</span></div>'
        )
    return f'<div class="log-wrap">{"".join(lines)}</div>'


def _resp_error(resp: requests.Response) -> str:
    try:
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("detail"):
            return str(payload.get("detail"))
        return str(payload)
    except Exception:
        return resp.text or f"http {resp.status_code}"


def _pick_folder_dialog(initial: str) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(initialdir=initial or str(Path.home()))
        root.destroy()
        if selected:
            return selected
        return None
    except Exception:
        return None


def _list_files(folder_path: str) -> list[dict]:
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        return []
    rows: list[dict] = []
    allowed = {".pdf", ".doc", ".docx", ".txt", ".png", ".jpg", ".jpeg"}
    for p in sorted(folder.glob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in allowed:
            continue
        rows.append(
            {
                "文件名": p.name,
                "类型": p.suffix.lower(),
                "大小KB": round(p.stat().st_size / 1024, 2),
            }
        )
    return rows


def run() -> None:
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(Path(__file__))], check=False)


def _inject_css() -> None:
    st.markdown(
        """
<style>
:root { --bg:#f5f7fb; --card:#fff; --line:#e4ecf7; --line2:#d6e0f0; --text:#1f2a44; --muted:#7484a0; --blue:#6aa6ff; --green:#2fb267; --red:#e56a6a; }
.stApp { background: var(--bg); color: var(--text); }
div[data-testid="stVerticalBlockBorderWrapper"] { border: 1px solid var(--line); border-radius: 14px; background: var(--card); }
.stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"] > div {
  border-radius: 10px !important;
  border-color: var(--line2) !important;
}
.stButton button {
  border-radius: 10px !important;
  border: 1px solid var(--line2) !important;
}
.stButton button[kind="primary"] {
  border: none !important;
  background: linear-gradient(180deg,#5fa2ff,#4b8ff2) !important;
}
.mode-card { background: #ffffff; border: 1px solid var(--line2); border-radius: 12px; padding: 12px; margin: 8px 0; font-size: 13px; }
.mode-card.active { border-color: var(--blue); box-shadow: 0 0 0 1px rgba(106,166,255,.5) inset; }
.work-card { background: #fcfdff; border: 1px solid var(--line); border-radius: 12px; padding: 12px; font-size: 13px; margin-bottom: 10px; }
.metric-row { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px; }
.metric-pill { border:1px solid #d6e4ff; background:#eef4ff; color:#2f5d9e; border-radius:999px; padding:4px 10px; font-size:12px; }
.progress-track { height:8px; border-radius:999px; background:#edf2fb; border:1px solid #e2e9f6; overflow:hidden; }
.progress-bar { height:100%; background:linear-gradient(90deg,#95bfff,#5a96ef); transition:width .4s ease; }
.progress-text { margin-top:6px; color:#60708e; font-size:12px; text-align:right; }
.badge-row { display: flex; gap: 8px; justify-content: flex-end; align-items: center; margin-top: 18px; flex-wrap: wrap; }
.badge { font-size: 12px; padding: 4px 10px; border-radius: 999px; border: 1px solid; }
.badge.red { color: #d85555; border-color: #f1c3c3; background: #fff7f7; }
.badge.green { color: #2d9e5d; border-color: #cce8d6; background: #f4fff8; }
.badge.blue { color: #2f5d9e; border-color: #cfe0ff; background: #eef4ff; }
.status-line { margin:6px 0 8px 0; display:flex; align-items:center; gap:8px; color:#4a5d7d; font-size:13px; }
.status-dot { width:10px; height:10px; border-radius:999px; background:#6aa6ff; box-shadow:0 0 0 4px rgba(106,166,255,.15); }
.step-row { display: flex; align-items: center; gap: 6px; padding: 8px 0 14px 0; overflow-x: auto; }
.step { min-width: 86px; text-align: center; background: #fff; border: 1px solid var(--line2); border-radius: 10px; padding: 8px 10px; font-size: 12px; color: #3d4a66; }
.step.active { border-color: #78a7ff; color: #1d4ed8; box-shadow: 0 0 8px rgba(98,154,255,.3); font-weight: 600; }
.arrow { color: #9cb0cc; font-size: 16px; }
.log-wrap { background:#fafcff; border:1px solid var(--line); border-radius:10px; padding:8px; max-height:270px; overflow:auto; }
.log-line { border:1px solid var(--line); background:#fff; border-radius:10px; padding:8px 10px; margin-bottom:8px; display:flex; gap:10px; }
.log-time { color:#6e7f9a; min-width:56px; font-size:12px; }
.log-text { color:#30435f; font-size:13px; }
</style>
""",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    render()
