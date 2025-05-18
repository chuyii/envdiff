import json
from pathlib import Path


def json_report_to_text(report_path: Path) -> str:
    """Convert an envdiff JSON report to a human readable string."""
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    lines = []
    meta = data.get("report_metadata", {})
    lines.append(f"Report generated on: {meta.get('generated_on', 'unknown')}")
    lines.append(f"Container tool: {meta.get('container_tool', 'unknown')}")
    lines.append("")

    lines.append("Main operation results:")
    for entry in data.get("main_operation_results", []):
        line = f"- {entry.get('command', '')} (exit code {entry.get('return_code', 'N/A')})"
        lines.append(line)
        if entry.get("stdout"):
            lines.append(f"  stdout: {entry['stdout']}")
        if entry.get("stderr"):
            lines.append(f"  stderr: {entry['stderr']}")
    lines.append("")

    diff_reports = data.get("diff_reports", {})

    lines.append("Filesystem diff (rq):")
    for item in diff_reports.get("filesystem_rq", []):
        lines.append(f"- {item}")
    lines.append("")

    lines.append("Filesystem diff (urN):")
    for item in diff_reports.get("filesystem_urN", []):
        lines.append(item)
    lines.append("")

    for entry in diff_reports.get("command_outputs", []):
        lines.append(f"Command diff for: {entry.get('command', '')} (file: {entry.get('diff_file', '')})")
        diff_content = entry.get("diff_content")
        if diff_content:
            lines.append(diff_content)
        else:
            lines.append("No diff content available.")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
