# P1 事件因子信号恢复方案（只读勘测产出）

> 勘测日期：2026-10-11 ｜ 勘测性质：**只读**（未修改 E:/project/sj 任何文件，未运行训练/长任务）
> 勘测范围：`E:/project/sj/data/P1/`、`E:/project/sj/P1-QuantFactor/`（代码只读）、`E:/project/ks/StockSignal/data/p1_signals/`、`E:/project/sj/models/P1/`、`E:/project/sj/_qf/`（git log 只读）
> parquet 一律只读元数据/日期列，未整读大文件。

---

## 一、现状快照（实测）

### 1.1 ks 侧信号文件（决策闭环消费端，`data/p1_signals/`）

| 文件 | ks mtime | generated_at | latest_date |
|---|---|---|---|
| signal_baseline_h10.json | 09-02 15:17 | 2026-08-31 | **2026-08-14** |
| signal_ev_h10.json（事件因子，55 页默认 / 54 面板引用） | 09-02 15:17 | 2026-09-02 | **2026-08-14** |
| signal_fusion_h10.json | 09-02 15:17 | 2026-09-01 | **2026-08-14** |
| signal_gru_h10.json | 09-02 15:17 | 2026-09-01 | **2026-08-14** |
| signal_ens_v39gru_w025_h10.json | 09-16 23:07 | 2026-09-15 | **2026-08-14** |

**全部 5 个信号 latest_date 停在 2026-08-14**（截至勘测日已滞后约 41 个自然日 / ~50 个交易日），决策闭环对事件因子诚实降权的现状与背景描述一致。

### 1.2 sj 侧数据集版本（`E:/project/sj/data/P1/processed/`）

| 文件 | mtime | 行数 | 只数 | 因子 | 日期范围 | 说明 |
|---|---|---|---|---|---|---|
| dataset_h10.parquet | **2026-10-08 20:27** | 2,862,399 | 1492 | 38 | 2018-01-24 ~ **2026-09-16** | **自动化 10-08 轮已重建（新）** |
| dataset_h10_v39.parquet | 09-06 09:23 | 3,320,235 | 1427 | 39(+log_amount) | 2015-01-27 ~ 2026-08-14 | v39 生产代 |
| dataset_h10_v40.parquet | 09-07 13:53 | 3,320,235 | 1427 | 41(+baostock 真实市值/换手) | 2015-01-27 ~ 2026-08-14 | v40 实验代 |
| dataset_h10_ev.parquet | 09-01 13:42 | — | 1427 | 47(38+9 牧羊人) | 2015-01-27 ~ **2026-08-14** | **EV 生产基座，已过期** |
| dataset_h10_ev_v48.parquet | 09-06 09:23 | 3,320,235 | 1427 | 48(47+log_amount) | 2015-01-27 ~ 2026-08-14 | v48 实验代 |
| panel.parquet | **2026-10-08 20:26** | 2,904,167 | 1492 | — | 2018-01-02 ~ **2026-10-08** | 面板已最新 |
| raw/kline（1492 只） | **2026-10-08 20:26** | — | 1492 | — | 至 **2026-10-08** | 原始 K 线已最新 |

> ⚠️ `src/features/pipeline.py:126` 对 `y_excess` 做 dropna → **数据集只保留「还有 10 个交易日前瞻标签」的行**。即：kline 刷到 T，数据集特征最多到 T−10 交易日，这是 h10 口径的**设计性滞后**，不是缺陷。10-08 建到 09-16（10-08 前推 10 个交易日）完全吻合。

### 1.3 勘测纠偏（推翻/修正此前结论 4 条）

