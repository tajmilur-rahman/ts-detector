import re
import os
from detectors.regex.regex_config import spread_toggle_patterns
from detectors.toggle_match_utils import normalize_extractor_lang

comment_regexes = {
    'python': r'^\s*#.*$',
    'csharp': r'^\s*//.*$',
    'java': r'^\s*//.*$',
    'golang': r'^\s*//.*$',
    "c++": r'^\s*//.*$',
    "config": r'^\s*[#!;].*$'
}

general_regexes = {
    'python': {
        'declare': r'(?P<toggle>\w+)\s*(?:\:\s*(?P<type>[^\s=]+))?\s*=\s*',
        # (?<![.:]) excludes qualified access like Module.MY_FLAG (not a definition)
        'capital_identifiers': r'(?<![.:])\b(?P<toggle>[A-Z][A-Z0-9_-]{2,})\b',
        'dict_keys': r'[{,]\s*(?P<toggle>(?:[\'\"][^\'\"]*[\'\"]|[^:]+?))\s*:',
        'enum_names': r'class\s+(?P<toggle>\w+)\(Enum\):',
        # Extracts only the member name from Class.member access (e.g. Config.enable_feature).
        # Negative lookahead excludes plain method calls like Obj.method().
        'qualified_member_access': r'\b[A-Z][a-zA-Z0-9_]*\.(?P<toggle>[a-zA-Z][a-zA-Z0-9_]{2,})\b(?!\s*\()',
    },
    'csharp': {
        'declare': (
            r'(public|protected|private\s+protected|private)\s+(?:static\s+|const\s+|readonly\s+)*(\w+(?:\s*<[^>]+>)?)\s+(?P<toggle>\w+)\s*(?=\s*(=|;|\[))'
        ),
        'capital_identifiers': r'(?<![.:])\b(?P<toggle>[A-Z][A-Z0-9_-]{2,})\b',
        'dict_keys': r'[{,]\s*(?P<toggle>(?:@"[^"]*"|"[^"]*"|\'[^\']*\'|[^,\s]+?))\s*,',
        'enum_names': r'enum\s+(?P<toggle>\w+)\s*',
        # Extracts the member name from PascalCase.PascalCase access (e.g. FeatureFlags.EnableNewUX).
        # Requires ≥3 chars on each side to avoid short noise.
        'qualified_member_access': r'\b[A-Z][a-zA-Z0-9_]{2,}\.(?P<toggle>[A-Z][a-zA-Z0-9_]{2,})\b(?!\s*\()',
    },
    'java': {
        'declare': (
            r'(public|protected|private)\s+'
            r'(?:static\s+|final\s+|volatile\s+|transient\s+)*'
            r'(?P<type>\w+(?:\s*<[^>]+>)?)\s+'
            r'(?P<toggle>\w+)\s*'
            r'(?=\s*(=|;|\[))'
        ),
        'getter_method': r'\b\w+\.\w+\((?P<toggle>.*?)\)',
        'method_call': r'(?P<toggle>[a-zA-Z0-9_]+)\s*=\s*\w+\.\w+\((.*?)\)',
        'field_access': r'\b[A-Za-z0-9_]+::(?P<toggle>\w+)\b',
        'interface_declaration': r'boolean\s+(?P<toggle>[a-zA-Z0-9_]+)\(\);',
        'capital_identifiers': r'(?<![.:])\b(?P<toggle>[A-Z][A-Z0-9_-]{2,})\b',
        'dict_keys': r'\bput\s*\(\s*(?P<toggle>"[^"]*"|\'[^\']*\'|[^,\s]+?)\s*,',
        'enum_names': r'enum\s+(?P<toggle>\w+)\s*',
        # Extracts only the member name from UpperClass.lowerMember access (e.g. Flags.recursive).
        # Negative lookahead excludes method calls. .class suffix filtered by no_invalid_chars.
        'qualified_member_access': r'\b[A-Z][a-zA-Z0-9_]*\.(?P<toggle>[a-z][a-zA-Z0-9_]{2,})\b(?!\s*\()',
    },
    'golang': {
        'declare': (
            r'(?:var\s+(?P<toggle>\w+)\s*(?:\s+(?P<type>[^\s=]+))?\s*(?:=\s*.*)?|'
            r'(?P<toggle2>\w+)\s*(?:\s+(?P<type2>[^\s=]+))?\s*:=\s*.*)'
        ),
        'toggle_usage': r'\b(?P<toggle>\w+)\b(?=\s*[=:\(\{\},])',
        'toggle_in_condition': r'(?P<toggle>\w+)\b(?=.*?\()',
        'struct_declaration': r'\b(?:bool|int|string|float64)\s+(?P<toggle>\w+)',
        'declare2': r'\s+(?P<toggle>\w+)\s* =',
        'capital_identifiers': r'(?<![.:])\b(?P<toggle>[A-Z][A-Z0-9_-]{2,})\b',
        'dict_keys': r'[{,]\s*(?P<toggle>(?:`[^`]*`|"[^"]*"|\'[^\']*\'|[\w.]+?))\s*:',
        'enum_names': r'type\s+(?P<toggle>\w+)\s+int\s*'
    },
    "c++": {
        'declare': (
            r'(?:(?:const|static|volatile|extern|mutable)\s+)*'
            r'(?P<type>(?:[\w:]+)(?:\s*<[^>;]+>)?'
            r'(?:\s*::\s*[\w:]+)*(?:\s*[\*&])?)\s+'
            r'(?P<toggle>\w+)\s*'
            r'(?=\s*(=|;|\[))'
        ),
        'capital_identifiers': r'(?<![.:])\b(?P<toggle>[A-Z][A-Z0-9_-]{2,})\b',
        'dict_keys': r'[{,]\s*(?P<toggle>(?:"[^"]*"|\'[^\']*\'|[^,\s]+?))\s*,',
        'toggle_names': r'(Feature)?(Toggle|Flag|Enable|Disable)?\w*::(?P<toggle>\w+),',
        'enum_names': r'enum\s+(?P<toggle>\w+)\s*',
        # Extracts only the member name from UpperClass::member access (e.g. Feature::kEnableX).
        # Outer name must start uppercase to exclude std::, boost:: etc.
        'qualified_scoped_access': r'\b[A-Z][a-zA-Z0-9_]+::(?P<toggle>[a-zA-Z_][a-zA-Z0-9_]{2,})\b(?!\s*\()',
    },
    "config": {
        'toggle_definition': r'^\s*(?P<toggle>[a-zA-Z0-9._-]+)\s*=\s*.*$',
        'toggle_colon_definition': r'^\s*(?P<toggle>[a-zA-Z0-9._-]+)\s*:\s*.*$',
        'capital_identifiers': r'(?P<toggle>[A-Z][A-Z0-9._-]{2,})',
    }
}

