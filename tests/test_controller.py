"""Run with unittest. Uses a fake serial device; never opens physical ports."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from desktop.main_window import MainWindow
from desktop.protocol import AXES, SERVO_PINS, move_command, parse_status, servo_command, parse_servo_status
from desktop.serial_worker import SerialWorker


def status_line(event="STATUS", state="IDLE", total=0, completed=0,
                direction="NONE", speed=200, reason="NONE", axis="X"):
    return (f"{event} {axis} state={state} dir={direction} total={total} completed={completed} "
            f"remaining={total - completed} speed={speed} reason={reason}")


class FakeSerial:
    """Fragmented replies and ACKs; no motor simulation or physical side effects."""
    instances = []
    silent = False
    fail_read = False
    supported_axes = AXES
    supported_servos = SERVO_PINS

    def __init__(self, *args, **kwargs):
        self.is_open = True
        self.buffer = bytearray()
        self.commands = []
        self.axes = {axis: dict(state="IDLE", total=0, completed=0, direction="NONE", speed=200)
                     for axis in self.supported_axes}
        self.servos = {pin: 90 for pin in self.supported_servos}
        self.instances.append(self)

    @property
    def in_waiting(self):
        return len(self.buffer)

    def reset_input_buffer(self):
        self.buffer.clear()

    def reply(self, line):
        if not self.silent:
            self.buffer.extend((line + "\r\n").encode("ascii"))

    def emit_status(self, event="STATUS", reason="NONE", axis="X"):
        self.reply(status_line(event=event, reason=reason, axis=axis, **self.axes[axis]))

    def write(self, data):
        command = data.decode("ascii").strip()
        self.commands.append(command)
        parts = command.split()
        if command == "STOP ALL":
            for values in self.axes.values():
                values["state"] = "STOPPED"
            self.reply("OK STOP_ALL")
        elif parts[0] == "STOP":
            axis = parts[1]
            self.axes[axis]["state"] = "STOPPED"
            self.emit_status("STOPPED", "USER", axis)
        elif command.startswith("STATUS"):
            for axis in ([parts[1]] if len(parts) == 2 else self.axes):
                self.emit_status(axis=axis)
        elif parts[0] == "SERVO_STATUS":
            for pin in ([parts[1]] if len(parts) == 2 else self.servos):
                self.reply(f"SERVO {pin} angle={self.servos[pin]}")
        elif parts[0] == "SERVO":
            pin, angle = parts[1], int(parts[2])
            self.servos[pin] = angle
            self.reply(f"OK SERVO {pin} angle={angle}")
        elif command == "PING":
            self.reply("OK PING")
        elif parts[0] == "MOVE":
            axis = parts[1]
            values = self.axes[axis]
            if values["state"] == "RUNNING":
                self.reply(f"ERROR axis={axis} code=BUSY")
            else:
                values.update(total=abs(int(parts[2])), completed=0,
                              direction="FORWARD" if int(parts[2]) > 0 else "REVERSE",
                              speed=int(parts[3]), state="RUNNING")
                self.emit_status("OK", axis=axis)
                self.emit_status("RUNNING", axis=axis)
        return len(data)

    def read(self, size=1):
        if self.fail_read:
            raise OSError("模拟 USB 断开")
        if not self.buffer:
            time.sleep(0.005)
            return b""
        # Deliberately split every line into small chunks.
        size = min(size, 7)
        data = bytes(self.buffer[:size])
        del self.buffer[:size]
        return data

    def readline(self):
        if b"\n" not in self.buffer:
            time.sleep(0.005)
            return b""
        line, _, tail = self.buffer.partition(b"\n")
        self.buffer = bytearray(tail)
        return bytes(line) + b"\n"

    def close(self):
        self.is_open = False


class ProtocolTests(unittest.TestCase):
    def test_servo_command_range_and_pins(self):
        self.assertEqual(servo_command("D12", 0), "SERVO D12 0")
        self.assertEqual(servo_command("D13", 180), "SERVO D13 180")
        for pin, angle in [("D11", 90), ("D12", -1), ("D13", 181), ("D12", 90.5), ("D13", True)]:
            with self.subTest(pin=pin, angle=angle), self.assertRaises(ValueError):
                servo_command(pin, angle)

    def test_servo_feedback_and_malformed_lines(self):
        result = parse_servo_status("OK SERVO D13 angle=180")
        self.assertEqual((result.pin, result.angle, result.acknowledged), ("D13", 180, True))
        self.assertEqual(parse_servo_status("SERVO D12 angle=0").angle, 0)
        for line in ["OK SERVO D11 angle=90", "SERVO D12 angle=181", "SERVO D13 angle=-1",
                     "SERVO D12 angle=bad", "SERVO D12 other=90", "SERVO D12", "OK PING"]:
            with self.subTest(line=line):
                self.assertIsNone(parse_servo_status(line))

    def test_signed_move_and_limits(self):
        self.assertEqual(move_command("X", -400, 500), "MOVE X -400 500")
        self.assertEqual(move_command("X", 1_000_000, 2000), "MOVE X 1000000 2000")
        for axis, steps, speed in [("A", 200, 200), ("X", 0, 200), ("X", 1000001, 200),
                                   ("X", -1000001, 200), ("X", 1, 0), ("X", 1, 2001)]:
            with self.subTest(axis=axis, steps=steps, speed=speed), self.assertRaises(ValueError):
                move_command(axis, steps, speed)

    def test_xyz_command_and_status(self):
        for axis in AXES:
            self.assertEqual(move_command(axis, -400, 500), f"MOVE {axis} -400 500")
            self.assertEqual(parse_status(status_line(axis=axis)).axis, axis)

    def test_stopped_retains_progress(self):
        result = parse_status(status_line("STOPPED", "STOPPED", 10000, 275, "REVERSE", 200, "USER"))
        self.assertEqual((result.completed, result.remaining, result.direction), (275, 9725, "REVERSE"))

    def test_malformed_status_is_ignored(self):
        for line in ["OK PING", "READY protocol=1 axes=X", "ERROR code=BUSY", "STATUS X state=IDLE",
                     status_line().replace("remaining=0", "remaining=7"),
                     status_line().replace("total=0", "total=-1"),
                     status_line().replace("dir=NONE", "dir=BAD"),
                     status_line().replace("speed=200", "speed=nan")]:
            with self.subTest(line=line):
                self.assertIsNone(parse_status(line))


class GuiSerialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        FakeSerial.instances.clear()
        FakeSerial.silent = False
        FakeSerial.fail_read = False
        FakeSerial.supported_axes = AXES
        FakeSerial.supported_servos = SERVO_PINS
        self.patcher = patch("desktop.serial_worker.serial.Serial", FakeSerial)
        self.patcher.start()
        self.window = MainWindow()
        self.x = self.window.axis_controls["X"]
        self.y = self.window.axis_controls["Y"]
        self.z = self.window.axis_controls["Z"]

    def wait_for(self, predicate, timeout=4.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.005)
        self.fail("等待条件超时")

    def connect_device(self):
        self.window.ports.setEditText("COM7")
        self.window.toggle_connection()
        self.wait_for(lambda: self.window.connected)
        return FakeSerial.instances[-1]

    def tearDown(self):
        if self.window.worker:
            self.window.worker.disconnect()
            self.wait_for(lambda: self.window.worker is None)
        self.window.close()
        self.app.processEvents()
        self.patcher.stop()

    def test_handshake_move_stop_and_disconnect(self):
        self.assertFalse(self.x.run_button.isEnabled())
        device = self.connect_device()
        self.assertTrue(self.x.run_button.isEnabled())
        self.assertEqual(device.commands[:2], ["STOP ALL", "STATUS"])
        self.x.steps.setValue(10000)
        self.x.reverse.click()
        self.assertFalse(self.x.run_button.isEnabled())
        self.wait_for(lambda: "X" in self.window.running_axes)
        self.assertEqual(self.x.direction_label.text(), "反转 (−)")
        self.assertIn("MOVE X -10000 200", device.commands)
        self.x.stop.click()
        self.wait_for(lambda: "X" not in self.window.running_axes and "X" not in self.window.pending_axes)
        self.assertEqual(self.x.remaining_label.text(), "10000")
        self.window.toggle_connection()
        self.wait_for(lambda: self.window.worker is None)
        self.assertFalse(device.is_open)
        self.assertEqual(device.commands[-1], "STOP ALL")

    def test_servos_initial_state_no_automatic_move_and_endpoints(self):
        self.assertEqual([slider.value() for slider in self.window.servo_sliders.values()], [90, 90])
        self.assertFalse(self.window.servo_sliders["D12"].isEnabled())
        device = self.connect_device()
        self.assertTrue(self.window.servo_sliders["D12"].isEnabled())
        self.assertFalse(any(command.startswith("SERVO ") for command in device.commands))
        self.window.servo_sliders["D12"].setValue(0)
        self.window.servo_sliders["D13"].setValue(180)
        self.window.flush_servo_targets()
        self.wait_for(lambda: self.window.servo_status == {"D12": 0, "D13": 180})
        self.assertEqual(device.servos, {"D12": 0, "D13": 180})
        self.assertEqual(self.window.servo_values["D12"].text(), "0°")
        self.assertEqual(self.window.servo_feedback["D13"].text(), "设备设定：180°")

    def test_servo_updates_keep_only_latest_and_stop_has_priority(self):
        worker = SerialWorker("COM7")
        worker.submit("SERVO D12 0")
        worker.submit("SERVO D13 30")
        worker.submit("SERVO D12 180")
        worker.submit("STOP X")
        with worker._lock:
            self.assertEqual(list(worker._queue), ["STOP X", "SERVO D13 30", "SERVO D12 180"])
        worker.submit("STOP ALL")
        self.assertFalse(worker.submit("SERVO D12 20"))
        with worker._lock:
            self.assertEqual(list(worker._queue), ["STOP ALL"])

    def test_stale_servo_feedback_does_not_pull_slider_back(self):
        self.connect_device()
        self.window.servo_timer.stop()
        self.window.servo_sliders["D12"].setValue(120)
        self.window.on_received("SERVO D12 angle=90")
        self.assertEqual(self.window.servo_sliders["D12"].value(), 120)
        self.window.flush_servo_targets()
        self.window.on_received("SERVO D12 angle=90")
        self.assertEqual(self.window.servo_sliders["D12"].value(), 120)
        self.wait_for(lambda: self.window.servo_status["D12"] == 120)
        self.assertNotIn("D12", self.window.servo_requested)

    def test_stepper_stop_cancels_staged_servo_angles_and_holds_last_command(self):
        device = self.connect_device()
        self.window.servo_timer.stop()
        self.window.servo_sliders["D12"].setValue(45)
        self.window.flush_servo_targets()
        self.wait_for(lambda: self.window.servo_status["D12"] == 45)
        self.window.servo_sliders["D12"].setValue(120)
        self.window.stop_all_motion()
        self.assertFalse(self.window.servo_sliders["D12"].isEnabled())
        self.wait_for(lambda: not self.window.all_stop_pending)
        self.window.flush_servo_targets()
        self.assertNotIn("SERVO D12 120", device.commands)
        self.assertEqual(device.servos["D12"], 45)

    def test_servo_controls_work_while_stepper_runs(self):
        device = self.connect_device()
        self.x.forward.click()
        self.wait_for(lambda: "X" in self.window.running_axes)
        self.assertTrue(self.window.servo_sliders["D13"].isEnabled())
        self.window.servo_sliders["D13"].setValue(110)
        self.window.flush_servo_targets()
        self.wait_for(lambda: self.window.servo_status["D13"] == 110)
        self.assertEqual(device.axes["X"]["state"], "RUNNING")

    def test_missing_servo_support_requires_firmware_update(self):
        FakeSerial.supported_servos = ()
        self.window.toggle_connection()
        self.wait_for(lambda: self.window.worker is None, timeout=7)
        self.assertFalse(self.window.connected)
        self.assertFalse(self.window.servo_sliders["D12"].isEnabled())
        self.assertIn("D12/D13", self.window.notice.text())

    def test_servo_error_does_not_cancel_stepper_pending(self):
        self.connect_device()
        self.window.pending_axes["Y"] = "MOVE"
        self.window.servo_requested["D12"] = 120
        self.window.on_received("ERROR servo=D12 code=ANGLE_RANGE")
        self.assertEqual(self.window.pending_axes, {"Y": "MOVE"})
        self.assertNotIn("D12", self.window.servo_requested)

    def test_stop_cancels_unsent_moves(self):
        worker = SerialWorker("COM7")
        worker.submit("MOVE X 200 200")
        worker.submit("STATUS X")
        worker.submit("STOP X")
        with worker._lock:
            self.assertEqual(list(worker._queue), ["STOP X"])

    def test_selective_stop_preserves_other_axis_commands(self):
        worker = SerialWorker("COM7")
        worker.submit("MOVE X 200 200")
        worker.submit("MOVE Y 400 200")
        worker.submit("STOP Z")
        worker.submit("STOP X")
        with worker._lock:
            self.assertEqual(list(worker._queue), ["STOP X", "STOP Z", "MOVE Y 400 200"])
        worker.submit("STOP ALL")
        with worker._lock:
            self.assertEqual(list(worker._queue), ["STOP ALL"])

    def test_three_panels_run_independently_and_stop_only_their_axis(self):
        self.window.show()
        device = self.connect_device()
        for panel in (self.x, self.y, self.z):
            self.assertTrue(panel.isVisible())
            self.assertTrue(panel.run_button.isEnabled())
        self.x.steps.setValue(300)
        self.x.speed.setValue(100)
        self.y.steps.setValue(400)
        self.y.speed.setValue(250)
        self.z.steps.setValue(600)
        self.z.speed.setValue(500)
        self.z.direction.setCurrentIndex(1)
        self.x.forward.click()
        # A pending X command must not lock Y or Z.
        self.assertFalse(self.x.run_button.isEnabled())
        self.assertTrue(self.y.run_button.isEnabled())
        self.assertTrue(self.z.run_button.isEnabled())
        self.y.reverse.click()
        self.z.run_button.click()
        self.wait_for(lambda: self.window.running_axes == set(AXES))
        self.assertIn("MOVE X 300 100", device.commands)
        self.assertIn("MOVE Y -400 250", device.commands)
        self.assertIn("MOVE Z -600 500", device.commands)
        self.assertEqual([p.steps.value() for p in (self.x, self.y, self.z)], [300, 400, 600])
        self.y.stop.click()
        self.wait_for(lambda: "Y" not in self.window.running_axes and "Y" not in self.window.pending_axes)
        self.assertEqual(self.window.running_axes, {"X", "Z"})
        self.assertEqual(self.y.state_label.text(), "已停止")
        self.assertEqual(self.z.state_label.text(), "运行中")
        self.assertEqual(self.y.remaining_label.text(), "400")
        self.assertTrue(self.y.run_button.isEnabled())
        self.assertFalse(self.x.run_button.isEnabled())
        self.assertFalse(self.z.run_button.isEnabled())
        self.window.stop_all.click()
        for panel in (self.x, self.y, self.z):
            self.assertFalse(panel.run_button.isEnabled())
        self.wait_for(lambda: not self.window.running_axes and not self.window.all_stop_pending)
        for axis, panel in self.window.axis_controls.items():
            self.assertEqual(device.axes[axis]["state"], "STOPPED")
            self.assertTrue(panel.run_button.isEnabled())

    def test_interleaved_axis_feedback_updates_only_its_panel(self):
        self.connect_device()
        self.window.on_received(status_line("RUNNING", "RUNNING", 1000, 100, "FORWARD", axis="X"))
        self.window.on_received(status_line("RUNNING", "RUNNING", 500, 50, "REVERSE", axis="Y"))
        self.window.on_received(status_line("RUNNING", "RUNNING", 800, 400, "FORWARD", 300, axis="Z"))
        self.window.on_received(status_line("DONE", "DONE", 1000, 1000, "FORWARD", axis="X"))
        self.assertEqual(self.x.state_label.text(), "已完成")
        self.assertEqual(self.x.completed_label.text(), "1000")
        self.assertEqual(self.x.progress.value(), 100)
        self.assertEqual(self.y.completed_label.text(), "50")
        self.assertEqual(self.y.remaining_label.text(), "450")
        self.assertEqual(self.y.direction_label.text(), "反转 (−)")
        self.assertEqual(self.y.progress.value(), 10)
        self.assertEqual(self.z.completed_label.text(), "400")
        self.assertEqual(self.z.actual_speed.text(), "300 脉冲/秒")
        self.assertEqual(self.z.progress.value(), 50)
        self.assertEqual(self.window.running_axes, {"Y", "Z"})
        self.assertTrue(self.x.run_button.isEnabled())
        self.assertFalse(self.y.run_button.isEnabled())
        self.assertFalse(self.z.run_button.isEnabled())

    def test_axis_error_only_clears_its_pending_command(self):
        self.connect_device()
        self.window.pending_axes = {"Y": "MOVE", "Z": "MOVE"}
        self.window.on_received("ERROR axis=Y code=BUSY")
        self.assertEqual(self.window.pending_axes, {"Z": "MOVE"})

    def test_missing_axes_never_enable_motion(self):
        FakeSerial.supported_axes = ("X",)
        self.window.toggle_connection()
        self.wait_for(lambda: self.window.worker is None, timeout=7)
        self.assertFalse(self.window.connected)
        for panel in self.window.axis_controls.values():
            self.assertFalse(panel.run_button.isEnabled())
        self.assertIn("三轴固件确认", self.window.notice.text())

    def test_completion_updates_counts(self):
        self.connect_device()
        self.window.on_received(status_line("DONE", "DONE", 400, 400, "FORWARD", 500))
        self.assertEqual(self.x.completed_label.text(), "400")
        self.assertEqual(self.x.remaining_label.text(), "0")
        self.assertEqual(self.x.progress.value(), 100)
        self.assertTrue(self.x.run_button.isEnabled())

    def test_serial_loss_disables_motion(self):
        self.connect_device()
        FakeSerial.fail_read = True
        self.wait_for(lambda: self.window.worker is None)
        for panel in self.window.axis_controls.values():
            for control in (panel.stop, panel.run_button, panel.forward, panel.reverse, panel.steps, panel.speed):
                self.assertFalse(control.isEnabled())
            self.assertEqual(panel.completed_label.text(), "—")
        self.assertIn("模拟 USB 断开", self.window.notice.text())

    def test_no_reply_disconnects_instead_of_hanging(self):
        self.connect_device()
        FakeSerial.silent = True
        self.wait_for(lambda: self.window.worker is None, timeout=3.5)
        self.assertIn("响应超时", self.window.notice.text())

    def test_busy_error_clears_pending_but_keeps_running(self):
        self.connect_device()
        self.window.running_axes.add("X")
        self.window.pending_axes["X"] = "MOVE"
        self.window.on_received("ERROR code=BUSY")
        self.assertFalse(self.window.pending_axes)
        self.assertFalse(self.x.run_button.isEnabled())

    def test_close_while_connected_stops_thread(self):
        device = self.connect_device()
        self.window.close()
        self.wait_for(lambda: self.window.worker is None)
        self.assertFalse(device.is_open)
        self.assertEqual(device.commands[-1], "STOP ALL")


if __name__ == "__main__":
    unittest.main()
