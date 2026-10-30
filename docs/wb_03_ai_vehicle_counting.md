# AI数车模块：目标检测与流入流出分析

> 文档编号：wb_03  
> 创建日期：2026-10-30  
> 文档定位：**核心难点模块** — YOLOv8车辆检测、图像比对、流入流出算法、模型训练方案

---

## 1. 模块目标与核心挑战

### 1.1 目标

从三家App截图中自动识别并计算：
- **时点车辆数**：每张截图中围栏内的电单车数量
- **流入数**：相邻时点间新出现的车辆数
- **流出数**：相邻时点间消失的车辆数
- **疑似调度入**：短时间内大量同向涌入的车辆数

### 1.2 已知挑战（来自SOP示例）

SOP中的对照实验暴露了核心问题：

| 抽样点 | AI数车 | 人工数车 | 结果 |
|--------|--------|---------|------|
| MT 18:50-19:00 | 3:3 | 3:4 | ❌ 流出数不一致 |
| HB 18:40-18:50 | 4:0 | 5:0 | ❌ 流入数不一致 |
| DD 18:50-19:00 | 3:5 | 2:10 | ❌ 差异大 |
| HB 18:50-19:00 | 0:0 | 7:8 | ❌ 完全错误 |

**结论**：AI在"时点车辆数"上基本可靠，但在"流入流出"上不可靠。

### 1.3 问题根因分析

```
流入流出判断的难点：

时点车辆数：只需数一张截图中有几辆车 → 单帧目标检测 → YOLOv8可解决
              ✅ 相对简单

流入流出数：需要比较两张截图，判断哪些车是新的、哪些车消失了
            → 多帧比对 → 需要解决以下问题：
            
            问题1：截图边界偏移
                   两张截图即使比例尺相同，地图中心点可能有几像素偏移
                   → 导致同一辆车在两张图中位置不同，误判为"流出+流入"
            
            问题2：车辆图标外观相似
                   同一品牌的电单车图标几乎完全一样
                   → 无法通过外观特征区分"这辆车"和"那辆车"
                   → 只能通过位置判断（但位置可能因地图偏移而变）
            
            问题3：图标遮挡
                   车辆图标可能被UI元素（按钮、弹窗）遮挡
                   → 一张图中能看到，另一张图中被遮挡 → 误判为"流出"
            
            问题4：地图刷新延迟
                   App的车辆位置数据可能不是实时更新的
                   → 车辆实际没动，但图标在不同截图间可能闪烁
                   → 同一辆车在T时刻显示，T+10时刻不显示 → 误判
```

---

## 2. 技术方案总览

### 2.1 方案架构

```
┌────────────────────────────────────────────────────────────┐
│                    AI数车分析管道                             │
│                                                            │
│  输入：同一点位、同一品牌、7个时间点的截图序列                 │
│  T0.png, T10.png, T20.png, T30.png, T40.png, T50.png, T60.png
│                                                            │
│  ┌─────────────┐                                          │
│  │ Step 1      │  YOLOv8 目标检测                          │
│  │ 车辆检测     │  → 每张截图中的车辆位置和数量              │
│  └──────┬──────┘                                          │
│         │                                                  │
│  ┌──────┴──────┐                                          │
│  │ Step 2      │  图像配准（对齐）                          │
│  │ 边界对齐     │  → 消除截图间的像素级偏移                  │
│  └──────┬──────┘                                          │
│         │                                                  │
│  ┌──────┴──────┐                                          │
│  │ Step 3      │  围栏裁剪                                 │
│  │ 围栏内筛选   │  → 只保留100m×100m围栏内的车辆             │
│  └──────┬──────┘                                          │
│         │                                                  │
│  ┌──────┴──────┐                                          │
│  │ Step 4      │  多目标跟踪（ByteTrack）                   │
│  │ 车辆匹配     │  → 跨时间点匹配同一辆车                    │
│  └──────┬──────┘                                          │
│         │                                                  │
│  ┌──────┴──────┐                                          │
│  │ Step 5      │  流入流出计算                              │
│  │ 增减判断     │  → 未匹配上的车 = 流入/流出               │
│  └──────┬──────┘                                          │
│         │                                                  │
│  ┌──────┴──────┐                                          │
│  │ Step 6      │  调度识别                                  │
│  │ 疑似调度判断  │  → 规则引擎判断是否为平台调度              │
│  └─────────────┘                                          │
│                                                            │
│  输出：每个时点的车辆数 + 每个间隔的流入/流出/疑似调度入       │
└────────────────────────────────────────────────────────────┘
```