_COMPILED_REGEXES = {
    lang: {name: re.compile(pattern) for name, pattern in patterns.items()}
    for lang, patterns in general_regexes.items()
}

# Identifiers that are language keywords or structural tokens, never enum constants.
_ENUM_CONST_STOPWORDS = frozenset({
    'public', 'private', 'protected', 'static', 'final', 'abstract',
    'override', 'Override', 'new', 'extends', 'implements', 'throws',
    'return', 'void', 'int', 'long', 'boolean', 'float', 'double',
    'char', 'byte', 'short', 'String', 'Object', 'null', 'true',
    'false', 'this', 'super', 'class', 'interface', 'enum', 'import',
    'package', 'default', 'switch', 'case', 'break', 'continue',
    # C++ / C# extras
    'const', 'constexpr', 'auto', 'typename', 'namespace', 'using',
    'struct', 'union', 'typedef', 'internal', 'sealed', 'readonly',
    'var', 'get', 'set', 'event', 'delegate', 'async', 'await',
})

_ENUM_BODY_RE = re.compile(r'\benum\s+\w+\s*\{([^}]+)\}', re.DOTALL)


def _extract_enum_constants(content, lang):
    """Extract individual enum constant names from enum body declarations.

    This separate extraction path is needed because enum constants used as
    feature flags are often short (e.g. 'recursive', 'revert') and would be
    dropped by the standard length filter applied to other patterns.
    Applies to Java, C#, and C++ only.
    """
    if lang not in ('java', 'csharp', 'c++'):
        return []
    constants = []
    for body_match in _ENUM_BODY_RE.finditer(content):
        body = body_match.group(1)
        # Constants appear before the first ';' which starts the methods section
        semi_pos = body.find(';')
        const_section = body[:semi_pos] if semi_pos != -1 else body
        # Strip comments and annotations before splitting
        const_section = re.sub(r'//[^\n]*', '', const_section)
        const_section = re.sub(r'/\*.*?\*/', '', const_section, flags=re.DOTALL)
        const_section = re.sub(r'@\w+(?:\s*\([^)]*\))?', '', const_section)
        const_section = re.sub(r'\([^)]*\)', '', const_section)
        for part in const_section.split(','):
            part = part.strip()
            # Skip parts with '=' (e.g. MAX_VALUE = LAST — sentinel values, not toggles)
            if '=' in part:
                continue
            if (re.fullmatch(r'[a-zA-Z_]\w*', part)
                    and part not in _ENUM_CONST_STOPWORDS
                    and len(part) >= 2):
                constants.append(part)
    return constants


