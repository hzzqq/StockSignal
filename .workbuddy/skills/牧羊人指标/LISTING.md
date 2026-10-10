# 牧羊人指标 · SkillHub 上架物料单（Submission Package）

> 目标平台：**SkillHub**（https://skillhub.cn/）——面向中国用户的 AI Skills 社区，
> 个人开发者真实入口：https://skillhub.cn/dashboard/publish

---

## 1. 基础信息（复制到平台表单）

| 字段 | 内容 | 合规检查 |
|------|------|----------|
| 技能名称 | 牧羊人指标 | ≤20 字 ✓（4 字） |
| 英文名 | Shepherd Indicator | 备用 |
| 版本 | 1.0.0 | 语义化版本 |
| 作者 | hzzqq（黄子州） | 与你开发者账号一致 |
| 分类标签 | 股票、金融、投资、量化 | 3–4 个，覆盖搜索场景 |
| 适用平台 | WorkBuddy / 支持 SkillHub 规范的 AI Agent | |

---

## 2. 技能描述（中文，100–300 字）

```text
牧羊人指标是一个股票（A股）类型的情绪指标技能。它读取当日 A 股涨跌停广度数据，基于 2007–2026 全历史 walk-forward 校准，判断次日行情方向。与多数「情绪判明天」工具不同，本技能只在「极端恐慌」这一条被严格验证的规律上表态：当跌停占比冲到历史前 10% 时，次日红盘概率达 62.5%（基准 49.8%，z=+4.36，296 天样本）；其余日子一律诚实弃权，绝不臆造偏多/偏空。支持手动输入、自动读取 StockSignal 当日快照、查看校准证据链三种用法。纯本地计算、零网络外呼、不读密钥、不写不删用户文件。
```

**字数**：约 200 字，符合 100–300 字要求。

---

## 3. 英文描述（平台双语备用）

```text
Shepherd Indicator is a Stock/A-share sentiment skill. It reads today's A-share breadth (advancers/decliners, limit-up/limit-down counts) and, based on a 2007–2026 walk-forward calibration, judges next-day direction. Unlike most sentiment tools, it only commits to one validated rule: on extreme panic (limit-down ratio in the historical top 10%), next-day up probability is 62.5% vs a 49.8% baseline (z=+4.36, 296 days); otherwise it honestly abstains. Supports manual input, auto-read from StockSignal daily snapshot, and calibration evidence view. Pure local compute, zero network calls, no secret access, no file writes or deletes.
```

---

## 4. 图标

- **文件**：`assets/icon_512.png`
- **规格**：512 × 512 像素，PNG，圆角透明背景
- **设计说明**：深蓝渐变圆角卡片 + 白色「羊」字（牧羊人意象）+ A股红色上行反弹箭头（红=涨）+ 左下角灰色「恐慌起点」小点。
- **存放位置**：
  - 仓库副本：`E:/project/ks/StockSignal/.workbuddy/skills/牧羊人指标/assets/icon_512.png`
  - 发布包目录：`E:/project/ks/StockSignal/build/牧羊人指标.skill.json`

---

## 5. 权限声明（基于 skill-safe-install 安全审计：P0=0，P1=2）

| 权限类别 | 行为 | 声明 |
|----------|------|------|
| 文件系统 | **只读**读取校准数据文件 | 读取路径：`STOCKSIGNAL_ROOT/data/sentiment_edge_calibration.json`、`STOCKSIGNAL_ROOT/reports/sentiment_edge_calibration.json`、`SS_SENTIMENT_EDGE_PATH` 指向的自定义路径、本 skill 自带 `assets/sentiment_edge_calibration.json`。 |
| 文件系统 | 写入 / 删除 | **无**。不写用户文件、不删除文件、不修改配置。 |
| 网络 | HTTP / socket / 下载 | **无**。零网络外呼（代码中无 requests / urllib / socket）。 |
| 凭证与隐私 | 读取密钥、Token、通讯录、位置、摄像头 | **无**。仅读取两个路径环境变量 `STOCKSIGNAL_ROOT` 与 `SS_SENTIMENT_EDGE_PATH`；不读取其他环境变量或敏感信息。 |
| 进程与代码执行 | subprocess / eval / exec / 动态导入 | **无**。仅使用 Python 标准库（json / os / statistics）；可选 import StockSignal 的 `modules.sentiment_edge`，缺失时安全回退自带引擎。 |

