
from pathlib import Path
import json

from envdiff.report_formatter import json_report_to_text


def test_json_report_to_text(tmp_path: Path):
    data = {
        "report_metadata": {"generated_on": "2020-01-01", "container_tool": "podman"},
        "definitions": {
            "base_image": "alpine:latest",
            "prepare": {"commands": ["setup"]},
            "main_operation": {"commands": ["echo hi"]},
            "command_diff": [
                {"command": "ls", "outfile": "ls.txt"}
            ],
        },
        "main_operation_results": [
            {"command": "echo hi", "stdout": "hi\n", "stderr": "", "return_code": 0}
        ],
        "diff_reports": {
            "filesystem_rq": ["Only in after: new.txt"],
            "filesystem_urN": ["diff -urN a b"],
            "command_outputs": [
                {
                    "command": "ls",
                    "diff_file": "ls.txt",
                    "diff_content": "--- a\n+++ b"
                }
            ],
        },
    }
    report = tmp_path / "report.json"
    with open(report, "w", encoding="utf-8") as f:
        json.dump(data, f)

    text = json_report_to_text(report)

    assert "Report generated on: 2020-01-01" in text
    assert "- echo hi (exit code 0)" in text
    assert "Definitions:" in text
    assert "- base_image:" in text
    assert "alpine:latest" in text
    assert "- prepare:" in text
    assert "  commands:" in text
    assert "    - setup" in text
    assert "Only in after: new.txt" in text
    assert "diff -urN a b" in text
    assert "Command diff for: ls" in text
    assert "  - Only in after: new.txt" in text
    assert "command_diff" not in text

