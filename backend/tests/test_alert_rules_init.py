"""守卫测试：告警规则文件缺失时 load_rules() 用 DEFAULT_RULES 初始化落盘（缺陷3 回归守卫）。

缺陷背景：
- data/alert_rules.json 与 alerts.log 均不存在，唯一写方是 v1 Streamlit 页面手动保存；
- load_rules() 原实现只读不初始化 → 后端/自动化消费方拿到的是「内存默认值」，
  文件永不落盘，规则改动无从审计。

守卫内容（tmp_path 注入路径，零真实数据污染）：
1. 文件缺失 → 落盘 DEFAULT_RULES 且返回默认规则；
2. 二次加载 → 从落盘文件读回，内容一致；
3. 文件存在但损坏 → 不覆盖用户文件，如实降级返回默认规则；
4. 落盘失败（路径非法）→ 不抛异常，仍返回默认规则。
"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys  # noqa: E402

sys.path.insert(0, REPO)

from modules.alert_rules import DEFAULT_RULES, load_rules  # noqa: E402


def test_missing_file_initialized_from_defaults(tmp_path):
    p = str(tmp_path / "alert_rules.json")
    rules = load_rules(p)
    assert rules == DEFAULT_RULES
    assert os.path.exists(p), "文件缺失时 load_rules 应把默认规则落盘"
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    assert data == {"rules": DEFAULT_RULES}


def test_second_load_reads_from_disk(tmp_path):
    p = str(tmp_path / "alert_rules.json")
    first = load_rules(p)
    second = load_rules(p)
    assert second == first == DEFAULT_RULES


def test_corrupt_file_not_overwritten(tmp_path):
    p = str(tmp_path / "alert_rules.json")
    with open(p, "w", encoding="utf-8") as f:
        f.write("{broken json!!")
    rules = load_rules(p)
    assert rules == DEFAULT_RULES, "损坏文件应降级返回默认规则"
    with open(p, encoding="utf-8") as f:
        assert f.read() == "{broken json!!", "损坏文件不得被覆盖（用户数据保护）"


def test_write_failure_still_returns_defaults(tmp_path):
    # 把规则文件路径指到一个「父级是文件」的非法路径 → makedirs 失败 → 落盘失败
    blocker = tmp_path / "f.txt"
    blocker.write_text("x", encoding="utf-8")
    p = str(blocker / "rules.json")
    rules = load_rules(p)
    assert rules == DEFAULT_RULES, "落盘失败不得影响返回默认值"
