# 宏观数据 · SkillHub 上架物料单（Submission Package）

> 目标平台：**SkillHub**（https://skillhub.cn/）——面向中国用户的 AI Skills 社区，
> 个人开发者真实入口：https://skillhub.cn/dashboard/publish

---

## 1. 基础信息（复制到平台表单）

| 字段 | 内容 | 合规检查 |
|------|------|----------|
| 技能名称 | 宏观数据 | ≤20 字 ✓（4 字） |
| 英文名 | 宏观数据·全球风险评分 | 备用 |
| slug | `macro-data` | 小写字母/数字/连字符 |
| 版本 | 1.1.0 | 语义化版本 |
| 作者 | hzzqq（黄子州） | 与你的开发者账号一致 |
| 分类标签 | 股票、金融、投资、宏观、量化 | 3–5 个，覆盖搜索场景 |
| 适用平台 | WorkBuddy / 支持 SkillHub 规范的 AI Agent | |

---

## 2. 技能描述（中文，100–300 字）

```text
宏观数据是一个股票（A股）类型的宏观指标取数技能。它调用 StockSignal 的 modules.macro_data，覆盖国内 6 项（PMI/CPI/PPI/GDP/M2/LPR）与全球 12 项（美国 ISM PMI/非农/失业率/CPI/PPI/GDP、美债 10Y、美元兑人民币、美元指数 DXY、标普500/纳斯达克/恒生），按可解释规则合成 0-100 全球宏观风险偏好评分，并给出各指标贡献明细与趋势。每一个数值都带真实数据日期；取不到即返回 None 与不可用原因，绝不用插值或估算值填充缺失项。输出为研究参考，不构成投资建议。
```

**字数**：约 275 字。

---

## 3. 英文描述（平台双语备用）

```text
Macro Data is a stock/A-share macro indicator skill. It calls StockSignal's modules.macro_data, covering 6 domestic indicators (PMI/CPI/PPI/GDP/M2/LPR) and 12 global ones (US ISM PMI, non-farm payrolls, unemployment, CPI, PPI, GDP, UST 10Y, USD/CNY, DXY, S&P 500, Nasdaq, Hang Seng), and combines them via an explainable rule into a 0-100 global macro risk-appetite score with per-indicator contributions and trends. Every value carries its real data date; missing items return None with a reason and are never filled by interpolation. Research use only.
```

---

## 4. 图标

- **文件**：`assets/icon_512.png`
- **规格**：512 × 512 像素，PNG，圆角透明背景
- **设计说明**：深蓝渐变圆角卡片 + 白色「宏」字 + 地球经纬线 + 上升柱状（全球风险偏好意象）。
- **存放位置**：
  - 仓库副本：`E:\project\ks\StockSignal\.workbuddy\skills\macro_data\assets\icon_512.png`
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

**实扫依据**：代码文件 ['scripts/query_macro.py']；扫描项 = 直接网络库 / 写文件 API / subprocess·eval·exec / 环境变量读取。

---

## 6. 使用说明（短，用于平台「使用案例」栏）

典型提问：“现在宏观环境怎么样”“美债收益率多少”“美元指数涨了没”“国内 CPI 是多少”“全球风险偏好多少分”。

---

## 7. 能力边界（写进产品页，不藏）

- **取不到返回 None**：缺失指标返回 None 并带原因，绝不插值、绝不估算、绝不填合成值。
- **每个数值带真实数据日**：输出里的每个指标都附 `date`（该指标的真实数据日），不是今天。
- **规则可解释**：评分由公开的阈值规则合成，各指标贡献可逐项展开（不声称预测能力）。
- **评分是描述性**：0-100 全球风险偏好读数，不是买卖信号，不声称预测指数涨跌。

---

## 8. SkillHub 上架八步清单

1. 打包：跑 `build/build_skills.py`（自动校验 description 为 inline 引号、剥离二进制、生成 zip）。
2. 打开 https://skillhub.cn/dashboard/publish ，进入发布表单。
3. 填 slug `macro-data`、版本 `1.1.0`、名称、中英文描述（复制第 1–3 节）。
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
| `scripts/query_macro.py` | 运行入口 / 引擎 |
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
