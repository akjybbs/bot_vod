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
    async def vod(self, event: AstrMessageEvent,text: str):
        # 检查是否配置了API URL
        if not self.api_url:
            yield event.plain_result("\n请先在配置文件中设置API地址")
            return
        yield event.plain_result(f"\n{self.api_url}?ac=videolist&wd={text}")

 
