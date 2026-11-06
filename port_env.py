"""port_env —— 读取本机分配的端口（由 port-doctor skill 管理）。

`.port.env` 是**本机文件**（已 gitignore），由 `portctl alloc --write` / `portctl prelaunch` 写入：

    # 由 port-doctor 自动生成（端口冲突自动分配）
    PORT=5100

用途：本地演示时多个项目同时起服务，不再互相抢 3000/5000/8000 这类默认端口。
端口优先级（从高到低）：

1. 显式环境变量（如 ``STOCKSIGNAL_PORT``）——命令行显式指定永远最优先；
2. ``.port.env`` 里的 ``PORT`` / 其它键——本机由 port-doctor 分配；
3. 调用方给的默认值——``.port.env`` 不存在（例如别人 clone 下来、或 CI）时行为与改造前完全一致。

诚实红线：``.port.env`` 缺失或取值非法时**回退默认值**，绝不臆造端口、绝不报错阻断启动。
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_FILE_NAME = ".port.env"


def repo_root() -> Path:
    """仓库根目录（本文件所在目录）。"""
    return Path(__file__).resolve().parent


def port_from_env_file(key: str = "PORT", default: int | None = None,
                       env_file: Path | None = None) -> int | None:
    """从 .port.env 读取指定键的端口值。

    解析规则：
    - 跳过空行与 ``#`` 注释行；
    - 取 ``KEY=VALUE`` 形式，VALUE 必须是纯数字（避免把 ``PORT=abc`` 变成脏端口）；
    - 文件缺失 / 读失败 / 键不存在 / 值非法 → 返回 ``default``。
    """
    path = Path(env_file) if env_file is not None else repo_root() / ENV_FILE_NAME
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return default
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() != key:
            continue
        v = v.strip()
        if v.isdigit():
            return int(v)
    return default


def resolve_port(key: str = "PORT", default: int = 0, env_var: str | None = None) -> int:
    """三级优先级解析端口：环境变量 > .port.env > 默认值。"""
    if env_var:
        env_val = (os.environ.get(env_var) or "").strip()
        if env_val.isdigit():
            return int(env_val)
    val = port_from_env_file(key, None)
    if val is not None:
        return val
    return default
