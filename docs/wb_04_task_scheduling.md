# 任务调度与数据管理模块

> 文档编号：wb_04  
> 创建日期：2026-10-30  
> 文档定位：任务调度引擎、设备/账号池管理、数据存储、围栏判断、坐标系处理

---

## 1. 任务调度模块

### 1.1 调度需求

| 调度场景 | 说明 | 触发方式 |
|---------|------|---------|
| 定时采集任务 | 每月一期，按城市/时段/点位编排 | 管理员手动创建或周期性自动创建 |
| 单点位采集序列 | 一个点位内7轮截图，每10分钟一次 | Celery定时触发（crontab式） |
| 多设备并行 | 多个点位分配到不同设备同时采集 | Celery Worker多进程 |
| AI数车任务 | 截图完成后触发AI分析 | 信号触发（collect_complete → analyze） |
| 校验任务 | AI分析完成后触发质量校验 | 信号触发（analyze_complete → validate） |

### 1.2 Celery 架构

```
┌──────────┐     ┌──────────┐     ┌──────────────────────────┐
│ FastAPI  │────→│ Celery   │────→│     Redis (Broker)        │
│ (生产者)  │     │ Beat     │     │                          │
└──────────┘     │ (定时)   │     │  ┌─────┐ ┌─────┐ ┌─────┐│
                 └──────────┘     │  │采集 │ │AI   │ │校验 ││
                                  │  │队列 │ │队列 │ │队列 ││
                                  │  └──┬──┘ └──┬──┘ └──┬──┘│
                                  └─────│───────│───────│───┘
                                        │       │       │
                                 ┌──────┴──┐┌───┴───┐┌──┴───┐
                                 │Worker 1 ││Worker 2││Worker3│
                                 │(采集+   ││(AI数车││(校验 │
                                 │ 设备)   ││ GPU)  ││)     │
                                 └─────────┘└───────┘└──────┘
```

### 1.3 任务定义

```python
# workers/celery_app.py
from celery import Celery
from celery.schedules import crontab

app = Celery("ebike_monitor", broker="redis://localhost:6379/0")

# 定时任务配置
app.conf.beat_schedule = {
    # 每月1日自动创建当期采集任务
    "create-monthly-tasks": {
        "task": "workers.tasks.create_monthly_tasks",
        "schedule": crontab(minute=0, hour=2, day_of_month=1),
    },
    # 每10分钟检查是否有待执行的采集轮次
    "check-collection-rounds": {
        "task": "workers.tasks.check_collection_rounds",
        "schedule": crontab(minute="*/10"),
    },
}

app.conf.task_routes = {
    "workers.tasks.collection.*": {"queue": "collection"},
    "workers.tasks.analysis.*": {"queue": "analysis"},
    "workers.tasks.validation.*": {"queue": "validation"},
}
```

```python
# workers/tasks/collection.py
from workers.celery_app import app
from collectors import AirtestCollector, DeviceManager, AccountPool

@app.task(bind=True, max_retries=3)
def collect_point_round(self, task_id, point_id, time_label, device_id):
    """
    采集一个点位在指定时间节点的三家App截图
    
    这是最小调度单元：一个点位 × 一个时间节点 × 三家平台
    """
    try:
        # 获取设备
        device = DeviceManager().get_device(device_id)
        
        # 采集三家截图
        collector = AirtestCollector(device)
        results = collector.capture_round(task_id, point_id, time_label)
        
        # 标记完成
        update_snapshot_status(task_id, point_id, time_label, "captured")
        
        # 检查该点位的7轮是否全部完成
        if is_point_complete(task_id, point_id):
            # 触发AI数车任务
            analyze_point.delay(task_id, point_id)
        
        return {"status": "success", "snapshots": len(results)}
    
    except Exception as exc:
        # 重试
        raise self.retry(exc=exc, countdown=60)


@app.task(bind=True)
def schedule_point_sequence(self, task_id, point_id, start_time, device_id):
    """
    为一个点位编排完整的7轮采集时间线
    
    在start_time时刻触发第一轮，之后每10分钟触发一轮
    """
    from datetime import timedelta
    
    for i in range(7):
        round_time = start_time + timedelta(minutes=i * 10)
        time_label = f"T+{i*10}" if i > 0 else "T"
        
        # 使用Celery的eta（estimated time of arrival）定时
        collect_point_round.apply_async(
            args=(task_id, point_id, time_label, device_id),
            eta=round_time,
        )


@app.task
def create_city_task(city_id, period, time_slot, start_date):
    """
    为一个城市创建完整采集任务
    20个点位 × 并行调度
    """
    points = get_points_for_city(city_id)
    devices = DeviceManager().get_available_devices()
    
    for i, point in enumerate(points):
        device = devices[i % len(devices)]  # 轮询分配设备
        
        # 计算每个点位的开始时间
        # 同一时段的点位可以错开5分钟开始，避免设备冲突
        point_start = start_date + timedelta(minutes=i * 5)
        
        schedule_point_sequence.delay(
            task_id=task_id,
            point_id=point.id,
            start_time=point_start,
            device_id=device.device_id,
        )
```

