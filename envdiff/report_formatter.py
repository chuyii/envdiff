import json
from pathlib import Path


def _indent_block(text: str, indent: int = 2) -> str:
    """Return the given multiline text indented by the specified spaces."""
    prefix = " " * indent
    return "\n".join(prefix + line for line in text.splitlines())


def json_report_to_text(report_path: Path) -> str:
    """Convert an envdiff JSON report to a human readable string."""
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    lines = []
    meta = data.get("report_metadata", {})
    lines.append(f"Report generated on: {meta.get('generated_on', 'unknown')}")
    lines.append(f"Container tool: {meta.get('container_tool', 'unknown')}")
    lines.append("")

    definitions = data.get("definitions", {})
    if definitions:
        lines.append("Definitions:")
        for key, value in definitions.items():
            if key == "command_diff":
                continue
            if key == "main_operation" and isinstance(value, dict):
                value = {k: v for k, v in value.items() if k != "commands"}
                if not value:
                    continue
            lines.append(f"- {key}:")
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value, indent=2, ensure_ascii=False)
                lines.append(_indent_block(value_str, 2))
            else:
                lines.append(f"  {value}")
        lines.append("")

    lines.append("Main operation results:")
    for entry in data.get("main_operation_results", []):
        line = f"- {entry.get('command', '')} (exit code {entry.get('return_code', 'N/A')})"
        lines.append(line)
        if entry.get("stdout"):
            lines.append("  stdout:")
            lines.append(_indent_block(str(entry["stdout"]), 4))
        if entry.get("stderr"):
            lines.append("  stderr:")
            lines.append(_indent_block(str(entry["stderr"]), 4))
    lines.append("")

    diff_reports = data.get("diff_reports", {})

    lines.append("Filesystem diff (rq):")
    for item in diff_reports.get("filesystem_rq", []):
        lines.append(f"  - {item}")
    lines.append("")

    lines.append("Filesystem diff (urN):")
    for item in diff_reports.get("filesystem_urN", []):
        lines.append(_indent_block(item, 2))
    lines.append("")

    for entry in diff_reports.get("command_outputs", []):
        lines.append(f"Command diff for: {entry.get('command', '')} (file: {entry.get('diff_file', '')})")
        diff_content = entry.get("diff_content")
        if diff_content:
            lines.append(_indent_block(diff_content, 2))
        else:
            lines.append("  No diff content available.")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
