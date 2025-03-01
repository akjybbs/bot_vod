from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
import re

@register("bot_vod", "appale", "从API获取视频地址（使用 /vod 或 /vodd + 电影名）", "1.4")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')
        self.records = int(config.get("records", "3"))

    async def _common_handler(self, event, api_urls, keyword):
        total_attempts = len(api_urls)
        successful_apis = 0
        
        # 四级数据结构：标题 -> 集数 -> API索引 -> URL列表
        result_tree = {}
        ordered_titles = []
        
        for api_index, api_url in enumerate(api_urls):
            api_url = api_url.strip()
            if not api_url:
                continue

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{api_url}?ac=videolist&wd={urllib.parse.quote(keyword)}",
                        timeout=15
                    ) as response:
                        if response.status != 200:
                            continue

                        html_content = await response.text()
                        parsed_items = self._parse_html(html_content)
                        
                        if parsed_items:
                            successful_apis += 1
                            for title, episode, url in parsed_items:
                                if title not in result_tree:
                                    ordered_titles.append(title)
                                    result_tree[title] = {}
                                
                                if episode not in result_tree[title]:
                                    result_tree[title][episode] = {}
                                
                                if api_index not in result_tree[title][episode]:
                                    result_tree[title][episode][api_index] = []
                                result_tree[title][episode][api_index].append(url)

            except Exception as e:
                self.context.logger.error(f"API请求异常: {str(e)}")
                continue

        # 构建输出结果
        result_lines = []
        current_index = 1
        total_videos = 0  # 统计总资源数
        
        for title in ordered_titles:
            if title not in result_tree:
                continue
            
            episodes = sorted(result_tree[title].keys())
            
            for episode in episodes:
                merged_urls = []
                for api_index in sorted(result_tree[title][episode].keys()):
                    merged_urls.extend(result_tree[title][episode][api_index])
                
                if merged_urls:
                    total_videos += len(merged_urls)
                    # 主条目
                    result_lines.append(f"{current_index}. 【{title}】🎬 {merged_urls[0]}")
                    # 附加链接
                    for url in merged_urls[1:]:
                        result_lines.append(f"   🎬 {url}")
            
            current_index += 1  # 处理完当前标题后递增

        if result_lines:
            header = [
                f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个",
                f"📊 找到 {total_videos} 条资源",
                "━" * 30
            ]
            footer = [
                "━" * 30,
                "💡 播放提示：",
                "1. 移动端直接粘贴链接到浏览器",
                "2. 电脑端推荐使用PotPlayer/VLC播放",
                "━" * 30
            ]
            full_msg = "\n".join(header + result_lines + footer)
            yield event.plain_result(full_msg)
        else:
            yield event.plain_result(f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个\n{'━'*30}\n未找到相关资源")

    def _parse_html(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')[:self.records]
        
        parsed_data = []
        for item in video_items:
            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
            
            # 提取集数信息
            for dd in item.select('dl > dd'):
                parts = dd.text.split('$')
                if len(parts) >= 2:
                    episode_text = parts[0].strip()
                    url = parts[-1].strip()
                    episode_num = self._normalize_episode(episode_text)
                    parsed_data.append((title, episode_num, url))
        return parsed_data

    def _normalize_episode(self, text):
        """统一处理不同格式的集数标识"""
        match = re.search(r'\d+', text)
        return f"{int(match.group()):03d}" if match else "999"

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        if not self.api_url_vod:
            yield event.plain_result("⚠️ 普通视频服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_vod, text):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        if not self.api_url_18:
            yield event.plain_result("⚠️ 成人内容服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg
