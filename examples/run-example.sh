#!/bin/sh
# Run the checker on the bundled examples and show the report.
# The checker exits 1 because the examples contain files with
# ragged rows; that is the point of the examples, so this script exits 0.
cd "$(dirname "$0")/.." || exit 2
python3 src/csv_column_count_checker.py examples || true
