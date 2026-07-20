"""
generator.py - 结果生成器 (终极完美版：分类 + 去重 + 清洗 + 兜底)
"""
import os
from collections import defaultdict, OrderedDict

class OutputGenerator:
    def __init__(self, tested_channels, demo_channels=None, output_dir="output", update_time=None):
        self.tested_channels = tested_channels
        self.demo_channels = demo_channels or {}
        self.output_dir = output_dir
        self.update_time = update_time  
        
        os.makedirs(self.output_dir, exist_ok=True)

    def _group_by_channel(self):
        """将测试结果按频道名称分组"""
        grouped = defaultdict(list)
        for ch in self.tested_channels:
            grouped[ch["name"]].append(ch)
        return grouped

    def _get_categories_structure(self):
        """构建分类结构，保持 demo.txt 中的顺序"""
        categories = OrderedDict()
        
        if self.demo_channels:
            for name, category_list in self.demo_channels.items():
                for category in category_list:
                    if category not in categories:
                        categories[category] = []
                    if name not in categories[category]:
                        categories[category].append(name)
        else:
            seen = set()
            categories["未分类"] = []
            for ch in self.tested_channels:
                if ch["name"] not in seen:
                    categories["未分类"].append(ch["name"])
                    seen.add(ch["name"])
                    
        return categories

    def generate_all(self):
        """生成所有格式的输出文件"""
        grouped_channels = self._group_by_channel()
        categories_structure = self._get_categories_structure()
        
        # ✅ 新增：独立的去重集合
        used_urls_m3u = set()
        used_urls_txt = set()
        
        # ✅ 新增：兜底逻辑，收集不在 demo.txt 中的“野生”频道
        demo_channel_names = set(self.demo_channels.keys()) if self.demo_channels else set()
        wild_channels = []
        for name in grouped_channels.keys():
            if name not in demo_channel_names:
                wild_channels.append(name)
        
        m3u_path = os.path.join(self.output_dir, "result.m3u")
        txt_path = os.path.join(self.output_dir, "result.txt")
        
        with open(m3u_path, "w", encoding="utf-8") as m3u_file, \
             open(txt_path, "w", encoding="utf-8") as txt_file:
             
            m3u_file.write("#EXTM3U\n")
            
            # 写入系统公告
            if self.update_time:
                custom_url = "http://xjj1.716888.xyz/fenlei/4k/4k.php"
                txt_file.write("系统公告,#genre#\n")
                txt_file.write(f"📅 更新日期 {self.update_time},{custom_url}\n\n")
                m3u_file.write(f'#EXTINF:-1 group-title="系统公告",📅 更新日期 {self.update_time}\n')
                m3u_file.write(f"{custom_url}\n")
            
            # 遍历分类写入
            for category, channel_names in categories_structure.items():
                has_valid_sources = any(name in grouped_channels and grouped_channels[name] for name in channel_names)
                if not has_valid_sources:
                    continue
                
                txt_file.write(f"{category},#genre#\n")
                
                for name in channel_names:
                    sources = grouped_channels.get(name, [])
                    for src in sources:
                        # ✅ 新增：强力清洗脏 URL
                        url = str(src["url"]).replace('\n', '').replace('\r', '').strip()
                        if not url:
                            continue
                            
                        # M3U 独立去重写入
                        if url not in used_urls_m3u:
                            used_urls_m3u.add(url)
                            m3u_file.write(f'#EXTINF:-1 group-title="{category}",{name}\n')
                            m3u_file.write(f"{url}\n")
                        
                        # TXT 独立去重写入
                        if url not in used_urls_txt:
                            used_urls_txt.add(url)
                            txt_file.write(f"{name},{url}\n")
                            
                txt_file.write("\n")

            # ✅ 新增：兜底写入“野生”频道（归入“其他频道”分类）
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
