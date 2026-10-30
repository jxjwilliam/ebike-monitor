# API逆向探索：效率提升补充方案

> 文档编号：wb_07  
> 创建日期：2026-10-30  
> 文档定位：辅助探索方向 — 非交付依赖项，仅供内部效率提升参考

---

## 1. 定位与边界

### 1.1 本文档的性质

API逆向探索是**内部效率提升的辅助方向**，不是交付方案的核心依赖。主交付路线始终是"App自动化截图 + AI数车"（见 wb_02、wb_03）。

```
主路线（交付用）：App截图 → AI数车 → 交付
                  ↑ 合规、可验证、有截图依据

辅助路线（内部用）：API逆向 → 结构化数据 → 交叉验证
                    ↑ 高效、低成本，但合规风险大，不作为交付依据
```

### 1.2 合规边界

| 允许 | 不允许 |
|------|--------|
| 分析App网络请求，了解数据格式（内部研究） | 将逆向获取的数据直接交付甲方 |
| 用API数据与截图AI数车结果交叉验证 | 对App服务器造成压力（高频请求） |
| 降低截图采集频率（API验证截图数据可信度后） | 破坏App的安全机制、绕过付费墙 |
| 在试点阶段验证技术可行性 | 规模化部署逆向方案替代截图 |

> **原则**：截图方案是合规的交付方式，API逆向仅用于内部数据质量验证和效率优化。所有对外交付的数据必须来源于截图+AI数车，并有截图存档可追溯。

---

## 2. 技术目标

如果API逆向成功，可以实现以下效率提升：

| 目标 | 说明 | 价值 |
|------|------|------|
| 数据交叉验证 | 同一点位同时用截图和API获取数据，对比一致性 | 验证AI数车准确率 |
| 降低采集频率 | 如果API数据可信，可以减少截图频率（如从7轮降到3轮） | 降低设备和人力成本 |
| 获取更多元数据 | API可能返回车辆ID、电量等信息 | 提供更丰富的分析维度 |
| 实时监控 | API可以更高频率轮询（如每分钟一次） | 更精细的流入流出分析 |

---

## 3. 技术方案

### 3.1 工具链

| 工具 | 用途 | 说明 |
|------|------|------|
| **mitmproxy** | HTTPS抓包 | 开源，Python脚本可编程，比Charles更灵活 |
| **Frida** | 动态插桩 | 在App运行时hook加密函数，获取签名算法 |
| **JADX** | APK反编译 | 将APK反编译为Java源码，分析加密逻辑 |
| **Python httpx** | 请求模拟 | 异步HTTP客户端，模拟App请求 |
| **curl_cffi** | TLS指纹模拟 | 模拟App的TLS指纹，绕过CDN检测 |

### 3.2 分析流程

```
Step 1: 抓包
│   mitmproxy 拦截App网络请求
│   重点关注：打开找车界面时的API请求
│   目标：找到返回车辆列表的API
│
├── Step 2: 分析请求结构
│   URL: https://api.xxx.com/bikes/nearby?
│         lat=22.804599&lng=108.327540&zoom=18
│   Headers: Authorization, X-Sign, X-Device-ID ...
│   Response: {"bikes": [{"id": "xxx", "lat": ..., "lng": ...}]}
│
├── Step 3: 破解签名
│   请求头中的 X-Sign 是如何生成的？
│   ├── 方案A：Frida hook签名函数，直接获取签名值
│   ├── 方案B：JADX反编译，分析签名算法，Python复现
│   └── 方案C：mitmproxy脚本自动替换签名（中间人方式）
│
├── Step 4: 请求验证
│   用Python模拟请求，验证返回数据正确性
│   对比API返回的车辆数与截图AI数车的结果
│
└── Step 5: 效率评估
    API数据 vs 截图数据的准确率对比
    API请求的频率限制和稳定性评估
    决定是否将API作为交叉验证手段
```

### 3.3 mitmproxy 抓包配置

