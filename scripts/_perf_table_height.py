"""I8/I9: add height=400 to st.dataframe calls that lack a height keyword.

Enables Streamlit virtual scrolling for potentially-large tables; tiny tables are
unaffected (Streamlit shows all rows if they fit the height). Uses AST so it only
touches real call sites.

IMPORTANT: ast.end_col_offset is a UTF-8 *byte* offset, but the source we edit is a
Python str (indexed by *characters*). On lines containing CJK characters this would
misalign, so we convert the absolute byte position back to a char index before editing.
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_DIRS = ["pages", "modules"]
HEIGHT_ARG = "height=400"


def line_byte_starts(src):
    """Byte offset (UTF-8) of the start of each line.

    line_byte_starts[0] = 0; line_byte_starts[i] = byte start of line i (1-indexed).
    """
    starts = [0]
    for line in src.split("\n"):
        # +1 accounts for the "\n" separator (a trailing "\r", if present, is part of
        # `line` and counted in its byte length, so this stays correct for CRLF too).
        starts.append(starts[-1] + len(line.encode("utf-8")) + 1)
    return starts


def byte_to_char(src, byte_pos):
    """Convert an absolute UTF-8 byte offset into a character index into `src`."""
    b = 0
    for i, ch in enumerate(src):
        if b >= byte_pos:
            return i
        b += len(ch.encode("utf-8"))
    return len(src)


def process_file(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"  SKIP (syntax): {path}: {e}")
        return 0
    starts = line_byte_starts(src)
    ops = []

    class V(ast.NodeVisitor):
        def visit_Call(self, node):
            ast.NodeVisitor.generic_visit(self, node)
            f = node.func
            if not (isinstance(f, ast.Attribute) and f.attr == "dataframe"):
                return
            for kw in node.keywords:
                if kw.arg == "height":
                    return  # already has height
            # Convert ast's byte offset -> character index in the source string.
            abs_byte = starts[node.end_lineno - 1] + node.end_col_offset
            close_off = byte_to_char(src, abs_byte) - 1
            if close_off < 0 or close_off >= len(src) or src[close_off] != ")":
                # Fallback: scan backward for the closing ')'.
                j = close_off if 0 <= close_off < len(src) else len(src) - 1
                while j >= 0 and src[j] != ")":
                    j -= 1
                if j < 0:
                    return
                close_off = j
            ops.append((close_off, HEIGHT_ARG))

    V().visit(tree)
    if not ops:
        return 0
    ops.sort(key=lambda x: x[0], reverse=True)
    new_src = src
    for off, text in ops:
        # Find the last non-whitespace char before the closing ')'.
        # If it is already a comma (e.g. the previous arg line ends with "},"),
        # do NOT add a leading comma (that would create a double comma -> SyntaxError).
        j = off - 1
        while j >= 0 and src[j] in " \t\r\n":
            j -= 1
        if j >= 0 and src[j] == ",":
            insert = text  # e.g. "height=400" -> "}, height=400)"
        else:
            insert = ", " + text  # e.g. ", height=400"
        new_src = new_src[:off] + insert + new_src[off:]
    # Safety: never write broken code. Validate before persisting.
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
            print(f"  {fp}  +height={n}")
    print(f"TOTAL height-added={total}")


if __name__ == "__main__":
    main()
