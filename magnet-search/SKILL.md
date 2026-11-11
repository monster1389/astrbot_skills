---
name: magnet-search
description: 搜索 BT4G 磁力链接。用户要搜磁力、找 BT 种子、要某个资源的下载链接时使用。运行 scripts/magnet.py 返回 magnet 列表。不用于普通网页搜索。
---

# 磁力搜索

在本 skill 目录下运行：

```bash
python3 scripts/magnet.py "<关键词>" <条数>
```

关键词必填，条数可选（默认 15）。

## 执行要点

1. 脚本默认走宿主机代理 `http://172.17.0.1:7890`，无需额外设置；换代理用 `PROXY=...`，强制直连用 `PROXY=`
2. 简体中文关键词常返回空，换繁体或英文重试一次
3. 退出码 2 表示无结果，退出码 3 表示请求失败，把 stderr 转述给用户
4. 输出是完整 magnet，原样返回，不截断、不改写、不追加 tracker

不要自己重写请求逻辑。不要访问 bt4g 的 HTML 页面，会被 Cloudflare 拦截。
