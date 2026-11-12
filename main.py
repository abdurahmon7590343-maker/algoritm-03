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
SYSTEM_PROMPT = """
Sen universitet talabalari uchun klassik o'zbekcha blok-sxema va eng sodda, odamdek tushunarli Python dastur tuzuvchi ustozsan.
Berilgan masala uchun faqat sof JSON qaytar.

ENG QAT'IY QOIDALAR:
1. INGLIZCHA SO'ZLAR TAQIQLANADI: "count", "max_coord", "R_squared", "floor", "result" kabi inglizcha nomlarni UMUMAN ISHLATMA!
2. QISQA MATEMATIK O'ZGARUVCHILAR ISHLAT: faqat `n`, `m`, `k`, `s`, `i`, `j`, `a`, `b`, `c`, `x`, `y`, `R` kabi 1 harfli matematik o'zgaruvchilarni ishlat!
3. "declare" (E'lon qilish) BLOKINI UMUMAN QO'SHMA! Blok-sxema to'g'ridan-to'g'ri "input" (Kiritish) blokidan boshlansin.
4. BLOK ICHIDAGI YOZUVLAR QISQA BO'LSIN:
   - Kiritish: "Kiritish: R" yoki "Kiritish: n"
   - O'zlashtirish: "m = int(R), s = 0" yoki "s = s + 1"
   - Sikl: "x = -m dan m gacha" yoki "i = 1 dan n gacha"
   - Shart: "x*x + y*y <= R*R" yoki "a*a + b*b == c*c"
   - Chiqarish: "Chiqarish: s" yoki "Chiqarish: a, b, c"
5. PYTHON KODI:
   - Kod juda sodda, toza va tushunarli bo'lsin. Murakkab funksiyalarsiz.
   - Izohlar toza o'zbek tilida bo'lsin.
6. Node turlari faqat: input, output, assign, if, for, while.

NAMUNA:
{
  "title": "§-5.1. 22-masala",
  "explanation": "Markazi koordinata boshida va radiusi R ga teng doira ichida yotuvchi butun koordinatali (x, y) nuqtalarni sanaymiz.",
  "code_python": "R = float(input(\\"R = \\"))\\nm = int(R)\\ns = 0\\n\\nfor x in range(-m, m + 1):\\n    for y in range(-m, m + 1):\\n        if x * x + y * y <= R * R:\\n            s += 1\\n\\nprint(\\"Natija:\\", s)",
  "nodes": [
    {"type": "input", "text": "Kiritish: R"},
    {"type": "assign", "text": "m = int(R), s = 0"},
    {
      "type": "for",
      "condition": "x = -m dan m gacha",
      "body": [
        {
          "type": "for",
          "condition": "y = -m dan m gacha",
          "body": [
            {
              "type": "if",
              "condition": "x*x + y*y <= R*R",
              "trueBranch": [
                {"type": "assign", "text": "s = s + 1"}
              ],
              "falseBranch": []
            }
          ]
        }
      ]
    },
    {"type": "output", "text": "Chiqarish: s"}
  ]
}
"""

def clean_json_text(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()

def strip_declare(nodes):
    """'declare' bloklarini ichma-ich olib tashlaydi."""
    result = []
    for n in nodes or []:
        if not isinstance(n, dict) or n.get("type") == "declare":
            continue
        for key in ("body", "trueBranch", "falseBranch"):
            if isinstance(n.get(key), list):
                n[key] = strip_declare(n[key])
        result.append(n)
    return result

def _call_gemini(prompt: str):
    return gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1
        )
    )

async def generate_flowchart_ast(sec: str, num: str) -> dict:
    cache_key = f"{sec}_{num}"
    if cache_key in FLOWCHART_CACHE:
        return FLOWCHART_CACHE[cache_key]

    prob_text = PROBLEMS_DB.get(sec, {}).get(num, f"§-{sec} bo'lim, {num}-masala.")
    full_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Bo'lim: {SECTION_NAMES.get(sec, sec)}\n"
        f"Masala #{num}: {prob_text}\n\n"
        f"Ushbu masalaning inglizcha so'zlarsiz, xatosiz blok-sxema JSON strukturasini va toza Python kodini qaytar:"
    )

    last_err = None
    data = None
    for attempt in range(2):
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(_call_gemini, full_prompt), timeout=75
            )
            data = json.loads(clean_json_text(response.text))
            if isinstance(data, list) and data:
                data = data[0]
            if not isinstance(data, dict):
                raise ValueError("AI noto'g'ri formatda javob qaytardi")
            break
        except Exception as e:
            last_err = e
            print(f"Gemini xatosi (urinish {attempt + 1}): {e}")
            data = None
            await asyncio.sleep(1.5)

    if data is None:
        raise RuntimeError(f"AI javob bera olmadi: {last_err}")

    data["nodes"] = strip_declare(data.get("nodes", []))
    data["problem_text"] = prob_text
    FLOWCHART_CACHE[cache_key] = data
    return data

