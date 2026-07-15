from collections import defaultdict
from bisect import bisect_right
import re
from function_utils import extract_functions, parse_source_cached
from detectors.toggle_match_utils import (
    strip_string_literals,
    build_term_to_toggle_map,
    build_combined_term_pattern,
    build_quick_filter_pattern,
)


def _merge_alias_maps(target, source):
    for name, toggles in source.items():
        if name not in target:
            target[name] = set(toggles)
        else:
            target[name].update(toggles)


def _resolve_aliases_from_rhs(raw_rhs_map, toggles):
    resolved = _resolve_direct_aliases(raw_rhs_map, toggles)
    return _propagate_alias_chains(raw_rhs_map, resolved)


def _resolve_direct_aliases(raw_rhs_map, toggles):
    resolved = {}
    toggles_lower = {toggle.lower(): toggle for toggle in toggles}
    for name, rhs in raw_rhs_map.items():
        rhs_lower = rhs.lower()
        direct = {
            toggles_lower[low]
            for low in toggles_lower
            if low in rhs_lower
        }
        if direct:
            resolved[name] = direct
    return resolved


def _propagate_alias_chains(raw_rhs_map, resolved):
    changed = True
    while changed:
        changed = False
        for name, rhs in raw_rhs_map.items():
            if _expand_single_alias(name, rhs, resolved):
                changed = True
    return resolved


def _expand_single_alias(name, rhs, resolved):
    current = resolved.get(name, set())
    rhs_lower = rhs.lower()
    for alias_name, alias_toggles in resolved.items():
        if alias_name == name:
            continue
        if alias_name.lower() in rhs_lower and not alias_toggles.issubset(current):
            current = current.union(alias_toggles)
    if current and current != resolved.get(name, set()):
        resolved[name] = current
        return True
    return False


_RE_JAVA_CLASS = re.compile(r"\b(class|interface|enum)\s+(\w+)")
_RE_CSHARP_TYPE = re.compile(r"\b(class|interface|struct|enum)\s+(\w+)")
_RE_CPP_TYPE = re.compile(r"\b(class|struct|enum)\s+(\w+)")
_RE_CPP_NAMESPACE = re.compile(r"\bnamespace\s+(\w+)")
_RE_GO_PACKAGE = re.compile(r"^\s*package\s+(\w+)")
_RE_PY_MODULE = re.compile(r"/([^/]+)\.py$")


def _extract_java_class_name(lines):
    for line in lines:
        match = _RE_JAVA_CLASS.search(line)
        if match:
            return match.group(2)
    return None


def _extract_csharp_type_name(lines):
    for line in lines:
        match = _RE_CSHARP_TYPE.search(line)
        if match:
            return match.group(2)
    return None


def _extract_cpp_type_or_namespace(lines):
    for line in lines:
        match = _RE_CPP_TYPE.search(line)
        if match:
            return match.group(2)
    for line in lines:
        match = _RE_CPP_NAMESPACE.search(line)
        if match:
            return match.group(1)
    return None


def _extract_go_package_name(lines):
    for line in lines:
        match = _RE_GO_PACKAGE.match(line)
        if match:
            return match.group(1)
    return None


def _extract_python_module_name(code_file):
    match = _RE_PY_MODULE.search(code_file.replace("\\", "/"))
    if match:
        return match.group(1)
    return None


def _build_term_pattern(terms, max_terms=2000):
    if not terms or len(terms) > max_terms:
        return None
    escaped = [re.escape(term) for term in sorted(terms, key=len, reverse=True)]
    return re.compile("|".join(escaped))


