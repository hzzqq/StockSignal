# 日线数据取数缓存层加固勘测报告

> 性质：**只读勘测**（2026-10-11，Trae 空间）。除本文档外未修改任何代码/数据；
> cache.db 全程 `sqlite3 mode=ro` 只读连接查询，未触碰任何拉取任务。
> 背景痛点：2026-10-11 蒙特卡洛模拟 300 只股票池拉取，新浪源大量 `RemoteDisconnected`
>（urlopen 重试 2 次仍失败）、BaoStock 空结果/限流，靠东财与缓存兜底才完成。

---

## 一、现状快照

### 1.1 get_daily 降级链（modules/fetcher.py:1900-1985）

```
cache 命中 → L1 akshare ┐
                        ├─ 4 线程并行竞速（FIRST_COMPLETED，每轮 wait 10s，最多 2 轮 ≈ 20s 上限）
             L2 BaoStock ┤
             L3 新浪     ┤
             L4 东财     ┘
→ L5 过期缓存兜底（_read_stale_cache）→ 全失败 RuntimeError（中文友好错误）
```

| 环节 | 关键实现 | 失败处理 |
|---|---|---|
| 缓存命中 | `cache_key = daily_{symbol}_{start}_{end}_{adjust}`；`end==今日` 时 TTL 6h，否则 `cache_days=7`（config.yaml） | 不命中则走竞速 |
| L1 akshare | `stock_zh_a_hist`，`max_retries=0`（RemoteDisconnected 立即跳过） | 返 None 交降级链 |
| L2 BaoStock | 进程级连接池复用登录（R77 锁）；`adjustflag` 映射 | 空结果/异常→None |
| L3 新浪 | `money.finance.sina.com.cn` json_v2，`datalen=800`（不可按日期过滤），`_safe_urlopen timeout=15, retries=2, backoff=0.5` | 同上 |
| L4 东财 | push2 kline，`timeout=20, retries=2` | 同上 |
| L5 缓存兜底 | `LIKE 'daily_{symbol}%'` 取 `updated_at` 最新一条，**忽略 start/end/adjust 差异** | 无则进 RuntimeError |
| 写缓存 | 成功后 `INSERT OR REPLACE`，`updated_at=CST now` | —— |

### 1.2 request_utils.py 治理参数（熔断/节流/代理）

| 参数 | 默认值 | 说明 |
|---|---|---|
| Session Retry | total=3, backoff=0.5, 429/5xx | 仅 GET/HEAD/OPTIONS；仅对走 `http_get/http_post` 的调用生效 |
| `SS_HOST_MIN_INTERVAL` | 0.2s | per-host 节流，本机后端除外 |
| `SS_FAIL_THRESHOLD` / `SS_COOLDOWN_SECONDS` | 5 次 / 60s | 连续失败熔断，冷却中抛 `CircuitOpenError` |
| `SS_PROXY_POOL` | **0（默认关）** | 免费代理池：3 采集源 + ipify 校验(8s) + fail_threshold=3 判死；407/429/403/5xx 轮换，池空回退直连 |
| `SS_PROXY_MAX_ATTEMPTS` | 3 | 单次请求最多换 3 个代理 |

⚠️ **覆盖缺口**：`fetcher` 的日线链路（`_feed_io._safe_urlopen` 直连 urllib）**不在**
request_utils 治理层内——新浪/东财 K 线请求既无 per-host 节流也无熔断。荐股一轮对新浪
约 300+ 次请求（8 并发×每股 1 次 L3 竞速，瞬时失败再重试 2 次），新浪限流相当程度是
自己打出来的。

### 1.3 cache.db 实测（2026-10-11 只读查询）

- 文件 ~56MB，8 表。`daily_cache` 1,080 行（其中日线键 1,074 行）、**506 只**个股
  （全 A ≈5,400 只，覆盖率 ≈9%——缓存是「用过的股票」沉淀，非全市场库）。
- **键碎片化**：每股平均 2.1 个缓存键、**最多 100 个**。cache_key 含滚动 start/end →
  日期一变键就变，**跨日天然 miss**（昨日键今日不命中，只能等 L5 兜底捞）。
