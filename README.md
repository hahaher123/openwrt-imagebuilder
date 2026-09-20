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
| 出厂 LAN 地址 | `192.168.100.1` | `192.168.100.1` |
| 引导 | GRUB（EFI） | u-boot |

出厂 LAN 地址由 `config/<配置>.conf` 的 `LAN_IP` 决定，写进镜像的
`/etc/uci-defaults/99-lan-ip`，**首次启动时**生效（把 OpenWrt 默认的 `192.168.1.1` 换掉），
所以刷完开机后管理页在 `http://192.168.100.1/`。

它只在该地址仍是出厂默认值时才动手：自己改过 LAN 地址的设备，升级后不会被冲回默认值。

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

刷入后 LAN 地址保持为原来的设置；只有仍停在出厂默认 `192.168.1.1` 的设备会被改成上面的出厂
LAN 地址。

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

完整清单以 `config/<配置>.conf` 的 `PACKAGES` 与 `CUSTOM_ASSETS` 为准，或系统启动后执行
`apk list --installed` 查看。

### 自建包与第三方包

上面两类都是官方源里的包。此外还有一批**不在官方源里**的包，构建时从各自仓库的
**最新 Release** 抓取后一并装入（来源与匹配规则见 `config/<配置>.conf` 的 `CUSTOM_ASSETS`，
抓取与格式校验由 `scripts/fetch-custom-packages.py` 完成）：

| 来源仓库 | 装入的包 | 说明 |
| --- | --- | --- |
| `hahaher123/openwrt-mihomo` | `mihomo`、`luci-app-mihomo` | mihomo 内核与 LuCI 界面 |
| `hahaher123/openwrt-oxidns` | `oxidns` | oxidns 主程序 |
| `hahaher123/luci-app-oxidns` | `luci-app-oxidns`、`luci-i18n-oxidns-zh-cn` | oxidns 的 LuCI 界面（含规则文件编辑） |
| `hahaher123/luci-app-natmap` | `luci-app-natmap`、`luci-i18n-natmap-zh-cn` | natmap 的 LuCI 界面 |
| `sirpdboy/luci-app-ddns-go` | `ddns-go`、`luci-app-ddns-go`、`luci-i18n-ddns-go-zh-cn` | 第三方仓库，按架构提供 `SNAPSHOT-<架构>.tar.gz` |

三点须知：

* 每个包都会按目标架构校验（必须标 `noarch` 或与该目标匹配），拿错架构会直接让构建失败；
  包名由脚本从包元数据里读出、自动并入 `PACKAGES`，无需在配置里重复列举。
* 并入 `PACKAGES` 时**钉死版本**（`包名=版本`）：`packages/` 只是 apk 的又一个仓库，
  同名包若在官方源里也有、且版本号排序更高，apk 会选官方那个。构建末段会拿 manifest
  逐个核对「名字 + 版本」，被盖住会直接报错而不是静默装成别的版本。
  为此构建时会先给 ImageBuilder 打一个一行补丁（它自带的 `FormatPackages` 会让
  版本后缀泄漏到后续所有包上，导致「unable to select packages」）；
  上游修好后该步骤可删，补丁锚点对不上时构建会直接报错。
* 取的是各仓库的**最新 Release**，这些包的版本因此由上游决定、不由本仓库固定。其中
  `sirpdboy/luci-app-ddns-go` 是第三方来源，它的 `SNAPSHOT-*` 资产会随上游重建而变动。

## 重新构建

默认构建目标（版本号 + 配置）在整个仓库里只在 **`config/build.conf`** 一处定义：

```sh
VERSION="25.12.5"
ARCH="x86_64"
```

* **换 OpenWrt 版本** → 改 `VERSION` 一行。
* **换目标** → 改 `ARCH` 一行，取值是 `config/<配置>.conf` 的文件名（`x86_64` 或 `r2s`，
  将来新增目标就照现有文件复制一份改内容）。
* **换包集 / rootfs 分区大小 / 出厂 LAN 地址** → 改 `config/<配置>.conf` 里对应的一行
  （`PACKAGES` / `ROOTFS_SIZE` / `LAN_IP`）。
* **换自建包来源** → 改 `config/<配置>.conf` 的 `CUSTOM_ASSETS` 一行或几行，格式为
  `owner/repo|资产名 glob`；整块留空或删掉，该目标就不再从外部仓库取包。

改完 push 到 `main` 即自动重建（触发路径：`config/**`、`files/**`、`scripts/**` 与工作流文件本身），
并把镜像发到 Release `v<版本>-<配置>`；同名 Release 只替换资产与说明，不新建。

不改仓库也可以：手动触发构建，在输入框里临时指定版本号、配置、profile、分区大小、出厂 LAN
地址或包集，留空即取 `config/` 下的配置（临时指定的值不会写回仓库）。

## 许可

MIT。镜像中的 OpenWrt 及其软件包各自遵循其原始许可（以 GPL 系列为主）。
