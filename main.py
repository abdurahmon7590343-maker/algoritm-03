import os
import re
import json
import asyncio
import fitz  # PyMuPDF
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import WebAppInfo
from google import genai
from google.genai import types as genai_types
from flowchart_builder import code_to_nodes

# ================= RENDER VA MUHIT SOZLAMALARI =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "BOT_TOKENINGIZNI_SHU_YERGA_YOZING")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "GEMINI_API_KEYINGIZNI_SHU_YERGA_YOZING")

WEBAPP_URL = (
    os.getenv("WEBAPP_URL")
    or os.getenv("RENDER_EXTERNAL_URL")
    or "https://algoritm-03.onrender.com"
).rstrip("/")

PDF_PATH = os.getenv("PDF_PATH", "BLACKCURSE.pdf")
PORT = int(os.getenv("PORT", 8080))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

gemini_client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={"api_version": "v1beta"}
)

PROBLEMS_DB = {}
FLOWCHART_CACHE = {}

SECTION_NAMES = {
    "5.1": "§-5.1. Butun sonli masalalar",
    "5.2": "§-5.2. Sanoq sistemalari",
    "5.3": "§-5.3. Geometriya",
    "5.4": "§-5.4. Massivlarni tartiblash",
    "5.5": "§-5.5. Ko'phadlar bilan ishlash",
    "5.6": "§-5.6. Matrisalarni tuzish",
    "5.7": "§-5.7. Matrisalar algebrasi"
}

# ================= PDF PARSER =================
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
            prob_text = sec_body[p_end:next_start].strip()
            prob_text = re.sub(r'\s+', ' ', prob_text)
            PROBLEMS_DB[sec_code][str(p_num)] = prob_text

    print(f"PDF muvaffaqiyatli o'qildi! Bo'limlar soni: {len(PROBLEMS_DB)}")

# ================= AI GENERATOR =================
def clean_json_text(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()

# AI faqat Python kodi va tushuntirish yozadi. Blok-sxema shu koddan
# flowchart_builder.code_to_nodes() yordamida aniq quriladi.
SYSTEM_PROMPT = """
Sen universitet talabalari uchun eng sodda, odamdek tushunarli Python dasturlarini yozuvchi ustozsan.
Berilgan masalani yechadigan dastur yoz va faqat sof JSON qaytar:
{"explanation": "...", "code_python": "..."}

QAT'IY QOIDALAR:
1. Dastur TO'LIQ bo'lsin: kiritish (input), hisoblash va chiqarish (print) hammasi bo'lsin. Masala shartini to'liq yech.
2. FAQAT bitta oddiy dastur: funksiyalar (def), klasslar, kutubxonalar (import), list comprehension, lambda, ichma-ich yozuvlar ISHLATMA.
   Faqat oddiy for / while / if / elif / else, o'zlashtirish va print ishlat.
3. O'ZGARUVCHILAR: qisqa matematik 1 harfli nomlar: n, m, k, s, i, j, a, b, c, x, y, R. Inglizcha uzun nomlar (count, result, max_value) TAQIQLANADI.
4. Kiritish: `n = int(input())` yoki `a = list(map(int, input().split()))` ko'rinishida, prompt matnisiz.
5. Massivlar uchun oddiy sikllar ishlat (sort(), sorted(), sum(), max() kabi tayyor funksiyalarsiz, algoritmni o'zing sikl bilan yoz).
   Matrisa uchun: `a = []` va ichma-ich for bilan to'ldirish.
6. Izohlar (#) kerak emas.
7. print da natija o'zgaruvchilarini chiqar: `print(s)` yoki `print("Natija:", s)`.
8. "explanation": 1-3 gapli sodda o'zbekcha tushuntirish (algoritm g'oyasi).
"""

def _call_gemini(prompt: str):
    cfg = dict(
        response_mime_type="application/json",
        temperature=0.2,
        max_output_tokens=8192,
    )
    try:
        cfg["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=1024)
    except Exception:
        pass
    return gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(**cfg)
    )

async def generate_flowchart_ast(sec: str, num: str) -> dict:
    cache_key = f"{sec}_{num}"
    if cache_key in FLOWCHART_CACHE:
        return FLOWCHART_CACHE[cache_key]

    prob_text = PROBLEMS_DB.get(sec, {}).get(num, f"§-{sec} bo'lim, {num}-masala.")
    base_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Bo'lim: {SECTION_NAMES.get(sec, sec)}\n"
        f"Masala #{num}: {prob_text}\n"
    )

    last_err = None
    extra = ""
    result = None
    for attempt in range(3):
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(_call_gemini, base_prompt + extra), timeout=75
            )
            data = json.loads(clean_json_text(response.text))
            if isinstance(data, list) and data:
                data = data[0]
            if not isinstance(data, dict):
                raise ValueError("AI noto'g'ri formatda javob qaytardi")

            code = str(data.get("code_python", "")).replace("\r\n", "\n").strip("\n")
            if not code.strip():
                raise ValueError("AI kod qaytarmadi")

            nodes = code_to_nodes(code)          # sintaksis xato bo'lsa SyntaxError beradi
            if not nodes:
                raise ValueError("Koddan blok-sxema qurib bo'lmadi")

            result = {
                "title": f"{SECTION_NAMES.get(sec, sec)}. {num}-masala",
                "explanation": data.get("explanation", ""),
                "code_python": code,
                "nodes": nodes,
                "problem_text": prob_text,
            }
            break
        except Exception as e:
            last_err = e
            print(f"Generatsiya xatosi (urinish {attempt + 1}): {e}")
            extra = (
                f"\nOLDINGI JAVOBDA XATO BO'LDI: {e}\n"
                f"Qoidalarga qat'iy amal qilib, to'g'ri JSON va ishlaydigan kodni qaytar.\n"
            )
            await asyncio.sleep(1.0)

    if result is None:
        raise RuntimeError(f"AI to'g'ri javob bera olmadi: {last_err}")

    FLOWCHART_CACHE[cache_key] = result
    return result

