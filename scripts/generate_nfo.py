#!/usr/bin/env python3
"""
Jellyfin NFO Generator v3.0
从 Bangumi API 抓取元数据并生成 Jellyfin 兼容的 NFO 文件。
使用 bangumi_ids.csv 作为元数据缓存，避免重复抓取。

用法:
  python3 generate_nfo.py                                              # 全量模式：默认库路径
  python3 generate_nfo.py --library "/Volumes/Media/Anime"             # 指定库路径
  python3 generate_nfo.py --refresh                                    # 强制刷新：重新抓取所有缓存
  python3 generate_nfo.py --series "Cowboy Bebop"                      # 指定系列
  python3 generate_nfo.py --library "/path" --series "君の名は。"       # 组合使用
"""
import csv, json, os, sys, time, re, urllib.request, urllib.parse, xml.sax.saxutils
from datetime import datetime

# ======== 默认配置 ========
BASE = '/server/Media/Anime'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; NFOGenerator/3.0; +https://github.com/PegionFish/jellyfin_animanagement_skill)'}
CACHE_TTL = 86400 * 7  # 缓存有效期 7 天
API_DELAY = 0.5        # API 请求间隔（秒）

# ======== 统计 ========
stats = {'series': 0, 'movies': 0, 'episodes': 0, 'concerts': 0, 'skipped': 0, 'errors': 0, 'cache_hits': 0, 'api_calls': 0}

# ======== 工具函数 ========
def log(msg, level='INFO'):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] [{level}] {msg}")

def esc(text):
    return xml.sax.saxutils.escape(str(text or ''))

def now_ts():
    return int(time.time())

# ======== 缓存管理 ========
def load_cache(cache_path):
    """加载元数据缓存"""
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            log("缓存文件损坏，重新创建", 'WARN')
    return {}

def save_cache(cache, cache_path):
    """保存元数据缓存"""
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    log(f"缓存已保存: {len(cache)} 条", 'CACHE')

def bgm_api(path, bid, cache, force_refresh=False):
    """从 Bangumi API 获取数据，优先使用缓存"""
    cache_key = f"subject_{bid}"
    now = now_ts()

    # 检查缓存
    if not force_refresh and cache_key in cache:
        entry = cache[cache_key]
        if now - entry.get('ts', 0) < CACHE_TTL:
            stats['cache_hits'] += 1
            return entry['data']

    # 抓取 API
    url = f'https://api.bgm.tv{path}'
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode('utf-8'))

        # 保存到缓存
        cache[cache_key] = {'ts': now, 'data': data}
        stats['api_calls'] += 1
        time.sleep(API_DELAY)
        return data
    except Exception as e:
        stats['errors'] += 1
        log(f"  [{bid}] API 错误: {e}", 'ERR')
        return None

def bgm_episodes_api(bid, cache, force_refresh=False):
    """获取剧集列表"""
    cache_key = f"episodes_{bid}"
    now = now_ts()

    if not force_refresh and cache_key in cache:
        entry = cache[cache_key]
        if now - entry.get('ts', 0) < CACHE_TTL:
            return entry['data']

    try:
        url = f'https://api.bgm.tv/v0/episodes?subject_id={bid}&limit=500'
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode('utf-8'))
        cache[cache_key] = {'ts': now, 'data': data}
        time.sleep(API_DELAY)
        return data
    except Exception as e:
        log(f"  [{bid}] 剧集列表错误: {e}", 'ERR')
        return None

