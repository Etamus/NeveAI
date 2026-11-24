import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from neveai.utils.studio_subtitles import compose_subtitles


def words(text, offset=0, step=.25, **attrs):
    return [dict(start=offset+i*step, end=offset+(i+1)*step, text=t, **attrs)
            for i, t in enumerate(text.split())]


def test_short_clause_and_final_word_stay_with_the_sentence():
    source = words("Hoje, finalmente, conseguimos terminar a primeira montagem.")
    cues = compose_subtitles(source, 6)
    assert [c["text"] for c in cues] == [" ".join(c["text"] for c in source)]
    assert cues[0]["start"] == 0 and cues[0]["end"] >= 1.15


def test_reading_time_respects_pauses_turns_and_selected_ranges():
    source = [*words("Oi!", speaker=1), *words("Sim.", .5, speaker=2),
              *words("Depois.", 4, speaker=2, _limit=4.6)]
    cues = compose_subtitles(source, 8)
    assert [(c["speaker"], c["text"]) for c in cues] == [(1,"Oi!"), (2,"Sim."), (2,"Depois.")]
    assert cues[0]["end"] == .5
    assert 1 <= cues[1]["end"] - .5 <= 1.15
    assert cues[2]["end"] == 4.6
    assert all("_limit" not in c for c in cues)


def test_filling_gaps_preserves_manual_cues_exactly():
    kept = dict(start=1, end=2, existingIndex=4, text="Edited!", speaker=2)
    result = compose_subtitles([*words("Before",_limit=.7), kept, *words("After",2.1)], 2.6)
    assert result[1] == kept
    assert result[0]["end"] == .7 and result[-1]["end"] == 2.6


def test_short_interjection_does_not_flash_between_words_from_the_same_speaker():
    source = words("Sim. Agora podemos continuar.",speaker=2)
    assert [c["text"] for c in compose_subtitles(source,2)] == ["Sim. Agora podemos continuar."]


def test_fast_continuous_speech_and_native_word_spacing():
    source = words(" ".join(["palavra"]*500), step=.09)
    cues = compose_subtitles(source, 45)
    assert " ".join(c["text"] for c in cues).split() == ["palavra"]*500
    assert all(len(c["text"]) <= 76 for c in cues)
    assert all(a["end"] <= b["start"] for a,b in zip(cues,cues[1:]))
    assert compose_subtitles(words("\u65e5 \u672c \u8a9e",_space=False),2)[0]["text"] == "\u65e5\u672c\u8a9e"
