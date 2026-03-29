# termchat

LAN terminal chat. or sum idrk

## Install

**Linux / macOS:**
```sh
curl -fsSL https://raw.githubusercontent.com/TheNeoNovo/Termchat/main/install.sh | sh
```

**Windows PowerShell:**
```powershell
irm https://raw.githubusercontent.com/TheNeoNovo/Termchat/main/install.ps1 | iex
```

The installer detects your OS and installs Python if needed and adds the `chat` command to your PATH.

---

## Commands

```
chat pub              join the public room
chat <id>             join or create a private room
chat <id> <pw>        join a password-protected room
chat dm <id>          open a DM with someone (Working but needs a update)
chat list             scan LAN for open rooms
chat who              see who is in a room
chat help             show all commands
chat                  show all commands
```

To leave — run a new `chat` command or press `Ctrl-C`.

---

## Requirements

- Python 3.7+ (installer handles this)
- Same WiFi / LAN as who you want to chat with
- Ports: UDP 5353 (discovery), TCP 47331 (chat)

---

## Firewall

If rooms can't find each other:

**Linux:** `sudo ufw allow 47331/tcp && sudo ufw allow 5353/udp`

**Windows:** Allow Python through Windows Defender Firewall when prompted.

---

## Uninstall

**Linux / macOS:** `rm ~/.local/bin/chat ~/.local/bin/termchat.py`

**Windows:** Delete `%USERPROFILE%\.termchat` and remove it from PATH in System Settings.

(Or just you know chat uninstall)
