"""Add complete Review & Summary crop ranges to the published problem index."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image


GENERATOR_PATH = Path(__file__).with_name("generate-problem-index.py")
SPEC = importlib.util.spec_from_file_location("problem_index_generator", GENERATOR_PATH)
generator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generator
SPEC.loader.exec_module(generator)


def normalized(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", text).lower()


def is_review_heading(text: str) -> bool:
    value = normalized(text)
    return (
        "정리및요약" in value
        or "리및요약" in value
        or ("요약" in value and ("review" in value or "revjew" in value or "rewew" in value))
        or ("review" in value and "summary" in value)
    )


def find_review_start(pages: list[dict]) -> tuple[int, float, str]:
    matches: list[tuple[int, float, str]] = []
    for page in pages:
        page_number = int(Path(page["path"]).stem.split("-")[-1])
        for line in page.get("lines", []):
            if not is_review_heading(line.get("text", "")):
                continue
            words = line.get("words", [])
            if not words:
                continue
            # Continued review pages repeat a small "정리 및 요약" running
            # header near the page edge. The actual section heading is larger.
            if max(float(word["height"]) for word in words) < 15:
                continue
            y = min(float(word["y"]) for word in words) / float(page["height"])
            matches.append((page_number, max(0.03, y - 0.022), line["text"]))
    if not matches:
        raise ValueError("Review & Summary heading was not found by OCR")
    return min(matches, key=lambda item: (item[0], item[1]))


def build_review_segments(
    start_page: int,
    start_y: float,
    exercise_page: int,
    exercise_y: float,
) -> list[dict]:
    if start_page > exercise_page:
        raise ValueError("Review starts after the exercise page")
    segments: list[dict] = []
    for page in range(start_page, exercise_page + 1):
        top = start_y if page == start_page else 0.035
        bottom = exercise_y if page == exercise_page else 0.975
        if bottom - top < 0.025:
            continue
        segments.append(
            {
                "page": page,
                "x": 0.0,
                "y": round(top, 5),
                "width": 1.0,
                "height": round(bottom - top, 5),
            }
        )
    if not segments:
        raise ValueError("Review range is empty")
    return segments


def page_key(path: str | Path) -> str:
    return str(Path(path).resolve()).casefold()


def run_ocr(
    images: list[Path],
    scratch: Path,
    ocr_script: Path,
    reuse: bool,
) -> dict[str, dict]:
    input_list = scratch / "ocr-images.txt"
    output = scratch / "ocr.json"
    input_list.write_text("\n".join(str(path.resolve()) for path in images), encoding="utf-8")
    if not (reuse and output.exists()):
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ocr_script.resolve()),
                "-InputList",
                str(input_list.resolve()),
                "-Output",
                str(output.resolve()),
            ],
            check=True,
        )
    payload = json.loads(output.read_text(encoding="utf-8-sig"))
    return {page_key(page["path"]): page for page in payload["pages"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate complete chapter review crop ranges")
    parser.add_argument("--book1", type=Path, required=True)
    parser.add_argument("--book2", type=Path, required=True)
    parser.add_argument("--pdftoppm", type=Path, required=True)
    parser.add_argument("--index", type=Path, default=Path("public/problem-index.json"))
    parser.add_argument("--scratch", type=Path, default=Path("tmp/pdfs/review-ranges"))
    parser.add_argument("--lookback", type=int, default=6)
    parser.add_argument("--reuse-ocr", action="store_true")
    parser.add_argument("--chapters", type=int, nargs="+")
    parser.add_argument("--ocr-script", type=Path, default=Path("scripts/windows-ocr.ps1"))
    args = parser.parse_args()

    data = json.loads(args.index.read_text(encoding="utf-8"))
    selected_chapters = set(args.chapters or [])
    pdfs = {"1": args.book1, "2": args.book2}
    args.scratch.mkdir(parents=True, exist_ok=True)

    rendered: dict[tuple[str, int], Path] = {}
    ordered_images: list[Path] = []
    for book_id, book in data["books"].items():
        book_scratch = args.scratch / f"book-{book_id}"
        book_scratch.mkdir(parents=True, exist_ok=True)
        required_pages: set[int] = set()
        for chapter_number, chapter in book["chapters"].items():
            if selected_chapters and int(chapter_number) not in selected_chapters:
                continue
            exercise_page = int(chapter["exercisePrintedPage"]) + int(data["pdfPageOffset"])
            required_pages.update(range(max(1, exercise_page - args.lookback), exercise_page + 1))
        for page in sorted(required_pages):
            output_prefix = book_scratch / f"page-{page}"
            cached_image = output_prefix.with_suffix(".png")
            image = (
                cached_image
                if args.reuse_ocr and cached_image.exists()
                else generator.render_page(args.pdftoppm, pdfs[book_id], page, output_prefix)
            )
            rendered[(book_id, page)] = image
            ordered_images.append(image)

    ocr_pages = run_ocr(ordered_images, args.scratch, args.ocr_script, args.reuse_ocr)

    for book_id, book in data["books"].items():
        for chapter_number, chapter in book["chapters"].items():
            if selected_chapters and int(chapter_number) not in selected_chapters:
                continue
            exercise_page = int(chapter["exercisePrintedPage"]) + int(data["pdfPageOffset"])
            candidates = []
            for page in range(max(1, exercise_page - args.lookback), exercise_page + 1):
                image = rendered[(book_id, page)]
                candidates.append(ocr_pages[page_key(image)])
            start_page, start_y, _heading = find_review_start(candidates)
            exercise_image = Image.open(rendered[(book_id, exercise_page)]).convert("RGB")
            first_problem = chapter["problems"]["1"]["segments"][0]
            if int(first_problem["page"]) != exercise_page:
                raise ValueError(f"Chapter {chapter_number}: first problem is not on exercise page")
            exercise_y = generator.find_exercise_top(
                exercise_image,
                float(first_problem["y"]),
            ) / exercise_image.height
            exercise_image.close()
            segments = build_review_segments(start_page, start_y, exercise_page, exercise_y)
            chapter["reviewSegments"] = segments
            print(
                f"chapter {chapter_number}: {start_page}:{start_y:.3f} -> "
                f"{exercise_page}:{exercise_y:.3f} ({len(segments)} segments)",
                flush=True,
            )

    data["version"] = 6
    args.index.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"wrote {args.index}")


if __name__ == "__main__":
    main()
