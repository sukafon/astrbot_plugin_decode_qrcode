# astrbot_plugin_decode_qrcode 插件

插件功能
- 基于 OpenCV 的微信开源二维码识别模块，识别图片中的二维码并返回解码结果。

快速要求
- 需要 Python 3.10+（遵循 AstrBot 项目要求）
- 插件会在初始化时自动检测并安装 OpenCV（opencv-contrib-python / opencv-contrib-python-headless）

使用方法
1. 发送命令：`/qrde`（与图片同一条消息或引用消息中发送）。
2. 插件将返回识别到的二维码文本；在 aiocqhttp（QQ群）平台会以转发形式返回结果。

注意事项
- 若运行环境无图形界面（如某些 Linux 容器），插件会自动安装 headless 版本的 OpenCV。
- 请确保 `models/` 中的模型文件存在，否则二维码检测会失败。
- 临时下载的图片会保存在 AstrBot 数据目录下的 `temp_data/images`，插件不会长期保存这些文件。