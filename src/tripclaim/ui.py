from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

import requests
import streamlit as st


API_BASE = os.getenv("TRIPCLAIM_API_BASE", "http://127.0.0.1:8765")
HTTP = requests.Session()
HTTP.trust_env = False


def render() -> None:
    st.set_page_config(page_title="交通费审批台", layout="wide")
    st.title("交通费自动审批台")
    if "folder_path" not in st.session_state:
        st.session_state["folder_path"] = r"D:\GitProgram\TripClaim Pilot\报销材料"

    api_ok, api_msg = _check_api()
    if api_ok:
        st.success("后端状态: 已连接")
    else:
        st.error(f"后端状态: 未连接 ({api_msg})")
        st.info("请先启动后端: python -m tripclaim.api")

    c1, c2 = st.columns([5, 1])
    with c1:
        folder_path = st.text_input("资料文件夹路径", st.session_state["folder_path"])
    with c2:
        st.write("")
        st.write("")
        if st.button("选择文件夹"):
            picked = _pick_folder_dialog(st.session_state["folder_path"])
            if picked:
                st.session_state["folder_path"] = picked
                st.rerun()

    st.session_state["folder_path"] = folder_path
    folder_path = st.session_state["folder_path"]
    files = _list_files(folder_path)
    st.subheader("文件夹文件列表")
    if files:
        st.dataframe(files, width="stretch")
    else:
        st.info("当前目录无可识别文件或路径不存在")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("开始校验", type="primary"):
            try:
                resp = HTTP.post(
                    f"{API_BASE}/cases",
                    json={"folder_path": folder_path},
                    timeout=30,
                )
                if not resp.ok:
                    st.error(_resp_error(resp))
                else:
                    case_id = resp.json()["case_id"]
                    run_resp = HTTP.post(f"{API_BASE}/cases/{case_id}/run", timeout=180)
                    if run_resp.ok:
                        st.session_state["case_id"] = case_id
                        payload = run_resp.json()
                        st.session_state["last_case_data"] = {
                            "id": case_id,
                            "status": "auto_reviewed",
                            "decision": payload.get("decision"),
                            "folder_path": folder_path,
                            "result": payload.get("result"),
                            "manual_reviews": [],
                        }
                        st.success(f"校验完成，case_id={case_id}")
                    else:
                        st.error(_resp_error(run_resp))
            except Exception as e:
                st.error(f"校验失败: {e}")
    with col2:
        if st.button("刷新上次结果"):
            case_id = st.session_state.get("case_id")
            if case_id:
                data, err = _fetch_case(int(case_id))
                if data:
                    st.session_state["last_case_data"] = data
                    st.success("结果已刷新")
                else:
                    st.error(f"刷新失败: {err or '未查询到案例'}")

    case_id = st.session_state.get("case_id")
    if not case_id:
        return
    data = st.session_state.get("last_case_data")
    if not data:
        data, err = _fetch_case(int(case_id))
        if data:
            st.session_state["last_case_data"] = data
        else:
            st.error(f"结果加载失败: {err or '未查询到案例结果'}")
            return

    st.subheader("自动审批结果")
    st.write(
        {
            "case_id": data["id"],
            "status": data["status"],
            "decision": data["decision"],
            "folder_path": data["folder_path"],
        }
    )

    result = data.get("result") or {}
    log_path = result.get("file_audit_log_path")
    if log_path:
        st.subheader("审核日志")
        st.code(log_path, language="text")
        p = Path(log_path)
        if p.exists():
            st.text_area("日志内容", p.read_text(encoding="utf-8"), height=220)

    st.subheader("逐文件校验结果")
    file_checks = result.get("file_checks", [])
    if file_checks:
        bad_rows = [
            row for row in file_checks if row.get("status") in {"不合规", "待复核"}
        ]
        st.subheader("有问题文件")
        if bad_rows:
            st.dataframe(
                [
                    {
                        "文件": row.get("file", ""),
                        "状态": row.get("status", ""),
                        "原因": row.get("reasons", ""),
                    }
                    for row in bad_rows
                ],
                width="stretch",
            )
        else:
            st.success("当前案例无问题文件")

        st.subheader("全部文件校验明细")
        st.dataframe(file_checks, width="stretch")
    else:
        st.write("暂无逐文件结果")

    issues = result.get("issues", [])
    st.subheader("问题列表")
    if issues:
        st.dataframe(issues, width="stretch")
    else:
        st.write("无问题")

    st.subheader("人工复核")
    reviewer = st.text_input("审核人", "财务老师")
    decision = st.selectbox("改判结论", ["通过", "驳回", "转人工"])
    comment = st.text_area("复核备注", "")
    if st.button("提交人工复核"):
        resp = HTTP.post(
            f"{API_BASE}/cases/{case_id}/manual-review",
            json={"reviewer": reviewer, "decision": decision, "comment": comment},
            timeout=30,
        )
        if resp.ok:
            st.success("人工复核提交成功")
        else:
            st.error(resp.text)

    st.subheader("人工复核记录")
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


if __name__ == "__main__":
    render()
