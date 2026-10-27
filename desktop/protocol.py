"""Protocol v3: X/Y/Z steppers and D12/D13 positional servos, ASCII lines."""
from dataclasses import dataclass

AXES = ("X", "Y", "Z")
SERVO_PINS = ("D12", "D13")
INITIAL_SERVO_ANGLE = 90
MAX_STEPS = 1_000_000
MAX_SPEED = 2000
BAUD_RATE = 115200


def servo_command(pin: str, angle: int) -> str:
    if pin not in SERVO_PINS:
        raise ValueError("舵机只支持 D12、D13")
    if type(angle) is not int or not 0 <= angle <= 180:
        raise ValueError("舵机角度必须是 0～180 的整数")
    return f"SERVO {pin} {angle}"


@dataclass(frozen=True)
class ServoStatus:
    pin: str
    angle: int
    acknowledged: bool


def parse_servo_status(line: str) -> ServoStatus | None:
    parts = line.split()
    acknowledged = bool(parts and parts[0] == "OK")
    if acknowledged:
        parts = parts[1:]
    if len(parts) != 3 or parts[0] != "SERVO" or parts[1] not in SERVO_PINS:
        return None
    try:
        key, angle = parts[2].split("=", 1)
        value = int(angle)
        if key != "angle" or not 0 <= value <= 180:
            return None
        return ServoStatus(parts[1], value, acknowledged)
    except ValueError:
        return None


def move_command(axis: str, steps: int, speed: int) -> str:
    if axis not in AXES:
        raise ValueError("只支持 X、Y、Z 轴")
    if not 1 <= abs(steps) <= MAX_STEPS:
        raise ValueError("步数必须在 1～1,000,000 之间")
    if not 1 <= speed <= MAX_SPEED:
        raise ValueError("速度必须在 1～2,000 脉冲/秒之间")
    return f"MOVE {axis} {steps} {speed}"


@dataclass(frozen=True)
class AxisStatus:
    event: str
    axis: str
    state: str
    direction: str
    total: int
    completed: int
    remaining: int
    speed: int
    reason: str


def parse_status(line: str) -> AxisStatus | None:
    parts = line.split()
    if len(parts) < 3 or parts[0] not in {"OK", "STATUS", "RUNNING", "STOPPED", "DONE"}:
        return None
    if parts[1] not in AXES:
        return None
    try:
        fields = dict(part.split("=", 1) for part in parts[2:])
        result = AxisStatus(
            parts[0], parts[1], fields["state"], fields["dir"],
            int(fields["total"]), int(fields["completed"]),
            int(fields["remaining"]), int(fields["speed"]), fields["reason"],
        )
        if result.state not in {"IDLE", "RUNNING", "STOPPED", "DONE"}:
            return None
        if result.direction not in {"NONE", "FORWARD", "REVERSE"}:
            return None
        if not (0 <= result.completed <= result.total <= MAX_STEPS):
            return None
        if result.remaining != result.total - result.completed or not 1 <= result.speed <= MAX_SPEED:
            return None
        return result
    except (KeyError, ValueError):
        return None
