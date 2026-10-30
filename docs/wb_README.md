# 电单车多平台车辆分布数据采集系统

> 共享电单车竞品数据监测平台 — 自动化采集美团(MT)、滴滴(DD)、哈啰(HB)三家平台的车辆实时分布数据

---

## 项目简介

本项目为乙方（供应商）承接的共享电单车竞品数据监测系统。通过自动化操控三家电单车平台App截图，结合YOLOv8目标检测和图像比对算法，定期输出各城市各点位的车辆分布、流入流出和疑似调度数据。

### 核心指标

| 指标 | 值 |
|------|-----|
| 覆盖城市 | 12个 |
| 时段数 | 4个（周中/周末 × 早/晚高峰） |
| 每城市点位数 | 20个 |
| 总点位数 | 960个 |
| 覆盖平台 | 3家（MT / DD / HB） |
| 单期截图数 | ~20,160张 |
| 采集频率 | 每10分钟一轮，每点位7轮（1小时） |
| 围栏范围 | 100m × 100m 正方形 |
| 坐标系 | GCJ-02 |
| 项目周期 | 长期，每月一期 |

---

## 系统架构图

```mermaid
graph TB
    subgraph Frontend["前端管理面板"]
        UI["React + Ant Design"]
        UI --> P1["任务管理"]
        UI --> P2["点位管理"]
        UI --> P3["数据看板"]
        UI --> P4["人工核对"]
        UI --> P5["报告导出"]
    end

    subgraph API["API服务层"]
        BE["FastAPI Backend"]
        BE --> A1["任务接口"]
        BE --> A2["数据查询"]
        BE --> A3["设备管理"]
        BE --> A4["报告生成"]
        BE --> A5["校验接口"]
    end

    subgraph Core["核心处理引擎"]
        SCHED["任务调度模块<br/>Celery + Redis"]
        COLLECT["采集执行模块<br/>Airtest + ADB"]
        AI["AI数车分析模块<br/>YOLOv8 + OpenCV"]
        VALID["质量校验模块<br/>规则引擎 + 异常检测"]
    end

    subgraph Data["数据存储层"]
        PG["PostgreSQL + PostGIS<br/>结构化数据 + 围栏判断"]
        MINIO["MinIO<br/>截图文件存储"]
        REDIS["Redis<br/>任务队列 + 账号池"]
    end

    subgraph Devices["设备层"]
        PHONE1["Android设备 #1"]
        PHONE2["Android设备 #2"]
        PHONEN["Android设备 #N"]
    end

    subgraph GPU["推理层"]
        INFER["ONNX Runtime<br/>GPU批量推理"]
    end

    UI -->|REST API| BE
    BE --> SCHED
    SCHED -->|触发采集任务| COLLECT
    SCHED -->|触发分析任务| AI
    SCHED -->|触发校验任务| VALID

    COLLECT --> PHONE1
    COLLECT --> PHONE2
    COLLECT --> PHONEN
    COLLECT -->|截图上传| MINIO
    COLLECT -->|元数据写入| PG

    AI -->|读取截图| MINIO
    AI -->|模型推理| INFER
    AI -->|结果写入| PG

    VALID -->|读取数据| PG
    VALID -->|标记异常| PG

    SCHED -->|账号状态| REDIS
    COLLECT -->|获取账号| REDIS

    style Frontend fill:#e3f2fd,stroke:#1565c0
    style API fill:#e8f5e9,stroke:#2e7d32
    style Core fill:#fff3e0,stroke:#e65100
    style Data fill:#f3e5f5,stroke:#6a1b9a
    style Devices fill:#fce4ec,stroke:#c62828
    style GPU fill:#e0f7fa,stroke:#006064
```

---

## 端到端数据流 Workflow

