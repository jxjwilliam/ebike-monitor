# GBFS 共享单车实时热力图：练通全流程

练通用的城市：**美国波特兰 Biketown**，公开 GBFS，无需注册、无需 key。

## 为什么选波特兰

- `gbfs.json` 里明确列出 `free_bike_status`，可直接拿到每辆可用车的经纬度
- 温哥华 Mobi 是有桩系统，只有 `station_status`（站点余量），没有单车自由浮动点，做点热力图不如波特兰直观
- 洛阳目前没有这类公开接口，所以先在这里把 pipeline 跑通，再切洛阳

## 跑一次

```bash
cd bikeshare-gbfs
python3 gbfs_heatmap.py
# 输出在 ./output/
#   bikes.csv     - 抓到的车辆经纬度
#   heatmap.html  - 双击打开就是热力图
```

只用 Python 标准库，不用装 folium / pandas。

## 全流程对应关系

1. 发现：读 `gbfs.json`，自动找 `free_bike_status` 的 URL，不硬编码
2. 抓取：GET 那个 JSON，取 `data.bikes[]` 的 `lat / lon`
3. 清洗：过滤经纬度越界、`is_disabled`、`is_reserved` 的车
4. 落盘：写 CSV，带抓取时间戳，方便之后按时间对比、做定时任务
5. 可视化：Leaflet + leaflet-heat，把点转成热力图，中心点取所有车的均值

定时刷新就是把第 2-5 步每 5 分钟跑一次（GBFS 的 `ttl` 通常是 60 秒左右，别刷太猛）。

## 切到洛阳时，只换第 2 步

洛阳没有公开实时接口，演示版的替换方案：

- 用高德 POI 搜索拿到洛阳真实的停车点、商圈、学校、景区、地铁站
- 按早晚高峰、景区周末等权重，在这些锚点周围模拟车辆分布
- 模拟函数返回同样格式的 `[{lat, lon, type}]`，后面清洗、落盘、画图一行不用改

等以后拿到官方合作数据，同样只换数据源函数。

## 数据来源与合规

- 波特兰数据来自公开 GBFS，本身就是设计给公众消费的实时数据
- 不要把这套方法直接套到哈啰 / 美团 / 青桔的 App 内接口上，那些不是公开接口


## deply to https://gbfs-heatmap.onrender.com/

- Render, not Railway
- 1. 多久不访问就 pause？15 分钟。
- 2. 中国国内能看到吗？大概率能打开，但不能保证又快又稳。
- 3. 不是静态文件，是每次访问实时抓的。


## Muse generated

- GBFS, General Bikeshare Feed Specification，通用共享单车数据规范。
- https://gbfs-heatmap.onrender.com/, https://gbfs.lyft.com/gbfs/1.1/pdx/gbfs.json
- Render + github (jxjwilliam/gbfs-heatmap)
- 用经纬度生成 Leaflet 热力图

### muse 结论
- GBFS 是国外共享单车通用的公开实时标准，格式就是 free_bike_status / vehicle_status 这种经纬度 JSON，但这套东西在中国基本不适用。哈啰、美团、青桔都没有对公众开放洛阳的车辆实时位置，我也没查到洛阳市政府数据开放平台有这份实时数据。
- 官方合作渠道，不是公开接口, 政府监管后台，不对公众开放, 高德公开数据，只能拿静态锚点(POI)
- 先用高德 POI 拿到洛阳的真实地理骨架，比如洛阳站、龙门石窟、洛邑古城、王府井商圈、大学城这些高需求点，再按早晚高峰、周末景区这种权重生成模拟车辆分布，热力图、定时刷新、聚合这套 pipeline 和接真实数据是一模一样的。以后真拿到合作数据，只要换数据源那一层就行。

### 全流程对应关系

1. 发现：读 gbfs.json，自动找 free_bike_status 的 URL，不硬编码
2. 抓取：GET 那个 JSON，取 data.bikes[] 的 lat / lon
3. 清洗：过滤经纬度越界、is_disabled、is_reserved 的车
4. 落盘：写 CSV，带抓取时间戳，方便之后按时间对比、做定时任务
5. 可视化：Leaflet + leaflet-heat，把点转成热力图，中心点取所有车的均值

定时刷新就是把第 2-5 步每 5 分钟跑一次（GBFS 的 ttl 通常是 60 秒左右，别刷太猛）。
