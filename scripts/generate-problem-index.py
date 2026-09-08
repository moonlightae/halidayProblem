from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
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

PROBLEM_COUNTS = {
    1: 32, 2: 66, 3: 44, 4: 68, 5: 61, 6: 66, 7: 55, 8: 82, 9: 61, 10: 60,
    11: 60, 12: 60, 13: 66, 14: 61, 15: 61, 16: 61, 17: 61, 18: 60, 19: 60, 20: 50,
    21: 51, 22: 60, 23: 60, 24: 61, 25: 60, 26: 55, 27: 61, 28: 60, 29: 60,
    30: 63, 31: 60, 32: 54, 33: 60, 34: 92, 35: 61, 36: 62, 37: 62, 38: 60,
    39: 56, 40: 58, 41: 53, 42: 61, 43: 58, 44: 54,
}

# Visually checked against the supplied Korean 11th-edition scans at 120 dpi.
# Match the page, column and position as well as the number, so a changed PDF
# cannot silently inherit a correction intended for a different location.
REVIEWED_NUMBERS = {
    10: [(270, 'right', .74807, 35)],
    23: [(82, 'left', .51742, 30), (83, 'left', .10926, 45)],
    27: [(189, 'left', .43939, 24)],
    30: [(280, 'left', .30705, 21)],
    38: [(542, 'right', .81591, 28), (543, 'right', .35909, 48)],
    42: [(667, 'right', .77845, 28)],
}

# Full-width floating tables whose physical page position does not follow the
# two-column reading order. Coordinates were visually checked against the
# supplied Korean 11th-edition scans.
REVIEWED_VISUALS = {
    34: [
        {"page": 409, "x": 0.195, "y": 0.765, "width": 0.59, "height": 0.168,
         "label": "표 34-3", "references": list(range(1, 7))},
        {"page": 410, "x": 0.195, "y": 0.638, "width": 0.59, "height": 0.152,
         "label": "표 34-4", "references": list(range(11, 16))},
        {"page": 410, "x": 0.195, "y": 0.797, "width": 0.59, "height": 0.148,
         "label": "표 34-5", "references": list(range(16, 21))},
        {"page": 411, "x": 0.195, "y": 0.608, "width": 0.59, "height": 0.201,
         "label": "표 34-6", "references": list(range(25, 34))},
        {"page": 411, "x": 0.195, "y": 0.817, "width": 0.59, "height": 0.13,
         "label": "표 34-7", "references": list(range(38, 42))},
    ],
}


def apply_reviewed_numbers(starts: list[dict], chapter: int) -> None:
    for page, column, y, number in REVIEWED_NUMBERS.get(chapter, []):
        matches = [start for start in starts if start['page'] == page
                   and start['column'] == column and abs(start['y'] - y) < .003]
        if len(matches) != 1:
            raise ValueError(f'Chapter {chapter}: reviewed number {number} needs reinspection')
        matches[0]['ocrNumber'] = number
        matches[0]['visuallyReviewed'] = True


def validate_chapter(starts: list[dict], problems: dict, expected_count: int) -> None:
    assigned = [number for start in starts for number in start['numbers']]
    if assigned != list(range(1, expected_count + 1)):
        raise ValueError('Missing, duplicate or out-of-order problem numbers')
    for start in starts:
        if start.get('ocrNumber') != start['numbers'][0]:
            raise ValueError(f"Unconfirmed printed number: {start}")
    for number, problem in problems.items():
        if not problem['segments']:
            raise ValueError(f'Problem {number} has an empty crop')
        for segment in problem['segments']:
            if not (0 <= segment['x'] < 1 and 0 <= segment['y'] < 1
                    and 0 < segment['width'] <= 1 and 0 < segment['height'] <= 1
                    and segment['x'] + segment['width'] <= 1.00001
                    and segment['y'] + segment['height'] <= 1.00001):
                raise ValueError(f'Invalid crop for problem {number}: {segment}')


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
    # The first wide orange band is the exercise heading. A later diagram
    # can contain a much larger orange area and must not move the page top.
    group = groups[0]
    return max(int(height * 0.06), group[0] - 4)