def _extract_line_toggles(line, term_pattern, toggles_set, alias_map, term_map=None):
    scan_line = strip_string_literals(line)
    if term_pattern:
        matches = term_pattern.findall(scan_line)
        if not matches:
            return set()
        if isinstance(matches[0], tuple):
            found_terms = {m for tup in matches for m in tup if m}
        else:
            found_terms = set(matches)
    else:
        scan_lower = scan_line.lower()
        found_terms = {term for term in toggles_set if term.lower() in scan_lower}
        found_terms.update(
            alias for alias in alias_map if alias.lower() in scan_lower
        )

    line_toggles = set()
    for term in found_terms:
        if term_map:
            canonical = term_map.get(term.lower())
            if canonical:
                line_toggles.add(canonical)
                continue
        if term in toggles_set:
            line_toggles.add(term)
        if term in alias_map:
            line_toggles.update(alias_map[term])
    return line_toggles


def _build_java_cross_file_alias_map(code_files, code_files_contents, toggles):
    const_decl = re.compile(
        r"^\s*(?:public|private|protected)?\s*(?:static)?\s*(?:final)?\s*[\w<>\[\]]+\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+);"
    )
    raw_by_file = []
    class_by_file = []
    for code_file, content in zip(code_files, code_files_contents):
        lines = content.splitlines()
        class_by_file.append(_extract_java_class_name(lines))
        raw_rhs_map = {}
        for line in lines:
            match = const_decl.match(line)
            if not match:
                continue
            name, rhs = match.groups()
            raw_rhs_map[name] = rhs
        raw_by_file.append(raw_rhs_map)

    global_alias_map = {}
    for raw_rhs_map, class_name in zip(raw_by_file, class_by_file):
        resolved = _resolve_aliases_from_rhs(raw_rhs_map, toggles)
        _merge_alias_maps(global_alias_map, resolved)
        if class_name:
            qualified = {f"{class_name}.{name}": toggles for name, toggles in resolved.items()}
            _merge_alias_maps(global_alias_map, qualified)

    return global_alias_map


def _build_csharp_cross_file_alias_map(code_files, code_files_contents, toggles):
    const_decl = re.compile(
        r"^\s*(?:public|private|protected|internal)?\s*(?:static)?\s*(?:readonly|const)?\s*[\w<>\[\]]+\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+);"
    )
    global_alias_map = {}
    for code_file, content in zip(code_files, code_files_contents):
        lines = content.splitlines()
        type_name = _extract_csharp_type_name(lines)
        raw_rhs_map = {}
        for line in lines:
            match = const_decl.match(line)
            if not match:
                continue
            name, rhs = match.groups()
            raw_rhs_map[name] = rhs
        resolved = _resolve_aliases_from_rhs(raw_rhs_map, toggles)
        _merge_alias_maps(global_alias_map, resolved)
        if type_name:
            qualified = {f"{type_name}.{name}": mapped for name, mapped in resolved.items()}
            _merge_alias_maps(global_alias_map, qualified)
    return global_alias_map


def _build_cpp_cross_file_alias_map(code_files, code_files_contents, toggles):
    const_decl = re.compile(
        r"^\s*(?:static|const|constexpr)?\s*[\w:<>\[\]]+\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+);"
    )
    global_alias_map = {}
    for code_file, content in zip(code_files, code_files_contents):
        lines = content.splitlines()
        type_or_ns = _extract_cpp_type_or_namespace(lines)
        raw_rhs_map = {}
        for line in lines:
            match = const_decl.match(line)
            if not match:
                continue
            name, rhs = match.groups()
            raw_rhs_map[name] = rhs
        resolved = _resolve_aliases_from_rhs(raw_rhs_map, toggles)
        _merge_alias_maps(global_alias_map, resolved)
        if type_or_ns:
            qualified = {f"{type_or_ns}::{name}": mapped for name, mapped in resolved.items()}
            _merge_alias_maps(global_alias_map, qualified)
    return global_alias_map


