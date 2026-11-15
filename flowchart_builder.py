"""Python kodidan blok-sxema daraxtini (nodes) quruvchi modul.

AI faqat Python kodini yozadi, sxema esa shu koddan aniq (deterministik) quriladi.
Blok ichidagi yozuvlar Python sintaksisida EMAS, darslikdagidek matematik/o'zbekcha
ko'rinishda bo'ladi: x mod 2 = 0, a[i] ≠ 0, butun(R), x ≤ y, n^2 va h.k.
"""
import ast
import re

MAX_MERGE_LEN = 34   # ketma-ket o'zlashtirishlarni bitta blokka birlashtirish chegarasi
MAX_MERGE_CNT = 3

PREC = {ast.Pow: 5, ast.Mult: 4, ast.Div: 4, ast.FloorDiv: 4, ast.Mod: 4, ast.Add: 3, ast.Sub: 3}
BIN_SYMBOL = {ast.Add: " + ", ast.Sub: " - ", ast.Mult: "*", ast.Div: "/",
              ast.FloorDiv: " div ", ast.Mod: " mod ", ast.Pow: "^"}
CMP_SYMBOL = {ast.Eq: "=", ast.NotEq: "≠", ast.Lt: "<", ast.LtE: "≤", ast.Gt: ">", ast.GtE: "≥",
              ast.In: "∈", ast.NotIn: "∉", ast.Is: "=", ast.IsNot: "≠"}


# ---------------------------------------------------------------- ifodalarni matematik yozuvga o'tkazish
def _s(node) -> str:
    """Zaxira: Python yozuvi (faqat ichki tekshiruvlar uchun)."""
    try:
        return ast.unparse(node)
    except Exception:
        return "?"


def _prec(node) -> int:
    if isinstance(node, ast.BinOp):
        return PREC.get(type(node.op), 3)
    if isinstance(node, ast.UnaryOp):
        return 6 if isinstance(node.op, (ast.USub, ast.UAdd)) else 1
    if isinstance(node, ast.Compare):
        return 1
    if isinstance(node, (ast.BoolOp, ast.IfExp)):
        return 0
    return 9


def _wrap(node, min_prec: int) -> str:
    t = _expr(node)
    return f"({t})" if _prec(node) < min_prec else t


