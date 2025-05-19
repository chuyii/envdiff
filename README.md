# envdiff

`envdiff` is a Python tool that analyzes the changes in a container environment before and after executing custom operations. It generates a JSON report that includes differences in the file system, command outputs and other relevant information.

## Requirements

- Python 3.8+
- Either `podman` or `docker` must be installed and accessible in `PATH`.

## Installation

Install the package from the repository root using `pip`:

```bash
pip install .
```

This will provide the `envdiff` command for running the tool.

## Usage

1. Prepare a YAML configuration file. An example is provided in `example-input.yaml`. See the next section for available keys.
2. Run the tool with:

```bash
envdiff --input example-input.yaml --output output.json
```

By default `podman` is used. To use Docker instead, pass `--container-tool docker`.

The resulting report is written to `output.json`. An example output is included in `example-output.json`.
### Input YAML structure
The configuration file uses these keys:
- `extends`: list of additional YAML files to load before this file. Lists are
  concatenated while other keys are overwritten by later files.
- `base_image` (required): container image to analyze.
- `prepare.copy_files`: list of `{src, dest}` pairs copied into the container before running any commands. Relative `src` paths are interpreted relative to the configuration file passed via `--input`.
- `prepare.commands`: commands executed before capturing the baseline state.
- `main_operation.commands`: commands executed during the main operation under analysis.
- `target_dirs`: directories inside the container to export and compare.
- `exclude_paths`: paths excluded from file system diff results.
- `omit_diff_paths`: paths whose diff hunks are omitted in the unified diff.
- `command_diff`: list of commands to capture and diff; each requires `command` and `outfile`.


### Formatting a JSON report

Convert an existing JSON report to a plain text summary:

```bash
python -m envdiff.cli --summarize output.json --text-output report.txt
```

If `--text-output` is omitted, the summary is printed to stdout.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
