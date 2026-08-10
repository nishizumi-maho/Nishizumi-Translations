import pytest

from jp2subs.runtime import search


def _payload(repo_id, files, downloads=100):
    return {
        "modelId": repo_id,
        "downloads": downloads,
        "likes": 3,
        "lastModified": "2026-01-02T03:04:05.000Z",
        "siblings": [{"rfilename": name} for name in files],
        "tags": ["ctranslate2"],
    }


CT2_FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
TORCH_FILES = ["config.json", "model.safetensors", "tokenizer.json"]


def test_search_keeps_only_loadable_repositories(monkeypatch):
    monkeypatch.setattr(
        search,
        "fetch_json",
        lambda _url: [
            _payload("owner/faster-whisper-ja", CT2_FILES, downloads=500),
            _payload("owner/plain-whisper", TORCH_FILES, downloads=900),
        ],
    )

    results = search.search_models("whisper japanese", with_sizes=False)

    assert [item.repo_id for item in results] == ["owner/faster-whisper-ja"]
    assert results[0].is_loadable
    assert results[0].downloads == 500
    assert results[0].last_modified == "2026-01-02"


def test_search_respects_the_limit(monkeypatch):
    monkeypatch.setattr(
        search,
        "fetch_json",
        lambda _url: [_payload(f"owner/model-{index}", CT2_FILES) for index in range(30)],
    )

    assert len(search.search_models("whisper", limit=5, with_sizes=False)) == 5


def test_search_defaults_to_a_useful_query(monkeypatch):
    captured = {}

    def fake_fetch(url):
        captured["url"] = url
        return []

    monkeypatch.setattr(search, "fetch_json", fake_fetch)
    search.search_models("   ", with_sizes=False)

    assert "faster-whisper" in captured["url"]
    assert "full=true" in captured["url"]


def test_search_survives_an_unexpected_response(monkeypatch):
    monkeypatch.setattr(search, "fetch_json", lambda _url: {"error": "nope"})

    assert search.search_models("whisper", with_sizes=False) == []


def test_result_helpers():
    result = search.SearchResult(repo_id="kotoba-tech/kotoba-whisper-v2.0-faster", files=tuple(CT2_FILES))

    assert result.owner == "kotoba-tech"
    assert result.name == "kotoba-whisper-v2.0-faster"
    assert result.is_loadable


def test_result_without_weights_is_not_loadable():
    assert not search.SearchResult(repo_id="a/b", files=("config.json",)).is_loadable


def test_inspect_repo_accepts_a_pasted_url(monkeypatch):
    captured = {}

    def fake_fetch(url):
        captured["url"] = url
        return _payload("owner/name", CT2_FILES)

    monkeypatch.setattr(search, "fetch_json", fake_fetch)
    monkeypatch.setattr(search, "remote_size", lambda _url: 1234)

    result = search.inspect_repo("https://huggingface.co/owner/name/tree/main")

    assert result.repo_id == "owner/name"
    assert result.size == 1234
    assert captured["url"].endswith("/owner/name")


def test_inspect_repo_rejects_incomplete_input():
    assert search.inspect_repo("") is None
    assert search.inspect_repo("just-a-name") is None


def test_inspect_repo_returns_none_when_missing(monkeypatch):
    def boom(_url):
        raise RuntimeError("404")

    monkeypatch.setattr(search, "fetch_json", boom)

    assert search.inspect_repo("owner/missing") is None
