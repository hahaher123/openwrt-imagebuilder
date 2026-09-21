# openwrt-imagebuilder

用 OpenWrt 官方 **ImageBuilder** 生成可直接刷入的固件镜像，发布在本仓库的 Release 中。

镜像不自行编译内核与软件包，全部使用官方 `downloads.openwrt.org` 的发行版二进制，因此产物与
官方固件同源同版本，只多了定制包集与可自定义的 rootfs 分区大小。

## 获取镜像

在 **Releases** 页面下载，**列表最上面一条就是最新镜像** —— 每次构建都是一条带日期的新发布，
有没有更新一眼可见。每条发布提供**一个**整盘镜像，构建时间、提交、`sha256` 与文件大小都写在发布
说明里，可用来核对拿到的文件对不对。

## 支持的目标

| 配置 | target / profile | 发布变体 | 刷入方式 |
| --- | --- | --- | --- |
| `x86_64` | `x86/64` · `generic` | `ext4-combined-efi` | U 盘 / SSD / 虚拟机磁盘（含 PVE） |
| `r2s` | `rockchip/armv8` · `friendlyarm_nanopi-r2s` | `ext4-sysupgrade` | microSD 卡 |

产物形态由平台引导方式决定：x86 用 GRUB，出 `combined-efi`（引导扇区 / 内核 / rootfs 一体）；
rockchip 用 u-boot，出 `sysupgrade` 整盘镜像。**rockchip 没有 combined-efi**。

## 镜像规格

| 项 | x86_64 | r2s |
| --- | --- | --- |
| 根文件系统 | ext4 | ext4 |
| 内核分区 | 16 MiB | 16 MiB |
| rootfs 分区 | 1024 MiB | 1024 MiB |
| 出厂 LAN 地址 | `192.168.100.1` | `192.168.100.1` |

官方镜像的 rootfs 分区是 104 MiB，这里统一放大到 **1024 MiB**（多占约 6 MiB 压缩体积），换来一块
够用的可写分区。

出厂 LAN 地址**首次启动时**生效，把 OpenWrt 默认的 `192.168.1.1` 换成上表地址，所以刷完开机后
管理页在 `http://192.168.100.1/`（x86_64 会跳到 `https://`，见「Web 服务」）。它只在该地址仍是出厂
默认值时才动手：自己改过 LAN 地址的设备，升级后不会被冲回默认值。

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

刷入后 LAN 地址保持原来的设置；只有仍停在出厂默认 `192.168.1.1` 的设备会被改成上表的出厂地址。

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

**本仓库的 rootfs 固定为 1024 MiB**，同一规格的自制镜像之间升级始终走增量写入；只有从官方镜像
（rootfs 104 MiB）首次切过来时，会因分区大小不同而整盘写一次 —— 这一次请先 `sysupgrade -b` 把配置
备份到电脑上，且数据不要放在系统盘。

## 包含的软件包

在官方对应 profile 的默认包集之上追加。

* **LuCI**：`luci`（x86_64 换成 `luci-nginx` + `nginx-ssl`，见「Web 服务」）、
  `luci-app-attendedsysupgrade`、`luci-proto-wireguard`
* **简体中文界面**：`luci-i18n-base-zh-cn`、`luci-i18n-firewall-zh-cn`、
  `luci-i18n-package-manager-zh-cn`、`luci-i18n-ttyd-zh-cn`、`luci-i18n-sqm-zh-cn`、
  `luci-i18n-unbound-zh-cn`、`luci-i18n-irqbalance-zh-cn`
* **网络与代理**：`nftables`、`kmod-nft-tproxy`、`kmod-nft-offload`、`natmap`、`ethtool`
* **其他**：`dnsmasq-full`（替代默认的 `dnsmasq`）、`kmod-fs-vfat`（挂 U 盘）
* **仅 x86_64**：网卡驱动一排 —— `kmod-e1000`、`kmod-e1000e`、`kmod-igb`、`kmod-igc`、`kmod-ixgbe`、
  `kmod-ixgbevf`、`kmod-r8169`、`kmod-tg3`、`kmod-forcedeth`、`kmod-bnx2`、`kmod-amd-xgbe`、
  `kmod-dwmac-intel`、`kmod-amazon-ena`；`kmod-drm-i915`；`grub2-bios-setup`；`kmod-button-hotplug`
* **仅 r2s**：`kmod-usb-net-rtl8152`（第二个千兆口挂在 USB 3.0 上，缺它就只剩一个网口）、
  `uboot-envtools`、`kmod-gpio-button-hotplug`

此外还装入一批**不在官方源里**的包，构建时从各自仓库的最新 Release 抓取：

| 来源仓库 | 装入的包 |
| --- | --- |
| `hahaher123/openwrt-mihomo` | `mihomo`、`luci-app-mihomo` |
| `hahaher123/openwrt-oxidns` | `oxidns` |
| `hahaher123/luci-app-oxidns` | `luci-app-oxidns`、`luci-i18n-oxidns-zh-cn`（含规则文件编辑） |
| `hahaher123/luci-app-natmap` | `luci-app-natmap`、`luci-i18n-natmap-zh-cn` |
| `sirpdboy/luci-app-ddns-go` | `ddns-go`、`luci-app-ddns-go`、`luci-i18n-ddns-go-zh-cn`（第三方） |

取的都是各仓库的**最新 Release**，所以这些包的版本由上游决定、不由本仓库固定。完整清单以设备上
执行 `apk list --installed` 为准。

### Web 服务：nginx 还是 uhttpd

OpenWrt 默认用 uhttpd，本仓库的 **x86_64 目标改用 nginx**，r2s 保持默认。

**访问方式随之变化（仅 x86_64）**：80 端口只把请求 `302` 跳到 HTTPS，LuCI 实际在 443，证书是
**首次启动时自动生成的自签名证书**。所以刷完访问 `https://192.168.100.1/`（输入 `http://` 会被
跳过去），浏览器会提示证书不受信任 —— 自签证书的正常现象，确认继续即可。访问范围限定在私有网段
（`192.168.0.0/16`、`10.0.0.0/8`、`172.16.0.0/12` 等），公网访问不到。

想改回「纯 HTTP、不跳转、不弹证书警告」，在设备上执行：

```sh
uci add_list nginx._lan.listen='80'
uci add_list nginx._lan.listen='[::]:80'
uci delete nginx._redirect2ssl
uci commit nginx
/etc/init.d/nginx restart
```

## 许可

MIT。镜像中的 OpenWrt 及其软件包各自遵循其原始许可（以 GPL 系列为主）。
