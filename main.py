import os
import subprocess
import tempfile
import shutil
import yaml
import json
from pathlib import Path
from datetime import datetime
import argparse
import time
import logging
import re

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

DEFAULT_CONTAINER_TOOL = "podman"

class ContainerManager:
    """
    Manages container operations such as creation, execution, and cleanup.
    This class can be used as a context manager to ensure containers are cleaned up.
    """
    def __init__(self, image_name: str, container_tool: str = DEFAULT_CONTAINER_TOOL):
        """
        Initializes the ContainerManager.

        Args:
            image_name: The name of the container image to use.
            container_tool: The container utility to use ("podman" or "docker").
        """
        self.image_name = image_name
        self.container_tool = container_tool
        self.container_id = None
        logger.info(f"ContainerManager initialized for image '{image_name}' using '{container_tool}'.")

    def _run_command(self, cmd_list: list, check: bool = True, shell: bool = False, **kwargs) -> subprocess.CompletedProcess:
        """
        Helper function to run a command using subprocess.
        Modified to always capture stdout and stderr.

        Args:
            cmd_list: Command and arguments as a list (if shell=False) or a string (if shell=True).
            check: If True, raises CalledProcessError if the command returns a non-zero exit code.
            shell: If True, the command is executed through the shell. Use with caution.
            **kwargs: Additional arguments for subprocess.run.

        Returns:
            A subprocess.CompletedProcess object.

        Raises:
            subprocess.CalledProcessError: If the command fails and check is True.
        """
        cmd_str = ' '.join(cmd_list) if isinstance(cmd_list, list) else cmd_list
        logger.debug(f"Executing command: {cmd_str}")
        try:
            kwargs.setdefault('text', True)
            result = subprocess.run(cmd_list, shell=shell, check=check, capture_output=True, **kwargs)
            if result.stdout:
                logger.debug(f"Stdout: {result.stdout.strip()}")
            if result.stderr:
                logger.debug(f"Stderr: {result.stderr.strip()}")
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with exit code {e.returncode}: {cmd_str}")
            if e.stdout:
                logger.error(f"Failed command stdout: {e.stdout.strip()}")
            if e.stderr:
                logger.error(f"Failed command stderr: {e.stderr.strip()}")
            raise
        except FileNotFoundError:
            logger.error(f"Command not found: {cmd_list[0] if isinstance(cmd_list, list) else cmd_str.split()[0]}. Ensure '{self.container_tool}' is installed and in PATH.")
            raise


    def create(self):
        """Creates a new container but does not start it."""
        if self.container_id:
            logger.warning(f"Container {self.container_id} already exists. Skipping creation.")
            return
        cmd = [self.container_tool, "create", "-ti", self.image_name, "tail", "-f", "/dev/null"]
        result = self._run_command(cmd)
        self.container_id = result.stdout.strip()
        logger.info(f"Container {self.container_id} created from image '{self.image_name}'.")

    def start(self, timeout: int = 30):
        """Starts the container and waits for it to be in a running state."""
        if not self.container_id:
            raise RuntimeError("Container must be created before starting.")

        logger.info(f"Starting container {self.container_id}...")
        self._run_command([self.container_tool, "start", self.container_id])

        logger.info(f"Waiting for container {self.container_id} to be running (timeout: {timeout}s)...")
        for _ in range(timeout):
            try:
                inspect_cmd = [self.container_tool, "inspect", "-f", "{{.State.Running}}", self.container_id]
                result = self._run_command(inspect_cmd, check=False)
                if result.returncode == 0 and result.stdout.strip() == "true":
                    logger.info(f"Container {self.container_id} is now running.")
                    return
            except subprocess.CalledProcessError as e:
                logger.warning(f"Error inspecting container {self.container_id} while waiting for start: {e.stderr}")
            time.sleep(1)
        raise RuntimeError(f"Container {self.container_id} did not reach running state within {timeout} seconds.")

    def stop(self, timeout: int = 10):
        """Stops the container."""
        if not self.container_id:
            logger.warning("No container ID set to stop.")
            return
        logger.info(f"Stopping container {self.container_id} (timeout: {timeout}s)...")
        # Podman uses --time, Docker uses -t for stop timeout
        stop_flag = "--time" if self.container_tool == "podman" else "-t"
        try:
            self._run_command([self.container_tool, "stop", stop_flag, str(timeout), self.container_id], check=False)
            logger.info(f"Container {self.container_id} stop command issued.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error stopping container {self.container_id}: {e.stderr}")


    def remove(self, force: bool = True):
        """Removes the container."""
        if not self.container_id:
            logger.warning("No container ID set to remove.")
            return
        logger.info(f"Removing container {self.container_id}...")
        cmd = [self.container_tool, "rm"]
        if force:
            cmd.append("-f")
        cmd.append(self.container_id)
        try:
            self._run_command(cmd, check=False)
            logger.info(f"Container {self.container_id} removed.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error removing container {self.container_id}: {e.stderr}")
        finally:
            self.container_id = None

    def copy_to(self, src_path: Path, dest_in_container: str):
        """Copies files/directories from the host to the container."""
        if not self.container_id:
            raise RuntimeError("Container not available for copy operation.")
        if not src_path.exists():
            raise FileNotFoundError(f"Source path for copy does not exist: {src_path}")

        dest_path_str = f"{self.container_id}:{dest_in_container}"
        logger.info(f"Copying '{src_path}' to '{dest_path_str}'...")
        self._run_command([self.container_tool, "cp", str(src_path), dest_path_str])
        logger.info(f"Successfully copied '{src_path}' to '{dest_path_str}'.")

    def execute_command(self, command: str) -> dict:
        """Executes a command inside the running container and returns a dictionary with the executed command, stdout, stderr, and return_code."""
        if not self.container_id:
            raise RuntimeError("Container not available for command execution.")

        cmd = [
            self.container_tool,
            "exec",
            self.container_id,
            "bash",
            "-c",
            command,
        ]

        full_cmd_str = " ".join(cmd)
        logger.info(f"Executing in container {self.container_id}: {full_cmd_str}")

        result = self._run_command(cmd, shell=False, check=False)

        if result.returncode == 0:
            logger.info(f"Successfully executed in container: {command}")
        else:
            logger.warning(f"Command in container exited with code {result.returncode}: {command}")
            if result.stdout.strip():
                logger.warning(f"  Stdout: {result.stdout.strip()}")
            if result.stderr.strip():
                logger.warning(f"  Stderr: {result.stderr.strip()}")

        return {
            "command": command,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "return_code": result.returncode
        }

    def export_paths(self, target_paths_in_container: list[str], host_output_dir: Path):
        """Exports specified paths from the container to the host."""
        if not self.container_id:
            raise RuntimeError("Container not available for export operation.")
        if not target_paths_in_container:
            logger.warning("No target paths specified for export. Skipping.")
            return

        host_output_dir.mkdir(parents=True, exist_ok=True)

        # Remove leading slashes for tar command compatibility within container context
        cleaned_target_paths = [p.lstrip("/") for p in target_paths_in_container]
        target_paths_str = " ".join(cleaned_target_paths)

        logger.info(f"Exporting '{target_paths_str}' from {self.container_id} to '{host_output_dir}'...")
        cmd_str = f"{self.container_tool} export {self.container_id} | tar -x -C \"{str(host_output_dir)}\" {target_paths_str}"
        self._run_command(cmd_str, shell=True)
        self._run_command(f"chmod -R u+rwx \"{str(host_output_dir)}\"", shell=True)
        logger.info(f"Successfully exported paths to '{host_output_dir}'.")

    def capture_command_output(self, command: str, host_outfile: Path):
        """Executes a command in the container and saves its stdout to a host file."""
        if not self.container_id:
            raise RuntimeError("Container not available for capturing command output.")

        logger.info(f"Capturing output of '{command}' from {self.container_id} to '{host_outfile}'...")
        escaped_command = command.replace('"', r'\"')
        full_cmd_str = f"{self.container_tool} exec {self.container_id} bash -c \"{escaped_command}\""
        result = self._run_command(full_cmd_str, shell=True, check=False)

        host_outfile.parent.mkdir(parents=True, exist_ok=True)
        with open(host_outfile, "w", encoding="utf-8") as f:
            f.write(result.stdout)
        logger.info(f"Output of '{command}' saved to '{host_outfile}'.")
        if result.returncode != 0:
            logger.warning(f"Command '{command}' in container exited with code {result.returncode}. Stderr: {result.stderr.strip()}")


    def __enter__(self):
        """Context manager entry: creates the container."""
        self.create()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: stops and removes the container."""
        logger.info(f"Cleaning up container {self.container_id}...")
        try:
            if self.container_id:
                self.stop(timeout=0)
        except Exception as e:
            logger.error(f"Exception during container stop in __exit__: {e}", exc_info=False)
        finally:
            if self.container_id:
                try:
                    self.remove(force=True)
                except Exception as e:
                    logger.error(f"Exception during container removal in __exit__: {e}", exc_info=False)
        logger.info("Container cleanup process finished.")


def load_config(config_path: Path) -> dict:
    """Loads YAML configuration from the given path."""
    logger.info(f"Loading configuration from '{config_path}'...")
    if not config_path.is_file():
        logger.error(f"Configuration file not found: {config_path}")
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    logger.info("Configuration loaded successfully.")
    return config

def generate_diff_report(
    base_path: Path,
    after_path: Path,
    diff_type: str,
    exclude_paths: list[str] = None
) -> str:
    """
    Generates a diff report between two directories or files.

    Args:
        base_path: Path to the base directory/file.
        after_path: Path to the after directory/file.
        diff_type: Type of diff ("rq", "urN", "text").
        exclude_paths: List of path patterns to exclude (for "rq" and "urN").

    Returns:
        The generated diff report as a string.
    """
    if exclude_paths is None:
        exclude_paths = []

    exclude_args_str = "|".join(exclude_paths) if exclude_paths else "EMPTY_EXCLUDE_LIST_PLACEHOLDER"

    cmd_str = None
    base_name = base_path.name
    after_name = after_path.name
    # All diff commands are executed from the parent directory for consistent paths

    if diff_type == "rq":
        diff_command_part = f"LANG=C diff -rq \"{base_name}\" \"{after_name}\""
        if exclude_paths: # Only add grep if there are exclusions
             diff_command_part += f" | grep -Ev '^[^ ]* ([^ ]* )?[^ /]*({exclude_args_str})'"
        cmd_str = f"cd \"{base_path.parent}\" && {diff_command_part}"

    elif diff_type == "urN":
        awk_script = "'/^[a-zA-Z]/{if(n){if(h!~p){for(i=0;i<c;i++)print a[i];}delete a};c=0;h=$0;n=1}n{a[c++]=$0}END{if(n&&h!~p){for(i=0;i<c;i++)print a[i]}}'"
        sed_script = r"'/^(---|\+\+) /s/\t.*/'"
        diff_command_part = f"LANG=C diff -urN \"{base_name}\" \"{after_name}\""
        if exclude_paths:
            diff_command_part += f" | awk -v p='^[^ ]* [^ ]* [^ /]*({exclude_args_str})' {awk_script}"
        else:
            simplified_awk = "'/^[a-zA-Z]/{if(n){for(i=0;i<c;i++)print a[i];delete a};c=0;h=$0;n=1}n{a[c++]=$0}END{if(n){for(i=0;i<c;i++)print a[i]}}'"
            diff_command_part += f" | awk {simplified_awk}"
        diff_command_part += f" | sed -e {sed_script}"
        cmd_str = f"cd \"{base_path.parent}\" && {diff_command_part}"

    elif diff_type == "text":
        base_relative_path = f"{base_path.parent.name}/{base_path.name}"
        after_relative_path = f"{after_path.parent.name}/{after_path.name}"
        sed_script = r"'/^\(---\|+++\) /s/\t.*//'"
        cmd_str = f"cd \"{base_path.parent.parent}\" && LANG=C diff -su \"{base_relative_path}\" \"{after_relative_path}\" | sed -e {sed_script}"
    else:
        logger.error(f"Unsupported diff type: {diff_type}")
        return ""
    logger.info(f"Generating {diff_type} diff...")
    logger.debug(f"Diff command: {cmd_str}")

    result = subprocess.run(cmd_str, shell=True, check=False, capture_output=True, text=True, encoding='utf-8')

    if result.returncode > 1:
        logger.error(f"Diff command failed or encountered an issue. Exit code: {result.returncode}. Stderr: {result.stderr.strip()}")
    logger.info(f"Diff content for type '{diff_type}' generated.")
    return result.stdout


def run_analysis(config_path: Path, output_report_path: Path, container_tool: str):
    """
    Main analysis workflow.
    """
    config = load_config(config_path)
    base_image = config.get('base_image')
    if not base_image:
        logger.error("Configuration error: 'base_image' not specified in input YAML.")
        raise ValueError("'base_image' must be defined in the configuration.")

    output_data = {
        "report_metadata": {
            "generated_on": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "container_tool": container_tool
        },
        "definitions": config,
        "main_operation_results": [],
        "diff_reports": {
            "filesystem_rq": None,
            "filesystem_urN": None,
            "command_outputs": []
        }
    }

    with ContainerManager(image_name=base_image, container_tool=container_tool) as cm:
        logger.info("--- Preparing Container ---")
        for entry in config.get('prepare', {}).get('copy_files', []):
            src_path = Path(entry['src'])
            if not src_path.exists():
                logger.error(f"Source file for copy not found: {src_path}. Skipping this copy operation.")
                continue
            cm.copy_to(src_path, entry['dest'])

        cm.start()

        for cmd_str in config.get('prepare', {}).get('commands', []):
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

            target_dirs = config.get('target_dirs', [])
            if not target_dirs:
                logger.warning("'target_dirs' not specified in config. File system diffs might be empty or limited.")

            logger.info("--- Capturing Baseline State ---")
            if target_dirs:
                cm.export_paths(target_dirs, base_fs_root)
            for entry in config.get('command_diff', []):
                outfile_name = Path(entry['outfile']).name
                cm.capture_command_output(entry['command'], base_cmd_output_dir / outfile_name)
            logger.info("--- Baseline State Captured ---")

            logger.info("--- Executing Main Operation ---")
            main_op_commands = config.get('main_operation', {}).get('commands', [])
            for cmd_str in main_op_commands:
                cmd_result = cm.execute_command(cmd_str)
                output_data["main_operation_results"].append(cmd_result)
            logger.info("--- Main Operation Complete ---")

            logger.info("--- Capturing State After Main Operation ---")
            if target_dirs:
                cm.export_paths(target_dirs, after_fs_root)
            for entry in config.get('command_diff', []):
                outfile_name = Path(entry['outfile']).name
                cm.capture_command_output(entry['command'], after_cmd_output_dir / outfile_name)
            logger.info("--- State After Main Operation Captured ---")

            logger.info("--- Generating Diff Reports ---")
            exclude_paths = config.get('exclude_paths', [])

            if target_dirs:
                fs_diff_rq_content = generate_diff_report(base_fs_root, after_fs_root, "rq", exclude_paths)
                output_data["diff_reports"]["filesystem_rq"] = list(filter(None, fs_diff_rq_content.split('\n')))

                fs_diff_urn_content = generate_diff_report(base_fs_root, after_fs_root, "urN", exclude_paths)
                output_data["diff_reports"]["filesystem_urN"] = list(filter(None, re.split(r'(?=^[a-zA-Z].+$)', fs_diff_urn_content, flags=re.MULTILINE)))
            else:
                logger.info("Skipping filesystem diffs as 'target_dirs' was empty.")
                output_data["diff_reports"]["filesystem_rq"] = ["Skipped: 'target_dirs' was not specified or empty in config."]
                output_data["diff_reports"]["filesystem_urN"] = ["Skipped: 'target_dirs' was not specified or empty in config."]


            for entry in config.get('command_diff', []):
                outfile_name = Path(entry['outfile']).name
                base_cmd_file = base_cmd_output_dir / outfile_name
                after_cmd_file = after_cmd_output_dir / outfile_name

                command_diff_entry = {"command": entry['command'], "diff_file": entry['outfile'], "diff_content": None}
                if base_cmd_file.exists() and after_cmd_file.exists():
                    cmd_diff_content = generate_diff_report(base_cmd_file, after_cmd_file, "text")
                    command_diff_entry["diff_content"] = cmd_diff_content
                else:
                    missing_files_info = []
                    if not base_cmd_file.exists(): missing_files_info.append(f"baseline output '{base_cmd_file}'")
                    if not after_cmd_file.exists(): missing_files_info.append(f"after output '{after_cmd_file}'")
                    logger.warning(f"Skipping diff for command '{entry['command']}' due to missing output files: {', '.join(missing_files_info)}")
                    command_diff_entry["diff_content"] = f"Skipped: Output file(s) not found ({', '.join(missing_files_info)})."
                output_data["diff_reports"]["command_outputs"].append(command_diff_entry)

            logger.info("--- Diff Report Generation Complete ---")

    logger.info(f"Writing final JSON report to '{output_report_path}'...")
    output_report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_report_path, "w", encoding='utf-8') as f_report:
        json.dump(output_data, f_report, indent=4, ensure_ascii=False)
    logger.info(f"✅ Environment diff report successfully generated: {output_report_path.resolve()}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyzes differences in a container environment before and after executing specified operations." \
                    "Generates a JSON report detailing file system changes, command output variations, and execution results.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--input",
        default="input.yaml",
        type=Path,
        help="Path to the input YAML configuration file."
    )
    parser.add_argument(
        "--output",
        default="output.json",
        type=Path,
        help="Path to save the generated JSON report."
    )
    parser.add_argument(
        "--container-tool",
        default=DEFAULT_CONTAINER_TOOL,
        choices=["podman", "docker"],
        help="Container runtime to use (podman or docker)."
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (DEBUG level)."
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        for handler in logging.getLogger().handlers:
            handler.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled.")


    try:
        run_analysis(args.input, args.output, args.container_tool)
    except FileNotFoundError as e:
        logger.critical(f"A critical file was not found: {e}")
        print(f"Error: {e}. Please check file paths and prerequisites.")
    except subprocess.CalledProcessError as e:
        logger.critical(f"A critical command failed during execution: {e}")
        print(f"Error: A critical command failed. Check logs for details: {e}")
    except RuntimeError as e:
        logger.critical(f"A runtime error occurred: {e}")
        print(f"Error: {e}. Check logs for details.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred during analysis: {e}", exc_info=True)
        print(f"An unexpected error occurred. Check logs for details: {e}")


if __name__ == "__main__":
    main()