# ================= MINI APP HTML KODI =================
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Blok-Sxema Mini App</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: #0f172a;
    --card: #1e293b;
    --text: #f8fafc;
    --accent: #38bdf8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
  html, body { height: 100%; }
  body { background: var(--bg); color: var(--text); display: flex; flex-direction: column; height: 100vh; height: 100dvh; overflow: hidden; }

  .topbar {
    background: var(--card);
    padding: 10px 12px;
    display: flex;
    gap: 8px;
    align-items: center;
    border-bottom: 1px solid #334155;
    z-index: 10;
  }
  select, button {
    background: #0f172a;
    color: var(--text);
    border: 1px solid #475569;
    padding: 8px 10px;
    border-radius: 8px;
    font-size: 13px;
    outline: none;
  }
  select { flex: 1; min-width: 0; }
  button.btn-primary { background: #0284c7; border-color: #38bdf8; font-weight: 600; cursor: pointer; }

  .problem-banner {
    background: #1e293b;
    padding: 10px 14px;
    font-size: 13px;
    line-height: 1.45;
    border-bottom: 1px solid #334155;
    max-height: 90px;
    overflow-y: auto;
    color: #e2e8f0;
  }

  .tabs { display: flex; background: #0f172a; border-bottom: 1px solid #334155; }
  .tab {
    flex: 1; text-align: center; padding: 11px; font-size: 13px; font-weight: 600;
    color: #94a3b8; cursor: pointer; border-bottom: 2px solid transparent;
  }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); background: #1e293b50; }

  .workspace { flex: 1; position: relative; overflow: hidden; background: #f8fafc; min-height: 0; }
  #canvas-container {
    width: 100%; height: 100%; overflow: auto;
    background-image: radial-gradient(#cbd5e1 1px, transparent 1px);
    background-size: 20px 20px;
    display: flex; justify-content: center; align-items: flex-start;
    padding: 24px;
  }
  #svg-wrapper { flex-shrink: 0; }
  #code-container {
    display: none; width: 100%; height: 100%; overflow: auto;
    background: #0f172a; padding: 16px; color: #e2e8f0;
  }
  .code-header {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;
  }
  .copy-btn {
    background: #1e293b; color: #38bdf8; border: 1px solid #38bdf8;
    padding: 5px 12px; border-radius: 6px; font-size: 12px; cursor: pointer;
  }
  pre {
    background: #1e293b; padding: 14px; border-radius: 10px; overflow-x: auto;
    font-family: Consolas, 'Courier New', monospace; font-size: 14px;
    line-height: 1.55; border: 1px solid #334155; color: #f8fafc;
  }

  .floating-controls {
    position: absolute; bottom: 16px; right: 16px;
    display: flex; gap: 8px; z-index: 20;
  }
  .fab {
    background: #1e293b; color: #fff; border: 1px solid #475569;
    width: 42px; height: 42px; border-radius: 50%; font-size: 18px;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3); cursor: pointer; padding: 0;
  }

  .loader {
    position: absolute; inset: 0; background: rgba(15,23,42,0.85);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    color: #fff; z-index: 50; gap: 12px; font-weight: 600;
  }
  .spinner {
    width: 38px; height: 38px; border: 4px solid #334155;
    border-top-color: var(--accent); border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="topbar">
  <select id="secSelect"></select>
  <select id="numSelect" style="max-width: 98px;"></select>
  <button class="btn-primary" onclick="loadFlowchart(false)">Chizish</button>
</div>

<div class="problem-banner" id="probText">Masala yuklanmoqda...</div>

<div class="tabs">
  <div class="tab active" onclick="switchTab('flow', this)">📊 Blok-Sxema</div>
  <div class="tab" onclick="switchTab('code', this)">🐍 Python Kod & Izoh</div>
</div>

<div class="workspace">
  <div id="loader" class="loader">
    <div class="spinner"></div>
    <div id="loaderText">Blok-sxema chizilmoqda...</div>
  </div>

  <div id="canvas-container">
    <div id="svg-wrapper" style="transform-origin: top center; transition: transform 0.15s ease;"></div>
  </div>

  <div id="code-container">
    <h4 style="color:#38bdf8; margin-bottom:8px;">📌 Algoritm tushuntirishi:</h4>
    <p id="explanationText" style="margin-bottom:18px; font-size:14px; line-height:1.55; color:#cbd5e1;"></p>
    <div class="code-header">
      <h4 style="color:#38bdf8;">🐍 Python dasturi:</h4>
      <button class="copy-btn" onclick="copyCode()">📋 Nusxalash</button>
    </div>
    <pre><code id="pythonCode"></code></pre>
  </div>

  <div class="floating-controls" id="zoomControls">
    <button class="fab" onclick="loadFlowchart(true)" title="Qayta generatsiya qilish">🔄</button>
    <button class="fab" onclick="zoom(0.15)" title="Yaqinlashtirish">➕</button>
    <button class="fab" onclick="zoom(-0.15)" title="Uzoqlashtirish">➖</button>
    <button class="fab" onclick="downloadPNG()" title="PNG rasm yuklab olish">💾</button>
  </div>
</div>

<script>
// Telegram bo'lmasa ham (oddiy brauzerda) ishlayversin
const tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : null;
if (tg) {
  try { tg.ready(); tg.expand(); } catch (e) { console.warn(e); }
}

let allProblems = {};
let currentScale = 1;

const NODE_W = 220;
const NODE_H = 54;
const V_GAP = 36;
const H_GAP = 60;

const COLORS = {
  terminal: { fill: "#f3e8ff", stroke: "#7e22ce", text: "#581c87" },
  assign:   { fill: "#fef9c3", stroke: "#ca8a04", text: "#713f12" },
  input:    { fill: "#e0f2fe", stroke: "#0284c7", text: "#0c4a6e" },
  output:   { fill: "#dcfce7", stroke: "#16a34a", text: "#14532d" },
  if:       { fill: "#ffedd5", stroke: "#ea580c", text: "#7c2d12" },
  loop:     { fill: "#ffe4e6", stroke: "#e11d48", text: "#881337" }
};

function showLoader(show, text) {
  document.getElementById("loader").style.display = show ? "flex" : "none";
  if (text) document.getElementById("loaderText").textContent = text;
}

async function init() {
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const initSec = urlParams.get("sec") || "5.1";
    const initNum = urlParams.get("num") || "1";

    const res = await fetch("/api/problems");
    const data = await res.json();
    allProblems = data.problems || {};
    const sections = data.sections || {};

    const secSelect = document.getElementById("secSelect");
    for (const [code, title] of Object.entries(sections)) {
      const opt = document.createElement("option");
      opt.value = code;
      opt.textContent = title;
      if (code === initSec) opt.selected = true;
      secSelect.appendChild(opt);
    }

    secSelect.addEventListener("change", () => populateNumbers(secSelect.value, "1"));
    populateNumbers(initSec, initNum);
  } catch (err) {
    showLoader(false);
    alert("Boshlang'ich yuklashda xatolik: " + err.message);
    return;
  }
  await loadFlowchart(false);
}

