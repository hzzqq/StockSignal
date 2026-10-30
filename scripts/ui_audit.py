# -*- coding: utf-8 -*-
"""P0-4 UI 审计基线脚本（AST 级，幂等可重跑）。

产出 docs/ui_audit_baseline.json（UI 改造前后的对照基线），并打印控制台摘要。

两组口径（全部 AST 实测，不用字符串 grep，不误伤注释；数字绝不编造）：

A. doc_baseline —— 母本《KS_改善执行提示词_交付版.md》P0-4 五维，scope=pages/*.py：
   a) 含 unsafe_allow_html=True 的页数/调用数
   b) 旧 sf_* 组件（sf_card/sf_metric/sf_table/sf_pill/sf_stat/sf_one_line/sf_alert/sf_tag）
      调用页数/调用数；另附 referenced_pages=调用∪import∪名称引用的宽口径页数
      （母本「引用 50 页」即宽口径；函数族实际仅 ui_theme.py 的 sf_card/sf_metric 在位）
   c) 调用 st.metric 的页数/调用数（含缺 delta_color 子集）
   d) 完全不（直接）import modules.ui_kit 的页数；另附 pure_legacy_pages=
      不 import ui_kit 且无 sf_*/xc_* 调用的「纯旧页」窄口径
   e) 使用 xc_kpi_grid/chart_card/table_wrap/page_hero/xc_section_header 的页数/调用数

B. hygiene_baseline —— T-353 卫生五维，scope=仓库全部 .py（排除 tests、__pycache__、
   .venv、.git、.workbuddy、.trae、site-packages、node_modules）：
   1) use_container_width= 违规（废弃 API，守卫 test_streamlit_api_hygiene 同口径）
   2) 裸 st.rerun()（无 scope= 参数 → 整页重跑）计数 + 分页分布
   3) 纯 except-pass（ExceptHandler 体仅 Pass）
   4) st.metric 缺 delta_color（守卫 test_metric_delta_color 为渐进白名单制，
      非白名单页的缺口在此如实计数，二者口径不矛盾）
   5) st_autorefresh / streamlit_autorefresh / trading_autorefresh 残留
      （imports / 直调 calls / 其他引用分开计；Call 的 func 节点不重复计入 refs）

诚实口径：SyntaxError / 解码失败文件如实记入 report["errors"]，不静默跳过。
脚本本身只审计不修改，退出码恒 0（它是尺子，不是守卫；守卫另行由 tests/ 承担）。
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DEFAULT = ROOT / "docs" / "ui_audit_baseline.json"

_SKIP_DIRS = {
    "__pycache__", ".venv", "venv", "site-packages", "node_modules",
    ".git", ".workbuddy", ".trae", ".idea", ".vscode", "build", "dist",
}

SF_COMPONENTS = (
    "sf_card", "sf_metric", "sf_table", "sf_pill", "sf_stat",
    "sf_one_line", "sf_alert", "sf_tag",
)
XC_COMPONENTS = (
    "xc_kpi_grid", "chart_card", "table_wrap", "page_hero", "xc_section_header",
)
AUTOREFRESH_NAMES = ("st_autorefresh", "streamlit_autorefresh", "trading_autorefresh")


def _is_skip(path: Path) -> bool:
    parts = path.parts
    if any(p in _SKIP_DIRS for p in parts):
        return True
    if "tests" in parts:  # 守卫/测试自身不进基线
        return True
    return False


def iter_repo_py():
    return [p for p in sorted(ROOT.rglob("*.py")) if not _is_skip(p)]


def parse_tree(path: Path):
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, "unicode_decode_error"
    except OSError as e:
        return None, f"read_error:{e.__class__.__name__}"
    try:
        return ast.parse(src), None
    except SyntaxError as e:
        return None, f"syntax_error:line{e.lineno}"


def _call_attr(call: ast.Call):
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _is_st_metric(call: ast.Call) -> bool:
    """与 tests/test_metric_delta_color.py 的 _metric_calls 同口径。"""
    f = call.func
    if not (isinstance(f, ast.Attribute) and f.attr == "metric"):
        return False
    base = f.value
    return (isinstance(base, ast.Attribute) and base.attr == "st") or (
        isinstance(base, ast.Name) and base.id == "st"
    )


def _has_kw(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


def _kw_is_const_true(call: ast.Call, name: str) -> bool:
    return any(
        kw.arg == name and isinstance(kw.value, ast.Constant) and kw.value.value is True
        for kw in call.keywords
    )


def analyze_file(path: Path, rel: str) -> dict:
    """单文件全维度 AST 明细（两组口径共用一次解析）。"""
    out = {
        "rel": rel,
        "top": rel.replace("\\", "/").split("/")[0],
        "is_page": rel.replace("\\", "/").startswith("pages/"),
        "error": None,
        "unsafe_allow_html": [],          # [lineno]
        "sf_calls": [],                   # [(lineno, name)]
        "sf_imports": [],                 # [(lineno, full)]
        "sf_refs": [],                    # [(lineno, name)]  非调用引用
        "xc_calls": [],                   # [(lineno, name)]
        "st_metric_all": [],              # [lineno]
        "st_metric_missing": [],          # [lineno]  缺 delta_color
        "ui_kit_import": False,
        "use_container_width": [],        # [lineno]
        "st_rerun_all": [],               # [(lineno, bare_bool)]
        "pure_except_pass": [],           # [lineno]
        "autorefresh_imports": [],        # [(lineno, full)]
        "autorefresh_calls": [],          # [(lineno, name)]
        "autorefresh_refs": [],           # [(lineno, name)]  非调用非 import 引用
    }
    tree, err = parse_tree(path)
    if tree is None:
        out["error"] = err
        return out

    call_func_ids: set[int] = set()  # Call.func 节点 id，防 Name/Attribute 重复计数
    for node in ast.walk(tree):
        # ---- import / from-import ----
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = (getattr(node, "module", "") or "")
            for a in node.names:
                if isinstance(node, ast.Import):
                    full = a.name
                    if full == "modules.ui_kit" or full.startswith("modules.ui_kit.") or full == "ui_kit":
                        out["ui_kit_import"] = True
                else:
                    full = f"{module}.{a.name}" if module else a.name
                    if module == "modules.ui_kit" or module.startswith("modules.ui_kit.") or module.endswith(".ui_kit"):
                        out["ui_kit_import"] = True
                    elif module == "modules" and a.name == "ui_kit":
                        out["ui_kit_import"] = True
                tail = full.split(".")[-1]
                if tail in AUTOREFRESH_NAMES or a.asname in AUTOREFRESH_NAMES:
                    out["autorefresh_imports"].append((node.lineno, full))
                if a.name in SF_COMPONENTS or a.asname in SF_COMPONENTS:
                    out["sf_imports"].append((node.lineno, full))
            continue

        # ---- 纯 except-pass ----
        if isinstance(node, ast.ExceptHandler):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                out["pure_except_pass"].append(node.lineno)
            continue

        # ---- 调用 ----
        if isinstance(node, ast.Call):
            call_func_ids.add(id(node.func))
            attr = _call_attr(node)
            if attr in SF_COMPONENTS:
                out["sf_calls"].append((node.lineno, attr))
            if attr in XC_COMPONENTS:
                out["xc_calls"].append((node.lineno, attr))
            if _is_st_metric(node):
                out["st_metric_all"].append(node.lineno)
                if not _has_kw(node, "delta_color"):
                    out["st_metric_missing"].append(node.lineno)
            if _kw_is_const_true(node, "unsafe_allow_html"):
                out["unsafe_allow_html"].append(node.lineno)
            if _has_kw(node, "use_container_width"):
                out["use_container_width"].append(node.lineno)
            f = node.func
            if (
                isinstance(f, ast.Attribute) and f.attr == "rerun"
                and isinstance(f.value, ast.Name) and f.value.id == "st"
            ):
                out["st_rerun_all"].append((node.lineno, not _has_kw(node, "scope")))
            if attr in AUTOREFRESH_NAMES:
                out["autorefresh_calls"].append((node.lineno, attr))
            continue

        # ---- 非调用引用（排除 Call 的 func 节点，防重复计数） ----
        if id(node) in call_func_ids:
            continue
        if isinstance(node, ast.Name):
            if node.id in AUTOREFRESH_NAMES:
                out["autorefresh_refs"].append((node.lineno, node.id))
            elif node.id in SF_COMPONENTS:
                out["sf_refs"].append((node.lineno, node.id))
        elif isinstance(node, ast.Attribute):
            if node.attr in AUTOREFRESH_NAMES:
                out["autorefresh_refs"].append((node.lineno, node.attr))
            elif node.attr in SF_COMPONENTS:
                out["sf_refs"].append((node.lineno, node.attr))

    return out


def _group_dir(files: list[dict]) -> Counter:
    return Counter(f["top"] for f in files)


def _dim(files: list[dict], key: str) -> dict:
    hit = [f for f in files if f[key]]
    return {
        "count": sum(len(f[key]) for f in hit),
        "files": len(hit),
        "by_dir": dict(sorted(_group_dir(hit).items())),
        "locations": _loc(hit, key),
    }


def _loc(files: list[dict], key: str, with_name: bool = False) -> list[str]:
    rows = []
    for f in files:
        for item in f[key]:
            if isinstance(item, tuple):
                lineno, name = item
                rows.append(f"{f['rel']}:{lineno}" + (f" ({name})" if with_name else ""))
            else:
                rows.append(f"{f['rel']}:{item}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="P0-4 UI 审计基线（AST 级）")
    ap.add_argument("--out", default=str(OUT_DEFAULT), help="输出 JSON 路径")
    args = ap.parse_args()

    files = [analyze_file(p, str(p.relative_to(ROOT))) for p in iter_repo_py()]
    errors = [
        {"file": f["rel"], "error": f["error"]} for f in files if f["error"]
    ]
    pages = [f for f in files if f["is_page"]]

    # ---------- A. doc_baseline（scope=pages/*.py） ----------
    unsafe_pages = [f for f in pages if f["unsafe_allow_html"]]
    sf_pages = [f for f in pages if f["sf_calls"]]
    sf_ref_pages = [
        f for f in pages if f["sf_calls"] or f["sf_imports"] or f["sf_refs"]
    ]
    sf_by_comp = Counter(name for f in pages for _, name in f["sf_calls"])
    metric_pages = [f for f in pages if f["st_metric_all"]]
    metric_missing_pages = [f for f in pages if f["st_metric_missing"]]
    no_uikit_pages = [f for f in pages if not f["ui_kit_import"]]
    pure_legacy_pages = [
        f for f in no_uikit_pages if not f["sf_calls"] and not f["xc_calls"]
    ]
    xc_pages = [f for f in pages if f["xc_calls"]]
    xc_by_comp = Counter(name for f in pages for _, name in f["xc_calls"])

    doc_baseline = {
        "scope": "pages/*.py",
        "page_count": len(pages),
        "unsafe_allow_html": {
            "pages": len(unsafe_pages),
            "calls": sum(len(f["unsafe_allow_html"]) for f in unsafe_pages),
            "page_files": sorted(f["rel"].replace("\\", "/") for f in unsafe_pages),
        },
        "sf_legacy_components": {
            "pages": len(sf_pages),
            "calls": sum(len(f["sf_calls"]) for f in sf_pages),
            "by_component": dict(sorted(sf_by_comp.items())),
            "referenced_pages": len(sf_ref_pages),
            "note": (
                "pages/calls=AST 调用口径；referenced_pages=调用∪import∪名称引用宽口径"
                "（母本『引用』口径）；函数族实际仅 modules/ui_theme.py 的 sf_card/sf_metric 在位"
            ),
            "page_files": sorted(f["rel"].replace("\\", "/") for f in sf_pages),
        },
        "st_metric": {
            "pages": len(metric_pages),
            "calls": sum(len(f["st_metric_all"]) for f in metric_pages),
            "missing_delta_color_pages": len(metric_missing_pages),
            "missing_delta_color_calls": sum(
                len(f["st_metric_missing"]) for f in metric_missing_pages
            ),
        },
        "no_ui_kit_import": {
            "pages": len(no_uikit_pages),
            "pure_legacy_pages": len(pure_legacy_pages),
            "note": (
                "pages=直接 import 口径（import modules.ui_kit / from modules.ui_kit "
                "import / from modules import ui_kit）；pure_legacy_pages=其中"
                "无 sf_*/xc_* 调用的纯旧页（母本『纯旧页』口径）"
            ),
            "page_files": sorted(f["rel"].replace("\\", "/") for f in no_uikit_pages),
        },
        "xc_new_components": {
            "pages": len(xc_pages),
            "calls": sum(len(f["xc_calls"]) for f in xc_pages),
            "by_component": dict(sorted(xc_by_comp.items())),
        },
    }

    # ---------- B. hygiene_baseline（scope=仓库 .py） ----------
    rerun_hit = [f for f in files if f["st_rerun_all"]]
    bare_hit = [f for f in files if any(b for _, b in f["st_rerun_all"])]
    per_page = Counter(
        f["rel"].replace("\\", "/")
        for f in bare_hit
        for _, b in f["st_rerun_all"] if b
    )
    ar_import_hit = [f for f in files if f["autorefresh_imports"]]
    ar_call_hit = [f for f in files if f["autorefresh_calls"]]
    ar_ref_hit = [f for f in files if f["autorefresh_refs"]]

    hygiene_baseline = {
        "scope": "仓库 .py（排除 tests/__pycache__/.venv/.git/.workbuddy/.trae 等）",
        "file_count": len(files),
        "use_container_width": _dim(files, "use_container_width"),
        "bare_st_rerun": {
            "all_calls": sum(len(f["st_rerun_all"]) for f in rerun_hit),
            "bare_calls": sum(1 for f in bare_hit for _, b in f["st_rerun_all"] if b),
            "pages_affected": len(per_page),
            "by_dir": dict(sorted(_group_dir(bare_hit).items())),
            "per_page_top10": [
                {"file": k, "count": v}
                for k, v in sorted(per_page.items(), key=lambda kv: -kv[1])[:10]
            ],
            "locations": _loc(bare_hit, "st_rerun_all"),
        },
        "pure_except_pass": _dim(files, "pure_except_pass"),
        "st_metric_missing_delta_color": _dim(files, "st_metric_missing"),
        "autorefresh_residue": {
            "imports": {
                "count": sum(len(f["autorefresh_imports"]) for f in ar_import_hit),
                "by_dir": dict(sorted(_group_dir(ar_import_hit).items())),
                "locations": _loc(ar_import_hit, "autorefresh_imports", with_name=True),
            },
            "direct_calls": {
                "count": sum(len(f["autorefresh_calls"]) for f in ar_call_hit),
                "by_dir": dict(sorted(_group_dir(ar_call_hit).items())),
                "locations": _loc(ar_call_hit, "autorefresh_calls", with_name=True),
            },
            "other_refs": {
                "count": sum(len(f["autorefresh_refs"]) for f in ar_ref_hit),
                "locations": _loc(ar_ref_hit, "autorefresh_refs", with_name=True),
            },
        },
    }

    report = {
        "meta": {
            "tool": "scripts/ui_audit.py",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "doc_source": "docs/KS_改善执行提示词_交付版.md P0-4 + T-353 卫生五维",
            "note": "AST 级实测，幂等可重跑，重跑即刷新快照；作为 UI 改造前后对照基线。脚本只读不写代码。",
        },
        "doc_baseline": doc_baseline,
        "hygiene_baseline": hygiene_baseline,
        "errors": errors,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---------- 控制台摘要 ----------
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("== P0-4 UI 审计基线（AST 级）==")
    d = doc_baseline
    print(f"[doc_baseline] scope=pages/*.py, pages={d['page_count']}")
    print(f"  a) unsafe_allow_html=True   pages={d['unsafe_allow_html']['pages']:>3}  calls={d['unsafe_allow_html']['calls']}")
    s = d["sf_legacy_components"]
    print(f"  b) sf_* 旧组件              pages={s['pages']:>3}  calls={s['calls']}  引用页(宽口径)={s['referenced_pages']}  by={s['by_component']}")
    print(f"  c) st.metric                pages={d['st_metric']['pages']:>3}  calls={d['st_metric']['calls']}  缺delta_color pages={d['st_metric']['missing_delta_color_pages']} calls={d['st_metric']['missing_delta_color_calls']}")
    print(f"  d) 不 import ui_kit         pages={d['no_ui_kit_import']['pages']:>3}  纯旧页={d['no_ui_kit_import']['pure_legacy_pages']}")
    print(f"  e) xc_* 新组件              pages={d['xc_new_components']['pages']:>3}  calls={d['xc_new_components']['calls']}  by={d['xc_new_components']['by_component']}")
    h = hygiene_baseline
    b = h["bare_st_rerun"]
    print(f"[hygiene_baseline] scope=仓库 .py, files={h['file_count']}")
    print(f"  1) use_container_width      calls={h['use_container_width']['count']}")
    print(f"  2) 裸 st.rerun()            bare={b['bare_calls']} / all={b['all_calls']}  pages={b['pages_affected']}  by_dir={b['by_dir']}")
    print(f"  3) 纯 except-pass           count={h['pure_except_pass']['count']}  by_dir={h['pure_except_pass']['by_dir']}")
    print(f"  4) st.metric 缺 delta_color calls={h['st_metric_missing_delta_color']['count']}")
    ar = h["autorefresh_residue"]
    print(f"  5) autorefresh 残留         imports={ar['imports']['count']}  direct_calls={ar['direct_calls']['count']}  other_refs={ar['other_refs']['count']}  by_dir={ar['imports']['by_dir']}|{ar['direct_calls']['by_dir']}")
    if errors:
        print(f"[errors] {len(errors)} 个文件解析失败（已记入 JSON，未静默）:")
        for e in errors:
            print(f"    {e['file']}: {e['error']}")
    print(f"快照已写入 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
