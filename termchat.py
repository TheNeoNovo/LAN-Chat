#!/usr/bin/env python3
"""
termchat v2.0 — LAN terminal chat

  chat pub              join public room
  chat <id>             join/create private room
  chat <id> <pw>        join password-protected room
  chat dm <id>          open DM with someone
  chat list             scan LAN for open rooms
  chat who              see who is in a room
  chat update           update to latest version
  chat uninstall        remove termchat
  chat help             show help
"""

import sys, os, socket, threading, time, json, hashlib, struct, signal, re
from datetime import datetime

WINDOWS = sys.platform == "win32"
if WINDOWS:
    import msvcrt
else:
    import select, termios, tty, fcntl

VERSION     = "2.0.0"
MCAST_GROUP = "224.0.0.251"
MCAST_PORT  = 5353
CHAT_PORT   = 47331
MAX_MSG     = 400
REPO        = "https://raw.githubusercontent.com/TheNeoNovo/Termchat/main"

# ── Colors ────────────────────────────────────────────────────────────────────

class C:
    RST  = "\033[0m";  BOLD = "\033[1m";  DIM  = "\033[2m";  REV  = "\033[7m"
    YEL  = "\033[33m"
    BRED = "\033[91m"; BGRN = "\033[92m"; BYEL = "\033[93m"
    BBLU = "\033[94m"; BMAG = "\033[95m"; BCYN = "\033[96m"; BWHT = "\033[97m"
    BG   = "\033[40m"

PALETTE = [C.BCYN, C.BGRN, C.BYEL, C.BMAG, C.BBLU, C.BRED, C.BWHT]
STATUS_ICON = {"online": "●", "away": "○", "busy": "◆"}
STATUS_COL  = {"online": C.BGRN, "away": C.BYEL, "busy": C.BRED}

def name_color(n): return PALETTE[sum(ord(c) for c in n) % len(PALETTE)]
def strip_ansi(s): return re.sub(r'\033\[[0-9;]*m', '', s)
def term_size():
    try:
        import shutil; s = shutil.get_terminal_size(); return s.columns, s.lines
    except: return 80, 24

# ── Config (persistent username + status) ────────────────────────────────────

def config_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, ".termchat")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "config.json")

def load_config():
    try:
        with open(config_path()) as f: return json.load(f)
    except: return {}

def save_config(cfg):
    try:
        with open(config_path(), "w") as f: json.dump(cfg, f)
    except: pass

def get_username():
    cfg = load_config()
    if cfg.get("username"): return cfg["username"]
    name = (os.environ.get("USER") or os.environ.get("USERNAME") or
            os.environ.get("LOGNAME") or "user")[:32]
    return name

def get_status():
    return load_config().get("status", "online")

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

# ── TUI ───────────────────────────────────────────────────────────────────────

