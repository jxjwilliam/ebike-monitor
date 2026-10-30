# 电单车平台：数据与 API 规格

日期：2026-10-30；版本：0.1。本文是开发契约草案，接口尚未实现。口径以 [产品规格](oc_01_product_spec.md) 为准。

## 1. 数据实体

所有业务实体采用 UUID 主键，记录 `created_at/created_by`；组织与项目字段用于隔离。外部点位 ID 按字符串保存，禁止经浮点数中转。

| 实体 | 关键字段与约束 |
| --- | --- |
| `project` | `org_id, name, timezone, policy_version`；默认 Asia/Shanghai |
| `source_contract` | `provider, brands, cities, capabilities, authorization_ref, valid_until, retention_policy`；不保存明文登录凭证 |
| `site` / `site_version` | `external_id, city, park_name, raw_coordinates, coord_sys, fence_geometry, center, version`；历史版本不可变 |
| `monitoring_region` | `site_version_id, polygon, coord_sys, size_m, construction_method, approved_by, version`；与停车围栏分别保存 |
| `campaign` | `project_id, dates, time_windows, planned_sessions, policy_version`；冻结计划分母 |
| `session` | `campaign_id, site_version_id, region_id, starts_at, ends_at, plan_revision, status` |
| `brand_run` | `session_id, brand, source_contract_id, source_mode`；同 Session 每品牌唯一 |
| `capture_slot` | `brand_run_id, round_index, scheduled_at, deadline_at, status, selected_attempt_id`；轮次 0..6 唯一 |
| `capture_attempt` | `slot_id, attempt_no, captured_at, received_at, source_updated_at, clock_offset_ms, device_id, evidence_id, issues` |
| `evidence` | `org_id, object_key, object_version, sha256, mime, bytes, capture_origin, retention_until`；原件不可覆盖 |
| `analysis_run` | `evidence_id, model_version, code_version, prompt_version, roi_version, status, outputs`；结果追加 |
| `count_result` | `slot_id, value, metric_kind, method, evidence_ids, status, revision, approved_by` |
| `interval_result` | `brand_run_id, interval_index, start/end_slot_id, net_change, endpoint_in/out, gross_in/out, suspected_dispatch_in, metric_metadata, revision` |
| `quality_issue` | `scope_type, scope_id, code, severity, resolution, resolved_by` |
| `review` / `audit_event` | 变更前后值、原因、版本、操作者；追加写入 |
| `outbox` / `job` | 事务事件、派发标记、幂等键、重试次数、租约、截止时间 |
| `delivery` | `campaign_id, included_result_revisions, manifest_key, manifest_hash, status, approved_by` |

位置多边形统一显式闭环 `[lng,lat]`；保留原始顶点顺序及字符串。校验经纬度范围、自交、至少三个不同顶点、城市合理性和坐标标签。GCJ-02 的 GeoJSON 外观数据只用于内部显式约定的格式，不能直接作为标准 WGS84 GeoJSON 对外发送；导出附 `coord_sys`。

## 2. 状态与指标约束

任务状态：`draft → scheduled → collecting → processing → review_required → approved → published`。失败、缺失和取消作为明确状态或异常原因，不自动变成 approved。

每个可空指标都带：`status ∈ {proposed, approved, unobservable, missing, rejected}`、`method`、`evidence_ids`、`reason_code`、`revision`。`method` 可取 `human_image_count`、`cv_icon_count`、`authorized_snapshot`、`endpoint_id_match`、`field_video_event`、`authorized_event_stream`、`human_review`。

- `value=0` 只能表示有足够证据支持零；`null` 必须说明原因。
- 非负计数是整数；净变化可为负数。净变化仅在首末同区域、同来源口径且有效时计算。
- `interval_index=0..5`，区间 `(start,end]`；边界时刻事件仅归到一个区间，事件必须有去重 ID 或可审计去重规则。
- 稳定 ID 先在供应商授权范围内处理，再使用项目范围 HMAC 假名化；不可把跨品牌车辆 ID 当同一实体。
- 调度入与总流入采用同一流量口径时，`0 ≤ suspected_dispatch_in ≤ total_in`。总流入不可观测时，独立的疑似调度事件只存事件表述，不强填数值子集。
- 在同口径完整观测下校验 `期末数−期初数=总流入−总流出`；不满足时记录 `BALANCE_MISMATCH`，不反算修改观测值。平台可见库存受上下线影响时，保留不可比原因。
- “人工现场库存”和“平台显示库存”分开，不混用平衡公式。

