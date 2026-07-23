"""
╔══════════════════════════════════════════════════════════════╗
║           YOUTUBE MODULE — SHUVO BOT                        ║
║   Features: /play, /video, /playvc, /stopvc,                ║
║             /skipvc, /vcqueue                               ║
║   Author: @Shuvobhai                                        ║
╚══════════════════════════════════════════════════════════════╝

HOW TO USE IN YOUR BOT:
─────────────────────────────────────────────
1. pip install yt-dlp python-telegram-bot pyrogram pytgcalls

2. (Optional but recommended) Create  bot/yt_cookies.txt
   — Export from your browser using "Get cookies.txt LOCALLY" extension
   — Log into YouTube first, then export youtube.com cookies
   — Save as  bot/yt_cookies.txt  (Netscape format)

3. (For /playvc only) Set these env vars or fill constants below:
   VC_API_ID      = your Telegram API ID (my.telegram.org)
   VC_API_HASH    = your Telegram API Hash
   VC_SESSION     = Pyrogram session string

4. In your main bot file:
   from youtube_module import register_youtube_handlers
   register_youtube_handlers(application)

5. In your CallbackQueryHandler, call:
   from youtube_module import handle_youtube_callback
   if await handle_youtube_callback(update, context):
       return
─────────────────────────────────────────────
"""

import os
import asyncio
import tempfile
import shutil

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

# ── VC Credentials (fill in or set as env vars) ───────────────────────────────
VC_API_ID   = int(os.getenv("VC_API_ID",   "0"))
VC_API_HASH = os.getenv("VC_API_HASH",     "")
VC_SESSION  = os.getenv("VC_SESSION",      "")

# ── Constants ─────────────────────────────────────────────────────────────────
YOUTUBE_COOKIES_FILE = "bot/yt_cookies.txt"

_PLAY_SRC_PREFIX = {
    "yt":  "ytsearch1:",
    "ytm": "https://music.youtube.com/search?q=",
    "sc":  "scsearch1:",
    "sp":  "ytsearch1:",
}
_PLAY_SRC_LABEL = {
    "yt":  "YouTube",
    "ytm": "YT Music",
    "sc":  "SoundCloud",
    "sp":  "Spotify→YT",
}

_VQ_FORMATS = {
    "360p":  "bestvideo[height<=360][ext=mp4]+bestaudio/best[height<=360][ext=mp4]/best[height<=360]",
    "480p":  "bestvideo[height<=480][ext=mp4]+bestaudio/best[height<=480][ext=mp4]/best[height<=480]",
    "720p":  "bestvideo[height<=720][ext=mp4]+bestaudio/best[height<=720][ext=mp4]/best[height<=720]",
    "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080][ext=mp4]/best[height<=1080]",
    "best":  "bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best",
}

# ── In-memory caches ──────────────────────────────────────────────────────────
_play_source_cache: dict = {}   # str(uid) → query_text
_video_cache:       dict = {}   # uid → {url, title, uploader, duration}
_vc_client               = None
_vc_calls                = None
_vc_queue:          dict = {}   # chat_id → list of (title, filepath)
_vc_current:        dict = {}   # chat_id → {title, filepath, requested_by}


