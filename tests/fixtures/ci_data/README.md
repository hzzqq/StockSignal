# CI 契约校验样本（真实归档，非合成）

## 来源与用途
- 本目录下所有 `.json` 样本均为 `data/` 目录**真实归档文件的字节级拷贝**
  （拷贝于 2026-11-15），未经任何合成、补零、改写或裁剪；入库后 Git 会按
  仓库规范统一换行（见下方「换行口径」），内容本身未改。
- 仅用于 GitHub Actions `contract-drift-live` job：全新 checkout 无行情数据时，
  把样本拷进隔离的 `data/`，让只读端点返回**真实结构**的 `status=ok` 响应，
  供 `contract-drift.test.ts` B 段用 Zod 真校验「后端 JSON ↔ 前端契约」。
- `manifest.json` 记录 `bytes`（原始归档字节数）、`bytes_lf` 与 LF 规范化
  sha256，`tests/test_ci_frontend_gate.py` 校验完整性，
  防止夹具被静默替换成编造数据。

## 换行口径（跨平台）
- 原始归档是 Windows CRLF；Git 会把它规范化成 LF 存入仓库，CI 的 Ubuntu
  checkout 工作副本就是 LF。因此完整性校验一律以
  **LF 归一化后的内容 + `bytes_lf` / `sha256_lf`** 为准；`bytes` 仅供溯源，
  跨平台不参与断言，避免 CI 因换行差异假红。
- `tests/test_ci_frontend_gate.py` 有「把样本换成 LF 版仍必须全绿」的正向断言，
  防止该跨平台口径被改回去。

## 诚实红线
- 这是**历史快照，不代表当前行情**，不得用于展示、回测结论、对外数字或生产判断。
- 不含账号、密钥、令牌或个人身份信息（拷贝前已扫描）。
- 本地开发与生产环境**绝不加载此目录**；只在 CI job 里拷入隔离 `data/`。
- 没有样本的端点仍如实返回 `status=error`；B 段会校验其诚实降级信封
  （code 非空、message 非空、data 必须为 null），绝不为了「让测试更绿」
  而伪造数据或把 error 洗成 ok。
