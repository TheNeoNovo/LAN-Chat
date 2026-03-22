# termchat

LAN terminal chat. No internet. No accounts. No servers. Just your network.

## Install

**Linux / macOS:**
```sh
curl -fsSL https://raw.githubusercontent.com/TheNeoNovo/LAN-Chat/main/install.sh | sh
```

**Windows PowerShell:**
```powershell
irm https://raw.githubusercontent.com/TheNeoNovo/LAN-Chat/main/install.ps1 | iex
```

The installer detects your OS, installs Python if needed, downloads termchat, and adds the `c` command to your PATH.

---

## Commands

```
c/pub              join the public room
c/<id>             join or create a private room
c/<id>/<pw>        join or create a password-protected room
c/dm/<name>        open a DM with someone
c/list             scan LAN for open rooms
c/who              see who is in a room
c/help             show all commands
```

To leave a room — just run a new `c/` command or press `Ctrl-C`.

---

## Inside a room

- Type normally to chat
- `@name` to mention someone (highlighted for them)
- `↑ ↓` arrows to scroll message history
- `Ctrl-C` to quit

---

## How it works

- No internet — stays 100% on your LAN
- No accounts — uses your OS username automatically
- No config — works out of the box
- First person to join a room becomes the host
- When the host leaves, the next person silently takes over
- When everyone leaves, the room is gone

---

## Requirements

- Python 3.7+ (installer handles this)
- Same WiFi / LAN network as who you want to chat with
- Ports: UDP 5353 (discovery), TCP 47331 (chat)

---

## Firewall note

If rooms can't find each other, allow these ports:

**Linux:**
```sh
sudo ufw allow 47331/tcp
sudo ufw allow 5353/udp
```

**Windows:** Allow Python through Windows Defender Firewall when prompted.

---

## Uninstall

**Linux / macOS:**
```sh
rm ~/.local/bin/c ~/.local/bin/termchat.py
```

**Windows:** Delete `%USERPROFILE%\.termchat` and remove it from your PATH in System Settings.
