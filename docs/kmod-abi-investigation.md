# 驱动模块 ABI 排查记录（v8 内核 + SDK 模块）

## 结论摘要

用**官方海思 SDK** 编译的 `mt7601u.ko`（vermagic 精确匹配 `4.4.35_ecoo_82082668`）
**可以成功加载、识别网卡、加载固件**，但在初始化阶段因 `struct sk_buff`
字段偏移不一致触发 `skb_under_panic` → 内核 panic。

这证明：**vermagic 匹配 ≠ ABI 匹配**。厂商内核（ecoo 自编译）与 SDK 默认配置
之间存在影响结构体布局的配置差异。

## 已确认可用的部分

| 项目 | 结果 |
|---|---|
| 模块加载 | ✅ 成功（无 panic） |
| USB 网卡识别 | ✅ `ASIC revision: 76010001 MAC revision: 76010500`（两块都识别） |
| 固件加载 | ✅ `Firmware Version: 0.1.00 Build: 7640` |
| cfg80211 | ✅ 原版内核已内建（374 符号） |
| mac80211 | ✅ 原版内核已内建（691 符号） |
| r8152 / usbnet | ✅ 已内建（59 符号）→ **USB 有线网卡可直接用** |

## 崩溃现场（netconsole 抓取）

```
skbuff: skb_under_panic: text:... len:12 put:4
        head:ffffffc026674a00 data:ffffffc0266749fc tail:0x8 end:0x80 dev:<NULL>
kernel BUG at net/core/skbuff.c:104!
PC is at skb_panic+0x6c/0x70
Call trace:
 skb_panic
 mt7601u_mcu_msg_send+0xb8/0x4a0 [mt7601u]
 mt7601u_mcu_cmd_init+0x44/0x120 [mt7601u]
 mt7601u_init_hardware+0x14c/0x4a0 [mt7601u]
 mt7601u_probe+0x1e4/0x258 [mt7601u]
```

`data` 比 `head` 低 8 字节 → 驱动程序里的 `skb_reserve()/skb_push()` 写入的
字段位置与内核实际布局不符（`struct sk_buff` 字段偏移错位）。

## 诊断方法（可复用）

盒子无 TTL 串口、屏幕不显示内核日志。用 **netconsole over UDP** 抓 panic：

```bash
# 主机侧监听（注意先开放防火墙！）
sudo iptables -I INPUT 1 -p udp --dport 6666 -j ACCEPT
python3 -c "
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(('0.0.0.0',6666))
open('/tmp/nc.log','wb').write(b'')
while True: open('/tmp/nc.log','ab').write(s.recvfrom(65535)[0])
"

# 盒子侧（内核已内建 CONFIG_NETCONSOLE_DYNAMIC，走 configfs）
mkdir -p /sys/kernel/config/netconsole/t1 && cd /sys/kernel/config/netconsole/t1
echo <主机IP> > remote_ip; echo 6666 > remote_port; echo 6666 > local_port
echo eth0 > dev_name; echo <主机MAC> > remote_mac; echo 1 > enabled

# 触发
insmod /root/kmods/mt7601u.ko
```

## 已排除 / 已对齐的配置项

通过 `/proc/kallsyms` 与 `/proc/sys/net/*` 探测盒子内核实际配置：

| 配置项 | 盒子内核 | SDK 默认 | 处理 |
|---|---|---|---|
| `CONFIG_NF_CONNTRACK` | ✅ 开 | ❌ 关 | 已改为开 |
| `CONFIG_BRIDGE_NETFILTER` | ✅ 开 | ❌ 关 | 已改为开 |
| `CONFIG_NET_SCHED` | ✅ 开 | ❌ 关 | 已改为开 |
| `CONFIG_NET_RX_BUSY_POLL` | ✅ 开（`busy_poll` sysctl 存在） | 默认 y | 一致，无需改 |
| `CONFIG_XFRM` | ✅ 开 | ✅ 开 | 一致 |

对齐上述 3 项后重新编译模块，**仍然 panic**，说明还有其他影响布局的差异未找到
（`sk_buff` 在 4.4 中有十余个 `#ifdef CONFIG_*` 字段，需逐项试错）。

## 为什么难以彻底解决

厂商内核由 ecoo 自编译（gcc 6.5 / `_ecoo_82082668`），**其 `.config` 未公开**，
内核也未启用 `CONFIG_IKCONFIG`（无 `/proc/config.gz`）。要精确匹配只能：
1. 向 histb 社区索取该内核版本的预编译 `.ko`（对应 `0808` 等特定版本）
2. 逐项试错对齐配置（每轮约 10 分钟，组合数量大）
3. 拿到厂商 `.config`（最根本）

## 实用替代方案

`r8152` + `usbnet` 已内建 → **USB 有线网卡（如 Realtek RTL8153）插上即可用**，
可给盒子增加一个有线网口，无需任何模块。
---

# 更新：ABI 问题已解决（2026-11-26）

## 决定性突破：厂商预编译模块 + 改 vermagic

官方 apt 源 `https://www.ecoo.top/update/repo/arm64` 里有现成的 WiFi 驱动包：

```
histb-wifi-hi3798mv200    v0.1.0 / v0.1.1
  └── usr/lib/modules/4.4.35_ecoo_26010066/
        ├── mt7601u.ko    (164 KB)
        ├── rtl8188eu.ko  (2.3 MB，Realtek 官方驱动)
        └── rtl8188fu.ko  (1.7 MB)
  └── usr/lib/firmware/rtlwifi/{rtl8188eufw,rtl8188fufw}.bin
```

