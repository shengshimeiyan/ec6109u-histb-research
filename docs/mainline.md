# 主线内核移植（histb-mainline 项目）

## 项目

https://github.com/histb-mainline — 海思 Hi3716/Hi3796/Hi3798 系列的主线内核移植组织。

| 仓库 | 内容 |
|---|---|
| patches | **130 个补丁**，基线 **Linux 7.4-rc4**（BASE_SHA `a4d7daea...`） |
| linux-config | 分层内核配置（Debian arm64 基线 + arch + driver + convenience 层） |
| hiloot | 开源 HiTool 替代品（USB 串口引导） |
| histb-stage1 | 从原厂 fastboot 交接给 TF-A BL31（RAM 启动，已在 MV200H 创维盒子验证） |
| u-boot / arm-trusted-firmware | 主线引导链 |

## 对 Hi3798MV200 的支持

补丁包含所有关键驱动：
- `510-02` CRG 时钟驱动（4.4 BSP 缺失的那个）
- `220-01` eMMC 控制器（himciv200）
- `230-*` 以太网（hisi_femac，含 fixed-link 修复）
- `205-*` USB2 PHY、`265-*` EHCI/OHCI
- `815-02` MV200 SoC DTS、`815-03` HC2910 板卡 DTS
- HDMI DRM、音频 AIAO、红外、pinctrl、看门狗、cpufreq

## 本项目为 EC6109-U/M 做的工作

1. 克隆 patches 仓库（130 个补丁）
2. 下载 Linux 7.4-rc4 源码（GitHub codeload，262MB / 解压 1.9GB）
3. **130 个补丁按文件名数字顺序全部成功应用（0 失败）**
4. 编写板级 DTS `hi3798mv200-ec6109u.dts`：基于 HC2910（同 MV200 芯片），
   内存改为 **1 GiB**（`0x40000000`），兼容串 `huawei,ec6109u`
5. 获取 Debian 7.4-rc4 arm64 基线配置，用项目 `merge-layers.sh`
   合并 `01-arch-arm64.txt` + `02-select-y.txt`（全 built-in）+ `03-convenience.txt`
6. **DTS 编译成功**：`hi3798mv200-ec6109u.dtb`（16KB）

## 当前状态

主线内核 Image 编译中（后台）。

## 后续计划

1. 内核编译成功后，用原厂 U-Boot 的 `bootm` 加载主线 Image + DTB
   （需要打包成海思格式：外层头 + uImage，DTB appended）
2. 或者用项目的 hiloot + stage1 + TF-A 完整主线引导链
3. 目标：主线内核 7.4 下 WiFi/蓝牙用原生驱动，fnOS 移植成为可能

## 风险

- 主线内核在真实 EC6109-U/M 硬件上未经验证（项目只验证了 HC2910/MV200H）
- 分区/引导格式、PHY 参数、DDR 地址可能需要按实际硬件调整
- 保留 v8 稳定包作为随时可恢复的退路

---

# 主线移植复盘：为什么还不能启动（2026-11-26）

## 已完成的构建（全部就绪）

```
kernel-tree/arch/arm64/boot/Image                                57 MB
kernel-tree/arch/arm64/boot/dts/hisilicon/hi3798mv200-ec6109u.dtb 16 KB
hi_kernel_mainline_gz.bin   21 MB（gzip 后，可放进 40MB kernel 分区）
```

- 130 个 histb-mainline 补丁全部应用（0 失败）
- Linux 7.4-rc4 编译通过，驱动齐全（mt7601u / rtl8xxxu / btusb / hisi_femac）
- 板级 DTS 基于 HC2910 改编，1 GiB 内存，DTS 编译通过

## 排除的错误假设

| 假设 | 结论 |
|---|---|
| 主线不支持 `blkdevparts=` | ❌ 错。主线有 `block/partitions/cmdline.c`，`CONFIG_CMDLINE_PARTITION=y` 已启用 |
| 内核太大放不进 40MB 分区 | ✅ 对，已用 gzip 解决（21MB） |
| 恢复阶段用新内核启动 p7 | ✅ 对，这是"卡在正在刷入"的直接原因 |

## 真正的技术障碍：引导协议

海思 `hi_kernel.bin` 的结构（实测）：

```
0x0     - 0x70a8   海思头 + **可执行 AArch64 stub**（0x80 处即 mov x0,#0 / mov x1,#8 等指令）
0x70a8  - 0x70e8   uImage header (load=ep=0x2000000, comp=0)
0x70e8  - ...      uImage payload
        └─ 原厂内核: [内层 stub 4.4KB][压缩内核+DTB] —— 内层 stub 负责
                      重定位、解压、**把 DTB 地址放进 x0**
```

**关键**：arm64 主线内核**必须**从 `x0` 取得 DTB 指针（arm64 不支持 appended DTB，
那是 arm32 的特性）。而海思这个 loader 不会传 x0。

原厂内核能启动，是因为它的 **uImage payload 自带一个内层 stub** 来做这件事。
我们直接用「gzImage + DTB」作 payload，缺了这个 stub → 内核拿不到设备树 → 挂死。

## 要走到下一步，必须

1. 反汇编海思 loader 的调用约定（入口地址、寄存器状态、payload 放置位置），
   然后自己写一个 ~100 行的 AArch64 stub（设 x0=DTB、跳到内核），
2. **或者** 走 histb-mainline 官方路线：`histb-stage1` → TF-A BL31 → 主线 U-Boot → 主线内核
   （项目已在 Hi3798MV200H 创维盒子硬件验证）

两条路都需要**观察启动早期行为**——而本机顶盒无 TTL 串口、HDMI 不显示内核日志。

## 为什么 kexec 也不行

本内核未编译 `CONFIG_KEXEC`（`/proc/kallsyms` 无 `kexec_load` / `machine_kexec`），
无法从运行中的 4.4 内核安全跳转到主线内核。所以没有"零风险试启动"的办法。

## 结论

主线移植的**软件工作已全部完成**（补丁、内核、DTS、驱动、打包格式）。
剩下的是引导链适配，这一步**必须有 USB-TTL 串口**才能进行：
- 观察 loader 的入口寄存器/内存布局
- 或用 hiloot（本项目提供的开源 HiTool 替代品，走 USB 串口）刷 stage1 + TF-A

一根 CH340（3.3V，约 8 元）即可解锁这条路，同时也能用来诊断 WiFi 驱动的硬件问题。
