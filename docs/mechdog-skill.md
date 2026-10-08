---
name: mechdog
description: 控制幻尔（Hiwonder）MechDog 机器狗。适用场景：用户要求让机器狗前进/后退/左转/右转/停止/坐下/趴下/站立/原地踏步/调整速度/调整机身高度/俯仰横滚姿态/运行动作组/开关自稳/读取超声波距离，或让小犬 agent 驱动机器狗做动作。使用前机器狗需已烧录 mechdog_server.py（MicroPython 指令接收程序）。**无线模式（推荐）**：ESP32 已连家庭 Wi-Fi（2.4GHz），Mac 通过 `--host <IP>`（TCP 5000）控制，USB 可拔；串口模式留作后备/烧录。
---

# MechDog 机器狗控制

## ⚡ 执行准则（必须先读，决定响应速度）

1. **一步直达**：收到指令后直接运行 CLI，不要先读本文件全文、不要重复确认、不要逐条试探。
2. **多动作合并**：连续动作用分号合并成**一次** bash 调用，如 `python3 <skill>/scripts/mechdog_cli.py --cmd "POSE_SIT;POSE_DEFAULT;ACTION 7"`——一次调用完成，别一条条发。
3. **汇报一句话**：执行完只报告结果（OK/距离/异常），不要展开解释。
4. 每步动作间自动有等待时间（默认 1s，动作用 `--wait` 调长到动作时长）。
5. **响应解析只看 `[←]` 行**：CLI 的 `[→] ...` 行是日志（不含 IP/路径数字，已改为 `[→] mechdog <- 命令`），
   **所有数据以 `[←]` 之后的内容为准**：`pong`（连通）、`OK ...`（动作成功）、`SONAR xx cm`（距离，带 cm 单位）。
   不要从日志行解析任何数字；`BLOCKED sonar=xxcm` 表示避障触发已停车。

## 架构

```
用户/小犬 agent → mechdog_cli.py (Mac) --Wi-Fi(TCP 5000) 或 USB串口--> ESP32 上的 mechdog_server.py (MicroPython) → HW_MechDog 库 → 8舵机动作
```

- **Mac 端**（本 skill）：`scripts/mechdog_cli.py`，用 socket（Wi-Fi TCP）或 pyserial（USB）发命令文本
- **ESP32 端**：`scripts/mechdog_server.py`（MicroPython），烧录到机器狗后**双通道同时监听**（Wi-Fi TCP 5000 + USB 串口）
- **无线模式（推荐，USB 可拔）**：ESP32 内置 Wi-Fi（STA 模式，仅 2.4GHz）连家庭 Wi-Fi。
  机器狗当前 IP：`192.168.1.15`（路由器可能重新分配；IP 变了就插 USB 读启动日志里的 `Wi-Fi OK, IP: xxx`）
- **串口模式（后备/烧录）**：USB 连接 Mac，`--port` 或自动探测

## 快速用法（90% 场景用这些）

```bash
# 无线模式（推荐）——命令表见下
python3 skills/mechdog/scripts/mechdog_cli.py --host 192.168.1.15 --cmd "F 80"

# 批量动作：一次调用完成坐下→站立→握手
python3 skills/mechdog/scripts/mechdog_cli.py --host 192.168.1.15 --cmd "POSE_SIT;POSE_DEFAULT;ACTION 7" --wait 2

# 串口后备模式
python3 skills/mechdog/scripts/mechdog_cli.py --port /dev/cu.usbserial-XXX --cmd "SONAR" --wait 2
```

> 无线：`--host <IP|主机名>` 走 TCP（默认端口 5000）；不带 `--host` 时自动探测 usbserial 走串口。
> 机器狗 IP 变了：插 USB 读启动日志找新 IP，或路由器后台查 DHCP 列表。

## 使用前检查（必须）

1. **无线模式**：机器狗已连 Wi-Fi（上电启动日志打印 `Wi-Fi OK, IP: xxx`）；Mac 与狗在同一局域网，能 ping 通
2. **串口后备**：机器狗 USB 已连 Mac：`ls /dev/cu.*` 应出现 `cu.usbserial-*`（没有则先插线/装 CP210x 或 CH340 驱动）
3. 测试链路（无线）：`python3 skills/mechdog/scripts/mechdog_cli.py --host 192.168.1.15 --cmd ping` → 返回 `pong`
   测试链路（串口）：`python3 skills/mechdog/scripts/mechdog_cli.py --port /dev/cu.usbserial-XXX --cmd ping` → 返回 `pong`

## 命令协议（纯文本，\\n 结尾）

| 命令 | 含义 | 示例 |
|---|---|---|
| `ping` | 连通测试 | `ping` |
| `F <mm>` | 前进（mm，1~120） | `F 80` |
| `B <mm>` | 后退（mm） | `B 50` |
| `L <deg>` | 左转（度，1~90） | `L 20` |
| `R <deg>` | 右转（度） | `R 30` |
| `M <mm> <deg>` | 组合移动（步幅，转角） | `M 60 15` |
| `STOP` | 停止 | `STOP` |
| `POSE_DEFAULT` | 恢复默认站立姿态 | `POSE_DEFAULT` |
| `POSE_SIT` | 坐下 | `POSE_SIT` |
| `POSE_LIE` | 趴下 | `POSE_LIE` |
| `HEIGHT <mm>` | 机身升降（-30~+30） | `HEIGHT 20` |
| `TILT <pitch> <roll>` | 机身俯仰/横滚（度，-30~30）。**第一个=前后倾(+前/-后)，第二个=左右倾(+右/-左)** | `TILT 15 0` |
| `MARCH` | 原地踏步 | `MARCH` |
| `SPEED <0-100>` | 设置步态速度参数 | `SPEED 60` |
| `ACTION <n\|动作名>` | 运行动作组：编号 1~15 或直接动作名 | `ACTION 7` / `ACTION handshake` |
| `STABLE <on|off>` | 自稳开关（homeostasis） | `STABLE on` |
| `SONAR` | 读超声波距离（cm，发光超声波 I2C 模块） | `SONAR` |

