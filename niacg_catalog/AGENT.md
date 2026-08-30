# niacg_catalog — Agent 上下文

> 本文档面向维护此项目的 agent（Amadeus 红莉栖），记录**项目背景、环境约束、编码规范与决策**。
> 可复现的技术链路（搜索→下载→验货）见 `REPRODUCE.md`；当前功能定稿见 `design.md`，本文档不重复。

---

## 1. 项目定位

niacg.com（次元 niacg）免费图集采集项目。目标：**真人私拍 / 荤向 / 免费 / 非AI，亚洲向为主**。
独立项目根：`/AstrBot/data/niacg_catalog/`（不放在会话工作区）。

## 2. 目录结构

```
niacg_catalog/
├── AGENT.md         # 本文档（项目背景/环境/编码规范/决策）
├── design.md        # 功能设计定稿（一问就列新 COS 图集 的 workflow）
├── requirements.txt # 依赖声明（唯一依赖清单，见 §3）
├── .gitignore       # 忽略 runtime 产物，见 §4
├── docs/
│   └── REPRODUCE.md # 可复现链路（搜索→下载→验货）
├── scripts/
│   ├── niacg_downloader/niacg_album_downloader.py   # 下载器（CLI）
│   └── niacg_catalog/
│       ├── migrate.py            # 【待建】建库/建表/迁移
│       ├── sync_metadata.py      # 【待建】增量抓元数据落库
│       ├── build_preview_pdf.py  # 【待建】拼预览 PDF（拼成即置 pdfed=1）
│       ├── spicy_tags.json       # 荤素四档 tag 映射表（配置）
│       └── spicy.py              # 分级查表逻辑（荤优先）
├── catalog/
│   ├── niacg.db      # SQLite 主库（【未动工】）
│   ├── exports/      # JSON/md 导出物（降级品）
│   └── logs/         # 抓取日志
├── pdf/              # 【待建】预览 PDF 存档（不删）
└── photos/           # 源图，按「模特 → 套」二级目录
```

## 3. 环境约束

- **所有依赖必须在 `requirements.txt` 声明**。运行环境以 `requirements.txt` 为准，任何脚本不得凭空引入未声明的第三方库。
- **新增依赖流程：先在 `requirements.txt` 追加声明，再执行 `pip install`**——「先声明、后安装」，保证环境可复现、可追溯，防止依赖进代码却不进清单。
- 依赖**建议锁定版本**（如 `httpx==0.28.1`），避免上游变更破坏链路。
- 运行环境为 Linux 容器，出网需走宿主机代理 `http://172.17.0.1:7890`（常量，可环境变量覆盖）。

## 4. 编码规范（硬性要求）

- **无兜底**：不写掩盖错误的兜底逻辑——禁止空 `try/except` 吞异常、禁止「出错也返回默认值继续跑」的防呆代码。真实失败应当**显式抛出 / 明确报错**，宁可失败也不要静默出错、装作无事发生。
- **高度复用**：重复逻辑抽成公共函数/模块，**不复制粘贴**、不出现「改一处忘一处」的散落逻辑。
- **解耦**：职责单一、边界清晰。脚本是执行层，**无发送/删除能力**；发送、删临时文件等由编排层（agent）负责。建库与抓取分离、分级与流程分离。
- **语言与文档**：注释、docstring、日志均用**中文**；Docstring 采用 **Google style**（模块/函数/类都写）。
- **类型注解**：所有函数签名必须带**完整类型注解**（参数类型 + 返回类型），如 `def collect_urls(classid: int, pid: int) -> list[str]:`。
- **测试**：核心逻辑（纯逻辑类，如分级、入参解析、抽样、SQL 构造）必须有 **pytest 覆盖**；沾 IO 的部分用 REPRODUCE.md 的复现命令当活体集成测试。

## 5. 内容分级规则（荤素四档）

- 白名单查表：`spicy_tags.json`，四档 **荤 / 擦边 / 素 / 未分类**（荤33·擦边35·素323）
- 判定规则：**荤优先**——任一荤 tag 命中即荤档
- **新 tag 不猜**：表外 tag 一律落「未分类」，人工补档后再入表
- 分级（`spicy`/`model`）是附加字段、仅作归档标注，**不参与「列不列 / 发不发」判定**
- 数据库 `spicy` 列为**字符串**（"荤"/"擦边"/"素"/"未分类"），非整数

