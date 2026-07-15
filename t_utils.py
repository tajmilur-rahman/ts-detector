import detectors.regex.regex_c as c_patterns
import detectors.regex.regex_java as j_patterns
import detectors.regex.regex_python as py_patterns
import detectors.regex.regex_go as go_patterns
import detectors.regex.regex_csharp as csharp_patterns
from collections import defaultdict

import detectors.toggle_extractor.toggle_extractor as toggle_extractor
from function_utils import extract_functions

import detectors.enum_detector.enum_detector as ed
import detectors.mixed_detector.mixed_detector as md

import detectors.helper as helper

import detectors.dead_detector.dead_detector as dd
import detectors.nested_detector.nested_detector as nd
import detectors.toggle_match_utils as tmu
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

def _is_test_file(path):
    normalized = path.replace("\\", "/").lower()
    parts = normalized.split("/")
    if any(part in {"test", "tests", "spec", "__tests__", "__test__"} for part in parts):
        return True
    filename = parts[-1]
    if filename.startswith(("test_", "spec_")):
        return True
    if any(marker in filename for marker in ("_test.", "_tests.", ".test.", ".tests.", ".spec.")):
        return True
    if filename.endswith(("test.cs", "tests.cs", "test.java", "tests.java")):
        return True
    return False


def _count_non_test_files(files):
    return len({os.path.abspath(path) for path in files if not _is_test_file(path)})

def _read_source_code(code_file):
    try:
        with open(code_file, 'r', encoding='utf-8') as file:
            return file.read()
    except UnicodeDecodeError:
        print(f"Unicode error in {code_file}. Retrying with ISO-8859-1")
        with open(code_file, 'r', encoding='ISO-8859-1') as file:
            return file.read()

_config_set_cache = {}

def _is_config_file(code_file, config_files):
    if not config_files:
        return False
    key = id(config_files)
    if key not in _config_set_cache:
        _config_set_cache[key] = {os.path.abspath(p) for p in config_files}
    return os.path.abspath(code_file) in _config_set_cache[key]

def _count_toggles_in_functions(
    source_bytes, functions, toggles, alias_map, global_alias_map, excluded_by_toggle
):
    term_map = tmu.build_term_to_toggle_map(toggles, alias_map, global_alias_map)
    term_pattern = tmu.build_combined_term_pattern(list(term_map.keys()))
    per_fn_counts = {}

    for fn in functions:
        body = source_bytes[fn["start_byte"]:fn["end_byte"]].decode("utf-8", errors="ignore")
        fn_counts = tmu.count_terms_in_text(
            body,
            term_map,
            term_pattern,
            excluded_by_toggle=excluded_by_toggle,
        )
        if fn_counts:
            per_fn_counts[fn["name"]] = fn_counts
    return per_fn_counts

def _initial_alias_resolution(raw_rhs_map, toggles):
    toggles_lower = {toggle.lower(): toggle for toggle in toggles}
    resolved = {}
    for name, rhs in raw_rhs_map.items():
        rhs_lower = rhs.lower()
        direct = {orig for low, orig in toggles_lower.items() if low in rhs_lower}
        if direct:
            resolved[name] = set(direct)
    return resolved

def _update_alias_from_resolved(name, rhs_lower, resolved):
    current = resolved.get(name, set())
    for alias_name, alias_toggles in resolved.items():
        if alias_name == name:
            continue
        if alias_name.lower() in rhs_lower and not alias_toggles.issubset(current):
            current = current.union(alias_toggles)
    if current and current != resolved.get(name, set()):
        resolved[name] = current
        return True
    return False

def _propagate_aliases(raw_rhs_map, resolved):
    changed = True
    while changed:
        changed = False
        for name, rhs in raw_rhs_map.items():
            rhs_lower = rhs.lower()
            if _update_alias_from_resolved(name, rhs_lower, resolved):
                changed = True
    return resolved

