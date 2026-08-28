"""I10: converge redundant full-app reruns inside fragments.

Converts `st.rerun()` -> `st.rerun(scope="fragment")` ONLY when the call is lexically
inside a function decorated with `@st.fragment` / `@safe_fragment` (or their call form).
Page-level `st.rerun()` (and `st.rerun(scope="app")`) are left untouched, because a
fragment-scoped rerun there would raise at runtime.

Byte/char offset handling mirrors _perf_table_height.py (ast end_col_offset is byte-based;
the source str is char-indexed).
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_DIRS = ["pages", "modules"]


def line_byte_starts(src):
    starts = [0]
    for line in src.split("\n"):
        starts.append(starts[-1] + len(line.encode("utf-8")) + 1)
    return starts


def byte_to_char(src, byte_pos):
    b = 0
    for i, ch in enumerate(src):
        if b >= byte_pos:
            return i
        b += len(ch.encode("utf-8"))
    return len(src)


def is_fragment_decorator(dec):
    """True if a decorator marks the function as a Streamlit fragment."""
    if isinstance(dec, ast.Call):
        dec = dec.func
    # @st.fragment / @page_guard.safe_fragment -> Attribute.attr
    if isinstance(dec, ast.Attribute) and dec.attr in ("fragment", "safe_fragment"):
        return True
    # @safe_fragment (name, if imported directly)
    if isinstance(dec, ast.Name) and dec.id == "safe_fragment":
        return True
    return False


def process_file(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"  SKIP (syntax): {path}: {e}")
        return 0

    starts = line_byte_starts(src)
    # Collect (start_char, end_char) spans of st.rerun() calls that should be rewritten.
    ops = []

    # Walk with function-stack context to know the nearest enclosing function's decorators.
    class V(ast.NodeVisitor):
        def __init__(self):
            self.func_stack = []  # each entry: bool is_fragment

        def _enter_func(self, node):
            frag = any(is_fragment_decorator(d) for d in node.decorator_list)
            self.func_stack.append(frag)

        def _exit_func(self):
            self.func_stack.pop()

        def visit_FunctionDef(self, node):
            self._enter_func(node)
            self.generic_visit(node)
            self._exit_func()

        # async def too
        def visit_AsyncFunctionDef(self, node):
            self._enter_func(node)
            self.generic_visit(node)
            self._exit_func()

        def visit_Call(self, node):
            ast.NodeVisitor.generic_visit(self, node)
            f = node.func
            if not (isinstance(f, ast.Attribute) and f.attr == "rerun"):
                return
            # Only `st.rerun()` with no args / keywords.
            if node.args or node.keywords:
                return
            in_fragment = bool(self.func_stack) and self.func_stack[-1]
            if not in_fragment:
                return
            start = byte_to_char(src, starts[node.lineno - 1] + node.col_offset)
            end = byte_to_char(src, starts[node.end_lineno - 1] + node.end_col_offset)
            snippet = src[start:end]
            if snippet != "st.rerun()":
                # Defensive: only rewrite the exact bare form.
                return
            ops.append((start, end))

    V().visit(tree)
    if not ops:
        return 0
    # Apply from right to left so earlier offsets stay valid.
    ops.sort(key=lambda x: x[0], reverse=True)
    new_src = src
    for s, e in ops:
        new_src = new_src[:s] + 'st.rerun(scope="fragment")' + new_src[e:]
    try:
        ast.parse(new_src)
    except SyntaxError:
        print(f"  SKIP (would break syntax): {path}")
        return 0
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new_src)
    return len(ops)


def main():
    files = []
    for d in TARGET_DIRS:
        base = os.path.join(ROOT, d)
        for fn in sorted(os.listdir(base)):
            if fn.endswith(".py"):
                files.append(os.path.join(base, fn))
    total = 0
    for fp in files:
        n = process_file(fp)
        if n:
            total += n
            print(f"  {fp}  rerun->fragment={n}")
    print(f"TOTAL rerun-converged={total}")


if __name__ == "__main__":
    main()
