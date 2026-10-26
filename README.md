# Toggle Smell Detector
Feature toggles can introduce one of the worst forms of technical debt when not used properly. There are unknown number of toggle usage patterns created by developers in different source code since there is no standard usage patterns. We identified six usage patterns in Google Chromium in a preliminary study. Although, we are not certain yet which toggle usage patterns are to be called as toggle smells, this project is offering a tool to detect toggle usage patterns in different source code.

Following are the usage patterns our tool can detect as of now.

- **Dead**: Declared but never used in code.
- **Spread**: The same toggle appears across multiple files or modules.
- **Nested**: Toggles used within other toggle conditionals.
- **Mixed**: A toggle exhibiting multiple patterns (e.g., dead + nested).
- **Enum**: Toggle that supports multiple states (not just true/false).
- **Combinatorial**: (Under research – not validated).

## Features

- **Supported languages**: Python, Java, C++, C, Go, C#.
- **Patterns detected**: `dead`, `spread`, `nested`, `mixed`, `enum`.
- **Two detection modes**: regex-based (default) and LLM-based (`--llm` flag).
- **Auto-detects programming language**: Automatically identifies the language based on file extension or content.
- **Config paths as relative paths**: Configuration files are provided as paths relative to the source directory.

## Setup

### 1. Clone the repository

```
git clone https://github.com/tajmilur-rahman/toggle-smells.git
cd toggle-smells/ts-detector
```

