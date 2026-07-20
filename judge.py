import json
import os
from datetime import datetime

# 🛡️ 免死金牌：白名单列表 (包含这些关键字的源，无论存活率多低，都不拉黑)
WHITELIST_KEYWORDS = ["migu", "cctv", "yangshipin", "52top"] 

def judge_sources_and_isolate(source_stats):
    """
    🧮 升级版秋后算账：带白名单、缓刑机制和去重写入
    """
    blacklist_path = "config/blacklist.txt"
    stats_path = "config/source_stats.json"
    
    # 1. 加载历史成绩单（用于判断是否连续拉跨）
    try:
        with open(stats_path, "r", encoding="utf-8") as f:
            history_stats = json.load(f)
    except FileNotFoundError:
        history_stats = {}

    print("\n--- 📊 源质量统计与隔离报告 ---")
    
    for src, stats in source_stats.items():
        if src == "unknown": continue
        
        total = stats["total"]
        alive = stats["alive"]
        rate = (alive / total) * 100 if total > 0 else 0
        
        print(f"  📦 {src[:60]}... | 贡献: {total} | 存活: {alive} | 存活率: {rate:.1f}%")
        
        # 🛑 核心隔离逻辑：
        # 1. 如果贡献的频道太少（< 5个），不具备统计意义，不拉黑。
        if total < 5:
            continue
            
        # 2. 检查是否在白名单中（免死金牌）
        is_whitelisted = any(kw in src.lower() for kw in WHITELIST_KEYWORDS)
        if is_whitelisted and rate < 5.0:
            print(f"    🛡️ [白名单保护] 虽存活率低，但属于受保护源，免除隔离。")
            continue
            
        # 3. 判定为垃圾源（存活率 < 5%）
        if rate < 5.0:
            # 检查历史战绩：如果上一次它也是 < 5%，说明是“惯犯”，直接拉黑！
            # 如果上一次它是好的，这次突然变差，给一次“缓刑”机会（可能是临时维护）
            hist = history_stats.get(src, {})
            hist_rate = (hist.get("alive", 0) / hist.get("total", 1)) * 100
            
            if hist_rate < 5.0:
                # ✅ 修复：先读取现有黑名单，去重后再覆盖写入，防止重复追加
                existing_blacklist = set()
                if os.path.exists(blacklist_path):
                    with open(blacklist_path, "r", encoding="utf-8") as f:
                        existing_blacklist = set(line.strip() for line in f if line.strip())
                
                existing_blacklist.add(src) # 加入新的黑名单
                
                # 覆盖写入（"w" 模式），确保没有重复项
                os.makedirs(os.path.dirname(blacklist_path), exist_ok=True)
                with open(blacklist_path, "w", encoding="utf-8") as f:
                    for item in existing_blacklist:
                        f.write(f"{item}\n")
                        
                print(f"    🚫 [自动隔离] 连续两次存活率极低，已永久拉黑！")
            else:
                print(f"    ⚠️ [黄牌警告] 本次表现极差，给予一次缓刑机会，下次再犯将拉黑。")
                
    # 3. 保存本次成绩单，覆盖历史记录
    os.makedirs(os.path.dirname(stats_path), exist_ok=True)
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(source_stats, f, indent=4)
    print(f"✅ 成绩单已更新至 {stats_path}")