def _build_go_cross_file_alias_map(code_files, code_files_contents, toggles):
    const_decl = re.compile(r"^\s*(?:var|const)\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+)")
    global_alias_map = {}
    for code_file, content in zip(code_files, code_files_contents):
        lines = content.splitlines()
        package_name = _extract_go_package_name(lines)
        raw_rhs_map = {}
        for line in lines:
            match = const_decl.match(line)
            if not match:
                continue
            name, rhs = match.groups()
            raw_rhs_map[name] = rhs
        resolved = _resolve_aliases_from_rhs(raw_rhs_map, toggles)
        _merge_alias_maps(global_alias_map, resolved)
        if package_name:
            qualified = {f"{package_name}.{name}": mapped for name, mapped in resolved.items()}
            _merge_alias_maps(global_alias_map, qualified)
    return global_alias_map


def _build_python_cross_file_alias_map(code_files, code_files_contents, toggles):
    const_decl = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.+)$")
    global_alias_map = {}
    for code_file, content in zip(code_files, code_files_contents):
        lines = content.splitlines()
        module_name = _extract_python_module_name(code_file)
        raw_rhs_map = {}
        for line in lines:
            match = const_decl.match(line)
            if not match:
                continue
            name, rhs = match.groups()
            raw_rhs_map[name] = rhs
        resolved = _resolve_aliases_from_rhs(raw_rhs_map, toggles)
        _merge_alias_maps(global_alias_map, resolved)
        if module_name:
            qualified = {f"{module_name}.{name}": mapped for name, mapped in resolved.items()}
            _merge_alias_maps(global_alias_map, qualified)
    return global_alias_map


_LOGICAL_OPS = re.compile(r"&&|\|\|")
_LOGICAL_OPS_PY = re.compile(r"\b(and|or)\b")

_CONDITION_START_BRACES = re.compile(r"^\s*(?:if|else\s+if|elif|while|for)\s*\(")
_CONDITION_START_PY = re.compile(r"^\s*(?:if|elif|while)\b")
_CONDITION_START_GO = re.compile(r"^\s*(?:if|for)\b")


def _get_logical_op_pattern(lang):
    if lang == "python":
        return _LOGICAL_OPS_PY
    return _LOGICAL_OPS


def _get_condition_start_pattern(lang):
    if lang == "python":
        return _CONDITION_START_PY
    if lang == "go":
        return _CONDITION_START_GO
    return _CONDITION_START_BRACES


def _merge_multiline_conditions(lines, lang):
    if lang == "python":
        return lines
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        if _is_open_condition(stripped, lang):
            combined = [line]
            j = i + 1
            while j < len(lines) and len(combined) < 6:
                combined.append(lines[j])
                if _condition_closes(lines[j], lang):
                    break
                j += 1
            merged.append(" ".join(combined))
            i = j + 1
        else:
            merged.append(line)
            i += 1
    return merged


_RE_GO_IF = re.compile(r"^\s*if\b")
_RE_OPEN_COND = re.compile(r"^\s*(?:if|else\s+if|elif|while|for)\s*\(")


def _is_open_condition(stripped, lang):
    if lang == "go":
        return bool(_RE_GO_IF.match(stripped)) and "{" not in stripped
    if _RE_OPEN_COND.match(stripped):
        return stripped.count("(") > stripped.count(")")
    return False


def _condition_closes(line, lang):
    if lang == "go":
        return "{" in line
    return line.count(")") >= line.count("(") and ")" in line


def _build_line_to_byte_offsets(lines):
    offsets = []
    pos = 0
    for line in lines:
        line_bytes = len(line.encode("utf-8"))
        offsets.append(pos)
        pos += line_bytes + 1
    return offsets


def _build_func_index(func_ranges):
    sorted_ranges = sorted(func_ranges, key=lambda r: r[1][0])
    starts = [r[1][0] for r in sorted_ranges]
    return sorted_ranges, starts


def _find_function_for_byte(func_ranges, byte_pos, _index=None):
    if _index is not None:
        sorted_ranges, starts = _index
        idx = bisect_right(starts, byte_pos) - 1
        if idx >= 0:
            fname, (start_b, end_b) = sorted_ranges[idx]
            if start_b <= byte_pos <= end_b:
                return fname
        return "GLOBAL"
    for fname, (start_b, end_b) in func_ranges:
        if start_b <= byte_pos <= end_b:
            return fname
    return "GLOBAL"


