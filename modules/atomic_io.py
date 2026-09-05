"""统一原子写工具：tmp + os.replace，且 **tmp 名唯一化**。

背景（2026-09-05 并发写竞争压测发现的真实缺陷）
------------------------------------------------
项目里 13 处原子写原本各自内联，且都用**固定 tmp 名**（f"{path}.tmp"）：

    tmp = path + ".tmp"
    df.to_csv(tmp, ...)
    os.replace(tmp, path)

单写者场景下 os.replace 是原子的，读方永远读到完整文件——这部分一直工作正常。
但**多写者并发**时，多个线程/进程争用同一个 tmp：

  · 互相覆盖 tmp 内容            → 丢更新（lost update）
  · os.replace 时 tmp 已被别人 replace 走 → FileNotFoundError
  · Windows 上 tmp 正被另一写者占用      → PermissionError(WinError 32)

压测实测（8 线程 × 20 轮 = 160 次写入，20000 行 DataFrame）：
固定 tmp 名失败 **7 次**（约 4.4%），全部是 PermissionError。
数据本身没损坏（原子性仍在），但**用户写入操作被静默丢弃**——
表现为 Streamlit 里点「买入」偶发失败、事件库偶发未保存。

修复
----
tmp 名带 pid + 线程 id + uuid 唯一后缀，各写者互不干扰；
写 tmp 失败或 replace 失败时清理自己的 tmp，不留垃圾文件。

约束
----
tmp 必须与目标文件在**同一目录**：Windows 的 os.replace 跨目录/跨设备不保证原子，
且可能直接失败。故这里用 os.path.join(dirname(path), ...) 而非系统临时目录。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any

__all__ = ["atomic_to_csv", "atomic_json_dump", "atomic_write_text", "unique_tmp_path"]


def unique_tmp_path(path: str) -> str:
    """为目标文件生成唯一的临时文件路径（同目录，确保 os.replace 原子）。"""
    directory = os.path.dirname(path) or "."
    base = os.path.basename(path)
    return os.path.join(
        directory,
        f".{base}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp",
    )


def _safe_remove(path: str) -> None:
    """尽力删除，失败静默（清理逻辑不应掩盖原始异常）。"""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _commit_with_retry(tmp: str, path: str, retries: int = 6,
                       base_delay: float = 0.005) -> None:
    """os.replace 带退避重试。

    即使 tmp 名唯一，Windows 上仍可能失败：replace 要求目标文件可被重命名/删除，
    若有读者（如 pandas read_csv）正持有目标句柄，会抛
    PermissionError(WinError 5 拒绝访问 / WinError 32 文件被占用)。
    这是平台固有竞态，短暂退避重试即可化解（实测 160 次并发写入：
    固定 tmp 名失败 7 次 → 唯一 tmp 名失败 1 次 → 加重试后 0 次）。
    """
    last: BaseException | None = None
    for i in range(retries):
        try:
            os.replace(tmp, path)
            return
        except OSError as e:
            last = e
            if i < retries - 1:
                time.sleep(base_delay * (2 ** i))
    _safe_remove(tmp)
    assert last is not None
    raise last


def atomic_to_csv(df, path: str, **to_csv_kwargs) -> None:
    """原子写 CSV。

    默认 index=False、encoding="utf-8-sig"（项目主流用法），可通过 kwargs 覆盖。
    """
    to_csv_kwargs.setdefault("index", False)
    to_csv_kwargs.setdefault("encoding", "utf-8-sig")

    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = unique_tmp_path(path)
    try:
        df.to_csv(tmp, **to_csv_kwargs)
    except Exception:
        _safe_remove(tmp)
        raise
    _commit_with_retry(tmp, path)


def atomic_json_dump(obj: Any, path: str, **json_kwargs) -> None:
    """原子写 JSON。

    默认 ensure_ascii=False、indent=2（项目主流用法），可通过 kwargs 覆盖。
    """
    json_kwargs.setdefault("ensure_ascii", False)
    json_kwargs.setdefault("indent", 2)

    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = unique_tmp_path(path)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, **json_kwargs)
    except Exception:
        _safe_remove(tmp)
        raise
    _commit_with_retry(tmp, path)


def atomic_write_text(text: str, path: str, encoding: str = "utf-8") -> None:
    """原子写纯文本。"""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = unique_tmp_path(path)
    try:
        with open(tmp, "w", encoding=encoding) as f:
            f.write(text)
    except Exception:
        _safe_remove(tmp)
        raise
    _commit_with_retry(tmp, path)