def _resolve_aliases_from_rhs_case_insensitive(raw_rhs_map, toggles):
    resolved = _initial_alias_resolution(raw_rhs_map, toggles)
    return _propagate_aliases(raw_rhs_map, resolved)

_ALIAS_PATTERNS_CACHE = None


def _build_alias_patterns_by_language():
    global _ALIAS_PATTERNS_CACHE
    if _ALIAS_PATTERNS_CACHE is not None:
        return _ALIAS_PATTERNS_CACHE
    _ALIAS_PATTERNS_CACHE = {
        "python": {
            "decl": [
                r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.+)$",
                r"^\s*(\w+)\s*=\s*(.+)$"
            ],
            "assign": [
                r"^\s*(?:self\.)?([A-Za-z_][\w\.]*)\s*=(?!=)\s*(.+)$"
            ]
        },
        "java": {
            "decl": [
                r"^\s*(?:public|private|protected)?\s*(?:static)?\s*(?:final)?\s*[\w<>\[\]]+\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+);",
                r"^\s*[\w<>\[\]]+\s+(\w+)\s*=\s*(.+);"
            ],
            "assign": [
                r"^\s*([A-Za-z_][\w\.]*)\s*=(?!=)\s*(.+);"
            ]
        },
        "csharp": {
            "decl": [
                r"^\s*(?:public|private|protected|internal)?\s*(?:static)?\s*(?:readonly|const)?\s*[\w<>\[\]]+\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+);",
                r"^\s*(?:public|private|protected|internal)?\s*(?:static)?\s*(?:readonly|const)?\s*[\w<>\[\]\?]+\s+(\w+)\s*=\s*(.+);",
                r"^\s*[\w<>\[\]]+\s+(\w+)\s*=\s*(.+);"
            ],
            "assign": [
                r"^\s*(?:this\.)?([A-Za-z_][\w\.]*)\s*=(?!=)\s*(.+);"
            ],
            "expression_body": [
                r"^\s*(?:public|private|protected|internal)?\s*(?:static)?\s*(?:override\s+)?[\w<>\[\]\?]+\s+(\w+)\s*=>\s*(.+);",
                r"^\s*(?:get|set)\s*=>\s*(.+);",
            ],
            "accessor": [
                r"^\s*(?:get|set)\s*\{\s*(?:return\s+)?(.+);\s*\}",
            ]
        },
        "c++": {
            "decl": [
                r"^\s*(?:static|const|constexpr)?\s*[\w:<>\[\]]+\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+);",
                r"^\s*[\w:<>\[\]]+\s+(\w+)\s*=\s*(.+);"
            ],
            "assign": [
                r"^\s*([A-Za-z_][\w\.]*)\s*=(?!=)\s*(.+);"
            ],
            "define": [
                r"^\s*#\s*define\s+(\w+)\s+(.+)$"
            ]
        },
        "go": {
            "decl": [
                r"^\s*(?:var|const)\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+)",
                r"^\s*(\w+)\s*:=\s*(.+)",
                r"^\s*(\w+)\s*=\s*(.+)"
            ],
            "assign": [
                r"^\s*([A-Za-z_][\w\.]*)\s*=(?!=)\s*(.+)$"
            ]
        }
    }
    return _ALIAS_PATTERNS_CACHE

def _merge_assignment_block(lines, start_idx, max_lines=4):
    combined = [lines[start_idx]]
    line_indexes = [start_idx]
    next_idx = start_idx + 1
    while next_idx < len(lines) and len(combined) < max_lines:
        combined.append(lines[next_idx])
        line_indexes.append(next_idx)
        if ";" in lines[next_idx]:
            break
        next_idx += 1
    return " ".join(combined), next_idx + 1, line_indexes

