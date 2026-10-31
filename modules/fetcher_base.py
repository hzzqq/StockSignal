"""fetcher_base — StockFetcher 共享基类（类属性 + 基础设施 helper + __init__）。"""

import io
import json
import os
import re
import sqlite3
import threading
import time
import warnings
import logging as _logging
import urllib.request
import urllib.error
import urllib.parse
import contextlib
import socket  # 捕获瞬时网络错误（超时/连接重置/DNS）做重试兜底
from datetime import datetime, timedelta
import concurrent.futures as _cf
import yaml  # load_config 用到；原在抽离块内，抽到 _feed_io 后在此补回
import pandas as pd  # 原在抽离块内，StockFetcher 大量使用 DataFrame
import numpy as np  # 原在抽离块内，StockFetcher 用到 np.

from modules.time_utils import now_cst_str, now_cst_naive


# 底层 I/O 层已抽到 modules._feed_io（P2-1 降耦），此处 re-export 保持全站 import 兼容
from modules._feed_io import (  # noqa: F401
    _safe_urlopen,
    logger,
    _AK_OK,
    _BS_OK,
    CONFIG,
    SOURCE_METRICS,
    _record_source_metric,
    _observe_log,
    observe_source,
    observe_cache_fallback,
    observe_cache_hit,
    get_source_metrics,
    _is_market_open,
    _is_midday_break,
    _validate_sector_data,
    _retry_request,
    _symbol_to_secid,
    _index_to_secid,
    _symbol_to_bs,
    _symbol_to_sina,
    _BaoStockFetcher,
    _SinaFetcher,
    _UrllibFetcher,
)

# 市场数据 I/O 叶子模块（#锐评整改：从 StockFetcher 下沉，零循环依赖）
import modules._market_data_io as _mdi

# T-247 Tier1.1：纯函数真身迁 modules.fetcher_core，此处 re-export 同一对象
# （调用点零改动；AST 守卫 tests/test_fetcher_core_tier11.py 锁死防本地定义回潮）
from modules.fetcher_core import (  # noqa: F401
    _df_last_date,
    _get_sina_prefix,
    _get_stock_industry_keywords,
    _proc_cache_get,
    _proc_cache_set,
    _resample_kline,
    _resolve_cache_db_path,
    _safe_ident,
    _safe_kline_df,
    _synth_us_index_intraday,
    SAFE_IDENT_RE,
)

# 代理 IP 池（免费，best-effort 抗封禁）：仅当 SS_PROXY_POOL=1 时启用。
# 通过进程级 HTTPS_PROXY/HTTP_PROXY 让 akshare / requests 继承轮换出口 IP。
# 初始化失败绝不影响主流程（akshare 仍可直连）。baostock 是账号级限流，不受本池影响。
try:
    from modules.proxy_pool import get_proxy_pool as _get_proxy_pool
    _pp = _get_proxy_pool()
    if _pp.enabled:
        _pp.apply_to_env()
except Exception as _pp_err:  # noqa: BLE001
    logger.warning("代理 IP 池初始化失败（已忽略，回退直连）: %s", _pp_err)


# Tier1.1 安全拆分 pilot：纯函数 _safe_json_loads 迁入 modules.fetcher_core，
# 此处 re-export 保持行为零变化（fetcher.py 内部 509/519/547/1174 行调用不受影响）。
from modules.fetcher_core import _safe_json_loads  # noqa: F401



# __init__ 直接调用本模块 load_config；_ensure_stock_db 用 flag，延迟读 fetcher 模块。
import modules.fetcher as _fetcher_mod



