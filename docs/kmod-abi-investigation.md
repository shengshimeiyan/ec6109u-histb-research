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