---

## 6. 使用说明（短，用于平台「使用案例」栏）

1. **手动输入今日广度**  
   在 Agent 对话中说：「用牧羊人指标判断明天行情，今日上涨 2000 家、下跌 2900 家、跌停 50 家、触及跌停 80 家。」

2. **自动读取 StockSignal 快照**  
   安装后说：「牧羊人指标，自动判断明天行情。」Skill 会读取 `data/daily_snapshot.json` 或最新 `data/snapshots/YYYY-MM-DD.json`。

3. **查看校准证据链**  
   说：「牧羊人指标，看看校准证据。」返回 2007–2026 walk-forward 统计结果：极端恐慌阈值、触发天数、次日红盘率、z 值、能力边界。

---

## 7. 能力边界（写进产品页，不藏）

- ✅ **可信**：极端恐慌（跌停占比历史前 10%）→ 次日红盘概率显著高于基准（62.5% vs 49.8%，z=+4.36，296 天样本）。
- ✅ **弱可信**：触及跌停占比与次日波动幅度弱正相关（IC≈0.13~0.16）→ 仅作风险提示。
- ❌ **不可信**：普通日子的次日方向（现有引擎无法超越基准率，本技能不硬猜）。

---

## 8. SkillHub 上架八步清单

| 步骤 | 动作 | 状态 |
|------|------|------|
| 1 | 访问 https://skillhub.cn/dashboard/publish，注册/登录账号 | 待你做 |
| 2 | 完成 **个人实名认证**（腾讯云人脸核身） | 待你做 |
| 3 | 点击「发布个人 Skill」，选择发布方式（网页/CLI/Agent） | 待你做 |
| 4 | 填写基础信息：名称、描述、英文名、分类标签、版本、作者 | 本单已备齐 |
| 5 | 上传图标 `icon_512.png` | 已生成 |
| 6 | 粘贴权限声明与使用说明 | 本单已备齐 |
| 7 | 上传技能包：拖拽 skill 文件夹或 `build/牧羊人指标.zip` 到 SkillHub 上传区 | 上传包已备好：`build/牧羊人指标.zip`（含 SKILL.md + scripts/ + lib/ + assets/ + references/） |
| 8 | 提交审核，等待 SkillHub **三线安全审核**（内容合规 + 科恩实验室漏洞扫描 + 云鼎实验室 AI 模型安全评估） | 待你做；通过后自动上架 |

**审核周期**：通常 1–3 个工作日（SkillHub 首页写「100% 强制安全准入」）。

---

## 9. 发布包清单

| 文件 | 路径 | 说明 |
|------|------|------|
| SKILL.md | `.workbuddy/skills/牧羊人指标/SKILL.md` | 技能主文件，含 name / description / 触发词 / 用法 |
| 主脚本 | `scripts/next_day_edge.py` | CLI 入口：--today / --auto / --summary |
| 兜底引擎 | `lib/edge_engine.py` | 无第三方依赖，可独立运行 |
| 校准件 | `assets/sentiment_edge_calibration.json` | 冻结 walk-forward 校准结果 |
| 图标 | `assets/icon_512.png` | 512×512 PNG |
| SkillHub 上传包 | `build/牧羊人指标.zip` | 参照 `python-ml-1.0.0.zip` 结构：SKILL.md + scripts/ + lib/ + assets/ + references/ |
| WorkBuddy 本地包 | `build/牧羊人指标.skill.json` | workbuddy-skill-package/1.0 格式，本地安装/验证用 |
| 市场简介 | `MARKETPLACE.md` | 中英双语市场文案 |
| 上架物料单 | `LISTING.md` | 即本文件，可直接复制到平台表单 |

---

## 10. 发布后 Checklist

- [ ] 自己完整走一遍「安装 → 触发关键词 → 收到信号」验证可用。
- [ ] 记录版本号 `1.0.0` 与发布日期。
- [ ] 监控用户反馈，把高频问题回写进 `SKILL.md` / `LISTING.md` 再发 `1.0.1`。

---

*备注：WorkBuddy 客户端内没有「一键发布到市场」按钮；公开市场 listing 必须走 SkillHub 网页流程。本单已把所需文字、图标、发布包全部备好，你可直接复制粘贴提交。*
