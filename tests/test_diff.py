import tempfile
from pathlib import Path

from envdiff.diff import generate_diff_report


def test_generate_diff_rq_and_urn():
    """Ensure diff output for 'rq' and 'urN' types contains expected lines."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "base"
        after_dir = Path(tmpdir) / "after"
        base_dir.mkdir()
        after_dir.mkdir()

        # File existing in both but with different contents
        (base_dir / "common.txt").write_text("foo\n", encoding="utf-8")
        (after_dir / "common.txt").write_text("bar\n", encoding="utf-8")
        # File existing only in after directory
        (after_dir / "new.txt").write_text("new\n", encoding="utf-8")

        rq_output = generate_diff_report(base_dir, after_dir, "rq")
        assert "Files base/common.txt and after/common.txt differ" in rq_output
        assert "Only in after: new.txt" in rq_output

        urn_output = generate_diff_report(base_dir, after_dir, "urN")
        assert "diff -urN base/common.txt after/common.txt" in urn_output
        assert "--- base/common.txt" in urn_output
        assert "+++ after/common.txt" in urn_output
        assert "diff -urN base/new.txt after/new.txt" in urn_output


def test_generate_text_diff():
    """Ensure textual diff is produced for single files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        base_file = tmp_path / "base.txt"
        after_file = tmp_path / "after.txt"

        base_file.write_text("foo\n", encoding="utf-8")
        after_file.write_text("bar\n", encoding="utf-8")

        diff_output = generate_diff_report(base_file, after_file, "text")
        assert "---" in diff_output and "+++" in diff_output
        assert "-foo" in diff_output
        assert "+bar" in diff_output
