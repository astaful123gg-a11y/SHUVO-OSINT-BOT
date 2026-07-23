import subprocess, sys, os, signal, time, json

# ── Auto-install all required packages on startup ──
def _install_requirements():
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    if not os.path.exists(req_file):
        print("[DEPS] requirements.txt not found, skipping.")
        return
    print("[DEPS] Installing / verifying all dependencies...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file,
             "--quiet", "--no-warn-script-location", "--break-system-packages"],
            capture_output=True, text=True, timeout=180
        )
        if result.returncode == 0:
            print("[DEPS] All dependencies ready ✅")
        else:
            print(f"[DEPS] pip warnings/errors:\n{result.stderr[-600:] if result.stderr else '(none)'}")
    except Exception as e:
        print(f"[DEPS] Dependency install failed: {e}")

_install_requirements()

# ── Ensure all required data files exist ──
os.makedirs("bot", exist_ok=True)

DEFAULT_FEATURES = {
    "ai_chat": True, "daily_claim": True, "redeem": True,
    "voice": True, "imagegen": True, "music": True,
    "bypass": True, "osint": True, "group_tools": True
}

INIT_FILES = {
    "bot/features.json":  json.dumps(DEFAULT_FEATURES),
    "bot/config.json":    "{}",
    "bot/user.json":      "{}",
    "bot/codes.json":     "{}",
    "bot/response.json":  "{}",
    "bot/groups.json":    "{}",
    "bot/locks.json":     "{}",
    "bot/lotteries.json": "{}",
    "bot/video_ids.json": "{}",
}
for fpath, default in INIT_FILES.items():
    if not os.path.exists(fpath):
        with open(fpath, "w") as fp:
            fp.write(default)
        print(f"[INIT] Created {fpath}")

SHUVO_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Auto-update yt-dlp so /play always works with latest YouTube fixes ──
def _update_ytdlp():
    print("[UPDATE] Checking for yt-dlp update...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-U", "--quiet", "yt-dlp"],
            capture_output=True, text=True, timeout=90
        )
        import yt_dlp
        print(f"[UPDATE] yt-dlp ready: v{yt_dlp.version.__version__}")
    except Exception as e:
        print(f"[UPDATE] yt-dlp update skipped: {e}")

_update_ytdlp()

processes = []

def cleanup(signum=None, frame=None):
    print("\n[EXIT] Shutting down all bots...")
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(2)
    for p in processes:
        try:
            if p.poll() is None:
                p.kill()
        except Exception:
            pass
    print("[EXIT] Done.")
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT,  cleanup)

def start_process(cmd_args, label, cwd=None):
    print(f"[START] {label}...")
    return subprocess.Popen(
        cmd_args,
        stdout=sys.stdout,
        stderr=sys.stderr,
        cwd=cwd or SHUVO_DIR,
    )

print("=" * 45)
print("   SHUVO BOT — Starting up")
print("=" * 45)

p1 = start_process([sys.executable, "-u", "main.py"],       "Shuvo Main Bot")
time.sleep(4)
p2 = start_process([sys.executable, "-u", "controller.py"], "Shuvo Controller Bot")

processes = [p1, p2]
print("[OK] Shuvobot is running!\n")

# ── Watchdog with exponential backoff + daily yt-dlp auto-update ──
_crash_count  = [0, 0]
_MAX_BACKOFF  = 60
_DAILY_UPDATE = 24 * 60 * 60   # seconds between auto-updates (24 h)
_last_update  = time.time()

while True:
    time.sleep(5)

    # Daily yt-dlp auto-update (keeps /play working through YouTube changes)
    if time.time() - _last_update >= _DAILY_UPDATE:
        _update_ytdlp()
        _last_update = time.time()

    if p1.poll() is not None:
        _crash_count[0] += 1
        wait = min(5 * _crash_count[0], _MAX_BACKOFF)
        print(f"[WARN] main.py crashed (#{_crash_count[0]}), retry in {wait}s...")
        time.sleep(wait)
        p1 = start_process([sys.executable, "-u", "main.py"], "Shuvo Main Bot")
        processes[0] = p1
    else:
        _crash_count[0] = 0   # reset on healthy tick

    if p2.poll() is not None:
        _crash_count[1] += 1
        wait = min(5 * _crash_count[1], _MAX_BACKOFF)
        print(f"[WARN] controller.py crashed (#{_crash_count[1]}), retry in {wait}s...")
        time.sleep(wait)
        p2 = start_process([sys.executable, "-u", "controller.py"], "Shuvo Controller Bot")
        processes[1] = p2
    else:
        _crash_count[1] = 0   # reset on healthy tick
