---
name: anime-media-manager
description: Full lifecycle of Jellyfin anime media library management — scan source folder, extract series/movie names, match Bangumi IDs, build Jellyfin-compatible folder structure, move/rename files, handle subtitles, generate NFO metadata.
---

# Skill: anime-media-manager — Jellyfin 动漫媒体库全流程管理

## 概述

将用户指定的原始 **Anime 内容文件夹** 中的混装内容（TV 动画、电影、演唱会、OVA、特典等），
逐个梳理、匹配 Bangumi ID、转换文件夹结构，最终输出为 Jellyfin 兼容的标准化媒体库。

**命名权威优先级：日文名（假名/罗马音） > 英文名 > 中文名**
中文可能存在翻译歧义（如「星际牛仔」vs「Cowboy Bebop」vs「カウボーイビバップ」），
因此 CSV 中以 `jp_name`（Bangumi name 字段）为锚定基准，`cn_name` 仅作辅助参考。
文件夹名使用**日文罗马音或官方英文名**，不用中文译名。

---

## 一、核心数据文件

### bangumi_ids.csv

位置：`<target_library>/bangumi_ids.csv`，UTF-8 BOM，七栏：

```csv
jp_name,cn_name,en_name,year,type,folder_name,bangumi_id,status
```

| 列 | 类型 | 说明 |
|---|---|---|
| `jp_name` | string | **主键** — 日文名/罗马音（来自 Bangumi name），以此为准匹配 | |
| `cn_name` | string | 中文名（来自 Bangumi name_cn），辅助参考 | |
| `en_name` | string | 英文名（Bangumi name 若为罗马音则与 jp_name 同值），辅助参考 |
| `year` | string | 发行年份 |
| `type` | string | 类型：`tv` / `movie` / `concert` / `ova` / `special` |
| `folder_name` | string | 最终标准化的文件夹名（日文罗马音/英文） |
| `bangumi_id` | string | Bangumi 条目 ID |
| `status` | enum | `confirmed` / `new` |

### metadata 目录

每个作品文件夹下生成 `<folder_name>.nfo`，存放 Jellyfin 可读的 NFO 元数据。
格式见第六节。

---

## 二、标准文件夹规范（Jellyfin 兼容）

```
<target_library>/
├── bangumi_ids.csv                     # 全局索引
│
├── Series Name (2006)/
│   ├── Series Name (2006).nfo
│   ├── Season 01/
│   │   ├── Series Name S01E01.mkv
│   │   ├── Series Name S01E01.ass      # 外挂字幕
│   │   ├── Series Name S01E02.mkv
│   │   └── ...
│   ├── Season 02/
│   ├── Specials/
│   └── Extras/
│
├── Movie Name (2001)/
│   ├── Movie Name (2001).nfo
│   ├── Movie Name (2001).mkv
│   └── Movie Name (2001).ass
│
└── Concert Name (2019)/
    ├── Concert Name (2019).nfo
    └── Concert Name (2019).mkv
```

关键规则：
- **文件夹名** = `English/Romaji Name (Year)`，不含特殊符号
- **剧集文件** = `Series Name SxxExx.mkv`，不含编码/分辨率/发布组信息
- **外挂字幕** `.ass` / `.srt` 与对应视频文件同名同目录
- **外挂音轨** `.mka` 与对应视频文件同名同目录

---

## 三、工作流程（8 步）

### Step 1: 用户指定 Anime 内容文件夹

用户提供一个**源路径**（source），即存放原始杂乱内容的目录。
该路径可能包含 TV 动画、电影、演唱会、OVA、特典等多种类型的混装内容。

```
源路径示例：
/Volumes/Media/Raw/Anime_Downloads/

目标库路径（用户指定或默认）：
/Volumes/Media/Anime/
```

执行：
1. 用 `ls -la` 或 `tree` 列出源目录的一级结构
2. 确认路径可读写
3. 如果目标库路径不存在，`mkdir -p` 创建
4. 告知用户初步发现的内容概况（多少个文件夹/文件）

### Step 2: 遍历所有文件，列出初步文件夹逻辑

递归扫描源目录，按文件类型分类：