language_keywords = {
    'python': ['__', '__main__', 'True', 'False', 'None', 'async', 'await', 'self', '"true"', '"false"', '__name__', '"CRITICAL"', '"ERROR"', '"WARNING"', '"INFO"'],
    'csharp': ['public', 'private', 'protected', 'const', 'static', 'readonly', 'string', 'Dictionary', 'List', 'bool',
               '"true"', '"false"', '"CRITICAL"', '"ERROR"', '"WARNING"', '"INFO"'],
    'java': ['public', 'private', 'protected', 'static', 'final', 'volatile', 'transient', 'String', 'Map', 'List',
             'boolean', '"true"', '"false"', '"CRITICAL"', '"ERROR"', '"WARNING"', '"INFO"'],
    'golang': ['var', 'const', 'func', 'int', 'string', 'bool', 'map', '"true"', '"false"', 'err', 'ok', '"CRITICAL"', '"ERROR"', '"WARNING"', '"INFO"'],
    "c++": ['const', 'static', 'public', 'private', 'protected', 'bool', 'int', 'float', 'double', 'std', '"true"',
            '"false"', '"CRITICAL"', '"ERROR"', '"WARNING"', '"INFO"'],
    "config": ['true', 'false', 'null', 'none', 'undefined', 'enabled', 'disabled'],  
}


def is_pure_number_or_dash_underscore(toggle):
    return bool(re.fullmatch(r'"?\d+([-_\.]\d+)*"?', toggle))


def no_invalid_chars(toggle):
    invalid_chars = ['(', ')', '{', '}', '[', ']', '|', '\\', ';', '<', '>', ' ', '!', '@', 'https://', 'http://',
                     'localhost:']
    for char in invalid_chars:
        if char in toggle:
            return False
    # Java reflection suffix (e.g. SomeClass.class) is never a toggle name
    if toggle.endswith('.class'):
        return False
    return True


def larger_is_from_toggle(content, var_a, var_b):
    pattern = rf'\b{re.escape(var_a)}\s*=\s*[\s\S]*?{re.escape(var_b)}[\s\S]*?;'
    matches = re.findall(pattern, content)
    return len(matches) > 0


def filter_substrings(toggles, config_file_contents):
    toggles = sorted(toggles, key=len, reverse=True)
    filtered_toggles = []
    seen = set()
    for toggle in toggles:
        flag = True
        for larger_toggle in toggles:
            if toggle in larger_toggle and toggle != larger_toggle:
                if _has_standalone_toggle(config_file_contents, toggle):
                    flag = True
                else:
                    flag = False
                    content = config_file_contents.replace(larger_toggle, "")
                    if (toggle in content
                            and not larger_is_from_toggle(config_file_contents, larger_toggle, toggle)
                            and toggle not in seen):
                        filtered_toggles.append(toggle)
                        seen.add(toggle)
        if flag and toggle not in seen:
            filtered_toggles.append(toggle)
            seen.add(toggle)
    return filtered_toggles

def _has_standalone_toggle(config_file_contents, toggle):
    pattern = re.compile(rf'\b{re.escape(toggle)}\b')
    return bool(pattern.search(config_file_contents))


