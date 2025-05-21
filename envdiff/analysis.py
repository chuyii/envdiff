import json
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from .container import ContainerManager
from .diff import generate_diff_report
import yaml

logger = logging.getLogger(__name__)


def _merge_dicts(base: dict, new: dict) -> dict:
    """Merge ``new`` into ``base`` following custom rules."""
    for key, value in new.items():
        if isinstance(value, list):
            existing = base.get(key)
            if isinstance(existing, list):
                base[key] = existing + value
            else:
                base[key] = list(value)
        elif isinstance(value, dict):
            if isinstance(base.get(key), dict):
                base[key] = _merge_dicts(base[key], value)
            else:
                base[key] = _merge_dicts({}, value)
        else:
            base[key] = value
    return base


def _resolve_relative_paths(config: dict, base_dir: Path, root_dir: Path) -> None:
    """Resolve relative file paths inside ``config``.

    Paths are resolved relative to ``base_dir`` but stored relative to
    ``root_dir`` so that configuration values avoid leaking absolute host
    paths.
    """
    prepare = config.get("prepare")
    if isinstance(prepare, dict):
        copy_files = prepare.get("copy_files", [])
        for entry in copy_files:
            if isinstance(entry, dict) and "src" in entry:
                src_path = Path(entry["src"])
                if not src_path.is_absolute():
                    abs_path = (base_dir / src_path).resolve()
                    entry["src"] = os.path.relpath(abs_path, root_dir)


def load_config(config_path: Path, *, _root_dir: Path | None = None) -> dict:
    """Load YAML configuration from the given path, processing ``extends``.

    ``_root_dir`` is used internally to keep track of the directory of the
    original configuration file specified by the user. Relative paths in nested
    configuration files are converted so that they remain relative to this root
    directory.
    """
    logger.info(f"Loading configuration from '{config_path}'...")
    if not config_path.is_file():
        logger.error(f"Configuration file not found: {config_path}")
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if _root_dir is None:
        _root_dir = config_path.parent

    _resolve_relative_paths(config, config_path.parent, _root_dir)

    combined: dict = {}
    extends_list = config.get("extends", [])
    if isinstance(extends_list, str):
        extends_list = [extends_list]

    for ext in extends_list:
        ext_path = Path(ext)
        if not ext_path.is_absolute():
            ext_path = config_path.parent / ext_path
        ext_path = ext_path.resolve()
        extended_cfg = load_config(ext_path, _root_dir=_root_dir)
        combined = _merge_dicts(combined, extended_cfg)

    config.pop("extends", None)
    combined = _merge_dicts(combined, config)

    title = combined.get("title")
    if isinstance(title, str):
        combined["title"] = " ".join(title.splitlines())

    # Remove duplicates from specific list entries
    def _dedup(seq: list) -> list:
        seen = set()
        result = []
        for item in seq:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    for key in ("target_dirs", "exclude_paths", "omit_diff_paths"):
        if isinstance(combined.get(key), list):
            combined[key] = _dedup(combined[key])

    logger.info("Configuration loaded successfully.")
    return combined


