"""
tests/test_xc_sessions_guard.py — T-311 星辰AI 多会话接线守卫（离线，不 import 页面模块）

钉住五条接线，防回潮（对应 mutation 注入点，删除接线 → 对应断言变红）：
1. 保存收口：有 xc_conv_id → 走会话端点；无 → 仅真实内容才懒建（浏览不建空会话）；
   旧后端 404 → xc_legacy_mode 回退单记录模式（行为不变）；保存失败诚实 toast。
2. restore：优先会话列表、记录 xc_conv_id、旧历史自愈导入「历史对话」。
3. 会话 UI：🗂️ 会话管理 expander + 任务进行中 disabled（防结果串会话）
   + 删除两步确认 + 切换按钮。
4. 后端端点：chat_routes 5 端点齐全，读写端点全部带 user_id 归属过滤（越权 404）。
5. 客户端：background_tasks 5 函数对接 /api/chat/conversations*，含旧后端 404 探测。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "53_星辰AI.py"
BGT = ROOT / "modules" / "background_tasks.py"
ROUTES = ROOT / "backend" / "api" / "chat_routes.py"
MODELS = ROOT / "backend" / "models.py"
MIGRATE = ROOT / "backend" / "scripts" / "migrate_add_chat_conversations.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_save_path_wiring():
    src = _src(PAGE)
    assert 'st.session_state.get("xc_conv_id")' in src, "未接线当前会话 ID"
    assert "save_chat_conversation_messages(cid, messages)" in src, \
        "有会话 ID 时未走会话端点（落库链断裂）"
    assert 'if not real:\n        return' in src, \
        "懒建守卫缺失（仅浏览页面会误建空会话）"
    assert 'create_chat_conversation(first_user[:24] or "新对话")' in src, \
        "懒建会话缺失（首条真实消息时创建）"
    assert 'st.session_state.get("xc_legacy_mode")' in src, "旧后端回退模式缺失"
    assert "save_chat_history(messages)" in src, "回退模式未保留旧单记录路径"
    assert "对话保存失败" in src, "保存失败缺少诚实 toast"


def test_restore_wiring():
    src = _src(PAGE)
    assert "convs, _available = list_chat_conversations()" in src, "restore 未取会话列表"
    assert 'xc_conv_id"] = top.get("id")' in src, "restore 未记录当前会话 ID"
    assert 'create_chat_conversation("历史对话")' in src, "旧历史自愈导入缺失"
    assert "_load_conversation_into_state" in src, "会话载入助手缺失"


def test_session_ui_wiring():
    src = _src(PAGE)
    assert 'st.expander("🗂️ 会话管理", expanded=False)' in src, "会话管理入口缺失"
    assert "disabled=_busy" in src, \
        "任务进行中未禁用会话切换/新建/删除（防结果串会话）"
    assert "xc_conv_del_confirm" in src, "删除当前会话缺少两步确认"
    assert "xc_conv_go_" in src, "会话切换按钮缺失"
    assert "xc_conv_new" in src, "新建对话按钮缺失"


def test_backend_endpoints():
    src = _src(ROUTES)
    for deco in ('@bp.get("/conversations")', '@bp.post("/conversations")',
                 '@bp.get("/conversations/<int:cid>")',
                 '@bp.post("/conversations/<int:cid>")',
                 '@bp.delete("/conversations/<int:cid>")'):
        assert deco in src, f"缺少端点 {deco}"
    # 归属过滤：get/save/delete 三个 <cid> 读写端点全部按 user_id 联合过滤（越权 404）
    assert src.count("filter_by(id=cid, user_id=g.current_user.id)") == 3, \
        "<cid> 端点归属过滤不完整（越权风险）"
    models = _src(MODELS)
    assert "class ChatConversation" in models, "会话模型缺失"
    assert '__tablename__ = "chat_conversations"' in models, "会话表名缺失"


def test_client_functions():
    src = _src(BGT)
    for fn in ("def list_chat_conversations", "def create_chat_conversation",
               "def get_chat_conversation_messages", "def save_chat_conversation_messages",
               "def delete_chat_conversation"):
        assert fn in src, f"缺少客户端函数 {fn}"
    assert src.count("/api/chat/conversations") >= 5, "客户端未对接会话端点"
    assert "status_code == 404" in src, "旧后端 404 探测缺失（回退模式依赖）"


def test_migrate_script():
    src = _src(MIGRATE)
    assert "def migrate(app)" in src, "迁移入口缺失"
    assert "target_names.issubset(existing_before)" in src, "迁移幂等守卫缺失"
    assert 'title="历史对话"' in src, "旧历史一次性导入缺失"


def test_sources_parse():
    """五文件 AST 可解析（防止半成品落盘）。"""
    for p in (PAGE, BGT, ROUTES, MODELS, MIGRATE):
        ast.parse(_src(p), filename=str(p))
