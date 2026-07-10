"""
新闻事件抓取与智能分析模块 v2.0（半导体专项增强版）
功能：
1. 多源新闻抓取（东方财富网页搜索 + 财新数据通 + 央视新闻 + 百度股市通）
2. 半导体行业专项关键词引擎（核心词汇 + 细分公司名 + 子赛道）
3. jieba 关键词提取（TF-IDF + TextRank 双算法）
4. 中文情感分析（金融领域词典法 + 半导体领域增强 + SnowNLP 兜底）
5. 新闻去重（标题相似度 + 内容指纹）
6. 自动摘要生成
7. 结构化 SQLite 存储，支持多维度查询
8. 个股-新闻关联预警模型
"""

import os
import re
import time
import json
import hashlib
import sqlite3
from datetime import datetime, timedelta
from collections import Counter, defaultdict

import pandas as pd
import numpy as np

try:
    import akshare as ak
    _AK_OK = True
except ImportError:
    _AK_OK = False

try:
    import jieba
    import jieba.analyse
    _JIEBA_OK = True
except ImportError:
    _JIEBA_OK = False

try:
    from snownlp import SnowNLP
    _SNOW_OK = True
except ImportError:
    _SNOW_OK = False

# ──────────────────────────────────────────────
# 网络请求工具
# ──────────────────────────────────────────────
def _retry_request(func, max_retries=3, base_delay=2):
    """网络请求自动重试。"""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except (ConnectionError, TimeoutError, OSError) as e:
            last_err = e
            err_msg = str(e).lower()
            is_transient = any(kw in err_msg for kw in [
                "remote disconnected", "connection aborted", "reset by peer",
                "timed out", "connection refused", "broken pipe",
                "remote end closed", "temporary failure"
            ])
            if not is_transient or attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            time.sleep(delay)
        except Exception:
            raise
    raise last_err