# ================= MINI APP HTML (index.html fayldan o'qiladi) =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
    nums = sorted(probs.keys(), key=lambda x: int(x)) if probs else [str(i) for i in range(1, 33)]

    for n in nums:
        builder.button(text=f"📌 #{n}", callback_data=f"prob:{sec}:{n}")
    builder.adjust(5)
    builder.row(types.InlineKeyboardButton(text="⬅️ Bo'limlarga qaytish", callback_data="back:sections"))
    return builder.as_markup()

async def safe_edit(callback: types.CallbackQuery, text: str, markup):
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        # masalan, "message is not modified"
        print(f"edit_text xatosi: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "📐 <b>Blok-Sxema va Python Kod Generator Boti</b>\n\n"
        "Kitobdagi (V BOB) barcha masalalarning toza o'zbekcha blok-sxemasini va sodda Python kodini ko'rish uchun bo'limni tanlang:",
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
    prob_text = PROBLEMS_DB.get(sec, {}).get(num, "Masala matni yuklanmoqda...")
    if len(prob_text) > 900:
        prob_text = prob_text[:900] + "..."
    # HTML belgilarini xavfsiz qilish
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

async def handle_api_problems(request):
    return web.json_response({"sections": SECTION_NAMES, "problems": PROBLEMS_DB})

async def handle_api_flowchart(request):
    sec = request.query.get("sec", "5.1")
    num = request.query.get("num", "1")
    force = request.query.get("force", "0")
    if force == "1":
        FLOWCHART_CACHE.pop(f"{sec}_{num}", None)
    try:
        data = await generate_flowchart_ast(sec, num)
        return web.json_response({"status": "ok", "data": data})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def main():
    load_problems_from_pdf(PDF_PATH)

    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/problems", handle_api_problems)
    app.router.add_get("/api/flowchart", handle_api_flowchart)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Web-server http://0.0.0.0:{PORT} da ishga tushdi! WEBAPP_URL: {WEBAPP_URL}")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