```python
扫描工具：find "$SOURCE" -type f | while read f; do ... done

分类：
- 视频文件：.mkv .mp4 .avi .mov .wmv .ts .m2ts
- 字幕文件：.ass .srt .ssa .sub .idx
- 音频文件：.flac .mka .aac .mp3
- 封面/图片：.jpg .jpeg .png .webp
- 其他忽略：.txt .nfo .torrent .sfv
```

输出一个初步的结构清单，格式：

```
源目录：/Volumes/Media/Raw/Anime_Downloads/
├── [SubGroup] Series_Name_01-26  (文件夹, 21.3GB)
│   ├── [SubGroup] Series_Name_Ep01.mkv
│   ├── [SubGroup] Series_Name_Ep01.ass
│   ├── ... (26集 + 字幕)
│   └── [SubGroup] Series_Name_SP.mkv
├── Movie_2024.mkv  (文件, 8.7GB)
├── [Group] Concert_Live_2023/  (文件夹, 12.1GB)
│   ├── CD1/
│   ├── CD2/
│   └── ...
└── OVA_Title (2005).mkv  (文件, 1.2GB)
```

**展示给用户确认后再进入下一步。**

### Step 3: 分析并提取关键作品名称，建立 bangumi_ids.csv 数据库

从 Step 2 的结构清单中，逐项分析出**作品名称**和**内容类型**：

**名称提取策略**（按优先级）：
1. 文件夹名中去除发布组标记 `[...]`、年份 `(YYYY)`、集数范围等后缀
2. 文件名中去除发布组标记、编码信息、分辨率、集数
3. 如果存在中文名称（文件名/子文件夹名中有汉字），优先保留
4. 将提取出的名称作为搜索关键词

**类型判断策略**：
| 特征 | 推断类型 |
|------|---------|
| 有明确剧集编号 01-26、多个视频文件（>3 集） | `tv` |
| 单个视频文件，命名不含集数，文件名含 Movie/Film | `movie` |
| 命名含 Live/Concert/ライブ/演唱 | `concert` |
| 命名含 OVA/OAD/SP/Special/特典 | `ova` / `special` |

**建立 CSV：**
```python
# 创建 bangumi_ids.csv（如果不存在）
import csv
with open('<target_library>/bangumi_ids.csv', 'w', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['jp_name','cn_name','en_name','year','type','folder_name','bangumi_id','status'])
    
# 将每个识别出的作品写入一行（初始 status=new）
for item in discovered_items:
    w.writerow([item['jp_name'], '', '', item['year'], item['type'], item['folder_name'], '', 'new'])
```

**展示 CSV 给用户预览和确认。**

### Step 4: 使用 Bangumi.tv 搜索并匹配 Bangumi ID

逐行处理 CSV 中 `bangumi_id` 为空且 `status=new` 的条目。

**API 调用端点：**

```bash
# 搜索（建议先按类型精搜，失败后再搜全类型）
# type=2: 动漫, type=6: 演唱会/演出

# 精搜
curl -s "https://api.bgm.tv/search/subject/$(python3 -c 'import urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$KEYWORD")?type=2"

# 全类型搜索（精搜无结果时）
curl -s "https://api.bgm.tv/search/subject/$(python3 -c 'import urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$KEYWORD")"
```

**搜索词优先级（按权威顺序）：**

```
第一优先：日文名（罗马音）  例：Cowboy Bebop, Shingeki no Kyojin
第二优先：日文名（假名/汉字） 例：カウボーイビバップ, 進撃の巨人
第三优先：英文名              例：Attack on Titan
第四优先：中文名（仅作参考）   例：进击的巨人
```

⚠️ **中文名可能存在翻译歧义**（如「星际牛仔」vs「Cowboy Bebop」vs「カウボーイビバップ」是同一个作品），
因此优先以日文罗马音搜索。如果文件夹名提取出的关键词是中文，先尝试翻译成日文/英文再搜。

**匹配流程：**

