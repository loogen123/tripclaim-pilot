from __future__ import annotations

from datetime import datetime
from pathlib import Path


def write_file_audit_log(
    *,
    file_checks: list[dict],
    output_path: Path,
    case_id: int | None = None,
    folder_path: str | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"time={datetime.now().isoformat(timespec='seconds')}")
    if case_id is not None:
        lines.append(f"case_id={case_id}")
    if folder_path:
        lines.append(f"folder_path={folder_path}")
    lines.append("---- file_audit ----")
    for item in file_checks:
        lines.append(
            " | ".join(
                [
                    f"status={item.get('status', '')}",
                    f"type={item.get('type', '')}",
                    f"confidence={item.get('confidence', '')}",
                    f"file={item.get('file', '')}",
                    f"reasons={item.get('reasons', '')}",
                ]
            )
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