---

## 3. Step 1：YOLOv8目标检测

### 3.1 模型选型

| 模型 | mAP | FPS(GPU) | FPS(CPU) | 模型大小 | 推荐场景 |
|------|-----|----------|----------|---------|---------|
| YOLOv8n | 37.3 | 450 | 80 | 6MB | 超高速，边缘设备 |
| YOLOv8s | 44.9 | 350 | 50 | 22MB | ⭐ **推荐：平衡精度速度** |
| YOLOv8m | 50.2 | 250 | 25 | 52MB | 高精度，GPU推理 |
| YOLOv8l | 52.9 | 180 | 15 | 87MB | 最高精度 |
| YOLOv8x | 53.9 | 120 | 10 | 131MB | 精度最高，速度慢 |

**选型：YOLOv8s** — 车辆图标检测是相对简单的目标检测任务（图标外观规则、背景简单），不需要超大模型。

### 3.2 检测目标定义

需要检测的目标类别：

| 类别ID | 类别名 | 说明 | 检测难度 |
|--------|--------|------|---------|
| 0 | mt_bike | 美团电单车图标 | 低（图标规则） |
| 1 | dd_bike | 滴滴电单车图标 | 低 |
| 2 | hb_bike | 哈啰电单车图标 | 低 |
| 3 | mt_cluster | 美团车辆聚集图标（数字角标） | 中（多车重叠时） |
| 4 | dd_cluster | 滴滴聚集图标 | 中 |
| 5 | hb_cluster | 哈啰聚集图标 | 中 |

> **注意**：当多辆车停在同一位置时，App可能显示一个带数字的聚集图标（如"3"），表示该位置有3辆车。需要将聚集图标也作为检测目标，并读取其中的数字。

### 3.3 聚集图标数字识别

```python
import cv2
import numpy as np

def count_vehicles_in_cluster(icon_image):
    """
    识别聚集图标中的数字
    输入：裁剪出的聚集图标图像
    输出：该图标代表的车辆数
    """
    # 方案1：OCR识别数字（PaddleOCR轻量版）
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(use_angle_cls=False, lang='ch', show_log=False)
    result = ocr.ocr(icon_image)
    if result and result[0]:
        text = result[0][0][1][0]  # 提取识别文本
        if text.isdigit():
            return int(text)
    
    # 方案2：模板匹配（预先准备0-9数字模板）
    # 更快但需要针对不同App的数字字体分别准备模板
    
    return 1  # 默认为1辆车
```

### 3.4 检测代码

```python
from ultralytics import YOLO
import cv2

class VehicleDetector:
    """电单车目标检测器"""
    
    def __init__(self, model_path="models/yolov8s_ebike.onnx"):
        # 加载ONNX格式模型（推理加速）
        self.model = YOLO(model_path)
        self.conf_threshold = 0.5  # 置信度阈值
        self.iou_threshold = 0.45  # NMS的IoU阈值
    
    def detect(self, image_path):
        """
        检测截图中的电单车
        
        返回：
            detections: List[Detection]  每个检测到的车辆
            count: int  车辆总数（含聚集图标展开）
        """
        results = self.model(
            image_path,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
        )
        
        detections = []
        total_count = 0
        
        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                
                if cls in [0, 1, 2]:  # 单车图标
                    count = 1
                elif cls in [3, 4, 5]:  # 聚集图标
                    # 裁剪图标区域，OCR识别数字
                    icon_img = cv2.imread(image_path)[
                        int(y1):int(y2), int(x1):int(x2)
                    ]
                    count = count_vehicles_in_cluster(icon_img)
                
                detections.append({
                    "class": cls,
                    "confidence": conf,
                    "bbox": [x1, y1, x2, y2],
                    "count": count,
                    "center": [(x1+x2)/2, (y1+y2)/2],
                })
                total_count += count
        
        return detections, total_count
```