## 3. API 约定

前缀 `/api/v1`，JSON UTF-8；OIDC 或经审查的会话登录方案。服务端签发短期访问会话，供应商凭证按项目授权；API 不接收三品牌账号验证码作为业务数据。分页使用 cursor；错误返回 `code/message/request_id/details`。

| 方法与路径 | 说明 |
| --- | --- |
| `POST /sites/imports` | 上传点位文件，预检并返回行级问题；确认后才创建版本 |
| `POST /regions` | 创建监控区域草稿；记录构造方法与坐标系 |
| `POST /regions/{id}/approve` | 有权限人员批准区域版本 |
| `POST /campaigns` | 创建日期、时段、点位与品牌计划 |
| `POST /campaigns/{id}/schedule` | 冻结计划并生成 Session、品牌和七轮槽位 |
| `GET /sessions?cursor=...` | 按当前权限查询任务 |
| `POST /capture-attempts` | 申请一次采集尝试和上传凭证 |
| `POST /capture-attempts/{id}/complete` | 上传完成确认，经服务端校验后进入处理 |
| `POST /sessions/{id}/issues` | 报告运营区外、漏采等异常 |
| `GET /sessions/{id}/review` | 七轮证据、建议结果、时空偏差和修订历史 |
| `PATCH /count-results/{id}` | 提交人工修订，必须带版本号与原因 |
| `PATCH /interval-results/{id}` | 按指标分别修订，不升级证据能力 |
| `POST /sessions/{id}/approve` | 检查质量状态与角色分离，再批准结果 |
| `POST /deliveries` | 异步生成固定结果版本的交付包 |
| `GET /deliveries/{id}` | 查询状态，授权下载 |

写操作接收 `Idempotency-Key`；同键同请求重放返回原结果，同键不同请求返回 409。数据库唯一约束是最终防线。修订采用 `If-Match`/revision 乐观锁，冲突返回 409，不静默覆盖。

示例请求，时间只是测试数据：

```json
{
  "slot_id": "00000000-0000-4000-8000-000000000001",
  "captured_at": "2026-11-03T18:10:08+08:00",
  "source_updated_at": null,
  "capture_origin": "manual_upload",
  "mime": "image/png",
  "bytes": 2400000,
  "sha256": "<64位十六进制摘要>"
}
```

## 4. 上传与处理事务

1. API 校验人员与槽位权限，创建 attempt、不可重复对象 key 和限制到该对象的短时上传授权。
2. 客户端直传私有 OSS；重试使用同 attempt，续传不创建额外有效结果。
3. 完成接口检查对象存在、大小、文件签名和服务端计算的 SHA-256；不盲信客户端摘要、文件扩展名或 ETag。
4. 证据记录和 Outbox 同事务提交。消费者以 `evidence_id+pipeline_version` 幂等处理。
5. 原始对象写入后不覆盖，派生图和标注使用新 key。多次采集作为新 attempt，不复用对象。
6. 短时预览授权按每次请求校验项目权限；日志不记录签名 URL 查询参数。

首期建议图片 ≤20 MB，实际解码像素也设上限；视频独立采用分片上传与配额，限值经 PoC 调整。人工截图的 `captured_at` 属于申报时间，结合设备日志/OCR交叉核对，不伪装成硬件可信时间。

## 5. 质量码与交付

至少实现：`MISSING_CAPTURE`、`TIME_OUT_OF_WINDOW`、`BRAND_TIME_SKEW`、`TIME_UNVERIFIED`、`SOURCE_STALE`、`ROI_UNVERIFIED`、`VIEWPORT_DRIFT`、`ICON_OCCLUSION`、`OUT_OF_SERVICE_AREA`、`UNSUPPORTED_FLOW`、`BALANCE_MISMATCH`。

每份交付清单固化输入证据、点位/区域、模型、人工修订、验收规则和结果 revision。批准后修订生成新 delivery，旧版本仍可查。CSV/Excel 对以 `=,+,-,@` 开头的用户文本执行公式注入防护，ID 保持文本；导出必须保留缺失状态，不能把空值格式化为零。
