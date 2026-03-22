# termchat installer
# irm https://raw.githubusercontent.com/TheNeoNovo/Termchat/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$REPO = "https://raw.githubusercontent.com/TheNeoNovo/Termchat/main"

function Ok   { Write-Host "  [ok] $args" -ForegroundColor Green }
function Warn { Write-Host "  [!]  $args" -ForegroundColor Yellow }
function Fail { Write-Host "  [x]  $args" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  termchat installer" -ForegroundColor Cyan
Write-Host ""

# ── Python ────────────────────────────────────────────────────────────────────

function Find-Python {
    $machinePath = [Environment]::GetEnvironmentVariable("PATH","Machine")
    $userPath    = [Environment]::GetEnvironmentVariable("PATH","User")
    $env:PATH    = "$machinePath;$userPath"
    foreach ($cmd in @("python","python3","py")) {
        try {
            $ok = & $cmd -c "import sys;print(int(sys.version_info>=(3,7)))" 2>$null
            if ($ok -eq "1") { return $cmd }
        } catch {}
    }
    return $null
}

$PYTHON = Find-Python

if (-not $PYTHON) {
    Warn "Python 3.7+ not found."
    $ans = Read-Host "  Install Python now? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        $tmp = "$env:TEMP\python_installer.exe"
        Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe" -OutFile $tmp -UseBasicParsing
        Start-Process -FilePath $tmp -ArgumentList "/quiet","InstallAllUsers=0","PrependPath=1","Include_launcher=0" -Wait
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
        $machinePath = [Environment]::GetEnvironmentVariable("PATH","Machine")
        $userPath    = [Environment]::GetEnvironmentVariable("PATH","User")
        $env:PATH    = "$machinePath;$userPath"
        $PYTHON      = Find-Python
        if (-not $PYTHON) {
            Warn "Open a new terminal and run the install command again."
            exit 0
        }
    } else { Fail "Python 3.7+ required. https://python.org" }
}

$pyVer = & $PYTHON --version 2>&1
Ok "Python: $pyVer"

# ── Install ───────────────────────────────────────────────────────────────────

$DIR = "$env:USERPROFILE\.termchat"
New-Item -ItemType Directory -Force -Path $DIR | Out-Null

Invoke-WebRequest -Uri "$REPO/termchat.py" -OutFile "$DIR\termchat.py" -UseBasicParsing
Ok "Downloaded termchat.py"

Set-Content -Path "$DIR\chat.cmd" -Value "@echo off`r`n`"$PYTHON`" `"$DIR\termchat.py`" %*"
Ok "Created chat command"

$cur = [Environment]::GetEnvironmentVariable("PATH","User")
if ($cur -notlike "*$DIR*") {
    [Environment]::SetEnvironmentVariable("PATH","$DIR;$cur","User")
    $env:PATH = "$DIR;$env:PATH"
    Ok "Added to PATH"
}

# ── Done ──────────────────────────────────────────────────────────────────────

Write-Host ""
Ok "termchat installed — open a new terminal and type:"
Write-Host ""
Write-Host "    chat <room>     join a room" -ForegroundColor Cyan
Write-Host "    chat list       see rooms on LAN" -ForegroundColor Cyan
Write-Host ""