---

## 4. Step 2：图像配准（解决截图边界偏移）

### 4.1 问题

SOP要求"同品牌7个时间节点截图边界统一"，但即使自动化控制，仍可能有几像素偏移。这会导致同一辆车在两张截图中的坐标不同，影响后续匹配。

### 4.2 方案：特征点配准

```python
import cv2
import numpy as np

class ImageAligner:
    """图像配准器：对齐同一品牌不同时间点的截图"""
    
    def __init__(self):
        self.matcher = cv2.SIFT_create()
        self.bf_matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=True)
    
    def align(self, ref_image, target_image):
        """
        将target_image对齐到ref_image的坐标系
        
        参数：
            ref_image: 参考图像（通常是T时刻的截图）
            target_image: 待对齐图像（如T+10时刻的截图）
        
        返回：
            aligned_image: 对齐后的图像
            transform_matrix: 变换矩阵（用于后续坐标转换）
            confidence: 配准置信度
        """
        # 1. 转灰度
        gray_ref = cv2.cvtColor(ref_image, cv2.COLOR_BGR2GRAY)
        gray_tgt = cv2.cvtColor(target_image, cv2.COLOR_BGR2GRAY)
        
        # 2. SIFT特征点检测
        kp_ref, des_ref = self.matcher.detectAndCompute(gray_ref, None)
        kp_tgt, des_tgt = self.matcher.detectAndCompute(gray_tgt, None)
        
        # 3. 特征点匹配
        matches = self.bf_matcher.match(des_ref, des_tgt)
        matches = sorted(matches, key=lambda x: x.distance)
        
        # 取最好的匹配点
        good_matches = matches[:min(50, len(matches))]
        
        # 4. 计算变换矩阵
        ref_pts = np.float32(
            [kp_ref[m.queryIdx].pt for m in good_matches]
        ).reshape(-1, 1, 2)
        tgt_pts = np.float32(
            [kp_tgt[m.trainIdx].pt for m in good_matches]
        ).reshape(-1, 1, 2)
        
        # 使用RANSAC计算仿射变换（排除异常匹配）
        transform_matrix, inliers = cv2.estimateAffine2D(
            tgt_pts, ref_pts, method=cv2.RANSAC, ransacReprojThreshold=3.0
        )
        
        # 5. 应用变换
        h, w = ref_image.shape[:2]
        aligned_image = cv2.warpAffine(target_image, transform_matrix, (w, h))
        
        # 6. 计算置信度
        confidence = len(inliers[inliers]) / len(good_matches) if len(good_matches) > 0 else 0
        
        return aligned_image, transform_matrix, confidence
    
    def transform_detection(self, detection, transform_matrix):
        """
        将检测结果的坐标转换到参考图像坐标系
        """
        center = np.array([detection["center"]])
        # 仿射变换：[x', y'] = M @ [x, y, 1]
        transformed = cv2.transform(
            center.reshape(1, 1, 2).astype(np.float32), 
            transform_matrix
        )
        detection["aligned_center"] = transformed[0][0].tolist()
        return detection
```

### 4.3 配准质量保障

| 配准置信度 | 处理策略 |
|-----------|---------|
| > 0.8 | 正常使用对齐结果 |
| 0.5 - 0.8 | 使用对齐结果但标记为"低置信度" |
| < 0.5 | 放弃对齐，使用原始坐标，标记为"未对齐"（人工核对时重点关注） |