def _detect_same_line_nesting(line, line_toggles, logical_op_pattern):
    if len(line_toggles) < 2:
        return set(), set()
    if not logical_op_pattern or not logical_op_pattern.search(line):
        return set(), set()
    return set(line_toggles), set(line_toggles)


def _detect_structural_nesting(toggle_line_map, func_ranges, content, lang):
    nested = defaultdict(lambda: defaultdict(set))
    lang_key = lang.lower().replace("c++", "cpp").replace("c#", "csharp")

    try:
        tree, _ = parse_source_cached(content, lang_key)
    except Exception:
        return nested

    if_types = {
        "python": {"if_statement", "elif_clause"},
        "java": {"if_statement"},
        "csharp": {
            "if_statement",
            "preproc_if", "preproc_ifdef",
            "preproc_elif", "preproc_elifdef",
        },
        "cpp": {
            "if_statement",
            "preproc_if", "preproc_ifdef",
            "preproc_if_in_field_declaration_list",
            "preproc_ifdef_in_field_declaration_list",
            "preproc_if_in_enumerator_list",
            "preproc_ifdef_in_enumerator_list",
            "preproc_elif", "preproc_elifdef",
        },
        "go": {"if_statement"},
    }
    valid_types = if_types.get(lang_key, {"if_statement"})

    content_bytes = content.encode("utf-8")
    toggle_positions = {}
    for toggle, line_idxs in toggle_line_map.items():
        for line_idx in line_idxs:
            toggle_positions.setdefault(line_idx, set()).add(toggle)

    func_index = _build_func_index(func_ranges) if func_ranges else None

    if_nodes = []
    _collect_if_nodes(tree.root_node, valid_types, if_nodes)

    for if_node in if_nodes:
        _check_node_for_structural_nesting(
            if_node, valid_types, content_bytes, toggle_positions, func_ranges, nested,
            func_index=func_index,
        )

    return nested


def _collect_if_nodes(node, valid_types, result):
    if node.type in valid_types:
        result.append(node)
    for child in node.children:
        _collect_if_nodes(child, valid_types, result)


def _check_node_for_structural_nesting(
    if_node, valid_types, _content_bytes, toggle_positions, func_ranges, nested, func_index=None
):
    outer_toggles = _get_toggles_in_condition(if_node, _content_bytes, toggle_positions)
    if not outer_toggles:
        return

    inner_ifs = []
    _find_nested_ifs(if_node, valid_types, inner_ifs, depth=0)

    for inner_if in inner_ifs:
        inner_toggles = _get_toggles_in_condition(inner_if, _content_bytes, toggle_positions)
        if not inner_toggles:
            continue
        if outer_toggles & inner_toggles:
            continue
        byte_pos = if_node.start_byte
        fn_name = _find_function_for_byte(func_ranges, byte_pos, _index=func_index)
        for outer_t in outer_toggles:
            for inner_t in inner_toggles:
                nested[(outer_t, fn_name)].setdefault("deps", set()).add(inner_t)
                nested[(inner_t, fn_name)].setdefault("deps", set()).add(outer_t)


_CONDITION_FALLBACK_TYPES = frozenset({
    "parenthesized_expression", "binary_expression", "comparison_operator",
    "preproc_defined", "identifier", "not_operator", "boolean_operator",
    "unary_expression", "call_expression",
})


def _get_toggles_in_condition(if_node, _content_bytes, toggle_positions):
    cond_node = _find_condition_node(if_node)
    if not cond_node:
        return set()

    start_line = cond_node.start_point[0]
    end_line = cond_node.end_point[0]
    toggles_found = set()
    for line_idx in range(start_line, end_line + 1):
        if line_idx in toggle_positions:
            toggles_found.update(toggle_positions[line_idx])
    return toggles_found


