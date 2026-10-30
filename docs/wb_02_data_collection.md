# 数据采集模块：App自动化截图方案

> 文档编号：wb_02  
> 创建日期：2026-10-30  
> 文档定位：App自动化操控、设备管理、定位模拟、SOP技术化实现

---

## 1. 模块目标

将当前依赖人工现场操作的截图SOP，升级为**无人值守自动化采集系统**：

- 自动操控三家App（美团/滴滴/哈啰）的电单车找车界面
- 自动模拟GPS定位到目标点位坐标
- 按7个时间节点（T到T+60，每10分钟一轮）自动截图
- 三家App比例尺/边界自动对齐
- 支持多设备并行采集不同点位
- 截图自动归档，附带完整元数据（时间、点位、品牌、设备）

---

## 2. 技术选型：Airtest + ADB

### 2.1 为什么选Airtest

| 对比项 | Airtest | Appium | UIAutomator2 |
|--------|---------|--------|--------------|
| 开发方 | 网易（中国） | 社区 | Google |
| 中国App兼容性 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 图像识别能力 | ⭐⭐⭐⭐⭐（内置） | ❌ 需额外集成 | ❌ 需额外集成 |
| UI元素操控 | ⭐⭐⭐⭐（Poco框架） | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Python支持 | ⭐⭐⭐⭐⭐（原生） | ⭐⭐⭐⭐（客户端） | ⭐⭐⭐⭐ |
| 上手难度 | 低 | 中 | 中 |
| 截图功能 | 内置snapshot() | 需额外封装 | 需额外封装 |
| 社区活跃度 | 高（游戏+App测试） | 最高 | 中 |

**选型结论**：Airtest。核心优势是**图像识别操控**——电单车App中的地图界面很难通过UI元素ID定位按钮，但可以通过图像匹配找到"骑单车"按钮、定位按钮等。这与SOP中"人眼找按钮"的操作逻辑完全一致。

### 2.2 技术栈清单

| 组件 | 技术 | 版本 | 用途 |
|------|------|------|------|
| 自动化框架 | Airtest | 1.3+ | App操控核心引擎 |
| UI操控 | Poco | 1.0+ | UI元素级操控（辅助） |
| 设备连接 | ADB | 最新 | Android设备调试桥 |
| 定位模拟 | ADB mockLocation | - | GPS位置伪造 |
| 截图 | Airtest snapshot() | - | 带元数据的截图 |
| 设备管理 | Python + ADB | - | 多设备注册、状态监控 |
| 并发控制 | Python multiprocessing | - | 多设备并行采集 |

---

## 3. 设备方案

### 3.1 实体手机方案（试点阶段）

| 项目 | 规格 | 数量 | 说明 |
|------|------|------|------|
| 测试手机 | Android 11+ | 3-5台 | 建议不同品牌型号，避免设备指纹一致 |
| USB Hub | 带供电 | 1台 | 连接多台手机到服务器 |
| 手机卡 | 各平台归属地 | 每台1张 | 用于接收验证码（如需重新登录） |
| 手机架 | 多层 | 1个 | 物理摆放，保持屏幕清洁 |

**设备准备清单**：
```
□ 开启开发者模式（设置 → 关于手机 → 连续点击版本号7次）
□ 开启USB调试（开发者选项 → USB调试）
□ 开启模拟定位（开发者选项 → 选择模拟位置信息应用）
□ 安装三家App（美团、滴滴、哈啰）
□ 登录三家App账号（使用收集到的真实账号）
□ 关闭屏幕自动锁定
□ 调整屏幕亮度（节能但保证截图清晰）
□ 关闭通知（避免截图时通知遮挡）
□ 安装AirtestAgent（通过Airtest IDE连接后自动安装）
```

### 3.2 云手机方案（规模化备选）

| 平台 | 优势 | 劣势 | 适用阶段 |
|------|------|------|---------|
| 红手指 | 国内主流，稳定性好 | 价格较高（约80-150元/台/月） | 12城规模化 |
| 雷电云手机 | 性价比高 | 偶有卡顿 | 测试阶段 |
| AWS Device Farm | 国际标准 | 中国App兼容性不确定 | 不推荐 |

