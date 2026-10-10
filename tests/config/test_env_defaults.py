from __future__ import annotations

import importlib
import os

import pytest

import app
import lib


@pytest.mark.parametrize("package", [app, lib])
def test_package_import_defaults_litellm_local_cost_map(monkeypatch, package) -> None:
    monkeypatch.delenv("LITELLM_LOCAL_MODEL_COST_MAP")

    importlib.reload(package)

    assert os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] == "True"


def test_package_import_respects_explicit_litellm_cost_map_setting(monkeypatch) -> None:
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "False")

    importlib.reload(app)

    assert os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] == "False"
