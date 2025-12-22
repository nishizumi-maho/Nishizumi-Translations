from jp2subs.io import load_master
from jp2subs.models import MasterDocument


def test_master_schema_roundtrip(tmp_path):
    sample = tmp_path / "master.json"
    sample.write_text(
        """
{
  "meta": {"source": "sample.wav", "tool_versions": {}, "settings": {}},
  "segments": [
    {"id": 1, "start": 0.0, "end": 1.0, "ja_raw": "テスト", "translations": {"ja": "テスト"}}
  ]
}
        """.strip(),
        encoding="utf-8",
    )
    doc = load_master(sample)
    assert isinstance(doc, MasterDocument)
    assert doc.segments[0].ja_raw == "テスト"
