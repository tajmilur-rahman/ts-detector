#!/usr/bin/env bash
# install_toggle_smells.sh
# One-shot installer for the Toggle Smell Detector.
# - Clones repo
# - Creates Python venv
# - Installs requirements
# - Builds tree-sitter languages
#
# Usage:
#   ./install_toggle_smells.sh [-d INSTALL_DIR] [-b BRANCH] [-p PYTHON_BIN] [-r REPO_URL]
#   Example:
#     ./install_toggle_smells.sh -d "$HOME/Repos/toggle-smells" -b main -p python3
#
# After it finishes, you can run the tool like:
#   source <INSTALL_DIR>/ts-detector/venv/bin/activate
#   python tsd.py -p <source_path> -c <relative_config_paths...> [-o output.json] [-t pattern] [-l language]
#
# Notes:
# - Requires: git, Python 3, a C/C++ toolchain, and (ideally) CMake.
# - macOS users may need: xcode-select --install

set -euo pipefail

# -------- Defaults --------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Default install dir to where this script lives (works even if the repo was renamed/moved)
INSTALL_DIR="${SCRIPT_DIR}"
PYTHON_BIN="python3"

# Start with fallback defaults, then override if we are already in a git repo
DEFAULT_BRANCH="add-fns"
DEFAULT_REPO_URL="https://github.com/tajmilur-rahman/toggle-smells.git"
BRANCH="${DEFAULT_BRANCH}"
REPO_URL="${DEFAULT_REPO_URL}"

if git -C "$SCRIPT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  REPO_URL="$(git -C "$SCRIPT_DIR" config --get remote.origin.url || echo "$DEFAULT_REPO_URL")"
  BRANCH="$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD || echo "$DEFAULT_BRANCH")"
fi

# -------- Parse flags --------
while getopts ":d:b:p:r:" opt; do
  case "$opt" in
    d) INSTALL_DIR="$OPTARG" ;;
    b) BRANCH="$OPTARG" ;;
    p) PYTHON_BIN="$OPTARG" ;;
    r) REPO_URL="$OPTARG" ;;
    *) echo "Unknown option: -$OPTARG" >&2; exit 2 ;;
  esac
done

# -------- Helpers --------
log() { printf "\033[1;36m[info]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[warn]\033[0m %s\n" "$*"; }
err() { printf "\033[1;31m[error]\033[0m %s\n" "$*"; }

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Missing required command: $1"
    return 1
  fi
}

try_install() {
  # Best-effort package installation for common managers.
  local pkg="$1"
  if command -v brew >/dev/null 2>&1; then
    log "Attempting 'brew install $pkg'..."
    brew install "$pkg" || true
  elif command -v apt-get >/dev/null 2>&1; then
    log "Attempting 'sudo apt-get update && sudo apt-get install -y $pkg'..."
    sudo apt-get update && sudo apt-get install -y "$pkg" || true
  elif command -v dnf >/dev/null 2>&1; then
    log "Attempting 'sudo dnf install -y $pkg'..."
    sudo dnf install -y "$pkg" || true
  elif command -v yum >/dev/null 2>&1; then
    log "Attempting 'sudo yum install -y $pkg'..."
    sudo yum install -y "$pkg" || true
  elif command -v pacman >/dev/null 2>&1; then
    log "Attempting 'sudo pacman -S --noconfirm $pkg'..."
    sudo pacman -S --noconfirm "$pkg" || true
  else
    warn "No known package manager found to auto-install '$pkg'. Please install it manually if missing."
  fi
}

# -------- Preflight checks --------
need_cmd git || { warn "Install git (brew/apt/etc.) and re-run."; exit 1; }
need_cmd "$PYTHON_BIN" || { warn "Install Python 3 and re-run. (Tried: $PYTHON_BIN)"; exit 1; }

# Build prerequisites: a C/C++ toolchain and CMake are commonly needed for tree-sitter.
if ! command -v cmake >/dev/null 2>&1; then
  warn "CMake not found. I’ll try to install it."
  try_install cmake
fi
if ! command -v cmake >/dev/null 2>&1; then
  warn "CMake still not found; tree-sitter build may fail. Install CMake and re-run if needed."
fi

# macOS: ensure Command Line Tools exist (for clang/cc).
if [[ "$(uname -s)" == "Darwin" ]]; then
  if ! xcode-select -p >/dev/null 2>&1; then
    warn "Xcode Command Line Tools not found. Run: xcode-select --install"
  fi
fi

# -------- Clone or update repo --------
log "Installing to: $INSTALL_DIR"
mkdir -p "$(dirname "$INSTALL_DIR")"

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  log "Cloning repository: $REPO_URL (branch: $BRANCH)"
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
else
  log "Repository already exists. Pulling latest on branch '$BRANCH'..."
  (cd "$INSTALL_DIR" && git fetch && git checkout "$BRANCH" && git pull --ff-only)
fi

# -------- Enter project root (flattened layout) --------
cd "$INSTALL_DIR"

# -------- Python venv --------
VENV_DIR="venv"
if [[ -d "$VENV_DIR" ]]; then
  log "Using existing virtual environment: $VENV_DIR"
else
  log "Creating virtual environment with $PYTHON_BIN -m venv $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
log "Python: $($PYTHON -V 2>/dev/null || echo 'not found')"
log "Pip:     $($PIP -V 2>/dev/null || echo 'not found')"

# -------- Install requirements --------
if [[ -f "requirements.txt" ]]; then
  log "Upgrading pip/setuptools/wheel…"
  "$PYTHON" -m pip install --upgrade pip setuptools wheel
  log "Installing Python dependencies from requirements.txt…"
  "$PYTHON" -m pip install -r requirements.txt
else
  warn "requirements.txt not found. Proceeding anyway."
fi

# -------- Build languages (tree-sitter grammars) --------
if [[ -f "build_languages.py" ]]; then
  log "Building tree-sitter languages…"
  export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-4}"
  "$PYTHON" build_languages.py || {
    warn "Language build failed. Attempting to install extra build tools and retry."
    try_install build-essential
    try_install pkg-config
    try_install llvm
    try_install gcc
    try_install clang
    "$PYTHON" build_languages.py
  }
  log "Language build complete."
else
  warn "build_languages.py not found—skipping language build step."
fi

cat <<EOF

✅ Setup complete!

Next steps:

1) Activate the environment:
   source "$(pwd)/${VENV_DIR}/bin/activate"

2) Run the detector (examples):

   # Detect a single pattern (e.g., nested) in a C++ repo:
   python tsd.py -p /path/to/source \\
     -c src/module/Toggles.cpp src/module/Features.cpp \\
     -t nested

   # Detect all patterns and write JSON output:
   python tsd.py -p /path/to/source \\
     -c path/to/config1 path/to/config2 \\
     -o outputs/output.json

   # Force language (e.g., python):
   python tsd.py -p /path/to/source \\
     -c path/to/config1 path/to/config2 \\
     -l python -o outputs/python-output.json

Tips:
- On macOS, if a build fails, ensure Command Line Tools are installed:
    xcode-select --install
- On Debian/Ubuntu, if a build fails, try:
    sudo apt-get update && sudo apt-get install -y build-essential cmake pkg-config

Repo location:
  $INSTALL_DIR

EOF