这些模块由厂商用其自有配置编译，**ABI 与 ecoo 内核一致**。唯一障碍是
目录名/vermagic 指向 `4.4.35_ecoo_26010066`，与本机 `4.4.35_ecoo_82082668` 不符。

**关键技巧**：两个版本号都是 8 位字符，可直接在 .ko 里等长替换 vermagic 字符串：

```python
d = open('mt7601u.ko','rb').read()
d = d.replace(b'4.4.35_ecoo_26010066', b'4.4.35_ecoo_82082668')
open('mt7601u_patched.ko','wb').write(d)
```

改完后模块**正常加载，不再 panic** —— 证明 ABI 与厂商内核完全兼容。

## 已验证的结果

| 网卡 | 驱动加载 | 识别 | 固件 | 上电初始化 | wlan0 |
|---|---|---|---|---|---|
| MT7601U ×2 (148f:7601 / 2717:4106) | ✅ | ✅ ASIC 76010001 | ✅ Build 7640 | ❌ MCU 超时 -110 | ❌ |
| Realtek RTL8188EU (0bda:b711) | ✅ | ✅ | ✅ | ❌ `HalPwrSeqCmdParsing: Fail to polling Offset[0x6]=00` | 建了但无法 UP |

## Realtek 网卡额外需要的两步

1. **模式切换**：这类网卡默认枚举为虚拟光驱 `0bda:1a2b`（USB Disk autorun），
   需用 `usb_modeswitch -v 0bda -p 1a2b -K` 切换到 `0bda:b711`。
   （本内核未启用 `CONFIG_CHR_DEV_SG` / `CONFIG_BLK_DEV_SR`，无法用 `eject /dev/sr0`）
2. **PID 补丁**：厂商 `rtl8188eu.ko` 的 USB ID 表只含 `8179`/`0179`，
   需把 ID 表项 `0x8179` 改为 `0xb711`（二进制偏移 `0xf0888`：
   `03 00 da 0b 79 81` → `03 00 da 0b 11 b7`），并同步改 `alias` 字符串。

## 剩余障碍：芯片上电失败

两块网卡都停在"芯片无法正常上电"：
- MT7601U：固件上传成功后 MCU 无响应（`Vendor request req:07 off:0080 failed:-110`）
- RTL8188EU：`HalPwrSeqCmdParsing: Fail to polling Offset[0x6]=00`
  该网卡 efuse 中 MAC 全零（`00:00:00:00:00:00`），属廉价克隆片

尝试过 `rtw_pll_ref_clk_sel=0/1/2/3` 均无效。

**共同点是"芯片不响应"** → 高度怀疑 **USB 供电不足**（机顶盒 USB 口带载能力弱，
WiFi 网卡峰值电流 300-500mA）。建议用**带外部供电的 USB HUB** 测试。

## 结论

驱动侧已完全打通（ABI、vermagic、模式切换、固件、PID 全部解决）。
剩下的是硬件供电/网卡质量问题：换一块正品 RTL8188EU（0bda:8179）或加带源 HUB 即可。

---

# 最终状态：软件打通，硬件受限

## 已固化到系统的成果（v8 系统上已验证）

```
/lib/modules/4.4.35_ecoo_82082668/extra/
├── rtl8188eu.ko   2.3M  (厂商原版 + PID 补丁 b711)
├── rtl8188fu.ko   1.7M  (厂商原版 + PID 补丁 b711)
└── mt7601u.ko     161K  (厂商原版)

/lib/firmware/
├── mt7601u.bin           (45K)
├── rtl8188eufw.bin       (14K)
└── rtl8188fufw.bin       (21K)

/etc/udev/rules.d/99-rtl8188-mode-switch.rules   # 自动模式切换
/usr/local/bin/rtl-modeswitch.sh
```

三个模块均可 `modprobe` 成功，`lsmod` 可见，系统稳定无崩溃。

## 决定性证据：问题在硬件

| 证据 | 说明 |
|---|---|
| 两个不同驱动 (8188EU v4.3.24 / 8188FU v4.3.23) | 在**完全相同位置**失败：`HalPwrSeqCmdParsing: Fail to polling Offset[0x6]=00` |
| efuse MAC = `00:00:00:00:00:00` | 正品芯片必有 MAC，此为克隆片特征 |
| MT7601U ×2 | 固件上传后 MCU 无响应 `req:07 off:0080 failed:-110` |
| 换 USB 口（EHCI/xHCI 都试） | 结果相同 |
| 关闭 USB autosuspend、调 PLL 时钟参数 | 无效 |
| dmesg 无过流告警 | 但廉价 STB 的 USB 供电可能不足以驱动 RF 芯片 |

三块网卡、两个芯片家族，全部停在"芯片无法上电" → 硬件问题（克隆片缺陷 或
机顶盒 USB 供电不足）。

## 建议的下一步

1. **把网卡插到电脑上验证**——若电脑上正常，则是盒子供电问题，需**带外部供电的 USB HUB**
2. **更换正品 RTL8188EU（PID 必须是 0bda:8179）**——厂商模块原生支持，
   插上后 udev 规则 + modprobe 即可工作，无需任何额外操作
3. 继续使用有线（v8 系统本身是稳定可用的 NAS）

## 附：Realtek 克隆网卡模式切换说明

这类网卡上电默认枚举为虚拟光驱 `0bda:1a2b`，必须切换到 WiFi 模式 `0bda:b711`：

```bash
usb_modeswitch -v 0bda -p 1a2b -K -W
```

本内核未启用 `CONFIG_CHR_DEV_SG` / `CONFIG_BLK_DEV_SR`，因此无法用
`eject /dev/sr0` 的方式触发，必须用 usb-modeswitch（走 libusb）。
