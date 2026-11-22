import os
import re
import json
import asyncio
import ast
import sys
import subprocess
import csv
import io
import sqlite3
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error
import fitz  # PyMuPDF
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import WebAppInfo, BufferedInputFile
from google import genai
from google.genai import types as genai_types
from flowchart_builder import code_to_nodes, validate_flowchart_nodes

# ================= RENDER VA MUHIT SOZLAMALARI =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKENINGIZNI_SHU_YERGA_YOZING")

WEBAPP_URL = (
    os.getenv("WEBAPP_URL")
    or os.getenv("RENDER_EXTERNAL_URL")
    or ("https://" + "algoritm-03.onrender.com")
).rstrip("/")

GROQ_API_URL = "https://" + "api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://" + "api.groq.com/openai/v1/models"

PDF_PATH = os.getenv("PDF_PATH", "BLACKCURSE.pdf")
PDF_BOB1_PATH = os.getenv("PDF_BOB1_PATH", "BLACKCURSE1.pdf")
PROBLEMS_JSON = os.getenv("PROBLEMS_JSON", "problems.json")
PROBLEMS_BOB1_JSON = os.getenv("PROBLEMS_BOB1_JSON", "problems_bob1.json")
SOLUTIONS_CACHE_FILE = os.getenv("SOLUTIONS_CACHE_FILE", "solutions_cache.json")
USERS_DB_FILE = os.getenv("USERS_DB_FILE", "users.db")
PORT = int(os.getenv("PORT", 8080))

# --- ADMIN SOZLAMALARI ---
# Render'da ADMIN_IDS="123456789" (bir nechta bo'lsa vergul bilan: "123456,789012")
_raw_admins = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_ID", "")
ADMIN_IDS = {int(x.strip()) for x in _raw_admins.split(",") if x.strip().isdigit()}
NOTIFY_ALL_VIEWS = os.getenv("NOTIFY_ALL_VIEWS", "0") == "1"

# --- GROQ API (katta bepul limitli asosiy provayder) ---
_raw_groq_keys = (
    os.getenv("GROQ_API_KEYS")
    or os.getenv("GROQ_API_KEY")
    or os.getenv("GROQ_KEY")
    or ""
)
GROQ_API_KEYS = [k.strip() for k in _raw_groq_keys.split(",") if k.strip()]

_raw_groq_models = os.getenv("GROQ_MODELS") or os.getenv("GROQ_MODEL", "")
GROQ_MODELS = [m.strip() for m in _raw_groq_models.split(",") if m.strip()]
_groq_key_idx = 0
_groq_discovered = False

# --- GEMINI API (zaxira provayder) ---
_raw_keys = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY", "")
GEMINI_API_KEYS = [
    k.strip() for k in _raw_keys.split(",")
    if k.strip() and k.strip() != "GEMINI_API_KEYINGIZNI_SHU_YERGA_YOZING"
]

_raw_models = os.getenv("GEMINI_MODELS") or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_MODELS = [m.strip() for m in _raw_models.split(",") if m.strip() and "2.0" not in m]
for _fallback_model in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
    if _fallback_model not in GEMINI_MODELS:
        GEMINI_MODELS.append(_fallback_model)

_GEMINI_CLIENTS = [
    genai.Client(api_key=k, http_options={"api_version": "v1beta"})
    for k in GEMINI_API_KEYS
]
_gemini_key_idx = 0

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

PROBLEMS_DB = {}
HINTS = {}
SOLUTIONS_DB = {}       # solutions_cache.json dan o'qilgan/saqlangan yechimlar
FLOWCHART_CACHE = {}    # RAM kesh (tayyor nodes bilan)
_PROBLEM_LOCKS = {}     # Bir vaqtda bir masalani ochgan talabalar uchun navbat