## 6. 归档规范

- photos 按 **模特 → 套** 二级目录（张雪馨是模特、Edison 是摄影团队，解析不出的保留原始数据）
- 套目录命名：`{套名}（可带 _N P 后缀）`，实际以 `photos/{模特}/{套名}/` 为准
- 可重建的 zip / 重复散图 / 临时文件：**发完即删**（PDF 预览档除外，见 design.md——预览 PDF 存档 `pdf/` 不删）
- 旧脚本污染说明：仙仙桃 41P 曾混入 3 张推荐位杂图（实际 38P），Machi、张雪馨可能有同类污染，新链路正则已规避

## 7. SQLite 主库方案（已拍板，未动工）

- **SQLite 为主库**，JSON/md 降级为导出物
- 存**元数据清单**（`albums` 表：id/classid/title/model/tags/pages/cover_url/date/spicy/pdfed/pulled/updated_at），全 COS 板 ≈1.67 万行，几 MB，可行
- **图片本体不进库**：走文件系统（photos/），库内存 URL 作为待拉队列
- 状态机两字段：`pdfed`=「拼过预览 PDF」，`pulled`=「下载过整套」；`selected` 已作废不建
- COS 板规模（2026-08-29 实测）：280 页 × 60 套/页 ≈ **1.67 万套**、百万张图、几百 GB~1TB 级——**只拉清单可全量，图片必须按需增量**
- 详情页**无**浏览量/点赞/评分（`video-views` 被模板注释，全站零热度数据）——schema 已砍掉这三个虚字段

## 8. 文档分工

| 文件 | 承载内容 |
|---|---|
| `design.md` | 功能 workflow 定稿、脚本分工、红线 |
| `docs/REPRODUCE.md` | 纯可复现技术链路（搜索→下载→验货）、已知坑 |
| `AGENT.md` | 项目背景 / 环境约束 / 编码规范 / 决策记录 / 归档规范 |

文件名一律**大写**（`AGENT.md` / `REPRODUCE.md`）；`AGENT.md`、`requirements.txt`、`.gitignore` 位于项目根目录。

## 9. 决策记录（tool-nut 拍板）

| 日期 | 决策 |
|---|---|
| 08-28 | scripts 按用途分包，探路脚本不保留，文件名说明用途 |
| 08-28 | photos 按「模特→套」整理，可重建 zip 全删 |
| 08-28 | 荤素分级、映射表先写、不扫全量、荤优先 |
| 08-28 | 清单脚本先测后进工作区 |
| 08-28 | SQLite 为主库，JSON/md 降级为导出物 |
| 08-28 | 项目迁移至 `/AstrBot/data/niacg_catalog/` |
| 08-29 | 链路文档只写可复现内容，项目背景归 AGENT.md |
| 08-30 | 发送不判荤素；`pdfed`=看过没、`pulled`=看过整套没；存量 photos 全部初始化 0 |
| 08-30 | `spicy` 改字符串四档；`selected` 作废；建库建表拆到 `migrate.py` |
| 08-30 | 增量同步「撞到已有 pid 即停」；建库/抓取分离 |

## 10. 工作流程规范

- **先测后进**：脚本先在 /tmp 等临时位置跑通验证，再归档进 `scripts/`
- **来源标注**：社区/官方结论标来源；自推导结论标「推测：」
- **红线**：含违法内容（乱伦/裸贷/盗摄，如铁手叫兽系列）一律不碰
- **token 纪律**：图片不整包塞上下文，走 元数据(file/identify)→缩略图→抽样→脚本闭环 四档方案
- **先问后干**：遇到不清楚的**优先问 tool-nut 拍板**，不要自己闷头框框干

## 11. 当前状态（2026-08-30）

- 功能设计已定稿（`design.md`）；`migrate.py` / `sync_metadata.py` / `build_preview_pdf.py` 待建，`niacg.db` 未动工
- 下载器 `niacg_album_downloader.py` 已能下载整套（`datu|hen` 双路径正则）；**缺**置 `pulled=1` + 每套均匀抽 5 张返回绝对路径
- `spicy.py` + `spicy_tags.json` 已有；需补「未分类」字符串映射
- 存量 photos：**9 模特 / 14 套 / 693 张**（详见 REPRODUCE.md 或目录）
