# termchat Windows Installer (PowerShell)
# Run with: irm https://raw.githubusercontent.com/termc/termc/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$REPO = "https://raw.githubusercontent.com/termc/termc/main"

function Write-Step  { Write-Host "  $args" -ForegroundColor Cyan }
function Write-Ok    { Write-Host "  [OK] $args" -ForegroundColor Green }
function Write-Warn  { Write-Host "  [!]  $args" -ForegroundColor Yellow }
function Write-Fail  { Write-Host "  [X]  $args" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  termchat installer" -ForegroundColor Cyan -NoNewline
Write-Host " — LAN terminal chat" -ForegroundColor DarkGray
Write-Host ""

# ── Find Python ───────────────────────────────────────────────────────────────

function Find-Python {
    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $ver = & $cmd -c "import sys; print(sys.version_info >= (3,7))" 2>$null
            if ($ver -eq "True") { return $cmd }
        } catch {}
    }
    return $null
}

$PYTHON = Find-Python

if (-not $PYTHON) {
    Write-Warn "Python 3.7+ not found."
    $ans = Read-Host "  Install Python now? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        Write-Step "Downloading Python installer..."
        $pyUrl = "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe"
        $tmp = "$env:TEMP\python_installer.exe"
        Invoke-WebRequest -Uri $pyUrl -OutFile $tmp
        Write-Step "Running Python installer (add to PATH will be checked automatically)..."
        Start-Process -FilePath $tmp -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1" -Wait
        Remove-Item $tmp -Force
        $PYTHON = Find-Python
        if (-not $PYTHON) {
            Write-Fail "Python installed but not found. Please restart your terminal and re-run this installer."
        }
    } else {
        Write-Fail "Python 3.7+ required. Download from https://python.org"
    }
}

$pyVer = & $PYTHON --version 2>&1
Write-Ok "Using Python: $PYTHON ($pyVer)"

# ── Install directory ─────────────────────────────────────────────────────────

$INSTALL_DIR = "$env:USERPROFILE\.termchat"
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
Write-Step "Installing to: $INSTALL_DIR"

# ── Download termchat.py ──────────────────────────────────────────────────────

$DEST_PY = "$INSTALL_DIR\termchat.py"
Write-Step "Downloading termchat..."
Invoke-WebRequest -Uri "$REPO/termchat.py" -OutFile $DEST_PY
Write-Ok "Downloaded termchat.py"

# ── Create chat.cmd wrapper ───────────────────────────────────────────────────

$WRAPPER = "$INSTALL_DIR\chat.cmd"
@"
@echo off
"$PYTHON" "$DEST_PY" %*
"@ | Set-Content -Path $WRAPPER
Write-Ok "Created chat.cmd"

# ── Add to PATH ───────────────────────────────────────────────────────────────

$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($currentPath -notlike "*$INSTALL_DIR*") {
    [Environment]::SetEnvironmentVariable("PATH", "$INSTALL_DIR;$currentPath", "User")
    $env:PATH = "$INSTALL_DIR;$env:PATH"
    Write-Ok "Added to user PATH"
    Write-Warn "Open a new terminal window for 'chat' to work."
} else {
    Write-Ok "Already in PATH"
}

# ── Done ──────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Ok "termchat installed!"
Write-Host ""
Write-Host "  c/pub          join the public room" -ForegroundColor Cyan
Write-Host "  c/<id>         join a private room" -ForegroundColor Cyan
Write-Host "  c/<id>/<pw>    join a password room" -ForegroundColor Cyan
Write-Host "  c/end          leave (or Ctrl-C)" -ForegroundColor Cyan
Write-Host ""
Write-Warn "Open a new terminal window, then type: c/pub"
Write-Host ""
