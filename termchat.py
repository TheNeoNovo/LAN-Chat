#!/usr/bin/env python3
"""
termchat — LAN chat

  chat <room>         join or create a room
  chat <room> <pw>    join a password-protected room
  chat list           list rooms on LAN
  chat update         update termchat
  chat uninstall      remove termchat
"""

import sys, os, socket, threading, time, json, hashlib, struct, signal, re
from datetime import datetime

WINDOWS     = sys.platform == "win32"
VERSION     = "3.0.0"
MCAST_GROUP = "224.0.0.251"
MCAST_PORT  = 5353
CHAT_PORT   = 47331
REPO        = "https://raw.githubusercontent.com/TheNeoNovo/Termchat/main"

if WINDOWS:
    import msvcrt
else:
    import select, termios, tty, fcntl

# ── Colors ────────────────────────────────────────────────────────────────────

RST  = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
BCYN = "\033[96m"; BWHT = "\033[97m"; BYEL = "\033[93m"
BGRN = "\033[92m"; BRED = "\033[91m"; BMAG = "\033[95m"
BBLU = "\033[94m"

PALETTE = [BCYN, BGRN, BYEL, BMAG, BBLU, BRED, BWHT]
def nc(n): return PALETTE[sum(ord(c) for c in n) % len(PALETTE)]
def strip_ansi(s): return re.sub(r'\033\[[0-9;]*m', '', s)

# ── Wire protocol ─────────────────────────────────────────────────────────────

def encode(obj):
    d = json.dumps(obj).encode()
    return struct.pack(">I", len(d)) + d

def decode_from(sock):
    raw = _recv(sock, 4)
    if not raw: return None
    n = struct.unpack(">I", raw)[0]
    if n > 1_000_000: return None
    d = _recv(sock, n)
    return json.loads(d) if d else None

def _recv(sock, n):
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
            if not chunk: return None
            buf += chunk
        except: return None
    return buf

# ── Discovery ─────────────────────────────────────────────────────────────────

class Announcer:
    def __init__(self, room_id, room_type, port, pw_hash=""):
        self.payload = json.dumps({
            "type": "announce", "room_id": room_id,
            "room_type": room_type, "port": port, "pw_hash": pw_hash,
        }).encode()
        self.running = False

    def start(self):
        self.running = True
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False
        try: self._sock.close()
        except: pass

    def _loop(self):
        while self.running:
            try: self._sock.sendto(self.payload, (MCAST_GROUP, MCAST_PORT))
            except: pass
            time.sleep(2)

