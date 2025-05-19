import subprocess
import time
import logging
from pathlib import Path
from typing import List

DEFAULT_CONTAINER_TOOL = "podman"

logger = logging.getLogger(__name__)

class ContainerManager:
    """Manage container lifecycle and operations."""

    def __init__(self, image_name: str, container_tool: str = DEFAULT_CONTAINER_TOOL):
        self.image_name = image_name
        self.container_tool = container_tool
        self.container_id = None
        logger.info(f"ContainerManager initialized for image '{image_name}' using '{container_tool}'.")

    def _run_command(self, cmd_list: list, check: bool = True, shell: bool = False, **kwargs) -> subprocess.CompletedProcess:
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
            logger.error(
                f"Command not found: {cmd_list[0] if isinstance(cmd_list, list) else cmd_str.split()[0]}. "
                f"Ensure '{self.container_tool}' is installed and in PATH."
            )
            raise

    def create(self):
        """Create a new container but do not start it."""
        if self.container_id:
            logger.warning(f"Container {self.container_id} already exists. Skipping creation.")
            return
        cmd = [self.container_tool, "create", "-ti", self.image_name, "tail", "-f", "/dev/null"]
        result = self._run_command(cmd)
        self.container_id = result.stdout.strip()
        logger.info(f"Container {self.container_id} created from image '{self.image_name}'.")

    def start(self, timeout: int = 30):
        """Start the container and wait until it is running."""
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
                logger.warning(
                    f"Error inspecting container {self.container_id} while waiting for start: {e.stderr}"
                )
            time.sleep(1)
        raise RuntimeError(f"Container {self.container_id} did not reach running state within {timeout} seconds.")

    def stop(self, timeout: int = 10):
        """Stop the container."""
        if not self.container_id:
            logger.warning("No container ID set to stop.")
            return
        logger.info(f"Stopping container {self.container_id} (timeout: {timeout}s)...")
        stop_flag = "--time" if self.container_tool == "podman" else "-t"
        try:
            self._run_command([self.container_tool, "stop", stop_flag, str(timeout), self.container_id], check=False)
            logger.info(f"Container {self.container_id} stop command issued.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error stopping container {self.container_id}: {e.stderr}")

    def remove(self, force: bool = True):
        """Remove the container."""
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
        """Copy files/directories from the host to the container."""
        if not self.container_id:
            raise RuntimeError("Container not available for copy operation.")
        if not src_path.exists():
            raise FileNotFoundError(f"Source path for copy does not exist: {src_path}")

        dest_path_str = f"{self.container_id}:{dest_in_container}"
        logger.info(f"Copying '{src_path}' to '{dest_path_str}'...")
        self._run_command([self.container_tool, "cp", str(src_path), dest_path_str])
        logger.info(f"Successfully copied '{src_path}' to '{dest_path_str}'.")

    def execute_command(self, command: str) -> dict:
        """Execute a command inside the running container."""
        if not self.container_id:
            raise RuntimeError("Container not available for command execution.")

        cmd = [self.container_tool, "exec", self.container_id, "bash", "-c", command]
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
            "return_code": result.returncode,
        }

    def export_paths(self, target_paths_in_container: List[str], host_output_dir: Path):
        """Export specified paths from the container to the host."""
        if not self.container_id:
            raise RuntimeError("Container not available for export operation.")
        if not target_paths_in_container:
            logger.warning("No target paths specified for export. Skipping.")
            return

        host_output_dir.mkdir(parents=True, exist_ok=True)
        cleaned_target_paths = [p.lstrip("/") for p in target_paths_in_container]
        target_paths_str = " ".join(cleaned_target_paths)

        logger.info(f"Exporting '{target_paths_str}' from {self.container_id} to '{host_output_dir}'...")
        cmd_str = f"{self.container_tool} export {self.container_id} | tar -x -C \"{str(host_output_dir)}\" {target_paths_str}"
        self._run_command(cmd_str, shell=True)
        self._run_command(f"chmod -R u+rwx \"{str(host_output_dir)}\"", shell=True)
        logger.info(f"Successfully exported paths to '{host_output_dir}'.")

    def capture_command_output(self, command: str, host_outfile: Path):
        """Execute a command in the container and save its stdout to a host file."""
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
            logger.warning(
                f"Command '{command}' in container exited with code {result.returncode}. Stderr: {result.stderr.strip()}"
            )

    def __enter__(self):
        self.create()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
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
