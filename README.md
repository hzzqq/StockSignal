<div align="center">

# StockSignal · A股事件驱动投资分析平台

**软件工程实训课程设计**

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-black?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-red?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![SQLite](https://img.shields.io/badge/DB-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)

> 基于事件驱动策略的 A 股数据分析工具，聚合产业事件、价格信号与宏观催化三类数据，
> 辅助投资者识别主线行情、回测交易策略、追踪仓位盈亏。

</div>

---

## 目录

- [项目概述](#项目概述)
- [系统架构](#系统架构)
- [目录结构](#目录结构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [环境变量](#环境变量)
- [默认账号](#默认账号)
- [API 总览](#api-总览)
- [测试](#测试)
- [暗夜 / 白天双主题](#暗夜--白天双主题)
- [Docker 部署](#docker-部署)
- [启动脚本说明与改进点](#启动脚本说明与改进点)
- [数据来源](#数据来源)

---

## 项目概述

StockSignal 是一款面向个人投资者的 **A 股事件驱动分析工具**，整合三类核心催化信号：

| 类型 | 说明 | 示例 |
|------|------|------|
| 产业事件 | 政策发布、行业并购、产能变化 | 光伏装机补贴、半导体设备禁令 |
| 价格信号 | 大宗商品价格、上游原材料变动 | MLCC 涨价、煤炭港口价格 |
| 宏观数据 | PMI、CPI、社融等关键指标 | PMI 超预期 → 顺周期主线 |

帮助用户 **快速识别行情主线**、**可视化行业轮动**、**回测事件驱动策略**、**管理持仓盈亏**。

平台采用「**Streamlit 多页前端 + Flask 后端 + SQLite**」前后端分离架构：
前端负责交互与可视化，后端以 JWT 鉴权的 REST API 提供数据/用户/配置服务，SQLite 持久化用户与股票基础数据。

---

## 系统架构

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│   Streamlit 多页前端 (8501)  │  HTTP   │   Flask 后端 API (5050)       │
│  pages/ + modules/          │ ──────▶ │  blueprints: auth/stocks/     │
│  session(API_BASE)          │  JWT    │  dashboard/admin/config       │
└─────────────────────────────┘         └───────────────┬──────────────┘
                                                         │ SQLAlchemy
                                                         ▼
                                              ┌────────────────────────┐
                                              │  SQLite                │
                                              │  backend/data/app.db  │
                                              │  (用户/股票/配置/日志) │
                                              └────────────────────────┘

前端运行数据（行情缓存/持仓/事件）落盘于 data/：
  data/cache.db  data/portfolio.csv  data/events.csv  data/news.db
```

---

## 目录结构

```
StockSignal/
├── app.py                      # Streamlit 主入口
├── config.yaml                 # 全局配置（Tushare token、信号权重…）
├── requirements.txt            # 前端/数据层依赖（streamlit/akshare/pandas…）
├── backend/
│   ├── requirements.txt        # 后端依赖（flask/flask-cors/sqlalchemy/pyjwt…）
│   ├── app.py                  # Flask 入口（create_app / 健康检查 /api/health）
│   ├── config.py               # 配置项（SECRET/CORS/限流/JWT 均支持环境变量）
│   ├── models.py  extensions.py  auth/  api/  services/  scripts/  tests/  utils/
│   └── data/                   # SQLite 落盘目录（app.db 由 init_db 生成）
├── modules/                    # 前端业务模块（fetcher/cleaner/signal/news/
│                               #   visualizer/backtest/portfolio/session/
│                               #   admin_api/auth_persist/search_ui/technical/
│                               #   ui_theme/admin_api.py …）
├── pages/                      # Streamlit 多页面
│   ├── 0_登录.py  1_行情看板.py(含板块涨跌)  2_个股分析.py  3_事件追踪.py
│   ├── 4_策略回测.py  5_仓位管理.py  6_我的.py(含偏好设置)
│   └── 7_用户管理.py  8_系统配置.py
├── data/                       # 前端运行数据（cache.db/portfolio.csv/events.csv/news.db）
├── logs/                       # 运行日志（backend.log / frontend.log / *.err）
├── tests/                      # 测试（黑盒 + 白盒）
└── .streamlit/config.toml      # Streamlit 主题（默认亮色金融风）
```

---

## 环境要求

- Python ≥ 3.10（Docker 镜像基于 `python:3.11-slim`）
- 操作系统：Windows（启动脚本）/ 支持 Docker 的 Linux / macOS
- 外网：首次运行 `import_stocks` 需访问 AKShare / Baostock 数据源
- 可选：Tushare Token（填入 `config.yaml` 或环境变量 `TUSHARE_TOKEN`）

---

## 快速开始

### 方式 A：本地一键启动（推荐）

```bash
# Windows：双击 D:/project/ks/启动StockSignal.bat
# Git Bash / WSL：bash D:/project/ks/启动StockSignal.sh
```

脚本会自动：清理旧进程 → 检查 Python → 初始化数据库 → 启动后端(5050)与前端(8501) → 打开浏览器。

### 方式 B：手动分步启动

```bash
# 1) 创建并激活虚拟环境
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 2) 安装依赖（前端 + 后端两处 requirements 都要装！）
pip install -r requirements.txt
pip install -r backend/requirements.txt

# 3) 初始化数据库（建表 + 写入 admin/demo 种子账号）
python -m backend.scripts.init_db

# 4) 导入 A 股股票列表（约 5177 只，需外网，首次较慢）
python -m backend.scripts.import_stocks

# 5) 启动 Flask 后端（端口 5050）
python -m flask --app backend.app:app run --host 127.0.0.1 --port 5050

# 6) 启动 Streamlit 前端（端口 8501，另开一个终端）
streamlit run app.py --server.port 8501 --server.headless true
```

浏览器打开 `http://localhost:8501`，后端地址 `http://127.0.0.1:5050`。

> ⚠️ 依赖分两处：`requirements.txt` 不含 Flask 等后端框架，
> `backend/requirements.txt` 才是后端依赖。两者都需安装，否则 `backend.app` 导入失败。

---

## 环境变量

后端配置均可通过环境变量覆盖（见 `backend/config.py`）。常用：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STOCKSIGNAL_SECRET` | `dev-only-change-me-in-production` | JWT 签名密钥，**生产必须覆盖** |
| `CORS_ORIGINS` | `*` | 允许跨域来源；生产收紧为前端地址 |
| `JWT_EXPIRES_SECONDS` | `3600` | Token 有效期（秒） |
| `STOCKSIGNAL_RATE_LIMIT_ENABLED` | `1` | 登录等接口限流开关（**注：真实变量名带前缀**） |
| `RATE_LIMIT_MAX` | `5` | 滑动窗口内单 key 最大请求次数 |
| `RATE_LIMIT_WINDOW` | `60` | 滑动窗口长度（秒） |
| `EXPOSE_INTERNAL_ERROR` | `0` | 是否暴露内部错误详情（生产保持 0） |
| `TUSHARE_TOKEN` | 空 | Tushare token（可选） |
| `DATABASE_URL` | `sqlite:///backend/data/app.db` | 数据库连接串 |
| `FLASK_DEBUG` | `0` | 调试模式 |

> 说明：team-lead 概览中提到的 `RATE_LIMIT_ENABLED` 在实际代码中名为
> **`STOCKSIGNAL_RATE_LIMIT_ENABLED`**（见 `backend/config.py:43`），其余
> `RATE_LIMIT_MAX` / `RATE_LIMIT_WINDOW` 名称一致。文档以代码为准。

---

## 默认账号

数据库初始化（`init_db`）会写入两个种子账号（见 `backend/scripts/init_db.py`）：

| 用户名 | 密码 | 角色 | 权限 |
|--------|------|------|------|
| `admin` | `Admin@123` | admin | 用户管理、系统配置、操作日志 |
| `demo` | `Demo@123` | user | 普通分析功能（演示用户） |

> 首次登录建议使用 `demo` 体验；`admin` 用于后台管理（用户 CRUD、配置、日志）。

---

## API 总览

基础地址：`http://127.0.0.1:5050`（容器/部署下为对应主机）。所有接口返回
`utils.response.ok/fail` 包装的 JSON；异常统一返回 JSON（绝不泄露 HTML/traceback）。

### 认证 `/api/auth`
| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | `/api/auth/login` | 登录，返回 JWT token | 否 |
| POST | `/api/auth/register` | 开放注册（角色固定 user） | 否 |
| GET | `/api/auth/me` | 当前登录用户 | JWT |
| POST | `/api/auth/logout` | 注销（客户端丢弃 token） | JWT |
| GET | `/api/auth/token-info` | token 非敏感声明 | JWT |

### 股票 `/api/stocks`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/stocks/search` | 按关键词搜索股票 |
| GET | `/api/stocks/list` | 股票列表 |
| GET | `/api/stocks/stats` | 市场统计 |
| GET | `/api/stocks/<code>` | 单只股票详情 |

### 看板 `/api/dashboard`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/summary` | 首页概览数据 |

### 管理 `/api/admin`（需 admin 角色）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/users` | 用户列表 |
| POST | `/api/admin/users` | 新建用户 |
| PUT | `/api/admin/users/<int:user_id>` | 更新用户 |
| DELETE | `/api/admin/users/<int:user_id>` | 删除用户 |
| GET | `/api/admin/logs` | 操作日志 |

### 配置 `/api`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/config` | 读取配置 |
| POST | `/api/admin/config` | 新增配置 |
| PUT | `/api/admin/config/<key>` | 修改配置 |
| DELETE | `/api/admin/config/<key>` | 删除配置 |
| GET | `/api/watchlist` | 自选股列表 |
| POST | `/api/watchlist` | 新增自选 |
| DELETE | `/api/watchlist/<int:item_id>` | 删除自选 |

### 系统
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（返回 `{"status":"alive"}`） |
| GET | `/` 、`/admin` | 后端管理界面（独立 HTML 页） |

> 接口契约以 `backend/` 路由实现为准；若后端改路由，README 由工程化模块同步更新。

---

## 测试

测试由「测试」模块维护（位于 `backend/tests/` 与 `tests/`）。常用命令：

```bash
# 后端安全/契约测试（单模块运行）
python -m backend.tests.test_security

# 跑全部后端测试（pytest）
python -m pytest backend/tests -q

# 前端/数据层测试
python -m pytest tests -q
```

> 限流默认开启；测试套件在 `backend/tests/test_api_contracts.py` 中通过
> `STOCKSIGNAL_RATE_LIMIT_ENABLED=0` + `reset_rate_limit()` 隔离限流用例。

---

## 暗夜 / 白天双主题

平台支持 **亮色（白天）** 与 **暗色（暗夜）** 两套主题：

- **基底主题**：由 `.streamlit/config.toml` 的 `[theme]` 定义（默认 `light`，
  金色品牌主色 `#B8860B`、护眼冷灰背景）。
- **暗色覆盖**：`modules/ui_theme.py` 中的 `_DARK_CSS` 在暗色模式下注入，
  覆盖 Streamlit 原生基底；图表使用 Plotly 暗色模板 `starfield_dark`
  （见 `inject_plotly_dark()`）。
- **切换方式**：页面通过 `st.session_state["theme_mode"]`（`"light"` / `"dark"`）
  控制，由 `apply_theme()` 应用；偏好设置入口已并入「我的」页的「⚙️ 偏好设置」页签。
- 修改 `config.toml` 后重启 Streamlit 生效。

---

## Docker 部署

提供两份 Dockerfile 与一份 compose：

- `Dockerfile.backend` —— Flask 后端镜像（端口 5050）
- `Dockerfile.streamlit` —— Streamlit 前端镜像（端口 8501）
- `docker-compose.yml` —— 编排两服务 + 端口映射 + 数据卷

```bash
# 在项目根目录构建并启动
docker compose -f docker-compose.yml up --build

# 前端 http://localhost:8501   后端 http://localhost:5050
```

数据持久化（卷挂载）：
- `./backend/data` → 后端 `app.db`（用户、股票、配置）
- `./data` → 前端运行数据（`cache.db` / `portfolio.csv` / `events.csv` / `news.db`）
- `./logs` → 运行日志

生产注意：通过环境变量覆盖 `STOCKSIGNAL_SECRET`、`CORS_ORIGINS`，并收紧
`EXPOSE_INTERNAL_ERROR=0`。

### 容器化双服务连通性（已解决）

前端通过 `modules/session.py` 读取环境变量 `STOCKSIGNAL_API_BASE`
（默认 `http://127.0.0.1:5050`，团队大脑已直接接入）。在 compose **两服务**布局下，
前端容器经 `STOCKSIGNAL_API_BASE=http://backend:5050` 跨容器访问后端，
双容器连通性成立，无需退回单容器双进程方案。生产部署请确保该变量已注入。

---

## 启动脚本说明与改进点

启动脚本位于项目根目录（**非** StockSignal 子目录）：
`启动StockSignal.bat` / `启动StockSignal.sh` / `_stop_services.bat` / `_launch_hidden.vbs`。

当前能力：端口清理 → 脱离终端（_launch_hidden.vbs / nohup+setsid）→ 日志按时间戳落盘 `logs/` →
.bat 与 .sh 步骤一一对应、行为一致。

已落地的改进项（详见工程化模块报告）：

1. **健康检查升级**：现仅 `curl` 端口可达性轮询，应改用后端 `GET /api/health` 做真就绪探测，避免“端口通但 DB 未就绪”的假成功。
2. **失败自恢复**：进程启动/中途退出时启动器无感知，应加存活回检与明确失败提示。
3. **Python 路径去硬编码**：脚本写死 `C:/Users/24995/.../python.exe`，换机/容器必失败，应优先用同目录 venv 并回退 `PATH`。
4. **补齐 `_stop_services.sh`**：现仅 `.bat`，违反 `.bat/.sh` 行为一致约定。
5. **纯 Linux 支持**：`.sh` 当前依赖 `powershell.exe`（实为 Git Bash 方案），纯 Linux 应改 `nohup`+`setsid`。
6. **容器内监听地址**：后端/前端在容器内需 `--host/--server.address 0.0.0.0`（脚本现为 `127.0.0.1`）。
7. **日志增强**：现单文件覆盖，建议按日期+启动序号命名并保留 `.err`。
8. **环境变量注入**：启动前导出 `STOCKSIGNAL_SECRET` / `CORS_ORIGINS` / `DATABASE_URL`，便于 Docker 复用。
9. **DB 健壮性**：库存在时仍做轻量表结构校验；`import_stocks` 失败给出可重试提示。
10. **遗留文件**：`_launch_hidden.vbs` 当前未被调用，建议接入或剔除。

---

## 数据来源

| 数据类型 | 来源 | 是否免费 | 说明 |
|----------|------|----------|------|
| A 股日线行情 | [AKShare](https://akshare.akfamily.xyz/) | 免费 | 无需注册 |
| 财务数据 | [Tushare](https://tushare.pro/) | 注册免费 | 需 Token |
| 宏观指标 | AKShare | 免费 | PMI、CPI、社融等 |
| 大宗商品价格 | AKShare | 免费 | 煤炭、螺纹钢、MLCC 等 |
| 新闻事件 | 东方财富 RSS（AKShare 封装） | 免费 | 新闻挖掘 + 情感分析 |

---

<div align="center">

**本项目为软件工程实训课程设计，仅用于学习研究，不构成任何投资建议。**

</div>
