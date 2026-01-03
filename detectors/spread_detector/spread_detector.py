from collections import defaultdict
import re
from .. import helper


def find_toggles_in_code_files(code_files, toggles):
    toggle_lookup = defaultdict(list)

    for code_file in code_files:
        with open(code_file, 'rb') as file:
            try:
                content = file.read().decode('utf-8')
                for toggle in toggles:
                    if toggle in content:
                        toggle_lookup[toggle].append((code_file, content))
            except UnicodeDecodeError:
                pass

    return toggle_lookup

def filter_spread_toggles(toggle_lookup):
    return {toggle: count for toggle, count in toggle_lookup.items() if len(count) > 1}


def find_parent_toggles(spread_toggles, lang):
    toggle_parent_patterns = helper.get_spread_toggle_var_patterns(lang)['parent_finder']
    toggles = defaultdict(list)

    for toggle, contents in spread_toggles.items():
        parent_list = find_parents_for_toggle(toggle, contents, toggle_parent_patterns, lang)
        if parent_list:
            toggles[toggle].extend(list(dict.fromkeys(parent_list)))

    return {t: v for t, v in toggles.items() if len(v) > 1}


def find_parents_for_toggle(toggle, contents, toggle_parent_patterns, lang):
    parent_list = []
    for content in contents:
        for pattern in toggle_parent_patterns:
            p = format_pattern(pattern, toggle)
            matches = re.findall(p, content[1])

            if len(matches) > 0 and (matches[0], helper.getFileName(lang, content[0])) not in parent_list:
                parent_list.append((matches[0], helper.getFileName(lang, content[0])))
            elif len(matches) == 0 and ("", helper.getFileName(lang, content[0])) not in parent_list:
                parent_list.append(("", helper.getFileName(lang, content[0])))
    return parent_list


def format_pattern(pattern, toggle):
    try:
        return pattern % toggle
    except Exception:
        return pattern


def format_spread_toggles(parent_toggles):
    parent_toggles.sort()
    return {
        "toggles": parent_toggles,
        "qty": len(parent_toggles)
    }
