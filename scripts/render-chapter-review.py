"""Render numbered contact sheets for visual crop-boundary review."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('book', choices=('1', '2'))
    parser.add_argument('chapter', type=int)
    parser.add_argument('--group-size', type=int, default=8)
    parser.add_argument('--pages-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()

    data = json.loads(Path('public/problem-index.json').read_text(encoding='utf-8'))
    chapter = data['books'][args.book]['chapters'][str(args.chapter)]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for first in range(1, chapter['problemCount'] + 1, args.group_size):
        cards = []
        last = min(first + args.group_size, chapter['problemCount'] + 1)
        for number in range(first, last):
            problem = chapter['problems'][str(number)]
            pieces = []
            for segment in problem['segments'] + problem.get('figures', []):
                page_path = args.pages_dir / f"page-{segment['page']}.png"
                with Image.open(page_path) as page:
                    width, height = page.size
                    pieces.append(page.crop((
                        int(width * segment['x']),
                        int(height * segment['y']),
                        int(width * (segment['x'] + segment['width'])),
                        int(height * (segment['y'] + segment['height'])),
                    )).copy())

            card_width = max(piece.width for piece in pieces)
            card_height = 28 + sum(piece.height + 3 for piece in pieces)
            card = Image.new('RGB', (card_width, card_height), 'white')
            ImageDraw.Draw(card).text(
                (4, 4), f'CH {args.chapter} - PROBLEM {number}', fill=(0, 0, 0)
            )
            y = 28
            for piece in pieces:
                card.paste(piece, (0, y))
                y += piece.height + 3
            cards.append(card)

        sheet = Image.new(
            'RGB',
            (max(card.width for card in cards), sum(card.height + 12 for card in cards)),
            'white',
        )
        draw = ImageDraw.Draw(sheet)
        y = 0
        for card in cards:
            sheet.paste(card, (0, y))
            y += card.height
            draw.line((0, y + 4, sheet.width, y + 4), fill=(220, 40, 40), width=3)
            y += 12
        sheet.save(args.output_dir / f'{first:02d}-{last - 1:02d}.png')


if __name__ == '__main__':
    main()
