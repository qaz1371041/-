"""
scraper.py - 第三方源抓取模块 (最终定稿版：纯净、稳定、不再改动)
"""
import re
import requests
import configparser
import logging
from typing import Dict, List, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# 🚀 全局复用 Session，减少 TCP 握手开销
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 VLC/3.0"})

def load_demo_channels(demo_file: str = "demo.txt") -> Optional[Dict[str, str]]:
    channels: Dict[str, str] = {}
    current_genre = "未分类"
    try:
        with open(demo_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.endswith(",#genre#"):
                    current_genre = line.replace(",#genre#", "").strip()
                else:
                    channels[line] = current_genre
    except FileNotFoundError:
        return None
    logger.info(f"📋 demo.txt 加载完成，共 {len(channels)} 个指定频道")
    return channels

def load_alias(alias_file: str = "alias.txt") -> Tuple[Dict[str, str], List[Tuple[re.Pattern, str]]]:
    exact_map: Dict[str, str] = {}
    regex_list: List[Tuple[re.Pattern, str]] = []
    try:
        with open(alias_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                parts = line.split(",")
                if len(parts) < 2: continue
                standard = parts[0].strip()
                aliases = [a.strip() for a in parts[1:] if a.strip()]
                exact_map[standard] = standard
                for alias in aliases:
                    if alias.startswith("re:"):
                        try:
                            compiled = re.compile(alias[3:], re.IGNORECASE)
                            regex_list.append((compiled, standard))
                        except re.error: pass
                    else:
                        exact_map[alias] = standard
    except FileNotFoundError: pass
    logger.info(f"📋 alias.txt 加载完成: {len(exact_map)} 个精确映射, {len(regex_list)} 个正则规则")
    return exact_map, regex_list

def match_channel_name(raw_name: str, exact_map: Dict[str, str], regex_list: List[Tuple[re.Pattern, str]]) -> Tuple[str, bool]:
    if raw_name in exact_map: return exact_map[raw_name], True
    cleaned = re.sub(r'\s*(HD|FHD|UHD|4K|8K|高清|标清|超清|蓝光|HEVC|H265|H264|50FPS|60FPS|25FPS|IPV6|IPv6|ipv6|ᴴᴰ|「.*?」|\[.*?\]|\(.*?\))\s*', '', raw_name.strip(), flags=re.IGNORECASE).strip()
    if cleaned in exact_map: return exact_map[cleaned], True
    for pattern, standard in regex_list:
        if pattern.fullmatch(raw_name) or pattern.fullmatch(cleaned): return standard, True
    for pattern, standard in regex_list:
        if pattern.search(raw_name) or pattern.search(cleaned): return standard, True
    return raw_name, False

def load_sources(config_file: str = "config/config.ini") -> Tuple[List[str], int]:
    """读取配置，返回: (源列表, 超时时间)"""
    config = configparser.ConfigParser()
    config.read(config_file, encoding="utf-8")
    
    sources_raw = config.get("scraper", "sources", fallback="")
    timeout = config.getint("scraper", "timeout", fallback=15)
    
    # configparser 会自动忽略多行值中以 # 或 ; 开头的注释行
    # 这里只需要过滤掉空行即可
    sources = [s.strip() for s in sources_raw.strip().split("\n") if s.strip()]
            
    return sources, timeout

def fetch_source(url: str, timeout: int = 15) -> Tuple[str, str, bool]:
    """使用全局 Session 发起请求"""
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return url, resp.text, True
    except Exception as e:
        return url, str(e), False

def parse_source(content: str, url: str = "") -> List[Dict[str, str]]:
    """解析源数据 (保持返回字典列表，确保与 speed_test.py 完美兼容)"""
    channels: List[Dict[str, str]] = []
    lines = content.strip().split("\n")
    if not lines or not lines[0]: return channels
    
    is_txt = not content.strip().startswith("#EXTM3U") and "," in lines[0]
    if is_txt:
        current_group = "未分类"
        for line in lines:
            line = line.strip()
            if not line: continue
            if line.endswith(",#genre#"):
                current_group = line.replace(",#genre#", "").strip()
                continue
            parts = line.split(",", 1)
            if len(parts) == 2:
                name, link = parts[0].strip(), parts[1].strip()
                if name and link and link.startswith(("http", "rtsp", "rtmp")):
                    channels.append({"name": name, "url": link, "group": current_group})
    else:
        for i in range(len(lines)):
            line = lines[i].strip()
            if line.startswith("#EXTINF"):
                name_match = re.search(r",(.+?)$", line)
                if not name_match: continue
                name = name_match.group(1).strip()
                group_match = re.search(r'group-title="([^"]*)"', line)
                # ✅ 微调：确保 group 永远不为空字符串，至少是 "未分类"
                group = group_match.group(1).strip() if group_match and group_match.group(1).strip() else "未分类"
                link = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if name and link and not link.startswith("#"):
                    channels.append({"name": name, "url": link, "group": group})
    return channels

def scrape_all(demo_channels: Optional[Dict[str, str]] = None, exact_map: Optional[Dict[str, str]] = None, regex_list: Optional[List[Tuple[re.Pattern, str]]] = None) -> List[Dict[str, Any]]:
    if exact_map is None: exact_map, regex_list = load_alias()
    if regex_list is None: regex_list = []
    
    sources, timeout = load_sources()
    
    # 抓取源的并发数固定为 10，不需要配置化，避免把 config.ini 搞得太复杂
    max_workers = 10 
    logger.info(f"\n🌐 开始抓取 {len(sources)} 个第三方源 (并发数: {max_workers})...")
    
    all_raw_channels: List[Dict[str, str]] = []
    dead_sources: List[str] = []
    
    if not sources:
        logger.warning("⚠️ config.ini 中未配置任何 sources，跳过抓取。")
        return []

    with ThreadPoolExecutor(max_workers=min(max_workers, len(sources))) as executor:
        futures = {executor.submit(fetch_source, url, timeout): url for url in sources}
        for future in as_completed(futures):
            url, content, success = future.result()
            if success and content:
                parsed = parse_source(content, url)
                logger.info(f"  ✅ {url} -> {len(parsed)} 个频道")
                all_raw_channels.extend(parsed)
            else:
                logger.warning(f"  ❌ [失效源] {url} ({content})")
                dead_sources.append(url)

    if dead_sources:
        logger.warning(f"\n⚠️ 发现 {len(dead_sources)} 个失效第三方源，建议从 config.ini 中移除：")
        for ds in dead_sources:
            logger.warning(f"   - {ds}")

    logger.info(f"\n📊 共抓取到 {len(all_raw_channels)} 条原始记录")

    matched: List[Dict[str, Any]] = []
    seen_urls = set()
    for ch in all_raw_channels:
        std_name, is_matched = match_channel_name(ch["name"], exact_map, regex_list)
        if demo_channels is None or std_name in demo_channels:
            if ch["url"] not in seen_urls:
                seen_urls.add(ch["url"])
                # ✅ 确保 category 永远有值
                category = demo_channels[std_name] if demo_channels and std_name in demo_channels else ch.get("group", "未分类")
                if not category:
                    category = "未分类"
                    
                matched.append({
                    "name": std_name,
                    "url": ch["url"],
                    "original_name": ch["name"],
                    "category": category
                })
                
    logger.info(f"✅ 匹配到 {len(matched)} 条指定频道记录")
    return matched
