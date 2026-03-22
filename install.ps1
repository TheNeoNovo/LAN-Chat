# termchat Windows Installer (PowerShell)
# Run with: irm https://raw.githubusercontent.com/TheNeoNovo/LAN-Chat/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$REPO = "https://raw.githubusercontent.com/TheNeoNovo/LAN-Chat/main"

function Write-Step { Write-Host "  $args" -ForegroundColor Cyan }
function Write-Ok   { Write-Host "  [OK] $args" -ForegroundColor Green }
function Write-Warn { Write-Host "  [!]  $args" -ForegroundColor Yellow }
function Write-Fail { Write-Host "  [X]  $args" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  termchat installer" -ForegroundColor Cyan -NoNewline
Write-Host " - LAN terminal chat" -ForegroundColor DarkGray
Write-Host ""

# ── Find Python ───────────────────────────────────────────────────────────────

function Find-Python {
    # Refresh PATH from registry first
    $machinePath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
    $userPath    = [Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH    = "$machinePath;$userPath"

    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $ok = & $cmd -c "import sys; print(int(sys.version_info>=(3,7)))" 2>$null
            if ($ok -eq "1") { return $cmd }
        } catch {}
    }
    return $null
}

$PYTHON = Find-Python

if (-not $PYTHON) {
    Write-Warn "Python 3.7+ not found."
    $ans = Read-Host "  Install Python now? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        Write-Step "Downloading Python 3.12 installer..."
        $pyUrl = "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe"
        $tmp   = "$env:TEMP\python_installer.exe"
        Invoke-WebRequest -Uri $pyUrl -OutFile $tmp -UseBasicParsing
        Write-Step "Installing Python (this may take a minute)..."
        Start-Process -FilePath $tmp -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=0" -Wait
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue

        # Reload PATH and try again
        $machinePath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
        $userPath    = [Environment]::GetEnvironmentVariable("PATH", "User")
        $env:PATH    = "$machinePath;$userPath"
        $PYTHON      = Find-Python

        if (-not $PYTHON) {
            Write-Warn "Python installed but this terminal can't see it yet."
            Write-Warn "Please close this window, open a NEW terminal, and run:"
            Write-Host ""
            Write-Host "  irm https://raw.githubusercontent.com/TheNeoNovo/LAN-Chat/main/install.ps1 | iex" -ForegroundColor Cyan
            Write-Host ""
            exit 0
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
Invoke-WebRequest -Uri "$REPO/termchat.py" -OutFile $DEST_PY -UseBasicParsing
Write-Ok "Downloaded termchat.py"

# ── Create c.cmd wrapper ──────────────────────────────────────────────────────

$WRAPPER = "$INSTALL_DIR\c.cmd"
Set-Content -Path $WRAPPER -Value "@echo off`r`n`"$PYTHON`" `"$DEST_PY`" %*"
Write-Ok "Created c.cmd"

# ── Add to PATH ───────────────────────────────────────────────────────────────

$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($currentPath -notlike "*$INSTALL_DIR*") {
    [Environment]::SetEnvironmentVariable("PATH", "$INSTALL_DIR;$currentPath", "User")
    $env:PATH = "$INSTALL_DIR;$env:PATH"
    Write-Ok "Added to PATH"
} else {
    Write-Ok "Already in PATH"
}

# ── Done ──────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Ok "termchat installed!"
Write-Host ""
Write-Host "  Open a NEW terminal window, then type:" -ForegroundColor Yellow
Write-Host ""
Write-Host "    c/pub          join the public room" -ForegroundColor Cyan
Write-Host "    c/<id>         join a private room" -ForegroundColor Cyan
Write-Host "    c/<id>/<pw>    join a password room" -ForegroundColor Cyan
Write-Host "    c/dm/<name>    DM someone" -ForegroundColor Cyan
Write-Host "    c/list         see rooms on LAN" -ForegroundColor Cyan
Write-Host "    c/help         show all commands" -ForegroundColor Cyan
Write-Host ""