### 1.4 任务状态流转

```
                    ┌─────────┐
                    │ PENDING │ ← 任务创建
                    └────┬────┘
                         │ 调度器分配设备和时间
                         ▼
                    ┌─────────┐
                    │ SCHEDULED│ ← 已安排执行时间
                    └────┬────┘
                         │ 到达执行时间
                         ▼
                    ┌─────────┐
                    │ RUNNING │ ← 正在采集
                    └────┬────┘
                         │
                    ┌────┴────┐
                    │         │
                    ▼         ▼
              ┌─────────┐ ┌─────────┐
              │SUCCESS  │ │ FAILED  │
              │(截图完成)│ │(采集失败)│
              └─────────┘ └────┬────┘
                               │ 自动重试3次
                               ▼
                          ┌─────────┐
                          │ RETRY   │
                          └────┬────┘
                               │ 仍失败
                               ▼
                          ┌─────────┐
                          │ ERROR   │ ← 需人工介入
                          └─────────┘
```

---

## 2. 数据存储设计

### 2.1 完整数据库Schema

```sql
-- ============================================
-- 城市表
-- ============================================
CREATE TABLE cities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    code VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 点位表
-- ============================================
CREATE TABLE points (
    id SERIAL PRIMARY KEY,
    city_id INT REFERENCES cities(id),
    external_id VARCHAR(50),           -- 甲方点位ID
    park_name VARCHAR(200),            -- 停车点名称
    center_lat DECIMAL(12, 9),        -- 中心纬度 (GCJ-02)
    center_lng DECIMAL(12, 9),        -- 中心经度 (GCJ-02)
    fence GEOMETRY(POLYGON, 4326),    -- 100m×100m围栏
    time_slot VARCHAR(50),            -- 适用时段（周中晚 等）
    status VARCHAR(20) DEFAULT 'active',
    is_supplement BOOLEAN DEFAULT FALSE, -- 是否为补点
    notes TEXT,                       -- 备注
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_points_fence ON points USING GIST(fence);
CREATE INDEX idx_points_city ON points(city_id);

-- ============================================
-- 采集任务表
-- ============================================
CREATE TABLE collection_tasks (
    id SERIAL PRIMARY KEY,
    period VARCHAR(20) NOT NULL,       -- 如 "2026-11"
    city_id INT REFERENCES cities(id),
    time_slot VARCHAR(50),             -- 周中晚 / 周中早 / 周末晚 / 周末早
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending',
    total_points INT DEFAULT 0,
    completed_points INT DEFAULT 0,
    failed_points INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 截图记录表
-- ============================================
CREATE TABLE snapshots (
    id SERIAL PRIMARY KEY,
    task_id INT REFERENCES collection_tasks(id),
    point_id INT REFERENCES points(id),
    brand VARCHAR(10) NOT NULL,        -- MT / DD / HB
    time_label VARCHAR(20) NOT NULL,   -- T / T+10 / T+20 ...
    capture_time TIMESTAMP NOT NULL,
    file_path VARCHAR(500),            -- MinIO对象路径
    file_size INT,                     -- 文件大小（字节）
    device_id VARCHAR(50),
    app_version VARCHAR(50),
    map_zoom_level FLOAT,
    alignment_confidence FLOAT,        -- 配准置信度
    status VARCHAR(20) DEFAULT 'captured', -- captured / analyzed / error
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_snapshots_task ON snapshots(task_id);
CREATE INDEX idx_snapshots_point ON snapshots(point_id);
CREATE INDEX idx_snapshots_brand_time ON snapshots(point_id, brand, time_label);

-- ============================================
-- 车辆数据表（AI分析结果）
-- ============================================
CREATE TABLE vehicle_data (
    id SERIAL PRIMARY KEY,
    task_id INT REFERENCES collection_tasks(id),
    point_id INT REFERENCES points(id),
    snapshot_id INT REFERENCES snapshots(id),
    brand VARCHAR(10) NOT NULL,
    time_label VARCHAR(20) NOT NULL,
    
    -- 时点数据
    vehicle_count INT,                 -- 时点车辆数
    vehicle_count_inside_fence INT,    -- 围栏内车辆数
    vehicle_count_outside_fence INT,   -- 围栏外车辆数
    
    -- 间隔数据
    inflow INT,                        -- 流入数
    outflow INT,                       -- 流出数
    suspected_dispatch INT,            -- 疑似调度入
    
    -- 分析元数据
    source VARCHAR(20) DEFAULT 'ai',   -- ai / manual
    confidence_score FLOAT,            -- 综合置信度
    matched_pairs INT,                 -- 匹配到的车辆对数
    
    -- 校验状态
    verified BOOLEAN DEFAULT FALSE,    -- 是否人工核对通过
    verified_by VARCHAR(50),           -- 核对人
    verified_at TIMESTAMP,
    manual_corrections JSONB,          -- 人工修正内容
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_vehicle_data_task ON vehicle_data(task_id);
CREATE INDEX idx_vehicle_data_point_brand ON vehicle_data(point_id, brand);

-- ============================================
-- 设备表
-- ============================================
CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) UNIQUE,      -- ADB设备标识
    model VARCHAR(100),                -- 设备型号
    android_version VARCHAR(20),
    status VARCHAR(20) DEFAULT 'idle', -- idle / busy / offline / error
    current_task_id INT,
    last_heartbeat TIMESTAMP,
    total_tasks INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 账号表
-- ============================================
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    brand VARCHAR(10) NOT NULL,        -- MT / DD / HB
    phone VARCHAR(20),
    status VARCHAR(20) DEFAULT 'available', -- available / in_use / banned / expired
    device_id VARCHAR(50),
    last_used TIMESTAMP,
    use_count INT DEFAULT 0,
    max_daily_uses INT DEFAULT 50,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 异常记录表
-- ============================================
CREATE TABLE anomalies (
    id SERIAL PRIMARY KEY,
    task_id INT REFERENCES collection_tasks(id),
    point_id INT REFERENCES points(id),
    type VARCHAR(50),                  -- vehicle_count_spike / alignment_failed / ...
    severity VARCHAR(20),              -- low / medium / high
    description TEXT,
    detected_at TIMESTAMP DEFAULT NOW(),
    resolved BOOLEAN DEFAULT FALSE,
    resolved_by VARCHAR(50),
    resolved_at TIMESTAMP
);
```

