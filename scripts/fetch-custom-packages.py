#!/usr/bin/env python3
"""从各仓库的最新 Release 拉取自建 apk，校验后放进 ImageBuilder 的 packages/。

ImageBuilder 根目录的 `packages/` 是官方留给本地包的目录：把 .apk 放进去，
`make image` 会自动用 `apk mkndx` 建索引，`apk add` 就能装上（见 packages/README.md）。
本脚本负责「把包弄进那个目录」这一步。

配置来自环境变量（由 workflow 先 source config/<arch>.conf 再传进来）：

    CUSTOM_ASSETS   每行一条：`owner/repo|资产名 glob`
                    以 # 开头的行与空行忽略；glob 支持 fnmatch 通配
                    （`${ARCH_PACKAGES}` 之类已在 source conf 时展开）
    ARCH_PACKAGES   目标架构标识，如 x86_64 / aarch64_generic
    GH_TOKEN        可选，GitHub API token（提高速率上限；下载公开资产本身不需要）

资产可以直接是一个 .apk，也可以是一个内含 .apk 的 .tar.gz 归档
（sirpdboy/luci-app-ddns-go 就是后者：每个架构一个 tar.gz，里面放几个 apk）。
两种情况都能处理，配置里不用区分。

校验：每个包都必须是 apk-tools 3 的 ADB 容器（OpenWrt 25.12 格式），
且 arch 必须是 noarch 或等于 ARCH_PACKAGES —— 资产名里没带架构时不至于拿错。

用法::

    fetch-custom-packages.py --dest ib/<dir>/packages [--out-env FILE]

`--out-env` 写出 `CUSTOM_PKGS="…"`（本次放进来的包名，去重排序），
供 workflow 追加到 `PACKAGES=`。
"""

import argparse
import io
import json
import os
import re
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zlib

API = "https://api.github.com"
PROXY_ENV = "CUSTOM_PKG_PROXY"  # 仅本地调试时设置；CI 里不设


def http_get(url, token=None, timeout=300):
    headers = {"User-Agent": "openwrt-imagebuilder"}
    if token and url.startswith(API):
        headers["Authorization"] = "Bearer " + token
        headers["Accept"] = "application/vnd.github+json"
    req = urllib.request.Request(url, headers=headers)
    handlers = []
    proxy = os.environ.get(PROXY_ENV)
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)
    return opener.open(req, timeout=timeout).read()


def latest_release(repo, token):
    """返回 (tag, {资产名: 下载地址})。"""
    url = "%s/repos/%s/releases/latest" % (API, repo)
    try:
        data = json.loads(http_get(url, token, timeout=60))
    except urllib.error.HTTPError as exc:
        raise SystemExit("查询 %s 的最新 Release 失败：HTTP %s %s"
                         % (repo, exc.code, exc.reason))
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    return data.get("tag_name", "?"), assets


# ---------------------------------------------------------------- ADB 校验
#
# 元数据字段是 <长度><内容> 的序列，长度前缀的宽度由内容长度决定
# （apk-tools src/adb.c 的 adb_w_blob_vec）：
#     > 0xffff -> 4 字节小端，> 0xff -> 2 字节小端，其余 1 字节。
# 数据流里没有类型标签字节，所以可能超 255 字节的 description 需要靠
# 「紧随其后的 arch 字段能否自洽解析」来反推宽度。
# 同一份解码逻辑在 luci-app-oxidns/scripts/check-apk.py 里也有一份，
# 两边改动要同步。

_ARCH_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_NEXT_FIELD_RE = re.compile(r"^[ -~]{1,64}$")


def adb_payload(raw, where):
    """解出 ADB 段内容；不是 ADB 容器就抛错。"""
    if raw[:3] != b"ADB":
        hint = ""
        if raw[:7] == b"!<arch>":
            hint = "（ipk / ar 归档）"
        elif raw[:2] == b"\x1f\x8b":
            hint = "（gzip 流，apk-tools 2.x 风格或 gzip 过的 tar）"
        raise SystemExit("%s：不是 ADB v3 容器%s，文件头 %r" % (where, hint, raw[:8]))
    decomp = zlib.decompressobj(-15)
    try:
        payload = decomp.decompress(raw[4:]) + decomp.flush()
    except zlib.error as exc:
        raise SystemExit("%s：ADB 段解压失败：%s" % (where, exc))
    if payload[:8] != b"ADB.pckg":
        raise SystemExit("%s：不是 ADB 的 pckg 段（%r）" % (where, payload[:8]))
    return payload


def _blob(payload, pos, width):
    if pos + width > len(payload):
        raise ValueError("元数据在偏移 %d 处被截断" % pos)
    size = int.from_bytes(payload[pos:pos + width], "little")
    start = pos + width
    end = start + size
    if end > len(payload):
        raise ValueError("字段越界（偏移 %d，长度 %d）" % (pos, size))
    return payload[start:end], end


def _printable_ascii(raw, key):
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise ValueError("字段 %s 不是 ASCII" % key)
    if not text or any(c < " " or c > "~" for c in text):
        raise ValueError("字段 %s 含不可打印字符" % key)
    return text


