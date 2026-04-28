from __future__ import annotations

import json
from pathlib import Path

import typer

from .audit_log import write_file_audit_log
from .engine import audit_folder


app = typer.Typer(no_args_is_help=True)


@app.command()
def audit(
    folder: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    output: Path = typer.Option(
        Path("output"),
        "--output",
        "-o",
        help="输出目录",
    ),
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    result = audit_folder(folder)
    json_path = output / "result.json"
    md_path = output / "result.md"

    json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(result.to_dict()), encoding="utf-8")
    log_path = write_file_audit_log(
        file_checks=result.to_dict().get("file_checks", []),
        output_path=output / "file_audit.log",
        folder_path=str(folder),
    )
    typer.echo(f"审批完成: {result.decision}")
    typer.echo(f"高风险: {result.stats['high_issues']} | 中风险: {result.stats['medium_issues']}")
    typer.echo(f"造假风险分: {result.fraud_score_total}")
    typer.echo(f"JSON: {json_path}")
    typer.echo(f"MD: {md_path}")
    typer.echo(f"LOG: {log_path}")


def render_markdown(data: dict) -> str:
    lines = [
        f"# 审批结果: {data['decision']}",
        "",
        "## 统计",
        f"- 总文件数: {data['stats']['total_files']}",
        f"- 高风险问题: {data['stats']['high_issues']}",
        f"- 中风险问题: {data['stats']['medium_issues']}",
        f"- 造假风险分 (Fraud Score): {data.get('fraud_score_total', 0)}",
        "",
        "## 问题列表",
    ]
    issues = data.get("issues", [])
    if not issues:
        lines.append("- 无")
    else:
        for item in issues:
            lines.append(
                f"- [{item['severity']}] {item['rule_id']} {item['message']} (证据: {item['evidence']})"
            )
    lines.append("")
    lines.append("## 材料识别")
    for doc in data.get("detected_documents", []):
        f_score = doc.get('fraud_score', 0)
        f_info = f" (风险分:{f_score})" if f_score > 0 else ""
        lines.append(f"- {doc['type']} | {doc['confidence']}{f_info} | {Path(doc['file']).name}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    app()