### 2.2 数据量估算

| 数据类型 | 单期数据量 | 年数据量（12期） |
|---------|-----------|----------------|
| 截图文件 | ~20,160张 × ~500KB = ~10GB | ~120GB |
| 车辆数据记录 | ~960 × 3 × 7 = ~20,160行 | ~24万行 |
| 截图元数据 | ~20,160行 | ~24万行 |
| 异常记录 | ~预估500行 | ~6000行 |

> 存储方案：PostgreSQL数据量不大，截图文件存储在MinIO，按 `任务期/城市/点位/品牌/时间` 目录组织。

### 2.3 MinIO对象存储目录结构

```
snapshots/
├── 2026-11/                          # 期号
│   ├── nanning/                      # 城市
│   │   ├── point_64348716/           # 点位ID
│   │   │   ├── MT/
│   │   │   │   ├── T_20261101_180000.png
│   │   │   │   ├── T+10_20261101_181000.png
│   │   │   │   ├── T+20_20261101_182000.png
│   │   │   │   └── ...
│   │   │   ├── DD/
│   │   │   │   └── ...
│   │   │   └── HB/
│   │   │       └── ...
│   │   └── point_62218946/
│   │       └── ...
│   └── luoyang/
│       └── ...
```

---

## 3. 围栏判断与坐标系处理

