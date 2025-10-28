import importlib
import os
import cv2
import astrbot.api.message_components as Comp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.message_components import Node, Nodes, Plain
from astrbot.api import logger
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_plugin_path,
)


class DecodeQrcode(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 检查依赖安装情况
        if not self._check_opencv():
            logger.error(
                "未检测到 OpenCV 或缺少 wechat_qrcode 模块，请先安装依赖：pip install opencv-contrib-python-headless"
            )
            raise

    def _check_opencv(self) -> bool:
        """检查是否安装了 OpenCV 且包含 cv2.wechat_qrcode_WeChatQRCode"""
        try:
            cv2 = importlib.import_module("cv2")
            # 检查 cv2 是否有 wechat_qrcode_WeChatQRCode 属性
            if hasattr(cv2, "wechat_qrcode_WeChatQRCode"):
                return True
            else:
                return False
        except ImportError:
            return False

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        # 图片缓存路径, 不使用插件数据目录，以便多插件数据共享
        self.temp_images_path = os.path.join(
            get_astrbot_data_path(), "temp_data", "images"
        )
        if not os.path.exists(self.temp_images_path):
            os.makedirs(self.temp_images_path, exist_ok=True)
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

    @filter.command("qrde")
    async def qrde(self, event: AstrMessageEvent):
        """使用wechat_qrcode模块的二维码解码功能"""
        file_path = ""
        # 遍历消息链，获取第一张图片
        for comp in event.get_messages():
            if isinstance(comp, Comp.Image):
                # 用框架的缓存方案，不重复造轮子了
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
                "无法读取图片，请确保图片格式正确且未损坏，然后再试一次。"
            )
            return

        # 直接识别
        texts, _ = self.detector.detectAndDecode(image)

        if not texts:
            logger.debug("直接识别二维码失败，尝试二值化处理后再次识别。")
            logger.debug("形态学修复后识别二维码失败，尝试二值化处理后再次识别。")
            # 转为灰度图
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            # 中值滤波，减少噪声影响
            blurred = cv2.medianBlur(gray, 5)
            # 大津法二值化处理
            _, binary = cv2.threshold(
                blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )

            # 检测和解码二维码
            texts, _ = self.detector.detectAndDecode(binary)

        if not texts:
            logger.debug("二值化处理后识别二维码失败，尝试形态学修复后再次识别。")
            # 创建形态学卷积核（对于艺术二维码，似乎能够提高识别率）
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            # 闭运算
            image = cv2.morphologyEx(image, cv2.MORPH_CLOSE, kernel, iterations=1)

            # 检测和解码二维码
            texts, _ = self.detector.detectAndDecode(image)

        # 处理解码结果
        if len(texts) > 0:
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

                for _, text in enumerate(texts):
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
                for _, text in enumerate(texts):
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
                    Comp.Plain("未识别到任何二维码。"),
                ]
            )

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