SECTION_NAMES = {
    "1.1": "§-1.1. Arifmetik ifodalar",
    "1.2": "§-1.2. Elementar funksiyalar",
    "1.3": "§-1.3. Geometrik va sodda masalalar",
    "1.4.1": "§-1.4 (1). Tarmoqlanish",
    "1.4.2": "§-1.4 (2). Tanlash operatori",
    "1.5.1": "§-1.5 (1). Takrorlash (for)",
    "1.5.2": "§-1.5 (2). Ichma-ich sikllar",
    "1.5.3": "§-1.5 (3). Takrorlash (while)",
    "1.6": "§-1.6. Bir o'lchovli massivlar",
    "1.7": "§-1.7. Ikki o'lchovli massivlar",
    "1.8": "§-1.8. Belgili kattaliklar",
    "5.1": "§-5.1. Butun sonli masalalar",
    "5.2": "§-5.2. Sanoq sistemalari",
    "5.3": "§-5.3. Geometriya",
    "5.4": "§-5.4. Massivlarni tartiblash",
    "5.5": "§-5.5. Ko'phadlar bilan ishlash",
    "5.6": "§-5.6. Matrisalarni tuzish",
    "5.7": "§-5.7. Matrisalar algebrasi",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UZ_TZ = timezone(timedelta(hours=5))


# ================= FOYDALANUVCHILAR STATISTIKASI (SQLite + ADMIN) =================
def _now_uz() -> str:
    return datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _today_uz() -> str:
    return datetime.now(UZ_TZ).strftime("%Y-%m-%d")


def _html_esc(text: str) -> str:
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _users_db_path() -> str:
    return USERS_DB_FILE if os.path.isabs(USERS_DB_FILE) else os.path.join(BASE_DIR, USERS_DB_FILE)


def init_users_db():
    conn = sqlite3.connect(_users_db_path())
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                full_name TEXT DEFAULT '',
                first_seen TEXT,
                last_seen TEXT,
                total_views INTEGER DEFAULT 0,
                last_problem TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                problem TEXT,
                source TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def record_user_activity(user_id: int, username: str = "", full_name: str = "",
                         problem: str = "", is_view: bool = False, source: str = "bot") -> bool:
    """Foydalanuvchi faolligini bazaga yozadi. Yangi foydalanuvchi bo'lsa True qaytaradi."""
    if not user_id:
        return False
    ts = _now_uz()
    uname = (username or "").lstrip("@").strip()
    fname = (full_name or "").strip()
    prob = (problem or "").strip()

    conn = sqlite3.connect(_users_db_path())
    try:
        row = conn.execute(
            "SELECT username, full_name, total_views, last_problem FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        is_new = row is None
        if is_new:
            conn.execute(
                "INSERT INTO users (user_id, username, full_name, first_seen, last_seen, total_views, last_problem) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, uname, fname or f"User {user_id}", ts, ts, 1 if is_view else 0, prob)
            )
        else:
            old_uname, old_fname, old_views, old_prob = row
            conn.execute(
                "UPDATE users SET username = ?, full_name = ?, last_seen = ?, total_views = ?, last_problem = ? "
                "WHERE user_id = ?",
                (
                    uname or old_uname,
                    fname or old_fname,
                    ts,
                    (old_views or 0) + (1 if is_view else 0),
                    prob or old_prob,
                    user_id,
                )
            )
        if is_view and prob:
            conn.execute(
                "INSERT INTO views (user_id, problem, source, created_at) VALUES (?, ?, ?, ?)",
                (user_id, prob, source, ts)
            )
        conn.commit()
        return is_new
    except Exception as e:
        print(f"Foydalanuvchi yozishda xato: {e}")
        return False
    finally:
        conn.close()


def get_admin_stats() -> dict:
    today = _today_uz()
    conn = sqlite3.connect(_users_db_path())
    try:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        new_today = conn.execute("SELECT COUNT(*) FROM users WHERE first_seen LIKE ?", (today + "%",)).fetchone()[0]
        active_today = conn.execute("SELECT COUNT(*) FROM users WHERE last_seen LIKE ?", (today + "%",)).fetchone()[0]
        total_views = conn.execute("SELECT COUNT(*) FROM views").fetchone()[0]
        views_today = conn.execute("SELECT COUNT(*) FROM views WHERE created_at LIKE ?", (today + "%",)).fetchone()[0]
        top_problems = conn.execute(
            "SELECT problem, COUNT(*) AS cnt FROM views GROUP BY problem ORDER BY cnt DESC LIMIT 5"
        ).fetchall()
        return {
            "total_users": total_users,
            "new_today": new_today,
            "active_today": active_today,
            "total_views": total_views,
            "views_today": views_today,
            "top_problems": top_problems,
        }
    finally:
        conn.close()


def get_users_list(order_by: str = "last_seen", limit: int = 20) -> list:
    col = "total_views" if order_by == "total_views" else "last_seen"
    conn = sqlite3.connect(_users_db_path())
    try:
        return conn.execute(
            f"SELECT user_id, username, full_name, first_seen, last_seen, total_views, last_problem "
            f"FROM users ORDER BY {col} DESC LIMIT ?",
            (limit,)
        ).fetchall()
    finally:
        conn.close()


def build_users_csv_bytes() -> bytes:
    conn = sqlite3.connect(_users_db_path())
    try:
        rows = conn.execute(
            "SELECT user_id, username, full_name, first_seen, last_seen, total_views, last_problem "
            "FROM users ORDER BY last_seen DESC"
        ).fetchall()
    finally:
        conn.close()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["User ID", "Username", "Ism-Familiya", "Birinchi kirish", "Oxirgi faollik", "Ko'rilgan blok-sxemalar", "Oxirgi masala"])
    for r in rows:
        uid, uname, fname, fseen, lseen, tviews, lprob = r
        writer.writerow([uid, f"@{uname}" if uname else "", fname, fseen, lseen, tviews, lprob])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


async def _send_admin_notice(text: str):
    if not ADMIN_IDS:
        return
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, text, parse_mode="HTML")
        except Exception as e:
            print(f"Adminga ({aid}) xabar yuborishda xato: {e}")


def track_activity_bg(user_id: int, username: str = "", full_name: str = "",
                      problem: str = "", is_view: bool = False, source: str = "bot"):
    """Foydalanuvchi faolligini yozadi va kerak bo'lsa adminga xabar yuboradi."""
    if not user_id:
        return
    is_new = record_user_activity(user_id, username, full_name, problem=problem, is_view=is_view, source=source)
    if not ADMIN_IDS or user_id in ADMIN_IDS:
        return

    safe_name = _html_esc(full_name or f"User {user_id}")
    uname_part = f" (@{_html_esc(username.lstrip('@'))})" if username else ""
    user_link = f'<a href="tg://user?id={user_id}">{safe_name}</a>{uname_part}'

    if is_new:
        prob_line = f"\n📘 Masala: <b>{_html_esc(problem)}</b>" if problem else ""
        msg = (
            f"🆕 <b>Yangi foydalanuvchi!</b>\n"
            f"👤 {user_link}\n"
            f"🆔 <code>{user_id}</code>{prob_line}\n"
            f"🕒 {_now_uz()}"
        )
        asyncio.create_task(_send_admin_notice(msg))
    elif is_view and NOTIFY_ALL_VIEWS and problem:
        msg = (
            f"👀 <b>Blok-sxema ko'rildi</b>\n"
            f"👤 {user_link} (<code>{user_id}</code>)\n"
            f"📘 Masala: <b>{_html_esc(problem)}</b> ({source})\n"
            f"🕒 {_now_uz()}"
        )
        asyncio.create_task(_send_admin_notice(msg))


def is_admin(user_id: int) -> bool:
    return bool(user_id and user_id in ADMIN_IDS)


# ================= GROQ MODELLARINI AVTO-ANIQLASH =================
_GROQ_SKIP_KEYWORDS = ("whisper", "tts", "guard", "orpheus", "playai", "embed", "moderation", "compound")
_GROQ_PREFER_KEYWORDS = ("70b", "qwen", "llama-4", "llama-3.3", "deepseek", "gpt-oss", "kimi", "mixtral", "gemma")


def _groq_model_rank(model_id: str) -> tuple:
    low = model_id.lower()
    for idx, kw in enumerate(_GROQ_PREFER_KEYWORDS):
        if kw in low:
            return (0, idx, low)
    return (1, 99, low)


