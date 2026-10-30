# 单城市端到端试点实施方案

> 文档编号：wb_06  
> 创建日期：2026-10-30  
> 文档定位：**执行入口文档** — 从零到跑通一个城市完整试点的详细步骤

---

## 1. 试点目标

在一个城市上验证完整的端到端流程：

```
点位录入 → 任务创建 → 自动化采集 → AI数车 → 质量校验 → 人工核对 → 报告导出
```

### 1.1 试点范围

| 项目 | 规格 |
|------|------|
| 试点城市 | 南宁市（已有3个点位+SOP示例数据） |
| 点位数 | 20个（需补充17个） |
| 时段 | 周中晚高峰（18:00-19:00） |
| 平台 | MT / DD / HB 三家 |
| 截图总数 | 20点位 × 3品牌 × 7时点 = 420张 |
| 预期工期 | 4周 |

### 1.2 试点成功标准

| 验收项 | 目标 |
|--------|------|
| 自动化采集成功率 | ≥ 95%（420张截图中至少399张成功） |
| 时点车辆数准确率 | ≥ 95%（与人工抽检对比） |
| 流入流出准确率 | ≥ 80%（与人工全检对比） |
| 端到端流程跑通 | 从任务创建到报告导出全流程无人工干预 |
| 报告格式符合甲方要求 | Excel报告包含所有要求字段 |

---

## 2. 里程碑规划

```
Week 1: 基础设施搭建
├── Day 1-2: 开发环境 + Docker部署
├── Day 3-4: 数据库 + API服务搭建
└── Day 5: 前端基础框架

Week 2: 采集模块开发
├── Day 1-2: Airtest环境 + 设备准备
├── Day 3-4: 三家App操控脚本开发
├── Day 5: GPS定位模拟 + 自动截图流程

Week 3: AI数车模块开发
├── Day 1-2: 数据标注 + YOLOv8训练
├── Day 3-4: 图像配准 + 车辆匹配算法
├── Day 5: 流入流出计算 + 端到端联调

Week 4: 试运行 + 优化
├── Day 1-2: 20个点位完整采集（一期）
├── Day 3: 人工核对 + 准确率评估
├── Day 4: 问题修复 + 参数调优
├── Day 5: 报告生成 + 试点验收
```

---

## 3. Week 1: 基础设施搭建

### 3.1 Day 1-2: 开发环境 + Docker部署

#### 环境准备

```bash
# 1. 创建项目目录
mkdir -p e-bike-monitor/{backend,frontend,scripts,models,datasets}
cd e-bike-monitor

# 2. 初始化Git
git init

# 3. 创建Docker Compose编排
```

#### docker-compose.yml

```yaml
version: "3.8"

services:
  # PostgreSQL + PostGIS
  postgres:
    image: postgis/postgis:15-3.4
    environment:
      POSTGRES_DB: ebike_monitor
      POSTGRES_USER: ebike
      POSTGRES_PASSWORD: ${DB_PASSWORD:-ebike_dev_2026}
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./scripts/init_db.sql:/docker-entrypoint-initdb.d/init.sql

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  # MinIO
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: ebike
      MINIO_ROOT_PASSWORD: ${MINIO_PASSWORD:-ebike_dev_2026}
    volumes:
      - minio_data:/data

  # FastAPI Backend
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
      - minio
    environment:
      DATABASE_URL: postgresql://ebike:ebike_dev_2026@postgres:5432/ebike_monitor
      REDIS_URL: redis://redis:6379/0
      MINIO_ENDPOINT: minio:9000
      MINIO_ACCESS_KEY: ebike
      MINIO_SECRET_KEY: ebike_dev_2026
    volumes:
      - ./backend:/app
      - ./snapshots:/snapshots

  # Celery Worker (采集)
  celery_collect:
    build: ./backend
    command: celery -A workers.celery_app worker -Q collection -l info --concurrency=2
    depends_on:
      - redis
      - postgres
    volumes:
      - ./backend:/app
      - ./snapshots:/snapshots

  # Celery Worker (AI分析)
  celery_analyze:
    build: ./backend
    command: celery -A workers.celery_app worker -Q analysis -l info --concurrency=1
    depends_on:
      - redis
      - postgres
    volumes:
      - ./backend:/app
      - ./models:/models

  # Celery Beat (定时调度)
  celery_beat:
    build: ./backend
    command: celery -A workers.celery_app beat -l info
    depends_on:
      - redis

  # Frontend
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
    volumes:
      - ./frontend:/app
      - /app/node_modules

volumes:
  pg_data:
  redis_data:
  minio_data:
```

