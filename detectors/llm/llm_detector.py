"""
LLM-based pattern classification.

Takes the structured output from llm_analyzer.analyze_project() and classifies
it into the same five patterns as the regex pipeline:
  spread, dead, nested, enum, mixed

Output format matches the regex pipeline exactly so both branches are comparable.
"""
import os
from collections import defaultdict

from detectors.llm import llm_extractor, llm_analyzer
from detectors.file_filter import is_test_file, is_generated_or_vendor_file


def _empty_result(t_usage):
    if t_usage in ("spread", "enum"):
        return {"toggles": {}, "qty": 0}
    if t_usage == "dead":
        return {"toggles": [], "qty": 0}
    if t_usage == "nested":
        return {"nested_toggles": [], "qty": 0}
    if t_usage == "mixed":
        return {"mixed_toggles": {}, "qty": 0}
    return {}


# ---------------------------------------------------------------------------
# pattern classifiers
# ---------------------------------------------------------------------------

def _classify_spread(toggle_list, all_analyses, config_set):
    """Toggle used in >1 production file (excludes test, generated, vendor, config)."""
    toggle_files = defaultdict(list)

    for file_path, file_data in all_analyses.items():
        if file_path in config_set:
            continue
        if is_test_file(file_path) or is_generated_or_vendor_file(file_path):
            continue
        rel = os.path.relpath(file_path)
        for toggle, data in file_data.items():
            via = data.get("via_alias", False)
            fns = data.get("functions", [])
            toggle_files[toggle].append({
                "file": rel,
                "via_alias": via,
                "aliases_used": data.get("aliases", []),
                "Functions": [{fn: 1 for fn in fns}] if fns else [{}],
                "count": len(fns) if fns else 1,
            })

    spread = {
        toggle: entries
        for toggle, entries in toggle_files.items()
        if len({e["file"] for e in entries}) > 1
    }
    return {"toggles": spread, "qty": len(spread)}


def _classify_dead(toggle_list, all_analyses):
    """Toggle defined in config but not found in any code file."""
    found = set()
    for file_data in all_analyses.values():
        found.update(file_data.keys())

    dead = sorted(t for t in toggle_list if t not in found)
    return {"toggles": dead, "qty": len(dead)}


def _classify_nested(toggle_list, all_analyses):
    """Two or more toggles co-located in the same function/block (production files only)."""
    nested = []

    for file_path, file_data in all_analyses.items():
        if is_test_file(file_path) or is_generated_or_vendor_file(file_path):
            continue
        rel = os.path.relpath(file_path)
        # Collect co-location pairs reported by LLM
        seen_pairs = set()
        for toggle, data in file_data.items():
            fns = data.get("functions", [])
            fn_name = fns[0] if fns else "unknown"
            for other in data.get("co_located_with", []):
                pair = tuple(sorted([toggle, other]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    nested.append({
                        "toggles": list(pair),
                        "file": rel,
                        "function": fn_name,
                    })

    return {"nested_toggles": nested, "qty": len(nested)}


def _classify_enum(toggle_list, all_analyses):
    """Toggle used as enum member or switch/match case (production files only)."""
    result = defaultdict(list)

    for file_path, file_data in all_analyses.items():
        if is_test_file(file_path) or is_generated_or_vendor_file(file_path):
            continue
        rel = os.path.relpath(file_path)
        for toggle, data in file_data.items():
            patterns = data.get("patterns", [])
            if any(p in ("enum_member", "switch_case") for p in patterns):
                fns = data.get("functions", [])
                result[toggle].append({
                    "file": rel,
                    "Functions": [{fn: 1 for fn in fns}] if fns else [{}],
                    "count": len(fns) if fns else 1,
                })

    return {"toggles": dict(result), "qty": sum(len(v) for v in result.values())}


def _classify_mixed(toggle_list, all_analyses):
    """Toggle used as condition_check in some file(s) AND assignment in others (production files only)."""
    # Aggregate all patterns seen per toggle across production files only
    toggle_all_patterns = defaultdict(set)
    toggle_files_by_pattern = defaultdict(lambda: defaultdict(list))

    for file_path, file_data in all_analyses.items():
        if is_test_file(file_path) or is_generated_or_vendor_file(file_path):
            continue
        rel = os.path.relpath(file_path)
        for toggle, data in file_data.items():
            for p in data.get("patterns", []):
                toggle_all_patterns[toggle].add(p)
                toggle_files_by_pattern[toggle][p].append(rel)

    result = defaultdict(list)
    for toggle, patterns in toggle_all_patterns.items():
        if "condition_check" in patterns and "assignment" in patterns:
            # Collect all files where either pattern appears
            files_seen = set()
            for p in ("condition_check", "assignment"):
                for f in toggle_files_by_pattern[toggle][p]:
                    files_seen.add(f)
            for f in files_seen:
                result[toggle].append({"file": f, "count": 1})

    return {"mixed_toggles": dict(result), "qty": sum(len(v) for v in result.values())}


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def llm_detect(lang, code_files, t_config_files, t_usage, llm_model=None):
    """
    Main entry point for LLM-based toggle detection.
    Mirrors the signature of the regex-based t_utils.detect().
    llm_model overrides the default model in llm_config.py when provided.
    """
    print(f"\n[LLM] Extracting toggles from {len(t_config_files)} config file(s)...")
    toggle_list = llm_extractor.extract_toggles_llm(t_config_files, model=llm_model)
    print(f"[LLM] Extracted {len(toggle_list)} toggle(s): "
          f"{toggle_list[:6]}{'...' if len(toggle_list) > 6 else ''}")

    if not toggle_list:
        print("[LLM] No toggles found — returning empty result.")
        return _empty_result(t_usage)

    print(f"\n[LLM] Analyzing {len(code_files)} code file(s) for pattern: {t_usage}")
    all_analyses, alias_map = llm_analyzer.analyze_project(code_files, toggle_list, lang, model=llm_model)

    if alias_map:
        print(f"[LLM] Alias map: { {t: v for t, v in list(alias_map.items())[:4]} }")

    config_set = set(t_config_files)

    if t_usage == "spread":
        result = _classify_spread(toggle_list, all_analyses, config_set)
    elif t_usage == "dead":
        result = _classify_dead(toggle_list, all_analyses)
    elif t_usage == "nested":
        result = _classify_nested(toggle_list, all_analyses)
    elif t_usage == "enum":
        result = _classify_enum(toggle_list, all_analyses)
    elif t_usage == "mixed":
        result = _classify_mixed(toggle_list, all_analyses)
    else:
        print(f"[LLM] Unsupported pattern: {t_usage}")
        result = _empty_result(t_usage)

    print(f"[LLM] Done. qty = {result.get('qty', '?')}")
    return result
