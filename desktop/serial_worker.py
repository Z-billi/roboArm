"""All serial I/O lives in this thread; GUI calls only touch a protected queue."""
from collections import deque
from threading import Event, Lock
from time import monotonic

import serial
from PySide6.QtCore import QThread, Signal

from .protocol import AXES, SERVO_PINS, BAUD_RATE, parse_status, parse_servo_status


class SerialWorker(QThread):
    received = Signal(str)
    sent = Signal(str)
    connection = Signal(bool, str)
    failure = Signal(str)

    def __init__(self, port: str, parent=None):
        super().__init__(parent)
        self.port = port
        self._queue: deque[str] = deque()
        self._lock = Lock()
        self._quit = Event()

    def submit(self, command: str):
        with self._lock:
            if self._quit.is_set():
                return False
            if command == "STOP ALL":
                self._queue.clear()
                self._queue.appendleft(command)
            elif command.startswith("STOP "):
                axis = command.split()[1]
                # Preserve stops/moves for other axes; cancel this axis's unsent commands.
                self._queue = deque(item for item in self._queue if item not in {command, f"STATUS {axis}"}
                                    and not item.startswith(f"MOVE {axis} "))
                if "STOP ALL" not in self._queue:
                    self._queue.appendleft(command)
            elif command.startswith("SERVO "):
                if "STOP ALL" in self._queue:
                    return False
                prefix = " ".join(command.split()[:2]) + " "
                self._queue = deque(item for item in self._queue if not item.startswith(prefix))
                if len(self._queue) >= 8:
                    return False
                self._queue.append(command)
            elif len(self._queue) < 8:
                self._queue.append(command)
            else:
                return False
            return True

    def disconnect(self):
        with self._lock:
            self._queue.clear()
            self._quit.set()

    def run(self):
        port = None
        ready = False
        buffer = bytearray()
        try:
            self.connection.emit(False, f"正在打开 {self.port}…")
            port = serial.Serial(self.port, BAUD_RATE, timeout=0.02, write_timeout=0.2)
            self.connection.emit(False, "等待 UNO 复位并确认固件…")
            # Opening UNO commonly toggles DTR and resets the bootloader.
            if self._quit.wait(2.0):
                return
            port.reset_input_buffer()

            def send(command: str):
                payload = (command + "\n").encode("ascii")
                if port.write(payload) != len(payload):
                    raise serial.SerialException("串口命令未完整写入")
                if command != "PING":
                    self.sent.emit(command)

            deadline = monotonic() + 4.0
            next_init = 0.0
            next_ping = 0.0
            stopped_axes = set()
            known_servos = set()
            stop_all_ack = False
            last_reply = monotonic()
            while not self._quit.is_set():
                now = monotonic()
                if not ready:
                    if now >= deadline:
                        raise serial.SerialException("未收到三轴固件确认及 D12/D13 舵机状态，请重新烧录新版 roboarm_x.ino")
                    if now >= next_init:
                        send("STOP ALL")
                        send("STATUS")
                        send("SERVO_STATUS")
                        next_init = now + 0.5
                else:
                    with self._lock:
                        command = self._queue.popleft() if self._queue else None
                    if command:
                        send(command)
                    if now >= next_ping:
                        send("PING")
                        next_ping = now + 0.3
                    if now - last_reply > 2.0:
                        raise serial.SerialException("设备响应超时，已请求停止；请检查 USB 连接")

                chunk = port.read(min(max(port.in_waiting, 1), 512))
                buffer.extend(chunk)
                if len(buffer) > 4096:
                    raise serial.SerialException("设备返回的串口数据过长或未换行")
                while b"\n" in buffer:
                    raw, _, tail = buffer.partition(b"\n")
                    buffer = bytearray(tail)
                    line = raw.decode("ascii", errors="replace").strip()
                    if not line:
                        continue
                    status = parse_status(line)
                    servo_status = parse_servo_status(line)
                    if status or servo_status or line == "OK PING":
                        last_reply = monotonic()
                    if not ready:
                        if line == "OK STOP_ALL":
                            stop_all_ack = True
                        if status and status.state == "STOPPED":
                            stopped_axes.add(status.axis)
                        if servo_status:
                            known_servos.add(servo_status.pin)
                    if not ready and stop_all_ack and stopped_axes == set(AXES) and known_servos == set(SERVO_PINS):
                        ready = True
                        next_ping = 0.0
                        self.connection.emit(True, f"已连接 {self.port} · {BAUD_RATE} baud")
                    if line != "OK PING":
                        self.received.emit(line)
        except (serial.SerialException, OSError, ValueError) as exc:
            self.failure.emit(str(exc))
        finally:
            if port is not None and port.is_open:
                try:
                    # Best effort; firmware watchdog also stops if the link is lost.
                    payload = b"STOP ALL\n"
                    port.write(payload)
                    self.sent.emit("STOP ALL (断开连接)")
                    end = monotonic() + 0.25
                    while monotonic() < end:
                        line = port.readline().decode("ascii", errors="replace").strip()
                        if line:
                            self.received.emit(line)
                        if line == "OK STOP_ALL":
                            break
                except (serial.SerialException, OSError):
                    pass
                finally:
                    try:
                        port.close()
                    except (serial.SerialException, OSError):
                        pass
            self.connection.emit(False, "未连接")
