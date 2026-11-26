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