```python
# scripts/mitm_proxy.py
"""
mitmproxy 插件脚本
用法: mitmproxy -s scripts/mitm_proxy.py
前提: 手机WiFi代理设置为本机IP:8080，安装mitmproxy证书
"""
import json
from mitmproxy import http

class BikeAPIInterceptor:
    def __init__(self):
        self.api_patterns = [
            "nearby",        # 附近车辆
            "bike",          # 电单车相关
            "vehicle",       # 车辆相关
            "map",           # 地图相关
        ]
        self.captured = []
    
    def response(self, flow: http.HTTPFlow):
        url = flow.request.url.lower()
        
        # 过滤出车辆相关API
        if any(pattern in url for pattern in self.api_patterns):
            entry = {
                "url": flow.request.url,
                "method": flow.request.method,
                "request_headers": dict(flow.request.headers),
                "request_body": flow.request.get_text(),
                "response_status": flow.response.status_code,
                "response_body": flow.response.get_text()[:5000],  # 截断
            }
            self.captured.append(entry)
            
            # 打印摘要
            print(f"\n{'='*60}")
            print(f"[API] {flow.request.method} {flow.request.url[:100]}")
            print(f"Status: {flow.response.status_code}")
            
            # 尝试解析JSON
            try:
                data = json.loads(flow.response.get_text())
                if isinstance(data, dict):
                    # 找到车辆列表
                    for key in data:
                        if isinstance(data[key], list) and len(data[key]) > 0:
                            print(f"Key '{key}': {len(data[key])} items")
                            if isinstance(data[key][0], dict):
                                print(f"  Sample: {json.dumps(data[key][0], ensure_ascii=False)[:200]}")
            except:
                pass
    
    def done(self):
        # 保存抓包结果
        with open("/tmp/captured_apis.json", "w") as f:
            json.dump(self.captured, f, ensure_ascii=False, indent=2)
        print(f"\n捕获 {len(self.captured)} 个API请求，已保存到 /tmp/captured_apis.json")


addons = [BikeAPIInterceptor()]
```

### 3.4 Frida 动态插桩

```javascript
// scripts/frida_hook_sign.js
// 用法: frida -U -l scripts/frida_hook_sign.js -f com.sankuai.meituan

// Hook签名相关函数
Java.perform(function() {
    // 查找签名工具类
    var SignUtils = Java.use("com.meituan.bicycle.utils.SignUtils");
    
    // Hook签名方法
    SignUtils.sign.overload('java.lang.String', 'java.util.Map').implementation = function(params, headers) {
        var result = this.sign(params, headers);
        console.log("[Sign] params=" + params);
        console.log("[Sign] headers=" + headers);
        console.log("[Sign] result=" + result);
        return result;
    };
});
```

### 3.5 Python 请求模拟

```python
# scripts/api_validator.py
"""
用逆向出的API模拟请求，获取车辆数据
与截图AI数车结果对比
"""
import httpx
import asyncio

class APIValidator:
    def __init__(self, brand):
        self.brand = brand
        self.client = httpx.AsyncClient(
            http2=True,
            timeout=10,
            # 模拟App的User-Agent
            headers={
                "User-Agent": get_app_ua(brand),
                "Accept": "application/json",
            }
        )
    
    async def get_nearby_bikes(self, lat, lng):
        """获取附近车辆列表"""
        # 注意：URL和签名算法需要通过逆向获得
        # 以下是示意结构
        url = get_api_url(self.brand, "nearby")
        params = {
            "lat": lat,
            "lng": lng,
            "zoom": 18,
        }
        headers = generate_signed_headers(self.brand, params)
        
        response = await self.client.get(url, params=params, headers=headers)
        data = response.json()
        
        # 解析车辆列表
        bikes = extract_bikes(data, self.brand)
        
        return {
            "count": len(bikes),
            "bikes": bikes,        # 包含lat/lng
            "raw_response": data,
        }
    
    async def validate_against_screenshot(self, point_id, time_label, lat, lng):
        """
        API数据与截图数据对比
        """
        # 1. API获取车辆数据
        api_result = await self.get_nearby_bikes(lat, lng)
        
        # 2. 获取截图AI数车结果
        ai_result = get_ai_result(point_id, self.brand, time_label)
        
        # 3. 对比
        api_count = api_result["count"]
        ai_count = ai_result["vehicle_count"]
        diff = abs(api_count - ai_count)
        
        print(f"[{self.brand}] {time_label}: API={api_count} AI={ai_count} 差异={diff}")
        
        return {
            "brand": self.brand,
            "time_label": time_label,
            "api_count": api_count,
            "ai_count": ai_count,
            "diff": diff,
            "match": diff <= 1,
        }
```

