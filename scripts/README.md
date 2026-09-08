# Problem index generation

The index is specific to the supplied Korean Halliday 11th-edition PDFs.
PDFs stay local; only crop coordinates and validation metadata are published.
OCR runs offline during index generation, not in the web app.

Requirements: Windows Korean OCR, Python with Pillow and NumPy, and Poppler.
Run from the repository root:

```powershell
python -B scripts/rebuild-index.py --book1 <volume-1.pdf> --book2 <volume-2.pdf> --pdftoppm <pdftoppm.exe>
```

The default output is `tmp/pdfs/verified-problem-index.json`. All 44 chapters
must pass before this file is written. Inspect representative final crops
before replacing `public/problem-index.json`, then run:

```powershell
python -B scripts/test-problem-index.py
pnpm run build
```

Page images, OCR output, candidate positions and selected positions are cached
under `tmp/pdfs/verified-index`. These ignored checkpoints allow failed chapters
to be reviewed without repeating OCR. Use a new scratch directory if changing
the source PDFs, render resolution or OCR engine.

Validation rejects missing, shifted, unconfirmed or duplicate numbers and empty
crops. Eight OCR corrections in `REVIEWED_NUMBERS` were visually checked against
the original scans; each is bound to a chapter, page, column and position.
`audit-index.py` produces a contact sheet of unconfirmed selected starts.

The generator also removes small running headers from page-top continuations,
links figures mentioned in the problem text, and handles visually reviewed
full-width floating tables that do not follow the normal two-column reading
order. `test-problem-index.py` contains regressions for these layout cases.

For an exact chapter-level boundary review, render every final problem crop into
numbered contact sheets and compare consecutive cards with the source pages:

```powershell
python -B scripts/render-chapter-review.py 2 24 `
  --pages-dir tmp/pdfs/verified-index/book-2-chapter-24 `
  --output-dir tmp/pdfs/verified-index/chapter-24-review
```

The review renderer includes both the main problem segments and any separately
attached figure segments. Its output stays under the ignored `tmp` directory.

`generate-problem-index.py --chapters ...` supports selective regeneration while
retaining the full book's chapter boundaries. It requires an existing output
index to avoid publishing an accidentally incomplete catalog.
