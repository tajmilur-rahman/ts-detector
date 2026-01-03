import unittest
from unittest.mock import patch, mock_open

import spread_detector as sd


class TestToggleFunctions(unittest.TestCase):

    @patch("builtins.open", new_callable=mock_open, read_data='toggle1\ntoggle2\n')
    def test_find_toggles_in_code_files(self, mock_file):
        code_files = ['file1.txt', 'file2.txt']
        toggles = ['toggle1', 'toggle2', 'toggle3']

        expected_output = {
            'toggle1': [('file1.txt', 'toggle1\ntoggle2\n')],
            'toggle2': [('file1.txt', 'toggle1\ntoggle2\n')],
        }

        result = sd.find_toggles_in_code_files(code_files, toggles)
        self.assertEqual(result, expected_output)

    @patch("builtins.open", new_callable=mock_open, read_data='toggle1\ntoggle2\n')
    def test_filter_spread_toggles(self, mock_file):
        toggle_lookup = {
            'toggle1': [('file1.txt', 'content1')],
            'toggle2': [('file1.txt', 'content2'), ('file2.txt', 'content2')],
            'toggle3': [('file1.txt', 'content3')],
        }

        expected_output = {'toggle2': [('file1.txt', 'content2'), ('file2.txt', 'content2')]}

        result = sd.filter_spread_toggles(toggle_lookup)
        self.assertEqual(result, expected_output)

    @patch('helper.get_spread_toggle_var_patterns')
    @patch('helper.getFileName')
    def test_find_parent_toggles(self, mock_get_filename, mock_get_patterns):
        mock_get_patterns.return_value = {'parent_finder': ['pattern1', 'pattern2']}
        spread_toggles = {
            'toggle1': [('file1.txt', 'content with toggle1')],
            'toggle2': [('file2.txt', 'content with toggle2')],
        }

        mock_get_filename.return_value = 'file1.txt'

        expected_output = {'toggle1': [('matched_pattern', 'file1.txt')]}

        result = sd.find_parent_toggles(spread_toggles, 'lang')
        self.assertEqual(result, expected_output)

    @patch('re.findall', return_value=['matched_pattern'])
    def test_find_parents_for_toggle(self, mock_findall):
        contents = [('file1.txt', 'content with toggle1')]
        toggle_parent_patterns = ['pattern1']
        lang = 'lang'

        expected_output = [('matched_pattern', 'file1.txt')]

        result = sd.find_parents_for_toggle('toggle1', contents, toggle_parent_patterns, lang)
        self.assertEqual(result, expected_output)

    def test_format_pattern(self):
        pattern = 'pattern_%s'
        toggle = 'toggle1'

        result = sd.format_pattern(pattern, toggle)
        self.assertEqual(result, 'pattern_toggle1')

        result = sd.format_pattern(None, toggle)
        self.assertIsNone(result)

    def test_format_spread_toggles(self):
        parent_toggles = {'toggle1': [('matched_pattern', 'file1.txt')]}
        expected_output = {
            "spread_toggles": parent_toggles,
            "total_count": 1
        }

        result = sd.format_spread_toggles(parent_toggles)
        self.assertEqual(result, expected_output)


if __name__ == '__main__':
    unittest.main()
