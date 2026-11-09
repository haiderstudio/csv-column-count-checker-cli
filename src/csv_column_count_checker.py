"""csv-column-count-checker-cli: check every row in a CSV file has the same number of columns as the header, fail CI on a ragged row.

Reads one or more CSV files (or folders of them), compares each row's
column count against the header (the first row), and reports every
ragged row with the file, the line number, the expected count and the
actual count. Report-only: it never rewrites a file. Exit 0 when
every file is clean, 1 when any ragged row is found, 2 for a usage
error.

Quoted fields are counted the way the csv module parses them, so a
comma inside quotes is part of one field, not a new column. Blank
lines are skipped. A file with only a header passes.
"""

import argparse
import csv
import fnmatch
import io
import json
import os
import sys
from pathlib import Path

__version__ = "1.0.0"


class Problem:
    """One problem in one file: path, line number, plain reason."""

    def __init__(self, path, line, reason):
        self.path = path
        self.line = line
        self.reason = reason

    def text(self):
        return f"{self.path}:{self.line}: {self.reason}"

    def as_dict(self):
        return {"file": self.path, "line": self.line, "reason": self.reason}


def check_text(text, path, delimiter=","):
    """Check one CSV document given as text. Returns a list of Problems."""
    problems = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "\x00" in line:
            problems.append(Problem(
                path,
                lineno,
                "cannot parse CSV: line contains NUL",
            ))
    reader = csv.reader(io.StringIO(text, newline=""),
                        delimiter=delimiter, strict=True)
    expected = None
    try:
        for row in reader:
            if row == []:
                continue
            if expected is None:
                expected = len(row)
                continue
            if len(row) != expected:
                problems.append(Problem(
                    path,
                    reader.line_num,
                    f"row has {len(row)} columns, header has {expected}",
                ))
    except csv.Error as exc:
        problems.append(Problem(
            path,
            reader.line_num,
            f"cannot parse CSV: {exc}",
        ))
    if expected is None:
        problems.append(Problem(path, 1, "no header row found"))
    return problems


def check_file(path, delimiter=","):
    """Check one CSV file on disk. Returns a list of Problems."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        return [Problem(path, 1, f"cannot be read: {exc.strerror or exc}")]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [Problem(path, 1, "cannot be read as UTF-8")]
    return check_text(text, path, delimiter=delimiter)


def collect_files(paths, recursive=True, exclude=()):
    """Turn command-line paths into a deduplicated list of CSV files.

    A file given directly is always checked, whatever its name. A
    folder is walked for *.csv files. .git folders are never walked,
    directory links are never followed.
    """
    found = []
    seen = set()
    for given in paths:
        if os.path.isfile(given):
            key = os.path.abspath(given)
            if key not in seen:
                seen.add(key)
                found.append(given)
            continue
        if os.path.isdir(given):
            for dirpath, dirnames, filenames in os.walk(given):
                if not recursive:
                    dirnames[:] = []
                dirnames[:] = [
                    d for d in dirnames
                    if d != ".git"
                    and not os.path.islink(os.path.join(dirpath, d))
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in sorted(filenames):
                    if not name.lower().endswith(".csv"):
                        continue
                    if any(fnmatch.fnmatch(name, pat) for pat in exclude):
                        continue
                    full = os.path.join(dirpath, name)
                    key = os.path.abspath(full)
                    if key not in seen:
                        seen.add(key)
                        found.append(full)
            continue
        return None, given
    return found, None


def run(argv=None):
    """Run the checker. Returns the exit code."""
    parser = argparse.ArgumentParser(
        prog="csv_column_count_checker",
        description="Check every row in a CSV file has the same number "
                    "of columns as the header.",
    )
    parser.add_argument("paths", nargs="*", help="CSV files or folders")
    parser.add_argument("--delimiter", default=",",
                        help="field delimiter (default: ',')")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files and folders matching this pattern "
                             "(may be repeated)")
    parser.add_argument("--stdin", action="store_true",
                        help="check one CSV file read from standard input")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    if len(args.delimiter) != 1:
        print("error: --delimiter must be one character",
              file=sys.stderr)
        return 2
    if args.stdin and args.paths:
        print("error: --stdin takes no file arguments", file=sys.stderr)
        return 2
    if not args.stdin and not args.paths:
        print("error: give a CSV file, a folder, or --stdin",
              file=sys.stderr)
        return 2

    if args.stdin:
        problems = check_text(sys.stdin.read(), "<stdin>",
                              delimiter=args.delimiter)
        files_checked = 1
    else:
        files, missing = collect_files(
            args.paths,
            recursive=not args.no_recursive,
            exclude=args.exclude,
        )
        if missing is not None:
            print(f"error: no such file or folder: {missing}",
                  file=sys.stderr)
            return 2
        files_checked = len(files)
        problems = []
        for path in files:
            problems.extend(check_file(path, delimiter=args.delimiter))

    files_with_problems = len({p.path for p in problems})

    if args.json:
        result = {
            "files_checked": files_checked,
            "problems": [p.as_dict() for p in problems],
            "files_with_problems": files_with_problems,
        }
        print(json.dumps(result, indent=2))
        for problem in problems:
            print(problem.text(), file=sys.stderr)
    else:
        for problem in problems:
            print(problem.text())
        if problems:
            print(f"Checked {files_checked} file(s), "
                  f"{len(problems)} problem(s) in "
                  f"{files_with_problems} file(s).")
        else:
            print(f"OK — {files_checked} file(s) checked, every row "
                  f"has the same column count.")
    return 1 if problems else 0


def main():
    sys.exit(run())


if __name__ == "__main__":
    main()
