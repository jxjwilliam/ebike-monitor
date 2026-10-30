# 数据校验与交付模块

> 文档编号：wb_05  
> 创建日期：2026-10-30  
> 文档定位：质量校验、人工核对工具、报告生成、验收标准

---

## 1. 数据质量校验体系

### 1.1 校验层次

```
┌──────────────────────────────────────────────────┐
│              数据质量三层校验                       │
│                                                  │
│  Layer 1: 自动校验（实时）                         │
│  ├── 采集完整性校验（21张截图是否齐全）              │
│  ├── 数据合理性校验（车辆数是否在合理范围）           │
│  ├── 异常检测（突变、缺失、矛盾）                    │
│  └── 自动标记可疑数据                              │
│                                                  │
│  Layer 2: AI置信度过滤（自动）                      │
│  ├── 图像配准置信度 < 0.5 → 标记                   │
│  ├── AI检测置信度 < 0.7 → 标记                     │
│  └── 流入流出匹配率低 → 标记                       │
│                                                  │
│  Layer 3: 人工核对（按比例抽检+全检可疑数据）        │
│  ├── 全检：所有被Layer1/2标记的数据                 │
│  ├── 抽检：正常数据的10%                           │
│  └── 人工在截图上圈车，修正AI结果                   │
└──────────────────────────────────────────────────┘
```

### 1.2 自动校验规则

```python
# validators/quality_checker.py

class QualityChecker:
    """数据质量检查器"""
    
    def check_all(self, task_id, point_id):
        """对一个点位的数据执行全部校验"""
        results = []
        
        # 规则1: 截图完整性
        results.append(self.check_snapshot_completeness(task_id, point_id))
        
        # 规则2: 车辆数合理性
        results.append(self.check_vehicle_count_reasonable(task_id, point_id))
        
        # 规则3: 数据一致性（车辆数 = 上轮 + 流入 - 流出）
        results.append(self.check_flow_consistency(task_id, point_id))
        
        # 规则4: 突变检测
        results.append(self.check_sudden_change(task_id, point_id))
        
        # 规则5: 配准置信度
        results.append(self.check_alignment_quality(task_id, point_id))
        
        return results
    
    def check_snapshot_completeness(self, task_id, point_id):
        """规则1: 检查21张截图是否齐全（3品牌×7时点）"""
        snapshots = get_snapshots(task_id, point_id)
        expected = {"MT": 7, "DD": 7, "HB": 7}
        actual = {}
        for s in snapshots:
            actual[s.brand] = actual.get(s.brand, 0) + 1
        
        missing = []
        for brand, count in expected.items():
            if actual.get(brand, 0) < count:
                missing.append(f"{brand}: {actual.get(brand, 0)}/{count}")
        
        return {
            "rule": "snapshot_completeness",
            "passed": len(missing) == 0,
            "detail": f"缺失: {missing}" if missing else "完整",
            "severity": "high" if missing else "none",
        }
    
    def check_vehicle_count_reasonable(self, task_id, point_id):
        """规则2: 车辆数在合理范围（0-200）"""
        data = get_vehicle_data(task_id, point_id)
        anomalies = []
        
        for d in data:
            if d.vehicle_count < 0:
                anomalies.append(f"{d.brand} {d.time_label}: 负数({d.vehicle_count})")
            elif d.vehicle_count > 200:
                anomalies.append(f"{d.brand} {d.time_label}: 异常高({d.vehicle_count})")
        
        return {
            "rule": "vehicle_count_reasonable",
            "passed": len(anomalies) == 0,
            "detail": "; ".join(anomalies) if anomalies else "合理",
            "severity": "medium" if anomalies else "none",
        }
    
    def check_flow_consistency(self, task_id, point_id):
        """
        规则3: 数据一致性校验
        车辆数(T+n) ≈ 车辆数(T+n-1) + 流入(T+n) - 流出(T+n)
        允许误差：±2（考虑疑似调度的模糊性）
        """
        data = get_vehicle_data_ordered(task_id, point_id)
        inconsistencies = []
        
        for i in range(1, len(data)):
            prev_count = data[i-1].vehicle_count
            curr_count = data[i].vehicle_count
            inflow = data[i].inflow or 0
            outflow = data[i].outflow or 0
            
            expected = prev_count + inflow - outflow
            actual = curr_count
            diff = abs(expected - actual)
            
            if diff > 2:
                inconsistencies.append(
                    f"{data[i].brand} {data[i].time_label}: "
                    f"预期{expected} 实际{actual} 差异{diff}"
                )
        
        return {
            "rule": "flow_consistency",
            "passed": len(inconsistencies) == 0,
            "detail": "; ".join(inconsistencies) if inconsistencies else "一致",
            "severity": "high" if inconsistencies else "none",
        }
    
    def check_sudden_change(self, task_id, point_id):
        """规则4: 突变检测（车辆数在一个间隔内变化超过50%）"""
        data = get_vehicle_data_ordered(task_id, point_id)
        spikes = []
        
        for i in range(1, len(data)):
            prev = data[i-1].vehicle_count
            curr = data[i].vehicle_count
            if prev > 0:
                change_rate = abs(curr - prev) / prev
                if change_rate > 0.5:
                    spikes.append(
                        f"{data[i].brand} {data[i].time_label}: "
                        f"{prev}→{curr} 变化{change_rate:.0%}"
                    )
        
        return {
            "rule": "sudden_change",
            "passed": len(spikes) == 0,
            "detail": "; ".join(spikes) if spikes else "无突变",
            "severity": "medium" if spikes else "none",
        }
    
    def check_alignment_quality(self, task_id, point_id):
        """规则5: 图像配准置信度检查"""
        snapshots = get_snapshots(task_id, point_id)
        low_confidence = []
        
        for s in snapshots:
            if s.alignment_confidence and s.alignment_confidence < 0.5:
                low_confidence.append(
                    f"{s.brand} {s.time_label}: {s.alignment_confidence:.2f}"
                )
        
        return {
            "rule": "alignment_quality",
            "passed": len(low_confidence) == 0,
            "detail": "; ".join(low_confidence) if low_confidence else "全部达标",
            "severity": "low" if low_confidence else "none",
        }
```

