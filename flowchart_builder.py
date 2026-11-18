"""Python kodidan Flowgorithm / klassik o'zbekcha standartdagi blok-sxema daraxtini (nodes) quruvchi modul.

Asosiy qoidalar:
  * Blok ichiga HECH QACHON Python funksiyalari (int(), float(), str(), len(), range(), append(), math.) chiqmaydi!
  * Har bir amal sof matematik-algoritmik yozuvda bo'ladi:
      - Kiritish: "Kiritish: n"
      - O'zlashtirish: "s = s + 1", "d = b^2 - 4*a*c"
      - Shart: "a^2 + b^2 = c^2", "x mod 2 = 0"
      - Parametrli sikl: "i = 1 dan n gacha"
      - Shartli sikl: "n > 0"
      - Chiqarish: "Chiqarish: s"
  * Massiv e'lon qilish va texnik qatorlar (a = [0]*n, a = [], a.append([0]*m), import) blok-sxemaga qo'shilmaydi!
"""
import ast

PREC = {
    ast.Pow: 5,
    ast.Mult: 4,
    ast.Div: 4,
    ast.FloorDiv: 4,
    ast.Mod: 4,
    ast.Add: 3,
    ast.Sub: 3,
}
BIN_SYMBOL = {
    ast.Add: " + ",
    ast.Sub: " - ",
    ast.Mult: " * ",
    ast.Div: " / ",
    ast.FloorDiv: " div ",
    ast.Mod: " mod ",
    ast.Pow: "^",
}
CMP_SYMBOL = {
    ast.Eq: "=",
    ast.NotEq: "≠",
    ast.Lt: "<",
    ast.LtE: "≤",
    ast.Gt: ">",
    ast.GtE: "≥",
    ast.In: "∈",
    ast.NotIn: "∉",
    ast.Is: "=",
    ast.IsNot: "≠",
}


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
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
        and (value is None or node.value == value)
    )


def _expr(node) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Constant):
        v = node.value
        if v is True:
            return "1"
        if v is False or v is None:
            return "0"
        if isinstance(v, str):
            return f'"{v}"'
        return repr(v)

    if isinstance(node, ast.Name):
        if node.id == "pi":
            return "π"
        if node.id == "True":
            return "1"
        if node.id == "False":
            return "0"
        return node.id

    if isinstance(node, (ast.Tuple, ast.List)):
        return ", ".join(_expr(e) for e in node.elts)

    if isinstance(node, ast.BinOp):
        op = type(node.op)
        p = PREC.get(op, 3)
        if op is ast.Pow:
            if _is_num(node.right, 0.5):
                return f"√({_expr(node.left)})"
            if _is_num(node.right, 2) and isinstance(node.left, ast.Name):
                return f"{_expr(node.left)}²"
            if _is_num(node.right, 3) and isinstance(node.left, ast.Name):
                return f"{_expr(node.left)}³"
            base = _wrap(node.left, p + 1)
            if isinstance(node.left, ast.UnaryOp) or (_is_num(node.left) and node.left.value < 0):
                base = f"({_expr(node.left)})"
            return f"{base}^{_wrap(node.right, p)}"
        left = _wrap(node.left, p)
        right = _wrap(node.right, p + 1)
        return f"{left}{BIN_SYMBOL.get(op, ' ? ')}{right}"

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
            out += f" {CMP_SYMBOL.get(type(op), '=')} {_wrap(cmp, 2)}"
        return out

    if isinstance(node, ast.IfExp):
        return f"{_expr(node.body)} (agar {_expr(node.test)}, aks holda {_expr(node.orelse)})"

    if isinstance(node, ast.Subscript):
        sl = node.slice
        base = _wrap(node.value, 9)
        if isinstance(sl, ast.Slice):
            lo = _expr(sl.lower) if sl.lower is not None else "0"
            up = _expr(sl.upper) if sl.upper is not None else ""
            return f"{base}[{lo}..{up}]"
        if isinstance(sl, ast.Tuple):
            return base + "".join(f"[{_expr(e)}]" for e in sl.elts)
        return f"{base}[{_expr(sl)}]"

    if isinstance(node, ast.Attribute):
        val = _expr(node.value)
        if val == "math":
            return "π" if node.attr == "pi" else node.attr
        return f"{val}.{node.attr}"

    if isinstance(node, ast.Call):
        fname = None
        if isinstance(node.func, ast.Name):
            fname = node.func.id
        elif isinstance(node.func, ast.Attribute):
            fname = node.func.attr

        args = [_expr(a) for a in node.args]
        a0 = args[0] if args else ""

        # Python tur almashtirish funksiyalarini blok-sxemada ko'rsatmaymiz (toza o'zgaruvchi qoladi)
        if fname in ("int", "float", "str", "bool", "round", "floor", "trunc"):
            if fname == "round" and len(args) == 1:
                return f"yaxlit({a0})"
            if fname == "int" and len(node.args) == 1 and isinstance(node.args[0], ast.BinOp) and isinstance(node.args[0].op, ast.Add) and _is_num(node.args[0].right, 0.5):
                return f"yaxlit({_expr(node.args[0].left)})"
            return a0 or "0"
        if fname == "ceil":
            return f"⌈{a0}⌉"
        if fname == "abs":
            return f"|{a0}|"
        if fname == "sqrt":
            return f"√({a0})"
        if fname == "pow" and len(args) == 2:
            return f"{_wrap(node.args[0], 6)}^{_wrap(node.args[1], 5)}"
        if fname == "len":
            return f"uzunlik({a0})"
        if fname == "input":
            return ""
        if fname in ("max", "min", "sin", "cos", "tan", "asin", "acos", "atan", "gcd"):
            uz_name = "EKUB" if fname == "gcd" else fname
            return f"{uz_name}({', '.join(args)})"
        if fname:
            return f"{fname}({', '.join(args)})"
        return ""

    return ""


