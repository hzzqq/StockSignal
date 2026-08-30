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


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="清理 StockSignal 本地缓存")
    ap.add_argument("--days", type=int, default=30, help="删除修改时间早于 N 天的缓存文件（默认 30）")
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR, help="缓存目录（默认 data/shepherd_cache）")
    ap.add_argument("--include-db", action="store_true", help="同时清理 cache.db / market_cache.db / news.db")
    ap.add_argument("--dry-run", action="store_true", help="仅预览，不删除")
    ap.add_argument("--yes", action="store_true", help="确认执行删除（否则仅预览）")
    args = ap.parse_args(argv)

    if not args.dry_run and not args.yes:
        ap.error("需 --yes 确认删除，或 --dry-run 仅预览")

    cache_dir = args.cache_dir
    if not cache_dir.exists():
        print(f"[skip] 缓存目录不存在: {cache_dir}")
        return

    removed, freed = collect_stale(cache_dir, args.days, args.include_db)

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