1. **「特征数据集 08-31 构建、只到 08-14」已过时**：`dataset_h10.parquet` 已于 **2026-10-08 20:27** 由自动化重建，特征到 **2026-09-16**（1492 只，38 因子）。原始 K 线已刷到 2026-10-08。
2. **「baostock 限流卡死」不准确**：baostock 走的是 `18_bridge_kline.py` 增量桥（START=2018-01-01，0.4s/只限速、指数退避、20 连败重登、`probe_latest_available()` 探针+断点续跑），WorkBuddy automation `cf399ccd` 在 **09-25 / 10-02×2 / 10-07 / 10-08** 五轮全部成功（10-08 轮全量 1492 只 ok=1492 fail=0，~1h25m）。09-16 探针的服务端数据流损坏（error 10002007/解压错误）是**间歇性故障**，非持续封禁。
3. **断点不在取数，在推理/导出**：每日推送脚本 `zz_daily_push.sh`（面板→数据集→log_amount→GRU 推理→baseline 2026 增补→集成→导出→复制 ks 共 8 步）**只有一份运行日志 `p1_daily_push_20260917_203439.log`，且仅 8 行、在步骤 1 特征构建中途中断**，此后再未运行。即 09-17 起推送链整体停摆。
4. **推送脚本本身不含 EV 环节**：`zz_daily_push.sh` 只导出 gru/baseline/ens 三路，**不含 `14.build_event_dataset()`（牧羊人事件因子并入）也不导出 signal_ev**——即使推送恢复，EV 信号仍不会前进。这是自动化的结构性盲区。

### 1.4 生产 EV 配置（实测锁定）

- 生产预测文件：`pred_gru_ev_t10_seq40_h128_lr1e-3_h10.parquet`（**t10：seq40/h128/lr1e-3，input_norm 权重，IC=0.0941**；执行层 I1 非重叠桶 rf=10 最优，2026 净 +16.83%/夏普 1.83，见 `report_improve_10x_rf10_evprod.csv`）
- 权重：`E:/project/sj/models/P1/gru_ev_t10_seq40_h128_lr1e-3_h10.pt`（存在，另有 .bak_20260905）
- EV 数据集合成：`scripts/14_event_factor_iterate.py::build_event_dataset()` 读 `dataset_h10.parquet`（默认名，即已刷新的新数据集）+ `E:/project/ks/StockSignal/data/shepherd_history.csv`（牧羊人 9 因子，z-score+ffill 按日广播）→ 覆盖写 `dataset_h10_ev.parquet`
- log_amount 并入：`scripts/27_add_logamount_factor.py`（dataset_h10→v39、dataset_h10_ev→v48）
- 导出：`scripts/06_export_signal.py --pred ... --model ev`；全链收尾 `scripts/15_finalize_ev.py`（含全量重训确认 ~25min）
- 牧羊人 CSV 现状：最新行 **2026-09-30**（mtime 10-07），≥ 数据集边界 09-16，**够用**（ks 侧注意 10-08/10-09 两个交易日尚未落）

### 1.5 baostock 全量拉取残片（旧 Plan B 遗留）

`raw/baostock_daily/` 仅 1 个未完成分片：`baostock_daily_batch_000.partial.parquet`（233,706 行、~100 只、2010-01-04~2026-09-15，mtime 09-15 22:21），另有 2 个空的 `_tushare_tmp*` 目录（09-16 试验残留）。**0 个整片**，`--combine` 的缺片护栏会拒绝合并。

---

## 二、三条恢复路径对比

| | A) 现有 v40/v48 预测直接接回 finalize/导出 | B) baostock 续拉完成重建 | C) Tushare 替换取数重建 |
|---|---|---|---|
| **本质** | 用已存在的 pred 文件重跑 15/06 导出 | 完成 31_baostock_fetch 15 片全量拉取 → 32 派生真实因子 → 重建 v40 型数据集 | 启用 31b_tushare_fetch（同 schema，下游 32 零改动）→ 重建 v40 型数据集 |
| **能否推进 latest_date** | **不能（已验证）**：v39/v40/v48 全部数据集止于 08-14，其 pred 文件最大日期即 08-14；09-18 sj 侧重导出的 signal_ev latest_date 仍是 08-14，实证重导出无解 | 间接能，但**与 EV 信号无关**：31 号拉的是逐日估值/换手（peTTM/pbMRQ/turn），只服务 v40 型 baseline 因子（log_mktcap_real/turnover_daily）；EV 生产链（38+9 牧羊人+log_amount）**不需要这份数据** | 同 B：只补 v40 型估值因子，**不在 EV 关键路径上** |
| **成本/时长** | 几分钟 | 免费但剩余 ~14 片×~95 只全历史拉取；服务端间歇性损坏（09-16 探针实录）+ 曾有黑名单（10001011）风险；约数小时且可能反复卡死 | 免费档 daily_basic 1 次/分 → 按股票模式 1427 只×65s ≈ **25.8h**（可断点续跑）；补全账户资料可能升 50 次/分 ≈ ~30-50min；付费 ¥200-500/年更快 |
| **风险** | 无新信息，纯浪费 | 高（服务端不稳 + 残片歧义：combine 有缺片护栏但 partial 只到 batch_000） | 低（脚本健壮：线程超时/自适应退避/断点续跑/--dry 校验），但**价值与 EV 恢复无关** |
| **建议** | ❌ 放弃（仅可作为导出链自检） | ❌ 不必做（K 线刷新已由 18_bridge 增量链接管且工作正常） | ⏸ 暂缓，仅作数据源备胎（若未来要推广 v40 型因子或 baostock 长期宕机再启用） |

