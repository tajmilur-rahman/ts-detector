import unittest
import json
from unittest.mock import patch
import nested_detector as nd


class TestToggleFunctions(unittest.TestCase):

    @patch('helper.getFileName')
    def test_process_code_files(self, mock_get_file_name):
        lang = "python"
        code_files = ['file1.py', 'file2.py']
        code_files_contents = [
            'toggle1\n toggle2',
            'toggle3\n toggle4'
        ]
        nested_patterns = [r'toggle\d+']
        nested_toggles = {}
        regex_patterns = {"general_pattern": [r'toggle\d+']}

        mock_get_file_name.side_effect = lambda lang, file: file
        nd.process_code_files(lang, code_files, code_files_contents, nested_patterns, nested_toggles)

        expected_output = {
            'file1.py': ['toggle1', 'toggle2'],
            'file2.py': ['toggle3', 'toggle4']
        }

        self.assertEqual(nested_toggles, expected_output)

    def test_extract_code_lines_python(self):
        lang = "python"
        match = "toggle1\n toggle2"

        expected_output = ['toggle1 toggle2']
        result = nd.extract_code_lines(lang, match)
        self.assertEqual(result, expected_output)

    def test_extract_code_lines_other(self):
        lang = "javascript"
        match = "toggle1\ntoggle2"

        expected_output = ['toggle1', 'toggle2']
        result = nd.extract_code_lines(lang, match)
        self.assertEqual(result, expected_output)

    @patch('helper.getFileName')
    def test_populate_nested_toggles(self, mock_get_file_name):
        nested_toggles = {}
        lang = "python"
        code_file = 'file1.py'
        code_lines = ['toggle1', 'toggle2']
        regex_patterns = {"general_pattern": [r'toggle\d+']}

        mock_get_file_name.return_value = code_file

        nd.populate_nested_toggles(nested_toggles, lang, code_file, code_lines, regex_patterns)

        expected_output = {
            'file1.py': ['toggle1', 'toggle2']
        }

        self.assertEqual(nested_toggles, expected_output)

    def test_clean_nested_toggles(self):
        nested_toggles = {
            'file1.py': ['toggle1', 'toggle1', 'toggle2'],
            'file2.py': [],
            'file3.py': ['toggle3']
        }

        cleaned_toggles, distinct_toggles = nd.clean_nested_toggles(nested_toggles)

        expected_cleaned_output = {
            'file1.py': ['toggle1', 'toggle2'],
            'file3.py': ['toggle3']
        }
        expected_distinct_toggles = {'toggle1', 'toggle2', 'toggle3'}

        self.assertEqual(cleaned_toggles, expected_cleaned_output)
        self.assertEqual(distinct_toggles, expected_distinct_toggles)

    def test_format_nested_toggles_data(self):
        nested_toggles = {
            'file1.py': ['toggle1', 'toggle2'],
            'file2.py': ['toggle3']
        }

        expected_output = json.dumps({
            "nested_toggles": nested_toggles,
            "total_count_path": len(nested_toggles),
            "total_count_toggles": 3
        }, indent=2)

        result = nd.format_nested_toggles_data(nested_toggles)
        self.assertEqual(result, expected_output)


if __name__ == '__main__':
    unittest.main()
