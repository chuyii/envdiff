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
    title = meta.get("title")
    if title:
        lines.append(f"Title: {title}")
    desc = meta.get("description")
    if desc:
        lines.append("Description:")
        lines.append(_indent_block(str(desc), 2))
    lines.append("")

    definitions = data.get("definitions", {})
    if definitions:
        lines.append("Definitions:")
        ordered_keys = [
            "base_image",
            "prepare",
            "target_dirs",
            "exclude_paths",
            "omit_diff_paths",
        ]
        keys = [k for k in ordered_keys if k in definitions]
        keys.extend(k for k in definitions if k not in keys)
        for key in keys:
            value = definitions[key]
            if key == "command_diff":
                continue
            if key == "main_operation" and isinstance(value, dict):
                value = {k: v for k, v in value.items() if k != "commands"}
                if not value:
                    continue

            lines.append(f"- {key}:")

            if key == "prepare" and isinstance(value, dict):
                copy_files = value.get("copy_files", [])
                if copy_files:
                    lines.append("  copy_files:")
                    for item in copy_files:
                        if isinstance(item, dict):
                            src = item.get("src", "")
                            dest = item.get("dest", "")
                            lines.append(f"    - {src} -> {dest}")
                        else:
                            lines.append(f"    - {item}")
                commands = value.get("commands", [])
                if commands:
                    lines.append("  commands:")
                    for cmd in commands:
                        lines.append(f"    - {cmd}")
                extra_keys = [k for k in value if k not in {"copy_files", "commands"}]
                for k in extra_keys:
                    val = value[k]
                    if isinstance(val, (dict, list)):
                        val_str = json.dumps(val, indent=2, ensure_ascii=False)
                        lines.append(_indent_block(val_str, 2))
                    else:
                        lines.append(f"  {k}: {val}")
            elif key in {"target_dirs", "exclude_paths", "omit_diff_paths"} and isinstance(value, list):
                for item in value:
                    lines.append(f"  - {item}")
            else:
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
        diff_lines = item.splitlines()
        if not diff_lines:
            continue
        lines.append(f"  - {diff_lines[0]}")
        for diff_line in diff_lines[1:]:
            lines.append(f"    {diff_line}")
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
