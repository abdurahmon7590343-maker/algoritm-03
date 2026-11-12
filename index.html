<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Blok-Sxema Mini App</title>
<script src="[https://telegram.org/js/telegram-web-app.js](https://telegram.org/js/telegram-web-app.js)"></script>
<style>
  :root {
    --bg: #0f172a;
    --card: #1e293b;
    --text: #f8fafc;
    --accent: #38bdf8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
  body { background: var(--bg); color: var(--text); display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
  
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
  select { flex: 1; }
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

  .workspace { flex: 1; position: relative; overflow: hidden; background: #f8fafc; }
  #canvas-container {
    width: 100%; height: 100%; overflow: auto;
    background-image: radial-gradient(#cbd5e1 1px, transparent 1px);
    background-size: 20px 20px;
    display: flex; justify-content: center; align-items: flex-start;
    padding: 24px;
  }
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
    box-shadow: 0 4px 12px rgba(0,0,0,0.3); cursor: pointer;
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
    <div>Blok-sxema chizilmoqda...</div>
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
const tg = window.Telegram.WebApp;
tg.expand();

let allProblems = {};
let currentScale = 1;

const COLORS = {
  terminal: { fill: "#f3e8ff", stroke: "#7e22ce", text: "#581c87" },
  assign:   { fill: "#fef9c3", stroke: "#ca8a04", text: "#713f12" },
  input:    { fill: "#e0f2fe", stroke: "#0284c7", text: "#0c4a6e" },
  output:   { fill: "#dcfce7", stroke: "#16a34a", text: "#14532d" },
  if:       { fill: "#ffedd5", stroke: "#ea580c", text: "#7c2d12" },
  loop:     { fill: "#ffe4e6", stroke: "#e11d48", text: "#881337" }
};

async function init() {
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
  await loadFlowchart(false);
}

function populateNumbers(sec, selectedNum) {
  const numSelect = document.getElementById("numSelect");
  numSelect.innerHTML = "";
  const probs = allProblems[sec] || {};
  const keys = Object.keys(probs).length ? Object.keys(probs).sort((a,b)=>Number(a)-Number(b)) : Array.from({length:30}, (_,i)=>String(i+1));
  
  for (const k of keys) {
    const opt = document.createElement("option");
    opt.value = k;
    opt.textContent = `#${k}-masala`;
    if (k === String(selectedNum)) opt.selected = true;
    numSelect.appendChild(opt);
  }
}

async function loadFlowchart(force = false) {
  const sec = document.getElementById("secSelect").value;
  const num = document.getElementById("numSelect").value;
  document.getElementById("loader").style.display = "flex";

  try {
    const res = await fetch(`/api/flowchart?sec=${sec}&num=${num}&force=${force ? 1 : 0}`);
    const json = await res.json();
    if (json.status !== "ok") throw new Error(json.message);

    const data = json.data;
    document.getElementById("probText").textContent = `${sec}.${num}-masala: ` + (data.problem_text || "");
    document.getElementById("explanationText").textContent = data.explanation || "";
    document.getElementById("pythonCode").textContent = data.code_python || "# Kod mavjud emas";

    const cleanNodes = (data.nodes || []).filter(n => n.type !== "declare");
    const fullNodes = [
      { type: "terminal", text: "Boshlash" },
      ...cleanNodes,
      { type: "terminal", text: "Tugash" }
    ];
    const svgString = renderFlowgorithmSVG(fullNodes);
    document.getElementById("svg-wrapper").innerHTML = svgString;
    currentScale = 1;
    document.getElementById("svg-wrapper").style.transform = `scale(1)`;
  } catch (err) {
    alert("Xatolik yuz berdi: " + err.message);
  } finally {
    document.getElementById("loader").style.display = "none";
  }
}

function copyCode() {
  const code = document.getElementById("pythonCode").textContent;
  navigator.clipboard.writeText(code);
  const btn = document.querySelector(".copy-btn");
  btn.textContent = "✅ Nusxalandi!";
  setTimeout(() => btn.textContent = "📋 Nusxalash", 2000);
}

// ================= SO'ZNI BO'LIB YUBORMAYDIGAN MATN FUNKSIYASI =================
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

// ================= GRAFIK MOTOR =================
const NODE_W = 220;
const NODE_H = 54;
const V_GAP = 36;
const H_GAP = 60;

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
  const t = (node.type || "assign").toLowerCase();
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
  return { type: t, node, width: NODE_W + 40, height: NODE_H };
}

function renderFlowgorithmSVG(nodes) {
  const tree = measureSequence(nodes);
  const svgW = Math.max(tree.width + 80, 380);
  const svgH = tree.height + 80;
  let out = [];

  function drawArrow(x1, y1, x2, y2) {
    out.push(`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#334155" stroke-width="2.2" marker-end="url(#arrow)"/>`);
  }

  function drawLine(x1, y1, x2, y2) {
    out.push(`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#334155" stroke-width="2.2"/>`);
  }

  function drawText(cx, cy, text, color, maxChars = 26) {
    const lines = wrapWords(text, maxChars);
    if (lines.length === 1) {
      out.push(`<text x="${cx}" y="${cy + 5}" text-anchor="middle" font-size="13.5" font-weight="600" fill="${color}">${esc(lines[0])}</text>`);
    } else {
      out.push(`<text x="${cx}" y="${cy - 3}" text-anchor="middle" font-size="12.5" font-weight="600" fill="${color}">${esc(lines[0])}</text>`);
      out.push(`<text x="${cx}" y="${cy + 14}" text-anchor="middle" font-size="12.5" font-weight="600" fill="${color}">${esc(lines.slice(1).join(" "))}</text>`);
    }
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
      out.push(`<rect x="${x + 25}" y="${y}" width="${NODE_W - 50}" height="${NODE_H - 6}" rx="24" ry="24" fill="${c.fill}" stroke="${c.stroke}" stroke-width="2.3"/>`);
      drawText(cx, y + (NODE_H - 6)/2, m.node.text, c.text);
    }
    else if (m.type === "input" || m.type === "output") {
      const c = m.type === "input" ? COLORS.input : COLORS.output;
      const sk = 18;
      const pts = `${x+sk},${y} ${x+NODE_W},${y} ${x+NODE_W-sk},${y+NODE_H} ${x},${y+NODE_H}`;
      out.push(`<polygon points="${pts}" fill="${c.fill}" stroke="${c.stroke}" stroke-width="2.3"/>`);
      drawText(cx, cy, m.node.text, c.text);
    }
    else if (m.type === "if") {
      const c = COLORS.if;
      const dh = 76;
      const dw = NODE_W + 30;
      const dcy = y + dh / 2;
      const pts = `${cx},${y} ${cx+dw/2},${dcy} ${cx},${y+dh} ${cx-dw/2},${dcy}`;
      out.push(`<polygon points="${pts}" fill="${c.fill}" stroke="${c.stroke}" stroke-width="2.3"/>`);
      drawText(cx, dcy, m.node.condition || m.node.text, c.text, 22);

      const leftCx = cx - H_GAP / 2 - m.leftW / 2;
      const rightCx = cx + H_GAP / 2 + m.rightW / 2;
      const branchStartY = y + dh + V_GAP;
      const mergeY = y + m.height;

      // Ha tarmog'i (Chap)
      drawLine(cx - dw / 2, dcy, leftCx, dcy);
      out.push(`<text x="${(cx - dw/2 + leftCx)/2}" y="${dcy - 7}" text-anchor="middle" font-size="12" font-weight="bold" fill="#15803d">Ha</text>`);
      if (m.tSeq.items.length > 0) {
        drawArrow(leftCx, dcy, leftCx, branchStartY);
        renderSeq(m.tSeq, leftCx, branchStartY);
        drawLine(leftCx, branchStartY + m.tSeq.height, leftCx, mergeY);
      } else {
        drawLine(leftCx, dcy, leftCx, mergeY);
      }

      // Yo'q tarmog'i (O'ng)
      drawLine(cx + dw / 2, dcy, rightCx, dcy);
      out.push(`<text x="${(cx + dw/2 + rightCx)/2}" y="${dcy - 7}" text-anchor="middle" font-size="12" font-weight="bold" fill="#b91c1c">Yo'q</text>`);
      if (m.fSeq.items.length > 0) {
        drawArrow(rightCx, dcy, rightCx, branchStartY);
        renderSeq(m.fSeq, rightCx, branchStartY);
        drawLine(rightCx, branchStartY + m.fSeq.height, rightCx, mergeY);
      } else {
        drawLine(rightCx, dcy, rightCx, mergeY);
      }

      // Pastki birlashish chizig'i
      drawLine(leftCx, mergeY, rightCx, mergeY);
      out.push(`<circle cx="${cx}" cy="${mergeY}" r="4" fill="#334155"/>`);
    }
    else if (m.type === "loop") {
      const c = COLORS.loop;
      const lh = 62;
      const lw = NODE_W + 26;
      const lcy = y + lh / 2;
      const pts = `${cx-lw/2+18},${y} ${cx+lw/2-18},${y} ${cx+lw/2},${lcy} ${cx+lw/2-18},${y+lh} ${cx-lw/2+18},${y+lh} ${cx-lw/2},${lcy}`;
      out.push(`<polygon points="${pts}" fill="${c.fill}" stroke="${c.stroke}" stroke-width="2.3"/>`);
      drawText(cx, lcy, m.node.condition || m.node.text, c.text, 25);

      const bodyStartY = y + lh + V_GAP;
      const bodyEndY = bodyStartY + m.bodySeq.height;
      const bottomY = y + m.height;

      // Sikl ichiga kirish
      drawArrow(cx, y + lh, cx, bodyStartY);
      out.push(`<text x="${cx + 16}" y="${y + lh + 18}" font-size="11.5" font-weight="bold" fill="#15803d">Ha</text>`);
      if (m.bodySeq.items.length > 0) {
        renderSeq(m.bodySeq, cx, bodyStartY);
      }

      // Chap tomondan sikl boshiga qaytish
      const leftLoopX = cx - m.width / 2 + 18;
      drawLine(cx, bodyEndY, cx, bodyEndY + 14);
      drawLine(cx, bodyEndY + 14, leftLoopX, bodyEndY + 14);
      drawLine(leftLoopX, bodyEndY + 14, leftLoopX, lcy);
      drawArrow(leftLoopX, lcy, cx - lw / 2, lcy);

      // O'ng tomondan sikldan chiqish (Yo'q)
      const rightExitX = cx + m.width / 2 - 18;
      drawLine(cx + lw / 2, lcy, rightExitX, lcy);
      out.push(`<text x="${cx + lw/2 + 22}" y="${lcy - 6}" font-size="11.5" font-weight="bold" fill="#b91c1c">Yo'q</text>`);
      drawLine(rightExitX, lcy, rightExitX, bottomY);
      drawLine(rightExitX, bottomY, cx, bottomY);
      out.push(`<circle cx="${cx}" cy="${bottomY}" r="4" fill="#334155"/>`);
    }
    else {
      const c = COLORS.assign;
      out.push(`<rect x="${x}" y="${y}" width="${NODE_W}" height="${NODE_H}" rx="6" fill="${c.fill}" stroke="${c.stroke}" stroke-width="2.3"/>`);
      drawText(cx, cy, m.node.text, c.text);
    }
  }

  renderSeq(tree, svgW / 2, 30);

  return `
    <svg id="flow-svg" xmlns="[http://www.w3.org/2000/svg](http://www.w3.org/2000/svg)" width="${svgW}" height="${svgH}" viewBox="0 0 ${svgW} ${svgH}">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="#334155"/>
        </marker>
      </defs>
      <rect width="100%" height="100%" fill="#f8fafc"/>
      ${out.join("\n")}
    </svg>
  `;
}

function esc(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
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
  document.getElementById("svg-wrapper").style.transform = `scale(${currentScale})`;
}

function downloadPNG() {
  const svgEl = document.getElementById("flow-svg");
  if (!svgEl) return;
  const serializer = new XMLSerializer();
  const svgStr = serializer.serializeToString(svgEl);
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
    a.download = `BlokSxema_${sec}_${num}.png`;
    a.href = canvas.toDataURL("image/png");
    a.click();
  };
  img.src = url;
}

window.addEventListener("DOMContentLoaded", init);
</script>
</body>
</html>
