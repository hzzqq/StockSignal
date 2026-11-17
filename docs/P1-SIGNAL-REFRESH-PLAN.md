# P1 信号推进方案（2026-11-17 实测，跨项目）

## 结论先行

P1 链路**没有死**——记忆中「baostock 脚本消失 / B 路径已死 / 信号停在 10-16」全部过时。
实测：信号已推进到 **2026-11-09**，卡点是 11-12 K 线桥接在 850/1492 超时中断。
已用 30 只小批量验证续跑可用（30/30 成功刷新到 11-16）。
**全量推进是数小时跨项目长任务，按长任务禁令不盲目启动**——本文件给出可安全执行的方案。

## 一、实测取证（2026-11-17）

| 项 | 实测真值 | 证据 |
|---|---|---|
| 6 个主信号 latest_date | **2026-11-09** | `E:/project/sj/data/P1/processed/signals/*.json` 逐个读 |
| fusion 信号 | 2026-10-26（设计性滞后，用前瞻 y_excess 标签，不参与一致性门禁） | 同上 |
| rotation | `latest_date=None`（诚实拒绝，非缺失） | `signal_rotation.json` |
| baostock 拉取脚本 | **存在**：`E:/project/sj/P1-QuantFactor/scripts/31_baostock_fetch.py`（mtime 11-07） | 磁盘实测 |
| baostock 原始数据 | `E:/project/sj/data/P1/raw/baostock_daily/baostock_daily.parquet`（149MB，361 万行，**最新 11-04**） | pandas 实测 |
| K 线本地最新日 | **2026-11-11** | 桥接日志 `saved_global_max` |
| 卡点 | 11-12 桥接日志在 `progress 850/1492` 后超时中断，无 `KLINE DONE` 完成标志 | `logs/bridge_run_20261112.log` |
| 环境 | baostock 0.9.20（登录成功，可拉到 **11-16**）、akshare 1.18.64、tushare 1.4.29 均已装 | import + 登录实测 |

## 二、推进链路（按顺序，全部支持断点续跑）

### Step 0：刷新 baostock 因子源（可选，数小时）

```bash
# 现有 batch parquet 会被跳过逻辑复用——要拉 11-05~11-16 必须先移走旧 batch
# E:/project/sj/tools/unattended/run_baostock_parallel.py
# ⚠️ 不要直接 rm——先备份到 E:/tmp/p1_baostock_bak/ 再移，防止拉取失败无回退
```

### Step 1：K 线桥接（关键卡点，支持断点续跑）

```bash
cd E:/project/sj/P1-QuantFactor
# 小批量验证已通过：--limit 30 → KLINE DONE ok=30 fail=0
python scripts/18_bridge_kline.py --source auto --limit 30     # 已验证
# 全量（1492 只，约 1.5~2 小时，务必带检查点后台任务）：
python scripts/18_bridge_kline.py --source auto               # 跳过已到 11-16 的，接着跑
# 断点续跑：脚本自动跳过 sym_max >= TARGET 的标的，重复执行不重复拉
```

**已知缺陷（勿踩）**：脚本打印 `KLINE DONE` 后进程**不自行退出**（本次 180s 硬超时 EXIT=124 才终止）。
全量跑时必须外层带硬超时 + 检查点，或在脚本末尾补 `sys.exit(0)`（跨项目代码，本次未改）。

### Step 2：信号全链推进

```bash
# zz_daily_push.sh 支持步骤级断点续跑：bash zz_daily_push.sh S04 从 S04 继续
bash scripts/zz_daily_push.sh
# 内置 13 步：面板→数据集→EV→log_amount→GRU推理→EV推理→集成→
#            四路导出→fusion→复制到 ks→绩效→敏感性矩阵
# 每步 exit 码 + 心跳落盘到 logs/p1_push_heartbeat.log，失败即停
```

### Step 3：同步到 StockSignal

`zz_daily_push.sh` 最后一步自动复制到 `E:/project/ks/StockSignal/data/p1_signals/`。
或用单一真理源 CLI 手动校验：
```bash
cd E:/project/ks/StockSignal
python scripts/refresh_p1_signals.py --check    # 按数据日 latest_date 选最新，不降级覆盖
```

## 三、长任务纪律（老板红线，必须遵守）

1. **硬超时**：Step 1 全量约 1.5~2 小时，外层 `timeout` + 检查点。
2. **检查点**：桥接脚本自身按标的落盘（跳过已完成），中断后重跑自动续。
3. **高频进度日志**：已有 `progress N/1492` 每 50 只打印一次。
4. **备份优先**：移动旧 baostock batch parquet 前先备份，不直接删。
5. **不碰生产服务**：全链写的是 P1 数据与 ks 副本，与 Flask(5050) 无关，不会锁库。

## 四、本次未执行的部分（诚实说明）

- **未跑 Step 0/1/2 全量**——数小时跨项目长任务，且 Step 1 有不自动退出的缺陷，
  按长任务禁令不在当前会话盲跑。已用 30 只小批量验证关键环节可用。
- **未改跨项目代码**——`18_bridge_kline.py` 退出缺陷属 P1 仓，需老板确认后再改。
- 待老板确认「启动全量推进」后，按本方案建带检查点的后台任务执行。