# ── HTML helpers ──────────────────────────────────────────────────────────────
def _e(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _bq(text: str) -> str:
    return f"<blockquote>{text}</blockquote>"

def _ikb(label: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=callback_data)


# ── yt-dlp base options (cookies + EJS n-challenge solver) ───────────────────
def _yt_base_opts(extra: dict = None) -> dict:
    """
    Base yt-dlp options for YouTube.
    - Loads cookies from bot/yt_cookies.txt if present
    - Passes node path so yt-dlp can solve YouTube's n-challenge
    - Downloads EJS challenge solver from GitHub automatically
    """
    import shutil as _shutil
    _node = (
        _shutil.which("node")
        or "/nix/store/s7awkfc4pym4zj139fsxrjs5xwf5hhnd-nodejs-24.13.0-wrapped/bin/node"
    )
    opts = {
        "quiet":            True,
        "no_warnings":      True,
        "noplaylist":       True,
        "socket_timeout":   30,
        "retries":          3,
        "fragment_retries": 3,
        "js_runtimes":      {"node": {"path": _node}} if _node else {},
        "remote_components": {"ejs:github"},
    }
    if os.path.isfile(YOUTUBE_COOKIES_FILE):
        opts["cookiefile"] = YOUTUBE_COOKIES_FILE
    if extra:
        opts.update(extra)
    return opts


# ── /play — Music Download ─────────────────────────────────────────────────────
async def _do_play_download(chat, query_text: str, uid: str, source: str, is_url: bool = False):
    """Download audio from chosen source and send to chat as audio file."""
    import yt_dlp

    prefix       = _PLAY_SRC_PREFIX.get(source, "ytsearch1:")
    label        = _PLAY_SRC_LABEL.get(source, "YouTube")
    search_query = query_text.strip() if is_url else f"{prefix}{query_text}"

    sent = await chat.send_message(
        f"<blockquote><b>🎵 Searching {_e(label)}...</b>\n⏳ Please wait...</blockquote>",
        parse_mode=ParseMode.HTML,
    )

    tmp_dir = tempfile.mkdtemp()
    try:
        loop = asyncio.get_event_loop()

        def _search_only(query: str) -> list:
            results = []
            seen = set()
            for sq in [
                f"ytsearch5:{query}",
                f"ytsearch5:{query} song",
                f"ytsearch5:{query} audio",
            ]:
                try:
                    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
                            "socket_timeout": 15, "extract_flat": "in_playlist"}
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        r = ydl.extract_info(sq, download=False)
                        for e in (r.get("entries") or []):
                            if not e:
                                continue
                            url = e.get("url") or e.get("webpage_url") or ""
                            if url and url not in seen:
                                seen.add(url)
                                if not url.startswith("http"):
                                    url = f"https://www.youtube.com/watch?v={url}"
                                results.append({"url": url, "title": e.get("title", "")})
                except Exception:
                    pass
                if len(results) >= 8:
                    break
            return results

        def _try_download(url: str) -> tuple:
            dl_opts = _yt_base_opts({
                "format": "bestaudio/best",
                "outtmpl": os.path.join(tmp_dir, "%(title).60s.%(ext)s"),
            })
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info and "entries" in info:
                    entries = [e for e in info["entries"] if e]
                    info = entries[0] if entries else None
                if not info:
                    raise ValueError("No info returned")
                audio_exts = (".m4a", ".mp3", ".webm", ".opus", ".ogg", ".aac")
                for f in os.listdir(tmp_dir):
                    if f.endswith(audio_exts):
                        return os.path.join(tmp_dir, f), info
                raise ValueError("Downloaded file not found")

        def _dl():
            if is_url:
                return _try_download(query_text.strip())
            candidates = _search_only(query_text)
            if not candidates:
                raise ValueError("No search results found.")
            last_err = None
            for c in candidates:
                try:
                    return _try_download(c["url"])
                except Exception as e:
                    last_err = e
                    continue
            raise last_err or ValueError("All candidates failed to download.")

        filepath, info = await loop.run_in_executor(None, _dl)

        audio_exts = (".m4a", ".mp3", ".webm", ".opus", ".ogg", ".aac")
        if not os.path.exists(filepath):
            for f in os.listdir(tmp_dir):
                if f.endswith(audio_exts):
                    filepath = os.path.join(tmp_dir, f)
                    break

        fsize    = os.path.getsize(filepath)
        title    = (info.get("title")    or query_text)[:80]
        uploader = (info.get("uploader") or info.get("channel") or label)[:50]
        duration = info.get("duration") or 0
        MAX_BYTES = 45 * 1024 * 1024

        if fsize > MAX_BYTES:
            part_dur = int((duration * MAX_BYTES) / fsize) - 5
            part_dur = max(60, part_dur)
            n_parts  = -(-duration // part_dur)

            await sent.edit_text(
                f"<blockquote><b>🎵 Large track detected!</b>\n"
                f"📦 Splitting into {n_parts} parts...\n⏳ Please wait...</blockquote>",
                parse_mode=ParseMode.HTML
            )

            parts = []
            for i in range(n_parts):
                start    = i * part_dur
                part_out = os.path.join(tmp_dir, f"part_{i+1}.mp3")
                cmd = [
                    "ffmpeg", "-y", "-i", filepath,
                    "-ss", str(start), "-t", str(part_dur),
                    "-acodec", "libmp3lame", "-q:a", "4",
                    "-loglevel", "quiet", part_out
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await proc.wait()
                if os.path.exists(part_out) and os.path.getsize(part_out) > 0:
                    parts.append(part_out)

            await sent.delete()
            for idx, part_path in enumerate(parts, 1):
                part_cap = (
                    "<blockquote><b>🎵 SHUVO MUSIC PLAYER 🎵</b>\n"
                    "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
                    f"<b>🎶 Title</b>  : {_e(title)}\n"
                    f"<b>🎤 Artist</b> : {_e(uploader)}\n"
                    f"<b>📦 Part</b>   : {idx} / {len(parts)}\n"
                    f"<b><tg-emoji emoji-id='5465169893580086142'>⭐</tg-emoji> Source</b> : {_e(label)}\n\n"
                    "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
                    "<b><tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> Dev</b> : @Shuvobhai</blockquote>"
                )
                with open(part_path, "rb") as pf:
                    await chat.send_audio(
                        audio=pf,
                        caption=part_cap if idx == len(parts) else
                                f"<blockquote><b>🎵 {_e(title)}</b> — Part {idx}/{len(parts)}</blockquote>",
                        parse_mode=ParseMode.HTML,
                        title=f"{title} (Part {idx}/{len(parts)})",
                        performer=uploader,
                    )
        else:
            caption = (
                "<blockquote><b>🎵 SHUVO MUSIC PLAYER 🎵</b>\n"
                "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
                f"<b>🎶 Title</b>    : {_e(title)}\n"
                f"<b>🎤 Artist</b>   : {_e(uploader)}\n"
                f"<b>⏱ Duration</b> : {duration//60}m {duration%60}s\n"
                f"<b><tg-emoji emoji-id='5465169893580086142'>⭐</tg-emoji> Source</b>   : {_e(label)}\n\n"
                "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
                "<b><tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> Dev</b> : @Shuvobhai</blockquote>"
            )
            await sent.delete()
            with open(filepath, "rb") as af:
                await chat.send_audio(
                    audio=af,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    title=title,
                    performer=uploader,
                    duration=duration,
                )

    except Exception as e:
        err = str(e)[:250]
        try:
            await sent.edit_text(
                f"<blockquote><b>❌ Play Failed!</b>\n\n"
                f"{_e(err)}\n\n"
                f"<b>Try:</b> /play Kesariya\n\n"
                f"<b><tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> Dev</b> @Shuvobhai</blockquote>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/play — Search and download audio from YouTube/SoundCloud/Spotify."""
    import re as _re
    tg_user    = update.effective_user
    uid        = str(tg_user.id)
    query_text = " ".join(context.args).strip() if context.args else ""

    if not query_text:
        await update.message.reply_text(
            _bq("🎵 Play — Music\n\n"
                "Usage: /play song name\n"
                "       /play YouTube link\n\n"
                "Example: /play Kesariya\n"
                "Example: /play Shape of You Ed Sheeran\n\n"
                "✅ FREE for everyone!")
        , parse_mode=ParseMode.HTML)
        return

    _YT_URL_RE = _re.compile(
        r"(https?://)?(www\.)?(youtube\.com/(watch\?.*v=|shorts/|embed/)|youtu\.be/)[\w\-]+"
    )
    is_url = bool(_YT_URL_RE.match(query_text.strip()))

    if is_url:
        await _do_play_download(update.effective_chat, query_text, uid, "yt", is_url=True)
        return

    query_text = query_text[:150]
    _play_source_cache[uid] = query_text

    kb = InlineKeyboardMarkup([
        [
            _ikb("📺 YouTube",    f"playsrc_yt_{uid}"),
            _ikb("🎵 YT Music",   f"playsrc_ytm_{uid}"),
        ],
        [
            _ikb("☁️ SoundCloud", f"playsrc_sc_{uid}"),
            _ikb("💚 Spotify",    f"playsrc_sp_{uid}"),
        ],
        [
            _ikb("❌ Cancel",     f"playsrc_cancel_{uid}"),
        ],
    ])
    await update.message.reply_text(
        f"<blockquote><b>🎵 Choose Music Source</b>\n"
        f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
        f"🔎 <b>Song :</b> {_e(query_text)}\n\n"
        f"Select a platform to search & play from 👇</blockquote>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


# ── /video — YouTube Video Download ───────────────────────────────────────────
async def _do_yt_download(update: Update, url: str, user_name: str = "User"):
    """Download YouTube video and send via Telegram (max 50 MB)."""
    import yt_dlp

    sent = await update.message.reply_text(
        "<blockquote>📥 <b>YouTube Download</b>\n⏳ Fetching video info...</blockquote>",
        parse_mode=ParseMode.HTML
    )
    tmp_dir  = tempfile.mkdtemp()
    out_tmpl = os.path.join(tmp_dir, "%(title).60s.%(ext)s")

    ydl_opts = _yt_base_opts({
        "format": "bestvideo[ext=mp4][filesize<45M]+bestaudio/best[ext=mp4][filesize<45M]/best[filesize<45M]/best",
        "outtmpl": out_tmpl,
        "merge_output_format": "mp4",
        "socket_timeout": 40,
    })

    try:
        loop = asyncio.get_event_loop()

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info).replace(".webm", ".mp4").replace(".mkv", ".mp4"), info

        filepath, info = await loop.run_in_executor(None, _download)

        if not os.path.exists(filepath):
            for f in os.listdir(tmp_dir):
                filepath = os.path.join(tmp_dir, f)
                break

        fsize = os.path.getsize(filepath)
        if fsize > 50 * 1024 * 1024:
            raise Exception(f"Video too large ({fsize // (1024*1024)} MB). Try a shorter video.")

        title    = (info.get("title") or "Video")[:80]
        duration = info.get("duration") or 0
        uploader = info.get("uploader") or info.get("channel") or "YouTube"

        caption = (
            "<blockquote>"
            "<b>⚡ SHUVO DOWNLOAD ⚡</b>\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            f"<b>📹 Title</b>    : {_e(title)}\n"
            f"<b>👤 Channel</b>  : {_e(uploader)}\n"
            f"<b><tg-emoji emoji-id='5465169893580086142'>⭐</tg-emoji> Source</b>   : YouTube\n"
            f"<b>⏱ Duration</b> : {duration//60}m {duration%60}s\n\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
            "<b>✅ Downloaded successfully!</b>\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            "<b>🥫 Dev</b> : @Shuvobhai"
            "</blockquote>"
        )
        await sent.delete()
        with open(filepath, "rb") as vf:
            await update.message.reply_video(
                video=vf,
                caption=caption,
                parse_mode=ParseMode.HTML,
                supports_streaming=True,
            )
    except Exception as e:
        err_msg = str(e)[:300]
        try:
            await sent.edit_text(
                f"<blockquote><b>❌ YouTube Download Failed!</b>\n\n{_e(err_msg)}\n\n"
                f"<b><tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> DEV</b> @Shuvobhai ✅</blockquote>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def cmd_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/video — Search YouTube, show quality buttons, then download on selection."""
    import yt_dlp, re as _re
    tg_user = update.effective_user
    uid     = str(tg_user.id)
    query   = " ".join(context.args).strip() if context.args else ""

    if not query:
        await update.message.reply_text(
            _bq("🎬 Video — YouTube Download\n\n"
                "Usage: /video song or title\n"
                "       /video YouTube link\n\n"
                "Example: /video Kesariya\n"
                "Example: /video https://youtu.be/xxxxx\n\n"
                "📌 Max 50 MB  |  ✅ FREE!")
        , parse_mode=ParseMode.HTML)
        return

    _YT_URL_RE = _re.compile(
        r"(https?://)?(www\.)?(youtube\.com/(watch\?.*v=|shorts/|embed/)|youtu\.be/)[\w\-]+"
    )
    is_url       = bool(_YT_URL_RE.match(query.strip()))
    search_query = query.strip() if is_url else f"ytsearch1:{query}"

    sent = await update.message.reply_text(
        "<blockquote>🎬 <b>YouTube Video</b>\n⏳ Searching...</blockquote>",
        parse_mode=ParseMode.HTML
    )

    try:
        loop          = asyncio.get_event_loop()
        ydl_info_opts = _yt_base_opts({"extract_flat": False})

        def _get_info():
            with yt_dlp.YoutubeDL(ydl_info_opts) as ydl:
                info = ydl.extract_info(search_query, download=False)
                if "entries" in info:
                    entries = [e for e in info["entries"] if e]
                    if not entries:
                        raise ValueError("No results found.")
                    info = entries[0]
                return info

        info     = await loop.run_in_executor(None, _get_info)
        title    = (info.get("title")    or query)[:80]
        uploader = (info.get("uploader") or info.get("channel") or "YouTube")[:50]
        duration = info.get("duration")  or 0
        yt_url   = info.get("webpage_url") or search_query
        mins, secs = divmod(int(duration), 60)

        _video_cache[uid] = {
            "url": yt_url, "title": title,
            "uploader": uploader, "duration": duration,
        }

        kb = InlineKeyboardMarkup([
            [
                _ikb("<tg-emoji emoji-id='5465169893580086142'>⭐</tg-emoji> 360p",  f"vq_{uid}_360p"),
                _ikb("📺 480p",  f"vq_{uid}_480p"),
                _ikb("🖥 720p",  f"vq_{uid}_720p"),
            ],
            [
                _ikb("🎞 1080p", f"vq_{uid}_1080p"),
                _ikb("⚡ Best",  f"vq_{uid}_best"),
            ],
        ])
        await sent.edit_text(
            f"<blockquote><b>🎬 Found!</b>\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            f"<b>📹</b> {_e(title)}\n"
            f"<b>👤</b> {_e(uploader)}\n"
            f"<b>⏱</b> {mins}m {secs}s\n\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
            f"<b>👇 Choose quality to download:</b></blockquote>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
    except Exception as e:
        err = str(e)[:250]
        try:
            await sent.edit_text(
                f"<blockquote><b>❌ Video Failed!</b>\n\n"
                f"<code>{_e(err)}</code>\n\n"
                f"💡 Try: /video Kesariya\n\n"
                f"<b><tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> Dev</b> @Shuvobhai</blockquote>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass


# ── Voice Chat Player ─────────────────────────────────────────────────────────
async def _vc_init():
    """Lazily initialise Pyrogram client + PyTgCalls."""
    global _vc_client, _vc_calls
    if _vc_calls is not None:
        return True
    try:
        from pyrogram import Client
        from pytgcalls import PyTgCalls, filters as tgfilters
        from pytgcalls.types import MediaStream, AudioQuality

        _vc_client = Client(
            name="vc_player",
            api_id=VC_API_ID,
            api_hash=VC_API_HASH,
            session_string=VC_SESSION,
            no_updates=False,
        )
        await _vc_client.start()
        _vc_calls = PyTgCalls(_vc_client)

        async def _on_stream_end(client, update_obj):
            try:
                cid = update_obj.chat_id
            except AttributeError:
                return
            _vc_current.pop(cid, None)
            nxt = _vc_queue.get(cid, [])
            if nxt:
                nxt_title, nxt_path, nxt_req = nxt.pop(0)
                _vc_current[cid] = {"title": nxt_title, "filepath": nxt_path, "requested_by": nxt_req}
                try:
                    await client.play(cid, MediaStream(nxt_path, audio_parameters=AudioQuality.HIGH,
                                                       video_flags=MediaStream.Flags.IGNORE))
                except Exception:
                    _vc_current.pop(cid, None)
            else:
                try:
                    await client.leave_call(cid)
                except Exception:
                    pass

        _vc_calls.add_handler(_on_stream_end, tgfilters.stream_end)
        await _vc_calls.start()
        return True
    except Exception as e:
        _vc_client = None
        _vc_calls  = None
        raise RuntimeError(f"VC init failed: {e}")


async def _vc_ensure_joined(chat_id: int):
    if _vc_client is None:
        return
    try:
        await _vc_client.get_chat(chat_id)
    except Exception:
        try:
            await _vc_client.join_chat(chat_id)
            await asyncio.sleep(1)
        except Exception:
            pass


async def cmd_playvc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/playvc — Play a song in the group Voice Chat."""
    import yt_dlp
    try:
        from pytgcalls.types import MediaStream, AudioQuality
    except ImportError:
        await update.message.reply_text(_bq("❌ Voice Chat feature not available on this server.", parse_mode=ParseMode.HTML)
        return

    tg_user    = update.effective_user
    chat       = update.effective_chat
    uid        = str(tg_user.id)
    query_text = " ".join(context.args).strip() if context.args else ""

    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text(
            _bq("❌ /playvc only works in groups!\n\nAdd me to a group, start a Voice Chat, then use /playvc.")
        , parse_mode=ParseMode.HTML)
        return

    if not query_text:
        await update.message.reply_text(
            "<blockquote>"
            "<b>🎙 VC PLAYER 🎙</b>\n\n"
            "<b>Usage:</b> /playvc song name\n\n"
            "<b>Example:</b> /playvc Kesariya\n\n"
            "▶ Bot must be in a <b>Voice Chat</b> to play!\n"
            "📌 Use /stopvc to stop\n"
            "📋 Use /vcqueue to see queue"
            "</blockquote>",
            parse_mode=ParseMode.HTML
        )
        return

    sent = await update.message.reply_text(
        f"<blockquote><b>🎙 VC Player</b>\n"
        f"🔎 Searching: <i>{_e(query_text)}</i>\n\n"
        f"⏳ Please wait...</blockquote>",
        parse_mode=ParseMode.HTML
    )

    tmp_dir = tempfile.mkdtemp()
    try:
        loop = asyncio.get_event_loop()

        def _vc_search(query: str) -> list:
            results = []
            seen = set()
            for sq in [f"ytsearch5:{query}", f"ytsearch5:{query} song", f"ytsearch5:{query} audio"]:
                try:
                    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
                            "socket_timeout": 15, "extract_flat": "in_playlist"}
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        r = ydl.extract_info(sq, download=False)
                        for e in (r.get("entries") or []):
                            if not e:
                                continue
                            url = e.get("url") or e.get("webpage_url") or ""
                            if url and url not in seen:
                                seen.add(url)
                                if not url.startswith("http"):
                                    url = f"https://www.youtube.com/watch?v={url}"
                                results.append({"url": url, "title": e.get("title", "")})
                except Exception:
                    pass
                if len(results) >= 8:
                    break
            return results

        def _vc_try_dl(url: str) -> tuple:
            dl_opts = _yt_base_opts({
                "format": "bestaudio/best",
                "outtmpl": os.path.join(tmp_dir, "%(title).60s.%(ext)s"),
            })
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info and "entries" in info:
                    entries = [e for e in info["entries"] if e]
                    info = entries[0] if entries else None
                if not info:
                    raise ValueError("No info returned")
                audio_exts = (".m4a", ".mp3", ".webm", ".opus", ".ogg", ".aac")
                for f in os.listdir(tmp_dir):
                    if f.endswith(audio_exts):
                        return os.path.join(tmp_dir, f), info
                raise ValueError("Downloaded file not found")

        def _dl():
            candidates = _vc_search(query_text)
            if not candidates:
                raise ValueError("No search results found.")
            last_err = None
            for c in candidates:
                try:
                    return _vc_try_dl(c["url"])
                except Exception as e:
                    last_err = e
                    continue
            raise last_err or ValueError("All candidates failed to download.")

        filepath, info = await loop.run_in_executor(None, _dl)

        audio_exts = (".m4a", ".mp3", ".webm", ".opus", ".ogg", ".aac")
        if not os.path.exists(filepath):
            for f in os.listdir(tmp_dir):
                if f.endswith(audio_exts):
                    filepath = os.path.join(tmp_dir, f)
                    break

        title    = (info.get("title")    or query_text)[:80]
        uploader = (info.get("uploader") or info.get("channel") or "YouTube")[:50]
        duration = info.get("duration") or 0

        await sent.edit_text(
            f"<blockquote><b>🎙 VC Player</b>\n"
            f"✅ Found: <b>{_e(title)}</b>\n\n"
            f"🔌 Connecting to Voice Chat...</blockquote>",
            parse_mode=ParseMode.HTML
        )
        await _vc_init()

        chat_id = chat.id
        await _vc_ensure_joined(chat_id)

        from pytgcalls.types import GroupCallConfig
        vc_call = await _vc_calls.get_full_chat(chat_id)
        if vc_call is None:
            await sent.edit_text(
                f"<blockquote><b>❌ No Active Voice Chat!</b>\n\n"
                f"Please ask an admin to start a <b>Voice Chat</b> in this group first.\n\n"
                f"<b>Steps:</b>\n"
                f"1️⃣ Tap the group name → Voice Chat → Start\n"
                f"2️⃣ Then send /playvc again\n\n"
                f"<b><tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> Dev</b> @Shuvobhai</blockquote>",
                parse_mode=ParseMode.HTML
            )
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return

        already_playing = chat_id in _vc_current

        if already_playing:
            if chat_id not in _vc_queue:
                _vc_queue[chat_id] = []
            _vc_queue[chat_id].append((title, filepath, tg_user.first_name or tg_user.username or uid))
            pos = len(_vc_queue[chat_id])
            await sent.edit_text(
                f"<blockquote><b>📋 Added to Queue #{pos}</b>\n\n"
                f"<b>🎵 Title</b>   : {_e(title)}\n"
                f"<b>🎤 Artist</b>  : {_e(uploader)}\n"
                f"<b>⏱ Duration</b>: {duration//60}m {duration%60}s\n\n"
                f"<b>▶ Now Playing</b>: {_e(_vc_current[chat_id]['title'])}</blockquote>",
                parse_mode=ParseMode.HTML
            )
        else:
            _vc_current[chat_id] = {
                "title":        title,
                "filepath":     filepath,
                "requested_by": tg_user.first_name or tg_user.username or uid,
            }
            await _vc_calls.play(
                chat_id,
                MediaStream(filepath, audio_parameters=AudioQuality.HIGH,
                            video_flags=MediaStream.Flags.IGNORE),
                GroupCallConfig(auto_start=False),
            )
            await sent.edit_text(
                f"<blockquote><b>🎙 SHUVO VC PLAYER 🎙</b>\n"
                f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
                f"<b>▶ Now Playing</b>\n"
                f"<b>🎵 Title</b>   : {_e(title)}\n"
                f"<b>🎤 Artist</b>  : {_e(uploader)}\n"
                f"<b>⏱ Duration</b>: {duration//60}m {duration%60}s\n\n"
                f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
                f"📌 /stopvc  |  ⏭ /skipvc  |  📋 /vcqueue\n"
                f"<b><tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> Dev</b>: @Shuvobhai</blockquote>",
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        err = str(e)[:200]
        try:
            await sent.edit_text(
                f"<blockquote><b>❌ VC Play Failed!</b>\n\n"
                f"<code>{_e(err)}</code>\n\n"
                f"<b>Make sure:</b>\n"
                f"• Voice Chat is <b>active</b> in the group\n"
                f"• Userbot has joined the group\n\n"
                f"<b><tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> Dev</b> @Shuvobhai</blockquote>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def cmd_stopvc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stopvc — Stop VC playback and leave the voice chat."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text(_bq("❌ Only works in groups.", parse_mode=ParseMode.HTML)
        return
    chat_id = chat.id
    if _vc_calls is None or chat_id not in _vc_current:
        await update.message.reply_text(_bq("❌ Nothing is playing right now.", parse_mode=ParseMode.HTML)
        return
    try:
        await _vc_calls.leave_call(chat_id)
    except Exception:
        pass
    _vc_current.pop(chat_id, None)
    _vc_queue.pop(chat_id, None)
    await update.message.reply_text(
        _bq("⏹ Stopped! Left the Voice Chat.\n\nUse /playvc to play again.")
    , parse_mode=ParseMode.HTML)


async def cmd_skipvc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/skipvc — Skip current track and play next in queue."""
    try:
        from pytgcalls.types import MediaStream, AudioQuality
    except ImportError:
        await update.message.reply_text(_bq("❌ Voice Chat feature not available.", parse_mode=ParseMode.HTML)
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text(_bq("❌ Only works in groups.", parse_mode=ParseMode.HTML)
        return
    chat_id = chat.id
    if _vc_calls is None or chat_id not in _vc_current:
        await update.message.reply_text(_bq("❌ Nothing is playing right now.", parse_mode=ParseMode.HTML)
        return
    nxt = _vc_queue.get(chat_id, [])
    if not nxt:
        try:
            await _vc_calls.leave_call(chat_id)
        except Exception:
            pass
        _vc_current.pop(chat_id, None)
        await update.message.reply_text(_bq("⏭ Skipped! Queue is empty, stopped VC.", parse_mode=ParseMode.HTML)
        return
    nxt_title, nxt_path, nxt_req = nxt.pop(0)
    _vc_current[chat_id] = {"title": nxt_title, "filepath": nxt_path, "requested_by": nxt_req}
    try:
        await _vc_calls.play(
            chat_id,
            MediaStream(nxt_path, audio_parameters=AudioQuality.HIGH,
                        video_flags=MediaStream.Flags.IGNORE)
        )
    except Exception as e:
        await update.message.reply_text(_bq(f"❌ Skip failed: {e}", parse_mode=ParseMode.HTML)
        return
    await update.message.reply_text(
        f"<blockquote><b>⏭ Skipped!</b>\n\n"
        f"<b>▶ Now Playing</b>: {_e(nxt_title)}\n"
        f"<b>📋 Queue left</b>: {len(_vc_queue.get(chat_id, []))}</blockquote>",
        parse_mode=ParseMode.HTML
    )


async def cmd_vcqueue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/vcqueue — Show current VC queue."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text(_bq("❌ Only works in groups.", parse_mode=ParseMode.HTML)
        return
    chat_id = chat.id
    current = _vc_current.get(chat_id)
    queue   = _vc_queue.get(chat_id, [])
    if not current:
        await update.message.reply_text(_bq("❌ Nothing is playing right now.\n\nUse /playvc to start.", parse_mode=ParseMode.HTML)
        return
    lines = [
        "<blockquote>",
        "<b>🎙 VC QUEUE</b>",
        "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n",
        f"<b>▶ Now Playing</b>",
        f"🎵 {_e(current['title'])}",
        f"👤 {_e(current['requested_by'])}\n",
    ]
    if queue:
        lines.append("<b>📋 Up Next:</b>")
        for i, (t, _, req) in enumerate(queue, 1):
            lines.append(f"  {i}. {_e(t)}  — {_e(req)}")
    else:
        lines.append("📋 Queue is empty")
    lines += ["<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>", "⏭ /skipvc  |  ⏹ /stopvc", "</blockquote>"]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ── Callback Query Handler ─────────────────────────────────────────────────────
async def handle_youtube_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Call this from your CallbackQueryHandler.
    Returns True if callback was handled.
    """
    import yt_dlp
    query = update.callback_query
    if not query:
        return False
    data = query.data or ""

    # ── Play source selection ──────────────────────────────────────────────────
    if data.startswith("playsrc_"):
        parts = data.split("_", 2)
        if len(parts) < 3:
            await query.answer()
            return True
        source = parts[1]
        uid    = parts[2]

        if source == "cancel":
            await query.answer("Cancelled")
            try:
                await query.message.delete()
            except Exception:
                pass
            return True

        query_text = _play_source_cache.get(uid, "")
        if not query_text:
            await query.answer("Session expired. Please use /play again.", show_alert=True)
            return True

        await query.answer(f"Searching {_PLAY_SRC_LABEL.get(source, source)}...")
        try:
            await query.message.delete()
        except Exception:
            pass
        await _do_play_download(query.message.chat, query_text, uid, source, is_url=False)
        return True

    # ── Video quality selection ────────────────────────────────────────────────
    if data.startswith("vq_"):
        parts = data.split("_", 2)
        if len(parts) < 3:
            await query.answer()
            return True
        uid     = parts[1]
        quality = parts[2]

        cached = _video_cache.get(uid)
        if not cached:
            await query.answer("Session expired. Please use /video again.", show_alert=True)
            return True

        yt_url = cached["url"]
        title  = cached["title"]
        fmt    = _VQ_FORMATS.get(quality, _VQ_FORMATS["best"])

        await query.answer(f"Downloading {quality}...")
        try:
            await query.message.edit_text(
                f"<blockquote><b>⬇️ Downloading {quality}...</b>\n\n"
                f"<b>📹</b> {_e(title)}\n⏳ Please wait...</blockquote>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

        tmp_dir = tempfile.mkdtemp()
        try:
            loop = asyncio.get_event_loop()
            ydl_opts = _yt_base_opts({
                "format":              fmt,
                "outtmpl":             os.path.join(tmp_dir, "%(title).60s.%(ext)s"),
                "merge_output_format": "mp4",
                "socket_timeout":      40,
            })

            def _dl():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    inf = ydl.extract_info(yt_url, download=True)
                    return ydl.prepare_filename(inf).replace(".webm", ".mp4").replace(".mkv", ".mp4"), inf

            filepath, inf = await loop.run_in_executor(None, _dl)

            if not os.path.exists(filepath):
                for f in os.listdir(tmp_dir):
                    filepath = os.path.join(tmp_dir, f)
                    break

            fsize = os.path.getsize(filepath)
            if fsize > 50 * 1024 * 1024:
                raise Exception(f"File too large ({fsize//(1024*1024)} MB). Try a lower quality.")

            title_dl    = (inf.get("title") or title)[:80]
            duration_dl = inf.get("duration") or 0
            uploader_dl = inf.get("uploader") or inf.get("channel") or "YouTube"

            caption = (
                "<blockquote>"
                "<b>⚡ SHUVO DOWNLOAD ⚡</b>\n"
                "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
                f"<b>📹 Title</b>    : {_e(title_dl)}\n"
                f"<b>👤 Channel</b>  : {_e(uploader_dl)}\n"
                f"<b>🎞 Quality</b>  : {quality}\n"
                f"<b>⏱ Duration</b> : {duration_dl//60}m {duration_dl%60}s\n\n"
                "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
                "<b>✅ Downloaded!</b>\n"
                "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
                "<b>🥫 Dev</b> : @Shuvobhai"
                "</blockquote>"
            )
            try:
                await query.message.delete()
            except Exception:
                pass
            with open(filepath, "rb") as vf:
                await query.message.chat.send_video(
                    video=vf,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    supports_streaming=True,
                )
        except Exception as e:
            err = str(e)[:250]
            try:
                await query.message.edit_text(
                    f"<blockquote><b>❌ Download Failed!</b>\n\n{_e(err)}\n\n"
                    f"<b><tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> Dev</b> @Shuvobhai</blockquote>",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return True

    return False


# ── Registration ──────────────────────────────────────────────────────────────
def register_youtube_handlers(application):
    """
    Call this in your main bot setup:
        from youtube_module import register_youtube_handlers
        register_youtube_handlers(application)
    """
    application.add_handler(CommandHandler("play",     cmd_play))
    application.add_handler(CommandHandler("video",    cmd_video))
    application.add_handler(CommandHandler("playvc",   cmd_playvc))
    application.add_handler(CommandHandler("stopvc",   cmd_stopvc))
    application.add_handler(CommandHandler("skipvc",   cmd_skipvc))
    application.add_handler(CommandHandler("vcqueue",  cmd_vcqueue))
    application.add_handler(CallbackQueryHandler(
        handle_youtube_callback,
        pattern=r"^(playsrc_|vq_)"
    ))
    print("[YouTube Module] Handlers registered: /play, /video, /playvc, /stopvc, /skipvc, /vcqueue")
