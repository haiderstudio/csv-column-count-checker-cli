# csv-column-count-checker-cli

Check every CSV row has the same column count, fail CI on a ragged row.

[![CI](https://github.com/haiderstudio/csv-column-count-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/csv-column-count-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`csv_column_count_checker` reads a CSV file and compares every
row's column count against the header (the first row). Each ragged
row — too few columns or too many — is reported with the file,
the line number, the expected count and the actual count. It
exits 1 when any ragged row is found, so it can fail a CI run.
A clean file exits 0.

- A ragged CSV breaks imports: pandas errors out, or columns
  shift silently and the wrong values land in the wrong fields.
  This tool catches the bad row before the file ships, and
  points at its exact line.
- Every ragged row is reported, not just the first: a file with
  three bad rows reports all three.
- Quoted fields are counted the way Python's `csv` module
  parses them, so a comma inside quotes is part of one field,
  not a new column. `"Carol, Jr."` is one column, not two.
- Blank lines are skipped, and line numbers are the real
  physical lines — a blank line in the middle does not shift
  the numbers that follow. A field that spans several lines
  inside quotes is reported at the line where it ends.
- A file with only a header passes. A file with no header row
  at all (empty, or only blank lines) is reported as a problem.
- A file given directly on the command line is always checked,
  whatever its name. A folder is walked for `*.csv` files,
  recursively by default (`--no-recursive` stops at the top
  level). `.git` folders are never walked, and directory links
  are never followed. `--exclude` skips files and folders by
  name pattern.
- `--delimiter` checks files that use another separator, such
  as `;`. `--json` prints the result as JSON (the human-readable
  lines go to standard error), and `--stdin` checks one CSV
  file read from standard input.

## Who it is for

Anyone who ships CSV data files — data engineers, analysts,
developers who import CSVs into a database or a spreadsheet,
and anyone who has ever watched an import fail on row 4,000
with no clue which row was wrong.

## What it does NOT do

- It does not check the header itself — that is repo #40's
  csv-header-checker-cli. A header can be wrong and still
  have every data row match it; a header can be right and
  still have a ragged data row. Header shape and row shape
  are two different checks.
- It does not compare two files — that is repo #35's
  csv-diff-cli. This checks one file's shape.
- It does not check data types, value ranges, or duplicate
  rows. It checks one thing: does every row have the same
  number of columns as the header?
- It does not convert or rewrite anything. It is report-only,
  and it never touches the network.

## How this differs

- Clever/csvlint (209 stars) is a Go linter for the whole of
  RFC 4180 — quote errors, syntax, and column counts all in
  one tool, installed as a downloaded binary. Column count
  is one check among many there, and it reports only "wrong
  number of fields in line", with no expected or actual count.
  This tool does one job only — column count — in plain
  Python with nothing to install, and reports the expected
  and actual count for every bad row, with a folder walk and
  JSON output.
- Data-Liberation-Front/csvlint.rb (286 stars) is a Ruby gem
  that validates CSVs against schemas, dialects, and web
  standards — a full validation suite that needs Ruby. This
  tool is the narrow CI gate: one check, stdlib only.
- There is no exact-name rival: a GitHub search for
  `"csv-column-count-checker-cli"` returns 0 results, and
  so does `"csv column count checker"` (checked Nov 8, 2026).

## Install

Python 3.10 or newer, nothing else to install.

```sh
git clone https://github.com/haiderstudio/csv-column-count-checker-cli.git
cd csv-column-count-checker-cli
```

## Usage

Check one clean file:

```sh
python3 src/csv_column_count_checker.py examples/good.csv
```

```text
OK — 1 file(s) checked, every row has the same column count.
```

Check a file with ragged rows:

```sh
python3 src/csv_column_count_checker.py examples/ragged.csv
```

```text
examples/ragged.csv:3: row has 2 columns, header has 3
examples/ragged.csv:4: row has 4 columns, header has 3
examples/ragged.csv:6: row has 2 columns, header has 3
Checked 1 file(s), 3 problem(s) in 1 file(s).
```

The exit code is 1, so a CI run fails.

Check a whole folder:

```sh
python3 src/csv_column_count_checker.py examples
```

```text
examples/ragged.csv:3: row has 2 columns, header has 3
examples/ragged.csv:4: row has 4 columns, header has 3
examples/ragged.csv:6: row has 2 columns, header has 3
examples/configs/more.csv:2: row has 3 columns, header has 2
Checked 4 file(s), 4 problem(s) in 2 file(s).
```

Check a file that uses semicolons:

```sh
python3 src/csv_column_count_checker.py semi.csv --delimiter ';'
```

```text
semi.csv:3: row has 2 columns, header has 3
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

Check one file from standard input:

```sh
printf 'a,b,c\n1,2\n' | python3 src/csv_column_count_checker.py --stdin
```

```text
<stdin>:2: row has 2 columns, header has 3
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

Machine-readable output:

```sh
python3 src/csv_column_count_checker.py examples/configs/more.csv --json
```

```json
{
  "files_checked": 1,
  "problems": [
    {
      "file": "examples/configs/more.csv",
      "line": 2,
      "reason": "row has 3 columns, header has 2"
    }
  ],
  "files_with_problems": 1
}
```

## Examples

- `examples/good.csv` — a clean file, including a quoted
  field with a comma inside it. Passes.
- `examples/ragged.csv` — three problems in one file: a short
  row, a long row, and another short row, with a quoted-comma
  row between them that passes. Fails with exit 1.
- `examples/header-only.csv` — a header and nothing else.
  Passes.
- `examples/configs/more.csv` — one long row, in a subfolder.
  Fails with exit 1.
- `sh examples/run-example.sh` runs the checker on the whole
  `examples/` folder. Its output is in
  `examples/sample-output.md`.

## How it is tested

```sh
python3 tests/test_csv_column_count_checker.py
```

The tests cover: every ragged shape with exact line numbers
and expected/actual counts (short row, long row, several bad
rows, single-column files), quoted fields (a comma inside
quotes is one field, and a ragged row is still caught),
blank lines skipped with real line numbers, multi-line
quoted fields, header-only files passing, empty files
flagged, CRLF endings, custom delimiters, non-UTF-8 and
null-byte files, folder walking (`.csv` only, `.git`
skipped, `--no-recursive`, `--exclude`, dedupe),
`--stdin`, `--json`, exit codes 0/1/2, input files left
unchanged, and the bundled examples (the sample output is
compared byte-for-byte against a fresh run, and the outputs
quoted in this README are checked against real runs).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. Counting
fields per row is done with Python's standard `csv` module.
The idea of linting a CSV file is a common one; the code,
the wording, and the tests are original.