### 1.3 异常处理流程

```
自动校验发现问题
       │
       ├── severity=high → 标记为"需人工核对"，暂停该点位交付
       │                    推送到人工核对队列
       │
       ├── severity=medium → 标记为"可疑"，保留数据但标记警告
       │                      按比例抽检
       │
       └── severity=low → 记录日志，数据正常流转
```

---

## 2. 人工核对工具

### 2.1 核对界面设计

前端人工核对页面功能：

```
┌────────────────────────────────────────────────────────────┐
│  人工核对面板                                                │
│                                                            │
│  点位：南宁-广西卫健委  │  任务：2026-11期  │  状态：待核对    │
│  ┌────────────────────────┐  ┌────────────────────────┐  │
│  │                        │  │ AI数车结果              │  │
│  │   截图显示区域           │  │                        │  │
│  │   （支持上一张/下一张    │  │ T(18:00):              │  │
│  │    切换时间点）          │  │   车辆数: 18 [修正: □] │  │
│  │                        │  │   流入: -              │  │
│  │   支持在截图上点击       │  │   流出: -              │  │
│  │   添加/删除车辆标记      │  │                        │  │
│  │                        │  │ T+10(18:10):           │  │
│  │   绿色圆点=AI检测到的   │  │   车辆数: 15 [修正: □] │  │
│  │   红色圆点=人工添加的   │  │   流入: 0  [修正: □]   │  │
│  │   灰色叉号=人工删除的   │  │   流出: 3  [修正: □]   │  │
│  │                        │  │                        │  │
│  └────────────────────────┘  │ T+20(18:20):           │  │
│                              │   ...                   │  │
│  品牌切换：[MT] [DD] [HB]    │                        │  │
│  时间点：T T+10 T+20 ...     └────────────────────────┘  │
│                                                            │
│  [确认无误，通过]  [提交修正]  [标记异常]                    │
└────────────────────────────────────────────────────────────┘
```

### 2.2 核对组件

