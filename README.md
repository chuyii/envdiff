# envdiff

`envdiff` is a Python tool that analyzes the changes in a container environment before and after executing custom operations. It generates a JSON report that includes differences in the file system, command outputs and other relevant information.

## Requirements

- Python 3.10+
- Either `podman` or `docker` must be installed and accessible in `PATH`.

## Installation

Install the package from the repository root using `pip`:

```bash
pip install .
```

This will provide the `envdiff` command for running the tool.

## Usage

1. Prepare a YAML configuration file. An example is provided in `example-input.yaml`.
2. Run the tool with:

```bash
python -m envdiff.cli --input example-input.yaml --output output.json
```

By default `podman` is used. To use Docker instead, pass `--container-tool docker`.

The resulting report is written to `output.json`. An example output is included in `example-output.json`.

### Formatting a JSON report

Convert an existing JSON report to a plain text summary:

```bash
python -m envdiff.cli --summarize output.json --text-output report.txt
```

If `--text-output` is omitted, the summary is printed to stdout.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