def _normalize_assignment_lines(lines, lang):
    if lang.lower() not in {"java", "csharp", "c++"}:
        return [(line, [idx]) for idx, line in enumerate(lines)]
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "=" in line and ";" not in line:
            merged_line, next_idx, line_indexes = _merge_assignment_block(lines, i)
            merged.append((merged_line, line_indexes))
            i = next_idx
            continue
        merged.append((line, [i]))
        i += 1
    return merged

def _build_file_alias_maps(lines, toggles, alias_patterns, lang):
    alias_map = {}
    raw_rhs_map = {}
    assignment_aliases = set()
    raw_rhs_lines = {}
    normalized_lines = _normalize_assignment_lines(lines, lang)
    for line, line_indexes in normalized_lines:
        _update_raw_rhs_maps(
            line, line_indexes, raw_rhs_map, raw_rhs_lines, assignment_aliases, alias_patterns
        )

    if raw_rhs_map:
        alias_map = _resolve_aliases_from_rhs_case_insensitive(raw_rhs_map, toggles)
    alias_def_lines_by_toggle = {}
    for var_name, mapped in alias_map.items():
        line_indexes = raw_rhs_lines.get(var_name, set())
        for toggle in mapped:
            alias_def_lines_by_toggle.setdefault(toggle, set()).update(line_indexes)
    return alias_map, assignment_aliases, alias_def_lines_by_toggle

def _try_match_two_group(patterns, line, raw_rhs_map, raw_rhs_lines, line_indexes, extras=None):
    for pattern in patterns:
        match = pattern.match(line)
        if not match:
            continue
        var_name, rhs = match.groups()
        if extras and "strip_dot" in extras and "." in var_name:
            var_name = var_name.split(".")[-1]
        raw_rhs_map[var_name] = rhs
        raw_rhs_lines.setdefault(var_name, set()).update(line_indexes)
        if extras and "aliases" in extras:
            extras["aliases"].add(var_name)


def _update_raw_rhs_maps(line, line_indexes, raw_rhs_map, raw_rhs_lines, assignment_aliases, alias_patterns):
    _try_match_two_group(
        alias_patterns.get("decl", alias_patterns if isinstance(alias_patterns, list) else []),
        line, raw_rhs_map, raw_rhs_lines, line_indexes,
    )
    _try_match_two_group(
        alias_patterns.get("assign", []),
        line, raw_rhs_map, raw_rhs_lines, line_indexes,
        extras={"strip_dot": True, "aliases": assignment_aliases},
    )
    for pattern in alias_patterns.get("expression_body", []):
        match = pattern.match(line)
        if not match or len(match.groups()) != 2:
            continue
        var_name, rhs = match.groups()
        raw_rhs_map[var_name] = rhs
        raw_rhs_lines.setdefault(var_name, set()).update(line_indexes)
        assignment_aliases.add(var_name)
    for pattern in alias_patterns.get("accessor", []):
        match = pattern.match(line)
        if not match:
            continue
        key = f"__accessor_L{line_indexes[0]}"
        raw_rhs_map[key] = match.group(1)
        raw_rhs_lines.setdefault(key, set()).update(line_indexes)
    _try_match_two_group(
        alias_patterns.get("define", []),
        line, raw_rhs_map, raw_rhs_lines, line_indexes,
    )

def _get_cross_file_alias_map(lang, code_files, code_files_contents, toggles):
    lang_key = lang.lower()
    if lang_key == "java":
        return nd._build_java_cross_file_alias_map(code_files, code_files_contents, toggles)
    if lang_key == "csharp":
        return nd._build_csharp_cross_file_alias_map(code_files, code_files_contents, toggles)
    if lang_key == "c++":
        return nd._build_cpp_cross_file_alias_map(code_files, code_files_contents, toggles)
    if lang_key == "go":
        return nd._build_go_cross_file_alias_map(code_files, code_files_contents, toggles)
    if lang_key == "python":
        return nd._build_python_cross_file_alias_map(code_files, code_files_contents, toggles)
    return {}