```mermaid
flowchart LR
    T1["管理员创建<br/>采集任务"] --> T2["Celery调度引擎<br/>按时间触发"]
    T2 --> T3["采集模块控制<br/>Android设备"]
    T3 --> T4["模拟GPS定位<br/>到目标点位"]
    T4 --> T5["打开三家App<br/>找车界面"]
    T5 --> T6["调整比例尺<br/>三家对齐"]
    T6 --> T7["截图保存<br/>3品牌×7轮=21张"]

    T7 --> T8["截图存入MinIO<br/>元数据写入PG"]
    T8 --> T9{"该点位<br/>7轮完成?"}
    T9 -->|否| T3
    T9 -->|是| T10["触发AI数车<br/>批量分析"]

    T10 --> T11["YOLOv8检测<br/>车辆图标"]
    T11 --> T12["SIFT图像配准<br/>对齐截图"]
    T12 --> T13["围栏内筛选<br/>100m×100m"]
    T13 --> T14["匈牙利算法<br/>车辆匹配"]
    T14 --> T15["计算流入流出<br/>+疑似调度"]
    T15 --> T16["结果写入PG"]

    T16 --> T17["自动质量校验<br/>5条规则检查"]
    T17 --> T18{"有异常<br/>数据?"}
    T18 -->|是| T19["推送人工核对<br/>队列"]
    T18 -->|否| T20["数据通过"]
    T19 --> T21["人工在截图上<br/>圈车修正"]
    T21 --> T20

    T20 --> T22["生成Excel<br/>交付报告"]
    T22 --> T23["截图索引 + <br/>质量报告"]
    T23 --> T24["交付甲方"]

    style T1 fill:#e3f2fd,stroke:#1565c0
    style T10 fill:#fff3e0,stroke:#e65100
    style T17 fill:#e8f5e9,stroke:#2e7d32
    style T24 fill:#f3e5f5,stroke:#6a1b9a
```

---

## 单点位采集时序图

```mermaid
sequenceDiagram
    participant S as Celery调度器
    participant D as Android设备
    participant MT as 美团App
    participant DD as 滴滴App
    participant HB as 哈啰App
    participant M as MinIO存储
    participant PG as PostgreSQL

    S->>D: 分配采集任务 (点位ID, 坐标, 时段)

    Note over D: T=0min 准备阶段
    D->>D: 设置GPS模拟定位 (lat, lng)
    D->>MT: 启动美团 → 进入骑单车界面
    D->>DD: 启动滴滴 → 进入骑行界面
    D->>HB: 启动哈啰 → 进入骑车界面
    D->>D: 调整三家比例尺统一 (100m视野)

    Note over D: T=0min 第1轮截图
    D->>MT: 截图 (T时刻)
    MT-->>D: screenshot_MT_T.png
    D->>DD: 截图 (T时刻)
    DD-->>D: screenshot_DD_T.png
    D->>HB: 截图 (T时刻)
    HB-->>D: screenshot_HB_T.png
    D->>M: 上传3张截图
    D->>PG: 写入元数据 (task_id, point_id, brand, time_label=T)

    Note over D: 等待10分钟...

    Note over D: T+10min 第2轮截图
    D->>MT: 截图 (T+10时刻)
    D->>DD: 截图 (T+10时刻)
    D->>HB: 截图 (T+10时刻)
    D->>M: 上传3张截图
    D->>PG: 写入元数据 (time_label=T+10)

    Note over D: ...重复至 T+60min ...

    Note over D: T+60min 第7轮截图 (最后一轮)
    D->>MT: 截图 (T+60时刻)
    D->>DD: 截图 (T+60时刻)
    D->>HB: 截图 (T+60时刻)
    D->>M: 上传3张截图
    D->>PG: 写入元数据 (time_label=T+60)

    D->>PG: 标记点位采集完成
    PG-->>S: 通知点位完成 (21张截图)
    S->>S: 触发AI数车分析任务
```

---

## AI数车分析管道

