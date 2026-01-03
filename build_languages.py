import os
import platform
from pathlib import Path
from tree_sitter import Language

# Set compiler flags for consistent builds
os.environ["CC"] = "cc"
os.environ["CFLAGS"] = "-std=c11"
ROOT_DIR = Path(__file__).resolve().parent
BUILD_DIR = ROOT_DIR / "build"
BUILD_DIR.mkdir(exist_ok=True)

# Choose shared library extension per platform
SYSTEM = platform.system().lower()
if SYSTEM == "windows":
    lib_ext = ".dll"
elif SYSTEM == "darwin":
    lib_ext = ".dylib"
else:
    lib_ext = ".so"

LIB_PATH = BUILD_DIR / f"my-languages{lib_ext}"
Language.build_library(
    str(LIB_PATH),
    [
        'tree-sitter-python',
        'tree-sitter-java',
        'tree-sitter-cpp',
        'tree-sitter-c-sharp',
        'tree-sitter-go',
    ]
)

print(f"Tree-sitter language library built successfully: {LIB_PATH}")
