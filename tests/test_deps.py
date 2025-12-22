from jp2subs import deps


def test_select_prefers_avx2_asset():
    release = {
        "assets": [
            {"name": "llama-bin-win-x64.zip", "browser_download_url": "https://example.com/fallback.zip"},
            {"name": "llama-bin-win-avx2-x64.zip", "browser_download_url": "https://example.com/preferred.zip"},
        ]
    }

    asset = deps.select_windows_asset(release)

    assert asset["name"] == "llama-bin-win-avx2-x64.zip"


def test_select_fallback_windows_asset():
    release = {
        "assets": [
            {"name": "README.txt", "browser_download_url": "https://example.com/readme"},
            {"name": "llama-bin-win-sse2-x64.zip", "browser_download_url": "https://example.com/fallback.zip"},
        ]
    }

    asset = deps.select_windows_asset(release)

    assert asset["name"] == "llama-bin-win-sse2-x64.zip"