def extract_value_for_toggle(toggle, config_file_contents):
    # Use =(?!=) to match assignment '=' but not comparison '=='
    assignment_pattern = re.compile(rf'{re.escape(toggle)}[^=\n]*=(?!=)\s*(.+)\n')
    match = assignment_pattern.search(config_file_contents)

    if match:
        value = match.group(1).strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')):
            value = value[1:-1]
        return value

    # Colon-style (YAML/properties): require toggle at start of line to avoid ternary ':'
    assignment_pattern = re.compile(rf'^\s*{re.escape(toggle)}\s*:\s*(.+)\n', re.MULTILINE)
    match = assignment_pattern.search(config_file_contents)
    if match:
        value = match.group(1).strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')):
            value = value[1:-1]
        return value

    return None


def filter_wrong_values(toggles, config_file_contents):
    dict_or_list_pattern = r'[\{\[\(]'
    ip_address_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    percentage_pattern = r'\b\d+%+'
    url_pattern = r'(https?://[^\s]+)'
    directory_pattern = r'([a-zA-Z]:\\|\/)[^<>:"|?*]+(?:\\|\/)[^<>:"|?*]*'
    language_code_pattern = r'\b[a-z]{2}\b'
    None_pattern = r'None|Null|none|null|undefined'
    function_call_pattern = r'\w+\s*\(.*'


    filtered_toggles = []
    for toggle in toggles:
        value = extract_value_for_toggle(toggle, config_file_contents)
        if value:
            stripped_value = value.strip().strip('"').strip("'")
            # Short boolean-like RHS values are valid toggles (e.g. on/off/true).
            if len(stripped_value) <= 5 and stripped_value.lower() in {
                "on", "off", "true", "false", "yes", "no", "1", "0",
            }:
                filtered_toggles.append(toggle)
                continue
            if (not re.search(dict_or_list_pattern, value) and
                    not re.search(ip_address_pattern, value) and
                    not re.search(percentage_pattern, value) and
                    not re.search(url_pattern, value) and
                    not re.search(directory_pattern, value) and
                    not (len(stripped_value) == 2 and re.search(language_code_pattern, value)) and
                    not re.search(None_pattern, value)) or re.search(function_call_pattern, value):
                filtered_toggles.append(toggle)
        else:
            filtered_toggles.append(toggle)

    return filtered_toggles


def clean_and_remove_duplicates(var_names):
    """
    This function aims finding same toggle that named in different format(camel case vs snake case etc.)
    It will only remove the string version of the toggle, since we can not determine which is primary

    Parameters:
    - var_names (list): A list of variable names, which could be normal names or strings in quotes.

    Returns:
    - list: A new list of variable names, excluding the quoted strings that were part of another name.
    """
    def clean_string(s):
        return s.replace(" ", "").replace("-", "").replace("_", "").lower()

    cleaned_names = []
    to_remove = set()

    for var in var_names:
        if var.startswith(("'", '"')) and var.endswith(("'", '"')):
            quoted_content = var[1:-1]
            cleaned_quoted = clean_string(quoted_content)

            for other_var in var_names:
                if var != other_var:
                    cleaned_other = clean_string(other_var)
                    if cleaned_quoted in cleaned_other:
                        to_remove.add(var)
                        break
        cleaned_names.append(var)

    final_list = [var for var in var_names if var not in to_remove]
    return final_list

def filter_toggles(toggles, language, file_contents):
    keywords = language_keywords.get(language, [])
    filtered_toggles = [t for t in toggles if t is not None and t != ""]

    filtered_toggles = [t for t in filtered_toggles if no_invalid_chars(t)]

    filtered_toggles = [t for t in filtered_toggles if not is_pure_number_or_dash_underscore(t)]

    filtered_toggles = [t for t in filtered_toggles if len(t) > 10]
    filtered_toggles = [t for t in filtered_toggles if (t[0] == '\"' and t[-1] == '\"' and len(t) >= 10) or (t[0] != '\"' or t[-1] != '\"')]
    filtered_toggles = [t for t in filtered_toggles if t not in keywords]
    filtered_toggles = filter_substrings(filtered_toggles, file_contents)
    filtered_toggles = filter_wrong_values(filtered_toggles, file_contents)
    filtered_toggles = clean_and_remove_duplicates(filtered_toggles)

    if language == "config":
    # Skip length and invalid char checks for config files
        filtered_toggles = [t for t in filtered_toggles if t not in keywords]

    return filtered_toggles


