"""
speed_test.py - 真实播放测试引擎 (全量测速优化版 + 源质量记账)
- 优化探测参数，大幅提升测速吞吐量
- 严格预检 + 动态超时，确保全量测完且不卡死
- 🚀 新增：无感统计每个 source_url 的 total 和 alive，完美衔接 judge.py
- 🛠️ 终极修复：解决 ThreadPoolExecutor 超时后 wait=True 导致的永久卡死问题
- 🛡️ 环境适配：限制 GitHub Actions 下的最大并发数，防止 ffprobe 进程资源耗尽团灭
"""
import re
import json
import subprocess
import configparser
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import requests

class SpeedTestEngine:
    def __init__(self, channels, config_file="config/config.ini"):
        self.channels = channels
        self.results = []
        self.source_stats = {}
        config = configparser.ConfigParser()
        config.read(config_file, encoding="utf-8")
        
        # 🛡️ 核心修复：GitHub Actions 环境下，50线程会导致 ffprobe 进程资源耗尽而静默团灭。
        # 强制将最大并发限制在 20，确保测速稳定执行。
        raw_threads = config.getint("speedtest", "threads", fallback=20)
        self.threads = min(20, raw_threads)
        self.timeout = config.getint("speedtest", "timeout", fallback=8)

    def _is_live_tv_channel(self, name):
        pattern = r'(卫视|CCTV|央视|CGTN|CHC|电视|TV|频道|新闻|财经|体育|科教|戏曲|影视|金鹰|卡酷|哈哈|优漫|嘉佳|炫动)'
        return bool(re.search(pattern, name, re.IGNORECASE))

    def _quick_http_check(self, url):
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            res = requests.get(url, timeout=(2, 3), stream=True, headers=headers)
            if res.status_code != 200: return False
            chunk = next(res.iter_content(chunk_size=512), None)
            res.close()
            return chunk is not None and len(chunk) > 0
        except Exception:
            return False

    def test_channel(self, channel):
        url = channel["url"]
        name = channel.get("name", "Unknown")
        if not self._quick_http_check(url): return None
        
        is_playable, resolution, width, height, bitrate = self._ffprobe_check_playable(url)
        if not is_playable: return None

        if height and 0 < height < 720:
            if self._is_live_tv_channel(name):
                print(f"   🚫 [卫视低画质放弃] {name} {width}x{height}", flush=True)
                return None
            else:
                print(f"   🎬 [影视剧保留] {name} {width}x{height}", flush=True)

        bitrate_mbps = round(bitrate / 1_000_000, 2) if bitrate and bitrate > 0 else 0.0
        return {
            **channel, "status": "alive",
            "resolution": resolution or "unknown",
            "width": width or 0, "height": height or 0,
            "bitrate_mbps": bitrate_mbps,
            "resolution_category": self._classify_resolution(height)
        }

    def _ffprobe_check_playable(self, url):
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", "-show_format",
                "-analyzeduration", "1500000", "-probesize", "2000000", url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            if result.returncode != 0: return False, None, None, None, None
            
            data = json.loads(result.stdout)
            has_video, width, height = False, 0, 0
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    has_video, width, height = True, int(stream.get("width", 0)), int(stream.get("height", 0))
                    break
            if not has_video: return False, None, None, None, None
            
            fmt = data.get("format", {})
            bitrate = int(fmt.get("bit_rate", 0))
            resolution = f"{width}x{height}" if width and height else None
            return True, resolution, width, height, bitrate
        except (subprocess.TimeoutExpired, Exception):
            return False, None, None, None, None

    def _classify_resolution(self, height):
        if not height: return "unknown"
        if height >= 2160: return "4K"
        if height >= 1080: return "1080p"
        if height >= 720: return "720p"
        if height >= 480: return "480p"
        return "SD"

    def run(self):
        total = len(self.channels)
        print(f"\n⚡ 开始全量真实播放测试 (线程:{self.threads}) | 共 {total} 个频道", flush=True)
        if total == 0: return self.results, self.source_stats

        for ch in self.channels:
            src = ch.get("source_url", "unknown")
            if src not in self.source_stats: self.source_stats[src] = {"total": 0, "alive": 0}
            self.source_stats[src]["total"] += 1

        completed = 0
        dynamic_timeout = max(180, min(14400, total // 50 * 60))
        print(f"   ⏱️ 动态全局超时: {dynamic_timeout//60}分{dynamic_timeout%60}秒", flush=True)

        # 🛠️ 终极修复：放弃 with 语句，手动控制 executor 生命周期，防止超时后卡死
        executor = ThreadPoolExecutor(max_workers=self.threads)
        futures = {executor.submit(self.test_channel, ch): ch for ch in self.channels}

        try:
            for f in as_completed(futures, timeout=dynamic_timeout):
                completed += 1
                try:
                    result = f.result(timeout=8)
                    if result:
                        self.results.append(result)
                        src = result.get("source_url", "unknown")
                        if src in self.source_stats: self.source_stats[src]["alive"] += 1
                except Exception: pass
                
                if completed % 50 == 0 or completed == total:
                    print(f"   进度: {completed}/{total} | 可播放: {len(self.results)}", flush=True)
        except TimeoutError:
            print(f"   ⚠️ 已达动态超时上限，已完成 {completed}/{total}，正在强制取消剩余任务...", flush=True)
            for f in futures:
                if not f.done(): f.cancel()
        finally:
            # 🚀 关键逃生舱：wait=False 确保主线程不会被卡死的子线程拖累
            executor.shutdown(wait=False)

        alive_count = len(self.results)
        print(f"\n📊 测试完成: 总计 {total} | 可播放 {alive_count} | 失效已丢弃", flush=True)
        self.results.sort(key=lambda x: x["bitrate_mbps"], reverse=True)
        print(f"✅ 已保留 {alive_count} 个有效源，按码率从高到低排序", flush=True)

        return self.results, self.source_stats
