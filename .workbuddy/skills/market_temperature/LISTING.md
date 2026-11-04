# 市场情绪温度计 · SkillHub 上架物料单（Submission Package）

> 目标平台：**SkillHub**（https://skillhub.cn/）——面向中国用户的 AI Skills 社区，
> 个人开发者真实入口：https://skillhub.cn/dashboard/publish

---

## 1. 基础信息（复制到平台表单）

| 字段 | 内容 | 合规检查 |
|------|------|----------|
| 技能名称 | 市场情绪温度计 | ≤20 字 ✓（7 字） |
| 英文名 | 市场情绪温度计·A股温度 | 备用 |
| slug | `market-temperature` | 小写字母/数字/连字符 |
| 版本 | 1.0.0 | 语义化版本 |
| 作者 | hzzqq（黄子州） | 与你的开发者账号一致 |
| 分类标签 | 股票、金融、投资、量化、情绪 | 3–5 个，覆盖搜索场景 |
| 适用平台 | WorkBuddy / 支持 SkillHub 规范的 AI Agent | |

---

## 2. 技能描述（中文，100–300 字）

```text
市场情绪温度计是一个股票（A股）类型的市场情绪读数技能。它调用 StockSignal 的 modules.market_temperature，把牧羊人 8 项广度指标用经验分位合成 0-100 综合温度，给出冰点/偏冷/中性/活跃/狂热五档分档与操作建议、各指标贡献明细、极端区信号（全历史仅「极端恐慌→次日红盘」一条有统计依据，其余诚实弃权），以及全历史广度向量最近相似日。与「猜明天涨跌」不同，温度是描述性读数：说现在冷热，不说明天涨跌。取不到数据即返回不可用状态，绝不编造温度值。输出为研究参考，不构成投资建议。
```

**字数**：约 261 字。

---

## 3. 英文描述（平台双语备用）

```text
Market Temperature is a stock/A-share market sentiment readout skill. It calls StockSignal's modules.market_temperature to combine 8 breadth indicators into a 0-100 composite temperature via empirical percentile scoring, then reports the five bands (ice-cold / cool / neutral / active / frenzied) with advice, per-indicator contributions, the extreme-zone signal (only 'panic washout -> next-day rebound' has statistical backing; everything else honestly abstains), and the most similar historical days. Unlike 'guess tomorrow's move', temperature is descriptive: how cold or hot now, not a forecast. Unavailable data returns an explicit unavailable state; values are never fabricated. Research use only.
```

---

## 4. 图标

- **文件**：`assets/icon_512.png`
- **规格**：512 × 512 像素，PNG，圆角透明背景
- **设计说明**：深蓝渐变圆角卡片 + 蓝→红渐变温度计液柱 + 白色「温」字 + 右下角红字「红=热」。
- **存放位置**：
  - 仓库副本：`E:\project\ks\StockSignal\.workbuddy\skills\market_temperature\assets\icon_512.png`
  - 图标存在性实测：True
- ⚠️ **发布包内不含 png**：SkillHub 拒收含二进制文件的包，图标走后台表单单独上传；
  打包器 `build/build_skills.py` 会在打包时剥离 png/jpg 等二进制。

---

## 5. 权限声明（基于代码实扫，非声称）

| 权限类别 | 行为 | 声明 |
|----------|------|------|
| 文件系统 | **只读**读取数据/历史文件 | 本 skill 自身只 `open(..., 'r')` 读取 StockSignal 仓库内的数据与历史文件；**不写、不删、不改**任何用户文件或配置。 |
| 网络 | HTTP / socket / 下载 | **本 skill 代码零网络外呼**（实扫：直接网络库命中 = 无）。调用 StockSignal 的 modules 时，其内部数据源可能访问 akshare / 东方财富等公开接口。 |
| 凭证与隐私 | 读取密钥、Token、通讯录、位置、摄像头 | **无**。仅读取环境变量 （无）；不读取其他环境变量、密钥或敏感信息。 |
| 进程与代码执行 | subprocess / eval / exec / 动态导入 | **无**（实扫无命中）。只用 Python 标准库；可选 import StockSignal 的 modules。 |
| 第三方依赖 | 需额外安装的包 | **无**（本 skill 代码只用标准库；StockSignal 侧依赖 akshare/pandas 等）。 |

**实扫依据**：代码文件 ['lib/temperature_engine.py', 'scripts/query_temperature.py']；扫描项 = 直接网络库 / 写文件 API / subprocess·eval·exec / 环境变量读取。

---

## 6. 使用说明（短，用于平台「使用案例」栏）

典型提问：“今天市场温度多少”“现在情绪是冷是热”“市场热不热”“今天该防守还是进攻”“温度到极值了吗”。

---

## 7. 能力边界（写进产品页，不藏）

- **温度是描述性指标，不声称预测能力**。它回答「现在市场冷不冷」，不回答「明天涨不涨」。
- **五档阈值与 StockSignal 完全一致**：引擎优先调用 `modules.market_temperature`（单一真理源），读不到才用内置镜像并标 `degraded=true`。
- **极端区只有一条可发布规律**：「极端恐慌 → 次日红盘」（全历史 296 天 z=+4.36）。其余时刻**明确弃权**，不硬猜方向。
- **相似日是描述不是预测**：历史相似 ≠ 明天必然如此，引擎不含任何前视泄漏。
- **取不到数据返回不可用**：各数据源不可用时返回 `available=false` + `reason`，绝不编造温度值。

---

## 8. SkillHub 上架八步清单

1. 打包：跑 `build/build_skills.py`（自动校验 description 为 inline 引号、剥离二进制、生成 zip）。
2. 打开 https://skillhub.cn/dashboard/publish ，进入发布表单。
3. 填 slug `market-temperature`、版本 `1.0.0`、名称、中英文描述（复制第 1–3 节）。
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
| `lib/temperature_engine.py` | 运行入口 / 引擎 |
| `scripts/query_temperature.py` | 运行入口 / 引擎 |
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
