# FETCHER_CONTRACT.md — StockFetcher / NewsFetcher 权威接口契约（冻结版）

> **状态：冻结（FROZEN）** — 由团队大脑（team-lead）基于 `modules/fetcher.py`、`modules/news.py` 实代码于 2026-07-09 定稿。
> 本文件是 **后端**（`/api/quote`、`/api/kline`）与 **测试模块**（19 个 fetcher/news 漂移用例改写）的唯一事实来源。
> **数据层在冻结后不得再修改下列任何公开方法的签名、返回类型或降级语义**，否则视为破坏契约并需重新评审。

---

## 0. 模块级数据源可用性标志（铁律）

两个模块各自在 import 期探测第三方库，失败时**绝不抛异常、绝不中断模块加载**：

| 模块 | 标志 | 含义 | False 时的行为 |
|------|------|------|----------------|
| `fetcher.py` | `_AK_OK` | `import akshare` 成功 | 跳过所有 akshare 路径，降级到 BaoStock/新浪/东方财富/缓存 |
| `fetcher.py` | `_BS_OK` | `import baostock` 成功 | 跳过 BaoStock 路径 |
| `news.py` | `_AK_OK` | `import akshare` 成功 | 跳过 akshare 抓取源 |
| `news.py` | `_JIEBA_OK` | `import jieba` 成功 | 关键词提取降级到规则法 |

- **最终语义**：`_AK_OK == False` 必须让所有公开方法**优雅降级**，返回安全空值（见各方法），且**不得**在运行时抛 `ImportError`。
- 测试模块改写漂移用例时，应 monkeypatch 这些标志为 `False` 来验证降级路径。

---

## 1. StockFetcher（`modules/fetcher.py`）

```python
from modules.fetcher import StockFetcher
f = StockFetcher()   # config_path="config.yaml"，缺省即可；测试可传自定义路径
```

### 1.1 后端行情接入核心方法（最高优先稳定）

#### `get_realtime_quote(self, ticker) -> dict | None`
- 输入：`ticker` 为 6 位字符串代码（方法内部 `.zfill(6)` 归一）。空值返回 `None`。
- 返回 dict（获取失败返回 `None`）：
  ```python
  {
    "ticker": "601088",
    "name": "中国神华",
    "open": float, "prev_close": float, "current": float,
    "high": float, "low": float,
    "volume": float, "amount": float,
    "bid": [{"price": float, "volume": float}, ...],   # 买一到买五
    "ask": [{"price": float, "volume": float}, ...],   # 卖一到卖五
    "datetime": "2026-07-09 15:00:00"
  }
  ```
- 缓存：交易时段 30s TTL，非交易时段 5min TTL。
- **后端消费约定**：`/api/quote` 调用此方法；返回 `None` 时统一返回 `response.fail("行情获取失败")`。

#### `get_daily(self, symbol, start="2024-01-01", end=None, adjust="qfq") -> pd.DataFrame`
- 输入：`symbol` 6 位代码；`end` 缺省为今天；`adjust` ∈ `qfq|hfq`（默认 `qfq`）。
- 返回 DataFrame，列为：`date, open, close, high, low, volume, amount, change_pct`。
  - `date` 为 `pd.Timestamp`（**已 `pd.to_datetime`**）。
  - **成功语义**：只要 L1-L4（akshare/BaoStock/新浪/东方财富）任一成功 **或 L5 过期缓存命中**，返回非空 DataFrame。
  - **全失败语义（重要）**：当 akshare/BaoStock/新浪/东方财富 **全部失败且缓存无兜底** 时，**抛出 `RuntimeError`**（中文描述性信息，如 `"无法获取 XXX(600519) 的K线数据 … 原因：…"`），**不返回空 DataFrame**。调用方（含后端 /api/kline、测试）必须 `try/except RuntimeError` 兜底，统一返回 `response.fail("无行情数据")`。
- **4 级降级链**：akshare `stock_zh_a_hist`（L1，需 `_AK_OK`）→ BaoStock `_BaoStockFetcher.fetch_kline`（L2）→ 新浪 `_SinaFetcher.fetch_kline`（L3）→ 东方财富 `_UrllibFetcher.fetch_kline`（L4）→ 缓存兜底。
- 缓存：`end == 今天` 时 6h TTL，否则长期。
- **后端消费约定**：`/api/kline` 调用此方法；空 DataFrame 时统一返回 `response.fail("无行情数据")`；否则 `df.to_dict("records")` 经 `response.ok(data=records)` 返回。

#### `get_index(self, symbol="000001", start="2024-01-01", end=None) -> pd.DataFrame`
- 与 `get_daily` 同形状（指数日线）。`symbol` 缺省 `"000001"`（上证指数）。

