"""Python kodidan Flowgorithm uslubidagi blok-sxema daraxtini (nodes) quruvchi modul."""
import ast

PREC = {ast.Pow: 5, ast.Mult: 4, ast.Div: 4, ast.FloorDiv: 4, ast.Mod: 4, ast.Add: 3, ast.Sub: 3}
BIN_SYMBOL = {ast.Add: " + ", ast.Sub: " - ", ast.Mult: "*", ast.Div: "/",
              ast.FloorDiv: " div ", ast.Mod: " mod ", ast.Pow: "^"}
CMP_SYMBOL = {ast.Eq: "=", ast.NotEq: "≠", ast.Lt: "<", ast.LtE: "≤", ast.Gt: ">", ast.GtE: "≥",
              ast.In: "∈", ast.NotIn: "∉", ast.Is: "=", ast.IsNot: "≠"}


def _s(node) -> str:
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
            return "1"
        if v is False or v is None:
            return "0"
        if isinstance(v, str):
            return "'" + v + "'"
        return repr(v)

    if isinstance(node, ast.Name):
        return "π" if node.id == "pi" else node.id

    if isinstance(node, ast.Tuple):
        return "(" + ", ".join(_expr(e) for e in node.elts) + ")"

    if isinstance(node, ast.List):
        return "[" + ", ".join(_expr(e) for e in node.elts) + "]"

    if isinstance(node, ast.BinOp):
        op = type(node.op)
        p = PREC.get(op, 3)
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

    if isinstance(node, ast.Subscript):
        sl = node.slice
        base = _wrap(node.value, 9)
        if isinstance(sl, ast.Slice):
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
        if name == "abs":
            return f"|{a0}|"
        if name == "sqrt":
            return f"√({a0})"
        if name == "floor":
            return f"⌊{a0}⌋"
        if name == "ceil":
            return f"⌈{a0}⌉"
        if name == "pow" and len(args) == 2:
            return f"{_wrap(node.args[0], 6)}^{_wrap(node.args[1], 5)}"
        if name == "input":
            return "?"
        if name:
            return f"{name}({', '.join(args)})"
        if isinstance(node.func, ast.Attribute):
            return f"{_expr(node.func.value)}.{node.func.attr}({', '.join(args)})"
        return _s(node)

    return _s(node)


def _expr_top(node) -> str:
    if isinstance(node, ast.Tuple):
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


def _is_list_decl(value) -> bool:
    if isinstance(value, (ast.List, ast.ListComp)):
        return True
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Mult):
        return isinstance(value.left, (ast.List, ast.ListComp)) or isinstance(value.right, (ast.List, ast.ListComp))
    return False


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


def _aug_text(stmt) -> str:
    bin_node = ast.BinOp(left=stmt.target, op=stmt.op, right=stmt.value)
    return f"{_expr(stmt.target)} = {_expr(bin_node)}"


def _input_nodes(names):
    if not names:
        return [{"type": "input", "text": "Kiritish"}]
    return [{"type": "input", "text": f"Kiritish: {n}"} for n in names]


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
        if isinstance(st, ast.If) and "__name__" in _s(st.test):
            nodes += _convert(st.body, func_names)
            continue

        if isinstance(st, ast.If):
            nodes.append({
                "type": "if",
                "condition": _cond(st.test),
                "trueBranch": _convert(st.body, func_names),
                "falseBranch": _convert(st.orelse, func_names),
            })
        elif isinstance(st, ast.For):
            body_nodes = _convert(st.body, func_names)
            if body_nodes:
                nodes.append({"type": "for", "condition": _for_condition(st), "body": body_nodes})
        elif isinstance(st, ast.While):
            body_nodes = _convert(st.body, func_names)
            if body_nodes:
                nodes.append({"type": "while", "condition": _cond(st.test), "body": body_nodes})
        elif isinstance(st, ast.Break):
            nodes.append({"type": "assign", "text": "Sikldan chiqish"})
        elif isinstance(st, ast.Continue):
            nodes.append({"type": "assign", "text": "Keyingi qadam"})
        elif isinstance(st, ast.Return):
            nodes.append({"type": "output",
                          "text": "Qaytarish" + (": " + _expr_top(st.value) if st.value is not None else "")})
        elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
            call = st.value
            fname = call.func.id if isinstance(call.func, ast.Name) else None
            is_attr = isinstance(call.func, ast.Attribute)
            if fname == "print":
                nodes.append({"type": "output", "text": _print_text(call)})
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
            else:
                nodes.append({"type": "assign", "text": _expr(call)})
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
                    nodes.append({"type": "assign", "text": f"{_expr_top(t)} = {_expr_top(value)}"})
        else:
            nodes.append({"type": "assign", "text": _s(st)})
    return nodes


def code_to_nodes(code: str) -> list:
    """Python kodidan blok-sxema bloklari ro'yxatini qaytaradi. Sintaksis xato bo'lsa SyntaxError."""
    tree = ast.parse(code)
    return _convert(tree.body, set())
