# Weather Chart Skill

和风天气图表技能——生成逐小时气温预报折线图和分钟降水预报柱状图。

## 功能

| 图表 | 脚本 | 数据源 | 触发 |
|------|------|--------|------|
| 逐小时预报 | `chart.py` | 24h/72h/168h | "天气" "温度" "预报" |
| 分钟降水 | `minutely_chart.py` | minutely/5m | "下雨" "降水" "带伞" |
| 定时推送 | `cron_rain.sh` | 绕开LLM直发 | 7:45 / 17:45 cron |

## 快速开始

### 1. 配置

```bash
cp scripts/config.example.json scripts/config.json
```

编辑 `scripts/config.json`，填入真实的 `api_host` 和 `api_key`。

### 2. JWT 私钥（分钟降水需要）

分钟降水需要 Ed25519 JWT 认证：

```bash
openssl genpkey -algorithm ed25519 -out scripts/private.pem
openssl pkey -in scripts/private.pem -pubout -out /tmp/public.pem
```

将 `public.pem` 上传到[和风控制台](https://console.qweather.com/project) → 创建 JWT 凭证，获取 `kid` 和项目 ID，填入 `minutely_chart.py`。

### 3. 使用

```bash
# 逐小时预报（越秀，48h）
python3 scripts/chart.py

# 指定区和时长
python3 scripts/chart.py -L 番禺 -H 24

# 分钟降水（越秀，未来2小时）
python3 scripts/minutely_chart.py

# 天河分钟降水
python3 scripts/minutely_chart.py -L 天河
```

## 目录结构

```
weather_chart/
├── README.md
├── SKILL.md              ← AstrBot 技能定义
├── temp/                 ← 生成图表输出目录
├── icons/                ← 天气图标缓存（自动下载）
└── scripts/
    ├── config.example.json
    ├── config.json        ← 不入库
    ├── private.pem        ← 不入库
    ├── chart.py
    ├── fetch_data.py
    ├── minutely_chart.py
    └── cron_rain.sh
```

## 定时推送

`scripts/cron_rain.sh` — 绕开 LLM，通过 AstrBot HTTP API 定时推送分钟降水图到 QQ。

需在 `config.json` 中配置 `astr_api_key`（WebUI 创建，需 `file` + `im` scope）。部署：

```bash
apt install cron && cron
crontab -e
# 一行：45 7,17 * * * /AstrBot/data/skills/weather_chart/scripts/cron_rain.sh >> /tmp/cron_rain.log 2>&1
```

## 依赖

- Python 3.12+
- matplotlib, numpy, scipy, pillow, cairosvg
- cryptography（JWT 签名）
- 文泉驿微米黑（中文字体，镜像自带）
