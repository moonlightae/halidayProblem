"""Produce a visual review sheet of every unconfirmed problem start."""
import json
from pathlib import Path
from PIL import Image, ImageDraw

scratch = Path('tmp/pdfs/verified-index')
items = []
for path in sorted(scratch.glob('*/selected.json')):
    chapter = int(path.parent.name.split('-')[-1])
    for start in json.loads(path.read_text()):
        if start.get('ocrNumber') == start['numbers'][0]:
            continue
        items.append((chapter, path.parent, start))
for batch in range(0, len(items), 24):
    sheet = Image.new('RGB', (1100, 24 * 78), 'white')
    draw = ImageDraw.Draw(sheet)
    for row, (chapter, folder, start) in enumerate(items[batch:batch + 24]):
        with Image.open(folder / f"page-{start['page']}.png") as page:
            w, h = page.size
            x = .045 if start['column'] == 'left' else .49
            y = max(0, start['y'] - .002)
            crop = page.crop((int(x*w), int(y*h), int((x+.46)*w), int((y+.041)*h)))
            crop = crop.resize((800, 67))
            sheet.paste(crop, (280, row*78))
        draw.text((4, row*78+10), f"ch{chapter} #{start['numbers']} OCR={start.get('ocrNumber')} p{start['page']}", fill='black')
    sheet.save(scratch / f'review-{batch//24}.png')
print('Unconfirmed:', len(items))
for chapter, folder, start in items:
    print(chapter, start['numbers'], start.get('ocrNumber'), start['page'], start['column'], round(start['y'],5))
