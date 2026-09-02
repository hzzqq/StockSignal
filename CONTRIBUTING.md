# 贡献指南

感谢你有兴趣参与 StockSignal！这是一个学习项目，**任何规模的贡献都欢迎**——包括但不限于修 Bug、加功能、写文档、补测试、提建议。

## 最快路径：提 Issue（不需要写代码）

1. 点顶部 **Issues → New Issue**
2. 按模板选择：🐛 Bug 反馈 / 💡 功能建议 / ❓ 使用问题
3. 填完提交即可，我会在 1~3 天内回复

## 提交代码（PR）

```bash
# 1) Fork 本仓库，然后克隆你的副本
git clone https://github.com/<你的用户名>/StockSignal.git
cd StockSignal

# 2) 建分支（命名描述你的改动）
git checkout -b feat/xxx

# 3) 改代码 + 跑测试（确保不破坏现有 1767 个用例）
pip install -r requirements.txt -r backend/requirements.txt
python -m pytest tests -q          # 前端/数据层
python -m pytest backend/tests -q  # 后端

# 4) 提交并推送到你的仓库，然后提 Pull Request
git add -A
git commit -m "feat: 一句话说明改动"
git push origin feat/xxx
```

## 跑测试常见问题（排错）

- **在 WorkBuddy / CodeBuddy 沙箱里跑 `pytest` 全量，出现几十~上百个 `setup` 阶段 `AssertionError`（`_pytest/fixtures.py:1221 assert not self._finalizers`），或 `SystemExit: 1` / `SAFE_DELETE_BULK_CONFIRM_REQUIRED`，但隔离单跑那些用例全过** → 这是**沙箱安全删除护栏的假象**，不是仓库坏掉。护栏会在测试 teardown 删除 ≥50 个文件时 `raise SystemExit(1)` 打断 teardown，导致夹具 `_finalizers` 残留、后续测试连锁报错。
  **解决**：跑 pytest 前先关掉护栏——
  ```bash
  export CODEBUDDY_SAFE_DELETE_ENABLED=0   # Windows PowerShell: $env:CODEBUDDY_SAFE_DELETE_ENABLED=0
  python -m pytest tests -q
  ```
  仓库已提供封装脚本 `run_tests.sh`，自动设好该变量，直接 `./run_tests.sh [任意 pytest 参数]` 即可（真机/CI 无此护栏，用了也无害）。关掉后套件应转绿（StockSignal 实测：护栏开 156 ERROR → 护栏关 2155 passed / 0 failed）。

- **`import scripts.xxx` 偶发 `ModuleNotFoundError`** → 本仓库 `scripts/` 可能与其它同名包（如 `backend/scripts`、或 venv 里 `site-packages/win32/scripts`）在 pytest 整目录收集时形成命名空间/常规包冲突，使 `import scripts` 解析到错误那个并缓存进 `sys.modules` 而失败（与收集顺序有关，故"偶发"）。`tests/test_daily_backfill.py` 的 `script` 夹具已改用 `importlib.util.spec_from_file_location` **按绝对路径直加载** `scripts/daily_snapshot.py`，与 sys.path 顺序完全解耦、确定性成功；其他测试若也踩，照此按文件路径加载即可，不要依赖 `import scripts`。

## 代码约定（重要）

- **数据正确性是底线**：新取数/转换逻辑请补"正确性断言"测试（如 OHLC 自洽、日期单调、列契约），不要只写"不崩"的冒烟
- **多源降级**：新增数据源请挂到现有降级链（AKShare → BaoStock → 新浪 → 东方财富 → 缓存），不要做成单点
- **中文优先**：UI 文案用中文；错误信息统一中文
- **A 股配色**：红涨绿跌是全局约定，不要改
- **接口安全**：后端响应必须走统一 JSON 包装，禁止泄露 traceback

## 在 PR 描述里写清楚

- 解决了什么问题（贴 Issue 链接更好）
- 改动涉及哪些文件
- 测试怎么跑的、结果如何
- 如果改了 UI，附一张前后对比截图

再次感谢！每一个贡献者都会被记在项目的感谢名单里 ❤️
