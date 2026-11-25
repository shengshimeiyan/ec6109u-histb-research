# 海思内核镜像格式解析

基于对 `hi_kernel.bin`（24578474 字节）的逐字节逆向分析。

## 总体结构

```
偏移        内容
0x0         海思外层头（magic 0xaa640001, 0x12345678）
0x10        16 字节签名/hash
0x38        16 字节签名/hash
0x48        uImage 偏移 = 0x70a8
0x50        uImage 总长 = 0x1769902
0x70        文件总长 = 0x17709aa
0x70a8      uImage header (64 字节)
0x70e8      payload = stub + arm64 Image + DTB
```

## uImage header（大端）

```
magic   = 0x27051956
hcrc    = 0x76014078
time    = 0x68ad5287
size    = 0x017698c2  (24549570)
load    = 0x02000000
ep      = 0x02000000
dcrc    = 0x83a282c9
os/arch/type/comp = 05 16 02 00  (Linux / arm64 / kernel / none)
name    = "Linux-4.4.35_ecoo_82082668"
```

### CRC 算法（关键）

```python
def uimage_hcrc(header64: bytes) -> int:
    h = bytearray(header64)
    h[4:8] = b'\x00\x00\x00\x00'   # hcrc 字段清零
    return zlib.crc32(bytes(h)) & 0xffffffff
```

dcrc = `zlib.crc32(payload) & 0xffffffff`，覆盖 uImage header 之后的 size 字节。

> 常见错误：只对 header 前 32 字节算 CRC —— 那是错的，
> 必须对整个 64 字节 header（hcrc 域清零后）算 CRC。算错会导致 fastboot 校验失败，
> 表现为卡在"正在刷入"画面。

## payload 内部结构

```
payload[0x0 - 0x1120]      海思重定位/解压 stub（4384 字节）
                           含字符串 "reloc: dtb too large" / "Kernel: %08x..."
payload[0x1120]            arm64 Image header
                           code0 = 0x14538000 (b 跳转指令，跳到解压器)
                           text_offset = 0x80000, image_size = 0x1a1d000
                           ARMd magic @ header+0x38
payload[末尾 - 14314]      DTB (magic 0xd00dfeed)
```

stub 关键参数（payload 头部 32 位字）：
```
[0x10] = 0x37ea   = 14314  = DTB 大小
[0x14] = 0x7b000           = 内核目标地址偏移
[0x18] = 0x7c120           = 源数据偏移
[0x30] = 0x7b0a0           = 跳转入口
[0x20] = 0x80000           = text offset
```

## 为什么不能直接替换 payload

新编译的裸 Image 与原来的 payload 有本质差异：

| | 原内核 payload | 裸 Image |
|---|---|---|
| code0 | `b` 跳转（到解压器，0x14538000） | `add x13,x2,#0x16`（0x91005a4d） |
| image_size | 0x1a1d000（27MB，含压缩数据） | 0xcd5000（13MB） |
| 结构 | stub + 压缩内核 + DTB | 单个可执行文件 |

stub 的参数区在文件内是 `0xffee` 填充，由 BootROM 运行时填入实际地址——
无法靠静态分析完整重建。因此即使 uImage CRC 正确、payload 换成裸 Image + DTB，
也无法保证能启动（实测卡在启动阶段）。

## 结论（已根据神雕原帖修正）

**手工改 uImage payload 不可行** —— 之前的尝试全部失败。

根本原因：内核必须用**海思官方 SDK** 编译，SDK 的 `make linux` 会自动
生成含正确 stub、DTB、签名的海思格式内核。第三方裸内核源码 + defconfig
猜测的方式行不通。

正确流程（来自神雕 teasiu 原帖 https://www.znds.com/tv-1207323-1-1.html）：
```bash
cd HiSTBLinuxV100R005C00SPC060
source ./env.sh                        # 海思专用编译环境 (gcc 6.5 + glibc 2.22)
cp configs/hi3798mv200/xxx_cfg.mak ./cfg.mak   # 厂商完整配置
make menuconfig
make hiboot                            # U-Boot
make prebuilts                         # 生成 bootargs.bin
cd source/kernel/linux-4.4.y/
make ARCH=arm64 hi3798mv200_defconfig
make ARCH=arm64 menuconfig             # 在这里勾选 mt7601u / rtl8188 / btusb 驱动
make clean
cd HiSTBLinuxV100R005C00SPC060
make linux                             # 自动产出正确的海思格式 hi_kernel.bin
```

关键点：
- 必须用 `source ./env.sh` 加载 SDK 的交叉编译环境
- 驱动在 `make menuconfig` 里勾选（built-in），随内核一起编译
- `make linux` 由 SDK 负责打包（stub/DTB/签名全部自动处理），无需手工封装 uImage
- 4G 与 8G 机型 fastboot.bin 不同，必须匹配（EC6109-U/M 用 mv2dma / 1+4G）

SDK 下载：https://www.histb.com/ ，编译示例见官方 HiSTBLinuxV100R005C00SPC060。
