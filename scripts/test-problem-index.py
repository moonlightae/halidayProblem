"""Regression checks for shifted numbering and merged exercise crops."""
import importlib.util
import json
import sys
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

    def test_shared_range_has_nonempty_common_crop(self):
        starts = g.resolve_problem_numbers([
            {'block': 0, 'y': .1, 'ocrNumber': 1, 'numberRange': [1, 6]},
            {'block': 0, 'y': .6, 'ocrNumber': 7}], 7)
        problems = g.build_segments([{'page': 1, 'column': 'left', 'top': .05, 'bottom': .95}], starts)
        self.assertTrue(problems['1']['segments'])
        self.assertEqual(problems['1']['segments'], problems['6']['segments'])

    def test_published_index_is_complete_and_validated(self):
        data = json.loads(Path('public/problem-index.json').read_text(encoding='utf-8'))
        self.assertEqual(data['version'], 4)
        chapters = {int(key): chapter for book in data['books'].values() for key, chapter in book['chapters'].items()}
        self.assertEqual(set(chapters), set(range(1, 45)))
        for number, chapter in chapters.items():
            self.assertEqual(chapter['problemCount'], g.PROBLEM_COUNTS[number])
            self.assertEqual(chapter['validation']['printedNumbersChecked'], chapter['problemCount'])
            self.assertTrue(all(problem['segments'] for problem in chapter['problems'].values()))
        problems = chapters[24]['problems']
        self.assertEqual(chapters[1]['problemCount'], 32)
        self.assertTrue(chapters[1]['problems']['32']['segments'])
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


if __name__ == '__main__':
    unittest.main()
