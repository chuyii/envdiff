import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_diff_report(
    base_path: Path,
    after_path: Path,
    diff_type: str,
    exclude_paths: list[str] | None = None,
) -> str:
    """Generate a diff report between two directories or files."""
    if exclude_paths is None:
        exclude_paths = []

    exclude_args_str = "|".join(exclude_paths) if exclude_paths else "EMPTY_EXCLUDE_LIST_PLACEHOLDER"

    cmd_str = None
    base_name = base_path.name
    after_name = after_path.name

    if diff_type == "rq":
        diff_command_part = f"LANG=C diff -rq \"{base_name}\" \"{after_name}\""
        if exclude_paths:
            diff_command_part += f" | grep -Ev '^[^ ]* ([^ ]* )?[^ /]*({exclude_args_str})'"
        cmd_str = f"cd \"{base_path.parent}\" && {diff_command_part}"

    elif diff_type == "urN":
        awk_script = (
            "'/^[a-zA-Z]/{if(n){if(h!~p){for(i=0;i<c;i++)print a[i];}delete a};c=0;h=$0;n=1}n{"
            "a[c++]=$0}END{if(n&&h!~p){for(i=0;i<c;i++)print a[i]}}'"
        )
        sed_script = r"'/^\(---\|+++\) /s/\t.*//'"
        diff_command_part = f"LANG=C diff -urN \"{base_name}\" \"{after_name}\""
        if exclude_paths:
            diff_command_part += f" | awk -v p='^[^ ]* [^ ]* [^ /]*({exclude_args_str})' {awk_script}"
        else:
            simplified_awk = (
                "'/^[a-zA-Z]/{if(n){for(i=0;i<c;i++)print a[i];delete a};c=0;h=$0;n=1}n{a[c++]=$0}END{if(n){for(i=0;i<c;i++)print a[i]}}'"
            )
            diff_command_part += f" | awk {simplified_awk}"
        diff_command_part += f" | sed -e {sed_script}"
        cmd_str = f"cd \"{base_path.parent}\" && {diff_command_part}"

    elif diff_type == "text":
        base_relative_path = f"{base_path.parent.name}/{base_path.name}"
        after_relative_path = f"{after_path.parent.name}/{after_path.name}"
        sed_script = r"'/^\(---\|+++\) /s/\t.*//'"
        cmd_str = (
            f"cd \"{base_path.parent.parent}\" && LANG=C diff -su \"{base_relative_path}\" \"{after_relative_path}\" | sed -e {sed_script}"
        )
    else:
        logger.error(f"Unsupported diff type: {diff_type}")
        return ""

    logger.info(f"Generating {diff_type} diff...")
    logger.debug(f"Diff command: {cmd_str}")

    result = subprocess.run(cmd_str, shell=True, check=False, capture_output=True, text=True, encoding="utf-8")

    if result.returncode > 1:
        logger.error(
            f"Diff command failed or encountered an issue. Exit code: {result.returncode}. Stderr: {result.stderr.strip()}"
        )
    logger.info(f"Diff content for type '{diff_type}' generated.")
    return result.stdout
