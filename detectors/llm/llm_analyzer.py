"""
LLM-based code file analysis with iterative alias tracking.

Pass 1 — direct detection:
  For every code file that contains at least one toggle name (quick grep),
  ask the LLM which toggles are used and whether any variable/property stores
  a toggle value (alias).

  Small files (≤ MAX_FILE_CHARS): analysed as a whole.
  Large files: chunked by function boundaries via tree-sitter so no code is
  ever skipped. Class-level code (outside any function) is also checked.

Pass 2+ — indirect/alias detection (iterative, up to MAX_ALIAS_HOPS):
  Build a reverse alias map from the previous pass.
  For files that contain an alias name but have not been analysed yet,
  ask the LLM to confirm the indirect usage and collect any new aliases.
  Repeat until no new aliases are found (converges) or the hop cap is reached.

Returns:
  all_analyses  — {file_path: {toggle_name: {functions, aliases, patterns, co_located_with}}}
  alias_map     — {toggle_name: [alias_var_names]}
"""
import json
import re
import os
import ollama

from detectors.llm.llm_config import OLLAMA_MODEL, MAX_FILE_CHARS, MAX_TOGGLES_PER_PROMPT

MAX_ALIAS_HOPS = 3

# Mapping from CLI lang names to the keys expected by function_utils.extract_functions
_LANG_KEY_MAP = {
    "golang": "go",
    "go":     "go",
    "c++":    "cpp",
    "cpp":    "cpp",
    "csharp": "csharp",
    "c#":     "csharp",
    "java":   "java",
    "python": "python",
}

_SIMPLE_IDENTIFIER = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


# ---------------------------------------------------------------------------
# file helpers
# ---------------------------------------------------------------------------

def _read_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, 'r', encoding='ISO-8859-1') as f:
            return f.read()
    except Exception:
        return ""