# 搬 load_config 逐字（含 def 行）
def load_config(config_path="config.yaml"):
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class BaseFetcher:

    """
    股票行情与宏观数据采集器。
    四级降级链：akshare -> BaoStock -> 新浪 -> 东方财富(urllib) -> 缓存兜底
    """

    _SAFE_IDENT_RE = SAFE_IDENT_RE

    _safe_ident = staticmethod(_safe_ident)

    _stock_df = None          # DataFrame(code, name)

    _name_to_code = {}        # {name: code} 精确映射

    _code_to_name = {}        # {code: name} 反向映射

    _pinyin_initials_cache = {}  # {name: initials} 拼音首字母缓存（性能关键）

    _pinyin_initials_variants_cache = {}  # {name: {initials variants}} 多音字首字母组合缓存

    _stocks_loaded = False    # 是否已加载

    _fund_cache = {}          # {code: (ts, fundamentals dict)} 进程内TTL缓存（基本面日频，#406）

    _biz_cache = {}           # {code: (ts, 核心业务描述 str)} 进程内TTL缓存（主营构成，#406）

    _proc_cache_get = staticmethod(_proc_cache_get)

    _proc_cache_set = staticmethod(_proc_cache_set)

    _INDEX_SINA_PREFIX = {
        "000001": "sh", "000016": "sh", "000010": "sh", "000009": "sh",
        "000300": "sh", "000688": "sh", "000905": "sh",
        "399001": "sz", "399006": "sz", "399005": "sz", "399300": "sz",
        "399673": "sz", "399006": "sz", "399102": "sz", "399103": "sz",
    }

    _INDUSTRY_KEYWORDS = {
        # ── 能源 / 资源 ──
        frozenset(["煤炭", "煤业", "能源", "神华", "中煤", "兖矿", "潞安", "西山", "平煤", "阳泉", "盘江", "兰花"]):
            ["煤炭", "动力煤", "焦煤", "保供", "电厂库存", "长协价", "坑口价", "产能"],
        frozenset(["石油", "石化", "海油", "油气", "杰瑞", "中曼", "洲际", "博迈"]):
            ["原油", "天然气", "油价", "炼化", "乙烯", "PX", "勘探", "页岩气"],
        frozenset(["电力", "电建", "水电", "火电", "核电", "风电", "光伏发电", "绿电", "粤电力", "浙能", "华能", "国电", "大唐", "华电", "国投", "川投", "申能", "福能"]):
            ["电力", "电价", "装机容量", "利用小时数", "新能源", "绿电", "火电", "水电", "风电", "光伏", "核电"],
        frozenset(["有色", "铜", "铝", "锂矿", "稀土", "黄金", "钨", "钼", "锌", "锡", "铂"]):
            ["有色金属", "铜", "铝", "锂", "稀土", "黄金", "钨", "钴", "镍", "大宗商品", "库存周期"],


        # ── 金融 ──
        frozenset(["银行", "农商", "农信", "城商", "平安银行", "招商银行", "工商银行", "建设银行", "农业银行", "中国银行", "交通银行", "邮储", "兴业", "浦发", "中信", "民生", "光大", "华夏", "北京银行", "江苏银行", "宁波银行", "南京银行", "杭州银行", "成都银行", "长沙银行", "重庆银行", "贵阳银行", "西安银行", "郑州银行", "苏州银行", "青岛银行"]):
            ["银行", "贷款", "净息差", "不良率", "拨备覆盖率", "存款", "信贷", "LPR", "MLF", "降息"],
        frozenset(["券商", "证券", "东方财富", "中信证券", "华泰证券", "国泰君安", "银河证券", "广发证券", "招商证券", "海通证券", "申万宏源", "光大证券", "国信证券"]):
            ["证券", "经纪业务", "投行", "自营", "两融", "成交量", "IPO", "基金", "资管", "牛市"],
        frozenset(["保险", "人寿", "人保", "太保", "新华", "平安寿险", "泰康", "中国平安", "平安"]):
            ["保险", "保费收入", "投资收益", "偿付能力", "新业务价值", "利率", "长端利率", "权益投资"],
        frozenset(["信托", "租赁", " AMC ", "资产管理", "不良资产"]):
            ["信托", "资产管理", "不良资产处置", "融资租赁", "ABS", "REITs"],


        # ── 科技 / 电子 / 半导体 ──
        frozenset(["科技", "电子", "信息", "软件", "通信", "网络", "互联", "数据", "云计算", "大数据", "人工智能", "AI", "芯片", "半导体", "集成电路", "存储", "传感器", "PCB", "连接器", "线缆", "光模块", "光纤", "LED", "液晶", "显示", "面板", "消费电子", "智能", "物联网", "5G", "6G", "深科技", "中兴", "华为", "小米概念", "立讯精密", "工业富联", "歌尔", "闻泰科技", "韦尔股份", "兆易创新", "北方华创", "中芯国际", "寒武纪", "海光信息", "澜起科技", "紫光国微", "卓胜微", "圣邦股份", "斯达半导", "新洁能", "扬杰科技", "士兰微", "晶方科技", "通富微电", "长电科技", "华天科技", "京东方", "TCL科技", "三安光电", "水晶光电", "欧菲光", "蓝思科技", "领益智造", "立讯", "鹏鼎控股", "东山精密", "深南电路", "沪电股份", "胜宏科技"]):
            ["科技", "半导体", "芯片", "电子", "AI", "人工智能", "云计算", "数据中心", "国产替代", "消费电子", "5G", "6G", "存储芯片", "GPU", "CPU", "先进封装", "HBM", "CPO", "光模块", "PCB", "被动元件", "MLCC", "面板", "OLED", "Mini LED", "Micro LED", "传感器", "物联网", "车规级", "汽车电子", "边缘计算", "算力", "大模型", "AIGC", "信创"],
        frozenset(["计算机", "IT服务", "软件开发", "SaaS", "用友", "金山办公", "恒生电子", "同花顺", "大智慧", "金蝶", "广联达", "卫宁健康", "创业慧康", "久远银海", "中科创达", "德赛西威", "中科创达", "科大讯飞", "三六零", "奇安信", "深信服", "安恒信息", "绿盟科技", "启明星辰", "美亚柏科", "太极股份", "中国软件", "海量数据", "星环科技"]):
            ["计算机", "软件", "SaaS", "云计算", "数字经济", "信创", "国产软件", "ERP", "金融科技", "医疗信息化", "网络安全", "数据安全", "密码学", "隐私计算", "数字政府", "智慧城市", "工业互联网", "MES", "CAD", "EDA", "操作系统", "数据库", "中间件", "大模型应用", "AI Agent"],


        # ── 新能源 / 电动车 ──
        frozenset(["新能源", "电池", "储能", "锂电", "宁德时代", "比亚迪", "亿纬锂能", "国轩高科", "欣旺达", "德赛电池", "璞泰来", "恩捷股份", "星源材质", "天赐材料", "当升科技", "容百科技", "杉杉股份", "中伟股份", "华友钴业", "赣锋锂业", "天齐锂业", "盐湖股份", "藏格矿业", "盛新锂能", "雅化集团", "永兴材料", "科达利"]):
            ["新能源", "锂电池", "储能", "动力电池", "正极", "负极", "电解液", "隔膜", "碳酸锂", "氢氧化锂", "锂盐", "钠离子电池", "固态电池", "4680", "麒麟电池", "刀片电池", "CTP", "CTC", "换电", "充电桩", "虚拟电厂", "VPP"],
        frozenset(["光伏", "太阳能", "硅料", "硅片", "组件", "逆变器", "EVA胶膜", "玻璃", "背板", "接线盒", "隆基绿能", "通威股份", " TCL 中环", "阳光电源", "锦浪科技", "固德威", "禾迈股份", "昱能科技", "德业股份", "福斯特", "福莱特", "信义光能", "大全能源", "合盛硅业", "石英股份"]):
            ["光伏", "太阳能", "硅料", "硅片", "电池片", "组件", "逆变器", "EVA", "POE", "玻璃", "背板", "N型", "TOPCon", "HJT", "BC", "钙钛矿", "分布式光伏", "集中式光伏", "BIPV", "光伏建筑一体化", "储能逆变器", "微型逆变器", "跟踪支架"],
        frozenset(["风能", "风电", "风机", "叶片", "塔筒", "铸件", "齿轮箱", "轴承", "变流器", "海缆", "明阳智能", "金风科技", "运达股份", "电气风电", "中材科技", "天顺风能", "大金重工", "海力风电", "新强联", "日月股份", "双一科技", "时代新材", "中际联合"]):
            ["风电", "风机", "海上风电", "陆上风电", "叶片", "塔筒", "铸件", "齿轮箱", "变流器", "海缆", "大型化", "漂浮式风电", "分散式风电", "老旧改造", "运维", "储能配套"],
        frozenset(["整车", "汽车", "电动", "比亚迪", "长城汽车", "长安汽车", "上汽集团", "广汽集团", "理想汽车", "蔚来", "小鹏汽车", "赛力斯", "江淮汽车", "吉利", "一汽", "东风", "北汽", "小康"]):
            ["新能源汽车", "电动车", "智能驾驶", "自动驾驶", "ADAS", "激光雷达", "毫米波雷达", "HUD", "座舱", "域控制器", "线控底盘", "一体化压铸", "热管理", "轻量化", "出海", "出口", "渗透率", "销量", "订单"] ,


        # ── 医药 / 生物 ──
        frozenset(["医药", "生物制药", "中药", "化学药", "疫苗", "医疗器械", "诊断", "CXO", "创新药", "恒瑞医药", "药明康德", "爱尔眼科", "通策医疗", "迈瑞医疗", "联影医疗", "乐普医疗", "鱼跃医疗", "智飞生物", "沃森生物", "长春高新", "片仔癀", "云南白药", "同仁堂", "以岭药业", "东阿阿胶", "华润三九", "白云山", "济川药业", "科伦药业", "健康元", "丽珠集团"]):
            ["医药", "创新药", "生物药", "中药", "化学药", "仿制药", "集采", "医保谈判", "CXO", "CDMO", "CRO", "疫苗", "医疗器械", "IVD", "高值耗材", "医疗服务", "医美", "辅助生殖", "细胞治疗", "基因治疗", "ADC", "GLP-1", "减肥药", "阿尔茨海默", "老龄化", "DRG/DIP"],


        # ── 消费 ──
        frozenset(["白酒", "酒类", "茅台", "五粮液", "泸州老窖", "洋河", "汾酒", "古井贡酒", "今世缘", "舍得酒业", "酒鬼酒", "水井坊", "老白干", "顺鑫农业", "迎驾贡酒", "口子窖"]):
            ["白酒", "次高端", "高端酒", "大众酒", "批价", "库存周期", "动销", "渠道", "宴席", "礼赠", "酱香", "浓香", "清香"],
        frozenset(["食品", "饮料", "乳制品", "调味品", "预制菜", "休闲食品", "速冻食品", "肉制品", "烘焙", "伊利股份", "蒙牛", "海天味业", "中炬高新", "千禾味业", "涪陵榨菜", "安井食品", "三全食品", "绝味食品", "洽洽食品", "桃李面包", "巴比食品", "元气森林"]):
            ["食品饮料", "乳制品", "啤酒", "调味品", "预制菜", "休闲食品", "速冻", "餐饮供应链", "成本下行", "原材料价格", "提价", "渠道下沉", "新品", "健康化", "零糖", "功能性"],
        frozenset(["家电", "美的", "格力", "海尔", "小家电", "厨电", "黑电", "老板电器", "苏泊尔", "九阳股份", "石头科技", "科沃斯", "海信视像", "海信家电", "TCL", "长虹", "创维"]):
            ["家电", "白电", "黑电", "厨电", "小家电", "清洁电器", "扫地机", "洗地机", "集成灶", "洗碗机", "以旧换新", "出海", "外销", "内需", "地产后周期", "竣工链"],
        frozenset(["免税", "零售", "商贸", "超市", "百货", "电商", "跨境电商", "化妆品", "珠宝", "酒店", "旅游", "餐饮", "免税店", "中国中免", "王府井", "永辉超市", "家家悦", "步步高", "红旗连锁", "爱婴室", "珀莱雅", "贝泰妮", "上海家化", "华熙生物", "爱美客", "锦江酒店", "首旅酒店", "同庆楼", "海底捞", "九毛九"]):
            ["零售", "免税", "化妆品", "医美", "黄金珠宝", "酒店", "旅游出行", "餐饮", "跨境电商", "直播电商", "即时零售", "社区团购", "折扣零售", "奥特莱斯", "会员制", "体验经济", "国潮"],


        # ── 地产 / 建筑 / 基建 ──
        frozenset(["房地产", "地产", "开发", "物业", "万科", "保利发展", "龙湖集团", "碧桂园", "融创", "新城控股", "招商蛇口", "金地集团", "华侨城", "绿地控股", "华润置地", "滨江集团", "华发股份", "越秀地产"]):
            ["房地产", "销售面积", "销售额", "房价", "土地储备", "拿地", "融资", "债务", "保交楼", "城中村改造", "保障房", "物管", "商业地产", "REITs", "LPR", "限购松绑", "因城施策", "二手房", "挂牌量"],
        frozenset(["建筑", "基建", "工程", "施工", "装饰", "园林", "设计", "咨询", "中铁", "中交", "中建", "中冶", "电建", "葛洲坝", "隧道股份", "上海建工", "四川路桥", "安徽建工", "山东路桥", "北方国际", "中工国际", "中钢国际", "中国化学"]):
            ["基建", "建筑工程", "PPP", "专项债", "一带一路", "海外工程", "装配式建筑", "BIM", "绿色建筑", "城市更新", "旧改", "水利", "轨道交通", "市政", "PPP存量", "REITs", "央企改革"],


        # ── 军工 / 航天 ──
        frozenset(["军工", "航空", "航天", "船舶", "兵器", "核工业", "中航沈飞", "航发动力", "洪都航空", "中航西飞", "中直股份", "航天彩虹", "中国卫星", "海防", "中国重工", "中国船舶", "中船防务", "中兵红箭", "内蒙一机", "北方导航", "睿创微纳", "菲利华", "光威复材", "中简科技", "图南股份", "西部超导", "抚顺特钢", "钢研高纳"]):
            ["军工", "航空航天", "战斗机", "发动机", "导弹", "无人机", "卫星", "雷达", "电子信息", "舰船", "核潜艇", "装甲", "弹药", "特种材料", "碳纤维", "高温合金", "隐身材料", "北斗", "商业航天", "低空经济", "eVTOL", "军费预算", "采购周期", "军民融合"],


        # ── 交通运输 ──
        frozenset(["港口", "航运", "物流", "机场", "航空", "快递", "高速", "铁路", "中远海控", "招商轮船", "中谷物流", "顺丰控股", "圆通速递", "韵达股份", "申通快递", "京东物流", "上海机场", "白云机场", "深圳机场", "首都机场", "宁沪高速", "招商公路", "京沪高铁", "大秦铁路", "广深铁路"]):
            ["航运", "港口", "集运", "干散货", "油运", "BDI", "CCFI", "SCFI", "快递", "物流", "航空客运", "民航", "免税购物", "机场", "高速公路", "通行费", "铁路货运", "铁运", "多式联运", "跨境物流", "冷链"],


        # ── 化工 / 材料 ──
        frozenset(["化工", "化学", "材料", "聚氨酯", "MDI", "TDI", "纯碱", "烧碱", "PVC", "化肥", "磷肥", "钾肥", "氮肥", "农药", "涂料", "万华化学", "华鲁恒升", "龙佰集团", "云天化", "华谊集团", "三友化工", "中泰化学", "新疆天业", "巨化材料", "三棵树"]):
            ["化工", "MDI", "TDI", "聚氨酯", "纯碱", "烧碱", "PVC", "化肥", "磷化工", "氟化工", "钛白粉", "有机硅", "新材料", "可降解塑料", "电子化学品", "湿电子化学品", "锂电材料", "光伏材料", "半导体材料", "碳中和", "能耗双控", "供给侧改革"],


        # ── 机械 / 设备 ──
        frozenset(["机械", "设备", "机床", "工程机械", "机器人", "自动化", "智能制造", "三一重工", "中联重科", "徐工机械", "恒立液压", "浙江鼎力", "安徽合力", "杭叉集团", "汇川技术", "埃斯顿", "绿的谐波", "拓斯达", "伊之密", "豪迈科技", "杰瑞股份", "中海油服", "石化机械", "天地科技", "郑煤机"]):
            ["工程机械", "挖掘机", "起重机", "混凝土机械", "高空作业平台", "工业母机", "数控机床", "机器人", "人形机器人", "减速器", "伺服系统", "PLC", "工业自动化", "智能制造", "激光设备", "3D打印", "锂电设备", "光伏设备", "半导体设备", "油服", "煤矿机械", "农机", "出口替代"],


        # ── 农业 / 农产品 ──
        frozenset(["农业", "种业", "养殖", "畜牧", "饲料", "农产品", "水产", "牧原股份", "温氏股份", "新希望", "海大集团", "圣农发展", "益生股份", "民和股份", "隆平高科", "登海种业", "大北农", "荃银高科", "北大荒", "苏垦农发", "中粮糖业", "金龙鱼", "中粮科技"]):
            ["农业", "生猪", "猪周期", "能繁母猪", "存栏量", "出栏量", "饲料原料", "玉米", "豆粕", "种业", "转基因", "粮食安全", "农产品价格", "白糖", "棉花", "油脂", "养殖户利润", "疫病防控", "预制食材", "中央厨房"],


        # ── 传媒 / 游戏 / 教育 ──
        frozenset(["传媒", "影视", "游戏", "动漫", "出版", "广告", "教育", "在线教育", "腾讯", "网易游戏", "三七互娱", "完美世界", "吉比特", "恺英网络", "神州泰岳", "中文传媒", "凤凰传媒", "中南传媒", "芒果超媒", "光线传媒", "万达电影", "中国电影", "分众传媒", "蓝色光标", "三人行", "值得买"]):
            ["传媒", "游戏", "AIGC", "元宇宙", "VR/AR", "短剧", "影视剧", "院线", "广告营销", "数字营销", "直播带货", "版权", "IP运营", "出版", "教育", "职业教育", "K12", "素质教育", "体育赛事", "线下演出", "演唱会经济"],
    }

    _safe_kline_df = staticmethod(_safe_kline_df)

    _resample_kline = staticmethod(_resample_kline)


    def _ak_ssl_context():
        """临时关闭 requests 的 SSL 验证，用于 akshare 在代理/证书环境异常时。

        部分数据源（东方财富 push2）在本地系统代理后会触发 SSLCertVerificationError。
        SSL 关闭逻辑已收敛到 modules.ssl_helper.ssl_bypass（#404）：patch 的是
        Session.request（覆盖 get + akshare 内部所有走 Session 的请求），比旧版只 patch
        Session.get 覆盖更全；仍是局部生效、退出恢复，不污染全局。
        """
        from modules.ssl_helper import ssl_bypass
        with ssl_bypass():
            yield

    def _get_conn(self):
        # T-257：WAL + busy_timeout——默认回滚日志模式下每次缓存写入全库排他锁，
        # 页面读被写阻塞（15:30 预热窗口/实时刷新时段页面卡顿同源）。WAL 读写并行，
        # busy_timeout 让偶发写锁由「抛错」变「短等待」。journal_mode 持久化，重复执行为 no-op。
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError as e:  # noqa: BLE001 - 只读/异常场景如实降级
            logger.debug(f"[fetcher] PRAGMA 设置降级: {e}")
        return conn

    def _warmup_stock_db(cls):
        """预热股票库到内存（类级别缓存，所有实例共享，只加载一次）。"""
        if cls._stocks_loaded:
            return
        try:
            import time as _time
            t0 = _time.time()
            # 用默认配置创建临时实例来加载数据
            temp = cls.__new__(cls)
            temp.config = load_config("config.yaml")
            db_path = _resolve_cache_db_path(temp.config.get("database", {}).get("path"))
            temp.db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path
            )
            os.makedirs(os.path.dirname(temp.db_path), exist_ok=True)
            df = temp._ensure_stock_db()
            if not df.empty:
                cls._stock_df = df
                cls._name_to_code = dict(zip(df["name"].astype(str), df["code"].astype(str)))
                cls._code_to_name = dict(zip(df["code"].astype(str), df["name"].astype(str)))
                # 预计算拼音首字母缓存（一次性324ms，后续每次查询省掉）
                t_py = _time.time()
                for name in df["name"].astype(str):
                    cls._pinyin_initials_cache[name] = cls._pinyin_static(name)
                    cls._pinyin_initials_variants_cache[name] = cls._pinyin_initials_variants(name)
                logger.debug(f"[StockFetcher] 拼音缓存预计算: {len(cls._pinyin_initials_cache)} 只 ({_time.time()-t_py:.2f}s)")
                logger.debug(f"[StockFetcher] 股票库预热完成: {len(df)} 只 ({_time.time()-t0:.2f}s)")
            cls._stocks_loaded = True
        except Exception as e:
            logger.info(f"[StockFetcher] 股票库预热失败: {e}")
            cls._stocks_loaded = True  # 标记已尝试，避免反复重试

    def _init_cache_table(self, conn, table_name):
        table_name = self._safe_ident(table_name)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                cache_key   TEXT PRIMARY KEY,
                data_json   TEXT,
                updated_at  TEXT
            )
        """)
        conn.commit()

    def _read_cache(self, conn, table_name, cache_key, max_age_hours=None, max_age_seconds=None, as_dataframe=True):
        self._init_cache_table(conn, table_name)
        row = conn.execute(
            f"SELECT data_json, updated_at FROM {table_name} WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            logger.debug(f"[CACHE] MISS key={cache_key} table={table_name} (无缓存条目)")
            return None
        updated_at = datetime.fromisoformat(row[1])
        if max_age_seconds is not None:
            max_age = timedelta(seconds=max_age_seconds)
        elif max_age_hours is not None:
            max_age = timedelta(hours=max_age_hours)
        else:
            max_age = timedelta(days=self.cache_days)
        age = now_cst_naive() - updated_at
        if age < max_age:
            age_s = age.total_seconds()
            age_str = f"{age_s/3600:.1f}h" if age_s >= 3600 else f"{age_s/60:.1f}m"
            logger.debug(f"[CACHE] HIT  key={cache_key} table={table_name} age={age_str}")
            if not as_dataframe:
                return _safe_json_loads(row[0])
            # 如果缓存的是 DataFrame（原格式），返回 DataFrame
            try:
                df = pd.read_json(io.StringIO(row[0]))
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")
                return df
            except Exception as e:
                logger.warning(f"[fetcher] 处理异常: {e}")
                # 非 DataFrame JSON（如实时行情字典），返回原始 dict/list
                return _safe_json_loads(row[0])
        return None

    def _read_stale_cache(self, conn, table_name, prefix, as_dataframe=True,
                          adjust=None, start=None, end=None, min_rows=1):
        """读取过期缓存（用于降级兜底）。排除 _source 等元数据键。

        as_dataframe=True（默认）：按 DataFrame 解析（daily/index/sector 等时序数据）；
        as_dataframe=False：按 JSON 原始 dict/list 解析（实时行情等）。

        T-248 一致性过滤（诚实语义，验收基线 docs/data_cache_hardening.md 第1步）：
        - adjust 一致：只考虑键以 ``_{adjust}`` 结尾的行——qfq/none 价格不可比，
          修复前 qfq 请求会静默命中 none 旧行拿到不可比价格序列；
        - 窗口裁剪：返回前裁剪到 [start, end]（旧行窗口可能与本次请求不同）；
        - 行数下限：裁剪后不足 ``min_rows`` 视为无有效兜底（宁可诚实失败不喂碎片）；
        - 不传 adjust/start/end 时维持旧语义（取最新一行），兼容既有调用方。
        """
        self._init_cache_table(conn, table_name)
        sql = (f"SELECT cache_key, data_json, updated_at FROM {table_name} "
               f"WHERE cache_key LIKE ? AND cache_key NOT LIKE ? ")
        params: list = [f"{prefix}%", f"%_source"]
        if adjust:
            sql += "AND cache_key LIKE ? "
            params.append(f"%_{adjust}")
        sql += "ORDER BY updated_at DESC LIMIT 8"
        rows = conn.execute(sql, params).fetchall()
        for cache_key, data_json, updated_at_str in rows:
            if not as_dataframe:
                return _safe_json_loads(data_json)
            try:
                df = pd.read_json(io.StringIO(data_json))
            except Exception as e:  # noqa: BLE001 - 损坏行跳过试下一候选
                logger.warning(f"[fetcher] 兜底缓存解析失败 key={cache_key}: {e}")
                continue
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
            if start and end and "date" in df.columns:
                df = df[(df["date"] >= pd.Timestamp(start))
                        & (df["date"] <= pd.Timestamp(end))]
            if len(df) < min_rows:
                logger.debug(f"[fetcher] 兜底缓存窗口裁剪后仅 {len(df)} 行(<{min_rows})，"
                             f"拒绝喂碎片 key={cache_key}")
                continue
            age_hours = (
                now_cst_naive() - datetime.fromisoformat(updated_at_str)
            ).total_seconds() / 3600
            logger.debug(f"[StockFetcher] 使用过期缓存 {cache_key} (已过期 {age_hours:.1f} 小时)")
            warnings.warn(
                f"数据源不可用，正在使用 {age_hours:.1f} 小时前的缓存数据",
                UserWarning, stacklevel=4,
            )
            return df
        return None

    def _write_cache(self, conn, table_name, cache_key, data):
        self._init_cache_table(conn, table_name)
        if isinstance(data, pd.DataFrame):
            data_json = data.to_json(orient="records", date_format="iso")
        else:
            data_json = json.dumps(data, ensure_ascii=False, default=str)
        conn.execute(
            f"INSERT OR REPLACE INTO {table_name} (cache_key, data_json, updated_at) "
            f"VALUES (?, ?, ?)",
            (cache_key, data_json, now_cst_naive().isoformat()),
        )
        conn.commit()

    def _write_cache_raw(self, conn, table_name, cache_key, json_str):
        """写入原始 JSON 字符串到缓存表。"""
        self._init_cache_table(conn, table_name)
        conn.execute(
            f"INSERT OR REPLACE INTO {table_name} (cache_key, data_json, updated_at) "
            f"VALUES (?, ?, ?)",
            (cache_key, json_str, now_cst_naive().isoformat()),
        )
        conn.commit()

    def _get_sina_prefix(self, ticker: str) -> str:
        """根据 6 位代码返回新浪市场前缀 sh/sz，正确处理指数代码。

        真身迁 modules.fetcher_core（T-247 Tier1.1，index_map 作参数注入）；
        领域常量 _INDEX_SINA_PREFIX 留本类（仅此消费）。
        """
        return _get_sina_prefix(ticker, self._INDEX_SINA_PREFIX)

    def _ensure_stock_db(self):
        """
        确保全量股票基本信息已加载到本地 SQLite。
        首次调用从 BaoStock 拉取，之后永久缓存（股票基本信息极少变化）。
        返回 DataFrame(code, name) 或空 DataFrame。
        """
        conn = self._get_conn()
        try:
            table_name = "all_stocks"
            self._init_cache_table(conn, table_name)

            # 检查缓存是否存在
            row = conn.execute(
                f"SELECT data_json FROM {table_name} WHERE cache_key = 'all'"
            ).fetchone()
            if row is not None:
                data = _safe_json_loads(row[0])
                if data is None:
                    return pd.DataFrame(columns=["code", "name"])
                return pd.DataFrame(data)

            # 缓存未命中 -> 从 BaoStock 拉取
            if not _fetcher_mod._BS_OK:
                return pd.DataFrame(columns=["code", "name"])

            logger.info("[StockFetcher] 正在从 BaoStock 加载全量股票列表...")
            import baostock as bs
            if not _BaoStockFetcher._ensure_login():
                return pd.DataFrame(columns=["code", "name"])
            rs = bs.query_stock_basic()
            if rs.error_code != "0":
                return pd.DataFrame(columns=["code", "name"])

            rows = []
            while (rs.error_code == "0") and rs.next():
                row_data = rs.get_row_data()
                if len(row_data) >= 2 and row_data[0] and row_data[1]:
                    # code 格式: sh.600519 -> 提取纯数字部分
                    code = row_data[0].replace("sh.", "").replace("sz.", "")
                    name = row_data[1]
                    # 过滤：仅保留正常A股个股（排除指数、基金、ETF、债券等）
                    code_int = int(code) if code.isdigit() else 0
                    is_valid_stock_range = (
                        (600000 <= code_int <= 609999) or   # 上海主板
                        (1 <= code_int <= 4999) or          # 深圳主板+中小板（超000001起）
                        (300000 <= code_int <= 309999) or   # 创业板
                        (688000 <= code_int <= 689999)      # 科创板
                    )
                    exclude_keywords = [
                        "指数", "综指", "公司债", "企债", "国债", "转债",
                        "基金", "ETF", "LOF", "回购", "期货", "期权", "债券",
                        "ST", "*ST", "PT", "退市", "优先股",
                        "上证", "深证", "中盘", "小盘", "全指", "中小",
                        "A股", "B股", "H股",
                    ]
                    # 额外规则：过滤纯板块名（无个股特征）
                    generic_names = {"A股资源", "消费服务", "食品饮料", "有色金属", "信息技术",
                                     "医药生物", "金融地产", "能源化工", "公用事业", "可选消费",
                                     "主要消费", "工业制造", "电信服务"}
                    if (
                        name and len(code) == 6 and is_valid_stock_range
                        and not any(kw in name for kw in exclude_keywords)
                        and name not in generic_names
                    ):
                        rows.append({"code": code, "name": name})

            # 复用连接：此处不 logout，下次还能用

            all_stocks = pd.DataFrame(rows)
            logger.debug(f"[StockFetcher] 全量股票加载完成: {len(all_stocks)} 只")

            # 写入永久缓存
            self._write_cache_raw(
                conn, table_name, "all",
                json.dumps(all_stocks.to_dict(orient="records"), ensure_ascii=False),
            )
            return all_stocks
        except Exception as e:
            logger.info(f"[StockFetcher] 加载全量股票失败: {e}")
            return pd.DataFrame(columns=["code", "name"])
        finally:
            conn.close()

    def _pinyin_static(name):
        """获取拼音首字母（纯函数，无副作用，用于缓存）。"""
        from modules._search_utils import pinyin_initials_static
        return pinyin_initials_static(name)

    def _pinyin_initials_variants(name):
        """
        获取股票名称的所有拼音首字母组合（处理多音字）。
        如 '长电科技' -> {'ZDKJ', 'CDKJ'}。
        """
        from modules._search_utils import pinyin_initials_variants
        return pinyin_initials_variants(name)

    def _pinyin_full(name):
        """获取股票名称的完整拼音（小写无空格）。如 '贵州茅台' -> 'guizhoumaotai'。"""
        from modules._search_utils import pinyin_full
        return pinyin_full(name)

    def _pinyin_initials(name):
        """
        获取股票名称的拼音首字母（大写）。
        优先从类缓存读取（预热时已预计算），避免重复调用pypinyin。
        如 '招商银行' -> 'ZSYH'。
        """
        cached = _fetcher_mod.StockFetcher._pinyin_initials_cache.get(name)
        if cached is not None:
            return cached
        return _fetcher_mod.StockFetcher._pinyin_static(name)

    def _name_tokens(name):
        """
        将股票名称拆分为搜索用的中文分词 token。
        覆盖常见的简称模式：首字+尾字、中间词、2-gram等。
        如 '招商银行' -> {'招商', '银行', '招', '商', '银', '行', '商银', '招商银', '商银行'}
        """
        from modules._search_utils import name_tokens
        return name_tokens(name)

    def _get_latest_price(self, code):
        """从日线缓存中获取最近一个交易日的收盘价。返回 (price, date_str) 或 (None, None)。"""
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT data_json, updated_at FROM daily_cache "
                    "WHERE cache_key LIKE ? ORDER BY updated_at DESC LIMIT 1",
                    (f"{code}%",),
                ).fetchone()
                if row is not None:
                    df = pd.read_json(io.StringIO(row[0]))
                    if not df.empty and "close" in df.columns:
                        latest = df.iloc[-1]
                        return float(latest["close"]), str(latest["date"])[:10]
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"[fetcher] 处理异常: {e}")
        return None, None

    def _lookup_name_for_code(self, code):
        """代码->名称（从内存缓存 O(1) 查找）。"""
        return self._code_to_name.get(code, "")

    def __init__(self, config_path="config.yaml"):
        self.config = load_config(config_path)
        db_path = _resolve_cache_db_path(self.config.get("database", {}).get("path"))
        self.db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path
        )
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.cache_days = self.config.get("default", {}).get("cache_days", 7)
        # 实例化时预热股票库（首次较慢，后续毫秒级）
        self._warmup_stock_db()