def _find_condition_node(if_node):
    cond_node = if_node.child_by_field_name("condition")
    if cond_node:
        return cond_node
    cond_node = if_node.child_by_field_name("name")
    if cond_node:
        return cond_node
    for child in if_node.children:
        if child.type in _CONDITION_FALLBACK_TYPES:
            return child
    if if_node.type.startswith("preproc_"):
        return _find_preproc_condition_line(if_node)
    return None


def _find_preproc_condition_line(node):
    for child in node.children:
        if child.type in ("preproc_arg", "preproc_defined", "identifier",
                          "binary_expression", "unary_expression"):
            return child
    return None


_BODY_CONTAINER_TYPES = frozenset({
    "block", "compound_statement", "statement_block",
    "else_clause", "preproc_else", "preproc_elif", "preproc_elifdef",
    "case_statement", "switch_body",
})


def _find_nested_ifs(node, valid_types, result, depth):
    for child in node.children:
        if child.type in valid_types:
            result.append(child)
            _find_nested_ifs(child, valid_types, result, depth + 1)
        elif child.type in _BODY_CONTAINER_TYPES:
            _find_nested_ifs(child, valid_types, result, depth + 1)
        else:
            _find_nested_ifs(child, valid_types, result, depth)


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
    return False


def process_code_files(lang, code_files, code_files_contents, toggles, proximity=3):  # noqa: ARG001 proximity kept for API compat
    nested_toggles = defaultdict(dict)

    alias_patterns_by_language = {
        "python": [
            r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.+)$",
            r"^\s*(\w+)\s*=\s*(.+)$"
        ],
        "java": [
            r"^\s*(?:public|private|protected)?\s*(?:static)?\s*(?:final)?\s*[\w<>\[\]]+\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+);",
            r"^\s*[\w<>\[\]]+\s+(\w+)\s*=\s*(.+);"
        ],
        "csharp": [
            r"^\s*(?:public|private|protected|internal)?\s*(?:static)?\s*(?:readonly|const)?\s*[\w<>\[\]]+\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+);",
            r"^\s*[\w<>\[\]]+\s+(\w+)\s*=\s*(.+);"
        ],
        "c++": [
            r"^\s*(?:static|const|constexpr)?\s*[\w:<>\[\]]+\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+);",
            r"^\s*[\w:<>\[\]]+\s+(\w+)\s*=\s*(.+);"
        ],
        "go": [
            r"^\s*(?:var|const)\s+([A-Z_][A-Z0-9_]*)\s*=\s*(.+)",
            r"^\s*(\w+)\s*:=\s*(.+)",
            r"^\s*(\w+)\s*=\s*(.+)"
        ]
    }

    lang_lower = lang.lower()
    lang_key = lang_lower.replace("c++", "cpp").replace("c#", "csharp")
    alias_patterns = alias_patterns_by_language.get(lang_lower, [])
    logical_op_pattern = _get_logical_op_pattern(lang_lower)

    compiled_alias_patterns = [re.compile(pattern) for pattern in alias_patterns]

    global_alias_map = _build_global_alias_map(lang, code_files, code_files_contents, toggles)

    quick_filter = build_quick_filter_pattern(toggles)
    toggles_set = set(toggles)
    for code_file, content in zip(code_files, code_files_contents):
        if _is_test_file(code_file):
            continue
        if quick_filter and not quick_filter.search(content):
            continue

        lines = content.splitlines()

        alias_map = _build_local_alias_map(lines, compiled_alias_patterns, toggles)
        if global_alias_map:
            _merge_alias_maps(alias_map, global_alias_map)

        term_map = build_term_to_toggle_map(toggles, alias_map, global_alias_map)
        term_pattern = build_combined_term_pattern(list(term_map.keys()))
        toggle_lines = _find_toggle_lines(lines, term_pattern, toggles_set, alias_map, lang_lower)

        try:
            functions = extract_functions(content, lang_key)
        except Exception:
            functions = []

        func_ranges = [(fn["name"], (fn["start_byte"], fn["end_byte"])) for fn in functions]
        line_byte_offsets = _build_line_to_byte_offsets(lines)

        merged_lines = _merge_multiline_conditions(lines, lang_lower)

        _detect_same_line_nested_in_file(
            merged_lines, toggle_lines, term_pattern, toggles_set,
            alias_map, logical_op_pattern, func_ranges, line_byte_offsets,
            code_file, nested_toggles, term_map,
        )

        toggle_line_map = _build_toggle_line_map(
            lines, toggle_lines, term_pattern, toggles_set, alias_map, lang_lower, term_map
        )
        structural = _detect_structural_nesting(toggle_line_map, func_ranges, content, lang)
        _merge_structural_results(structural, code_file, nested_toggles)

    return {
        "nested_toggles": nested_toggles,
        "qty": _count_nested_deps(nested_toggles),
    }