### 3.1 GCJ-02坐标系

| 坐标系 | 使用方 | 说明 |
|--------|--------|------|
| GCJ-02 | 高德地图、腾讯地图、美团、滴滴、哈啰 | 中国大陆标准加密坐标系 |
| WGS-84 | GPS原始坐标、Google Maps | 国际标准 |
| BD-09 | 百度地图 | 在GCJ-02基础上二次加密 |

本项目全链路使用GCJ-02，与三家App一致，**无需坐标转换**。

### 3.2 围栏创建

```python
from shapely.geometry import Polygon, Point
import math

def create_fence(center_lat, center_lng, side_length_m=100):
    """
    以中心点创建正方形围栏
    
    参数：
        center_lat, center_lng: GCJ-02中心点坐标
        side_length_m: 围栏边长（米），默认100m
    
    返回：
        四个角的坐标列表 [(lng, lat), ...]
    """
    half_side = side_length_m / 2  # 50m
    
    # 将米转换为经纬度偏移
    # 纬度：1度 ≈ 111320米
    lat_offset = half_side / 111320
    
    # 经度：1度 ≈ 111320 × cos(lat) 米
    lng_offset = half_side / (111320 * math.cos(math.radians(center_lat)))
    
    corners = [
        (center_lng - lng_offset, center_lat - lat_offset),  # 左下
        (center_lng + lng_offset, center_lat - lat_offset),  # 右下
        (center_lng + lng_offset, center_lat + lat_offset),  # 右上
        (center_lng - lng_offset, center_lat + lat_offset),  # 左上
    ]
    
    return corners


def point_in_fence(lat, lng, fence_corners):
    """
    判断坐标点是否在围栏内
    
    参数：
        lat, lng: 待判断的点坐标
        fence_corners: 围栏四角坐标列表
    """
    polygon = Polygon(fence_corners)
    point = Point(lng, lat)
    return polygon.contains(point)
```

### 3.3 点位数据导入

```python
import openpyxl

def import_points_from_excel(file_path):
    """
    从甲方提供的Excel导入点位数据
    
    Excel格式（来自"assets/电单数车 线上测试点位 to 供应商.xlsx"）：
    序号 | 城市名称 | id | park_name | 围栏经纬度 | HB | DD
    """
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb['工作表1']
    
    points = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        # 跳过空行和补点标记行
        seq = row[1]
        city = row[2]
        ext_id = row[3]
        park_name = row[4]
        fence_str = row[5]
        
        if not city or not park_name or not fence_str:
            continue
        
        # 解析围栏经纬度（逗号分隔的8个数值：4个点的lng,lat）
        coords = [float(x) for x in fence_str.split(",")]
        # 每2个为一组：(lng, lat)
        corners = [(coords[i], coords[i+1]) for i in range(0, len(coords), 2)]
        
        # 计算中心点
        center_lng = sum(c[0] for c in corners) / len(corners)
        center_lat = sum(c[1] for c in corners) / len(corners)
        
        points.append({
            "city_name": city,
            "external_id": str(ext_id),
            "park_name": park_name,
            "center_lat": center_lat,
            "center_lng": center_lng,
            "fence_corners": corners,
        })
    
    return points
```

---

## 4. API接口设计

### 4.1 任务管理

