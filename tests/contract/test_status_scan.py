# -*- coding: utf-8 -*-
"""界面用的四档状态：未安装 / 未破甲 / 部分破甲 / 已破甲。

判据是护照里的文件戳记（大小 + sha256 前 16 位），不是 markers，也不是主文件
里那串哈希。原因很实在：客户端一升级就把注入过的文件整树换回出厂版本，主文件
里连标记都没了，可护照还躺在 .pojia 下说「我写过」。只看主文件会把这种机器报成
「未安装」或「严格态」，而用户真正需要看见的是「一部分文件被人换回去了」。

于是四档是这么分的：
    护照里一个戳记都没有        -> clean（未破甲）
    有戳记、但一个都对不上      -> clean（写过的全被换回去了）
    对上一部分                  -> partial（部分破甲）
    全对上                      -> full（已破甲）
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pojia  # noqa: E402


class FakeTarget(object):
    """只实现 scan_target 用到的那几个口子。"""

    key = "fake"
    name = "Fake 工具"

    def __init__(self, root="", label="严格态", detail=""):
        self._root = root
        self._label = label
        self._detail = detail

    def resolve(self, explicit=""):
        return (self._root, "测试", [])

    def status(self, root, ctx):
        return (self._label, self._detail)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _passport(root, stamps, version=None):
    pojia.passport_save(str(root), {
        "tool": pojia.APP,
        "version": version or pojia.VERSION,
        "target": "fake",
        "root": str(root),
        "file_stamps": dict(stamps),
        "kinds": {},
        "created": [],
        "persona_hash": "",
    })


def test_no_root_is_none():
    row = pojia.scan_target(FakeTarget(""), pojia.Ctx())
    assert row["state"] == "none"
    assert row["label"] == "未安装"


def test_no_passport_is_clean(tmp_path):
    root = tmp_path / "app"
    _write(str(root / "keep.txt"), "x")
    row = pojia.scan_target(FakeTarget(str(root)), pojia.Ctx())
    assert row["state"] == "clean"
    assert row["total"] == 0


def test_all_stamps_match_is_full(tmp_path):
    root = tmp_path / "app"
    _write(str(root / "a.md"), "alpha")
    _write(str(root / "b.json"), "{}")
    stamps = {str(root / "a.md"): pojia.file_stamp(str(root / "a.md")),
              str(root / "b.json"): pojia.file_stamp(str(root / "b.json"))}
    _passport(root, stamps)

    row = pojia.scan_target(FakeTarget(str(root)), pojia.Ctx())
    assert (row["state"], row["hit"], row["total"]) == ("full", 2, 2)
    assert row["stale"] is False


def test_half_replaced_is_partial(tmp_path):
    root = tmp_path / "app"
    _write(str(root / "a.md"), "alpha")
    _write(str(root / "b.json"), "{}")
    stamps = {str(root / "a.md"): pojia.file_stamp(str(root / "a.md")),
              str(root / "b.json"): pojia.file_stamp(str(root / "b.json"))}
    _passport(root, stamps)

    # 客户端升级把其中一个换回出厂版
    _write(str(root / "b.json"), '{"fresh": true}')

    row = pojia.scan_target(FakeTarget(str(root)), pojia.Ctx())
    assert (row["state"], row["hit"], row["total"]) == ("partial", 1, 2)


def test_every_file_replaced_is_clean(tmp_path):
    root = tmp_path / "app"
    _write(str(root / "a.md"), "alpha")
    stamps = {str(root / "a.md"): pojia.file_stamp(str(root / "a.md"))}
    _passport(root, stamps)

    _write(str(root / "a.md"), "back to factory")

    row = pojia.scan_target(FakeTarget(str(root)), pojia.Ctx())
    assert row["state"] == "clean"


def test_missing_file_counts_as_lost(tmp_path):
    root = tmp_path / "app"
    _write(str(root / "a.md"), "alpha")
    _write(str(root / "b.md"), "beta")
    stamps = {str(root / "a.md"): pojia.file_stamp(str(root / "a.md")),
              str(root / "b.md"): pojia.file_stamp(str(root / "b.md"))}
    _passport(root, stamps)

    os.remove(str(root / "b.md"))

    row = pojia.scan_target(FakeTarget(str(root)), pojia.Ctx())
    assert (row["state"], row["hit"]) == ("partial", 1)


def test_old_version_stamp_is_flagged(tmp_path):
    root = tmp_path / "app"
    _write(str(root / "a.md"), "alpha")
    stamps = {str(root / "a.md"): pojia.file_stamp(str(root / "a.md"))}
    _passport(root, stamps, version="1.02")

    row = pojia.scan_target(FakeTarget(str(root)), pojia.Ctx())
    assert row["state"] == "full"
    assert row["stale"] is True
    assert "1.02" in row["detail"]


def test_marker_without_passport_is_full(tmp_path):
    """有标记、没护照：别的版本写过的，算已破甲但标过期。"""
    root = tmp_path / "app"
    _write(str(root / "a.md"), "alpha")
    row = pojia.scan_target(
        FakeTarget(str(root), "宽松态·过期", "哈希来自上一版"), pojia.Ctx())
    assert row["state"] == "full"
    assert row["stale"] is True


def test_status_json_line(tmp_path, capsys):
    root = tmp_path / "app"
    _write(str(root / "a.md"), "alpha")
    stamps = {str(root / "a.md"): pojia.file_stamp(str(root / "a.md"))}
    _passport(root, stamps)

    code = pojia.do_status_json(pojia.Ctx(), [
        FakeTarget(str(root)), FakeTarget("")])
    out = capsys.readouterr().out

    assert code == 0
    line = [x for x in out.splitlines() if x.startswith("#status ")][0]
    import json
    rows = json.loads(line[len("#status "):])
    assert [r["state"] for r in rows] == ["full", "none"]
    # 顺序按传进来的 targets 走，界面按 key 对，不依赖并行完成的先后
    assert [r["key"] for r in rows] == ["fake", "fake"]


def test_state_labels_cover_every_state():
    assert set(pojia._STATE_LABEL) == {"none", "clean", "partial", "full"}


def test_auto_scan_defaults_off():
    """启动自检默认关：开一次界面就扫二十个目标的安装目录，机械盘上能卡好几秒。"""
    import json
    saved = None
    path = pojia.state_path(pojia.SETTINGS_FILE)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                saved = fh.read()
        pojia.save_json(path, {"channel": "beta"})
        assert pojia.load_settings()["auto_scan"] is False

        pojia.save_settings(auto_scan=True)
        assert pojia.load_settings()["auto_scan"] is True
        pojia.save_settings(auto_scan=False)
        assert pojia.load_settings()["auto_scan"] is False
    finally:
        if saved is None:
            try:
                os.remove(path)
            except OSError:
                pass
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(saved)