def _expr_top(node) -> str:
    if isinstance(node, (ast.Tuple, ast.List)):
        return ", ".join(_expr(e) for e in node.elts)
    return _expr(node)


def _cond(node) -> str:
    if isinstance(node, ast.Name):
        return f"{_expr(node)} = 1"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) and isinstance(node.operand, ast.Name):
        return f"{_expr(node.operand)} = 0"
    return _expr(node).strip()


def _has_input(node) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name) and n.func.id == "input":
                return True
            if isinstance(n.func, ast.Attribute) and n.func.attr in ("split", "readline", "read"):
                return True
    return False


def _target_names(target) -> list:
    if isinstance(target, (ast.Tuple, ast.List)):
        res = []
        for e in target.elts:
            res += _target_names(e)
        return res
    return [_expr(target)]


def _is_list_decl(value) -> bool:
    """a = [], a = [0]*n, [[0]*m for ...] kabi texnik massiv e'lonlari blok-sxemada ko'rsatilmaydi."""
    if isinstance(value, (ast.List, ast.ListComp, ast.Dict, ast.Set)):
        return True
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Mult):
        return isinstance(value.left, (ast.List, ast.ListComp)) or isinstance(value.right, (ast.List, ast.ListComp))
    return False


def _is_list_init_loop(node: ast.For) -> bool:
    """Faqat massiv/matritsani nollar bilan to'ldiruvchi texnik siklni aniqlash (a.append([0]*m))."""
    if len(node.body) == 1:
        st = node.body[0]
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
            call = st.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == "append" and len(call.args) == 1:
                if _is_list_decl(call.args[0]) and not _has_input(call.args[0]):
                    return True
    return False


def _print_text(call: ast.Call) -> str:
    shown, literals = [], []
    for a in call.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            val = a.value.strip().rstrip(":").strip()
            if val:
                literals.append(val)
        elif isinstance(a, ast.JoinedStr):
            for v in a.values:
                if isinstance(v, ast.FormattedValue):
                    shown.append(_expr(v.value))
                elif isinstance(v, ast.Constant) and isinstance(v.value, str):
                    val = v.value.strip().rstrip(":").strip()
                    if val:
                        literals.append(val)
        else:
            ex = _expr(a)
            if ex:
                shown.append(ex)

    if shown:
        return "Chiqarish: " + ", ".join(shown)
    lit = " ".join(x for x in literals if x).strip()
    if lit:
        return f'Chiqarish: "{lit}"'
    return ""


def _stop_inclusive(stop, step_positive=True) -> str:
    if step_positive:
        if isinstance(stop, ast.BinOp) and isinstance(stop.op, ast.Add) and _is_num(stop.right, 1):
            return _expr(stop.left)
        if isinstance(stop, ast.Constant) and isinstance(stop.value, int):
            return str(stop.value - 1)
        return f"{_wrap(stop, 4)} - 1"
    else:
        if isinstance(stop, ast.BinOp) and isinstance(stop.op, ast.Sub) and _is_num(stop.right, 1):
            return _expr(stop.left)
        if isinstance(stop, ast.Constant) and isinstance(stop.value, int):
            return str(stop.value + 1)
        return f"{_wrap(stop, 4)} + 1"


def _for_condition(node: ast.For) -> str:
    var = _expr(node.target)
    it = node.iter
    if (
        isinstance(it, ast.Call)
        and isinstance(it.func, ast.Name)
        and it.func.id == "range"
        and 1 <= len(it.args) <= 3
    ):
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


def _aug_text(stmt) -> str:
    bin_node = ast.BinOp(left=stmt.target, op=stmt.op, right=stmt.value)
    return f"{_expr(stmt.target)} = {_expr(bin_node)}"