def discover_groq_models(force: bool = False) -> list:
    """Groq API kalitiga ochiq bo'lgan faol matnli modellarni avtomatik aniqlaydi."""
    global GROQ_MODELS, _groq_discovered
    if _groq_discovered and GROQ_MODELS and not force:
        return GROQ_MODELS
    if not GROQ_API_KEYS:
        return GROQ_MODELS

    discovered = []
    for api_key in GROQ_API_KEYS:
        req = urllib.request.Request(
            GROQ_MODELS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "Mozilla/5.0",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            for item in body.get("data", []):
                mid = str(item.get("id", "")).strip()
                if not mid:
                    continue
                low = mid.lower()
                if any(bad in low for bad in _GROQ_SKIP_KEYWORDS):
                    continue
                if mid not in discovered:
                    discovered.append(mid)
            if discovered:
                break
        except Exception as e:
            print(f"Groq modellari ro'yxatini olishda xato: {e}")

    if discovered:
        discovered.sort(key=_groq_model_rank)
        # Foydalanuvchi qo'lda bergan modellar ro'yxatda bo'lsa, oldinga qo'yiladi
        merged = [m for m in GROQ_MODELS if m in discovered]
        for m in discovered:
            if m not in merged:
                merged.append(m)
        GROQ_MODELS = merged[:6]
        _groq_discovered = True
        print(f"Groq faol modellar aniqlandi: {GROQ_MODELS}")
    elif not GROQ_MODELS:
        GROQ_MODELS = ["llama-3.3-70b-versatile", "qwen/qwen3-32b", "openai/gpt-oss-120b"]

    return GROQ_MODELS


# ================= SOLUTIONS_CACHE.JSON BAZASI =================
def _solutions_cache_path() -> str:
    return (
        SOLUTIONS_CACHE_FILE
        if os.path.isabs(SOLUTIONS_CACHE_FILE)
        else os.path.join(BASE_DIR, SOLUTIONS_CACHE_FILE)
    )


def load_solutions_cache():
    path = _solutions_cache_path()
    if not os.path.exists(path):
        print("solutions_cache.json hali mavjud emas (yangi yechimlar saqlanib boradi).")
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            SOLUTIONS_DB.update(data)
            print(f"solutions_cache.json o'qildi: {len(SOLUTIONS_DB)} ta tayyor yechim")
    except Exception as e:
        print(f"solutions_cache.json o'qishda xato: {e}")


def save_solution_to_disk(cache_key: str, item: dict):
    SOLUTIONS_DB[cache_key] = {
        "explanation": item.get("explanation", ""),
        "input_format": item.get("input_format", ""),
        "sample_input": item.get("sample_input", ""),
        "code_python": item.get("code_python", ""),
    }
    path = _solutions_cache_path()
    try:
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(SOLUTIONS_DB, f, ensure_ascii=False, indent=1)
        os.replace(tmp_path, path)
    except Exception as e:
        print(f"solutions_cache.json saqlashda xato: {e}")


def build_result_from_cached(sec: str, num: str, cached: dict, prob_text: str):
    code = ensure_input_prompts(str(cached.get("code_python", "")).replace("\r\n", "\n").strip("\n"))
    if not code.strip():
        return None
    nodes = code_to_nodes(code)
    if not nodes:
        return None
    return {
        "title": f"{SECTION_NAMES.get(sec, sec)}. {num}-masala",
        "explanation": cached.get("explanation", ""),
        "input_format": cached.get("input_format", ""),
        "sample_input": cached.get("sample_input", ""),
        "code_python": code,
        "nodes": nodes,
        "problem_text": prob_text,
    }


# ================= PDF VA JSON PARSERLAR =================
def _parse_numbered_block(sec_body: str, prefix: str = "") -> dict:
    probs = {}
    matches = list(re.finditer(r'(?:^|\n)\s*(\d{1,2})\s*[\.,]\s+', sec_body))
    valid = []
    for m in matches:
        num = int(m.group(1))
        if 1 <= num <= 25 and str(num) not in probs:
            valid.append((num, m.start(), m.end()))
            probs[str(num)] = ""
    for i, (num, _, end_pos) in enumerate(valid):
        nxt = valid[i + 1][1] if i + 1 < len(valid) else len(sec_body)
        txt = re.sub(r'\s+', ' ', sec_body[end_pos:nxt]).strip()
        probs[str(num)] = (f"{prefix} {txt}".strip() if prefix else txt)
    return probs


def load_bob1_from_pdf(pdf_path: str):
    path = pdf_path if os.path.isabs(pdf_path) else os.path.join(BASE_DIR, pdf_path)
    if not os.path.exists(path):
        print(f"DIQQAT: {path} topilmadi (I bob yuklanmadi).")
        return

    doc = fitz.open(path)
    full_text = ""
    for page in doc:
        t = page.get_text("text")
        t = re.sub(r'\n\s*\d{1,2}\s*\n', '\n', t)
        full_text += t + "\n"

    sec_matches = list(re.finditer(r'§\s*-\s*(1\.[1-8])\.\s*([^\n]+)', full_text))
    for idx, match in enumerate(sec_matches):
        sec_code = match.group(1)
        start_pos = match.end()
        end_pos = sec_matches[idx + 1].start() if idx + 1 < len(sec_matches) else len(full_text)
        body = full_text[start_pos:end_pos]

        if sec_code == "1.4":
            parts = re.split(r'2\s*-\s*vazifa', body, maxsplit=1, flags=re.IGNORECASE)
            PROBLEMS_DB["1.4.1"] = _parse_numbered_block(parts[0])
            if len(parts) > 1:
                PROBLEMS_DB["1.4.2"] = _parse_numbered_block(parts[1])
        elif sec_code == "1.5":
            p1 = re.split(r'2\s*-\s*topshiriq', body, maxsplit=1, flags=re.IGNORECASE)
            PROBLEMS_DB["1.5.1"] = _parse_numbered_block(p1[0])
            if len(p1) > 1:
                p2 = re.split(r'3\s*-\s*topshiriq', p1[1], maxsplit=1, flags=re.IGNORECASE)
                PROBLEMS_DB["1.5.2"] = _parse_numbered_block(p2[0], "n, k natural va x haqiqiy sonlari uchun hisoblang:")
                if len(p2) > 1:
                    PROBLEMS_DB["1.5.3"] = _parse_numbered_block(p2[1])
        else:
            prefix = ""
            if sec_code == "1.1":
                prefix = "Haqiqiy a, b, c, d sonlari uchun hisoblang (darajaga ko'tarish amalidan foydalanmasdan):"
            elif sec_code == "1.2":
                prefix = "Haqiqiy x, y, z sonlari uchun elementar funksiyalar yordamida hisoblang:"
            PROBLEMS_DB[sec_code] = _parse_numbered_block(body, prefix)

    print("BLACKCURSE1.pdf (I bob) yuklandi!")


def load_problems_from_pdf(pdf_path: str):
    if not os.path.exists(pdf_path):
        print(f"DIQQAT: {pdf_path} topilmadi!")
        return

    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        text = page.get_text("text")
        text = re.sub(r'\n\s*(11[4-9]|12[0-9]|13[0-5])\s*\n', '\n', text)
        full_text += text + "\n"

    sec_matches = list(re.finditer(r'§\s*-\s*(5\.[1-7])\.\s*([^\n]+)', full_text))
    for idx, match in enumerate(sec_matches):
        sec_code = match.group(1)
        start_pos = match.end()
        end_pos = sec_matches[idx + 1].start() if idx + 1 < len(sec_matches) else len(full_text)
        sec_body = full_text[start_pos:end_pos]

        PROBLEMS_DB[sec_code] = {}
        prob_matches = list(re.finditer(r'(?:^|\n)\s*(\d{1,2})\s*[\.,]\s+', sec_body))

        expected_num = 1
        valid_matches = []
        for pm in prob_matches:
            num = int(pm.group(1))
            if num == expected_num or (sec_code == "5.4" and expected_num == 4 and num == 5):
                valid_matches.append((num, pm.start(), pm.end()))
                expected_num = num + 1

        for p_idx, (p_num, p_start, p_end) in enumerate(valid_matches):
            next_start = valid_matches[p_idx + 1][1] if p_idx + 1 < len(valid_matches) else len(sec_body)
            prob_text = re.sub(r'\s+', ' ', sec_body[p_end:next_start]).strip()
            PROBLEMS_DB[sec_code][str(p_num)] = prob_text


def load_problems():
    p1 = PROBLEMS_BOB1_JSON if os.path.isabs(PROBLEMS_BOB1_JSON) else os.path.join(BASE_DIR, PROBLEMS_BOB1_JSON)
    if os.path.exists(p1):
        try:
            with open(p1, "r", encoding="utf-8") as f:
                data1 = json.load(f)
            for sec, probs in data1.items():
                PROBLEMS_DB[sec] = {str(k): v for k, v in probs.items()}
            print(f"problems_bob1.json o'qildi: {sum(len(v) for v in data1.values())} ta masala")
        except Exception as e:
            print(f"problems_bob1.json xatosi: {e}. PDF ishlatiladi.")
            load_bob1_from_pdf(PDF_BOB1_PATH)
    else:
        load_bob1_from_pdf(PDF_BOB1_PATH)

    path = PROBLEMS_JSON if os.path.isabs(PROBLEMS_JSON) else os.path.join(BASE_DIR, PROBLEMS_JSON)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            HINTS.update(data.pop("_hints", {}) or {})
            for sec, probs in data.items():
                PROBLEMS_DB[sec] = {str(k): v for k, v in probs.items()}
            print(f"Jami yuklangan masalalar: {sum(len(v) for v in PROBLEMS_DB.values())} ta")
            return
        except Exception as e:
            print(f"problems.json o'qishda xato: {e}. PDF ishlatiladi.")
    load_problems_from_pdf(PDF_PATH)


# ================= AI GENERATOR (GROQ + GEMINI) =================
def clean_json_text(raw_text: str) -> str:
    text = (raw_text or "").strip()
    # Ba'zi modellar (Qwen/DeepSeek) <think>...</think> bloki qaytarishi mumkin
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
    return text.strip()


_EMPTY_INPUT_RE = re.compile(
    r'^([ \t]*)([a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])*)\s*=\s*((?:int|float)\s*\(\s*)?input\(\s*(?:""|\'\')?\s*\)',
    re.MULTILINE
)


def ensure_input_prompts(code: str) -> str:
    """Bo'sh input() larning barchasiga avtomatik o'zgaruvchi nomini yozib qo'yadi."""
    return _EMPTY_INPUT_RE.sub(
        lambda m: f'{m.group(1)}{m.group(2)} = {m.group(3) or ""}input("{m.group(2)} = ")',
        code
    )


SYSTEM_PROMPT = r"""
Sen universitet talabasi daftariga yozgandek ENG TOZA, SODDA va 100% KODSIZ blok-sxemaga aylanadigan matematik Python kodi yozuvchi ustozsan.
Faqat sof JSON qaytar (boshqa matn yozma):
{"explanation": "...", "input_format": "...", "test_input": "...", "code_python": "..."}

QAT'IY QOIDALAR:
1. ORTIQCHA BELGILASH YOZMA:
   - Faqat masalada berilgan harflarni (a, b, c, d, x, y, z, n, m, S, K va h.k.), natija uchun `s` (bo'laklari `s1, s2, s3`), sikl uchun `i, j, k` ishlat.
   - Ortiqcha oraliq o'zgaruvchilar (`t`, `t1`, `u`, `v`, `w`, `o`, `temp`, `flag`, `res`, `ans`) yaratma!
   - §-1.1 va §-1.2 da FAQAT asosiy kasrlar uchun `s1, s2, s3` va yakuniy natija uchun `s` ishlat (`t` ham ISHLATMA!).
     Daraja taqiqlangan joyda kvadratni `(...) * (...)` deb bevosita o'sha `s1` qatorining ichida yoz.
2. FAQAT RUXSAT ETILGAN FUNKSIYALAR (OQ RO'YXAT):
   - RUXSAT: `input`, `print`, `range`, `int`, `float`, `abs`, va kerak bo'lsa `from math import sin, cos, tan, asin, acos, atan, log, log10, exp, sqrt, pi, e` (matnli §-1.8 da `len`).
   - BOSHQA HAMMA FUNKSIYA VA METODLAR QAT'IY TAQIQLANADI:
     `ord()`, `chr()`, `str()`, `min()`, `max()`, `sum()`, `pow()`, `round()`, `sorted()`, `list()`, `dict()`, `set()`, `map()`, `zip()`,
     `.append()`, `.split()`, `.join()`, `.replace()`, `.lower()`, `.upper()`, `.isdigit()`, `.isalpha()`, `.find()`, `.sort()`, `.pop()`,
     `def`, `class`, `lambda`, `break`, `continue`, `True`, `False`, `while True`.
3. MATN VA HARFLAR (§-1.8) UCHUN QOIDA:
   - `ord()` va `chr()` UMUMAN ISHLATMA!
   - Alifbo kerak bo'lsa: `A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"`, `a = "abcdefghijklmnopqrstuvwxyz"` deb yoz va sikl bilan `S[i] == A[j]` tekshirib, `A[(j + K) % 26]` ol.
   - Raqam tekshirish uchun `'0' <= S[i] <= '9'`, harf tekshirish uchun `'A' <= S[i] <= 'Z'` ishlat.
4. MASSIV VA MATRITSA:
   - Massiv: `a = [0] * n` (indeks bilan yoz). Matritsa: `A = [[0] * m for i in range(n)]`.
5. NAMUNALAR (AYNAN SHU USLUBDA YOZ):
   [§-1.1.13 namuna]
   a = float(input("a = "))
   b = float(input("b = "))
   c = float(input("c = "))
   d = float(input("d = "))
   s1 = (1 - (a + 2.9 * b)) * (1 - (a + 2.9 * b)) / (a * b - d - 1.45)
   s2 = ((c - a) / d) / (a * (b + c * c))
   s3 = a / (1 + 2 / c)
   s = s1 - s2 + s3
   print(s)

   [§-1.8.1 Sezar shifri namuna]
   N = int(input("N = "))
   S = input("S = ")
   K = int(input("K = "))
   A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
   a = "abcdefghijklmnopqrstuvwxyz"
   R = ""
   for i in range(N):
       c = S[i]
       for j in range(26):
           if S[i] == A[j]:
               c = A[(j + K) % 26]
           elif S[i] == a[j]:
               c = a[(j + K) % 26]
       R = R + c
   print(R)
6. KIRITISH VA CHIQARISH:
   - Har bir kiritiladigan qiymat albatta prompt bilan: `a = float(input("a = "))` yoki `n = int(input("n = "))`.
   - Agar masalada barcha sonlar aniq berilgan bo'lsa — input() ISHLATMA.
   - Natijani oddiy chiqar: `print(s)` yoki `print("Ha")` / `print("Yo'q")`.
7. TEZLIK VA XAVFSIZ TEST:
   - Cheksiz sikl yozma. `test_input` ga kichik va XATOSIZ (0 ga bo'linmaydigan, log/ildiz ichi musbat) qiymatlar ber.
8. Izohlar (#) YOZMA.
9. JSON: "explanation" (1-2 gap), "input_format", "test_input", "code_python".
"""


class AllProvidersFailedError(RuntimeError):
    """Barcha AI provayderlar (Groq va Gemini) javob bera olmaganda chiqadi."""
    pass


def _is_quota_error(err: Exception) -> bool:
    msg = str(err)
    return (
        "429" in msg
        or "RESOURCE_EXHAUSTED" in msg
        or "Quota exceeded" in msg
        or "rate_limit" in msg.lower()
    )


def _call_groq_once(api_key: str, model_name: str, user_prompt: str, force_json: bool = True) -> str:
    body_obj = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    if force_json:
        body_obj["response_format"] = {"type": "json_object"}

    payload = json.dumps(body_obj).encode("utf-8")
    req = urllib.request.Request(
        GROQ_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="ignore")[:240]
        except Exception:
            pass
        if e.code == 400 and force_json:
            return _call_groq_once(api_key, model_name, user_prompt, force_json=False)
        raise RuntimeError(f"Groq HTTP {e.code}: {err_body}")


def _call_ai(user_prompt: str) -> str:
    """Avval Groq (faol modellarni avto-aniqlab), u bo'lmasa Gemini ishlatadi."""
    global _groq_key_idx, _gemini_key_idx
    if not GROQ_API_KEYS and not _GEMINI_CLIENTS:
        raise AllProvidersFailedError("Render'da GROQ_API_KEY ham, GEMINI_API_KEY ham kiritilmagan.")

    diagnostics = []

    # 1) GROQ API
    if not GROQ_API_KEYS:
        diagnostics.append("Groq: kalit kiritilmagan")
    else:
        models = discover_groq_models()
        groq_errs = []
        for model_name in models:
            for step in range(len(GROQ_API_KEYS)):
                idx = (_groq_key_idx + step) % len(GROQ_API_KEYS)
                try:
                    text = _call_groq_once(GROQ_API_KEYS[idx], model_name, user_prompt)
                    _groq_key_idx = idx
                    return text
                except Exception as e:
                    short_e = "429 limit" if _is_quota_error(e) else str(e)[:120]
                    groq_errs.append(f"{model_name}({short_e})")
                    print(f"Groq o'tkazildi (kalit #{idx + 1}, {model_name}): {e}")
                    continue
        if groq_errs:
            diagnostics.append("Groq: " + "; ".join(groq_errs[:3]))

    # 2) GEMINI API (zaxira)
    if not _GEMINI_CLIENTS:
        diagnostics.append("Gemini: kalit kiritilmagan")
    else:
        full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"
        gemini_errs = []
        for model_name in GEMINI_MODELS:
            for step in range(len(_GEMINI_CLIENTS)):
                idx = (_gemini_key_idx + step) % len(_GEMINI_CLIENTS)
                client = _GEMINI_CLIENTS[idx]
                cfg = dict(
                    response_mime_type="application/json",
                    temperature=0.1,
                    max_output_tokens=8192,
                )
                if "2.5" in model_name and "lite" not in model_name:
                    try:
                        cfg["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=2048)
                    except Exception:
                        pass
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=full_prompt,
                        config=genai_types.GenerateContentConfig(**cfg)
                    )
                    _gemini_key_idx = idx
                    return resp.text
                except Exception as e:
                    short_e = "429 limit" if _is_quota_error(e) else str(e)[:100]
                    gemini_errs.append(f"{model_name}({short_e})")
                    print(f"Gemini o'tkazildi (kalit #{idx + 1}, {model_name}): {short_e}")
                    continue
        if gemini_errs:
            diagnostics.append("Gemini: " + "; ".join(gemini_errs[:3]))

    raise AllProvidersFailedError(" | ".join(diagnostics))


# ================= QAT'IY OQ RO'YXAT TEKSHIRUVI =================
ALLOWED_IMPORTS = {"math"}
ALLOWED_MATH_FUNCS = {"sin", "cos", "tan", "asin", "acos", "atan", "log", "log10", "exp", "sqrt", "fabs", "floor", "ceil"}
ALLOWED_BUILTINS = {"input", "print", "range", "int", "float", "abs"}
VAR_RE = re.compile(r"^[a-zA-Z]([0-9]{1,2}|[a-zA-Z0-9])?$")


def check_code_safety(code: str):
    tree = ast.parse(code)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for al in n.names:
                if al.name.split(".")[0] not in ALLOWED_IMPORTS:
                    raise ValueError(f"'{al.name}' kutubxonasi taqiqlangan, faqat math ruxsat etiladi")
        elif isinstance(n, ast.ImportFrom):
            if (n.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                raise ValueError(f"'{n.module}' kutubxonasi taqiqlangan, faqat math ruxsat etiladi")
        elif isinstance(n, ast.Attribute) and n.attr.startswith("__"):
            raise ValueError("maxsus (__) atributlar taqiqlangan")
    return tree


def _is_zero_matrix_comp(node: ast.ListComp) -> bool:
    if len(node.generators) != 1 or node.generators[0].ifs:
        return False
    elt = node.elt
    if isinstance(elt, ast.BinOp) and isinstance(elt.op, ast.Mult):
        return isinstance(elt.left, ast.List) or isinstance(elt.right, ast.List)
    return isinstance(elt, ast.List)


def _node_has_input(node) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "input":
            return True
    return False


def check_code_style(tree, sec: str, num: str):
    bad = set()
    allowed_calls = set(ALLOWED_BUILTINS) | set(ALLOWED_MATH_FUNCS)
    if sec == "1.8" or f"{sec}.{num}" == "5.1.31":
        allowed_calls.add("len")

    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Lambda, ast.GeneratorExp, ast.DictComp, ast.SetComp)):
            bad.add("def/class/lambda taqiqlangan")
        elif isinstance(n, ast.ListComp) and not _is_zero_matrix_comp(n):
            bad.add("list comprehension taqiqlangan (faqat matritsa e'loni [[0]*m for i in range(n)] ruxsat)")
        elif isinstance(n, (ast.Break, ast.Continue)):
            bad.add("break/continue o'rniga toza sikl sharti yoz")
        elif isinstance(n, ast.Constant) and isinstance(n.value, bool):
            bad.add("True/False o'rniga 1/0 ishlat")
        elif sec == "1.1" and isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow):
            bad.add("§-1.1 da darajaga ko'tarish (**) taqiqlangan, oddiy ko'paytirish (a*a, d*d*d) ishlat")
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            if not VAR_RE.match(n.id):
                bad.add(f"uzun o'zgaruvchi '{n.id}' taqiqlangan (faqat 1-2 harfli matematik nom ishlat)")
        elif isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                if f.id not in allowed_calls:
                    extra_tip = " (alifbo satri A='ABCDEFGHIJKLMNOPQRSTUVWXYZ' va sikl ishlat)" if f.id in {"ord", "chr"} else ""
                    bad.add(f"'{f.id}()' funksiyasi taqiqlangan{extra_tip}")
            elif isinstance(f, ast.Attribute):
                if not (isinstance(f.value, ast.Name) and f.value.id == "math" and f.attr in ALLOWED_MATH_FUNCS):
                    bad.add(f"'.{f.attr}()' metodi taqiqlangan, oddiy sikl va indeks ishlat")
            else:
                bad.add("murakkab funksiya chaqiruvi taqiqlangan")

    if sec in {"1.1", "1.2"}:
        allowed_vars = ({"a", "b", "c", "d"} if sec == "1.1" else {"x", "y", "z"}) | {
            "s", "s1", "s2", "s3", "s4", "s5"
        }
        calc_vars = []
        for st in tree.body:
            if isinstance(st, ast.Assign) and not _node_has_input(st.value):
                for tgt in st.targets:
                    if isinstance(tgt, ast.Name):
                        if tgt.id not in allowed_vars:
                            bad.add(f"ortiqcha '{tgt.id}' belgilashi taqiqlangan; faqat s1, s2, s3 va s ishlat")
                        if tgt.id in calc_vars:
                            bad.add(f"'{tgt.id}' ni qayta ishlatma, har bir kasr uchun alohida s1, s2, s3 yoz")
                        calc_vars.append(tgt.id)
        if len(calc_vars) < 2:
            bad.add("ifodani bitta s qatoriga tiqma; har bir asosiy kasrni s1, s2, s3 ga ajratib, oxirida s da jamla")
        elif len(calc_vars) > 6:
            bad.add("ortiqcha bo'laklarga ajratma; faqat asosiy kasrlar uchun s1, s2, s3 va yakuniy s yoz")

    if bad:
        raise ValueError("USLUB: " + "; ".join(sorted(bad)))