def _is_num(node, value=None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
        and not isinstance(node.value, bool) and (value is None or node.value == value)


def _expr(node) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Constant):
        v = node.value
        if v is True:
            return "Ha"
        if v is False:
            return "Yo'q"
        if v is None:
            return "bo'sh"
        if isinstance(v, str):
            return "'" + v + "'"
        return repr(v)

    if isinstance(node, ast.Name):
        return "π" if node.id == "pi" else node.id

    if isinstance(node, ast.Tuple):
        return "(" + ", ".join(_expr(e) for e in node.elts) + ")"

    if isinstance(node, ast.List):
        if not node.elts:
            return "bo'sh massiv"
        return "[" + ", ".join(_expr(e) for e in node.elts) + "]"

    if isinstance(node, ast.BinOp):
        op = type(node.op)
        p = PREC.get(op, 3)
        # [0] * n  ->  n ta 0 dan iborat massiv
        if op is ast.Mult and isinstance(node.left, ast.List) and len(node.left.elts) == 1:
            return f"{_wrap(node.right, 5)} ta {_expr(node.left.elts[0])} dan iborat massiv"
        if op is ast.Mult and isinstance(node.right, ast.List) and len(node.right.elts) == 1:
            return f"{_wrap(node.left, 5)} ta {_expr(node.right.elts[0])} dan iborat massiv"
        if op is ast.Pow:
            if _is_num(node.right, 0.5):
                return "√(" + _expr(node.left) + ")"
            base = _wrap(node.left, p + 1)
            if isinstance(node.left, ast.UnaryOp) or (_is_num(node.left) and node.left.value < 0):
                base = f"({_expr(node.left)})"
            return f"{base}^{_wrap(node.right, p)}"
        left = _wrap(node.left, p)
        right = _wrap(node.right, p + 1)
        return f"{left}{BIN_SYMBOL.get(op, '?')}{right}"

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return "-" + _wrap(node.operand, 6)
        if isinstance(node.op, ast.UAdd):
            return _wrap(node.operand, 6)
        inner = _expr(node.operand)
        if isinstance(node.operand, (ast.Compare, ast.BoolOp)):
            inner = f"({inner})"
        return "emas " + inner

    if isinstance(node, ast.BoolOp):
        word = " va " if isinstance(node.op, ast.And) else " yoki "
        parts = []
        for v in node.values:
            t = _expr(v)
            if isinstance(v, ast.IfExp) or (isinstance(v, ast.BoolOp) and type(v.op) is not type(node.op)):
                t = f"({t})"
            parts.append(t)
        return word.join(parts)

    if isinstance(node, ast.Compare):
        out = _wrap(node.left, 2)
        for op, cmp in zip(node.ops, node.comparators):
            out += f" {CMP_SYMBOL.get(type(op), '?')} {_wrap(cmp, 2)}"
        return out

    if isinstance(node, ast.IfExp):
        return f"{_expr(node.body)} (agar {_expr(node.test)}), aks holda {_expr(node.orelse)}"

    if isinstance(node, ast.Subscript):
        sl = node.slice
        base = _wrap(node.value, 9)
        if isinstance(sl, ast.Slice):
            if sl.lower is None and sl.upper is None and isinstance(sl.step, ast.UnaryOp) \
                    and isinstance(sl.step.op, ast.USub) and _is_num(sl.step.operand, 1):
                return f"teskari({_expr(node.value)})"
            lo = _expr(sl.lower) if sl.lower is not None else ""
            up = _expr(sl.upper) if sl.upper is not None else ""
            return f"{base}[{lo}:{up}]"
        if isinstance(sl, ast.Tuple):
            return base + "".join(f"[{_expr(e)}]" for e in sl.elts)
        return f"{base}[{_expr(sl)}]"

    if isinstance(node, ast.Attribute):
        return f"{_expr(node.value)}.{node.attr}"

    if isinstance(node, ast.Call):
        name = node.func.id if isinstance(node.func, ast.Name) else None
        args = [_expr(a) for a in node.args]
        a0 = args[0] if args else ""
        if name == "float":
            return a0 or "0"
        if name == "int":
            arg = node.args[0] if node.args else None
            if isinstance(arg, ast.Subscript) and isinstance(arg.slice, ast.Slice) \
                    and isinstance(arg.value, ast.Call) and isinstance(arg.value.func, ast.Name) \
                    and arg.value.func.id == "str" and len(arg.value.args) == 1 \
                    and arg.slice.lower is None and arg.slice.upper is None \
                    and isinstance(arg.slice.step, ast.UnaryOp) and isinstance(arg.slice.step.op, ast.USub):
                return f"teskari({_expr(arg.value.args[0])})"   # raqamlari teskari tartibdagi son
            return f"butun({a0})"
        if name == "abs":
            return f"|{a0}|"
        if name == "len":
            return f"uzunlik({a0})"
        if name == "str":
            return f"satr({a0})"
        if name == "sqrt":
            return f"√({a0})"
        if name == "floor":
            return f"⌊{a0}⌋"
        if name == "ceil":
            return f"⌈{a0}⌉"
        if name == "round":
            return f"yaxlit({a0})"
        if name == "pow" and len(args) == 2:
            return f"{_wrap(node.args[0], 6)}^{_wrap(node.args[1], 5)}"
        if name == "input":
            return "kiritilgan qiymat"
        if name:
            return f"{name}({', '.join(args)})"
        if isinstance(node.func, ast.Attribute):
            return f"{_expr(node.func.value)}.{node.func.attr}({', '.join(args)})"
        return _s(node)

    if isinstance(node, ast.JoinedStr):
        return "matn"

    return _s(node)


def _expr_top(node) -> str:
    """Tuple'ni qavssiz yozadi (a, b = b, a mod b)."""
    if isinstance(node, ast.Tuple):
        return ", ".join(_expr(e) for e in node.elts)
    return _expr(node)


def _cond(node) -> str:
    if isinstance(node, ast.Name):
        return f"{_expr(node)} = Ha"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) and isinstance(node.operand, ast.Name):
        return f"{_expr(node.operand)} = Yo'q"
    return _expr(node).strip()


# ---------------------------------------------------------------- yordamchilar
def _has_input(node) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "input":
            return True
    return False


def _target_names(target) -> list:
    if isinstance(target, (ast.Tuple, ast.List)):
        res = []
        for e in target.elts:
            res += _target_names(e)
        return res
    return [_expr(target)]


def _print_text(call: ast.Call) -> str:
    shown, literals = [], []
    for a in call.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            literals.append(a.value.strip())
        elif isinstance(a, ast.JoinedStr):
            for v in a.values:
                if isinstance(v, ast.FormattedValue):
                    shown.append(_expr(v.value))
                elif isinstance(v, ast.Constant) and isinstance(v.value, str):
                    literals.append(v.value.strip())
        else:
            shown.append(_expr(a))
    if shown:
        return "Chiqarish: " + ", ".join(shown)
    lit = " ".join(x for x in literals if x).strip(" :")
    return "Chiqarish: " + (lit if lit else "")


