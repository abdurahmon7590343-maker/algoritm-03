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
PDF_BOB1_PATH = os.getenv("PDF_BOB1_PATH", "BLACKCURSE1.pdf")
PROBLEMS_JSON = os.getenv("PROBLEMS_JSON", "problems.json")
PROBLEMS_BOB1_JSON = os.getenv("PROBLEMS_BOB1_JSON", "problems_bob1.json")
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
    base = os.path.dirname(os.path.abspath(__file__))
    path = pdf_path if os.path.isabs(pdf_path) else os.path.join(base, pdf_path)
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
    base = os.path.dirname(os.path.abspath(__file__))

    # 1) I bob (avval tozalangan problems_bob1.json, bo'lmasa PDF)
    p1 = PROBLEMS_BOB1_JSON if os.path.isabs(PROBLEMS_BOB1_JSON) else os.path.join(base, PROBLEMS_BOB1_JSON)
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

    # 2) V bob (problems.json, bo'lmasa PDF)
    path = PROBLEMS_JSON if os.path.isabs(PROBLEMS_JSON) else os.path.join(base, PROBLEMS_JSON)
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


# ================= AI GENERATOR =================
def clean_json_text(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


SYSTEM_PROMPT = r"""
Sen matematika va informatika o'qituvchisisanki, talaba daftariga yozgandek ENG TOZA, SODDA va MANTIQIY matematik Python kodi yozasan.
Shu koddan avtomatik ravishda blok-sxema chiziladi. Faqat sof JSON qaytar:
{"explanation": "...", "input_format": "...", "test_input": "...", "code_python": "..."}

QAT'IY QOIDALAR:
1. O'ZGARUVCHILAR (ENG MUHIM):
   - FAQAT 1-2 harfli matematik nomlar ishlat: a, b, c, d, d1, d2, d3, n, m, k, s, p, q, r, i, j, x, y, z, t, u, v, w, N, M, K, R, A, B.
   - 3 va undan ko'p harfli inglizcha nomlar (sequence, result, count, visited, found, temp, flag, total, ans, num, mid, pos, arr, cur) QAT'IY TAQIQLANADI!
2. ORTIQCHA FUNKSIYALARSIZ, LEKIN MANTIQIY BO'LAKLANGAN KOD:
   - Oddiy qisqa formulani bitta qatorda yoz (masalan: s = (a + b) / 2).
   - Katta, bir nechta kasr yoki qismdan iborat arifmetik ifodalarni (§-1.1, §-1.2 kabi) HECH QACHON bitta uzun `s = ...` qatoriga tiqma!
     Har bir asosiy kasr yoki takrorlanuvchi qismni alohida qisqa matematik harfda (t, p, q, r yoki u, v, w) hisoblab, oxirida `s = p - q + r` ko'rinishida jamla.
   - Masalada "darajaga ko'tarish amalidan foydalanmasdan" deyilsa, `**` va `pow` ISHLATMA: kvadrat uchun `t * t`, kub uchun `d * d * d` yoz (takroriy qavsni avval `t = ...` qilib ol, ikki marta ko'chirib yozma).
   - TAQIQLANADI: def, class, lambda, break, continue, True, False, while True, .append(), .pop(), .sort(), .reverse(), .split(), .join(), sum(), min(), max(), sorted(), map(), zip(), enumerate(), round(), pow(), list(), dict(), set(), tuple().
   - Agar 1.8 (matnli masalalar) yoki 5.1.31 bo'lmasa: len() va str() ham TAQIQLANADI!
   - Massiv kerak bo'lsa `a = [0] * n` (indeks bilan yoz, .append() ISHLATMA), matritsa kerak bo'lsa `A = [[0] * m for i in range(n)]` deb e'lon qil.
   - Kutubxona faqat juda zarur bo'lsa (sin, cos, tan, log, exp, sqrt, pi) `from math import ...` ishlat.
3. KIRITISH VA CHIQARISH:
   - Har bir kiritiladigan qiymat: `n = int(input("n = "))` yoki `x = float(input("x = "))`.
   - Agar masalada barcha sonlar aniq berilgan bo'lsa (masalan [200, 300] oraliq) — input() ISHLATMA.
   - Natijani ortiqcha so'zlarsiz chiqar: `print(s)` yoki `print("Ha")` / `print("Yo'q")`.
4. ARIFMETIK IFODA UCHUN YAXSHI NAMUNA:
   t = 1 - (a + 2.9 * b)
   p = (t * t) / (a * b - d - 1.45)
   q = ((c - a) / d) / (a * (b + c * c))
   r = a / (1 + 2 / c)
   s = p - q + r
   print(s)
5. TEZLIK VA XAVFSIZ TEST:
   - Cheksiz yoki sekin sikl yozma.
   - `test_input` ga kichik, tez ishlaydigan va XATOSIZ (0 ga bo'linmaydigan, log/ildiz ichi musbat chiqadigan) namuna qiymatlar ber (masalan n=5, yoki a=2.5, b=3.1, c=1.8, d=0.7).
6. Izohlar (#) YOZMA.
7. JSON maydonlari:
   - "explanation": 1-2 gapli qisqa o'zbekcha tushuntirish.
   - "input_format": nimalarni qaysi tartibda kiritish kerakligi (bo'lmasa "Kiritish kerak emas").
   - "test_input": har bir input() uchun alohida qiymat (\n bilan), bo'lmasa "".
   - "code_python": toza, qisqa, odam yozgandek matematik Python kodi.
"""


def _call_gemini(prompt: str):
    cfg = dict(
        response_mime_type="application/json",
        temperature=0.1,
        max_output_tokens=8192,
    )
    try:
        cfg["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=2048)
    except Exception:
        pass
    return gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(**cfg)
    )


# ================= KODNI TEKSHIRISH =================
ALLOWED_IMPORTS = {"math"}
BANNED_NAMES = {"open", "exec", "eval", "compile", "__import__", "globals", "locals",
                "getattr", "setattr", "delattr", "vars", "breakpoint", "exit", "quit"}
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
        elif isinstance(n, ast.Name) and n.id in BANNED_NAMES:
            raise ValueError(f"'{n.id}' ishlatish taqiqlangan")
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


def check_code_style(tree, sec: str, num: str):
    bad = set()
    allow_str = (sec == "1.8" or f"{sec}.{num}" == "5.1.31")
    banned_funcs = {"list", "dict", "set", "tuple", "map", "filter", "zip",
                    "enumerate", "sum", "min", "max", "sorted", "reversed",
                    "round", "pow", "divmod", "all", "any"}
    if not allow_str:
        banned_funcs |= {"str", "len"}
    banned_methods = {"append", "extend", "insert", "pop", "remove", "sort",
                      "reverse", "split", "join", "replace"}

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
            if isinstance(f, ast.Name) and f.id in banned_funcs:
                bad.add(f"keraksiz funksiya {f.id}() taqiqlangan")
            if isinstance(f, ast.Attribute) and f.attr in banned_methods:
                bad.add(f".{f.attr}() taqiqlangan, oddiy massiv indeksi a[i] ishlat")
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
        base_prompt += (
            f"\nYO'L-YO'RIQ (g'oyani ol, lekin .append() va uzun nomlar ishlatma, "
            f"faqat 1-2 harfli nomlar va a[k] indeks bilan yoz): {hint}\n"
        )

    last_err = None
    extra = ""
    result = None
    candidate = None
    fallback = None
    warning = ""

    for attempt in range(4):
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

            tree = check_code_safety(code)
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
            fallback = cand

            await verify_run(code, test_input, code_has_input(tree))
            candidate = cand
            check_code_style(tree, sec, num)

            result = cand
            break
        except Exception as e:
            last_err = e
            print(f"Generatsiya xatosi (urinish {attempt + 1}): {e}")
            if isinstance(e, ValueError):
                warning = str(e)
            extra = (
                f"\nOLDINGI JAVOBDA XATO BO'LDI: {e}\n"
                f"Xatoni aniq tuzat: faqat 1-2 harfli matematik nomlar va oddiy arifmetika/sikllar ishlat.\n"
            )
            await asyncio.sleep(1.0)

    if result is None:
        result = candidate or fallback
        if result is not None and warning and not warning.startswith("USLUB") and candidate is None:
            result["explanation"] = (result.get("explanation", "") +
                                     f"\n\n⚠️ Avtomatik tekshiruv: {warning}").strip()

    if result is None:
        raise RuntimeError(f"AI to'g'ri javob bera olmadi: {last_err}")

    FLOWCHART_CACHE[cache_key] = result
    return result


# ================= MINI APP HTML =================
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


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
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


async def handle_api_problems(request):
    return web.json_response({"sections": SECTION_NAMES, "problems": PROBLEMS_DB})


async def handle_api_flowchart(request):
    sec = request.query.get("sec", "1.1")
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
    print(f"Web-server [http://0.0.0.0](http://0.0.0.0):{PORT} da ishga tushdi! WEBAPP_URL: {WEBAPP_URL}")

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
