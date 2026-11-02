import os
import sys

import utils


def test_theme_is_found_from_any_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert os.path.isfile(utils.resource_path("theme_dark_grey.json"))


def test_packaged_app_looks_in_its_unpacked_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert utils.resource_path("theme_dark_grey.json") == str(tmp_path / "theme_dark_grey.json")