def read_meta(payload):
    """读元数据头：name / version / description / arch。

    只走前四个：OpenWrt 构建系统保证这四个都在且顺序固定。再往后的字段
    可能缺省（实测 sirpdboy 的包就没有 license），按位置硬走会失配。

    name / version 按 1 字节长度读；description 宽度未知，逐个候选试，
    用 arch 能否干净解析（以及其后一个字段像不像一段短 ASCII）来定夺。
    """
    total = int.from_bytes(payload[8:16], "little")
    content = int.from_bytes(payload[16:20], "little") & 0xFFFFFF
    if total != 20 + content:
        raise SystemExit("pckg 段头不自洽：u64@8=%d，20+%d=%d"
                         % (total, content, 20 + content))

    pos = 20
    meta = {}
    for key in ("name", "version"):
        raw, pos = _blob(payload, pos, 1)
        meta[key] = _printable_ascii(raw, key)

    for width in (1, 2, 4):
        try:
            desc, after_desc = _blob(payload, pos, width)
            arch, after_arch = _blob(payload, after_desc, 1)
            nxt, _ = _blob(payload, after_arch, 1)
            arch = _printable_ascii(arch, "arch")
            nxt = _printable_ascii(nxt, "arch 后面的字段")
        except ValueError:
            continue
        if _ARCH_RE.match(arch) and _NEXT_FIELD_RE.match(nxt):
            meta["description"] = desc.decode("utf-8", "replace")
            meta["arch"] = arch
            return meta

    raise SystemExit("无法确定 description 的长度编码（游标 %d），格式可能已变" % pos)


def split_apks(blob, asset_name):
    """把下载到的内容拆成 [(文件名, 字节)]：直接是 apk，或 tar.gz 里的成员。"""
    if blob[:3] == b"ADB":
        return [(asset_name, blob)]
    if blob[:2] == b"\x1f\x8b":
        try:
            tf = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
        except tarfile.TarError as exc:
            raise SystemExit("%s：不是可读的 tar.gz：%s" % (asset_name, exc))
        out = []
        for member in tf.getmembers():
            if member.isfile() and member.name.endswith(".apk"):
                out.append((os.path.basename(member.name), tf.extractfile(member).read()))
        if not out:
            raise SystemExit("%s：归档里没有 .apk" % asset_name)
        return out
    raise SystemExit("%s：既不是 apk 也不是 tar.gz，文件头 %r" % (asset_name, blob[:8]))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="下载各仓库最新 Release 里的自建 apk 到 ImageBuilder 的 packages/。")
    parser.add_argument("--dest", required=True, help="ImageBuilder 的 packages/ 目录")
    parser.add_argument("--out-env", help="写出 CUSTOM_PKGS 的文件")
    args = parser.parse_args(argv)

    specs = []
    for line in os.environ.get("CUSTOM_ASSETS", "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            specs.append(line)

    arch = os.environ.get("ARCH_PACKAGES", "").strip()
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()

    if not specs:
        print("CUSTOM_ASSETS 为空，没有要拉的包")
        if args.out_env:
            with open(args.out_env, "w", encoding="utf-8") as fh:
                fh.write('CUSTOM_PKGS=""\n')
        return 0

    print("目标架构 ARCH_PACKAGES = %s" % (arch or "(未设置)"))
    print("共 %d 条来源：" % len(specs))
    for s in specs:
        print("   ", s)
    print()

    os.makedirs(args.dest, exist_ok=True)

    import fnmatch

    release_cache = {}
    written = {}      # 文件名 -> 来源描述
    pkgnames = []     # 已放入的包名
    failures = []

    for spec in specs:
        if "|" not in spec:
            raise SystemExit("CUSTOM_ASSETS 里的行必须形如 owner/repo|资产glob：%s" % spec)
        repo, pattern = spec.split("|", 1)
        repo, pattern = repo.strip(), pattern.strip()

        if repo not in release_cache:
            release_cache[repo] = latest_release(repo, token)
        tag, assets = release_cache[repo]

        matched = sorted(n for n in assets if fnmatch.fnmatchcase(n, pattern))
        print("[%s] tag=%s  按 %r 匹配到 %d 个资产" % (repo, tag, pattern, len(matched)))
        if not matched:
            print("   可用资产（前 12 个）：")
            for n in sorted(assets)[:12]:
                print("      -", n)
            failures.append("%s：没有资产匹配 %r（tag %s）" % (repo, pattern, tag))
            continue

        for name in matched:
            print("   ↓ %s" % name)
            blob = http_get(assets[name], token)

            try:
                members = split_apks(blob, name)
            except SystemExit as exc:
                failures.append(str(exc))
                continue

            for fname, data in members:
                where = "%s / %s" % (repo, fname)
                payload = adb_payload(data, where)
                meta = read_meta(payload)

                if arch and meta["arch"] not in ("noarch", arch):
                    failures.append("%s：arch=%s 既不是 noarch 也不是 %s"
                                    % (where, meta["arch"], arch))
                    continue
                if fname in written:
                    failures.append("%s：文件名与 %s 冲突" % (where, written[fname]))
                    continue

                path = os.path.join(args.dest, fname)
                with open(path, "wb") as fh:
                    fh.write(data)
                written[fname] = where
                pkgnames.append(meta["name"])
                print("      ✓ %-46s %8d B  name=%s version=%s arch=%s"
                      % (fname, len(data), meta["name"], meta["version"], meta["arch"]))

    print()
    print("=" * 74)
    print("放进 packages/ 的包：%d 个，共 %d 字节"
          % (len(written), sum(os.path.getsize(os.path.join(args.dest, f)) for f in written)))
    for fname in sorted(written):
        print("   %-46s <- %s" % (fname, written[fname]))

    # 去重排序后写出去（同名包理论上不该出现，真出现前面的检查已经报错）
    custom = sorted(set(pkgnames))
    if args.out_env:
        with open(args.out_env, "w", encoding="utf-8") as fh:
            fh.write('CUSTOM_PKGS="%s"\n' % " ".join(custom))

    print()
    print("CUSTOM_PKGS=%s" % " ".join(custom))

    if failures:
        print()
        print("以下来源没有按预期拿到包：")
        for f in failures:
            print("   ✗", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