class TUI:
    def __init__(self, username, room_id, room_type, status="online"):
        self.username  = username
        self.room_id   = room_id
        self.room_type = room_type
        self.status    = status
        self.topic     = ""
        self.messages  = []         # (ts, sender, text, kind)
        self.users     = {}         # name -> {host, status}
        self.lan_rooms = {}         # room_id -> info  (live from background scan)
        self.input_buf = ""
        self.scroll    = 0
        self.lock      = threading.Lock()
        self.running   = True
        self.is_host   = False
        self.typing_users = set()   # names currently typing
        self._old_term = None
        self._orig_fl  = None
        # pending command to run after room closes
        self.pending_cmd = None

    def raw_mode(self):
        if WINDOWS: return
        self._old_term = termios.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin.fileno())
        fl = fcntl.fcntl(sys.stdin.fileno(), fcntl.F_GETFL)
        fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, fl | os.O_NONBLOCK)
        self._orig_fl = fl

    def restore(self):
        if WINDOWS: return
        try:
            if self._old_term: termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_term)
            if self._orig_fl is not None: fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, self._orig_fl)
        except: pass

    def _w(self, s): sys.stdout.write(s)
    def _mv(self, r, c=1): self._w(f"\033[{r};{c}H")
    def _cl(self): self._w("\033[2K")
    def _clamp(self, n, lo, hi): return max(lo, min(hi, n))

    def render(self):
        with self.lock: self._render()

    def _render(self):
        cols, rows = term_size()

        # ── Layout ────────────────────────────────────────────────────────────
        # Left sidebar: LAN rooms  (14 cols)
        # Main chat area
        # Right sidebar: users     (16 cols)
        # Top bar: row 1
        # Bottom input: row N

        LSIDE = 15   # left sidebar width
        RSIDE = 17   # right sidebar width
        DIV   = 1    # divider col
        CW    = cols - LSIDE - RSIDE - 2  # chat width
        CH    = rows - 3                  # chat height (top bar + typing row + input)
        # column positions
        L_DIV = LSIDE + 1
        C_START = LSIDE + 2
        R_DIV = cols - RSIDE
        R_START = R_DIV + 1

        self._w("\033[?25l")

        # ── Top status bar ────────────────────────────────────────────────────
        self._mv(1, 1); self._cl()
        host_tag = f" {C.BYEL}[host]{C.RST}{C.BG}" if self.is_host else ""
        room_label = {
            "pub":      f"{C.BGRN}#pub{C.RST}{C.BG}",
            "private":  f"{C.BCYN}#{self.room_id}{C.RST}{C.BG}",
            "password": f"{C.BMAG}#{self.room_id}{C.RST}{C.BG}",
            "dm":       f"{C.BYEL}DM:{self.room_id}{C.RST}{C.BG}",
        }.get(self.room_type, f"#{self.room_id}")
        sc  = STATUS_COL.get(self.status, C.BGRN)
        si  = STATUS_ICON.get(self.status, "●")
        nc  = name_color(self.username)
        topic_str = f"  {C.DIM}│ {self.topic}{C.RST}{C.BG}" if self.topic else ""
        bar = (f"{C.BG}{C.BOLD}{C.BWHT} termchat{C.RST}{C.BG} {C.DIM}v{VERSION}{C.RST}{C.BG}"
               f"  {room_label}{host_tag}{topic_str}"
               f"  {sc}{si}{C.RST}{C.BG} {nc}{self.username}{C.RST}{C.BG}"
               f"{C.DIM}  chat help{C.RST}")
        pad = cols - len(strip_ansi(bar)) - 1
        self._w(bar + " " * max(0, pad))

        # ── Dividers ──────────────────────────────────────────────────────────
        for r in range(2, rows):
            self._mv(r, L_DIV);  self._w(f"{C.DIM}│{C.RST}")
            self._mv(r, R_DIV);  self._w(f"{C.DIM}│{C.RST}")

        # ── Left sidebar: LAN rooms ───────────────────────────────────────────
        self._mv(2, 1)
        self._w(f"{C.BOLD}{C.DIM} Rooms{C.RST}")
        lr = 3
        max_lr = rows - 2
        rooms_shown = list(self.lan_rooms.items())[:max_lr - lr]
        for rid, info in rooms_shown:
            self._mv(lr, 1); self._cl()
            kind_col = {"pub": C.BGRN, "private": C.BCYN,
                        "password": C.BMAG, "dm": C.BYEL}.get(info.get("type",""), C.BWHT)
            marker = "*" if rid == self.room_id else " "
            label  = rid[:LSIDE - 3]
            self._w(f" {kind_col}{marker}{label}{C.RST}")
            lr += 1
        while lr < max_lr:
            self._mv(lr, 1); self._cl(); lr += 1

        # ── Right sidebar: users ──────────────────────────────────────────────
        self._mv(2, R_START)
        self._w(f"{C.BOLD}{C.DIM}{len(self.users)} online{C.RST}")
        ur = 3
        for name, info in list(self.users.items())[:rows - 4]:
            self._mv(ur, R_START); self._cl()
            st   = info.get("status", "online")
            sc2  = STATUS_COL.get(st, C.BGRN)
            si2  = STATUS_ICON.get(st, "●")
            star = f"{C.BYEL}^{C.RST}" if info.get("host") else " "
            label = name[:RSIDE - 5]
            self._w(f"{star}{sc2}{si2}{C.RST} {name_color(name)}{label}{C.RST}")
            ur += 1
        while ur < rows - 1:
            self._mv(ur, R_START); self._cl(); ur += 1

        # ── Message area ──────────────────────────────────────────────────────
        lines  = self._render_lines(CW - 1)
        vstart = max(0, len(lines) - CH + self.scroll)
        vis    = lines[vstart:vstart + CH]
        for i, line in enumerate(vis):
            self._mv(2 + i, C_START); self._cl()
            pad = CW - len(strip_ansi(line)) - 1
            self._w(line + " " * max(0, pad))
        for i in range(len(vis), CH):
            self._mv(2 + i, C_START); self._cl()

        # ── Typing indicator row ──────────────────────────────────────────────
        self._mv(rows - 1, C_START); self._cl()
        if self.typing_users:
            names = ", ".join(list(self.typing_users)[:3])
            self._w(f"{C.DIM}{names} {'is' if len(self.typing_users)==1 else 'are'} typing...{C.RST}")

        # ── Input bar ─────────────────────────────────────────────────────────
        self._mv(rows, C_START); self._cl()
        prompt = f"{name_color(self.username)}{C.BOLD}{self.username}{C.RST} "
        max_w  = CW - len(strip_ansi(prompt)) - 4
        shown  = self.input_buf[-max_w:] if len(self.input_buf) > max_w else self.input_buf
        # character limit warning
        remaining = MAX_MSG - len(self.input_buf)
        warn_str = ""
        if remaining <= 50:
            col = C.BRED if remaining <= 10 else C.BYEL
            warn_str = f" {col}{remaining}{C.RST}"
        self._w(f"{prompt}{C.BWHT}{shown}{C.RST}>{warn_str} \033[?25l")
        sys.stdout.flush()

    def _render_lines(self, width):
        lines = []
        for ts, sender, text, kind in self.messages:
            if kind == "system":
                lines.append(f"{C.DIM}{C.YEL}* {text}{C.RST}")
            elif kind == "dm_in":
                lines.append(f"{C.BMAG}<- {sender}{C.RST}  {text}")
            elif kind == "dm_out":
                lines.append(f"{C.BMAG}-> {sender}{C.RST}  {text}")
            else:
                hi  = re.sub(r'@(\w+)',
                              lambda m: f"{C.REV}{C.BYEL}@{m.group(1)}{C.RST}"
                              if m.group(1) in self.users or m.group(1) == self.username
                              else m.group(0), text)
                col = name_color(sender)
                lines.append(f"{C.DIM}{ts}{C.RST} {col}{C.BOLD}{sender}{C.RST} - {hi}")
        return lines

    def msg(self, sender, text, kind="chat"):
        ts = datetime.now().strftime("%H:%M:%S")
        with self.lock: self.messages.append((ts, sender, text, kind))
        self._render()

    def sys(self, text): self.msg("", text, "system")

    def add_user(self, name, is_host=False, status="online"):
        with self.lock:
            new = name not in self.users
            self.users[name] = {"host": is_host, "status": status}
        if new and name != self.username: self.sys(f"{name} joined")
        self._render()

    def remove_user(self, name):
        with self.lock: self.users.pop(name, None)
        self.sys(f"{name} left")
        self._render()

    def set_host(self, name):
        with self.lock:
            for n in self.users: self.users[n]["host"] = (n == name)
        self.is_host = (name == self.username)
        self.sys("You are now host" if name == self.username else f"{name} is now host")
        self._render()

    def set_user_status(self, name, status):
        with self.lock:
            if name in self.users: self.users[name]["status"] = status
        self._render()

    def set_topic(self, topic):
        self.topic = topic
        self.sys(f"Topic set: {topic}" if topic else "Topic cleared")
        self._render()

    def update_lan_rooms(self, rooms):
        with self.lock: self.lan_rooms = dict(rooms)
        self._render()

    def set_typing(self, name, is_typing):
        with self.lock:
            if is_typing: self.typing_users.add(name)
            else: self.typing_users.discard(name)
        self._render()

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
                        "type": m["room_type"], "pw_hash": m.get("pw_hash", ""),
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
    def __init__(self, room_id, room_type, password, tui):
        self.room_id   = room_id
        self.room_type = room_type
        self.password  = password
        self.tui       = tui
        self.clients   = {}     # name -> {sock, status}
        self.history   = []
        self.topic     = ""
        self._lock     = threading.Lock()
        self.port      = CHAT_PORT
        self.running   = False

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
            name   = pkt.get("name", "?")[:32]
            pw     = pkt.get("password", "")
            status = pkt.get("status", "online")

            if self.room_type == "password":
                exp = hashlib.sha256((self.room_id + self.password).encode()).hexdigest()
                got = hashlib.sha256((self.room_id + pw).encode()).hexdigest()
                if exp != got:
                    conn.sendall(encode({"type": "error", "msg": "Wrong password"}))
                    conn.close(); return

            ghost = name == "__who__"
            with self._lock: self.clients[name] = {"sock": conn, "status": status}

            # send history + topic + user list
            for h in self.history[-200:]: conn.sendall(encode(h))
            if self.topic: conn.sendall(encode({"type": "topic", "topic": self.topic}))

            users_info = {n: {"host": n == self.tui.username,
                               "status": self.clients[n]["status"]}
                          for n in self.clients}
            conn.sendall(encode({
                "type": "joined", "host": self.tui.username,
                "users": users_info,
                "topic": self.topic,
            }))

            if not ghost:
                self._broadcast({"type": "user_join", "name": name,
                                  "host": self.tui.username, "status": status}, skip=name)
                self.tui.add_user(name, status=status)

            while self.running:
                p = decode_from(conn)
                if not p: break
                self._route(p, name)
        except: pass
        finally:
            if name:
                with self._lock: self.clients.pop(name, None)
                if name != "__who__":
                    self._broadcast({"type": "user_leave", "name": name})
                    self.tui.remove_user(name)
            try: conn.close()
            except: pass

    def _route(self, pkt, sender):
        t = pkt.get("type")
        if t == "chat":
            rec = {"type": "chat", "name": sender,
                   "text": pkt.get("text", "")[:MAX_MSG], "ts": pkt.get("ts", "")}
            self.history.append(rec)
            self._broadcast(rec)
            self.tui.msg(sender, rec["text"])
        elif t == "dm":
            target = pkt.get("target")
            with self._lock: info = self.clients.get(target)
            if info:
                try: info["sock"].sendall(encode({"type": "dm", "from": sender,
                                                   "text": pkt.get("text", "")}))
                except: pass
        elif t == "status":
            new_status = pkt.get("status", "online")
            with self._lock:
                if sender in self.clients: self.clients[sender]["status"] = new_status
            self._broadcast({"type": "status", "name": sender, "status": new_status})
            self.tui.set_user_status(sender, new_status)
        elif t == "topic" and sender == self.tui.username:
            self.topic = pkt.get("topic", "")
            self._broadcast({"type": "topic", "topic": self.topic})
            self.tui.set_topic(self.topic)
        elif t == "typing":
            self._broadcast({"type": "typing", "name": sender,
                              "typing": pkt.get("typing", False)}, skip=sender)

    def _broadcast(self, msg, skip=None):
        data = encode(msg)
        with self._lock:
            dead = []
            for n, info in self.clients.items():
                if n == skip: continue
                try: info["sock"].sendall(data)
                except: dead.append(n)
            for n in dead: del self.clients[n]

    def send_chat(self, text):
        rec = {"type": "chat", "name": self.tui.username,
               "text": text, "ts": datetime.now().strftime("%H:%M:%S")}
        self.history.append(rec)
        self._broadcast(rec)

    def send_dm(self, target, text):
        with self._lock: info = self.clients.get(target)
        if info:
            try:
                info["sock"].sendall(encode({"type": "dm", "from": self.tui.username, "text": text}))
                return True
            except: pass
        return False

    def set_topic(self, topic):
        self.topic = topic
        self._broadcast({"type": "topic", "topic": topic})
        self.tui.set_topic(topic)