def code_has_input(tree) -> bool:
    return _node_has_input(tree)


def _run_sync(code: str, test_input: str):
    def limits():
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
        except Exception:
            pass
    return subprocess.run(
        [sys.executable, "-I", "-c", code],
        input=test_input, capture_output=True, text=True, timeout=10,
        preexec_fn=limits if os.name == "posix" else None,
    )


async def verify_run(code: str, test_input: str, has_input: bool):
    if has_input and not test_input.strip():
        return
    try:
        r = await asyncio.to_thread(_run_sync, code, test_input if has_input else "")
    except subprocess.TimeoutExpired:
        raise ValueError(
            "Dastur 10 soniyada tugamadi (cheksiz yoki sekin sikl). "
            "Samaraliroq algoritm ishlat yoki test_input ni kichikroq ol."
        )
    if r.returncode != 0:
        last = (r.stderr.strip().splitlines() or ["noma'lum xato"])[-1]
        if has_input and last.startswith(("EOFError", "ValueError")):
            return
        raise ValueError(f"Dastur ishlaganda xato chiqdi: {last}")
    if not r.stdout.strip():
        raise ValueError("Dastur hech narsa chiqarmadi (print yo'q)")


async def generate_flowchart_ast(sec: str, num: str, force: bool = False) -> dict:
    cache_key = f"{sec}_{num}"
    lock = _PROBLEM_LOCKS.setdefault(cache_key, asyncio.Lock())

    async with lock:
        prob_text = PROBLEMS_DB.get(sec, {}).get(num, f"§-{sec} bo'lim, {num}-masala.")

        if not force:
            if cache_key in FLOWCHART_CACHE:
                return FLOWCHART_CACHE[cache_key]
            cached = SOLUTIONS_DB.get(cache_key)
            if cached:
                try:
                    built = build_result_from_cached(sec, num, cached, prob_text)
                    if built:
                        FLOWCHART_CACHE[cache_key] = built
                        return built
                except Exception as e:
                    print(f"Keshdagi yechimda xato ({cache_key}): {e}")

        hint = HINTS.get(f"{sec}.{num}")
        user_prompt = (
            f"Bo'lim: {SECTION_NAMES.get(sec, sec)}\n"
            f"Masala #{num}: {prob_text}\n"
        )
        if hint:
            user_prompt += (
                f"\nYO'L-YO'RIQ (g'oyani ol, lekin ord/chr/.append va uzun nomlar ishlatma, "
                f"faqat masaladagi harflar hamda s, k, i, j, a[k] bilan yoz): {hint}\n"
            )

        last_err = None
        extra = ""
        result = None
        clean_candidate = None

        for attempt in range(4):
            try:
                raw_text = await asyncio.wait_for(
                    asyncio.to_thread(_call_ai, user_prompt + extra), timeout=65
                )
                data = json.loads(clean_json_text(raw_text))
                if isinstance(data, list) and data:
                    data = data[0]
                if not isinstance(data, dict):
                    raise ValueError("AI noto'g'ri formatda javob qaytardi")

                code = str(data.get("code_python", "")).replace("\r\n", "\n").strip("\n")
                if not code.strip():
                    raise ValueError("AI kod qaytarmadi")
                code = ensure_input_prompts(code)

                tree = check_code_safety(code)
                nodes = code_to_nodes(code)
                if not nodes:
                    raise ValueError("Koddan blok-sxema qurib bo'lmadi")

                validate_flowchart_nodes(nodes)

                test_input = str(data.get("test_input", "") or "").replace("\\n", "\n")
                if test_input and not test_input.endswith("\n"):
                    test_input += "\n"

                await verify_run(code, test_input, code_has_input(tree))

                cand = {
                    "title": f"{SECTION_NAMES.get(sec, sec)}. {num}-masala",
                    "explanation": data.get("explanation", ""),
                    "input_format": data.get("input_format", ""),
                    "sample_input": test_input.strip("\n"),
                    "code_python": code,
                    "nodes": nodes,
                    "problem_text": prob_text,
                }
                clean_candidate = cand

                check_code_style(tree, sec, num)

                result = cand
                break
            except AllProvidersFailedError as e:
                last_err = e
                print(f"Barcha AI provayderlar ishlamadi: {e}")
                break
            except Exception as e:
                last_err = e
                print(f"Generatsiya xatosi (urinish {attempt + 1}): {e}")
                extra = (
                    f"\nOLDINGI JAVOBDA XATO BO'LDI: {e}\n"
                    f"Xatoni 100% tuzat: ord/chr/metodlar va ortiqcha o'zgaruvchilarsiz toza matematik kod qaytar.\n"
                )
                await asyncio.sleep(0.8)

        if result is None and clean_candidate is not None:
            result = clean_candidate

        if result is None:
            if isinstance(last_err, AllProvidersFailedError):
                raise RuntimeError(f"AI ulanish xatosi: {last_err}")
            raise RuntimeError(f"Toza blok-sxema yaratib bo'lmadi (qayta urining): {last_err}")

        FLOWCHART_CACHE[cache_key] = result
        save_solution_to_disk(cache_key, result)
        return result