```mermaid
flowchart TD
    START["输入: 7张截图序列<br/>T0.png → T60.png<br/>同一品牌同一点位"] --> S1

    subgraph S1["Step 1: YOLOv8目标检测"]
        S1A["加载YOLOv8s ONNX模型"] --> S1B["逐张检测车辆图标"]
        S1B --> S1C["输出: 每张截图的<br/>车辆位置(bbox) + 数量"]
        S1C --> S1D{"有聚集图标?"}
        S1D -->|是| S1E["OCR识别聚集数字<br/>PaddleOCR"]
        S1D -->|否| S1F["车辆数 = 检测框数"]
        S1E --> S1F
    end

    S1 --> S2

    subgraph S2["Step 2: 图像配准对齐"]
        S2A["以T0为参考图像"] --> S2B["SIFT特征点检测<br/>+ RANSAC匹配"]
        S2B --> S2C["计算仿射变换矩阵"]
        S2C --> S2D["将所有截图坐标<br/>转换到T0坐标系"]
        S2D --> S2E["输出配准置信度"]
    end

    S2 --> S3

    subgraph S3["Step 3: 围栏内筛选"]
        S3A["将围栏地理坐标<br/>映射到像素坐标"] --> S3B["点在多边形内判断<br/>(Shapely)"]
        S3B --> S3C["输出: 围栏内车辆<br/>vs 围栏外车辆"]
    end

    S3 --> S4

    subgraph S4["Step 4: 车辆跨帧匹配"]
        S4A["构建距离矩阵<br/>(T0 vs T10)"] --> S4B["匈牙利算法<br/>最优匹配"]
        S4B --> S4C{"距离 < 阈值?"}
        S4C -->|是| S4D["标记为同一辆车"]
        S4C -->|否| S4E["未匹配"]
        S4E --> S4F["T0有T10无 → 流出"]
        S4E --> S4G["T10有T0无 → 流入"]
    end

    S4 --> S5

    subgraph S5["Step 5: 流入流出计算"]
        S5A["统计每个时间间隔<br/>的流入数/流出数"] --> S5B["多帧确认:<br/>消除地图刷新闪烁"]
        S5B --> S5C["输出: 6组间隔数据<br/>(T→T10, T10→T20, ...)"]
    end

    S5 --> S6

    subgraph S6["Step 6: 疑似调度识别"]
        S6A["DBSCAN聚类<br/>分析流入车辆位置"] --> S6B{"短时间≥3辆<br/>且位置聚集?"}
        S6B -->|是| S6C["标记为疑似调度入"]
        S6B -->|否| S6D["标记为自然流入"]
    end

    S6 --> OUTPUT

    OUTPUT["输出: 完整车辆数据序列<br/>每个时点: 车辆数<br/>每个间隔: 流入/流出/疑似调度"]

    style S1 fill:#e3f2fd,stroke:#1565c0
    style S2 fill:#e8f5e9,stroke:#2e7d32
    style S3 fill:#fff3e0,stroke:#e65100
    style S4 fill:#fce4ec,stroke:#c62828
    style S5 fill:#f3e5f5,stroke:#6a1b9a
    style S6 fill:#e0f7fa,stroke:#006064
    style OUTPUT fill:#fff9c4,stroke:#f57f17
```

---

## 任务调度时序图

```mermaid
sequenceDiagram
    participant U as 管理员
    participant API as FastAPI
    participant Q as Redis队列
    participant CW as Celery Worker (采集)
    participant AW as Celery Worker (AI分析)
    participant VW as Celery Worker (校验)
    participant DB as PostgreSQL
    participant FS as MinIO

    U->>API: 创建采集任务 (城市, 时段, 点位列表)
    API->>DB: 写入任务记录
    API->>Q: 发送调度任务 (schedule_point_sequence)

    loop 每个点位 (20个)
        CW->>Q: 获取点位采集任务
        CW->>DB: 查询点位信息 (坐标, 围栏)

        loop 7轮 (T → T+60, 每10分钟)
            CW->>CW: 控制设备截图 (3品牌)
            CW->>FS: 上传截图文件
            CW->>DB: 写入截图元数据
        end

        CW->>DB: 标记点位采集完成
        CW->>Q: 发送AI分析任务 (analyze_point)
    end

    AW->>Q: 获取AI分析任务
    AW->>FS: 下载该点位所有截图
    AW->>AW: YOLOv8检测 + 图像配准 + 匹配
    AW->>DB: 写入车辆数据 (车辆数/流入/流出/调度)
    AW->>Q: 发送校验任务 (validate_point)

    VW->>Q: 获取校验任务
    VW->>DB: 读取车辆数据
    VW->>VW: 执行5条质量校验规则

    alt 有异常
        VW->>DB: 标记异常记录 (severity=high)
        VW->>DB: 推送人工核对队列
    else 无异常
        VW->>DB: 标记数据通过
    end

    U->>API: 查询任务进度
    API->>DB: 统计完成率
    API-->>U: 返回进度 (85%完成)

    U->>API: 导出报告
    API->>DB: 汇总所有点位数据
    API->>FS: 附加截图索引
    API-->>U: 返回Excel报告
```

---

## 技术栈全景