# ── Client ────────────────────────────────────────────────────────────────────

class Client:
    def __init__(self, tui, password=""):
        self.tui = tui; self.password = password
        self._sock = None; self.running = False
        self._room_info = None   # saved for reconnect
        self._typing_timer = None

    def connect(self, addr, port):
        self._room_info = (addr, port)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0); s.connect((addr, port)); s.settimeout(None)
        self._sock = s
        s.sendall(encode({"type": "join", "name": self.tui.username,
                          "password": self.password, "status": self.tui.status}))
        resp = decode_from(s)
        if not resp: raise ConnectionError("No response")
        if resp.get("type") == "error": raise ConnectionError(resp.get("msg", "Refused"))
        if resp.get("type") != "joined": raise ConnectionError("Bad handshake")
        self.running = True

        users_info = resp.get("users", {})
        host_name  = resp.get("host", "")
        if isinstance(users_info, dict):
            for uname, uinfo in users_info.items():
                self.tui.add_user(uname,
                                   is_host=(uname == host_name),
                                   status=uinfo.get("status", "online"))
        else:
            for u in users_info:
                self.tui.add_user(u, is_host=(u == host_name))

        if resp.get("topic"):
            self.tui.topic = resp["topic"]

        threading.Thread(target=self._recv, daemon=True).start()

    def _recv(self):
        while self.running:
            try:
                p = decode_from(self._sock)
                if not p: break
                t = p.get("type")
                if   t == "chat":        self.tui.msg(p["name"], p["text"])
                elif t == "user_join":   self.tui.add_user(p["name"],
                                             is_host=(p["name"] == p.get("host")),
                                             status=p.get("status", "online"))
                elif t == "user_leave":  self.tui.remove_user(p["name"])
                elif t == "host_change": self.tui.set_host(p["name"])
                elif t == "dm":          self.tui.msg(p["from"], p["text"], "dm_in")
                elif t == "system":      self.tui.sys(p.get("msg", ""))
                elif t == "status":      self.tui.set_user_status(p["name"], p["status"])
                elif t == "topic":       self.tui.set_topic(p.get("topic", ""))
                elif t == "typing":      self.tui.set_typing(p["name"], p.get("typing", False))
            except: break
        self.running = False
        if self.tui.running:
            self.tui.sys("Lost connection — attempting reconnect...")
            self._reconnect()

    def _reconnect(self, attempts=5):
        for i in range(attempts):
            time.sleep(2)
            if not self.tui.running: return
            try:
                self.tui.sys(f"Reconnecting... ({i+1}/{attempts})")
                addr, port = self._room_info
                self._sock = None
                self.connect(addr, port)
                self.tui.sys("Reconnected!")
                return
            except: pass
        self.tui.sys("Could not reconnect. Host may be gone.")

    def send_chat(self, text):
        self._sock.sendall(encode({"type": "chat", "text": text,
                                   "ts": datetime.now().strftime("%H:%M:%S")}))

    def send_dm(self, target, text):
        self._sock.sendall(encode({"type": "dm", "target": target, "text": text}))

    def send_status(self, status):
        self._sock.sendall(encode({"type": "status", "status": status}))

    def send_typing(self, is_typing):
        try: self._sock.sendall(encode({"type": "typing", "typing": is_typing}))
        except: pass

    def disconnect(self):
        self.running = False
        try: self._sock.close()
        except: pass