**决策建议**：试点阶段用实体手机（成本低、可控性强），验证方案可行后规模化时评估云手机。

---

## 4. 采集流程设计

### 4.1 单点位采集完整流程

```
┌─────────────────────────────────────────────────────────────┐
│                  单点位采集流程（1小时）                      │
│                                                              │
│  T=0min   ┌─── 准备阶段 ───┐                                │
│           │ 1. 设备解锁      │                                │
│           │ 2. 设置GPS定位   │ → 模拟到点位中心坐标            │
│           │ 3. 打开App       │ → 美团/滴滴/哈啰                │
│           │ 4. 进入找车界面  │ → 点击"骑单车"                  │
│           │ 5. 等待地图加载  │ → 等待车辆图标出现              │
│           │ 6. 调整比例尺    │ → 放大到100m×100m视野           │
│           │ 7. 三家对齐      │ → 比例尺统一                    │
│           └──────────────────┘                                │
│                                                              │
│  T=0min   截图第1轮：MT截图 → DD截图 → HB截图（T时刻）       │
│           ↓ 保存3张截图，T时刻的截图需额外圈出车辆范围          │
│                                                              │
│  T+10min  截图第2轮：MT → DD → HB（T+10时刻）                │
│  T+20min  截图第3轮：MT → DD → HB（T+20时刻）                │
│  T+30min  截图第4轮：MT → DD → HB（T+30时刻）                │
│  T+40min  截图第5轮：MT → DD → HB（T+40时刻）                │
│  T+50min  截图第6轮：MT → DD → HB（T+50时刻）                │
│  T+60min  截图第7轮：MT → DD → HB（T+60时刻）                │
│                                                              │
│  完成     截图归档 → 21张图片上传MinIO → 元数据写入PG         │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 三家App比例尺对齐策略（SOP Step2-3的技术化）

SOP中人工对齐比例尺是痛点，自动化方案策略：

```python
# 比例尺对齐策略
# 1. 以美团为基准（SOP要求先调整MT）
# 2. 通过双指缩放控制地图缩放级别
# 3. 用图像匹配验证三家视野范围一致

def align_map_scale(device, brand):
    """
    对齐地图比例尺到统一缩放级别
    """
    # Step 1: 获取当前地图缩放级别
    # 多数App在地图上有比例尺标识，可通过OCR读取
    scale_text = ocr_read_scale(device)
    
    # Step 2: 通过双指缩放调整到目标级别
    # 目标：100m×100m区域在屏幕中清晰可见
    # 通常需要缩放到地图级别18-19级（约50-100m视野）
    target_scale = "100m"  # 比例尺标识文字
    
    while not is_scale_matched(scale_text, target_scale):
        pinch_to_zoom(device, direction="in" or "out")
        scale_text = ocr_read_scale(device)
    
    # Step 3: 验证三家地图中心点一致
    # 通过截图中的地标（道路交叉等）做图像配准验证
    verify_center_alignment(device, reference_point)
```

### 4.3 GPS定位模拟

```python
import subprocess
import time

def set_mock_location(device_id, lat, lng):
    """
    通过ADB设置模拟GPS定位
    前提：设备已开启"模拟位置信息应用"
    
    参数：
        device_id: ADB设备标识
        lat, lng: GCJ-02坐标（纬度，经度）
    """
    # 方案1：通过ADB命令直接设置（需Android 12+或特定ROM）
    cmd = f"adb -s {device_id} emu geo fix {lng} {lat}"
    subprocess.run(cmd, shell=True)
    
    # 方案2：通过Airtest的Location插件
    # 需要安装 Airtest Location Provider App
    # device.set_location(lat, lng)
    
    # 方案3（推荐）：通过MockLocation App
    # 安装 "Lockito" 或 "Fake GPS Location" App
    # 通过Intent或ADB广播设置位置
    
    time.sleep(2)  # 等待App地图刷新到新位置


