---
name: anime-media-manager
description: Manage anime media library at /server/Media/Anime — maintain bangumi_ids CSV, match Bangumi IDs, standardize folder structure, rename files for Jellyfin.
---

# Skill: anime-media-manager — Anime 媒体库标准化管理

## 概述

管理 `/server/Media/Anime` 目录下的动画媒体库，确保文件夹结构、文件命名、
Bangumi ID 映射三者一致，兼容 Jellyfin 和 Bangumi 插件。

## 数据文件

`/server/Media/Anime/bangumi_ids.csv` — UTF-8 BOM，六栏：

```csv
cn_name,jp_name,year,folder_name,bangumi_id,status
```

| 列 | 类型 | 说明 |
|---|---|---|
| `cn_name` | string | 中文名（来自 Bangumi name_cn） |
| `jp_name` | string | 日文名或罗马音（来自 Bangumi name） |
| `year` | string | 发行年份 |
| `folder_name` | string | 磁盘文件夹名，含 (Year) 后缀 |
| `bangumi_id` | string | Bangumi 条目 ID |
| `status` | enum | `confirmed` 已验证 / `new` 待审 |

## 文件夹规范

```
TV Series Name (Year)/
├── Season 01/
│   ├── TV Series Name S01E01.mkv
│   └── ...
├── Season 02/
├── Specials/
└── Extras/

Movie Name (Year)/
├── Movie Name (Year).mkv
└── ...
```

- 文件夹名 = 罗马音/英文名 + ` (Year)`，不含特殊符号
- 剧集文件 = `Series Name SxxExx.mkv`，不含编码/分辨率/发布组信息
- 外挂音轨 `.mka`，外挂字幕 `.ass`

---

## 标准工作流程

### 1. Bangumi ID 匹配与校正

当 CSV 中 `bangumi_id` 缺失或可疑时，通过 Bangumi API 重新匹配：

**步骤 A — 确定搜索词（按优先级）**

1. 如果已有 `cn_name`，优先用它搜索（Bangumi 中文名匹配精度最高）
2. 如果没有 `cn_name`，用 `jp_name`
3. 如果两者都无，从 `folder_name` 提取番名（去掉 `(YYYY)` 后缀）
4. 搜索前统一清理特殊字符

**步骤 B — 调用 Bangumi API**

```python
# 按动漫类型搜索
GET https://api.bgm.tv/search/subject/{quote(query)}?type=2

# 不限类型（演唱会/OVA 等可能不在 type=2）
GET https://api.bgm.tv/search/subject/{quote(query)}

# 获取条目详情（确认 cn_name/jp_name）
GET https://api.bgm.tv/v0/subjects/{id}
```

- 请求头加 `User-Agent: Mozilla/5.0`
- 调用间隔 ≥ 0.15s，避免限流

**步骤 C — 验证结果**

- 搜索结果 top 1 通常是正确的，但多季同名条目需用 year 二次确认
- 通过 `/v0/subjects/{id}` 获取详情，对比 `name_cn`/`name` 与预期是否吻合
- `type` 字段标识条目类型（2=动漫，6=演唱会/演出，1=书籍）
- 如类型不匹配，不带 `?type=` 参数重试

**步骤 D — 更新 CSV**

将 `bangumi_id`、`cn_name`、`jp_name` 写入对应行，新条目 `status` 设为 `new`，
人工确认后改为 `confirmed`。

### 2. 新增条目入库

1. 创建 `Name (Year)/` 目录
2. 放入媒体文件，按规范重命名
3. 搜索 Bangumi 获取正确 ID
4. 向 CSV 追加一行

### 3. 批量重命名（发布组 → SxxExx）

发布组原文件名示例：
```
[Group] Series Name [01][Codec_resolution][x264_flac].mkv
```

步骤：
1. `cp -l` 创建硬链接到标准文件名（`Series Name S01E01.mkv`）
2. 确认硬链接文件可正常读取
3. `stat -c '%i' 原名 标准名` 验证 inode 一致
4. `rm` 原名释放目录空间

### 4. 目录规范化

1. 创建符合规范的新目录
2. 用 `cp -r --reflink=auto` 或硬链接复制内容
3. 扁平化嵌套结构（移除发布组子目录、CDs 文件夹等）
4. 确认新旧目录内容一致后删除旧目录

## 验证模板

### CSV 完整性
```python
import csv
with open('/server/Media/Anime/bangumi_ids.csv', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for r in reader:
        assert r['bangumi_id'], f'Missing ID: {r["folder_name"]}'
        assert r['cn_name'] or r['jp_name'], f'Missing name: {r["folder_name"]}'
```

### 文件夹规范性
```python
import os, re
base = '/server/Media/Anime'
for f in sorted(os.listdir(base)):
    if not os.path.isdir(f'{base}/{f}'):
        continue
    assert re.search(r'\(\d{4}\)', f), f'Missing year: {f}'
```

## 安全规范

- 修改 CSV 前先创建 `.bak` 备份
- 硬链接操作前确认 inode 一致
- 删除旧目录前确认标准目录已就绪
- Bangumi API 调用间隔 ≥ 0.15s
- 所有删除操作先用 `ls` 确认目标

## 相关链接

- Bangumi API: https://api.bgm.tv/
- Bangumi Jellyfin 插件：读取 ID 匹配元数据
