"""
Shared file exclusion logic used by both the regex and LLM detection paths.

Rules:
  - Test files are excluded from: spread, nested, enum, mixed
    (these measure production-code complexity)
  - Test files are INCLUDED in: dead
    (a toggle unused even in tests is truly dead)
  - Auto-generated and vendor/third-party files are excluded from all patterns
"""
import os
import re

# Directory names that mark test or vendor subtrees (case-insensitive match)
_EXCLUDED_DIRS = {
    # test directories
    'test', 'tests', 'testing',
    'spec', 'specs',
    '__tests__',
    'unittest', 'unittests',
    'integrationtest', 'integrationtests',
    'e2e',
    'mock', 'mocks', 'stubs', 'fakes', 'fixtures',
    # vendor / generated directories
    'vendor', 'third_party', 'thirdparty', 'external',
    'node_modules', 'deps',
    'generated', 'gen', 'obj', 'bin',
}

# File name suffixes that indicate a test file (language-specific)
_TEST_SUFFIXES = (
    # C#
    'Test.cs', 'Tests.cs', 'Spec.cs',
    'Mock.cs', 'Stub.cs', 'Fake.cs',
    # Java
    'Test.java', 'Tests.java', 'Spec.java',
    'IT.java',                     # integration test convention
    'Mock.java', 'Stub.java', 'Fake.java',
    # Go
    '_test.go',
    # Python
    '_test.py',
    # C++
    '_test.cc', '_test.cpp',
    'Test.cc', 'Tests.cc',
    'Test.cpp', 'Tests.cpp',
)

# File name prefixes that indicate a test file
_TEST_PREFIXES = ('test_', 'spec_')

# Suffixes that indicate auto-generated files
_GENERATED_SUFFIXES = (
    # C#
    '.Designer.cs', '.g.cs', '.g.i.cs',
    'AssemblyInfo.cs',
    # protobuf
    '.pb.go', '.pb.cc', '.pb.h',
    '_pb2.py', '_pb2_grpc.py',
    # XAML / resource
    '.xaml', '.resx',
)


def is_test_file(file_path):
    """Return True if the file is part of a test suite."""
    path = file_path.replace('\\', '/')
    parts = path.lower().split('/')
    basename = os.path.basename(file_path)

    # Any directory component matches an excluded test dir name
    if any(p in _EXCLUDED_DIRS for p in parts[:-1]):
        return True

    # File name ends with a test suffix
    if any(basename.endswith(s) for s in _TEST_SUFFIXES):
        return True

    # File name starts with a test prefix
    if basename.lower().startswith(_TEST_PREFIXES):
        return True

    return False


def is_generated_or_vendor_file(file_path):
    """Return True if the file is auto-generated or from a vendor/third-party tree."""
    path = file_path.replace('\\', '/')
    parts = path.lower().split('/')
    basename = os.path.basename(file_path)

    if any(p in _EXCLUDED_DIRS for p in parts[:-1]):
        return True

    if any(basename.endswith(s) for s in _GENERATED_SUFFIXES):
        return True

    return False


def is_excluded(file_path):
    """True if the file should be excluded from ALL patterns (generated/vendor)."""
    return is_generated_or_vendor_file(file_path)


def filter_production_files(code_files):
    """
    Return only production source files — excludes test files AND generated/vendor files.
    Use for: spread, nested, enum, mixed.
    """
    return [f for f in code_files if not is_test_file(f) and not is_generated_or_vendor_file(f)]


def filter_non_generated(code_files):
    """
    Return all non-generated/non-vendor files (test files included).
    Use for: dead toggle detection.
    """
    return [f for f in code_files if not is_generated_or_vendor_file(f)]