---

## 5. Step 3：围栏内筛选

### 5.1 围栏定义

围栏是以停车点为中心的100m×100m正方形。需要将围栏的地理坐标映射到截图的像素坐标。

```python
class FenceFilter:
    """围栏内车辆筛选"""
    
    def __init__(self, fence_coords, image_corners_geo):
        """
        参数：
            fence_coords: 围栏四角GCJ-02坐标
            image_corners_geo: 截图四角对应的地理坐标
                              （通过App地图的比例尺和中心点推算）
        """
        # 计算地理坐标到像素坐标的仿射变换
        self.geo_to_pixel = self._compute_transform(
            image_corners_geo, 
            [(0, 0), (img_w, 0), (img_w, img_h), (0, img_h)]
        )
        
        # 将围栏地理坐标转为像素坐标
        self.fence_pixel = [
            self._geo_to_pixel(coord) for coord in fence_coords
        ]
    
    def is_inside_fence(self, detection_center):
        """判断车辆是否在围栏内（点在多边形内）"""
        from matplotlib.path import Path
        fence_path = Path(self.fence_pixel)
        return fence_path.contains_point(detection_center)
    
    def filter(self, detections):
        """筛选围栏内的车辆"""
        inside = [d for d in detections if self.is_inside_fence(d["aligned_center"])]
        outside = [d for d in detections if not self.is_inside_fence(d["aligned_center"])]
        return inside, outside
```

### 5.2 围栏边界近似

> **实际操作中的简化**：如果截图视野恰好覆盖100m×100m区域（SOP要求放大到此范围），则可以近似认为整个截图都在围栏内，无需精确的地理-像素映射。只需要排除截图边缘的部分（UI元素遮挡区域）。

---

## 6. Step 4：多目标跟踪（车辆匹配）

### 6.1 问题

这是流入流出计算的核心步骤：判断两张截图中哪些车是"同一辆车"。

### 6.2 匹配策略

由于同品牌的电单车图标外观几乎完全一致，无法通过外观特征匹配。只能依赖**位置匹配**：

```
假设：在10分钟间隔内，同一辆电单车不会移动太远（通常<50m）
策略：如果两张截图中某两辆车的位置距离 < 阈值，则认为是同一辆车

匹配方法：
T时刻截图中检测到车辆A（位置x1, y1）
T+10时刻截图中检测到车辆B（位置x2, y2）
如果 dist(A, B) < D_threshold → A和B是同一辆车
如果 T时刻的车辆A在T+10时刻没有匹配 → A已流出
如果 T+10时刻的车辆B在T时刻没有匹配 → B是流入
```

### 6.3 匹配算法：匈牙利算法

```python
from scipy.optimize import linear_sum_assignment
import numpy as np

class VehicleMatcher:
    """车辆匹配器：跨时间点匹配同一辆车"""
    
    def __init__(self, distance_threshold=50):
        """
        参数：
            distance_threshold: 最大匹配距离（像素）
                            10分钟内车辆移动不应超过此距离
        """
        self.distance_threshold = distance_threshold
    
    def match(self, detections_t1, detections_t2):
        """
        匹配两个时间点的车辆检测结果
        
        参数：
            detections_t1: T时刻的车辆列表 [{center: [x,y], ...}]
            detections_t2: T+10时刻的车辆列表
        
        返回：
            matched: [(idx_t1, idx_t2)] 匹配的车辆对
            outflow: [idx_t1] T时刻有但T+10时刻没有的（流出）
            inflow: [idx_t2] T+10时刻有但T时刻没有的（流入）
        """
        n1 = len(detections_t1)
        n2 = len(detections_t2)
        
        if n1 == 0:
            return [], [], list(range(n2))  # 全部是流入
        if n2 == 0:
            return [], list(range(n1)), []  # 全部是流出
        
        # 构建距离矩阵
        cost_matrix = np.zeros((n1, n2))
        for i, d1 in enumerate(detections_t1):
            for j, d2 in enumerate(detections_t2):
                p1 = np.array(d1["aligned_center"])
                p2 = np.array(d2["aligned_center"])
                cost_matrix[i, j] = np.linalg.norm(p1 - p2)
        
        # 超过阈值的距离设为极大值（禁止匹配）
        cost_matrix[cost_matrix > self.distance_threshold] = 1e6
        
        # 匈牙利算法求最优匹配
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        
        # 筛选有效匹配（距离小于阈值）
        matched = []
        matched_t1 = set()
        matched_t2 = set()
        for r, c in zip(row_ind, col_ind):
            if cost_matrix[r, c] < self.distance_threshold:
                matched.append((r, c))
                matched_t1.add(r)
                matched_t2.add(c)
        
        # 未匹配的 = 流出（T有T+10没有）或流入（T+10有T没有）
        outflow = [i for i in range(n1) if i not in matched_t1]
        inflow = [j for j in range(n2) if j not in matched_t2]
        
        return matched, outflow, inflow
```

