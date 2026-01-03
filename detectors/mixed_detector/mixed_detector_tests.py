import unittest
import json
import mixed_detector as md

class TestMixedToggleFunctions(unittest.TestCase):

    def test_process_code_files(self):
        code_files = ['file1.py', 'file2.py']
        code_files_contents = [
            'toggle1\n toggle2 toggle1',
            'toggle2\n toggle3 toggle2 toggle3'
        ]
        mixed_patterns = [r'toggle\d+']
        mixed_toggles = {}

        md.process_code_files(code_files, code_files_contents, mixed_patterns, mixed_toggles)

        expected_output = {
            'toggle1': [('file1.py', 2)],
            'toggle2': [('file1.py', 1), ('file2.py', 2)],
            'toggle3': [('file2.py', 2)]
        }

        self.assertEqual(mixed_toggles, expected_output)

    def test_count_occurrences(self):
        mixed_toggles = {}
        code_file = 'file1.py'
        matches = ['toggle1', 'toggle1', 'toggle2']

        md.count_occurrences(code_file, matches, mixed_toggles)

        expected_output = {
            'toggle1': [('file1.py', 2)],
            'toggle2': [('file1.py', 1)]
        }

        self.assertEqual(mixed_toggles, expected_output)

    def test_format_mixed_toggles_data(self):
        mixed_toggles = {
            'toggle1': [('file1.py', 2)],
            'toggle2': [('file2.py', 1)]
        }

        expected_output = json.dumps({
            "mixed_toggles": mixed_toggles,
            "total_count": 2
        }, indent=2)

        result = md.format_mixed_toggles_data(mixed_toggles)
        self.assertEqual(result, expected_output)


if __name__ == '__main__':
    unittest.main()
