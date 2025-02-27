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
        # 分割API地址为列表，并过滤空值
        self.api_url_vod = [url.strip() for url in config.get("api_url_vod", "").split(',') if url.strip()]
        self.api_url_18 = [url.strip() for url in config.get("api_url_18", "").split(',') if url.strip()]

    async def _common_handler(self, event, api_urls, keyword):
        """支持多API地址的通用处理器"""
        if not api_urls:
            yield event.plain_result("⚠️ 服务未正确配置，请联系管理员")
            return

        error_log = []
        for base_url in api_urls:
            encoded_keyword = urllib.parse.quote(keyword)
            query_url = f"{base_url}?ac=videolist&wd={encoded_keyword}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(query_url, timeout=15) as response:
                        if response.status != 200:
                            error_log.append(f"{base_url} 状态码 {response.status}")
                            continue  # 尝试下一个API

                        html_content = await response.text()
                        parsed_result = self._parse_html(html_content)
                        
                        if not parsed_result:
                            error_log.append(f"{base_url} 无结果")
                            continue  # 继续尝试其他API

                        # 成功获取结果时构建响应
                        result_msg = [
                            "📺 查询结果：",
                            parsed_result,
                            "\n" + "*" * 25,
                            "💡 重要观看提示：",
                            "1. 手机端：复制链接到浏览器地址栏打开",
                            "2. 电脑端：使用专业播放器打开链接",
                            "*" * 25
                        ]
                        yield event.plain_result("\n".join(result_msg))
                        return  # 成功返回，终止处理

            except aiohttp.ClientTimeout:
                error_log.append(f"{base_url} 请求超时")
            except Exception as e:
                error_log.append(f"{base_url} 异常: {str(e)}")

        # 所有API均失败后的处理
        self.context.logger.error(f"所有API请求失败 | {' | '.join(error_log)}")
        yield event.plain_result("❌ 所有服务暂时不可用，请稍后重试")

    # _parse_html 方法保持不变

    @filter.command("vod")
    async def search_normal(self, event: AstrMessageEvent, text: str):
        """普通影视资源搜索"""
        if not self.api_url_vod:
            yield event.plain_result("🔧 普通视频服务未配置")
            return
        async for msg in self._common_handler(event, self.api_url_vod, text):
            yield msg

    @filter.command("vodd")
    async def search_adult(self, event: AstrMessageEvent, text: str):
        """18+视频搜索"""
        if not self.api_url_18:
            yield event.plain_result("🔞 服务未启用")
            return
        async for msg in self._common_handler(event, self.api_url_18, text):
            yield msg