#### 后端Dockerfile

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

# 系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    adb \
    && rm -rf /var/lib/apt/lists/*

# Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Airtest
RUN pip install airtest pocouimobile

WORKDIR /app
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### requirements.txt

```
# Web框架
fastapi==0.104.1
uvicorn==0.24.0
python-multipart==0.0.6

# 数据库
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
geoalchemy2==0.14.2
alembic==1.12.1

# 任务队列
celery==5.3.4
redis==5.0.1

# 对象存储
minio==7.2.0

# 图像处理
opencv-python-headless==4.8.1.78
Pillow==10.1.0
scikit-learn==1.3.2
scipy==1.11.4

# AI/ML
ultralytics==8.0.200
onnxruntime==1.16.1

# OCR
paddleocr==2.7.0.3

# 采集
airtest==1.3.0.1
pocoui==1.0.92

# 工具
pydantic==2.5.2
python-jose==3.3.0
openpyxl==3.1.2
shapely==2.0.2
httpx==0.25.2
```

### 3.2 Day 3-4: 数据库 + API服务

```bash
# 启动基础设施
docker-compose up -d postgres redis minio

# 初始化数据库
docker-compose exec backend python scripts/init_db.py

# 导入已有点位数据
docker-compose exec backend python scripts/load_points.py \
    "/data/电单数车 线上测试点位 to 供应商.xlsx"

# 启动后端
docker-compose up -d backend

# 验证API
curl http://localhost:8000/docs  # Swagger文档
curl http://localhost:8000/api/points  # 查询点位
```

### 3.3 Day 5: 前端基础

```bash
# 创建React项目
cd frontend
npm create vite@. -- --template react-ts
npm install antd @ant-design/icons axios zustand konva react-konva

# 基础页面结构
mkdir -p src/pages src/components src/api src/stores
```

---

## 4. Week 2: 采集模块开发

### 4.1 Day 1-2: Airtest环境 + 设备准备

```bash
# 安装Airtest IDE（开发调试用）
# 下载: https://airtest.netease.com/

# 在开发机上安装Airtest Python库
pip install airtest pocoui

# 连接Android设备
adb devices  # 确认设备已连接

# 验证Airtest连接
python -c "
from airtest.core.api import connect_device
device = connect_device('Android:///')
print(f'Connected: {device}')
print(f'Resolution: {device.get_current_resolution()}')
"
```

#### 设备准备清单

```
□ 3台Android手机（不同品牌型号推荐）
□ 每台手机开启开发者模式 + USB调试 + 模拟定位
□ 每台手机安装：美团、滴滴、哈啰
□ 每台手机登录三家App（使用收集到的账号）
□ 手机连接到服务器（USB或WiFi ADB）
□ 安装AirtestAgent到每台手机（通过Airtest IDE自动安装）
□ 准备模板图片（各App的按钮截图，用于图像匹配）
```

### 4.2 Day 3-4: 三家App操控脚本

这是最耗时的开发工作。每家App的操控流程需要反复调试。

#### 开发顺序

```
1. 先开发美团采集器（SOP以美团为基准）
   ├── 启动App → 进入骑单车界面
   ├── 定位到目标位置
   ├── 调整比例尺
   └── 截图

2. 再开发滴滴和哈啰采集器
   └── 参照美团的流程适配

3. 最后开发三家对齐逻辑
   └── 比例尺统一 + 边界对齐
```

#### 模板图片准备

每家App需要截取以下模板图片（用Airtest IDE的截图功能）：

```
templates/
├── mt/
│   ├── mt_bike_entry.png      # 骑单车入口按钮
│   ├── mt_locate_button.png   # 定位按钮
│   ├── mt_vehicle_icon.png    # 电单车图标（用于检测）
│   ├── mt_scale_bar.png       # 比例尺标识
│   └── mt_loading.png         # 加载中标识
├── dd/
│   ├── dd_bike_tab.png
│   ├── dd_locate_button.png
│   ├── dd_vehicle_icon.png
│   ├── dd_scale_bar.png
│   └── dd_loading.png
└── hb/
    ├── hb_locate_button.png
    ├── hb_vehicle_icon.png
    ├── hb_scale_bar.png
    └── hb_loading.png
```

### 4.3 Day 5: GPS定位 + 自动截图流程

```python
# 完整的单点位采集脚本
# scripts/test_single_point.py

def test_collect_single_point():
    """测试单个点位的完整采集流程"""
    
    # 1. 连接设备
    device = connect_device("Android:///")
    
    # 2. 设置GPS定位（南宁-广西卫健委）
    set_mock_location(device, lat=22.804599, lng=108.327540)
    
    # 3. 采集第一轮（T时刻）
    collector = MeituanCollector(device)
    collector.open_bike_interface()
    collector.align_map_scale()
    collector.capture("T")
    
    # 4. 等待10分钟
    print("等待10分钟...")
    time.sleep(600)
    
    # 5. 采集第二轮（T+10）
    collector.capture("T+10")
    
    # ... 重复到T+60
    
    print("采集完成！")
```

---

## 5. Week 3: AI数车模块开发

### 5.1 Day 1-2: 数据标注 + 模型训练

#### 标注数据准备

```
1. 收集已有截图
   - SOP示例中的南宁数据（21张）
   - Week 2测试采集的截图（预估100-200张）
   
2. 标注工具：CVAT（开源，Docker部署）
   docker run --rm -p 8080:8080 cvat/server
   
3. 标注规则
   - 每个电单车图标画一个矩形框
   - 类别：mt_bike / dd_bike / hb_bike / mt_cluster / dd_cluster / hb_cluster
   - 至少标注200张（每品牌至少50张）

4. 导出YOLO格式
   - CVAT → Export → YOLO 1.1
```

#### 模型训练

```bash
# 训练
python scripts/train_model.py --data datasets/ebike.yaml --epochs 100

# 验证
python scripts/validate_model.py --model models/yolov8s_ebike.onnx

# 测试单张图片
python scripts/test_detection.py \
    --model models/yolov8s_ebike.onnx \
    --image /snapshots/test_mt_T.png
```

### 5.2 Day 3-4: 图像配准 + 车辆匹配

```python
# 开发图像配准模块
# backend/analyzers/comparator.py

# 开发车辆匹配模块
# backend/analyzers/matcher.py

# 单元测试：用SOP示例数据验证
python -m pytest tests/test_comparator.py -v
python -m pytest tests/test_matcher.py -v
```

#### 用SOP示例验证准确率

```python
# scripts/validate_accuracy.py
"""
用SOP示例中的南宁数据验证AI数车准确率
已知人工数车结果，对比AI结果
"""

def validate_against_sop():
    # SOP中的人工结果
    manual_results = {
        "HB": {
            "T": 18, "T+10": 15, "T+20": 17, "T+30": 16,
            "T+40": 17, "T+50": 21, "T+60": 20,
        },
        # ... MT, DD
    }
    
    # 运行AI分析
    ai_results = analyze_point("nanning_zhenxinglu")
    
    # 对比
    for brand in ["MT", "DD", "HB"]:
        for time_label in TIME_LABELS:
            ai_count = ai_results[brand][time_label]["vehicle_count"]
            manual_count = manual_results[brand][time_label]
            diff = abs(ai_count - manual_count)
            print(f"{brand} {time_label}: AI={ai_count} 人工={manual_count} 差异={diff}")
```

### 5.3 Day 5: 端到端联调

```bash
# 完整流程测试
1. 创建任务（Web面板）
2. 任务自动调度采集
3. 截图自动上传
4. AI自动分析
5. 质量校验
6. 查看结果
7. 导出报告
```

---

## 6. Week 4: 试运行 + 优化

### 6.1 Day 1-2: 完整采集运行

```
任务：南宁市 20个点位 × 周中晚高峰 × 三家平台
时间：18:00-19:00（每个点位1小时）
设备：3-5台Android手机并行

执行：
□ 17:30 设备准备（解锁、App检查、定位设置）
□ 18:00-19:00 自动采集（20点位并行，每点位7轮截图）
□ 19:00-19:30 AI数车批量分析
□ 19:30-20:00 质量校验 + 异常标记
```

### 6.2 Day 3: 人工核对

```
核对计划：
□ 全检所有被自动校验标记为"high"的数据
□ 抽检10%正常数据
□ 重点核对流入流出数（已知短板）
□ 记录AI vs 人工差异

核对工具：前端Review页面
```

### 6.3 Day 4: 问题修复

根据试运行发现的问题修复：

| 预期问题 | 修复方向 |
|---------|---------|
| 某家App操控失败 | 调整模板图片/操控逻辑 |
| GPS定位偏差 | 校准定位模拟参数 |
| AI检测漏检 | 补充训练数据，调整置信度阈值 |
| 流入流出错误 | 调整匹配距离阈值，优化配准 |
| 截图边界不齐 | 优化比例尺对齐逻辑 |

### 6.4 Day 5: 报告生成 + 验收

```bash
# 生成报告
curl -X GET http://localhost:8000/api/reports/1/export?format=xlsx

# 验收检查清单
□ 20个点位数据完整（420张截图）
□ 报告格式符合甲方要求
□ 时点车辆数准确率 ≥ 95%
□ 流入流出准确率 ≥ 80%
□ 截图可追溯（索引表完整）
□ 三家时空一致性验证通过
```

---

## 7. 风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| Airtest操控某家App不稳定 | 高 | 采集失败 | 保留人工截图作为fallback；重点调试 |
| YOLOv8训练数据不足 | 中 | 检测准确率低 | 数据增强；迁移学习；人工标注更多数据 |
| GPS模拟被App识别 | 低 | 定位失败 | 使用Xposed方案；或物理GPS模拟器 |
| 设备性能不足（USB带宽） | 中 | 多设备同时截图卡顿 | 降低同时采集设备数；错开截图时间 |
| 三家App更新UI | 低 | 模板匹配失效 | 模板图片定期更新；UI变化告警 |
| 账号被封禁 | 中 | 无法登录App | 多账号轮转；降低操作频率 |

---

## 8. 试点交付物清单

| 交付物 | 格式 | 说明 |
|--------|------|------|
| 采集报告 | Excel | 20点位×3品牌×7时点的完整数据 |
| 截图存档 | PNG | 420张截图，按目录组织 |
| 截图索引 | Excel | 每张截图的元数据索引 |
| 质量报告 | Excel | 准确率统计、异常记录 |
| 系统部署 | Docker | 可复现的Docker Compose部署 |
| 源代码 | Git | 完整后端+前端+脚本代码 |
| 技术文档 | Markdown | wb_00 ~ wb_07 全套文档 |
| 模型权重 | ONNX | 训练好的YOLOv8模型 |
| 模板图片 | PNG | 三家App的操作模板图片集 |

---

## 9. 从试点到规模化的路径

```
试点完成（南宁，20点位）
    │
    │ 验证点：
    │ ✓ 自动化采集可行
    │ ✓ AI数车准确率达标
    │ ✓ 端到端流程跑通
    │
    ▼
扩展到第二个城市（洛阳，20点位）
    │
    │ 验证点：
    │ ✓ 不同城市点位适配
    │ ✓ 参数无需大调整
    │
    ▼
扩展到4个时段
    │
    │ 验证点：
    │ ✓ 早高峰/晚高峰/周末等不同时段
    │
    ▼
扩展到12城市×4时段×20点位 = 960点位
    │
    │ 基础设施升级：
    │ - Docker Compose → Kubernetes
    │ - 实体手机 → 云手机集群
    │ - 单GPU → 多GPU推理
    │
    ▼
常态化运行（每月一期）
```
