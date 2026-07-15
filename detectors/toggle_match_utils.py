"""Shared toggle term matching helpers for spread and nested detectors."""
import re

_STRING_LITERAL_RE = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`'
)


def strip_string_literals(line):
    return _STRING_LITERAL_RE.sub("", line)


def normalize_extractor_lang(lang):
    if not lang:
        return lang
    key = lang.lower()
    if key in ("go", "golang"):
        return "golang"
    if key in ("cpp", "c++"):
        return "c++"
    if key in ("c#", "csharp"):
        return "csharp"
    return key


def normalize_parser_lang(lang):
    key = (lang or "").lower()
    if key in ("c++", "cpp"):
        return "cpp"
    if key in ("c#", "csharp"):
        return "csharp"
    return key


def term_regex_fragment(term):
    escaped = re.escape(term)
    if re.fullmatch(r"[\w]+", term):
        return rf"\b{escaped}\b"
    return rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])"


def build_term_to_toggle_map(toggles, alias_map, global_alias_map=None):
    """Map lowercase matched text to canonical toggle name."""
    term_map = {}
    toggles_lower = {t.lower(): t for t in toggles}

    def register(term, toggle):
        if not term:
            return
        term_map[term.lower()] = toggle

    for toggle in toggles:
        register(toggle, toggle)

    for alias, mapped in alias_map.items():
        for toggle in mapped:
            register(alias, toggle)
            if "." in alias:
                register(alias.split(".")[-1], toggle)
            register(f".{alias}", toggle)

    if global_alias_map:
        for qualified, mapped in global_alias_map.items():
            for toggle in mapped:
                register(qualified, toggle)
                if qualified.startswith("."):
                    register(qualified[1:], toggle)
                if "::" in qualified:
                    register(qualified.split("::")[-1], toggle)
                if "." in qualified:
                    register(qualified.split(".")[-1], toggle)

    return term_map


def build_combined_term_pattern(terms, max_terms=2000):
    if not terms or len(terms) > max_terms:
        return None
    unique = sorted({t for t in terms if t}, key=len, reverse=True)
    if not unique:
        return None
    fragments = [term_regex_fragment(t) for t in unique]
    return re.compile("|".join(fragments), re.IGNORECASE)


def count_terms_in_text(
    text,
    term_map,
    term_pattern=None,
    excluded_positions=None,
    excluded_by_toggle=None,
):
    """
    Count toggle usages in text. Returns dict toggle -> count.
    excluded_positions: line indexes skipped for every toggle.
    excluded_by_toggle: per-toggle alias-definition line indexes to skip.
    """
    global_excluded = excluded_positions or set()
    counts = {}
    lines = text.splitlines() if isinstance(text, str) else text

    for idx, line in enumerate(lines):
        if idx in global_excluded:
            continue
        if _is_comment_line(line):
            continue
        scan_line = strip_string_literals(line)
        if not scan_line.strip():
            continue

        if term_pattern:
            for match in term_pattern.finditer(scan_line):
                matched = match.group(0)
                toggle = term_map.get(matched.lower())
                if not toggle:
                    continue
                if excluded_by_toggle and idx in excluded_by_toggle.get(toggle, set()):
                    continue
                counts[toggle] = counts.get(toggle, 0) + 1
        else:
            scan_lower = scan_line.lower()
            for term_lower, toggle in term_map.items():
                if excluded_by_toggle and idx in excluded_by_toggle.get(toggle, set()):
                    continue
                if term_lower in scan_lower:
                    counts[toggle] = counts.get(toggle, 0) + scan_lower.count(term_lower)

    return counts


def build_quick_filter_pattern(toggles, max_terms=300):
    """Return a fast pre-filter pattern built from toggle name stems.

    A file that matches none of these stems has zero toggle references and can
    skip expensive tree-sitter parsing entirely.
    """
    if not toggles:
        return None
    terms = set()
    for t in toggles:
        t_lower = t.lower()
        terms.add(t_lower)
        for sep in ('.', '::'):
            if sep in t_lower:
                for part in t_lower.split(sep):
                    if len(part) >= 4:
                        terms.add(part)
    escaped = sorted((re.escape(t) for t in terms if t), key=len, reverse=True)[:max_terms]
    if not escaped:
        return None
    return re.compile('|'.join(escaped), re.IGNORECASE)


def _is_comment_line(line):
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(("//", "///", "/*", "*/", "* ", "#")):
        return True
    return False
