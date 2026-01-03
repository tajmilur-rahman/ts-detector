import json
import sys
import glob
import os
import argparse
import t_utils

patterns = ["dead", "spread", "nested", "mixed", "enum"]


def auto_detect_language(config_files):
    for config_file in config_files:
        file_extension = config_file.split('.')[-1]  # Get the file extension
        # Check for common programming language extensions
        if file_extension == "py":
            return "python"
        elif file_extension == "java":
            return "java"
        elif file_extension in ["cpp", "cc", "cxx", "hpp"]:
            return "c++"
        elif file_extension == "go":
            return "go"
        elif file_extension == "js":
            return "javascript"
        elif file_extension == "ts":
            return "typescript"
        elif file_extension == "cs":
            return "csharp"

        # If extension doesn't provide enough information, check content for more clues
        with open(config_file, 'r') as f:
            content = f.read()
            if "import java" in content:
                return "java"
            elif "#include <" in content:
                return "c++"
            elif "def " in content:
                return "python"
            elif "package main" in content:
                return "go"
            elif "function " in content or "console.log" in content:
                return "javascript"
            elif "namespace " in content or "using System" in content:
                return "csharp"

    return None


def main():
    parser = argparse.ArgumentParser(description='Detect usage patterns in source code.')
    parser.add_argument('-p', '--source-path', required=True, help='Source code directory path')
    parser.add_argument('-c', '--config-path', required=True, nargs='+',
                        help='Relative configuration file paths (relative to source path)')
    parser.add_argument('-o', '--output', required=False, help='Output file path')
    parser.add_argument('-t', '--toggle-usage', required=False, choices=patterns, help='Toggle usage pattern to detect')
    parser.add_argument('-l', '--language', required=False,
                        help='Programming language (optional, auto-detect if not provided)')

    args = parser.parse_args()
    source_path = args.source_path.rstrip("/")
    config_paths = []
    for c in args.config_path:
        config_paths.extend([os.path.join(source_path, path.strip()) for path in c.split(",")])

    # config_paths = [os.path.join(source_path, c) for c in args.config_path]
    output_path = args.output
    toggle_usage = args.toggle_usage
    lang = args.language

    if not lang:
        config_files = []
        for config_path in config_paths:
            resolved_files = glob.glob(f'{config_path}', recursive=True)
            config_files.extend(resolved_files)

        if not config_files:
            print("No configuration files found.")
            sys.exit(1)

        # Checking if none of the config files have language specific extension
        config_file_type = ""
        for config_file in config_files:
            if not os.path.exists(config_file):
                print(f"File does not exist: {config_file}")
                continue
            file_extension = config_file.split('.')[-1]
            # config files with different extensions like .properties, .conf or .cfg (can add more extensions if found)
            if file_extension in ["properties", "conf", "cfg", "tsx"]:
                config_file_type = "config"
                break

        if config_file_type == "config":
            lang = input("Please provide the programming language associated with this project: ").strip().lower()
            if not lang:
                print("Language input is required. Exiting.")
                sys.exit(1)
        else:
            lang = auto_detect_language(config_files)
            print(f"Auto-detected language: {lang}")

        if not lang:
            print("Could not auto-detect language. Please provide it using the -l flag.")
            sys.exit(1)

    print(f"Language: {lang}, Source path: {source_path}, Config file pattern: {config_paths}, "
          f"Toggle usage pattern: {toggle_usage}")

    config_files_paths = []
    for c in config_paths:
        resolved_files = glob.glob(f'{c}', recursive=True)
        # Filter out directories
        valid_files = [f for f in resolved_files if os.path.isfile(f)]
        config_files_paths.extend(valid_files)
        print(f"Valid files for path {c}: {valid_files}")

    if not config_files_paths:
        print("No valid configuration files found.")
        sys.exit(1)

    if lang.lower() == "c++":
        c_files = glob.glob(f'{source_path}/**/*.cc', recursive=True)
        cpp_files = glob.glob(f'{source_path}/**/*.cpp', recursive=True)
        mm_files = glob.glob(f'{source_path}/**/*.mm', recursive=True)
        m_files = glob.glob(f'{source_path}/**/*.m', recursive=True)
        code_files = c_files + cpp_files + mm_files + m_files
    elif lang.lower() == "go":
        code_files = glob.glob(f'{source_path}/**/*.go', recursive=True)
    elif lang.lower() == "java":
        code_files = glob.glob(f'{source_path}/**/*.java', recursive=True)
    elif lang.lower() == "python":
        code_files = glob.glob(f'{source_path}/**/*.py', recursive=True)
    elif lang.lower() in ["c#", "csharp"]:
        code_files = glob.glob(f'{source_path}/**/*.cs', recursive=True)
    else:
        print("Unsupported language. Exiting.")
        sys.exit(1)

    # When all code files are collected above the code_files list may contain config files as well.
    # Remove config files from the code files list.
    for config_file in config_files_paths:
        if config_file in code_files:
            code_files.remove(config_file)

    if toggle_usage:
        res = {}
        print(f"Parsing {toggle_usage} toggles")
        try:
            detected_toggles = t_utils.detect(lang, code_files or [], config_files_paths, toggle_usage)
            res[toggle_usage] = detected_toggles
        except Exception as exc:
            print(f"Parsing Error ({toggle_usage} toggles): {exc}")
            res[toggle_usage] = {"error": str(exc)}

        res_json = json.dumps(res, indent=2)
        print("Extracting Toggles in JSON Format:")
        print(res_json)

        if output_path:
            with open(output_path, 'w') as f:
                f.write(str(res_json))
            print(f"Output written to {output_path}")

    else:
        res = {}
        print("Parsing toggle patterns:")
        for p in patterns:
            if p == "mixed" and lang.lower() != "c++":
                continue

            print(f"Parsing {p} toggles")
            try:
                detected_toggles = t_utils.detect(lang, code_files or [], config_files_paths, p)
                res[p] = detected_toggles
            except Exception as exc:
                print(f"Parsing Error ({p} toggles): {exc}")
                res[p] = {"error": str(exc)}

        res_json = json.dumps(res, indent=2)
        if output_path:
            with open(output_path, 'w') as f:
                f.write(str(res_json))
            print("Extracting Toggles in JSON Format:")
            print(res_json)
            print(f"Output written to {output_path}")
        else:
            print("Extracting Toggles in JSON Format:")
            print(res_json)


if __name__ == "__main__":
    main()
