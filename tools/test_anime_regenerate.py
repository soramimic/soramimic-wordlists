import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image


def load_module():
    path = Path(__file__).with_name("anime_regenerate.py")
    spec = importlib.util.spec_from_file_location("anime_regenerate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_grid(root: Path, key: str, words: list[str], accepted=None) -> None:
    grids = root / "grids"
    grids.mkdir(parents=True, exist_ok=True)
    data = {"words": words, "cols": 2, "rows": 2}
    if accepted is not None:
        data["accepted"] = accepted
    (grids / f"{key}.json").write_text(json.dumps(data), encoding="utf-8")
    Image.new("RGB", (101, 103), "white").save(grids / f"grid_{key}.png")


def test_split_grids_respects_accepted_and_non_divisible_size(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "WORK", tmp_path)
    write_grid(tmp_path, "one", ["ac_0001", "ac_0002"], [True, False])

    module.split_grids()

    with Image.open(tmp_path / "images" / "ac_0001.jpg") as image:
        assert image.size == (720, 720)
    assert not (tmp_path / "images" / "ac_0002.jpg").exists()


def test_split_grids_rejects_duplicate_accepted_stem(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "WORK", tmp_path)
    write_grid(tmp_path, "one", ["dc_0001"])
    write_grid(tmp_path, "two", ["dc_0001"])

    with pytest.raises(ValueError, match="duplicate accepted output stem"):
        module.split_grids()


def test_split_grids_rejects_invalid_shape(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "WORK", tmp_path)
    write_grid(tmp_path, "bad", ["ac_0001"])
    meta = tmp_path / "grids" / "bad.json"
    data = json.loads(meta.read_text(encoding="utf-8"))
    data["cols"] = 0
    meta.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="positive integers"):
        module.split_grids()