class Discovery:
    def __init__(self):
        self.rooms = {}
        self._running = True

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError: pass
        s.bind(("", MCAST_PORT))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                     struct.pack("4sL", socket.inet_aton(MCAST_GROUP), socket.INADDR_ANY))
        s.settimeout(0.5)
        self._sock = s
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False
        try: self._sock.close()
        except: pass

    def _loop(self):
        while self._running:
            try:
                data, addr = self._sock.recvfrom(4096)
                m = json.loads(data)
                if m.get("type") == "announce":
                    self.rooms[m["room_id"]] = {
                        "addr": addr[0], "port": m["port"],
                        "type": m["room_type"],
                    }
            except socket.timeout: pass
            except: pass

    def find(self, room_id, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            if room_id in self.rooms: return self.rooms[room_id]
            time.sleep(0.1)
        return None

    def scan(self, timeout=3.0):
        time.sleep(timeout)
        return dict(self.rooms)

# ── Host ──────────────────────────────────────────────────────────────────────

class Host:
    def __init__(self, room_id, room_type, password, username):
        self.room_id   = room_id
        self.room_type = room_type
        self.password  = password
        self.username  = username
        self.clients   = {}
        self.history   = []
        self._lock     = threading.Lock()
        self.port      = CHAT_PORT
        self.running   = False
        self._on_msg   = None   # callback(sender, text)
        self._on_join  = None   # callback(name)
        self._on_leave = None   # callback(name)

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        for p in range(CHAT_PORT, CHAT_PORT + 20):
            try: s.bind(("", p)); self.port = p; break
            except OSError: continue
        s.listen(64); s.settimeout(1.0)
        self._sock = s; self.running = True
        pw_hash = hashlib.sha256(self.password.encode()).hexdigest() if self.password else ""
        self.announcer = Announcer(self.room_id, self.room_type, self.port, pw_hash)
        self.announcer.start()
        threading.Thread(target=self._accept, daemon=True).start()

    def stop(self):
        self.running = False
        try: self.announcer.stop()
        except: pass
        try: self._sock.close()
        except: pass

    def _accept(self):
        while self.running:
            try:
                conn, _ = self._sock.accept()
                threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
            except socket.timeout: pass
            except: break

    def _handle(self, conn):
        name = None
        try:
            pkt = decode_from(conn)
            if not pkt or pkt.get("type") != "join": conn.close(); return
            name = pkt.get("name", "?")[:32]
            pw   = pkt.get("password", "")

            if self.room_type == "password":
                exp = hashlib.sha256((self.room_id + self.password).encode()).hexdigest()
                got = hashlib.sha256((self.room_id + pw).encode()).hexdigest()
                if exp != got:
                    conn.sendall(encode({"type": "error", "msg": "Wrong password"}))
                    conn.close(); return

            ghost = name == "__who__"
            with self._lock: self.clients[name] = conn
            for h in self.history[-200:]: conn.sendall(encode(h))
            conn.sendall(encode({
                "type": "joined", "host": self.username,
                "users": [n for n in self.clients] + [self.username],
            }))
            if not ghost:
                self._broadcast({"type": "sys", "msg": f"{name} joined"}, skip=name)
                if self._on_join: self._on_join(name)

            while self.running:
                p = decode_from(conn)
                if not p: break
                if p.get("type") == "chat":
                    rec = {"type": "chat", "name": name,
                           "text": p.get("text", "")[:500],
                           "ts":   p.get("ts", "")}
                    self.history.append(rec)
                    self._broadcast(rec)
                    if self._on_msg: self._on_msg(name, rec["text"], rec["ts"])
        except: pass
        finally:
            if name:
                with self._lock: self.clients.pop(name, None)
                if not (name == "__who__"):
                    self._broadcast({"type": "sys", "msg": f"{name} left"})
                    if self._on_leave: self._on_leave(name)
            try: conn.close()
            except: pass

    def _broadcast(self, msg, skip=None):
        data = encode(msg)
        with self._lock:
            dead = []
            for n, s in self.clients.items():
                if n == skip: continue
                try: s.sendall(data)
                except: dead.append(n)
            for n in dead: del self.clients[n]

    def send(self, text):
        ts = datetime.now().strftime("%H:%M")
        rec = {"type": "chat", "name": self.username, "text": text, "ts": ts}
        self.history.append(rec)
        self._broadcast(rec)

# ── Client ────────────────────────────────────────────────────────────────────

class Client:
    def __init__(self, username, password=""):
        self.username  = username
        self.password  = password
        self._sock     = None
        self.running   = False
        self._on_msg   = None
        self._on_sys   = None
        self._on_join  = None
        self._on_leave = None
        self._room_info = None

    def connect(self, addr, port):
        self._room_info = (addr, port)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0); s.connect((addr, port)); s.settimeout(None)
        self._sock = s
        s.sendall(encode({"type": "join", "name": self.username,
                          "password": self.password}))
        resp = decode_from(s)
        if not resp: raise ConnectionError("No response")
        if resp.get("type") == "error": raise ConnectionError(resp.get("msg", "Refused"))
        if resp.get("type") != "joined": raise ConnectionError("Bad handshake")
        self.running = True
        threading.Thread(target=self._recv, daemon=True).start()
        return resp.get("users", [])

    def _recv(self):
        while self.running:
            try:
                p = decode_from(self._sock)
                if not p: break
                t = p.get("type")
                if t == "chat" and self._on_msg:
                    self._on_msg(p["name"], p["text"], p.get("ts", ""))
                elif t == "sys" and self._on_sys:
                    self._on_sys(p.get("msg", ""))
            except: break
        self.running = False
        if self._on_sys: self._on_sys("Disconnected. Reconnecting...")
        self._reconnect()

    def _reconnect(self, attempts=5):
        for i in range(attempts):
            time.sleep(2)
            if not self.running and self._on_sys:
                pass
            try:
                addr, port = self._room_info
                self.connect(addr, port)
                if self._on_sys: self._on_sys("Reconnected.")
                return
            except: pass
        if self._on_sys: self._on_sys("Could not reconnect.")

    def send(self, text):
        ts = datetime.now().strftime("%H:%M")
        self._sock.sendall(encode({"type": "chat", "text": text, "ts": ts}))

    def disconnect(self):
        self.running = False
        try: self._sock.close()
        except: pass

