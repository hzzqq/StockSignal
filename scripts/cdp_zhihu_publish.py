"""CDP 接管已登录浏览器，帮老板把知乎草稿填好并发布（#R101 辅助）。

前提：浏览器以 --remote-debugging-port=9222 启动（保留默认 profile 登录态）。
用法：
  python scripts/cdp_zhihu_publish.py list                 # 列出 tabs
  python scripts/cdp_zhihu_publish.py fill <md_file>       # 向知乎编辑页填入内容
  python scripts/cdp_zhihu_publish.py publish              # 点击"发布"按钮
  python scripts/cdp_zhihu_publish.py shot <out.png>       # 截图当前 tab 验证
"""
import asyncio
import json
import sys
import urllib.request

import websockets

CDP_HTTP = "http://127.0.0.1:9222"


def _tabs():
    with urllib.request.urlopen(f"{CDP_HTTP}/json/list", timeout=3) as r:
        return json.load(r)


def _find_zhihu_tab():
    for t in _tabs():
        url = t.get("url", "")
        if "zhuanlan.zhihu.com" in url or "zhihu.com" in url:
            return t
    return None


async def _rpc(ws, method, params=None, timeout=15):
    mid = 1
    await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        if msg.get("id") == mid:
            return msg


async def _connect(tab):
    return await websockets.connect(tab["webSocketDebuggerUrl"], max_size=50 * 1024 * 1024)


async def _eval(ws, expr):
    r = await _rpc(ws, "Runtime.evaluate",
                   {"expression": expr, "returnByValue": True, "awaitPromise": True})
    return r.get("result", {}).get("result", {}).get("value")


def cmd_list():
    for t in _tabs():
        print(f"  [{t.get('type')}] {t.get('title','')[:40]} | {t.get('url','')[:80]}")


async def cmd_fill(md_file):
    tab = _find_zhihu_tab()
    if not tab:
        print("❌ 未找到知乎 tab。请先在浏览器打开知乎专栏编辑页。")
        return 1
    body = open(md_file, encoding="utf-8").read()
    ws = await _connect(tab)
    # 定位知乎富文本编辑器（contenteditable）
    editor_found = await _eval(ws, """
        (() => {
          const eds = document.querySelectorAll('[contenteditable="true"]');
          return eds.length;
        })()
    """)
    print(f"  编辑器数量: {editor_found}")
    # 注入 HTML：先聚焦编辑器，再设置 innerHTML（知乎 Draft 编辑器用 contenteditable 承载）
    esc = json.dumps(body)
    result = await _eval(ws, f"""
        (() => {{
          const eds = document.querySelectorAll('[contenteditable="true"]');
          if (!eds.length) return 'NO_EDITOR';
          const ed = eds[0];
          ed.focus();
          // 知乎编辑器基于 Draft.js：直接改 DOM 不会同步 state，改用粘贴。
          // 先尝试 document.execCommand('insertHTML')
          const ok = document.execCommand('insertHTML', false, {esc});
          return ok ? 'INSERTED' : 'EXEC_FAIL';
        }})()
    """)
    print(f"  注入结果: {result}")
    # 注：知乎新版编辑器可能需要先清空已有占位内容再插入；execCommand 失败时用户手动 Ctrl+V
    await ws.close()
    return 0


async def cmd_publish():
    tab = _find_zhihu_tab()
    if not tab:
        print("❌ 未找到知乎 tab")
        return 1
    ws = await _connect(tab)
    btns = await _eval(ws, """
        (() => {
          const out = [];
          document.querySelectorAll('button').forEach(b => {
            const t = (b.innerText || '').trim();
            if (t.includes('发布') || t.includes('保存')) out.push(t);
          });
          return out;
        })()
    """)
    print(f"  找到按钮: {btns}")
    if not btns:
        print("  ⚠️ 未找到发布按钮")
        await ws.close()
        return 1
    clicked = await _eval(ws, """
        (() => {
          const btns = [...document.querySelectorAll('button')];
          const b = btns.find(x => (x.innerText||'').trim().includes('发布'));
          if (b) { b.click(); return 'CLICKED'; }
          return 'NOT_FOUND';
        })()
    """)
    print(f"  发布点击: {clicked}")
    await asyncio.sleep(2)
    await ws.close()
    return 0


async def cmd_shot(out):
    tab = _find_zhihu_tab()
    if not tab:
        print("❌ 未找到知乎 tab")
        return 1
    ws = await _connect(tab)
    r = await _rpc(ws, "Page.captureScreenshot", {"format": "png"})
    data = r.get("result", {}).get("data")
    if data:
        import base64
        open(out, "wb").write(base64.b64decode(data))
        print(f"  ✓ 截图: {out}")
    else:
        print("  ⚠️ 截图失败")
    await ws.close()
    return 0


async def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    op = argv[0]
    if op == "list":
        cmd_list()
        return 0
    if op == "fill":
        return await cmd_fill(argv[1])
    if op == "publish":
        return await cmd_publish()
    if op == "shot":
        return await cmd_shot(argv[1])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
