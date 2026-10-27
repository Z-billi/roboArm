# 参与贡献

欢迎通过 Issue 描述问题或提交 Pull Request。请说明复现步骤、Python/Arduino 环境、预期行为和实际结果；硬件问题附上开发板、驱动器、电源和电机型号，避免公开私人信息。

## 控制代码

安装 `requirements.txt` 后执行：

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q main.py desktop tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试使用模拟串口，不应连接或驱动真实电机。固件改动需用 Arduino UNO 目标和 Servo 1.3.0 编译验证；涉及协议时同步更新上位机、固件、测试和说明。模拟测试不替代实机验收。

## 机械模型

保留原有中文文件名和装配引用关系。提交修改时说明 SolidWorks 版本、修改零件及尺寸，尽量附上 STEP 导出。整机 STEP 应包含所有几何数据，或同时提交其引用的全部外部零件文件。

不要提交 `~$` 锁文件、自动备份、虚拟环境、工具安装包、密钥或本机编译产物。新增第三方模型或资源时注明来源并保留其许可，不要将第三方权利声明替换为本项目 MIT 许可。
