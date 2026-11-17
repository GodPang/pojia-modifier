# -*- coding: utf-8 -*-
"""TeleAgent 目标契约：账号根定位、落点、往返可逆、asar 新头兼容。

黑盒：主流程用子进程 + 命令行，只看退出码与磁盘字节；asar 头解析用纯函数断言。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pojia  # noqa: E402


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def write_bytes(path, blob):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(blob)


def _seed(box, owner="v1_public_test"):
    """造一个 TeleAgent 账号根：设备根/user/账号/memory/USER.md + current-owner.json。"""
    device = os.path.join(box.home, ".local", "share", "TeleAgent")
    acct = os.path.join(device, "users", owner)
    user = os.path.join(acct, "memory", "USER.md")
    write_bytes(user,
                b"---\r\nAIGC:\r\n  Label: '1'\r\n---\r\n\r\n"
                b"# \xe7\x94\xa8\xe6\x88\xb7\xe9\x95\xbf\xe6\x9c\x9f\xe8\xae\xb0\xe5\xbf\x86\r\n\r\n"
                b"- \xe4\xb8\x80\xe6\x9d\xa1\xe5\xb7\xb2\xe6\x9c\x89\xe8\xae\xb0\xe5\xbf\x86\r\n")
    write_bytes(os.path.join(device, "current-owner.json"),
                ('{"ownerDir": "%s"}' % owner).encode("utf-8"))
    return device, acct, user


def test_registered_with_cli_flag():
    t = pojia.get_target("teleagent")
    assert t is not None
    assert t.dir_flag == "--teleagent-dir"
    assert t.mode == "block"
    assert t.instr.replace("\\", "/") == "memory/USER.md"
    assert t.key in pojia.target_keys()
    assert pojia.target_addendum("teleagent").strip()


def test_resolve_prefers_current_owner(box, monkeypatch):
    device, acct, _user = _seed(box)
    monkeypatch.setenv("HOME", box.home)
    monkeypatch.setenv("USERPROFILE", box.home)
    monkeypatch.delenv("TELEAGENT_DATA_DIR", raising=False)
    t = pojia.get_target("teleagent")
    root, src, _tried = t.resolve("")
    assert root == acct, (root, acct)
    assert "current-owner" in src
    assert t.is_valid(root)


def test_resolve_explicit_account_dir(box):
    _device, acct, _user = _seed(box)
    t = pojia.get_target("teleagent")
    root, _src, _tried = t.resolve(acct)
    assert root == acct


def test_roundtrip_idempotent_reversible(box):
    """注入 -> 再注入字节不变 -> 撤回逐字节还原（含 frontmatter 与 CRLF）。"""
    _device, _acct, user = _seed(box)
    orig = read_bytes(user)

    r1 = box.run("--apply", "--target", "teleagent", "--yes")
    assert r1.returncode == 0, box.out(r1)
    once = read_bytes(user)
    assert once != orig
    assert b"POJIA-NEXT-INJECT" in once

    r2 = box.run("--apply", "--target", "teleagent", "--yes")
    assert r2.returncode == 0, box.out(r2)
    assert read_bytes(user) == once, "二次注入不是幂等的"

    r3 = box.run("--status", "--target", "teleagent")
    assert "宽松态" in box.out(r3)

    r4 = box.run("--revert", "--target", "teleagent", "--yes")
    assert r4.returncode == 0, box.out(r4)
    assert read_bytes(user) == orig, "撤回没有逐字节还原"


def test_multi_account_only_current_touched(box):
    device, acct, _user = _seed(box, owner="v1_public_a")
    other = os.path.join(device, "users", "v1_public_b", "memory", "USER.md")
    write_bytes(other, b"other account, must stay untouched\r\n")
    before = read_bytes(other)

    r = box.run("--apply", "--target", "teleagent", "--yes")
    assert r.returncode == 0, box.out(r)
    assert read_bytes(other) == before


def test_asar_header_new_and_classic():
    """新版 Electron 的四 u32 头，与旧版 [size][json_size] 头都能解析。"""
    import json as _json
    import struct
    import tempfile

    header = {"files": {"a.js": {"offset": "0", "size": "2"}}}
    raw = _json.dumps(header).encode("utf-8")

    # 新格式：[4][size][size-4][json_len] + JSON；数据从 8+size 起
    size = len(raw) + 8
    new_blob = (struct.pack("<IIII", 4, size, size - 4, len(raw)) + raw + b"xx")
    # 旧格式：[size][json_len] + u32(json_len) + JSON
    old_size = len(raw) + 4
    old_blob = (struct.pack("<II", old_size, len(raw))
                + struct.pack("<I", len(raw)) + raw + b"xx")

    for blob in (new_blob, old_blob):
        path = os.path.join(tempfile.gettempdir(), "pojia_asar_probe.asar")
        write_bytes(path, blob)
        h, data_start = pojia.asar_read_header(path)
        assert h is not None, "头解析失败: %r" % blob[:16]
        assert "files" in h
        assert blob[data_start:data_start + 2] == b"xx", (data_start, blob[data_start:])
        os.remove(path)
