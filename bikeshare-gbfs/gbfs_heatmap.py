#!/usr/bin/env python3
"""
GBFS 共享单车实时热力图 - 全流程示例
练通用的城市: 美国波特兰 Biketown (公开 GBFS, 无需 key)
原理, 和之后切洛阳完全一样, 只有数据源一层不同:
  1. gbfs.json 发现 free_bike_status 的真实 URL
  2. 抓取 -> 清洗 -> 存 CSV
  3. 用经纬度生成 Leaflet 热力图 HTML (离线可打开, CDN 加载地图底图)

用法:
  python3 gbfs_heatmap.py
  python3 gbfs_heatmap.py --gbfs https://gbfs.lyft.com/gbfs/1.1/pdx/gbfs.json --out ./output

切到洛阳时:
  把 fetch_free_bikes() 换成你的洛阳数据源函数即可,
  只要它返回 [{"lat": float, "lon": float, "type": str}, ...],
  后面的清洗和画图不用改.
  洛阳目前没有公开实时接口, 演示版可用高德 POI 停车点 +
  按早晚高峰权重模拟分布, 先跑通同一套 pipeline.
"""
import argparse
import csv
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_GBFS = "https://gbfs.lyft.com/gbfs/1.1/pdx/gbfs.json"
HEADERS = {"User-Agent": "gbfs-heatmap-demo/1.0 (+personal-learning-project)"}


def fetch_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        return json.loads(resp.read().decode("utf-8"))


def resolve_free_bike_url(gbfs_url: str) -> str:
    """从 gbfs.json 自动发现 free_bike_status, 不硬编码, 换城市也通用."""
    doc = fetch_json(gbfs_url)
    feeds = doc.get("data", {})
    # v1.1 结构: data.en.feeds ; v2/v3 结构可能不同, 做兼容
    candidates = []
    if isinstance(feeds, dict):
        for lang_block in feeds.values():
            if isinstance(lang_block, dict):
                candidates.extend(lang_block.get("feeds", []))
        candidates.extend(feeds.get("feeds", []))
    for feed in candidates:
        if feed.get("name") in ("free_bike_status", "vehicle_status"):
            return feed["url"]
    raise RuntimeError("gbfs.json 里没有 free_bike_status / vehicle_status")


def fetch_free_bikes(free_bike_url: str) -> list[dict]:
    doc = fetch_json(free_bike_url)
    data = doc.get("data", {})
    # v1/v2: data.bikes ; v3: data.vehicles
    raw = data.get("bikes") or data.get("vehicles") or []
    bikes = []
    for item in raw:
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        if item.get("is_disabled"):
            continue
        if item.get("is_reserved"):
            continue
        bikes.append({
            "lat": lat,
            "lon": lon,
            "type": item.get("type") or item.get("vehicle_type_id") or "unknown",
            "bike_id": item.get("bike_id") or item.get("vehicle_id") or "",
        })
    return bikes


def write_csv(bikes: list[dict], path: Path, fetched_at: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["fetched_at", "lat", "lon", "type", "bike_id"])
        w.writeheader()
        for b in bikes:
            w.writerow({"fetched_at": fetched_at, **b})


def write_heatmap(bikes: list[dict], path: Path, title: str, fetched_at: str) -> tuple[float, float]:
    center_lat = sum(b["lat"] for b in bikes) / len(bikes)
    center_lon = sum(b["lon"] for b in bikes) / len(bikes)
    points = json.dumps([[b["lat"], b["lon"], 1] for b in bikes])
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<style>html,body,#map{{height:100%;margin:0}} .info{{position:absolute;z-index:999;top:12px;left:12px;background:#fff;padding:10px 12px;border-radius:8px;font:14px/1.6 system-ui;box-shadow:0 2px 10px rgba(0,0,0,.2)}}</style>
</head><body><div id="map"></div>
<div class="info"><b>{title}</b><br>抓取时间: {fetched_at} UTC<br>可用车辆: {len(bikes)} 辆<br>数据来源: 公开 GBFS free_bike_status, 无需 key</div>
<script>
var map = L.map('map').setView([{center_lat:.6f}, {center_lon:.6f}], 12);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{maxZoom: 19, attribution: '&copy; OpenStreetMap'}}).addTo(map);
var points = {points};
L.heatLayer(points, {{radius: 25, blur: 18, maxZoom: 17}}).addTo(map);
</script></body></html>"""
    path.write_text(html, encoding="utf-8")
    return center_lat, center_lon


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gbfs", default=DEFAULT_GBFS)
    ap.add_argument("--out", default="./output")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    free_url = resolve_free_bike_url(args.gbfs)
    print(f"free_bike_status: {free_url}")
    bikes = fetch_free_bikes(free_url)
    print(f"可用车辆: {len(bikes)}")
    if not bikes:
        print("没有可用车辆, 不生成热力图", file=sys.stderr)
        return 1

    write_csv(bikes, out / "bikes.csv", fetched_at)
    center = write_heatmap(bikes, out / "heatmap.html", "Biketown Portland 实时分布热力图", fetched_at)
    print(f"中心点: {center[0]:.5f}, {center[1]:.5f}")
    print(f"CSV: {out / 'bikes.csv'}")
    print(f"热力图: {out / 'heatmap.html'}")
    # 类型分布, 方便你一眼看懂数据
    from collections import Counter
    print("类型分布:", dict(Counter(b["type"] for b in bikes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
