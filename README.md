# openwrt-imagebuilder

用 OpenWrt 官方 **ImageBuilder** 生成可直接刷入的固件镜像，发布在本仓库的 Release 中。

镜像不自行编译内核与软件包，全部使用官方 `downloads.openwrt.org` 的发行版二进制，因此产物与
官方固件同源同版本，只多了定制包集与可自定义的 rootfs 分区大小。

## 获取镜像

在 **Releases** 页面下载，**列表最上面一条就是最新镜像** —— 每次构建都是一条带日期的新发布，
有没有更新一眼可见。每条发布提供整盘镜像本体与**同名的 `.sha256` 校验文件**两样；构建时间、提交、
`sha256` 与文件大小都写在发布说明里。把两个文件下到同一目录后，用
`sha256sum -c <镜像文件名>.sha256` 核对，输出 `<镜像文件名>: OK` 即为完好。

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
管理页在 `http://192.168.100.1/`。它只在该地址仍是出厂
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

### 升级时保留的配置

镜像出厂带 `/etc/sysupgrade.conf`（源文件 `files/etc/sysupgrade.conf`），把这两个目录**整目录**列入备份：

| 目录 | 内容 | 体积 |
| --- | --- | --- |
| `/etc/mihomo/` | `config.yaml`（用户配置）、`config.sh`、`ruleset/`、`ui/` 定制、`sources` | 33 MB（含 mmdb / cache.db） |
| `/etc/oxidns/` | `config.yaml`、`rule/*.txt` 分流规则 | 76 KB |

* 包自带的 `/lib/upgrade/keep.d/*` 与这里取**并集**：mihomo 包只保 `config.yaml`，其余靠本文件补全；
  oxidns 包已列 `/etc/oxidns/` 与 `/usr/share/v2ray/`，本文件再列一次是镜像级兜底（重复不会重复打包）。
* `sysupgrade` 用 `find` 展开目录、只收 `-type f` 与 `-type l` ⇒ **空目录不会还原**；
  `/etc/mihomo/{geoip,geosite}.dat` 这两个指向 `/usr/share/v2ray/` 的软链接按链接保存。
* 备份包实测约 **20 MB**（mmdb 压缩后），写入内存盘 `/tmp/sysupgrade.tgz`。

## 包含的软件包

在官方对应 profile 的默认包集之上追加。

* **LuCI**：`luci-nginx` + `nginx-ssl`（两个目标都用 nginx，见「Web 服务」）、
  `luci-app-attendedsysupgrade`、`luci-proto-wireguard`
* **简体中文界面**：`luci-i18n-base-zh-cn`、`luci-i18n-firewall-zh-cn`、
  `luci-i18n-package-manager-zh-cn`、`luci-i18n-ttyd-zh-cn`、`luci-i18n-sqm-zh-cn`、
  `luci-i18n-irqbalance-zh-cn`
* **网络与代理**：`nftables`、`kmod-nft-tproxy`、`kmod-nft-offload`、`natmap`、`ethtool`
* **其他**：`dnsmasq-full`（替代默认的 `dnsmasq`）、`kmod-fs-vfat`（挂 U 盘）
* **拥塞控制**：`kmod-tcp-bbr`（BBR）。⚠️ 装在镜像里只是让 bbr **可选**（内核里它是模块），
  默认仍是 `cubic`。要启用，在设备上把这行写进 `/etc/sysctl.conf` 后执行 `sysctl -p`：

  ```
  net.ipv4.tcp_congestion_control=bbr
  ```

  用 `/etc/sysctl.conf` 而不是 `/etc/sysctl.d/*.conf`：后者不在 sysupgrade 的保留列表里，
  重刷后就没了（官方在该文件顶部有明确注释）。另外 `net.core.default_qdisc` 保持默认的
  `fq_codel` 即可 —— 这是转发设备，BBR 只作用于设备自身发起的连接，改 `default_qdisc`
  反而会连带动到所有接口的队列行为。
* **仅 x86_64**：网卡驱动一排 —— `kmod-e1000`、`kmod-e1000e`、`kmod-igb`、`kmod-igc`、`kmod-ixgbe`、
  `kmod-ixgbevf`、`kmod-r8169`、`kmod-tg3`、`kmod-forcedeth`、`kmod-bnx2`、`kmod-amd-xgbe`、
  `kmod-dwmac-intel`、`kmod-amazon-ena`；`kmod-drm-i915`；`grub2-bios-setup`；`kmod-button-hotplug`
* **仅 r2s**：`kmod-usb-net-rtl8152`（第二个千兆口挂在 USB 3.0 上，缺它就只剩一个网口）、
  `uboot-envtools`、`kmod-gpio-button-hotplug`
* **地理数据**：不以 apk 包预装（`v2ray-geoip` / `v2ray-geosite` 已移除），由构建时下载的
  Loyalsoldier 最新版直接进覆盖层，落点 `/usr/share/v2ray/{geoip.dat,geosite.dat}`，
  见下面的「地理数据」一节。

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

`ddns-go` 的运行日志默认会被它的 init 脚本重定向进系统日志（logread），镜像里由
`files/etc/uci-defaults/60-ddns-go-quiet` 在首次启动时移除该重定向；日志仍可在 LuCI
ddns-go 页面查看，不受影响。

