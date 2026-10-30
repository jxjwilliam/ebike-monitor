# Visuals — 可视化产物目录

本目录存放项目所有可视化相关文件，与 `docs/` 下的 Markdown 文档分离。

## 目录结构

```
visuals/
├── README.md              # 本文件
├── html/                  # 可交互的 HTML 可视化页面
│   ├── oc_architecture.html        # 系统架构图
│   ├── oc_processing.html          # 数据处理流程图
│   ├── oc_sequence.html            # 时序图
│   ├── oc_workflow.html            # Workflow 流程图
│   └── *.visual-check.html         # 可视化校验页面
├── screenshots/           # 可视化截图（PNG，多分辨率/主题）
│   ├── *.1440x900.dark.png
│   ├── *.1440x900.light.png
│   ├── *.2048x1320.dark.png
│   └── *.2048x1320.light.png
└── configs/               # 可视化配置文件（JSON）
    ├── oc_architecture.json
    ├── oc_processing.json
    ├── oc_sequence.json
    ├── oc_workflow.json
    └── *_delivery.json    # 交付配置
```

## 查看方式

- **HTML 页面**：直接在浏览器中打开 `html/` 下的 `.html` 文件
- **Mermaid 图表**：在 `docs/wb_README.md` 中内嵌，支持 GitHub/VS Code 自动渲染
- **截图**：`screenshots/` 下的 PNG 文件可直接查看，包含明暗主题 × 多分辨率

## 文件命名规则

- `oc_` 前缀：由可视化引擎自动生成
- `wb_` 前缀：项目文档关联的可视化