### 1.2 搜索 / 元数据方法

#### `search_stocks(self, query, limit=15, with_price=False) -> list[dict]`
- 返回 list，每项：`{"code", "name", "display", "_matchType", "_score"}`。
- 空 query 或空库返回 `[]`。**永不抛异常**（降级到 `[]`）。

#### `lookup_code(self, query, limit=15) -> list[dict]`
- 返回 list，每项含 `code, name` 及评分字段（代码/名称/拼音首字母匹配）。
- 空 query 返回 `[]`。

#### `get_stock_name(self, ticker) -> str`
- 返回 `"代码(名称)"`（如 `600519(贵州茅台)`）；查询失败仅返回 `"代码"`；`ticker` 为空返回 `"<未知>"`。

#### `get_stock_basic(self, code) -> tuple[str, str]`
- 返回 `(code, name)`，未找到返回 `(str(code), "")`。

#### `get_name_code_map(self) -> dict`
- 返回 `{code: name}` 全量映射。

#### `get_all_codes(self, limit=None, random_seed=None) -> list[str]`
- 返回本地股票库**全部 A 股代码**列表（`list[str]`）。
- `random_seed` 指定时按种子洗牌（可复现）；`limit` 截断池大小。空库返回 `[]`。

#### `stock_exists(self, symbol) -> bool`

#### `get_stock_keywords(self, code_or_name, top_k=10) -> list`

### 1.3 板块方法

#### `get_sector_list(self, force_refresh=False) -> pd.DataFrame`
- 返回列：`sector, change_pct`（及透传来源）。
- 降级链：本地实时缓存 → 东方财富 urllib（L1）→ 同花顺 akshare（L2，需 `_AK_OK`）→ BaoStock（L3）→ 过期缓存兜底。**全部源与缓存均失败时抛 `RuntimeError`**（中文描述，如 `"ERROR 无法获取板块数据\n   数据源全部失败：…"`），**不返回空 DataFrame**。调用方须 `try/except RuntimeError` 兜底。
- TTL 三档：交易时 6min，午间休市 30min，其他休市 7 天。`force_refresh=True` 跳过缓存。

#### `get_sector_stocks(self, sector_name) -> pd.DataFrame`
- 返回列：`code, name, close, change_pct, market_cap`。
- **注意**：⚠️ 此方法**强依赖 `_AK_OK`**，未安装 akshare 时 **`raise RuntimeError("akshare 未安装，无法获取成分股")`**。后端/测试调用前需先判 `_AK_OK`，或 try/except 兜底。

#### `get_sector_cache_info(self) -> dict`
- 返回更新时间、缓存分钟数、数据来源（`sector_list_v3_source`）。

### 1.4 缓存管理

#### `clear_cache(self, table_name=None, cache_key=None) -> None`

---

## 2. NewsFetcher / EventMiner / SentimentAnalyzer（`modules/news.py`）

```python
from modules.news import NewsFetcher, EventMiner, SentimentAnalyzer
```

### 2.1 `NewsFetcher`

#### `fetch(self, keyword=None, source="auto", limit=50) -> pd.DataFrame`
- 返回列：`title, content, date, source, url`（抓取失败/空返回**空 DataFrame**）。

#### `fetch_stock_events(self, stock_code=None, stock_name=None, keywords=None, limit=50) -> pd.DataFrame`

#### `fetch_semi_news(self, keyword="半导体", limit=50) -> pd.DataFrame`

### 2.2 `EventMiner`（**规范类名，勿改名**）

```python
em = EventMiner()   # config_path="config.yaml"
```

#### `mine_events(self, keyword=None, source="auto", limit=30, auto_save=True) -> pd.DataFrame`
- 全流程：抓取 → 去重 → 关键词 → 情感 → 代码提取 → 入库。
- 返回 DataFrame，列为：
  `date, ticker, title, type, keywords, sentiment_score, source, url, is_major, intensity, pos_words, neg_words`
  - `type` = 情感类别（利好/利空/中性，对应 `sentiment["sentiment"]`）。
  - 附加 `df.attrs["original_count"]` / `df.attrs["deduped_count"]`。
- **空输入/抓取失败返回 `pd.DataFrame()`**（列结构允许为空）。`auto_save=True` 时写 `data/news.db` + 旧 CSV 兼容。

#### `auto_mine_events(self, keyword=None, source="eastmoney", limit=30) -> pd.DataFrame`

#### `generate_report(self, keyword=None, limit=50)` → 生成结构化报告（返回 str/DataFrame，严禁改名）

