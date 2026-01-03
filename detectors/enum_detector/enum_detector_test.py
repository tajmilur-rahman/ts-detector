import unittest
from enum_detector import *


class TestEnumParsing(unittest.TestCase):

    def test_java_enum(self):
        java_code = """
        public enum Day {
            SUNDAY, MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY
        }
        """
        self.assertEqual(is_enum_member(java_code, ["MONDAY"], "java"), ["MONDAY"])
        self.assertEqual(is_enum_member(java_code, ["BLACK"], "java"), [])
        self.assertEqual(is_enum_member(java_code, ["MONDAY", "BLACK"], "java"), ["MONDAY"])

    def test_python_enum(self):
        python_code = """
        from enum import Enum
        class Day(Enum):
            SUNDAY = 1
            MONDAY = 2
        """
        self.assertEqual(is_enum_member(python_code, ["MONDAY"], "python"), ["MONDAY"])
        self.assertEqual(is_enum_member(python_code, ["BLACK"], "python"), [])
        self.assertEqual(is_enum_member(python_code, ["MONDAY", "BLACK"], "python"), ["MONDAY"])

    def test_go_enum(self):
        go_code = """
        const (
            SUNDAY = iota
            MONDAY
            TUESDAY
        )
        """
        self.assertEqual(is_enum_member(go_code, ["MONDAY"], "go"), ["MONDAY"])
        self.assertEqual(is_enum_member(go_code, ["BLACK"], "go"), [])
        self.assertEqual(is_enum_member(go_code, ["MONDAY", "BLACK"], "go"), ["MONDAY"])

    def test_cpp_enum(self):
        cpp_code = """
        enum Day { SUNDAY, MONDAY, TUESDAY, WEDNESDAY };
        """
        self.assertEqual(is_enum_member(cpp_code, ["MONDAY"], "cpp"), ["MONDAY"])
        self.assertEqual(is_enum_member(cpp_code, ["BLACK"], "cpp"), [])
        self.assertEqual(is_enum_member(cpp_code, ["MONDAY", "BLACK"], "cpp"), ["MONDAY"])

    def test_csharp_enum(self):
        csharp_code = """
        public enum Day {
            SUNDAY, MONDAY, TUESDAY, WEDNESDAY
        }
        """
        self.assertEqual(is_enum_member(csharp_code, ["MONDAY"], "csharp"), ["MONDAY"])
        self.assertEqual(is_enum_member(csharp_code, ["BLACK"], "csharp"), [])
        self.assertEqual(is_enum_member(csharp_code, ["MONDAY", "BLACK"], "csharp"), ["MONDAY"])

    def test_c_enum(self):
        c_code = """
        enum Day { SUNDAY, MONDAY, TUESDAY, WEDNESDAY };
        """
        self.assertEqual(is_enum_member(c_code, ["MONDAY"], "c"), ["MONDAY"])
        self.assertEqual(is_enum_member(c_code, ["BLACK"], "c"), [])
        self.assertEqual(is_enum_member(c_code, ["MONDAY", "BLACK"], "c"), ["MONDAY"])


if __name__ == "__main__":
    unittest.main()
