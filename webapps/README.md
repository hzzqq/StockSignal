# webapps/ — 网页渲染作品集

本目录收录 **AI 生成 / 手写的交互式前端小作品**（对标 [ai-demo](https://github.com/fanhuayishiy/ai-demo) 的收录模式），
由本地 Flask 后端静态托管（路由 `/webapps/<path:filename>`，见 `backend/app.py`），
Streamlit 端通过 `pages/86_网页作品集.py` 提供索引卡片与页内嵌入预览。

## 收录规则（追加式，仿 ai-demo）

1. **追加式收录**：新作品只能加在下方「作品列表」的**末位**，
   不得改动既有作品的顺序、目录与内容（要改就发新版本，见 `meta.json` 的 `version`）。
2. **一作品一目录**：每个作品一个独立子目录，入口固定为该目录下的 `index.html`。
   **单文件、自包含**——零外部 CDN 依赖（无外链 JS/CSS/字体/图片），
   保证离线（甚至断网）也能完整运行。
3. **必须附 `meta.json`**，字段固定：

   ```json
   {
     "title":   "作品标题（展示用）",
     "desc":    "一句话简介（展示用，纯文本）",
     "entry":   "index.html",
     "version": "1.0.0",
     "added":   "2026-10-31"
   }
   ```

   - `entry` 只允许相对本作品目录的相对路径（禁止 `..`、禁止绝对路径，索引页会拒绝渲染）。
   - `added` 为收录日期（ISO `YYYY-MM-DD`）。
4. **诚实红线**：涉及行情/数据的作品，数据一律为**静态示意值**，
   页面显著位置必须标注「示意数据 · 非实时行情」；不得伪造实时性。
5. **git 策略**：本目录内容**入库**（.gitignore 未忽略），clone 即含全部作品。

## 作品列表（只许末位追加）

| # | 目录 | 标题 | 版本 | 收录日期 |
|---|------|------|------|----------|
| 1 | `emotion-cycle-clock/` | 市场情绪周期时钟 | 1.0.0 | 2026-10-31 |

## 托管与访问

- 静态路由：`GET {API_BASE}/webapps/<作品目录>/<文件>`（默认 `index.html`），
  例：`http://127.0.0.1:5050/webapps/emotion-cycle-clock/index.html`。
- `backend/tests/test_webapps_static_route.py` 含防目录穿越回归
  （`../`、`..%2f` 必须被拒），改路由时必须保持全绿。
- Flask 索引页 (`pages/86_网页作品集.py`) 扫描 `webapps/*/meta.json` 生成卡片；
  扫不到任何作品或后端未启动时诚实降级提示，**不渲染假数据**。
