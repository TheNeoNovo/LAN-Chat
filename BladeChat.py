#!/usr/bin/env python3
"""
BladeChat — LAN terminal chat. No internet. No accounts. Just chat.

  chat pub              join public room
  chat <id>             join/create private room
  chat <id> <pw>        join password-protected room
  chat dm <id>          open DM with someone
  chat list             scan LAN for open rooms
  chat who              see who is in a room
  chat help             show help
"""

import sys, os, socket, threading, time, json, hashlib, struct, signal, re
from datetime import datetime

WINDOWS = sys.platform == "win32"

if WINDOWS:
    import msvcrt
else:
    import select, termios, tty, fcntl

VERSION     = "1.0.3"
MCAST_GROUP = "224.0.0.251"
MCAST_PORT  = 5353
CHAT_PORT   = 47331

# ── Colors ────────────────────────────────────────────────────────────────────

class C:
    RST  = "\033[0m";  BOLD = "\033[1m";  DIM  = "\033[2m";  REV  = "\033[7m"
    YEL  = "\033[33m"
    BRED = "\033[91m"; BGRN = "\033[92m"; BYEL = "\033[93m"
    BBLU = "\033[94m"; BMAG = "\033[95m"; BCYN = "\033[96m"; BWHT = "\033[97m"
    BG   = "\033[40m"

PALETTE = [C.BCYN, C.BGRN, C.BYEL, C.BMAG, C.BBLU, C.BRED, C.BWHT]

