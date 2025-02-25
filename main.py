from astrbot.api.message_components import *
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
import aiohttp

@register("bot_vod", "appale", "从API获取视频地址。使用 /vod 电影名", "1.0")
class SetuPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.api_url = config.get("api_url", "")

    @filter.command("vod")
    async def get_setu(self, event: AstrMessageEvent):
        # 检查是否配置了API URL
        if not self.api_url:
            yield event.plain_result("\n请先在配置文件中设置API地址")
            return
            
        # 创建一个不验证SSL的连接上下文
        ssl_context = aiohttp.TCPConnector(verify_ssl=False)
        async with aiohttp.ClientSession(connector=ssl_context) as session:
            try:
                # 使用配置中的API URL发送GET请求
                async with session.get(self.api_url) as response:
                    data = await response.json()
                    
                    if data["error"]:
                        yield event.plain_result(f"\n获取图片失败：{data['error']}")
                        return
                    
                    if not data["data"]:
                        yield event.plain_result("\n未获取到图片")
                        return
                    
                    # 获取图片信息
                    image_data = data["data"][0]
                    image_url = image_data["urls"]["original"]
                    title = image_data["title"]
                    author = image_data["author"]
                    
                    # 构建消息链
                    chain = [
                        Image.fromURL(image_url)  # 从URL加载图片
                    ]
                    
                    yield event.chain_result(chain)
                    
            except Exception as e:
                yield event.plain_result(f"\n请求失败: {str(e)}")