```tsx
// frontend/src/pages/Review.tsx
import React, { useState, useEffect } from 'react';
import { Image as KonvaImage, Circle, Layer, Stage } from 'react-konva';

const ReviewPage: React.FC = () => {
  const [currentSnapshot, setCurrentSnapshot] = useState(null);
  const [detections, setDetections] = useState([]);
  const [corrections, setCorrections] = useState({});
  
  // 加载截图和AI检测结果
  useEffect(() => {
    if (currentSnapshot) {
      loadDetections(currentSnapshot.id).then(setDetections);
    }
  }, [currentSnapshot]);
  
  // 在截图上点击添加车辆标记
  const handleStageClick = (e) => {
    const { x, y } = e.target.getStage().getPointerPosition();
    const newDetection = {
      id: `manual_${Date.now()}`,
      center: [x, y],
      source: 'manual',
      action: 'add',
    };
    setDetections([...detections, newDetection]);
  };
  
  // 提交修正
  const submitCorrections = () => {
    api.post(`/api/data/${currentSnapshot.id}/review`, {
      corrections: corrections,
      detections: detections,
    }).then(() => {
      message.success('修正已提交');
      loadNextReviewTask();
    });
  };
  
  return (
    <div className="review-container">
      <div className="snapshot-viewer">
        <Stage width={600} height={800} onClick={handleStageClick}>
          <Layer>
            <KonvaImage image={currentSnapshot?.url} />
            {detections.map(det => (
              <Circle
                key={det.id}
                x={det.center[0]}
                y={det.center[1]}
                radius={8}
                fill={det.source === 'ai' ? 'green' : 'red'}
                stroke="white"
                strokeWidth={2}
                onClick={() => removeDetection(det.id)}
              />
            ))}
          </Layer>
        </Stage>
      </div>
      <div className="data-panel">
        {/* AI数车结果列表 + 修正输入框 */}
      </div>
    </div>
  );
};
```

---

## 3. 报告生成

### 3.1 报告格式

按甲方需求，每个点位需要提供以下数据：

```
| 时间轴 | T | T+10 | T+20 | T+30 | T+40 | T+50 | T+60 |
|--------|---|------|------|------|------|------|------|
| MT 车辆数 | 18 | 15 | 17 | 17 | 17 | 21 | 21 |
| MT 流入数 | - | 0 | 2 | 0 | 0 | 4 | 0 |
| MT 流出数 | - | 3 | 0 | 0 | 0 | 0 | 0 |
| MT 疑似调度 | - | 0 | 0 | 0 | 0 | 4 | 0 |
| DD 车辆数 | ... |
| DD 流入数 | ... |
| DD 流出数 | ... |
| DD 疑似调度 | ... |
| HB 车辆数 | ... |
| HB 流入数 | ... |
| HB 流出数 | ... |
| HB 疑似调度 | ... |
```

### 3.2 报告生成代码

```python
# backend/app/services/report_service.py
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border
from openpyxl.utils import get_column_letter

class ReportGenerator:
    """交付报告生成器"""
    
    BRANDS = ["MT", "DD", "HB"]
    TIME_LABELS = ["T", "T+10", "T+20", "T+30", "T+40", "T+50", "T+60"]
    METRICS = ["车辆数", "流入数", "流出数", "疑似调度入"]
    
    def generate(self, task_id, output_path=None):
        """生成完整任务报告"""
        wb = openpyxl.Workbook()
        
        # Sheet 1: 汇总数据
        ws_summary = wb.active
        ws_summary.title = "汇总数据"
        self._write_summary_sheet(ws_summary, task_id)
        
        # Sheet 2: 分点位明细
        ws_detail = wb.create_sheet("分点位明细")
        self._write_detail_sheet(ws_detail, task_id)
        
        # Sheet 3: 截图索引
        ws_screenshots = wb.create_sheet("截图索引")
        self._write_screenshot_index(ws_screenshots, task_id)
        
        # Sheet 4: 质量报告
        ws_quality = wb.create_sheet("质量报告")
        self._write_quality_report(ws_quality, task_id)
        
        # 保存
        if not output_path:
            output_path = f"/reports/report_{task_id}.xlsx"
        wb.save(output_path)
        
        return output_path
    
    def _write_summary_sheet(self, ws, task_id):
        """汇总数据表"""
        points = get_points_for_task(task_id)
        
        # 表头
        headers = ["序号", "城市", "点位名称", "品牌"]
        headers += [f"{tl}\n{metric}" for tl in self.TIME_LABELS for metric in self.METRICS]
        
        header_font = Font(bold=True, size=10)
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font_white = Font(bold=True, size=10, color="FFFFFF")
        
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font_white
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
        # 数据行
        row = 2
        for point in points:
            for brand in self.BRANDS:
                data = get_vehicle_data_ordered(task_id, point.id, brand)
                data_map = {d.time_label: d for d in data}
                
                ws.cell(row=row, column=1, value=row - 1)
                ws.cell(row=row, column=2, value=point.city_name)
                ws.cell(row=row, column=3, value=point.park_name)
                ws.cell(row=row, column=4, value=brand)
                
                col = 5
                for tl in self.TIME_LABELS:
                    d = data_map.get(tl)
                    ws.cell(row=row, column=col, value=d.vehicle_count if d else "")
                    col += 1
                    ws.cell(row=row, column=col, value=d.inflow if d and d.inflow is not None else "")
                    col += 1
                    ws.cell(row=row, column=col, value=d.outflow if d and d.outflow is not None else "")
                    col += 1
                    ws.cell(row=row, column=col, value=d.suspected_dispatch if d and d.suspected_dispatch is not None else "")
                    col += 1
                
                row += 1
        
        # 设置列宽
        for col in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col)].width = 12
    
    def _write_screenshot_index(self, ws, task_id):
        """截图索引表（可复查核验依据）"""
        ws.cell(row=1, column=1, value="截图索引（可复查核验依据）").font = Font(bold=True, size=14)
        ws.cell(row=3, column=1, value="序号")
        ws.cell(row=3, column=2, value="城市")
        ws.cell(row=3, column=3, value="点位")
        ws.cell(row=3, column=4, value="品牌")
        ws.cell(row=3, column=5, value="时间标签")
        ws.cell(row=3, column=6, value="截图时间")
        ws.cell(row=3, column=7, value="文件路径")
        ws.cell(row=3, column=8, value="设备ID")
        
        snapshots = get_all_snapshots(task_id)
        for i, s in enumerate(snapshots, 1):
            ws.cell(row=i + 3, column=1, value=i)
            ws.cell(row=i + 3, column=2, value=s.point.city_name)
            ws.cell(row=i + 3, column=3, value=s.point.park_name)
            ws.cell(row=i + 3, column=4, value=s.brand)
            ws.cell(row=i + 3, column=5, value=s.time_label)
            ws.cell(row=i + 3, column=6, value=s.capture_time)
            ws.cell(row=i + 3, column=7, value=s.file_path)
            ws.cell(row=i + 3, column=8, value=s.device_id)
```