def verify_location(device, expected_lat, expected_lng):
    """
    验证App地图已定位到目标位置
    通过截图OCR读取地图上的地名或坐标标识
    """
    screenshot = device.snapshot()
    # 方案：截图后通过OCR匹配附近的POI名称
    # 如果匹配到点位名称（如"万达广场"），则定位成功
    poi_text = ocr_extract_text(screenshot)
    return expected_poi_name in poi_text
```

### 4.4 截图元数据管理

每张截图必须附带完整的元数据，用于后续追溯和校验：

```python
import json
from datetime import datetime

def capture_snapshot(device, task_id, point_id, brand, time_label):
    """
    截图并保存元数据
    
    参数：
        device: Airtest设备对象
        task_id: 采集任务ID
        point_id: 点位ID
        brand: 平台品牌（MT/DD/HB）
        time_label: 时间标签（T/T+10/T+20...）
    """
    capture_time = datetime.now().isoformat()
    
    # 截图
    filename = f"{task_id}_{point_id}_{brand}_{time_label}_{capture_time}.png"
    filepath = f"/snapshots/{filename}"
    device.snapshot(filename=filepath)
    
    # 元数据
    metadata = {
        "task_id": task_id,
        "point_id": point_id,
        "brand": brand,
        "time_label": time_label,
        "capture_time": capture_time,
        "device_id": device.serialno,
        "file_path": filepath,
        "point_name": point_name,
        "point_coord": {"lat": lat, "lng": lng},
        "fence_coord": fence_polygon,
        "app_version": get_app_version(device, brand),
        "map_zoom_level": current_zoom,
    }
    
    # 上传到MinIO
    minio_client.upload(filepath, metadata)
    
    # 元数据写入PostgreSQL
    db.insert_snapshot(metadata)
    
    return metadata
```

---

## 5. 三家App操控详细方案

### 5.1 美团（MT）操控流程

```python
class MeituanCollector(BaseCollector):
    """美团电单车采集器"""
    
    APP_PACKAGE = "com.sankuai.meituan"
    BIKE_ENTRY = "骑单车"  # 入口按钮文字
    
    def open_bike_interface(self, device):
        """打开美团电单车找车界面"""
        # 1. 启动美团App
        device.start_app(self.APP_PACKAGE)
        time.sleep(3)
        
        # 2. 通过图像匹配找到"骑单车"入口
        #    可能在首页顶部tab或中间区域
        device.touch(Template("mt_bike_entry.png"))
        time.sleep(2)
        
        # 3. 等待地图加载（等待车辆图标出现）
        self._wait_for_map_ready(device, brand="MT")
        
        # 4. 点击定位按钮回到当前位置
        device.touch(Template("mt_locate_button.png"))
        time.sleep(1)
```

### 5.2 滴滴（DD）操控流程

```python
class DidiCollector(BaseCollector):
    """滴滴电单车采集器"""
    
    APP_PACKAGE = "com.sdu.didi.psnger"
    BIKE_ENTRY = "骑行"
    
    def open_bike_interface(self, device):
        """打开滴滴电单车找车界面"""
        device.start_app(self.APP_PACKAGE)
        time.sleep(3)
        
        # 滴滴的骑行入口可能在底部tab
        device.touch(Template("dd_bike_tab.png"))
        time.sleep(2)
        
        self._wait_for_map_ready(device, brand="DD")
        device.touch(Template("dd_locate_button.png"))
        time.sleep(1)
```

### 5.3 哈啰（HB）操控流程

```python
class HellobikeCollector(BaseCollector):
    """哈啰电单车采集器"""
    
    APP_PACKAGE = "com.jingyao.easybike"
    BIKE_ENTRY = "骑车"
    
    def open_bike_interface(self, device):
        """打开哈啰电单车找车界面"""
        device.start_app(self.APP_PACKAGE)
        time.sleep(3)
        
        # 哈啰通常是独立App，首页即地图
        # 等待地图加载
        self._wait_for_map_ready(device, brand="HB")
        
        # 点击定位按钮
        device.touch(Template("hb_locate_button.png"))
        time.sleep(1)