## 预置动作组（官方出厂动作表）

| 编号 | 动作名（官方拼写） | 含义 | 编号 | 动作名 | 含义 |
|---|---|---|---|---|---|
| 1 | `left_foot_kick` | 踢左脚 | 9 | `nodding_motion` | 点头 |
| 2 | `right_foot_kick` | 踢右脚 | 10 | `boxing` | 打拳 |
| 3 | `stand_four_legs` | 四脚站立 | 11 | `stretch_oneself` | 伸懒腰 |
| 4 | `sit_dowm` | 坐下（**注意拼写 dowm**） | 12 | `pee` | 撒尿 |
| 5 | `go_prone` | 趴下 | 13 | `press_up` | 俯卧撑 |
| 6 | `stand_two_legs` | 双脚站立 | 14 | `rotation_pitch` | 俯仰旋转 |
| 7 | `handshake` | 握手 | 15 | `rotation_roll` | 横滚旋转 |
| 8 | `scrape_a_bow` | 鞠躬 | | | |

> 坐下/趴下/站立请用 `POSE_SIT` / `POSE_LIE` / `POSE_DEFAULT`（内部已映射到正确动作名），
> 或 `ACTION 4` / `ACTION 5` / `ACTION 3`。

## 官方 API 语义（来自 MechDog 官方示例程序）

- `move(步幅mm, 转角deg)`：步幅正=前进、负=后退；转角正=左转、负=右转；`move(0,0)`=停止
- `transform([x,y,z],[pitch,roll,yaw], ms)`：x/y/z 平移（z 正=升高）、三轴旋转、变换时长
- `set_gait_params(脚尖离地时间, 脚尖触地时间, 抬腿高度)`：步态参数
- `homeostasis(True/False)` + `read_homeostasis_status()`：自平衡
- `action_run("动作名")`：运行动作组（名称见上表）
- 超声波：`Hiwonder_IIC.I2CSonar(Hiwonder_IIC.IIC(1)).getDistance()`（I2C 发光超声波，非 `Hiwonder.Sonar`）

## CLI 用法

```bash
# 无线模式（推荐）：--host 走 TCP 5000
python3 skills/mechdog/scripts/mechdog_cli.py --host 192.168.1.15 --cmd "F 80"

# 超声波测距（无线）
python3 skills/mechdog/scripts/mechdog_cli.py --host 192.168.1.15 --cmd "SONAR"

# 串口模式：--port 指定或自动探测
python3 skills/mechdog/scripts/mechdog_cli.py --cmd "POSE_DEFAULT"
python3 skills/mechdog/scripts/mechdog_cli.py --port /dev/cu.usbserial-XXX --cmd "F 80"
```

## 动作安全规则

1. 动作前先 `POSE_DEFAULT` 复位，避免突然改变姿态导致翻倒
2. `F/B` 步幅不要超过 120mm；`L/R` 转角不要超过 90 度
3. 机器狗在桌面/高处时**禁止**使用移动命令，防止摔落
4. 长时间运行动作后让狗休息（舵机过热保护）
5. 超声波距离 < 20cm 时应自动 `STOP`（server 端已内置）

## 文件

- `scripts/mechdog_cli.py` — Mac 端命令行控制（`--host` 无线 TCP / 缺省串口）
- `scripts/mechdog_server.py` — ESP32 端 MicroPython 指令接收程序（Wi-Fi + 串口双通道，需烧录）

## 已知坑（实测记录）

1. **MechDog 库 `transform` 旋转参数顺序是 `[roll, pitch, yaw]`**，官方 demo 注释（pitch 在前）与库实现不符；且**库的 roll 正值=向左倾**（与直觉相反）。`mechdog_server.py` 已在内部做「顺序交换 + roll 取反」，协议层 `TILT <pitch> <roll>` 语义正确（+前/-后，+右/-左），**不要在 server 之外再调整**。
2. **动作名必须用官方拼写**：坐下的动作名是 `sit_dowm`（d-o-w-m，官方拼写错误但库只认这个），趴下 `go_prone`。传 `sit`/`down`/`lie` 会被库**静默忽略**（返回 OK 但狗不动）。
3. **ESP32 固件的 `sys.stdin.readline()` 是非阻塞的**，直接死循环读会空转；server 必须用 `select.poll()` 轮询输入（已内置）。
4. 重新烧录前需先发 `Ctrl+C` 清 REPL，否则 mpremote 报 `could not enter raw repl`；烧录后 `mpremote ... reset` 重启生效。上传提示 `Up to date` 不代表内容一致，需 reset 后看启动日志验证。
5. **基础版 MechDog 无发光超声波模块**时 `SONAR` 返回 `N/A`（正常）；安装模块后走 I2C（`I2CSonar`），避障阈值 20cm 生效。
6. 串口响应里偶尔夹带 `$$>1<$$` / `$$>end<$$` / `err:except` 杂讯（mpremote/raw REPL 残留或模块调试输出），以 `OK ...` / `pong` 为准，杂讯可忽略。
7. **Wi-Fi 无线注意**：① ESP32 只支持 2.4GHz；② 路由器重分配 IP 后需重查地址（启动日志/路由器 DHCP 列表）；③ 断线后 ESP32 每轮自动重连（约 20ms 轮询）；④ USB 拔掉后靠电池供电，纯无线工作正常；⑤ 无线传输偶尔丢包时命令是"发后即忘"（TCP 会保证送达，响应超时重发一次即可）。
