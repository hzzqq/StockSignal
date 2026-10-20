# -*- coding: utf-8 -*-
"""
清理 StockSignal 本地缓存，避免 data/ 无限膨胀（shepherd_cache 曾占 317M / 5547 个文件）。

默认只清理 data/shepherd_cache/ 下 mtime 超过 --days 天的文件。
这些是「按股票代码缓存的日线 CSV」，缺失会自动重新拉取，删了安全。

用法:
  python clean_cache.py --dry-run            # 预览将删除哪些
  python clean_cache.py --days 30 --yes      # 删除 30 天前的缓存 CSV
  python clean_cache.py --include-db --yes   # 连同 cache.db / market_cache.db / news.db 一起清
                                            #（三个 SQLite 缓存也是可再生的，但清掉后首次访问会重新预热）

安全: 不会删除缓存目录之外的任何文件；删除前必须显式 --yes（或 --dry-run 仅预览）。
"""
import argparse
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CACHE_DIR = HERE / "data" / "shepherd_cache"
DB_FILES = ["cache.db", "market_cache.db", "news.db"]
V2_CACHE_DIR = HERE / "data" / "shepherd_cache_v2"

import sys  # noqa: E402
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from modules.cache_maintenance import run_cache_maintenance  # noqa: E402


def human(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1e6:.1f} MB"
    if n >= 1_000:
        return f"{n / 1e3:.1f} KB"
    return f"{n} B"


def collect_stale(cache_dir: Path, days: int, include_db: bool = False, here: Path = HERE):
    """纯枚举：返回 (待删文件列表, 释放字节数)。不打印、不删除，便于单测。

    cutoff = now - days*86400；mtime 早于 cutoff 的文件计入。
    """
    cutoff = time.time() - days * 86400
    removed: list[Path] = []
    freed = 0

    if cache_dir.exists():
        for f in cache_dir.rglob("*"):
            if not f.is_file():
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            if st.st_mtime < cutoff:
                removed.append(f)
                freed += st.st_size

    if include_db:
        for db in DB_FILES:
            p = here / "data" / db
            if p.exists():
                try:
                    st = p.stat()
                except OSError:
                    continue
                if st.st_mtime < cutoff:
                    removed.append(p)
                    freed += st.st_size

    return removed, freed


def _report_maintenance(rep: dict, dry_run: bool) -> None:
    """打印 run_cache_maintenance 的报告（诚实：真实删除数 / 释放字节 / 错误）。"""
    tag = "[dry-run] " if dry_run else ""
    total_del = (
        sum(s.get("deleted", 0) for s in rep.get("sqlite", []))
        + sum(s.get("removed", 0) for s in rep.get("shepherd", []))
    )
    total_freed = (
        sum(s.get("freed_bytes", 0) for s in rep.get("sqlite", []))
        + sum(s.get("freed_bytes", 0) for s in rep.get("shepherd", []))
    )
    if total_del == 0:
        print(f"{tag}缓存均在保留期（{rep.get('days')} 天）内，无需清理")
        return
    print(f"{tag}将清理（保留 {rep.get('days')} 天）：")
    for s in rep.get("sqlite", []):
        if s.get("deleted"):
            extra = f"  ⚠{s['error']}" if s.get("error") else ""
            print(f"   [sqlite] {s['db']}: 删 {s['deleted']} 行，释放 {human(s['freed_bytes'])}{extra}")
    for s in rep.get("shepherd", []):
        if s.get("removed"):
            print(f"   [csv] {s['dir']}: 删 {s['removed']} 文件，释放 {human(s['freed_bytes'])}")
    for e in rep.get("errors", []):
        print(f"   [error] {e}")
    if dry_run:
        print(f"[dry-run] 未执行删除（预计释放约 {human(total_freed)}）")
    else:
        print(f"已清理合计 {total_del} 项，释放约 {human(total_freed)}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="清理 StockSignal 本地缓存")
    ap.add_argument("--days", type=int, default=30, help="删除修改时间早于 N 天的缓存文件（默认 30）")
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR, help="缓存目录（默认 data/shepherd_cache）")
    ap.add_argument("--include-db", action="store_true", help="按保留期清理 cache.db / market_cache.db / news.db（委托 cache_maintenance，非整库删除）")
    ap.add_argument("--include-v2", action="store_true", help="同时清理 data/shepherd_cache_v2 目录（默认仅 v1；此前该 202MB 目录漏在默认清理范围外）")
    ap.add_argument("--dry-run", action="store_true", help="仅预览，不删除")
    ap.add_argument("--yes", action="store_true", help="确认执行删除（否则仅预览）")
    args = ap.parse_args(argv)

    if not args.dry_run and not args.yes:
        ap.error("需 --yes 确认删除，或 --dry-run 仅预览")

    cache_dir = args.cache_dir
    if not cache_dir.exists():
        print(f"[skip] 缓存目录不存在: {cache_dir}")
        return

    # ── 路径 A：含 SQLite 库保留期清理（委托 cache_maintenance 单一真理源）──
    if args.include_db:
        rep = run_cache_maintenance(days=args.days, include_v2=args.include_v2, dry_run=not args.yes)
        _report_maintenance(rep, args.dry_run)
        return

    # ── 路径 B：仅 CSV 目录（mtime 枚举，默认 v1，--include-v2 加 v2）──
    removed, freed = collect_stale(cache_dir, args.days)
    if args.include_v2:
        r2, f2 = collect_stale(V2_CACHE_DIR, args.days)
        removed += r2
        freed += f2

    if not removed:
        print(f"无需清理（{cache_dir} 内无超过 {args.days} 天的文件）")
        return

    print(f"将清理 {len(removed)} 个文件，释放约 {human(freed)}：")
    for f in removed[:50]:
        try:
            rel = f.relative_to(HERE)
        except ValueError:
            rel = f
        print("   ", rel)
    if len(removed) > 50:
        print(f"   ... 共 {len(removed)} 个")

    if args.dry_run:
        print("[dry-run] 未执行删除")
        return

    ok = 0
    for f in removed:
        try:
            f.unlink()
            ok += 1
        except OSError as e:
            print(f"   [warn] 删除 {f} 失败: {e}")
    print(f"已清理 {ok}/{len(removed)} 个文件，释放约 {human(freed)}")


if __name__ == "__main__":
    main()