def _stop_inclusive(stop, step_positive=True) -> str:
    """range(a, stop) ning oxirgi qiymati: stop-1 (yoki teskari yurishda stop+1)."""
    if step_positive:
        if isinstance(stop, ast.BinOp) and isinstance(stop.op, ast.Add) and _is_num(stop.right, 1):
            return _expr(stop.left)
        if isinstance(stop, ast.Constant) and isinstance(stop.value, int):
            return str(stop.value - 1)
        return f"{_wrap(stop, 4)}-1"
    else:
        if isinstance(stop, ast.BinOp) and isinstance(stop.op, ast.Sub) and _is_num(stop.right, 1):
            return _expr(stop.left)
        if isinstance(stop, ast.Constant) and isinstance(stop.value, int):
            return str(stop.value + 1)
        return f"{_wrap(stop, 4)}+1"


def _for_condition(node: ast.For) -> str:
    var = _expr(node.target)
    it = node.iter
    if isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range" \
            and 1 <= len(it.args) <= 3:
        args = it.args
        if len(args) == 1:
            start, stop, step = "0", args[0], None
        elif len(args) == 2:
            start, stop, step = _expr(args[0]), args[1], None
        else:
            start, stop, step = _expr(args[0]), args[1], args[2]

        positive = True
        step_txt = ""
        if step is not None:
            try:
                sv = ast.literal_eval(step)
                positive = sv > 0
                if sv != 1:
                    step_txt = f" (qadam {sv})"
            except Exception:
                step_txt = f" (qadam {_expr(step)})"
        end = _stop_inclusive(stop, positive)
        return f"{var} = {start} dan {end} gacha{step_txt}"
    return f"{var} ∈ {_expr(it)}"


def _simple_text(stmt) -> str:
    if isinstance(stmt, ast.AugAssign):
        t = _expr(stmt.target)
        bin_node = ast.BinOp(left=stmt.target, op=stmt.op, right=stmt.value)
        return f"{t} = {_expr(bin_node)}"
    if isinstance(stmt, ast.AnnAssign):
        if stmt.value is None:
            return _expr(stmt.target)
        return f"{_expr(stmt.target)} = {_expr_top(stmt.value)}"
    if isinstance(stmt, ast.Assign):
        targets = ", ".join(_expr_top(t) for t in stmt.targets)
        return f"{targets} = {_expr_top(stmt.value)}"
    return _s(stmt)


# ---------------------------------------------------------------- daraxt qurish
def _convert(stmts, func_names) -> list:
    nodes = []
    for st in stmts:
        if isinstance(st, (ast.Import, ast.ImportFrom, ast.Pass, ast.Global, ast.Nonlocal)):
            continue
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
            continue  # docstring / yolg'iz satr

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
            nodes.append({
                "type": "while",
                "condition": _cond(st.test),
                "body": _convert(st.body, func_names),
            })
        elif isinstance(st, ast.Break):
            nodes.append({"type": "assign", "text": "Sikldan chiqish", "_special": True})
        elif isinstance(st, ast.Continue):
            nodes.append({"type": "assign", "text": "Keyingi qadamga o'tish", "_special": True})
        elif isinstance(st, ast.Return):
            txt = "Qaytarish" + (": " + _expr_top(st.value) if st.value is not None else "")
            nodes.append({"type": "output", "text": txt, "_special": True})
        elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
            call = st.value
            fname = call.func.id if isinstance(call.func, ast.Name) else None
            if fname != "input" and _has_input(call):
                nm = []
                if isinstance(call.func, ast.Attribute):
                    nm = [_expr(call.func.value)]
                nodes.append({"type": "input", "text": "", "_names": nm})
            elif fname == "print":
                nodes.append({"type": "output", "text": _print_text(call), "_special": True})
            elif fname == "input":
                nodes.append({"type": "input", "text": "Kiritish", "_names": []})
            elif fname in func_names:
                continue
            elif isinstance(call.func, ast.Attribute) and call.func.attr == "append" and len(call.args) == 1:
                nodes.append({"type": "assign",
                              "text": f"{_expr(call.func.value)} massiviga {_expr(call.args[0])} ni qo'shish",
                              "_special": True})
            else:
                nodes.append({"type": "assign", "text": _expr(call), "_special": True})
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
        if prev and n["type"] == "input" and prev["type"] == "input" and n.get("_names") \
                and prev.get("_names") is not None:
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
