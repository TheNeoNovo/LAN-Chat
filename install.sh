#!/usr/bin/env sh
# termchat installer — Linux / macOS
# Usage: curl -fsSL https://raw.githubusercontent.com/TheNeoNovo/Termchat/main/install.sh | sh

set -e

REPO="https://raw.githubusercontent.com/TheNeoNovo/Termchat/main"

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[0;33m'; CYN='\033[0;36m'
BOLD='\033[1m'; RST='\033[0m'
say()  { printf "${CYN}▸${RST} %s\n" "$1"; }
ok()   { printf "${GRN}✓${RST} %s\n" "$1"; }
warn() { printf "${YEL}!${RST} %s\n" "$1"; }
fail() { printf "${RED}✗${RST} %s\n" "$1"; exit 1; }

echo ""
printf "${BOLD}${CYN}Termchat installer${RST} — LAN terminal chat\n"
echo ""

# ── Detect OS ─────────────────────────────────────────────────────────────────

case "$(uname -s 2>/dev/null)" in
    Darwin*) OS="macos" ;;
    Linux*)  OS="linux" ;;
    CYGWIN*|MINGW*|MSYS*) OS="windows_bash" ;;
    *) OS="unknown" ;;
esac

# ── Find Python ───────────────────────────────────────────────────────────────

find_python() {
    for cmd in python3 python python3.12 python3.11 python3.10 python3.9; do
        if command -v "$cmd" >/dev/null 2>&1; then
            ok=$("$cmd" -c "import sys; print(int(sys.version_info>=(3,7)))" 2>/dev/null)
            [ "$ok" = "1" ] && echo "$cmd" && return 0
        fi
    done
    return 1
}

PYTHON=$(find_python || true)

if [ -z "$PYTHON" ]; then
    warn "Python 3.7+ not found."
    printf "  Install Python now? [Y/n] "; read -r ans; ans=${ans:-Y}
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
                linux)
                    if command -v apt-get >/dev/null 2>&1; then
                        say "Installing Python via apt..."
                        sudo apt-get update -qq && sudo apt-get install -y python3
                    elif command -v dnf >/dev/null 2>&1; then
                        sudo dnf install -y python3
                    elif command -v pacman >/dev/null 2>&1; then
                        sudo pacman -S --noconfirm python
                    else
                        fail "Cannot auto-install Python. Please install Python 3.7+ from https://python.org"
                    fi ;;
                *)
                    fail "Please install Python 3.7+ from https://python.org then re-run this." ;;
            esac
            PYTHON=$(find_python || true)
            [ -z "$PYTHON" ] && fail "Python still not found. Please open a new terminal and try again." ;;
        *) fail "Python 3.7+ is required. Install from https://python.org" ;;
    esac
fi

ok "Python: $PYTHON ($($PYTHON --version 2>&1))"

# ── Install dir ───────────────────────────────────────────────────────────────

for dir in "$HOME/.local/bin" "$HOME/bin" "/usr/local/bin"; do
    mkdir -p "$dir" 2>/dev/null || true
    if [ -w "$dir" ]; then INSTALL_DIR="$dir"; break; fi
done
[ -z "$INSTALL_DIR" ] && mkdir -p "$HOME/.local/bin" && INSTALL_DIR="$HOME/.local/bin"
say "Installing to: $INSTALL_DIR"

# ── Download ──────────────────────────────────────────────────────────────────

say "Downloading termchat..."
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$REPO/termchat.py" -o "$INSTALL_DIR/termchat.py"
elif command -v wget >/dev/null 2>&1; then
    wget -q "$REPO/termchat.py" -O "$INSTALL_DIR/termchat.py"
else
    fail "curl or wget is required."
fi
chmod +x "$INSTALL_DIR/termchat.py"
ok "Downloaded termchat.py"

# ── Create c wrapper ──────────────────────────────────────────────────────────

cat > "$INSTALL_DIR/chat" << WRAPPER
#!/usr/bin/env sh
exec "$PYTHON" "$INSTALL_DIR/termchat.py" "\$@"
WRAPPER
chmod +x "$INSTALL_DIR/chat"
ok "Created chat command"

# ── PATH ──────────────────────────────────────────────────────────────────────

case ":$PATH:" in
    *":$INSTALL_DIR:"*) ok "Already in PATH" ;;
    *)
        warn "$INSTALL_DIR not in PATH — adding now..."
        if [ -n "$ZSH_VERSION" ] || [ "$(basename "${SHELL:-}")" = "zsh" ]; then
            PROFILE="$HOME/.zshrc"
        elif [ -f "$HOME/.bash_profile" ]; then
            PROFILE="$HOME/.bash_profile"
        else
            PROFILE="$HOME/.bashrc"
        fi
        printf '\n# termchat\nexport PATH="%s:$PATH"\n' "$INSTALL_DIR" >> "$PROFILE"
        ok "Added to $PROFILE"
        warn "Run: source $PROFILE  (or open a new terminal)"
        ;;
esac

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
ok "${BOLD}Termchat installed!${RST}"
echo ""
printf "  ${CYN}chat pub${RST}           join the public room\n"
printf "  ${CYN}chat <id>${RST}          join a private room\n"
printf "  ${CYN}chat <id> <pw>${RST}     join a password room\n"
printf "  ${CYN}chat dm <name>${RST}     DM someone\n"
printf "  ${CYN}chat list${RST}          see rooms on LAN\n"
printf "  ${CYN}chat help${RST}          show all commands\n"
echo ""