# ── Background LAN room scanner ───────────────────────────────────────────────

class LanScanner:
    """Continuously scans LAN and updates tui.lan_rooms."""
    def __init__(self, tui):
        self.tui = tui
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self): self.running = False

    def _loop(self):
        d = Discovery(); d.start()
        while self.running:
            time.sleep(3)
            self.tui.update_lan_rooms(d.rooms)

# ── Input ─────────────────────────────────────────────────────────────────────

class Input:
    def __init__(self, tui, host, client):
        self.tui    = tui
        self.host   = host
        self.client = client
        self._last_typing_sent = False
        self._typing_clear_timer = None

    def run(self):
        self.tui.raw_mode()
        try:
            if WINDOWS: self._run_windows()
            else:       self._run_unix()
        finally:
            self.tui.restore()

    def _run_windows(self):
        while self.tui.running:
            if not msvcrt.kbhit():
                time.sleep(0.05); continue
            ch = msvcrt.getwch(); code = ord(ch)
            if code == 3:             self._quit(); break
            elif ch in ('\r', '\n'):  self._submit()
            elif code in (8, 127):
                self.tui.input_buf = self.tui.input_buf[:-1]
                self._on_type(); self.tui.render()
            elif code in (0, 224):
                ch2 = msvcrt.getwch()
                if ch2 == 'H':
                    self.tui.scroll = self.tui._clamp(self.tui.scroll - 1, -9999, 0)
                    self.tui.render()
                elif ch2 == 'P':
                    self.tui.scroll = self.tui._clamp(self.tui.scroll + 1, -9999, 0)
                    self.tui.render()
            elif 32 <= code < 127:
                if len(self.tui.input_buf) < MAX_MSG:
                    self.tui.input_buf += ch
                self._on_type(); self.tui.render()

    def _run_unix(self):
        while self.tui.running:
            rl, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not rl: continue
            try: ch = sys.stdin.read(1)
            except: continue
            if not ch: continue
            code = ord(ch)
            if code == 3:            self._quit(); break
            elif code == 13:         self._submit()
            elif code in (127, 8):
                self.tui.input_buf = self.tui.input_buf[:-1]
                self._on_type(); self.tui.render()
            elif code == 27:
                time.sleep(0.01); seq = ""
                try:
                    while True:
                        c2 = sys.stdin.read(1)
                        if not c2: break
                        seq += c2
                except: pass
                if seq == "[A":
                    self.tui.scroll = self.tui._clamp(self.tui.scroll - 1, -9999, 0)
                    self.tui.render()
                elif seq == "[B":
                    self.tui.scroll = self.tui._clamp(self.tui.scroll + 1, -9999, 0)
                    self.tui.render()
            elif 32 <= code < 127:
                if len(self.tui.input_buf) < MAX_MSG:
                    self.tui.input_buf += ch
                self._on_type(); self.tui.render()

    def _on_type(self):
        """Send typing indicator."""
        if self.client and not self._last_typing_sent:
            self.client.send_typing(True)
            self._last_typing_sent = True
        # Reset clear timer
        if self._typing_clear_timer: self._typing_clear_timer.cancel()
        self._typing_clear_timer = threading.Timer(2.0, self._stop_typing)
        self._typing_clear_timer.daemon = True
        self._typing_clear_timer.start()

    def _stop_typing(self):
        if self.client: self.client.send_typing(False)
        self._last_typing_sent = False

    def _quit(self):
        self.tui.running = False
        if self.client: self.client.disconnect()
        if self.host:   self.host.stop()

    def _submit(self):
        text = self.tui.input_buf.strip()
        self.tui.input_buf = ""
        self._stop_typing()
        if not text: self.tui.render(); return

        # Check if it's an in-room chat- command
        lower = text.lower()
        if lower.startswith("chat ") or lower == "chat":
            self.tui.pending_cmd = text  # e.g. "chat list"
            self._quit()
            return

        # Host commands
        if lower.startswith("/topic ") and self.tui.is_host:
            topic = text[7:].strip()
            if self.host: self.host.set_topic(topic)
            elif self.client: self.client._sock.sendall(encode({"type": "topic", "topic": topic}))
            self.tui.render(); return

        if lower.startswith("/status "):
            new_status = lower.split()[1] if len(lower.split()) > 1 else "online"
            if new_status not in STATUS_ICON: new_status = "online"
            self.tui.status = new_status
            cfg = load_config(); cfg["status"] = new_status; save_config(cfg)
            if self.client: self.client.send_status(new_status)
            with self.tui.lock:
                if self.tui.username in self.tui.users:
                    self.tui.users[self.tui.username]["status"] = new_status
            self.tui.sys(f"Status set to {new_status}")
            self.tui.render(); return

        # Send message
        if self.host:
            self.host.send_chat(text)
            self.tui.msg(self.tui.username, text)
        elif self.client:
            self.client.send_chat(text)
            self.tui.msg(self.tui.username, text)
        self.tui.render()