### 地理数据（geoip.dat / geosite.dat）

两个 v2ray 地理数据库在整机里只有**一份**，落在 `/usr/share/v2ray/`：

| 文件 | 用途 | 归属 | 谁更新 |
| --- | --- | --- | --- |
| `geoip.dat` | oxidns 的 `geoip` provider（`cn` 段） | FILES 覆盖层（无 apk 归属） | oxidns |
| `geosite.dat` | oxidns 的 `geosite` provider（`gfw` / `google` / `category-ads*` …） | FILES 覆盖层（无 apk 归属） | oxidns |

* **内容来源**：构建时从 [Loyalsoldier/v2ray-rules-dat](https://github.com/Loyalsoldier/v2ray-rules-dat)
  取最新发布，按官方 `.sha256sum` 校验后写进 `FILES` 覆盖层 —— 这是镜像里唯一的来源
  （`v2ray-geoip` / `v2ray-geosite` 两个包已从包集移除，openwrt-oxidns 与 openwrt-mihomo
  的依赖里也不再声明它们）。用了哪个 tag 会写在 Release 正文里。
* **运行时刷新**：由设备上的 oxidns 负责 —— `download` 插件的目标目录就是 `/usr/share/v2ray`，
  默认 144 小时一次，下完再热重载 provider。mihomo 不参与，也**不再打包**这两个文件。
* **sysupgrade 视角**：文件无 apk 归属，靠 oxidns 包 keep.d 里的 `/usr/share/v2ray/` 条目
  整目录保留，升级不丢。
* **mihomo**：默认 `geodata-mode: false`，GEOIP 规则走 `Country.mmdb`（仍随 mihomo 包发布到
  `/etc/mihomo/`），这两个 `.dat` 平时不会被打开。mihomo 包安装时已把
  `/etc/mihomo/{geoip,geosite}.dat` 软链接到 `/usr/share/v2ray/`，无需手动建链。

### R2S 专属：接口定向与系统调优

只对 `friendlyarm,nanopi-r2s*` 生效（覆盖层是所有目标共用的，脚本里按板名判断）。

* **接口定向**：原生网口 `eth0` 作 **LAN**、USB 网口 `eth1` 作 **WAN**
  （官方默认正好相反：LAN=eth1/USB）。原生口接交换机/AP 要的是稳，USB 口跑上行单流够用。
* **CPU 调频**：`schedutil` + 最低 `816MHz` + 最高取**可用档位中的最高值**。
  官方内核的 opp 表最高只到 `1296MHz`；若换成带 `1512MHz` 档的内核
  （如 immortalwrt，它自己打了 dts 补丁），脚本会自动用满，无需改动。
* **中断绑核**：原生网卡中断 → CPU1、USB 网卡（xhci 控制器）中断 → CPU2，
  并把两个中断加入 irqbalance 的 `banirq` —— 它是常驻进程（默认每 10s 重平衡），
  不排除掉会把绑定覆盖回去。irqbalance 本身保持启用，只是 `interval` 放宽到 30s、避开 CPU0。
* **USB 网卡稳定性**：禁止 USB autosuspend；关闭 USB 网口（`eth1`）的
  `gro/gso/tso/rxvlan/txvlan` —— RTL8153 在高负载下开着这些 offload 容易触发发送超时与重传异常。

### Web 服务：nginx 还是 uhttpd

OpenWrt 默认用 uhttpd，本仓库的**两个目标都改用 nginx**。

**访问方式**：`http://192.168.100.1/` 直接打开 LuCI；`https://` 同样可用（证书是首次启动自动
生成的自签名证书，浏览器会提示不受信任，确认继续即可）。两种方式都限定在私有网段
（`192.168.0.0/16`、`10.0.0.0/8`、`172.16.0.0/12` 等），公网访问不到。

80 端口**直接提供 LuCI**，而不是跳转到 HTTPS —— 这一点与 OpenWrt 官方 nginx 默认行为相反，
由镜像里的 `files/etc/uci-defaults/59-nginx-http` 在首次启动时改掉。想只保留 HTTPS，删掉 80 的两条
监听即可：

```sh
uci del_list nginx._lan.listen='80'
uci del_list nginx._lan.listen='[::]:80'
uci commit nginx
/etc/init.d/nginx restart
```

## 软件源

镜像出厂时 `apk` 的更新源已换成**南京大学镜像**（`https://mirror.nju.edu.cn/openwrt`），
不再指向官方 `downloads.openwrt.org`。换源在**首次启动**时完成（`/etc/uci-defaults/58-apk-mirror`），
且**只换域名** —— feed 路径、条目与 `kmods/<内核>-<hash>/` 结构原样保留。

所以 `apk update` / `apk add` 开箱即用，不必自己换源。想改成别的源，直接编辑
`/etc/apk/repositories.d/distfeeds.list`（脚本只在文件仍指向官方源时才动手，不会覆盖你的改动）。

## 许可

MIT。镜像中的 OpenWrt 及其软件包各自遵循其原始许可（以 GPL 系列为主）。