```
输入：文件夹提取名 + 类型 + 年份（若有）
  │
  ├─ 1. 用日文罗马音搜索（最优先）
  │    ├─ 有结果 → 进入「交叉验证」
  │    └─ 无结果 → 用日文汉字/假名搜索
  │
  ├─ 2. 用英文名搜索（第二优先）
  │    ├─ 有结果 → 进入「交叉验证」
  │    └─ 无结果 → 用中文名搜索
  │
  └─ 3. 所有搜索都无结果 → 转到 Step 5（用户手动介入）

  ┌─────────────────────────────────────┐
  │       交叉验证（关键步骤）            │
  │                                     │
  │ 获取到 Bangumi 条目详情后，提取：    │
  │   jp_name = data['name']            │
  │   cn_name = data.get('name_cn','')  │
  │   en_name = 从别名/官方英文名获取    │
  │   year    = data.get('date','')[:4]  │
  │                                     │
  │ 对比 <folder_name>（源文件夹名）与    │
  │ jp_name / en_name / cn_name 三者     │
  │                                     │
  │  ├─ 至少一项高度匹配（子串包含）       │
  │  │   └─ ✓ 通过，写入 CSV             │
  │  │                                    │
  │  ├─ 年份匹配但名称偏差大               │
  │  │   └─ 用不同语言关键词重新搜索       │
  │  │                                    │
  │  └─ 三者都与 folder_name 不匹配       │
  │      └─ 转到 Step 5（用户手动介入）    │
  └─────────────────────────────────────┘
```

**演唱会/多场次年份精准匹配（重要）：**

对于 `concert` 类型，同一艺人在**不同年份**可能有不同场次的演唱会条目，
如「Aimer 2023 Live」vs「Aimer 2024 Live」。Bangumi 上每个年份有独立条目。

```
源文件夹名：Aimer_2023_Live_in_Budokan
提取名：Aimer
年份：2023

搜索：Aimer → 多个结果
  ├─ [ID:123] Aimer Live at Budokan (2024)
  └─ [ID:456] Aimer Live in Budokan (2023)  ← 精确匹配年份
                                              ↓
使用 /v0/subjects/{id} 确认 date 字段与文件夹名中的年份一致
```

规则：
- 从文件夹名中提取 `(YYYY)` 或 `_YYYY_` 作为**目标年份**
- 匹配时优先过滤 Bangumi 结果的 `date` 字段与目标年份一致
- 如果找到 year 精确匹配的条目且名称相关 → 自动确认
- 如果年份不匹配但有其他相关结果 → 展示所有候选，让用户选择
- 如果文件夹名中**没有**年份信息 → 用名称匹配，但写入 CSV 时标注 year 为空

**多季同名作品处理：**

对于多季同名（如「Fate/stay night」不同线、「進撃の巨人」不同季）：
```
源文件名：Shingeki_no_Kyojin_S3
提取：Shingeki no Kyojin（但不确定哪一季）
Bangumi 搜索：
  1. [ID:456] 進撃の巨人 Season 3 (2018) — 第三季
  2. [ID:257] 進撃の巨人 Season 2 (2017) — 第二季
  3. [ID:991] 進撃の巨人 Season 3 Part 2 (2019) — 第三季后半

判断逻辑：
  ├─ 文件夹名前缀匹配（S3 / Season 3 / 第三季）→ 对应第 1 个
  ├─ 有年份（2018）→ 对应第 1 个
  └─ 无法判断 → 转到 Step 5 用户介入
```

**获取条目详情：**

```bash
curl -s "https://api.bgm.tv/v0/subjects/$BANGUMI_ID" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(f'ID: {d[\"id\"]}')
print(f'Name: {d[\"name\"]}')
print(f'NameCN: {d.get(\"name_cn\",\"\")}')
print(f'Type: {d[\"type\"]}')
print(f'Date: {d.get(\"date\",\"\")}')
print(f'Summary: {d.get(\"summary\",\"\")[:200]}...')
"
```

**类型编号映射：**
| type | 含义 |
|------|------|
| 1 | Book |
| 2 | Anime（TV 动画/OVA/电影） |
| 3 | Music |
| 4 | Game |
| 6 | Real（演唱会/真人演出） |

**限流规则：**
- 每次请求间隔 ≥ 0.15 秒
- User-Agent 必须设置（`Mozilla/5.0` 或项目标识）
- 如果返回 429，等待 5 秒后重试

**更新 CSV：**
匹配成功后，将 `bangumi_id`、`cn_name`、`jp_name`、`year` 写回 CSV。

### Step 5: 置信度低时用户手动介入

当以下情况发生时，**暂停自动流程，向用户展示信息请求介入**：

