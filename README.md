# 华沿机器人智能焊接助手

这是一个面向焊接机器人现场作业的 MES 助手原型项目，用于演示机器人侧任务执行、过程采集、焊缝追溯、焊后检查和 BI 分析的完整操作闭环。

## 项目结构

```text
weldMES_ws/
├─ src/
│  ├─ index.html                         # 可点击 HTML 原型
│  └─ assets/
│     └─ welding-plugin-ui.png           # WeldPlus 焊接插件界面预览图
├─ data/
│  ├─ samples/
│  │  └─ sample_tables.xlsx              # 系统样例数据表
│  ├─ dictionaries/
│  │  └─ 华沿机器人智能焊接助手_数据表头说明.xlsx  # 数据字段说明表
│  └─ crafts/
│     ├─ exports/                        # 真实焊接工艺 JSON 导出文件
│     └─ templates/                      # 焊接工艺 JSON 导入模板
├─ docs/
│  ├─ 焊接机器人MES助手.docx              # MES + BI 系统说明文档
│  └─ robot-interfaces/                  # 机器人控制器、焊接插件和 SDK 接口文档
├─ README.md
└─ .gitignore
```

## 如何查看原型

直接用浏览器打开：

```text
src/index.html
```

该文件是独立 HTML 原型，不需要启动服务器。

## 原型内容

- 支持操作员、检查员、班组长等不同角色入口。
- 覆盖登录、自检、焊材录入、工件确认、焊缝任务确认、工艺确认、机器人焊接、焊缝检查、追溯和 BI 看板。
- “机器人焊接”页面已使用 WeldPlus 焊接插件界面作为现场执行预览，MES 助手保留机器人使能、任务完成确认和去使能的流程按钮。
- `data/samples/` 中提供系统需要读取和采集的样例数据表。
- `data/dictionaries/` 中提供字段说明表，方便开发工程师确认字段含义、类型、来源和示例。
- `data/crafts/` 中放置真实焊接工艺 JSON 导出文件和导入模板。
- `docs/robot-interfaces/` 中放置机器人控制器通信协议、焊接工艺包通信协议、Python SDK 文档，以及机器人状态和焊机参数读取说明。

## 当前边界

当前项目是静态原型和开发对接资料，不直接连接真实机器人、焊机、客户 MES/ERP、数据库或后端服务。

后续真实接入时，建议通过后端适配层读取机器人控制器、焊接插件和焊机数据，再由 MES 助手前端展示状态、过程采集和追溯结果；机器人使能、去使能等安全相关动作不建议由纯前端直接下发。