Or use the installer script (see [One-shot installer](#one-shot-installer) below).

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Build tree-sitter language grammars

```bash
python build_languages.py
```

This creates `build/my-languages.dylib` (macOS), `.so` (Linux), or `.dll` (Windows).

> **macOS**: if the build fails, first run `xcode-select --install`.  
> **Linux**: if the build fails, run `sudo apt-get install -y build-essential cmake`.

### 5. (Optional) Install Ollama for LLM-based detection

LLM mode requires [Ollama](https://ollama.com) running locally with the `qwen2.5-coder:7b` model.

```bash
# Install Ollama (macOS)
brew install ollama

# Pull the model
ollama pull qwen2.5-coder:7b

# Start the Ollama server (keep this running in a separate terminal)
ollama serve
```

Skip this step if you only intend to use the default regex-based detection.

---

## Usage

### Basic Syntax

```bash
python tsd.py -p <source_path> -c <config_path> [options]
```

### Required Arguments

| Flag | Description |
|------|-------------|
| `-p, --source-path` | Path to the source code directory. |
| `-c, --config-path` | Config file path(s), **relative to `source-path`**. Accepts multiple values. |

### Optional Arguments

| Flag | Description |
|------|-------------|
| `-o, --output` | Path to save the output JSON file. Prints to console if omitted. |
| `-t, --toggle-usage` | Pattern to detect: `dead`, `spread`, `nested`, `mixed`, `enum`. Detects all if omitted. |
| `-l, --language` | Programming language. Auto-detected from file extensions if omitted. |
| `--llm` | Use LLM-based detection via Ollama instead of regex. Requires Ollama running locally. |
| `--llm-model` | Ollama model to use. Default: `qwen2.5-coder:7b`. Example: `--llm-model qwen2.5-coder:32b`. |

---

## Examples

### Regex mode (default)

```bash
# Detect all patterns, save output to file
python tsd.py -p /path/to/source \
  -c path/to/config.java \
  -o outputs/result.json

# Detect only the nested pattern in a C++ project
python tsd.py -p /path/to/source \
  -c src/module/Toggles.cpp src/module/Features.cpp \
  -t nested

# Force language
python tsd.py -p /path/to/source \
  -c path/to/config.py \
  -l python -o outputs/result.json
```

### LLM mode (`--llm`)

LLM mode uses a local Ollama model to extract toggle names from config files and analyze each code file for pattern usage. It handles aliases, indirect usages, and large files via tree-sitter chunking.

```bash
# Detect all patterns using LLM (Java project)
python tsd.py -p /path/to/civiform \
  -c server/conf/helper/feature-flags.conf \
  -l java --llm \
  -o outputs/civiform_llm.json

# Use a larger model for better accuracy
python tsd.py -p /path/to/source \
  -c path/to/config \
  --llm --llm-model qwen2.5-coder:32b \
  -o outputs/result.json
```

> **Note**: LLM mode is slower than regex mode (minutes to hours depending on project size). A progress log is printed to the console. For large projects, the first run is slower; subsequent pattern runs in the same process reuse cached grep results.

---

## Sample Commands (Known Repos)

| Project | Language | Command |
|---------|----------|---------|
| [PyViCare](https://github.com/overxfl0w13/PyViCare) | Python | `python tsd.py -p /path/to/PyViCare -c PyViCare/PyViCareUtils.py --llm -l python` |
| [civiform](https://github.com/civiform/civiform) | Java | `python tsd.py -p /path/to/civiform -c server/conf/helper/feature-flags.conf -l java --llm` |
| [etcd](https://github.com/etcd-io/etcd) | Go | `python tsd.py -p /path/to/etcd -c server/features/etcd_features.go -l go --llm` |
| [vstest](https://github.com/microsoft/vstest) | C# | `python tsd.py -p /path/to/vstest -c src/Microsoft.TestPlatform.CoreUtilities/FeatureFlag/FeatureFlag.cs --llm` |
| [OpenSearch](https://github.com/opensearch-project/OpenSearch) | Java | `python tsd.py -p /path/to/OpenSearch -c server/src/main/java/org/opensearch/common/util/FeatureFlags.java server/src/main/java/org/opensearch/common/settings/FeatureFlagSettings.java` |
| [Dawn](https://github.com/google/dawn) | C++ | `python tsd.py -p /path/to/dawn -c src/dawn/native/Toggles.cpp src/dawn/native/Features.cpp` |
| [Temporal](https://github.com/temporalio/temporal) | Go | `python tsd.py -p /path/to/temporal -c common/dynamicconfig/constants.go` |

---

## Output Format

The result is a JSON object printed to the console or saved to a file.

### Regex mode output

```json
{
  "dead": { "toggles": ["TOGGLE_A", "TOGGLE_B"], "qty": 2 },
  "spread": {
    "toggles": {
      "TOGGLE_C": [
        {"file": "path/component/moduleA.py", "count": 3},
        {"file": "path/component/moduleC.py", "count": 1}
      ]
    },
    "qty": 1
  },
  "nested": {
    "nested_toggles": [
      {"toggles": ["TOGGLE_A", "TOGGLE_B"], "file": "src/module.py", "function": "myFunc"}
    ],
    "qty": 1
  },
  "enum": { "toggles": {}, "qty": 0 }
}
```

### LLM mode output

LLM mode produces richer output — each spread entry includes the function name, alias variable(s) used, and whether the detection was via a direct reference or an alias:

```json
{
  "dead": { "toggles": ["TOGGLE_A"], "qty": 1 },
  "spread": {
    "toggles": {
      "TOGGLE_B": [
        {
          "file": "path/to/file.java",
          "via_alias": false,
          "aliases_used": ["aliasVar"],
          "Functions": [{"myFunction": 1}],
          "count": 1
        },
        {
          "file": "path/to/other.java",
          "via_alias": true,
          "aliases_used": ["aliasVar"],
          "Functions": [{"anotherFunction": 1}],
          "count": 1
        }
      ]
    },
    "qty": 1
  },
  "nested": {
    "nested_toggles": [
      {"toggles": ["TOGGLE_B", "TOGGLE_C"], "file": "path/to/file.java", "function": "myFunction"}
    ],
    "qty": 1
  },
  "enum": { "toggles": {}, "qty": 0 }
}
```

---

## Notes on LLM Detection Reliability

- **Dead and spread** detections are backed by a grep pre-filter plus a post-LLM presence check — these are the most reliable patterns.
- **Nested and enum** detections are LLM-interpreted without a secondary mechanical check — treat these as indicative.
- **False negatives are possible** in very large files: the tool chunks large files by function boundary (tree-sitter), but the LLM may occasionally miss a usage within a long function.
- Temperature is fixed at 0 for reproducibility.

---

## One-shot Installer

```bash
./install_toggletool.sh [-d INSTALL_DIR] [-b BRANCH] [-p PYTHON_BIN] [-r REPO_URL]
```

Example:
```bash
./install_toggletool.sh -d "$HOME/Repos/toggle-smells" -b main
```

---

## Recent Improvements

- **LLM-based detection** (`--llm`): uses a local Ollama model to extract toggle names and detect patterns; handles aliases, indirect usages, and large files via tree-sitter chunking
- **Alias tracking**: two-pass analysis traces toggle aliases across files to catch indirect spread
- **SIGALRM-based timeout**: every LLM call is guarded by a 90-second OS-level timeout to prevent infinite hangs
- **Hallucination filter**: post-LLM grep check drops any toggle the LLM reports in a file where the name does not actually appear
- **Grep + extractor caching**: within a single run, the file scan and toggle extraction are cached across patterns so each project is scanned only once
- Added support for multiple configuration files
- Output now includes dependency paths for `spread` and `nested` patterns along with toggle counts

---

## Video Demonstration
https://drive.google.com/file/d/1vlVJeFr0PYZszajo40foBDO8QRNWkLaM/view?usp=drive_link