```

### 5.4 通用辅助方法

```python
class BaseCollector:
    """采集器基类"""
    
    def _wait_for_map_ready(self, device, brand):
        """
        等待地图加载完成
        判断条件：屏幕上出现车辆图标
        超时：30秒
        """
        for _ in range(15):  # 每2秒检查一次，最多30秒
            screenshot = device.snapshot()
            if self._detect_vehicle_icons(screenshot, brand):
                return True
            time.sleep(2)
        
        raise MapNotReadyError(f"{brand} 地图加载超时")
    
    def _detect_vehicle_icons(self, screenshot, brand):
        """
        检测截图中是否有车辆图标
        使用轻量级模板匹配（OpenCV matchTemplate）
        预先准备三家平台的车辆图标模板
        """
        import cv2
        template = cv2.imread(f"templates/{brand}_vehicle_icon.png")
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        return (result >= 0.8).any()
    
    def pinch_to_zoom(self, device, direction="in", duration=0.5):
        """
        双指缩放地图
        direction: "in"（放大）或 "out"（缩小）
        """
        w, h = device.get_current_resolution()
        cx, cy = w // 2, h // 2
        
        if direction == "in":
            # 从外向内捏合（放大）
            device.pinch(in_or_out="in", center=(cx, cy), duration=duration)
        else:
            device.pinch(in_or_out="out", center=(cx, cy), duration=duration)
    
    def capture_round(self, device, task_id, point_id, time_label):
        """
        截取一轮三家App截图
        """
        results = []
        for collector in [self.mt, self.dd, self.hb]:
            collector.open_bike_interface(device)
            self.align_map_scale(device, collector.brand)
            
            metadata = capture_snapshot(
                device, task_id, point_id, 
                collector.brand, time_label
            )
            results.append(metadata)
            
            # 切换到下一家App前等待2秒
            time.sleep(2)
        
        return results
```

---

## 6. 设备管理模块

### 6.1 设备注册与状态监控

```python
class DeviceManager:
    """设备管理器"""
    
    def __init__(self):
        self.devices = {}  # device_id -> DeviceInfo
    
    def discover_devices(self):
        """通过ADB发现已连接设备"""
        result = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True
        )
        # 解析输出，获取设备列表
        lines = result.stdout.strip().split("\n")[1:]
        for line in lines:
            if "device" in line:
                device_id = line.split("\t")[0]
                if device_id not in self.devices:
                    self.register_device(device_id)
    
    def register_device(self, device_id):
        """注册新设备"""
        info = {
            "device_id": device_id,
            "model": self._get_device_model(device_id),
            "android_version": self._get_android_version(device_id),
            "status": "idle",          # idle / busy / offline / error
            "current_task": None,
            "last_heartbeat": datetime.now(),
            "apps_installed": self._check_apps(device_id),
        }
        self.devices[device_id] = info
    
    def get_available_device(self):
        """获取空闲设备"""
        for device_id, info in self.devices.items():
            if info["status"] == "idle":
                return device_id
        return None
    
    def health_check(self, device_id):
        """设备健康检查"""
        checks = {
            "adb_connected": self._check_adb(device_id),
            "screen_on": self._check_screen(device_id),
            "apps_running": self._check_apps_alive(device_id),
            "gps_mock_enabled": self._check_mock_location(device_id),
            "storage_available": self._check_storage(device_id),
        }
        return checks
```

### 6.2 账号池管理

```python
import redis
import json

