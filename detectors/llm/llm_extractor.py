"""
LLM-based toggle name extraction from config/source files.
Replaces the regex-based toggle_extractor for the --llm pipeline.
"""
import json
import re
import os
import signal
import ollama
from detectors.llm.llm_config import OLLAMA_MODEL, MAX_FILE_CHARS

_LLM_TIMEOUT = 90

# Cache: tuple(sorted(config_files)) → toggle_list
# Avoids re-calling the LLM extractor for every pattern when config files are identical.
_extractor_cache = {}


class _LLMTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _LLMTimeout()


def _parse_json_array(text):
    """Robustly extract a JSON array from LLM response text."""
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "toggles" in data:
            return data["toggles"]
    except json.JSONDecodeError:
        pass

    match = re.search(r'\[[\s\S]*?\]', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Fall back: parse each non-empty line as a toggle name
    toggles = []
    for line in text.splitlines():
        line = re.sub(r'^[\s\-\*\d\.]+', '', line).strip()
        line = re.sub(r'^[`"\']|[`"\']$', '', line).strip()
        if line and 2 < len(line) <= 120 and not line.startswith(('#', '//', '{')):
            toggles.append(line)
    return toggles


def extract_toggles_llm(config_files, model=None):
    """
    Extract feature toggle names from config/source files using LLM.
    Returns a deduplicated list of toggle name strings.
    """
    if model is None:
        model = OLLAMA_MODEL

    cache_key = tuple(sorted(config_files))
    if cache_key in _extractor_cache:
        cached = _extractor_cache[cache_key]
        print(f"  [LLM extractor] toggle list cached ({len(cached)} toggle(s))")
        return cached

    all_toggles = []

    for config_file in config_files:
        if not os.path.isfile(config_file):
            continue

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(config_file, 'r', encoding='ISO-8859-1') as f:
                content = f.read()

        snippet = content[:MAX_FILE_CHARS]

        prompt = (
            "You are analyzing source code to find feature toggle / feature flag names.\n\n"
            "A feature toggle is a named identifier that controls whether a feature is "
            "enabled or disabled. Common forms:\n"
            "  - ALL_CAPS constants  (e.g. ENABLE_NEW_UI, DISABLE_FAST_JSON)\n"
            "  - CamelCase enum members  (e.g. EnableFastJson, DisableCache)\n"
            "  - String keys  (e.g. \"feature.x.enabled\", \"enable_new_feature\")\n\n"
            "File content:\n"
            "```\n"
            f"{snippet}\n"
            "```\n\n"
            "Return ONLY a JSON array of the toggle names found, exactly as they appear "
            "in the code. Example: [\"TOGGLE_A\", \"TOGGLE_B\"]\n"
            "If none found, return: []"
        )

        signal.signal(signal.SIGALRM, _alarm_handler)
        signal.alarm(_LLM_TIMEOUT)
        try:
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0},
            )
            signal.alarm(0)
            raw = response["message"]["content"]
            toggles = _parse_json_array(raw)
            valid = [str(t).strip() for t in toggles if t and isinstance(t, str) and len(t.strip()) > 2]
            all_toggles.extend(valid)
            print(f"  [LLM extractor] {os.path.basename(config_file)}: {len(valid)} toggle(s) found")
        except _LLMTimeout:
            print(f"  [LLM extractor] timeout ({_LLM_TIMEOUT}s) for {config_file} — skipping")
        except Exception as exc:
            signal.alarm(0)
            print(f"  [LLM extractor] failed for {config_file}: {exc}")

    result = list(set(filter(None, all_toggles)))
    _extractor_cache[cache_key] = result
    return result
