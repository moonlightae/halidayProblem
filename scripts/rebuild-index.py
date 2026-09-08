"""Resume every chapter independently, preserving failures for inspection."""
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location('generator', Path(__file__).with_name('generate-problem-index.py'))
g = importlib.util.module_from_spec(spec)
sys.modules['generator'] = g
spec.loader.exec_module(g)

if __name__ == '__main__':
    parser = g.argparse.ArgumentParser()
    parser.add_argument('--book1', type=Path, required=True)
    parser.add_argument('--book2', type=Path, required=True)
    parser.add_argument('--pdftoppm', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, default=Path('tmp/pdfs/verified-index'))
    parser.add_argument('--output', type=Path, default=Path('tmp/pdfs/verified-problem-index.json'))
    args = parser.parse_args()
    errors = {}
    books = {}
    for book_id in ('1', '2'):
        books[book_id] = {'label': g.BOOKS[book_id]['label'], 'fileHint': g.BOOKS[book_id]['file_hint'],
                          'pageCount': g.BOOKS[book_id]['page_count'], 'chapters': {}}
        for chapter in g.BOOKS[book_id]['chapters']:
            try:
                generated = g.generate_book(book_id, getattr(args, 'book' + book_id), args.pdftoppm,
                                            args.scratch, Path('scripts/windows-ocr.ps1'), {chapter.number})
                books[book_id]['chapters'].update(generated['chapters'])
            except Exception as error:
                errors[str(chapter.number)] = str(error)
                print(f'REVIEW chapter {chapter.number}: {error}', flush=True)
    (args.scratch / 'errors.json').write_text(json.dumps(errors, indent=2), encoding='utf-8')
    print('Review required:', errors, flush=True)
    if errors:
        raise SystemExit(1)
    if sum(len(book['chapters']) for book in books.values()) != 44:
        raise ValueError('A complete index must contain all 44 chapters')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'version': 5, 'pdfPageOffset': g.PDF_OFFSET, 'books': books},
                                     ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'Wrote verified index: {args.output}', flush=True)