# ================= MINI APP HTML =================
INDEX_PATH = os.path.join(BASE_DIR, "index.html")


def load_index_html() -> str:
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h3>index.html topilmadi. Uni bot.py bilan bir papkaga qo'ying.</h3>"


INDEX_HTML = load_index_html()


# ================= TELEGRAM BOT HANDLERLARI =================
def get_sections_keyboard():
    builder = InlineKeyboardBuilder()
    for code, title in SECTION_NAMES.items():
        builder.button(text=f"📂 {title}", callback_data=f"sec:{code}")
    builder.button(
        text="🚀 Mini Appni to'liq ochish",
        web_app=WebAppInfo(url=f"{WEBAPP_URL}/")
    )
    builder.adjust(1)
    return builder.as_markup()


def get_problems_keyboard(sec: str):
    builder = InlineKeyboardBuilder()
    probs = PROBLEMS_DB.get(sec, {})
    nums = sorted(probs.keys(), key=lambda x: int(x)) if probs else [str(i) for i in range(1, 26)]

    for n in nums:
        builder.button(text=f"📌 #{n}", callback_data=f"prob:{sec}:{n}")
    builder.adjust(5)
    builder.row(types.InlineKeyboardButton(text="⬅️ Bo'limlarga qaytish", callback_data="back:sections"))
    return builder.as_markup()


