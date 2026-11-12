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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# v1beta API versiyasini majburiy ko'rsatamiz
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
        print(f"DIQQAT: {pdf_path} topilmadi! Standart holatda ishlaydi.")
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

# ================= AI GENERATOR (FLOWGORITHM DARAJASIDA) =================
SYSTEM_PROMPT = """
Sen Flowgorithm dasturi uchun xatosiz blok-sxema (AST daraxt) tuzuvchi algoritmik dvijoksan.
Berilgan matematik/algoritmik masala uchun Flowgorithm qoidalariga 100% mos sof JSON qaytar (markdown ```json belgisiz).

QAT'IY QOIDALAR:
1. O'zgaruvchilar ishlatilishidan oldin "declare" blokida e'lon qilinishi shart (Masalan: "Butun son: n, i, s").
2. Kiritish bloki ("input"): faqat masala shartida berilgan kiruvchi o'zgaruvchilar (Masalan: "Kiritish: n").
3. O'zlashtirish bloki ("assign"): matematik ifodalar aniq ko'rsatilsin (Masalan: "s = 0", "i = 1").
4. Sikl bloki ("while" yoki "for"): "condition" maydonida aniq shart bo'lsin (Masalan: "i <= n"), "body" massivida sikl ichidagi qadamlar bo'lsin. Sikl oxirida qadam o'zgarishi ("i = i + 1") unutib qoldirilmasin!
5. Tarmoqlanish ("if"): "condition" maydonida shart (Masalan: "a^2 + b^2 == c^2"), "trueBranch" (Ha) va "falseBranch" (Yo'q) massivlari bo'lsin.
6. Chiqarish ("output"): natijani ekranga chiqarish (Masalan: "Chiqarish: a, b, c").

JSON FORMATI:
{
  "title": "§-5.x. y-masala",
  "explanation": "Algoritmning qisqacha matematik mohiyati (1-2 gap)",
  "code_python": "Masalaning toza Python kodi",
  "nodes": [
    {"type": "declare", "text": "Butun son: n, i"},
    {"type": "input", "text": "Kiritish: n"},
    {"type": "assign", "text": "i = 1"},
    {
      "type": "while",
      "condition": "i <= n",
      "body": [
        {
          "type": "if",
          "condition": "i % 2 == 0",
          "trueBranch": [{"type": "output", "text": "Chiqarish: i"}],
          "falseBranch": []
        },
        {"type": "assign", "text": "i = i + 1"}
      ]
    }
  ]
}
"""

def clean_json_text(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()

async def generate_flowchart_ast(sec: str, num: str) -> dict:
    cache_key = f"{sec}_{num}"
    if cache_key in FLOWCHART_CACHE:
        return FLOWCHART_CACHE[cache_key]

    prob_text = PROBLEMS_DB.get(sec, {}).get(num, f"§-{sec} bo'lim, {num}-masala.")
    full_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Bo'lim: {SECTION_NAMES.get(sec, sec)}\n"
        f"Masala #{num}: {prob_text}\n\n"
        f"Ushbu masalaning to'liq, xatosiz Flowgorithm blok-sxema JSON strukturasini qaytar:"
    )

    response = await asyncio.to_thread(
        gemini_client.models.generate_content,
        model="gemini-2.5-flash",
        contents=full_prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1
        )
    )
    cleaned = clean_json_text(response.text)
    data = json.loads(cleaned)
    data["problem_text"] = prob_text
    FLOWCHART_CACHE[cache_key] = data
    return data

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

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "📐 <b>Flowgorithm Blok-Sxema Generator Boti</b>\n\n"
        "Kitobdagi (V BOB) barcha masalalarning xatosiz, interaktiv Flowgorithm blok-sxemasini va Python kodini ko'rish uchun bo'limni tanlang:",
        reply_markup=get_sections_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "back:sections")
async def cb_back_sections(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📐 <b>Kerakli bo'limni tanlang:</b>",
        reply_markup=get_sections_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("sec:"))
async def cb_section(callback: types.CallbackQuery):
    sec = callback.data.split(":")[1]
    title = SECTION_NAMES.get(sec, sec)
    await callback.message.edit_text(
        f"📂 <b>{title}</b>\n\nBlok-sxemasini chizish uchun masala raqamini tanlang:",
        reply_markup=get_problems_keyboard(sec),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("prob:"))
async def cb_problem(callback: types.CallbackQuery):
    _, sec, num = callback.data.split(":")
    prob_text = PROBLEMS_DB.get(sec, {}).get(num, "Masala matni yuklanmoqda...")

    builder = InlineKeyboardBuilder()
    builder.button(
        text="📊 Flowgorithm Blok-Sxemani Ochish",
        web_app=WebAppInfo(url=f"{WEBAPP_URL}/?sec={sec}&num={num}")
    )
    builder.button(text="⬅️ Masalalarga qaytish", callback_data=f"sec:{sec}")
    builder.adjust(1)

    await callback.message.edit_text(
        f"📘 <b>{SECTION_NAMES.get(sec)} | {num}-masala</b>\n\n"
        f"📝 <i>{prob_text}</i>\n\n"
        f"👇 Quyidagi interaktiv tugma orqali masalaning <b>Flowgorithm</b> blok-sxemasini oching:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# ================= WEB SERVER (MINI APP API) =================
async def handle_index(request):
    return web.FileResponse("index.html")

async def handle_health(request):
    return web.Response(text="OK")

async def handle_api_problems(request):
    return web.json_response({"sections": SECTION_NAMES, "problems": PROBLEMS_DB})

async def handle_api_flowchart(request):
    sec = request.query.get("sec", "5.1")
    num = request.query.get("num", "1")
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
