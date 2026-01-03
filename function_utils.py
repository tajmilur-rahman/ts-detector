import platform
from pathlib import Path
from tree_sitter import Language, Parser

_ROOT_DIR = Path(__file__).resolve().parent
_BUILD_DIR = _ROOT_DIR / "build"

# Platform-specific shared library extension
_SYSTEM = platform.system().lower()
if _SYSTEM == "windows":
    _LIB_EXT = ".dll"
elif _SYSTEM == "darwin":
    _LIB_EXT = ".dylib"
else:
    _LIB_EXT = ".so"

LANGUAGE_SO = str(_BUILD_DIR / f"my-languages{_LIB_EXT}")
LANGUAGES = {
    "python": "python",
    "java": "java",
    "cpp": "cpp",
    "c++": "cpp",
    "go": "go",
    "csharp": "c_sharp" 
}
LANG_OBJS = {lang: Language(LANGUAGE_SO, lib) for lang, lib in LANGUAGES.items()}

MACRO_NODE_TYPES = {
    "cpp": {"preproc_function_def", "preproc_def"},
}


def extract_functions(source_code, lang_name):
    parser = Parser()
    parser.set_language(LANG_OBJS[lang_name])
    tree = parser.parse(bytes(source_code, "utf8"))
    root = tree.root_node
    funcs = []
    lang_key = lang_name.lower().replace("c++", "cpp")
    macro_nodes = MACRO_NODE_TYPES.get(lang_key, set())

    def resolve_declarator_name(node):
        if node is None:
            return None
        inner = node.child_by_field_name("declarator")
        if inner:
            return resolve_declarator_name(inner)
        if node.type in ("identifier", "field_identifier", "operator", "destructor_name"):
            return node
        for child in node.children:
            name = resolve_declarator_name(child)
            if name:
                return name
        return None

    def resolve_function_name(node):
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node
        declarator = node.child_by_field_name("declarator")
        return resolve_declarator_name(declarator) if declarator else None

    def visit(node):
        node_type = node.type
        if node_type in ("function_definition", "method_definition", "method_declaration"):
            name_node = resolve_function_name(node)
            if name_node:
                name = source_code[name_node.start_byte:name_node.end_byte]
                funcs.append({
                    "name": name,
                    "start_byte": node.start_byte,
                    "end_byte": node.end_byte
                })
        elif node_type in macro_nodes:
            name = None
            for child in node.children:
                if child.type == "identifier":
                    name = source_code[child.start_byte:child.end_byte]
                    break
            if not name:
                line_no = node.start_point[0] + 1
                name = f"macro@L{line_no}"
            funcs.append({
                "name": name,
                "start_byte": node.start_byte,
                "end_byte": node.end_byte
            })
        for child in node.children:
            visit(child)

    visit(root)
    return funcs

def match_toggle_usage(source_code, functions, toggle_name):
    results = {}
    for fn in functions:
        body = source_code[fn["start_byte"]:fn["end_byte"]]
        count = body.count(toggle_name)
        if count > 0:
            results[fn["name"]] = count
    return results
