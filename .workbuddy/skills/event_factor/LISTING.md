# 事件因子 · SkillHub 上架物料单（Submission Package）

> 目标平台：**SkillHub**（https://skillhub.cn/）——面向中国用户的 AI Skills 社区，
> 个人开发者真实入口：https://skillhub.cn/dashboard/publish

---

## 1. 基础信息（复制到平台表单）

| 字段 | 内容 | 合规检查 |
|------|------|----------|
| 技能名称 | 事件因子 | ≤20 字 ✓（4 字） |
| 英文名 | 事件因子·A股信号 | 备用 |
| slug | `event-factor` | 小写字母/数字/连字符 |
| 版本 | 1.0.2 | 语义化版本 |
| 作者 | hzzqq（黄子州） | 与你的开发者账号一致 |
| 分类标签 | 股票、金融、投资、量化 | 3–5 个，覆盖搜索场景 |
| 适用平台 | WorkBuddy / 支持 SkillHub 规范的 AI Agent | |

---

## 2. 技能描述（中文，100–300 字）

```text
事件因子是一个股票（A股）类型的事件/regime 信号技能。它调用 StockSignal 的 modules.event_factor，从五个真实源按兜底序取真实信号：P1-QuantFactor EV 模型、东方财富个股新闻情感、东方财富龙虎榜、本地事件追踪主表（人工录入与语音入库沉淀）、用户语音转写事件（仅本人可见，受隐私闸门强制）。可选叠加全球宏观上下文（美债10Y、DXY、美元兑人民币、美联储利率等）作展示，但绝不参与事件因子评分。五个源互不替代、绝不造数；取不到即如实返回不可用状态，不编造信号、不臆造填充。输出为看多/看空方向与百分位等研究参考，不构成投资建议。
```

**字数**：约 291 字。

---

## 3. 英文描述（平台双语备用）

```text
Event Factor is a stock/A-share event & regime signal skill. It calls StockSignal's modules.event_factor and reads five real sources in fallback order: P1-QuantFactor EV model, Eastmoney per-stock news sentiment, Eastmoney dragon-tiger list, the local event ledger (manual + voice-ingested), and the user's own voice-transcribed events (strictly private, gated). Optional global macro context is display-only and never enters the score. The five sources never substitute for one another and never fabricate data; when data is unavailable it returns an explicit unavailable state. Research use only.
```

---

## 4. 图标

- **文件**：`assets/icon_512.png`
- **规格**：512 × 512 像素，PNG，圆角透明背景
- **设计说明**：深蓝渐变圆角卡片 + 白色「因」字 + 事件脉冲波纹（多源汇流意象）+ 右下角红色事件点。
- **存放位置**：
  - 仓库副本：`E:\project\ks\StockSignal\.workbuddy\skills\event_factor\assets\icon_512.png`
  - 图标存在性实测：True
- ⚠️ **发布包内不含 png**：SkillHub 拒收含二进制文件的包，图标走后台表单单独上传；
  打包器 `build/build_skills.py` 会在打包时剥离 png/jpg 等二进制。

---

## 5. 权限声明（基于代码实扫，非声称）

| 权限类别 | 行为 | 声明 |
|----------|------|------|
| 文件系统 | **只读**读取数据/历史文件 | 本 skill 自身只 `open(..., 'r')` 读取 StockSignal 仓库内的数据与历史文件；**不写、不删、不改**任何用户文件或配置。 |
| 网络 | HTTP / socket / 下载 | **本 skill 代码零网络外呼**（实扫：直接网络库命中 = 无）。调用 StockSignal 的 modules 时，其内部数据源可能访问 akshare / 东方财富等公开接口。 |
| 凭证与隐私 | 读取密钥、Token、通讯录、位置、摄像头 | **无**。仅读取环境变量 ['STOCKSIGNAL_ROOT']；不读取其他环境变量、密钥或敏感信息。 |
| 进程与代码执行 | subprocess / eval / exec / 动态导入 | **无**（实扫无命中）。只用 Python 标准库；可选 import StockSignal 的 modules。 |
| 第三方依赖 | 需额外安装的包 | **无**（本 skill 代码只用标准库；StockSignal 侧依赖 akshare/pandas 等）。 |

**实扫依据**：代码文件 ['scripts/query_event_factor.py']；扫描项 = 直接网络库 / 写文件 API / subprocess·eval·exec / 环境变量读取。

---

## 6. 使用说明（短，用于平台「使用案例」栏）

典型提问：“用事件因子看 600519”“查一下宁德时代的事件信号”“这只票有没有事件面”“事件面偏多还是偏空”。

---

## 7. 能力边界（写进产品页，不藏）

- **五个源互不替代**：某一源不可用时按兜底序降级，并在输出里标明实际用了哪个源。
- **绝不造数**：所有源取不到时返回不可用状态（`available=false` + `reason`），不填合成值、不臆造候选。
- **语音源仅本人可见**：只有调用方显式传入登录用户名才启用；隐私闸门强制不跨用户读桶。
- **宏观上下文只作展示**：`include_macro=True` 也不参与 `event_score` 计算，不改变方向判定。
- **决策链不含语音**：语音事件必须先显式入库 `data/events.csv` 走第四源进入 `event_score`，不得按用户隔离地影响全局决策与回测（守卫 `tests/test_voice_decision_boundary.py` 锁死）。

---

## 8. SkillHub 上架八步清单

1. 打包：跑 `build/build_skills.py`（自动校验 description 为 inline 引号、剥离二进制、生成 zip）。
2. 打开 https://skillhub.cn/dashboard/publish ，进入发布表单。
3. 填 slug `event-factor`、版本 `1.0.2`、名称、中英文描述（复制第 1–3 节）。
4. 上传 zip 包（**不含 png**，二进制已被剥离）。
5. 单独上传图标 `assets/icon_512.png`（512×512）。
6. 权限声明照抄第 5 节（按真实实扫写，别夸大也别漏报）。
7. 提交后平台会跑安全扫描与人工审核，状态可能为 `pending`——**如实等审核，不谎称已上架**。
8. 回写发布台账：更新本目录 `_meta.json`（slug / version / skillId / versionId / publishedAt / lastPublishStatus）。

---

## 9. 发布包清单

| 文件 | 作用 |
|------|------|
| `SKILL.md` | 技能规格与触发词（含 slug / version / description） |
| `scripts/query_event_factor.py` | 运行入口 / 引擎 |
| `assets/icon_512.png` | 图标（**不进包**，后台单独传） |

---

## 10. 发布后 Checklist

- [ ] 平台 slug 与 `_meta.json` 一致（同名迭代升版，**不新建同名**）
- [ ] 版本号已升（同名 skill 必须升版，不能覆盖同版本）
- [ ] zip 内无 png/jpg 等二进制（打包器已剥离，提交前再确认一次）
- [ ] description 为 inline 引号（**不能是 `|` / `>` 块标量**，平台拒收）
- [ ] frontmatter 结尾 `---` 独立成行
- [ ] 图标已单独上传
- [ ] 安全扫描 / 审核状态已如实记录（`pending` 就写 `pending`）
- [ ] `_meta.json` 已回写 skillId / versionId / publishedAt / lastPublishStatus
