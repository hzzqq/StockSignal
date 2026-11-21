"""数据导出 v2 后端化验收测试（纯函数 + 端点）。

测试夹具说明：
  * 所有数据集均为**合成确定性夹具，非真实行情**，数据源全部通过参数注入 /
    monkeypatch，零联网、零真实数据源依赖；
  * 端点层用真 Flask test_client + 独立 SQLite（E:/tmp/ss_probe_d/app.db）+ 真 JWT；
  * 验收点：zip PK magic、xlsx 可被 openpyxl 读回、pdf 头 %PDF、json NaN→None、
    全源失败诚实降级 available=false、非法参数 422、无 token 401。
"""
from __future__ import annotations

import io
import os
import sys
import zipfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
for _p in (PROJECT_ROOT, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import User  # noqa: E402
from modules import export_bundle as eb  # noqa: E402
from modules import research_report as rrp  # noqa: E402


# ── 合成数据集夹具（非真实行情）──
def _fixture_datasets() -> dict:
    return {
        "行业板块资金流向.csv": pd.DataFrame({
            "板块": ["银行", "证券"],
            "主力净流入": [1.5, float("nan")],
        }),
        "大盘主力净流入30日.csv": pd.DataFrame({
            "日期": ["2026-01-01", "2026-01-02"],
            "主力净流入": [100.0, 200.0],
        }),
    }


FIXTURE_SKIPPED = ["北向资金_板块.csv", "北向资金_汇总.csv"]


# ───────────── 1. 纯函数层（不起 client）─────────────
def test_sheet_name_rules():
    assert eb.sheet_name("行业板块资金流向.csv") == "行业板块资金流向"
    # 非法字符逐个替换为 -（与 v1 行为一致，[ 与 ] 各得一个 -）+ 截断到 31 字符
    assert eb.sheet_name("a/b\\c[d]:e*f?g.csv") == "a-b-c-d--e-f-g"
    long = "很" * 40
    assert len(eb.sheet_name(long)) == 31


def test_to_csv_zip_magic_and_manifest():
    zbytes = eb.to_csv_zip(_fixture_datasets(), FIXTURE_SKIPPED)
    assert zbytes[:4] == b"PK\x03\x04", zbytes[:4]
    zf = zipfile.ZipFile(io.BytesIO(zbytes))
    names = zf.namelist()
    assert "行业板块资金流向.csv" in names and "大盘主力净流入30日.csv" in names
    assert "manifest.csv" in names
    # CSV 内容 utf-8-sig（带 BOM）
    raw = zf.read("行业板块资金流向.csv")
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "银行".encode("utf-8") in raw
    # manifest 含 skipped 说明
    manifest = zf.read("manifest.csv").decode("utf-8-sig")
    assert "北向资金_板块.csv" in manifest and "已跳过" in manifest
    assert "行业板块资金流向.csv" in manifest and "已包含" in manifest


def test_to_excel_roundtrip():
    import openpyxl

    xbytes = eb.to_excel(_fixture_datasets())
    assert xbytes[:2] == b"PK", xbytes[:2]  # xlsx 本质是 zip 容器
    wb = openpyxl.load_workbook(io.BytesIO(xbytes))
    assert wb.sheetnames == ["行业板块资金流向", "大盘主力净流入30日"], wb.sheetnames
    ws = wb["行业板块资金流向"]
    assert ws["A1"].value == "板块" and ws["A2"].value == "银行"
    # 冻结表头
    assert ws.freeze_panes == "A2"


def test_to_excel_skips_empty_and_invalid():
    datasets = _fixture_datasets()
    datasets["空数据集.csv"] = pd.DataFrame()
    datasets["坏数据集.csv"] = None
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(eb.to_excel(datasets)))
    assert wb.sheetnames == ["行业板块资金流向", "大盘主力净流入30日"], wb.sheetnames


def test_to_pdf_magic():
    pbytes = eb.to_pdf(_fixture_datasets(), FIXTURE_SKIPPED, "20260331", "600519")
    assert pbytes[:5] == b"%PDF-", pbytes[:5]