def _merge_structural_results(structural, code_file, nested_toggles):
    for (toggle, fn_name), data in structural.items():
        deps = sorted(data.get("deps", set()))
        if not deps:
            continue
        if code_file not in nested_toggles[toggle]:
            nested_toggles[toggle][code_file] = {}
        if fn_name not in nested_toggles[toggle][code_file]:
            nested_toggles[toggle][code_file][fn_name] = {"dependencies": set()}
        nested_toggles[toggle][code_file][fn_name]["dependencies"].update(deps)


def _count_nested_deps(nested_toggles):
    total = 0
    for toggle in nested_toggles:
        for code_file in nested_toggles[toggle]:
            for fn_name in nested_toggles[toggle][code_file]:
                total += len(nested_toggles[toggle][code_file][fn_name]["dependencies"])
    return total


def _build_global_alias_map(lang, code_files, code_files_contents, toggles):
    lang_key = lang.lower()
    if lang_key == "java":
        return _build_java_cross_file_alias_map(code_files, code_files_contents, toggles)
    if lang_key == "csharp":
        return _build_csharp_cross_file_alias_map(code_files, code_files_contents, toggles)
    if lang_key == "c++":
        return _build_cpp_cross_file_alias_map(code_files, code_files_contents, toggles)
    if lang_key == "go":
        return _build_go_cross_file_alias_map(code_files, code_files_contents, toggles)
    if lang_key == "python":
        return _build_python_cross_file_alias_map(code_files, code_files_contents, toggles)
    return {}


def _build_local_alias_map(lines, compiled_alias_patterns, toggles):
    alias_map = {}
    for line in lines:
        for pattern in compiled_alias_patterns:
            match = pattern.match(line)
            if not match:
                continue
            var_name, rhs = match.groups()
            rhs_lower = rhs.lower()
            rhs_toggles = {
                toggle for toggle in toggles if toggle.lower() in rhs_lower
            }
            if rhs_toggles:
                alias_map[var_name] = rhs_toggles
    return alias_map


def _is_comment_only(line, lang=""):
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(("//", "///", "/*", "*/", "* ")):
        return True
    if lang == "python" and stripped.startswith("#"):
        return True
    return False


def _find_toggle_lines(lines, term_pattern, toggles_set, alias_map, lang=""):
    result = []
    for i, line in enumerate(lines):
        if _is_comment_only(line, lang):
            continue
        scan_line = strip_string_literals(line)
        if term_pattern:
            if term_pattern.search(scan_line):
                result.append(i)
        else:
            scan_lower = scan_line.lower()
            if any(toggle.lower() in scan_lower for toggle in toggles_set):
                result.append(i)
            elif any(alias.lower() in scan_lower for alias in alias_map):
                result.append(i)
    return result


def _build_toggle_line_map(
    lines, toggle_lines, term_pattern, toggles_set, alias_map, lang="", term_map=None
):
    toggle_line_map = defaultdict(set)
    for line_idx in toggle_lines:
        if _is_comment_only(lines[line_idx], lang):
            continue
        line_toggles = _extract_line_toggles(
            lines[line_idx], term_pattern, toggles_set, alias_map, term_map
        )
        for toggle in line_toggles:
            toggle_line_map[toggle].add(line_idx)
    return toggle_line_map