# ======== NFO 生成 ========
def write_nfo(path, root_tag, fields, uniqueid_type, uniqueid_value, extra_tags=None):
    """通用 NFO 写入器，统一 uniqueid 和 tag 输出"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ['<?xml version="1.0" encoding="utf-8" standalone="yes"?>', f'<{root_tag}>']
    for k, v in fields:
        if v:
            lines.append(f'  <{k}>{esc(v)}</{k}>')
    # uniqueid
    if uniqueid_value:
        lines.append(f'  <uniqueid type="{uniqueid_type}" default="true">{esc(uniqueid_value)}</uniqueid>')
    # extra tags
    if extra_tags:
        for tag in extra_tags:
            lines.append(f'  <tag>{esc(tag)}</tag>')
    lines.append(f'</{root_tag}>')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

def process_series(row, cache, force_refresh, base):
    """处理一个 TV 系列"""
    name = row['series_name']
    folder = row['actual_folder']
    bid = row['bangumi_id']
    folder_path = f'{base}/{folder}'

    log(f"[{bid}] {name} — 抓取系列元数据...", 'API')
    data = bgm_api(f'/v0/subjects/{bid}', bid, cache, force_refresh)
    if not data:
        stats['errors'] += 1
        return

    title = data.get('name_cn') or data.get('name', '')
    orig_title = data.get('name', '')
    plot = (data.get('summary', '') or '')[:800]
    premiered = data.get('date', '')
    year = premiered[:4] if premiered else ''
    genres = [t['name'] for t in data.get('tags', [])[:5]]

    # 写入 tvshow.nfo
    tvshow_fields = [
        ('title', title),
        ('originaltitle', orig_title),
        ('sorttitle', title),
        ('plot', plot),
        ('premiered', premiered),
        ('year', year),
    ]
    # 提取 genre 标签
    for g in genres:
        tvshow_fields.append(('genre', g))

    tvshow_path = f'{folder_path}/tvshow.nfo'
    if not os.path.exists(tvshow_path) or force_refresh:
        write_nfo(tvshow_path, 'tvshow', tvshow_fields, 'bangumi', bid, extra_tags=['bangumi'])
        log(f"  → {folder}/tvshow.nfo", 'NFO')
    else:
        stats['skipped'] += 1

    stats['series'] += 1

    # 获取剧集列表
    log(f"  [{bid}] {name} — 抓取剧集列表...", 'API')
    eps_data = bgm_episodes_api(bid, cache, force_refresh)
    if not eps_data:
        return

    episodes = {ep.get('ep'): ep for ep in eps_data.get('data', []) if ep.get('type', 0) == 0}

    # 遍历 Season 目录
    season_dirs = sorted([d for d in os.listdir(folder_path)
                         if os.path.isdir(f'{folder_path}/{d}') and d.startswith('Season ')])

    for snum, sdir in enumerate(season_dirs, 1):
        s_path = f'{folder_path}/{sdir}'

        # 写入 season.nfo
        seas_path = f'{s_path}/season.nfo'
        if not os.path.exists(seas_path) or force_refresh:
            write_nfo(seas_path, 'season', [
                ('title', f'Season {snum}'),
                ('seasonnumber', str(snum)),
            ], uniqueid_type=None, uniqueid_value=None)

        # 遍历视频文件
        video_files = sorted([f for f in os.listdir(s_path)
                            if f.endswith(('.mkv', '.mp4', '.avi')) and not f.startswith('.')])

        for vf in video_files:
            m = re.search(r'S\d+E(\d+)', vf)
            if not m:
                continue
            ep_num = int(m.group(1))
            ep_data = episodes.get(ep_num)

            if not ep_data:
                stats['skipped'] += 1
                continue

            nfo_path = f'{s_path}/{os.path.splitext(vf)[0]}.nfo'
            if os.path.exists(nfo_path) and not force_refresh:
                stats['skipped'] += 1
                continue

            ep_title = ep_data.get('name_cn') or ep_data.get('name', f'EP{ep_num}')
            ep_orig = ep_data.get('name', '')
            ep_plot = (ep_data.get('desc', '') or '')[:500]
            ep_aired = ep_data.get('airdate', '')
            ep_dur = ep_data.get('duration', '')

            write_nfo(nfo_path, 'episodedetails', [
                ('title', ep_title),
                ('originaltitle', ep_orig),
                ('showtitle', title),
                ('season', str(snum)),
                ('episode', str(ep_num)),
                ('plot', ep_plot),
                ('aired', ep_aired),
                ('runtime', ep_dur),
            ], 'bangumi', str(ep_data.get('id', '')), extra_tags=['bangumi'])

            stats['episodes'] += 1
            log(f"  → {sdir}/{os.path.basename(nfo_path)} [{ep_title}]", 'NFO')

def process_movie_or_concert(row, cache, force_refresh, base):
    """处理一部电影或演唱会（通用逻辑）"""
    name = row['series_name']
    folder = row['actual_folder']
    bid = row['bangumi_id']
    content_type = row.get('content_type', 'movie')  # movie or concert
    folder_path = f'{base}/{folder}'

    log(f"[{bid}] {name} — 抓取{content_type}元数据...", 'API')
    data = bgm_api(f'/v0/subjects/{bid}', bid, cache, force_refresh)
    if not data:
        stats['errors'] += 1
        return

    title = data.get('name_cn') or data.get('name', '')
    orig_title = data.get('name', '')
    plot = (data.get('summary', '') or '')[:800]
    premiered = data.get('date', '')
    year = premiered[:4] if premiered else ''
    genres = [t['name'] for t in data.get('tags', [])[:5]]

    # 查找已有视频文件
    video_files = [f for f in os.listdir(folder_path)
                  if f.endswith(('.mkv', '.mp4', '.avi')) and not f.startswith('.')]
    if not video_files:
        stats['skipped'] += 1
        return

    video_name = os.path.splitext(video_files[0])[0]
    nfo_path = f'{folder_path}/{video_name}.nfo'

    if os.path.exists(nfo_path) and not force_refresh:
        stats['skipped'] += 1
        return

    movie_fields = [
        ('title', title),
        ('originaltitle', orig_title),
        ('sorttitle', title),
        ('plot', plot),
        ('premiered', premiered),
        ('year', year),
    ]
    for g in genres:
        movie_fields.append(('genre', g))

    write_nfo(nfo_path, 'movie', movie_fields, 'bangumi', bid, extra_tags=['bangumi'])

    if content_type == 'concert':
        stats['concerts'] += 1
    else:
        stats['movies'] += 1
    log(f"  → {folder}/{os.path.basename(nfo_path)} [{title}]", 'NFO')

# ======== 主流程 ========
def main():
    import argparse

    parser = argparse.ArgumentParser(description='Jellyfin NFO Generator from Bangumi v3.0')
    parser.add_argument('--library', type=str, default=BASE,
                        help='Jellyfin 媒体库根路径（默认: %(default)s）')
    parser.add_argument('--refresh', action='store_true', help='强制刷新所有缓存')
    parser.add_argument('--series', type=str, help='仅处理指定的系列名（支持模糊匹配）')
    parser.add_argument('--delay', type=float, default=0.5, help='API 请求间隔（秒）')
    args = parser.parse_args()

    global API_DELAY, BASE
    BASE = args.library
    API_DELAY = args.delay
    CSV_PATH = f'{BASE}/bangumi_ids.csv'
    CACHE_PATH = f'{BASE}/.bangumi_cache.json'

    # Banner
    print("=" * 60)
    print("  Jellyfin NFO Generator v3.0")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  库路径: {BASE}")
    print(f"  缓存: {CACHE_PATH}")
    print(f"  模式: {'强制刷新' if args.refresh else '增量更新'}")
    if args.series:
        print(f"  筛选: {args.series}")
    print("=" * 60)

    # 加载缓存
    log("加载元数据缓存...", 'CACHE')
    cache = load_cache(CACHE_PATH)
    log(f"缓存中 {len(cache)} 条记录", 'CACHE')

    # 读取 CSV（格式：cn_name,jp_name,year,type,folder_name,bangumi_id,status）
    if not os.path.exists(CSV_PATH):
        log(f"CSV 文件不存在: {CSV_PATH}", 'ERR')
        sys.exit(1)

    log("读取 bangumi_ids.csv...", 'INFO')
    entries = []
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bid = row.get('bangumi_id', '').strip()
            if bid and bid.isdigit():
                content_type = row.get('type', '').strip().lower()
                entries.append({
                    'series_name': row.get('cn_name', '').strip() or row.get('jp_name', '').strip(),
                    'year': row.get('year', '').strip(),
                    'folder_name': row.get('folder_name', '').strip(),
                    'bangumi_id': bid,
                    'content_type': content_type if content_type in ('tv', 'movie', 'concert', 'ova', 'special') else 'movie',
                    'status': row.get('status', '').strip(),
                })

    if not entries:
        log("CSV 中没有有效的 bangumi_id 条目", 'WARN')
        return

    # 建立文件夹映射
    folder_map = {}
    for d in os.listdir(BASE):
        full = f'{BASE}/{d}'
        if os.path.isdir(full):
            folder_map[d] = full

    # 匹配实际文件夹
    matched = []
    for row in entries:
        csv_name = row['folder_name']
        for disk_name in folder_map:
            if disk_name.startswith(csv_name):
                row['actual_folder'] = disk_name
                path = folder_map[disk_name]
                has_season = os.path.isdir(f'{path}/Season 01')
                row['_is_tv'] = has_season or row['content_type'] == 'tv'
                matched.append(row)
                break
        else:
            log(f"未找到实际文件夹: {csv_name}", 'WARN')

    # 筛选指定系列
    if args.series:
        kw = args.series.lower()
        matched = [r for r in matched if kw in r['series_name'].lower() or kw in r.get('actual_folder', '').lower()]

    tv = [r for r in matched if r['_is_tv']]
    movies_and_concerts = [r for r in matched if not r['_is_tv']]

    log(f"待处理: TV {len(tv)} 部, 电影/演唱会 {len(movies_and_concerts)} 部", 'INFO')
    print("-" * 60)

    # 处理 TV 系列
    for i, row in enumerate(tv):
        print()
        log(f"[{i+1}/{len(tv)}] 处理 TV: {row['series_name']}", 'PROG')
        process_series(row, cache, args.refresh, BASE)

    # 处理电影/演唱会
    for i, row in enumerate(movies_and_concerts):
        print()
        label = '演唱会' if row['content_type'] == 'concert' else '电影'
        log(f"[{i+1}/{len(movies_and_concerts)}] 处理{label}: {row['series_name']}", 'PROG')
        process_movie_or_concert(row, cache, args.refresh, BASE)

    # 保存缓存
    save_cache(cache, CACHE_PATH)

    # 最终报告
    print()
    print("=" * 60)
    print("  生成报告")
    print("-" * 60)
    print(f"  系列 NFO:    {stats['series']}")
    print(f"  电影 NFO:    {stats['movies']}")
    print(f"  演唱会 NFO:  {stats['concerts']}")
    print(f"  剧集 NFO:    {stats['episodes']}")
    print(f"  跳过(已存在): {stats['skipped']}")
    print(f"  错误:        {stats['errors']}")
    print(f"  API 请求:    {stats['api_calls']}")
    print(f"  缓存命中:    {stats['cache_hits']}")
    print("=" * 60)

if __name__ == '__main__':
    main()
