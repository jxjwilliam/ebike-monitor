# 系统架构设计

> 文档编号：wb_01  
> 创建日期：2026-10-30  
> 文档定位：整体架构、模块划分、技术选型、部署方案

---

## 1. 架构总览

### 1.1 系统全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        管理面板（Web Frontend）                       │
│              React + Ant Design                                      │
│   任务管理 │ 点位管理 │ 数据看板 │ 人工核对 │ 报告导出               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ REST API
┌──────────────────────────────┴──────────────────────────────────────┐
│                        API 服务层（Backend）                          │
│                    FastAPI (Python 3.11+)                            │
│   任务创建/查询 │ 数据查询 │ 设备管理 │ 报告生成 │ 校验接口           │
└──────┬───────────┬───────────┬───────────┬───────────┬──────────────┘
       │           │           │           │           │
       ▼           ▼           ▼           ▼           ▼
  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐
  │ 任务调度 │ │ 采集执行 │ │ AI数车  │ │ 数据存储 │ │ 质量校验    │
  │ 模块     │ │ 模块     │ │ 分析模块│ │ 模块     │ │ 模块        │
  │ Celery  │ │ Airtest │ │ YOLOv8  │ │ PG+MinIO│ │ 规则引擎    │
  │ +Redis  │ │ +ADB    │ │ +OpenCV │ │ +PostGIS│ │ +异常检测   │
  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────────┘
       │           │                        │
       │     ┌─────┴──────┐          ┌──────┴──────┐
       │     │ 设备集群    │          │ GPU推理节点  │
       │     │ Android手机│          │ ONNX/TensorRT│
       │     │ 或云手机    │          │              │
       │     └────────────┘          └──────────────┘
       │
       ▼
  ┌──────────┐
  │ 账号池    │
  │ Redis    │
  │ MT/DD/HB │
  └──────────┘
```

### 1.2 数据流

```
1. 管理员在Web面板创建采集任务（城市+时段+点位列表）
        │
        ▼
2. Celery调度引擎按时间触发采集子任务
        │
        ▼
3. 采集模块控制Android设备：
   - 切换到对应平台App
   - 模拟定位到点位坐标
   - 打开找车界面
   - 等待地图加载
   - 截图保存
        │
        ▼
4. 每个点位×每个平台×7轮 = 21张截图
   存入MinIO，元数据写入PostgreSQL
        │
        ▼
5. AI数车模块批量处理截图：
   - YOLOv8检测车辆图标 → 时点车辆数
   - 相邻时点图像比对 → 流入/流出
   - 规则判断 → 疑似调度入
        │
        ▼
6. 结构化结果写入PostgreSQL
        │
        ▼
7. 质量校验模块：
   - 异常检测（车辆数突变等）
   - 标记可疑数据
   - 推送人工核对任务
        │
        ▼
8. 人工核对（Web面板）或自动通过
        │
        ▼
9. 报告生成：导出Excel交付甲方
```

---

## 2. 模块详细划分

### 2.1 模块清单

| 编号 | 模块名 | 技术栈 | 职责 | 详细文档 |
|------|--------|--------|------|---------|
| M1 | 任务调度模块 | Celery + Redis | 采集任务编排、定时触发、失败重试、任务状态管理 | wb_04 |
| M2 | 采集执行模块 | Airtest + ADB + Python | App操控、定位模拟、截图、设备管理 | wb_02 |
| M3 | AI数车分析模块 | YOLOv8 + OpenCV + ONNX | 目标检测、图像比对、流入流出计算、调度识别 | wb_03 |
| M4 | 数据存储模块 | PostgreSQL + PostGIS + MinIO | 结构化数据存储、围栏空间判断、截图文件存储 | wb_04 |
| M5 | 质量校验模块 | Python + 规则引擎 | 异常检测、数据校验、人工核对任务管理 | wb_05 |
| M6 | API服务模块 | FastAPI | RESTful API，对接前端和外部系统 | wb_04 |
| M7 | 管理面板 | React + Ant Design | 任务管理、数据看板、人工核对界面、报告导出 | wb_05 |
| M8 | 报告生成模块 | Python openpyxl + 模板引擎 | 按甲方要求格式生成Excel交付报告 | wb_05 |
| M9 | 设备管理模块 | Python + ADB | 设备注册、健康检查、状态监控、远程控制 | wb_02 |
| M10 | 账号池管理 | Redis + Python | 三家平台账号管理、登录态维护、轮转策略 | wb_02 |

### 2.2 模块间依赖关系

```
M1(调度) ──触发──→ M2(采集) ──产出截图──→ M3(AI数车) ──产出数据──→ M5(校验)
    │                  │                                       │
    │                  ├──依赖──→ M10(账号池)                   │
    │                  ├──依赖──→ M9(设备管理)                   │
    │                                                          │
    └──依赖──→ M4(存储) ←──读写──→ M3, M5, M6, M8              │
                                                              │
