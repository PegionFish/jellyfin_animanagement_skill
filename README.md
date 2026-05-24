# Jellyfin Anime Management Skill

DeepSeek TUI skill for managing Jellyfin anime media library with Bangumi integration.

## 目录结构

```
jellyfin_animanagement_skill/
├── SKILL.md                    # DeepSeek TUI skill 定义
├── scripts/
│   └── generate_nfo.py         # 从 Bangumi API 生成 Jellyfin NFO 元数据
├── references/                 # 参考文件
├── README.md
└── .gitignore
```

## 功能

- **Bangumi ID 匹配** — 基于文件夹名搜索 Bangumi API，自动匹配条目 ID
- **NFO 元数据生成** — 从 Bangumi 抓取标题、简介、首播日期、标签等，生成 Jellyfin 兼容 NFO
- **文件夹规范化** — 标准化 `Name (Year) [bangumi-XXXXX]` 命名
- **CSV 台账管理** — 维护 `bangumi_ids.csv` 作为媒体库索引

## 使用方式

在 DeepSeek TUI 中加载 skill 后自动生效，或手动调用：

```bash
# 生成 NFO 元数据（全量）
python3 scripts/generate_nfo.py

# 生成 NFO 元数据（指定系列）
python3 scripts/generate_nfo.py --series "Cowboy Bebop"

# 强制刷新缓存
python3 scripts/generate_nfo.py --refresh
```

## 依赖

- Python 3.8+
- Bangumi API（https://api.bgm.tv/）
- 仅需标准库，无第三方依赖

## 部署

1. 将 `SKILL.md` 复制到 `~/.deepseek/skills/anime-media-manager/SKILL.md`
2. 将 `scripts/` 放置在可访问路径
3. 确保 bangumi_ids.csv 位于媒体库根目录 `/server/Media/Anime/`

## 后续开发

此仓库为本地开发版本，同步到 GitHub 后：
```bash
git remote add origin https://github.com/PegionFish/jellyfin_animanagement_skill.git
git push -u origin main
```
