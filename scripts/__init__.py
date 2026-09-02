"""scripts 包：项目级命令行脚本集合（收盘快照、历史回填、回测打分等）。

显式声明为常规包（而非命名空间包），避免与 venv 中 pywin32 自带的
`site-packages/win32/scripts` 形成多 portion 命名空间、在 pytest 整目录收集时
出现「import scripts.daily_snapshot 偶发 ModuleNotFoundError」的解析不稳定。
（modules/ 同为常规包，已长期稳定；scripts/ 对齐之。）
"""