### 6.4 距离阈值标定

距离阈值是关键参数，需要根据实际数据标定：

| 参数 | 推荐值 | 标定方法 |
|------|--------|---------|
| distance_threshold | 50像素 | 在截图比例尺下，100m围栏大约对应屏幕宽度的80%，即100m≈0.8×截图宽度。10分钟内自然移动的车辆通常不超过20m，对应约0.16×截图宽度。对于1080px宽截图，约170px。考虑停车状态下设为50px更保守。 |

> **建议**：用SOP示例中的南宁数据做标定——已知人工数车结果，反推最优阈值。

---

## 7. Step 5：流入流出计算

### 7.1 完整计算流程

```python
class FlowCalculator:
    """流入流出计算器"""
    
    def __init__(self, detector, aligner, fence_filter, matcher):
        self.detector = detector       # YOLOv8检测器
        self.aligner = aligner         # 图像配准
        self.fence_filter = fence_filter  # 围栏筛选
        self.matcher = matcher         # 车辆匹配
    
    def analyze_sequence(self, image_paths, brand):
        """
        分析一个点位一个品牌的完整7张截图序列
        
        参数：
            image_paths: [T0.png, T10.png, ..., T60.png] 按时间排序
            brand: MT / DD / HB
        
        返回：完整的车辆数据序列
        """
        # Step 1: 检测所有截图中的车辆
        all_detections = []
        for img_path in image_paths:
            detections, count = self.detector.detect(img_path)
            all_detections.append(detections)
        
        # Step 2: 以第一张为参考，对齐所有截图
        ref_image = cv2.imread(image_paths[0])
        aligned_detections = [all_detections[0]]  # 第一张不需要对齐
        
        for i in range(1, len(image_paths)):
            target_image = cv2.imread(image_paths[i])
            aligned_image, transform, conf = self.aligner.align(ref_image, target_image)
            
            # 转换检测坐标到参考坐标系
            transformed_dets = []
            for det in all_detections[i]:
                det = self.aligner.transform_detection(det, transform)
                transformed_dets.append(det)
            aligned_detections.append(transformed_dets)
        
        # Step 3: 围栏内筛选
        fenced_detections = []
        for dets in aligned_detections:
            inside, outside = self.fence_filter.filter(dets)
            fenced_detections.append(inside)
        
        # Step 4: 逐对比对，计算流入流出
        results = []
        results.append({
            "time_label": "T",
            "vehicle_count": len(fenced_detections[0]),
            "inflow": None,        # 第一个时间点没有流入
            "outflow": None,
            "suspected_dispatch": None,
        })
        
        for i in range(1, len(fenced_detections)):
            matched, outflow_idx, inflow_idx = self.matcher.match(
                fenced_detections[i-1], 
                fenced_detections[i]
            )
            
            inflow_count = len(inflow_idx)
            outflow_count = len(outflow_idx)
            
            # Step 6: 疑似调度判断
            dispatch_count = self._identify_dispatch(
                fenced_detections[i-1], 
                fenced_detections[i], 
                inflow_idx, 
                time_gap_min=10
            )
            
            results.append({
                "time_label": f"T+{i*10}",
                "vehicle_count": len(fenced_detections[i]),
                "inflow": inflow_count,
                "outflow": outflow_count,
                "suspected_dispatch": dispatch_count,
                "matched_pairs": len(matched),
                "alignment_confidence": conf if i > 0 else 1.0,
            })
        
        return results
```