async def safe_edit(callback: types.CallbackQuery, text: str, markup):
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        print(f"edit_text xatosi: {e}")


def get_admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Yangilash", callback_data="adm:stats")
    builder.button(text="👥 Oxirgi 20 foydalanuvchi", callback_data="adm:recent")
    builder.button(text="🏆 Eng faol 10 ta", callback_data="adm:top")
    builder.button(text="📥 Excel (CSV) yuklab olish", callback_data="adm:export")
    bell = "🔔 Har ko'rishda xabar: YOQILGAN" if NOTIFY_ALL_VIEWS else "🔕 Har ko'rishda xabar: O'CHIRILGAN"
    builder.button(text=bell, callback_data="adm:toggle_views")
    builder.adjust(1)
    return builder.as_markup()


def format_admin_stats_text() -> str:
    st = get_admin_stats()
    top_lines = "\n".join(
        f"   • <b>{_html_esc(p)}</b> — {c} marta" for p, c in st["top_problems"]
    ) or "   • Hali ma'lumot yo'q"
    return (
        f"📊 <b>Bot statistikasi (Admin panel)</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{st['total_users']}</b>\n"
        f"🆕 Bugun qo'shilganlar: <b>{st['new_today']}</b>\n"
        f"🟢 Bugun faol bo'lganlar: <b>{st['active_today']}</b>\n"
        f"📈 Jami ko'rilgan blok-sxemalar: <b>{st['total_views']}</b>\n"
        f"⚡ Bugun ko'rilganlar: <b>{st['views_today']}</b>\n"
        f"💾 Keshdagi tayyor masalalar: <b>{len(SOLUTIONS_DB)}</b>\n\n"
        f"🔥 <b>Eng ko'p ko'rilgan masalalar:</b>\n{top_lines}\n\n"
        f"🕒 Vaqt: {_now_uz()}"
    )