def apply_combined_regexes(combined_content, language):
    toggles = set()
    patterns = _COMPILED_REGEXES.get(language)
    if not patterns:
        return toggles
    for name, compiled_pattern in patterns.items():
        for match in compiled_pattern.finditer(combined_content):
            gd = match.groupdict()
            toggle = gd.get('toggle') or gd.get('toggle2')
            if not toggle:
                continue
            # getter_method captures method arguments; skip unquoted qualified
            # names (e.g. Flags.revert) since qualified_member_access handles those.
            if name == 'getter_method' and '.' in toggle and not toggle[0] in ('"', "'"):
                continue
            toggles.add(toggle)
    return toggles


def get_language_from_extension(file_path):
    if file_path.endswith('.py'):
        return 'python'
    elif file_path.endswith('.cs'):
        return 'csharp'
    elif file_path.endswith('.java'):
        return 'java'
    elif file_path.endswith('.go'):
        return 'golang'
    elif file_path.endswith('.cpp') or file_path.endswith('.cc'):
        return "c++"
    return None


def remove_comments(content, language):
    """Remove comment lines based on the language."""
    comment_pattern = comment_regexes.get(language)
    # Remove single-line comments
    if comment_pattern:
        content = re.sub(comment_pattern, '', content, flags=re.MULTILINE)

    # Remove block comments (/* ... */)    
    if language in ['java', 'csharp', 'c++', 'golang', 'c']:
        content = re.sub(r'/\*[\s\S]*?\*/', '', content, flags=re.MULTILINE)
    return content

def extract_toggles_from_config_files(config_files, lang=None):
    """
    Extracts toggles from configuration files or language-specific files.
    Handles both config-specific cases (e.g., properties, conf) and language-specific files.
    """
    toggle_list = []

    for conf_file in config_files:
        if not os.path.isfile(conf_file):
            print(f"Skipping invalid or non-file path: {conf_file}")
            continue

        with open(conf_file, 'r', encoding='utf-8') as file:
            file_content = file.read()

        # Determine the language if not explicitly provided
        file_lang = normalize_extractor_lang(lang or get_language_from_extension(conf_file))

        # Remove comments based on the file type
        file_content = remove_comments(file_content, file_lang)

        # Apply regex patterns to extract toggles
        combined_toggles = apply_combined_regexes(file_content, file_lang)

        # Filter toggles to remove invalid entries
        filtered_toggles = filter_toggles(
            list(combined_toggles), file_lang, file_contents=file_content
        )
        toggle_list.extend(filtered_toggles)

        # Extract enum constants directly from enum bodies — these bypass the
        # standard length filter because enum flag names are often short.
        lang_kws = set(language_keywords.get(file_lang, []))
        for const in _extract_enum_constants(file_content, file_lang):
            if const not in lang_kws and no_invalid_chars(const):
                toggle_list.append(const)

    # Remove duplicates and invalid toggles
    return list(set(filter(None, toggle_list)))

if __name__ == "__main__":
    # config_files_path = "../getToggleTests/example-config-files/cadence-constants.go"
    # config_files_path = "../getToggleTests/example-config-files/chrome-feature.cc"
    config_files_path = "../toggle_extractor/example-config-files/dawn-toggles.cpp"
    # config_files_path = "../toggle_extractor/example-config-files/opensearch-FeatureFlags.java"
    # config_files_path = "../getToggleTests/example-config-files/pytorch-proxy.py"
    # config_files_path = "../getToggleTests/example-config-files/sdb2-feature.java"
    # config_files_path = "../toggle_extractor/example-config-files/sentry-server.py"
    # config_files_path = "../toggle_extractor/example-config-files/temporal-constants.go"
    # config_files_path = "../getToggleTests/example-config-files/vtest-FeatureFlag.cs"
    # config_files_path = "../getToggleTests/example-config-files/vtest-FeatureFlag.cs"
    # config_files_path = "../toggle_extractor/example-config-files/sentry-temporary.py"
    config_files = [config_files_path]

    extracted_toggles = extract_toggles_from_config_files(config_files)

    print("Extracted Toggles:", extracted_toggles)
    print("Extracted Toggles length:", len(extracted_toggles))
