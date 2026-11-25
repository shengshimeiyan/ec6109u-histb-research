# 无线驱动探索记录

## 硬件现状

设备**没有内置 WiFi/蓝牙芯片**：USB 总线上只有 root hub，SDIO 的 mmc1/mmc2 为空，
设备树无 wifi/bt 节点。想用无线只能外接 USB 适配器。

## 测试过的 USB 设备

| 设备 | VID:PID | 芯片 |
|---|---|---|
| 小米 MI WLAN | 2717:4106 | MT7601U |
| Ralink 802.11n | 148f:7601 | MT7601U |
| Realtek 802.11n | 0bda:b711 | RTL8188EU |
| CSR Bluetooth Dongle | 0a12:0001 | CSR HCI |

## 系统自带驱动为何用不了

`/lib/modules/4.4.35_ecoo_81082668/` 里有 `rtl8188eu.ko` / `rtl8188fu.ko`，但：

1. **架构不匹配**：全是 `ELF 32-bit ARM`，运行在 64 位 aarch64 内核 →
   `insmod` 报 `Exec format error`
2. **PID 不匹配**：rtl8188eu 只支持 0x8179/0x0179，不含 0xb711
3. **目录名不匹配**：驱动在 `81082668` 目录，运行内核是 `82082668`，modprobe 找不到

## 交叉编译 64 位模块

环境准备（设备上）：
```bash
apt-get install gcc make flex bison libssl-dev wireless-tools wpasupplicant bluez
```

内核源码：`leandrotsampa/hisilicon-kernel`（atto-linux 分支，v4.4.35，
arm64 defconfig = `hi3798mv200_defconfig`）。本机装 `gcc-aarch64-linux-gnu` 交叉编译。

关键编译参数（新版 GCC 编老内核需要）：
```bash
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- HOSTCFLAGS="-fcommon" \
  -j4 M=drivers/net/wireless/mediatek/mt7601u
```

 vermagic 匹配技巧：内核**未启用 CONFIG_MODVERSIONS**（`/proc/kallsyms` 无
 `module_layout` 符号），所以只需把 defconfig 的 `CONFIG_LOCALVERSION` 改成
 `_ecoo_82082668`，编译出的模块 vermagic = `4.4.35_ecoo_82082668 SMP mod_unload aarch64`
 就能 `insmod` 成功，**不需要符号 CRC 匹配**。

为 rtl8188eu 加 b711 支持：在 `os_dep/usb_intf.c` 的 ID 表加一行
`{USB_DEVICE(USB_VENDER_ID_REALTEK, 0xb711)},` 后重编译。

MT7601U 需要固件 `mt7601u.bin`（从 linux-firmware-mediatek 包解压 zst 得到，45KB）。

## 惨痛教训

模块虽然 `insmod` 成功，但加载真硬件时**内核 panic**，盒子彻底失联，只能 U 盘救砖。

根因：vermagic 匹配只是字符串匹配，模块内部访问的内核数据结构布局
必须与运行内核**完全一致**。用 defconfig（不是设备的精确 .config）编译的模块，
ABI 很可能不兼容——insmod 时不会立刻崩，但真正 work 时踩坏内存就 panic。

**结论**：
- 不要在这类定制内核上用"猜 config 编译的模块"方式加载驱动
- 正确做法是把驱动 built-in 进一个完整替换的内核，且 config 必须与设备内核一致
- 而 Hi3798MV200 没有主线内核支持，fnNAS 等需要 6.x 内核的系统无法移植

## 最终建议

这台 4GB eMMC / 1GB RAM 的海思盒子，现实可用的就是原版海纳思系统 + 有线网络。
想要 WiFi/蓝牙，换支持的主线内核硬件（Amlogic/Rockchip 盒子）更划算。
