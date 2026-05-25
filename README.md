# Jellyfin Anime Management Skill

Agent skill + Python scripts for managing **Jellyfin anime media library** with **Bangumi.tv** integration.

## 主要功能

| 模块 | 说明 |
|------|------|
| **SKILL.md** | Agent 全流程操作规范（8 步），指导 AI agent 自动完成媒体库整理 |
| **generate_nfo.py** | 从 Bangumi API 生成 Jellyfin 兼容的 NFO 元数据文件（支持 tvshow / movie / concert） |
| **bangumi_ids.csv** | 作品索引数据库，记录 cn_name, jp_name, year, type, bangumi_id, status |

## 工作流程（8 步）

```
Step 1  用户指定源文件夹
  │
Step 2  遍历扫描所有文件，建立初步结构清单（显示给用户确认）
  │
Step 3  分析并提取作品名称，分类（TV / 电影 / 演唱会），生成 CSV
  │
Step 4  Bangumi API 搜索匹配，通过 name + year 自动匹配 ID
  │   ├─ 匹配成功 → 写入 CSV
  │   └─ 置信度低 → Step 5 用户手动介入
  │
Step 5  用户手动选择或跳过（交互式确认）
  │
Step 6  创建 Jellyfin 兼容文件夹名，逐个 cp 文件并重命名
  │       （完整路径 + 引号，避免 shell 转义）
  │
Step 7  同步处理字幕文件（.ass / .srt），按规范命名
  │
Step 8  生成 NFO 元数据 → Jellyfin 自动识别
```

## 使用方式

### NFO 元数据生成

```bash
# 全量生成（默认 /server/Media/Anime）
python3 scripts/generate_nfo.py

# 指定库路径
python3 scripts/generate_nfo.py --library "/Volumes/Media/Anime"

# 指定系列
python3 scripts/generate_nfo.py --series "Cowboy Bebop"

# 强制刷新缓存
python3 scripts/generate_nfo.py --refresh

# 指定 API 间隔（防止限流）
python3 scripts/generate_nfo.py --delay 0.3
```

### 配合 Agent 使用完整流程

在 Agent 中加载 skill 后，指定源目录即可自动执行 8 步流程：

```
用户：整理 /Volumes/Media/Raw/Anime_Downloads/ 到 /Volumes/Media/Anime/
Agent：自动执行 Step 1-8
```

## CSV 格式

```csv
jp_name,cn_name,en_name,year,type,folder_name,bangumi_id,status
```

| 列 | 说明 |
|---|---|
| `jp_name` | **主键** — 日文名/罗马音（来自 Bangumi name），以此为准 |
| `cn_name` | 中文名（来自 Bangumi name_cn），辅助参考 |
| `en_name` | 英文名，辅助交叉验证 |
| `year` | 发行年份 |
| `type` | `tv` / `movie` / `concert` / `ova` / `special` |
| `folder_name` | 标准化文件夹名（日文罗马音/英文） |
| `bangumi_id` | Bangumi 条目 ID |
| `status` | `confirmed` / `new` |

## Jellyfin 文件夹规范

```
Anime/
├── bangumi_ids.csv
├── Series Name (2006)/
│   ├── tvshow.nfo
│   ├── Season 01/
│   │   ├── Series Name S01E01.mkv
│   │   ├── Series Name S01E01.ass
│   │   └── ...
│   └── Season 02/
├── Movie Title (2016)/
│   ├── Movie Title (2016).nfo
│   ├── Movie Title (2016).mkv
│   └── Movie Title (2016).srt
└── Concert Live (2023)/
    ├── Concert Live (2023).nfo
    └── Concert Live (2023).mkv
```

## 依赖

- Python 3.8+
- Bangumi API（https://api.bgm.tv/）
- 仅需标准库，无第三方依赖

## 仓库结构

```
jellyfin_animanagement_skill/
├── SKILL.md                    # Agent 全流程操作规范（8 步）
├── README.md                   # 本文件
├── AGENTS.md                   # 代理执行基线指引（跨仓库通用）
├── LICENSE
├── scripts/
│   └── generate_nfo.py         # NFO 元数据生成器 v3.0
└── references/                 # 参考文件（预留）
```
