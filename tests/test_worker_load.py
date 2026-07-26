"""针对 worker.py 中 _parse_task_status 的纯逻辑单元测试（不涉及磁盘/网络）。"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.tasks.worker import TaskStatus, _parse_task_status


def test_valid_pending():
    assert _parse_task_status("pending") == TaskStatus.PENDING


def test_valid_running():
    assert _parse_task_status("running") == TaskStatus.RUNNING


def test_garbage_status_falls_back_no_raise():
    assert _parse_task_status("garbage_status") == TaskStatus.ERROR


def test_none_falls_back_no_raise():
    assert _parse_task_status(None) == TaskStatus.ERROR


def test_empty_string_falls_back_no_raise():
    assert _parse_task_status("") == TaskStatus.ERROR


def test_non_string_falls_back_no_raise():
    assert _parse_task_status(123) == TaskStatus.ERROR
