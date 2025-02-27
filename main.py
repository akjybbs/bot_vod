from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup

@register("bot_vod", "appale", "从API获取视频地址（使用 /vod 或 /vodd + 电影名）", "1.1")
class VideoSearchPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        # 将 api_url_vod 和 api_url_18 设置为列表
        self.api_url_vod = config.get("api_url_vod", "").split(',')
        self.api_url_18 = config.get("api_url_18", "").split(',')

    async def _common_handler(self, event, api_urls, keyword):
        """通用请求处理核心逻辑"""
        total_sources = len(api_urls)
        successful_sources = 0
        all_found_results = {}

        for api_url in api_urls:
            api_url = api_url.strip()
            if not api_url:
                continue  # 跳过空的API地址

            # URL编码处理
            encoded_keyword = urllib.parse.quote(keyword)
            query_url = f"{api_url}?ac=videolist&wd={encoded_keyword}"

            try:
                # 异步HTTP请求
                async with aiohttp.ClientSession() as session:
                    async with session.get(query_url, timeout=15) as response:
                        # HTTP状态码处理
                        if response.status == 200:
                            successful_sources += 1
                            # 响应内容处理
                            html_content = await response.text()
                            parsed_result = self._parse_html(html_content)
                            if parsed_result:
                                for title, episodes in parsed_result.items():
                                    if title not in all_found_results:
                                        all_found_results[title] = []
                                    all_found_results[title].extend(episodes)

            except aiohttp.ClientTimeout:
                continue  # 请求超时，继续尝试下一个API
            except Exception as e:
                self.context.logger.error(f"视频查询异常: {str(e)}")
                continue  # 发生异常，继续尝试下一个API

        # 合并所有找到的结果并限制最多8条
        displayed_results = []
        result_count = 0
        for title, episodes in all_found_results.items():
            episode_count = 0
            for idx, episode in enumerate(episodes, 1):
                displayed_results.append(f"{result_count + 1}. 【{title}】\n   🎬 第{idx}集\n   {episode}")
                episode_count += 1
                result_count += 1
                if result_count >= 8:
                    break
            if result_count >= 8:
                break
        
        # 构建统计信息
        stats_msg = f"🔍 搜索 {total_sources} 个源｜成功 {successful_sources} 个\n📊 找到 {len(all_found_results)} 条结果｜展示前 8 条"

        if displayed_results:
            result_msg = [
                stats_msg,
                "📺 查询结果：",
                "\n".join(displayed_results),
                "\n" + "*" * 25,
                "💡 重要观看提示：",
                "1. 手机端：复制链接到浏览器地址栏打开",
                "2. 电脑端：使用专业播放器打开链接",
                "*" * 25
            ]
            yield event.plain_result("\n".join(result_msg))
        else:
            yield event.plain_result(f"{stats_msg}\n🔍 没有找到相关视频资源")

    def _parse_html(self, html_content):
        """HTML解析专用方法"""
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')

        results = {}
        for item in video_items:
            # 提取标题
            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
            
            # 提取播放链接
            dd_elements = item.select('dl > dd')
            episodes = []
            for dd in dd_elements:
                for url in dd.text.split('#'):
                    if url.strip():
                        episodes.append(url.strip())

            if title not in results:
                results[title] = []
            results[title].extend(episodes)

        return results

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通影视资源搜索"""
        if not any(self.api_url_vod):  # 检查是否有配置有效的API地址
            yield event.plain_result("🔧 普通视频服务未配置")
            return
        async for msg in self._common_handler(event, self.api_url_vod, text):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        """18+视频搜索"""
        if not any(self.api_url_18):  # 检查是否有配置有效的API地址
            yield event.plain_result("🔞 服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg
