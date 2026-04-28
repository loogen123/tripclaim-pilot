from __future__ import annotations

from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .audit_log import write_file_audit_log
from .engine import audit_folder
from .storage import add_manual_review, create_case, get_case, update_case_result


app = FastAPI(title="TripClaim Auto Approval API")
WEB_DIR = Path(__file__).resolve().parent / "web"


class CreateCaseRequest(BaseModel):
    folder_path: str


class ListFilesRequest(BaseModel):
    folder_path: str


class PickFolderRequest(BaseModel):
    initial_path: str | None = None


class ManualReviewRequest(BaseModel):
    reviewer: str
    decision: str
    comment: str


@app.post("/cases")
def create_case_api(req: CreateCaseRequest) -> dict[str, Any]:
    folder = Path(req.folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail="folder_path 不存在或不是目录")
    case_id = create_case(str(folder))
    return {"case_id": case_id}


@app.post("/files/list")
def list_files_api(req: ListFilesRequest) -> dict[str, Any]:
    folder = Path(req.folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail="folder_path 不存在或不是目录")
    allowed = {".pdf", ".ofd", ".doc", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    files: list[dict[str, Any]] = []
    for item in sorted(folder.glob("*")):
        if not item.is_file():
            continue
        ext = item.suffix.lower()
        if ext not in allowed:
            continue
        files.append(
            {
                "name": item.name,
                "path": str(item.resolve()),
                "type": ext,
                "size_kb": round(item.stat().st_size / 1024, 2),
            }
        )
    return {"files": files}


@app.post("/folders/pick")
def pick_folder_api(req: PickFolderRequest) -> dict[str, Any]:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        initial = req.initial_path or str(Path.home())
        selected = filedialog.askdirectory(initialdir=initial)
        root.destroy()
        if not selected:
            raise HTTPException(status_code=400, detail="未选择目录")
        return {"folder_path": selected}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"目录选择失败: {exc}") from exc


@app.post("/cases/{case_id}/run")
def run_case_api(case_id: int) -> dict[str, Any]:
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case 不存在")
    result = audit_folder(Path(case["folder_path"])).to_dict()
    log_path = write_file_audit_log(
        file_checks=result.get("file_checks", []),
        global_issues=result.get("global_issues", []),
        output_path=Path("logs") / f"case_{case_id}_file_audit.log",
        case_id=case_id,
        folder_path=case["folder_path"],
    )
    result["file_audit_log_path"] = str(log_path.resolve())
    update_case_result(case_id, result)
    return {"case_id": case_id, "decision": result["decision"], "result": result}


@app.get("/cases/{case_id}")
def get_case_api(case_id: int) -> dict[str, Any]:
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case 不存在")
    return case


@app.post("/cases/{case_id}/manual-review")
def manual_review_api(case_id: int, req: ManualReviewRequest) -> dict[str, Any]:
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case 不存在")
    if req.decision not in {"通过", "驳回", "转人工"}:
        raise HTTPException(status_code=400, detail="decision 必须为 通过/驳回/转人工")
    add_manual_review(case_id, req.reviewer, req.decision, req.comment)
    return {"ok": True, "case_id": case_id}


@app.get("/health")
def health_api() -> dict[str, bool]:
    return {"ok": True}


@app.get("/")
def root_page() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


@app.get("/ui")
def ui_page_shortcut() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


@app.get("/ui/")
def ui_page() -> FileResponse:
    if not WEB_DIR.exists():
        raise HTTPException(status_code=500, detail="前端页面目录不存在")
    return FileResponse(WEB_DIR / "index.html")


app.mount("/ui/static", StaticFiles(directory=str(WEB_DIR)), name="ui_static")


def run() -> None:
    uvicorn.run("tripclaim.api:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    run()