def find_problem_starts(image: Image.Image, first_page: bool) -> tuple[int, list[dict]]:
    width, height = image.size
    content_top = find_exercise_top(image) if first_page else int(height * 0.05)
    starts: list[dict] = []
    zones = {
        "left": (int(width * 0.05), int(width * 0.105)),
        "right": (int(width * 0.495), int(width * 0.55)),
    }

    for column, (x0, x1) in zones.items():
        qualifying_rows: list[int] = []
        row_pixels: dict[int, list[int]] = {}
        for y in range(content_top + 1, int(height * 0.965)):
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


def run_windows_ocr(images: list[Path], scratch: Path, ocr_script: Path) -> dict[str, dict]:
    def recognize(index_and_image: tuple[int, Path]) -> dict:
        index, image = index_and_image
        input_list = scratch / f"ocr-image-{index}.txt"
        output = scratch / f"ocr-result-{index}.json"
        input_list.write_text(str(image.resolve()), encoding="utf-8")
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
            stdout=subprocess.DEVNULL,
        )
        payload = json.loads(output.read_text(encoding="utf-8-sig"))
        return payload["pages"][0]

    worker_count = min(4, len(images))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        pages = list(executor.map(recognize, enumerate(images)))
    return {Path(page["path"]).name: page for page in pages}


def ocr_problem_starts(ocr_page: dict, content_top: float, image: Image.Image | None = None) -> list[dict]:
    width = ocr_page["width"]
    height = ocr_page["height"]
    starts: list[dict] = []
    zones = {"left": (0.04, 0.12), "right": (0.48, 0.56)}

    # OCR sometimes merges the two columns into one line, or joins a number
    # to the following word. Verify every margin word against its printed color.
    words = [word for line in ocr_page['lines'] for word in line.get('words', [])]
    for first in words:
        token = first["text"].strip()
        range_match = re.fullmatch(r"(\d{1,3})\s*[-–—~]\s*(\d{1,3})[.,]?", token)
        number_match = re.match(r"^(\d{1,3})(?!\d)", token)
        if not range_match and not number_match:
            continue
        x = first["x"] / width
        y = first["y"] / height
        if y < content_top:
            continue
        if image is not None:
            x0, y0 = int(first['x']), int(first['y'])
            x1 = min(width, x0 + max(10, min(int(first['width']), 28)))
            y1 = min(height, y0 + int(first['height']) + 1)
            colored = sum(is_problem_color(image.getpixel((px, py)))
                          for py in range(max(0, y0), y1)
                          for px in range(max(0, x0), x1))
            if colored < 4:
                continue
        for column, (x0, x1) in zones.items():
            if x0 <= x <= x1:
                start = {
                    "column": column,
                    "y": max(content_top, y - 0.006),
                    "ocrNumber": int((range_match or number_match).group(1)),
                }
                if range_match:
                    first_number = int(range_match.group(1))
                    last_number = int(range_match.group(2))
                    if first_number < last_number and last_number - first_number <= 30:
                        start["numberRange"] = [first_number, last_number]
                starts.append(start)
                break
    return starts


def merge_problem_starts(color_starts: list[dict], ocr_starts: list[dict]) -> list[dict]:
    combined: list[dict] = []
    used_ocr: set[int] = set()
    for color_start in color_starts:
        candidates = [
            (index, item)
            for index, item in enumerate(ocr_starts)
            if index not in used_ocr
            and item["column"] == color_start["column"]
            and abs(item["y"] - color_start["y"]) <= 0.012
        ]
        merged = dict(color_start)
        if candidates:
            index, nearest = min(candidates, key=lambda pair: abs(pair[1]["y"] - color_start["y"]))
            used_ocr.add(index)
            merged["ocrNumber"] = nearest["ocrNumber"]
            if "numberRange" in nearest:
                merged["numberRange"] = nearest["numberRange"]
        combined.append(merged)

    combined.extend(item for index, item in enumerate(ocr_starts) if index not in used_ocr)
    combined.sort(key=lambda item: (0 if item["column"] == "left" else 1, item["y"]))

    deduplicated: list[dict] = []
    for item in combined:
        if (
            deduplicated
            and deduplicated[-1]["column"] == item["column"]
            and item["y"] - deduplicated[-1]["y"] <= 0.008
        ):
            current = deduplicated[-1]
            if "numberRange" in item and "numberRange" not in current:
                deduplicated[-1] = item
            elif "ocrNumber" in item and "ocrNumber" not in current:
                deduplicated[-1] = item
            continue
        deduplicated.append(item)
    return deduplicated