#### `sentiment_report(self, keyword=None, limit=50)` → 情感报告（返回结构同上 mine_events 派生）

#### `get_hot_keywords(self, days=7, topk=20)`

#### `alert_check(self, stock_code=None, hours=6)`

### 2.3 `SentimentAnalyzer`

#### `analyze(self, text) -> dict`
- 返回字段：`sentiment, score, is_major, intensity, pos_words, neg_words`。
- **失败时返回 `_default_result()` 安全 dict**（所有键存在，分数为 0，非空列表）。这是测试漂移用例的核心断言点。

#### `analyze_news(self, title, content="") -> dict`（同 `analyze` 形状）

#### `batch_analyze(self, news_df) -> pd.DataFrame`

---

## 3. 后端接入规约（/api/quote、/api/kline）

1. 复用进程内 `StockFetcher()` 单例（market_routes.py 已惰性创建，避免重复建连）。
2. 统一走 `backend/utils/response.ok/fail`，**禁止**直接 `return dict/str`。
3. 错误文案、状态码与 code 严格统一（与 `backend/api/market_routes.py` 实现一致）：
   - **/api/quote**：ticker 非 6 位数字 → `fail("参数无效", 400, invalid_param)`；`get_realtime_quote` 返回 `None` → `fail("行情获取失败", 502, quote_failed)`；成功 → `ok(data=dict)`；异常 → `fail("服务内部错误", 500, internal_error)`。
   - **/api/kline**：symbol 非 6 位数字 → `fail("参数无效", 400, invalid_param)`；**`get_daily` 抛 `RuntimeError`（全源+缓存失败）→ `fail("无行情数据", 404, no_kline_data)`**（注意：`get_daily` 永不返回空 DataFrame，404 由 RuntimeError 触发）；其他非预期异常 → `fail("服务内部错误", 500, internal_error)`；成功 → `ok(data=df.to_dict("records"))`。
   - quote 路由为裸 `except Exception → 服务内部错误`（`get_realtime_quote` 返回 None 而非抛错，已由 `if data is None` 处理，正确）。
4. 鉴权：行情接口仍需 JWT（与现有受保护接口一致）。
5. 入参校验：`symbol`/`ticker` 必须为 6 位数字，否则 `response.fail("参数无效")`。
6. 不实现 `get_sector_stocks`（强依赖 akshare，不在行情接入范围）。
7. **响应信封形状（权威，与 `backend/utils/response.py` 一致）**：
   ```json
   { "status": "ok" | "error", "code": "<业务码>", "message": "<人类可读提示>", "data": "<业务数据|null>" }
   ```
   - 成功判定键为 **`status == "ok"`**（不是 `code`），前端消费方必须按此判断。
   - 错误时 `status == "error"`，`code` 为业务码（如 `invalid_param`/`quote_failed`/`no_kline_data`/`internal_error`），`message` 为中文提示。
   - 注意：早期文档/对话中曾误写为 `{code,msg,data}`，以此处为准。

## 4. 测试模块改写规约（19 个漂移用例）

- 用 monkeypatch 把 `fetcher._AK_OK` / `news._AK_OK` / `news._JIEBA_OK` 设为 `False`，验证：
  - `get_daily` 全源失败 → 抛 `RuntimeError`（**非**返回空 DataFrame）；`get_realtime_quote` → `None`；`get_sector_stocks` → 抛 `RuntimeError`；`get_sector_list` 全源失败 → 抛 `RuntimeError`。
  - `search_stocks`/`lookup_code`/`get_all_codes` → `[]` 或安全空。
  - `EventMiner.mine_events(...)` → 空 DataFrame（不抛）。
  - `SentimentAnalyzer.analyze("任意")` → dict 且含全部 6 个键。
- **类名锁定**：所有测试引用 `EventMiner`（不是任何改名后的类）。
- 改写后必须守住：`backend/tests/test_api_contracts.py` 16 passed + `backend/tests/test_security.py` 12/12。
- 测试需自建轻量 stock DB fixture（避免依赖生产 `data/`），`StockFetcher(config_path=...)` 指向测试配置。

---

## 5. 非契约范围（数据层可继续内部优化，不影响签名）

- `_BaoStockFetcher` / `_SinaFetcher` / `_UrllibFetcher` 内部实现可改。
- 缓存表结构、TTL 数值、降级顺序可微调（只要对外返回类型不变）。
- 日志/`print` 语句、`_read_cache`/`_write_cache` 内部参数可优化。
- 新增方法（如 `get_macro`/`get_commodity_price`/`get_financial`）自由演进，不纳入本契约冻结。
