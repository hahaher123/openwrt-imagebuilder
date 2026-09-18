# openwrt-imagebuilder

用 OpenWrt 官方 **ImageBuilder** 生成可直接刷入的 x86_64 固件镜像，发布在本仓库的 Release 中。

镜像不自行编译内核与软件包，全部使用官方 `downloads.openwrt.org` 的发行版二进制，因此产物与
官方固件同源同版本，只多了定制包集与可自定义的 rootfs 分区大小。

## 获取镜像

在本仓库的 **Releases** 页面选择对应版本下载，每个 Release 提供**一个**整盘镜像：

```
openwrt-<版本>-<文件名标记>-x86-64-generic-ext4-combined-efi.img.gz
```

例如 `openwrt-25.12.5-ext4-1g-x86-64-generic-ext4-combined-efi.img.gz`。
`sha256` 与文件大小写在该 Release 的说明里。

## 镜像规格

| 项 | 值 |
| --- | --- |
| 架构 / target | x86_64 (`x86/64`) |
| profile | `generic` |
| 引导方式 | EFI（GPT 分区表） |
| 根文件系统 | ext4 |
| 内核分区 | 16 MiB |
| rootfs 分区 | 1024 MiB |
| 镜像形态 | `combined-efi` 整盘镜像（含引导扇区、内核分区、rootfs 分区） |

## 用法

### 全新安装

写入 U 盘、SSD 或虚拟机磁盘：

```sh
gunzip -c openwrt-25.12.5-ext4-1g-x86-64-generic-ext4-combined-efi.img.gz | dd of=/dev/sdX bs=4M
```

PVE / KVM 可直接把 `.img.gz` 解压后的文件作为磁盘导入。

### 从已有 OpenWrt 升级

```sh
sysupgrade openwrt-25.12.5-ext4-1g-x86-64-generic-ext4-combined-efi.img.gz
```

刷入前可先做无写入的预检，看是否会重写分区表：

```sh
sysupgrade -T openwrt-25.12.5-ext4-1g-x86-64-generic-ext4-combined-efi.img.gz
```

* 打印 `Partition layout has changed. Full image will be written.` —— 会整盘覆盖，磁盘上自建的
  其他分区（如数据分区）会被清除。
* 没有这行 —— 按分区增量写入，分区表与额外分区保留，配置也保留。

**本仓库的镜像固定 rootfs 为 1024 MiB**，所以在同一规格的自制镜像之间升级始终走增量写入。
只有从官方镜像（rootfs 104 MiB）首次切过来时，会因为分区大小不同而整盘写一次——这一次请先
`sysupgrade -b` 把配置备份到电脑上，且数据不要放在系统盘。

## 包含的软件包

在官方 `generic` profile 默认包集之上，主要追加：

* **LuCI**：`luci`、`luci-app-attendedsysupgrade`、`luci-proto-wireguard`、`natmap`
* **中文界面**：`luci-i18n-base-zh-cn`、`luci-i18n-firewall-zh-cn`、`luci-i18n-package-manager-zh-cn`、
  `luci-i18n-ttyd-zh-cn`、`luci-i18n-sqm-zh-cn`、`luci-i18n-unbound-zh-cn`、`luci-i18n-irqbalance-zh-cn`
* **网络与代理**：`nftables`、`kmod-nft-tproxy`、`kmod-nft-offload`、`kmod-tun`、`natmap`、`ethtool`
* **虚拟化与网卡驱动**：`kmod-vmxnet3`（VMware）、`kmod-amd-xgbe`、`kmod-bnx2`、`kmod-dwmac-intel`、
  `kmod-e1000`/`kmod-e1000e`、`kmod-forcedeth`、`kmod-igb`、`kmod-igc`、`kmod-ixgbe`、`kmod-ixgbevf`、
  `kmod-r8169`、`kmod-tg3`、`kmod-amazon-ena`、`kmod-drm-i915`
* **其他**：`dnsmasq-full`（替代默认的 `dnsmasq`）、`kmod-fs-vfat`、`openssl-util`、`curl`

完整包清单可在系统启动后执行 `apk list --installed` 查看。

## 许可

MIT。镜像中的 OpenWrt 及其软件包各自遵循其原始许可（以 GPL 系列为主）。