| 场景 | 展示内容 |
|------|---------|
| Bangumi 搜索无结果 | 作品名、推断类型、源文件夹/文件名 |
| 搜索 top 1 名称偏差大 | 作品名、top 1 结果（name + name_cn + year）、偏差说明 |
| **交叉验证失败**（jp_name / en_name / cn_name 三者都与文件夹名不匹配） | 文件夹名、Bangumi 条目的 jp_name、en_name、cn_name、差异分析 |
| 多季同名难以判断 | 作品名、所有候选结果（含 year/jp_name/cn_name） |
| 演唱会年份不匹配 | 作品名、文件夹中的年份、Bangumi 结果的年份 |
| 类型存疑（不确定是 TV 还是 OVA） | 作品名、文件清单、候选类型分析 |

**用户介入交互模板：**

```
━━━ 需要你帮忙确认 ━━━
作品来源：[源文件夹/文件名]
提取名称：「XXX」
推断类型：tv（含 13 集视频）
━━━━━━━━━━━━━━━━━━

【自动匹配结果】
Bangumi 条目标题：
  jp_name:   進撃の巨人 (Shingeki no Kyojin)
  en_name:   Attack on Titan
  cn_name:   进击的巨人
  年份:      2013
  Bangumi ID: 12345

【交叉验证】
文件夹名「Shingeki_no_Kyojin_S3」与 jp_name「進撃の巨人」→ 部分匹配
年份「2013」→ 文件夹无年份信息，无法确认
检测到文件名含「S3」，可能为第三季而非第一季

请选择：
  a) 使用当前结果 — 進撃の巨人 (2013) [ID:12345]
  b) 搜索第三季 — 進撃の巨人 Season 3 [尝试搜索]
  c) 手动输入 Bangumi ID
  d) 跳过此条目
━━━━━━━━━━━━━━━━━━
```

**演唱会/多场次年份有冲突时的交互模板：**

```
━━━ 演唱会年份需要确认 ━━━
作品来源：[Live_Aimer_2023_Budokan]
提取名称：Aimer
推断类型：concert
文件夹年份：2023
━━━━━━━━━━━━━━━━━━

Bangumi 搜索结果：
  1. [ID:123] Aimer Live at Budokan (2024) — date=2024-04-15
  2. [ID:456] Aimer Live in Budokan (2023) — date=2023-09-10  ← 年份匹配

提示：结果 2 的年份 (2023) 与文件夹年份一致，是否确认？
  a) 确认使用结果 2 — Aimer Live in Budokan (2023)
  b) 使用结果 1 — Aimer Live at Budokan (2024)
  c) 手动输入 Bangumi ID
  d) 跳过此条目
━━━━━━━━━━━━━━━━━━
```

在 CSV 中将用户确认的条目 `status` 改为 `confirmed`。

### Step 6: 建立 Jellyfin 兼容文件夹名，分类转移和重命名

**⚠️ 安全第一原则：**
- 使用完整的绝对路径，并用双引号包裹，防止 Shell 转义空格/特殊字符
- 避免使用正则表达式脚本（`sed`、`rename` 等）处理文件名
- 逐个使用 `cp` / `mv` 命令操作，每步验证
- 先 **复制** 到目标结构，保留原始文件直到确认无误

**标准名称转换规则（使用 jp_name 罗马音/英文，不用中文译名）：**

| 原始 | 标准化后 |
|------|---------|
| `[SubsGroup] カウボーイビバップ [01][1080p][x264_flac].mkv` | `Cowboy Bebop S01E01.mkv` |
| `[Group] 君の名は。[1080p].mkv` | `Your Name (2016).mkv` |
| `[Group] Aimer_2023_Live_D1.mkv` | `Aimer Live 2023 (2023) - Disc 1.mkv` |

**操作步骤（逐项执行，每项确认）：**

```bash
# 1. 创建目标目录
mkdir -p "/target_library/Anime Title (2006)/Season 01"

# 2. 复制视频文件（用 cp，不用 mv，保留原始）
cp "/source/[SubsGroup] Anime Title [01][1080p][x264_flac].mkv" \
   "/target_library/Anime Title (2006)/Season 01/Anime Title S01E01.mkv"

# 3. 验证目标文件存在且大小匹配
ls -l "/target_library/Anime Title (2006)/Season 01/Anime Title S01E01.mkv"

# 4. 源文件确认无误后，用户确认删除或保留
```

