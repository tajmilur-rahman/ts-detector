import re


def process_code_files(code_files, code_files_contents, mixed_patterns, mixed_toggles):
    for code_file, content in zip(code_files, code_files_contents):
        for pattern in mixed_patterns:
            matches = re.findall(pattern, content)
            count_occurrences(code_file, matches, mixed_toggles)


def count_occurrences(code_file, matches, mixed_toggles):
    for match in matches:
        mixed_toggles[match].append((code_file, matches.count(match)))


def format_mixed_toggles_data(mixed_toggles):
    m = list(mixed_toggles)
    m.sort()
    mixed_toggles_data = {
        "toggles": m,
        "qty": len(mixed_toggles)
    }
    return mixed_toggles_data
