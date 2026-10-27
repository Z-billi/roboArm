from datetime import datetime
from dataclasses import replace

from PySide6.QtCore import Qt, QSignalBlocker, QTimer, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMainWindow,
    QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget,
    QSlider, QScrollArea,
)
from serial.tools import list_ports

from .protocol import (
    AXES, SERVO_PINS, INITIAL_SERVO_ANGLE, MAX_SPEED, MAX_STEPS,
    move_command, parse_status, servo_command, parse_servo_status,
)
from .serial_worker import SerialWorker


class AxisControlPanel(QGroupBox):
    """One permanently visible set of controls and feedback for an axis."""

    def __init__(self, axis: str):
        super().__init__(f"{axis} 轴")
        grid = QGridLayout(self)
        self.steps = QSpinBox()
        self.steps.setRange(1, MAX_STEPS)
        self.steps.setValue(200)
        self.steps.setSuffix(" 脉冲")
        self.steps.setAccessibleName(f"{axis} 轴运行步数")
        self.speed = QSpinBox()
        self.speed.setRange(1, MAX_SPEED)
        self.speed.setValue(200)
        self.speed.setSuffix(" 脉冲/秒")
        self.speed.setAccessibleName(f"{axis} 轴速度")
        self.direction = QComboBox()
        self.direction.addItems(["正转 (+)", "反转 (−)"])
        self.direction.setAccessibleName(f"{axis} 轴运行方向")
        for row, (text, control) in enumerate([
            ("运行步数", self.steps), ("速度", self.speed), ("运行方向", self.direction),
        ]):
            grid.addWidget(QLabel(text), row, 0)
            grid.addWidget(control, row, 1)
        self.run_button = QPushButton(f"运行 {axis} 轴")
        self.forward = QPushButton("正转")
        self.reverse = QPushButton("反转")
        self.stop = QPushButton(f"停止 {axis} 轴")
        self.stop.setStyleSheet("background: #b91c1c; color: white; font-weight: bold; padding: 6px;")
        grid.addWidget(self.run_button, 3, 0, 1, 2)
        grid.addWidget(self.forward, 4, 0)
        grid.addWidget(self.reverse, 4, 1)
        grid.addWidget(self.stop, 5, 0, 1, 2)
        self.state_label = QLabel("未知")
        self.direction_label = QLabel("—")
        self.completed_label = QLabel("—")
        self.remaining_label = QLabel("—")
        self.actual_speed = QLabel("—")
        for row, (text, value) in enumerate([
            ("运动状态", self.state_label), ("当前/最近方向", self.direction_label),
            ("已发出脉冲", self.completed_label), ("剩余脉冲", self.remaining_label),
            ("设备设定速度", self.actual_speed),
        ], start=6):
            grid.addWidget(QLabel(text), row, 0)
            grid.addWidget(value, row, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setAccessibleName(f"{axis} 轴运行进度")
        grid.addWidget(self.progress, 11, 0, 1, 2)
        grid.setColumnStretch(1, 1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RoboArm · 三轴步进电机 + 双舵机控制")
        self.resize(1000, 850)
        self.worker: SerialWorker | None = None
        self.connected = False
        self.running_axes = set()
        self.pending_axes = {}
        self.axis_status = {}
        self.all_stop_pending = False
        self.closing = False
        self.communication_error = False
        self.servo_status = {}
        self.servo_targets = {}  # Latest slider value waiting for the rate-limit timer.
        self.servo_requested = {}  # Values sent, awaiting matching device feedback.

        root = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(root)
        self.setCentralWidget(scroll)
        layout = QVBoxLayout(root)
        title = QLabel("Arduino UNO · CNC Shield V3 · A4988")
        title.setStyleSheet("font-size: 20px; font-weight: 600; padding: 8px 0;")
        layout.addWidget(title)

        box = QGroupBox("USB 串口 · 115200 baud")
        row = QHBoxLayout(box)
        self.ports = QComboBox()
        self.ports.setEditable(True)
        self.ports.setMinimumWidth(230)
        self.refresh = QPushButton("刷新串口")
        self.connect_button = QPushButton("连接")
        row.addWidget(self.ports, 1)
        row.addWidget(self.refresh)
        row.addWidget(self.connect_button)
        layout.addWidget(box)
        self.connection_label = QLabel("未连接")
        layout.addWidget(self.connection_label)

        motion = QGroupBox("三轴步进控制 · 各轴独立设置，可并行运行")
        motion_layout = QVBoxLayout(motion)
        panels = QHBoxLayout()
        self.axis_controls = {}
        for axis in AXES:
            panel = AxisControlPanel(axis)
            self.axis_controls[axis] = panel
            panels.addWidget(panel, 1)
            panel.forward.clicked.connect(lambda checked=False, a=axis: self.move(a, 1))
            panel.reverse.clicked.connect(lambda checked=False, a=axis: self.move(a, -1))
            panel.run_button.clicked.connect(
                lambda checked=False, a=axis: self.move(
                    a, 1 if self.axis_controls[a].direction.currentIndex() == 0 else -1
                )
            )
            panel.stop.clicked.connect(lambda checked=False, a=axis: self.stop_motion(a))
        motion_layout.addLayout(panels)
        self.stop_all = QPushButton("停止全部步进")
        self.stop_all.setStyleSheet("background: #b91c1c; color: white; font-weight: bold; padding: 8px;")
        hint = QLabel("正转/反转按钮直接运行输入步数。全步模式：200 脉冲 ≈ 1 圈。")
        hint.setWordWrap(True)
        footer = QHBoxLayout()
        footer.addWidget(hint, 1)
        footer.addWidget(self.stop_all)
        motion_layout.addLayout(footer)
        layout.addWidget(motion)

        servo_box = QGroupBox("舵机角度 · 0～180° · 启动位置 90°")
        servo_grid = QGridLayout(servo_box)
        self.servo_sliders = {}
        self.servo_values = {}
        self.servo_feedback = {}
        for row_index, pin in enumerate(SERVO_PINS):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 180)
            slider.setValue(INITIAL_SERVO_ANGLE)
            slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            slider.setTickInterval(30)
            slider.setPageStep(10)
            slider.setAccessibleName(f"{pin} 舵机目标角度")
            value = QLabel(f"{INITIAL_SERVO_ANGLE}°")
            value.setMinimumWidth(45)
            feedback = QLabel("设备设定：—")
            servo_grid.addWidget(QLabel(f"舵机 {row_index + 1} · {pin}"), row_index, 0)
            servo_grid.addWidget(QLabel("0°"), row_index, 1)
            servo_grid.addWidget(slider, row_index, 2)
            servo_grid.addWidget(QLabel("180°"), row_index, 3)
            servo_grid.addWidget(value, row_index, 4)
            servo_grid.addWidget(feedback, row_index, 5)
            self.servo_sliders[pin] = slider
            self.servo_values[pin] = value
            self.servo_feedback[pin] = feedback
            slider.valueChanged.connect(lambda angle, p=pin: self.servo_changed(p, angle))
            slider.sliderReleased.connect(self.flush_servo_targets)
        servo_grid.setColumnStretch(2, 1)
        servo_hint = QLabel("拖动滑块实时设定角度；停止步进、断开连接时，舵机保持最后设定角度。")
        servo_hint.setWordWrap(True)
        servo_grid.addWidget(servo_hint, len(SERVO_PINS), 0, 1, 6)
        layout.addWidget(servo_box)
        self.servo_timer = QTimer(self)
        self.servo_timer.setInterval(80)
        self.servo_timer.timeout.connect(self.flush_servo_targets)
        self.servo_timer.start()

        self.notice = QLabel("请先烧录固件，接线完成后连接串口。初次测试建议 200 脉冲/秒。")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

        log_row = QHBoxLayout()
        log_row.addWidget(QLabel("串口通信日志（自动隐藏 PING 心跳）"), 1)
        self.status_button = QPushButton("查询状态")
        self.clear_log = QPushButton("清空日志")
        log_row.addWidget(self.status_button)
        log_row.addWidget(self.clear_log)
        layout.addLayout(log_row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.setMinimumHeight(100)
        layout.addWidget(self.log, 1)

        self.refresh.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.toggle_connection)
        self.stop_all.clicked.connect(self.stop_all_motion)
        self.status_button.clicked.connect(self.query_status)
        self.clear_log.clicked.connect(self.log.clear)
        self.refresh_ports()
        self.render_status()
        self.update_controls()

    @Slot()
    def query_status(self):
        if self.connected and self.worker:
            self.worker.submit("STATUS")
            self.worker.submit("SERVO_STATUS")

    def set_servo_slider(self, pin, angle):
        with QSignalBlocker(self.servo_sliders[pin]):
            self.servo_sliders[pin].setValue(angle)
        self.servo_values[pin].setText(f"{angle}°")

    def servo_changed(self, pin, angle):
        self.servo_values[pin].setText(f"{angle}°")
        if self.connected and not self.all_stop_pending and pin in self.servo_status:
            self.servo_targets[pin] = angle

    @Slot()
    def flush_servo_targets(self):
        if not self.connected or not self.worker or self.all_stop_pending:
            return
        for pin, angle in list(self.servo_targets.items()):
            if self.worker.submit(servo_command(pin, angle)):
                self.servo_requested[pin] = angle
                del self.servo_targets[pin]

    def reset_servos(self):
        self.servo_status.clear()
        self.servo_targets.clear()
        self.servo_requested.clear()
        for pin in SERVO_PINS:
            self.set_servo_slider(pin, INITIAL_SERVO_ANGLE)
            self.servo_feedback[pin].setText("设备设定：—")

    def render_status(self):
        names = {"IDLE": "空闲", "RUNNING": "运行中", "STOPPED": "已停止", "DONE": "已完成"}
        directions = {"FORWARD": "正转 (+)", "REVERSE": "反转 (−)", "NONE": "—"}
        for axis, panel in self.axis_controls.items():
            status = self.axis_status.get(axis) if self.connected else None
            panel.state_label.setText(names[status.state] if status else "未知（等待连接）")
            panel.direction_label.setText(directions[status.direction] if status else "—")
            panel.completed_label.setText(str(status.completed) if status else "—")
            panel.remaining_label.setText(str(status.remaining) if status else "—")
            panel.actual_speed.setText(f"{status.speed} 脉冲/秒" if status else "—")
            panel.progress.setValue(round(100 * status.completed / status.total) if status and status.total else 0)

    @Slot()
    def refresh_ports(self):
        selected = self.ports.currentData() or self.ports.currentText().strip() or "COM7"
        self.ports.clear()
        for port in list_ports.comports():
            self.ports.addItem(f"{port.device} — {port.description}", port.device)
        index = self.ports.findData(selected)
        if index >= 0:
            self.ports.setCurrentIndex(index)
        else:
            self.ports.setEditText(selected)

    def append_log(self, prefix: str, text: str):
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S.%f}"[:-3] + f" {prefix} {text}")

    def update_controls(self):
        active = self.worker is not None
        self.ports.setEnabled(not active)
        self.refresh.setEnabled(not active)
        self.connect_button.setText("断开" if active else "连接")
        self.connect_button.setEnabled(not self.closing)
        for axis, panel in self.axis_controls.items():
            available = (self.connected and axis in self.axis_status
                         and axis not in self.running_axes and axis not in self.pending_axes
                         and not self.all_stop_pending)
            for control in (panel.forward, panel.reverse, panel.run_button, panel.steps, panel.speed, panel.direction):
                control.setEnabled(available)
            panel.stop.setEnabled(self.connected)
        self.stop_all.setEnabled(self.connected)
        self.status_button.setEnabled(self.connected)
        for pin in SERVO_PINS:
            self.servo_sliders[pin].setEnabled(self.connected and pin in self.servo_status and not self.all_stop_pending)

    @Slot()
    def toggle_connection(self):
        if self.worker:
            self.connection_label.setText("正在停止并断开…")
            self.worker.disconnect()
            self.servo_targets.clear()
            self.servo_requested.clear()
            self.connected = False
            self.update_controls()
            return
        port = self.ports.currentData()
        if not port:
            port = self.ports.currentText().strip().split(" — ")[0]
        if not port:
            self.notice.setText("请输入串口名称，例如 COM7。")
            return
        self.worker = SerialWorker(port, self)
        self.communication_error = False
        self.worker.connection.connect(self.on_connection)
        self.worker.received.connect(self.on_received)
        self.worker.sent.connect(lambda line: self.append_log("TX →", line))
        self.worker.failure.connect(self.on_failure)
        self.worker.finished.connect(self.on_finished)
        self.running_axes.clear()
        self.pending_axes.clear()
        self.axis_status.clear()
        self.all_stop_pending = False
        self.reset_servos()
        self.render_status()
        self.worker.start()
        self.update_controls()

    def move(self, axis: str, direction: int):
        if (not self.connected or not self.worker or axis not in self.axis_status
                or axis in self.running_axes or axis in self.pending_axes or self.all_stop_pending):
            return
        panel = self.axis_controls[axis]
        panel.direction.setCurrentIndex(0 if direction > 0 else 1)
        command = move_command(axis, direction * panel.steps.value(), panel.speed.value())
        if not self.worker.submit(command):
            self.notice.setText("命令队列已满，请稍后重试。")
            return
        self.pending_axes[axis] = "MOVE"
        self.notice.setText(f"等待 Arduino 确认 {axis} 轴运行命令…")
        self.update_controls()

    def stop_motion(self, axis: str):
        if self.connected and self.worker:
            self.worker.submit(f"STOP {axis}")
            self.pending_axes[axis] = "STOP"
            self.notice.setText(f"{axis} 轴停止命令已提交，等待设备确认…")
            self.update_controls()

    @Slot()
    def stop_all_motion(self):
        if self.connected and self.worker:
            self.worker.submit("STOP ALL")
            self.servo_targets.clear()
            self.servo_requested.clear()
            self.pending_axes.clear()
            self.all_stop_pending = True
            self.notice.setText("全部停止命令已提交，等待设备确认…")
            self.update_controls()

    @Slot(bool, str)
    def on_connection(self, connected: bool, text: str):
        self.connected = connected
        self.connection_label.setText(text)
        self.append_log("SYS", text)
        if connected:
            self.notice.setText("三轴及 D12/D13 舵机固件已确认，可以控制。")
            for pin, angle in self.servo_status.items():
                self.servo_feedback[pin].setText(f"设备设定：{angle}°")
        else:
            for label in self.servo_feedback.values():
                label.setText("设备设定：—（未连接）")
        self.render_status()
        self.update_controls()

    @Slot(str)
    def on_failure(self, text: str):
        self.communication_error = True
        self.append_log("ERROR", text)
        self.notice.setText(f"连接错误：{text}")

    @Slot(str)
    def on_received(self, line: str):
        self.append_log("RX ←", line)
        servo = parse_servo_status(line)
        if servo:
            self.servo_status[servo.pin] = servo.angle
            if self.servo_requested.get(servo.pin) == servo.angle:
                self.servo_requested.pop(servo.pin, None)
            self.servo_feedback[servo.pin].setText(f"设备设定：{servo.angle}°" if self.connected else "设备设定：—（未连接）")
            if (servo.pin not in self.servo_targets and servo.pin not in self.servo_requested
                    and not self.servo_sliders[servo.pin].isSliderDown()):
                self.set_servo_slider(servo.pin, servo.angle)
            self.update_controls()
            return
        if line == "OK STOP_ALL":
            self.all_stop_pending = False
            self.pending_axes.clear()
            self.running_axes.clear()
            self.axis_status = {axis: replace(status, state="STOPPED") for axis, status in self.axis_status.items()}
            if not self.communication_error:
                self.notice.setText("X/Y/Z 已全部停止，计数随后更新。")
            self.render_status()
            self.update_controls()
            return
        if line.startswith("ERROR"):
            fields = dict(part.split("=", 1) for part in line.split()[1:] if "=" in part)
            if fields.get("servo") in SERVO_PINS:
                pin = fields["servo"]
                self.servo_requested.pop(pin, None)
                self.servo_targets.pop(pin, None)
                if pin in self.servo_status:
                    self.set_servo_slider(pin, self.servo_status[pin])
            elif fields.get("axis") in AXES:
                self.pending_axes.pop(fields["axis"], None)
            else:
                self.pending_axes.clear()
            self.notice.setText(f"设备拒绝命令：{line}")
            self.update_controls()
            return
        status = parse_status(line)
        if status is None:
            return
        self.axis_status[status.axis] = status
        if status.state == "RUNNING":
            self.running_axes.add(status.axis)
        else:
            self.running_axes.discard(status.axis)
        pending_kind = self.pending_axes.get(status.axis)
        if (pending_kind == "STOP" and status.state == "STOPPED") or (
            pending_kind == "MOVE" and (status.event in {"OK", "RUNNING", "DONE"} or status.state == "RUNNING")
        ):
            self.pending_axes.pop(status.axis, None)
        self.render_status()
        if self.communication_error:
            pass  # Preserve connection failure even if final best-effort STOP is acknowledged.
        elif status.reason == "LINK_TIMEOUT":
            self.notice.setText(f"{status.axis} 轴因心跳超时停止。请检查连接后重新运行。")
        elif status.event == "DONE":
            self.notice.setText(f"{status.axis} 轴运行完成；所有轴空闲后驱动器统一释放。")
        elif status.event == "STOPPED":
            self.notice.setText(f"{status.axis} 轴已停止；再次运行会开始新的步数任务。")
        elif status.event in {"OK", "RUNNING"}:
            self.notice.setText(f"{status.axis} 轴正在运行，可以随时点击该轴停止或停止全部步进。")
        self.update_controls()

    @Slot()
    def on_finished(self):
        worker = self.worker
        self.worker = None
        self.connected = False
        self.running_axes.clear()
        self.pending_axes.clear()
        self.all_stop_pending = False
        self.servo_targets.clear()
        self.servo_requested.clear()
        self.render_status()
        for panel in self.axis_controls.values():
            panel.state_label.setText("未知（已断开）")
        if worker:
            worker.deleteLater()
        self.update_controls()
        if self.closing:
            self.close()

    def closeEvent(self, event: QCloseEvent):
        if self.worker:
            self.closing = True
            self.worker.disconnect()
            self.servo_targets.clear()
            self.servo_requested.clear()
            self.connected = False
            self.connection_label.setText("正在停止并退出…")
            self.update_controls()
            event.ignore()  # Leave the event loop alive until QThread.finished.
        else:
            event.accept()