def candidate_cost(start: dict, problem_number: int, expected_count: int) -> int:
    ocr_number = start.get("ocrNumber")
    if ocr_number == problem_number:
        return 0
    if ocr_number is None or not 1 <= ocr_number <= expected_count:
        return 2 if "detectedY" in start else 5
    return 12 + min(abs(ocr_number - problem_number), 20)


def resolve_problem_numbers(starts: list[dict], expected_count: int) -> list[dict]:
    candidate_count = len(starts)
    maximum_capacity = sum(
        item.get("numberRange", [0, 0])[1] - item.get("numberRange", [0, 0])[0] + 1
        if "numberRange" in item
        else 1
        for item in starts
    )
    if maximum_capacity < expected_count:
        raise RuntimeError(
            f"Only {maximum_capacity} problem numbers were found for {expected_count} expected problems"
        )

    infinity = 10**9
    costs = [[infinity] * (candidate_count + 1) for _ in range(expected_count + 1)]
    took = [[0] * (candidate_count + 1) for _ in range(expected_count + 1)]
    for candidate_index in range(candidate_count + 1):
        costs[0][candidate_index] = 0

    for problem_number in range(1, expected_count + 1):
        for candidate_index in range(1, candidate_count + 1):
            skip_cost = costs[problem_number][candidate_index - 1]
            start = starts[candidate_index - 1]
            number_range = start.get("numberRange")
            span = number_range[1] - number_range[0] + 1 if number_range else 1
            range_is_aligned = not number_range or number_range == [problem_number - span + 1, problem_number]
            take_cost = infinity
            if problem_number >= span and range_is_aligned:
                take_cost = costs[problem_number - span][candidate_index - 1]
                if number_range:
                    take_cost += 0
                else:
                    take_cost += candidate_cost(start, problem_number, expected_count)
            if take_cost < skip_cost:
                costs[problem_number][candidate_index] = take_cost
                took[problem_number][candidate_index] = span
            else:
                costs[problem_number][candidate_index] = skip_cost

    selected: list[dict] = []
    problem_number = expected_count
    candidate_index = candidate_count
    while problem_number > 0 and candidate_index > 0:
        span = took[problem_number][candidate_index]
        if span:
            selected.append(
                {
                    **starts[candidate_index - 1],
                    "numbers": list(range(problem_number - span + 1, problem_number + 1)),
                }
            )
            problem_number -= span
        candidate_index -= 1
    if problem_number:
        raise RuntimeError(f"Could not align {expected_count} problem numbers")
    selected.reverse()
    return selected


