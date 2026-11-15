import os
import re
import json
import asyncio
import ast
import sys
import subprocess
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
HINTS = {}
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

# ================= MASALALARNI YUKLASH =================
PROBLEMS_JSON = os.getenv("PROBLEMS_JSON", "problems.json")

def load_problems():
    """Avval tozalangan problems.json dan o'qiydi (PDF'dagi formulalar buzilib chiqadi),
    u bo'lmasa PDF'dan o'qishga urinadi."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = PROBLEMS_JSON if os.path.isabs(PROBLEMS_JSON) else os.path.join(base, PROBLEMS_JSON)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            HINTS.update(data.pop("_hints", {}) or {})
            for sec, probs in data.items():
                PROBLEMS_DB[sec] = {str(k): v for k, v in probs.items()}
            print(f"problems.json o'qildi: {sum(len(v) for v in PROBLEMS_DB.values())} ta masala, {len(HINTS)} ta ko'rsatma")
            return
        except Exception as e:
            print(f"problems.json o'qishda xato: {e}. PDF ishlatiladi.")
    load_problems_from_pdf(PDF_PATH)

# ================= AI GENERATOR =================
def clean_json_text(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()

# AI faqat Python kodi va tushuntirish yozadi. Blok-sxema shu koddan
# flowchart_builder.code_to_nodes() yordamida aniq quriladi.
SYSTEM_PROMPT = r"""
Sen universitet talabalari uchun Flowgorithm blok-sxemasiga aynan mos keladigan, eng sodda Python dasturlarini yozuvchi ustozsan.
Berilgan masalani TO'G'RI va TEZ ishlaydigan qilib yechadigan dastur yoz va faqat sof JSON qaytar:
{"explanation": "...", "input_format": "...", "test_input": "...", "code_python": "..."}

MASALA MATNIDAGI BELGILAR: ^ — daraja (2^200 = 2 ning 200-darajasi), _ yoki pastki indeks — indeks (a_i, d₀),
n! — faktorial, ≤ ≥ — taqqoslash. Masala shartini ehtiyotkorlik bilan o'qi va to'liq yech.

