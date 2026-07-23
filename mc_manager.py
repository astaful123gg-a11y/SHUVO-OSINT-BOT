import threading
import subprocess
import time
import json
import random
import os
import sys

MC_USERS_FILE = "mc_users.json"
MC_BOT_DEFAULT_PASSWORD = "ShuvoBot@2024"

_instances: dict = {}
_lock = threading.Lock()

# Path to the mc_bot.js script
_BOT_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mc_node", "mc_bot.js")
_NODE_BINARY = "node"


def ping_server(ip: str, port: int = 25565) -> dict:
    try:
        from mcstatus import JavaServer
        srv = JavaServer(ip, int(port), timeout=6)
        s = srv.status()
        return {
            "online": True,
            "players": s.players.online,
            "max_players": s.players.max,
            "description": str(s.description)[:100].strip(),
            "latency": round(s.latency, 1),
            "version": s.version.name,
        }
    except Exception as e:
        return {"online": False, "error": str(e)[:120]}


def load_mc_users() -> list:
    try:
        path = os.path.join(os.path.dirname(__file__), MC_USERS_FILE)
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("usernames", [])
    except Exception:
        return []


def random_username() -> str:
    users = load_mc_users()
    if users:
        return random.choice(users)
    return f"SHUVO_{random.randint(1000, 9999)}"


class BotInstance:
    def __init__(self, chat_id: str, ip: str, port: int, username: str, password: str):
        self.chat_id = str(chat_id)
        self.ip = ip
        self.port = int(port)
        self.username = username
        self.password = password
        self.running = False
        self.status = "⛔ Stopped"
        self._proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self):
        self._stop_event.clear()
        self.running = True
        self.status = "🔄 Connecting..."
        self._spawn()

    def stop(self):
        self.running = False
        self._stop_event.set()
        self._send_cmd("stop")
        time.sleep(0.5)
        self._kill_proc()
        self.status = "⛔ Stopped"

    def rejoin(self):
        self._send_cmd("rejoin")
        self.status = "🔄 Rejoining..."

    def _send_cmd(self, cmd: str):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write(cmd + "\n")
                self._proc.stdin.flush()
            except Exception:
                pass

    def _kill_proc(self):
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

    def _spawn(self):
        self._kill_proc()
        script = _BOT_SCRIPT
        cmd = [
            _NODE_BINARY, script,
            self.ip, str(self.port),
            self.username, self.password,
        ]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=os.path.dirname(__file__),
            )
        except Exception as e:
            self.status = f"❌ Failed to start: {str(e)[:80]}"
            self.running = False
            return

        self._reader_thread = threading.Thread(
            target=self._read_output, daemon=True,
            name=f"mc-reader-{self.chat_id}"
        )
        self._reader_thread.start()

        # Watchdog: restart if process dies and we're still running
        watcher = threading.Thread(
            target=self._watchdog, daemon=True,
            name=f"mc-watch-{self.chat_id}"
        )
        watcher.start()

    def _read_output(self):
        proc = self._proc
        if not proc:
            return
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("STATUS:"):
                    raw = line[7:]
                    if raw == "online":
                        self.status = f"🟢 Online — {self.username}"
                    elif raw == "connecting":
                        self.status = "🔄 Connecting..."
                    elif raw == "disconnected":
                        self.status = "❌ Disconnected"
                    elif raw == "rejoining":
                        self.status = "🔄 Rejoining..."
                    elif raw == "stopping":
                        self.status = "⛔ Stopping..."
                    elif raw == "logged_in":
                        self.status = f"🟢 Online + Logged in — {self.username}"
                    elif raw.startswith("error:"):
                        self.status = f"❌ {raw[6:80]}"
                    elif raw.startswith("kicked:"):
                        self.status = f"⚠️ Kicked: {raw[7:60]}"
        except Exception:
            pass

    def _watchdog(self):
        while self.running and not self._stop_event.is_set():
            self._stop_event.wait(10)
            if self._stop_event.is_set():
                break
            proc = self._proc
            if proc and proc.poll() is not None and self.running:
                self.status = "⏳ Reconnecting in 15s..."
                self._stop_event.wait(15)
                if self.running and not self._stop_event.is_set():
                    self.username = random_username()
                    self.status = "🔄 Reconnecting..."
                    self._spawn()
                    return


def start_bot(chat_id, ip: str, port: int, username: str,
              password: str = MC_BOT_DEFAULT_PASSWORD) -> BotInstance:
    cid = str(chat_id)
    with _lock:
        if cid in _instances:
            _instances[cid].stop()
        inst = BotInstance(cid, ip, int(port), username, password)
        _instances[cid] = inst
    inst.start()
    return inst


def stop_bot(chat_id) -> bool:
    inst = _instances.get(str(chat_id))
    if inst:
        inst.stop()
        return True
    return False


def rejoin_bot(chat_id) -> bool:
    inst = _instances.get(str(chat_id))
    if inst:
        inst.rejoin()
        return True
    return False


def get_instance(chat_id) -> BotInstance | None:
    return _instances.get(str(chat_id))