def _fetch_url(url, headers=None, timeout=15, encoding="utf-8"):
    """
    通用 URL 抓取（urllib，无额外依赖）。
    返回 decoded text 或 None。
    """
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request(
            url,
            headers=headers or {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://www.eastmoney.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            # 自动检测编码
            if encoding == "auto":
                ct = resp.headers.get("Content-Type", "")
                m = re.search(r"charset=([\\w-]+)", ct, re.I)
                enc = m.group(1).lower() if m else "utf-8"
            else:
                enc = encoding
            return data.decode(enc, errors="ignore")
    except Exception as e:
        print(f"[_fetch_url] {url[:60]}... failed: {e}")
        return None


# ──────────────────────────────────────────────
# 半导体行业关键词引擎
# ──────────────────────────────────────────────

class SemiconductorKeywordEngine:
    """
    半导体行业关键词引擎。
    提供三级关键词体系：核心术语、细分赛道、龙头公司。
    支持按股票代码自动匹配相关关键词集合。
    """

    # ─── 核心术语（通用） ───
    CORE_TERMS = [
        "半导体", "芯片", "集成电路", "晶圆", "光刻机", "刻蚀机",
        "薄膜沉积", "离子注入", "CMP", "封装测试", "封测",
        "IC设计", "芯片设计", "代工", "晶圆厂", "IDM", "Fabless",
        "Foundry", "OSAT", "硅片", "大硅片", "电子特气",
        "光掩模", "光刻胶", "靶材", "湿电子化学品", "抛光液",
        "溅射靶材", "前道设备", "后道设备", "测试设备",
        "摩尔定律", "先进制程", "成熟制程", "7nm", "5nm", "3nm",
        "14nm", "28nm", "FinFET", "GAA", "Chiplet", "SiP",
        "HBM", "CPO", "硅光子", "第三代半导体", "碳化硅", "氮化镓",
        "化合物半导体", "功率半导体", "IGBT", "MOSFET", "二极管",
        "存储芯片", "DRAM", "NAND", "NOR Flash", "EEPROM",
        "MCU", "GPU", "CPU", "FPGA", "DSP", "SoC", "ASIC",
        "模拟芯片", "射频芯片", "电源管理芯片", "信号链",
        "传感器", "MEMS", "CIS", "指纹芯片", "驱动IC",
        "国产替代", "自主可控", "供应链安全", "芯片法案",
        "出口管制", "实体清单", "制裁", "断供", "卡脖子",
        "产能扩充", "产能利用率", "稼动率", "良率", "yield",
        "涨价", "降价", "缺货", "库存", "去库存", "补库",
        "订单饱满", "需求旺盛", "景气上行", "景气下行",
        "并购重组", "IPO", "定增", "股权激励",
        "研发投入", "专利", "技术突破", "量产", "送样",
        "客户导入", "验证通过", "小批量供货", "放量",
    ]

    # ─── 细分赛道 → 关键词映射 ───
    SUB_SECTORS = {
        "晶圆制造": ["中芯国际", "华虹半导体", "晶合集成", "粤芯半导体",
                     "积塔半导体", "合肥晶合", "华虹宏力"],
        "设备材料": ["北方华创", "中微公司", "盛美上海", "拓荆科技",
                     "华海清科", "微导纳米", "芯源微", "精测电子",
                     "安集科技", "雅克科技", "江丰电子", "沪硅产业",
                     "TCL中环", "有研新材", "立昂微"],
        "IC设计-存储": ["兆易创新", "北京君正", "东芯股份", "佰维存储",
                       "普冉股份", "恒烁股份"],
        "IC设计-GPU/CPU": ["海光信息", "寒武纪", "龙芯中科", "景嘉微"],
        "IC设计-模拟": ["圣邦股份", "思瑞浦", "艾为电子", "卓胜微",
                       "韦尔股份", "纳芯微", "帝奥微"],
        "IC设计-MCU/控制": ["中颖电子", "乐鑫信息", "极术科技", "峰昭科技",
                           "国芯科技", "复旦微电"],
        "IC设计-FPGA/其他": ["紫光国微", "安路科技", "复旦微电", "澜起科技"],
        "功率半导体": ["斯达半导", "士兰微", "扬杰科技", "新洁能",
                      "时代电气", "宏微科技", "东微半导", "芯导电子"],
        "封测": ["长电科技", "通富微电", "华天科技", "晶方科技"],
        "第三代半导体": ["天岳先进", "三安光电", "天科合达", "光莆股份"],
        "显示芯片": ["京东方A", "TCL科技", "汇顶科技", "格科微"],
        "消费电子芯片": ["立讯精密", "闻泰科技", "歌尔股份", "领益智造"],
    }

    # ─── 龙头公司完整列表（含代码）→ 用于个股精确匹配 ───
    SEMI_LEADERS = {
        # 晶圆代工
        "688981": ("中芯国际", ["先进制程", "成熟制程", "晶圆代工", "CoWoS"]),
        "688126": ("沪硅产业", ["硅片", "大硅片", "半导体材料"]),
        "688037": ("芯源微", ["涂胶显影", "清洗设备", "半导体设备"]),

        # 设备
        "002371": ("北方华创", ["刻蚀机", "薄膜沉积", "PVD", "CVD", "ALD", "半导体设备"]),
        "688012": ("中微公司", ["刻蚀机", "MOCVD", "LPCVD", "半导体设备"]),
        "688082": ("盛美上海", ["镀铜", "清洗", "炉管", "半导体设备"]),
        "688370": ("拓荆科技", ["ALD", "CVD", "薄膜沉积", "半导体设备"]),
        "688396": ("华海清科", ["CMP", "抛光", "减薄", "半导体设备"]),
        "688262": ("微导纳米", ["ALD", "薄膜", "半导体设备"]),
        "300567": ("精测电子", ["检测设备", "量测", "面板检测"]),

        # 材料端
        "688019": ("安集科技", ["抛光液", "CMP材料", "功能性湿电子化学品"]),
        "002409": ("雅克科技", ["光刻胶", "前驱体", "电子特气", "LDS输送系统"]),
        "300666": ("江丰电子", ["靶材", "溅射靶材", "高纯金属材料"]),
        "605358": ("立昂微", ["硅片", "半导体硅片", "功率器件"]),
        "002129": ("TCL中环", ["硅片", "大硅片", "半导体材料", "光伏硅片"]),

        # IC设计 - 存储
        "603986": ("兆易创新", ["存储器", "NOR Flash", "MCU", "DRAM"]),
        "300223": ("北京君正", ["存储器", "DRAM", "视频处理"]),
        "688041": ("海光信息", ["DCU", "CPU", "x86", "服务器芯片"]),
        "688256": ("寒武纪", ["AI芯片", "NPU", "智能计算", "训练", "推理"]),
        "688047": ("龙芯中科", ["LoongArch", "CPU", "自主指令集"]),
        "300474": ("景嘉微", ["GPU", "图形处理器", "军用GPU"]),
        "300782": ("安路科技", ["FPGA", "可编程逻辑器件"]),
        "688200": ("华峰测控", ["测试设备", "模拟测试", "SoC测试"]),

        # IC设计 - 模拟/射频
        "300661": ("圣邦股份", ["模拟芯片", "电源管理", "信号链"]),
        "688536": ("思瑞浦", ["模拟芯片", "信号链", "电源管理"]),
        "688501": ("艾为电子", ["音频功放", "射频", "模拟芯片"]),
        "603501": ("韦尔股份", ["CIS", "图像传感器", "模拟芯片", "显示驱动"]),
        "688052": ("纳芯微", ["隔离芯片", "模拟芯片", "信号链"]),
        "301281": ("帝奥微", ["模拟芯片", "电源管理", "信号链"]),
        "603160": ("汇顶科技", ["指纹芯片", "触控芯片", "IoT"]),
        "688099": ("晶丰明源", ["LED驱动", "电源管理", "照明芯片"]),

        # 功率器件
        "603290": ("斯达半导", ["IGBT", "功率模块", "SiC", "车规级"]),
        "600460": ("士兰微", ["IDM", "功率器件", "模拟电路", "MEMS"]),
        "300553": ("扬杰科技", ["功率二极管", "整流桥", "功率模块"]),
        "605111": ("新洁能", ["MOSFET", "IGBT", "功率器件"]),
        "688187": ("时代电气", ["IGBT", "轨道交通", "功率器件"]),
        "688268": ("华特气体", ["电子特气", "特种气体"]),

        # 封测
        "600584": ("长电科技", ["先进封装", "SiP", "WLCSP", "FCBGA"]),
        "002156": ("通富微电", ["先进封装", "Chiplet", "2.5D/3D封装"]),
        "002185": ("华天科技", ["封装测试", "TSV", "SiP"]),
        "603005": ("晶方科技", ["CIS封装", "WLCSP", "晶圆级封装"]),

        # 第三代半导体 / LED等
        "600703": ("三安光电", ["LED", "MiniLED", "MicroLED", "碳化硅", "射频"]),
        "688234": ("天岳先进", ["碳化硅衬底", "SiC substrate"]),
        "301121": ("紫建电子", ["锂电池", "消费电子电池"]),

        # 连接器/被动元件
        "000063": ("中兴通讯", ["通信设备", "5G基站", "芯片"]),
        "002384": ("东山精密", ["PCB", "FPC", "连接器", "屏蔽件"]),
        "002241": ("歌尔股份", ["VR/AR", "声学", "TWS", "光学"]),
        "002475": ("立讯精密", ["连接器", "线缆", "苹果供应链"]),
        "002241": ("歌尔股份", ["VR/AR", "TWS", "声学器件"]),
        "600183": ("生益科技", ["覆铜板", "高频高速基板"]),
        "603160": ("汇顶科技", ["指纹识别", "触控芯片"]),
        "688981": ("中芯国际", ["晶圆代工", "先进制程", "14nm", "28nm"]),
        "688008": ("澜起科技", ["内存接口芯片", "DDR5", "津逮CPU"]),
        "688396": ("华海清科", ["CMP", "化学机械抛光", "减薄"]),
    }

    def __init__(self):
        # 构建名称→代码 反向映射
        self._name_to_code = {}
        for code, (name, _) in self.SEMI_LEADERS.items():
            self._name_to_code[name] = code

    def get_keywords_for_stock(self, code_or_name, top_k=15):
        """
        根据股票代码或名称获取该股相关的半导体关键词。
        返回逗号分隔的关键词字符串。
        """
        code = code_or_name.strip()

        # 1. 精确匹配 SEMI_LEADERS
        info = self.SEMI_LEADERS.get(code)
        if not info and code in self._name_to_code:
            info = self.SEMI_LEADERS.get(self._name_to_code[code])

        if info:
            name, specific_kws = info
            result = list(specific_kws)
        else:
            name = ""
            result = []

        # 2. 匹配细分赛道
        for sector, companies in self.SUB_SECTORS.items():
            if code in companies or (name and name in companies):
                sector_kws = [sector]
                sector_tags = [t.strip() for t in [sector.replace("IC设计-", ""), "设备", "材料", "封测"] if len(t.strip()) >= 2]
                for k in self.CORE_TERMS:
                    if any(tag in k for tag in sector_tags):
                        sector_kws.append(k)
                        break
                for sk in sector_kws:
                    if sk not in result:
                        result.append(sk)

        # 3. 补充通用核心词（如果结果太少）
        if len(result) < top_k:
            for kw in self.CORE_TERMS:
                if kw not in result:
                    result.append(kw)
                    if len(result) >= top_k * 2:
                        break

        return ",".join(result[:top_k])

    def get_all_semi_codes(self):
        """返回所有半导体龙头股票代码列表。"""
        return list(self.SEMI_LEADERS.keys())

    def get_search_keywords(self, category="all"):
        """
        获取用于新闻搜索的扩展关键词。
        category: all / core / companies / sectors
        """
        if category == "companies":
            return [name for name, _ in self.SEMI_LEADERS.values()]
        elif category == "core":
            return self.CORE_TERMS
        elif category == "sectors":
            return list(self.SUB_SECTORS.keys())
        else:
            # 返回所有搜索用关键词（核心+公司名）
            kws = set(self.CORE_TERMS)
            for name, _ in self.SEMI_LEADERS.values():
                kws.add(name)
            return sorted(kws)

    def is_semi_related(self, stock_code):
        """判断某只股票是否属于半导体板块。"""
        return stock_code in self.SEMI_LEADERS


# ──────────────────────────────────────────────
# 金融领域情感词典（v2 增强版）
# ──────────────────────────────────────────────

POSITIVE_WORDS = {
    # 通用利好
    "利好", "增长", "超预期", "订单", "突破", "涨价", "补贴", "支持", "回升",
    "增持", "回购", "业绩大增", "涨停", "大涨", "暴涨", "创新高", "丰收",
    "盈利", "翻倍", "强劲", "繁荣", "刺激", "宽松", "降息", "减税", "复苏",
    "扩张", "加速", "强劲增长", "供不应求", "紧缺", "高速增长", "大幅提升",
    "景气回升", "景气度", "高景气", "需求旺盛", "产销两旺", "量价齐升",
    # 半导体专属利好
    "国产替代加速", "自主可控", "技术突破", "量产成功", "良率提升",
    "产能爬坡", "稼动率提升", "订单饱满", "验证通过", "导入成功",
    "送样通过", "小批量出货", "开始放量", "市场份额扩大",
    "获得大单", "签下长协", "涨价函", "毛利率改善", "净利率提升",
    "研发突破", "专利授权", "新品发布", "先进制程进展", "制程迭代",
    "客户拓展", "新应用落地", "车规认证", "AEC-Q100", "IATF16949",
    "并购整合", "产业链协同", "生态建设",
}

NEGATIVE_WORDS = {
    # 通用利空
    "利空", "下降", "亏损", "违规", "处罚", "下跌", "停产", "风险", "预警",
    "减持", "质押", "爆雷", "退市", "暴跌", "大跌", "跳水", "创新低", "萧条",
    "收缩", "放缓", "滞销", "过剩", "库存积压", "裁员", "停产限产", "限产",
    "违约", "诉讼", "调查", "问询", "监管", "收紧", "加息", "通胀", "滞胀",
    "产能过剩", "价格战", "恶性竞争", "需求疲软", "景气下行", "业绩暴雷",
    # 半导体专属利空
    "出口管制", "实体清单", "制裁升级", "断供风险", "被列入",
    "技术封锁", "禁售", "许可证拒批", "设备禁运",
    "产能过剩", "价格战加剧", "毛利率下滑", "存货减值",
    "良率不及预期", "研发延期", "量产推迟",
    "大客户流失", "订单取消", "砍单", "下调预期",
    "高管离职", "内控问题", "财务造假",
    "解禁潮", "股东减持", "质押平仓",
    "下游需求疲软", "消费电子寒冬", "手机销量下滑",
}


STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "它", "被", "从", "把", "对", "为", "与",
    "及", "或", "等", "但", "而", "则", "其", "此", "以", "可", "将", "已",
    "该", "某", "多", "少", "大", "小", "中", "后", "前", "年", "月", "日",
    "时", "分", "点", "个", "只", "量", "项", "家", "位", "名", "号",
}


# ──────────────────────────────────────────────
# 新闻抓取器 v2（多源 + 直接抓取）
# ──────────────────────────────────────────────

class NewsFetcher:
    """
    多源新闻抓取器 v2.0。
    数据源优先级：
      1. 东方财富网页搜索（直接 HTTP 抓取，支持任意关键词）
      2. 财新数据通（akshare stock_news_main_cx）
      3. 央视新闻联播（akshare news_cctv）
      4. 百度股市通经济日历（补充宏观事件）
    """

    def __init__(self):
        self.semi_engine = SemiconductorKeywordEngine()
        self._cache = {}  # 内存缓存 {keyword_hash: (timestamp, df)}

    def fetch(self, keyword=None, source="auto", limit=50):
        """
        抓取新闻。
        :param keyword: 搜索关键词（支持中文，如"半导体"、"中芯国际"）
        :param source: auto / eastmoney / eastmoney_web / caixin / cctv / all
                       （eastmoney 为历史别名，内部映射为 eastmoney_web）
        :param limit: 最多返回条数
        :return: DataFrame[date, title, content, source, url]
        """
        # 兼容历史调用：页面中大量 source="eastmoney" 需要正常工作
        if source == "eastmoney":
            source = "eastmoney_web"

        if source == "auto":
            return self._fetch_auto(keyword, limit)
        elif source == "all":
            return self.fetch_all(keyword, limit_per_source=limit // 3 + 10)
        elif source == "eastmoney_web":
            return self._fetch_eastmoney_web(keyword, limit)
        elif source == "caixin":
            return self._fetch_caixin(keyword, limit)
        elif source == "cctv":
            return self._fetch_cctv(keyword, limit)
        else:
            raise ValueError(f"不支持的来源: {source}")

    def _fetch_auto(self, keyword, limit):
        """自动聚合多数据源，按关键词过滤后合并去重。"""
        frames = []
        errors = []
        per_limit = max(limit // 2, 10)

        # Source 1: 东方财富财经要闻（关键词过滤）
        try:
            df = self._fetch_eastmoney_web(keyword, per_limit)
            if not df.empty:
                frames.append(df)
                print(f"[NewsFetcher] 东方财富网页: {len(df)} 条")
        except Exception as e:
            errors.append(f"东方财富网页: {e}")

        # Source 2: 财新数据通（补充）
        try:
            df = self._fetch_caixin(keyword, per_limit)
            if not df.empty:
                frames.append(df)
                print(f"[NewsFetcher] 财新数据通: {len(df)} 条")
        except Exception as e:
            errors.append(f"财新: {e}")

        # Source 3: 央视新闻联播（宏观/政策类补充）
        if keyword:
            try:
                df = self._fetch_cctv(keyword, per_limit // 2)
                if not df.empty:
                    frames.append(df)
                    print(f"[NewsFetcher] 央视新闻: {len(df)} 条")
            except Exception as e:
                errors.append(f"央视: {e}")

        if frames:
            combined = pd.concat(frames, ignore_index=True)
            combined = combined.drop_duplicates(subset=["title"], keep="first")
            return combined.sort_values("date", ascending=False).head(limit).reset_index(drop=True)

        print(f"[NewsFetcher] 所有源均失败: {errors[-1] if errors else 'unknown'}")
        return pd.DataFrame(columns=["date", "title", "content", "source", "url"])

    # ------------------------------------------------------------------
    # Source 1: 东方财富搜索 API（最高精度、覆盖全面）
    # 策略：
    #   1) 优先调用 search-api-web.eastmoney.com 搜索接口，按关键词精确检索，
    #      支持股票代码、股票名称、行业关键词，返回带 URL 的真实新闻。
    #   2) 若搜索 API 失败或无结果，回退到东方财富财经要闻页面兜底。
    # ------------------------------------------------------------------
    def _fetch_eastmoney_web(self, keyword, limit=50):
        """
        东方财富新闻抓取（搜索 API + 财经要闻兜底）。
        :param keyword: 搜索关键词；可为股票代码、名称、行业关键词等
        :param limit: 最多返回条数
        :return: DataFrame[date, title, content, source, url]
        """
        items = self._fetch_eastmoney_search_api(keyword=keyword, limit=limit)
        if not items:
            # 兜底：财经要闻页面 + 关键词过滤
            items = self._fetch_eastmoney_yw(keyword=keyword, limit=limit)

        if not items:
            return pd.DataFrame(columns=["date", "title", "content", "source", "url"])

        df = pd.DataFrame(items)
        df["source"] = "eastmoney_web"
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df[["date", "title", "content", "source", "url"]].head(limit).dropna(subset=["title"])

    def _fetch_eastmoney_search_api(self, keyword=None, limit=50):
        """
        调用东方财富搜索 API 获取新闻。
        接口: https://search-api-web.eastmoney.com/search/jsonp
        """
        if not keyword:
            return []

        import urllib.parse

        inner_param = {
            "uid": "",
            "keyword": str(keyword),
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": 1,
                    "pageSize": min(limit, 50),
                    "preTag": "<em>",
                    "postTag": "</em>",
                }
            },
        }
        params = {
            "cb": "jQuery3510",
            "param": json.dumps(inner_param, ensure_ascii=False),
            "_": str(int(datetime.now().timestamp() * 1000)),
        }
        url = "https://search-api-web.eastmoney.com/search/jsonp?" + urllib.parse.urlencode(params)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Referer": "https://so.eastmoney.com/",
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")

            m = re.search(r'jQuery\w*\((.*)\)\s*$', raw, re.DOTALL)
            if not m:
                return []

            data = json.loads(m.group(1))
            if data.get("code") != 0:
                return []

            result = data.get("result", {})
            cms_list = result.get("cmsArticleWebOld", [])

            items = []
            for item in cms_list:
                title = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
                content = re.sub(r"<[^>]+>", "", item.get("content", "")).strip()
                url = item.get("url", "")
                date_str = item.get("date", "") or datetime.now().strftime("%Y-%m-%d")
                if title and url:
                    items.append({
                        "date": date_str,
                        "title": title,
                        "content": content,
                        "url": url,
                    })
            return items
        except Exception as e:
            print(f"[NewsFetcher] 东方财富搜索 API 失败: {e}")
            return []

    def _fetch_eastmoney_yw(self, keyword=None, limit=50):
        """
        抓取东方财富财经要闻页面，返回原始 item 列表。
        URL: https://finance.eastmoney.com/a/cywjh.html
        """
        url = "https://finance.eastmoney.com/a/cywjh.html"
        html = _fetch_url(url, timeout=15)
        if not html:
            return []

        items = self._parse_eastmoney_yw(html)
        if not items:
            return []

        # 关键词过滤：标题或摘要包含任一关键词即保留
        if keyword and str(keyword).strip():
            kw = str(keyword).strip()
            kws = [k.strip() for k in kw.replace(",", " ").split() if k.strip()]
            filtered = []
            for it in items:
                text = f"{it.get('title', '')} {it.get('content', '')}"
                if any(k in text for k in kws):
                    filtered.append(it)
            items = filtered

        return items[:limit]

    @staticmethod
    def _parse_eastmoney_yw(html):
        """
        解析东方财富财经要闻页面 HTML。
        返回 [{'date', 'title', 'content', 'url'}, ...]
        """
        items = []
        pattern = re.compile(
            r'<a[^>]+href=\"(https?://finance\.eastmoney\.com/a/\d+\.html)\"[^>]*>'
            r'([^<]{5,120})</a>',
            re.IGNORECASE | re.DOTALL,
        )

        for match in pattern.finditer(html):
            url = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if not title or len(title) < 6:
                continue

            nearby = html[max(0, match.start() - 500):match.end() + 500]
            date_m = re.search(
                r'(\d{4}-\d{2}-\d{2}|\d{2}-\d{2}\s+\d{2}:\d{2}|\d{2}-\d{2})',
                nearby,
            )
            date_str = date_m.group(1) if date_m else datetime.now().strftime("%Y-%m-%d")

            if re.match(r"^\d{2}-\d{2}\s+\d{2}:\d{2}$", date_str):
                date_str = f"{datetime.now().year}-{date_str}"
            elif re.match(r"^\d{2}-\d{2}$", date_str):
                date_str = f"{datetime.now().year}-{date_str}"

            items.append({
                "date": date_str,
                "title": title,
                "content": "",
                "url": url,
            })

        return items

    # ------------------------------------------------------------------
    # Source 2: 财新数据通
    # ------------------------------------------------------------------
    def _fetch_caixin(self, keyword=None, limit=50):
        """财新数据通来源。"""
        if not _AK_OK:
            return pd.DataFrame(columns=["date", "title", "content", "source", "url"])
        try:
            df = _retry_request(lambda: ak.stock_news_main_cx(), max_retries=3, base_delay=2)

            df = df.rename(columns={
                "summary": "content",
                "tag": "category",
            })

            df["title"] = df["content"].str.split(r"[\n。，；]", n=1).str[0].str.strip()
            df["title"] = df["title"].str.slice(0, 80)
            df["date"] = datetime.now().strftime("%Y-%m-%d")
            df["url"] = df.get("url", "")

            if keyword:
                kws = [k.strip() for k in str(keyword).replace(",", " ").split() if k.strip()]
                if kws:
                    mask = (
                        df["category"].apply(lambda x: any(k in str(x) for k in kws)) |
                        df["title"].apply(lambda x: any(k in str(x) for k in kws)) |
                        df["content"].apply(lambda x: any(k in str(x) for k in kws))
                    )
                    df = df[mask]

            df["source"] = "caixin"
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            return df[["date", "title", "content", "source", "url"]].head(limit).dropna(subset=["title"])
        except Exception as e:
            print(f"[NewsFetcher] 财新抓取失败: {e}")
            return pd.DataFrame(columns=["date", "title", "content", "source", "url"])

    # ------------------------------------------------------------------
    # Source 3: 央视新闻联播
    # ------------------------------------------------------------------
    def _fetch_cctv(self, keyword=None, limit=30):
        """央视新闻联播来源。"""
        if not _AK_OK:
            return pd.DataFrame(columns=["date", "title", "content", "source", "url"])
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            df = _retry_request(
                lambda: ak.news_cctv(date=date_str),
                max_retries=3, base_delay=2,
            )
            df = df.rename(columns={"date": "date", "title": "title", "content": "content"})
            df["source"] = "cctv"
            df["url"] = ""
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            if keyword:
                kws = [k.strip() for k in str(keyword).replace(",", " ").split() if k.strip()]
                if kws:
                    df = df[
                        df["title"].apply(lambda x: any(k in str(x) for k in kws)) |
                        df["content"].apply(lambda x: any(k in str(x) for k in kws))
                    ]
            return df[["date", "title", "content", "source", "url"]].head(limit).dropna(subset=["date"])
        except Exception:
            return pd.DataFrame(columns=["date", "title", "content", "source", "url"])

    def fetch_all(self, keyword=None, limit_per_source=30):
        """聚合所有来源的新闻。"""
        frames = []
        sources_funcs = [
            ("eastmoney_web", lambda: self._fetch_eastmoney_web(keyword, limit_per_source)),
            ("caixin", lambda: self._fetch_caixin(keyword, limit_per_source)),
            ("cctv", lambda: self._fetch_cctv(keyword, limit_per_source)),
        ]
        for src_name, src_func in sources_funcs:
            try:
                df = src_func()
                if not df.empty:
                    frames.append(df)
            except Exception as e:
                print(f"[NewsFetcher] {src_name}: {e}")
        if frames:
            combined = pd.concat(frames, ignore_index=True)
            combined = combined.drop_duplicates(subset=["title"], keep="first")
            return combined.sort_values("date", ascending=False).reset_index(drop=True)
        return pd.DataFrame(columns=["date", "title", "content", "source", "url"])

    # ------------------------------------------------------------------
    # Source 4: 个股公告（东方财富公告大全）
    # ------------------------------------------------------------------
    def _fetch_eastmoney_announcements(self, stock_code, limit=50):
        """
        抓取指定股票的上市公司公告。
        使用 akshare.stock_individual_notice_report，数据源为东方财富公告大全。
        :param stock_code: 6 位 A 股代码，如 "600519"
        :param limit: 最多返回条数
        :return: DataFrame[date, title, content, source, url]
        """
        if not stock_code or not str(stock_code).strip().isdigit():
            return pd.DataFrame(columns=["date", "title", "content", "source", "url"])

        code = str(stock_code).strip()
        if len(code) != 6:
            return pd.DataFrame(columns=["date", "title", "content", "source", "url"])

        if not _AK_OK:
            return pd.DataFrame(columns=["date", "title", "content", "source", "url"])

        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            df = _retry_request(
                lambda: ak.stock_individual_notice_report(
                    security=code, symbol="全部", begin_date=start, end_date=end
                ),
                max_retries=2, base_delay=2,
            )
            if df.empty:
                return pd.DataFrame(columns=["date", "title", "content", "source", "url"])

            df = df.rename(columns={
                "公告标题": "title",
                "公告类型": "category",
                "公告日期": "date",
                "网址": "url",
                "名称": "name",
            })
            df["content"] = df["title"]
            df["source"] = "eastmoney_announcement"
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            return df[["date", "title", "content", "source", "url"]].head(limit).dropna(subset=["title"])
        except Exception as e:
            print(f"[NewsFetcher] 个股公告抓取失败({code}): {e}")
            return pd.DataFrame(columns=["date", "title", "content", "source", "url"])

    def fetch_stock_events(self, stock_code=None, stock_name=None, keywords=None, limit=50):
        """
        为单只股票抓取专属事件列表。
        合并：
          1) 公司公告（公告类型标记为 eastmoney_announcement）
          2) 行业/板块相关新闻（按 keywords 过滤东方财富财经要闻、财新、央视）
        返回的 DataFrame 含 url，可直接点击跳转。
        """
        frames = []

        # 1) 公司公告
        if stock_code:
            try:
                ann_df = self._fetch_eastmoney_announcements(stock_code, limit=limit // 2)
                if not ann_df.empty:
                    frames.append(ann_df)
            except Exception as e:
                print(f"[NewsFetcher] 公告源失败: {e}")

        # 2) 板块新闻：用股票名称 + 行业关键词搜索
        keyword_parts = []
        if stock_name:
            keyword_parts.append(str(stock_name).strip())
        if keywords:
            if isinstance(keywords, str):
                keyword_parts.extend([k.strip() for k in keywords.split(",") if k.strip()][:5])
            elif isinstance(keywords, (list, tuple)):
                keyword_parts.extend([str(k).strip() for k in keywords if str(k).strip()][:5])

        keyword_str = " ".join(keyword_parts)

        if keyword_str:
            try:
                news_df = self.fetch(keyword=keyword_str, source="auto", limit=limit)
                if not news_df.empty:
                    frames.append(news_df)
            except Exception as e:
                print(f"[NewsFetcher] 板块新闻源失败: {e}")

        if not frames:
            return pd.DataFrame(columns=["date", "title", "content", "source", "url"])

        combined = pd.concat(frames, ignore_index=True)
        combined = combined.drop_duplicates(subset=["title"], keep="first")
        combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
        return combined.sort_values("date", ascending=False).head(limit).reset_index(drop=True)

    def fetch_semi_news(self, keyword="半导体", limit=50):
        """
        专门针对半导体行业的新闻抓取。
        自动使用扩展关键词（核心术语 + 龙头公司名）进行多次搜索并合并。
        """
        all_frames = []

        # 1. 用主关键词搜索
        main_df = self.fetch(keyword=keyword, source="auto", limit=limit)
        if not main_df.empty:
            all_frames.append(main_df)

        # 2. 用龙头公司名补充搜索（确保覆盖个股新闻）
        searched_titles = set(main_df["title"].tolist()) if not main_df.empty else set()
        company_names = self.semi_engine.get_search_keywords(category="companies")[:8]

        for company in company_names:
            if len(all_frames) * 30 > limit:
                break
            try:
                company_df = self.fetch(keyword=company, source="eastmoney_web", limit=15)
                if not company_df.empty:
                    # 过滤掉已存在的
                    new_mask = ~company_df["title"].isin(searched_titles)
                    new_df = company_df[new_mask]
                    if not new_df.empty:
                        all_frames.append(new_df)
                        searched_titles.update(new_df["title"].tolist())
            except Exception:
                continue

        if all_frames:
            combined = pd.concat(all_frames, ignore_index=True)
            combined = combined.drop_duplicates(subset=["title"], keep="first")
            combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
            return combined.sort_values("date", ascending=False).head(limit).reset_index(drop=True)

        return pd.DataFrame(columns=["date", "title", "content", "source", "url"])


# ──────────────────────────────────────────────
# 关键词提取器（不变）
# ──────────────────────────────────────────────

class KeywordExtractor:
    """关键词提取器（jieba TF-IDF + TextRank 融合）。"""

    DOMAIN_WORDS = [
        "事件驱动", "主线", "顺周期", "景气度", "供需缺口", "产能利用率",
        "渗透率", "国产替代", "专精特新", "碳中和", "新能源", "半导体",
        "光伏", "储能", "锂电", "煤炭", "有色", "化工", "军工", "消费",
        "医药", "房地产", "银行", "券商", "保险", "MLCC", "存储芯片",
        "动力电池", "稀土", "螺纹钢", "原油", "天然气",
        # 补充半导体领域词
        "晶圆代工", "先进封装", "Chiplet", "HBM", "CPO",
        "光刻机", "刻蚀机", "薄膜沉积", "CMP", "国产化率",
        "功率半导体", "碳化硅", "氮化镓", "IGBT", "MOSFET",
        "存储芯片", "MCU", "GPU", "FPGA", "SoC",
        "模拟芯片", "射频芯片", "电源管理", "CIS", "MEMS",
    ]

    def __init__(self):
        if _JIEBA_OK:
            for w in self.DOMAIN_WORDS:
                jieba.add_word(w)

    def extract(self, text, topk=8, method="hybrid"):
        if not text or not _JIEBA_OK:
            return []
        text = self._clean_text(text)
        if method == "tfidf":
            return jieba.analyse.extract_tags(text, topK=topk, withWeight=True)
        elif method == "textrank":
            return jieba.analyse.textrank(text, topK=topk, withWeight=True)
        elif method == "hybrid":
            tfidf = dict(jieba.analyse.extract_tags(text, topK=topk * 2, withWeight=True))
            textrank = dict(jieba.analyse.textrank(text, topK=topk * 2, withWeight=True))
            merged = {}
            all_words = set(tfidf.keys()) | set(textrank.keys())
            for w in all_words:
                score = tfidf.get(w, 0) * 0.6 + textrank.get(w, 0) * 0.4
                if w not in STOP_WORDS and len(w) >= 2:
                    merged[w] = score
            ranked = sorted(merged.items(), key=lambda x: x[1], reverse=True)
            return ranked[:topk]
        else:
            raise ValueError(f"不支持的方法: {method}")

    def extract_from_news(self, title, content="", topk=5):
        full_text = (title * 2) + " " + (content or "")
        return self.extract(full_text, topk=topk, method="hybrid")

    @staticmethod
    def _clean_text(text):
        text = re.sub(r"<[^>]+>", "", str(text))
        text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def batch_extract(self, news_df, topk=5):
        results = []
        for _, row in news_df.iterrows():
            kws = self.extract_from_news(row.get("title", ""), row.get("content", ""), topk)
            results.append({
                "date": row.get("date"),
                "title": row.get("title"),
                "keywords": [k[0] for k in kws],
                "keyword_weights": [round(k[1], 4) for k in kws],
            })
        return pd.DataFrame(results)


# ──────────────────────────────────────────────
# 情感分析器 v2（半导体增强版）
# ──────────────────────────────────────────────

class SentimentAnalyzer:
    """中文金融情感分析器 v2（增强半导体领域情感词典）。"""

    def __init__(self):
        self.positive = POSITIVE_WORDS
        self.negative = NEGATIVE_WORDS

    def analyze(self, text):
        """
        情感分析。
        :return: dict {sentiment, score(-1~1), pos_words[], neg_words[], intensity}
        """
        if not text:
            return self._default_result()

        text = str(text)

        pos_hits = [w for w in self.positive if w in text]
        neg_hits = [w for w in self.negative if w in text]
        pos_count = len(pos_hits)
        neg_count = len(neg_hits)

        snownlp_score = 0.5
        if _SNOW_OK and pos_count == 0 and neg_count == 0:
            try:
                s = SnowNLP(text)
                snownlp_score = s.sentiments
            except Exception:
                pass

        # 计算强度修饰词（非常/极度/显著/大幅）
        intensifiers = re.findall(r"(非常|极其|显著|大幅|急剧|持续|严重|深度)(?=的?[^\w])?", text)
        intensity_mod = 1.0 + min(len(intensifiers) * 0.15, 0.5) if intensifiers else 1.0

        if pos_count + neg_count > 0:
            raw = (pos_count - neg_count) / (pos_count + neg_count) * intensity_mod
        else:
            raw = (snownlp_score - 0.5) * 0.3

        score = round(max(-1.0, min(1.0, raw)), 3)

        if score > 0.15:
            sentiment = "正面"
        elif score < -0.15:
            sentiment = "负面"
        else:
            sentiment = "中性"

        # 判断是否为重大新闻（高绝对值分数）
        is_major = abs(score) >= 0.4

        return {
            "sentiment": sentiment,
            "score": score,
            "pos_words": pos_hits,
            "neg_words": neg_hits,
            "is_major": is_major,
            "intensity": round(intensity_mod, 2),
        }

    def analyze_news(self, title, content=""):
        """分析单条新闻情感（标题权重高）。"""
        full_text = (title * 3) + " " + (content or "")
        return self.analyze(full_text)

    def batch_analyze(self, news_df):
        results = []
        for _, row in news_df.iterrows():
            r = self.analyze_news(row.get("title", ""), row.get("content", ""))
            r["date"] = row.get("date")
            r["title"] = row.get("title")
            results.append(r)
        return pd.DataFrame(results)

    @staticmethod
    def _default_result():
        return {
            "sentiment": "中性", "score": 0.0,
            "pos_words": [], "neg_words": [],
            "is_major": False, "intensity": 1.0,
        }

    def sentiment_distribution(self, news_df):
        if news_df.empty:
            return {}
        analyzed = self.batch_analyze(news_df)
        dist = analyzed["sentiment"].value_counts().to_dict()
        total = len(analyzed)
        return {k: round(v / total * 100, 1) for k, v in dist.items()}


# ──────────────────────────────────────────────
# 新闻去重器
# ──────────────────────────────────────────────

class NewsDeduplicator:
    """
    新闻去重器。
    使用标题相似度（编辑距离/Jaccard）+ 内容指纹（SimHash思想）进行去重。
    """

    def __init__(self, similarity_threshold=0.75):
        self.threshold = similarity_threshold

    @staticmethod
    def _fingerprint(text):
        """生成文本的简化 MD5 指纹。"""
        clean = re.sub(r"\s+", "", str(text).lower())[:200]
        return hashlib.md5(clean.encode()).hexdigest()[:16]

    @staticmethod
    def _jaccard_similarity(s1, s2):
        """计算两个字符串的 Jaccard 相似度（基于字符级别 shingle）。"""
        if not s1 or not s2:
            return 0.0
        shingle_size = 3
        s1_set = set(s1[i:i + shingle_size] for i in range(len(s1) - shingle_size + 1))
        s2_set = set(s2[i:i + shingle_size] for i in range(len(s2) - shingle_size + 1))
        if not s1_set or not s2_set:
            return 0.0
        intersection = s1_set & s2_set
        union = s1_set | s2_set
        return len(intersection) / len(union)

    def deduplicate(self, news_df):
        """
        对新闻 DataFrame 进行去重。
        保留最早发布的版本。
        返回去重后的 DataFrame。
        """
        if news_df.empty or "title" not in news_df.columns:
            return news_df

        seen_fingerprints = set()
        seen_titles_similar = []  # [(fingerprint, title), ...]
        keep_indices = []

        for idx, row in news_df.iterrows():
            title = str(row.get("title", ""))

            # 快速路径：完全相同的标题
            fp = self._fingerprint(title)
            if fp in seen_fingerprints:
                continue

            # 慢速路径：相似标题
            is_dup = False
            for prev_fp, prev_title in seen_titles_similar:
                sim = self._jaccard_similarity(title, prev_title)
                if sim >= self.threshold:
                    is_dup = True
                    break

            if not is_dup:
                seen_fingerprints.add(fp)
                seen_titles_similar.append((fp, title))
                # 只保留最近的 N 个做比较（避免 O(N^2)）
                if len(seen_titles_similar) > 200:
                    seen_titles_similar.pop(0)
                keep_indices.append(idx)

        return news_df.loc[keep_indices].reset_index(drop=True)

    def deduplicate_with_merge(self, news_df):
        """
        去重 + 合并同质新闻。
        对于相似新闻，保留信息量最大的那条（标题最长），并在 content 中标记合并来源数。
        """
        deduped = self.deduplicate(news_df)
        deduped["_merge_count"] = 1
        deduped["_original_count"] = len(news_df)
        return deduped


# ──────────────────────────────────────────────
# 新闻摘要生成器
# ──────────────────────────────────────────────

class NewsSummarizer:
    """
    新闻摘要生成器。
    从多条新闻中提取关键信息，生成结构化摘要报告。
    """

    @staticmethod
    def generate_summary(news_df, top_k=10):
        """
        生成新闻摘要。
        :return: dict {
            total, date_range, sentiment_summary,
            major_events: [{title, sentiment, score, keywords}],
            hot_topics: [(topic, count)],
            key_stats: {positive_pct, negative_pct, neutral_pct, major_count}
        }
        """
        if news_df.empty:
            return {"total": 0, "major_events": [], "hot_topics": [], "key_stats": {}}

        total = len(news_df)

        # 时间范围
        dates = pd.to_datetime(news_df["date"], errors="coerce").dropna()
        date_range = f"{dates.min().strftime('%Y-%m-%d')} ~ {dates.max().strftime('%Y-%m-%d')}" if not dates.empty else "未知"

        # 情感统计（如果还没算过）
        analyzer = SentimentAnalyzer()
        if "sentiment" not in news_df.columns:
            analyzed = analyzer.batch_analyze(news_df)
            sentiments = analyzed["sentiment"].tolist()
            scores = analyzed["score"].tolist()
            is_major = analyzed.get("is_major", [False] * total).tolist()
        else:
            sentiments = news_df["sentiment"].tolist()
            scores = news_df.get("sentiment_score", [0.0] * total).tolist()
            is_major = news_df.get("is_major", [False] * total).tolist()

        pos_count = sum(1 for s in sentiments if s == "正面")
        neg_count = sum(1 for s in sentiments if s == "负面")
        neu_count = total - pos_count - neg_count

        # 重大事件（高绝对值分数或 is_major 标记）
        major_events = []
        for i, row in news_df.iterrows():
            sc = scores[i] if i < len(scores) else 0
            major = is_major[i] if i < len(is_major) else (abs(sc) >= 0.4)
            if major or abs(sc) >= 0.25:
                major_events.append({
                    "title": row.get("title", ""),
                    "sentiment": sentiments[i] if i < len(sentiments) else "中性",
                    "score": round(sc, 3),
                    "source": row.get("source", ""),
                    "date": str(row.get("date", ""))[:10],
                })

        # 排序：按情绪强度降序
        major_events.sort(key=lambda x: abs(x["score"]), reverse=True)
        major_events = major_events[:top_k]

        # 热门话题
        extractor = KeywordExtractor() if _JIEBA_OK else None
        topic_counter = Counter()
        if extractor and "content" in news_df.columns:
            for _, row in news_df.iterrows():
                kws = extractor.extract_from_news(
                    row.get("title", ""),
                    row.get("content", ""),
                    topk=3
                )
                for kw, _ in kws:
                    topic_counter[kw] += 1

        hot_topics = topic_counter.most_common(10)

        return {
            "total": total,
            "date_range": date_range,
            "key_stats": {
                "positive": pos_count,
                "negative": neg_count,
                "neutral": neu_count,
                "positive_pct": round(pos_count / total * 100, 1) if total > 0 else 0,
                "negative_pct": round(neg_count / total * 100, 1) if total > 0 else 0,
                "neutral_pct": round(neu_count / total * 100, 1) if total > 0 else 0,
                "major_count": len(major_events),
            },
            "major_events": major_events,
            "hot_topics": hot_topics,
        }


# ──────────────────────────────────────────────
# 新闻数据库（SQLite）
# ──────────────────────────────────────────────

class NewsDatabase:
    """
    新闻结构化数据库（SQLite）。
    支持按时间、板块、情感、股票等多维度查询。
    """

    def __init__(self, db_path="data/news.db"):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = os.path.join(base_dir, db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT DEFAULT '',
                url TEXT DEFAULT '',
                source TEXT DEFAULT '',
                date TEXT,
                inserted_at TEXT DEFAULT (datetime('now','localtime')),
                fingerprint TEXT UNIQUE,
                -- 分析字段
                sentiment TEXT DEFAULT '中性',
                sentiment_score REAL DEFAULT 0.0,
                is_major INTEGER DEFAULT 0,
                keywords TEXT DEFAULT '',
                related_stocks TEXT DEFAULT '',
                -- 元数据
                search_keyword TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_news_date ON news(date);
            CREATE INDEX IF NOT EXISTS idx_news_sentiment ON news(sentiment);
            CREATE INDEX IF NOT EXISTS idx_news_source ON news(source);
            CREATE INDEX IF NOT EXISTS idx_news_keyword ON news(search_keyword);
            CREATE INDEX IF NOT EXISTS idx_news_fp ON news(fingerprint);

            -- 板块配置表
            CREATE TABLE IF NOT EXISTS sectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                keywords TEXT NOT NULL,
                stock_codes TEXT DEFAULT '',
                description TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
        """)
        conn.commit()
        conn.close()

        # 初始化半导体板块
        self._init_sector("semiconductor")

    def _init_sector(self, sector_key):
        """预置板块数据。"""
        engine = SemiconductorKeywordEngine()
        if sector_key == "semiconductor":
            codes = ",".join(engine.get_all_semi_codes())
            names = ",".join(engine.get_search_keywords(category="companies"))
            core = ",".join(engine.get_search_keywords(category="core")[:30])
            self.upsert_sector(
                name="半导体",
                keywords=f"{core},{names}",
                stock_codes=codes,
                description="A股半导体全产业链：设计/制造/封测/设备/材料"
            )

    def save_news(self, news_df, search_keyword=""):
        """
        批量保存新闻到数据库（自动去重）。
        :return: (新增数量, 总数量)
        """
        if news_df.empty:
            return 0, 0

        conn = self._get_conn()
        new_count = 0
        try:
            for _, row in news_df.iterrows():
                title = str(row.get("title", "")).strip()
                if not title:
                    continue

                fp = hashlib.md5(title.encode()).hexdigest()[:16]

                # 检查是否已存在
                existing = conn.execute(
                    "SELECT id FROM news WHERE fingerprint = ?", (fp,)
                ).fetchone()

                if existing:
                    continue

                sentiment = row.get("type", row.get("sentiment", "中性"))
                score = row.get("sentiment_score", row.get("score", 0.0))

                # 序列化 keywords
                kws = row.get("keywords", "")
                if isinstance(kws, list):
                    kws = ",".join(str(k) for k in kws)

                conn.execute("""
                    INSERT INTO news (title, content, url, source, date,
                                      fingerprint, sentiment, sentiment_score,
                                      keywords, search_keyword)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    title,
                    str(row.get("content", ""))[:2000],
                    str(row.get("url", ""))[:500],
                    str(row.get("source", "")),
                    str(row.get("date", ""))[:19],
                    fp,
                    str(sentiment),
                    float(score) if score else 0.0,
                    kws,
                    search_keyword,
                ))
                new_count += 1

            conn.commit()
        finally:
            total = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
            conn.close()

        return new_count, total

    def query(self, **filters):
        """
        多维度查询新闻。
        支持 filters: keyword, sentiment, source, date_from, date_to,
                       stock_code, is_major, limit, offset, order_by
        """
        conn = self._get_conn()
        try:
            where = []
            params = []

            if filters.get("keyword"):
                where.append("(title LIKE ? OR content LIKE ? OR keywords LIKE ?)")
                kw = f"%{filters['keyword']}%"
                params.extend([kw, kw, kw])

            if filters.get("sentiment"):
                where.append("sentiment = ?")
                params.append(filters["sentiment"])

            if filters.get("source"):
                where.append("source = ?")
                params.append(filters["source"])

            if filters.get("date_from"):
                where.append("date >= ?")
                params.append(filters["date_from"])

            if filters.get("date_to"):
                where.append("date <= ?")
                params.append(filters["date_to"])

            if filters.get("is_major"):
                where.append("is_major = 1")

            if filters.get("search_keyword"):
                where.append("search_keyword = ?")
                params.append(filters["search_keyword"])

            where_clause = " AND ".join(where) if where else "1=1"

            order_by = filters.get("order_by", "inserted_at DESC")
            limit = filters.get("limit", 50)
            offset = filters.get("offset", 0)

            sql = f"""SELECT * FROM news
                      WHERE {where_clause}
                      ORDER BY {order_by}
                      LIMIT ? OFFSET ?"""
            params.extend([limit, offset])

            df = pd.read_sql_query(sql, conn, params=params)
            return df
        finally:
            conn.close()

    def get_sentiment_trend(self, days=30, keyword=None):
        """获取情感趋势（按天聚合）。"""
        conn = self._get_conn()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            where = "date >= ?"
            params = [cutoff]
            if keyword:
                where += " AND (title LIKE ? OR keywords LIKE ?)"
                kw = f"%{keyword}%"
                params.extend([kw, kw])

            sql = f"""
                SELECT date,
                       COUNT(*) as total,
                       SUM(CASE WHEN sentiment='正面' THEN 1 ELSE 0 END) as positive,
                       SUM(CASE WHEN sentiment='负面' THEN 1 ELSE 0 END) as negative,
                       SUM(CASE WHEN sentiment='中性' THEN 1 ELSE 0 END) as neutral,
                       AVG(sentiment_score) as avg_score
                FROM news
                WHERE {where}
                GROUP BY date
                ORDER BY date
            """
            return pd.read_sql_query(sql, conn, params=params)
        finally:
            conn.close()

    def get_hot_keywords(self, days=7, top_k=20):
        """热门关键词统计。"""
        conn = self._get_conn()
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            rows = conn.execute(
                """SELECT keywords FROM news
                   WHERE date >= ? AND keywords != ''""",
                (cutoff,)
            ).fetchall()
            counter = Counter()
            for (kws,) in rows:
                for kw in kws.split(","):
                    kw = kw.strip()
                    if len(kw) >= 2:
                        counter[kw] += 1
            return counter.most_common(top_k)
        finally:
            conn.close()

    def upsert_sector(self, name, keywords, stock_codes="", description=""):
        """更新或插入板块配置。"""
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO sectors (name, keywords, stock_codes, description)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    keywords=excluded.keywords,
                    stock_codes=excluded.stock_codes,
                    description=excluded.description
            """, (name, keywords, stock_codes, description))
            conn.commit()
        finally:
            conn.close()


# ──────────────────────────────────────────────
# 事件挖掘器 v2（集成全部能力）
# ──────────────────────────────────────────────

class EventMiner:
    """
    事件挖掘器 v2：新闻抓取 → 关键词提取 → 情感分析 → 去重 → 入库 → 摘要
    """

    def __init__(self, config_path="config.yaml"):
        self.news_fetcher = NewsFetcher()
        self.keyword_extractor = KeywordExtractor()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.deduplicator = NewsDeduplicator(similarity_threshold=0.72)
        self.summarizer = NewsSummarizer()
        self.semi_engine = SemiconductorKeywordEngine()
        self.db = NewsDatabase()

        import yaml
        from .fetcher import load_config
        self.config = load_config(config_path)
        self.event_csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            self.config.get("events", {}).get("file", "data/events.csv")
        )

    def mine_events(self, keyword=None, source="auto", limit=30, auto_save=True):
        """
        完整挖掘流程：抓取 → 去重 → 分析 → 入库
        :return: DataFrame[date, ticker, title, type, keywords, sentiment_score, source, url, is_major]
        """
        # 1. 选择抓取策略
        if keyword and self.semi_engine.is_semi_related(keyword):
            news = self.news_fetcher.fetch_semi_news(keyword=keyword, limit=limit)
        else:
            news = self.news_fetcher.fetch(keyword=keyword, source=source, limit=limit)

        if news.empty:
            return pd.DataFrame()

        # 2. 去重
        original_count = len(news)
        news = self.deduplicator.deduplicate(news)
        deduped_count = len(news)

        events = []
        for _, row in news.iterrows():
            title = str(row.get("title", ""))
            content = str(row.get("content", ""))
            source_name = str(row.get("source", ""))

            # 3. 关键词提取
            kws = self.keyword_extractor.extract_from_news(title, content, topk=5)
            kw_list = [k[0] for k in kws]

            # 4. 情感分析
            sentiment = self.sentiment_analyzer.analyze_news(title, content)

            # 5. 股票代码提取（增强版：也匹配半导体龙头）
            ticker = self._extract_ticker_enhanced(title + " " + content, keyword)

            events.append({
                "date": row.get("date"),
                "ticker": ticker or "",
                "title": title,
                "type": sentiment["sentiment"],
                "keywords": ",".join(kw_list),
                "sentiment_score": sentiment["score"],
                "source": source_name,
                "url": row.get("url", ""),
                "is_major": sentiment.get("is_major", False),
                "intensity": sentiment.get("intensity", 1.0),
                "pos_words": ",".join(sentiment.get("pos_words", [])),
                "neg_words": ",".join(sentiment.get("neg_words", [])),
            })

        events_df = pd.DataFrame(events)

        # 6. 入库
        if auto_save and not events_df.empty:
            new_cnt, total = self.db.save_news(events_df, keyword)
            print(f"[EventMiner] 新增 {new_cnt} 条，总计 {total} 条")

            # 同时存到旧 CSV 格式（兼容）
            self._save_events_csv(events_df)

        # 附加元信息
        if not events_df.empty:
            events_df.attrs["original_count"] = original_count
            events_df.attrs["deduped_count"] = deduped_count

        return events_df

    def _extract_ticker_enhanced(self, text, context_keyword=None):
        """增强版股票代码/名称提取。"""
        # A. 标准 6 位代码
        match = re.search(r"(?<!\d)(6\d{5}|0\d{5}|3\d{5})(?!\d)", text)
        if match:
            return match.group(1)

        # B. 半导体公司名匹配
        for code, (name, _) in self.semi_engine.SEMI_LEADERS.items():
            if name in text:
                return code

        # C. 上下文关键词匹配
        if context_keyword and context_keyword.isdigit() and len(context_keyword) == 6:
            return context_keyword

        return ""

    def _save_events_csv(self, events_df):
        """兼容旧的 CSV 存储。"""
        os.makedirs(os.path.dirname(self.event_csv_path), exist_ok=True)
        existing = pd.DataFrame()
        if os.path.exists(self.event_csv_path):
            existing = pd.read_csv(self.event_csv_path, encoding="utf-8-sig")

        csv_cols = ["date", "ticker", "title", "type", "keywords", "sentiment_score", "source"]
        to_save = events_df[[c for c in csv_cols if c in events_df.columns]].copy()

        if existing.empty:
            combined = to_save
        else:
            combined = pd.concat([existing, to_save], ignore_index=True)
            combined = combined.drop_duplicates(subset=["title"], keep="last")

        combined.to_csv(self.event_csv_path, index=False, encoding="utf-8-sig")

    def auto_mine_events(self, keyword=None, source="eastmoney", limit=30):
        """兼容旧接口。"""
        return self.mine_events(keyword=keyword, source=source, limit=limit)

    def generate_report(self, keyword=None, limit=50):
        """
        生成完整的新闻分析报告。
        :return: report dict（同 NewsSummarizer.generate_summary + 更多）
        """
        news = self.news_fetcher.fetch(keyword=keyword, source="auto", limit=limit)
        if news.empty:
            return {"total": 0, "top_keywords": [], "sample_news": [],
                    "positive_pct": 0, "negative_pct": 0, "neutral_pct": 0}

        # 去重 + 分析
        news = self.deduplicator.deduplicate(news)
        analyzed = self.sentiment_analyzer.batch_analyze(news)

        # 合并回原 DataFrame
        for col in ["sentiment", "score", "is_major", "pos_words", "neg_words"]:
            if col in analyzed.columns:
                news[col] = analyzed[col].values

        # 保存
        self.db.save_news(news, keyword or "")

        # 摘要
        summary = self.summarizer.generate_summary(news)

        # 样本新闻
        sample_news = []
        major = analyzed[analyzed.get("is_major", False)] if "is_major" in analyzed.columns else pd.DataFrame()
        if not major.empty:
            for _, row in major.head(5).iterrows():
                sample_news.append({
                    "title": row.get("title", "")[:80],
                    "sentiment": row.get("sentiment", ""),
                    "score": row.get("score", 0),
                    "source": row.get("source", ""),
                })
        else:
            for _, row in analyzed.head(5).iterrows():
                sample_news.append({
                    "title": row.get("title", "")[:80],
                    "sentiment": row.get("sentiment", ""),
                    "score": row.get("score", 0),
                    "source": row.get("source", ""),
                })

        summary.update({
            "top_keywords": summary.get("hot_topics", [])[:15],
            "sample_news": sample_news,
            "positive_pct": summary.get("key_stats", {}).get("positive_pct", 0),
            "negative_pct": summary.get("key_stats", {}).get("negative_pct", 0),
            "neutral_pct": summary.get("key_stats", {}).get("neutral_pct", 0),
        })
        return summary

    def sentiment_report(self, keyword=None, limit=50):
        """兼容旧接口。"""
        return self.generate_report(keyword=keyword, limit=limit)

    def get_hot_keywords(self, days=7, topk=20):
        """获取热门关键词（从 DB）。"""
        return self.db.get_hot_keywords(days=days, top_k=topk)

    def alert_check(self, stock_code=None, hours=6):
        """
        重大新闻预警检查。
        查询最近 N 小时内的重大新闻，判断是否需要推送预警。
        :return: list of alert dicts
        """
        since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
        query_params = {"date_from": since, "is_major": True, "limit": 20}

        if stock_code:
            query_params["keyword"] = stock_code

        alerts = self.db.query(**query_params)

        results = []
        for _, row in alerts.iterrows():
            score = row.get("sentiment_score", 0)
            results.append({
                "title": row.get("title", ""),
                "sentiment": row.get("sentiment", ""),
                "score": float(score),
                "source": row.get("source", ""),
                "date": str(row.get("date", ""))[:16],
                "alert_level": "HIGH" if abs(score) >= 0.5 else ("MEDIUM" if abs(score) >= 0.3 else "LOW"),
                "action": "关注" if score > 0.2 else ("回避" if score < -0.2 else "观望"),
            })

        # 按紧急程度排序
        results.sort(key=lambda x: abs(x["score"]), reverse=True)
        return results