# ── Room entry ────────────────────────────────────────────────────────────────

def enter_room(room_id, room_type, password, username, status="online"):
    tui = TUI(username, room_id, room_type, status=status)
    disc = Discovery(); disc.start()
    tui.sys(f"Looking for {room_id} on LAN...")
    tui.render()
    found = disc.find(room_id)
    disc.stop()

    host = None; client = None

    if found:
        tui.sys(f"Connecting to {found['addr']}...")
        tui.render()
        client = Client(tui, password=password)
        try: client.connect(found["addr"], found["port"])
        except ConnectionError as e:
            tui.restore(); _clear()
            print(f"{C.BRED}Error: {e}{C.RST}"); sys.exit(1)
        tui.sys(f"Joined {room_id}")
    else:
        host = Host(room_id, room_type, password, tui)
        host.start()
        tui.is_host = True
        tui.add_user(username, is_host=True, status=status)
        tui.sys(f"Created {room_id} — you are host. Waiting for others...")
        tui.sys(f"Tip: /topic <text> to set a room topic")

    # Background LAN scanner for sidebar
    scanner = LanScanner(tui); scanner.start()

    if not WINDOWS:
        signal.signal(signal.SIGWINCH, lambda s, f: tui.render())

    _clear(); tui.render()
    Input(tui, host, client).run()
    scanner.stop()
    tui.restore(); _clear()
    print(f"{C.DIM}Left {room_id}.{C.RST}")

    # Run pending command if user typed one inside the room
    return tui.pending_cmd