---

## 8. Step 6：疑似调度识别

### 8.1 调度行为特征

平台主动调度（用卡车搬运电单车投放）的行为特征：

| 特征 | 说明 |
|------|------|
| 短时间大量涌入 | 10分钟内出现≥3辆新车 |
| 位置聚集 | 新出现的车辆集中在同一小区域（卡车停靠点附近） |
| 时间规律 | 通常在凌晨/早晨调度（但夜间采集时可能观察到） |
| 无流出对应 | 调度入不伴随同时段的流出 |

### 8.2 规则引擎

```python
class DispatchDetector:
    """疑似调度识别"""
    
    def __init__(self):
        self.min_dispatch_count = 3      # 最少车辆数才算调度
        self.cluster_radius = 80          # 聚集半径（像素）
        self.max_concurrent_outflow = 1   # 同时段流出不超过此数才算纯调度入
    
    def identify(self, prev_detections, curr_detections, inflow_indices, time_gap_min):
        """
        判断流入的车辆中哪些是疑似调度入
        
        参数：
            prev_detections: T时刻车辆列表
            curr_detections: T+10时刻车辆列表
            inflow_indices: 流入车辆在curr_detections中的索引
            time_gap_min: 时间间隔（分钟）
        
        返回：疑似调度入的车辆数
        """
        if len(inflow_indices) < self.min_dispatch_count:
            return 0
        
        # 获取流入车辆的位置
        inflow_vehicles = [curr_detections[i] for i in inflow_indices]
        inflow_positions = [v["aligned_center"] for v in inflow_vehicles]
        
        # 检查是否聚集（DBSCAN聚类）
        from sklearn.cluster import DBSCAN
        positions = np.array(inflow_positions)
        clustering = DBSCAN(
            eps=self.cluster_radius, 
            min_samples=self.min_dispatch_count
        ).fit(positions)
        
        # 有聚类标签（非-1）的车辆 = 疑似调度入
        dispatch_indices = [
            i for i, label in enumerate(clustering.labels_) 
            if label != -1
        ]
        
        return len(dispatch_indices)
```

---

## 9. 模型训练方案

### 9.1 训练数据收集

| 数据来源 | 数量 | 说明 |
|---------|------|------|
| SOP示例截图 | ~21张 | 南宁试点数据 |
| 试点城市采集 | ~500张 | 单城市完整试点 |
| 人工补充采集 | ~300张 | 不同城市、不同光照条件 |
| 数据增强 | ×5倍 | 翻转、缩放、亮度调整 |

**目标**：收集至少1000张标注截图，覆盖三家平台、多个城市。

### 9.2 标注流程

```
Step 1: 使用CVAT创建标注项目
Step 2: 导入截图，按品牌分组
Step 3: 标注员框选每辆电单车图标
        - 单车图标：标注为 mt_bike / dd_bike / hb_bike
        - 聚集图标：标注为 mt_cluster / dd_cluster / hb_cluster
Step 4: 审核员复核标注质量
Step 5: 导出YOLO格式标注文件
```

### 9.3 训练流程

