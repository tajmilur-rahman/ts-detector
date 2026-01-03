import detectors.regex.regex_c as c_patterns
import detectors.regex.regex_java as j_patterns
import detectors.regex.regex_python as py_patterns
import detectors.regex.regex_go as go_patterns
import detectors.regex.regex_csharp as csharp_patterns
import detectors.regex.regex_config as config_patterns
import re

language_map = {
    "c++": c_patterns,
    "java": j_patterns,
    "python": py_patterns,
    "go": go_patterns,
    "csharp": csharp_patterns,
    "config": config_patterns
}

def get_code_file_contents(lang, code_files):
    code_files_contents = []
    for file in code_files:
        if lang.lower() == "c++":
            with open(file, 'rb') as f:
                try:
                    content = f.read().decode('utf-8')
                    code_files_contents.append(content)
                except UnicodeDecodeError:
                    pass
        else:
            with open(file, 'rb') as f:
                try:
                    content = f.read().decode('utf-8')
                    code_files_contents.append(content)
                except UnicodeDecodeError:
                    pass
    return code_files_contents


def getFileName(lang, path):
    if lang == "python":
        regex = r"[^\/]*\.py"
        return re.findall(regex, path)[0]
    elif lang == "js":
        regex = r"[^\/]*\.js"
        return re.findall(regex, path)[0]
    elif lang == 'java':
        regex = r"[^\/]*\.java"
        return re.findall(regex, path)[0]
    elif lang == 'go':
        regex = r"[^\/]*\.go"
        return re.findall(regex, path)[0]

    return path


def get_mixed_toggle_var_patterns(lang):
    return list(language_map[lang.lower()].mixed_toggle_patterns.values())

def get_spread_toggle_var_patterns(lang):
    """
    Returns the regex patterns for spread toggle variables based on language.
    Supports both programming languages and configuration file types.
    """
    lang = lang.lower()
    
    # Configuration file-specific patterns
    config_patterns = {
        "spread_toggle_patterns": {
            "parent_finder": [
                r"(?i)(toggle|feature|flag)\s*[:=]\s*\w+",
                r"(?i)(parent_toggle|base_toggle)\s*[:=]\s*\w+"
            ]
        }
    }

    # Check if lang is for a configuration file
    if lang == "config":
        return config_patterns["spread_toggle_patterns"]

    # Check for programming language patterns in the language_map
    if lang in language_map:
        return language_map[lang].spread_toggle_patterns

    # If no patterns are defined for the given language
    raise ValueError(f"No spread toggle patterns defined for language: {lang}")
