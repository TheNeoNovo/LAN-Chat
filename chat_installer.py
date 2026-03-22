#!/usr/bin/env python3
import os, sys, socket, threading, time
import platform

# Determine chat folder
if platform.system()=="Windows":
    CHAT_DIR = os.path.join(os.environ["USERPROFILE"], "ChatApp")
else:
    CHAT_DIR = os.path.join(os.path.expanduser("~"), "ChatApp")
if not os.path.exists(CHAT_DIR):
    os.makedirs(CHAT_DIR)

CLIENT_FILE = os.path.join(CHAT_DIR,"chat_client.py")
WRAPPER_FILE = os.path.join(CHAT_DIR,"Chat.py")

# Main chat client code
CLIENT_CODE = '''import socket, threading, sys, os, time
import platform

PORT = 5000
HOST = None
NAME = ""
ROOM = ""
ONLINE = []

def broadcast(msg, clients_list, exclude=None):
    for c,_ in clients_list:
        if c!=exclude:
            try: c.send(msg.encode())
            except: pass

def server_loop(port):
    clients = []
    rooms = {"public":[]}
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s.bind(("0.0.0.0",port))
    s.listen()
    print("🌐 Server started on port {}".format(port))
    def handle_client(conn,addr):
        name = conn.recv(1024).decode()
        rooms["public"].append((conn,name))
        broadcast("{} joined the chat.".format(name),rooms["public"],conn)
        while True:
            try:
                msg = conn.recv(1024)
                if not msg: break
                text = msg.decode()
                if text=="/end": break
                broadcast("{} - {}".format(name,text),rooms["public"],conn)
            except: break
        rooms["public"].remove((conn,name))
        conn.close()
        broadcast("{} left the chat.".format(name),rooms["public"])
    while True:
        conn,addr = s.accept()
        threading.Thread(target=handle_client,args=(conn,addr),daemon=True).start()

def client_loop(host,port):
    sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.connect((host,port))
    global NAME
    NAME = input("Enter your name: ")
    sock.send(NAME.encode())
    def recv_thread():
        while True:
            try:
                msg = sock.recv(1024).decode()
                if msg: print(msg)
            except: break
    threading.Thread(target=recv_thread,daemon=True).start()
    print("Connected! Type messages, /end to quit.")
    while True:
        msg = input()
        if msg=="/end": break
        sock.send(msg.encode())
    sock.close()

def start_chat(cmd,args):
    if cmd=="help":
        print("Available commands:")
        print(" Chat/pub              Join public chat")
        print(" Chat/join/<id>[/pw]  Join private chat with optional password")
        print(" Chat/end              Leave chat")
        print(" Chat/id               Show session ID")
        print(" Chat/list             List active rooms (LAN)")
        print(" Chat/online           Show users in current room")
        print(" Chat/uninstall        Remove chat system")
        return
    if cmd=="pub":
        host_ip = input("Enter host IP (empty to start as host): ").strip()
        if host_ip=="": server_loop(PORT)
        else: client_loop(host_ip,PORT)
    elif cmd=="join":
        host_ip = input("Enter host IP: ").strip()
        client_loop(host_ip,PORT)
    elif cmd=="end":
        print("Use /end inside chat to leave.")
    elif cmd=="id":
        print("Session ID:", os.getpid())
    elif cmd=="list":
        print("LAN room listing not implemented yet.")
    elif cmd=="online":
        print("Users in room not implemented yet.")
    elif cmd=="uninstall":
        chat_dir = os.path.dirname(os.path.abspath(__file__))
        confirm = input("Are you sure? (Y/n) ").lower()
        if confirm=="y":
            import shutil
            shutil.rmtree(chat_dir)
            print("Chat uninstalled.")
    else:
        print("Unknown command. Use Chat/help.")

if __name__=="__main__":
    args = sys.argv[1:]
    if args:
        start_chat(args[0].lower(),args[1:])
    else:
        start_chat("help",[])
'''

# Write client code
with open(CLIENT_FILE,"w") as f:
    f.write(CLIENT_CODE)

# Create wrapper
WRAPPER_CODE = f'''#!/usr/bin/env python3
import sys, os
sys.path.insert(0,r"{CHAT_DIR}")
from chat_client import start_chat
args = sys.argv[1:]
if args: start_chat(args[0].lower(),args[1:])
else: start_chat("help",[])
'''
with open(WRAPPER_FILE,"w") as f:
    f.write(WRAPPER_CODE)

# Make wrapper executable on Linux
if platform.system()!="Windows":
    os.chmod(WRAPPER_FILE,0o755)
    bash_path = "/usr/local/bin/Chat"
    with open(bash_path,"w") as f:
        f.write(f'#!/bin/bash\npython3 "{WRAPPER_FILE}" "$@"')
    os.chmod(bash_path,0o755)

print("✅ Chat installed successfully!")
print("Run 'Chat/help' to see available commands.")
'''
