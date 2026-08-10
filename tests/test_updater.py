import sys

import pytest

from jp2subs import __version__
from jp2subs.runtime import updater


def test_parse_version_accepts_tags_and_prereleases():
    assert updater.parse_version("v2.1.0") == (2, 1, 0, "")
    assert updater.parse_version("2.1.0") == (2, 1, 0, "")
    assert updater.parse_version("2.1.0-rc1") == (2, 1, 0, "rc1")
    assert updater.parse_version("not-a-version") is None
    assert updater.parse_version("") is None


@pytest.mark.parametrize(
    ("candidate", "baseline", "expected"),
    [
        ("2.1.0", "2.0.0", True),
        ("2.0.0", "2.1.0", False),
        ("2.1.0", "2.1.0", False),
        ("2.10.0", "2.9.0", True),
        ("3.0.0", "2.99.99", True),
        ("2.1.1", "2.1.0", True),
        # A final release beats its own pre-releases, and vice versa.
        ("2.1.0", "2.1.0-rc1", True),
        ("2.1.0-rc1", "2.1.0", False),
        ("2.1.0-rc2", "2.1.0-rc1", True),
        ("garbage", "2.0.0", False),
    ],
)
def test_is_newer(candidate, baseline, expected):
    assert updater.is_newer(candidate, baseline) is expected


def test_pick_asset_prefers_the_windows_installer(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assets = [
        {"name": "source.zip", "browser_download_url": "u1", "size": 1},
        {"name": "Nishizumi-Translations-Setup-2.1.0.exe", "browser_download_url": "u2", "size": 2},
        {"name": "Nishizumi-Translations-Setup-2.1.0.exe.sha256", "browser_download_url": "u3", "size": 3},
    ]

    name, url, size = updater._pick_asset(assets)

    assert (name, url, size) == ("Nishizumi-Translations-Setup-2.1.0.exe", "u2", 2)


def test_pick_asset_returns_nothing_when_no_match(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")

    assert updater._pick_asset([{"name": "notes.txt", "browser_download_url": "u"}]) == ("", "", 0)


def test_to_release_maps_the_payload(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    release = updater._to_release(
        {
            "tag_name": "v2.2.0",
            "name": "Nishizumi Translations 2.2.0",
            "body": "notes here",
            "html_url": "https://example.invalid/release",
            "prerelease": False,
            "assets": [{"name": "Setup-2.2.0.exe", "browser_download_url": "u", "size": 10}],
        }
    )

    assert release.version == "2.2.0"
    assert release.tag == "v2.2.0"
    assert release.has_installer
    assert release.asset_size == 10


def test_latest_release_skips_drafts_and_prereleases(monkeypatch):
    payloads = [
        {"tag_name": "v3.0.0", "draft": True, "assets": []},
        {"tag_name": "v2.5.0", "prerelease": True, "assets": []},
        {"tag_name": "v2.2.0", "assets": []},
        {"tag_name": "v2.1.0", "assets": []},
        {"tag_name": "nightly", "assets": []},
    ]
    monkeypatch.setattr(updater, "fetch_json", lambda _url: payloads)

    assert updater.latest_release().tag == "v2.2.0"
    assert updater.latest_release(include_prerelease=True).tag == "v2.5.0"


def test_check_for_updates_compares_against_the_running_version(monkeypatch):
    monkeypatch.setattr(updater, "fetch_json", lambda _url: [{"tag_name": f"v{__version__}", "assets": []}])
    assert updater.check_for_updates() is None

    monkeypatch.setattr(updater, "fetch_json", lambda _url: [{"tag_name": "v99.0.0", "assets": []}])
    assert updater.check_for_updates().tag == "v99.0.0"


def test_download_update_refuses_a_release_without_an_installer():
    release = updater.ReleaseInfo(version="9.0.0", tag="v9.0.0", name="", notes="", html_url="")

    with pytest.raises(RuntimeError, match="no downloadable installer"):
        updater.download_update(release)


def test_launch_installer_rejects_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        updater.launch_installer(tmp_path / "nope.exe")