function populateNumbers(sec, selectedNum) {
  const numSelect = document.getElementById("numSelect");
  numSelect.innerHTML = "";
  const probs = allProblems[sec] || {};
  const keys = Object.keys(probs).length
    ? Object.keys(probs).sort((a, b) => Number(a) - Number(b))
    : Array.from({ length: 30 }, (_, i) => String(i + 1));

  for (const k of keys) {
    const opt = document.createElement("option");
    opt.value = k;
    opt.textContent = "#" + k + "-masala";
    if (k === String(selectedNum)) opt.selected = true;
    numSelect.appendChild(opt);
  }
}

async function loadFlowchart(force = false) {
  const sec = document.getElementById("secSelect").value;
  const num = document.getElementById("numSelect").value;
  showLoader(true, "Blok-sxema chizilmoqda...");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);

  try {
    const res = await fetch(
      "/api/flowchart?sec=" + encodeURIComponent(sec) + "&num=" + encodeURIComponent(num) + "&force=" + (force ? 1 : 0),
      { signal: controller.signal }
    );
    const json = await res.json();
    if (json.status !== "ok") throw new Error(json.message || "Noma'lum xatolik");

    const data = json.data;
    document.getElementById("probText").textContent = sec + "." + num + "-masala: " + (data.problem_text || "");
    document.getElementById("explanationText").textContent = data.explanation || "";
    document.getElementById("pythonCode").textContent = data.code_python || "# Kod mavjud emas";

    const cleanNodes = (data.nodes || []).filter(n => n && n.type !== "declare");
    const fullNodes = [
      { type: "terminal", text: "Boshlash" },
      ...cleanNodes,
      { type: "terminal", text: "Tugash" }
    ];
    document.getElementById("svg-wrapper").innerHTML = renderFlowgorithmSVG(fullNodes);
    currentScale = 1;
    document.getElementById("svg-wrapper").style.transform = "scale(1)";
  } catch (err) {
    const msg = err.name === "AbortError" ? "Server javob bermadi (vaqt tugadi)" : err.message;
    alert("Xatolik yuz berdi: " + msg);
  } finally {
    clearTimeout(timer);
    showLoader(false);
  }
}

