---
name: image_sender
description: 发送 3 张及以上图片时使用。按优先级选择发送方式（合并转发插件 > PDF），多图生成 PDF 用 scripts/images_to_pdf.py，交付物发完即删（仅限可重建的）。单张/2张图片不使用本 skill。
---

# Image Sender 图片发送

本 skill 专门负责**批量图片发送**：发送 ≥3 张图片时触发。单张或 2 张直接单发，不适用本 skill。

## 发送规则（优先级从高到低）

1. **用户特殊要求**：用户明确要求（发图/拼 PDF/打包）时，以用户要求为准。
2. **合并转发插件**：存在合并转发工具（如 merge_send_images）时**优先使用插件**：
   - 图片 **≤30 张** → 插件合并转发卡片（一张卡片包含全部）
   - 图片 **>30 张** → 拼 PDF 发送
3. **无合并转发插件**时：
   - **<3 张** → 直接单发
   - **≥3 张** → 拼 PDF 发送

## PDF 生成

使用 `scripts/images_to_pdf.py`：

```bash
# 文件列表输入
python3 scripts/images_to_pdf.py -o out.pdf -i a.webp b.webp c.jpg

# 目录输入（自动按文件名自然排序）
python3 scripts/images_to_pdf.py -o out.pdf -d /path/to/images/

# 不指定 -o 时默认输出到当前目录 images_<时间戳>.pdf
python3 scripts/images_to_pdf.py -d /path/to/images/
```

特性：每页一张保留原比例（可 --page-rows/cols 网格）、自动过滤缩略图（--min-width）、生成后 pypdf 自动复核页数。

## 交付与清理

- **输出位置**：PDF 默认输出当前工作目录（NapCat 容器可读）。
- **发完即删（仅限能重建的）**：PDF、zip 等可重新生成的传输载体，发送成功后删除本地副本；**源图/素材不删**。
- **发送方式**：PDF 用 send_message_to_user 的 file 类型发送，文件名用英文 + 完整后缀（QQ 对中文文件名会吃后缀），文件消息不带附加文字。

## 流程

```
收集图片路径 → 按优先级选择方式（插件卡片 / 拼PDF）→ 发送 → 确认成功 → 删交付物
```