def _compile_alias_patterns(lang):
    alias_patterns_by_language = _build_alias_patterns_by_language()
    raw_patterns = alias_patterns_by_language.get(lang.lower(), [])
    if isinstance(raw_patterns, dict):
        compiled = {}
        for key, patterns in raw_patterns.items():
            compiled[key] = [re.compile(p) for p in patterns]
        return compiled
    return [re.compile(p) for p in raw_patterns]

def _build_global_assignment_alias_map(eligible_files, eligible_contents, toggles, alias_patterns, lang):
    global_assignment_alias_map = {}
    for code_file, source_code in zip(eligible_files, eligible_contents):
        lines = source_code.splitlines()
        alias_map, assignment_aliases, _ = _build_file_alias_maps(
            lines, toggles, alias_patterns, lang
        )
        for alias in assignment_aliases:
            mapped = alias_map.get(alias)
            if not mapped:
                continue
            dotted = f".{alias}"
            if dotted not in global_assignment_alias_map:
                global_assignment_alias_map[dotted] = set(mapped)
            else:
                global_assignment_alias_map[dotted].update(mapped)
    return global_assignment_alias_map

def _should_skip_spread_file(code_file, config_files):
    if _is_test_file(code_file):
        return True
    if _is_config_file(code_file, config_files):
        return True
    if not os.path.exists(code_file):
        print(f"Warning: File not found - {code_file}")
        return True
    return False

def _flatten_fn_toggle_counts(per_fn_counts, toggle):
    return {
        fn_name: counts[toggle]
        for fn_name, counts in per_fn_counts.items()
        if toggle in counts
    }

def _is_comment_only(line):
    stripped = line.strip()
    if not stripped:
        return False
    return stripped.startswith(("//", "///", "/*", "*/", "* "))


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
    formatted = dd.format_dead_toggles_data(dead_toggles)
    formatted["counters"] = {
        "total_toggles_found": len(formatted.get("toggles", [])),
        "total_toggle_usages": 0,
        "total_files_excluding_test_files": _count_non_test_files(code_files),
    }
    return formatted

def extract_nested_toggles(lang, code_files, t_config_files):
    toggles = get_toggles_from_config_files(t_config_files, lang)
    code_files_contents = helper.get_code_file_contents(lang, code_files)

    nested_data = nd.process_code_files(lang, code_files, code_files_contents, toggles, proximity=3)
    formatted = nd.format_nested_toggles_data({"nested_toggles": nested_data["nested_toggles"]})
    formatted["counters"] = {
        "total_toggles_found": len(formatted.get("toggles", {})),
        "total_toggle_usages": nested_data.get("qty", 0),
        "total_files_excluding_test_files": _count_non_test_files(code_files),
    }
    return formatted

def extract_spread_toggles(lang, code_files, t_config_files):
    spread_toggles = defaultdict(list)
    toggles = get_toggles_from_config_files(t_config_files, lang)

    eligible_files = []
    eligible_contents = []
    for code_file in code_files:
        if _should_skip_spread_file(code_file, t_config_files):
            continue

        source_code = _read_source_code(code_file)
        eligible_files.append(code_file)
        eligible_contents.append(source_code)

    alias_patterns = _compile_alias_patterns(lang)
    global_alias_map = _get_cross_file_alias_map(
        lang, eligible_files, eligible_contents, toggles
    )
    global_assignment_alias_map = _build_global_assignment_alias_map(
        eligible_files, eligible_contents, toggles, alias_patterns, lang
    )

    quick_filter = tmu.build_quick_filter_pattern(toggles)
    for code_file, source_code in zip(eligible_files, eligible_contents):
        if quick_filter and not quick_filter.search(source_code):
            continue
        _append_spread_toggles_for_file(
            spread_toggles,
            lang,
            code_file,
            source_code,
            toggles,
            alias_patterns,
            global_alias_map,
            global_assignment_alias_map,
        )

    # Filter toggles that appear in more than one file
    spread_toggles = {
        toggle: occurrences
        for toggle, occurrences in spread_toggles.items()
        if len({entry["file"] for entry in occurrences}) > 1
    }

    total_toggle_usages = sum(
        entry.get("count", 0)
        for occurrences in spread_toggles.values()
        for entry in occurrences
    )
    formatted_toggles = {
        "toggles": spread_toggles,
        "qty": len(spread_toggles),
        "counters": {
            "total_toggles_found": len(spread_toggles),
            "total_toggle_usages": total_toggle_usages,
            "total_files_excluding_test_files": _count_non_test_files(code_files),
        }
    }

    return formatted_toggles