---

## 4. 验收标准

### 4.1 甲方验收要求（来自PDF需求文档）

> "可复查核验的依据。依据包括但不限于视频、图片、实时动态监测的模型。"

| 验收项 | 要求 | 交付物 |
|--------|------|--------|
| 截图留存 | 每个点位每品牌每时点一张截图 | 21张/点位 × 960点位 = 20,160张 |
| 车辆数据 | 4个指标（车辆数/流入/流出/疑似调度）× 7时点 × 3品牌 | Excel报告 |
| 时空一致性 | 三家平台同一时间点同一位置截图 | 截图元数据中的时间戳和坐标 |
| 数据可追溯 | 每条数据可追溯到对应截图 | 截图索引表 |
| 质量可信 | AI数车结果经人工校验 | 质量报告 |

### 4.2 内部质量标准

| 指标 | 标准 | 检查方式 |
|------|------|---------|
| 截图完整率 | ≥ 99%（允许少量设备故障导致的缺失） | 自动统计 |
| 截图清晰度 | 车辆图标可辨识，无模糊/黑屏 | 图像方差检测 |
| 时点车辆数准确率 | ≥ 95%（与人工抽检对比） | 10%抽检 |
| 流入流出准确率 | ≥ 80%（试点阶段目标） | 全检可疑+10%抽检 |
| 三家时空一致性 | 时间差 < 30秒 | 截图时间戳比对 |
| 围栏覆盖率 | 截图视野覆盖100m×100m围栏 | 比例尺校验 |

---

## 5. 监控看板

### 5.1 关键指标

```
┌──────────────────────────────────────────────────────┐
│                    数据采集监控看板                     │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐│
│  │ 任务进度  │ │ 设备状态  │ │ 今日采集  │ │ 准确率   ││
│  │   68%    │ │ 4/5 在线  │ │ 1,240张  │ │ 92.3%   ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘│
│                                                      │
│  ┌────────────────────────────────────────────────┐ │
│  │  城市采集进度                                     │ │
│  │  南宁  ████████████████░░ 85%                   │ │
│  │  洛阳  ██████████░░░░░░░░ 50%                   │ │
│  │  长沙  ████████░░░░░░░░░░ 40%                   │ │
│  │  ...                                             │ │
│  └────────────────────────────────────────────────┘ │
│                                                      │
│  ┌────────────────┐  ┌─────────────────────────┐   │
│  │ 异常告警        │  │ 待人工核对队列            │   │
│  │ ⚠ 南宁点位3    │  │ 12条待核对               │   │
│  │   配准失败      │  │                          │   │
│  │ ⚠ 设备A12离线  │  │ [去核对 →]               │   │
│  └────────────────┘  └─────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```