def format_users_text(rows: list, title: str) -> str:
    if not rows:
        return f"<b>{title}</b>\n\nHali foydalanuvchilar yo'q."
    lines = [f"<b>{title}</b>\n"]
    for idx, (uid, uname, fname, fseen, lseen, tviews, lprob) in enumerate(rows, 1):
        safe_name = _html_esc(fname or f"User {uid}")
        u_txt = f" @{_html_esc(uname)}" if uname else ""
        p_txt = f" | oxirgi: {_html_esc(lprob)}" if lprob else ""
        short_time = (lseen or "")[5:16]
        lines.append(
            f"{idx}. <a href=\"tg://user?id={uid}\">{safe_name}</a>{u_txt}\n"
            f"    🆔 <code>{uid}</code> | 👁 {tviews}{p_txt} | 🕒 {short_time}"
        )
    text = "\n".join(lines)
    return text[:3950] + "\n..." if len(text) > 3950 else text


@dp.message(Command("myid"))
async def cmd_myid(message: types.Message):
    u = message.from_user
    await message.answer(
        f"🆔 Sizning Telegram ID raqamingiz: <code>{u.id}</code>\n"
        f"Admin bo'lish uchun Render → Environment bo'limida:\n"
        f"<code>ADMIN_IDS</code> = <code>{u.id}</code> deb saqlang.",
        parse_mode="HTML"
    )


@dp.message(Command("admin", "stats"))
async def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Bu buyruq faqat admin uchun.")
        return
    await message.answer(format_admin_stats_text(), reply_markup=get_admin_keyboard(), parse_mode="HTML")


@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Bu buyruq faqat admin uchun.")
        return
    rows = get_users_list("last_seen", 20)
    await message.answer(format_users_text(rows, "👥 Oxirgi 20 ta foydalanuvchi"), parse_mode="HTML")


