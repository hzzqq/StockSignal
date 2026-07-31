# StockSignal 公共模块包。
# 首次 import modules.* 时自动安装统一网络韧性护栏（requests + socket 双层默认超时），
# 根治 akshare 等库在代理/上游挂起时的「无限阻塞 / 页面卡死」问题。幂等。
from modules.netguard import install_network_guard

install_network_guard()
