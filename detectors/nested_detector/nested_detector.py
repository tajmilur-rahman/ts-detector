from collections import defaultdict
import re
from function_utils import extract_functions

def process_code_files(lang, code_files, code_files_contents, toggles, proximity=3):
    """
    Processes code files to identify nested toggles and their dependencies.
    """
    nested_toggles = defaultdict(dict)  # toggle -> {file_path -> [dependencies]}
    total_count_toggles = 0

    regex_patterns_by_language = {
        "python": {
            'return_and': r"return\s+(.*?)\s+and",
            'if_and': r"if\s+(.*?)\s+and",
            'return_or': r"return\s+(.*?)\s+or",
            'if_or': r"if\s+(.*?)\s+or",
            'or_enter': r" or\s+(.*?)\n",
            'and_enter': r" and\s+(.*?)\n",
            'multi_line_condition': r"(\b(and|or)\b.*\\n)+",  
            'function_call': r"\b\w+\((.*?)(and|or)(.*?)\)",
            'assign_and': r"[^=]=\s+(.*?) and",
            'assign_or': r"[^=]=\s+(.*?) or",
            'nested_if': r"if\s.*:\s*if\s.*:",  
            'nested_return': r"return\s+.*(?:and|or).*",  
            'elif_condition': r"\belif\s+.*:",
            'condition': r"(if|elif|return|and|or)\s+(.*?)\b",
            'logical_and': r"\b(and|&&)\b",
            'logical_or': r"\b(or|\|\|)\b"
        },       
        "java": {
            'if_statement': r"if\s*\(.*?\)\s*\{",
            'nested_if': r"if\s*\(.*?\)\s*\{.*if\s*\(.*?\)\s*\{", 
            'conditional_operator': r"\?.*?:",  
            'logical_combination': r"\b&&|\|\|\b", 
            'function_call': r"\b\w+\((.*?)(&&|\|\|)(.*?)\)",  
            'variable_assignment': r"\w+\s*=\s*.*?;",
            'return_statement': r"return\s+.*?;",
            'condition': r"(if|return)\s*\(.*?\)"
        },
        "csharp": {
            'if_statement': r"if\s*\(.*?\)\s*\{",
            'nested_if': r"if\s*\(.*?\)\s*\{.*if\s*\(.*?\)\s*\{", 
            'conditional_expression': r"\?.*?:", 
            'logical_combination': r"\b&&|\|\|\b", 
            'function_call': r"\b\w+\((.*?)(&&|\|\|)(.*?)\)",  
            'variable_assignment': r"\w+\s*=\s*.*?;",
            'return_statement': r"return\s+.*?;",
            'condition': r"(if|return)\s*\(.*?\)"
        },
        "c++": {
            'if_statement': r"if\s*\(.*?\)\s*\{",
            'nested_if': r"if\s*\(.*?\)\s*\{.*if\s*\(.*?\)\s*\{", 
            'conditional_operator': r"\?.*?:", 
            'logical_combination': r"\b&&|\|\|\b", 
            'function_call': r"\b\w+\((.*?)(&&|\|\|)(.*?)\)", 
            'variable_assignment': r"\w+\s*=\s*.*?;",
            'return_statement': r"return\s+.*?;",
            'condition': r"(if|return)\s*\(.*?\)"
        },
        "go": {
            'if_statement': r"if\s*.*?\s*\{",
            'nested_if': r"if\s*.*?\s*\{.*if\s*.*?\s*\{", 
            'logical_combination': r"\b&&|\|\|\b", 
            'function_call': r"\b\w+\((.*?)(&&|\|\|)(.*?)\)",  
            'variable_assignment': r"\w+\s*=\s*.*?;",
            'return_statement': r"return\s+.*?;",
            'condition': r"(if|return)\s*.*?\{"
        }
    }

    regex_patterns = regex_patterns_by_language.get(lang.lower())
    if not regex_patterns:
        raise ValueError(f"Unsupported language: {lang}")

    compiled_patterns = {name: re.compile(pattern) for name, pattern in regex_patterns.items()}

    for code_file, content in zip(code_files, code_files_contents):
        lines = content.splitlines()
        num_lines = len(lines)

        toggle_lines = [i for i, line in enumerate(lines) if any(toggle in line for toggle in toggles)]

        # Get function ranges using Tree-sitter
        try:
            functions = extract_functions(content, lang.lower().replace("c++", "cpp").replace("c#", "csharp"))
        except Exception as e:
            # print(f"Error parsing functions in {code_file}: {e}")
            functions = []

        # Map: function name -> [line start, line end]
        func_map = {
            fn["name"]: (fn["start_byte"], fn["end_byte"]) for fn in functions
        }

        for line_idx in toggle_lines:
            start_idx = max(0, line_idx - proximity)
            end_idx = min(num_lines, line_idx + proximity + 1)
            nearby_lines = lines[start_idx:end_idx]

            # Concatenate lines for byte offset approximation
            cumulative_lines = "\n".join(lines[:line_idx + 1])
            byte_pos = len(cumulative_lines.encode("utf-8"))

            matched_fn = None
            for fname, (start_b, end_b) in func_map.items():
                if start_b <= byte_pos <= end_b:
                    matched_fn = fname
                    break

            if not matched_fn:
                matched_fn = "GLOBAL"

            # Analyze dependencies
            dependencies = set()
            matched_toggles = set()
            for nearby_line in nearby_lines:
                for pattern_name, pattern in compiled_patterns.items():
                    if pattern.search(nearby_line):
                        matched_toggles.update(toggle for toggle in toggles if toggle in nearby_line)
                        dependencies.update(dep for dep in toggles if dep in nearby_line)

            for toggle in matched_toggles:
                if dependencies:
                    if code_file not in nested_toggles[toggle]:
                        nested_toggles[toggle][code_file] = {}
                    if matched_fn not in nested_toggles[toggle][code_file]:
                        nested_toggles[toggle][code_file][matched_fn] = {
                            "dependencies": []
                        }
                    nested_toggles[toggle][code_file][matched_fn]["dependencies"].extend(
                        list(dependencies - {toggle})
                    )
                    total_count_toggles += len(dependencies - {toggle})

    return {
        "nested_toggles": nested_toggles,
        "qty": total_count_toggles
    }

def format_nested_toggles_data(nested_toggles_data):
    nested_toggles = nested_toggles_data["nested_toggles"]
    formatted_toggles = defaultdict(list)

    for toggle, file_map in nested_toggles.items():
        for file_path, fn_map in file_map.items():
            formatted_toggles[toggle].append({
                "file": file_path,
                "Functions": [
                    {
                        fn_name: data["dependencies"]
                        for fn_name, data in fn_map.items()
                    }
                ]
            })

    return {
        "toggles": dict(formatted_toggles),
        "qty": len(formatted_toggles)
    }