- 写入分布：2026-10-11 写 364 行（当日蒙特卡洛）；09-08/09 两日 463 行；其余散布 7 月起。
- 样本 60 只「每股最新缓存行」的**数据真实截止日**：43 只→2026-09-30、13 只→2026-09-08、
  4 只→7 月。即写入时间 ≠ 数据截止日（10-11 的批量写入数据停在 09-30，与模拟以
  `end=2026-09-30` 拉取一致）。
- 单行 data_json 平均 50KB / 最大 232KB。其余表：index_cache 11 / sector_cache 18 /
  rt_quote_cache 8 / stock_name_cache 23 / all_stocks 1（全列表永久缓存）。

### 1.4 消费方

- **荐股引擎** `recommend_engine.generate_daily_recommendation`：universe 200 只（蒙特卡洛
  300）×260 交易日，`fetch_many(max_workers=8, timeout=240)` 整批硬边界；取数失败→None→
  **该股静默跳过**（<90 行也跳），**无任何「用了旧缓存」标注**。调度器
  `backend/recommend_scheduler.py` 每交易日 15:30 后自动跑（20min 巡检、幂等）。
- **页面**：10/13/22/23/31/34/40/41/42/47/95 等约 34 个文件引用 get_daily；backtest.py、
  analysis_engine、signal.py 等模块同链路。
- **已有诚实基建**（A 方案的现成范式，不必新造）：
  - `request_utils.fetch_with_snapshot`：live/snapshot/unavailable 三态回退 + as_of；
  - `modules/display_provenance.py`（T-215）：daily_kline 展示源 as_of 取自 daily_cache
    内容日期，已挂 10/24 页——但是**页面级全局值**，非单次调用级；
  - `modules/data_health.py`：as_of/停更检测/新鲜度评分单一真理源。

### 1.5 勘测要点（关键发现）

1. **L5 旧缓存兜底已存在但完全静默**：返回的 DataFrame 与新鲜数据不可区分，无 as_of /
   is_fallback 元数据；荐股与回测拿旧数据当新数据用，诚实语义缺口在此。
2. **`observe_cache_fallback`（_feed_io.py:240）是死埋点**：全仓零调用点，缓存兜底命中
   率在 SOURCE_METRICS 里看不到。
3. **L5 兜底存在数据正确性隐患**：按 `daily_{symbol}%` 匹配，可能捞到**不同复权**
   （qfq vs none 价格不可比）或不同窗口的旧行，直接返回给调用方。
4. **缓存键碎片化**：滚动日期窗口进键 → 跨日命中率 ≈0，缓存退化为「当日 6h 去重 +
   事后兜底」，这是 B 方案效果的前置约束。
5. **治理层未覆盖 fetcher urllib 路径**：新浪/东财 K 线无节流无熔断。
6. **风控实证**（T-177/T-179 留痕）：东财是「频率配额+灰度降级」非 IP 封禁；BaoStock 是
   账号级限流（proxy_pool docstring 诚实声明代理无效）；BaoStock 全量刷新实测 11h 只完成
   1/3——全市场预热不可行。

---

## 二、三方案对比

