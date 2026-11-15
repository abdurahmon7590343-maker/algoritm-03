"""Python kodidan blok-sxema daraxtini (nodes) quruvchi modul.

AI faqat Python kodini yozadi, sxema esa shu koddan aniq (deterministik) quriladi,
shuning uchun sxema doim kod bilan mos va to'liq bo'ladi.
"""
import ast
import re

MAX_MERGE_LEN = 34   # ketma-ket o'zlashtirishlarni bitta blokka birlashtirish chegarasi
MAX_MERGE_CNT = 3

OPS = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
}


def _s(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "?"


def _cond(node) -> str:
    t = _s(node)
    t = re.sub(r"\band\b", "va", t)
    t = re.sub(r"\bor\b", "yoki", t)
    t = re.sub(r"\bnot\b\s*", "emas ", t)
    return t.strip()


def _has_input(node) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "input":
            return True
    return False


def _target_names(target) -> list:
    if isinstance(target, ast.Tuple) or isinstance(target, ast.List):
        res = []
        for e in target.elts:
            res += _target_names(e)
        return res
    return [_s(target)]


def _print_text(call: ast.Call) -> str:
    shown, literals = [], []
    for a in call.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            literals.append(a.value.strip())
        elif isinstance(a, ast.JoinedStr):
            has_expr = False
            for v in a.values:
                if isinstance(v, ast.FormattedValue):
                    shown.append(_s(v.value))
                    has_expr = True
                elif isinstance(v, ast.Constant) and isinstance(v.value, str):
                    literals.append(v.value.strip())
            if not has_expr:
                pass
        else:
            shown.append(_s(a))
    if shown:
        return "Chiqarish: " + ", ".join(shown)
    lit = " ".join(x for x in literals if x).strip(" :")
    return "Chiqarish: " + (lit if lit else "")


def _stop_inclusive(stop, step_positive=True) -> str:
    """range(a, stop) -> 'stop-1' (yoki oldingi son) ni chiroyli yozish."""
    if step_positive:
        if isinstance(stop, ast.BinOp) and isinstance(stop.op, ast.Add) \
                and isinstance(stop.right, ast.Constant) and stop.right.value == 1:
            return _s(stop.left)
        if isinstance(stop, ast.Constant) and isinstance(stop.value, int):
            return str(stop.value - 1)
        return f"{_s(stop)}-1"
    else:
        if isinstance(stop, ast.BinOp) and isinstance(stop.op, ast.Sub) \
                and isinstance(stop.right, ast.Constant) and stop.right.value == 1:
            return _s(stop.left)
        if isinstance(stop, ast.Constant) and isinstance(stop.value, int):
            return str(stop.value + 1)
        return f"{_s(stop)}+1"


def _for_condition(node: ast.For) -> str:
    var = _s(node.target)
    it = node.iter
    if isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range" \
            and 1 <= len(it.args) <= 3:
        args = it.args
        if len(args) == 1:
            start, stop, step = "0", args[0], None
        elif len(args) == 2:
            start, stop, step = _s(args[0]), args[1], None
        else:
            start, stop, step = _s(args[0]), args[1], args[2]

        positive = True
        step_txt = ""
        if step is not None:
            try:
                sv = ast.literal_eval(step)
                positive = sv > 0
                if sv != 1:
                    step_txt = f" (qadam {sv})"
            except Exception:
                step_txt = f" (qadam {_s(step)})"
        end = _stop_inclusive(stop, positive)
        return f"{var} = {start} dan {end} gacha{step_txt}"
    return f"{var} in {_s(it)}"


def _simple_text(stmt) -> str:
    if isinstance(stmt, ast.AugAssign):
        op = OPS.get(type(stmt.op), "?")
        return f"{_s(stmt.target)} = {_s(stmt.target)} {op} {_s(stmt.value)}"
    if isinstance(stmt, ast.AnnAssign):
        return f"{_s(stmt.target)} = {_s(stmt.value)}" if stmt.value is not None else _s(stmt.target)
    return _s(stmt)


def _convert(stmts, func_names) -> list:
    nodes = []
    for st in stmts:
        # e'tiborga olinmaydigan
        if isinstance(st, (ast.Import, ast.ImportFrom, ast.Pass, ast.Global, ast.Nonlocal)):
            continue
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
            continue  # docstring / yolg'iz satr

        # funksiya, try, with: ichini ochib qo'yamiz
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_names.add(st.name)
            nodes += _convert(st.body, func_names)
            continue
        if isinstance(st, ast.Try):
            nodes += _convert(st.body, func_names)
            continue
        if isinstance(st, (ast.With, ast.AsyncWith)):
            nodes += _convert(st.body, func_names)
            continue

        # if __name__ == "__main__":
        if isinstance(st, ast.If) and "__name__" in _s(st.test):
            nodes += _convert(st.body, func_names)
            continue

        if isinstance(st, ast.If):
            nodes.append({
                "type": "if",
                "condition": _cond(st.test),
                "trueBranch": _convert(st.body, func_names),
                "falseBranch": _convert(st.orelse, func_names),   # elif -> ichma-ich if
            })
        elif isinstance(st, ast.For):
            nodes.append({
                "type": "for",
                "condition": _for_condition(st),
                "body": _convert(st.body, func_names),
            })
        elif isinstance(st, ast.While):
            c = _cond(st.test)
            nodes.append({
                "type": "while",
                "condition": c,
                "body": _convert(st.body, func_names),
            })
        elif isinstance(st, ast.Break):
            nodes.append({"type": "assign", "text": "Sikldan chiqish", "_special": True})
        elif isinstance(st, ast.Continue):
            nodes.append({"type": "assign", "text": "Keyingi qadamga o'tish", "_special": True})
        elif isinstance(st, ast.Return):
            txt = "Qaytarish" + (": " + _s(st.value) if st.value is not None else "")
            nodes.append({"type": "output", "text": txt, "_special": True})
        elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
            call = st.value
            fname = call.func.id if isinstance(call.func, ast.Name) else None
            if fname == "print":
                nodes.append({"type": "output", "text": _print_text(call), "_special": True})
            elif fname == "input":
                nodes.append({"type": "input", "text": "Kiritish", "_names": []})
            elif fname in func_names:
                continue
            else:
                nodes.append({"type": "assign", "text": _s(st), "_special": True})
        elif isinstance(st, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            value = st.value
            if value is not None and _has_input(value):
                targets = st.targets if isinstance(st, ast.Assign) else [st.target]
                names = []
                for t in targets:
                    names += _target_names(t)
                nodes.append({"type": "input", "text": "", "_names": names})
            else:
                nodes.append({"type": "assign", "text": _simple_text(st)})
        else:
            nodes.append({"type": "assign", "text": _s(st), "_special": True})

    return _merge(nodes)


def _merge(nodes: list) -> list:
    """Ketma-ket bir xil bloklarni (kiritish / o'zlashtirish) ixcham birlashtiradi."""
    merged = []
    for n in nodes:
        prev = merged[-1] if merged else None
        if prev and n["type"] == "input" and prev["type"] == "input" and n.get("_names") and prev.get("_names") is not None:
            joined = prev["_names"] + n["_names"]
            if len(", ".join(joined)) <= 28:
                prev["_names"] = joined
                continue
        if prev and n["type"] == "assign" and prev["type"] == "assign" \
                and not n.get("_special") and not prev.get("_special"):
            if prev.get("_cnt", 1) < MAX_MERGE_CNT and len(prev["text"]) + len(n["text"]) + 2 <= MAX_MERGE_LEN:
                prev["text"] += ", " + n["text"]
                prev["_cnt"] = prev.get("_cnt", 1) + 1
                continue
        merged.append(n)
    return merged


def _finalize(nodes: list) -> list:
    out = []
    for n in nodes:
        if n["type"] == "input":
            names = n.get("_names") or []
            n["text"] = "Kiritish: " + ", ".join(names) if names else "Kiritish"
        for k in ("_names", "_special", "_cnt"):
            n.pop(k, None)
        for k in ("body", "trueBranch", "falseBranch"):
            if k in n:
                n[k] = _finalize(n[k])
        out.append(n)
    return out


def code_to_nodes(code: str) -> list:
    """Python kodidan blok-sxema bloklari ro'yxatini qaytaradi. Sintaksis xato bo'lsa SyntaxError."""
    tree = ast.parse(code)
    nodes = _convert(tree.body, set())
    return _finalize(nodes)
