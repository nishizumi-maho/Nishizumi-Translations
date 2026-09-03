"""What ends up in the files the user actually opens."""
from __future__ import annotations

import json

from reuniao.model import Transcript, Utterance, assign_names
from reuniao.pipeline import unique_path
from reuniao.writers import write_json, write_srt, write_txt, write_vtt


def sample(diarized: bool = True) -> Transcript:
    return Transcript(
        source="/gravacoes/reuniao semanal.m4a",
        duration=3725.0,
        utterances=[
            Utterance(4.0, 12.5, "Bom dia a todos, vamos começar.", 0 if diarized else None),
            Utterance(13.0, 29.0, "O orçamento fecha na sexta.", 1 if diarized else None),
        ],
        speaker_names=assign_names(2, ["Ana"]) if diarized else [],
        model="large-v3-turbo",
        diarized=diarized,
        created_at="2026-09-02T14:33:00",
    )


def test_block_layout_carries_times_speakers_and_speech(tmp_path):
    path = write_txt(sample(), tmp_path / "reuniao.txt")
    text = path.read_text(encoding="utf-8-sig")

    assert "TRANSCRIÇÃO DA REUNIÃO" in text
    assert "Arquivo......: reuniao semanal.m4a" in text
    assert "Duração......: 1 h 2 min 5 s" in text
    assert "Modelo.......: large-v3-turbo (Whisper)" in text
    assert "Interlocutores: 2 (Ana, Interlocutor 2)" in text
    assert "[00:00:04 → 00:00:12]  Ana" in text
    assert "Bom dia a todos, vamos começar." in text
    assert "[00:00:13 → 00:00:29]  Interlocutor 2" in text


def test_line_layout_puts_one_turn_on_each_line(tmp_path):
    path = write_txt(sample(), tmp_path / "reuniao.txt", layout="linhas")
    body = [
        line
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.startswith("[")
    ]

    assert body == [
        "[00:00:04 → 00:00:12] Ana: Bom dia a todos, vamos começar.",
        "[00:00:13 → 00:00:29] Interlocutor 2: O orçamento fecha na sexta.",
    ]


def test_a_transcript_without_speakers_says_so(tmp_path):
    text = write_txt(sample(diarized=False), tmp_path / "r.txt").read_text(encoding="utf-8-sig")
    stamps = [line for line in text.splitlines() if line.startswith("[")]

    assert "Interlocutores: não identificados" in text
    # The timing stays; only the name is gone from each turn.
    assert stamps == ["[00:00:04 → 00:00:12]", "[00:00:13 → 00:00:29]"]


def test_text_is_written_with_a_bom_so_notepad_shows_the_accents(tmp_path):
    path = write_txt(sample(), tmp_path / "r.txt")

    assert path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_srt_and_vtt_timecodes(tmp_path):
    srt = write_srt(sample(), tmp_path / "r.srt").read_text(encoding="utf-8")
    vtt = write_vtt(sample(), tmp_path / "r.vtt").read_text(encoding="utf-8")

    assert srt.startswith("1\n00:00:04,000 --> 00:00:12,500\nAna: Bom dia")
    assert vtt.startswith("WEBVTT")
    assert "00:00:04.000 --> 00:00:12.500" in vtt


def test_json_names_its_fields_in_portuguese(tmp_path):
    data = json.loads(write_json(sample(), tmp_path / "r.json").read_text(encoding="utf-8"))

    assert data["interlocutores"] == ["Ana", "Interlocutor 2"]
    assert data["falas"][0] == {
        "inicio": 4.0,
        "fim": 12.5,
        "interlocutor": "Ana",
        "texto": "Bom dia a todos, vamos começar.",
        "confianca": 1.0,
        "duvidoso": False,
    }
    assert data["interlocutores_identificados"] is True
    # Talk time is there for whatever reads the file next.
    assert [row["interlocutor"] for row in data["tempo_de_fala"]] == ["Interlocutor 2", "Ana"]


def test_a_second_run_never_overwrites_the_first_transcript(tmp_path):
    first = tmp_path / "reuniao.txt"
    first.write_text("corrigido à mão", encoding="utf-8")

    assert unique_path(first).name == "reuniao (2).txt"

    (tmp_path / "reuniao (2).txt").touch()
    assert unique_path(first).name == "reuniao (3).txt"
