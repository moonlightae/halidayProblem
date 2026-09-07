from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


PDF_OFFSET = 10
RENDER_DPI = 120


@dataclass(frozen=True)
class ChapterSpec:
    number: int
    title: str
    start: int
    exercises: int


BOOKS = {
    "1": {
        "label": "일반물리학 I",
        "file_hint": "할리데이 일반물리학1 11판.pdf",
        "page_count": 592,
        "final_exercise_page": 552,
        "chapters": [
            ChapterSpec(1, "측정", 1, 9),
            ChapterSpec(2, "직선운동", 13, 33),
            ChapterSpec(3, "벡터", 39, 55),
            ChapterSpec(4, "2차원 운동과 3차원 운동", 59, 79),
            ChapterSpec(5, "힘과 운동-I", 85, 106),
            ChapterSpec(6, "힘과 운동-II", 111, 126),
            ChapterSpec(7, "운동에너지와 일", 133, 154),
            ChapterSpec(8, "퍼텐셜에너지와 에너지 보존", 159, 183),
            ChapterSpec(9, "질량중심과 선운동량", 191, 222),
            ChapterSpec(10, "회전", 227, 257),
            ChapterSpec(11, "굴림운동, 토크, 각운동량", 263, 289),
            ChapterSpec(12, "평형과 탄성", 295, 312),
            ChapterSpec(13, "중력", 319, 343),
            ChapterSpec(14, "유체", 349, 369),
            ChapterSpec(15, "진동", 373, 395),
            ChapterSpec(16, "파동-I", 401, 428),
            ChapterSpec(17, "파동-II", 433, 459),
            ChapterSpec(18, "온도, 열, 열역학 제1법칙", 465, 490),
            ChapterSpec(19, "기체운동론", 495, 524),
            ChapterSpec(20, "엔트로피와 열역학 제2법칙", 529, 549),
        ],
    },
    "2": {
        "label": "일반물리학 II",
        "file_hint": "할리데이 일반물리학2 11판.pdf",
        "page_count": 750,
        "final_exercise_page": 722,
        "chapters": [
            ChapterSpec(21, "Coulomb의 법칙", 1, 16),
            ChapterSpec(22, "전기장", 21, 43),
            ChapterSpec(23, "Gauss의 법칙", 49, 69),
            ChapterSpec(24, "전기퍼텐셜", 75, 99),
            ChapterSpec(25, "전기용량", 105, 127),
            ChapterSpec(26, "전류와 저항", 131, 150),
            ChapterSpec(27, "회로이론", 155, 177),
            ChapterSpec(28, "자기장", 183, 208),
            ChapterSpec(29, "전류가 만드는 자기장", 213, 232),
            ChapterSpec(30, "유도와 유도용량", 237, 268),
            ChapterSpec(31, "전자기적 진동과 교류", 273, 305),
            ChapterSpec(32, "Maxwell 방정식, 물질의 자성", 309, 334),
            ChapterSpec(33, "전자기파", 339, 367),
            ChapterSpec(34, "영상", 373, 399),
            ChapterSpec(35, "간섭", 407, 431),
            ChapterSpec(36, "회절", 437, 463),
            ChapterSpec(37, "상대론", 467, 497),
            ChapterSpec(38, "광자와 물질파", 503, 531),
            ChapterSpec(39, "물질파 더 알아보기", 535, 564),
            ChapterSpec(40, "원자의 모든 것", 569, 597),
            ChapterSpec(41, "고체의 전기적 성질", 603, 625),
            ChapterSpec(42, "핵물리", 629, 655),
            ChapterSpec(43, "핵 에너지", 661, 682),
            ChapterSpec(44, "쿼크, 경입자, 그리고 빅뱅", 687, 716),
        ],
    },
}


def is_problem_color(pixel: tuple[int, int, int]) -> bool:
    red, green, blue = pixel
    return (
        red >= 105
        and green >= 24
        and red - green >= 20
        and red - blue >= 32
        and red >= int(green * 1.18)
    )


def group_rows(rows: list[int], max_gap: int = 3) -> list[list[int]]:
    groups: list[list[int]] = []
    for row in rows:
        if not groups or row - groups[-1][-1] > max_gap:
            groups.append([row])
        else:
            groups[-1].append(row)
    return groups


def find_exercise_top(image: Image.Image) -> int:
    width, height = image.size
    candidates: list[int] = []
    for y in range(int(height * 0.05), int(height * 0.9)):
        xs = [
            x
            for x in range(int(width * 0.035), int(width * 0.27))
            if is_problem_color(image.getpixel((x, y)))
        ]
        if len(xs) >= 12 and max(xs) - min(xs) >= 35:
            candidates.append(y)
    groups = group_rows(candidates, 4)
    if not groups:
        return int(height * 0.065)
    group = max(groups, key=lambda item: len(item))
    return max(int(height * 0.06), group[0] - 4)