function copyCode() {
  const code = document.getElementById("pythonCode").textContent;
  const done = () => {
    const btn = document.querySelector(".copy-btn");
    btn.textContent = "✅ Nusxalandi!";
    setTimeout(() => btn.textContent = "📋 Nusxalash", 2000);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(code).then(done).catch(() => fallbackCopy(code, done));
  } else {
    fallbackCopy(code, done);
  }
}

function fallbackCopy(text, cb) {
  const ta = document.createElement("textarea");
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); } catch (e) {}
  document.body.removeChild(ta);
  cb();
}

function wrapWords(text, maxChars = 26) {
  const words = String(text || "").trim().split(/\s+/);
  const lines = [];
  let current = "";
  for (const w of words) {
    if (!current) {
      current = w;
    } else if ((current + " " + w).length <= maxChars) {
      current += " " + w;
    } else {
      lines.push(current);
      current = w;
    }
  }
  if (current) lines.push(current);
  return lines.length ? lines : [""];
}

function measureSequence(nodes) {
  let width = NODE_W + 40;
  let height = 0;
  const measured = [];

  for (let i = 0; i < nodes.length; i++) {
    const m = measureNode(nodes[i]);
    measured.push(m);
    width = Math.max(width, m.width);
    height += m.height;
    if (i < nodes.length - 1) height += V_GAP;
  }
  return { type: "seq", items: measured, width, height };
}

function measureNode(node) {
  const t = String(node.type || "assign").toLowerCase();
  if (t === "if") {
    const tSeq = measureSequence(node.trueBranch || []);
    const fSeq = measureSequence(node.falseBranch || []);
    const leftW = Math.max(tSeq.width, NODE_W / 2 + 40);
    const rightW = Math.max(fSeq.width, NODE_W / 2 + 40);
    const totalW = leftW + rightW + H_GAP;
    const branchH = Math.max(tSeq.height, fSeq.height, 36);
    const totalH = 76 + V_GAP + branchH + 24;
    return { type: "if", node, tSeq, fSeq, leftW, rightW, branchH, width: totalW, height: totalH };
  }
  if (t === "while" || t === "for" || t === "loop") {
    const bodySeq = measureSequence(node.body || []);
    const totalW = Math.max(NODE_W + 90, bodySeq.width + 100);
    const totalH = 62 + V_GAP + bodySeq.height + 34;
    return { type: "loop", node, bodySeq, width: totalW, height: totalH };
  }
  const known = ["terminal", "input", "output"];
  return { type: known.includes(t) ? t : "assign", node, width: NODE_W + 40, height: NODE_H };
}

function esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderFlowgorithmSVG(nodes) {
  const tree = measureSequence(nodes);
  const svgW = Math.max(tree.width + 80, 380);
  const svgH = tree.height + 80;
  const out = [];

  function drawArrow(x1, y1, x2, y2) {
    out.push('<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" stroke="#334155" stroke-width="2.2" marker-end="url(#arrow)"/>');
  }

  function drawLine(x1, y1, x2, y2) {
    out.push('<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" stroke="#334155" stroke-width="2.2"/>');
  }

  function drawText(cx, cy, text, color, maxChars = 26) {
    let lines = wrapWords(text, maxChars);
    if (lines.length > 3) {
      lines = [lines[0], lines[1], lines.slice(2).join(" ")];
    }
    const size = lines.length === 1 ? 13.5 : 12;
    const lh = 15;
    const startY = cy - ((lines.length - 1) * lh) / 2 + 4.5;
    lines.forEach((ln, i) => {
      out.push('<text x="' + cx + '" y="' + (startY + i * lh) + '" text-anchor="middle" font-size="' + size + '" font-weight="600" fill="' + color + '">' + esc(ln) + '</text>');
    });
  }

  function renderSeq(seq, cx, startY) {
    let curY = startY;
    for (let i = 0; i < seq.items.length; i++) {
      const item = seq.items[i];
      renderItem(item, cx, curY);
      curY += item.height;
      if (i < seq.items.length - 1) {
        drawArrow(cx, curY, cx, curY + V_GAP);
        curY += V_GAP;
      }
    }
  }

  function renderItem(m, cx, y) {
    const x = cx - NODE_W / 2;
    const cy = y + NODE_H / 2;

    if (m.type === "terminal") {
      const c = COLORS.terminal;
      out.push('<rect x="' + (x + 25) + '" y="' + y + '" width="' + (NODE_W - 50) + '" height="' + (NODE_H - 6) + '" rx="24" ry="24" fill="' + c.fill + '" stroke="' + c.stroke + '" stroke-width="2.3"/>');
      drawText(cx, y + (NODE_H - 6) / 2, m.node.text, c.text);
    }
    else if (m.type === "input" || m.type === "output") {
      const c = m.type === "input" ? COLORS.input : COLORS.output;
      const sk = 18;
      const pts = (x + sk) + "," + y + " " + (x + NODE_W) + "," + y + " " + (x + NODE_W - sk) + "," + (y + NODE_H) + " " + x + "," + (y + NODE_H);
      out.push('<polygon points="' + pts + '" fill="' + c.fill + '" stroke="' + c.stroke + '" stroke-width="2.3"/>');
      drawText(cx, cy, m.node.text || m.node.condition, c.text);
    }
    else if (m.type === "if") {
      const c = COLORS.if;
      const dh = 76;
      const dw = NODE_W + 30;
      const dcy = y + dh / 2;
      const pts = cx + "," + y + " " + (cx + dw / 2) + "," + dcy + " " + cx + "," + (y + dh) + " " + (cx - dw / 2) + "," + dcy;
      out.push('<polygon points="' + pts + '" fill="' + c.fill + '" stroke="' + c.stroke + '" stroke-width="2.3"/>');
      drawText(cx, dcy, m.node.condition || m.node.text, c.text, 22);

      const leftCx = cx - H_GAP / 2 - m.leftW / 2;
      const rightCx = cx + H_GAP / 2 + m.rightW / 2;
      const branchStartY = y + dh + V_GAP;
      const mergeY = y + m.height;

      drawLine(cx - dw / 2, dcy, leftCx, dcy);
      out.push('<text x="' + ((cx - dw / 2 + leftCx) / 2) + '" y="' + (dcy - 7) + '" text-anchor="middle" font-size="12" font-weight="bold" fill="#15803d">Ha</text>');
      if (m.tSeq.items.length > 0) {
        drawArrow(leftCx, dcy, leftCx, branchStartY);
        renderSeq(m.tSeq, leftCx, branchStartY);
        drawLine(leftCx, branchStartY + m.tSeq.height, leftCx, mergeY);
      } else {
        drawLine(leftCx, dcy, leftCx, mergeY);
      }

      drawLine(cx + dw / 2, dcy, rightCx, dcy);
      out.push('<text x="' + ((cx + dw / 2 + rightCx) / 2) + '" y="' + (dcy - 7) + '" text-anchor="middle" font-size="12" font-weight="bold" fill="#b91c1c">Yo\'q</text>');
      if (m.fSeq.items.length > 0) {
        drawArrow(rightCx, dcy, rightCx, branchStartY);
        renderSeq(m.fSeq, rightCx, branchStartY);
        drawLine(rightCx, branchStartY + m.fSeq.height, rightCx, mergeY);
      } else {
        drawLine(rightCx, dcy, rightCx, mergeY);
      }

      drawLine(leftCx, mergeY, rightCx, mergeY);
      out.push('<circle cx="' + cx + '" cy="' + mergeY + '" r="4" fill="#334155"/>');
    }
    else if (m.type === "loop") {
      const c = COLORS.loop;
      const lh = 62;
      const lw = NODE_W + 26;
      const lcy = y + lh / 2;
      const pts = (cx - lw / 2 + 18) + "," + y + " " + (cx + lw / 2 - 18) + "," + y + " " + (cx + lw / 2) + "," + lcy + " " + (cx + lw / 2 - 18) + "," + (y + lh) + " " + (cx - lw / 2 + 18) + "," + (y + lh) + " " + (cx - lw / 2) + "," + lcy;
      out.push('<polygon points="' + pts + '" fill="' + c.fill + '" stroke="' + c.stroke + '" stroke-width="2.3"/>');
      drawText(cx, lcy, m.node.condition || m.node.text, c.text, 25);

      const bodyStartY = y + lh + V_GAP;
      const bodyEndY = bodyStartY + m.bodySeq.height;
      const bottomY = y + m.height;

      drawArrow(cx, y + lh, cx, bodyStartY);
      out.push('<text x="' + (cx + 16) + '" y="' + (y + lh + 18) + '" font-size="11.5" font-weight="bold" fill="#15803d">Ha</text>');
      if (m.bodySeq.items.length > 0) {
        renderSeq(m.bodySeq, cx, bodyStartY);
      }

      const leftLoopX = cx - m.width / 2 + 18;
      drawLine(cx, bodyEndY, cx, bodyEndY + 14);
      drawLine(cx, bodyEndY + 14, leftLoopX, bodyEndY + 14);
      drawLine(leftLoopX, bodyEndY + 14, leftLoopX, lcy);
      drawArrow(leftLoopX, lcy, cx - lw / 2, lcy);

      const rightExitX = cx + m.width / 2 - 18;
      drawLine(cx + lw / 2, lcy, rightExitX, lcy);
      out.push('<text x="' + (cx + lw / 2 + 22) + '" y="' + (lcy - 6) + '" font-size="11.5" font-weight="bold" fill="#b91c1c">Yo\'q</text>');
      drawLine(rightExitX, lcy, rightExitX, bottomY);
      drawLine(rightExitX, bottomY, cx, bottomY);
      out.push('<circle cx="' + cx + '" cy="' + bottomY + '" r="4" fill="#334155"/>');
    }
    else {
      const c = COLORS.assign;
      out.push('<rect x="' + x + '" y="' + y + '" width="' + NODE_W + '" height="' + NODE_H + '" rx="6" fill="' + c.fill + '" stroke="' + c.stroke + '" stroke-width="2.3"/>');
      drawText(cx, cy, m.node.text || m.node.condition, c.text);
    }
  }

  renderSeq(tree, svgW / 2, 30);

  return '<svg id="flow-svg" xmlns="http://www.w3.org/2000/svg" width="' + svgW + '" height="' + svgH + '" viewBox="0 0 ' + svgW + ' ' + svgH + '">' +
    '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">' +
    '<path d="M 0 1 L 10 5 L 0 9 z" fill="#334155"/></marker></defs>' +
    '<rect width="100%" height="100%" fill="#f8fafc"/>' +
    out.join("\n") +
    '</svg>';
}

