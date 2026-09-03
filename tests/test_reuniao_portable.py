"""Running the app out of its own folder, for machines that refuse the rest."""
from __future__ import annotations

import pytest

from jp2subs.runtime import store
from reuniao import config, portable


@pytest.fixture
def program_folder(tmp_path, monkeypatch):
    """A pretend install folder, with every path decision reset around it."""

    folder = tmp_path / "NishizumiReunioes"
    folder.mkdir()
    monkeypatch.setattr(portable, "app_dir", lambda: folder)
    monkeypatch.delenv(store.ENV_DATA_DIR, raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv(portable.ENV_FLAG, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "perfil-do-usuario"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "perfil-do-usuario"))
    portable._reset_for_tests()
    yield folder
    portable._reset_for_tests()


def test_without_the_marker_nothing_changes(program_folder, tmp_path):
    assert portable.is_active() is False
    assert config.config_dir() == tmp_path / "perfil-do-usuario" / "reuniao"


def test_the_marker_moves_the_models_and_the_settings(program_folder):
    portable.write_marker()
    portable._reset_for_tests()

    assert portable.activate() is True
    assert store.data_dir() == program_folder / "dados" / "componentes"
    assert config.config_dir() == program_folder / "dados" / "config"


def test_settings_are_written_inside_the_program_folder(program_folder):
    portable.write_marker()
    portable._reset_for_tests()
    portable.activate()

    config.save_settings(config.Settings())

    assert (program_folder / "dados" / "config" / "config.json").exists()
    # Nothing reached the user profile.
    assert not (program_folder.parent / "perfil-do-usuario").exists()


def test_the_marker_explains_itself(program_folder):
    text = portable.write_marker().read_text(encoding="utf-8")

    assert "modo portátil" in text.lower()
    assert portable.DATA_FOLDER in text
    # It says how to undo it, because a stray file nobody understands is worse.
    assert "apague" in text.lower()


def test_the_environment_variable_overrides_the_marker_both_ways(program_folder, monkeypatch):
    portable.write_marker()
    monkeypatch.setenv(portable.ENV_FLAG, "0")
    portable._reset_for_tests()

    assert portable.requested() is False

    monkeypatch.setenv(portable.ENV_FLAG, "sim")
    portable._reset_for_tests()
    assert portable.requested() is True


def test_a_folder_that_cannot_be_written_falls_back_instead_of_failing(
    tmp_path, monkeypatch
):
    # A program folder inside a regular file: creating anything under it is
    # impossible, which is the closest stand-in for a locked-down disk.
    blocker = tmp_path / "nao-e-pasta"
    blocker.write_text("arquivo", encoding="utf-8")
    monkeypatch.setattr(portable, "app_dir", lambda: blocker / "programa")
    monkeypatch.delenv(store.ENV_DATA_DIR, raising=False)
    monkeypatch.setenv(portable.ENV_FLAG, "1")
    monkeypatch.setenv("APPDATA", str(tmp_path / "perfil"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "perfil"))
    portable._reset_for_tests()

    assert portable.activate() is False
    assert portable.is_active() is False
    assert portable.problem()  # it says why, rather than failing silently
    assert store.ENV_DATA_DIR not in __import__("os").environ
    assert config.config_dir() == tmp_path / "perfil" / "reuniao"
    portable._reset_for_tests()


def test_the_components_page_says_which_mode_is_in_force(program_folder):
    portable.write_marker()
    portable._reset_for_tests()
    portable.activate()

    assert str(program_folder) in portable.describe()


def test_an_explicit_data_folder_still_wins(program_folder, monkeypatch, tmp_path):
    # Someone who points the store somewhere on purpose keeps that choice.
    chosen = tmp_path / "disco-externo"
    monkeypatch.setenv(store.ENV_DATA_DIR, str(chosen))
    portable.write_marker()
    portable._reset_for_tests()

    portable.activate()

    assert store.data_dir() == chosen