def test_datasets_to_json_nan_to_none():
    out = eb.datasets_to_json(_fixture_datasets(), FIXTURE_SKIPPED)
    assert set(out) == {"datasets", "skipped"}
    rows = out["datasets"]["行业板块资金流向.csv"]
    assert rows[0]["主力净流入"] == 1.5
    assert rows[1]["主力净流入"] is None  # NaN → None，不出现 "NaN"/nan 字面量
    assert out["skipped"] == FIXTURE_SKIPPED
    # 整体可 JSON 序列化且不含 NaN 字面量
    import json

    text = json.dumps(out, ensure_ascii=False)
    assert "NaN" not in text


def test_assemble_datasets_best_effort_with_injected_sources():
    good = pd.DataFrame({"x": [1, 2]})

    def ok_src():
        return {"好的.csv": good}

    def empty_src():
        return {"空的.csv": pd.DataFrame()}

    def boom():
        raise RuntimeError("源接口不可用")

    datasets, skipped = eb.assemble_datasets(
        "20260331", "600519",
        sources=[(["好的.csv"], ok_src),
                 (["空的.csv"], empty_src),
                 (["炸的.csv"], boom)],
    )
    assert list(datasets) == ["好的.csv"], datasets
    assert skipped == ["空的.csv", "炸的.csv"], skipped


def test_build_default_sources_pre_skipped_without_fetch():
    # 缺 code / period 非法 / 无自选股查询通道 → 前置跳过，不发起任何取数
    sources, pre = eb.build_default_sources("", "", watchlist_codes=None)
    assert "个股主力资金.csv" in pre and "业绩报表.csv" in pre
    assert "自选股实时快照.csv" in pre
    # 合法条件时不进 pre_skipped（数据集名参数化）
    sources, pre = eb.build_default_sources("20260331", "600519", watchlist_codes=lambda: [])
    assert pre == [], pre
    names = [n for names_, _ in sources for n in names_]
    assert "个股主力资金_600519.csv" in names and "业绩报表_20260331.csv" in names


def test_collect_report_data_injected_sources_offline():
    # 全部注入 + 全部成功
    data, name = eb.collect_report_data(
        "600519", fetcher=None,
        name_fn=lambda: "贵州茅台",
        daily_fn=lambda: None,  # 不走清洗/技术分析
        fundamentals_fn=lambda: {"pe": 1.0},
        fundflow_fn=lambda: {"main_net": 1.0, "source": "夹具"},
        risk_fn=lambda: ({"dims": {}}, ["公告A"]),
    )
    assert name == "贵州茅台"
    assert data["fundamentals"] == {"pe": 1.0}
    assert data["fundflow"]["source"] == "夹具"
    assert data["risk_report"] == {"dims": {}}
    assert data["announcements"] == ["公告A"]

    # 全部注入 + 全部失败：data 为空、name 回退为 code，绝不编造
    def boom():
        raise RuntimeError("boom")

    data, name = eb.collect_report_data(
        "600519", fetcher=None,
        name_fn=boom, daily_fn=boom, fundamentals_fn=boom,
        fundflow_fn=boom, risk_fn=boom,
    )
    assert data == {} and name == "600519"


