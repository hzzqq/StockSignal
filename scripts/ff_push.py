#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双机 / 多 agent 协作安全推送脚本（固化 dual-machine-git-safety 红线）。

用法:
  python scripts/ff_push.py            # 推送当前分支（默认 main）
  python scripts/ff_push.py --branch feature/x
  python scripts/ff_push.py --dry      # 只校验 FF，不实际推送

铁律:
  * 只 fast-forward 推送；非快进绝不强推，直接上报退出（由人定夺）。
  * 网络取不到远端时，留本地提交，不强制、不 --no-verify。
  * 绝不 git reset --hard / 删历史 / --force。
退出码: 0=已同步或安全跳过, 1=非快进已拦截, 2=使用错误
"""
import argparse
import subprocess
import sys


def run(cmd, check=True, capture=True):
    return subprocess.run(cmd, shell=True, check=check,
                          capture_output=capture, text=True)


def branch_name():
    r = run("git rev-parse --abbrev-ref HEAD")
    return r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default=None, help="要推送的分支，默认当前分支")
    ap.add_argument("--dry", action="store_true", help="只校验 fast-forward，不推送")
    args = ap.parse_args()

    br = args.branch or branch_name()
    print(f"[ff_push] 分支 = {br}")

    # 1) fetch
    f = run("git fetch origin", check=False)
    if f.returncode != 0:
        print("[ff_push] NETWORK_BLOCKED: 取不到远端，留本地提交，待网络恢复或另一台拉取。")
        return 0
    print("[ff_push] fetch ok")

    # 2) 远端 SHA
    remote_sha = run(f"git rev-parse origin/{br}", check=False).stdout.strip()
    local_sha = run(f"git rev-parse {br}").stdout.strip()
    if not remote_sha:
        print(f"[ff_push] 远端无 {br}（可能是新话题分支），按新 ref 直接推（永远算快进）。")
    else:
        # 3) FF 校验
        mb = run(f"git merge-base --is-ancestor {remote_sha} {local_sha}", check=False)
        if mb.returncode != 0:
            print("=" * 60)
            print("[ff_push] NON_FF: 远端有新提交，本地非快进 —— 按红线不强制推送！")
            print(f"          本地 = {local_sha[:12]}  远端 = {remote_sha[:12]}")
            print("[ff_push] 请先让另一台/本地 rebase 或人工协调后再推。上报老板定夺。")
            print("=" * 60)
            return 1

    if args.dry:
        print("[ff_push] DRY: FF 校验通过，未实际推送。")
        return 0

    # 4) push
    p = run(f"git push origin {br}", check=False)
    if p.returncode != 0:
        out = (p.stdout + p.stderr).strip()
        if "non-fast-forward" in out or "tip of your current branch is behind" in out:
            print("[ff_push] NON_FF 被服务端拒绝（双机并发）：停手，上报老板。")
            return 1
        print(f"[ff_push] PUSH_FAILED: {out[:300]}")
        return 1

    # 5) 复核
    r2 = run(f"git rev-parse origin/{br}", check=False).stdout.strip()
    if r2 == local_sha:
        print("[ff_push] SYNCED ✓")
        return 0
    print("[ff_push] PUSH_INCOMPLETE: 推送后远端 != 本地，请检查。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
