import argparse
import logging
import subprocess
from pathlib import Path

from .analysis import run_analysis
from .container import DEFAULT_CONTAINER_TOOL

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Analyzes differences in a container environment before and after executing specified operations."\
            " Generates a JSON report detailing file system changes, command output variations, and execution results."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        default="input.yaml",
        type=Path,
        help="Path to the input YAML configuration file.",
    )
    parser.add_argument(
        "--output",
        default="output.json",
        type=Path,
        help="Path to save the generated JSON report.",
    )
    parser.add_argument(
        "--container-tool",
        default=DEFAULT_CONTAINER_TOOL,
        choices=["podman", "docker"],
        help="Container runtime to use (podman or docker).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (DEBUG level).",
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
