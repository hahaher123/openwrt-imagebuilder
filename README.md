# openwrt-imagebuilder

用 OpenWrt 官方 **ImageBuilder** 生成可直接刷入的固件镜像，发布在本仓库的 Release 中。

镜像不自行编译内核与软件包，全部使用官方 `downloads.openwrt.org` 的发行版二进制，因此产物与
官方固件同源同版本，只多了定制包集与可自定义的 rootfs 分区大小。

## 获取镜像

在 **Releases** 页面按版本下载，每个 Release 提供**一个**整盘镜像，`sha256` 与文件大小写在
该 Release 的说明里。

## 支持的目标

| 配置 | target / profile | 发布变体 | 刷入方式 |
| --- | --- | --- | --- |
| `x86_64` | `x86/64` · `generic` | `ext4-combined-efi` | U 盘 / SSD / 虚拟机磁盘（含 PVE） |
| `r2s` | `rockchip/armv8` · `friendlyarm_nanopi-r2s` | `ext4-sysupgrade` | microSD 卡 |

两者的产物形态不同，这不是取舍而是平台决定的：

* x86 用 GRUB 引导，出 `combined-efi`（GPT + EFI 分区，引导扇区 + 内核分区 + rootfs 分区一体）。
* rockchip 用 u-boot 引导，出 `sysupgrade`（整盘镜像，u-boot 写在扇区 0x40，
  SPL 从 8 MiB 处读 U-Boot ITB）。**rockchip 没有 combined-efi** —— 那是 x86/armsr 才有的形态。

## 镜像规格

| 项 | x86_64 | r2s |
| --- | --- | --- |
| 根文件系统 | ext4 | ext4 |
| 内核分区 | 16 MiB | 16 MiB |
| rootfs 分区 | 1024 MiB | 1024 MiB |
| 引导 | GRUB（EFI） | u-boot |

官方 x86 镜像的 rootfs 分区是 104 MiB（同版本 13.2 MiB 的压缩体积），官方 R2S 镜像也是
104 MiB。这里统一放大到 **1024 MiB**，代价是多占约 6 MiB 压缩体积，换来一块够用的可写分区。

rootfs 分区大小由 `ROOTFS_PARTSIZE` 写进 `CONFIG_TARGET_ROOTFS_PARTSIZE`，最终决定分区 2 的
扇区数。**保持这个值不变**，自制镜像之间升级就会走增量写、配置与额外分区都保住。

## 用法

### 全新安装

x86_64（写 U 盘 / SSD / 虚拟机磁盘）：

```sh
gunzip -c openwrt-<版本>-ext4-1g-x86-64-generic-ext4-combined-efi.img.gz | dd of=/dev/sdX bs=4M
```

PVE / KVM 可直接把解压后的 `.img` 作为磁盘导入。

r2s（写 microSD 卡）：

```sh
gunzip -c openwrt-<版本>-ext4-1g-rockchip-armv8-friendlyarm_nanopi-r2s-ext4-sysupgrade.img.gz \
  | dd of=/dev/sdX bs=4M
```

### 从已有 OpenWrt 升级

```sh
sysupgrade openwrt-<版本>-<文件名标记>-<target>-<profile>-<变体>.img.gz
```

刷入前可先做无写入的预检，看是否会重写分区表：

```sh
sysupgrade -T <镜像>
```

* 打印 `Partition layout has changed. Full image will be written.` —— 会整盘覆盖，磁盘上自建的
  其他分区（如数据分区）会被清除。
* 没有这行 —— 按分区增量写入，分区表与额外分区保留，配置也保留。

**本仓库的 rootfs 固定为 1024 MiB**，所以在同一规格的自制镜像之间升级始终走增量写入。只有从
官方镜像（rootfs 104 MiB）首次切过来时，会因为分区大小不同而整盘写一次 —— 这一次请先
`sysupgrade -b` 把配置备份到电脑上，且数据不要放在系统盘。

> x86 与 r2s 的这一判定链路是同一条：都用 `get_partitions` 比对磁盘与镜像的分区表
> （只比分区号 / 起始 LBA / 扇区数），差集为空就逐分区写。

## 包含的软件包

在官方对应 profile 的默认包集之上追加。

**两个目标共有**：

* **LuCI**：`luci`、`luci-app-attendedsysupgrade`、`luci-proto-wireguard`
* **简体中文界面**：`luci-i18n-base-zh-cn`、`luci-i18n-firewall-zh-cn`、
  `luci-i18n-package-manager-zh-cn`、`luci-i18n-ttyd-zh-cn`、`luci-i18n-sqm-zh-cn`、
  `luci-i18n-unbound-zh-cn`、`luci-i18n-irqbalance-zh-cn`
* **网络与代理**：`nftables`、`kmod-nft-tproxy`、`kmod-nft-offload`、`natmap`、`ethtool`
* **其他**：`dnsmasq-full`（替代默认的 `dnsmasq`）、`kmod-fs-vfat`（挂 U 盘）

**按平台不同**：

| 目标 | 额外内容 |
| --- | --- |
| x86_64 | 网卡驱动一排：`kmod-e1000`、`kmod-e1000e`、`kmod-igb`、`kmod-igc`、`kmod-ixgbe`、`kmod-ixgbevf`、`kmod-r8169`、`kmod-tg3`、`kmod-forcedeth`、`kmod-bnx2`、`kmod-amd-xgbe`、`kmod-dwmac-intel`、`kmod-amazon-ena`；`kmod-drm-i915`；`grub2-bios-setup`；`kmod-button-hotplug` |
| r2s | `kmod-usb-net-rtl8152`（R2S 的第二个千兆口挂在 USB 3.0 上，缺它就只剩一个网口）；`uboot-envtools`；`kmod-gpio-button-hotplug` |

完整清单以 `config/<配置>.conf` 的 `PACKAGES` 为准，或系统启动后执行 `apk list --installed` 查看。

## 重新构建

默认构建目标（版本号 + 配置）在整个仓库里只在 **`config/build.conf`** 一处定义：

```sh
VERSION="25.12.5"
ARCH="r2s"
```

* **换 OpenWrt 版本** → 改 `VERSION` 一行。
* **换目标** → 改 `ARCH` 一行，取值是 `config/<配置>.conf` 的文件名（`x86_64` 或 `r2s`，
  将来新增目标就照现有文件复制一份改内容）。
* **换包集 / rootfs 分区大小** → 改 `config/<配置>.conf` 里对应的一行。

改完 push 到 `main` 即自动重建，并把镜像发到 Release `v<版本>-<配置>`；同名 Release 只替换
资产与说明，不新建。

不改仓库也可以：手动触发构建，在输入框里临时指定版本号、配置、分区大小或包集，留空即取
`config/build.conf`（临时指定的值不会写回仓库）。

## 许可

MIT。镜像中的 OpenWrt 及其软件包各自遵循其原始许可（以 GPL 系列为主）。
