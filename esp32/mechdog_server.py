# MechDog 指令接收程序（MicroPython / ESP32 端）— 支持 USB 串口 + Wi-Fi(TCP) 双通道
# 作用：监听命令（串口 stdin 或 TCP 5000 端口），调用 HW_MechDog 库执行动作
# 安装：用 Hiwonder Python Editor 或 mpremote 上传本文件为 main.py（先备份原 main.py！）
#
# 命令协议（每行一条，\n 结尾）：
#   ping / F <mm> / B <mm> / L <deg> / R <deg> / M <mm> <deg> / STOP
#   POSE_DEFAULT / POSE_SIT / POSE_LIE / HEIGHT <mm> / TILT <pitch> <roll>
#   MARCH / SPEED <0-100> / ACTION <n|name> / STABLE <on|off> / SONAR
import sys
import time
import select
import network
import socket as _socket
from HW_MechDog import MechDog

# ================= Wi-Fi 配置（填写你的家庭/热点 Wi-Fi，仅支持 2.4GHz） =================
WIFI_SSID = "私人以太之光"
WIFI_PASS = "PP20030317"
TCP_PORT = 5000
WIFI_CONNECT_TIMEOUT_S = 20
# ====================================================================================

SONAR_MIN_CM = 20   # 超声波避障阈值：小于该距离自动停车
STRAIGHT_COMP_DEG = 3   # 直线补偿：前进时叠加的右转角度（度），抵消"前进向左走歪"的机械偏差（0=不补偿）
SPEED_SLOW = 30    # SPEED 命令默认值（0-100），越小越慢

# 官方预置动作组（出厂 main.py 动作表，注意官方拼写 sit_dowm）
ACTIONS = {
    "1": "left_foot_kick",    "2": "right_foot_kick", "3": "stand_four_legs",
    "4": "sit_dowm",          "5": "go_prone",        "6": "stand_two_legs",
    "7": "handshake",         "8": "scrape_a_bow",    "9": "nodding_motion",
    "10": "boxing",           "11": "stretch_oneself","12": "pee",
    "13": "press_up",         "14": "rotation_pitch", "15": "rotation_roll",
}


def get_sonar():
    """读取发光超声波距离（cm）。官方模块为 I2C 发光超声波 I2CSonar(IIC(1))；
    未安装模块或读取失败返回 -1。"""
    try:
        import Hiwonder_IIC
        s = Hiwonder_IIC.I2CSonar(Hiwonder_IIC.IIC(1))
        return s.getDistance()
    except Exception:
        return -1


def execute(cmd_line):
    parts = cmd_line.strip().upper().split()
    if not parts:
        return "ERR: empty"
    c = parts[0]
    try:
        if c == "PING":
            return "pong"
        if c == "F":
            mm = int(parts[1]) if len(parts) > 1 else 60
            mm = max(1, min(mm, 120))
            # 直线补偿：前进时叠加微小右转角（负=右转），抵消机械左偏
            mechdog.move(mm, -STRAIGHT_COMP_DEG)
            return "OK F %d" % mm
        if c == "B":
            mm = int(parts[1]) if len(parts) > 1 else 50
            mm = max(1, min(mm, 120))
            mechdog.move(-mm, 0)
            return "OK B %d" % mm
        if c == "L":
            d = int(parts[1]) if len(parts) > 1 else 20
            d = max(1, min(d, 90))
            mechdog.move(50, d)
            return "OK L %d" % d
        if c == "R":
            d = int(parts[1]) if len(parts) > 1 else 20
            d = max(1, min(d, 90))
            mechdog.move(50, -d)
            return "OK R %d" % d
        if c == "M":
            mm = int(parts[1]) if len(parts) > 1 else 60
            deg = int(parts[2]) if len(parts) > 2 else 0
            mechdog.move(mm, deg)
            return "OK M %d %d" % (mm, deg)
        if c == "STOP":
            mechdog.move(0, 0)
            return "OK STOP"
        if c == "POSE_DEFAULT":
            mechdog.set_default_pose()
            return "OK POSE_DEFAULT"
        if c == "POSE_SIT":
            mechdog.action_run("sit_dowm")
            return "OK POSE_SIT"
        if c == "POSE_LIE":
            mechdog.action_run("go_prone")
            return "OK POSE_LIE"
        if c == "HEIGHT":
            mm = int(parts[1]) if len(parts) > 1 else 10
            mm = max(-30, min(mm, 30))
            mechdog.transform([0, 0, mm], [0, 0, 0], 1000)
            return "OK HEIGHT %d" % mm
        if c == "TILT":
            p = int(parts[1]) if len(parts) > 1 else 0
            r = int(parts[2]) if len(parts) > 2 else 0
            p = max(-30, min(p, 30))
            r = max(-30, min(r, 30))
            # 实测确认：MechDog 库 transform 旋转参数实际顺序为 [roll, pitch, yaw]
            # （官方注释写 pitch 在前，与库实现不符）；且库的 roll 正值=向左倾
            # （与直觉相反）。此处做「顺序交换 + roll 取反」，保证协议
            # TILT <pitch> <roll>：第一个=前后倾(点头，+为前)，第二个=左右倾(+为右)。
            mechdog.transform([0, 0, 0], [-r, p, 0], 500)
            return "OK TILT %d %d" % (p, r)
        if c == "MARCH":
            mechdog.move(1, 0)  # 极小步幅 = 原地踏步
            return "OK MARCH (运行中，发 STOP 停止)"
        if c == "SPEED":
            v = int(parts[1]) if len(parts) > 1 else SPEED_SLOW
            v = max(0, min(v, 100))
            # 真调速：触地时间越大步频越慢（v=0→1000ms 很慢，v=100→500ms 正常）
            # 离地时间随速度略增（防慢速时顿挫），抬腿高度固定 30 适中
            touch = 1000 - v * 5
            lift = 150 + v
            mechdog.set_gait_params(lift, touch, 30)
            return "OK SPEED %d (touch=%dms)" % (v, touch)
        if c == "ACTION":
            n = parts[1] if len(parts) > 1 else "3"
            name = ACTIONS.get(n, n if n in ACTIONS.values() else None)
            if name is None:
                return "ERR: unknown action %s (可用 1-15 或动作名)" % n
            mechdog.action_run(name)
            return "OK ACTION %s (%s)" % (n, name)
        if c == "STABLE":
            on = parts[1] if len(parts) > 1 else "on"
            if on == "ON":
                mechdog.homeostasis(True)
            else:
                mechdog.homeostasis(False)
            return "OK STABLE %s" % on
        if c == "SONAR":
            d = get_sonar()
            return "SONAR %s cm" % (d if d >= 0 else "N/A")
        return "ERR: unknown %s" % c
    except Exception as e:
        return "ERR: %s" % e


