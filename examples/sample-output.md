```text
examples/ragged.csv:3: row has 2 columns, header has 3
examples/ragged.csv:4: row has 4 columns, header has 3
examples/ragged.csv:6: row has 2 columns, header has 3
examples/configs/more.csv:2: row has 3 columns, header has 2
Checked 4 file(s), 4 problem(s) in 2 file(s).
```

Output of `sh examples/run-example.sh` — the checker on the whole
`examples/` folder. It exits 1, because the examples contain files
with ragged rows on purpose; the script itself exits 0.
