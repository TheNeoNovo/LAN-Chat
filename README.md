# termchat

LAN terminal chat. No internet. No accounts. No servers.

## Install

**Linux / macOS:**
```sh
curl -fsSL https://raw.githubusercontent.com/TheNeoNovo/Termchat/main/install.sh | sh
```

**Windows PowerShell:**
```powershell
irm https://raw.githubusercontent.com/TheNeoNovo/Termchat/main/install.ps1 | iex
```

## Commands

```
chat <room>         join or create a room
chat <room> <pw>    join a password-protected room
chat list           list rooms on LAN
chat update         update termchat
chat uninstall      remove termchat
```

## Requirements

- Python 3.7+ (installer handles this)
- Same WiFi / LAN as who you want to chat with