# ── Chat session ──────────────────────────────────────────────────────────────

def run_chat(room_id, room_type, password, username):
    host   = None
    client = None
    lines  = []   # all printed lines for redraw
    running = threading.Event(); running.set()
    lock   = threading.Lock()

    cols = lambda: __import__('shutil').get_terminal_size().columns

    def header():
        w   = cols()
        ts  = datetime.now().strftime("%H:%M")
        mid = f" termchat  |  {room_id}  |  {username}  |  {ts} "
        pad = w - len(mid)
        lp  = pad // 2; rp = pad - lp
        sys.stdout.write(f"\033[1;1H\033[2K{DIM}{'-'*lp}{RST}{BOLD}{mid}{RST}{DIM}{'-'*rp}{RST}\n")

    def rewrite_input(buf=""):
        w = cols()
        prompt = f"{nc(username)}{BOLD}{username}{RST} > "
        sys.stdout.write(f"\033[{term_rows()};1H\033[2K{prompt}{BWHT}{buf}{RST}")
        sys.stdout.flush()

    def term_rows():
        try: return __import__('shutil').get_terminal_size().lines
        except: return 24

    def print_line(line):
        with lock:
            rows = term_rows()
            # move to line above input, scroll up, print
            sys.stdout.write(f"\033[{rows-1};1H\033[S\033[{rows-1};1H\033[2K{line}\n")
            sys.stdout.flush()

    def on_msg(sender, text, ts):
        col = nc(sender)
        print_line(f"{DIM}{ts}{RST}  {col}{BOLD}{sender}{RST}  {text}")
        rewrite_input(inp[0])

    def on_sys(msg):
        print_line(f"{DIM}* {msg}{RST}")
        rewrite_input(inp[0])

    inp = [""]   # defined early so all closures can safely access it

    # Setup screen
    sys.stdout.write("\033[2J\033[H")
    header()
    sys.stdout.flush()

    # Start header refresh
    def hdr_loop():
        while running.is_set():
            with lock:
                header()
                rewrite_input(inp[0])
            time.sleep(30)
    threading.Thread(target=hdr_loop, daemon=True).start()

    # Discover / host
    disc = Discovery(); disc.start()
    on_sys(f"Looking for {room_id}...")
    found = disc.find(room_id)
    disc.stop()

    if found:
        client = Client(username, password)
        client._on_msg  = on_msg
        client._on_sys  = on_sys
        try:
            users = client.connect(found["addr"], found["port"])
            on_sys(f"Joined {room_id}  ({len(users)} online)")
        except ConnectionError as e:
            print(f"{BRED}Error: {e}{RST}"); return
    else:
        host = Host(room_id, room_type, password, username)
        host._on_msg  = on_msg
        host._on_join = lambda n: on_sys(f"{n} joined")
        host._on_leave= lambda n: on_sys(f"{n} left")
        host.start()
        on_sys(f"Created {room_id}  (you are host)")

    rewrite_input()

    # ── Input loop ────────────────────────────────────────────────────────────
    old_term = None
    try:
        if not WINDOWS:
            old_term = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin.fileno())
            fl = fcntl.fcntl(sys.stdin.fileno(), fcntl.F_GETFL)
            fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, fl | os.O_NONBLOCK)

        while running.is_set():
            if WINDOWS:
                if not msvcrt.kbhit(): time.sleep(0.05); continue
                ch = msvcrt.getwch(); code = ord(ch)
            else:
                r, _, _ = select.select([sys.stdin], [], [], 0.1)
                if not r: continue
                try: ch = sys.stdin.read(1)
                except: continue
                if not ch: continue
                code = ord(ch)

            if WINDOWS and code in (0, 224):
                msvcrt.getwch(); continue   # skip arrow keys silently

            if code == 3:   # Ctrl-C
                running.clear(); break
            elif ch in ('\r', '\n') or code == 13:
                text = inp[0].strip()
                inp[0] = ""
                if text:
                    if text.lower() == "chat end":
                        running.clear(); break
                    elif text.lower() == "chat help":
                        on_sys("Commands: chat <room>  chat list  chat end  chat update  chat uninstall  chat help")
                    elif host:  host.send(text);   on_msg(username, text, datetime.now().strftime("%H:%M"))
                    elif client: client.send(text); on_msg(username, text, datetime.now().strftime("%H:%M"))
                rewrite_input()
            elif code in (8, 127):
                inp[0] = inp[0][:-1]
                rewrite_input(inp[0])
            elif 32 <= code < 127:
                inp[0] += ch
                rewrite_input(inp[0])

    finally:
        if not WINDOWS and old_term:
            try: termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_term)
            except: pass
        if client: client.disconnect()
        if host:   host.stop()
        running.clear()
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        print(f"{DIM}Left {room_id}.{RST}")