**文件类型对应处理：**
| 视频格式 | 目标格式 | 容器 |
|---------|---------|------|
| .mkv | .mkv | 直接复制 |
| .mp4 | .mp4 / .mkv | 直接复制 |
| .avi | .mkv | 可转封装，直接复制也可 |
| .ts / .m2ts | .mkv | 建议转封装 |

**多盘/多 CD 处理：**
```
原始：Concert_Live_2023/
├── CD1/01.mkv
├── CD1/02.mkv
├── CD2/01.mkv
└── CD2/02.mkv

目标：Concert Live (2023)/
├── Concert Live (2023) - Disc 1.mkv   # CD1 合并为单文件（或保持多文件）
├── Concert Live (2023) - Disc 2.mkv
└── Concert Live (2023) - Disc 1.nfo
```

**特殊/特典/SP 处理：**
```
原始：Series_Name_SP.mkv
目标：Series Name (2006)/Specials/Series Name S00E01.mkv
```

### Step 7: 字幕文件同步处理

扫描每个源文件夹/文件旁边的字幕文件：

```bash
# 在同一目录下查找与视频文件同名的字幕
find "/source/Series_Folder/" -type f \( -name "*.ass" -o -name "*.srt" \) | while read sub; do
    echo "发现字幕: $sub"
done
```

**字幕匹配规则：**
1. 如果字幕名与视频名相同（仅扩展名不同），直接对应
2. 如果字幕名含章节标记（如 `01.chn.ass`），对应到同章节视频
3. 如果是多语言字幕（`.chs.ass`, `.eng.srt`），保持语言后缀
4. 没有对应视频的字幕 → 暂时不处理，记录到元数据中标注

**字幕复制：**
```bash
cp "/source/[SubsGroup] Anime Title [01][1080p][x264_flac].ass" \
   "/target_library/Anime Title (2006)/Season 01/Anime Title S01E01.ass"
```

**字幕命名规范（Jellyfin 兼容）：**
| 格式 | 说明 |
|------|------|
| `Anime Title S01E01.ass` | 默认字幕（Jellyfin 自动选择） |
| `Anime Title S01E01.chi.ass` | 中文（`chi` / `chs` / `zho`） |
| `Anime Title S01E01.eng.ass` | 英文 |
| `Anime Title S01E01.chi.default.ass` | 默认中文 |
| `Anime Title S01E01.chi.forced.ass` | 强制中文（如双语字幕） |

### Step 8: 建立元数据文件（NFO）

每个作品（系列/电影/演唱会）在各自根目录下生成 NFO 文件。

**NFO 格式（Jellyfin 兼容的 XML）：**

```xml
<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<movie>     <!-- tvshow 对应 TV 系列，movie 对应电影 -->
  <title>Anime Title</title>
  <originaltitle>アニメタイトル</originaltitle>
  <sorttitle>Anime Title</sorttitle>
  <year>2006</year>
  <premiered>2006-10-01</premiered>
  <enddate>2007-03-25</enddate>
  <plot>Anime summary from Bangumi...</plot>
  <outline>Short description...</outline>
  <genre>Action</genre>
  <genre>Sci-Fi</genre>
  <tag>bangumi</tag>
  <uniqueid type="bangumi" default="true">12345</uniqueid>
  <uniqueid type="imdb">tt0123456</uniqueid>
  <episodeguide/>
</movie>
```

**TV 系列根目录 NFO（Jellyfin 的 tvshow.nfo 格式）：**

```xml
<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<tvshow>
  <title>Anime Title</title>
  <originaltitle>アニメタイトル</originaltitle>
  <sorttitle>Anime Title</sorttitle>
  <year>2006</year>
  <premiered>2006-10-01</premiered>
  <enddate>2007-03-25</enddate>
  <plot>...</plot>
  <genre>Action</genre>
  <genre>Sci-Fi</genre>
  <tag>bangumi</tag>
  <uniqueid type="bangumi" default="true">12345</uniqueid>
  <uniqueid type="imdb">tt0123456</uniqueid>
</tvshow>
```

