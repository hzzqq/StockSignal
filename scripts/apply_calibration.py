# -*- coding: utf-8 -*-
"""
把「仓位刻度校准」的建议真正落到 decision.CYCLE_ADJ（闭合校准环路）。

为什么要这个脚本（补闭环最后一步）：
    calibration.as_patch() 算出了补丁，但此前没有任何代码路径能应用——只能人肉 copy
    进 decision.py，容易漏改、容易与 tests/test_decision.py 期望值漂移。本脚本补上
    **带护栏的程序化落地**，仍守住「人仍在回路」：

    · 默认 dry-run：只打印将要改什么，绝不写文件（安全预览）
    · 真正落地需显式 --apply
    · 落地前会校验 verdict.ready（单组样本够 + 调节量超噪音），否则拒绝
    · 写前自动备份 decision.py.bak，写后追加 calibration_apply.log 审计

用法：
    python scripts/apply_calibration.py            # 预览：将改哪些刻度
    python scripts/apply_calibration.py --apply   # 真正落地（需 verdict.ready）
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import calibration as _cal  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="把仓位刻度校准建议落地到 decision.CYCLE_ADJ")
    ap.add_argument("--apply", action="store_true",
                    help="真正写入 decision.CYCLE_ADJ（默认仅 dry-run 预览）")
    ap.add_argument("--strong-samples", type=int, default=_cal.DEFAULT_STRONG_SAMPLES,
                    help="可采纳阈值（默认 %(default)s 条）")
    args = ap.parse_args()

    res = _cal.apply_patch(strong_samples=args.strong_samples, dry_run=not args.apply)
    if res["applied"]:
        print(f"[apply] 已落地 CYCLE_ADJ 补丁: {res['changed']}")
        print(f"        完整补丁: {res['patch']}")
        print("[apply] 记得同步更新 tests/test_decision.py 的期望值（如有硬编码刻度断言）。")
        return 0
    if res.get("dry_run"):
        patch = res.get("patch") or {}
        if patch:
            print("[dry-run] 将达到采纳阈值的刻度补丁（加 --apply 才落地）：")
            for k, v in patch.items():
                print(f"    {k}: {v:+d}")
        else:
            print(f"[dry-run] 暂无值得采纳的校准建议：{res['reason']}")
        return 0
    print(f"[skip] 未落地：{res['reason']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
