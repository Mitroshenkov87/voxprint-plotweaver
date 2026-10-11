"""VOXPrint MDL plans the stock set. Plotweaver does not download it."""

from __future__ import annotations

from voxprint_common.gpu_probe import VramTier
from voxprint_common.mdl.catalog import load_manifest, plan_files

from plotweaver.mdl_progress import download_command, mdl_gui_supported
from plotweaver.paths import repo_root

_T_LITE_Q4 = "68c75f5940c36baca18113058ad3d55f6d1d3e1123a8053bb4bba8481805c960"
_GEMMA_12 = "0a270ec9fe6b34f4a0d33992b6135117b484ebc4766ab76b51d4ae8c457e4c42"
_T_PRO = "b19e88cc1154b4b0c99f09bc7b57b8e5f3a6af4135581a3bfd31a2518ed58714"


def test_gui_flag_waits_for_0_2_2() -> None:
    assert mdl_gui_supported() is False


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


def test_16gb_stock_is_two_files_and_24gb_is_t_pro() -> None:
    manifest = load_manifest(repo_root() / "src" / "plotweaver" / "data" / "mdl.json")
    sixteen = {item.sha256 for item in plan_files([manifest], VramTier.GB16)}
    assert sixteen == {_T_LITE_Q4, _GEMMA_12}
    twenty = [item.sha256 for item in plan_files([manifest], VramTier.GB24)]
    assert twenty == [_T_PRO]
