import platform
from pathlib import Path
from tree_sitter import Language, Parser

_ROOT_DIR = Path(__file__).resolve().parent
_BUILD_DIR = _ROOT_DIR / "build"

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

_FUNCTION_NODE_TYPES = {
    "function_definition", "method_definition", "method_declaration",
    "constructor_declaration", "constructor_body",
}

_PARSER_CACHE = {}
_TREE_CACHE = {}


def _content_fingerprint(source_code, lang_key):
    return (lang_key, len(source_code), hash(source_code))


def parse_source_cached(source_code, lang_name):
    lang_key = lang_name.lower().replace("c++", "cpp").replace("c#", "csharp")
    key = _content_fingerprint(source_code, lang_key)
    if key not in _TREE_CACHE:
        parser = _get_parser(lang_key)
        source_bytes = source_code.encode("utf-8")
        tree = parser.parse(source_bytes)
        _TREE_CACHE[key] = (tree, source_bytes)
    return _TREE_CACHE[key]


def _get_parser(lang_name):
    if lang_name not in _PARSER_CACHE:
        parser = Parser()
        parser.set_language(LANG_OBJS[lang_name])
        _PARSER_CACHE[lang_name] = parser
    return _PARSER_CACHE[lang_name]


def _slice_source_bytes(source_code, start_byte, end_byte):
    source_bytes = source_code.encode("utf-8") if isinstance(source_code, str) else source_code
    return source_bytes[start_byte:end_byte].decode("utf-8", errors="ignore")


def extract_functions(source_code, lang_name):
    tree, source_bytes = parse_source_cached(source_code, lang_name)
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
        if node_type in _FUNCTION_NODE_TYPES:
            name_node = resolve_function_name(node)
            if name_node:
                name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="ignore")
                funcs.append({
                    "name": name,
                    "start_byte": node.start_byte,
                    "end_byte": node.end_byte
                })
        elif node_type in macro_nodes:
            name = None
            for child in node.children:
                if child.type == "identifier":
                    name = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore")
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
    source_bytes = source_code.encode("utf-8") if isinstance(source_code, str) else source_code
    for fn in functions:
        body = source_bytes[fn["start_byte"]:fn["end_byte"]].decode("utf-8", errors="ignore")
        count = body.count(toggle_name)
        if count > 0:
            results[fn["name"]] = count
    return results
