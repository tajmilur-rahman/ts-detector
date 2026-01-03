import re

REGEX_PATTERNS = {
    'java': r'enum\s+(\w+)\s*{([^}]*)}',
    'python': r'class\s+(\w+)\(Enum\):\s*([^#]*)',
    'go': r'const\s*\((.*?)\)',
    'c++': r'enum\s+(\w+)?\s*{([^}]*)}',
    'csharp': r'enum\s+(\w+)\s*{([^}]*)}',
    'c': r'enum\s+(\w+)?\s*{([^}]*)}'
}


def extract_enum_members(code, language):
    """
    Extracts the enum members from a given code string based on the specified language.

    Args:
        code (str): The content of a code file as a string.
        language (str): The programming language ('java', 'python', 'go', "c++", 'csharp', 'c').

    Returns:
        dict: A dictionary where keys are enum names and values are lists of enum members.
    """
    enum_members = {}

    if language not in REGEX_PATTERNS:
        raise ValueError(f"Unsupported language: {language}")

    enum_pattern = re.compile(REGEX_PATTERNS[language], re.DOTALL)

    if language == 'java' or language == 'c++' or language == 'csharp' or language == 'c':
        for match in enum_pattern.finditer(code):
            enum_name = match.group(1) or "UnnamedEnum"
            members_block = match.group(2)
            members = [member.strip() for member in members_block.split(',') if member.strip()]
            enum_members[enum_name] = members

    elif language == 'python':
        for match in enum_pattern.finditer(code):
            enum_name = match.group(1)
            members_block = match.group(2)
            members = re.findall(r'(\w+)\s*=\s*\d+', members_block)
            enum_members[enum_name] = members

    elif language == 'go':
        for match in enum_pattern.finditer(code):
            members_block = match.group(1)
            members = [member.split('=')[0].strip() for member in members_block.split('\n') if member.strip()]
            enum_members['go'] = members

    return enum_members


def is_enum_member(code, var_names, language):
    """
    Checks if a given variable name is a member of any enum in the code for a given language.

    Args:
        code (str): The content of a code file as a string.
        var_names ([str]): a list of variable names to check.
        language (str): The programming language ('java', 'python', 'go', "c++", 'csharp', 'c').

    Returns:
        [str]:  a list of variable names that is enum
    """
    enums = extract_enum_members(code, language)

    isEnums = []
    for enum_name, members in enums.items():
        for var_name in var_names:
            if var_name in members:
                isEnums.append(var_name)
    return isEnums

