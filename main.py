import os
import cv2
import asyncio
import astrbot.api.message_components as Comp
from pyzbar.pyzbar import decode
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.message_components import Node, Nodes, Plain
from astrbot.api import logger
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_path


class DecodeQrcode(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 检查依赖安装情况
        if not self._check_opencv():
            logger.error(
                "未检测到 OpenCV 或缺少 wechat_qrcode 模块，请先安装依赖：pip install opencv-contrib-python-headless"
            )
            raise ImportError("缺少 OpenCV wechat_qrcode 模块")

    def _check_opencv(self) -> bool:
        """检查是否安装了 OpenCV 且包含 cv2.wechat_qrcode_WeChatQRCode"""
        # 检查 cv2 是否有 wechat_qrcode_WeChatQRCode 属性
        if hasattr(cv2, "wechat_qrcode_WeChatQRCode"):
            return True
        else:
            return False

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        # 配置模型文件路径
        models = os.path.join(
            get_astrbot_plugin_path(), "astrbot_plugin_decode_qrcode", "models"
        )
        detect_prototxt_path = os.path.join(models, "detect.prototxt")
        detect_caffe_model_path = os.path.join(models, "detect.caffemodel")
        sr_prototxt_path = os.path.join(models, "sr.prototxt")
        sr_caffe_model_path = os.path.join(models, "sr.caffemodel")

        # 创建模型实例
        self.detector = cv2.wechat_qrcode_WeChatQRCode(
            detect_prototxt_path,
            detect_caffe_model_path,
            sr_prototxt_path,
            sr_caffe_model_path,
        )

    def process_image_sync(self, image_data) -> tuple[str, ...]:
        # 直接识别
        texts, _ = self.detector.detectAndDecode(image_data)
        if not texts:
            logger.debug("直接识别二维码失败，尝试滤波处理后再次识别。")
            # 转为灰度图
            image_data = cv2.cvtColor(image_data, cv2.COLOR_BGR2GRAY)
            # 滤波器
            image_data = cv2.bilateralFilter(
                image_data, d=9, sigmaColor=75, sigmaSpace=75
            )
            # 检测和解码二维码
            texts, _ = self.detector.detectAndDecode(image_data)

        if not texts:
            logger.debug("识别二维码失败，尝试降级 Pyzbar 再次识别。")
            # 检测和解码二维码
            result = decode(image_data)
            texts = tuple(d.data.decode("utf-8") for d in result)
        return texts

    @filter.command("qrde")
    async def qrde(self, event: AstrMessageEvent):
        """使用wechat_qrcode模块的二维码解码功能"""
        file_path = ""
        # 遍历消息链，获取第一张图片
        for comp in event.get_messages():
            if isinstance(comp, Comp.Image):
                file_path = await download_image_by_url(comp.url)
                break
            elif isinstance(comp, Comp.Reply):
                for quote in comp.chain:
                    if isinstance(quote, Comp.Image):
                        file_path = await download_image_by_url(quote.url)
                        break

        if not file_path:
            yield event.plain_result("请在消息中携带或者引用图片。")
            return

        # 读取图片
        image = cv2.imread(file_path)

        # error: (-215:Assertion failed) !img.empty() in function 'detectAndDecode'
        if image is None:
            yield event.plain_result(
                "无法读取图片，可能图片格式不支持或文件损坏，请再试一次。"
            )
            return
        texts = await asyncio.to_thread(self.process_image_sync, image)
        # 处理解码结果
        if texts:
            # 对QQ使用转发
            if event.platform_meta.name == "aiocqhttp":
                nodes = [
                    Node(
                        uin=event.get_sender_id(),
                        name=event.get_sender_name(),
                        content=[
                            Plain("二维码识别结果:"),
                        ],
                    )
                ]

                for text in texts:
                    nodes.append(
                        Node(
                            uin=event.get_sender_id(),
                            name=event.get_sender_name(),
                            content=[Plain(text)],
                        )
                    )

                yield event.chain_result([Nodes(nodes)])
            # 其他平台则直接发送
            else:
                result = "二维码识别结果: \n"
                for text in texts:
                    result += f"{text.strip()}\n"
                yield event.chain_result(
                    [
                        Comp.Reply(id=event.message_obj.message_id),
                        Comp.Plain(result.strip()),
                    ]
                )
            return
        else:
            yield event.chain_result(
                [
                    Comp.Reply(id=event.message_obj.message_id),
                    Comp.Plain("未识别到任何二维码或者有效内容。"),
                ]
            )

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
