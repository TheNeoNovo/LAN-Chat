#!/usr/bin/env sh
# termchat installer — installs via NEO Launcher
# curl -fsSL https://raw.githubusercontent.com/TheNeoNovo/Termchat/main/install.sh | sh

set -e
NEO_REPO="https://raw.githubusercontent.com/TheNeoNovo/NEO-Launcher/main"
GRN='\033[0;32m'; YEL='\033[0;33m'; CYN='\033[0;36m'; RED='\033[0;31m'; RST='\033[0m'
ok()   { printf "${GRN}[ok]${RST} %s\n" "$1"; }
warn() { printf "${YEL}[!] ${RST} %s\n" "$1"; }
fail() { printf "${RED}[x] ${RST} %s\n" "$1"; exit 1; }

echo ""
printf "${CYN}termchat installer${RST}\n\n"

find_python() {
    for cmd in python3 python python3.12 python3.11 python3.10 python3.9; do
        if command -v "$cmd" >/dev/null 2>&1; then
            r=$("$cmd" -c "import sys;print(int(sys.version_info>=(3,7)))" 2>/dev/null)
            [ "$r" = "1" ] && echo "$cmd" && return 0
        fi
    done
    return 1
}

PYTHON=$(find_python || true)

if [ -z "$PYTHON" ]; then
    warn "Python 3.7+ not found."
    printf "  Install now? [Y/n] "; read -r ans; ans=${ans:-Y}
    case "$ans" in
        [Yy]*)
            case "$(uname -s)" in
                Darwin*)
                    command -v brew >/dev/null 2>&1 && brew install python3 || {
                        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
                        brew install python3
                    } ;;
                Linux*)
                    command -v apt-get >/dev/null 2>&1 && sudo apt-get install -y python3 ||
                    command -v dnf     >/dev/null 2>&1 && sudo dnf install -y python3 ||
                    command -v pacman  >/dev/null 2>&1 && sudo pacman -S --noconfirm python ||
                    fail "Install Python 3.7+ from https://python.org" ;;
                *) fail "Install Python 3.7+ from https://python.org" ;;
            esac
            PYTHON=$(find_python || true)
            [ -z "$PYTHON" ] && fail "Python not found. Open a new terminal and retry." ;;
        *) fail "Python 3.7+ required." ;;
    esac
fi

ok "Python: $($PYTHON --version 2>&1)"

NEO_DIR="$HOME/.neo"
NEO_BIN="$NEO_DIR/bin"
NEO_PY="$NEO_DIR/neo.py"

if [ -f "$NEO_PY" ]; then
    ok "NEO Launcher already installed"
else
    printf "${CYN}  Installing NEO Launcher first...${RST}\n"
    mkdir -p "$NEO_DIR" "$NEO_BIN"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$NEO_REPO/neo.py" -o "$NEO_PY"
    else
        wget -q "$NEO_REPO/neo.py" -O "$NEO_PY"
    fi
    chmod +x "$NEO_PY"
    printf '#!/usr/bin/env sh\nexec "%s" "%s" "$@"\n' "$PYTHON" "$NEO_PY" > "$NEO_BIN/neo"
    chmod +x "$NEO_BIN/neo"
    case ":$PATH:" in
        *":$NEO_BIN:"*) ;;
        *)
            PROF=""
            [ -n "$ZSH_VERSION" ] && PROF="$HOME/.zshrc"
            [ -z "$PROF" ] && [ -f "$HOME/.bash_profile" ] && PROF="$HOME/.bash_profile"
            [ -z "$PROF" ] && PROF="$HOME/.bashrc"
            printf '\nexport PATH="%s:$PATH"\n' "$NEO_BIN" >> "$PROF"
            warn "Run: source $PROF  (or open a new terminal)"
            ;;
    esac
    ok "NEO Launcher installed"
fi

printf "${CYN}  Installing chat...${RST}\n"
"$PYTHON" "$NEO_PY" install chat

echo ""
ok "Done — open a new terminal and type:"
echo ""
printf "    ${CYN}chat <room>${RST}       join a room\n"
printf "    ${CYN}neo list${RST}          see all apps\n"
echo ""
