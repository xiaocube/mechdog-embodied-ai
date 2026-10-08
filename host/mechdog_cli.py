#!/usr/bin/env python3
"""
MechDog 控制库（Mac 端）— 通过 USB 串口 或 Wi-Fi(TCP) 向 ESP32 上的 mechdog_server.py 发送命令

用法（串口）:
  python3 mechdog_cli.py --cmd "F 80"
  python3 mechdog_cli.py --port /dev/cu.usbserial-XXX --cmd "SONAR"

用法（Wi-Fi/TCP）:
  python3 mechdog_cli.py --host 192.168.1.50 --cmd "POSE_SIT;POSE_DEFAULT"
  python3 mechdog_cli.py --host mechdog.local --cmd "ping"

批量：分号或 && 分隔多条命令，一次调用完成多个动作。
"""
import argparse
import glob
import socket
import sys
import time

try:
    import serial
except ImportError:
    serial = None

DEFAULT_BAUD = 115200
DEFAULT_TCP_PORT = 5000
TIMEOUT = 3.0
VALID_CMDS = {
    "PING", "F", "B", "L", "R", "M", "STOP", "POSE_DEFAULT", "POSE_SIT", "POSE_LIE",
    "HEIGHT", "TILT", "MARCH", "SPEED", "ACTION", "STABLE", "SONAR",
}


def find_port():
    """自动探测第一个 USB 串口设备"""
    candidates = sorted(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.wchusbserial*")
                        + glob.glob("/dev/cu.SLAB_USBtoUART*"))
    if not candidates:
        sys.exit("未找到串口设备。请确认: ①机器狗已USB连接Mac ②CP210x/CH340驱动已装 ③ls /dev/cu.* 能看到串口")
    return candidates[0]


class Transport:
    """封装串口或 TCP 两种传输，对外统一 send/drain/close"""

    def __init__(self, host=None, tcp_port=DEFAULT_TCP_PORT, serial_port=None):
        self.host = host
        self.sock = None
        self.ser = None
        if host:
            try:
                self.sock = socket.create_connection((host, tcp_port), timeout=TIMEOUT)
                self.sock.settimeout(0.2)
            except Exception as e:
                sys.exit(f"无法连接机器狗 Wi-Fi {host}:{tcp_port}: {e}")
        else:
            if serial is None:
                sys.exit("缺少 pyserial，请先运行: pip3 install pyserial")
            p = serial_port or find_port()
            try:
                self.ser = serial.Serial(p, DEFAULT_BAUD, timeout=TIMEOUT)
            except serial.SerialException as e:
                sys.exit(f"无法打开串口 {p}: {e}")

    def send(self, data: bytes):
        if self.sock:
            self.sock.sendall(data)
        else:
            self.ser.write(data)

    def drain(self, settle=0.05):
        """读取当前所有可用输出"""
        out = b""
        try:
            if self.sock:
                while True:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        break
                    out += chunk
                    if len(chunk) < 4096:
                        break
                    time.sleep(settle)
            else:
                while self.ser.in_waiting:
                    chunk = self.ser.read(self.ser.in_waiting)
                    out += chunk
                    time.sleep(settle)
        except (socket.timeout, BlockingIOError):
            pass
        except serial.SerialTimeoutException:
            pass
        except Exception:
            pass
        return out

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        elif self.ser:
            try:
                self.ser.close()
            except Exception:
                pass


def run(transport, cmds, wait=1.0, verbose=True):
    """顺序发送多条命令，统一返回合并输出"""
    out = b""
    for cmd in cmds:
        cmd = cmd.strip()
        if not cmd:
            continue
        if verbose:
            # 日志行不打印 IP/串口路径数字，避免 agent 把地址数字误解析成距离/参数
            print(f"[→] mechdog <- {cmd}")
        transport.send((cmd + "\n").encode())
        time.sleep(wait)
        out += transport.drain()
    text = out.decode(errors="replace").strip()
    if text:
        print(f"[←] {text}")
    return text


def main():
    ap = argparse.ArgumentParser(description="MechDog 控制（Mac 端，串口或 Wi-Fi）")
    ap.add_argument("--port", default=None, help="串口，如 /dev/cu.usbserial-0001（缺省自动探测）")
    ap.add_argument("--host", default=None,
                    help="机器狗 Wi-Fi 地址，如 192.168.1.50 或 mechdog.local（指定后走 TCP 而非串口）")
    ap.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT, help="TCP 端口（默认 5000）")
    ap.add_argument("--cmd", required=True, help="命令，如 'F 80' / 'SONAR' / 'POSE_SIT;POSE_DEFAULT'")
    ap.add_argument("--wait", type=float, default=1.0, help="每条命令发送后等待秒数（动作执行时长）")
    args = ap.parse_args()

    cmd = args.cmd.strip().upper()
    parts = [p.strip() for p in cmd.replace("&&", ";").split(";") if p.strip()]
    if not parts:
        sys.exit("无效命令: 空")
    for p in parts:
        if p.split()[0] not in VALID_CMDS:
            sys.exit(f"无效命令: {p}。可用: {sorted(VALID_CMDS)}")

    t = Transport(host=args.host, tcp_port=args.tcp_port, serial_port=args.port)
    try:
        run(t, parts, wait=args.wait)
    finally:
        t.close()


if __name__ == "__main__":
    main()
