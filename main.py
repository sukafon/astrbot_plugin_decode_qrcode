import importlib
import subprocess
import sys
import os
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Reply, Nodes
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_plugin_path,
)


@register(
    "DecodeQrcode", "Sukafon", "使用微信开源OpenCV二维码识别模块识别二维码", "1.0.0"
)
class DecodeQrcode(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 检查依赖安装情况
        if not self._check_opencv():
            self._install_opencv()
        global cv2
        cv2 = importlib.import_module("cv2")

    def _check_opencv(self) -> bool:
        """检查是否安装了 OpenCV"""
        try:
            importlib.import_module("cv2")
            return True
        except ImportError:
            return False

    def _has_gui(self) -> bool:
        """
        检测当前环境是否有图形化界面
        Linux 系统：检查 DISPLAY 环境变量
        Windows / Mac 可以默认认为有 GUI
        """
        if sys.platform.startswith("linux"):
            display = os.environ.get("DISPLAY")
            if display:
                return True
            else:
                return False
        elif sys.platform.startswith("win") or sys.platform.startswith("darwin"):
            return True
        else:
            return False

    def _install_opencv(self):
        """安装 OpenCV 包"""
        try:
            if self._has_gui():
                logger.info("检测到 GUI 环境，安装 opencv-contrib-python")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "opencv-contrib-python"])
            else:
                logger.info("未检测到 GUI，安装 opencv-contrib-python-headless")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "opencv-contrib-python-headless"])

            logger.info("成功安装 OpenCV 包")
        except subprocess.CalledProcessError as e:
            logger.error(f"安装 OpenCV 包失败: {str(e)}")
            raise

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
            if isinstance(comp, Image):
                fileName = comp.file.replace("{", "").replace("}", "").replace("-", "")
                file_path = os.path.join(self.temp_images_path, fileName)
                # 检查文件是否存在
                if not os.path.isfile(file_path):
                    file_path = await download_image_by_url(comp.url, path=file_path)
                break
            elif isinstance(comp, Reply):
                for quote in comp.chain:
                    if isinstance(quote, Image):
                        fileName = (
                            quote.file.replace("{", "")
                            .replace("}", "")
                            .replace("-", "")
                        )
                        file_path = os.path.join(self.temp_images_path, fileName)
                        # 检查文件是否存在
                        if not os.path.isfile(file_path):
                            file_path = await download_image_by_url(
                                quote.url, path=file_path
                            )
                        break
        if not file_path:
            yield event.plain_result("请在消息中携带或者引用图片。")
            return

        # 读取图片
        image = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)

        # 对图片进行二值化处理
        _, binary_img = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)

        # 检测和解码二维码
        texts, _ = self.detector.detectAndDecode(binary_img)

        # 处理解码结果
        if len(texts) > 0 or event.platform_meta.name == "aiocqhttp":
            # 对QQ群使用转发
            if event.platform_meta.name == "aiocqhttp":
                from astrbot.api.message_components import Node, Plain

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
                    result += text.strip() + "\n"
                yield event.plain_result(result.strip())
            return
        else:
            yield event.plain_result("未识别任何二维码。")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