def handle_line(line):
    """执行一行命令（含超声波避障），返回响应字符串"""
    line = line.strip()
    if not line:
        return None
    head = line.split()[0].upper()
    if head in ("F", "B", "L", "R", "M", "MARCH"):
        d = get_sonar()
        if 0 <= d < SONAR_MIN_CM:
            mechdog.move(0, 0)
            return "BLOCKED sonar=%dcm" % d
    return execute(line)


# ================= 初始化 =================
print("MechDog server ready.")
mechdog = MechDog()
mechdog.set_default_pose()
time.sleep(1)

# ---- Wi-Fi（STA 模式）----
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
if not wlan.isconnected():
    print("Connecting Wi-Fi %s..." % WIFI_SSID)
    try:
        wlan.connect(WIFI_SSID, WIFI_PASS)
    except Exception as e:
        print("Wi-Fi connect error: %s" % e)
    t0 = time.time()
    while not wlan.isconnected() and (time.time() - t0) < WIFI_CONNECT_TIMEOUT_S:
        time.sleep(0.2)
if wlan.isconnected():
    print("Wi-Fi OK, IP:", wlan.ifconfig()[0])
else:
    print("Wi-Fi FAILED (检查 SSID/密码/2.4GHz)；继续用 USB 串口")

# ---- TCP server ----
_srv = None
try:
    _srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    _srv.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    _srv.bind(("0.0.0.0", TCP_PORT))
    _srv.listen(1)
    _srv.setblocking(False)
    print("TCP ready :%d" % TCP_PORT)
except Exception as e:
    print("TCP init error: %s" % e)
    _srv = None

# ---- 主循环：同时轮询 USB 串口 stdin + TCP 连接 ----
_poller = select.poll()
_poller.register(sys.stdin, select.POLLIN)
if _srv:
    _poller.register(_srv, select.POLLIN)

_conn = None
_buf = b""

while True:
    try:
        _events = _poller.poll(20)  # 20ms 超时轮询
    except Exception:
        _events = []
    if _events:
        for _fd, _ev in _events:
            if _srv and _fd == _srv:
                # 新 TCP 连接
                try:
                    _conn, _addr = _srv.accept()
                    _conn.setblocking(False)
                    _poller.register(_conn, select.POLLIN)
                    _buf = b""
                    print("TCP client: %s" % str(_addr[0]))
                except Exception:
                    pass
            elif _conn is not None and _fd == _conn:
                # TCP 客户端数据
                try:
                    _data = _conn.recv(64)
                except Exception:
                    _data = b""
                if not _data:
                    # 客户端断开
                    try:
                        _poller.unregister(_conn)
                        _conn.close()
                    except Exception:
                        pass
                    _conn = None
                    _buf = b""
                else:
                    _buf += _data
                    while b"\n" in _buf:
                        _line, _, _buf = _buf.partition(b"\n")
                        _resp = handle_line(_line.decode("utf-8", "ignore"))
                        if _resp is not None:
                            try:
                                _conn.sendall((_resp + "\n").encode())
                            except Exception:
                                pass
            elif _fd == sys.stdin:
                # USB 串口命令
                _line = sys.stdin.readline()
                if _line:
                    _resp = handle_line(_line)
                    if _resp is not None:
                        print(_resp)
    # Wi-Fi 断线重连（每轮检查，开销小）
    if wlan.isconnected():
        try:
            if not wlan.isconnected():
                pass
        except Exception:
            pass
    else:
        try:
            wlan.connect(WIFI_SSID, WIFI_PASS)
        except Exception:
            pass
    time.sleep(0.02)
