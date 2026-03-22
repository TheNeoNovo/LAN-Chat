#!/usr/bin/env sh
# termchat installer
# curl -fsSL https://raw.githubusercontent.com/TheNeoNovo/Termchat/main/install.sh | sh

set -e
REPO="https://raw.githubusercontent.com/TheNeoNovo/Termchat/main"
GRN='\033[0;32m'; YEL='\033[0;33m'; CYN='\033[0;36m'; RED='\033[0;31m'; RST='\033[0m'
ok()   { printf "${GRN}[ok]${RST} %s\n" "$1"; }
warn() { printf "${YEL}[!] ${RST} %s\n" "$1"; }
fail() { printf "${RED}[x] ${RST} %s\n" "$1"; exit 1; }

echo ""
printf "${CYN}termchat installer${RST}\n\n"

# ── Python ────────────────────────────────────────────────────────────────────

find_python() {
    for cmd in python3 python python3.12 python3.11 python3.10 python3.9; do
        if command -v "$cmd" >/dev/null 2>&1; then
            ok=$("$cmd" -c "import sys;print(int(sys.version_info>=(3,7)))" 2>/dev/null)
            [ "$ok" = "1" ] && echo "$cmd" && return 0
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

# ── Install ───────────────────────────────────────────────────────────────────

for dir in "$HOME/.local/bin" "$HOME/bin" "/usr/local/bin"; do
    mkdir -p "$dir" 2>/dev/null || true
    [ -w "$dir" ] && { IDIR="$dir"; break; }
done
[ -z "$IDIR" ] && mkdir -p "$HOME/.local/bin" && IDIR="$HOME/.local/bin"

if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$REPO/termchat.py" -o "$IDIR/termchat.py"
else
    wget -q "$REPO/termchat.py" -O "$IDIR/termchat.py"
fi
chmod +x "$IDIR/termchat.py"
ok "Downloaded termchat.py"

printf '#!/usr/bin/env sh\nexec "%s" "%s/termchat.py" "$@"\n' "$PYTHON" "$IDIR" > "$IDIR/chat"
chmod +x "$IDIR/chat"
ok "Created chat command"

case ":$PATH:" in
    *":$IDIR:"*) ;;
    *)
        PROF=""
        [ -n "$ZSH_VERSION" ] && PROF="$HOME/.zshrc"
        [ -z "$PROF" ] && [ -f "$HOME/.bash_profile" ] && PROF="$HOME/.bash_profile"
        [ -z "$PROF" ] && PROF="$HOME/.bashrc"
        printf '\nexport PATH="%s:$PATH"\n' "$IDIR" >> "$PROF"
        warn "Run: source $PROF  (or open a new terminal)"
        ;;
esac

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
ok "termchat installed — type:"
echo ""
printf "    ${CYN}chat <room>${RST}     join a room\n"
printf "    ${CYN}chat list${RST}       see rooms on LAN\n"
echo ""