QAT'IY QOIDALAR:
1. Dastur TO'LIQ bo'lsin: kiritish, hisoblash va chiqarish (print). Masalaning BARCHA bandlarini (a, b, c ...) bajar.
2. HAR BIR QATORDA FAQAT BITTA AMAL (blok-sxemadagi bitta blok kabi): bitta input, bitta o'zlashtirish, bitta print.
   Ruxsat: oddiy for / while / if / elif / else, o'zlashtirish (=, +=), arifmetika (+ - * / // % **), taqqoslash, and/or/not, print, input, int(), float().
   TAQIQ: def, class, lambda, list comprehension, kesim (a[::-1], a[1:3]), `a, b = b, a` kabi bir vaqtdagi o'zlashtirish,
   `a = b = 0` kabi zanjirli o'zlashtirish, str() bilan raqamlarni ajratish, .split(), list(map(...)), True/False, while True,
   .append (faqat matritsa satrini e'lon qilishdan tashqari), len(), sum(), max(), min(), sort(), sorted(), range ichida murakkab ifoda.
   Qiymatlarni almashtirish uchun qo'shimcha o'zgaruvchi ishlat: t = a, a = b, b = t (har biri alohida qatorda).
   Mantiqiy belgi (flag) uchun True/False o'rniga 1 va 0 ishlat. Cheksiz sikl o'rniga shart bilan while yoz.
3. KUTUBXONA: odatda import KERAK EMAS. Faqat zarur bo'lsa (sin, cos, sqrt, pi, acos kabilar uchun) `from math import ...` ishlat.
4. O'ZGARUVCHILAR: qisqa matematik nomlar: n, m, k, s, i, j, a, b, c, d, t, x, y, p, q, R, A, B. Inglizcha uzun nomlar (count, result, max_value) TAQIQLANADI.
5. KIRITISH: HAR BIR qiymat ALOHIDA input() bilan va albatta qisqa YOZUV (prompt) bilan kiritiladi, aks holda dastur jim turib qolgandek ko'rinadi:
   `n = int(input("n = "))`, `x = float(input("x = "))`.
   MASSIV: avval e'lon qil `a = [0] * n`, so'ng sikl bilan element-element kirit:
      for i in range(n):
          a[i] = int(input("a[i] = "))
   MATRITSA: avval `a = []`, `for i in range(n): a.append([0] * m)` bilan e'lon qil, so'ng ichma-ich for bilan:
          a[i][j] = float(input("a[i][j] = "))
   Massiv/matritsani chiqarish ham sikl bilan, element-element: print(a[i]) yoki print(a[i][j]).
   Agar masalada berilgan qiymat YO'Q bo'lsa (masalan, oraliq aniq berilgan: [200,300], uch xonali sonlar, 7 gacha maxraj) — input ISHLATMA, to'g'ridan-to'g'ri hisobla.
   «Fayl» (f, g, h fayllar) so'zi bo'lsa — fayl o'rniga oddiy massiv ishlat.
   Ko'phad: koeffitsientlar massivi sifatida element-element kirit.
6. RAQAMLAR bilan ishlash (palindrom, raqamlar yig'indisi, teskari son, sanoq sistemasi): faqat `x % 10` (oxirgi raqam) va `x // 10` (oxirgi raqamni olib tashlash) bilan, sikl ichida.
7. KATTA SONLAR: Python butun sonlari cheksiz: 2**200, 3**2022 ni to'g'ridan-to'g'ri hisoblash mumkin va raqamlarini % 10, // 10 bilan ajratish mumkin; 100! ni sikl bilan ko'paytirib hisobla.
8. Massivlarni tartiblash, yig'indi, maksimum kabilarni tayyor funksiyalarsiz o'zing sikl bilan yoz. Matrisa ko'paytirish, transponirlash, daraja va h.k. ichma-ich for bilan yoz.
9. TEZLIK: hech qachon cheksiz yoki soatlab ishlaydigan dastur yozma. Chegaralar katta bo'lsa (10^15, 2·10^9, 10^7) to'g'ridan-to'g'ri sikl YOZMA:
   davr topish, binar qidiruv, tez daraja, dinamik dasturlash kabi samarali usul ishlat. Har bir while sikli albatta tugasin.
10. Izohlar (#) kerak emas. print da natijani tushunarli chiqar: `print("Natija:", s)`. "Mumkinmi? / bormi? / mavjudmi?" masalalarida print("Ha") yoki print("Yo'q").
11. Rasmga bog'liq bandlar masala matnida so'z bilan tushuntirilgan, shunga amal qil.
12. Agar «YO'L-YO'RIQ» berilgan bo'lsa — aynan shu usulga amal qil (lekin yuqoridagi taqiqlarga ham amal qil).
13. JSON maydonlari:
    "explanation": 1-3 gapli sodda o'zbekcha tushuntirish (algoritm g'oyasi);
    "input_format": nimalarni qaysi tartibda kiritish kerakligi (o'zbekcha, qisqa; kiritish bo'lmasa «Kiritish kerak emas»);
    "test_input": dasturni sinash uchun TO'G'RI namuna kiritish: HAR BIR input() uchun alohida qiymat, qiymatlar \n bilan ajratilgan.
      Skalyar parametrlarni masaladagi eng katta chegaraga yaqin ol (massiv/matritsa kichik bo'lsin). Kiritish bo'lmasa bo'sh satr "".
"""

def _call_gemini(prompt: str):
    cfg = dict(
        response_mime_type="application/json",
        temperature=0.1,
        max_output_tokens=8192,
    )
    try:
        cfg["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=4096)
    except Exception:
        pass
    return gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(**cfg)
    )


# ================= KODNI TEKSHIRISH (xavfsizlik + sinov ishga tushirish) =================
ALLOWED_IMPORTS = {"math"}
BANNED_NAMES = {"open", "exec", "eval", "compile", "__import__", "globals", "locals",
                "getattr", "setattr", "delattr", "vars", "breakpoint", "exit", "quit"}

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
        elif isinstance(n, ast.Name) and n.id in BANNED_NAMES:
            raise ValueError(f"'{n.id}' ishlatish taqiqlangan")
        elif isinstance(n, ast.Attribute) and n.attr.startswith("__"):
            raise ValueError("maxsus (__) atributlar taqiqlangan")
    return tree

def check_code_style(tree):
    """Flowgorithm uslubi: har qatorda bitta amal, taqiqlangan konstruksiyalarsiz."""
    bad = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Lambda, ast.GeneratorExp, ast.DictComp, ast.SetComp)):
            bad.add("def/class/lambda taqiqlangan")
        elif isinstance(n, ast.ListComp):
            bad.add("list comprehension taqiqlangan (matritsani a.append([0] * m) bilan e'lon qil)")
        elif isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice):
            bad.add("kesim (a[::-1], a[1:3]) taqiqlangan")
        elif isinstance(n, ast.Assign):
            if len(n.targets) > 1:
                bad.add("zanjirli o'zlashtirish (a = b = 0) taqiqlangan, har bir amalni alohida qatorga yoz")
            elif isinstance(n.targets[0], ast.Tuple):
                bad.add("a, b = b, a kabi bir vaqtdagi o'zlashtirish taqiqlangan, t o'zgaruvchi ishlat")
        elif isinstance(n, ast.Constant) and isinstance(n.value, bool):
            bad.add("True/False o'rniga 1/0 ishlat")
        elif isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in {"str", "list", "map", "sum", "sorted"}:
                bad.add(f"{f.id}() taqiqlangan")
            if isinstance(f, ast.Attribute) and f.attr in {"split", "sort", "join", "reverse"}:
                bad.add(f".{f.attr}() taqiqlangan, qiymatlarni input() bilan element-element kirit")
    if bad:
        raise ValueError("USLUB: " + "; ".join(sorted(bad)))


def code_has_input(tree) -> bool:
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "input":
            return True
    return False

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
    """Kodni sinab ko'radi: cheksiz/sekin sikl yoki xatoni aniqlasa ValueError beradi."""
    if has_input and not test_input.strip():
        return  # namuna kiritish yo'q — sinab bo'lmaydi
    try:
        r = await asyncio.to_thread(_run_sync, code, test_input if has_input else "")
    except subprocess.TimeoutExpired:
        raise ValueError(
            "Dastur 10 soniyada tugamadi (cheksiz yoki juda sekin sikl). "
            "Samaraliroq algoritm ishlat: davr topish, binar qidiruv, tez daraja yoki dinamik dasturlash."
        )
    if r.returncode != 0:
        last = (r.stderr.strip().splitlines() or ["noma'lum xato"])[-1]
        if has_input and last.startswith(("EOFError", "ValueError")):
            return  # namuna kiritish mos kelmagan bo'lishi mumkin, kodni ayblamaymiz
        raise ValueError(f"Dastur ishlaganda xato chiqdi: {last}")
    if not r.stdout.strip():
        raise ValueError("Dastur hech narsa chiqarmadi (print yo'q)")

async def generate_flowchart_ast(sec: str, num: str) -> dict:
    cache_key = f"{sec}_{num}"
    if cache_key in FLOWCHART_CACHE:
        return FLOWCHART_CACHE[cache_key]

    prob_text = PROBLEMS_DB.get(sec, {}).get(num, f"§-{sec} bo'lim, {num}-masala.")
    hint = HINTS.get(f"{sec}.{num}")
    base_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Bo'lim: {SECTION_NAMES.get(sec, sec)}\n"
        f"Masala #{num}: {prob_text}\n"
    )
    if hint:
        base_prompt += f"\nYO'L-YO'RIQ (aynan shu usulga amal qil): {hint}\n"

    last_err = None
    extra = ""
    result = None
    candidate = None      # sintaksis jihatdan to'g'ri, lekin sinovdan o'tmagan variant
    warning = ""
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

            tree = check_code_safety(code)       # SyntaxError / taqiqlangan narsa -> xato
            nodes = code_to_nodes(code)
            if not nodes:
                raise ValueError("Koddan blok-sxema qurib bo'lmadi")

            test_input = str(data.get("test_input", "") or "").replace("\\n", "\n")
            if test_input and not test_input.endswith("\n"):
                test_input += "\n"

            cand = {
                "title": f"{SECTION_NAMES.get(sec, sec)}. {num}-masala",
                "explanation": data.get("explanation", ""),
                "input_format": data.get("input_format", ""),
                "sample_input": test_input.strip("\n"),
                "code_python": code,
                "nodes": nodes,
                "problem_text": prob_text,
            }
            candidate = cand
            check_code_style(tree)               # Flowgorithm uslubi buzilsa ValueError

            await verify_run(code, test_input, code_has_input(tree))   # cheksiz sikl / xato bo'lsa ValueError
            result = cand
            break
        except Exception as e:
            last_err = e
            print(f"Generatsiya xatosi (urinish {attempt + 1}): {e}")
            if candidate is not None and isinstance(e, ValueError):
                warning = str(e)
            extra = (
                f"\nOLDINGI JAVOBDA XATO BO'LDI: {e}\n"
                f"Qoidalarga qat'iy amal qilib, to'g'ri JSON va ishlaydigan, TEZ kodni qaytar.\n"
            )
            await asyncio.sleep(1.0)

    if result is None and candidate is not None and warning:
        # Sinovdan/uslub tekshiruvidan o'tmadi, lekin kod mavjud: foydalanuvchiga beramiz
        if not warning.startswith("USLUB"):
            candidate["explanation"] = (candidate.get("explanation", "") +
                                        f"\n\n⚠️ Avtomatik tekshiruv ogohlantirishi: {warning}").strip()
        result = candidate

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
    load_problems()

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

    # Telegram bilan bog'lanishda xato bo'lsa (masalan, eski nusxa hali ishlayotgan bo'lsa)
    # veb-server o'chib qolmasin: 10 soniyadan keyin qayta uriniladi.
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