def _detect_same_line_nested_in_file(
    merged_lines, toggle_lines, term_pattern, toggles_set,
    alias_map, logical_op_pattern, func_ranges, line_byte_offsets,
    code_file, nested_toggles, term_map=None,
):
    processed_combos = set()

    merged_nesting_results = _precompute_merged_nesting(
        merged_lines, term_pattern, toggles_set, alias_map, logical_op_pattern, term_map,
    )

    _scan_toggle_lines_for_nesting(
        toggle_lines, merged_nesting_results, func_ranges, line_byte_offsets,
        code_file, nested_toggles, processed_combos,
    )
    _scan_merged_lines_for_nesting(
        merged_nesting_results, func_ranges, line_byte_offsets,
        code_file, nested_toggles, processed_combos,
    )


def _precompute_merged_nesting(
    merged_lines, term_pattern, toggles_set, alias_map, logical_op_pattern, term_map=None
):
    results = []
    seen = set()
    for idx, merged_line in enumerate(merged_lines):
        if merged_line in seen:
            continue
        seen.add(merged_line)
        line_toggles = _extract_line_toggles(
            merged_line, term_pattern, toggles_set, alias_map, term_map
        )
        matched, deps = _detect_same_line_nesting(merged_line, line_toggles, logical_op_pattern)
        if matched:
            results.append((matched, deps, idx))
    return results


def _scan_toggle_lines_for_nesting(
    toggle_lines, merged_nesting_results, func_ranges, line_byte_offsets,
    code_file, nested_toggles, processed_combos,
):
    if not merged_nesting_results:
        return
    for line_idx in toggle_lines:
        if line_idx >= len(line_byte_offsets):
            continue
        byte_pos = line_byte_offsets[line_idx]
        matched_fn = _find_function_for_byte(func_ranges, byte_pos)

        for matched, deps, _ in merged_nesting_results:
            combo_key = (code_file, matched_fn, frozenset(matched))
            if combo_key in processed_combos:
                continue
            processed_combos.add(combo_key)
            _record_nested_toggles(nested_toggles, matched, deps, code_file, matched_fn)


def _scan_merged_lines_for_nesting(
    merged_nesting_results, func_ranges, line_byte_offsets,
    code_file, nested_toggles, processed_combos,
):
    if not merged_nesting_results:
        return
    for matched, deps, line_idx in merged_nesting_results:
        byte_pos = line_byte_offsets[line_idx] if line_idx < len(line_byte_offsets) else 0
        matched_fn = _find_function_for_byte(func_ranges, byte_pos)
        combo_key = (code_file, matched_fn, frozenset(matched))
        if combo_key in processed_combos:
            continue
        processed_combos.add(combo_key)
        _record_nested_toggles(nested_toggles, matched, deps, code_file, matched_fn)


def _record_nested_toggles(nested_toggles, matched, deps, code_file, matched_fn):
    for toggle in matched:
        toggle_deps = sorted(deps - {toggle})
        if not toggle_deps:
            continue
        if code_file not in nested_toggles[toggle]:
            nested_toggles[toggle][code_file] = {}
        if matched_fn not in nested_toggles[toggle][code_file]:
            nested_toggles[toggle][code_file][matched_fn] = {"dependencies": set()}
        nested_toggles[toggle][code_file][matched_fn]["dependencies"].update(toggle_deps)


def format_nested_toggles_data(nested_toggles_data):
    nested_toggles = nested_toggles_data["nested_toggles"]
    formatted_toggles = defaultdict(list)

    for toggle, file_map in nested_toggles.items():
        for file_path, fn_map in file_map.items():
            formatted_toggles[toggle].append({
                "file": file_path,
                "Functions": [
                    {
                        fn_name: sorted(data["dependencies"])
                        for fn_name, data in fn_map.items()
                    }
                ]
            })

    return {
        "toggles": dict(formatted_toggles),
        "qty": len(formatted_toggles)
    }
