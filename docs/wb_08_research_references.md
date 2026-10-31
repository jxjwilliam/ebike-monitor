# 竞品与参考项目调研

> 文档编号：wb_08  
> 创建日期：2026-10-30  
> 文档定位：在线调研的同类应用、开源项目、技术参考，用于指导本项目开发

---

## 1. 调研概述

本文档汇总了与"电单车多平台车辆分布数据采集系统"相关的在线调研结果，覆盖四个维度：

1. 共享单车数据采集爬虫项目（技术方案直接参考）
2. 城市级共享单车监测平台（政府/城管视角，业务逻辑参考）
3. 国际开源标准与规范（数据模型设计参考）
4. 技术栈层面的直接参考（框架与算法）

---

## 2. 共享单车数据采集爬虫项目

### 2.1 共享单车实时数据爬虫（Python + 可视化热力图）

- **来源**：[CSDN 实战教程](https://blog.csdn.net/2201_76125261/article/details/148165106)（2025-05）
- **方案**：用 Python 异步爬虫（asyncio + aiohttp）实时采集共享单车地理分布数据，解析车辆坐标并聚合统计，绘制热力图，部署 API 供前端使用
- **可参考点**：
  - 异步采集架构设计（asyncio + aiohttp 批量请求）
  - 车辆坐标聚合统计方法
  - 热力图可视化展示思路
- **与本项目差异**：该项目直接爬 API，本项目走截图路线（合规考虑）

### 2.2 爬取 6 万条共享单车数据并分析（附代码）

- **来源**：[微信公众号技术文章](https://mp.weixin.qq.com/s?__biz=MzI1MjQ2OTQ3Ng==&mid=2247486887)（2017-11）
- **方案**：爬取摩拜单车成都约 6 万辆车数据，分析车辆类型分布（55% 标准车 / 44% Lite）、空闲率（三成车辆无移动）、位置聚类
- **可参考点**：
  - "三成车辆没有移动"的分析方法 → 对应本项目的"流出数=0"判断逻辑
  - 批量车辆数据处理的数据结构设计
  - 车辆类型分布统计思路
- **局限**：2017 年项目，API 早已变更，但数据分析思路仍有效

### 2.3 共享单车大数据分析系统（Hadoop + Spark）

- **来源**：[CSDN](https://blog.csdn.net/weixin_33402252/article/details/163557981)（2026-08）
- **方案**：用 Scrapy 构建分布式爬虫集群，每日定时从各平台 API 抓取车辆状态数据，用 Hadoop+Spark 处理 TB 级数据，输出车辆分布热力图、骑行轨迹聚类、高峰时段预测
- **可参考点**：
  - 分布式爬虫架构思路（本项目规模化到 12 城时可能需要）
  - 车辆分布热力图的业务逻辑
  - TB 级数据处理的架构选型参考
- **与本项目差异**：规模和量级远大于本项目当前阶段，但规模化后可参考

### 2.4 共享单车数据爬取与可视化分析

- **来源**：[CSDN](https://blog.csdn.net/weixin_39887531/article/details/111097724)（2020-12）
- **方案**：Python 爬取共享单车数据，用 pandas/matplotlib/seaborn 做可视化分析
- **可参考点**：
  - 数据清洗和预处理流程
  - 可视化图表类型选择（分布图、趋势图、热力图）

---

## 3. 城市级共享单车监测平台

### 3.1 南宁共享电单车智能监测系统 ⭐ 高度相关

- **来源**：[广西住建厅](http://zjt.gxzf.gov.cn/xwdt/dsdt/t27168892.shtml)（2026-01）
- **方案**：南宁市引入 AI 技术，依托城市运行管理服务平台，构建"AI+大数据"智慧监管体系，搭建智能监测系统，实现"感知—预警—处置—核验"全流程闭环管理，推动共享电单车淤堵点位由上线初期的 30~40 个下降至个位数
- **高度相关原因**：
  - 本项目试点城市就是南宁
  - 监测对象同样是美团/哈啰/青桔三家电单车
  - "感知—预警—处置—核验"闭环与本项目"采集→校验→人工核对→交付"流程高度吻合
- **可参考点**：
  - 南宁的点位划分逻辑和淤堵点位识别方法
  - AI 辅助决策的具体应用场景
  - 淤堵点位从 30-40 个降到个位数的治理路径
- **调研建议**：可深入了解该系统的技术供应商和具体技术方案

### 3.2 共享单车数据终端（硬件采集方案）

- **来源**：[百家号](https://baijiahao.baidu.com/s?id=1774262128601067726)（2023-08）
- **方案**：固定安装的硬件数据终端，采集半径 150-200 米范围内所有共享单车，通过蓝牙嗅探等技术识别各品牌车辆数量，结合云平台判断车辆是否过多、辅助调度
- **可参考点**：
  - 硬件采集方案的思路（如果后期想降低 App 截图依赖）
  - 多品牌车辆识别技术（蓝牙广播 MAC 地址前缀区分品牌）
  - 半径 150-200m 的采集范围与本项目 100m×100m 围栏的对比
- **局限**：硬件成本高，无法获取"流入流出"精确数据，仅能做时点计数
- **B 站视频**：[共享单车数量检测黑科技](https://www.bilibili.com/video/BV1vSWYzhECU/)（2025-10）

### 3.3 重庆高新区"城市大脑"共享单车管理

- **来源**：[重庆市政府网](https://www.cq.gov.cn/ywdt/zwhd/bmdt/202506/t20250619_14725533.html)（2025-06）
- **方案**：一屏掌控 2.9 万辆共享单车，显示美团/青桔/哈啰各平台车辆配置总额，668 个点位，7 个街道，方圆 200 平方公里。支持点击查看点位订单情况，长期不产生订单的点位预警
- **可参考点**：
  - 多平台汇总看板的 UI 设计思路
  - 点位级车辆配置监控逻辑
  - 点位异常预警机制（长期无订单 → 对应本项目的"车辆数突变检测"）

### 3.4 "一网统管"南宁创新共享电单车智能管理

- **来源**：[山西新闻网](https://www.sxrb.com/content/202509/16/c14854.html)（2025-09）
- **方案**：南宁实现智能采集、智能派遣、AI 辅助决策、共享电单车监测及精品线路保障
- **可参考点**：与 3.1 同一体系，补充了"智能派遣"和"精品线路保障"的业务场景

---

## 4. 国际开源标准与规范

### 4.1 MDS (Mobility Data Specification) ⭐ 架构参考

- **来源**：[GitHub - openmobilityfoundation/mobility-data-specification](https://github.com/openmobilityfoundation/mobility-data-specification)
- **维护方**：Open Mobility Foundation (OMF)
- **定位**：城市与出行服务商之间的标准化数据接口规范，支持地理围栏、车辆状态、行程数据等双向通信
- **与本项目的关系**：MDS 定义的数据模型与本项目的核心数据字段高度吻合
- **可参考点**：

#### MDS status_changes 数据结构 → 对应本项目的流入流出

```
MDS 字段:
  - vehicle_id        → 车辆唯一标识
  - event_type        → registered / available / reserved / absent / removed
  - event_location    → 事件发生位置 (geography)
  - event_time        → 事件时间
  - battery_pct       → 电量百分比

本项目对应:
  - 车辆位置变化 → 流入/流出判断
  - event_type=available 且位置在围栏内 → 车辆数+1
  - event_type=absent 且原位置在围栏内 → 流出+1
```

#### MDS trips 数据结构 → 对应本项目的疑似调度

```
MDS 字段:
  - trip_id           → 行程唯一标识
  - vehicle_id        → 车辆标识
  - route             → 行程路线 (GeoJSON LineString)
  - start_location    → 起点
  - end_location      → 终点

本项目对应:
  - 短时间大量同起点→终点 → 疑似调度入
```

#### MDS geofencing → 对应本项目的围栏定义

```
MDS 字段:
  - geofence_area     → GeoJSON MultiPolygon
  - rules             → 规则（允许/禁止骑行、停车等）

本项目对应:
  - fence (PostGIS POLYGON) → 100m×100m 围栏
```

- **特别建议**：本项目 PostgreSQL Schema 可参考 MDS 的数据字段定义，甚至可以直接兼容 MDS 格式输出，提升数据的通用性

### 4.2 GBFS (General Bikeshare Feed Specification)

GBFS 就是 General Bikeshare Feed Specification，通用共享单车数据规范。

简单说，它是共享单车行业约定的一套公开实时 JSON 格式，让任何 App、地图、研究者都能用同一种方式读到“现在哪有车”。它只管实时状态，不管历史订单。核心就一个入口加几张表：
- gbfs.json：发现文件，列出这个系统提供了哪些接口，就像目录
- system_information：系统名字、运营方、时区这些基本信息
- station_information：有桩系统的站点位置、容量
- station_status：每个站点现在剩几辆车、几个空位，要求尽量实时，最迟不超过 5 分钟
- free_bike_status（v2）/ vehicle_status（v3）：无桩系统的每辆车经纬度、车型、是否被预约或故障

- **来源**：[GitHub - MobilityData/gbfs](https://github.com/MobilityData/gbfs) / [NABSA/gbfs](https://github.com/NABSA/gbfs)
- **维护方**：MobilityData
- **定位**：共享单车的开放数据标准，Bird、Lime 等国际平台均支持，提供实时车辆位置、可用性、站点状态
- **国际平台支持情况**：

| 平台 | GBFS 支持 | 说明 |
|------|-----------|------|
| Bird | ✅ | 提供实时车辆位置 GBFS feed |
| Lime | ✅ | 提供实时车辆位置 GBFS feed |
| 美团 | ❌ | 不开放 |
| 滴滴 | ❌ | 不开放 |
| 哈啰 | ❌ | 不开放 |

- **关键洞察**：国际上共享单车数据是标准化的开放 API，但中国三家平台不开放 GBFS，这正是本项目必须走"截图+AI数车"路线的根本原因
- **可参考点**：
  - `station_status.json` 的数据结构 → 点位状态设计
  - `free_bike_status.json` 的车辆实时位置格式 → 车辆数据表设计
  - 如果未来中国平台开放 GBFS，本系统可以平滑对接

### 4.3 GitHub micromobility 主题

- **来源**：[github.com/topics/micromobility](https://github.com/topics/micromobility)
- **相关项目**：
  - `openmobilityfoundation/mds-open-api` — MDS 的 OpenAPI 描述
  - 多个用 Python 做 e-scooter 数据分析的项目
  - geopandas + 空间分析示例
- **可参考点**：空间分析工具链（geopandas、shapely）的使用方式

### 4.4 MDS 与其他出行标准的比较

- **来源**：[CSDN](https://blog.csdn.net/gitblog_00502/article/details/155292895)（2026-07）
- **对比**：

| 标准 | 全称 | 定位 | 与本项目关系 |
|------|------|------|-------------|
| MDS | Mobility Data Specification | 城市与运营商双向通信 | 数据模型参考 |
| GBFS | General Bikeshare Feed Specification | 共享单车实时数据开放标准 | 数据格式参考 |
| CDS | Curb Data Specification | 路侧停车/装卸数据 | 不相关 |
| GTFS | General Transit Feed Specification | 公共交通数据 | 不相关 |

---

## 5. 技术栈层面的直接参考

### 5.1 Airtest（本项目采集框架）

- **来源**：[Airtest 官方文档](https://airtest.doc.io.netease.com/) / [Airtest 开源项目](https://airtest-new.nie.netease.com/opensource)
- **开发方**：网易
- **核心能力**：
  - 基于图像识别的 UI 自动化（touch/wait/exists/swipe）
  - Poco 框架：UI 元素级操控（适用于 Android/iOS/Unity/Cocos2d）
  - 跨平台支持：Android 原生 App、iOS、Windows、Web（Selenium 插件）
  - AirtestIDE：可视化脚本编辑和调试工具
- **适用场景评估**：
  - ✅ 地图界面按钮定位（图像匹配"骑单车"入口）
  - ✅ 截图功能（snapshot() 自带元数据）
  - ✅ 多设备管理（connect_device 支持多设备）
  - ⚠️ 主要用于游戏测试，商业 App 自动化操控案例较少
  - ⚠️ 可能需要额外处理 App 的反自动化检测

### 5.2 Appium（备选采集框架）

- **来源**：[Appium 官方](https://dpgraham.github.io/) / [Appium 文档](https://developer.baidu.com/article/detail.html?id=5935630)
- **核心能力**：
  - 基于 WebDriver 协议的移动 App 自动化
  - UI 元素定位：ID / Accessibility ID / XPath / UIAutomator2
  - Appium Inspector：可视化元素查看工具
  - 跨平台：Android + iOS
- **与 Airtest 对比**：

| 对比项 | Airtest | Appium |
|--------|---------|--------|
| 操控方式 | 图像识别为主 | UI 元素定位为主 |
| 地图界面适用性 | ⭐⭐⭐⭐⭐（图像匹配无需元素 ID） | ⭐⭐（地图内无 UI 元素可定位） |
| 社区生态 | 中（游戏测试为主） | 高（移动测试标准工具） |
| 中文 App 兼容性 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Python 支持 | 原生 | 客户端库 |

- **选型结论**：本项目选用 Airtest，因为电单车 App 的地图界面无法通过 UI 元素 ID 定位按钮，必须依赖图像匹配

### 5.3 YOLOv8 图标检测

- **学术论文参考**：[An Improved YOLOv8 Algorithm for Icon Detection in Vehicle Dashboard](http://xueshu.baidu.com/s?wd=paperuri:(194r0xf0es5j04w0j42k0ts0ca137864))（2024）
- **做了什么**：用 YOLOv8 检测车载仪表盘上的图标，解决公开数据集缺乏的问题
- **与本项目的关系**：与"检测 App 截图中的电单车图标"场景高度类似——都是小目标图标检测
- **可参考点**：
  - 图标检测的 YOLOv8 改进方案（小目标检测优化）
  - 图标数据集的构建和标注方法
  - 缺乏公开数据集时的解决方案（自建+数据增强）

### 5.4 YOLOv8 车辆检测系统（无人机视角）

- **来源**：[CSDN](https://blog.csdn.net/weixin_33212799/article/details/169385877)（2026-10）
- **方案**：无人机视角下用 YOLOv8 检测车辆，自定义骨干网络（GhostBottleneck + CBAM 注意力机制）
- **可参考点**：
  - 小目标检测的模型结构优化思路
  - GhostBottleneck 轻量化设计（降低推理延迟）

### 5.5 SIFT 特征匹配用于车辆识别

- **来源**：[Rutgers 大学论文](https://rucore.libraries.rutgers.edu/rutgers-lib/53656/PDF/1/)
- **做了什么**：通过 SIFT 特征匹配识别对向车道的唯一车辆，估计车速
- **与本项目的关系**：
  - SIFT 匹配做车辆唯一性识别 → 但本项目场景中同品牌车辆图标外观一致，SIFT 不适合做车辆匹配
  - SIFT 更适合做**截图配准**（对齐同一品牌不同时间点的截图边界）→ 这正是本项目的用法
- **结论**：SIFT 在本项目中用于图像配准而非车辆识别

---

## 6. 商业平台参考

### 6.1 Ride Layer

- **来源**：[ridelayer.com](https://ridelayer.com/)
- **定位**：城市出行（电单车/滑板车/IoT/充电桩）的软件平台，提供运营管理、车队管理、消费者 App、社区租赁等
- **参考价值**：后台管理面板设计、车辆分布可视化、车队调度逻辑

### 6.2 Wunder Mobility

- **来源**：[wundermobility.com](https://wundermobility.com/)
- **定位**：白标共享出行软件平台，提供骑手 App（iOS/Android）、管理后台、车队调度、多区域/多国家支持
- **参考价值**：产品架构和管理后台 UI 设计参考

### 6.3 EazyRide

- **来源**：[eazyride.io](https://www.eazyride.io/)
- **定位**：白标滑板车 & 共享单车软件
- **参考价值**：品牌化 App 的快速部署思路

### 6.4 Roamr

- **来源**：[getroamr.com](https://getroamr.com/)
- **定位**：微出行 & LSV 车队管理平台，提供 IoT 跟踪、无钥匙激活、车队管理
- **参考价值**：IoT 设备管理、车队追踪界面设计

---

## 7. 美团/滴滴 API 逆向相关参考

### 7.1 美团外卖 Token 逆向实战

- **来源**：[CSDN](https://blog.csdn.net/2201_76125261/article/details/162165404)（2026-06）
- **做了什么**：从反编译到 Python 爬虫全流程，解析美团外卖 Token 生成逻辑（AES-256-CBC + RSA-4096 + 时间戳）
- **可参考点**：
  - 美团 App 的风控体系演进（第 4 代：设备指纹+行为轨迹+环境感知）
  - Frida 动态插桩的具体用法
  - JADX 反编译分析流程
- **对 API 逆向探索（wb_07）的启示**：美团的风控已经非常成熟，逆向难度极高，验证了本项目"截图为主路线"的正确性

### 7.2 美团 mtgsig 加密算法解析

- **来源**：[CSDN](https://blog.csdn.net/weixin_33690367/article/details/85521176)（2026-04）
- **做了什么**：解析美团 API 的 mtgsig 1.2 签名算法
- **可参考点**：美团 API 签名机制的演进路径，逆向工程工具链

### 7.3 共享单车数据可视化分析

- **来源**：[CSDN](https://blog.csdn.net/weixin_39887531/article/details/111097724)（2020-12）
- **做了什么**：Python 爬取共享单车数据并用 pandas 做分析
- **可参考点**：数据清洗和可视化分析的基础流程

---

## 8. 调研总结与推荐

### 8.1 最值得深入研究的 3 个参考

| 优先级 | 参考项目 | 理由 | 行动建议 |
|--------|---------|------|---------|
| ⭐⭐⭐ | **南宁共享电单车智能监测系统** | 同一城市、同一行业、同一目标，"感知-预警-处置-核验"流程与本项目高度吻合 | 深入了解该系统的技术供应商和具体方案 |
| ⭐⭐⭐ | **MDS (Mobility Data Specification)** | 开源的出行数据标准，数据模型设计可以直接参考，特别是 status_changes 和 trips 数据结构 | 对照 MDS 规范优化本项目数据库 Schema |
| ⭐⭐ | **GBFS (General Bikeshare Feed Specification)** | 国际共享单车数据标准，理解中国平台不开放数据的现状 | 参考 GBFS 的 free_bike_status.json 设计车辆数据表 |

### 8.2 技术栈验证

| 本项目选型 | 参考项目/标准 | 验证结论 |
|-----------|-------------|---------|
| Airtest（采集） | Airtest 官方文档 + 社区 | ✅ 适用于地图界面图像匹配操控 |
| YOLOv8（检测） | 学术论文 + CSDN 实战 | ✅ 图标检测场景验证可行，需自建数据集 |
| SIFT（配准） | Rutgers 大学论文 | ✅ 适用于截图配准，不适用于车辆匹配 |
| 截图方案（合规） | GBFS 标准缺失 | ✅ 中国平台不开放 GBFS，截图是唯一合规方案 |

### 8.3 新发现的机会

| 机会 | 来源 | 可行性 |
|------|------|--------|
| 兼容 MDS 格式输出 | MDS 规范 | 中 — 增加数据通用性，但甲方未要求 |
| 硬件数据终端补充采集 | 共享单车数据终端 | 低 — 成本高，但可作为特定点位的交叉验证手段 |
| 与南宁智能监测系统对接 | 南宁住建厅 | 待验证 — 需了解该系统是否对外开放数据接口 |