M6(API) ←──对接──→ M7(前端) ←──展示──→ M5, M8 ←──汇总──→ M5 ─┘
```

---

## 3. 技术选型详细说明

### 3.1 采集层

| 组件 | 选型 | 备选 | 选型理由 |
|------|------|------|---------|
| App自动化框架 | **Airtest** | Appium, UIAutomator2 | 网易开源，对中国App生态支持好；图像识别能力强；Python原生；Poco框架支持UI元素级操控 |
| 设备连接 | **ADB** | 无 | Android标准调试桥，Airtest底层依赖 |
| 定位模拟 | **ADB mockLocation** | Xposed, Magisk | 无需Root的标准方案（Android开发者模式模拟定位）；如需更高隐蔽性可考虑Xposed |
| 截图 | **Airtest snapshot()** | ADB screencap | Airtest封装的截图接口，自动带时间戳和设备信息 |
| 云手机（备选） | **红手指/雷电云手机** | AWS Device Farm | 规模化时替代实体手机，降低运维成本 |

### 3.2 AI数车层

| 组件 | 选型 | 备选 | 选型理由 |
|------|------|------|---------|
| 目标检测模型 | **YOLOv8** | RT-DETR, YOLOv10, DETR | 精度与速度的最佳平衡；Ultralytics生态成熟；训练流程简单；社区支持好 |
| 图像处理 | **OpenCV** | PIL/Pillow | 功能最全的计算机视觉库；图像配准、差分、模板匹配 |
| 多目标跟踪 | **ByteTrack** | SORT, DeepSORT | 轻量高效，适合图标级目标跟踪 |
| 模型推理加速 | **ONNX Runtime** | TensorRT, OpenVINO | 跨平台兼容性好；部署简单；支持CPU/GPU切换 |
| 模型训练 | **Ultralytics Hub** | 本地训练 | 云端训练，自动数据增强，快速迭代 |
| 数据标注 | **CVAT** | LabelImg, Roboflow | 开源，支持团队协作，支持视频标注（用于流入流出样本） |

### 3.3 后端与数据层

| 组件 | 选型 | 备选 | 选型理由 |
|------|------|------|---------|
| API框架 | **FastAPI** | Flask, Django | 异步高性能；自动生成Swagger文档；类型安全；Python生态 |
| 任务调度 | **Celery** + **Redis** | APScheduler, XXL-Job | Python生态最成熟的分布式任务队列；支持定时任务、重试、优先级 |
| 关系型数据库 | **PostgreSQL 15+** | MySQL | PostGIS扩展支持空间查询（围栏判断）；JSON字段支持灵活的元数据存储 |
| 空间扩展 | **PostGIS** | MongoDB GeoJSON | PostgreSQL原生扩展，空间查询性能好，支持多边形围栏判断 |
| 对象存储 | **MinIO** | 阿里云OSS, 腾讯云COS | 开源自部署，S3兼容；试点阶段无需云服务费用；规模化后可平滑迁移到云OSS |
| 缓存 | **Redis 7+** | 无 | Celery broker + 账号池状态 + 设备状态 + 任务锁 |

### 3.4 前端

| 组件 | 选型 | 备选 | 选型理由 |
|------|------|------|---------|
| 框架 | **React 18** | Vue 3 | 生态最成熟；团队熟悉度高 |
| UI组件库 | **Ant Design 5** | Material UI | 中文文档好；企业级管理面板首选；表格/表单/图表组件丰富 |
| 地图 | **高德地图 JS API** | Leaflet | 与GCJ-02坐标系一致；无需坐标转换；支持围栏绘制和点位标注 |
| 图像标注 | **Konva.js** | Fabric.js | React生态集成好；支持在截图上绘制标记、圈选区域 |
| 状态管理 | **Zustand** | Redux Toolkit | 轻量简洁，适合中等复杂度应用 |
| 构建工具 | **Vite** | Webpack | 开发体验好，构建速度快 |

### 3.5 基础设施

| 组件 | 选型 | 备选 | 选型理由 |
|------|------|------|---------|
| 容器化 | **Docker + Docker Compose** | 无 | 试点阶段单机部署够用；环境一致性 |
| 编排（规模化） | **Kubernetes** | Docker Swarm | 规模化后设备/推理节点弹性伸缩 |
| 监控 | **Prometheus + Grafana** | 无 | 任务指标、设备状态、推理性能监控 |
| 日志 | **ELK Stack** | Loki + Grafana | 采集日志、App日志、系统日志统一收集分析 |
| CI/CD | **GitLab CI** 或 **GitHub Actions** | Jenkins | 自动化测试、镜像构建、部署 |

---

## 4. 部署架构

### 4.1 试点阶段（单城市）

```
┌─────────────── 单台服务器（16核 / 32GB / GPU可选）───────────────┐
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ FastAPI     │  │ Celery      │  │ Celery      │            │
│  │ (API服务)   │  │ Worker      │  │ Worker      │            │
│  │             │  │ (采集任务)   │  │ (AI数车)    │            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│         │                │                │                    │
│  ┌──────┴────────────────┴────────────────┴──────┐             │
│  │              Redis (Broker + 缓存)              │             │
│  ├────────────────────────────────────────────────┤             │
│  │         PostgreSQL + PostGIS (数据)             │             │
│  ├────────────────────────────────────────────────┤             │
│  │              MinIO (截图存储)                   │             │
│  └────────────────────────────────────────────────┘             │
│                                                                  │
│  ┌────────────────────────────────────────────────┐             │
│  │         React 前端 (Nginx 静态托管)             │             │
│  └────────────────────────────────────────────────┘             │
│                                                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ USB / 网络
                    ┌──────┴──────┐
                    │ Android设备  │
                    │ 3-5台测试机  │
                    └─────────────┘