# ── Non-TUI commands ──────────────────────────────────────────────────────────

def cmd_list():
    print(f"{C.DIM}Scanning LAN...{C.RST}", flush=True)
    d = Discovery(); d.start()
    rooms = d.scan(3.0); d.stop()
    if not rooms: print(f"{C.DIM}No rooms found.{C.RST}"); return
    kinds = {"pub": "public", "private": "private", "password": "password", "dm": "dm"}
    print(f"{C.BOLD}Rooms on LAN:{C.RST}")
    for rid, info in rooms.items():
        print(f"  {C.BCYN}{rid}{C.RST}  {C.DIM}{kinds.get(info['type'], info['type'])}  {info['addr']}{C.RST}")

def cmd_who(room_id="pub"):
    print(f"{C.DIM}Looking for {room_id}...{C.RST}", flush=True)
    d = Discovery(); d.start()
    found = d.find(room_id, 3.0); d.stop()
    if not found: print(f"{C.DIM}{room_id} not found.{C.RST}"); return
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0); s.connect((found["addr"], found["port"]))
        s.sendall(encode({"type": "join", "name": "__who__", "password": ""}))
        resp = decode_from(s); s.close()
        if resp and resp.get("type") == "joined":
            h     = resp.get("host", "")
            users = resp.get("users", {})
            print(f"{C.BOLD}Users in {room_id}:{C.RST}")
            if isinstance(users, dict):
                for u, info in users.items():
                    star = f" {C.BYEL}[host]{C.RST}" if u == h else ""
                    st   = info.get("status", "online")
                    sc   = STATUS_COL.get(st, C.BGRN)
                    si   = STATUS_ICON.get(st, "●")
                    print(f"  {sc}{si}{C.RST} {name_color(u)}{u}{C.RST}{star}")
            else:
                for u in users:
                    star = f" {C.BYEL}[host]{C.RST}" if u == h else ""
                    print(f"  {name_color(u)}{u}{C.RST}{star}")
        else: print(f"{C.DIM}Could not fetch users.{C.RST}")
    except Exception as e: print(f"{C.DIM}Error: {e}{C.RST}")