---

## 4. 三家平台API预估分析

> ⚠️ 以下为基于经验的预估，实际需通过抓包验证

| 平台 | API结构预估 | 签名复杂度 | 反爬强度 | 逆向难度 |
|------|------------|-----------|---------|---------|
| 美团(MT) | RESTful JSON | 高（多参数签名） | 高（设备指纹+风控） | ⭐⭐⭐⭐⭐ |
| 滴滴(DD) | RESTful JSON | 高（加密SDK） | 高（频控+设备验证） | ⭐⭐⭐⭐⭐ |
| 哈啰(HB) | RESTful JSON | 中-高 | 中-高 | ⭐⭐⭐⭐ |

**预估结论**：三家平台的API都有较强的安全保护，逆向难度较高。建议：
1. 先从哈啰入手（预估难度相对最低）
2. 如果逆向成功，用API数据交叉验证截图AI数车
3. 如果逆向受阻，不要在此投入过多资源，坚持截图方案

---

## 5. 时间投入建议

| 阶段 | 时间 | 产出 | 决策点 |
|------|------|------|--------|
| 抓包分析 | 2天 | 三家App的API请求列表 | 是否找到车辆数据API？ |
| 签名破解 | 3-5天 | 可用的签名生成代码 | 能否成功模拟请求？ |
| 数据验证 | 2天 | API vs 截图数据对比报告 | API数据是否可信？ |
| **决策** | - | - | 继续投入 or 放弃 |

**建议**：最多投入2周。如果2周内无法破解签名，放弃API方案，全力投入截图+AI数车。

---

## 6. 如果API逆向成功的使用方式

### 6.1 交叉验证模式

```
截图采集（每10分钟一轮，7轮）
         +
API轮询（每2分钟一轮，30轮）← 更高频率
         │
         ▼
交叉验证：
  - 截图AI数车的时点车辆数 vs API对应时刻的车辆数
  - 如果一致 → 增强截图数据的可信度
  - 如果不一致 → 标记该数据点，人工核对
```

### 6.2 频率优化模式

```
如果交叉验证证明AI数车准确率 ≥ 95%：
  → 可以将截图频率从7轮降到3轮（T, T+30, T+60）
  → 中间的T+10/T+20/T+40/T+50用API数据补充
  → 截图数从21张/点位 降到 9张/点位
  → 采集效率提升 57%
```

---

## 7. 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 逆向失败 | 高（60%） | 浪费2周时间 | 严格时间box，不超期 |
| App更新导致签名失效 | 中 | API方案中断 | 截图方案为主，不依赖API |
| 法律风险 | 中 | 平台起诉 | 仅内部研究，不对外交付API数据 |
| 账号封禁 | 中 | 无法继续测试 | 多账号、低频率、分散请求 |
| 数据不一致 | 中 | 验证结果混乱 | 以截图数据为准，API仅参考 |

---

## 8. 决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-10-30 | API逆向列为P2优先级 | 截图方案已能满足交付需求，API仅效率提升 |
| 2026-10-30 | 最多投入2周 | 避免沉没成本过大 |
| 2026-10-30 | 不作为交付依据 | 合规风险，截图方案有据可查 |
| 2026-10-30 | 先从哈啰入手 | 预估难度相对最低 |
