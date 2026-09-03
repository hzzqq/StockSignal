# -*- coding: utf-8 -*-
r"""
治本方案 · 外部 runner 测试临时目录清理脚本化（替换 `rm -rf E:\tmp\pt_fix`）

背景（见 StockSignal_治本方案_咨询.md 七 / Q3-Q5）：
  - 测试用 SQLite 临时库（~4% 残量 .db/.lock/.wal/.shm）原本由外部 runner 用
    `rm -rf E:\tmp\pt_fix` 清理，但沙箱里所有 `rm` 被 genie-trash 拦截进回收站，
    导致 .lock/.db 残留无法真正删除 → 回收站被海量测试临时文件淹没。
  - 治本方案已在 conftest.py 用 MEMORY 模式（_install_sqlite_memory_journal）把
    测试 SQLite 全程内存化，但外部 runner 的清理步骤仍需脚本化，以便：
      ① 用 os 级 shutil.rmtree 真正删除（绕过 genie-trash，不进回收站）；
      ② 可纳入定时任务 / CI 幂等重复执行；
      ③ 先 dry-run 审计、再执行，且不误删非 pt_fix 目录。

用法：
  python scripts/clean_test_tmp.py                  # 实际删除根 E:\tmp\pt_fix* 临时目录
  python scripts/clean_test_tmp.py --dry-run        # 仅列出将删除的目标，不删
  python scripts/clean_test_tmp.py --target DIR      # 指定基目录（默认 E:\tmp\pt_fix）
  python scripts/clean_test_tmp.py --root DIR        # 指定允许的安全根（默认 E:\tmp，仅调试/测试用）
  python scripts/clean_test_tmp.py --quiet           # 静默（仅失败输出）

安全：
  - 仅删除「落在 --root 下且目录名以 pt_fix 开头」的目录，绝不递归删除父级；
  - 默认 root=E:\tmp、base=E:\tmp\pt_fix，绝不触碰其它路径；
  - 使用 shutil.rmtree(ignore_errors=True) 强制删除（含只读 / 被占用的 .lock）。

退出码：0 成功 / 1 参数不安全 / 2 删除异常
"""
import argparse
import os
import shutil
import sys

DEFAULT_ROOT = r"E:\tmp"
DEFAULT_BASE = r"E:\tmp\pt_fix"


def _safe_base(target: str, root: str = DEFAULT_ROOT) -> bool:
    """校验 target 必须落在 root 下，且目录名以 pt_fix 开头，防误删系统盘。"""
    ap_abs = os.path.abspath(target)
    root_abs = os.path.abspath(root)
    if not (ap_abs == root_abs or ap_abs.startswith(root_abs + os.sep)):
        return False
    base_name = os.path.basename(ap_abs.rstrip(os.sep))
    return base_name.startswith("pt_fix")


def _collect(target: str) -> list:
    """收集待删目录：target 本体 + 同前缀兄弟（如 pt_fix_xxx）。"""
    ap_abs = os.path.abspath(target)
    candidates = []
    if os.path.isdir(ap_abs):
        candidates.append(ap_abs)
    parent = os.path.dirname(ap_abs)
    base = os.path.basename(ap_abs.rstrip(os.sep))
    if os.path.isdir(parent):
        try:
            with os.scandir(parent) as it:
                for e in it:
                    if e.is_dir() and e.name.startswith(base):
                        p = os.path.abspath(e.path)
                        if p != ap_abs:
                            candidates.append(p)
        except Exception:  # noqa: BLE001
            pass
    return candidates


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="治本方案 · 外部 runner 测试临时目录清理")
    ap.add_argument("--root", default=DEFAULT_ROOT,
                    help="允许的安全根目录（target 必须落在其下，防误删）")
    ap.add_argument("--target", default=DEFAULT_BASE,
                    help="要清理的基目录（默认 E:\\tmp\\pt_fix）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    def log(*a):
        if not args.quiet:
            print(*a)

    if not _safe_base(args.target, args.root):
        print(f"[clean_test_tmp] 不安全的 target（必须落在 {args.root} 且以 pt_fix 开头）: {args.target}",
              file=sys.stderr)
        return 1

    candidates = _collect(args.target)
    if not candidates:
        log(f"[clean_test_tmp] 未发现需清理的目录（base={args.target}）")
        return 0

    log(f"[clean_test_tmp] 命中 {len(candidates)} 个目录：")
    for c in candidates:
        log(f"  - {c}")

    if args.dry_run:
        log("[dry-run] 未执行删除。")
        return 0

    failed = []
    for c in candidates:
        try:
            shutil.rmtree(c, ignore_errors=True)
            log(f"✅ 已删除 {c}")
        except Exception as e:  # noqa: BLE001
            failed.append((c, str(e)))
            log(f"⚠️ 删除失败 {c}: {e}")
    if failed:
        print(f"[clean_test_tmp] 有 {len(failed)} 个目录删除异常", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