@dp.message(Command("export"))
async def cmd_export(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Bu buyruq faqat admin uchun.")
        return
    csv_bytes = build_users_csv_bytes()
    fname = f"foydalanuvchilar_{_today_uz()}.csv"
    await message.answer_document(
        BufferedInputFile(csv_bytes, filename=fname),
        caption=f"📥 Barcha foydalanuvchilar ro'yxati ({_now_uz()})"
    )


@dp.callback_query(F.data.startswith("adm:"))
async def cb_admin(callback: types.CallbackQuery):
    global NOTIFY_ALL_VIEWS
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo'q", show_alert=True)
        return
    action = callback.data.split(":")[1]
    if action == "stats":
        await callback.answer("Yangilandi")
        await safe_edit(callback, format_admin_stats_text(), get_admin_keyboard())
    elif action == "recent":
        await callback.answer()
        rows = get_users_list("last_seen", 20)
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ Statistikaga qaytish", callback_data="adm:stats")
        await safe_edit(callback, format_users_text(rows, "👥 Oxirgi 20 ta foydalanuvchi"), builder.as_markup())
    elif action == "top":
        await callback.answer()
        rows = get_users_list("total_views", 10)
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ Statistikaga qaytish", callback_data="adm:stats")
        await safe_edit(callback, format_users_text(rows, "🏆 Eng faol 10 ta foydalanuvchi"), builder.as_markup())
    elif action == "toggle_views":
        NOTIFY_ALL_VIEWS = not NOTIFY_ALL_VIEWS
        state = "yoqildi" if NOTIFY_ALL_VIEWS else "o'chirildi"
        await callback.answer(f"Har ko'rishda xabar berish {state}")
        await safe_edit(callback, format_admin_stats_text(), get_admin_keyboard())
    elif action == "export":
        await callback.answer("Fayl tayyorlanmoqda...")
        csv_bytes = build_users_csv_bytes()
        fname = f"foydalanuvchilar_{_today_uz()}.csv"
        await callback.message.answer_document(
            BufferedInputFile(csv_bytes, filename=fname),
            caption=f"📥 Barcha foydalanuvchilar ro'yxati ({_now_uz()})"
        )


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    u = message.from_user
    if u:
        track_activity_bg(u.id, u.username or "", u.full_name or "", source="bot")
    await message.answer(
        "📐 <b>Blok-Sxema va Python Kod Generator Boti</b>\n\n"
        "Kitobdagi (I va V BOB) barcha masalalarning toza blok-sxemasini va sodda matematik Python kodini ko'rish uchun bo'limni tanlang:",
        reply_markup=get_sections_keyboard(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "back:sections")
async def cb_back_sections(callback: types.CallbackQuery):
    await callback.answer()
    await safe_edit(callback, "📐 <b>Kerakli bo'limni tanlang:</b>", get_sections_keyboard())


@dp.callback_query(F.data.startswith("sec:"))
async def cb_section(callback: types.CallbackQuery):
    await callback.answer()
    sec = callback.data.split(":")[1]
    title = SECTION_NAMES.get(sec, sec)
    await safe_edit(
        callback,
        f"📂 <b>{title}</b>\n\nBlok-sxemasini chizish uchun masala raqamini tanlang:",
        get_problems_keyboard(sec)
    )


@dp.callback_query(F.data.startswith("prob:"))
async def cb_problem(callback: types.CallbackQuery):
    await callback.answer()
    _, sec, num = callback.data.split(":")
    u = callback.from_user
    if u:
        track_activity_bg(u.id, u.username or "", u.full_name or "", problem=f"{sec} #{num}", is_view=False, source="bot")
    prob_text = PROBLEMS_DB.get(sec, {}).get(num, "Masala matni yuklanmoqda...")
    if len(prob_text) > 900:
        prob_text = prob_text[:900] + "..."
    prob_text = prob_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    builder = InlineKeyboardBuilder()
    builder.button(
        text="📊 Blok-Sxema va Kodni Ochish",
        web_app=WebAppInfo(url=f"{WEBAPP_URL}/?sec={sec}&num={num}")
    )
    builder.button(text="⬅️ Masalalarga qaytish", callback_data=f"sec:{sec}")
    builder.adjust(1)

    await safe_edit(
        callback,
        f"📘 <b>{SECTION_NAMES.get(sec)} | {num}-masala</b>\n\n"
        f"📝 <i>{prob_text}</i>\n\n"
        f"👇 Quyidagi tugma orqali masalaning <b>Blok-sxemasi</b> va <b>Python kodini</b> oching:",
        builder.as_markup()
    )


# ================= WEB SERVER =================
async def handle_index(request):
    return web.Response(
        text=INDEX_HTML,
        content_type="text/html",
        headers={"Cache-Control": "no-store"}
    )


async def handle_health(request):
    return web.Response(text="OK")


async def handle_status(request):
    if GROQ_API_KEYS and not _groq_discovered:
        await asyncio.to_thread(discover_groq_models)
    return web.json_response({
        "groq_keys": len(GROQ_API_KEYS),
        "groq_models": GROQ_MODELS,
        "gemini_keys": len(_GEMINI_CLIENTS),
        "gemini_models": GEMINI_MODELS,
        "cached_solutions": len(SOLUTIONS_DB),
        "total_problems": sum(len(v) for v in PROBLEMS_DB.values()),
        "admins_configured": len(ADMIN_IDS),
    })


async def handle_api_problems(request):
    return web.json_response({"sections": SECTION_NAMES, "problems": PROBLEMS_DB})


async def handle_api_flowchart(request):
    sec = request.query.get("sec", "1.1")
    num = request.query.get("num", "1")
    force = request.query.get("force", "0") == "1"
    uid_raw = (request.query.get("uid") or "").strip()
    if uid_raw.isdigit():
        uname = (request.query.get("uname") or "").strip()[:64]
        fname = (request.query.get("fname") or "").strip()[:120]
        track_activity_bg(int(uid_raw), uname, fname, problem=f"{sec} #{num}", is_view=True, source="webapp")
    try:
        data = await generate_flowchart_ast(sec, num, force=force)
        return web.json_response({"status": "ok", "data": data})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def main():
    init_users_db()
    load_problems()
    load_solutions_cache()
    print(f"Admin IDs: {sorted(ADMIN_IDS) if ADMIN_IDS else 'sozlanmagan (Render da ADMIN_IDS ni kiriting)'}")
    if GROQ_API_KEYS:
        await asyncio.to_thread(discover_groq_models)
    print(
        f"Groq kalitlar: {len(GROQ_API_KEYS)} ta ({GROQ_MODELS}) | "
        f"Gemini kalitlar: {len(_GEMINI_CLIENTS)} ta ({GEMINI_MODELS})"
    )

    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/problems", handle_api_problems)
    app.router.add_get("/api/flowchart", handle_api_flowchart)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Web-server http://0.0.0.0:{PORT} da ishga tushdi! WEBAPP_URL: {WEBAPP_URL}")

    while True:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
            break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Polling xatosi: {type(e).__name__}: {e}. 10 soniyadan keyin qayta uriniladi...")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