def name_color(n): return PALETTE[sum(ord(c) for c in n) % len(PALETTE)]
def strip_ansi(s): return re.sub(r'\033\[[0-9;]*m', '', s)
def term_size():
    try:
        import shutil; s = shutil.get_terminal_size(); return s.columns, s.lines
    except: return 80, 24

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
    def __init__(self, username, room_id, room_type):
        self.username  = username
        self.room_id   = room_id
        self.room_type = room_type
        self.messages  = []
        self.users     = {}
        self.input_buf = ""
        self.scroll    = 0
        self.lock      = threading.Lock()
        self.running   = True
        self.is_host   = False
        self._old_term = None
        self._orig_fl  = None

    def raw_mode(self):
        if WINDOWS:
            pass  # Windows reads char-by-char via msvcrt, no setup needed
        else:
            self._old_term = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin.fileno())
            fl = fcntl.fcntl(sys.stdin.fileno(), fcntl.F_GETFL)
            fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, fl | os.O_NONBLOCK)
            self._orig_fl = fl

    def restore(self):
        if WINDOWS:
            pass
        else:
            try:
                if self._old_term: termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_term)
                if self._orig_fl is not None: fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, self._orig_fl)
            except: pass

    def _w(self, s): sys.stdout.write(s)
    def _mv(self, r, c=0): self._w(f"\033[{r};{c}H")
    def _cl(self): self._w("\033[2K")
    def _clamp(self, n, lo, hi): return max(lo, min(hi, n))

    def render(self):
        with self.lock: self._render()

    def _render(self):
        cols, rows = term_size()
        SIDE = 18
        CW   = cols - SIDE - 1
        CH   = rows - 2
        MTOP = 2

        self._w("\033[?25l")

        # top bar
        self._mv(1); self._cl()
        host_tag = f" {C.BYEL}*host*{C.RST}{C.BG}" if self.is_host else ""
        room_label = {
            "pub":      f"{C.BGRN}pub{C.RST}{C.BG}",
            "private":  f"{C.BCYN}{self.room_id}{C.RST}{C.BG}",
            "password": f"{C.BMAG}{self.room_id}{C.RST}{C.BG}",
            "dm":       f"{C.BYEL}DM:{self.room_id}{C.RST}{C.BG}",
        }.get(self.room_type, self.room_id)
        nc  = name_color(self.username)
        bar = (f"{C.BG}{C.BOLD}{C.BWHT} BladeChat {C.RST}{C.BG}"
               f"  {room_label}  "
               f"{C.DIM}{nc}{self.username}{C.RST}{C.BG}{host_tag}"
               f"{C.DIM}  chat help{C.RST}")
        pad = cols - len(strip_ansi(bar)) - 1
        self._w(bar + " " * max(0, pad))

        # divider
        for r in range(MTOP, rows):
            self._mv(r, CW + 1); self._w(f"{C.DIM}|{C.RST}")

        # sidebar
        self._mv(MTOP, CW + 2)
        self._w(f"{C.BOLD}{C.DIM} {len(self.users)} online{C.RST}")
        ur = MTOP + 1
        for name, info in list(self.users.items())[:CH - 2]:
            self._mv(ur, CW + 2); self._cl()
            star = f"{C.BYEL}*{C.RST} " if info.get("host") else "  "
            self._w(f" {star}{name_color(name)}{name[:SIDE-4]}{C.RST}")
            ur += 1
        while ur < rows:
            self._mv(ur, CW + 2); self._cl(); ur += 1

        # messages
        lines  = self._render_lines()
        vstart = max(0, len(lines) - CH + self.scroll)
        vis    = lines[vstart:vstart + CH]
        for i, line in enumerate(vis):
            self._mv(MTOP + i, 1); self._cl()
            pad = CW - len(strip_ansi(line)) - 1
            self._w(" " + line + " " * max(0, pad))
        for i in range(len(vis), CH):
            self._mv(MTOP + i, 1); self._cl()

        # input bar
        self._mv(rows); self._cl()
        prompt = f"{name_color(self.username)}{C.BOLD}{self.username}{C.RST} "
        max_w  = cols - len(strip_ansi(prompt)) - 3
        shown  = self.input_buf[-max_w:] if len(self.input_buf) > max_w else self.input_buf
        self._w(f"{prompt}{C.BWHT}{shown}{C.RST}> \033[?25l")
        sys.stdout.flush()

    def _render_lines(self):
        lines = []
        for ts, sender, text, kind in self.messages:
            if kind == "system":
                lines.append(f"  {C.DIM}{C.YEL}* {text}{C.RST}")
            elif kind == "dm_in":
                lines.append(f"  {C.BMAG}<- {sender}{C.RST}  {text}")
            elif kind == "dm_out":
                lines.append(f"  {C.BMAG}-> {sender}{C.RST}  {text}")
            else:
                hi  = re.sub(r'@(\w+)',
                              lambda m: f"{C.REV}{C.BYEL}@{m.group(1)}{C.RST}"
                              if m.group(1) in self.users or m.group(1) == self.username
                              else m.group(0), text)
                col = name_color(sender)
                lines.append(f"  {C.DIM}{ts}{C.RST} {col}{C.BOLD}{sender}{C.RST} - {hi}")
        return lines

    def msg(self, sender, text, kind="chat"):
        ts = datetime.now().strftime("%H:%M")
        with self.lock: self.messages.append((ts, sender, text, kind))
        self._render()

    def sys(self, text): self.msg("", text, "system")

    def add_user(self, name, is_host=False):
        with self.lock:
            new = name not in self.users
            self.users[name] = {"host": is_host}
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
        # Send multicast on the real LAN interface, not a virtual adapter
        lan_ip = get_lan_ip()
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                              socket.inet_aton(lan_ip))
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