def _append_spread_toggles_for_file(
    spread_toggles,
    lang,
    code_file,
    source_code,
    toggles,
    alias_patterns,
    global_alias_map,
    global_assignment_alias_map,
):
    lines = source_code.splitlines()
    source_bytes = source_code.encode("utf-8")
    alias_map, _, alias_def_lines_by_toggle = _build_file_alias_maps(
        lines, toggles, alias_patterns, lang
    )
    merged_global = {}
    if global_alias_map:
        nd._merge_alias_maps(merged_global, global_alias_map)
    if global_assignment_alias_map:
        nd._merge_alias_maps(merged_global, global_assignment_alias_map)

    lang_key = tmu.normalize_parser_lang(lang)
    try:
        functions = extract_functions(source_code, lang_key)
    except Exception as e:
        print(f"Function parsing failed for {code_file}: {e}")
        functions = []

    per_fn_counts = _count_toggles_in_functions(
        source_bytes,
        functions,
        toggles,
        alias_map,
        merged_global or None,
        alias_def_lines_by_toggle,
    )

    relative_path = os.path.relpath(code_file)
    for toggle in toggles:
        fn_usage = _flatten_fn_toggle_counts(per_fn_counts, toggle)
        count = sum(fn_usage.values()) if fn_usage else 0
        if count > 0:
            spread_toggles[toggle].append({
                "file": relative_path,
                "Functions": [fn_usage],
                "count": count
            })

def extract_mixed_toggles(lang, code_files):
    mixed_toggles = defaultdict(lambda: defaultdict(int))
    code_files_contents = helper.get_code_file_contents(lang, code_files)
    mixed_patterns = helper.get_mixed_toggle_var_patterns(lang)

    for code_file, content in zip(code_files, code_files_contents):
        functions = []
        try:
            lang_key = tmu.normalize_parser_lang(lang)
            functions = extract_functions(content, lang_key)
        except Exception:
            print(f"Parsing Error ({code_file})")
            continue

        source_bytes = content.encode("utf-8")
        for fn in functions:
            func_body = source_bytes[fn["start_byte"]:fn["end_byte"]].decode("utf-8", errors="ignore")
            toggle_candidates = extract_toggle_matches(func_body, mixed_patterns)
            for toggle in toggle_candidates:
                mixed_toggles[fn["name"]][toggle] += 1

    formatted = md.format_mixed_toggles_data(mixed_toggles)
    total_toggle_usages = sum(
        count
        for toggle_counts in mixed_toggles.values()
        for count in toggle_counts.values()
    )
    formatted["counters"] = {
        "total_toggles_found": len(formatted.get("toggles", [])),
        "total_toggle_usages": total_toggle_usages,
        "total_files_excluding_test_files": _count_non_test_files(code_files),
    }
    return formatted

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
    result["counters"] = {
        "total_toggles_found": len(result["toggles"]),
        "total_toggle_usages": result.get("qty", 0),
        "total_files_excluding_test_files": _count_non_test_files(code_files),
    }
    return result

def get_toggles_from_config_files(config_files, lang=None):
    """
    Wrapper around toggle extraction to manage and return toggles from files.
    """
    return toggle_extractor.extract_toggles_from_config_files(config_files, lang=lang)
