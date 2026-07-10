# StockSignal 管理后端

> 一个最小但**安全基线合格**的 Flask 后端，给 StockSignal 业务系统做登录、鉴权、用户管理。
> 重点修复点：**所有响应严格走统一 JSON 包装**，杜绝 HTML / 调试信息泄露。

## 安全要点（核心修复）

| 风险 | 修复手段 |
|---|---|
| 错误响应里夹杂 HTML 标签 | 强制 `Content-Type: application/json`；`after_request` 兜底修正 |
| Werkzeug 默认 404/405 返回 HTML | `@app.errorhandler(HTTPException)` 统一转 JSON，message 中文脱敏 |
| 内部异常把 traceback 写进响应体 | `@app.errorhandler(Exception)` 兜底，统一返回 `服务内部错误` |
| 密码错响应暴露"用户不存在 / 密码错误"（账户枚举） | 统一消息 `用户名或密码错误`，两种情况响应完全一致 |
| `to_public` 误暴露 `password_hash` | User 模型中 `to_public()` 黑名单，序列化时只输出白名单字段 |
| 弱密钥导致 JWT 被伪造 | `SECRET_KEY` 通过环境变量注入，启动时有默认值提示 |
| 路由旁路（裸 `jsonify`） | 强制所有业务返回 `utils.response.ok/fail` 包好的 Response |
| X-Content-Type-Options 缺失 | `after_request` 加 `nosniff`、`DENY frame`、`no-store` |

## 启动

```bash
# 1. 安装依赖
pip install -r backend/requirements.txt

# 2. 初始化数据库（创建 admin / demo 账号）
cd E:/ks/StockSignal
python -m backend.scripts.init_db

# 3. 启动服务
python -m flask --app backend.app:app run --host 127.0.0.1 --port 5050

# 4. 运行安全回归测试
PYTHONIOENCODING=utf-8 python -m backend.tests.test_security
```

## 默认账号

| 用户名 | 密码 | 角色 |
|---|---|---|
| `admin` | `Admin@123` | admin |
| `demo`  | `Demo@123`  | user（对应截图中"演示用户"） |

> 生产部署务必先通过环境变量改 `STOCKSIGNAL_SECRET`、`JWT_EXPIRES_SECONDS`、`CORS_ORIGINS`、`DATABASE_URL`。

## API 一览

所有响应统一格式：

```json
{ "status": "ok|error", "code": "<业务码>", "message": "<已脱敏>", "data": <T|null> }
```

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/api/auth/login` | 无 | body: `{"username","password"}`，返回 token |
| GET  | `/api/auth/me` | Bearer | 当前登录用户 |
| POST | `/api/auth/logout` | Bearer | 注销（客户端丢弃 token） |
| GET  | `/api/auth/token-info` | Bearer | 返回 token 中的非敏感声明 |
| GET  | `/api/dashboard/summary` | Bearer | 市场全景看板（对应截图中三个模块入口） |
| GET  | `/api/admin/users` | admin | 用户列表（不含 password_hash） |
| GET  | `/api/health` | 无 | 健康检查 |

## 项目结构

```
backend/
├── app.py              # Flask 入口；统一 JSON 响应；全局 errorhandler
├── config.py           # 密钥 / 过期 / CORS / DB URI
├── extensions.py       # SQLAlchemy 实例
├── models.py           # User 模型
├── auth/
│   ├── routes.py       # /api/auth/*
│   ├── service.py      # 登录 + JWT 签发/校验
│   └── decorators.py   # @jwt_required / @admin_required
├── api/
│   ├── dashboard.py    # /api/dashboard/summary（市场全景看板）
│   └── admin_routes.py # /api/admin/users
├── utils/
│   ├── errors.py       # ApiError 体系（业务层异常）
│   └── response.py     # ok() / fail() 统一包装
├── scripts/
│   └── init_db.py      # 建表 + 种子用户
├── tests/
│   └── test_security.py # 安全回归测试（12 条断言）
├── data/               # SQLite 文件
└── requirements.txt
```