def _input_nodes(names):
    clean = [n for n in names if n]
    if not clean:
        return [{"type": "input", "text": "Kiritish"}]
    return [{"type": "input", "text": f"Kiritish: {', '.join(clean)}"}]


def _convert(stmts, func_names) -> list:
    nodes = []
    for st in stmts:
        if isinstance(st, (ast.Import, ast.ImportFrom, ast.Pass, ast.Global, ast.Nonlocal)):
            continue
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
            continue

        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_names.add(st.name)
            nodes += _convert(st.body, func_names)
            continue
        if isinstance(st, (ast.Try, ast.With, ast.AsyncWith)):
            nodes += _convert(st.body, func_names)
            continue
        if isinstance(st, ast.If) and "__name__" in ast.unparse(st.test):
            nodes += _convert(st.body, func_names)
            continue

        if isinstance(st, ast.If):
            t_branch = _convert(st.body, func_names)
            f_branch = _convert(st.orelse, func_names)
            if t_branch or f_branch:
                nodes.append({
                    "type": "if",
                    "condition": _cond(st.test),
                    "trueBranch": t_branch,
                    "falseBranch": f_branch,
                })
        elif isinstance(st, ast.For):
            if _is_list_init_loop(st):
                continue
            body_nodes = _convert(st.body, func_names)
            if body_nodes:
                nodes.append({
                    "type": "for",
                    "condition": _for_condition(st),
                    "body": body_nodes,
                })
        elif isinstance(st, ast.While):
            body_nodes = _convert(st.body, func_names)
            if body_nodes:
                nodes.append({
                    "type": "while",
                    "condition": _cond(st.test),
                    "body": body_nodes,
                })
        elif isinstance(st, ast.Break):
            nodes.append({"type": "assign", "text": "Sikldan chiqish"})
        elif isinstance(st, ast.Continue):
            nodes.append({"type": "assign", "text": "Keyingi qadamga o'tish"})
        elif isinstance(st, ast.Return):
            if st.value is not None:
                nodes.append({"type": "output", "text": f"Chiqarish: {_expr_top(st.value)}"})
        elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
            call = st.value
            fname = call.func.id if isinstance(call.func, ast.Name) else None
            is_attr = isinstance(call.func, ast.Attribute)
            if fname == "print":
                ptxt = _print_text(call)
                if ptxt:
                    nodes.append({"type": "output", "text": ptxt})
            elif fname == "input":
                nodes += _input_nodes([])
            elif fname in func_names:
                continue
            elif is_attr and call.func.attr == "append" and len(call.args) == 1:
                arg = call.args[0]
                if _has_input(arg):
                    nodes += _input_nodes([_expr(call.func.value)])
                elif _is_list_decl(arg):
                    continue
                else:
                    a = _expr(call.func.value)
                    nodes.append({"type": "assign", "text": f"{a} ga {_expr(arg)} qo'shish"})
            elif _has_input(call):
                nodes += _input_nodes([_expr(call.func.value)] if is_attr else [])
        elif isinstance(st, ast.AugAssign):
            nodes.append({"type": "assign", "text": _aug_text(st)})
        elif isinstance(st, (ast.Assign, ast.AnnAssign)):
            value = st.value
            targets = st.targets if isinstance(st, ast.Assign) else [st.target]
            if value is None:
                continue
            if _has_input(value):
                names = []
                for t in targets:
                    names += _target_names(t)
                nodes += _input_nodes(names)
            elif _is_list_decl(value):
                continue
            else:
                for t in targets:
                    lhs = _expr_top(t)
                    rhs = _expr_top(value)
                    if lhs and rhs and lhs != rhs:
                        nodes.append({"type": "assign", "text": f"{lhs} = {rhs}"})

    # Ketma-ket kelgan Kiritish bloklarini (masalan Kiritish: k, Kiritish: l, Kiritish: m) bitta chiroyli blokka birlashtirish
    merged = []
    for nd in nodes:
        if (
            nd["type"] == "input"
            and merged
            and merged[-1]["type"] == "input"
            and nd["text"].startswith("Kiritish: ")
            and merged[-1]["text"].startswith("Kiritish: ")
            and "[" not in nd["text"]
            and "[" not in merged[-1]["text"]
            and len(merged[-1]["text"]) + len(nd["text"]) < 34
        ):
            var_part = nd["text"].replace("Kiritish: ", "").strip()
            merged[-1]["text"] += f", {var_part}"
        else:
            merged.append(nd)

    return merged


def code_to_nodes(code: str) -> list:
    """Python kodidan toza blok-sxema bloklari ro'yxatini qaytaradi."""
    tree = ast.parse(code)
    return _convert(tree.body, set())
