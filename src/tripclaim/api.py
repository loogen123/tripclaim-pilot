from __future__ import annotations

from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .audit_log import write_file_audit_log
from .engine import audit_folder
from .storage import add_manual_review, create_case, get_case, update_case_result


app = FastAPI(title="TripClaim Auto Approval API")


class CreateCaseRequest(BaseModel):
    folder_path: str


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


@app.post("/cases/{case_id}/run")
def run_case_api(case_id: int) -> dict[str, Any]:
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case 不存在")
    result = audit_folder(Path(case["folder_path"])).to_dict()
    log_path = write_file_audit_log(
        file_checks=result.get("file_checks", []),
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


def run() -> None:
    uvicorn.run("tripclaim.api:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    run()
