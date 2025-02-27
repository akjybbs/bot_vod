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
        total_attempts = len(api_urls)  # 总共尝试的API数量
        successful_apis = 0  # 成功获取数据的API数量
        all_results = []  # 存储所有结果

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
                        if response.status != 200:
                            continue  # 如果当前API请求失败，继续尝试下一个API

                        # 响应内容处理
                        html_content = await response.text()
                        parsed_result = self._parse_html(html_content)

                        if parsed_result:
                            successful_apis += 1  # 记录成功的API数量
                            all_results.append(parsed_result)  # 添加解析结果

            except aiohttp.ClientTimeout:
                continue  # 请求超时，继续尝试下一个API
            except Exception as e:
                self.context.logger.error(f"视频查询异常: {str(e)}")
                continue  # 发生异常，继续尝试下一个API

        # 合并所有结果
        combined_results = "\n".join(all_results) if all_results else None

        if combined_results:
            result_msg = [
                f"🔍 搜索 {total_attempts} 个源｜成功 {successful_apis} 个📊 找到 {len(all_results)} 条结果",
                "📺 查询结果：",
                combined_results,
                "\n" + "*" * 25,
                "💡 重要观看提示：",
                "1. 手机端：复制链接到浏览器地址栏打开",
                "2. 电脑端：使用专业播放器打开链接",
                "*" * 25
            ]
            yield event.plain_result("\n".join(result_msg))
        else:
            yield event.plain_result("🔍 没有找到相关视频资源")

    def _parse_html(self, html_content):
        """HTML解析专用方法"""
        soup = BeautifulSoup(html_content, 'html.parser')
        video_items = soup.select('rss list video')

        results = []
        for idx, item in enumerate(video_items[:8], 1):
            # 提取标题
            title = item.select_one('name').text.strip() if item.select_one('name') else "未知标题"
            
            # 提取播放链接
            dd_elements = item.select('dl > dd')
            for dd in dd_elements:
                for url in dd.text.split('#'):
                    if url.strip():
                        results.append(f"{idx}. 【{title}】\n   🎬 {url.strip()}")

        return "\n".join(results) if results else None

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
