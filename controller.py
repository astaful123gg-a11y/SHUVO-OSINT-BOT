import json
import os
import re
import sys
import signal
import subprocess
import hashlib
import string
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, MessageEntity
from telegram.constants import ParseMode


_BTN_EMOJI_IDS = {
    "⭐": "5465169893580086142",
    "💰": "5224257782013769471",
    "🎁": "5262889711466193287",
}

def _first_icon_id(text: str):
    """Return custom_emoji_id of the first recognized emoji in text, for icon_custom_emoji_id.
    Uses the full PREMIUM_EMOJI dict (resolved at call-time) so every known emoji is covered."""
    src = PREMIUM_EMOJI if 'PREMIUM_EMOJI' in globals() else _BTN_EMOJI_IDS
    for emoji_char, emoji_id in src.items():
        if emoji_char in text:
            return emoji_id
    return None

def _btn_entities(text: str):
    """Auto-build MessageEntity list for ALL premium custom emoji found in button text.
    Uses the full PREMIUM_EMOJI dict (resolved at call-time) so every known emoji is upgraded."""
    src = PREMIUM_EMOJI if 'PREMIUM_EMOJI' in globals() else _BTN_EMOJI_IDS
    entities = []
    for emoji_char, emoji_id in src.items():
        if emoji_char not in text:
            continue
        idx = 0
        while True:
            pos = text.find(emoji_char, idx)
            if pos == -1:
                break
            offset = len(text[:pos].encode('utf-16-le')) // 2
            length = len(emoji_char.encode('utf-16-le')) // 2
            entities.append(MessageEntity(
                type=MessageEntity.CUSTOM_EMOJI,
                offset=offset,
                length=length,
                custom_emoji_id=emoji_id,
            ))
            idx = pos + len(emoji_char)
    return entities or None

class _StyledIKB(InlineKeyboardButton):
    """InlineKeyboardButton subclass — style + animated emoji icon + entities via to_dict()."""
    def __init__(self, text, style=None, **kwargs):
        self.__style    = 'success' if style == 'active' else style
        self.__entities = kwargs.pop('entities', None)
        if 'icon_custom_emoji_id' not in kwargs:
            icon_id = _first_icon_id(text)
            if icon_id:
                kwargs['icon_custom_emoji_id'] = icon_id
        super().__init__(text, **kwargs)

    def to_dict(self, recursive=True):
        d = super().to_dict()
        if self.__style:
            d['style'] = self.__style
        if self.__entities:
            d['entities'] = [e.to_dict() for e in self.__entities]
        return d

def SBtn(text, style=None, **kwargs):
    """Button factory — animated icon + clean text label. Zero plain emojis ever show."""
    if style == 'active':
        style = 'success'
    # Step 1 — pick the animated icon from the first emoji in text (if not already supplied)
    if 'icon_custom_emoji_id' not in kwargs:
        icon_id = _first_icon_id(text)
        if icon_id:
            kwargs['icon_custom_emoji_id'] = icon_id
    # Step 2 — strip ALL emoji characters so button text is clean plain text
    try:
        text = _BARE_EMOJI_RE.sub('', text).strip()
    except NameError:
        pass
    # Step 3 — no entities needed
    kwargs.pop('entities', None)
    try:
        return _StyledIKB(text, style=style, **kwargs)
    except Exception:
        try:
            return InlineKeyboardButton(text, **kwargs)
        except Exception:
            return InlineKeyboardButton(text, callback_data=kwargs.get('callback_data', 'noop'))

from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, Defaults, ExtBot
)

os.makedirs("bot", exist_ok=True)

# ── Premium Emoji Map (emoji char → ID) — use pe("⚡") anywhere ─────────────
PREMIUM_EMOJI = {
    "⚡":   "5399934661818359384",
    "🔄":   "5373310679241466020",
    "⚙️":   "5787672468076367185",
    "⭐":   "6242413641052722528",
    "👤":   "5373012449597335010",
    "💘":   "6266818250818983044",
    "🎁":   "6129497211379129336",
    "➿":   "6329854094252970694",
    "➖":   "6307665627481903641",
    "💎":   "6123070651814124726",
    "🌀":   "5913534466051021148",
    "☄️":   "6339024429250515243",
    "🥇":   "6265004494719816749",
    "📞":   "6282996898701775483",
    "👑":   "6242406378263025026",
    "🔥":   "6307636391639519250",
    "❤️":   "5406926593698312391",
    "✅":   "6071022434234930063",
    "❌":   "6105179944067798549",
    "💀":   "5960961797035922820",
    "📊":   "5431577498364158238",
    "📢":   "5197304993920616826",
    "👥":   "5301276827782755360",
    "🆔":   "5888781182249738113",
    "📅":   "5413879192267805083",
    "💰":   "6267068789146260253",
    "🪙":   "5366223171454278937",
    "🎉":   "6242389503336518600",
    "🎮":   "6070964971867477673",
    "🛡️":   "6170491132326188067",
    "🔍":   "5258274739041883702",
    "📌":   "5258361175258712272",
    "🎯":   "5463274047771000031",
    "🎫":   "5418010521309815154",
    "📛":   "5407091670766343316",
    "🌎":   "5397575638146110953",
    "👋":   "6276133811545706331",
    "🚪":   "6035130900075777681",
    "🔔":   "6264510702329797113",
    "🔕":   "5244807637157029775",
    "📱":   "5465169893580086142",
    "📸":   "6305331119482999807",
    "💣":   "5454225015534805938",
    "🪪":   "6030753228889526497",
    "🟢":   "6120953301656670791",
    "🔴":   "6122945749870187150",
    "⏳":   "5451732530048802485",
    "⏰":   "5413704112220949842",
    "⏱️":   "6179440452601647526",
    "💬":   "5409496608287634515",
    "🔗":   "5431695342289379366",
    "🔒":   "6195245116207143870",
    "🎥":   "5449600639283619330",
    "🖼️":   "5334759607939040793",
    "👇":   "5301038027601098171",
    "💡":   "5219745609631674840",
    "🔙":   "5471937446368975982",
    "👆":   "5373091747827689552",
    "👨‍💻": "4958900559139570572",
    "🧩":   "5188052560342545947",
    "🎀":   "5219745609631674840",
    "💸":   "5253804796589402657",
    "🏅":   "5415727875041021959",
    "🤝":   "5445261194662391481",
    "🔐":   "5472308992514464048",
    "📧":   "6046310987710078440",
    "📡":   "5399934661818359384",
    "🏠":   "5465226866321268133",
    "😎":   "6123091160282964016",
    "⚠️":   "5278211596656639183",
    "📤":   "5197304993920616826",
    "📋":   "6034969813032374911",
    "🔵":   "6330188813939251966",
    "🤖":   "6070964971867477673",
    "🗣️":   "5406705252558724532",
    "🟥":   "6330022375366598950",
    "📍":   "5258361175258712272",
    "💠":   "4960766907113276588",
    "💍":   "6129913342170506824",
    "🔓":   "5890882606668452641",
    "🙂":   "6129440444796378483",
    "👉":   "5465467698022468218",
    "➕":   "6257944590687410044",
    "👁":   "6159021800119341504",
    "🗑️":   "6129486856212979482",
    "🔑":   "5472308992514464048",
    "📄":   "6034969813032374911",
    "⚜":   "6181649972757271368",
    "🩶":   "5789607097440147328",
    "🍾":   "5798459514663473705",
    "✉️":   "5929312878816400493",
    # Extended — buttons & messages (confirmed from reference)
    "🌏":   "6178984829585986541",
    "👨":   "5373012449597335010",
    "▶":    "6323282781405190847",
    "▶️":   "6323282781405190847",
    "◀":    "6323282781405190847",
    "◀️":   "6323282781405190847",
    "🗺":   "6303001048185309018",
    "🗺️":   "6303001048185309018",
    "🎓":   "5357419403325481346",
    "💼":   "5348227245599105972",
    "🌐":   "6075739493736915024",
    "🚗":   "5312322066328853156",
    "🚘":   "5312322066328853156",
    "📝":   "5409496608287634515",
    "⬇":    "6129694470637100146",
    "⬇️":   "6129694470637100146",
    "🌟":   "6147565374289220368",
    "👾":   "5303396278179210513",
    "🛒":   "5780824606579364273",
    "📮":   "5287533898803211359",
    "🌍":   "6329854094252970694",
    "🎨":   "5415727875041021959",
    "🚀":   "6158836197402615172",
    "🗑":   "6158751479172702139",
    "🎙":   "5377544228505134960",
    "🎙️":   "5377544228505134960",
    "🇮🇳":  "5447419223242449630",
    # ── Weather ──────────────────────────────────────────────────────────────
    "⛅":   "6178984829585986541",
    "⛅️":   "6178984829585986541",
    "🌤":   "6178984829585986541",
    "🌤️":   "6178984829585986541",
    "🌥":   "6178984829585986541",
    "🌥️":   "6178984829585986541",
    "🌦":   "6178984829585986541",
    "🌦️":   "6178984829585986541",
    "🌧":   "6178984829585986541",
    "🌧️":   "6178984829585986541",
    "🌨":   "6178984829585986541",
    "🌨️":   "6178984829585986541",
    "🌩":   "6178984829585986541",
    "🌩️":   "6178984829585986541",
    "⛈":   "6178984829585986541",
    "⛈️":   "6178984829585986541",
    "☁":   "6178984829585986541",
    "☁️":   "6178984829585986541",
    "☀":   "6147565374289220368",
    "☀️":   "6147565374289220368",
    "🌞":   "6147565374289220368",
    "🌈":   "6147565374289220368",
    "❄":   "6271523694617243479",
    "❄️":   "6271523694617243479",
    "🌊":   "6178984829585986541",
    "🌋":   "6178984829585986541",
    "🌌":   "6178984829585986541",
    "🌠":   "6147565374289220368",
    "🌃":   "6178984829585986541",
    "🌁":   "6178984829585986541",
    "🌄":   "6178984829585986541",
    "🌅":   "6178984829585986541",
    "🌆":   "5415727875041021959",
    "🌇":   "5242564946968992534",
    "🌉":   "5041882544228795301",
    "🌙":   "5415727875041021959",
    # ── Music / Audio ────────────────────────────────────────────────────────
    "🎵":   "5377544228505134960",
    "🎶":   "5377544228505134960",
    "🎧":   "5377544228505134960",
    "🎸":   "5377544228505134960",
    "🎷":   "5377544228505134960",
    "🎺":   "5377544228505134960",
    "🎻":   "5377544228505134960",
    "🎹":   "5377544228505134960",
    "🥁":   "5377544228505134960",
    "🎼":   "5377544228505134960",
    "📻":   "5377544228505134960",
    "💿":   "5258274739041883702",
    "📀":   "5258274739041883702",
    "🔊":   "6105179944067798549",
    "🔉":   "6105179944067798549",
    "🔈":   "6105179944067798549",
    "🔇":   "6105179944067798549",
    # ── Gaming / Tech ────────────────────────────────────────────────────────
    "🕹":   "5303396278179210513",
    "🕹️":   "5303396278179210513",
    "🖥":   "5415727875041021959",
    "🖥️":   "5415727875041021959",
    "📺":   "5415727875041021959",
    "📷":   "5258274739041883702",
    "📸":   "5258274739041883702",
    "📹":   "5258274739041883702",
    # ── Storage / Files ──────────────────────────────────────────────────────
    "🗄":   "5258274739041883702",
    "🗄️":   "5258274739041883702",
    "💾":   "5258274739041883702",
    "📦":   "5258274739041883702",
    # ── Tools / Craft ────────────────────────────────────────────────────────
    "⛏":   "5215441850537618106",
    "⛏️":   "5215441850537618106",
    "🔧":   "5215441850537618106",
    "🔨":   "5215441850537618106",
    # ── People / Family ──────────────────────────────────────────────────────
    "👪":   "5373012449597335010",
    "👨‍👩‍👧": "5373012449597335010",
    "👨‍👩‍👦": "5373012449597335010",
    "👨‍👩‍👧‍👦": "5373012449597335010",
    "👩":   "5373012449597335010",
    "👧":   "5373012449597335010",
    "👦":   "5373012449597335010",
    "🧑":   "5373012449597335010",
    # ── Nature / Moon ────────────────────────────────────────────────────────
    "🌚":   "5415727875041021959",
    "🌑":   "5415727875041021959",
    "🌒":   "5415727875041021959",
    "🌓":   "5415727875041021959",
    "🌔":   "5415727875041021959",
    "🌕":   "6147565374289220368",
    "🌖":   "5415727875041021959",
    "🌗":   "5415727875041021959",
    "🌘":   "5415727875041021959",
    "🌛":   "5415727875041021959",
    "🌜":   "5415727875041021959",
    # ── ID / License ─────────────────────────────────────────────────────────
    "🪪":   "5422388085121885096",
    # ── Video / Media ────────────────────────────────────────────────────────
    "🎞":   "5258274739041883702",
    "🎞️":   "5258274739041883702",
    "🎬":   "5258274739041883702",
    "🎥":   "5258274739041883702",
    # ── Misc visual ──────────────────────────────────────────────────────────
    "🧊":   "6271523694617243479",
    "🌟":   "6147565374289220368",
    "⭐":   "6147565374289220368",
    "✨":   "6147565374289220368",
    "💥":   "6147565374289220368",
    "🔥":   "6257944590687410044",
    "💧":   "6178984829585986541",
    "💨":   "6178984829585986541",
    "🌿":   "6178984829585986541",
    # ── Colours / Hearts ─────────────────────────────────────────────────────
    "💚":   "5789607097440147328",
    "💛":   "5789607097440147328",
    "🧡":   "5789607097440147328",
    "💜":   "5789607097440147328",
    "🖤":   "5789607097440147328",
    "🤍":   "5789607097440147328",
    "🤎":   "5789607097440147328",
    "💙":   "5789607097440147328",
    "❤":   "5789607097440147328",
    "❤️":   "5789607097440147328",
    # ── Navigation symbols ───────────────────────────────────────────────────
    "🔄":   "5377544228505134960",
    "🔃":   "5377544228505134960",
    "🔁":   "5377544228505134960",
    "🔂":   "5377544228505134960",
    "⏩":   "6323282781405190847",
    "⏪":   "6323282781405190847",
    "⏫":   "6129694470637100146",
    "⏬":   "6129694470637100146",
    "⏯":   "6323282781405190847",
    "🔛":   "6323282781405190847",
    "🔜":   "6323282781405190847",
    "🔚":   "6323282781405190847",
    "🔝":   "6129694470637100146",
    "🔙":   "6323282781405190847",
    # ── Buildings / Places ───────────────────────────────────────────────────
    "🏠":   "5465226866321268133",
    "🏡":   "5465226866321268133",
    "🏘":   "5465226866321268133",
    "🏗":   "5415727875041021959",
    "🏢":   "5217822164362739968",
    "🛸":   "6158836197402615172",
    "🗣":   "5406705252558724532",
    "🗣️":   "5406705252558724532",
    "🔎":   "5258274739041883702",
    "🔍":   "5258274739041883702",
    "📧":   "5303416490295304868",
    "⚡":   "6257790126483578242",
    "🖌":   "5415727875041021959",
    "🖌️":   "5415727875041021959",
    "🔌":   "5215441850537618106",
    "📌":   "5287533898803211359",
    "📍":   "5287533898803211359",
    "🏆":   "5357419403325481346",
    "🥇":   "5357419403325481346",
    "🎯":   "5472308992514464048",
    "🎲":   "5303396278179210513",
    "🎮":   "5303396278179210513",
    "🧩":   "5303396278179210513",
    "💳":   "5224257782013769471",
    "💰":   "5224257782013769471",
    "💎":   "6034969813032374911",
    "👑":   "6034969813032374911",
    "🎁":   "5798459514663473705",
    "🎉":   "5798459514663473705",
    "🪄":   "5472308992514464048",
}

def pe(emoji: str, fallback: str = None) -> str:
    """Return premium tg-emoji HTML by plain emoji char.
    Usage: pe('⚡')  pe('✅', 'OK')
    Falls back to plain emoji if no mapping found."""
    eid = PREMIUM_EMOJI.get(emoji)
    fb = fallback if fallback is not None else emoji
    if not eid:
        return fb
    return f"<tg-emoji emoji-id='{eid}'>{fb}</tg-emoji>"

_BARE_EMOJI_RE = re.compile(
    r'[\U0001F000-\U0001FFFF'
    r'\U00002194-\U000027BF'    # Arrows (↩↪), Misc Technical, Dingbats, Enclosed Alphanum
    r'\U00002900-\U00002BFF'
    r'\u3030\u303D\u3297\u3299'
    r'\uFE00-\uFE0F'
    r'\u20E3'
    r'\U0001F1E0-\U0001F1FF'    # Regional Indicator letters (flags)
    r']+',
    re.UNICODE
)

def _pe_all(text: str) -> str:
    """Replace every plain emoji with its premium tg-emoji version.
    Emojis NOT in PREMIUM_EMOJI are stripped so no plain emoji leaks through."""
    if not text:
        return text
    parts = re.split(r'(<tg-emoji[^>]*>.*?</tg-emoji>)', str(text), flags=re.DOTALL)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(part)
        else:
            for emoji, eid in PREMIUM_EMOJI.items():
                if emoji in part:
                    part = part.replace(
                        emoji, f"<tg-emoji emoji-id='{eid}'>{emoji}</tg-emoji>"
                    )
            sub_parts = re.split(r'(<tg-emoji[^>]*>.*?</tg-emoji>)', part, flags=re.DOTALL)
            cleaned = []
            for j, sub in enumerate(sub_parts):
                if j % 2 == 1:
                    cleaned.append(sub)
                else:
                    cleaned.append(_BARE_EMOJI_RE.sub('', sub))
            out.append(''.join(cleaned))
    return ''.join(out)

def _strip_btn_emoji(text: str) -> str:
    """Remove plain emoji chars from button text that have no premium mapping."""
    src = PREMIUM_EMOJI if 'PREMIUM_EMOJI' in globals() else _BTN_EMOJI_IDS
    saved, work = {}, text
    for idx, emoji_char in enumerate(src):
        if emoji_char in work:
            ph = f'\x00{idx}\x00'
            work = work.replace(emoji_char, ph)
            saved[ph] = emoji_char
    work = _BARE_EMOJI_RE.sub('', work)
    for ph, emoji_char in saved.items():
        work = work.replace(ph, emoji_char)
    return work

# ── Text Style Helpers ────────────────────────────────────────────────────────
def _sc_cap(text: str) -> str:
    """Bold first letter of each word, rest smallcaps — e.g. '𝐔ꜱᴀɢᴇ' style."""
    if not text: return text
    _SC_REV = {
        'ᴀ':'A','ʙ':'B','ᴄ':'C','ᴅ':'D','ᴇ':'E','ꜰ':'F','ɢ':'G','ʜ':'H','ɪ':'I','ᴊ':'J',
        'ᴋ':'K','ʟ':'L','ᴍ':'M','ɴ':'N','ᴏ':'O','ᴩ':'P','ʀ':'R','ꜱ':'S','ᴛ':'T',
        'ᴜ':'U','ᴠ':'V','ᴡ':'W','ʏ':'Y','ᴢ':'Z',
    }
    _BOLD = {
        'A':'𝐀','B':'𝐁','C':'𝐂','D':'𝐃','E':'𝐄','F':'𝐅','G':'𝐆','H':'𝐇','I':'𝐈','J':'𝐉',
        'K':'𝐊','L':'𝐋','M':'𝐌','N':'𝐍','O':'𝐎','P':'𝐏','Q':'𝐐','R':'𝐑','S':'𝐒','T':'𝐓',
        'U':'𝐔','V':'𝐕','W':'𝐖','X':'𝐗','Y':'𝐘','Z':'𝐙',
    }
    result, cap_next = [], True
    for ch in text:
        if ch == ' ':
            result.append(ch); cap_next = True
        elif cap_next:
            plain = _SC_REV.get(ch, ch.upper() if ch.isalpha() else None)
            if plain and plain in _BOLD:
                result.append(_BOLD[plain])
            else:
                result.append(ch)
            cap_next = False
        else:
            result.append(ch)
    return ''.join(result)

CONTROLLER_TOKEN  = os.getenv("CONTROLLER_TOKEN", "8999526361:AAHiHkjpP5QNxHwX6hm6vd6LmGMyhnyUNmg")
OWNER_ID          = os.getenv("OWNER_ID",         "8600328303")
MAIN_BOT_SCRIPT   = "main.py"

FEATURES_FILE     = "bot/features.json"
CONFIG_FILE       = "bot/config.json"
USER_FILE         = "bot/user.json"
CODES_FILE        = "bot/codes.json"
GROUPS_FILE       = "bot/groups.json"
LOG_FILE          = "bot/shuvo.log"
PID_FILE          = "bot/.main_pid"
PAUSE_FILE        = "bot/.paused"
CTRL_BANNER_FILE  = "bot/controller_banner.png"

_DEFAULT_PASS_HASH = hashlib.sha256("asraful123".encode()).hexdigest()

_authenticated: set = set()

FEATURES = {
    "ai_chat":     "🤖 AI Chat",
    "daily_claim": "<tg-emoji emoji-id='5262889711466193287'>🎁</tg-emoji> Daily Claim",
    "redeem":      "🎫 Redeem Code",
    "voice":       "🎙️ Voice TTS",
    "imagegen":    "🌈 Image Gen",
    "music":       "🎧 Music Gen",
    "videogen":    "🎞️ Video Gen",
    "sprite":      "👾 Sprite Gen",
    "model3d":     "🧊 3D Model",
    "editimage":   "🖌️ Edit Image",
    "tgid":        "<tg-emoji emoji-id='5465169893580086142'>⭐</tg-emoji> TG ID→Num",
    "tguser":      "🔍 User→Num",
    "indinfo":     "<tg-emoji emoji-id='5465169893580086142'>⭐</tg-emoji> IND Info",
    "instainfo":   "📸 Instagram",
    "viddown":     "🎬 Vid Download",
    "pincode":     "📮 Pincode",
    "ifsc":        "🏦 IFSC",
    "ipinfo":      "🌐 IP Info",
    "ffstats":     "🎯 FF Stats",
    "emailrep":    "📧 Email Check",
    "vehicle":     "🚗 Vehicle",
    "weather":     "⛅ Weather",
    "nasa":        "🚀 NASA",
    "aadhar":      "🪪 Aadhar",
    "gst":         "💼 GST",
    "pan":         "🪪 PAN",
    "paknum":      "🇵🇰 Pak Num",
    "vehicle_rc":  "🚗 Vehicle RC",
    "upi":         "💳 UPI Info",
    "bypass":      "🔗 Link Bypass",
}


def is_owner(uid):
    return str(uid) == str(OWNER_ID)

def is_authed(uid):
    return str(uid) in _authenticated

def get_pass_hash() -> str:
    cfg = load_config()
    return cfg.get("controller_pass_hash", _DEFAULT_PASS_HASH)

def set_pass_hash(new_hash: str):
    cfg = load_config()
    cfg["controller_pass_hash"] = new_hash
    save_config(cfg)

def check_pass(text: str) -> bool:
    return hashlib.sha256(text.strip().encode()).hexdigest() == get_pass_hash()

def load_users():
    try:
        with open(USER_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_users(data):
    os.makedirs("bot", exist_ok=True)
    with open(USER_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_codes():
    try:
        with open(CODES_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_codes(data):
    os.makedirs("bot", exist_ok=True)
    with open(CODES_FILE, "w") as f:
        json.dump(data, f, indent=2)

def esc(t):
    return str(t).replace("&","&").replace("<","<").replace(">",">")


def load_features():
    os.makedirs("bot", exist_ok=True)
    try:
        with open(FEATURES_FILE) as f:
            data = json.load(f)
    except Exception:
        data = {}
    for k in FEATURES:
        if k not in data:
            data[k] = True
    return data

def save_features(data):
    os.makedirs("bot", exist_ok=True)
    with open(FEATURES_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(data):
    os.makedirs("bot", exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_groups():
    try:
        with open(GROUPS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def parse_channel_link(link: str) -> str:
    link = link.strip()
    if "t.me/" in link:
        part = link.split("t.me/")[-1].strip("/").split("?")[0]
        if part.startswith("+") or part.lower().startswith("joinchat"):
            return link
        return "@" + part
    elif link.startswith("@"):
        return link
    elif link.startswith("-") or link.lstrip("-").isdigit():
        return link
    else:
        return "@" + link.lstrip("@")

MAX_CHANNELS       = 5
MAX_ALLOWED_GROUPS = 10

def allowed_groups_panel_text():
    cfg    = load_config()
    groups = cfg.get("allowed_groups", [])
    count  = len(groups)
    if not groups:
        return (
            f"🏘 Allowed Groups\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            f"📊 Status : 🔓 OFF — Bot works in ALL chats\n\n"
            f"No groups set. Bot is accessible everywhere.\n\n"
            f"Tap ➕ Add Group to restrict the bot to\n"
            f"specific groups only. Outside those groups,\n"
            f"users will see a 'Join Group' message."
        )
    lines  = "\n".join(
        f"  {i+1}. {g['title']}  »  {g.get('username', g.get('chat_id','?'))}"
        for i, g in enumerate(groups)
    )
    return (
        f"🏘 Allowed Groups\n"
        f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
        f"📊 Status : 🔒 ON — Restricted to {count} group(s)\n\n"
        f"Allowed Groups:\n"
        f"{lines}\n\n"
        f"⚠️ Bot only responds inside these groups.\n"
        f"Others see a redirect message."
    )

def allowed_groups_keyboard():
    cfg    = load_config()
    groups = cfg.get("allowed_groups", [])
    count  = len(groups)
    rows   = []
    for i, g in enumerate(groups):
        label = g["title"][:24]
        rows.append([SBtn(f"🗑 Remove  {i+1}. {label}", style="danger", callback_data=f"c_remove_ag_{i}")])
    if count < MAX_ALLOWED_GROUPS:
        rows.append([SBtn("➕ Add Allowed Group", style="success", callback_data="c_add_allowedgroup")])
    else:
        rows.append([SBtn(f"🚫 Max {MAX_ALLOWED_GROUPS} reached", style="danger", callback_data="c_allowedgroups")])
    rows.append([
        SBtn(f"📊 Total: {count}/{MAX_ALLOWED_GROUPS}", style="primary", callback_data="c_allowedgroups"),
        SBtn("🔁 Refresh", style="primary", callback_data="c_allowedgroups"),
    ])
    rows.append([SBtn("🏠 Home", style="primary", callback_data="c_home")])
    return InlineKeyboardMarkup(rows)

def channels_panel_text():
    cfg      = load_config()
    channels = cfg.get("required_channels", [])
    count    = len(channels)
    if not channels:
        return (
            f"📢 Force Join Manager\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            f"📊 Total Added : 0 / {MAX_CHANNELS}\n\n"
            f"No channels or groups added yet.\n"
            f"Users can freely use the bot.\n\n"
            f"Tap ➕ Add to require membership.\n"
            f"You can add up to {MAX_CHANNELS} channels/groups."
        )
    lines = "\n".join(
        f"  {i+1}. {ch['title']}  »  {ch['username']}"
        for i, ch in enumerate(channels)
    )
    status = "🔴 Limit reached!" if count >= MAX_CHANNELS else f"🟢 {MAX_CHANNELS - count} slot(s) remaining"
    return (
        f"📢 Force Join Manager\n"
        f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
        f"📊 Total Added : {count} / {MAX_CHANNELS}  —  {status}\n\n"
        f"Required Channels/Groups:\n"
        f"{lines}\n\n"
        f"⚠️ Users must join all of these before using the bot."
    )

def channels_keyboard():
    cfg      = load_config()
    channels = cfg.get("required_channels", [])
    count    = len(channels)
    rows     = []
    for i, ch in enumerate(channels):
        label = ch['title'][:24]
        rows.append([SBtn(f"🗑 Remove  {i+1}. {label}", style="danger", callback_data=f"c_remove_ch_{i}")])
    if count < MAX_CHANNELS:
        rows.append([SBtn("➕ Add Channel / Group", style="success", callback_data="c_add_channel")])
    else:
        rows.append([SBtn(f"🚫 Max {MAX_CHANNELS} reached — Remove one to add", style="danger", callback_data="c_channels")])
    rows.append([
        SBtn(f"📊 Total: {count}/{MAX_CHANNELS}", style="primary", callback_data="c_channels"),
        SBtn("🔁 Refresh", style="primary",                         callback_data="c_channels"),
    ])
    rows.append([SBtn("🏠 Home", style="primary", callback_data="c_home")])
    return InlineKeyboardMarkup(rows)

def userlogs_panel_text():
    cfg = load_config()
    log_grp = cfg.get("log_group_id")
    if not log_grp:
        return (
            "📝 User Logs System\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            "📴 Status : Disabled\n\n"
            "When enabled, every message users send to the bot\n"
            "will be logged to your chosen group, with a\n"
            "💬 DM button to reply directly to any user.\n\n"
            "Tap ➕ Set Log Group to activate."
        )
    return (
        f"📝 User Logs System\n"
        f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
        f"🟢 Status    : Active\n"
        f"📨 Log Group : {log_grp}\n\n"
        f"All user messages & commands are being logged.\n"
        f"Use the 💬 DM button in any log entry to\n"
        f"send a message directly to that user."
    )


def userlogs_keyboard():
    cfg = load_config()
    log_grp = cfg.get("log_group_id")
    rows = []
    if log_grp:
        rows.append([SBtn("🗑 Remove Log Group", style="danger", callback_data="c_clear_loggroup")])
    else:
        rows.append([SBtn("➕ Set Log Group", style="success",    callback_data="c_set_loggroup")])
    rows.append([
        SBtn("🔁 Refresh", style="primary", callback_data="c_userlogs"),
        SBtn("🏠 Home", style="primary",    callback_data="c_home"),
    ])
    return InlineKeyboardMarkup(rows)


# ─────────────────── BOT GROUPS ───────────────────

def bot_groups_panel_text():
    groups = load_groups()
    cfg    = load_config()
    auto   = cfg.get("autoapprove_chats", [])
    if not groups:
        return (
            "🤖 Bot Groups\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            "📭 Bot is not in any group yet.\n\n"
            "Add the bot to a group and it will appear here automatically."
        )
    lines = [
        f"🤖 Bot Groups\n"
        f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
        f"📊 Total groups: {len(groups)}\n\n"
    ]
    for i, g in enumerate(groups.values(), 1):
        title      = g.get("title", "Unknown")
        link       = g.get("invite_link") or g.get("username") or "No link"
        is_admin   = "<tg-emoji emoji-id='6253517256794311831'>😎</tg-emoji> Admin" if g.get("is_admin") else "👤 Member"
        gtype      = g.get("type", "group")
        aa_icon    = "✅" if str(g.get("id","")) in [str(x) for x in auto] else "❌"
        lines.append(
            f"{i}. {title}\n"
            f"   🔗 {link}\n"
            f"   {is_admin}  •  {gtype}  •  Auto-approve: {aa_icon}\n\n"
        )
    return "".join(lines)


def bot_groups_keyboard():
    groups = load_groups()
    rows   = []
    for g in groups.values():
        title = g.get("title", "Unknown")[:22]
        link  = g.get("invite_link") or g.get("username") or ""
        if link:
            rows.append([InlineKeyboardButton(f"🔗 {title}", url=link)])
    rows.append([
        SBtn("🔁 Refresh", style="primary", callback_data="c_botgroups"),
        SBtn("🏠 Home",    style="primary", callback_data="c_home"),
    ])
    return InlineKeyboardMarkup(rows)


# ─────────────────── USER MANAGER ───────────────────

USERS_PAGE_SIZE = 8

def users_list_text(page=0):
    users  = load_users()
    items  = sorted(users.items(), key=lambda x: x[1].get("first_name","").lower())
    total  = len(items)
    start  = page * USERS_PAGE_SIZE
    chunk  = items[start:start + USERS_PAGE_SIZE]
    lines  = []
    for uid, u in chunk:
        name   = esc(u.get("first_name","") + " " + u.get("last_name","")).strip() or "Unknown"
        uname  = f"@{u.get('username')}" if u.get("username") else "—"
        banned = " 🚫" if u.get("banned") else ""
        admin  = " <tg-emoji emoji-id='6253517256794311831'>😎</tg-emoji>" if u.get("is_admin") else ""
        cr     = u.get("credits", 0)
        lines.append(f"  {uid}  {esc(name)}{admin}{banned}\n"
                     f"  └ {uname}  •  <tg-emoji emoji-id='5224257782013769471'>💰</tg-emoji> {cr} credits")
    body = "\n".join(lines) if lines else "  No users found."
    pages = max(1, (total + USERS_PAGE_SIZE - 1) // USERS_PAGE_SIZE)
    return (
        f"👤 User Manager\n"
        f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
        f"📊 Total: {total}  •  Page {page+1}/{pages}\n\n"
        f"{body}\n\n"
        f"🔍 Tap Search to look up a specific user."
    )

def users_list_keyboard(page=0):
    users  = load_users()
    total  = len(users)
    pages  = max(1, (total + USERS_PAGE_SIZE - 1) // USERS_PAGE_SIZE)
    nav = []
    if page > 0:
        nav.append(SBtn("◀️ Prev", style="primary", callback_data=f"c_users_{page-1}"))
    nav.append(SBtn(f"• {page+1}/{pages} •", style="primary", callback_data="c_noop"))
    if page < pages - 1:
        nav.append(SBtn("Next ▶️", style="primary", callback_data=f"c_users_{page+1}"))
    return InlineKeyboardMarkup([
        nav,
        [SBtn("🔍 Search User", style="primary",  callback_data="c_user_search"),
         SBtn("🔁 Refresh", style="primary",       callback_data=f"c_users_{page}")],
        [SBtn("🏠 Home", style="primary",          callback_data="c_home")],
    ])

def user_profile_text(uid, u):
    name   = esc((u.get("first_name","") + " " + u.get("last_name","")).strip()) or "Unknown"
    uname  = f"@{esc(u.get('username'))}" if u.get("username") else "—"
    cr     = u.get("credits", 0)
    banned = "🚫 Yes" if u.get("banned") else "✅ No"
    admin  = "<tg-emoji emoji-id='6253517256794311831'>😎</tg-emoji> Yes" if u.get("is_admin") else "—"
    joined = esc(u.get("joined_at", "—"))
    last   = esc(u.get("last_seen", "—"))
    return (
        f"👤 User Profile\n"
        f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
        f"🆔 User ID   : {uid}\n"
        f"📛 Name      : {name}\n"
        f"🔗 Username  : {uname}\n"
        f"<tg-emoji emoji-id='5224257782013769471'>💰</tg-emoji> Credits   : {cr:,}\n"
        f"🚫 Banned    : {banned}\n"
        f"<tg-emoji emoji-id='6253517256794311831'>😎</tg-emoji> Admin     : {admin}\n"
        f"📅 Joined    : {joined}\n"
        f"🕐 Last seen : {last}"
    )

def user_profile_keyboard(uid, u):
    ban_btn = (
        SBtn("✅ Unban", style="success",  callback_data=f"c_unban_{uid}")
        if u.get("banned") else
        SBtn("🚫 Ban", style="danger",    callback_data=f"c_ban_{uid}")
    )
    adm_btn = (
        SBtn("😎 Remove Admin", style="danger", callback_data=f"c_deadmin_{uid}")
        if u.get("is_admin") else
        SBtn("😎 Make Admin", style="success",   callback_data=f"c_mkadmin_{uid}")
    )
    return InlineKeyboardMarkup([
        [ban_btn, adm_btn],
        [SBtn("💰 Add Credits", style="success",    callback_data=f"c_addcr_{uid}"),
         SBtn("💸 Remove Credits", style="danger", callback_data=f"c_remcr_{uid}")],
        [SBtn("🗑 Delete User", style="danger",    callback_data=f"c_deluser_{uid}"),
         SBtn("🔁 Refresh", style="primary",        callback_data=f"c_viewuser_{uid}")],
        [SBtn("◀️ Back", style="primary",            callback_data="c_users_0"),
         SBtn("🏠 Home", style="primary",            callback_data="c_home")],
    ])


# ─────────────────── CODE MANAGER ───────────────────

def codes_list_text():
    codes = load_codes()
    if not codes:
        return (
            "🎫 Code Manager\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            "📭 No redeem codes found.\n\n"
            "Tap ➕ Create Code to generate a new one."
        )
    lines = []
    for code, info in list(codes.items())[:20]:
        cr  = info.get("credits", 0)
        lim = info.get("limit", "∞")
        used= info.get("used", 0)
        exp = info.get("expires", "Never")
        lines.append(f"  🎫 {esc(code)}\n"
                     f"  └ <tg-emoji emoji-id='5224257782013769471'>💰</tg-emoji> {cr} cr  •  Used: {used}/{lim}  •  Exp: {esc(exp)}")
    body = "\n".join(lines)
    shown = min(len(codes), 20)
    return (
        f"🎫 Code Manager\n"
        f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
        f"📊 Total Codes: {len(codes)}"
        + (f"  (showing first {shown})" if len(codes) > 20 else "") +
        f"\n\n{body}"
    )

def codes_keyboard():
    codes = load_codes()
    rows  = []
    for code in list(codes.keys())[:8]:
        rows.append([SBtn(
            f"🗑 Delete  {code[:20]}", style="danger", callback_data=f"c_delcode_{code}"
        )])
    rows.append([
        SBtn("➕ Create Code", style="success",  callback_data="c_createcode"),
        SBtn("🗑 Clear All", style="danger",    callback_data="c_clearallcodes"),
    ])
    rows.append([
        SBtn("🔁 Refresh", style="primary",      callback_data="c_codes"),
        SBtn("🏠 Home", style="primary",          callback_data="c_home"),
    ])
    return InlineKeyboardMarkup(rows)


# ─────────────────── DM USER ───────────────────

def dm_user_text():
    return (
        "💬 DM User\n"
        "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
        "Send a private message to any bot user directly.\n\n"
        "Tap ➕ Send DM and enter the User ID first."
    )

def dm_user_keyboard():
    return InlineKeyboardMarkup([
        [SBtn("📤 Send DM", style="success",  callback_data="c_dm_start")],
        [SBtn("🏠 Home", style="primary",     callback_data="c_home")],
    ])


def get_main_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None

def process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def bot_status_line():
    pid    = get_main_pid()
    paused = os.path.exists(PAUSE_FILE)
    if pid and process_alive(pid):
        state = f"🟢 Running  (PID {pid})"
    elif pid:
        state = f"🔴 Dead     (stale PID {pid})"
    else:
        state = "⚪ Unknown  (no PID file)"
    mode = "⏸️ PAUSED" if paused else "▶️ Active"
    return state, mode

def panel_text():
    feats       = load_features()
    on          = sum(1 for v in feats.values() if v)
    tot         = len(feats)
    state, mode = bot_status_line()
    now         = datetime.now().strftime("%d %b  %H:%M:%S")
    cfg         = load_config()
    ch_count    = len(cfg.get("required_channels", []))
    return (
        f"╔<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>╗\n"
        f"   🎛 SHUVO BOT CONTROLLER\n"
        f"╚<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>╝\n\n"
        f""
        f"🤖 Status   ›  {state}\n"
        f"🕹 Mode     ›  {mode}\n"
        f"🔧 Features ›  {on}/{tot} enabled\n"
        f"📢 Force Join ›  {ch_count}/5\n"
        f"🕐 Time     ›  {now}"
        f""
    )

def main_keyboard():
    cfg      = load_config()
    channels = cfg.get("required_channels", [])
    log_grp  = cfg.get("log_group_id")
    n        = len(channels)
    fj_label = f"📢  Force Join  •  {n}/5" if channels else "📢  Force Join"
    ul_label = f"📝  User Logs  •  ON ✅" if log_grp else "📝  User Logs"
    return InlineKeyboardMarkup([
        [SBtn("⚙️  Features",      style="primary",  callback_data="c_feat_0"),
         SBtn("📋  Live Logs",     style="primary",  callback_data="c_logs")],
        [SBtn("📊  Stats",         style="primary",  callback_data="c_stats"),
         SBtn("🔁  Refresh",       style="primary",  callback_data="c_home")],
        [SBtn(fj_label,            style="primary",  callback_data="c_channels"),
         SBtn(ul_label,            style="primary",  callback_data="c_userlogs")],
        [SBtn("👤  User Manager",  style="primary",  callback_data="c_users_0"),
         SBtn("📣  Broadcast",     style="primary",  callback_data="c_broadcast")],
        [SBtn("🎫  Code Manager",  style="primary",  callback_data="c_codes"),
         SBtn("💬  DM User",       style="primary",  callback_data="c_dm_user")],
        [SBtn("🏘  Allowed Groups", style="primary",  callback_data="c_allowedgroups"),
         SBtn("🤖  Bot Groups",    style="primary",  callback_data="c_botgroups")],
        [SBtn("📁  Backup Files",  style="primary",  callback_data="c_backup"),
         SBtn("💰  Reset Credits", style="danger",   callback_data="c_resetcredits")],
        [SBtn("⏸️  Pause Bot",    style="danger",   callback_data="c_pause"),
         SBtn("▶️  Resume Bot",   style="success",  callback_data="c_resume")],
        [SBtn("🔄  Restart Bot",   style="success",  callback_data="c_restart"),
         SBtn("💀  Kill Process",  style="danger",   callback_data="c_kill")],
        [SBtn("⚡  Spawn Process", style="primary",  callback_data="c_spawn"),
         SBtn("🗑  Clear Logs",    style="danger",   callback_data="c_clearlogs")],
        [SBtn("🔑  Change Password", style="primary", callback_data="c_changepass"),
         SBtn("🔒  Logout",         style="danger",   callback_data="c_logout")],
    ])

def features_keyboard(page=0):
    feats      = load_features()
    items      = list(FEATURES.items())
    per        = 8
    start      = page * per
    chunk      = items[start:start + per]
    rows       = []
    for i in range(0, len(chunk), 2):
        row = []
        for key, label in chunk[i:i+2]:
            icon = "✅" if feats.get(key, True) else "❌"
            row.append(SBtn(f"{icon} {label}", style="primary", callback_data=f"cf_{key}"))
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(SBtn("◀️ Prev", style="primary", callback_data=f"c_feat_{page-1}"))
    total_pages = (len(items) + per - 1) // per
    if page < total_pages - 1:
        nav.append(SBtn("Next ▶️", style="primary", callback_data=f"c_feat_{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([
        SBtn("🔛 All ON", style="success",  callback_data="c_allon"),
        SBtn("🔕 All OFF", style="danger", callback_data="c_alloff"),
    ])
    rows.append([SBtn("🏠 Home", style="primary", callback_data="c_home")])
    return InlineKeyboardMarkup(rows)

def feat_panel_text():
    feats = load_features()
    on    = sum(1 for v in feats.values() if v)
    tot   = len(feats)
    return f"🔧 Feature Toggle\n✅ Enabled: {on}/{tot}\n\nTap any feature to toggle it:"


async def _send_banner_panel(target, caption: str, keyboard):
    """Send banner photo + caption. target = update.message or query.message"""
    try:
        if os.path.exists(CTRL_BANNER_FILE):
            with open(CTRL_BANNER_FILE, "rb") as f:
                await target.reply_photo(photo=f, caption=caption,
                                         reply_markup=keyboard)
            return
    except Exception:
        pass
    await target.reply_text(caption, reply_markup=keyboard)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not is_owner(uid):
        try:
            with open(CTRL_BANNER_FILE, "rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption="🚫 Access Denied\n\nThis is a private controller bot."
                )
        except Exception:
            await update.message.reply_text("🚫 Unauthorized.")
        return

    if is_authed(uid):
        await _send_banner_panel(update.message, panel_text(), main_keyboard())
        return

    context.user_data["awaiting_pass"] = True
    login_text = (
        "🔐 SHUVO BOT Controller\n"
        "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
        "<tg-emoji emoji-id='6255570556104477305'>😎</tg-emoji> Owner-only access panel\n"
        "🔑 Enter your password to continue:"
    )
    try:
        if os.path.exists(CTRL_BANNER_FILE):
            with open(CTRL_BANNER_FILE, "rb") as f:
                await update.message.reply_photo(photo=f, caption=login_text)
            return
    except Exception:
        pass
    await update.message.reply_text(login_text)

async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    _authenticated.discard(uid)
    context.user_data["awaiting_pass"] = False
    await update.message.reply_text("🔒 Logged out. Send /start to log in again.")

async def cmd_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not is_owner(uid):
        await update.message.reply_text("🚫 Unauthorized.")
        return

    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        feats = load_features()
        current = "✅ ON" if feats.get("ai_chat", True) else "❌ OFF"
        await update.message.reply_text(
            f"🤖 AI Chat is currently: <b>{current}</b>\n\n"
            f"Usage:\n"
            f"• /ai on — Enable AI Chat\n"
            f"• /ai off — Disable AI Chat"
        )
        return

    action = args[0].lower()
    feats = load_features()
    feats["ai_chat"] = (action == "on")
    save_features(feats)

    if action == "on":
        await update.message.reply_text(
            "✅ <b>AI Chat Enabled!</b>\n\n"
            "Users can now use AI chat in the main bot."
        )
    else:
        await update.message.reply_text(
            "❌ <b>AI Chat Disabled!</b>\n\n"
            "AI chat has been turned off for all users."
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not is_owner(uid):
        return

    text = (update.message.text or "").strip()

    # ── Log Group ID input ──
    if context.user_data.get("awaiting_loggroup"):
        try:
            await update.message.delete()
        except Exception:
            pass
        context.user_data["awaiting_loggroup"] = False
        raw = text.strip()
        if not raw.lstrip("-").isdigit():
            await update.message.reply_text(
                "❌ Invalid Group ID!\n\n"
                "Group IDs are numbers, e.g. -1001234567890\n\n"
                "Try again with ➕ Set Log Group.",
                reply_markup=userlogs_keyboard()
            )
            return
        cfg = load_config()
        cfg["log_group_id"] = raw
        save_config(cfg)
        await update.message.reply_text(
            f"✅ Log Group Set!\n\n"
            f"📨 Group ID: {raw}\n\n"
            f"User logs are now active.\n"
            f"Every message users send to the bot will appear there\n"
            f"with a 💬 DM button to reply directly.",
            reply_markup=userlogs_keyboard()
        )
        return

    # ── Allowed Group input ──
    if context.user_data.get("awaiting_allowedgroup"):
        try:
            await update.message.delete()
        except Exception:
            pass
        context.user_data["awaiting_allowedgroup"] = False
        raw = text.strip()

        if raw.lstrip("-").isdigit():
            chat_id  = raw
            username = ""
            title    = f"Group {chat_id}"
        else:
            username = parse_channel_link(raw)
            chat_id  = ""
            title    = username.lstrip("@") if username.startswith("@") else raw.split("/")[-1]

        cfg    = load_config()
        groups = cfg.get("allowed_groups", [])

        if any(
            (g.get("chat_id") and str(g["chat_id"]) == str(chat_id)) or
            (g.get("username") and g["username"].lower() == username.lower())
            for g in groups
        ):
            await update.message.reply_text(
                "⚠️ Already added!\n\nThis group is already in the allowed list.",
                reply_markup=allowed_groups_keyboard()
            )
            return

        groups.append({"title": title, "username": username, "chat_id": chat_id})
        cfg["allowed_groups"] = groups
        save_config(cfg)
        await update.message.reply_text(
            f"✅ Allowed Group Added!\n\n"
            f"📛 Title : {title}\n"
            f"{'🆔 Chat ID : ' + chat_id if chat_id else '👤 Username : ' + username}\n\n"
            f"Bot will now only respond inside allowed groups.\n"
            f"Outsiders will see a redirect / join message.",
            reply_markup=allowed_groups_keyboard()
        )
        return

    # ── Channel link input ──
    if context.user_data.get("awaiting_channel"):
        try:
            await update.message.delete()
        except Exception:
            pass
        context.user_data["awaiting_channel"] = False

        username = parse_channel_link(text)
        title    = username.lstrip("@") if username.startswith("@") else text.split("/")[-1]

        cfg      = load_config()
        channels = cfg.get("required_channels", [])
        if any(ch["username"].lower() == username.lower() for ch in channels):
            await update.message.reply_text(
                "⚠️ Already added!\n\nThis channel/group is already in the list.",
                reply_markup=channels_keyboard()
            )
            return

        is_private = text.strip().startswith("https://t.me/+") or "joinchat" in text
        context.user_data["pending_channel"] = {"title": title, "link": text, "username": username}

        if is_private:
            context.user_data["awaiting_chatid"] = True
            await update.message.reply_text(
                f"🔒 Private Channel Detected!\n"
                f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
                f"Link: {text}\n\n"
                f"To verify members in a private channel/group,\n"
                f"the bot needs the numeric Chat ID.\n\n"
                f"How to get Chat ID:\n"
                f"┣ Forward a message from the channel to @userinfobot\n"
                f"┗ Or add @RawDataBot to the group\n\n"
                f"📌 Send the Chat ID now (e.g. -1001234567890):\n\n"
                f"Or send /skip to add without ID (join button will show but not be verified):"
            )
            return

        channels.append({"title": title, "link": text, "username": username})
        cfg["required_channels"] = channels
        save_config(cfg)

        await update.message.reply_text(
            f"✅ Added Successfully!\n\n"
            f"📢 {username}\n\n"
            f"Users must now join this to use the bot.",
            reply_markup=channels_keyboard()
        )
        return

    # ── Private channel Chat ID input ──
    if context.user_data.get("awaiting_chatid"):
        try:
            await update.message.delete()
        except Exception:
            pass
        pending = context.user_data.pop("pending_channel", {})
        context.user_data["awaiting_chatid"] = False

        if text.strip().lower() == "/skip" or text.strip().lower() == "skip":
            cfg      = load_config()
            channels = cfg.get("required_channels", [])
            channels.append(pending)
            cfg["required_channels"] = channels
            save_config(cfg)
            await update.message.reply_text(
                f"✅ Added (without Chat ID)\n\n"
                f"⚠️ Join button will show but membership won't be verified.\n"
                f"Add Chat ID later by removing and re-adding the channel.",
                reply_markup=channels_keyboard()
            )
            return

        chat_id_raw = text.strip()
        if not chat_id_raw.lstrip("-").isdigit():
            await update.message.reply_text(
                f"❌ Invalid Chat ID!\n\n"
                f"Chat IDs are numbers like -1001234567890.\n"
                f"Send /skip to add without Chat ID.",
            )
            context.user_data["awaiting_chatid"] = True
            context.user_data["pending_channel"] = pending
            return

        pending["chat_id"] = chat_id_raw
        cfg      = load_config()
        channels = cfg.get("required_channels", [])
        channels.append(pending)
        cfg["required_channels"] = channels
        save_config(cfg)

        await update.message.reply_text(
            f"✅ Private Channel Added!\n\n"
            f"📢 {pending.get('username', pending.get('link', ''))}\n"
            f"🆔 Chat ID: {chat_id_raw}\n\n"
            f"Members will now be verified properly.",
            reply_markup=channels_keyboard()
        )
        return

    # ── User lookup ──
    if context.user_data.get("awaiting_user_lookup"):
        context.user_data["awaiting_user_lookup"] = False
        query_val = text.strip().lstrip("@")
        users = load_users()
        found_uid, found_u = None, None
        if query_val.isdigit():
            found_uid = query_val
            found_u   = users.get(query_val)
        else:
            for u_id, u_data in users.items():
                if (u_data.get("username") or "").lower() == query_val.lower():
                    found_uid, found_u = u_id, u_data
                    break
        if found_u is None:
            await update.message.reply_text(
                f"❌ User not found\n\n{esc(text)}\n\n"
                f"Make sure the user has started the bot.",
                reply_markup=InlineKeyboardMarkup([[SBtn("◀️ Back", style="primary", callback_data="c_users_0")]])
            )
        else:
            await update.message.reply_text(
                user_profile_text(found_uid, found_u),
                reply_markup=user_profile_keyboard(found_uid, found_u)
            )
        return

    # ── Credits input ──
    if context.user_data.get("awaiting_credits_uid"):
        c_uid  = context.user_data.pop("awaiting_credits_uid")
        c_mode = context.user_data.pop("awaiting_credits_mode", "add")
        try:
            amount = int(text.strip())
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid amount!\n\nSend a positive number (e.g. 100)."
            )
            return
        users = load_users()
        if c_uid not in users:
            await update.message.reply_text("❌ User not found.")
            return
        old_cr = users[c_uid].get("credits", 0)
        if c_mode == "add":
            users[c_uid]["credits"] = old_cr + amount
            verb = f"➕ Added {amount} credits"
        else:
            users[c_uid]["credits"] = max(0, old_cr - amount)
            verb = f"➖ Removed {amount} credits"
        save_users(users)
        new_cr = users[c_uid]["credits"]
        await update.message.reply_text(
            f"<tg-emoji emoji-id='5224257782013769471'>💰</tg-emoji> Credits Updated!\n\n"
            f"User: {c_uid}\n"
            f"{verb}\n"
            f"Before: {old_cr:,}  →  After: {new_cr:,}",
            reply_markup=user_profile_keyboard(c_uid, users[c_uid])
        )
        return

    # ── Delete user confirmation ──
    if context.user_data.get("awaiting_confirm_deluser"):
        target_uid = context.user_data.pop("awaiting_confirm_deluser")
        if text.strip() == "CONFIRM":
            users = load_users()
            users.pop(target_uid, None)
            save_users(users)
            await update.message.reply_text(
                f"🗑 User Deleted!\n\nUser {target_uid} has been removed.",
                reply_markup=InlineKeyboardMarkup([
                    [SBtn("👤 User Manager", style="primary", callback_data="c_users_0"),
                     SBtn("🏠 Home", style="primary",         callback_data="c_home")],
                ])
            )
        else:
            await update.message.reply_text(
                "❌ Cancelled. Type CONFIRM exactly to delete, or go back.",
                reply_markup=InlineKeyboardMarkup([[SBtn("◀️ Back", style="primary", callback_data="c_users_0")]])
            )
        return

    # ── Broadcast — supports text, photo, sticker, video, voice, doc ──
    if context.user_data.get("awaiting_broadcast"):
        context.user_data["awaiting_broadcast"] = False
        users    = load_users()
        total    = len(users)
        success  = 0
        fail     = 0
        from_chat  = update.message.chat_id
        src_msg_id = update.message.message_id
        prog_msg = await update.message.reply_text(
            f"📣 Broadcasting…\n\n0 / {total} sent…"
        )
        for i, u_id in enumerate(users):
            try:
                await context.bot.copy_message(
                    chat_id=int(u_id),
                    from_chat_id=from_chat,
                    message_id=src_msg_id
                )
                success += 1
            except Exception:
                fail += 1
            if (i + 1) % 20 == 0:
                try:
                    await prog_msg.edit_text(
                        f"📣 Broadcasting…\n\n{i+1} / {total} sent…"
                    )
                except Exception:
                    pass
        await prog_msg.edit_text(
            f"✅ Broadcast Complete!\n\n"
            f"📊 Sent : {success}\n"
            f"❌ Failed: {fail}\n"
            f"👥 Total : {total}",
            reply_markup=InlineKeyboardMarkup([[SBtn("🏠 Home", style="primary", callback_data="c_home")]])
        )
        return

    # ── DM User — step 1: get UID ──
    if context.user_data.get("awaiting_dm_uid"):
        context.user_data["awaiting_dm_uid"] = False
        dm_target = text.strip()
        if not dm_target.isdigit():
            await update.message.reply_text(
                "❌ Invalid User ID!\n\nUser IDs are numbers only (e.g. 123456789)."
            )
            return
        context.user_data["awaiting_dm_msg"] = dm_target
        await update.message.reply_text(
            f"💬 DM User\n\n"
            f"Target: {dm_target}\n\n"
            f"Now send the message you want to send to this user:"
        )
        return

    # ── DM User — step 2: send message ──
    if context.user_data.get("awaiting_dm_msg"):
        dm_target = context.user_data.pop("awaiting_dm_msg")
        try:
            await context.bot.send_message(
                chat_id=int(dm_target),
                text=f"💬 Message from Bot Owner\n<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n{text}"
            )
            await update.message.reply_text(
                f"✅ Message Sent!\n\nDelivered to user {dm_target}.",
                reply_markup=InlineKeyboardMarkup([
                    [SBtn("💬 Send Another", style="success", callback_data="c_dm_start"),
                     SBtn("🏠 Home", style="primary",          callback_data="c_home")],
                ])
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Failed to send!\n\nUser {dm_target} may have blocked the bot.\n\nError: {esc(str(e))}",
                reply_markup=InlineKeyboardMarkup([[SBtn("🏠 Home", style="primary", callback_data="c_home")]])
            )
        return

    # ── Code Create — multi-step ──
    if context.user_data.get("awaiting_code_create"):
        step = context.user_data.get("code_create_step", "credits")

        if step == "credits":
            try:
                cr = int(text.strip())
                if cr <= 0: raise ValueError
            except ValueError:
                await update.message.reply_text("❌ Send a positive number for credits (e.g. 100).")
                return
            context.user_data["code_create_credits"] = cr
            context.user_data["code_create_step"]    = "limit"
            await update.message.reply_text(
                f"🎫 Create Code — Step 2/3\n\n"
                f"Credits: {cr}\n\n"
                f"How many times can this code be used?\n"
                f"📌 Send a number, or 0 for unlimited:"
            )

        elif step == "limit":
            try:
                lim = int(text.strip())
                if lim < 0: raise ValueError
            except ValueError:
                await update.message.reply_text("❌ Send 0 for unlimited, or a positive number.")
                return
            context.user_data["code_create_limit"] = lim
            context.user_data["code_create_step"]  = "code"
            await update.message.reply_text(
                f"🎫 Create Code — Step 3/3\n\n"
                f"Credits: {context.user_data['code_create_credits']}\n"
                f"Limit  : {'Unlimited' if lim == 0 else lim}\n\n"
                f"Send the code text, or send AUTO to generate one automatically:"
            )

        elif step == "code":
            cr  = context.user_data.pop("code_create_credits", 0)
            lim = context.user_data.pop("code_create_limit", 0)
            context.user_data.pop("awaiting_code_create", None)
            context.user_data.pop("code_create_step", None)

            if text.strip().upper() == "AUTO":
                code_text = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
            else:
                code_text = text.strip().upper()

            codes = load_codes()
            if code_text in codes:
                await update.message.reply_text(
                    f"❌ Code {esc(code_text)} already exists!\n\nTry a different name."
                )
                return
            codes[code_text] = {
                "credits": cr,
                "limit":   lim if lim > 0 else "unlimited",
                "used":    0,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            save_codes(codes)
            await update.message.reply_text(
                f"✅ Code Created!\n\n"
                f"🎫 Code    : {esc(code_text)}\n"
                f"<tg-emoji emoji-id='5224257782013769471'>💰</tg-emoji> Credits : {cr}\n"
                f"<tg-emoji emoji-id='5465169893580086142'>⭐</tg-emoji> Limit   : {'Unlimited' if lim == 0 else lim}\n\n"
                f"Users can redeem it with /redeem {esc(code_text)}",
                reply_markup=codes_keyboard()
            )
        return

    # ── Reset All Credits confirmation ──
    if context.user_data.get("awaiting_confirm_resetcredits"):
        context.user_data.pop("awaiting_confirm_resetcredits")
        if text.strip() == "CONFIRM":
            users = load_users()
            count = 0
            for u in users.values():
                if not u.get("is_admin"):
                    u["credits"] = 0
                    u["last_claim"] = None
                    u["force_join_passed"] = False
                    count += 1
            save_users(users)
            await update.message.reply_text(
                f"✅ Full Reset Done!\n\n"
                f"<tg-emoji emoji-id='5224257782013769471'>💰</tg-emoji> Credits → 0\n"
                f"📅 Daily claim → Reset (can claim again)\n"
                f"✅ Affected: {count} users\n"
                f"<tg-emoji emoji-id='6253517256794311831'>😎</tg-emoji> Admins were skipped.",
                reply_markup=InlineKeyboardMarkup([[SBtn("🏠 Home", style="primary", callback_data="c_home")]])
            )
        else:
            await update.message.reply_text(
                "❌ Cancelled. Type CONFIRM exactly to reset, or go back.",
                reply_markup=InlineKeyboardMarkup([[SBtn("🏠 Home", style="primary", callback_data="c_home")]])
            )
        return

    # ── Clear all codes confirmation ──
    if context.user_data.get("awaiting_confirm_clearall"):
        context.user_data.pop("awaiting_confirm_clearall")
        if text.strip() == "CONFIRM":
            save_codes({})
            await update.message.reply_text(
                "🗑 All Codes Cleared!\n\nAll redeem codes have been deleted.",
                reply_markup=InlineKeyboardMarkup([[SBtn("🏠 Home", style="primary", callback_data="c_home")]])
            )
        else:
            await update.message.reply_text(
                "❌ Cancelled. Type CONFIRM exactly to clear.",
                reply_markup=codes_keyboard()
            )
        return

    # ── Change Password — step 1: new password ──
    if context.user_data.get("awaiting_new_pass"):
        context.user_data["awaiting_new_pass"]    = False
        context.user_data["awaiting_confirm_pass"] = True
        context.user_data["new_pass_candidate"]    = text.strip()
        try:
            await update.message.delete()
        except Exception:
            pass
        await update.message.reply_text(
            "🔑 Confirm New Password\n\n"
            "Re-enter the new password to confirm:"
        )
        return

    # ── Change Password — step 2: confirm ──
    if context.user_data.get("awaiting_confirm_pass"):
        context.user_data["awaiting_confirm_pass"] = False
        candidate = context.user_data.pop("new_pass_candidate", "")
        try:
            await update.message.delete()
        except Exception:
            pass
        if text.strip() == candidate:
            new_hash = hashlib.sha256(candidate.encode()).hexdigest()
            set_pass_hash(new_hash)
            await update.message.reply_text(
                "✅ Password Changed!\n\n"
                "Your new password is now active.\n"
                "Use it next time you log in.",
                reply_markup=InlineKeyboardMarkup([[SBtn("🏠 Home", style="primary", callback_data="c_home")]])
            )
        else:
            await update.message.reply_text(
                "❌ Passwords don't match!\n\n"
                "Password was not changed. Try again from Settings.",
                reply_markup=InlineKeyboardMarkup([
                    [SBtn("🔑 Try Again", style="success", callback_data="c_changepass"),
                     SBtn("🏠 Home", style="primary",      callback_data="c_home")],
                ])
            )
        return

    # ── Password input ──
    if not context.user_data.get("awaiting_pass"):
        return

    try:
        await update.message.delete()
    except Exception:
        pass

    if check_pass(text):
        _authenticated.add(uid)
        context.user_data["awaiting_pass"] = False
        await _send_banner_panel(
            update.message,
            "✅ Access Granted!\n\n" + panel_text(),
            main_keyboard()
        )
    else:
        context.user_data["awaiting_pass"] = True
        await update.message.reply_text(
            "❌ Wrong password!\n\nTry again:"
        )



async def safe_edit(query, text, reply_markup=None):
    """Works whether the message is a photo (caption) or plain text."""
    try:
        await query.edit_message_caption(caption=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception:
        try:
            await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception:
            pass

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = str(query.from_user.id)

    if not is_owner(uid):
        await query.answer("🚫 Unauthorized.", show_alert=True)
        return

    if not is_authed(uid):
        await query.answer("🔒 Session expired. Send /start to log in.", show_alert=True)
        return

    data = query.data
    try:
        await query.answer()
    except Exception:
        pass  # query expired — ignore, continue handling

    if data in ("c_home", "c_refresh"):
        try:
            await query.edit_message_caption(
                caption=panel_text(), reply_markup=main_keyboard()
            )
        except Exception:
            try:
                await safe_edit(query, panel_text(), reply_markup=main_keyboard())
            except Exception:
                pass

    elif data == "c_userlogs":
        await safe_edit(query, userlogs_panel_text(), reply_markup=userlogs_keyboard())

    elif data == "c_set_loggroup":
        context.user_data["awaiting_loggroup"] = True
        await safe_edit(query, 
            "📝 Set Log Group\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            "Send the Group ID where user logs should be sent.\n\n"
            "How to get Group ID:\n"
            "┣ Add the main bot to your group\n"
            "┣ Forward any message from that group to\n"
            "┃   @userinfobot — it shows the chat ID\n"
            "┗ Group IDs usually start with -100\n\n"
            "📌 Send the group ID now:"
        )

    elif data == "c_clear_loggroup":
        cfg = load_config()
        cfg.pop("log_group_id", None)
        save_config(cfg)
        await safe_edit(query, 
            "🗑 Log Group Removed\n\n"
            "User logs are now disabled.\n"
            "Users' messages will no longer be forwarded.",
            reply_markup=userlogs_keyboard()
        )

    elif data == "c_botgroups":
        await safe_edit(query, bot_groups_panel_text(), reply_markup=bot_groups_keyboard())

    elif data == "c_allowedgroups":
        await safe_edit(query, allowed_groups_panel_text(), reply_markup=allowed_groups_keyboard())

    elif data == "c_add_allowedgroup":
        cfg    = load_config()
        groups = cfg.get("allowed_groups", [])
        if len(groups) >= MAX_ALLOWED_GROUPS:
            await query.answer(f"🚫 Limit reached! Max {MAX_ALLOWED_GROUPS} groups allowed.", show_alert=True)
            await safe_edit(query, allowed_groups_panel_text(), reply_markup=allowed_groups_keyboard())
            return
        context.user_data["awaiting_allowedgroup"] = True
        await safe_edit(query,
            f"🏘 Add Allowed Group\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            f"📊 Slots used: {len(groups)} / {MAX_ALLOWED_GROUPS}\n\n"
            f"Send the group username or numeric Chat ID:\n\n"
            f"✅ Formats:\n"
            f"┣ @groupusername\n"
            f"┣ https://t.me/groupusername\n"
            f"┗ -1001234567890  (numeric Chat ID)\n\n"
            f"⚠️ Bot must be a member of the group.\n"
            f"Outside these groups, users will see a redirect."
        )

    elif data.startswith("c_remove_ag_"):
        idx    = int(data.split("c_remove_ag_")[-1])
        cfg    = load_config()
        groups = cfg.get("allowed_groups", [])
        if 0 <= idx < len(groups):
            removed = groups.pop(idx)
            cfg["allowed_groups"] = groups
            save_config(cfg)
            await safe_edit(query,
                f"🗑 Removed!\n\n"
                f"{removed['title']} removed from allowed groups.\n\n"
                + allowed_groups_panel_text(),
                reply_markup=allowed_groups_keyboard()
            )
        else:
            await safe_edit(query, allowed_groups_panel_text(), reply_markup=allowed_groups_keyboard())

    elif data == "c_channels":
        await safe_edit(query, channels_panel_text(), reply_markup=channels_keyboard())

    elif data == "c_add_channel":
        cfg      = load_config()
        channels = cfg.get("required_channels", [])
        if len(channels) >= MAX_CHANNELS:
            await query.answer(f"🚫 Limit reached! Max {MAX_CHANNELS} channels allowed.", show_alert=True)
            await safe_edit(query, channels_panel_text(), reply_markup=channels_keyboard())
            return
        context.user_data["awaiting_channel"] = True
        await safe_edit(query,
            f"📢 Add Channel / Group\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            f"📊 Slots used: {len(channels)} / {MAX_CHANNELS}\n\n"
            f"Send the channel or group link/username:\n\n"
            f"✅ Public formats:\n"
            f"┣ https://t.me/username\n"
            f"┣ @username\n"
            f"┗ username\n\n"
            f"🔒 Private channel:\n"
            f"┗ https://t.me/+xxxxxxxx  (you'll be asked for Chat ID next)\n\n"
            f"⚠️ Bot must be admin in the channel/group to verify members."
        )

    elif data.startswith("c_remove_ch_"):
        idx = int(data.split("c_remove_ch_")[-1])
        cfg      = load_config()
        channels = cfg.get("required_channels", [])
        if 0 <= idx < len(channels):
            removed = channels.pop(idx)
            cfg["required_channels"] = channels
            save_config(cfg)
            await safe_edit(query, 
                f"🗑 Removed!\n\n"
                f"{removed['username']} removed from required channels.\n\n"
                f"{channels_panel_text()}",
                reply_markup=channels_keyboard()
            )
        else:
            await safe_edit(query, channels_panel_text(), reply_markup=channels_keyboard())

    elif data == "c_logout":
        _authenticated.discard(uid)
        context.user_data["awaiting_pass"] = False
        await safe_edit(query, 
            "🔒 Logged out.\n\nSend /start to log in again."
        )

    elif data.startswith("c_feat_"):
        page = int(data.split("_")[-1])
        await safe_edit(query, feat_panel_text(), reply_markup=features_keyboard(page))

    elif data.startswith("cf_"):
        key   = data[3:]
        feats = load_features()
        feats[key] = not feats.get(key, True)
        save_features(feats)
        await safe_edit(query, feat_panel_text(), reply_markup=features_keyboard(0))

    elif data == "c_allon":
        save_features({k: True for k in FEATURES})
        await safe_edit(query, feat_panel_text(), reply_markup=features_keyboard(0))

    elif data == "c_alloff":
        save_features({k: False for k in FEATURES})
        await safe_edit(query, feat_panel_text(), reply_markup=features_keyboard(0))

    elif data == "c_logs":
        try:
            with open(LOG_FILE, encoding="utf-8") as f:
                lines = f.readlines()[-50:]
            log_text = "".join(lines).strip() or "No logs yet."
        except FileNotFoundError:
            log_text = "📭 No log file found yet."
        if len(log_text) > 3500:
            log_text = "…" + log_text[-3500:]
        kb = InlineKeyboardMarkup([
            [SBtn("🔁 Refresh", style="primary", callback_data="c_logs"),
             SBtn("🗑 Clear", style="danger",   callback_data="c_clearlogs")],
            [SBtn("🏠 Home", style="primary",    callback_data="c_home")],
        ])
        await safe_edit(query, 
            f"📋 Live Logs (last 50 lines)\n\n{log_text}",
            reply_markup=kb
        )

    elif data == "c_clearlogs":
        try:
            open(LOG_FILE, "w").close()
            msg = "🗑 Log file cleared."
        except Exception as e:
            msg = f"❌ Could not clear: {e}"
        await safe_edit(query, msg, reply_markup=InlineKeyboardMarkup([
            [SBtn("🏠 Home", style="primary", callback_data="c_home")]
        ]))

    elif data == "c_pause":
        os.makedirs("bot", exist_ok=True)
        with open(PAUSE_FILE, "w") as f:
            f.write(datetime.now().isoformat())
        await safe_edit(query, 
            "⏸️ Bot Paused\n\nAll user commands are blocked.\nUsers will see a maintenance message.",
            reply_markup=InlineKeyboardMarkup([
                [SBtn("▶️ Resume", style="success", callback_data="c_resume"),
                 SBtn("🏠 Home", style="primary",   callback_data="c_home")],
            ])
        )

    elif data == "c_resume":
        try:
            os.remove(PAUSE_FILE)
        except FileNotFoundError:
            pass
        await safe_edit(query, 
            "▶️ Bot Resumed\n\nAll commands are active again.",
            reply_markup=InlineKeyboardMarkup([
                [SBtn("🏠 Home", style="primary", callback_data="c_home")]
            ])
        )

    elif data == "c_restart":
        pid = get_main_pid()
        if pid and process_alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                result = f"🔄 SIGTERM sent to PID {pid}\nWorkflow will auto-restart the bot."
            except Exception as e:
                result = f"❌ Failed: {e}"
        else:
            result = "⚠️ Process not found. Use Spawn to start it manually."
        await safe_edit(query, result, reply_markup=InlineKeyboardMarkup([
            [SBtn("🏠 Home", style="primary", callback_data="c_home")]
        ]))

    elif data == "c_kill":
        pid = get_main_pid()
        if pid and process_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
                result = f"🛑 SIGKILL sent to PID {pid}\nProcess forcefully terminated."
            except Exception as e:
                result = f"❌ Failed: {e}"
        else:
            result = "⚠️ No running process found."
        await safe_edit(query, result, reply_markup=InlineKeyboardMarkup([
            [SBtn("🏠 Home", style="primary", callback_data="c_home")]
        ]))

    elif data == "c_spawn":
        try:
            proc = subprocess.Popen(
                [sys.executable, MAIN_BOT_SCRIPT],
                stdout=open(LOG_FILE, "a"),
                stderr=subprocess.STDOUT
            )
            result = f"🟢 Spawned new bot process\nPID: {proc.pid}"
        except Exception as e:
            result = f"❌ Failed to spawn: {e}"
        await safe_edit(query, result, reply_markup=InlineKeyboardMarkup([
            [SBtn("🏠 Home", style="primary", callback_data="c_home")]
        ]))

    elif data == "c_resetcredits":
        users = load_users()
        total = len(users)
        await safe_edit(query,
            f"<tg-emoji emoji-id='5224257782013769471'>💰</tg-emoji> Reset All Credits\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            f"⚠️ This will set credits to 0 for ALL {total} users.\n"
            f"This action cannot be undone!\n\n"
            f"Type CONFIRM in chat to proceed, or press Home to cancel.",
            reply_markup=InlineKeyboardMarkup([
                [SBtn("🏠 Cancel / Home", style="primary", callback_data="c_home")]
            ])
        )
        context.user_data["awaiting_confirm_resetcredits"] = True

    elif data == "c_confirm_resetcredits":
        users = load_users()
        count = 0
        for u in users.values():
            if not u.get("is_admin"):
                u["credits"] = 0
                u["last_claim"] = None
                u["force_join_passed"] = False
                count += 1
        save_users(users)
        await safe_edit(query,
            f"✅ Full Reset Done!\n\n"
            f"<tg-emoji emoji-id='5224257782013769471'>💰</tg-emoji> Credits → 0\n"
            f"📅 Daily claim → Reset (can claim again)\n"
            f"✅ Affected: {count} users\n"
            f"<tg-emoji emoji-id='6253517256794311831'>😎</tg-emoji> Admins were skipped.",
            reply_markup=InlineKeyboardMarkup([
                [SBtn("🏠 Home", style="primary", callback_data="c_home")]
            ])
        )

    elif data == "c_noop":
        pass

    # ──── USER MANAGER ────
    elif data.startswith("c_users_"):
        page = int(data.split("c_users_")[-1])
        users_data = load_users()
        total_pages = max(1, (len(users_data) + USERS_PAGE_SIZE - 1) // USERS_PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        await safe_edit(query, users_list_text(page), reply_markup=users_list_keyboard(page))

    elif data == "c_user_search":
        context.user_data["awaiting_user_lookup"] = True
        await safe_edit(query, 
            "🔍 Search User\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            "Send the User ID or @username to look up:\n\n"
            "📌 User IDs are numeric (e.g. 123456789)\n"
            "📌 Usernames start with @ (e.g. @john)"
        )

    elif data.startswith("c_viewuser_"):
        uid2 = data.split("c_viewuser_")[-1]
        users = load_users()
        u = users.get(uid2)
        if not u:
            await query.answer("❌ User not found.", show_alert=True)
            return
        await safe_edit(query, user_profile_text(uid2, u), reply_markup=user_profile_keyboard(uid2, u))

    elif data.startswith("c_ban_"):
        uid2 = data.split("c_ban_")[-1]
        users = load_users()
        if uid2 not in users:
            await query.answer("❌ User not found.", show_alert=True); return
        users[uid2]["banned"] = True
        save_users(users)
        await safe_edit(query, user_profile_text(uid2, users[uid2]), reply_markup=user_profile_keyboard(uid2, users[uid2]))
        await query.answer("✅ User banned!", show_alert=True)

    elif data.startswith("c_unban_"):
        uid2 = data.split("c_unban_")[-1]
        users = load_users()
        if uid2 not in users:
            await query.answer("❌ User not found.", show_alert=True); return
        users[uid2]["banned"] = False
        save_users(users)
        await safe_edit(query, user_profile_text(uid2, users[uid2]), reply_markup=user_profile_keyboard(uid2, users[uid2]))
        await query.answer("✅ User unbanned!", show_alert=True)

    elif data.startswith("c_mkadmin_"):
        uid2 = data.split("c_mkadmin_")[-1]
        users = load_users()
        if uid2 not in users:
            await query.answer("❌ User not found.", show_alert=True); return
        users[uid2]["is_admin"] = True
        save_users(users)
        await safe_edit(query, user_profile_text(uid2, users[uid2]), reply_markup=user_profile_keyboard(uid2, users[uid2]))
        await query.answer("😎 Made admin!", show_alert=True)

    elif data.startswith("c_deadmin_"):
        uid2 = data.split("c_deadmin_")[-1]
        users = load_users()
        if uid2 not in users:
            await query.answer("❌ User not found.", show_alert=True); return
        users[uid2]["is_admin"] = False
        save_users(users)
        await safe_edit(query, user_profile_text(uid2, users[uid2]), reply_markup=user_profile_keyboard(uid2, users[uid2]))
        await query.answer("✅ Admin removed!", show_alert=True)

    elif data.startswith("c_addcr_"):
        uid2 = data.split("c_addcr_")[-1]
        context.user_data["awaiting_credits_uid"]  = uid2
        context.user_data["awaiting_credits_mode"] = "add"
        await safe_edit(query, 
            f"<tg-emoji emoji-id='5224257782013769471'>💰</tg-emoji> Add Credits\n\n"
            f"Adding credits to user {uid2}\n\n"
            f"Send the amount to add (e.g. 500):"
        )

    elif data.startswith("c_remcr_"):
        uid2 = data.split("c_remcr_")[-1]
        context.user_data["awaiting_credits_uid"]  = uid2
        context.user_data["awaiting_credits_mode"] = "remove"
        await safe_edit(query, 
            f"💸 Remove Credits\n\n"
            f"Removing credits from user {uid2}\n\n"
            f"Send the amount to remove (e.g. 200):"
        )

    elif data.startswith("c_deluser_"):
        uid2 = data.split("c_deluser_")[-1]
        users = load_users()
        if uid2 not in users:
            await query.answer("❌ User not found.", show_alert=True); return
        context.user_data["awaiting_confirm_deluser"] = uid2
        await safe_edit(query, 
            f"⚠️ Delete User?\n\n"
            f"User ID: {uid2}\n\n"
            f"This will permanently remove this user and all their data.\n"
            f"This action cannot be undone.\n\n"
            f"Type CONFIRM to proceed:"
        )

    # ──── BROADCAST ────
    elif data == "c_broadcast":
        context.user_data["awaiting_broadcast"] = True
        await safe_edit(query, 
            "📣 Broadcast Message\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            "Send your message below and it will be forwarded to ALL bot users.\n\n"
            "✅ Supports: Text, Bold, Italic, Links\n"
            "✅ You can include emojis\n\n"
            "⚠️ This cannot be undone — send carefully!\n\n"
            "📌 Send your broadcast message now:"
        )

    # ──── CODE MANAGER ────
    elif data == "c_codes":
        await safe_edit(query, codes_list_text(), reply_markup=codes_keyboard())

    elif data == "c_createcode":
        context.user_data["awaiting_code_create"] = True
        context.user_data["code_create_step"]     = "credits"
        await safe_edit(query, 
            "🎫 Create Redeem Code\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            "Step 1/3 — How many credits should this code give?\n\n"
            "📌 Send a number (e.g. 100):"
        )

    elif data.startswith("c_delcode_"):
        code = data[len("c_delcode_"):]
        codes = load_codes()
        if code in codes:
            codes.pop(code)
            save_codes(codes)
            await query.answer(f"🗑 Code '{code}' deleted!", show_alert=True)
        else:
            await query.answer("❌ Code not found.", show_alert=True)
        await safe_edit(query, codes_list_text(), reply_markup=codes_keyboard())

    elif data == "c_clearallcodes":
        context.user_data["awaiting_confirm_clearall"] = True
        await safe_edit(query, 
            "⚠️ Clear All Codes?\n\n"
            "This will delete ALL redeem codes permanently.\n\n"
            "Type CONFIRM to proceed:"
        )

    # ──── DM USER ────
    elif data == "c_dm_user":
        await safe_edit(query, dm_user_text(), reply_markup=dm_user_keyboard())

    elif data == "c_dm_start":
        context.user_data["awaiting_dm_uid"] = True
        await safe_edit(query, 
            "💬 DM User\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            "Send the User ID of the user you want to message:\n\n"
            "📌 Example: 123456789"
        )

    # ──── CHANGE PASSWORD ────
    elif data == "c_changepass":
        context.user_data["awaiting_new_pass"]    = True
        context.user_data["awaiting_confirm_pass"] = False
        context.user_data["new_pass_candidate"]    = None
        await safe_edit(query, 
            "🔑 Change Password\n"
            "<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            "All current sessions will remain active.\n"
            "You'll need the new password next time you log in.\n\n"
            "📌 Send your new password:"
        )

    # ──── BACKUP FILES ────
    elif data == "c_backup":
        files_to_send = [
            (USER_FILE,     "👥 user.json — user data & credits"),
            (CODES_FILE,    "🎫 codes.json — redeem codes"),
            (CONFIG_FILE,   "⚙️ config.json — bot configuration"),
            (FEATURES_FILE, "🔧 features.json — feature flags"),
            (GROUPS_FILE,   "🤖 groups.json — tracked bot groups"),
            (LOG_FILE,      "📋 shuvo.log — runtime log"),
        ]
        await safe_edit(query, 
            "📁 Backup Files\n\n"
            "Sending all data files now…"
        )
        sent = 0
        for fpath, label in files_to_send:
            if os.path.exists(fpath):
                try:
                    with open(fpath, "rb") as fp:
                        await context.bot.send_document(
                            chat_id=uid,
                            document=fp,
                            filename=os.path.basename(fpath),
                            caption=f"📦 {label}"
                        )
                    sent += 1
                except Exception as e:
                    await context.bot.send_message(chat_id=uid, text=f"❌ Could not send {fpath}: {e}")
        await context.bot.send_message(
            chat_id=uid,
            text=f"✅ Backup Complete!\n\nSent {sent} files.",
            reply_markup=InlineKeyboardMarkup([[SBtn("🏠 Home", style="primary", callback_data="c_home")]])
        )

    elif data == "c_stats":
        try:
            with open("bot/user.json") as f:
                users = json.load(f)
            total    = len(users)
            active   = sum(1 for u in users.values() if not u.get("banned"))
            banned   = total - active
            admins   = sum(1 for u in users.values() if u.get("is_admin"))
            tot_cr   = sum(u.get("credits", 0) for u in users.values())
            has_uname= sum(1 for u in users.values() if u.get("username"))
        except Exception:
            total = active = banned = admins = tot_cr = has_uname = 0
        try:
            with open("bot/codes.json") as f:
                codes = json.load(f)
            n_codes = len(codes)
        except Exception:
            n_codes = 0
        try:
            log_size = os.path.getsize(LOG_FILE) // 1024
        except Exception:
            log_size = 0
        cfg     = load_config()
        ch_cnt  = len(cfg.get("required_channels", []))
        log_grp = "✅ Set" if cfg.get("log_group_id") else "❌ Not set"
        state, mode = bot_status_line()
        feats   = load_features()
        on_cnt  = sum(1 for v in feats.values() if v)
        off_cnt = len(feats) - on_cnt
        now     = datetime.now().strftime("%d %b %Y  %H:%M:%S")
        await safe_edit(query, 
            f"📊 SHUVO BOT — Full Stats\n"
            f"<tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji><tg-emoji emoji-id='6307665627481903641'>➖</tg-emoji>\n\n"
            f"👥 Users\n"
            f"   ┣ Total       : {total}\n"
            f"   ┣ Active      : {active}\n"
            f"   ┣ Banned      : {banned}\n"
            f"   ┣ Admins      : {admins}\n"
            f"   ┗ With @user  : {has_uname}\n\n"
            f"<tg-emoji emoji-id='5224257782013769471'>💰</tg-emoji> Economy\n"
            f"   ┣ Total Credits : {tot_cr:,}\n"
            f"   ┗ Redeem Codes  : {n_codes}\n\n"
            f"🔧 Features\n"
            f"   ┣ Enabled  : {on_cnt}  ✅\n"
            f"   ┗ Disabled : {off_cnt}  ❌\n\n"
            f"⚙️ Config\n"
            f"   ┣ Force Join  : {ch_cnt}/5 channels\n"
            f"   ┣ User Logs   : {log_grp}\n"
            f"   ┗ Log Size    : {log_size} KB\n\n"
            f"🤖 Process\n"
            f"   ┣ {state}\n"
            f"   ┗ {mode}\n\n"
            f"🕐 Checked: {now}",
            reply_markup=InlineKeyboardMarkup([
                [SBtn("🔁 Refresh", style="primary", callback_data="c_stats"),
                 SBtn("🏠 Home", style="primary",    callback_data="c_home")],
            ])
        )


async def error_handler(update, context):
    err_str = str(context.error)
    silent = ("Conflict:", "Forbidden: bot was blocked", "Message is not modified",
               "Query is too old", "Bad Request: message to delete not found",
               "Bad Request: message can't be deleted", "NetworkError", "TimedOut")
    if any(s in err_str for s in silent):
        return
    print(f"Controller error: {err_str}")


# ── Premium Emoji Bot Subclass ────────────────────────────────────────────────
class _PremiumBot(ExtBot):
    """Auto-upgrades plain emojis to premium animated versions in all HTML sends."""

    @staticmethod
    def _fix(t):
        return _pe_all(str(t)) if t else t

    @staticmethod
    def _html_mode(kwargs):
        pm = kwargs.get('parse_mode')
        return pm is None or pm not in ('', 'Markdown', 'MarkdownV2')

    async def send_message(self, chat_id, text=None, **kwargs):
        if text and self._html_mode(kwargs):
            text = self._fix(text)
        return await super().send_message(chat_id, text=text, **kwargs)

    async def edit_message_text(self, text, **kwargs):
        if text and self._html_mode(kwargs):
            text = self._fix(text)
        return await super().edit_message_text(text, **kwargs)

    async def send_photo(self, chat_id, photo, caption=None, **kwargs):
        if caption and self._html_mode(kwargs):
            caption = self._fix(caption)
        return await super().send_photo(chat_id, photo, caption=caption, **kwargs)

    async def send_video(self, chat_id, video, caption=None, **kwargs):
        if caption and self._html_mode(kwargs):
            caption = self._fix(caption)
        return await super().send_video(chat_id, video, caption=caption, **kwargs)

    async def send_document(self, chat_id, document, caption=None, **kwargs):
        if caption and self._html_mode(kwargs):
            caption = self._fix(caption)
        return await super().send_document(chat_id, document, caption=caption, **kwargs)
# ─────────────────────────────────────────────────────────────────────────────


def main():
    print("Controller bot starting...")
    _bot = _PremiumBot(token=CONTROLLER_TOKEN, defaults=Defaults(parse_mode=ParseMode.HTML))
    app = Application.builder().bot(_bot).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("logout", cmd_logout))
    app.add_handler(CommandHandler("ai",     cmd_ai))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Sticker.ALL | filters.VIDEO |
         filters.Document.ALL | filters.ANIMATION | filters.AUDIO | filters.VOICE) & ~filters.COMMAND,
        handle_text
    ))
    app.add_error_handler(error_handler)
    print("Controller bot running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
