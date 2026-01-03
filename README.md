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
- **Auto-detects programming language**: Automatically identifies the language based on file extension or content.
- **Config paths as relative paths**: Configuration files are provided as paths relative to the source directory.

## Usage

### Basic Syntax
1. Clone the repository:
https://github.com/tajmilur-rahman/toggle-smells.git
2. CD into ts-detector in commandline

3. Create a virtual environment
python3 -m venv venv
source venv/bin/activate

4. Install the dependencies
pip install -r requirements.txt

5. Build the languages (creates build/my-languages.{so|dylib|dll} automatically)
python build_languages.py

6. Run the tool
`` 
python tsd.py -p <source_path> -c <config_paths> [-o <output_path>] [-t <toggle_usage_pattern>] [-l <language>]
``

### Required Arguments

- `-p, --source-path`: Path to the source code directory.
- `-c, --config-path`: Relative paths (from `source-path`) to the configuration files used in the analysis.

### Optional Arguments

- `-o, --output`: Path to save the output JSON file. If not provided, the result will be printed to the console.
- `-t, --toggle-usage`: Specify which toggle usage pattern to detect. If not provided, the script will detect all patterns. Options are:
  - `dead`
  - `spread`
  - `nested`
  - `mixed` (applicable for C++, C, and C#)
  - `enum`
- `-l, --language`: Specify the programming language. If not provided, the script will attempt to auto-detect the language based on file extensions or content.

### Example Usage

#### Example 1: Detect `nested` usage in a C++ project and print output to the console

`python tsd.py -p /path/to/source/ -c src/module/Toggles.cpp src/module/Features.cpp -t nested
`
This command will:
- Use `/path/to/source/` as the source path.
- Check the `src/module/Toggles.cpp` and `src/module/Features.cpp` configuration files (relative to the source path).
- Detect only the `nested` pattern in C++ files.
- Print the results to the console.

#### Example 2: Detect all toggle usage patterns and write output to a file

`python tsd.py -p /path/to/source/ -c src/module/Toggles.cpp src/module/Features.cpp -o outputs/output.json
`

This command will:
- Detect all toggle usage patterns (`dead`, `spread`, `nested`, `mixed`, `enum`).
- Save the results in `outputs/output.json`.

#### Example 3: Manually specify the programming language

`python tsd.py -p /path/to/source/ -c src/module/Toggles.cpp src/module/Features.cpp -l python -o outputs/python-output.json
`

This command will:
- Force the detection to assume Python as the language.
- Save the results to `outputs/python-output.json`.


### Note for macOS Users
The included `tree-sitter-cpp` grammar is pre-patched with a macro to support `static_assert` on macOS (C11). No manual changes are needed after cloning the repository.

## Supported Languages

- Python
- Java
- C++
- C
- Go
- C#

If the language is not provided via the `-l` flag, the script will attempt to auto-detect the language based on file extensions or content analysis.

## Output

The result will be a JSON object, either printed to the console or saved to a file. The format will be similar to:

```json
{
  "dead": {
    "toggles": ["TOGGLE_A", "TOGGLE_B"],
    "qty": 2
  },
  "spread": {
    "toggles": {
      "TOGGLE_C": [
        {"file": "path/component/moduleA.py", "count": 3},
        {"file": "path/component/moduleC.py", "count": 1}
      ],
      "TOGGLE_D": [
        {"file": "path/core/moduleB.py", "count": 2}
      ]
    },
    "qty": 2
  },
  "nested": {
    "toggles": {
      "TOGGLE_E": [
        {"src/component/moduleA.py": ["DEPENDS_ON_TOGGLE_A"]},
        {"src/component/moduleB.py": ["DEPENDS_ON_TOGGLE_D"]}
        ],
    },
    "qty": 1
  },
  "enum": {
    "toggles": ["TOGGLE_F"],
    "qty": 1
  },
  "mixed": {
    "toggles": ["TOGGLE_B"],
    "qty": 1
  }
}
```
In this example:

- `dead`: 2 toggles are declared but never used.
- `spread`: Toggles appear in multiple files.
- `nested`: Toggles appear within another toggle's scope.
- `enum`: A toggle with multiple conditional values.
- `mixed`: A toggle that fits more than one pattern.

## Recent Improvements

- Added support for multiple configuration files
- Output now includes dependency paths for `spread` and `nested` patterns along with its dependency toggle count
- Updated JSON structure for better clarity

# Sample commands with known repo

[OpenSearch](https://github.com/opensearch-project/OpenSearch): `python tsd.py -p H:\Repos\OpenSearch\ -c server\src\main\java\org\opensearch\common\util\FeatureFlags.java server\src\main\java\org\opensearch\common\settings\FeatureFlagSettings.java`

[SDB2](https://github.com/mathisdt/sdb2/tree/master): `python tsd.py -p H:\Repos\sdb2 -c src\main\java\org\zephyrsoft\sdb2\Feature.java`

[Sentry](https://github.com/getsentry/sentry): `python tsd.py -p H:\Repos\toggle-smells\repos\sentry\ -c src\sentry\conf\server.py src\sentry\features\temporary.py src\sentry\features\permanent.py`

[Pytorch](https://github.com/pytorch/pytorch): `python tsd.py -p H:\Repos\pytorch -c torch\fx\proxy.py `

[Temporal](https://github.com/temporalio/temporal): `python tsd.py -p H:\Repos\temporal -c common\dynamicconfig\constants.go `

[Candence](https://github.com/uber/cadence): `python tsd.py -p H:\Repos\cadence -c common\dynamicconfig\constants.go `

[Vstest](https://github.com/microsoft/vstest): `python tsd.py -p H:\Repos\vstest\ -c src\Microsoft.TestPlatform.CoreUtilities\FeatureFlag\FeatureFlag.cs`

[Bitwarden/Server](https://github.com/bitwarden/server): `python tsd.py -p H:\Repos\server -c src\Core\Constants.cs `

[chromium](https://github.com/chromium/chromium): `python tsd.py -p H:\Repos\chromium -c chrome\browser\flag_descriptions.cc `

[Dawn](https://github.com/google/dawn): `python tsd.py -p H:\Repos\toggle-smells\repos\dawn\ -c src\dawn\native\Toggles.cpp  src\dawn\native\Features.cpp`

# Video Demonstration
https://drive.google.com/file/d/1vlVJeFr0PYZszajo40foBDO8QRNWkLaM/view?usp=drive_link