def _parse_json_object(text):
    """Extract the first JSON object from LLM response text."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def _validate_analysis(result, toggle_set):
    """Keep only actual toggle names; normalise value structure."""
    clean = {}
    for toggle, data in result.items():
        if toggle not in toggle_set:
            continue
        if not isinstance(data, dict):
            continue
        # Aliases must be simple identifiers — reject full expressions like
        # `_flag.IsSet(...)` which the LLM sometimes returns incorrectly.
        valid_aliases = [
            str(a) for a in data.get("aliases", [])
            if a and _SIMPLE_IDENTIFIER.match(str(a))
        ]
        clean[toggle] = {
            "functions":        [str(f) for f in data.get("functions", []) if f],
            "aliases":          valid_aliases,
            "patterns":         [str(p) for p in data.get("patterns", []) if p],
            "co_located_with":  [str(t) for t in data.get("co_located_with", [])
                                  if t and t in toggle_set],
        }
    return clean


def _merge_analyses(base, additions):
    """Merge additional per-toggle analysis into base (union of all fields)."""
    for toggle, data in additions.items():
        if toggle not in base:
            base[toggle] = data
        else:
            for field in ("functions", "aliases", "patterns"):
                merged_set = set(base[toggle].get(field, [])) | set(data.get(field, []))
                base[toggle][field] = list(merged_set)
            for other in data.get("co_located_with", []):
                if other not in base[toggle]["co_located_with"]:
                    base[toggle]["co_located_with"].append(other)
    return base


# ---------------------------------------------------------------------------
# LLM prompt builders
# ---------------------------------------------------------------------------

def _direct_prompt(file_label, snippet, toggles_json):
    return (
        "You are analyzing source code for feature toggle usage.\n\n"
        f"Feature toggles to look for: {toggles_json}\n\n"
        "For each toggle USED in this code, return JSON (no explanation, no markdown):\n"
        "{\n"
        "  \"TOGGLE_NAME\": {\n"
        "    \"functions\": [\"name of every function/method where the toggle is used; "
        "use 'class_level' for code outside any function such as field initializers or "
        "static declarations\"],\n"
        "    \"aliases\": [\"simple variable/property identifier that stores this toggle's "
        "value — identifier only, no expressions\"],\n"
        "    \"patterns\": [\"one or more of: condition_check, assignment, enum_member, "
        "switch_case, function_arg\"],\n"
        "    \"co_located_with\": [\"other toggle names from the list used in the same function\"]\n"
        "  }\n"
        "}\n\n"
        "Important rules:\n"
        "- SKIP import / using / require / include / package lines — these are NOT usages.\n"
        "- 'functions' must name every function where the toggle appears. "
        "Use 'class_level' for field initializers or code outside functions.\n"
        "- 'aliases' must be a SIMPLE IDENTIFIER (e.g. 'captureOutput'), NOT a full expression.\n"
        "- For C++ also check: #if BUILDFLAG(TOGGLE), #ifdef TOGGLE, #if defined(TOGGLE).\n"
        "- For Python also check: dict lookups like flags['TOGGLE'] or flags.get('TOGGLE').\n"
        "- For Java/C# also check: enum members, switch/case, and annotations.\n"
        "- Return empty object {} if no listed toggles are actually used here.\n"
        "- Return ONLY valid JSON.\n\n"
        f"Code ({file_label}):\n"
        "```\n"
        f"{snippet}\n"
        "```"
    )


def _function_chunk_prompt(file_label, func_name, snippet, toggles_json):
    return (
        "You are analyzing a single function for feature toggle usage.\n\n"
        f"Function name: {func_name}\n"
        f"Feature toggles to look for: {toggles_json}\n\n"
        "For each toggle USED in this function, return JSON (no explanation, no markdown):\n"
        "{\n"
        "  \"TOGGLE_NAME\": {\n"
        f"    \"functions\": [\"{func_name}\"],\n"
        "    \"aliases\": [\"simple variable identifier that stores this toggle's value\"],\n"
        "    \"patterns\": [\"condition_check|assignment|enum_member|switch_case|function_arg\"],\n"
        "    \"co_located_with\": [\"other toggle names from the list used in this function\"]\n"
        "  }\n"
        "}\n\n"
        "Rules:\n"
        "- SKIP import/using lines.\n"
        "- aliases must be simple identifiers only (no expressions).\n"
        "- For C++ also check: #if BUILDFLAG(TOGGLE), #ifdef TOGGLE.\n"
        "- Return {} if no listed toggles are used here.\n"
        "- Return ONLY valid JSON.\n\n"
        f"Function body ({file_label} → {func_name}):\n"
        "```\n"
        f"{snippet}\n"
        "```"
    )


def _alias_prompt(file_label, snippet, context_json):
    return (
        "You are checking for indirect feature toggle usage via known alias variables.\n\n"
        f"Known aliases (alias_variable → toggle_name): {context_json}\n\n"
        "For each alias that is actually USED in this file (not just declared), "
        "return JSON (no explanation, no markdown):\n"
        "{\n"
        "  \"TOGGLE_NAME\": {\n"
        "    \"functions\": [\"function/method name; 'class_level' if outside any function\"],\n"
        "    \"aliases\": [\"alias_variable_name\"],\n"
        "    \"patterns\": [\"condition_check|assignment|function_arg|etc\"],\n"
        "    \"co_located_with\": []\n"
        "  }\n"
        "}\n\n"
        "Rules:\n"
        "- Only report aliases that are actually READ/USED, not just declared here.\n"
        "- SKIP import/using/include lines.\n"
        "- Return {} if none of the aliases are actually used here.\n"
        "- Return ONLY valid JSON.\n\n"
        f"Code ({file_label}):\n"
        "```\n"
        f"{snippet}\n"
        "```"
    )


# ---------------------------------------------------------------------------
# LLM callers
# ---------------------------------------------------------------------------

def _llm_call(prompt, label, model):
    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0},
        )
        return _parse_json_object(response["message"]["content"])
    except Exception as exc:
        print(f"    [LLM] call failed for {label}: {exc}")
        return {}


# ---------------------------------------------------------------------------
# per-file analysis (small and large)
# ---------------------------------------------------------------------------

def _analyze_small_file(file_path, content, toggle_list, model):
    """Whole-file analysis for files that fit within MAX_FILE_CHARS."""
    toggles_json = json.dumps(toggle_list[:MAX_TOGGLES_PER_PROMPT])
    label = os.path.basename(file_path)
    prompt = _direct_prompt(label, content, toggles_json)
    return _llm_call(prompt, label, model)


def _analyze_large_file(file_path, content, toggle_list, lang, model):
    """
    Chunk by function boundaries (tree-sitter) so no code is ever skipped.
    Falls back to overlapping character chunks if tree-sitter fails.
    """
    from function_utils import extract_functions

    label = os.path.basename(file_path)
    toggles_json = json.dumps(toggle_list[:MAX_TOGGLES_PER_PROMPT])
    toggle_set = set(toggle_list)
    merged = {}

    lang_key = _LANG_KEY_MAP.get(lang.lower(), lang.lower())

    try:
        functions = extract_functions(content, lang_key)
    except Exception as exc:
        print(f"      (tree-sitter failed [{exc}], using char chunks)")
        return _analyze_char_chunks(file_path, content, toggle_list, model)

    # ----- analyse each function that mentions a toggle -----
    for fn in functions:
        func_body = content[fn["start_byte"]:fn["end_byte"]]
        func_name = fn["name"]

        if not any(t.lower() in func_body.lower() for t in toggle_list):
            continue

        if len(func_body) > MAX_FILE_CHARS:
            chunk_result = _analyze_char_chunks(
                file_path, func_body, toggle_list, model,
                label=f"{label}/{func_name}"
            )
        else:
            prompt = _function_chunk_prompt(label, func_name, func_body, toggles_json)
            chunk_result = _llm_call(prompt, f"{label}/{func_name}", model)

        clean = _validate_analysis(chunk_result, toggle_set)
        for data in clean.values():
            if func_name not in data.get("functions", []):
                data.setdefault("functions", []).insert(0, func_name)
        merged = _merge_analyses(merged, clean)

    # ----- analyse class-level code (outside all functions) -----
    used_ranges = sorted((fn["start_byte"], fn["end_byte"]) for fn in functions)
    class_parts = []
    prev = 0
    for start, end in used_ranges:
        if start > prev:
            class_parts.append(content[prev:start])
        prev = end
    if prev < len(content):
        class_parts.append(content[prev:])
    class_content = "".join(class_parts).strip()

    if class_content and any(t.lower() in class_content.lower() for t in toggle_list):
        class_result = _analyze_char_chunks(
            file_path, class_content, toggle_list, model,
            label=f"{label}/class_level",
            force_function_name="class_level"
        )
        merged = _merge_analyses(merged, class_result)

    return merged


def _analyze_char_chunks(file_path, content, toggle_list, model,
                          label=None, force_function_name=None):
    """
    Fallback / class-level chunker: overlapping MAX_FILE_CHARS windows.
    `force_function_name` stamps that name into every result's 'functions' list.
    """
    OVERLAP = 500
    label = label or os.path.basename(file_path)
    toggles_json = json.dumps(toggle_list[:MAX_TOGGLES_PER_PROMPT])
    toggle_set = set(toggle_list)
    merged = {}

    start = 0
    chunk_idx = 0
    while start < len(content):
        end = min(start + MAX_FILE_CHARS, len(content))
        chunk = content[start:end]
        chunk_label = f"{label}[chunk{chunk_idx}]"

        prompt = _direct_prompt(chunk_label, chunk, toggles_json)
        raw = _llm_call(prompt, chunk_label, model)
        clean = _validate_analysis(raw, toggle_set)

        if force_function_name:
            for data in clean.values():
                if force_function_name not in data.get("functions", []):
                    data.setdefault("functions", []).insert(0, force_function_name)

        merged = _merge_analyses(merged, clean)

        if end == len(content):
            break
        start = end - OVERLAP
        chunk_idx += 1

    return merged


def _analyze_alias_file(file_path, content, alias_context, model):
    """
    Analyze a file for alias (indirect) usage.
    Handles both small and large files — large files are split into overlapping
    chunks so no code is ever truncated.
    """
    label = os.path.basename(file_path)
    context_json = json.dumps(alias_context)
    toggle_set = set(alias_context.values())

    if len(content) <= MAX_FILE_CHARS:
        prompt = _alias_prompt(label, content, context_json)
        return _llm_call(prompt, label, model)

    # Large file: chunk with overlap and merge results
    OVERLAP = 500
    merged = {}
    start = 0
    chunk_idx = 0
    while start < len(content):
        end = min(start + MAX_FILE_CHARS, len(content))
        chunk = content[start:end]
        chunk_label = f"{label}[alias_chunk{chunk_idx}]"
        prompt = _alias_prompt(chunk_label, chunk, context_json)
        raw = _llm_call(prompt, chunk_label, model)
        clean = _validate_analysis(raw, toggle_set)
        merged = _merge_analyses(merged, clean)
        if end == len(content):
            break
        start = end - OVERLAP
        chunk_idx += 1

    return merged


def _analyze_file(file_path, content, toggle_list, lang, model):
    """Route to whole-file or chunked analysis based on file size."""
    if len(content) <= MAX_FILE_CHARS:
        return _analyze_small_file(file_path, content, toggle_list, model)
    print(f"      (large file: {len(content):,} chars — chunking by function boundaries)")
    return _analyze_large_file(file_path, content, toggle_list, lang, model)


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def analyze_project(code_files, toggle_list, lang, model=None):
    """
    Two-pass (iterative) LLM analysis of all code files.

    Pass 1 finds direct toggle references and alias variables.
    Passes 2+ iteratively trace those aliases through files that don't
    mention the toggle directly (up to MAX_ALIAS_HOPS hops).

    Returns:
        all_analyses  {file_path: {toggle: {functions, aliases, patterns, co_located_with}}}
        alias_map     {toggle: [alias_var_names]}
    """
    model = model or OLLAMA_MODEL
    toggle_set = set(toggle_list)
    all_analyses = {}
    alias_map = {}

    # -----------------------------------------------------------------------
    # Pass 1 — direct detection
    # -----------------------------------------------------------------------
    if not toggle_list:
        return all_analyses, alias_map

    quick_pattern = re.compile(
        r'\b(?:' + '|'.join(re.escape(t) for t in toggle_list) + r')\b',
        re.IGNORECASE,
    )

    direct_candidates = []
    for f in code_files:
        content = _read_file(f)
        if content and quick_pattern.search(content):
            direct_candidates.append((f, content))

    print(f"  [LLM analyzer] Pass 1: {len(direct_candidates)}/{len(code_files)} files contain a toggle name")

    for idx, (file_path, content) in enumerate(direct_candidates, 1):
        print(f"    [{idx}/{len(direct_candidates)}] {os.path.basename(file_path)}", end=" ... ", flush=True)
        raw = _analyze_file(file_path, content, toggle_list, lang, model)
        clean = _validate_analysis(raw, toggle_set)
        if clean:
            all_analyses[file_path] = clean
            for toggle, data in clean.items():
                for alias in data.get("aliases", []):
                    alias_map.setdefault(toggle, [])
                    if alias not in alias_map[toggle]:
                        alias_map[toggle].append(alias)
            print(f"found {list(clean.keys())}")
        else:
            print("none")

    # -----------------------------------------------------------------------
    # Pass 2+ — iterative alias / indirect detection
    # Each hop looks for aliases discovered in the PREVIOUS hop that have not
    # been searched yet. Stops when no new aliases are found or the hop cap
    # (MAX_ALIAS_HOPS) is reached.
    # -----------------------------------------------------------------------
    already_analysed = set(all_analyses.keys())
    processed_aliases = set()   # aliases we have already searched for

    for hop in range(1, MAX_ALIAS_HOPS + 1):
        # Collect aliases that haven't been searched yet
        reverse_aliases = {}
        for toggle, aliases in alias_map.items():
            for alias in aliases:
                if alias not in processed_aliases:
                    reverse_aliases[alias] = toggle

        safe_aliases = [a for a in reverse_aliases if _SIMPLE_IDENTIFIER.match(a)]

        if not safe_aliases:
            if hop == 1:
                print("  [LLM analyzer] Pass 2: no simple-identifier aliases, skipping")
            else:
                print(f"  [LLM analyzer] Hop {hop + 1}: no new aliases, stopping")
            break

        processed_aliases.update(safe_aliases)

        alias_quick_pattern = re.compile(
            r'\b(?:' + '|'.join(re.escape(a) for a in safe_aliases) + r')\b'
        )

        alias_candidates = []
        for f in code_files:
            if f in already_analysed:
                continue
            content = _read_file(f)
            if content and alias_quick_pattern.search(content):
                present_aliases = {
                    alias: toggle
                    for alias, toggle in reverse_aliases.items()
                    if alias in safe_aliases
                    and re.search(r'\b' + re.escape(alias) + r'\b', content)
                }
                if present_aliases:
                    alias_candidates.append((f, content, present_aliases))

        pass_label = "Pass 2" if hop == 1 else f"Hop {hop + 1}"
        print(f"  [LLM analyzer] {pass_label}: {len(alias_candidates)} additional files have alias names")

        if not alias_candidates:
            break

        new_aliases_this_hop = False

        for idx, (file_path, content, alias_context) in enumerate(alias_candidates, 1):
            print(f"    [{idx}/{len(alias_candidates)}] {os.path.basename(file_path)}", end=" ... ", flush=True)
            raw = _analyze_alias_file(file_path, content, alias_context, model)
            clean = _validate_analysis(raw, toggle_set)
            if clean:
                for data in clean.values():
                    data["via_alias"] = True
                existing = all_analyses.get(file_path, {})
                existing.update(clean)
                all_analyses[file_path] = existing
                already_analysed.add(file_path)

                # Collect new aliases for the next hop
                for toggle, data in clean.items():
                    for alias in data.get("aliases", []):
                        if alias not in alias_map.get(toggle, []) and alias not in processed_aliases:
                            alias_map.setdefault(toggle, []).append(alias)
                            new_aliases_this_hop = True

                print(f"indirect usage of {list(clean.keys())}")
            else:
                print("none confirmed")

        if not new_aliases_this_hop:
            print(f"  [LLM analyzer] No new aliases after {pass_label}, stopping alias search")
            break

    return all_analyses, alias_map