```mermaid
graph LR
    subgraph 采集["数据采集层"]
        A1["Airtest"]
        A2["ADB"]
        A3["Python"]
        A4["Android设备"]
    end

    subgraph AI["AI分析层"]
        B1["YOLOv8"]
        B2["OpenCV"]
        B3["SIFT/ORB"]
        B4["匈牙利算法"]
        B5["DBSCAN"]
        B6["ONNX Runtime"]
        B7["PaddleOCR"]
    end

    subgraph 后端["后端服务层"]
        C1["FastAPI"]
        C2["Celery"]
        C3["Redis"]
        C4["SQLAlchemy"]
    end

    subgraph 存储["数据存储层"]
        D1["PostgreSQL"]
        D2["PostGIS"]
        D3["MinIO"]
    end

    subgraph 前端["前端展示层"]
        E1["React 18"]
        E2["Ant Design 5"]
        E3["Konva.js"]
        E4["高德地图JS API"]
        E5["Vite"]
    end

    subgraph 基础["基础设施"]
        F1["Docker"]
        F2["Docker Compose"]
        F3["Prometheus"]
        F4["Grafana"]
    end

    style 采集 fill:#e3f2fd,stroke:#1565c0
    style AI fill:#fff3e0,stroke:#e65100
    style 后端 fill:#e8f5e9,stroke:#2e7d32
    style 存储 fill:#f3e5f5,stroke:#6a1b9a
    style 前端 fill:#fce4ec,stroke:#c62828
    style 基础 fill:#e0f7fa,stroke:#006064
```

---

## 试点实施计划（4周）

```mermaid
gantt
    title 单城市试点实施甘特图（南宁市 · 20点位）
    dateFormat  YYYY-MM-DD
    axisFormat  %m/%d

    section Week 1: 基础设施
    开发环境 + Docker部署        :w1a, 2026-11-02, 2d
    数据库 + API服务搭建         :w1b, after w1a, 2d
    前端基础框架                 :w1c, after w1b, 1d

    section Week 2: 采集模块
    Airtest环境 + 设备准备       :w2a, after w1c, 2d
    三家App操控脚本开发          :w2b, after w2a, 2d
    GPS定位 + 自动截图流程       :w2c, after w2b, 1d

    section Week 3: AI数车
    数据标注 + YOLOv8训练        :w3a, after w2c, 2d
    图像配准 + 车辆匹配算法      :w3b, after w3a, 2d
    流入流出 + 端到端联调        :w3c, after w3b, 1d

    section Week 4: 试运行
    20点位完整采集 (一期)        :w4a, after w3c, 2d
    人工核对 + 准确率评估        :w4b, after w4a, 1d
    问题修复 + 参数调优          :w4c, after w4b, 1d
    报告生成 + 试点验收          :w4d, after w4c, 1d
```

---

## 数据校验流程

```mermaid
flowchart TD
    DATA["AI分析完成<br/>车辆数据写入PG"] --> L1

    subgraph L1["Layer 1: 自动校验 (实时)"]
        R1["规则1: 截图完整性<br/>21张是否齐全"]
        R2["规则2: 车辆数合理性<br/>0-200范围"]
        R3["规则3: 数据一致性<br/>车辆数=上轮+流入-流出"]
        R4["规则4: 突变检测<br/>变化率>50%标记"]
        R5["规则5: 配准置信度<br/><0.5标记"]
    end

    L1 --> L2

    subgraph L2["Layer 2: AI置信度过滤"]
        C1["检测置信度 < 0.7?"]
        C2["配准置信度 < 0.5?"]
        C3["匹配率低?"]
    end

    L2 --> CHECK{"有标记?"}

    CHECK -->|无标记| PASS["数据自动通过<br/>进入交付队列"]
    CHECK -->|有标记| L3

    subgraph L3["Layer 3: 人工核对"]
        H1["全检: 所有标记数据"]
        H2["抽检: 正常数据的10%"]
        H3["人工在截图上圈车<br/>修正AI结果"]
    end

    L3 --> SUBMIT{"核对结果"}
    SUBMIT -->|修正后通过| PASS
    SUBMIT -->|确认异常| REJECT["标记异常<br/>不交付"]

    style L1 fill:#e3f2fd,stroke:#1565c0
    style L2 fill:#e8f5e9,stroke:#2e7d32
    style L3 fill:#fff3e0,stroke:#e65100
    style PASS fill:#c8e6c9,stroke:#2e7d32
    style REJECT fill:#ffcdd2,stroke:#c62828
```

---

## 从试点到规模化路径