### 推荐：A′（勘测新发现的最短路径）——在已刷新的数据链上重建 EV 并恢复推送

**核心事实**：取数（kline→10-08）、面板（→10-08）、基座数据集（→09-16）**已经由 10-08 自动化轮全部就位**，EV 信号恢复只剩「EV 合成 → 推理 → 导出 → 复制」四步，全部本地操作、零外部 API 依赖、预计 **≤1 小时**。

**落地步骤**（执行主体应为 sj/WorkBuddy 空间，本勘测只给路线）：

```bash
# ① EV 数据集重建（读已刷新的 dataset_h10.parquet + ks 牧羊人 CSV → dataset_h10_ev.parquet，~2-5min）
python scripts/14_event_factor_iterate.py 中的 build_event_dataset(10)   # 需以模块方式调用或加 CLI 入口

# ② log_amount 并入（→ dataset_h10_ev_v48.parquet，~2-5min）
python scripts/27_add_logamount_factor.py

# ③ EV 2026 窗口推理（二选一）：
#    a. 首选【predict-only】：仿 zz_predict_only_gru.py 写 EV 变体，复用 gru_ev_t10_*.pt 权重
#       只延伸 2026 预测至 09-16，模型口径与已部署信号完全一致（无重训漂移），~10-20min
#    b. 备选【重训】：python scripts/15_finalize_ev.py（全量确认 ~25min；注意新面板起始 2018-01
#       与 v40 代的 2015-01 不同，训练窗变短 → 口径漂移，须老板认可后方可采用）
# ④ 导出（秒级）
python scripts/06_export_signal.py --pred data/P1/processed/pred_gru_ev_<tag>_h10.parquet --model ev --horizon 10

# ⑤ 复制到 ks（推送链第 8 步原样）
cp data/P1/processed/signals/signal_ev_h10.json E:/project/ks/StockSignal/data/p1_signals/

# ⑥ 顺带恢复 gru/baseline/ens 三路：重跑 zz_daily_push.sh 步骤 3-8
#    （zz_predict_only_gru.py 直接兼容新 dataset_h10，无需改动）
```

恢复后预期：`signal_ev_h10.json` latest_date = **2026-09-16**（当前 kline→10-08 的 h10 标签边界；若先把 10-09 K 线补上再重建则为 09-17）。后续每个交易日由修复后的自动化维持「T 日 K 线 → T−10 信号日」滚动。

**自动化修复（防复发，与 ④ 同等重要）**：
1. 恢复 `zz_daily_push.sh` 的定时调度（09-17 步骤 1 中断后无人重试；建议每步落 exit 码与心跳日志，断在哪一步一眼可见）；
2. 给推送脚本**补 EV 环节**（①②③④ 当前缺失），否则 EV 信号永远不会自动前进；
3. 确认 automation `cf399ccd` 是否仍激活（10-09（周五）晚间无执行记录、无日志，疑似 10-08 后停摆，需 sj 侧核实）。

---

## 三、风险与前置条件