# ───────────── 2. 端点（真 Flask test_client + 临时 SQLite + JWT）─────────────
@pytest.fixture
def app(monkeypatch):
    os.makedirs("E:/tmp/ss_probe_d", exist_ok=True)
    db_uri = "sqlite:///E:/tmp/ss_probe_d/app.db"
    monkeypatch.setenv("DATABASE_URL", db_uri)

    class _TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = db_uri
        RATE_LIMIT_ENABLED = False
        TESTING = True
        JWT_EXPIRES_SECONDS = 3600

    application = create_app(_TestConfig)
    # team-lead 会在 backend/app.py 统一注册本 blueprint；此处条件注册保证测试在当前
    # worktree（app.py 尚未改）也能跑，且未来 app.py 注册后不会重复注册。
    from backend.api.export_routes import bp as export_bp

    if "export" not in application.blueprints:
        application.register_blueprint(export_bp)

    with application.app_context():
        db.create_all()
        if User.query.filter_by(username="demo").first() is None:
            u = User(username="demo", role="user")
            u.set_password("Pass@123")
            db.session.add(u)
            db.session.commit()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "Pass@123"})
    assert r.status_code == 200, f"登录失败: {r.status_code} {r.text[:300]}"
    token = r.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _patch_assemble(monkeypatch, datasets="default", skipped=None):
    """把端点的数据集装配替换为零联网夹具（modules.export_bundle 上打补丁，
    端点经 eb.assemble_datasets 调用即生效）。"""
    if datasets == "default":
        datasets = _fixture_datasets()
        skipped = FIXTURE_SKIPPED if skipped is None else skipped

    def fake(period, code, sources=None, watchlist_codes=None):
        return dict(datasets), list(skipped or [])

    monkeypatch.setattr(eb, "assemble_datasets", fake)


def _assert_validation_422(r):
    assert r.status_code == 422, f"期望 422，实得 {r.status_code}: {r.text[:300]}"
    j = r.get_json()
    assert j["status"] == "error" and j["code"] == "validation_error", j
    assert j["data"] is None, j


def test_export_bundle_zip_happy(client, auth, monkeypatch):
    _patch_assemble(monkeypatch)
    r = client.get("/api/v2/read/export-bundle?format=zip&period=20260331&code=600519",
                   headers=auth)
    assert r.status_code == 200, r.text[:300]
    # 注：app.py 的 _add_headers 安全网目前会把非 JSON/HTML/MD 响应的 Content-Type
    # 兜底改成 application/json（本 worktree 未改 app.py）；此处验证
    # Content-Disposition 与响应体 magic bytes，mime 豁免由 lead 集成 app.py 时补。
    assert "attachment" in r.headers["Content-Disposition"]
    assert "filename*=utf-8''" in r.headers["Content-Disposition"]  # RFC 5987
    assert "text/html" not in r.headers["Content-Type"]  # 绝不泄漏 HTML 错误页
    body = r.data
    assert body[:4] == b"PK\x03\x04", body[:4]
    zf = zipfile.ZipFile(io.BytesIO(body))
    assert set(zf.namelist()) == {"行业板块资金流向.csv", "大盘主力净流入30日.csv", "manifest.csv"}
    assert zf.read("行业板块资金流向.csv").startswith(b"\xef\xbb\xbf")
    assert "已跳过" in zf.read("manifest.csv").decode("utf-8-sig")