# ── Non-chat commands ─────────────────────────────────────────────────────────

def cmd_list():
    print(f"{DIM}Scanning...{RST}", flush=True)
    d = Discovery(); d.start()
    rooms = d.scan(3.0); d.stop()
    if not rooms:
        print(f"{DIM}No rooms found.{RST}"); return
    for rid, info in rooms.items():
        kind = {"pub": "public", "private": "private",
                "password": "password"}.get(info.get("type",""), "room")
        print(f"  {BCYN}{rid}{RST}  {DIM}{kind}  {info['addr']}{RST}")

def cmd_update():
    import urllib.request
    script = os.path.abspath(__file__)
    print(f"{DIM}Checking for update...{RST}", flush=True)
    try:
        with urllib.request.urlopen(f"{REPO}/termchat.py", timeout=8) as r:
            src = r.read()
        new_ver = VERSION
        for line in src.decode().splitlines():
            if line.strip().startswith("VERSION"):
                try: new_ver = line.split('"')[1]
                except: pass
                break
        if new_ver == VERSION:
            print(f"{BGRN}Already up to date{RST} (v{VERSION})"); return
        with open(script, "wb") as f: f.write(src)
        print(f"{BGRN}Updated{RST} v{VERSION} -> v{new_ver}")
    except Exception as e:
        print(f"{BRED}Update failed:{RST} {e}")

def cmd_uninstall():
    script = os.path.abspath(__file__)
    folder = os.path.dirname(script)
    print(f"{BYEL}This will remove termchat.{RST}")
    ans = input("Sure? [y/N] ").strip().lower()
    if ans != "y": print(f"{DIM}Cancelled.{RST}"); return
    for f in [script,
              os.path.join(folder, "chat"),
              os.path.join(folder, "chat.cmd")]:
        if os.path.exists(f):
            try: os.remove(f); print(f"  {DIM}Removed {f}{RST}")
            except Exception as e: print(f"  {DIM}Could not remove {f}: {e}{RST}")
    print(f"{DIM}Done.{RST}")

def cmd_help():
    print(f"{BOLD}termchat{RST} v{VERSION}")
    print()
    print(f"  {BCYN}chat <room>{RST}         join or create a room")
    print(f"  {BCYN}chat <room> <pw>{RST}     join a password-protected room")
    print(f"  {BCYN}chat list{RST}            list rooms on LAN")
    print(f"  {BCYN}chat end{RST}             leave current room (or Ctrl-C)")
    print(f"  {BCYN}chat update{RST}          update termchat")
    print(f"  {BCYN}chat uninstall{RST}       remove termchat")
    print(f"  {BCYN}chat help{RST}            show this")
    print()

def get_username():
    return (os.environ.get("USER") or os.environ.get("USERNAME") or
            os.environ.get("LOGNAME") or "user")[:32]

def main():
    args = sys.argv[1:]
    if not args:
        print(f"{BOLD}termchat{RST} v{VERSION}")
        print(f"  chat <room>          join or create a room")
        print(f"  chat <room> <pw>     join a password room")
        print(f"  chat list            list rooms on LAN")
        print(f"  chat end             leave current room")
        print(f"  chat update          update termchat")
        print(f"  chat uninstall       remove termchat")
        print(f"  chat help            show this")
        return

    cmd = args[0].lower()

    if cmd == "help":        cmd_help()
    elif cmd == "list":      cmd_list()
    elif cmd == "update":    cmd_update()
    elif cmd == "uninstall": cmd_uninstall()
    elif cmd == "end":
        print(f"{DIM}Not in a room.{RST}")
    elif cmd == "pub":
        run_chat("pub", "pub", "", get_username())
    else:
        room_id  = cmd
        password = args[1] if len(args) > 1 else ""
        run_chat(room_id, "password" if password else "private", password, get_username())

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print(f"\n{DIM}Bye.{RST}")