1. **h10 设计性滞后（须向老板明示）**：即使全链恢复，latest_date 永远 ≈ 「今天 − 10 个交易日」。要贴到当日需改推理为 label-free 尾部（对最新 N 日仅用特征出分、不带标签），属**设计变更**，影响口径与守卫，须老板拍板，不在本方案内擅动。
2. **只数与起始日期漂移**：新数据集 1492 只 / 2018-01-24 起（v40 代为 1427 只 / 2015-01-27 起）。predict-only 路线只延伸 2026 预测、权重不变，风险小；重训路线则训练窗缩短 3 年，**必须走老板审批**。
3. **EV 数据集覆盖写风险**：`build_event_dataset()` 与 `27_add_logamount_factor.py` 均直接覆盖 `dataset_h10_ev*.parquet`，执行前应备份现文件（`*.bak_2026MMDD` 惯例已存在，沿用）。
4. **推送脚本 09-17 中断原因未查明**：日志无错误尾迹（疑似会话被杀）。重跑前先补步骤级 exit 码落盘；首跑用短面板样本验证到第 8 步全通后再挂定时。
5. **牧羊人 CSV 单向依赖**：EV 因子源在 ks 领地（sj 只读引用）。当前到 09-30 ≥ 09-16 够用；ks 侧需保证自身牧羊人流水线恢复日更（10-08/10-09 缺行，另案确认，不影响本次恢复）。
6. **baostock 服务端间歇故障**：bridge 已有退避/重登/探针缓存护栏且 10-08 全量成功；但 09-16 型数据流损坏可能复发。红线：**取不到就如实停在上一个真实交易日，绝不伪造/补齐**（automation 记录显示该红线一直被遵守）。
7. **诚实语义不破**：latest_date 由 pred 数据决定，导出链不会说谎；恢复后决策闭环的「事件因子降权」随 latest_date 前进而自动解除，ks 侧**无需改代码**（55 页/54 面板按 mtime 自动重载）。
8. **git 发布仓同步**：若 ③ 走「新增 EV predict-only 脚本」路线，改动属 sj 实验树，需经 `sync_to_qf.py --check/--apply` 单向同步到 `_qf` 并中文提交（FF 推送），勿直接改 `_qf`。

---

## 附录：关键文件索引

| 用途 | 路径 |
|---|---|
| ks 消费端信号目录 | `E:/project/ks/StockSignal/data/p1_signals/`（README.md/VERIFY.md 含口径铁律） |
| 基座数据集（已刷新） | `E:/project/sj/data/P1/processed/dataset_h10.parquet`（meta: 10-08 建，至 09-16） |
| 面板 | `E:/project/sj/data/P1/processed/panel.parquet`（至 10-08） |
| EV 合成 | `E:/project/sj/P1-QuantFactor/scripts/14_event_factor_iterate.py`（`SHEPHERD_CSV` 硬指 ks CSV） |
| log_amount 并入 | `E:/project/sj/P1-QuantFactor/scripts/27_add_logamount_factor.py` |
| EV 生产预测/权重 | `processed/pred_gru_ev_t10_seq40_h128_lr1e-3_h10.parquet`、`models/P1/gru_ev_t10_...pt` |
| 导出/收尾 | `scripts/06_export_signal.py`、`scripts/15_finalize_ev.py` |
| GRU 推理专用 | `scripts/zz_predict_only_gru.py`（38 因子版，可直接复用） |
| 每日推送（已断） | `scripts/zz_daily_push.sh`（日志：`ks/StockSignal/logs/p1_daily_push_20260917_203439.log`，8 行即断） |
| K 线增量桥（可用） | `scripts/18_bridge_kline.py`（baostock，0.4s 限速，断点续跑） |
| baostock 全量残片 | `data/P1/raw/baostock_daily/baostock_daily_batch_000.partial.parquet`（233,706 行） |
| tushare 备胎 | `scripts/31b_tushare_fetch.py`（TUSHARE_TOKEN 环境变量，token 不落盘） |
| 发布仓 | `E:/project/sj/_qf`（git，最新 4b80fda）；同步工具 `scripts/sync_to_qf.py` |
| 自动化执行记录 | `E:/project/sj/P1-QuantFactor/.workbuddy/memory/automations/cf399ccd-.../memory.md`（09-25~10-08 五轮） |