function switchTab(tab, el) {
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  el.classList.add("active");
  if (tab === "flow") {
    document.getElementById("canvas-container").style.display = "flex";
    document.getElementById("code-container").style.display = "none";
    document.getElementById("zoomControls").style.display = "flex";
  } else {
    document.getElementById("canvas-container").style.display = "none";
    document.getElementById("code-container").style.display = "block";
    document.getElementById("zoomControls").style.display = "none";
  }
}

function zoom(delta) {
  currentScale = Math.min(2.2, Math.max(0.4, currentScale + delta));
  document.getElementById("svg-wrapper").style.transform = "scale(" + currentScale + ")";
}

function downloadPNG() {
  const svgEl = document.getElementById("flow-svg");
  if (!svgEl) return;
  const svgStr = new XMLSerializer().serializeToString(svgEl);
  const img = new Image();
  const svgBlob = new Blob([svgStr], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);

  img.onload = function () {
    const canvas = document.createElement("canvas");
    canvas.width = svgEl.width.baseVal.value * 2;
    canvas.height = svgEl.height.baseVal.value * 2;
    const ctx = canvas.getContext("2d");
    ctx.scale(2, 2);
    ctx.drawImage(img, 0, 0);
    URL.revokeObjectURL(url);

    const a = document.createElement("a");
    const sec = document.getElementById("secSelect").value;
    const num = document.getElementById("numSelect").value;
    a.download = "BlokSxema_" + sec + "_" + num + ".png";
    a.href = canvas.toDataURL("image/png");
    a.click();
  };
  img.src = url;
}

window.addEventListener("DOMContentLoaded", init);
</script>
</body>
</html>
"""

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