def cmd_help():
    print(f"""
  {C.BOLD}{C.BCYN}termchat{C.RST} {C.DIM}v{VERSION}{C.RST}

  {C.BOLD}Terminal commands:{C.RST}
    {C.BCYN}chat pub{C.RST}              join the public room
    {C.BCYN}chat <id>{C.RST}             join or create a private room
    {C.BCYN}chat <id> <pw>{C.RST}        join a password-protected room
    {C.BCYN}chat dm <id>{C.RST}          open a DM with someone
    {C.BCYN}chat list{C.RST}             scan LAN for open rooms
    {C.BCYN}chat who{C.RST}              see who is in a room
    {C.BCYN}chat status <s>{C.RST}       set your status (online/away/busy)
    {C.BCYN}chat update{C.RST}           update to latest version
    {C.BCYN}chat uninstall{C.RST}        remove termchat
    {C.BCYN}chat help{C.RST}             show this help

  {C.BOLD}Inside a room:{C.RST}
    {C.DIM}@name{C.RST}                 mention someone (highlighted)
    {C.DIM}/topic <text>{C.RST}         set room topic (host only)
    {C.DIM}/status <s>{C.RST}           change your status (online/away/busy)
    {C.DIM}up/down arrows{C.RST}        scroll message history
    {C.DIM}chat <cmd>{C.RST}            leave room and run that command
    {C.DIM}Ctrl-C{C.RST}               quit

  {C.BOLD}Statuses:{C.RST}  {C.BGRN}● online{C.RST}   {C.BYEL}○ away{C.RST}   {C.BRED}◆ busy{C.RST}
""")