def parse_number_references(tokens: list[str]) -> list[int]:
    references: list[int] = []
    for token in tokens:
        normalized = token.strip(".,()[]{}")
        range_match = re.fullmatch(r"(\d{1,3})\s*[-–—~]\s*(\d{1,3})", normalized)
        if range_match:
            first_number, last_number = map(int, range_match.groups())
            if first_number <= last_number and last_number - first_number <= 30:
                references.extend(range(first_number, last_number + 1))
                continue
        digit_groups = re.findall(r"\d{1,3}", normalized)
        if len(digit_groups) == 2 and len(digit_groups[1]) < len(digit_groups[0]):
            # OCR can replace the dash and the repeated tens digit with a
            # Korean glyph (for example, "69蕁3" for "69-73"). Reconstruct
            # the nearest non-decreasing endpoint instead of treating the
            # trailing 3 as exercise 3.
            first_number, suffix = map(int, digit_groups)
            modulus = 10 ** len(digit_groups[1])
            last_number = (first_number // modulus) * modulus + suffix
            if last_number < first_number:
                last_number += modulus
            if last_number - first_number <= 30:
                references.extend(range(first_number, last_number + 1))
                continue
        references.extend(int(value) for value in re.findall(r"\d{1,3}", normalized))
    return references


def parse_figure_captions(ocr_page: dict, chapter_number: int) -> list[dict]:
    captions: list[dict] = []
    page_width = ocr_page["width"]
    page_height = ocr_page["height"]
    for line in ocr_page["lines"]:
        words = line.get("words", [])
        if not words or not (
            "그림" in words[0]["text"]
            or (words[0]["text"].startswith("그") and len(words[0]["text"]) <= 3)
        ):
            continue
        bounds = {
            "x0": min(word["x"] for word in words),
            "y0": min(word["y"] for word in words),
            "x1": max(word["x"] + word["width"] for word in words),
            "y1": max(word["y"] + word["height"] for word in words),
        }
        figure_token = words[1]["text"] if len(words) > 1 else ""
        digit_groups = re.findall(r"\d+", figure_token)
        figure_number = ""
        if len(digit_groups) >= 2:
            figure_number = digit_groups[-1]
        elif digit_groups:
            digits = digit_groups[0]
            chapter_digits = str(chapter_number)
            if digits.startswith(chapter_digits) and len(digits) > len(chapter_digits):
                figure_number = digits[len(chapter_digits) :]

        marker = next(
            (
                index
                for index, word in enumerate(words)
                if any(fragment in word["text"] for fragment in ("연습", "습문", "인습", "년1습"))
            ),
            None,
        )
        if marker is None:
            continue
        references: list[int] = []
        if marker is not None:
            reference_tokens = [word["text"] for word in words[marker + 1 :]]
            references.extend(parse_number_references(reference_tokens))
            for token in reference_tokens:
                if not re.search(r"\d", token) and re.fullmatch(r"[.·,Ss]+", token):
                    if "S" in token or "s" in token:
                        references.append(5)

        center_x = (bounds["x0"] + bounds["x1"]) / 2 / page_width
        captions.append(
            {
                "column": (
                    "wide" if 0.43 <= center_x <= 0.57
                    else ("left" if center_x < 0.5 else "right")
                ),
                "y": bounds["y0"] / page_height,
                "captionBottom": bounds["y1"] / page_height,
                "label": f"그림 {chapter_number}-{figure_number}" if figure_number else "관련 그림",
                "figureNumber": int(figure_number) if figure_number else None,
                "references": references,
            }
        )
    return captions


def find_figure_mentions(problems: dict, ocr_pages: dict, chapter_number: int) -> dict[int, set[int]]:
    """Map figure numbers mentioned in each final problem text to problem numbers."""
    mentions: dict[int, set[int]] = {}
    pattern = re.compile(rf"그림\s*{chapter_number}\s*[-•·]\s*(\d+)")
    for problem_number, problem in problems.items():
        text_parts = []
        for segment in problem["segments"]:
            page = ocr_pages.get(f"page-{segment['page']}.png")
            if not page:
                continue
            page_width = page["width"]
            page_height = page["height"]
            x0 = segment["x"]
            x1 = x0 + segment["width"]
            y0 = segment["y"]
            y1 = y0 + segment["height"]
            for line in page["lines"]:
                selected = []
                for word in line.get("words", []):
                    center_x = (word["x"] + word["width"] / 2) / page_width
                    center_y = (word["y"] + word["height"] / 2) / page_height
                    if x0 <= center_x <= x1 and y0 <= center_y <= y1:
                        selected.append(word["text"])
                if selected:
                    text_parts.append(" ".join(selected))
        text = " ".join(text_parts)
        for match in pattern.finditer(text):
            mentions.setdefault(int(match.group(1)), set()).add(int(problem_number))
    return mentions


def figure_segment(image: Image.Image, caption: dict, page: int, block_top: float) -> dict:
    width, height = image.size
    if caption["column"] == "wide":
        x, crop_width = 0.052, 0.897
    elif caption["column"] == "left":
        x, crop_width = 0.052, 0.445
    else:
        x, crop_width = 0.497, 0.452
    x0 = int(width * x)
    x1 = int(width * (x + crop_width))
    caption_y = int(height * caption["y"])
    pixels = np.asarray(image)
    ink_rows = np.flatnonzero((pixels[:, x0:x1].min(axis=2) < 225).sum(axis=1) >= 3).tolist()
    groups = group_rows(ink_rows, 8)
    previous_groups = [group for group in groups if group[-1] < caption_y]
    substantial = [group for group in previous_groups[-4:] if len(group) >= 25]
    if substantial:
        # Wide figures frequently contain several vertically stacked
        # subfigures. Their earliest substantial band is part of the same
        # figure, while a normal column figure should stay anchored to the
        # closest substantial band above its caption.
        anchor = substantial[0] if caption["column"] == "wide" else substantial[-1]
        top_px = anchor[0] - 45
    else:
        top_px = caption_y - int(height * 0.22)
    top = max(block_top, top_px / height)
    bottom = min(0.972, caption["captionBottom"] + 0.01)
    return {
        "page": page,
        "x": round(x, 5),
        "y": round(top, 5),
        "width": round(crop_width, 5),
        "height": round(max(0.02, bottom - top), 5),
        "label": caption["label"],
    }


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
    max_number = max((number for start in starts for number in start["numbers"]), default=0)
    problems: dict[str, dict] = {
        str(number): {"segments": [], "figures": []} for number in range(1, max_number + 1)
    }
    for index, start in enumerate(starts):
        next_start = starts[index + 1] if index + 1 < len(starts) else None
        start_block = start["block"]
        end_block = next_start["block"] if next_start else len(blocks) - 1
        segments: list[dict] = []

        for block_index in range(start_block, end_block + 1):
            block = blocks[block_index]
            y0 = start["y"] if block_index == start_block else block["top"]
            y1 = next_start["y"] - 0.001 if next_start and block_index == end_block else block["bottom"]
            # A legitimate one-line exercise can be only 2% of a page tall.
            if y1 - y0 < 0.003:
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

        for number in start["numbers"]:
            problems[str(number)]["segments"] = segments
    return problems


def segment_overlaps(first: dict, second: dict) -> bool:
    if first["page"] != second["page"]:
        return False
    if abs(first["x"] - second["x"]) > 0.03:
        return False
    overlap = min(first["y"] + first["height"], second["y"] + second["height"]) - max(
        first["y"], second["y"]
    )
    return overlap > 0.015


def trim_blank_margins(problems: dict, rendered_pages: dict[int, Path]) -> None:
    """Keep only ink-bearing rows; never append blank end-of-chapter pages."""
    pixels_by_page = {}
    for page, path in rendered_pages.items():
        with Image.open(path).convert('RGB') as image:
            pixels_by_page[page] = np.asarray(image)
    for problem in problems.values():
        trimmed = []
        for segment in problem['segments']:
            pixels = pixels_by_page[segment['page']]
            height, width = pixels.shape[:2]
            x0 = int(width * segment['x'])
            x1 = int(width * (segment['x'] + segment['width']))
            y0 = int(height * segment['y'])
            y1 = min(height, int(height * (segment['y'] + segment['height'])))
            rows = np.flatnonzero((pixels[y0:y1, x0:x1].min(axis=2) < 210).sum(axis=1) >= 3)
            if len(rows) < 3:
                continue
            absolute_groups = group_rows((rows + y0).tolist(), 4)
            if len(absolute_groups) >= 2:
                first_group, second_group = absolute_groups[:2]
                # Running headers are smaller than body text and separated
                # from a continued exercise by a conspicuously large gap.
                # Remove just that header band while retaining the continuation.
                if (
                    first_group[-1] / height < 0.06
                    and len(first_group) <= 10
                    and second_group[0] / height > 0.068
                    and second_group[0] - first_group[-1] > height * 0.01
                ):
                    rows = rows[rows + y0 >= second_group[0]]
            top = max(y0, y0 + int(rows[0]) - 3)
            bottom = min(y1, y0 + int(rows[-1]) + 4)
            normalized_y = top / height
            normalized_height = (bottom - top) / height
            # A running page header can occupy the empty bridge between the
            # left and right columns. Real one-line exercise text is roughly
            # 1.5–2% of the page high; these headers are below 1.2% and sit at
            # the very top. Do not attach them to the preceding exercise.
            if normalized_y < 0.06 and normalized_height < 0.012:
                continue
            trimmed.append({**segment, 'y': round(normalized_y, 5), 'height': round(normalized_height, 5)})
        problem['segments'] = trimmed


def attach_figures(
    problems: dict[str, dict],
    starts: list[dict],
    figures: list[dict],
    rendered_pages: dict[int, Path],
    figure_mentions: dict[int, set[int]],
) -> int:
    attached = 0
    max_problem = len(problems)
    for figure in figures:
        preceding = [
            start
            for start in starts
            if start["block"] < figure["block"]
            or (start["block"] == figure["block"] and start["y"] < figure["y"])
        ]
        default_problem = preceding[-1]["numbers"][0] if preceding else None
        parsed_references = sorted(
            {number for number in figure["references"] if 1 <= number <= max_problem}
        )
        references = set(
            parsed_references
            if default_problem is not None and default_problem in parsed_references
            else ([default_problem] if default_problem is not None else [])
        )
        if figure["figureNumber"] is not None:
            references.update(figure_mentions.get(figure["figureNumber"], set()))
        if not references:
            continue

        block_top = 0.064
        with Image.open(rendered_pages[figure["page"]]).convert("RGB") as image:
            segment = figure_segment(image, figure, figure["page"], block_top)
        for problem_number in references:
            problem = problems.get(str(problem_number))
            if not problem:
                continue
            if figure["column"] == "wide":
                # A two-column figure is often already present as a clipped
                # half inside the continuation crop. Remove its vertical band
                # from both text columns and attach one full-width copy.
                figure_top = segment["y"]
                figure_bottom = segment["y"] + segment["height"]
                text_segments = []
                for item in problem["segments"]:
                    if item["page"] != segment["page"]:
                        text_segments.append(item)
                        continue
                    item_top = item["y"]
                    item_bottom = item["y"] + item["height"]
                    overlap = min(item_bottom, figure_bottom) - max(item_top, figure_top)
                    if overlap <= 0.015:
                        text_segments.append(item)
                        continue
                    if item_top < figure_top - 0.003:
                        text_segments.append({
                            **item,
                            "height": round(figure_top - 0.003 - item_top, 5),
                        })
                    if item_bottom > figure_bottom + 0.003:
                        text_segments.append({
                            **item,
                            "y": round(figure_bottom + 0.003, 5),
                            "height": round(item_bottom - figure_bottom - 0.003, 5),
                        })
                problem["segments"] = text_segments
            elif any(segment_overlaps(item, segment) for item in problem["segments"]):
                continue
            key = (segment["page"], segment["x"], segment["y"], segment["height"])
            existing = {
                (item["page"], item["x"], item["y"], item["height"])
                for item in problem["figures"]
            }
            if key not in existing:
                problem["figures"].append(segment)
                attached += 1
    return attached


def subtract_wide_visual(problems: dict, visual: dict) -> None:
    """Remove a full-width floating visual from every sequential text crop."""
    visual_top = visual["y"]
    visual_bottom = visual_top + visual["height"]
    for problem in problems.values():
        text_segments = []
        for item in problem["segments"]:
            if item["page"] != visual["page"]:
                text_segments.append(item)
                continue
            item_top = item["y"]
            item_bottom = item_top + item["height"]
            overlap = min(item_bottom, visual_bottom) - max(item_top, visual_top)
            if overlap <= 0.015:
                text_segments.append(item)
                continue
            if item_top < visual_top - 0.003:
                text_segments.append({
                    **item,
                    "height": round(visual_top - 0.003 - item_top, 5),
                })
            if item_bottom > visual_bottom + 0.003:
                text_segments.append({
                    **item,
                    "y": round(visual_bottom + 0.003, 5),
                    "height": round(item_bottom - visual_bottom - 0.003, 5),
                })
        problem["segments"] = text_segments


def attach_reviewed_visuals(problems: dict, chapter_number: int) -> int:
    attached = 0
    for visual in REVIEWED_VISUALS.get(chapter_number, []):
        subtract_wide_visual(problems, visual)
        segment = {key: value for key, value in visual.items() if key != "references"}
        for problem_number in visual["references"]:
            problem = problems[str(problem_number)]
            problem["figures"].append(segment.copy())
            attached += 1
    return attached


def generate_book(book_id: str, pdf: Path, pdftoppm: Path, scratch: Path, ocr_script: Path, selected_chapters: set[int] | None = None) -> dict:
    spec = BOOKS[book_id]
    chapters_out: dict[str, dict] = {}
    chapter_specs: list[ChapterSpec] = spec["chapters"]

    for chapter_index, chapter in enumerate(chapter_specs):
        if selected_chapters and chapter.number not in selected_chapters:
            continue
        exercise_end = (
            chapter_specs[chapter_index + 1].start - 1
            if chapter_index + 1 < len(chapter_specs)
            else spec["final_exercise_page"]
        )
        pdf_start = chapter.exercises + PDF_OFFSET
        pdf_end = exercise_end + PDF_OFFSET
        chapter_scratch = scratch / f"book-{book_id}-chapter-{chapter.number}"
        chapter_scratch.mkdir(parents=True, exist_ok=True)
        rendered_pages: dict[int, Path] = {}
        page_data: dict[int, dict] = {}
        try:
            for pdf_page in range(pdf_start, pdf_end + 1):
                prefix = chapter_scratch / f"page-{pdf_page}"
                rendered = prefix.with_suffix('.png')
                if not rendered.exists():
                    rendered = render_page(pdftoppm, pdf, pdf_page, prefix)
                rendered_pages[pdf_page] = rendered
                with Image.open(rendered).convert("RGB") as image:
                    content_top_px, color_starts = find_problem_starts(image, pdf_page == pdf_start)
                    _, height = image.size
                content_top = content_top_px / height
                page_data[pdf_page] = {
                    "contentTop": content_top,
                    "colorStarts": [
                        item
                        for item in color_starts
                        if item["y"] >= content_top + (0.015 if pdf_page == pdf_start else 0)
                    ],
                }

            ocr_cache = chapter_scratch / 'pages-ocr.json'
            if ocr_cache.exists():
                ocr_pages = json.loads(ocr_cache.read_text(encoding='utf-8'))
            else:
                ocr_pages = run_windows_ocr(list(rendered_pages.values()), chapter_scratch, ocr_script)
                ocr_cache.write_text(json.dumps(ocr_pages, ensure_ascii=False), encoding='utf-8')
            blocks: list[dict] = []
            starts: list[dict] = []
            figures: list[dict] = []
            diagnostics: list[dict] = []
            block_lookup: dict[tuple[int, str], int] = {}

            for pdf_page in range(pdf_start, pdf_end + 1):
                rendered = rendered_pages[pdf_page]
                ocr_page = ocr_pages[rendered.name]
                content_top = page_data[pdf_page]["contentTop"]
                with Image.open(rendered).convert('RGB') as image:
                    ocr_starts = ocr_problem_starts(ocr_page, content_top, image)
                page_starts = merge_problem_starts(page_data[pdf_page]["colorStarts"], ocr_starts)

                for column in ("left", "right"):
                    blocks.append(
                        {
                            "page": pdf_page,
                            "column": column,
                            "top": content_top,
                            "bottom": 0.966,
                        }
                    )
                    block_index = len(blocks) - 1
                    block_lookup[(pdf_page, column)] = block_index
                    for item in page_starts:
                        if item["column"] == column:
                            starts.append({**item, "block": block_index, "page": pdf_page})

                page_figures = parse_figure_captions(ocr_page, chapter.number)
                for figure in page_figures:
                    figures.append(
                        {
                            **figure,
                            "page": pdf_page,
                            "block": block_lookup[(
                                pdf_page,
                                "left" if figure["column"] == "wide" else figure["column"],
                            )],
                        }
                    )

                diagnostics.append(
                    {
                        "page": pdf_page,
                        "left": sum(item["column"] == "left" for item in page_starts),
                        "right": sum(item["column"] == "right" for item in page_starts),
                        "ocr": len(ocr_starts),
                        "figures": len(page_figures),
                    }
                )

            apply_reviewed_numbers(starts, chapter.number)
            (chapter_scratch / 'candidates.json').write_text(json.dumps(starts), encoding='utf-8')
            starts = resolve_problem_numbers(starts, PROBLEM_COUNTS[chapter.number])
            (chapter_scratch / 'selected.json').write_text(json.dumps(starts), encoding='utf-8')
            problems = build_segments(blocks, starts)
            trim_blank_margins(problems, rendered_pages)
            validate_chapter(starts, problems, PROBLEM_COUNTS[chapter.number])
            figure_mentions = find_figure_mentions(problems, ocr_pages, chapter.number)
            figure_count = attach_figures(
                problems, starts, figures, rendered_pages, figure_mentions
            )
            figure_count += attach_reviewed_visuals(problems, chapter.number)
            trim_blank_margins(problems, rendered_pages)
        except Exception:
            print(f'Inspection checkpoints retained in {chapter_scratch}', flush=True)
            raise

        if not problems:
            raise RuntimeError(f"No problems detected for chapter {chapter.number}")
        chapters_out[str(chapter.number)] = {
            "title": chapter.title,
            "exercisePrintedPage": chapter.exercises,
            "problemCount": len(problems),
            "problems": problems,
            "diagnostics": diagnostics,
            "validation": {
                "printedNumbersChecked": len(problems),
                "visuallyReviewedStarts": sum(bool(item.get('visuallyReviewed')) for item in starts),
                "emptyCrops": 0,
            },
        }
        (chapter_scratch / 'chapter.json').write_text(json.dumps(chapters_out[str(chapter.number)], ensure_ascii=False), encoding='utf-8')
        print(f"chapter {chapter.number}: {len(problems)} problems, {figure_count} related figure crops")

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
    parser.add_argument("--ocr-script", type=Path, default=Path("scripts/windows-ocr.ps1"))
    parser.add_argument("--output", type=Path, default=Path("public/problem-index.json"))
    parser.add_argument("--scratch", type=Path, default=Path("tmp/pdfs/indexer"))
    parser.add_argument('--chapters', type=int, nargs='+', help='Regenerate only these chapters; page bounds still use the complete book.')
    args = parser.parse_args()

    args.scratch.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    books = {
        "1": generate_book("1", args.book1, args.pdftoppm, args.scratch, args.ocr_script, set(args.chapters or [])),
        "2": generate_book("2", args.book2, args.pdftoppm, args.scratch, args.ocr_script, set(args.chapters or [])),
    }
    if args.chapters:
        if not args.output.exists():
            raise ValueError('Partial regeneration requires an existing complete output index')
        previous = json.loads(args.output.read_text(encoding='utf-8'))
        for book_id, book in books.items():
            previous['books'][book_id]['chapters'].update(book['chapters'])
        books = previous['books']
    payload = {"version": 5, "pdfPageOffset": PDF_OFFSET, "books": books}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
