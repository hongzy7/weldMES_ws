# 华沿机器人智能焊接助手

这是一个面向焊接机器人现场作业的 MES 助手原型项目，用于演示机器人侧任务执行、过程采集、焊缝追溯、焊后检查和 BI 分析的完整操作闭环。

## 项目结构

```text
weldMES_ws/
├─ src/
│  ├─ index.html                         # 可点击 HTML 原型
│  └─ assets/
│     └─ welding-plugin-ui.png           # WeldPlus 焊接插件界面预览图
├─ services/
│  └─ robot_adapter.py                   # 本地机器人只读数据采集适配服务
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

如只查看界面，可直接用浏览器打开：

```text
src/index.html
```

如需要读取机器人实时数据，先启动本地适配服务：

```bash
python services/robot_adapter.py
```

再打开：

```text
src/index.html
```

机器人焊接页会从 `http://127.0.0.1:8765/api/robot/sample` 读取数据，再由本地适配服务访问机器人控制器和焊接工艺包。

## 原型内容

- 支持操作员、检查员、班组长等不同角色入口。
- 覆盖登录、自检、焊材录入、工件确认、焊缝任务确认、工艺确认、机器人焊接、焊缝检查、追溯和 BI 看板。
- “机器人焊接”页面嵌入 WeldPlus 机器人操作界面，并通过本地适配服务读取实时电流、实时电压和起弧/收弧之间的 TCP 轨迹累计长度。
- `data/samples/` 中提供系统需要读取和采集的样例数据表。
- `data/dictionaries/` 中提供字段说明表，方便开发工程师确认字段含义、类型、来源和示例。
- `data/crafts/` 中放置真实焊接工艺 JSON 导出文件和导入模板。
- `docs/robot-interfaces/` 中放置机器人控制器通信协议、焊接工艺包通信协议、Python SDK 文档，以及机器人状态和焊机参数读取说明。

## 当前边界

当前项目主要是原型和开发对接资料；`services/robot_adapter.py` 提供第一版只读采集适配，用于读取机器人控制器 `10003` 和焊接工艺包状态端口 `30601`。

实际电流、实际电压依赖焊接工艺包或焊机协议是否提供对应实时字段；如果现场工艺包未输出这些字段，需要继续接入焊机协议、模拟量输入或厂商 SDK。实际焊接长度只累计起弧到收弧之间的 TCP 末端轨迹距离，空走、定位、回零等非弧段移动不计入焊接长度。机器人使能、去使能等安全相关动作不建议由纯前端直接下发。