```

部署方式：`docker-compose up -d` 一键启动所有服务。

### 4.2 规模化阶段（12城市）

```
┌─────────────── Kubernetes 集群 ───────────────────────────┐
│                                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │ API Pod  │  │ 调度Pod  │  │ 前端Pod  │               │
│  │ (x2)     │  │ (x1)     │  │ (x2)     │               │
│  └──────────┘  └──────────┘  └──────────┘               │
│                                                            │
│  ┌──────────┐  ┌──────────────────────────┐              │
│  │ 采集Pod  │  │ AI推理Pod (GPU)          │              │
│  │ (xN)     │  │ YOLOv8 ONNX TensorRT    │              │
│  └──────────┘  └──────────────────────────┘              │
│                                                            │
│  ┌──────────────────────────────────────────┐             │
│  │  持久化层                                  │             │
│  │  PostgreSQL (主从) + Redis (集群)         │             │
│  │  + MinIO/OSS (截图存储)                   │             │
│  └──────────────────────────────────────────┘             │
│                                                            │
└──────────────────────┬─────────────────────────────────────┘
                       │
              ┌────────┴────────┐
              │  设备农场        │
              │  云手机集群      │
              │  或实体设备柜    │
              └─────────────────┘
```

---

## 5. 项目目录结构

```
e-bike-monitor/
├── docs/                          # 技术文档（本目录）
│   ├── wb_00_project_overview.md
│   ├── wb_01_system_architecture.md
│   ├── wb_02_data_collection.md
│   ├── wb_03_ai_vehicle_counting.md
│   ├── wb_04_task_scheduling.md
│   ├── wb_05_data_validation.md
│   ├── wb_06_pilot_plan.md
│   └── wb_07_api_exploration.md
│
├── backend/                       # 后端服务
│   ├── app/
│   │   ├── main.py               # FastAPI 入口
│   │   ├── api/                  # API 路由
│   │   │   ├── tasks.py          # 任务管理接口
│   │   │   ├── data.py           # 数据查询接口
│   │   │   ├── devices.py        # 设备管理接口
│   │   │   └── reports.py        # 报告导出接口
│   │   ├── models/               # 数据模型（SQLAlchemy）
│   │   │   ├── task.py
│   │   │   ├── point.py          # 点位
│   │   │   ├── snapshot.py       # 截图记录
│   │   │   └── vehicle_data.py   # 车辆数据
│   │   ├── services/             # 业务逻辑
│   │   │   ├── task_service.py
│   │   │   ├── device_service.py
│   │   │   └── report_service.py
│   │   └── core/
│   │       ├── config.py         # 配置管理
│   │       ├── database.py       # 数据库连接
│   │       └── geo.py            # 坐标转换 + 围栏判断
│   │
│   ├── workers/                   # Celery Worker
│   │   ├── celery_app.py         # Celery 配置
│   │   ├── tasks/
│   │   │   ├── collection.py     # 采集任务
│   │   │   ├── analysis.py       # AI数车任务
│   │   │   └── validation.py     # 校验任务
│   │   └── schedulers/
│   │       └── periodic.py       # 定时任务配置
│   │
│   ├── collectors/                # 采集器
│   │   ├── base_collector.py     # 采集基类
│   │   ├── airtest_collector.py  # Airtest采集实现
│   │   ├── device_manager.py     # 设备管理
│   │   └── account_pool.py       # 账号池
│   │
│   ├── analyzers/                 # AI分析器
│   │   ├── detector.py           # YOLOv8目标检测
│   │   ├── comparator.py         # 图像比对（流入流出）
│   │   ├── dispatcher.py         # 疑似调度识别
│   │   └── models/               # 训练好的模型权重
│   │
│   ├── validators/                # 校验器
│   │   ├── anomaly_detector.py   # 异常检测
│   │   └── quality_checker.py    # 质量检查规则
│   │
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                      # 前端
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx     # 数据看板
│   │   │   ├── TaskManager.tsx   # 任务管理
│   │   │   ├── PointManager.tsx  # 点位管理
│   │   │   ├── Review.tsx        # 人工核对
│   │   │   └── Reports.tsx       # 报告导出
│   │   ├── components/
│   │   ├── api/
│   │   └── stores/
│   ├── package.json
│   └── Dockerfile
│
├── scripts/                       # 运维脚本
│   ├── init_db.py                # 数据库初始化
│   ├── load_points.py            # 导入点位数据
│   └── train_model.py            # 模型训练脚本
│
├── docker-compose.yml             # 试点部署编排
├── docker-compose.prod.yml        # 生产部署编排
└── README.md
```

---

## 6. 数据库设计概要

### 6.1 核心表

```sql
-- 城市表
CREATE TABLE cities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    code VARCHAR(20)
);

