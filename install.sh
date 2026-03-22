#!/usr/bin/env sh
# termchat universal installer
# Works on Linux, macOS, Windows (Git Bash / WSL / MSYS2)
# Usage: curl -fsSL https://raw.githubusercontent.com/termc/termc/main/install.sh | sh

set -e

REPO="https://raw.githubusercontent.com/termc/termc/main"
SCRIPT_NAME="termchat.py"
INSTALL_DIR=""
CMD_NAME="chat"

# ── Colors ────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[0;33m'
CYN='\033[0;36m'; BOLD='\033[1m'; RST='\033[0m'
say()  { printf "${BOLD}${CYN}▸${RST} %s\n" "$1"; }
ok()   { printf "${GRN}✓${RST} %s\n" "$1"; }
warn() { printf "${YEL}⚠${RST}  %s\n" "$1"; }
fail() { printf "${RED}✗${RST} %s\n" "$1"; exit 1; }

# ── Detect OS ─────────────────────────────────────────────────────────────────

detect_os() {
    case "$(uname -s 2>/dev/null)" in
        Darwin*)  echo "macos" ;;
        Linux*)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                echo "wsl"
            else
                echo "linux"
            fi ;;
        CYGWIN*|MINGW*|MSYS*) echo "windows_bash" ;;
        *)
            # PowerShell / cmd fallback (won't reach here in sh, but defensive)
            echo "unknown" ;;
    esac
}

OS=$(detect_os)
say "Detected OS: $OS"

# ── Find Python ───────────────────────────────────────────────────────────────

find_python() {
    for cmd in python3 python python3.12 python3.11 python3.10 python3.9; do
        if command -v "$cmd" >/dev/null 2>&1; then
            ver=$("$cmd" -c "import sys; print(sys.version_info[:2])" 2>/dev/null)
            # need >= (3, 7)
            ok_ver=$("$cmd" -c "import sys; print(int(sys.version_info >= (3,7)))" 2>/dev/null)
            if [ "$ok_ver" = "1" ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON=$(find_python 2>/dev/null || true)

if [ -z "$PYTHON" ]; then
    warn "Python 3.7+ not found."
    printf "  Install Python now? [Y/n] "
    read -r ans
    ans=${ans:-Y}
    case "$ans" in
        [Yy]*)
            case "$OS" in
                macos)
                    if command -v brew >/dev/null 2>&1; then
                        say "Installing Python via Homebrew..."
                        brew install python3
                    else
                        say "Installing Homebrew + Python..."
                        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
                        brew install python3
                    fi ;;
                linux|wsl)
                    if command -v apt-get >/dev/null 2>&1; then
                        say "Installing Python via apt..."
                        sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip
                    elif command -v dnf >/dev/null 2>&1; then
                        say "Installing Python via dnf..."
                        sudo dnf install -y python3
                    elif command -v pacman >/dev/null 2>&1; then
                        say "Installing Python via pacman..."
                        sudo pacman -S --noconfirm python
                    else
                        fail "Cannot auto-install Python. Please install Python 3.7+ manually from https://python.org"
                    fi ;;
                windows_bash)
                    warn "Please install Python from https://python.org/downloads"
                    warn "Ensure you check 'Add Python to PATH' during install."
                    fail "Re-run this installer after installing Python." ;;
                *)
                    fail "Cannot auto-install on this platform. Please install Python 3.7+ from https://python.org" ;;
            esac
            PYTHON=$(find_python 2>/dev/null || true)
            [ -z "$PYTHON" ] && fail "Python still not found after install attempt."
            ;;
        *)
            # Try other runtimes
            warn "Skipping Python install. Checking for other runtimes..."
            if command -v node >/dev/null 2>&1; then
                warn "Node.js found, but termchat requires Python. Please install Python 3.7+."
            fi
            fail "Cannot continue without Python 3.7+. Install from https://python.org"
            ;;
    esac
fi

ok "Using Python: $PYTHON ($($PYTHON --version 2>&1))"

# ── Pick install directory ─────────────────────────────────────────────────────

pick_install_dir() {
    # Try in order: ~/.local/bin, ~/bin, /usr/local/bin (if writable)
    for dir in "$HOME/.local/bin" "$HOME/bin"; do
        mkdir -p "$dir" 2>/dev/null || true
        if [ -w "$dir" ]; then
            echo "$dir"
            return
        fi
    done
    if [ -w "/usr/local/bin" ]; then
        echo "/usr/local/bin"
        return
    fi
    # fallback: create ~/.local/bin
    mkdir -p "$HOME/.local/bin"
    echo "$HOME/.local/bin"
}

INSTALL_DIR=$(pick_install_dir)
say "Installing to: $INSTALL_DIR"

# ── Download termchat.py ──────────────────────────────────────────────────────

DEST_PY="$INSTALL_DIR/termchat.py"

say "Downloading termchat..."
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$REPO/$SCRIPT_NAME" -o "$DEST_PY"
elif command -v wget >/dev/null 2>&1; then
    wget -q "$REPO/$SCRIPT_NAME" -O "$DEST_PY"
else
    fail "curl or wget required. Please install one and retry."
fi

chmod +x "$DEST_PY"
ok "Downloaded termchat.py"

# ── Create 'chat' wrapper script ──────────────────────────────────────────────

WRAPPER="$INSTALL_DIR/$CMD_NAME"

cat > "$WRAPPER" << WRAPPER_EOF
#!/usr/bin/env sh
exec "$PYTHON" "$DEST_PY" "\$@"
WRAPPER_EOF

chmod +x "$WRAPPER"
ok "Created 'chat' command at $WRAPPER"

# ── Ensure install dir is on PATH ─────────────────────────────────────────────

ensure_path() {
    local dir="$1"
    # Check if already on PATH
    case ":$PATH:" in
        *":$dir:"*) return 0 ;;
    esac

    warn "$dir is not in your PATH."
    say "Adding to PATH in shell profile..."

    # Detect shell profile
    local profile=""
    if [ -n "$ZSH_VERSION" ] || [ "$(basename "${SHELL:-}")" = "zsh" ]; then
        profile="$HOME/.zshrc"
    elif [ -n "$BASH_VERSION" ] || [ "$(basename "${SHELL:-}")" = "bash" ]; then
        if [ -f "$HOME/.bash_profile" ]; then
            profile="$HOME/.bash_profile"
        else
            profile="$HOME/.bashrc"
        fi
    else
        profile="$HOME/.profile"
    fi

    if [ -n "$profile" ]; then
        echo "" >> "$profile"
        echo "# termchat" >> "$profile"
        echo "export PATH=\"$dir:\$PATH\"" >> "$profile"
        ok "Added to $profile"
        warn "Run: source $profile  (or open a new terminal)"
    else
        warn "Add this to your shell profile manually:"
        warn "  export PATH=\"$dir:\$PATH\""
    fi
}

ensure_path "$INSTALL_DIR"

# ── Done ──────────────────────────────────────────────────────────────────────

printf "\n"
ok "${BOLD}termchat installed!${RST}"
printf "\n"
printf "  ${CYN}c/pub${RST}           join the public room\n"
printf "  ${CYN}c/<id>${RST}          join a private room\n"
printf "  ${CYN}c/<id>/<pw>${RST}     join a password room\n"
printf "  ${CYN}c/end${RST}           leave (or Ctrl-C)\n"
printf "\n"
printf "  ${YEL}If 'chat' is not found, open a new terminal or run:${RST}\n"
printf "  source ~/.bashrc  (or ~/.zshrc)\n\n"