```python
# backend/app/api/tasks.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

class CreateTaskRequest(BaseModel):
    period: str                    # "2026-11"
    city_id: int
    time_slot: str                 # "周中晚"
    start_time: str                # ISO datetime
    point_ids: list[int]           # 指定点位列表（可选，不传则全城）

@router.post("/")
def create_task(req: CreateTaskRequest):
    """创建采集任务"""
    task = create_collection_task(req)
    # 触发Celery调度
    create_city_task.delay(task.id, ...)
    return {"task_id": task.id, "status": "scheduled"}

@router.get("/")
def list_tasks(status: str = None, city_id: int = None):
    """查询任务列表"""
    tasks = query_tasks(status=status, city_id=city_id)
    return tasks

@router.get("/{task_id}")
def get_task(task_id: int):
    """查询任务详情"""
    task = get_task_detail(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task

@router.get("/{task_id}/data")
def get_task_data(task_id: int, brand: str = None):
    """获取任务采集的车辆数据"""
    data = query_vehicle_data(task_id, brand=brand)
    return data

@router.get("/{task_id}/progress")
def get_task_progress(task_id: int):
    """获取任务进度"""
    progress = calculate_progress(task_id)
    return {
        "total_points": progress["total"],
        "completed": progress["completed"],
        "failed": progress["failed"],
        "in_progress": progress["in_progress"],
        "percentage": progress["completed"] / progress["total"] * 100,
    }
```

### 4.2 点位管理

```python
# backend/app/api/points.py
from fastapi import UploadFile, File

@router.post("/import")
async def import_points(file: UploadFile = File(...)):
    """从Excel导入点位"""
    # 保存上传文件
    path = f"/tmp/{file.filename}"
    with open(path, "wb") as f:
        f.write(await file.read())
    
    # 解析并导入
    points = import_points_from_excel(path)
    count = save_points(points)
    return {"imported": count}

@router.get("/")
def list_points(city_id: int = None, time_slot: str = None):
    """查询点位列表"""
    return query_points(city_id=city_id, time_slot=time_slot)

@router.get("/{point_id}/map")
def get_point_map(point_id: int):
    """获取点位地图信息（前端高德地图渲染用）"""
    point = get_point(point_id)
    return {
        "center": {"lat": point.center_lat, "lng": point.center_lng},
        "fence": point.fence_corners,
        "park_name": point.park_name,
    }
```

### 4.3 设备管理

```python
@router.get("/devices")
def list_devices():
    """查询设备状态"""
    devices = DeviceManager().list_all()
    return devices

@router.post("/devices/{device_id}/health")
def device_health_check(device_id: str):
    """设备健康检查"""
    return DeviceManager().health_check(device_id)
```

### 4.4 数据查询与导出

```python
@router.get("/data/{point_id}")
def get_point_data(point_id: int, task_id: int = None):
    """获取某个点位的车辆数据"""
    data = query_vehicle_data(point_id=point_id, task_id=task_id)
    return format_data_table(data)

@router.get("/reports/{task_id}/export")
def export_report(task_id: int, format: str = "xlsx"):
    """导出报告"""
    if format == "xlsx":
        file_path = generate_excel_report(task_id)
        return FileResponse(file_path, filename=f"report_{task_id}.xlsx")
```

---

## 5. 关键技术决策记录

| 决策点 | 选择 | 理由 | 日期 |
|--------|------|------|------|
| 任务队列 | Celery + Redis | Python生态成熟，支持定时任务和重试 | 2026-10-30 |
| 数据库 | PostgreSQL + PostGIS | 空间查询原生支持，围栏判断性能好 | 2026-10-30 |
| 对象存储 | MinIO（试点）→ OSS（规模化） | 试点自部署零成本，S3兼容可平滑迁移 | 2026-10-30 |
| API框架 | FastAPI | 异步高性能，自动文档，类型安全 | 2026-10-30 |
| 坐标系 | GCJ-02全链路统一 | 与三家App一致，无需转换 | 2026-10-30 |
| 围栏表示 | PostGIS POLYGON + Shapely | 支持精确的多边形包含判断 | 2026-10-30 |
