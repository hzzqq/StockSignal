#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build SkillHub-compliant zip packages from the repo-level skill dirs.

SkillHub rules enforced here:
  * Slug = lowercase letters/digits/hyphens only (derived from dir name).
  * description must be inline-quoted in SKILL.md frontmatter (no `|` / `>` block scalars).
  * zip MUST NOT contain binary files (icons are uploaded separately in the form),
    so we strip png/jpg/etc at packaging time.
"""
import os
import re
import shutil
import zipfile
import sys

REPO_SKILLS = "E:/project/ks/StockSignal/.workbuddy/skills"
USER_SKILLS = "C:/Users/Administrator/.workbuddy/skills"
BUILD_DIR = "E:/project/ks/StockSignal/build"

# (repo_dir_name, slug)
TARGETS = [
    ("牧羊人指标", "shepherd-sentiment"),
    ("连板龙头共振", "limit-up-ladder-resonance"),
]

BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".zip",
                ".bin", ".exe", ".dll", ".so", ".pyc"}


def check_description_inline(skill_root: str) -> str:
    """Verify SKILL.md frontmatter uses inline-quoted description (not block scalar)."""
    md = os.path.join(skill_root, "SKILL.md")
    if not os.path.isfile(md):
        raise SystemExit(f"MISSING SKILL.md in {skill_root}")
    text = open(md, encoding="utf-8").read()
    m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
    if not m:
        raise SystemExit(f"NO description field in {md}")
    val = m.group(1).strip()
    if val.startswith("|") or val.startswith(">"):
        raise SystemExit(f"BLOCK SCALAR description detected in {md}: {val!r} -- SkillHub rejects this")
    if not (val.startswith('"') or val.startswith("'")):
        raise SystemExit(f"description not inline-quoted in {md}: {val!r}")
    # length sanity
    inner = val.strip('"').strip("'")
    print(f"  description ok ({len(inner)} chars): {inner[:40]}...")
    return inner


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def build_zip(skill_root: str, slug: str):
    out = os.path.join(BUILD_DIR, f"{slug}.zip")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, _, files in os.walk(skill_root):
            for f in files:
                full = os.path.join(dirpath, f)
                ext = os.path.splitext(f)[1].lower()
                if ext in BINARY_EXTS:
                    print(f"  SKIP binary: {os.path.relpath(full, skill_root)}")
                    continue
                # skip marketplace-only docs that shouldn't ship in zip
                rel = os.path.relpath(full, skill_root)
                if rel in ("MARKETPLACE.md", "LISTING.md") or rel.startswith("references" + os.sep) and rel.endswith("LISTING.md"):
                    # keep references/LISTING.md out (listing metadata, not skill logic)
                    if rel.endswith("LISTING.md"):
                        print(f"  SKIP listing meta: {rel}")
                        continue
                z.write(full, arcname=os.path.join(os.path.basename(skill_root), rel))
                n += 1
    print(f"  wrote {out} ({n} files, {os.path.getsize(out)} bytes)")


def sync_icon(skill_dir: str, slug: str):
    """Copy the new icon from repo skill dir to the user-level skill dir (for local use)."""
    src = os.path.join(REPO_SKILLS, skill_dir, "assets", "icon_512.png")
    dst_root = os.path.join(USER_SKILLS, skill_dir)
    os.makedirs(os.path.join(dst_root, "assets"), exist_ok=True)
    dst = os.path.join(dst_root, "assets", "icon_512.png")
    if os.path.isfile(src):
        shutil.copyfile(src, dst)
        print(f"  synced icon -> {dst} ({os.path.getsize(dst)} bytes)")
    else:
        print(f"  WARN no icon at {src}")


def main():
    os.makedirs(BUILD_DIR, exist_ok=True)
    for skill_dir, slug in TARGETS:
        root = os.path.join(REPO_SKILLS, skill_dir)
        print(f"[build] {skill_dir} -> {slug}")
        check_description_inline(root)
        build_zip(root, slug)
        sync_icon(skill_dir, slug)
    print("DONE")


if __name__ == "__main__":
    main()
