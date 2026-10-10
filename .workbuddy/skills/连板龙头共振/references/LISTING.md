# 连板龙头共振 · SkillHub 上架物料单

> 目标平台：**SkillHub**（https://skillhub.cn/）  
> 个人开发者入口：https://skillhub.cn/dashboard/publish  
> 上传格式：含 `SKILL.md` 的文件夹或 zip（参照 `python-ml-1.0.0.zip` 结构）

---

## 1. 基础信息

| 字段 | 内容 | 合规检查 |
|------|------|----------|
| Slug | `lianban-longtou-gongzhen` 或 `ladder-resonance` | 仅小写字母、数字、连字符 ✓ |
| 显示名称 | 连板龙头共振 | ≤20 字 ✓ |
| 英文名 | Ladder Resonance | 备用 |
| 版本 | 1.0.0 | 语义化版本 |
| 作者 | hzzqq（黄子州） | 与开发者账号一致 |
| 分类标签 | 股票、金融、投资、量化 | 1 个主分类 + 最多 3 个二级 |

---

## 2. 技能描述（中文，100–300 字）

```text
连板龙头共振是一个股票（A股）类型的短线接力分析技能。它读取每日连板梯队分布，跨日递推各档晋级率：首板→二板、二板→三板……核心口径是「首板→二板晋级率」，被认为是接力意愿最纯粹的度量。历史样本≥10 天时输出综合晋级率与置信度；样本不足或数据缺失时明确标注 confidence=low/none、actionable=false，不编造信号、不驱动决策。支持自动读取 StockSignal 历史、手动传入今日分布、历史回填三种用法。纯本地计算、零网络、不写不删文件。
```

**字数**：约 180 字。

---

## 3. 英文描述（备用）

```text
Ladder Resonance is a Stock/A-share short-term relay analysis skill. It reads daily limit-up ladder distributions and computes cross-day promotion rates (1st→2nd board, 2nd→3rd, etc.). The key metric is the 1st→2nd board promotion rate, the purest measure of relay willingness. Outputs a composite rate and confidence when history ≥10 days; honestly abstains when data is insufficient. Supports auto-read from StockSignal, manual input, and backfill-as-of. Pure local, zero network, no file writes/deletes.
```

---

## 4. 图标

- **文件**：`assets/icon_512.png`
- **规格**：512×512 PNG，深蓝圆角卡片 + 白「板」字 + A股红色阶梯上行方块

---

## 5. 权限声明

- **文件系统**：只读 `STOCKSIGNAL_ROOT/data/shepherd_ladder_history.json` 或 `SS_LADDER_FILE` 指向文件；不写、不删、不改。
- **网络**：零网络请求。
- **凭证/隐私**：仅读取 `STOCKSIGNAL_ROOT` 与 `SS_LADDER_FILE` 两个路径变量，不读密钥。
- **进程/代码执行**：无 subprocess / eval / exec；仅 Python 标准库 + json。

---

## 6. 使用说明

1. **自动读取**：「连板龙头共振，看看今天的晋级率。」
2. **手动传入**：「连板龙头共振，今日梯队 {1:16, 2:8, 3:3, 4:1}。」
3. **历史回填**：「连板龙头共振，9 月 30 日的晋级率是多少？」

---

## 7. 能力边界

- ✅ 可信：历史≥10 天的首板→二板晋级率，可描述接力强度。
- ⚠️ 低可信：历史 2–9 天，返回 confidence=low，不 action。
- ❌ 不可信：无历史/分布缺失 → available=false。
- ❌ 不输出个股、不提供买卖点。

---

## 8. 上传文件清单

| 文件/目录 | 说明 |
|-----------|------|
| `SKILL.md` | 必填。技能主文件，含 name / description / 用法 |
| `scripts/ladder_resonance.py` | CLI 入口 |
| `lib/ladder_engine.py` | 纯标准库引擎 |
| `assets/icon_512.png` | 技能图标 |
| `references/` | 可选。可放本 LISTING.md 与 MARKETPLACE.md |

打包命令（在 skill 目录内执行）：

```bash
python -m zipfile -c build/连板龙头共振.zip SKILL.md scripts/ lib/ assets/ references/
```

或直接拖拽 skill 文件夹到 SkillHub 上传区。