-- 点位表
CREATE TABLE points (
    id SERIAL PRIMARY KEY,
    city_id INT REFERENCES cities(id),
    external_id VARCHAR(50),       -- 甲方点位ID
    park_name VARCHAR(200),        -- 停车点名称
    fence GEOMETRY(POLYGON, 4326), -- 100m×100m围栏（PostGIS）
    center POINT,                  -- 围栏中心点
    status VARCHAR(20) DEFAULT 'active'
);

-- 采集任务表
CREATE TABLE collection_tasks (
    id SERIAL PRIMARY KEY,
    period VARCHAR(20),            -- 如 "2026-11" 第几期
    city_id INT REFERENCES cities(id),
    time_slot VARCHAR(50),         -- 时段类型：周中晚 等
    start_time TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending', -- pending/running/completed/failed
    created_at TIMESTAMP DEFAULT NOW()
);

-- 截图表
CREATE TABLE snapshots (
    id SERIAL PRIMARY KEY,
    task_id INT REFERENCES collection_tasks(id),
    point_id INT REFERENCES points(id),
    brand VARCHAR(10),             -- MT / DD / HB
    time_label VARCHAR(20),        -- T / T+10 / T+20 ...
    capture_time TIMESTAMP,
    file_path VARCHAR(500),        -- MinIO中的路径
    device_id VARCHAR(50),
    status VARCHAR(20) DEFAULT 'captured'
);

-- 车辆数据表
CREATE TABLE vehicle_data (
    id SERIAL PRIMARY KEY,
    snapshot_id INT REFERENCES snapshots(id),
    task_id INT REFERENCES collection_tasks(id),
    point_id INT REFERENCES points(id),
    brand VARCHAR(10),
    time_label VARCHAR(20),
    vehicle_count INT,             -- 时点车辆数
    inflow INT,                    -- 流入数
    outflow INT,                   -- 流出数
    suspected_dispatch INT,        -- 疑似调度入
    source VARCHAR(20),            -- ai / manual
    verified BOOLEAN DEFAULT FALSE -- 是否人工核对通过
);
```

---

## 7. 接口设计概要

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tasks` | 创建采集任务 |
| GET | `/api/tasks` | 查询任务列表 |
| GET | `/api/tasks/{id}` | 查询任务详情 |
| GET | `/api/tasks/{id}/data` | 获取任务采集的数据 |
| POST | `/api/points` | 新增点位 |
| GET | `/api/points` | 查询点位列表 |
| POST | `/api/points/import` | 批量导入点位（Excel上传） |
| GET | `/api/devices` | 查询设备状态 |
| POST | `/api/data/{id}/review` | 人工核对提交 |
| GET | `/api/reports/{task_id}` | 导出报告 |
| GET | `/api/dashboard/stats` | 看板统计数据 |