```mermaid
flowchart LR
    P1["试点<br/>南宁 · 20点位<br/>1时段 · 3品牌<br/>420张截图"] -->|"验证: 采集可行<br/>AI准确率达标"| P2

    P2["扩展城市<br/>洛阳 · 20点位<br/>验证跨城市适配"] -->|"验证: 参数无需大调"| P3

    P3["扩展时段<br/>4时段全覆盖<br/>20×4=80点位/城市"] -->|"验证: 时段适配"| P4

    P4["规模化<br/>12城市 × 4时段 × 20点位<br/>= 960点位/期<br/>~20,160张截图/期"] -->|"基础设施升级"| P5

    P5["常态化运行<br/>每月一期<br/>Docker→K8s<br/>实体机→云手机<br/>单GPU→多GPU"]

    style P1 fill:#e3f2fd,stroke:#1565c0
    style P2 fill:#e8f5e9,stroke:#2e7d32
    style P3 fill:#fff3e0,stroke:#e65100
    style P4 fill:#f3e5f5,stroke:#6a1b9a
    style P5 fill:#fff9c4,stroke:#f57f17
```

---

## 文档导航

| 文档 | 内容 | 优先级 |
|------|------|--------|
| [wb_00_project_overview.md](docs/wb_00_project_overview.md) | 项目背景、需求、状态评估、技术路线总览 | - |
| [wb_01_system_architecture.md](docs/wb_01_system_architecture.md) | 系统架构、模块划分、技术选型、部署方案、DB Schema | P0 |
| [wb_02_data_collection.md](docs/wb_02_data_collection.md) | Airtest自动化方案、设备管理、GPS模拟、SOP技术化 | P0 |
| [wb_03_ai_vehicle_counting.md](docs/wb_03_ai_vehicle_counting.md) | YOLOv8检测、图像配准、车辆匹配、流入流出算法 | **P0 核心** |
| [wb_04_task_scheduling.md](docs/wb_04_task_scheduling.md) | Celery调度、数据库设计、API接口、围栏坐标系 | P1 |
| [wb_05_data_validation.md](docs/wb_05_data_validation.md) | 三层校验、人工核对工具、报告生成、验收标准 | P1 |
| [wb_06_pilot_plan.md](docs/wb_06_pilot_plan.md) | 4周试点计划、Docker配置、设备清单 | **P0 执行** |
| [wb_07_api_exploration.md](docs/wb_07_api_exploration.md) | API逆向探索、合规边界、效率提升 | P2 |

### 建议阅读顺序

| 角色 | 阅读路径 |
|------|---------|
| 决策者 | wb_00 → wb_01 → wb_06 |
| 采集开发 | wb_00 → wb_02 → wb_04 |
| 算法工程师 | wb_00 → wb_03（重点） |
| 全栈工程师 | 按编号顺序通读 |

---

## 快速开始

```bash
# 1. 克隆项目
git clone <repo-url> e-bike-monitor
cd e-bike-monitor

# 2. 启动基础设施
docker-compose up -d postgres redis minio

# 3. 初始化数据库
docker-compose exec backend python scripts/init_db.py

# 4. 导入点位数据
docker-compose exec backend python scripts/load_points.py \
    "电单数车 线上测试点位 to 供应商.xlsx"

# 5. 启动全部服务
docker-compose up -d

# 6. 访问管理面板
# 前端: http://localhost:3000
# API文档: http://localhost:8000/docs
# MinIO控制台: http://localhost:9001
```

---

## 核心风险与应对

| 风险 | 概率 | 影响 | 缓解方案 |
|------|------|------|---------|
| AI流入流出准确率不达标 | 高 | 交付质量不通过 | 图像配准+匈牙利匹配+多帧确认，保留人工核对 |
| App反自动化检测 | 中 | 采集中断 | 模拟真实操作行为，账号轮转，设备指纹多样化 |
| 账号被封禁 | 中 | 无法采集 | 多账号池管理，异常监控，快速切换 |
| 点位清单不完整 | 高 | 无法全量采集 | 先完成单城市试点，逐步补全12城点位 |

---

## 术语表

| 术语 | 含义 |
|------|------|
| MT | 美团（Meituan）电单车平台 |
| DD | 滴滴（DiDi）电单车平台 |
| HB | 哈啰（HelloBike）电单车平台 |
| 围栏 | 以停车点为中心的100m×100m正方形区域 |
| 时点车辆数 | 某一时刻围栏内的车辆总数 |
| 流入数 | 两时点间新出现在围栏内的车辆数 |
| 流出数 | 两时点间从围栏内消失的车辆数 |
| 疑似调度入 | 短时间内大量同向涌入，推断为平台主动调度 |
| T~T+60 | 从起始时间到60分钟后的7个采集时间点 |
| GCJ-02 | 中国大陆标准加密坐标系（高德/腾讯使用） |
| SOP | Standard Operating Procedure，标准操作流程 |
