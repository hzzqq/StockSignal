#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
"""Build SkillHub-compliant packages from the repo-level skill dirs.

SkillHub rules enforced here:
  * Slug = lowercase letters/digits/hyphens only (from frontmatter ``slug:``).
  * description must be inline-quoted in SKILL.md frontmatter (no `|` / `>` block scalars).
  * slug + version must be present in frontmatter (needed to update an existing listing).
  * zip MUST NOT contain binary files (icons are uploaded separately in the form),
    so we strip png/jpg/etc at packaging time.
  * listing metadata (LISTING.md / MARKETPLACE.md) stays out of the zip.

Also mirrors each skill into the user-level skills dir **completely**
(SKILL.md + scripts/ + lib/ + assets/ + icon) — syncing only the icon leaves
the local skill uninstallable (no SKILL.md / scripts), which is what happened
before 2026-11-04.
"""
import datetime  # noqa: I001
import hashlib
import json
import os  # noqa: I001
import re
import shutil
import zipfile
import sys  # noqa: F401

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
REPO_SKILLS = os.path.join(REPO_ROOT, ".workbuddy", "skills")
USER_SKILLS = os.environ.get(
    "WORKBUDDY_USER_SKILLS",
    os.path.join(os.path.expanduser("~"), ".workbuddy", "skills"),
)
BUILD_DIR = os.path.join(_HERE)

# (repo_dir_name, zip_slug)
TARGETS = [
    ("牧羊人指标", "shepherd-sentiment"),
    ("连板龙头共振", "limit-up-ladder-resonance"),
    ("event_factor", "event-factor"),
    ("macro_data", "macro-data"),
    ("market_temperature", "market-temperature"),
]

BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".zip",
                ".bin", ".exe", ".dll", ".so", ".pyc"}

# 上架物料：不进 zip、不进用户级 skill 本体
LISTING_META = ("LISTING.md", "MARKETPLACE.md")


def check_frontmatter(skill_root: str) -> dict:
    """校验 SKILL.md frontmatter：description inline + slug/version 必填。"""
    md = os.path.join(skill_root, "SKILL.md")
    if not os.path.isfile(md):
        raise SystemExit(f"MISSING SKILL.md in {skill_root}")
    text = open(md, encoding="utf-8").read()
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        raise SystemExit(f"NO frontmatter in {md}")
    fm = m.group(1)
    dm = re.search(r"^description:\s*(.+)$", fm, re.M)
    if not dm:
        raise SystemExit(f"NO description field in {md}")
    val = dm.group(1).strip()
    if val.startswith("|") or val.startswith(">"):
        raise SystemExit(f"BLOCK SCALAR description detected in {md}: {val!r} -- SkillHub rejects this")
    if not (val.startswith('"') or val.startswith("'")):
        raise SystemExit(f"description not inline-quoted in {md}: {val!r}")
    slug = re.search(r"^slug:\s*(.+)$", fm, re.M)
    ver = re.search(r"^version:\s*(.+)$", fm, re.M)
    if not slug:
        raise SystemExit(f"NO slug field in {md} (needed to update an existing listing)")
    if not ver:
        raise SystemExit(f"NO version field in {md} (same-slug skills must bump version)")
    inner = val.strip('"').strip("'")
    print(f"  frontmatter ok: slug={slug.group(1).strip()} version={ver.group(1).strip()} "
          f"description({len(inner)} chars)")
    return {"slug": slug.group(1).strip(), "version": ver.group(1).strip(),
            "description": inner}


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
                rel = os.path.relpath(full, skill_root)
                if rel in LISTING_META or rel.replace(os.sep, "/").startswith("references/"):
                    print(f"  SKIP listing meta: {rel}")
                    continue
                z.write(full, arcname=os.path.join(os.path.basename(skill_root), rel))
                n += 1
    print(f"  wrote {out} ({n} files, {os.path.getsize(out)} bytes)")
    return out


def sync_to_user(skill_dir: str, slug: str):
    """完整同步到用户级 skills 目录（此前只同步 icon，导致本地 skill 缺 SKILL.md/scripts）。"""
    src_root = os.path.join(REPO_SKILLS, skill_dir)
    dst_root = os.path.join(USER_SKILLS, skill_dir)
    if not os.path.isdir(src_root):
        print(f"  WARN source missing: {src_root}")
        return
    n = 0
    for dirpath, _, files in os.walk(src_root):
        for f in files:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, src_root)
            # 上架物料不进本地 skill 本体
            if rel in LISTING_META:
                continue
            if rel.startswith("references" + os.sep):
                continue
            dst = os.path.join(dst_root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(full, dst)
            n += 1
    print(f"  synced {n} files -> {dst_root}")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build_skill_json(skill_dir: str, slug: str, fm: dict):
    """生成 .skill.json 包（workbuddy-skill-package/1.0）：frontmatter + 文件内容 + sha256 清单。"""
    src_root = os.path.join(REPO_SKILLS, skill_dir)
    files = []
    manifest = hashlib.sha256()
    for dirpath, _, fnames in os.walk(src_root):
        for f in sorted(fnames):
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, src_root).replace(os.sep, "/")
            if rel in LISTING_META or rel.startswith("references/"):
                continue
            raw = open(full, "rb").read()
            sha = _sha256_bytes(raw)
            try:
                content = raw.decode("utf-8")
                enc = "text"
            except UnicodeDecodeError:
                content = ""
                enc = "binary"
            files.append({"path": rel, "size": len(raw), "sha256": sha,
                          "encoding": enc, "content": content})
            manifest.update(rel.encode("utf-8"))
            manifest.update(sha.encode("utf-8"))
    files.sort(key=lambda x: x["path"])
    pkg = {
        "format": "workbuddy-skill-package/1.0",
        "name": skill_dir,
        "source_path": src_root,
        "packaged_at": datetime.datetime.now().astimezone().isoformat(),
        "file_count": len(files),
        "manifest_sha256": manifest.hexdigest(),
        "frontmatter": fm,
        "files": files,
    }
    out = os.path.join(BUILD_DIR, f"{skill_dir}.skill.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(pkg, fh, ensure_ascii=False, indent=2)
    print(f"  wrote {out} ({len(files)} files, {os.path.getsize(out)} bytes)")
    return out


def main():
    os.makedirs(BUILD_DIR, exist_ok=True)
    for skill_dir, slug in TARGETS:
        root = os.path.join(REPO_SKILLS, skill_dir)
        print(f"[build] {skill_dir} -> {slug}")
        fm = check_frontmatter(root)
        build_zip(root, slug)
        build_skill_json(skill_dir, slug, fm)
        sync_to_user(skill_dir, slug)
    print("DONE")


if __name__ == "__main__":
    main()
