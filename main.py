"""
main.py - IPTV 自动化系统主入口 (架构优化版：职责分离 + 调用 OutputGenerator)
"""
import os
import sys
import gc
import time
import logging
import traceback
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Any

# 导入你的核心模块
from scraper import load_demo_channels, load_alias, scrape_all
from speed_test import SpeedTestEngine
# ✅ 新增：导入我们优化好的 OutputGenerator
from generator import OutputGenerator

# ==========================================
# ⚙️ 全局配置与日志设置
# ==========================================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEMO_FILE = "demo.txt"
ALIAS_FILE = "alias.txt"
OUTPUT_DIR = "output"
CONFIG_DIR = "config"
CONFIG_INI = os.path.join(CONFIG_DIR, "config.ini")
BLACKLIST_FILE = os.path.join(CONFIG_DIR, "blacklist.txt")

def init_environment():
    """
    🛡️ 自动初始化缺失的配置文件，防止 FileNotFoundError 崩溃
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    if not os.path.exists(CONFIG_INI):
        with open(CONFIG_INI, "w", encoding="utf-8") as f:
            f.write("[scraper]\ntimeout = 15\nmax_workers = 10\nsources =\n\n[speedtest]\nthreads = 20\ntimeout = 6\n")
        logger.warning(f"⚠️ 未找到 {CONFIG_INI}，已自动创建默认模板，请手动填入源地址！")
        
    if not os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
            f.write("# 在此处填写需要拉黑的关键词，每行一个\n")
        logger.info(f"ℹ️ 未找到 {BLACKLIST_FILE}，已自动创建空文件。")

def main():
    # 🛡️ 第一步：初始化环境，防止文件缺失崩溃
    init_environment()
    
    start_time = time.time()
    beijing_tz = timezone(timedelta(hours=8))
    update_time = datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M')

    print("=" * 60)
    print("🚀 IPTV 自动化系统启动 (架构优化版 + 调用 OutputGenerator)")
    print(f"   ⏱️  时间: {update_time} (北京时间)")
    print("=" * 60)

    # Step 1: 加载配置
    logger.info("📋 Step 1: 加载配置")
    raw_demo = load_demo_channels(DEMO_FILE)
    if raw_demo is None:
        logger.error(f"未找到 {DEMO_FILE}，程序退出")
        sys.exit(1)
        
    # 兼容处理：确保 demo_channels 是我们期望的字典格式 {频道名: [分类列表]}
    demo_channels = raw_demo[0] if isinstance(raw_demo, tuple) else raw_demo
    exact_map, regex_list = load_alias(ALIAS_FILE)

    # Step 2: 抓取第三方源
    logger.info("🌐 Step 2: 抓取第三方源 + 别名匹配")
    matched_channels = scrape_all(demo_channels, exact_map, regex_list)
    if not matched_channels:
        logger.error("未匹配到任何指定频道，程序退出")
        sys.exit(1)

    # Step 3: 高并发真实播放测速
    logger.info("⚡ Step 3: 高并发真实播放测速")
    engine = SpeedTestEngine(matched_channels)
    run_result = engine.run()
    
    # 智能兼容：无论 speed_test.py 返回一个值还是两个值，都不会崩溃
    if isinstance(run_result, tuple) and len(run_result) == 2:
        valid_channels, source_stats = run_result
    else:
        valid_channels = run_result if isinstance(run_result, list) else []

    del matched_channels, engine
    gc.collect()

    if not valid_channels:
        logger.error("测速后无有效可播放频道，程序退出")
        sys.exit(1)

    # Step 4: 生成输出文件 (调用统一的 OutputGenerator)
    logger.info("📦 Step 4: 生成输出文件 (调用 OutputGenerator)")
    
    # 实例化生成器，将测速结果和 demo 结构传入
    generator = OutputGenerator(
        tested_channels=valid_channels,
        demo_channels=demo_channels if isinstance(demo_channels, dict) else {},
        output_dir=OUTPUT_DIR,
        update_time=update_time
    )
    
    # 执行生成
    generator.generate_all()

    logger.info(f"🎉 全部任务完成！耗时: {time.time() - start_time:.2f} 秒")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("用户手动中断了程序运行。")
        sys.exit(130)
    except Exception as e:
        logger.critical(f"发生未捕获的严重异常: {e}")
        traceback.print_exc()
        sys.exit(1)
