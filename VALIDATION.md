# 验证记录

## 2026-10-27 开源发布检查

- 项目包含 22 个 `.SLDPRT`、3 个 `.SLDASM`、4 个 `.STEP`，全部纳入发布；4 个 SolidWorks 临时锁文件排除。
- 原生 CAD 二进制不改动；STEP 仅替换头部个人邮箱作者字段，数据段逐字节对照原件一致。发布版本的 SHA-256 见 `docs/MODEL_INVENTORY.md`。
- `总装配体.STEP` 的 `DOCUMENT_FILE` 记录涉及 17 个不同外部 STEP 文件，其中 14 个未提供。已在建模说明中列出；未宣称整机 STEP 自包含或装配已完整验证。
- `python -m pip check` 通过；`python -m compileall -q main.py desktop tests` 通过。
- 重新执行全部模拟测试：**25 项通过，43.385 秒**。测试使用模拟串口，未连接真实设备。
- 重新编译 Arduino UNO 固件通过：Servo 1.3.0、Arduino AVR Boards 1.8.8；Flash **8874 / 32256 bytes（27%）**，静态 RAM **1350 / 2048 bytes（65%）**。
- 编译器在受限运行环境首次启动遇到 Windows DLL 重定位错误，在正常权限环境运行同一编译命令成功；未修改固件或上传到开发板。
- 新增 MIT 许可证、模型清单、模型打开与依赖说明、硬件复现范围、贡献说明和仓库忽略规则。控制程序与协议未修改。
- 本机 `.venv`、`.tools`、缓存及 CAD 锁文件不发布；依赖由 `requirements.txt` 和 Arduino 库安装说明复现。

以下保留此前控制界面版本的验证记录。实机验收和 CAD 原生装配检查仍待完成。

## 2026-10-22 控制界面版本

日期：2026-10-22。项目目录：`D:\roboArm`。本次将 X/Y/Z 改为三个同时显示的独立控制区，使用现有协议 v3，保留 D12/D13 双舵机滑块。

## 已完成

- Python 3.12.14；实际安装并验证 PySide6 6.11.2、pyserial 3.5，运行依赖已锁定在 `requirements.txt`。
- `python -m pip check` 通过，无依赖冲突。
- `python -m compileall -q main.py desktop tests` 通过。
- 本次运行 `python -m unittest discover -s tests -v`：**25 项通过（42.977 秒）**。已更新界面回归测试，通过实际按钮验证三个控制区同时显示、分别设置步数/速度/方向、三轴并行运行、单轴等待确认时其他轴可操作、停止 Y 时 X/Z 继续运行、全部停止、交错反馈分别更新计数和进度、断线后禁用三轴控制；原有舵机与协议测试同样通过。测试不打开真实串口，也不验证实际引脚波形。
- Windows 原生 Qt GUI（Fusion 样式）启动并截图检查：X/Y/Z 三列控制和反馈同时显示，保留 D12/D13 双滑块、全部停止按钮和串口日志，内容可滚动访问。启动不自动连接、不发送运动命令。
- 本次仅修改上位机界面、对应测试和说明，未修改串口协议或 Arduino 固件，无需为此次界面更新重新烧录。
- 现有协议 v3 固件此前使用 Arduino 官方 CLI 1.5.2-rc.1 + Arduino AVR Boards 1.8.8，目标 `arduino:avr:uno` 编译通过；`--warnings all` 无项目固件警告。本次固件未变，未重复编译。
- Arduino 官方 Servo **1.3.0** 安装在项目 `.tools/arduino-user/libraries` 下用于编译；用户 Arduino IDE 中也需安装官方 Servo 库。
- 现有固件此前编译结果：Flash 使用 **8874 / 32256 bytes（27%）**，静态 RAM **1350 / 2048 bytes（65%）**，剩余 698 bytes 供栈等使用。

编译命令（验证工具放在项目 `.tools` 下）：

```powershell
.\.tools\arduino-cli\arduino-cli.exe --config-file .tools\arduino-cli.yaml compile --fqbn arduino:avr:uno --warnings all --build-path D:\roboArm\.tools\uno-build D:\roboArm\arduino\roboarm_x
```

## 待实机完成

**未自动烧录、未打开 COM7、未驱动真实电机。** 模拟测试验证上位机通信和界面流程，固件编译验证代码可构建；均不代表实际电机已验收。

按 README 第五节逐轴验证全步 200/400 脉冲、正反方向、运动中单轴停止、并行时停止一轴不影响另一轴、全部停止、主动断开、异常断线心跳全部停止，以及各模块限流、温升和负载下的可靠速度。实际 USB 停止延迟、步进频率/抖动、共享 ENABLE 引脚行为、丢步和机械表现尚未测量。

舵机需验证独立电源与共地、启动/串口复位回中、D12/D13 对应关系、角度和机械端点、并行步进是否抖动。模拟角度反馈只是命令已被写入，不能证明实际位置或移动完成。Servo 定时器中断的实际步进影响尚未实测。

当前无加减速、限位、回零和编码器，计数代表发出的 STEP 脉冲。任一轴运行时 D8 保持使能；全部空闲后统一释放步进驱动器。舵机在停止步进/断开/超时后维持最后设定，UNO 复位则写回 90°。A 轴尚未启用。若板上烧录过协议 v4 固件，需重新烧录恢复的协议 v3 固件，再重启上位机。