def test_export_bundle_excel_happy(client, auth, monkeypatch):
    import openpyxl

    _patch_assemble(monkeypatch)
    r = client.get("/api/v2/read/export-bundle?format=excel", headers=auth)
    assert r.status_code == 200, r.text[:300]
    assert "attachment" in r.headers["Content-Disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.data))
    assert wb.sheetnames == ["行业板块资金流向", "大盘主力净流入30日"], wb.sheetnames


def test_export_bundle_pdf_happy(client, auth, monkeypatch):
    _patch_assemble(monkeypatch)
    r = client.get("/api/v2/read/export-bundle?format=pdf", headers=auth)
    assert r.status_code == 200, r.text[:300]
    assert "attachment" in r.headers["Content-Disposition"]
    assert r.data[:5] == b"%PDF-", r.data[:5]


def test_export_bundle_json_happy(client, auth, monkeypatch):
    _patch_assemble(monkeypatch)
    r = client.get("/api/v2/read/export-bundle?format=json", headers=auth)
    assert r.status_code == 200, r.text[:300]
    j = r.get_json()
    assert j["status"] == "ok", j
    d = j["data"]
    assert d["available"] is True and d["reason"] is None, d
    assert set(d["datasets"]) == {"行业板块资金流向.csv", "大盘主力净流入30日.csv"}
    assert d["datasets"]["行业板块资金流向.csv"][1]["主力净流入"] is None  # NaN → None
    assert d["skipped"] == FIXTURE_SKIPPED


def test_export_bundle_all_failed_honest_degradation(client, auth, monkeypatch):
    all_names = ["行业板块资金流向.csv", "北向资金_板块.csv", "北向资金_汇总.csv",
                 "大盘主力净流入30日.csv", "个股主力资金.csv", "业绩报表.csv",
                 "组合持仓盈亏.csv", "组合持仓汇总.csv", "自选股实时快照.csv"]
    _patch_assemble(monkeypatch, datasets={}, skipped=all_names)
    r = client.get("/api/v2/read/export-bundle?format=zip", headers=auth)
    assert r.status_code == 200, r.text[:300]  # 诚实降级：200 + available=false
    j = r.get_json()
    assert j["status"] == "ok", j
    d = j["data"]
    assert d["available"] is False
    assert d["datasets"] == {}
    assert d["skipped"] == all_names  # skipped 全清单
    assert d["reason"] and "不可用" in d["reason"], d


def test_export_bundle_pdf_build_failure_degrades(client, auth, monkeypatch):
    _patch_assemble(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("pdf engine boom")

    monkeypatch.setattr(eb, "to_pdf", boom)
    r = client.get("/api/v2/read/export-bundle?format=pdf", headers=auth)
    assert r.status_code == 200, r.text[:300]  # 格式化失败 → 200 + available=false + reason
    j = r.get_json()
    d = j["data"]
    assert d["available"] is False
    assert "pdf" in d["reason"] and "生成失败" in d["reason"], d
    # 绝不返回半个损坏文件：响应必须是 JSON 信封，而非二进制
    assert j["status"] == "ok"


@pytest.mark.parametrize("query", [
    "format=csv",       # 白名单只有 zip/excel/pdf/json
    "format=foo",
    "format=",
    "format=zip&code=60051",     # 5 位
    "format=zip&code=60051a",    # 含字母
    "format=zip&code=ABCDEF",
    "format=zip&period=2026",    # 不足 8 位
    "format=zip&period=abcd0331",
])
def test_export_bundle_invalid_params_422(client, auth, monkeypatch, query):
    _patch_assemble(monkeypatch)
    r = client.get(f"/api/v2/read/export-bundle?{query}", headers=auth)
    _assert_validation_422(r)


def test_export_bundle_no_token_401(client, monkeypatch):
    _patch_assemble(monkeypatch)
    r = client.get("/api/v2/read/export-bundle?format=zip")
    assert r.status_code == 401, f"期望 401，实得 {r.status_code}: {r.text[:300]}"
    assert r.get_json()["status"] == "error"


def _patch_report(monkeypatch, data="default", name="贵州茅台"):
    if data == "default":
        # pe_ttm/industry 是 research_report._basic 可识别的基本面键（有值 → basic 板块可用）
        data = {"fundamentals": {"pe_ttm": 20.0, "industry": "白酒"}}

    def fake(code, fetcher=None, **kwargs):
        return dict(data), name

    monkeypatch.setattr(eb, "collect_report_data", fake)


def test_stock_report_html_happy(client, auth, monkeypatch):
    _patch_report(monkeypatch)
    r = client.get("/api/v2/read/stock-report?code=600519&format=html", headers=auth)
    assert r.status_code == 200, r.text[:300]
    j = r.get_json()
    d = j["data"]
    assert d["available"] is True, d  # fundamentals 板块可用 → 覆盖率 > 0
    assert d["code"] == "600519" and d["name"] == "贵州茅台"
    assert d["coverage_pct"] > 0 and d["coverage_pct"] < 100  # 其余板块缺失
    assert d["skipped_blocks"], d  # 缺失板块进 skipped_blocks（warnings）
    html = d["html"]
    assert "<html" in html.lower() and "600519" in html
    assert "数据不可用" in html  # 缺失板块明确标注，绝不编造


def test_stock_report_md_happy(client, auth, monkeypatch):
    _patch_report(monkeypatch)
    r = client.get("/api/v2/read/stock-report?code=600519&format=md", headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is True
    md = d["md"]
    assert "## " in md and "数据不可用" in md


def test_stock_report_zero_coverage_honest(client, auth, monkeypatch):
    _patch_report(monkeypatch, data={}, name="600519")
    r = client.get("/api/v2/read/stock-report?code=600519&format=html", headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is False
    assert "无有效数据" in d["reason"], d


def test_stock_report_render_failure_degrades(client, auth, monkeypatch):
    _patch_report(monkeypatch)

    def boom(rep):
        raise RuntimeError("render boom")

    monkeypatch.setattr(rrp, "render_html", boom)
    r = client.get("/api/v2/read/stock-report?code=600519&format=html", headers=auth)
    assert r.status_code == 200, r.text[:300]  # 渲染失败 → 200 + available=false + reason
    d = r.get_json()["data"]
    assert d["available"] is False and "渲染失败" in d["reason"], d


@pytest.mark.parametrize("query", [
    "code=60051&format=html",   # code 5 位
    "code=ABCDEF&format=html",
    "code=&format=html",
    "code=600519&format=pdf",   # 白名单只有 html/md
    "code=600519&format=",
])
def test_stock_report_invalid_params_422(client, auth, monkeypatch, query):
    _patch_report(monkeypatch)
    r = client.get(f"/api/v2/read/stock-report?{query}", headers=auth)
    _assert_validation_422(r)


def test_stock_report_no_token_401(client, monkeypatch):
    _patch_report(monkeypatch)
    r = client.get("/api/v2/read/stock-report?code=600519&format=html")
    assert r.status_code == 401, f"期望 401，实得 {r.status_code}: {r.text[:300]}"
    assert r.get_json()["status"] == "error"


# ───────────── 64 投研圆桌静态交付物（v1 双格式展示 + 双下载后端化）─────────────
URL_ROUNDTABLE = "/api/v2/read/roundtable-report"


def test_roundtable_meta_reads_real_deliverable(client, auth):
    r = client.get(f"{URL_ROUNDTABLE}?format=meta", headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is True
    assert d["as_of"] == "2026-09-11"
    assert d["md_available"] is True and d["html_available"] is True
    assert d["kpis"], "真实报告应能从正文提取至少 1 张 KPI 卡"
    assert all(set(k) >= {"label", "value", "meta"} for k in d["kpis"])


@pytest.mark.parametrize("fmt,marker", [
    ("md", "数据日期"),
    ("html", "<style>"),
])
def test_roundtable_md_html_content(client, auth, fmt, marker):
    r = client.get(f"{URL_ROUNDTABLE}?format={fmt}", headers=auth)
    assert r.status_code == 200, r.text[:300]
    d = r.get_json()["data"]
    assert d["available"] is True and d["format"] == fmt
    assert d["filename"].endswith(f".{fmt}") and d["content"]
    assert marker in d["content"], f"{fmt} 原文缺少预期标记 {marker}"


def test_roundtable_invalid_format_422(client, auth):
    r = client.get(f"{URL_ROUNDTABLE}?format=pdf", headers=auth)
    _assert_validation_422(r)


def test_roundtable_missing_files_is_honest(client, auth, monkeypatch, tmp_path):
    from backend.api import export_routes

    monkeypatch.setattr(export_routes, "_ROUNDTABLE_DIR", tmp_path)
    for fmt in ("meta", "md", "html"):
        r = client.get(f"{URL_ROUNDTABLE}?format={fmt}", headers=auth)
        assert r.status_code == 200, r.text[:300]
        d = r.get_json()["data"]
        assert d["available"] is False and d["reason"], d
        assert "content" not in d, "缺文件绝不返回样例正文"


def test_roundtable_no_token_401(client):
    r = client.get(URL_ROUNDTABLE)
    assert r.status_code == 401