**生成方式：**
- 使用 `scripts/generate_nfo.py`（已有），调用 Bangumi API 获取详情后生成
- TV 系列使用 `<tvshow>` / `<episodedetails>` 格式
- 电影使用 `<movie>` 格式
- 演唱会使用 `<movie>` 格式（Jellyfin 无专门演唱会类型）

```bash
# 为所有作品生成 NFO
python3 scripts/generate_nfo.py --library "/target_library/"

# 为指定系列生成 NFO（单条更新时）
python3 scripts/generate_nfo.py --series "Anime Title"
```

**NFO 文件放置位置：**
```
Anime Title (2006)/
├── tvshow.nfo                    # 系列元数据（根目录）
├── Season 01/
│   ├── Anime Title S01E01.mkv
│   ├── Anime Title S01E01.nfo    # 单集元数据（可选）
│   └── ...
├── Season 02/
├── Specials/
└── Extras/

Movie Title (2001)/
├── Movie Title (2001).nfo        # 电影元数据（文件名与视频一致）
└── Movie Title (2001).mkv
```

NFO 文件命名规则：
- TV 系列根目录：`tvshow.nfo`（Jellyfin 规范）
- 剧集单集：`同视频文件名.nfo`
- 电影：`同视频文件名.nfo`

---

## 四、会话状态记录文件

每次工作结束后，在 `<target_library>/` 下生成 `.hermes_session.json`，
记录当前进度，方便后续 session 接管：

```json
{
  "session_id": "2026-05-25-anime-scan",
  "source_path": "/Volumes/Media/Raw/Anime_Downloads/",
  "target_path": "/Volumes/Media/Anime/",
  "last_step": 3,
  "status": "in_progress",
  "items_total": 12,
  "items_matched": 8,
  "items_pending_user": 2,
  "items_pending_rename": 2,
  "updated_at": "2026-05-25T14:30:00+08:00"
}
```

此文件供后续 session 的 agent 读取，自动判断工作进度和下一步操作。

---

## 五、安全规范

| 规则 | 说明 |
|------|------|
| 先复制后删除 | 所有文件操作先用 `cp` 到目标位置，确认无误后再考虑是否删除源文件 |
| 逐个操作 | 每次只处理一个文件，不使用批处理脚本，避免误操作 |
| 完整路径 + 引号 | 所有路径参数使用绝对路径 + 双引号包裹 |
| cp 验证 | 复制后对比文件大小 `ls -l`，可选校验 `md5sum` |
| 删除确认 | 每次删除前展示删除清单，用户确认后才执行 |
| API 限流 | Bangumi API 间隔 ≥ 0.15s，429 时等待 5s 重试 |
| CSV 备份 | 修改 `bangumi_ids.csv` 前自动创建 `.bak` 备份 |
| 类型标注 | 每次写入 CSV 的 `type` 和 `status` 必须准确，方便后续筛选 |

---

## 六、验证清单

完成所有 8 步后，执行以下验证：

```python
def verify_library(target_path):
    """验证媒体库完整性"""
    import csv, os, re
    
    # 1. CSV 完整性
    csv_path = os.path.join(target_path, 'bangumi_ids.csv')
    with open(csv_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) > 0, 'CSV 为空'
    for r in rows:
        assert r['bangumi_id'], f'缺少 Bangumi ID: {r["folder_name"]}'
    
    # 2. 文件夹规范性
    for r in rows:
        folder = os.path.join(target_path, r['folder_name'])
        assert os.path.isdir(folder), f'文件夹不存在: {folder}'
        # 检查 NFO
        if r['type'] == 'tv':
            assert os.path.isfile(f'{folder}/tvshow.nfo'), f'缺少 tvshow.nfo: {folder}'
        else:
            assert any(f.endswith('.nfo') for f in os.listdir(folder)), f'缺少 NFO: {folder}'
    
    print(f'✓ 验证通过: {len(rows)} 个条目')
```

---

## 七、相关链接

- Bangumi API: https://api.bgm.tv/
- Bangumi Jellyfin 插件：读取 `uniqueid type="bangumi"` 匹配元数据
- Jellyfin NFO 规范：https://jellyfin.org/docs/general/server/media/movies/
- 本仓库脚本：`scripts/generate_nfo.py` — NFO 元数据生成器
