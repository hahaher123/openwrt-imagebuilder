# openwrt-imagebuilder

用 OpenWrt 官方 **ImageBuilder** 生成可直接刷入的固件镜像，发布在本仓库的 Release 中。

镜像不自行编译内核与软件包，全部使用官方 `downloads.openwrt.org` 的发行版二进制，因此产物与
官方固件同源同版本，只多了定制包集与可自定义的 rootfs 分区大小。

## 获取镜像

在 **Releases** 页面选择版本下载，每个 Release 提供**一个**整盘镜像，文件名形如：

```
openwrt-<版本>-<文件名标记>-x86-64-generic-ext4-combined-efi.img.gz
```

其中 `<文件名标记>` 由 `config/x86_64.conf` 的 `EXTRA_IMAGE_NAME` 决定（目前是 `ext4-1g`）。
`sha256` 与文件大小写在该 Release 的说明里。

## 默认镜像规格

默认目标是 **x86_64**（`x86/64`，profile `generic`）。可改写的定义在 `config/build.conf` 与
`config/x86_64.conf`，当前取值：

| 项 | 值 |
| --- | --- |
| 引导方式 | EFI（GPT 分区表） |
| 根文件系统 | ext4 |
| 内核分区 | 16 MiB |
| rootfs 分区 | 1024 MiB |
| 镜像形态 | `combined-efi` 整盘镜像（引导扇区 + 内核分区 + rootfs 分区） |

## 用法

### 全新安装

写入 U 盘、SSD 或虚拟机磁盘：

```sh
gunzip -c openwrt-<版本>-ext4-1g-x86-64-generic-ext4-combined-efi.img.gz | dd of=/dev/sdX bs=4M
```

PVE / KVM 可直接把解压后的 `.img` 作为磁盘导入。

### 从已有 OpenWrt 升级

```sh
sysupgrade openwrt-<版本>-ext4-1g-x86-64-generic-ext4-combined-efi.img.gz
```

刷入前可先做无写入的预检，看是否会重写分区表：

```sh
sysupgrade -T openwrt-<版本>-ext4-1g-x86-64-generic-ext4-combined-efi.img.gz
```

* 打印 `Partition layout has changed. Full image will be written.` —— 会整盘覆盖，磁盘上自建的
  其他分区（如数据分区）会被清除。
* 没有这行 —— 按分区增量写入，分区表与额外分区保留，配置也保留。

**本仓库的镜像 rootfs 固定为 1024 MiB**，所以在同一规格的自制镜像之间升级始终走增量写入。
只有从官方镜像（rootfs 104 MiB）首次切过来时，会因为分区大小不同而整盘写一次 —— 这一次请先
`sysupgrade -b` 把配置备份到电脑上，且数据不要放在系统盘。

## 包含的软件包

在官方 `generic` profile 默认包集之上，主要追加：

* **LuCI**：`luci`、`luci-app-attendedsysupgrade`、`luci-proto-wireguard`
* **简体中文界面**：`luci-i18n-base-zh-cn`、`luci-i18n-firewall-zh-cn`、
  `luci-i18n-package-manager-zh-cn`、`luci-i18n-ttyd-zh-cn`、`luci-i18n-sqm-zh-cn`、
  `luci-i18n-unbound-zh-cn`、`luci-i18n-irqbalance-zh-cn`
* **网络与代理**：`nftables`、`kmod-nft-tproxy`、`kmod-nft-offload`、`natmap`、`ethtool`
* **网卡驱动**：`kmod-e1000`、`kmod-e1000e`、`kmod-igb`、`kmod-igc`、`kmod-ixgbe`、`kmod-ixgbevf`、
  `kmod-r8169`、`kmod-tg3`、`kmod-forcedeth`、`kmod-bnx2`、`kmod-amd-xgbe`、`kmod-dwmac-intel`、
  `kmod-amazon-ena`
* **其他**：`dnsmasq-full`（替代默认的 `dnsmasq`）、`kmod-fs-vfat`、`kmod-drm-i915`

完整清单以 `config/x86_64.conf` 的 `PACKAGES` 为准，或系统启动后执行 `apk list --installed` 查看。

## 重新构建

版本号与架构在整个仓库里只在 **`config/build.conf`** 一处定义：

```sh
VERSION="25.12.5"
ARCH="x86_64"
```

* **换 OpenWrt 版本** → 改 `VERSION` 一行，push 到 `main`，自动重建并把新镜像发到 Release
  `v<版本>-<架构>`（同名 Release 只替换资产，不新建）。
* **换架构** → 改 `ARCH` 一行，并保证 `config/<架构>.conf` 存在（新增架构时照
  `config/x86_64.conf` 复制一份改内容）。
* **换包集 / rootfs 分区大小** → 改 `config/<架构>.conf` 对应的一行，同样是改一处。

不改仓库也可以：手动触发构建，在输入框里临时指定版本号、架构、分区大小或包集，留空即取
`config/build.conf`（临时指定的值不会写回仓库）。

## 许可

MIT。镜像中的 OpenWrt 及其软件包各自遵循其原始许可（以 GPL 系列为主）。
