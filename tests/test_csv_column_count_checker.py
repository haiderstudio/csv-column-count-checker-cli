"""Tests for csv-column-count-checker-cli.

Stdlib unittest only. Run with:
    python3 tests/test_csv_column_count_checker.py
"""

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "csv_column_count_checker.py"
EXAMPLES = ROOT / "examples"

sys.path.insert(0, str(ROOT / "src"))
from csv_column_count_checker import (  # noqa: E402
    check_file,
    check_text,
    collect_files,
    run,
)


def run_cli(args, cwd=None, stdin_text=None):
    """Run the checker as a subprocess. Returns (exit_code, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(SRC)] + args,
        cwd=cwd,
        input=stdin_text,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


class CheckTextTests(unittest.TestCase):
    def test_clean_file_passes(self):
        problems = check_text("a,b,c\n1,2,3\n4,5,6\n", "f.csv")
        self.assertEqual(problems, [])

    def test_short_row(self):
        problems = check_text("a,b,c\n1,2\n", "f.csv")
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].line, 2)
        self.assertIn("2 columns", problems[0].reason)
        self.assertIn("header has 3", problems[0].reason)

    def test_long_row(self):
        problems = check_text("a,b\n1,2,3\n", "f.csv")
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].line, 2)
        self.assertIn("3 columns", problems[0].reason)
        self.assertIn("header has 2", problems[0].reason)

    def test_every_ragged_row_reported(self):
        text = "a,b,c\n1,2\n3,4,5,6\n7,8,9\n10\n"
        problems = check_text(text, "f.csv")
        self.assertEqual([p.line for p in problems], [2, 3, 5])

    def test_quoted_comma_is_one_field(self):
        problems = check_text('a,b,c\n1,"x, y",3\n', "f.csv")
        self.assertEqual(problems, [])

    def test_quoted_comma_does_not_hide_a_ragged_row(self):
        problems = check_text('a,b,c\n1,"x, y"\n', "f.csv")
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].line, 2)

    def test_blank_lines_skipped_with_real_line_numbers(self):
        text = "a,b,c\n\n1,2,3\n\n4,5\n"
        problems = check_text(text, "f.csv")
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].line, 5)

    def test_header_only_passes(self):
        problems = check_text("a,b,c\n", "f.csv")
        self.assertEqual(problems, [])

    def test_empty_file_flagged(self):
        problems = check_text("", "f.csv")
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].line, 1)
        self.assertIn("no header row", problems[0].reason)

    def test_only_blank_lines_flagged(self):
        problems = check_text("\n\n", "f.csv")
        self.assertEqual(len(problems), 1)
        self.assertIn("no header row", problems[0].reason)

    def test_unterminated_quote_flagged(self):
        problems = check_text('a,b\n1,"xyz\n', "f.csv")
        self.assertEqual(len(problems), 1)
        self.assertIn("cannot parse CSV", problems[0].reason)

    def test_multiline_quoted_field_line_number(self):
        text = 'a,b\n1,"x\ny"\n2\n'
        problems = check_text(text, "f.csv")
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].line, 4)

    def test_single_column_file(self):
        problems = check_text("name\nalice\nbob\n", "f.csv")
        self.assertEqual(problems, [])

    def test_single_column_ragged(self):
        problems = check_text("name\nalice,bob\n", "f.csv")
        self.assertEqual(len(problems), 1)
        self.assertIn("2 columns", problems[0].reason)

    def test_custom_delimiter(self):
        problems = check_text("a;b;c\n1;2\n", "f.csv", delimiter=";")
        self.assertEqual(len(problems), 1)
        self.assertIn("2 columns", problems[0].reason)

    def test_custom_delimiter_clean(self):
        problems = check_text("a;b;c\n1;2;3\n", "f.csv", delimiter=";")
        self.assertEqual(problems, [])

    def test_crlf_line_endings(self):
        problems = check_text("a,b,c\r\n1,2\r\n", "f.csv")
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].line, 2)

    def test_row_of_only_commas_counts(self):
        problems = check_text("a,b\n,,\n", "f.csv")
        self.assertEqual(len(problems), 1)
        self.assertIn("3 columns", problems[0].reason)

    def test_problem_text_format(self):
        problems = check_text("a,b\n1,2,3\n", "dir/f.csv")
        self.assertEqual(problems[0].text(),
                         "dir/f.csv:2: row has 3 columns, header has 2")


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content, mode="w"):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if "b" in mode:
            path.write_bytes(content)
        else:
            path.write_text(content)
        return str(path)

    def test_non_utf8_file(self):
        path = self.write("bad.csv", b"a,b\n\xff,\n", mode="wb")
        problems = check_file(path)
        self.assertEqual(len(problems), 1)
        self.assertIn("UTF-8", problems[0].reason)

    def test_null_byte_file(self):
        path = self.write("nul.csv", b"a,b\n1,\x00\n", mode="wb")
        problems = check_file(path)
        self.assertEqual(len(problems), 1)
        self.assertIn("cannot parse CSV", problems[0].reason)

    def test_unreadable_file(self):
        path = self.write("gone.csv", "a,b\n1,2\n")
        os.chmod(path, 0)
        try:
            problems = check_file("/nonexistent-dir-xyz/nope.csv")
        finally:
            os.chmod(path, 0o644)
        self.assertEqual(len(problems), 1)
        self.assertIn("cannot be read", problems[0].reason)

    def test_file_given_directly_is_checked_whatever_its_name(self):
        path = self.write("data.txt", "a,b\n1,2,3\n")
        problems = check_file(path)
        self.assertEqual(len(problems), 1)

    def test_folder_walk_only_csv_names(self):
        self.write("good.csv", "a,b\n1,2\n")
        self.write("notes.txt", "a,b\n1,2,3\n")
        files, missing = collect_files([str(self.dir)])
        self.assertIsNone(missing)
        self.assertEqual([Path(f).name for f in files], ["good.csv"])

    def test_folder_walk_recursive(self):
        self.write("top.csv", "a,b\n1,2\n")
        self.write("sub/deep.csv", "a,b\n1,2\n")
        files, missing = collect_files([str(self.dir)])
        self.assertEqual(len(files), 2)

    def test_no_recursive(self):
        self.write("top.csv", "a,b\n1,2\n")
        self.write("sub/deep.csv", "a,b\n1,2\n")
        files, missing = collect_files([str(self.dir)], recursive=False)
        self.assertEqual(len(files), 1)

    def test_git_folder_skipped(self):
        self.write(".git/evil.csv", "a,b\n1,2,3\n")
        self.write("good.csv", "a,b\n1,2\n")
        files, missing = collect_files([str(self.dir)])
        self.assertEqual([Path(f).name for f in files], ["good.csv"])

    def test_exclude(self):
        self.write("keep.csv", "a,b\n1,2\n")
        self.write("skip.csv", "a,b\n1,2\n")
        files, missing = collect_files([str(self.dir)], exclude=["skip.csv"])
        self.assertEqual([Path(f).name for f in files], ["keep.csv"])

    def test_dedupe(self):
        path = self.write("a.csv", "a,b\n1,2\n")
        files, missing = collect_files([path, path])
        self.assertEqual(len(files), 1)

    def test_missing_path(self):
        files, missing = collect_files([str(self.dir / "nope.csv")])
        self.assertIsNone(files)
        self.assertIn("nope.csv", missing)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return str(path)

    def test_clean_exit_0(self):
        path = self.write("good.csv", "a,b\n1,2\n")
        code, out, err = run_cli([path])
        self.assertEqual(code, 0)
        self.assertIn("OK", out)
        self.assertIn("1 file(s) checked", out)

    def test_ragged_exit_1(self):
        path = self.write("bad.csv", "a,b,c\n1,2\n")
        code, out, err = run_cli([path])
        self.assertEqual(code, 1)
        self.assertIn("row has 2 columns, header has 3", out)
        self.assertIn("Checked 1 file(s), 1 problem(s) in 1 file(s).", out)

    def test_no_args_exit_2(self):
        code, out, err = run_cli([])
        self.assertEqual(code, 2)

    def test_missing_path_exit_2(self):
        code, out, err = run_cli([str(self.dir / "nope.csv")])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_bad_flag_exit_2(self):
        code, out, err = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_bad_delimiter_exit_2(self):
        path = self.write("a.csv", "a,b\n1,2\n")
        code, out, err = run_cli([path, "--delimiter", ";;"])
        self.assertEqual(code, 2)

    def test_stdin(self):
        code, out, err = run_cli(["--stdin"], stdin_text="a,b,c\n1,2\n")
        self.assertEqual(code, 1)
        self.assertIn("<stdin>:2: row has 2 columns, header has 3", out)

    def test_stdin_clean(self):
        code, out, err = run_cli(["--stdin"], stdin_text="a,b\n1,2\n")
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_stdin_with_paths_is_usage_error(self):
        code, out, err = run_cli(["x.csv", "--stdin"])
        self.assertEqual(code, 2)

    def test_json(self):
        path = self.write("bad.csv", "a,b\n1,2,3\n")
        code, out, err = run_cli([path, "--json"])
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["files_checked"], 1)
        self.assertEqual(data["files_with_problems"], 1)
        self.assertEqual(data["problems"][0]["line"], 2)
        self.assertIn("3 columns", data["problems"][0]["reason"])
        self.assertIn("row has 3 columns", err)

    def test_json_clean(self):
        path = self.write("good.csv", "a,b\n1,2\n")
        code, out, err = run_cli([path, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["problems"], [])

    def test_version(self):
        code, out, err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("1.0.0", out)

    def test_delimiter_flag(self):
        path = self.write("semi.csv", "a;b;c\n1;2\n")
        code, out, err = run_cli([path, "--delimiter", ";"])
        self.assertEqual(code, 1)
        self.assertIn("row has 2 columns, header has 3", out)

    def test_input_files_unchanged(self):
        path = self.write("a.csv", "a,b\n1,2,3\n")
        before = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        run_cli([path])
        after = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_folder_run(self):
        self.write("good.csv", "a,b\n1,2\n")
        self.write("bad.csv", "a,b\n1,2,3\n")
        code, out, err = run_cli([str(self.dir)])
        self.assertEqual(code, 1)
        self.assertIn("Checked 2 file(s), 1 problem(s) in 1 file(s).", out)

    def test_run_example_output_matches_sample(self):
        proc = subprocess.run(["sh", "examples/run-example.sh"],
                              cwd=str(ROOT), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        sample = (EXAMPLES / "sample-output.md").read_text()
        block = sample.split("```text\n")[1].split("\n```")[0]
        self.assertEqual(proc.stdout.strip(), block.strip())

    def test_examples_checked(self):
        code, out, err = run_cli(["examples"], cwd=str(ROOT))
        self.assertEqual(code, 1)
        self.assertIn("Checked 4 file(s), 4 problem(s) in 2 file(s).", out)

    def test_readme_quoted_outputs_are_real(self):
        readme = (ROOT / "README.md").read_text()
        blocks = [
            "OK — 1 file(s) checked, every row has the same column count.",
            "examples/ragged.csv:3: row has 2 columns, header has 3",
            "examples/ragged.csv:4: row has 4 columns, header has 3",
            "examples/ragged.csv:6: row has 2 columns, header has 3",
            "Checked 1 file(s), 3 problem(s) in 1 file(s).",
            "examples/configs/more.csv:2: row has 3 columns, header has 2",
            "Checked 4 file(s), 4 problem(s) in 2 file(s).",
            "<stdin>:2: row has 2 columns, header has 3",
            '"files_checked": 1',
            '"reason": "row has 3 columns, header has 2"',
        ]
        for block in blocks:
            self.assertIn(block, readme,
                          f"README is missing real output: {block!r}")


class HygieneTests(unittest.TestCase):
    def test_gitignore_first_line_is_env(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_no_banned_words_outside_tests(self):
        banned = ["TODO", "FIXME", "XXX", "lorem", "coming soon"]
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(errors="replace")
            for word in banned:
                self.assertNotIn(word, text,
                                 f"{word} found in {path.relative_to(ROOT)}")

    def test_no_absolute_paths(self):
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(errors="replace")
            self.assertNotIn("/home/hatch", text,
                             f"absolute path in {path.relative_to(ROOT)}")
            self.assertNotIn("/Users/", text,
                             f"absolute path in {path.relative_to(ROOT)}")
            self.assertNotIn("/tmp/", text,
                             f"absolute path in {path.relative_to(ROOT)}")

    def test_stdlib_only_imports(self):
        allowed_src = {
            "argparse", "csv", "fnmatch", "io", "json", "os", "sys",
            "pathlib",
        }
        allowed_tests = allowed_src | {
            "ast", "hashlib", "subprocess", "tempfile", "unittest",
            "csv_column_count_checker",
        }
        for path, allowed in [(SRC, allowed_src),
                              (Path(__file__), allowed_tests)]:
            tree = ast.parse(path.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported.add(node.module.split(".")[0])
            self.assertTrue(imported <= allowed,
                            f"{path.name} imports non-stdlib: "
                            f"{imported - allowed}")
            self.assertNotIn("yaml", imported)

    def test_no_yaml_anywhere_in_source(self):
        text = SRC.read_text()
        self.assertNotIn("yaml", text)

    def test_no_secrets_in_repo(self):
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(errors="replace").lower()
            for marker in ["api_key", "api-key", "password =", "secret ="]:
                self.assertNotIn(marker, text,
                                 f"possible secret in {path.relative_to(ROOT)}")


if __name__ == "__main__":
    unittest.main()
