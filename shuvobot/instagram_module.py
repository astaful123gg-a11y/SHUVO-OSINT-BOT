"""
╔══════════════════════════════════════════════════════════════╗
║          INSTAGRAM MODULE — SHUVO BOT                       ║
║   Features: /instainfo, /download (Instagram)               ║
║   Author: @Shuvobhai                                        ║
╚══════════════════════════════════════════════════════════════╝

HOW TO USE IN YOUR BOT:
─────────────────────────────────────────────
1. pip install instagrapi yt-dlp python-telegram-bot

2. Create  bot/insta_cookies.json  with your Instagram session:
   {
     "sessionid":  "YOUR_SESSIONID_HERE",
     "csrftoken":  "YOUR_CSRFTOKEN",
     "ds_user_id": "YOUR_USER_ID"
   }
   (Get these from browser DevTools → Application → Cookies → instagram.com)

3. In your main bot file:
   from instagram_module import register_instagram_handlers
   register_instagram_handlers(application)

4. In your message handler (handle_message), call:
   from instagram_module import handle_instagram_message
   if await handle_instagram_message(update, context, pending, users, uid):
       return
─────────────────────────────────────────────
"""

import os
import json
import asyncio
import tempfile
import urllib.parse

from telegram import Update, InputMediaVideo, InputMediaPhoto, ParseMode
from telegram.ext import ContextTypes, CommandHandler

# ── Constants ────────────────────────────────────────────────────────────────
INSTA_COOKIES_FILE = "bot/insta_cookies.json"
INSTA_COOKIES_TXT  = "bot/insta_cookies.txt"
INSTA_PROFILE_API  = "https://i.instagram.com/api/v1/users/web_profile_info/?username={}"

# ── Singleton instagrapi client ───────────────────────────────────────────────
_ig_client_instance  = None
_ig_client_sessionid = None


def _load_insta_cookies() -> dict:
    try:
        with open(INSTA_COOKIES_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _insta_cookies_have_session() -> bool:
    return bool(_load_insta_cookies().get("sessionid", "").strip())


def _write_insta_cookies_txt():
    """Write Netscape cookies.txt for yt-dlp from JSON cookies."""
    cookies = _load_insta_cookies()
    if not cookies.get("sessionid", "").strip():
        return None
    lines = ["# Netscape HTTP Cookie File\n"]
    for name, value in cookies.items():
        if value and str(value).strip():
            lines.append(f".instagram.com\tTRUE\t/\tTRUE\t9999999999\t{name}\t{value}\n")
    with open(INSTA_COOKIES_TXT, "w") as f:
        f.writelines(lines)
    return INSTA_COOKIES_TXT


def _insta_api_headers() -> dict:
    cookies = _load_insta_cookies()
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items() if v and str(v).strip())
    return {
        "User-Agent":       "Instagram 275.0.0.27.98 Android (33/13; 420dpi; 1080x2400; samsung; SM-G991B; o1s; exynos2100; en_US; 458229258)",
        "Accept":           "*/*",
        "Accept-Language":  "en-US,en;q=0.9",
        "X-IG-App-ID":      "936619743392459",
        "X-IG-WWW-Claim":   "0",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie":           cookie_str,
        "Referer":          "https://www.instagram.com/",
        "Origin":           "https://www.instagram.com",
    }


def _get_ig_client():
    """Return a cached instagrapi Client, re-login only if sessionid changed."""
    global _ig_client_instance, _ig_client_sessionid
    from instagrapi import Client as _IgClient
    cookies   = _load_insta_cookies()
    sessionid = cookies.get("sessionid", "").strip()
    if not sessionid:
        raise Exception("No Instagram sessionid in bot/insta_cookies.json")
    if _ig_client_instance is None or _ig_client_sessionid != sessionid:
        cl = _IgClient()
        cl.delay_range = [1, 3]
        cl.login_by_sessionid(sessionid)
        _ig_client_instance  = cl
        _ig_client_sessionid = sessionid
    return _ig_client_instance


