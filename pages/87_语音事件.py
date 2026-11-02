"""
页面87：语音事件因子（2026-11-02 从 23_事件追踪.py 抽离为独立导航页）。

把「语音」这一输入通道独立成可达入口（此前仅藏于 23 页底部，可发现性弱）。
录音/上传 → ASR 转写 → 结构化因子标注（事件性质 / 时间敏感度 / 情绪倾向）。
复用 modules.voice_event.render_voice_event_block，与 23 页共享会话内 ve_history。

红线：未配置 key / 端点不支持 audio / 转写失败 → 诚实降级，绝不编造转写或结论。
"""
from modules.page_utils import render_standard_page
from modules.voice_event import render_voice_event_block

render_standard_page(
    title='语音事件',
    icon='🎙️',
    caption='⚠️ 数据仅供参考，不构成投资建议',
    layout='wide',
)

render_voice_event_block()