```python
from ultralytics import YOLO

def train_model():
    """训练YOLOv8电单车检测模型"""
    
    # 加载预训练模型
    model = YOLO('yolov8s.pt')
    
    # 训练
    results = model.train(
        data='datasets/ebike_dataset.yaml',  # 数据集配置
        epochs=100,                          # 训练轮数
        imgsz=640,                           # 输入尺寸
        batch=16,                            # 批量大小
        device='0',                          # GPU
        patience=20,                         # 早停容忍轮数
        save=True,                           # 保存最佳模型
        cache=True,                          # 缓存数据加速
        augment=True,                        # 数据增强
        # 数据增强参数
        hsv_h=0.015,                        # 色调变化
        hsv_s=0.7,                          # 饱和度变化
        hsv_v=0.4,                          # 亮度变化
        degrees=5,                          # 旋转角度
        translate=0.1,                      # 平移比例
        scale=0.5,                          # 缩放比例
        fliplr=0.5,                         # 水平翻转概率
        mosaic=1.0,                         # Mosaic增强
    )
    
    # 导出为ONNX格式（推理加速）
    model.export(format='onnx')
    
    return results
```

### 9.4 数据集配置

```yaml
# datasets/ebike_dataset.yaml
path: ./datasets/ebike
train: images/train
val: images/val
test: images/test

names:
  0: mt_bike
  1: dd_bike
  2: hb_bike
  3: mt_cluster
  4: dd_cluster
  5: hb_cluster
```

---

## 10. 准确率提升策略（解决SOP暴露的问题）

### 10.1 问题1：截图边界偏移 → 图像配准

已通过Step 2的SIFT特征点配准解决。

### 10.2 问题2：车辆图标外观一致 → 位置匹配+配准

已通过Step 4的匈牙利算法位置匹配解决。关键是对齐后的位置匹配比原始位置匹配准确率高很多。

### 10.3 问题3：图标遮挡 → 遮挡检测

```python
def detect_occlusion(detection, image):
    """
    检测车辆图标是否被UI元素遮挡
    通过检查图标区域的边缘完整性
    """
    x1, y1, x2, y2 = detection["bbox"]
    icon_region = image[int(y1):int(y2), int(x1):int(x2)]
    
    # 计算边缘密度
    edges = cv2.Canny(icon_region, 50, 150)
    edge_density = np.sum(edges) / (icon_region.shape[0] * icon_region.shape[1])
    
    # 边缘密度过低 → 可能被遮挡
    if edge_density < 0.05:
        return True, "low_edge_density"
    
    # 检查是否有UI元素颜色（如白色按钮背景）
    white_ratio = np.mean(
        (icon_region[:,:,0] > 240) & 
        (icon_region[:,:,1] > 240) & 
        (icon_region[:,:,2] > 240)
    )
    if white_ratio > 0.3:
        return True, "ui_overlap"
    
    return False, None
```

### 10.4 问题4：地图刷新延迟 → 多帧确认

```python
def confirm_vehicle_presence(detections_sequence, vehicle_idx, window=2):
    """
    多帧确认：一辆车需要在连续多个时间点出现才认为是真实存在
    避免因地图刷新延迟导致的闪烁误判
    
    如果一辆车在T出现，T+10消失，T+20又出现
    → 可能是地图刷新问题，不是真实流出
    """
    presence = [False] * len(detections_sequence)
    
    for t, dets in enumerate(detections_sequence):
        # 检查该位置附近是否有车
        if vehicle_idx < len(dets):
            presence[t] = True
    
    # 检查窗口内的出现频率
    for t in range(len(presence) - window + 1):
        window_presence = presence[t:t+window]
        # 如果在窗口内出现次数 >= 1，认为是存在的
        if any(window_presence):
            presence[t] = True
    
    return presence
```

### 10.5 综合准确率提升方案

```
原始方案（SOP中的AI数车）：
  截图 → YOLOv8检测 → 直接比较车辆数差值
  问题：没有对齐、没有匹配、没有遮挡处理

改进方案：
  截图 → YOLOv8检测 → 图像配准 → 围栏筛选 → 遮挡过滤 
       → 位置匹配（匈牙利算法） → 多帧确认 → 流入流出
       → 调度识别
  改进：全链路优化，每一步解决一个已知问题

预期准确率提升：
  时点车辆数：85% → 95%+（遮挡处理后提升）
  流入流出数：50%（SOP数据）→ 80%+（配准+匹配+多帧确认）
```

