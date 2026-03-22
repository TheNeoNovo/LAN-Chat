# termchat

LAN terminal chat. No internet. No accounts. No servers. Just your network.

## Install

**Linux / macOS:**
```sh
curl -fsSL https://raw.githubusercontent.com/TheNeoNovo/Termchat/main/install.sh | sh
```

**Windows PowerShell:**
```powershell
irm https://raw.githubusercontent.com/TheNeoNovo/Termchat/main/install.ps1 | iex
```

---

## Commands

```
chat pub              join the public room
chat <id>             join or create a private room
chat <id> <pw>        join a password-protected room
chat dm <id>          open a DM with someone
chat list             scan LAN for open rooms
chat who              see who is in a room
chat status <s>       set your status (online / away / busy)
chat update           update to latest version
chat uninstall        remove termchat
chat help             show all commands
```

---

## Inside a room

- Type and press Enter to send
- `@name` to mention someone (highlighted for them)
- `/topic <text>` to set the room topic (host only)
- `/status <s>` to change your status mid-session
- Type `chat <cmd>` to leave the room and run a command
- Up/Down arrows to scroll history
- Ctrl-C to quit

---

## Layout

```
┌─ LAN Rooms ──┬─── Messages ──────────────┬─ Users ────┐
│ #pub      *  │  12:00:01 alice - hey!     │ 2 online   │
│ #devroom     │  12:00:05 bob - hi         │ ^ alice    │
│              │  * bob joined              │  ● bob     │
├──────────────┴───────────────────────────┴────────────┤
│ alice > _                                              │
└────────────────────────────────────────────────────────┘
```

---

## Statuses

- `●` online  `○` away  `◆` busy

---

## How it works

- No internet — stays 100% on your LAN
- No accounts — uses your OS username automatically
- First person to join becomes the host
- Host transfers silently when they leave
- Room disappears when everyone leaves
- Auto-reconnects if host temporarily drops

---

## Requirements

- Python 3.7+  (installer handles this)
- Same WiFi / LAN as who you want to chat with
- Ports: UDP 5353 (discovery), TCP 47331 (chat)
