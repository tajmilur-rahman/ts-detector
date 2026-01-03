import detectors.regex.regex_c as c_patterns
import detectors.regex.regex_java as j_patterns
import detectors.regex.regex_python as py_patterns
import detectors.regex.regex_go as go_patterns
import detectors.regex.regex_csharp as csharp_patterns
from collections import defaultdict

import detectors.toggle_extractor.toggle_extractor as toggle_extractor
from function_utils import extract_functions, match_toggle_usage

import detectors.enum_detector.enum_detector as ed
import detectors.mixed_detector.mixed_detector as md

import detectors.helper as helper

import detectors.spread_detector.spread_detector as sd
import detectors.dead_detector.dead_detector as dd
import detectors.nested_detector.nested_detector as nd
import os
import re

language_map = {
    "c++": c_patterns,
    "cpp": c_patterns,
    "java": j_patterns,
    "python": py_patterns,
    "go": go_patterns,
    "csharp": csharp_patterns
}


def detect(lang, code_files, t_config_files, t_usage):
    if lang is None:
        raise ValueError("Language is not defined.")

    if code_files is None:
        raise ValueError("A list of code files is required.")

    if t_config_files is None:
        raise ValueError("A list of config files is required.")

    toggle_source_files = code_files + t_config_files

    if t_usage == "dead":
        return extract_dead_toggles(lang, toggle_source_files, t_config_files)
    elif t_usage == "spread":
        return extract_spread_toggles(lang, toggle_source_files, t_config_files)
    elif t_usage == "nested":
        return extract_nested_toggles(lang, toggle_source_files, t_config_files)
    elif t_usage == "enum":
        return extract_enum_toggles(lang, toggle_source_files, t_config_files)
    elif t_usage == "mixed" and lang != "config":
        return extract_mixed_toggles(lang, toggle_source_files)
    else:
        print(f"The '{t_usage}' toggle pattern is not supported for {lang}.")
        return []
    
def process_config_toggles(toggles, pattern_type):
    """
    Process config toggles based on the toggle type.
    :param toggles: List of extracted toggles
    :param pattern_type: Type of toggle pattern (e.g., dead, nested, enum, spread)
    :return: Dictionary with processed toggle data
    """
    if pattern_type == "dead":
        return {"dead_toggles": toggles}
    elif pattern_type == "nested":
        return {"nested_toggles": toggles}
    elif pattern_type == "enum":
        return {"enum_toggles": list(toggles), "qty": len(toggles)}
    elif pattern_type == "spread":
        return {"spread_toggles": toggles}
    else:
        raise ValueError(f"Unsupported pattern type: {pattern_type}")
    
def extract_dead_toggles(lang, code_files, t_config_files):
    # Extract toggles from config files
    toggles = get_toggles_from_config_files(t_config_files, lang)
    code_files_contents = helper.get_code_file_contents(lang, code_files)

    dead_toggles = dd.find_dead_toggles(toggles, code_files, code_files_contents)
    return dd.format_dead_toggles_data(dead_toggles)

def extract_nested_toggles(lang, code_files, t_config_files):
    toggles = toggle_extractor.extract_toggles_from_config_files(t_config_files)
    code_files_contents = helper.get_code_file_contents(lang, code_files)

    nested_data = nd.process_code_files(lang, code_files, code_files_contents, toggles, proximity=3)
    return nd.format_nested_toggles_data({"nested_toggles": nested_data["nested_toggles"]})

def extract_spread_toggles(lang, code_files, t_config_files):
    spread_toggles = defaultdict(list)
    toggles = get_toggles_from_config_files(t_config_files, lang)

    for code_file in code_files:
        if not os.path.exists(code_file):
            print(f"Warning: File not found - {code_file}")
            continue

        try:
            with open(code_file, 'r', encoding='utf-8') as file:
                source_code = file.read()
        except UnicodeDecodeError:
            print(f"Unicode error in {code_file}. Retrying with ISO-8859-1")
            with open(code_file, 'r', encoding='ISO-8859-1') as file:
                source_code = file.read()

        for toggle in toggles:
            count = source_code.lower().count(toggle.lower())
            if count > 0:
                relative_path = os.path.relpath(code_file)

                # Function-level toggle usage
                lang_key = lang.lower().replace("c++", "cpp").replace("c#", "csharp")
                try:
                    functions = extract_functions(source_code, lang_key)
                    function_usage = match_toggle_usage(source_code, functions, toggle)
                except Exception as e:
                    print(f"Function parsing failed for {code_file}: {e}")
                    function_usage = {}

                spread_toggles[toggle].append({
                    "file": relative_path,
                    "Functions": [function_usage],
                    "count": count
                })

    # Filter toggles that appear in more than one file
    spread_toggles = {
        toggle: occurrences
        for toggle, occurrences in spread_toggles.items()
        if len({entry["file"] for entry in occurrences}) > 1
    }

    formatted_toggles = {
        "toggles": spread_toggles,
        "qty": len(spread_toggles)
    }

    return formatted_toggles

def extract_mixed_toggles(lang, code_files):
    mixed_toggles = defaultdict(lambda: defaultdict(int))
    code_files_contents = helper.get_code_file_contents(lang, code_files)
    mixed_patterns = helper.get_mixed_toggle_var_patterns(lang)

    for code_file, content in zip(code_files, code_files_contents):
        functions = []
        try:
            functions = extract_functions(lang, content)
        except Exception as e:
            print(f"Parsing Error ({code_file})")
            continue

        for func_name, func_body, *_ in functions:
            toggle_candidates = extract_toggle_matches(func_body, mixed_patterns)
            for toggle in toggle_candidates:
                mixed_toggles[func_name][toggle] += 1

    return md.format_mixed_toggles_data(mixed_toggles)

def extract_toggle_matches(func_body, patterns):
    matches = []
    for pattern in patterns:
        for match in re.findall(pattern, func_body):
            if isinstance(match, tuple):
                matches.extend([m for m in match if m])
            else:
                matches.append(match)
    return matches

def extract_enum_toggles(lang, code_files, t_config_files):
    toggles = set(get_toggles_from_config_files(t_config_files, lang))
    code_files_contents = helper.get_code_file_contents(lang, code_files)

    result = {
        "toggles": defaultdict(list),
        "qty": 0
    }

    for code_file, content in zip(code_files, code_files_contents):
        functions = extract_functions(content, lang)
        file_toggle_data = defaultdict(dict)
        file_toggle_count = defaultdict(int)

        for func in functions:
            if len(func) == 3:
                func_name, func_body, _ = func
            else:
                func_name, func_body, *_ = func
            matched = ed.is_enum_member(func_body, toggles, lang)
            for toggle in matched:
                file_toggle_data[toggle][func_name] = file_toggle_data[toggle].get(func_name, 0) + 1
                file_toggle_count[toggle] += 1
                result["qty"] += 1

        for toggle, funcs in file_toggle_data.items():
            result["toggles"][toggle].append({
                "file": code_file,
                "Functions": [funcs],
                "count": file_toggle_count[toggle]
            })

    result["toggles"] = dict(result["toggles"])
    return result

def get_toggles_from_config_files(config_files, lang=None):
    """
    Wrapper around toggle extraction to manage and return toggles from files.
    """
    return toggle_extractor.extract_toggles_from_config_files(config_files, lang=lang)