def get_lan_ip():
    """Find the real LAN IP by connecting a UDP socket — picks the right interface."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "0.0.0.0"

class Discovery:
    def __init__(self):
        self.rooms = {}

    def start(self):
        lan_ip = get_lan_ip()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError: pass
        s.bind(("", MCAST_PORT))
        # Bind multicast to the real LAN interface, not a virtual adapter
        mreq = struct.pack("4s4s", socket.inet_aton(MCAST_GROUP), socket.inet_aton(lan_ip))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        s.settimeout(0.5)
        self._sock = s
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        try: self._sock.close()
        except: pass

    def _loop(self):
        while True:
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
        self.clients   = {}
        self.history   = []
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
            name = pkt.get("name", "?")[:32]
            pw   = pkt.get("password", "")

            if self.room_type == "password":
                exp = hashlib.sha256((self.room_id + self.password).encode()).hexdigest()
                got = hashlib.sha256((self.room_id + pw).encode()).hexdigest()
                if exp != got:
                    conn.sendall(encode({"type": "error", "msg": "Wrong password"}))
                    conn.close(); return

            with self._lock: self.clients[name] = conn
            for h in self.history[-200:]: conn.sendall(encode(h))
            conn.sendall(encode({
                "type": "joined", "host": self.tui.username,
                "users": list(self.clients.keys()) + [self.tui.username],
            }))
            self._broadcast({"type": "user_join", "name": name,
                              "host": self.tui.username}, skip=name)

            if name != "__who__":
                self.tui.add_user(name)

            while self.running:
                p = decode_from(conn)
                if not p: break
                self._route(p, name)
        except: pass
        finally:
            if name and name != "__who__":
                with self._lock: self.clients.pop(name, None)
                self._broadcast({"type": "user_leave", "name": name})
                self.tui.remove_user(name)
            elif name:
                with self._lock: self.clients.pop(name, None)
            try: conn.close()
            except: pass

    def _route(self, pkt, sender):
        t = pkt.get("type")
        if t == "chat":
            rec = {"type": "chat", "name": sender,
                   "text": pkt.get("text", "")[:2000], "ts": pkt.get("ts", "")}
            self.history.append(rec)
            self._broadcast(rec)
            self.tui.msg(sender, rec["text"])
        elif t == "dm":
            target = pkt.get("target")
            with self._lock: tsock = self.clients.get(target)
            if tsock:
                try: tsock.sendall(encode({"type": "dm", "from": sender,
                                           "text": pkt.get("text", "")}))
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

    def send_chat(self, text):
        rec = {"type": "chat", "name": self.tui.username,
               "text": text, "ts": datetime.now().strftime("%H:%M")}
        self.history.append(rec)
        self._broadcast(rec)

    def send_dm(self, target, text):
        with self._lock: tsock = self.clients.get(target)
        if tsock:
            try:
                tsock.sendall(encode({"type": "dm", "from": self.tui.username, "text": text}))
                return True
            except: pass
        return False

# ── Client ────────────────────────────────────────────────────────────────────

class Client:
    def __init__(self, tui, password=""):
        self.tui = tui; self.password = password
        self._sock = None; self.running = False

    def connect(self, addr, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0); s.connect((addr, port)); s.settimeout(None)
        self._sock = s
        s.sendall(encode({"type": "join", "name": self.tui.username,
                          "password": self.password}))
        resp = decode_from(s)
        if not resp: raise ConnectionError("No response")
        if resp.get("type") == "error": raise ConnectionError(resp.get("msg", "Refused"))
        if resp.get("type") != "joined": raise ConnectionError("Bad handshake")
        self.running = True
        for u in resp.get("users", []):
            self.tui.add_user(u, is_host=(u == resp.get("host")))
        threading.Thread(target=self._recv, daemon=True).start()

    def _recv(self):
        while self.running:
            try:
                p = decode_from(self._sock)
                if not p: break
                t = p.get("type")
                if   t == "chat":        self.tui.msg(p["name"], p["text"])
                elif t == "user_join":   self.tui.add_user(p["name"],
                                             is_host=(p["name"] == p.get("host")))
                elif t == "user_leave":  self.tui.remove_user(p["name"])
                elif t == "host_change": self.tui.set_host(p["name"])
                elif t == "dm":          self.tui.msg(p["from"], p["text"], "dm_in")
                elif t == "system":      self.tui.sys(p.get("msg", ""))
            except: break
        self.running = False
        self.tui.sys("Disconnected from host")

    def send_chat(self, text):
        self._sock.sendall(encode({"type": "chat", "text": text,
                                   "ts": datetime.now().strftime("%H:%M")}))

    def send_dm(self, target, text):
        self._sock.sendall(encode({"type": "dm", "target": target, "text": text}))

    def disconnect(self):
        self.running = False
        try: self._sock.close()
        except: pass

# ── Input ─────────────────────────────────────────────────────────────────────

class Input:
    def __init__(self, tui, host, client):
        self.tui = tui; self.host = host; self.client = client

    def run(self):
        self.tui.raw_mode()
        try:
            if WINDOWS:
                self._run_windows()
            else:
                self._run_unix()
        finally:
            self.tui.restore()

    def _run_windows(self):
        while self.tui.running:
            if not msvcrt.kbhit():
                time.sleep(0.05); continue
            ch = msvcrt.getwch()
            code = ord(ch)

            if code == 3 or ch == '\x03':       # Ctrl-C
                self._quit(); break
            elif ch in ('\r', '\n'):             # Enter
                self._submit()
            elif code in (8, 127):              # Backspace
                self.tui.input_buf = self.tui.input_buf[:-1]
                self.tui.render()
            elif code == 0 or code == 224:      # Special key prefix (arrows)
                ch2 = msvcrt.getwch()
                if ch2 == 'H':                  # Up arrow
                    self.tui.scroll = self.tui._clamp(self.tui.scroll - 1, -9999, 0)
                    self.tui.render()
                elif ch2 == 'P':                # Down arrow
                    self.tui.scroll = self.tui._clamp(self.tui.scroll + 1, -9999, 0)
                    self.tui.render()
            elif 32 <= code < 127:
                self.tui.input_buf += ch
                self.tui.render()

    def _run_unix(self):
        while self.tui.running:
            rl, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not rl: continue
            try: ch = sys.stdin.read(1)
            except: continue
            if not ch: continue
            code = ord(ch)

            if code == 3:
                self._quit(); break
            elif code == 13:
                self._submit()
            elif code in (127, 8):
                self.tui.input_buf = self.tui.input_buf[:-1]
                self.tui.render()
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
                self.tui.input_buf += ch
                self.tui.render()

    def _quit(self):
        self.tui.running = False
        if self.client: self.client.disconnect()
        if self.host:   self.host.stop()

    def _submit(self):
        text = self.tui.input_buf.strip()
        self.tui.input_buf = ""
        if not text: self.tui.render(); return
        if self.host:
            self.host.send_chat(text)
            self.tui.msg(self.tui.username, text)  # host echoes locally (not in route)
        elif self.client:
            self.client.send_chat(text)
            # no local echo — server broadcasts back and _recv displays it
        self.tui.render()

# ── Room entry ────────────────────────────────────────────────────────────────

def enter_room(room_id, room_type, password, username):
    tui = TUI(username, room_id, room_type)
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
        tui.add_user(username, is_host=True)
        tui.sys(f"Created {room_id} — you are host. Waiting for others...")

    if not WINDOWS:
        signal.signal(signal.SIGWINCH, lambda s, f: tui.render())
    _clear(); tui.render()
    Input(tui, host, client).run()
    tui.restore(); _clear()
    print(f"{C.DIM}Left {room_id}.{C.RST}")

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

def cmd_who(room_id):
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
            h = resp.get("host", "")
            print(f"{C.BOLD}Users in {room_id}:{C.RST}")
            for u in resp.get("users", []):
                star = f" {C.BYEL}*{C.RST}" if u == h else ""
                print(f"  {name_color(u)}{u}{C.RST}{star}")
        else: print(f"{C.DIM}Could not fetch users.{C.RST}")
    except Exception as e: print(f"{C.DIM}Error: {e}{C.RST}")

def cmd_help():
    print(f"""
  {C.BOLD}{C.BCYN}BladeChat{C.RST} {C.DIM}v{VERSION}{C.RST}

  {C.BOLD}Commands:{C.RST}
    {C.BCYN}chat pub{C.RST}              join the public room
    {C.BCYN}chat <id>{C.RST}             join or create a private room
    {C.BCYN}chat <id> <pw>{C.RST}        join a password-protected room
    {C.BCYN}chat dm <id>{C.RST}          open a DM with someone
    {C.BCYN}chat list{C.RST}             scan LAN for open rooms
    {C.BCYN}chat who{C.RST}              see who is in a room
    {C.BCYN}chat update{C.RST}           update to the latest version
    {C.BCYN}chat uninstall{C.RST}        remove BladeChat from this machine
    {C.BCYN}chat help{C.RST}             show this help

  {C.BOLD}Inside a room:{C.RST}
    {C.DIM}@name{C.RST}                 mention someone
    {C.DIM}up/down arrows{C.RST}        scroll history
    {C.DIM}Ctrl-C{C.RST}               quit / leave
    {C.DIM}run a new chat command{C.RST} to switch rooms
