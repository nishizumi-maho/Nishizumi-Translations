import re
import tomllib
from pathlib import Path

import jp2subs
from jp2subs import branding
from jp2subs.runtime import updater

ROOT = Path(__file__).resolve().parent.parent


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", jp2subs.__version__)


def test_branding_reuses_the_package_version():
    assert branding.VERSION == jp2subs.__version__
    assert jp2subs.__version__ in branding.window_title()


def test_pyproject_reads_the_version_from_the_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "version" in data["project"]["dynamic"]
    assert data["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "jp2subs.__version__"}


def test_updater_points_at_this_repository():
    assert updater.REPO == f"{branding.REPO_OWNER}/{branding.REPO_NAME}"
    assert updater.current_version() == jp2subs.__version__


def test_installer_script_declares_the_matching_app_name():
    script = (ROOT / "installer" / "jp2subs.iss").read_text(encoding="utf-8")

    assert f'#define MyAppName "{branding.APP_NAME}"' in script
    assert "PrivilegesRequired=lowest" in script
