# MechDog Embodied AI（四足机器狗具身智能）

基于幻尔（Hiwonder）MechDog 四足机器狗 + AI Agent 的具身智能探索项目：通过大语言模型将自然语言指令直接转化为机器狗动作，探索"语言 → 动作"的端到端控制范式。

<div align="center">
  <img src="assets/mechdog-photo.jpg" alt="MechDog 机器狗" width="480"/>
</div>

## ✨ 特性

- **自然语言控制**：AI Agent 接收指令后直接驱动 8 舵机完成前进/后退/转向/坐下/趴下/姿态调整/动作组
- **双端架构**：Mac 控制端（Python CLI） + ESP32 指令接收固件（MicroPython），USB 串口或 WiFi 通信
- **超声波避障**：移动命令前自动测距，<20cm 自动停车
- **无线化改造**：ESP32 通过 WiFi 接收指令，脱离 USB 线缆束缚
- **VLA 探索**：验证视觉语言动作模型直控舵机的可行性（实验性）

## 🏗️ 架构

```mermaid
flowchart LR
    U[用户 / AI Agent] -->|自然语言| CLI[mechdog_cli.py<br/>Mac 控制端]
    CLI -->|USB 串口 / WiFi| FW[mechdog_server.py<br/>ESP32 固件]
    FW --> LIB[HW_MechDog 库]
    LIB --> S1[8× 舵机]
    LIB --> SR[超声波传感器]

    FW -->|BLOCKED &lt;20cm| FW
```

## 🚀 快速开始

### 1. 烧录 ESP32 固件

将 [`esp32/mechdog_server.py`](esp32/mechdog_server.py) 上传到机器狗 ESP32（MicroPython），覆盖 `main.py`（**先备份原文件**）。用 Hiwonder Python Editor 或 mpremote 均可。

### 2. 安装 Mac 端依赖

```bash
pip3 install pyserial
```

### 3. 连接并测试

```bash
# 自动探测串口并 ping
python3 host/mechdog_cli.py --cmd "ping"        # → pong

# 前进 80mm
python3 host/mechdog_cli.py --cmd "F 80"

# 坐下 → 站立 → 握手（一次调用）
python3 host/mechdog_cli.py --cmd "POSE_SIT;POSE_DEFAULT;ACTION 7" --wait 2

# 超声波测距
python3 host/mechdog_cli.py --cmd "SONAR"
```

## 📜 命令协议

| 命令 | 含义 | 示例 |
|---|---|---|
| `ping` | 连通测试 | `ping` |
| `F <mm>` / `B <mm>` | 前进/后退（1~120） | `F 80` |
| `L <deg>` / `R <deg>` | 左转/右转（1~90） | `L 20` |
| `STOP` | 停止 | `STOP` |
| `POSE_DEFAULT` / `POSE_SIT` / `POSE_LIE` | 站立/坐下/趴下 | `POSE_SIT` |
| `HEIGHT <mm>` | 机身升降（-30~30） | `HEIGHT 20` |
| `TILT <pitch> <roll>` | 俯仰/横滚（-30~30） | `TILT 15 0` |
| `ACTION <n>` | 预置动作组（1~15） | `ACTION 7` |
| `SPEED <0-100>` | 步态速度 | `SPEED 60` |
| `SONAR` | 超声波测距 | `SONAR` |

## 🧩 接入 AI Agent

在 OpenClaw / 任意 Agent 框架中注册该 CLI 为工具（Skill）：

```markdown
# skills/mechdog/SKILL.md
## 执行准则
1. 收到指令后直接运行 CLI，不要重复确认
2. 连续动作用分号合并为一次调用
3. 执行完一句话汇报
```

Agent 即获得"让机器狗前进/坐下/握手"等具身能力。完整技能文档见 [`docs/mechdog-skill.md`](docs/mechdog-skill.md)。

## 📁 项目结构

```
mechdog-embodied-ai/
├── host/
│   └── mechdog_cli.py      # Mac 端控制 CLI（pyserial）
├── esp32/
│   └── mechdog_server.py   # ESP32 MicroPython 固件（需烧录）
├── docs/
│   └── mechdog-skill.md    # Agent 技能接入文档
└── assets/
    └── mechdog-photo.jpg   # 实拍照片
```

## ⚠️ 已知坑（实测记录）

1. **`transform` 旋转参数顺序是 `[roll, pitch, yaw]`**，且库内 roll 正值=向左倾（与直觉相反）——固件已在内部做顺序交换 + roll 取反，协议层语义正确，**不要二次调整**
2. **动作名必须用官方拼写**：坐下的动作名是 `sit_dowm`（官方拼写错误，库只认这个），趴下 `go_prone`，传 `sit`/`lie` 会被库静默忽略
3. ESP32 固件的 `stdin` 非阻塞，需用 `select.poll()` 轮询（已内置）
4. 基础版无发光超声波模块时 `SONAR` 返回 `N/A`（正常）
5. 串口响应偶尔夹带 `$$>1<$$` 杂讯（mpremote 残留），以 `OK` / `pong` 为准

## 🔒 安全规则

- 动作前先 `POSE_DEFAULT` 复位，避免翻倒
- 步幅 ≤120mm、转角 ≤90°
- 桌面/高处禁止移动命令，防止摔落
- 长时间动作后让舵机休息（过热保护）

## 📄 License

MIT