class AccountPool:
    """三家平台账号池"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def add_account(self, brand, phone, password=None, cookies=None):
        """添加账号"""
        key = f"accounts:{brand}"
        account = {
            "phone": phone,
            "password": password,
            "cookies": cookies,       # 登录态
            "status": "available",    # available / in_use / banned / expired
            "last_used": None,
            "use_count": 0,
            "device_id": None,        # 当前绑定设备
        }
        self.redis.lpush(key, json.dumps(account))
    
    def acquire(self, brand):
        """获取可用账号"""
        key = f"accounts:{brand}"
        accounts = self.redis.lrange(key, 0, -1)
        for acc_json in accounts:
            acc = json.loads(acc_json)
            if acc["status"] == "available":
                acc["status"] = "in_use"
                acc["last_used"] = datetime.now().isoformat()
                self.redis.lrem(key, 0, acc_json)
                self.redis.lpush(key, json.dumps(acc))
                return acc
        raise NoAvailableAccountError(f"No available {brand} account")
    
    def release(self, brand, phone, status="available"):
        """释放账号"""
        key = f"accounts:{brand}"
        accounts = self.redis.lrange(key, 0, -1)
        for acc_json in accounts:
            acc = json.loads(acc_json)
            if acc["phone"] == phone:
                acc["status"] = status
                acc["device_id"] = None
                self.redis.lrem(key, 0, acc_json)
                self.redis.lpush(key, json.dumps(acc))
                return
```

---

## 7. SOP技术化对照

将人工SOP的每一步映射到自动化实现：

| SOP步骤 | 人工操作 | 自动化实现 | 对应模块 |
|---------|---------|-----------|---------|
| Step1 人员准备与定位 | 到达目标地点，打开App，点击定位 | set_mock_location() + start_app() + touch(定位按钮) | 采集器 |
| Step2 MT界面放大 | 手动双指缩放到能覆盖所有车辆 | pinch_to_zoom() + _detect_vehicle_icons()验证 | 采集器 |
| Step3 DD/HB对齐MT | 手动调整比例尺与MT一致 | align_map_scale() + 图像配准验证 | 采集器 |
| Step4 T时刻截图 | 人工截图三张 | capture_snapshot() × 3 | 采集器 |
| Step4 T时刻圈车 | 人工在截图上圈出车辆 | T时刻截图自动标记（YOLOv8检测结果叠加） | AI数车模块 |
| Step4 T+10~T+60 | 每10分钟重复截图 | Celery定时触发 capture_round() | 调度模块 |
| 汇总提交 | 人工整理21张图 | 自动归档MinIO + 元数据写PG | 数据存储模块 |

---

## 8. 异常处理

| 异常场景 | 检测方式 | 处理策略 |
|---------|---------|---------|
| App崩溃/闪退 | 截图后检测App是否在前台 | 自动重启App，该轮截图标记为"重试" |
| 地图加载失败 | 30秒内未检测到车辆图标 | 重试1次，仍失败则标记异常并跳过 |
| 账号登录态失效 | App弹出登录页面 | 从账号池切换新账号，重新登录 |
| 设备断连 | ADB heartbeat超时 | 标记设备offline，任务重新分配 |
| GPS定位偏差 | 截图OCR未匹配到预期POI | 重新设置定位，重试1次 |
| 截图模糊/黑屏 | 图像方差检测 | 重新截图，重试2次 |
| App反自动化检测 | App弹出验证码/风控提示 | 暂停采集，人工介入处理 |
| 比例尺无法对齐 | 图像配准分数低于阈值 | 记录日志，使用最近一次成功比例尺 |

---

## 9. 反自动化检测应对策略

三家平台可能检测自动化操作，应对措施：

| 检测类型 | 应对策略 |
|---------|---------|
| 操作速度异常 | 在操作间加入随机延迟（2-5秒），模拟人类节奏 |
| 点击位置固定 | 在目标按钮区域内随机偏移点击坐标（±10px） |
| 设备指纹一致 | 使用不同品牌型号手机；修改Build属性 |
| 操作轨迹机械 | 使用贝塞尔曲线模拟人类滑动轨迹 |
| 同一IP大量请求 | 如果使用网络请求，通过代理池轮换IP |
| 账号短时间大量操作 | 限制单账号每日操作次数（如不超过50轮截图） |
| 截图频率固定 | 在10分钟间隔上加入±30秒随机偏移 |

```python
import random

def human_like_delay(min_sec=2, max_sec=5):
    """模拟人类操作间隔"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)

def human_like_touch(device, target_pos, offset_range=10):
    """模拟人类点击（位置随机偏移）"""
    x = target_pos[0] + random.randint(-offset_range, offset_range)
    y = target_pos[1] + random.randint(-offset_range, offset_range)
    device.touch((x, y))
```