| 维度 | A) 失败回落旧缓存 + as_of 标注 | B) 定期批量快照/预热 | C) 代理池默认启用/调优 |
|---|---|---|---|
| 现状基础 | L5 兜底**已有**（缺元数据通道）；fetch_with_snapshot / display_provenance 范式现成 | 调度范式现成（recommend_scheduler / daily_snapshot.py），**无**预热脚本；键碎片化未解 | 池子完整、默认关、覆盖 HTTP 层（BaoStock 无效） |
| 成本 | **低**：get_daily 加可选 meta 通道（34 文件引用，不动签名）；stale 匹配补 adjust/窗口过滤；接通 observe_cache_fallback；荐股落盘 data_as_of + stale_count；页面 caption | **中**：scripts/warm_daily_cache.py（候选池 300~500 只，非全市场）+ 挂 15:30 后调度；**前置项：缓存键按 symbol 归一化**（否则预热写的键与运行时请求键不一致＝白拉）；遵守长任务四件套（硬超时/检查点/进度日志/短任务） | 默认启用**改造成本低但风险高**；真正有效的小改造是给 `_safe_urlopen` 路径补 per-host 节流 |
| 收益 | **高**：直击本次实测痛点（降级时静默用旧数据）；符合诚实数据语义铁律；零网络层改动 | **高**：把「生成时才发现取不到」变「收盘后闲时充分重试」，容忍窗口从秒级放大到小时级；预热后荐股基本全缓存命中（速度也快） | **低/为负**：新浪 RemoteDisconnected 是频率型风控，免费代理（慢/失效率高/蜜罐）大概率雪上加霜；东财实证为配额型非 IP 封禁；`apply_to_env` 写**进程级**代理环境变量，akshare 及一切 trust_env 出网（含后端/LLM API）全被带偏——误伤面不可控 |
| 风险 | 低。注意：stale 兜底的 adjust 不一致隐患须一并修（否则标注 as_of 反而固化一个价格口径 bug）；meta 通道纯 additive | 中。①键归一化是动 cache_key 的大改（涉及 L5 匹配/清理逻辑，需独立评估）；②与常驻服务并发写 cache.db（SQLite 单写锁）——须错峰荐股窗口/短事务；③BaoStock 限流决定只能预热候选池 | 默认开启**不可控**（外溢进程级 env）。节流补全是低风险改法 |
| 结论 | **首选（P0）** | **第二期（P1）**，键归一化前置或捆绑 | **不推荐默认启用（P2 维持 opt-in）**；改投节流补全 |

---

## 三、推荐路径

**第 1 步（P0）— A：as_of 诚实标注 + L5 兜底一致性修复**（一轮一缺陷，可拆两笔）
1. `_read_stale_cache` 增加复权（adjust）一致过滤 + 请求窗口裁剪 + 行数下限校验——先复现
   取证（构造 qfq 请求命中 none 旧行），修复 + 负向验证；
2. `get_daily` 加可选元数据出口（如 `meta_out: dict | None`：`as_of`/`is_stale`/`source`），
   L5 命中时如实填充，同时接通 `observe_cache_fallback` 死埋点；
3. `recommend_engine` 落盘带 `data_as_of` + `stale_count`；页面/荐股结果展示
   「数据截至 X 日」（复用 display_provenance 既有展示样式，additive）。
   守卫：tests/test_fetcher.py、test_whitebox_fetcher.py、test_display_provenance.py，
   新行为必须 mutation 证非假绿。

**第 2 步（P1）— B：候选池预热**
1. 前置评估缓存键按 symbol 归一化（如 `daily_{symbol}_{adjust}` 单键 + 增量拼接），或预热
   端复刻调用方键参数（快速但脆弱，作过渡）；
2. `scripts/warm_daily_cache.py`：荐股候选池 + 自选股 + 指数（300~500 只），东财/akshare
   优先、BaoStock 限速兜底，批量 650 交易日窗口；检查点落盘 + 硬超时 + per-host 节流；
3. 挂 recommend_scheduler 同款守护线程（15:30 收盘后、错峰荐股生成窗口），STOCKSIGNAL_*
   开关默认可关；绝不手工编辑 data/，全走脚本 + 先 --dry-run。

**第 3 步（P2，可选小改）— 治理补全而非代理**
- 把 `request_utils._throttle` 语义延伸到 `_safe_urlopen` 路径（新浪/东财 K 线），
  消灭「自己打自己」的限流诱因；L3 新浪 `datalen=800` 可按需收窄。
- 代理池维持 `SS_PROXY_POOL` 默认关（`SS_PROXIES` 手动塞自有付费代理的用法保留）。

> 每步均按项目铁律：spec 冻结 → 测试先行 → mutation 证非假绿 → pytest 全绿 → 独立提交
> → 改完即推（FF 流程）。本报告仅为勘测产出，未做任何实现。
