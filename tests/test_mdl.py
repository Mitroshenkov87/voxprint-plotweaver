"""VOXPrint MDL plans the stock set. Plotweaver does not download it."""

from __future__ import annotations

from voxprint_common.gpu_probe import VramTier
from voxprint_common.mdl.catalog import load_manifest, plan_files

from plotweaver.mdl_progress import (
    download_command,
    installer_gui_command,
    manage_command,
    mdl_gui_supported,
    verify_repair_command,
)
from plotweaver.paths import repo_root

_T_LITE_Q4 = "68c75f5940c36baca18113058ad3d55f6d1d3e1123a8053bb4bba8481805c960"
_GEMMA_12 = "0a270ec9fe6b34f4a0d33992b6135117b484ebc4766ab76b51d4ae8c457e4c42"
_T_PRO = "b19e88cc1154b4b0c99f09bc7b57b8e5f3a6af4135581a3bfd31a2518ed58714"
_T_LITE_ABL_IQ4 = "0f0d10020cd7186c5fa46eed0feb5007f5af7fdef01dcd90883e8fe5ee758df0"
_GEMMA_12_ABL = "46fce9e43ba9d625317e95513c6a47d126196a300536b54391c88e6d1ad9573a"
_QWEN_27B_Q5 = "a4fd0da6216fb8b9a74e25a688a118b001888b704e17f5c851c2bd80f4f5e284"


def test_manage_models_uses_the_mdl_window() -> None:
    assert mdl_gui_supported() is True
    command = manage_command()
    assert command[-5:] == ["-m", "voxprint_common.mdl", "--gui", "--app", "plotweaver"]
    assert "download" not in command
    installer = installer_gui_command()
    assert installer[-6:] == [
        "-m",
        "voxprint_common.mdl",
        "download",
        "--gui",
        "--app",
        "plotweaver",
    ]
    repair = verify_repair_command()
    assert repair[-6:] == ["-m", "voxprint_common.mdl", "verify", "--repair", "--app", "plotweaver"]


def test_download_command_is_json_events() -> None:
    command = download_command(("t-lite-it-2.1-q4",))
    assert command[-8:] == [
        "-m",
        "voxprint_common.mdl",
        "download",
        "--app",
        "plotweaver",
        "--json",
        "--model",
        "t-lite-it-2.1-q4",
    ]
    assert "--gui" not in command


def test_16gb_default_is_two_abliterated_files_and_24gb_is_qwen() -> None:
    manifest = load_manifest(repo_root() / "src" / "plotweaver" / "data" / "mdl.json")
    sixteen = {item.sha256 for item in plan_files([manifest], VramTier.GB16)}
    assert sixteen == {_T_LITE_ABL_IQ4, _GEMMA_12_ABL}
    twenty = [item.sha256 for item in plan_files([manifest], VramTier.GB24)]
    assert twenty == [_QWEN_27B_Q5]