""")

def _find_self():
    """Return the path to this script and its parent directory."""
    script = os.path.abspath(__file__)
    folder = os.path.dirname(script)
    return script, folder

def cmd_update():
    import urllib.request
    RAW = "https://raw.githubusercontent.com/FadingBlade/BladeChat/main/BladeChat.py"
    script, _ = _find_self()
    print(f"{C.DIM}Checking for update...{C.RST}", flush=True)
    try:
        with urllib.request.urlopen(RAW, timeout=8) as r:
            new_src = r.read()
        # Extract version from downloaded source
        new_ver = VERSION
        for line in new_src.decode().splitlines():
            if line.strip().startswith("VERSION"):
                new_ver = line.split('"')[1] if '"' in line else VERSION
                break
        if new_ver == VERSION:
            print(f"{C.BGRN}Already up to date{C.RST} (v{VERSION})")
            return
        with open(script, "wb") as f:
            f.write(new_src)
        print(f"{C.BGRN}Updated{C.RST} v{VERSION} -> v{new_ver}")
    except Exception as e:
        print(f"{C.BRED}Update failed:{C.RST} {e}")

def cmd_uninstall():
    script, folder = _find_self()
    print(f"{C.BYEL}This will remove BladeChat from your machine.{C.RST}")
    ans = input("  Are you sure? [y/N] ").strip().lower()
    if ans != "y":
        print(f"{C.DIM}Cancelled.{C.RST}"); return

    removed = []
    # Remove BladeChat.py
    try: os.remove(script); removed.append(script)
    except Exception as e: print(f"{C.DIM}Could not remove {script}: {e}{C.RST}")

    # Remove chat / chat.cmd wrapper
    for wrapper in [os.path.join(folder, "chat"), os.path.join(folder, "chat.cmd")]:
        if os.path.exists(wrapper):
            try: os.remove(wrapper); removed.append(wrapper)
            except Exception as e: print(f"{C.DIM}Could not remove {wrapper}: {e}{C.RST}")

    if removed:
        print(f"{C.BGRN}Removed:{C.RST}")
        for f in removed: print(f"  {C.DIM}{f}{C.RST}")
    print(f"{C.DIM}BladeChat uninstalled. Goodbye.{C.RST}")

# ── Main ──────────────────────────────────────────────────────────────────────

def _clear(): sys.stdout.write("\033[2J\033[H"); sys.stdout.flush()

def get_username():
    return (os.environ.get("USER") or os.environ.get("USERNAME") or
            os.environ.get("LOGNAME") or "user")[:32]

def main():
    args = sys.argv[1:]
    if not args: cmd_help(); return

    cmd = args[0].lower()

    if cmd == "help":                    cmd_help()
    elif cmd == "update":                cmd_update()
    elif cmd == "uninstall":             cmd_uninstall()
    elif cmd == "list":                  cmd_list()
    elif cmd == "who":                   cmd_who(args[1] if len(args) > 1 else "pub")
    elif cmd == "pub":                   enter_room("pub", "pub", "", get_username())
    elif cmd == "dm":
        target = args[1] if len(args) > 1 else ""
        if not target: print(f"{C.BRED}Usage: chat dm <username>{C.RST}"); return
        username = get_username()
        dm_id = "dm-" + "-".join(sorted([username, target]))
        enter_room(dm_id, "dm", "", username)
    elif cmd:
        room_id  = cmd
        password = args[1] if len(args) > 1 else ""
        enter_room(room_id, "password" if password else "private", password, get_username())
    else:
        cmd_help()

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print(f"\n{C.DIM}Bye.{C.RST}")