def run_analysis(config_path: Path, output_report_path: Path, container_tool: str):
    """Main analysis workflow."""
    config = load_config(config_path)
    root_dir = config_path.parent
    title = config.pop("title", None)
    description = config.pop("description", None)
    base_image = config.get("base_image")
    if not base_image:
        logger.error("Configuration error: 'base_image' not specified in input YAML.")
        raise ValueError("'base_image' must be defined in the configuration.")

    output_data = {
        "report_metadata": {
            "generated_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "container_tool": container_tool,
            **({"title": title} if title else {}),
            **({"description": description} if description else {}),
        },
        "definitions": config,
        "main_operation_results": [],
        "diff_reports": {
            "filesystem_rq": None,
            "filesystem_urN": None,
            "command_outputs": [],
        },
    }

    with ContainerManager(image_name=base_image, container_tool=container_tool) as cm:
        logger.info("--- Preparing Container ---")
        for entry in config.get("prepare", {}).get("copy_files", []):
            src_path = Path(entry["src"])
            if not src_path.is_absolute():
                src_path = (root_dir / src_path).resolve()
            if not src_path.exists():
                logger.error(f"Source file for copy not found: {src_path}. Skipping this copy operation.")
                continue
            cm.copy_to(src_path, entry["dest"])

        cm.start()

        for cmd_str in config.get("prepare", {}).get("commands", []):
            cm.execute_command(cmd_str)
        logger.info("--- Container Preparation Complete ---")

        with tempfile.TemporaryDirectory(prefix="env_diff_") as tmpdir_str:
            tmpdir = Path(tmpdir_str)
            logger.info(f"Using temporary directory: {tmpdir}")

            base_fs_root = tmpdir / "fs_base"
            after_fs_root = tmpdir / "fs_after"
            base_cmd_output_dir = tmpdir / "cmd_outputs_base"
            after_cmd_output_dir = tmpdir / "cmd_outputs_after"

            for d_path in [base_fs_root, after_fs_root, base_cmd_output_dir, after_cmd_output_dir]:
                d_path.mkdir(parents=True, exist_ok=True)

            target_dirs = config.get("target_dirs", [])
            if not target_dirs:
                logger.warning("'target_dirs' not specified in config. File system diffs might be empty or limited.")

            logger.info("--- Capturing Baseline State ---")
            if target_dirs:
                cm.export_paths(target_dirs, base_fs_root)
            for entry in config.get("command_diff", []):
                outfile_name = Path(entry["outfile"]).name
                cm.capture_command_output(entry["command"], base_cmd_output_dir / outfile_name)
            logger.info("--- Baseline State Captured ---")

            logger.info("--- Executing Main Operation ---")
            main_op_commands = config.get("main_operation", {}).get("commands", [])
            for cmd_str in main_op_commands:
                cmd_result = cm.execute_command(cmd_str)
                output_data["main_operation_results"].append(cmd_result)
            logger.info("--- Main Operation Complete ---")

            logger.info("--- Capturing State After Main Operation ---")
            if target_dirs:
                cm.export_paths(target_dirs, after_fs_root)
            for entry in config.get("command_diff", []):
                outfile_name = Path(entry["outfile"]).name
                cm.capture_command_output(entry["command"], after_cmd_output_dir / outfile_name)
            logger.info("--- State After Main Operation Captured ---")

            logger.info("--- Generating Diff Reports ---")
            exclude_paths = config.get("exclude_paths", [])
            omit_diff_paths = config.get("omit_diff_paths", [])

            if target_dirs:
                fs_diff_rq_content = generate_diff_report(
                    base_fs_root, after_fs_root, "rq", exclude_paths
                )
                output_data["diff_reports"]["filesystem_rq"] = list(filter(None, fs_diff_rq_content.split("\n")))

                fs_diff_urn_content = generate_diff_report(
                    base_fs_root,
                    after_fs_root,
                    "urN",
                    exclude_paths,
                    omit_diff_paths,
                )
                output_data["diff_reports"]["filesystem_urN"] = list(
                    map(
                        lambda l: l[:-1],
                        filter(None, re.split(r"(?=^[a-zA-Z].+$)", fs_diff_urn_content, flags=re.MULTILINE))
                    )
                )
            else:
                logger.info("Skipping filesystem diffs as 'target_dirs' was empty.")
                output_data["diff_reports"]["filesystem_rq"] = [
                    "Skipped: 'target_dirs' was not specified or empty in config."
                ]
                output_data["diff_reports"]["filesystem_urN"] = [
                    "Skipped: 'target_dirs' was not specified or empty in config."
                ]

            for entry in config.get("command_diff", []):
                outfile_name = Path(entry["outfile"]).name
                base_cmd_file = base_cmd_output_dir / outfile_name
                after_cmd_file = after_cmd_output_dir / outfile_name

                command_diff_entry = {
                    "command": entry["command"],
                    "diff_file": entry["outfile"],
                    "diff_content": None,
                }
                if base_cmd_file.exists() and after_cmd_file.exists():
                    cmd_diff_content = generate_diff_report(base_cmd_file, after_cmd_file, "text")
                    command_diff_entry["diff_content"] = cmd_diff_content[:-1]
                else:
                    missing_files_info = []
                    if not base_cmd_file.exists():
                        missing_files_info.append(f"baseline output '{base_cmd_file}'")
                    if not after_cmd_file.exists():
                        missing_files_info.append(f"after output '{after_cmd_file}'")
                    logger.warning(
                        f"Skipping diff for command '{entry['command']}' due to missing output files: {', '.join(missing_files_info)}"
                    )
                    command_diff_entry["diff_content"] = (
                        f"Skipped: Output file(s) not found ({', '.join(missing_files_info)})."
                    )
                output_data["diff_reports"]["command_outputs"].append(command_diff_entry)

            logger.info("--- Diff Report Generation Complete ---")

    logger.info(f"Writing final JSON report to '{output_report_path}'...")
    output_report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_report_path, "w", encoding="utf-8") as f_report:
        json.dump(output_data, f_report, indent=4, ensure_ascii=False)
    logger.info(f"✅ Environment diff report successfully generated: {output_report_path.resolve()}")