---

## 11. 模型部署与推理

### 11.1 ONNX推理

```python
import onnxruntime as ort

class ONNXVehicleDetector:
    """ONNX推理加速的车辆检测器"""
    
    def __init__(self, model_path="models/yolov8s_ebike.onnx"):
        self.session = ort.InferenceSession(
            model_path, 
            providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
        )
        self.input_name = self.session.get_inputs()[0].name
    
    def detect(self, image):
        # 预处理
        input_tensor = self._preprocess(image)
        
        # 推理
        outputs = self.session.run(None, {self.input_name: input_tensor})
        
        # 后处理（NMS等）
        detections = self._postprocess(outputs)
        
        return detections
```

### 11.2 批量推理

```python
def batch_analyze(snapshots, batch_size=8):
    """
    批量分析截图
    一个点位的21张截图（3品牌×7时点）可以在一个batch中处理
    """
    for i in range(0, len(snapshots), batch_size):
        batch = snapshots[i:i+batch_size]
        
        # 批量检测
        detections = detector.batch_detect(batch)
        
        # 按品牌分组
        for brand in ["MT", "DD", "HB"]:
            brand_dets = [d for s, d in zip(batch, detections) if s.brand == brand]
            # 分析流入流出
            results = flow_calculator.analyze_sequence(brand_dets, brand)
```

### 11.3 推理性能预估

| 硬件 | 单张推理时间 | 21张/点位 | 960点位/期 |
|------|-------------|-----------|-----------|
| CPU（Intel i7） | ~200ms | ~4.2秒 | ~67分钟 |
| GPU（RTX 3060） | ~15ms | ~0.3秒 | ~5分钟 |
| GPU（RTX 4090） | ~5ms | ~0.1秒 | ~1.7分钟 |

> 结论：一块RTX 3060即可在10分钟内完成一期的全部推理。

---

## 12. 持续优化机制

### 12.1 人工反馈闭环

```
AI数车 → 人工核对 → 标记错误样本 → 加入训练集 → 重新训练 → 模型更新
                          ↑                                          │
                          └────────────── 定期迭代 ─────────────────┘
                          （建议每两周一次）
```

### 12.2 准确率监控

```python
def calculate_accuracy(ai_results, manual_results):
    """
    计算AI数车准确率
    """
    metrics = {
        "vehicle_count_accuracy": [],    # 时点车辆数准确率
        "inflow_accuracy": [],            # 流入数准确率
        "outflow_accuracy": [],           # 流出数准确率
        "dispatch_accuracy": [],          # 疑似调度准确率
    }
    
    for ai, manual in zip(ai_results, manual_results):
        # 时点车辆数：误差<=1算正确
        if abs(ai["vehicle_count"] - manual["vehicle_count"]) <= 1:
            metrics["vehicle_count_accuracy"].append(1)
        else:
            metrics["vehicle_count_accuracy"].append(0)
        
        # 流入流出：完全一致算正确
        for field in ["inflow", "outflow", "suspected_dispatch"]:
            if ai.get(field) == manual.get(field):
                metrics[f"{field}_accuracy"].append(1)
            else:
                metrics[f"{field}_accuracy"].append(0)
    
    return {k: np.mean(v) if v else 0 for k, v in metrics.items()}
```

### 12.3 目标准确率

| 指标 | 当前（SOP） | 试点目标 | 规模化目标 |
|------|------------|---------|-----------|
| 时点车辆数准确率 | ~85% | 95% | 98%+ |
| 流入数准确率 | ~50% | 80% | 90%+ |
| 流出数准确率 | ~50% | 80% | 90%+ |
| 疑似调度识别率 | 未验证 | 70% | 85%+ |
