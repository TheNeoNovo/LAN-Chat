# termchat installer — installs via NEO Launcher
# irm https://raw.githubusercontent.com/TheNeoNovo/Termchat/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$NEO_REPO = "https://raw.githubusercontent.com/TheNeoNovo/NEO-Launcher/main"

function Ok   { Write-Host "  [ok] $args" -ForegroundColor Green }
function Warn { Write-Host "  [!]  $args" -ForegroundColor Yellow }
function Fail { Write-Host "  [x]  $args" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  termchat installer" -ForegroundColor Cyan
Write-Host ""

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

$NEO_DIR = "$env:USERPROFILE\.neo"
$NEO_BIN = "$NEO_DIR\bin"
$NEO_PY  = "$NEO_DIR\neo.py"

if (Test-Path $NEO_PY) {
    Ok "NEO Launcher already installed"
} else {
    Write-Host "  Installing NEO Launcher first..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $NEO_DIR | Out-Null
    New-Item -ItemType Directory -Force -Path $NEO_BIN | Out-Null
    Invoke-WebRequest -Uri "$NEO_REPO/neo.py" -OutFile $NEO_PY -UseBasicParsing
    Set-Content -Path "$NEO_BIN\neo.cmd" -Value "@echo off`r`n`"$PYTHON`" `"$NEO_PY`" %*"
    $cur = [Environment]::GetEnvironmentVariable("PATH","User")
    if ($cur -notlike "*$NEO_BIN*") {
        [Environment]::SetEnvironmentVariable("PATH","$NEO_BIN;$cur","User")
        $env:PATH = "$NEO_BIN;$env:PATH"
    }
    Ok "NEO Launcher installed"
}

Write-Host "  Installing chat..." -ForegroundColor Cyan
& $PYTHON $NEO_PY install chat

Write-Host ""
Ok "Done — open a new terminal and type:"
Write-Host ""
Write-Host "    chat <room>       join a room" -ForegroundColor Cyan
Write-Host "    neo list          see all apps" -ForegroundColor Cyan
Write-Host ""
