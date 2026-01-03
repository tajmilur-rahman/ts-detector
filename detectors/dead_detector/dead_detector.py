import re
from concurrent.futures import ThreadPoolExecutor

def format_python_toggles(toggles):
    return [f'"{toggle}"' for toggle in toggles]

def find_dead_toggles(toggles, code_files, code_files_contents):
    if not toggles:
        return []

    # Precompile regex pattern for all toggles
    combined_pattern = re.compile(r'\b(?:' + '|'.join(re.escape(toggle) for toggle in toggles) + r')\b')
    active_toggles = set()

    # Process files in parallel
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_file, combined_pattern, file_content) for file_content in code_files_contents]

        for future in futures:
            matches = future.result()
            active_toggles.update(matches)

            if len(active_toggles) == len(toggles):
                return []
            
    dead_toggles = [toggle for toggle in toggles if toggle not in active_toggles]
    return dead_toggles


def process_file(pattern, file_content):
    """
    Process a single file to find active toggles using a precompiled regex pattern.
    Returns a set of matched toggles.
    """
    matches = set(pattern.findall(file_content))
    return matches

def format_dead_toggles_data(dead_toggles):
    dead_toggles.sort()
    dead_toggles_data = {
        "toggles": dead_toggles,
        "qty": len(dead_toggles)
    }
    return dead_toggles_data