def cmd_status(status):
    if status not in STATUS_ICON:
        print(f"{C.BRED}Unknown status. Use: online, away, busy{C.RST}"); return
    cfg = load_config(); cfg["status"] = status; save_config(cfg)
    print(f"{STATUS_COL[status]}{STATUS_ICON[status]} Status set to {status}{C.RST}")

def _find_self():
    script = os.path.abspath(__file__)
    return script, os.path.dirname(script)

def cmd_update():
    import urllib.request
    script, _ = _find_self()
    print(f"{C.DIM}Checking for update...{C.RST}", flush=True)
    try:
        with urllib.request.urlopen(f"{REPO}/termchat.py", timeout=8) as r:
            new_src = r.read()
        new_ver = VERSION
        for line in new_src.decode().splitlines():
            if line.strip().startswith("VERSION"):
                try: new_ver = line.split('"')[1]
                except: pass
                break
        if new_ver == VERSION:
            print(f"{C.BGRN}Already up to date{C.RST} (v{VERSION})"); return
        with open(script, "wb") as f: f.write(new_src)
        print(f"{C.BGRN}Updated{C.RST} v{VERSION} -> v{new_ver}")
    except Exception as e:
        print(f"{C.BRED}Update failed:{C.RST} {e}")

def cmd_uninstall():
    script, folder = _find_self()
    print(f"{C.BYEL}This will remove termchat from your machine.{C.RST}")
    ans = input("  Are you sure? [y/N] ").strip().lower()
    if ans != "y": print(f"{C.DIM}Cancelled.{C.RST}"); return
    removed = []
    for f in [script,
              os.path.join(folder, "chat"),
              os.path.join(folder, "chat.cmd")]:
        if os.path.exists(f):
            try: os.remove(f); removed.append(f)
            except Exception as e: print(f"{C.DIM}Could not remove {f}: {e}{C.RST}")
    for f in removed: print(f"  {C.DIM}Removed {f}{C.RST}")
    print(f"{C.DIM}termchat uninstalled. Goodbye.{C.RST}")

# ── Main ──────────────────────────────────────────────────────────────────────

def _clear(): sys.stdout.write("\033[2J\033[H"); sys.stdout.flush()

def dispatch(raw_args):
    """Parse and run a command from sys.argv style args."""
    if not raw_args: cmd_help(); return

    # Join args and split on dash for compound commands like chat-myroom-mypass
    # argv[0] is the command string e.g. "chat-pub" or "chat-myroom"
    cmd_str = raw_args[0].lower()
    # strip leading "chat-" prefix if present (when called as `chat pub` style too)
    if cmd_str == "chat":
        # space-separated: "chat pub", "chat myroom mypass"
        parts = [p for p in raw_args[1:]]
        sub   = parts[0].lower() if parts else "help"
        rest  = parts[1:]
    else:
        sub  = cmd_str
        rest = raw_args[1:]

    username = get_username()
    status   = get_status()

    if sub == "help":       cmd_help()
    elif sub == "list":     cmd_list()
    elif sub == "update":   cmd_update()
    elif sub == "uninstall":cmd_uninstall()
    elif sub == "who":
        room = rest[0] if rest else "pub"
        cmd_who(room)
    elif sub == "status":
        s = rest[0] if rest else "online"
        cmd_status(s)
    elif sub == "pub":
        pending = enter_room("pub", "pub", "", username, status)
        if pending: dispatch(pending.split())
    elif sub == "dm":
        target = rest[0] if rest else ""
        if not target: print(f"{C.BRED}Usage: chat-dm-<username>{C.RST}"); return
        dm_id = "dm-" + "-".join(sorted([username, target]))
        pending = enter_room(dm_id, "dm", "", username, status)
        if pending: dispatch(pending.split())
    elif sub:
        room_id  = sub
        password = rest[0] if rest else ""
        pending = enter_room(room_id, "password" if password else "private",
                             password, username, status)
        if pending: dispatch(pending.split())
    else:
        cmd_help()

def main():
    dispatch(sys.argv[1:])

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print(f"\n{C.DIM}Bye.{C.RST}")