def find_problem_starts(image: Image.Image, first_page: bool) -> tuple[int, list[dict]]:
    width, height = image.size
    content_top = find_exercise_top(image) if first_page else int(height * 0.065)
    starts: list[dict] = []
    zones = {
        "left": (int(width * 0.05), int(width * 0.105)),
        "right": (int(width * 0.495), int(width * 0.55)),
    }

    for column, (x0, x1) in zones.items():
        qualifying_rows: list[int] = []
        row_pixels: dict[int, list[int]] = {}
        for y in range(content_top + 12, int(height * 0.965)):
            xs = [x for x in range(x0, x1) if is_problem_color(image.getpixel((x, y)))]
            if len(xs) >= 2:
                qualifying_rows.append(y)
                row_pixels[y] = xs

        for rows in group_rows(qualifying_rows, 2):
            pixels = [(x, y) for y in rows for x in row_pixels[y]]
            min_x = min(x for x, _ in pixels)
            max_x = max(x for x, _ in pixels)
            min_y = min(rows)
            max_y = max(rows)
            pixel_count = len(pixels)
            band_height = max_y - min_y + 1
            band_width = max_x - min_x + 1
            if not (5 <= band_height <= 23 and 3 <= band_width <= 28 and 9 <= pixel_count <= 155):
                continue

            text_x0 = x1
            text_x1 = int(width * (0.47 if column == "left" else 0.95))
            dark_ink = 0
            for y in range(max(content_top, min_y - 3), min(height, max_y + 5)):
                for x in range(text_x0, text_x1):
                    red, green, blue = image.getpixel((x, y))
                    if red + green + blue < 500 and max(red, green, blue) - min(red, green, blue) < 90:
                        dark_ink += 1
            if dark_ink < 20:
                continue

            starts.append(
                {
                    "column": column,
                    "y": max(content_top, min_y - 7) / height,
                    "detectedY": min_y,
                }
            )

    starts.sort(key=lambda item: (0 if item["column"] == "left" else 1, item["y"]))
    return content_top, starts


def render_page(pdftoppm: Path, pdf: Path, page: int, output_prefix: Path) -> Path:
    subprocess.run(
        [
            str(pdftoppm),
            "-f",
            str(page),
            "-singlefile",
            "-r",
            str(RENDER_DPI),
            "-png",
            str(pdf),
            str(output_prefix),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return output_prefix.with_suffix(".png")


def build_segments(blocks: list[dict], starts: list[dict]) -> dict[str, dict]:
    problems: dict[str, dict] = {}
    for index, start in enumerate(starts):
        next_start = starts[index + 1] if index + 1 < len(starts) else None
        start_block = start["block"]
        end_block = next_start["block"] if next_start else len(blocks) - 1
        segments: list[dict] = []

        for block_index in range(start_block, end_block + 1):
            block = blocks[block_index]
            y0 = start["y"] if block_index == start_block else block["top"]
            y1 = next_start["y"] - 0.006 if next_start and block_index == end_block else block["bottom"]
            if y1 - y0 < 0.018:
                continue
            x = 0.052 if block["column"] == "left" else 0.497
            width = 0.445 if block["column"] == "left" else 0.452
            segments.append(
                {
                    "page": block["page"],
                    "x": round(x, 5),
                    "y": round(max(0, y0), 5),
                    "width": round(width, 5),
                    "height": round(min(0.972, y1) - max(0, y0), 5),
                }
            )

        problems[str(index + 1)] = {"segments": segments}
    return problems


def generate_book(book_id: str, pdf: Path, pdftoppm: Path, scratch: Path) -> dict:
    spec = BOOKS[book_id]
    chapters_out: dict[str, dict] = {}
    chapter_specs: list[ChapterSpec] = spec["chapters"]

    for chapter_index, chapter in enumerate(chapter_specs):
        exercise_end = (
            chapter_specs[chapter_index + 1].start - 1
            if chapter_index + 1 < len(chapter_specs)
            else spec["final_exercise_page"]
        )
        pdf_start = chapter.exercises + PDF_OFFSET
        pdf_end = exercise_end + PDF_OFFSET
        blocks: list[dict] = []
        starts: list[dict] = []
        diagnostics: list[dict] = []

        for pdf_page in range(pdf_start, pdf_end + 1):
            prefix = scratch / f"book-{book_id}-chapter-{chapter.number}-page-{pdf_page}"
            rendered = render_page(pdftoppm, pdf, pdf_page, prefix)
            with Image.open(rendered).convert("RGB") as image:
                content_top_px, page_starts = find_problem_starts(image, pdf_page == pdf_start)
                _, height = image.size
            rendered.unlink(missing_ok=True)

            for column in ("left", "right"):
                blocks.append(
                    {
                        "page": pdf_page,
                        "column": column,
                        "top": content_top_px / height,
                        "bottom": 0.966,
                    }
                )
                block_index = len(blocks) - 1
                for item in page_starts:
                    if item["column"] == column:
                        starts.append({**item, "block": block_index, "page": pdf_page})

            diagnostics.append(
                {
                    "page": pdf_page,
                    "left": sum(item["column"] == "left" for item in page_starts),
                    "right": sum(item["column"] == "right" for item in page_starts),
                }
            )

        problems = build_segments(blocks, starts)
        if not problems:
            raise RuntimeError(f"No problems detected for chapter {chapter.number}")
        chapters_out[str(chapter.number)] = {
            "title": chapter.title,
            "exercisePrintedPage": chapter.exercises,
            "problemCount": len(problems),
            "problems": problems,
            "diagnostics": diagnostics,
        }
        print(f"chapter {chapter.number}: {len(problems)} problems")

    return {
        "label": spec["label"],
        "fileHint": spec["file_hint"],
        "pageCount": spec["page_count"],
        "chapters": chapters_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Halliday exercise crop index")
    parser.add_argument("--book1", type=Path, required=True)
    parser.add_argument("--book2", type=Path, required=True)
    parser.add_argument("--pdftoppm", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("public/problem-index.json"))
    parser.add_argument("--scratch", type=Path, default=Path("tmp/pdfs/indexer"))
    args = parser.parse_args()

    args.scratch.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        books = {
            "1": generate_book("1", args.book1, args.pdftoppm, args.scratch),
            "2": generate_book("2", args.book2, args.pdftoppm, args.scratch),
        }
        payload = {"version": 1, "pdfPageOffset": PDF_OFFSET, "books": books}
        args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"wrote {args.output}")
    finally:
        shutil.rmtree(args.scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
