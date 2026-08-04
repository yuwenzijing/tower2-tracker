# Buyali 数据采集助手

Windows 便携式采集程序。无需安装 Python 或 Tesseract；程序只在内存中截取当前 AION2 窗口，不上传或保留原始截图。

## 使用方法

1. 保持 `BuyaliCollector`、`runtime` 和本说明文件的相对位置不变。
2. 运行 `BuyaliCollector/BuyaliCollector.exe`。
3. 打开 `https://buyali.xyz`，点击“数据采集”生成配对码，并在助手中输入。
4. 任务栏保留“Buyali 数据采集助手”入口，可查看状态、重新绑定、显示浮窗或退出。
5. 浮窗可直接拖动；所有确认和结果窗口都会显示在浮窗下方，空间不足时显示在上方。

程序优先从 `AION2 l 角色名` 游戏窗口标题读取当前角色，窗口标题不可用时才识别角色头顶绿色名字。

## 本地调试

运行 `python main.py`。服务地址可通过环境变量 `BUYALI_API_BASE` 覆盖。

## 打包

运行 `build.ps1`，产物位于 `release/`。必须整体发布该目录。
