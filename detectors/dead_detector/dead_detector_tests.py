import unittest
import json
import dead_detector as dd


class TestToggleFunctions(unittest.TestCase):

    def test_format_python_toggles(self):
        toggles = ['toggle1', 'toggle2', 'toggle3']
        expected_output = ['"toggle1"', '"toggle2"', '"toggle3"']

        result = dd.format_python_toggles(toggles)
        self.assertEqual(result, expected_output)

    def test_find_dead_toggles_no_matches(self):
        toggles = ['toggle1', 'toggle2']
        code_files = ['file1.txt', 'file2.txt']
        code_files_contents = [
            'This is some code without toggles.',
            'Another file with no toggles here.'
        ]

        expected_output = ['toggle1', 'toggle2']

        result = dd.find_dead_toggles(toggles, code_files, code_files_contents)
        self.assertEqual(result, expected_output)

    def test_find_dead_toggles_with_matches(self):
        toggles = ['toggle1', 'toggle2']
        code_files = ['file1.txt', 'file2.txt']
        code_files_contents = [
            'This is some code with toggle1.',
            'Another file with toggle2 here.'
        ]

        expected_output = []

        result = dd.find_dead_toggles(toggles, code_files, code_files_contents)
        self.assertEqual(result, expected_output)

    def test_format_dead_toggles_data(self):
        dead_toggles = ['toggle1', 'toggle2']
        expected_output = json.dumps({
            "dead_toggles": dead_toggles,
            "total_count": len(dead_toggles)
        }, indent=2)

        result = dd.format_dead_toggles_data(dead_toggles)
        self.assertEqual(result, expected_output)


if __name__ == '__main__':
    unittest.main()
