# termchat

**LAN terminal chat. No internet. No accounts. No servers. Just your network.**

```
  termchat v1.0.0

  c/pub           join public room
  c/<id>          join private room
  c/<id>/<pw>     join password-protected room
  c/end           leave room
```

---

## Install

### Linux / macOS (one command)

```sh
curl -fsSL https://raw.githubusercontent.com/termc/termc/main/install.sh | sh
```

### Windows PowerShell (one command)

```powershell
irm https://raw.githubusercontent.com/termc/termc/main/install.ps1 | iex
```

The installer will:
- Detect your OS
- Check for Python 3.7+
- Offer to install Python if it's not found
- Download termchat
- Add the `chat` command to your PATH

---

## Usage

```sh
c/pub              # join the public room (anyone on LAN)
c/devteam          # join/create private room "devteam"
c/devteam/secret   # join/create password-protected room
c/end              # leave (or just Ctrl-C)
```

**How rooms work:**
- The first person to run a room command **becomes the host**
- Others on your LAN discover the room automatically via mDNS
- When the host leaves, the **next person becomes host silently**
- When the room is empty, it's **gone** — no trace left

---

## Commands

| Command | What it does |
|---------|-------------|
| `/help` | Show all commands |
| `/who` | List users in this room |
| `/list` | Scan LAN for open rooms |
| `/dm <name>` | Start a private DM session |
| `/dm` | Exit DM mode, back to room |
| `/nick <name>` | Change your display name |
| `/leave` | Leave the room |
| `@name` | Mention someone (they see it highlighted) |
| `↑ ↓` arrows | Scroll message history |
| `Ctrl-C` | Quit |

---

## How it works

```
You (host)                      Others on LAN
────────────────────────────────────────────────
c/myroom                     c/myroom
    │                               │
    ├── Binds TCP on port 47331      ├── Sends mDNS multicast
    ├── Announces via UDP multicast  │   discovers room
    │                               ├── Connects to your IP
    │◄──────────────── TCP ─────────┤
    │                               │
    │   Messages flow both ways      │
    └── History kept in memory  ────┘
        until room closes
```

- **No internet** — stays 100% on your LAN
- **No accounts** — uses your OS username automatically
- **No config** — works out of the box
- **No servers** — whoever joins first hosts
- **No persistence** — rooms die when empty

---

## Requirements

- Python 3.7+ (installer can install this for you)
- Same WiFi / LAN network as the people you want to chat with
- Ports: UDP 5353 (mDNS discovery), TCP 47331 (chat)

---

## Firewall note

If users can't find each other's rooms, check that UDP multicast (224.0.0.251:5353) and TCP port 47331 are allowed on your local network firewall.

On Linux:
```sh
sudo ufw allow 47331/tcp
sudo ufw allow 5353/udp
```

---

## Uninstall

```sh
rm ~/.local/bin/chat ~/.local/bin/termchat.py
```

Windows: delete `%USERPROFILE%\.termchat` and remove it from your PATH.
