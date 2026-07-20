"""
generator.py - 结果生成器 (类型修复 + 防御性清洗 + 兜底)
"""
import os
import re
from collections import defaultdict, OrderedDict

class OutputGenerator:
    def __init__(self, tested_channels, demo_channels=None, output_dir="output", update_time=None):
        self.tested_channels = tested_channels
        self.demo_channels = demo_channels or {}
        self.output_dir = output_dir
        self.update_time = update_time  
        os.makedirs(self.output_dir, exist_ok=True)

    def _group_by_channel(self):
        grouped = defaultdict(list)
        for ch in self.tested_channels:
            grouped[ch["name"]].append(ch)
        return grouped

    def _clean_category_name(self, category):
        """✅ 核心防御：防止分类名被截断或包含非法字符"""
        if not category or not isinstance(category, str):
            return "未分类"
        
        cleaned = category.strip().replace('\n', '').replace('\r', '')
        
        # 如果只剩下纯 emoji/符号（长度<=2且不含中英文数字），视为无效
        if not cleaned or (len(cleaned) <= 2 and not re.search(r'[\u4e00-\u9fa5a-zA-Z0-9]', cleaned)):
            print(f"[WARN] 检测到无效分类名 '{category}'，已替换为 '未分类'")
            return "未分类"
            
        # M3U group-title 不允许双引号，替换为单引号防止格式损坏
        return cleaned.replace('"', "'")

    def _get_categories_structure(self):
        """构建分类结构，保持 demo.txt 中的顺序"""
        categories = OrderedDict()
        
        if self.demo_channels:
            # ✅ 采纳 DeepSeek 修复：demo_channels 值为字符串，不再是列表
            for name, category in self.demo_channels.items():
                clean_cat = self._clean_category_name(category)
                if clean_cat not in categories:
                    categories[clean_cat] = []
                if name not in categories[clean_cat]:
                    categories[clean_cat].append(name)
        else:
            seen = set()
            categories["未分类"] = []
            for ch in self.tested_channels:
                if ch["name"] not in seen:
                    categories["未分类"].append(ch["name"])
                    seen.add(ch["name"])
                    
        return categories

    def generate_all(self):
        grouped_channels = self._group_by_channel()
        categories_structure = self._get_categories_structure()
        
        used_urls_m3u = set()
        used_urls_txt = set()
        
        demo_channel_names = set(self.demo_channels.keys()) if self.demo_channels else set()
        wild_channels = [name for name in grouped_channels.keys() if name not in demo_channel_names]
        
        m3u_path = os.path.join(self.output_dir, "result.m3u")
        txt_path = os.path.join(self.output_dir, "result.txt")
        
        with open(m3u_path, "w", encoding="utf-8") as m3u_file, \
             open(txt_path, "w", encoding="utf-8") as txt_file:
             
            m3u_file.write("#EXTM3U\n")
            
            if self.update_time:
                custom_url = "http://xjj1.716888.xyz/fenlei/4k/4k.php"
                txt_file.write("系统公告,#genre#\n")
                txt_file.write(f"📅 更新日期 {self.update_time},{custom_url}\n\n")
                m3u_file.write(f'#EXTINF:-1 group-title="系统公告",📅 更新日期 {self.update_time}\n')
                m3u_file.write(f"{custom_url}\n")
            
            for category, channel_names in categories_structure.items():
                has_valid_sources = any(name in grouped_channels and grouped_channels[name] for name in channel_names)
                if not has_valid_sources:
                    continue
                
                # ✅ 写入时使用清洗后的安全分类名
                safe_category = self._clean_category_name(category)
                txt_file.write(f"{safe_category},#genre#\n")
                
                for name in channel_names:
                    sources = grouped_channels.get(name, [])
                    for src in sources:
                        url = str(src["url"]).replace('\n', '').replace('\r', '').strip()
                        if not url:
                            continue
                            
                        if url not in used_urls_m3u:
                            used_urls_m3u.add(url)
                            m3u_file.write(f'#EXTINF:-1 group-title="{safe_category}",{name}\n')
                            m3u_file.write(f"{url}\n")
                        
                        if url not in used_urls_txt:
                            used_urls_txt.add(url)
                            txt_file.write(f"{name},{url}\n")
                            
                txt_file.write("\n")

            if wild_channels:
                txt_file.write("其他频道,#genre#\n")
                for name in wild_channels:
                    sources = grouped_channels.get(name, [])
                    for src in sources:
                        url = str(src["url"]).replace('\n', '').replace('\r', '').strip()
                        if not url:
                            continue
                            
                        if url not in used_urls_m3u:
                            used_urls_m3u.add(url)
                            m3u_file.write(f'#EXTINF:-1 group-title="其他频道",{name}\n')
                            m3u_file.write(f"{url}\n")
                        
                        if url not in used_urls_txt:
                            used_urls_txt.add(url)
                            txt_file.write(f"{name},{url}\n")
                txt_file.write("\n")

        print(f"✅ 生成完成: M3U 写入 {len(used_urls_m3u)} 条，TXT 写入 {len(used_urls_txt)} 条")
        print(f"   📁 M3U: {m3u_path}")
        print(f"   📁 TXT: {txt_path}")