# ── HTML helpers ─────────────────────────────────────────────────────────────
def _h(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _bq(text: str) -> str:
    return f"<blockquote>{text}</blockquote>"


# ── Instagram Profile Info ────────────────────────────────────────────────────
async def _do_insta_info_cookie(username: str):
    """Fetch Instagram profile info using instagrapi. Returns (caption_html, pic_url_or_None)."""
    import re as _re
    from datetime import datetime as _dt

    uname = username.lstrip("@").strip()
    if not uname:
        return _bq("❌ Invalid username.\n\n<tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> DEV @Shuvobhai ✅"), None

    loop = asyncio.get_event_loop()

    def _fetch():
        from instagrapi.exceptions import UserNotFound as _UserNotFound
        try:
            cl      = _get_ig_client()
            u       = cl.user_info_by_username(uname)
            uid_num = u.pk

            raw_user = {}
            try:
                raw_resp = cl.private_request(f"users/{uid_num}/info/")
                raw_user = raw_resp.get("user", {})
            except Exception:
                pass

            _actype_map = {1: "👤 Personal", 2: "🌟 Creator", 3: "💼 Business"}
            actype = _actype_map.get(u.account_type, f"Type {u.account_type}")

            def _fmt_num(n):
                if n is None: return "N/A"
                n = int(n)
                if n >= 1_000_000: return f"{n/1_000_000:.2f}M ({n:,})"
                if n >= 1_000:     return f"{n/1_000:.1f}K ({n:,})"
                return str(n)

            bio_links_str = "—"
            if u.bio_links:
                parts = [f"• {bl.title or 'Link'}: {bl.url}" for bl in u.bio_links]
                bio_links_str = "\n            ".join(parts)

            channel_str = "—"
            if u.broadcast_channel:
                bc = u.broadcast_channel[0]
                if bc and hasattr(bc, "title"):
                    channel_str = bc.title

            pinned_ch_list = (raw_user.get("pinned_channels_info", {}) or {}).get("pinned_channels_list", [])
            pinned_str = "—"
            if pinned_ch_list:
                pinned_str = ", ".join(
                    pc.get("title", "Channel") for pc in pinned_ch_list if pc.get("title")
                ) or str(len(pinned_ch_list)) + " channel(s)"

            threads_url   = raw_user.get("threads_profile_glyph_url", "")
            threads_uname = "—"
            if threads_url:
                _m = _re.search(r"username=([^&]+)", threads_url)
                if _m:
                    threads_uname = f"@{_m.group(1)}"

            fb_id    = str(u.interop_messaging_user_fbid or raw_user.get("interop_messaging_user_fbid") or "—")
            fb_id_v2 = str(raw_user.get("fbid_v2") or "—")
            fb_page  = raw_user.get("page_name") or "—"

            reels_count   = raw_user.get("total_clips_count")
            reels_str     = str(reels_count) if reels_count is not None else "N/A"
            latest_reel_ts  = raw_user.get("latest_reel_media")
            latest_reel_str = "—"
            if latest_reel_ts:
                try:
                    latest_reel_str = _dt.utcfromtimestamp(int(latest_reel_ts)).strftime("%d %b %Y")
                except Exception:
                    pass

            city     = u.city_name or "—"
            zip_code = raw_user.get("zip") or "—"
            email    = u.public_email or "—"
            phone    = (u.public_phone_number and
                        f"+{u.public_phone_country_code}{u.public_phone_number}") or "—"
            address  = u.address_street or "—"
            category = u.category_name or u.business_category_name or "—"

            meta_elig = raw_user.get("is_eligible_for_meta_verified_label", False)
            meta_str  = "✅ Eligible" if meta_elig else "❌ No"

            hd_info  = raw_user.get("hd_profile_pic_url_info", {})
            pic_url  = hd_info.get("url") or str(u.profile_pic_url_hd or u.profile_pic_url or "")

            return {
                "status": "ok",
                "username": u.username, "fullname": u.full_name or "—",
                "userid": str(uid_num), "fb_id": fb_id, "fb_id_v2": fb_id_v2,
                "fb_page": fb_page, "threads": threads_uname,
                "verified": u.is_verified, "private": u.is_private,
                "actype": actype, "is_biz": u.is_business, "category": category,
                "meta_verified": meta_str,
                "followers": _fmt_num(u.follower_count),
                "following": _fmt_num(u.following_count),
                "posts": str(u.media_count) if u.media_count is not None else "N/A",
                "reels": reels_str, "latest_reel": latest_reel_str,
                "bio": (u.biography or "—")[:300], "bio_links": bio_links_str,
                "ext_url": str(u.external_url or "—"),
                "channel": channel_str, "pinned_ch": pinned_str,
                "email": email, "phone": phone, "city": city,
                "zip": zip_code, "address": address, "pic_url": pic_url,
            }
        except _UserNotFound:
            return {"status": "notfound"}
        except Exception:
            return {"status": "ratelimit"}

    try:
        d = await loop.run_in_executor(None, _fetch)

        if d["status"] == "notfound":
            return _bq(f"📸 Instagram Info\n\n❌ @{_h(uname)} not found.\n\n<tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> DEV @Shuvobhai ✅"), None

        if d["status"] == "ratelimit":
            return _bq(
                f"📸 Instagram Info\n\n"
                f"⚠️ Instagram rate-limiting requests from this server.\n"
                f"Please try again in a few minutes.\n\n"
                f"<tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> DEV @Shuvobhai ✅"
            ), None

        v   = "✅ Yes" if d["verified"] else "❌ No"
        p   = "🔒 Yes" if d["private"]  else "🌐 No"
        biz = "✅ Yes" if d["is_biz"]   else "❌ No"

        caption = (
            f"<b>📸 Instagram Profile Info</b>\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
            f"👤 <b>Username</b>      : @{_h(d['username'])}\n"
            f"📛 <b>Full Name</b>     : {_h(d['fullname'])}\n"
            f"🆔 <b>User ID</b>       : <code>{_h(d['userid'])}</code>\n"
            f"📘 <b>FB User ID</b>    : <code>{_h(d['fb_id'])}</code>\n"
            f"📗 <b>FB Page ID</b>    : <code>{_h(d['fb_id_v2'])}</code>\n"
            f"📙 <b>FB Page Name</b>  : {_h(d['fb_page'])}\n"
            f"🧵 <b>Threads</b>       : {_h(d['threads'])}\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
            f"✅ <b>Verified</b>      : {v}\n"
            f"🔒 <b>Private</b>       : {p}\n"
            f"🏷 <b>Acc Type</b>     : {_h(d['actype'])}\n"
            f"💼 <b>Business</b>      : {biz}\n"
            f"📂 <b>Category</b>     : {_h(d['category'])}\n"
            f"🏅 <b>Meta Verified</b> : {_h(d['meta_verified'])}\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
            f"👥 <b>Followers</b>     : {_h(d['followers'])}\n"
            f"➡️ <b>Following</b>     : {_h(d['following'])}\n"
            f"📷 <b>Posts</b>         : {_h(d['posts'])}\n"
            f"🎬 <b>Reels</b>         : {_h(d['reels'])}\n"
            f"🕐 <b>Latest Reel</b>   : {_h(d['latest_reel'])}\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
            f"📝 <b>Bio</b>           : {_h(d['bio'])}\n"
            f"🔗 <b>Bio Links</b>     :\n   {_h(d['bio_links'])}\n"
            f"🌐 <b>Website</b>       : {_h(d['ext_url'])}\n"
            f"📺 <b>Broadcast Ch</b>  : {_h(d['channel'])}\n"
            f"📌 <b>Pinned Ch</b>     : {_h(d['pinned_ch'])}\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
            f"📧 <b>Email</b>         : {_h(d['email'])}\n"
            f"<tg-emoji emoji-id='5465169893580086142'>⭐</tg-emoji> <b>Phone</b>         : {_h(d['phone'])}\n"
            f"🏙 <b>City</b>          : {_h(d['city'])}\n"
            f"📮 <b>ZIP</b>           : {_h(d['zip'])}\n"
            f"🏠 <b>Address</b>       : {_h(d['address'])}\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
            f"<tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> DEV @Shuvobhai ✅"
        )
        return _bq(caption), d["pic_url"] or None

    except Exception as e:
        return _bq(f"📸 Instagram Info\n\n❌ Error: {_h(str(e)[:200])}\n\n<tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> DEV @Shuvobhai ✅"), None


# ── Instagram Download ────────────────────────────────────────────────────────
async def _do_insta_download_cookie(update: Update, url: str, user_name: str = "User"):
    """
    Download Instagram post/reel/story/carousel.
    Primary: instagrapi (handles albums). Fallback: yt-dlp.
    """
    import shutil as _shutil

    sent = await update.message.reply_text(
        "<blockquote>📸 <b>Instagram Download</b>\n⏳ Connecting to Instagram...</blockquote>",
        parse_mode=ParseMode.HTML
    )

    tmp_dir    = tempfile.mkdtemp()
    loop       = asyncio.get_event_loop()
    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
    VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi")

    def _make_caption(count=1):
        extra = f"\n📦 <b>Photos</b> : {count}" if count > 1 else ""
        return (
            "<blockquote>"
            "<b>⚡ INSTAGRAM DOWNLOAD ⚡</b>\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            f"<b>👤 User</b>   : {_h(user_name)}\n"
            f"<b><tg-emoji emoji-id='5465169893580086142'>⭐</tg-emoji> Source</b> : Instagram{extra}\n\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n"
            "<b>✅ Downloaded successfully!</b>\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            "<b>🥫 Dev</b> : @Shuvobhai"
            "</blockquote>"
        )

    async def _send_files(downloaded):
        total = len(downloaded)
        cap   = _make_caption(total)
        if total == 0:
            raise Exception("No files to send")
        if total == 1:
            fp, dur = downloaded[0]
            ext = os.path.splitext(fp)[1].lower()
            if ext in VIDEO_EXTS:
                await update.message.reply_video(
                    video=open(fp, "rb"), caption=cap,
                    parse_mode=ParseMode.HTML, duration=dur,
                    supports_streaming=True,
                )
            else:
                await update.message.reply_photo(
                    photo=open(fp, "rb"), caption=cap,
                    parse_mode=ParseMode.HTML,
                )
        else:
            BATCH = 10
            for batch_start in range(0, total, BATCH):
                batch = downloaded[batch_start:batch_start + BATCH]
                media_group = []
                handles = []
                for j, (fp, dur) in enumerate(batch):
                    ext = os.path.splitext(fp)[1].lower()
                    fh  = open(fp, "rb")
                    handles.append(fh)
                    item_cap = cap if (batch_start == 0 and j == 0) else None
                    pm = ParseMode.HTML if item_cap else None
                    if ext in VIDEO_EXTS:
                        media_group.append(InputMediaVideo(
                            media=fh, caption=item_cap, parse_mode=pm,
                            duration=dur, supports_streaming=True,
                        ))
                    else:
                        media_group.append(InputMediaPhoto(
                            media=fh, caption=item_cap, parse_mode=pm,
                        ))
                await update.message.reply_media_group(media=media_group)
                for fh in handles:
                    try: fh.close()
                    except Exception: pass
            await update.message.reply_text(
                _bq(f"📸 Instagram\n✅ {total} item(s) downloaded!\n\n<tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> DEV @Shuvobhai ✅"),
                parse_mode=ParseMode.HTML,
            )

    async def _try_instagrapi():
        def _fetch_and_download():
            global _ig_client_instance, _ig_client_sessionid
            cl = _get_ig_client()
            try:
                pk    = cl.media_pk_from_url(url)
                media = cl.media_info(pk)
            except Exception:
                _ig_client_instance  = None
                _ig_client_sessionid = None
                cl    = _get_ig_client()
                pk    = cl.media_pk_from_url(url)
                media = cl.media_info(pk)

            items = []
            if media.media_type == 8 and media.resources:
                for res in media.resources:
                    items.append(res)
            else:
                items = [media]

            result = []
            for i, item in enumerate(items):
                import urllib.request as _req
                if item.media_type == 2 and item.video_url:
                    fp = os.path.join(tmp_dir, f"{i:03d}.mp4")
                    _req.urlretrieve(str(item.video_url), fp)
                    dur = int(item.video_duration) if item.video_duration else 0
                    result.append((fp, dur))
                elif item.thumbnail_url:
                    fp = os.path.join(tmp_dir, f"{i:03d}.jpg")
                    _req.urlretrieve(str(item.thumbnail_url), fp)
                    result.append((fp, 0))
            return result
        return await loop.run_in_executor(None, _fetch_and_download)

    async def _try_ytdlp():
        import yt_dlp as _yt_dlp
        cookie_file = _write_insta_cookies_txt() if _insta_cookies_have_session() else None
        dl_opts = {
            "quiet": True, "no_warnings": True,
            "noplaylist": False, "socket_timeout": 30,
            "outtmpl": os.path.join(tmp_dir, "ytdlp_%(autonumber)s.%(ext)s"),
            "format": "best",
        }
        if cookie_file:
            dl_opts["cookiefile"] = cookie_file

        def _dl():
            with _yt_dlp.YoutubeDL(dl_opts) as ydl:
                return ydl.extract_info(url, download=True)
        info = await loop.run_in_executor(None, _dl)

        all_files = sorted(
            [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)
             if os.path.isfile(os.path.join(tmp_dir, f)) and f.startswith("ytdlp_")],
            key=lambda f: os.path.getmtime(f)
        )
        result = []
        for fp in all_files:
            ext = os.path.splitext(fp)[1].lower()
            if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
                continue
            if os.path.getsize(fp) > 50 * 1024 * 1024:
                continue
            result.append((fp, 0))
        return result

    try:
        downloaded = []
        try:
            downloaded = await _try_instagrapi()
        except Exception as ig_err:
            try:
                downloaded = await _try_ytdlp()
            except Exception:
                raise ig_err

        if not downloaded:
            raise Exception("No media found in this post")

        await sent.delete()
        await _send_files(downloaded)

    except Exception as e:
        try:
            await sent.edit_text(
                _bq(f"📸 Instagram Download\n\n❌ Failed: {_h(str(e)[:150])}\n\n<tg-emoji emoji-id='6147464060305676048'>😎</tg-emoji> DEV @Shuvobhai ✅"),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    finally:
        try:
            _shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


# ── Command Handlers ──────────────────────────────────────────────────────────
PENDING_INSTAINFO  = "instainfo"
PENDING_IG_DOWNLOAD = "ig_download"


async def cmd_instainfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /instainfo command."""
    if not update.message:
        return
    if context.args:
        username = " ".join(context.args).strip()
        await update.message.reply_text(
            "<blockquote>📸 <b>Instagram Info</b>\n⏳ Fetching profile...</blockquote>",
            parse_mode=ParseMode.HTML
        )
        caption, pic_url = await _do_insta_info_cookie(username)
        if pic_url:
            try:
                await update.message.reply_photo(photo=pic_url, caption=caption, parse_mode=ParseMode.HTML)
                return
            except Exception:
                pass
        await update.message.reply_text(caption, parse_mode=ParseMode.HTML)
        return
    context.user_data["pending"] = PENDING_INSTAINFO
    await update.message.reply_text(
        _bq("📸 Instagram Info\n\nSend Instagram username:\nExample: cristiano\n\n/cancel to go back.")
    , parse_mode=ParseMode.HTML)


async def cmd_igdownload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /igdownload command."""
    if not update.message:
        return
    if context.args:
        url = " ".join(context.args).strip()
        name = update.effective_user.first_name or update.effective_user.username or "User"
        await _do_insta_download_cookie(update, url, user_name=name)
        return
    context.user_data["pending"] = PENDING_IG_DOWNLOAD
    await update.message.reply_text(
        _bq("📥 Instagram Download\n\nSend Instagram post/reel/story URL:\n\n/cancel to go back.")
    , parse_mode=ParseMode.HTML)


async def handle_instagram_message(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                    pending: str, uid: str) -> bool:
    """
    Call this from your main message handler.
    Returns True if message was handled (so you can return early).
    """
    if not update.message or not update.message.text:
        return False
    text = update.message.text.strip()

    if pending == PENDING_INSTAINFO:
        context.user_data["pending"] = None
        caption, pic_url = await _do_insta_info_cookie(text)
        if pic_url:
            try:
                await update.message.reply_photo(photo=pic_url, caption=caption, parse_mode=ParseMode.HTML)
                return True
            except Exception:
                pass
        await update.message.reply_text(caption, parse_mode=ParseMode.HTML)
        return True

    if pending == PENDING_IG_DOWNLOAD:
        context.user_data["pending"] = None
        name = update.effective_user.first_name or update.effective_user.username or uid
        await _do_insta_download_cookie(update, text, user_name=name)
        return True

    # Auto-detect Instagram URL in any message
    import re as _re
    _INSTA_PATTERN = _re.compile(
        r"https?://(www\.)?instagram\.com/(p|reel|tv|stories)/[^\s]+"
    )
    if _INSTA_PATTERN.search(text):
        name = update.effective_user.first_name or update.effective_user.username or uid
        await _do_insta_download_cookie(update, text, user_name=name)
        return True

    return False


# ── Registration ──────────────────────────────────────────────────────────────
def register_instagram_handlers(application):
    """
    Call this in your main bot setup:
        from instagram_module import register_instagram_handlers
        register_instagram_handlers(application)
    """
    application.add_handler(CommandHandler("instainfo",   cmd_instainfo))
    application.add_handler(CommandHandler("igdownload",  cmd_igdownload))
    print("[Instagram Module] Handlers registered: /instainfo, /igdownload")
