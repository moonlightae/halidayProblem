"""Regression checks for shifted numbering and merged exercise crops."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

spec = importlib.util.spec_from_file_location('generator', Path(__file__).with_name('generate-problem-index.py'))
g = importlib.util.module_from_spec(spec)
sys.modules['generator'] = g
spec.loader.exec_module(g)


class IndexRegressionTests(unittest.TestCase):
    def test_close_distinct_numbers_are_not_merged(self):
        starts = [{'column': 'left', 'y': .2, 'ocrNumber': 1},
                  {'column': 'left', 'y': .218, 'ocrNumber': 2}]
        self.assertEqual(len(g.merge_problem_starts([], starts)), 2)

    def test_diagram_cannot_replace_exercise_heading(self):
        image = Image.new('RGB', (1000, 1300), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((60, 300, 180, 312), fill=(180, 70, 30))
        draw.rectangle((100, 750, 200, 850), fill=(180, 70, 30))
        self.assertLess(g.find_exercise_top(image), 320)

    def test_first_problem_near_page_top_is_detected(self):
        image = Image.new('RGB', (1000, 1300), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((60, 77, 65, 86), fill=(180, 70, 30))
        draw.rectangle((110, 78, 170, 85), fill='black')
        _, starts = g.find_problem_starts(image, False)
        self.assertEqual(len(starts), 1)

    def test_unconfirmed_number_cannot_pass_validation(self):
        with self.assertRaisesRegex(ValueError, 'Unconfirmed'):
            g.validate_chapter([{'numbers': [1], 'ocrNumber': 2}], {}, 1)

    def test_empty_crop_cannot_pass_validation(self):
        with self.assertRaisesRegex(ValueError, 'empty crop'):
            g.validate_chapter([{'numbers': [1], 'ocrNumber': 1}], {'1': {'segments': []}}, 1)

    def test_one_line_problem_keeps_its_crop(self):
        problems = g.build_segments([{'page': 1, 'column': 'left', 'top': .05, 'bottom': .95}],
                                    [{'block': 0, 'y': .62, 'numbers': [9]},
                                     {'block': 0, 'y': .64, 'numbers': [10]}])
        self.assertTrue(problems['9']['segments'])

    def test_running_header_is_removed_but_continuation_is_kept(self):
        image = Image.new('RGB', (1000, 1300), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((500, 64, 700, 70), fill='black')
        draw.rectangle((500, 98, 900, 113), fill='black')
        problems = {'1': {'segments': [
            {'page': 1, 'x': .497, 'y': .04, 'width': .452, 'height': .06}
        ]}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'page.png'
            image.save(path)
            g.trim_blank_margins(problems, {1: path})
        self.assertGreater(problems['1']['segments'][0]['y'], .07)
        self.assertTrue(problems['1']['segments'][0]['height'] > .01)

    def test_figure_mentions_are_found_inside_problem_crop(self):
        problems = {'54': {'segments': [
            {'page': 1, 'x': .05, 'y': .1, 'width': .45, 'height': .2}
        ]}}
        ocr_pages = {'page-1.png': {
            'width': 1000,
            'height': 1300,
            'lines': [{'words': [
                {'text': '그림', 'x': 80, 'y': 150, 'width': 30, 'height': 15},
                {'text': '44-13a', 'x': 115, 'y': 150, 'width': 50, 'height': 15},
            ]}],
        }}
        self.assertEqual(g.find_figure_mentions(problems, ocr_pages, 44), {13: {54}})

    def test_shared_range_has_nonempty_common_crop(self):
        starts = g.resolve_problem_numbers([
            {'block': 0, 'y': .1, 'ocrNumber': 1, 'numberRange': [1, 6]},
            {'block': 0, 'y': .6, 'ocrNumber': 7}], 7)
        problems = g.build_segments([{'page': 1, 'column': 'left', 'top': .05, 'bottom': .95}], starts)
        self.assertTrue(problems['1']['segments'])
        self.assertEqual(problems['1']['segments'], problems['6']['segments'])

    def test_corrupted_range_suffix_is_not_a_stray_problem_number(self):
        self.assertEqual(g.parse_number_references(['69蕁3']), list(range(69, 74)))

    def test_published_index_is_complete_and_validated(self):
        data = json.loads(Path('public/problem-index.json').read_text(encoding='utf-8'))
        self.assertEqual(data['version'], 5)
        chapters = {int(key): chapter for book in data['books'].values() for key, chapter in book['chapters'].items()}
        self.assertEqual(set(chapters), set(range(1, 45)))
        self.assertEqual(sum(chapter['problemCount'] for chapter in chapters.values()), 2637)
        for number, chapter in chapters.items():
            self.assertEqual(chapter['problemCount'], g.PROBLEM_COUNTS[number])
            self.assertEqual(chapter['validation']['printedNumbersChecked'], chapter['problemCount'])
            self.assertTrue(all(problem['segments'] for problem in chapter['problems'].values()))
            for problem in chapter['problems'].values():
                for segment in problem['segments']:
                    self.assertFalse(segment['y'] < .06 and segment['height'] < .012)
            for problem_number in range(1, chapter['problemCount']):
                current = chapter['problems'][str(problem_number)]['segments']
                following = chapter['problems'][str(problem_number + 1)]['segments']
                if current == following:
                    continue
                for first in current:
                    for second in following:
                        if first['page'] != second['page'] or abs(first['x'] - second['x']) >= .03:
                            continue
                        overlap = min(first['y'] + first['height'], second['y'] + second['height']) - max(first['y'], second['y'])
                        self.assertLessEqual(overlap, .003, f'chapter {number}, problems {problem_number}/{problem_number + 1}')
        problems = chapters[24]['problems']
        self.assertEqual(chapters[1]['problemCount'], 32)
        self.assertTrue(chapters[1]['problems']['32']['segments'])
        for chapter_number, last_problem in ((13, 66), (15, 61), (35, 61)):
            self.assertEqual(chapters[chapter_number]['problemCount'], last_problem)
            self.assertTrue(chapters[chapter_number]['problems'][str(last_problem)]['segments'])
        for number in (1, 4, 5, 6, 7, 60, 61):
            self.assertTrue(problems[str(number)]['segments'])
        self.assertEqual(problems['60']['segments'][0]['page'], 113)
        self.assertEqual(problems['61']['segments'][0]['page'], 113)
        self.assertEqual(len(problems['59']['segments']), 1)
        for number in (5, 6):
            end = problems[str(number)]['segments'][-1]
            following = problems[str(number + 1)]['segments'][0]
            self.assertEqual(end['page'], following['page'])
            self.assertLess(end['y'] + end['height'], following['y'])

        chapter34 = chapters[34]['problems']
        expected_tables = {
            '표 34-3': range(1, 7),
            '표 34-4': range(11, 16),
            '표 34-5': range(16, 21),
            '표 34-6': range(25, 34),
            '표 34-7': range(38, 42),
        }
        for label, numbers in expected_tables.items():
            for number in numbers:
                self.assertIn(label, [item['label'] for item in chapter34[str(number)]['figures']])
        self.assertNotIn('그림 34-33', [item['label'] for item in chapter34['3']['figures']])
        for number in range(69, 74):
            self.assertEqual(chapter34[str(number)]['segments'], chapter34['69']['segments'])
            self.assertIn('그림 34-35', [item['label'] for item in chapter34[str(number)]['figures']])

        chapter44 = chapters[44]['problems']
        for number in ('53', '54'):
            wide_figures = [item for item in chapter44[number]['figures'] if item['width'] > .5]
            self.assertTrue(any(item['label'] == '그림 44-13' for item in wide_figures))


if __name__ == '__main__':
    unittest.main()
