import asyncio
import json
import os
import subprocess
import sys
import time
import wave
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import av
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from neveai.routers import video_edit
from neveai.utils import video_edit_model
from neveai.utils import video_edit_director as director
from neveai.utils import video_edit_selection as selection
from neveai.utils.video_edit_selection import ripple, sound_attacks
from neveai.utils.video_edit import Caption, Clip, ffmpeg_binary, projected_captions


@pytest.mark.parametrize("glyph", ["W", "i", "e\u0301", "\U0001f469\u200d\U0001f4bb"])
def test_caption_limit_counts_visible_characters(glyph):
    from pydantic import ValidationError
    from neveai.utils.video_edit import _caption
    kwargs = dict(asset="video", start=0, end=1)
    assert Caption(**kwargs, text=glyph*180).text == glyph*180
    with pytest.raises(ValidationError):
        Caption(**kwargs, text=glyph*181)
    cues = []
    _caption(cues, [SimpleNamespace(word=glyph*181, start=0, end=1)], 1)
    assert cues[0]["text"] == glyph*180


@pytest.mark.parametrize("layered", [False, True])
def test_cue_appearance_survives_projection_and_uses_local_ass_style(tmp_path, layered):
    from neveai.utils.video_edit import Timeline
    from neveai.utils.video_edit_captions import write_animated
    timeline = Timeline(clips=[dict(asset="a", start=0, end=4, at=0 if layered else None)],
                        captionStyle=dict(font="Tahoma"), captions=[
                            dict(asset="a", start=0, end=1, text="Default"),
                            dict(asset="a", start=1, end=2, text="Individual", style=dict(font="Impact", size=32, theme="box")),
                            dict(asset="a", start=2, end=3, text="Partial", style=dict(theme="highlight"))])
    cues = list(projected_captions(timeline.clips, timeline.captions, styled=True))
    path = tmp_path / "captions.ass"
    write_animated(path, cues, timeline.captionStyle, 854, 480)
    lines = path.read_text(encoding="utf8").splitlines()
    styles = {line.split(",")[0][7:]:line.split(",") for line in lines if line.startswith("Style: ")}
    rows = [styles[line.split(",")[3]] for line in lines if line.startswith("Dialogue: ")]
    assert [row[1:3] for row in rows] == [["Tahoma","18"],["Impact","32"],["Tahoma","18"]]
    assert [row[15] for row in rows] == ["1","3","1"]
    assert rows[0][3] != rows[2][3]
    assert [len(c) for c in projected_captions(timeline.clips, timeline.captions)] == [3,3,3]


def test_event_removal_ripples_audio_and_respects_visible_tracks():
    timeline = video_edit.Timeline(title="Do not rename", clips=[
        Clip(asset="base",start=10,end=20,at=0,zoom=1.2,effect="mono"),
        Clip(asset="upper",start=0,end=2,at=3,lane=1),
        Clip(asset="sound",start=5,end=15,at=0,lane=2,audioOnly=True,gain=.3)
    ],captions=[Caption(asset="base",start=17,end=18,text="Still here")])
    result,hits = ripple(timeline, {"base":[(11,12),(13,15)], "upper":[(.5,1.5)]},False)
    assert hits == [(1,2),(3.5,4.5)]
    assert [(c.start,c.end,c.at) for c in result.clips if c.audioOnly] == [(5,6,0),(7,8.5,1),(9.5,15,2.5)]
    assert all(c.gain == .3 for c in result.clips if c.audioOnly)
    assert all(c.zoom == 1.2 and c.effect == "mono" for c in result.clips if c.asset=="base")
    assert list(projected_captions(result.clips,result.captions)) == [(5,6,"Still here")]
    assert result.title == timeline.title


def test_event_selection_keep_repeats_and_reject_unseen_or_empty_edits():
    clip = Clip(asset="source",start=10,end=15)
    timeline = video_edit.Timeline(clips=[clip,clip])
    result,hits = ripple(timeline, {"source":[(11,12)]},True)
    assert hits == [(1,2),(6,7)]
    assert [(c.start,c.end,c.at) for c in result.clips] == [(11,12,0),(11,12,1)]
    for absent in [{}, {"source":[(4,8)]},{"unseen":[(11,12)]}]:
        with pytest.raises(ValueError,match="No matching"):
            ripple(timeline,absent,False)
    with pytest.raises(ValueError,match="empty"):
        ripple(timeline,{"source":[(10,15)]},False)


def test_sound_landmarks_are_source_timed_across_decode_blocks(tmp_path):
    rate = 16000
    samples = np.zeros(rate * 7, dtype=np.float32)
    t = np.arange(2400)/rate
    impact = (.6*np.sin(2*np.pi*95*t) + .25*np.sin(2*np.pi*1700*t))*np.exp(-t*28)
    for at in [1.3,4.18,5.75]:
        i = round(at*rate)
        samples[i:i+len(t)] = impact
    wav = tmp_path/"audio.wav"
    with wave.open(str(wav),"wb") as out:
        out.setparams((1,2,rate,0,"NONE","not compressed"))
        out.writeframes((samples*32767).astype("<i2").tobytes())
    src = tmp_path/"test.mp4"
    subprocess.run([ffmpeg_binary(),"-v","error","-f","lavfi","-i","color=black:s=128x72:r=10",
                    "-i",str(wav),"-shortest","-c:v","libx264","-c:a","aac",str(src)],check=True)
    times = sound_attacks({"videoIndex":0,"audio":True,"path":src})
    assert len(times) == 3
    assert np.allclose(times,[1.3,4.18,5.75],atol=.08)
    assert sound_attacks({"audio":False}) == []


def test_event_search_requires_visual_evidence_even_with_synchronous_transients(monkeypatch):
    timeline = video_edit.Timeline(clips=[Clip(asset="a",start=0,end=5)])
    monkeypatch.setattr(selection,"sheets",lambda *_: ((str(i),(i,i+1)) for i in range(5)))
    # Three transients but the middle window shows an unrelated scene.
    monkeypatch.setattr(selection,"sound_attacks",lambda _: [.8,1.6,2.2])
    async def ask(complete,schema,messages,tokens):
        if schema is selection.Predicate:
            return schema(question_about_visual_content_in_english="Does the door slam?")
        if schema is selection.Signal:
            return schema(characteristic_sound_if_any="slam",evidence="impact")
        if schema is selection.EventWindow:
            image = messages[-1]["content"][0]["image_url"]["url"]
            return schema(visual_evidence="fixture",answer_to_question="yes" if image in ["0","2"] else "no")
        raise AssertionError(schema)
    edit,_,_ = asyncio.run(selection.select_events(timeline,{"a":{}},"remove door slams",False,ask,None,lambda *_:None))
    assert any(c.start <= 1.6 < c.end for c in edit.clips)
    assert not any(c.start <= t < c.end for t in [.8,2.2] for c in edit.clips)


def test_maker_worker_arguments_isolate_local_service(tmp_path):
    cmd = video_edit_model._command(tmp_path / "llama-server", tmp_path / "maker.gguf",
                                    tmp_path / "encoder.gguf", 5555, "per-run-key", False)
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1"
    assert cmd[cmd.index("--api-key") + 1] == "per-run-key"
    assert cmd[cmd.index("--device") + 1] == "none"
    assert "--no-mmproj-offload" in cmd and "--no-webui" in cmd
    assert not any("http" in arg or "-hf" == arg for arg in cmd)


def test_cuts_keep_padding_and_retime_caption():
    same_source = [Clip(asset="a", start=0, end=1), Clip(asset="a", start=1, end=2, motion="flash")]
    assert list(projected_captions(same_source, [Caption(asset="a", start=.5, end=1.5, text="Continuous")])) == [
        (.5, 1.5, "Continuous")
    ]
    repeated = [Clip(asset="a", start=0, end=2, at=0), Clip(asset="a", start=0, end=2, at=2, gain=0)]
    line = Caption(asset="a", start=.5, end=1.5, text="Speech", speechOnly=True)
    assert list(projected_captions(repeated, [line])) == [(.5, 1.5, "Speech"), (2.5, 3.5, "Speech")]
    assert len(list(projected_captions(repeated, [line.model_copy(update={"speechOnly": False})]))) == 2


def test_story_uses_whole_lines_and_keeps_sound_across_a_picture_cut():
    sources = [("asset", {"duration": 30, "audio": True})]
    audio = {"asset": {"cues": [
        {"start": 2, "end": 3.5, "text": "This line must"},
        {"start": 3.5, "end": 5, "text": "not get cut."},
    ], "wave": [.3] * 240, "speech_windows": [(2, 5)]}}
    lines = director.dialogue_lines(sources, audio)
    assert lines == [[0, 2, 5, "This line must not get cut."]]
    brief = director.Brief(reorder=False, overlay=False, layout="any", effects=[],
                           captions="optional", minSeconds=0, maxSeconds=0)
    beds = director.available_beds(sources, audio)
    assert beds and all(end <= 2 or start >= 5 for _, start, end, _ in beds.values())
    quote = director.Beat(purpose="An answer over a reaction", picture=1, sound="Q0: This line must not get cut.",
                          seconds=2, transition="none", look="cinema", framing=1)
    board = director.Storyboard(premise="A question and its consequence", title="Not requested",
        aspect="source", ambience=next(iter(beds)), beats=[quote, quote.model_copy(update={"sound": "Location sound", "seconds": 1})])
    catalog = [[0, 1, 5, "speaking"], [0, 11, 14, "reaction"]]
    decision = director.story_decision(board, catalog, lines, sources, brief, 12, beds)
    assert not decision.title and decision.captions == "keep"
    edit = director.compile_edit(decision, video_edit.Timeline(clips=[Clip(asset="asset", start=0, end=30)]), sources, audio)
    pictures = [c for c in edit.clips if not c.audioOnly]
    speech, *beds_on_track = [c for c in edit.clips if c.audioOnly]
    ambience = beds_on_track[0]
    assert pictures[0].gain == pictures[1].gain == 0
    assert speech.at == 0 and speech.start < 2 and speech.end > 5
    assert pictures[1].start >= 11 and pictures[1].at < speech.end - speech.start
    assert ambience.lane != speech.lane and 0 < ambience.gain < speech.gain
    decision.captions = "generate"
    audio["asset"]["cues"].append({"start": 20, "end": 21, "text": "Not in the edit"})
    spoken_only = director.compile_edit(decision, video_edit.Timeline(clips=[Clip(asset="asset", start=0, end=30)]), sources, audio)
    assert [c.text for c in spoken_only.captions] == ["This line must", "not get cut."]
    with pytest.raises(ValueError, match="limit"):
        director.story_decision(board, catalog, lines, sources, brief, 2, beds)
    with pytest.raises(ValueError, match="distinct beats"):
        director.story_decision(board.model_copy(update={"beats": [quote, quote]}), catalog, lines, sources, brief, 12, beds)


def test_picture_handles_fit_duration_without_trimming_dialogue():
    sources = [("a", {"duration": 60, "audio": True})]
    catalog = [[0, 0, 10, "question"], [0, 11, 23, "reaction"], [0, 30, 45, "answer"]]
    lines = [[0, 1, 4, "A question?"], [0, 30, 33, "An answer."]]
    refs = {"Q0": 0, "Q1": 1}
    beat = director.Beat(purpose="Question", picture=0, sound="Q0", seconds=2, transition="none", look="none", framing=1)
    beats = [beat, beat.model_copy(update={"picture": 1, "sound": "Location sound", "seconds": 8}),
             beat.model_copy(update={"picture": 2, "sound": "Q1"})]
    for minimum, maximum, expected in [(0, 10, 3.58), (16, 20, 9.58)]:
        fitted = director.fit_beats(beats, catalog, lines, refs, sources, minimum, maximum)
        assert [b.sound for b in fitted] == ["Q0", "Location sound", "Q1"]
        assert fitted[1].seconds == pytest.approx(expected)


def test_credit_filter_matches_the_image_not_a_fixed_tail_duration(monkeypatch):
    from PIL import Image
    scenes = []
    for i, color in enumerate(["red", "green", "blue", "green"]):
        img = Image.new("RGB", (60, 40), color)
        scenes.append(director.Scene(i, 0, i*5, (i+1)*5, [img, img]))
    catalog = [[0, s.start, s.end, "footage"] for s in scenes]
    monkeypatch.setattr(director, "read_end_screen", lambda *_: "THANKS FOR WATCHING")
    result = asyncio.run(director.end_cards(None, scenes, catalog, [("a", {"duration": 20})]))
    assert result == {1, 3}


@pytest.fixture
def app(tmp_path, monkeypatch):
    from neveai import config
    from neveai.storage import provider
    from neveai.models.files import Files, File
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    archive = tmp_path / "uploads"
    archive.mkdir()
    monkeypatch.setattr(config,"UPLOAD_DIR",archive)
    monkeypatch.setattr(provider,"UPLOAD_DIR",archive)
    engine=create_engine(f"sqlite:///{tmp_path/'files.db'}")
    File.__table__.create(engine)
    insert=Files.insert_new_file
    def store(user_id,form):
        with Session(engine) as db:
            return insert(user_id,form,db=db)
    monkeypatch.setattr(Files,"insert_new_file",store)
    monkeypatch.setattr(video_edit, "ROOT", tmp_path / "projects")
    video_edit.jobs.clear()
    monkeypatch.setattr(video_edit, "workers", asyncio.Semaphore(1))
    monkeypatch.setattr(video_edit, "uploads", asyncio.Semaphore(2))
    monkeypatch.setattr(video_edit, "analysis_slots", asyncio.Semaphore(1))
    backend = FastAPI()
    backend.include_router(video_edit.router)
    actor = SimpleNamespace(id="alice")
    backend.dependency_overrides[video_edit.get_verified_user] = lambda: actor
    with TestClient(backend) as client:
        yield client, actor


def wait_export(client, job):
    for _ in range(200):
        status = client.get("/exports/" + job).json()
        if status["status"] not in ("queued", "exporting"):
            return status
        time.sleep(.15)
    pytest.fail("Video export timed out")


def import_media(client, path):
    with path.open("rb") as input:
        response = client.post("/media", files={"file": (path.name, input, "video/mp4")})
    assert response.status_code == 200, response.text
    return response.json()


def test_assist_local_speech_trim_color_and_discard(app, tmp_path, monkeypatch):
    """Optional reference speech: Windows pt-BR 'Hoje vamos testar a edição de vídeo...'."""
    client, actor = app
    speech = ROOT / "logs/studio-assist-pt.wav"
    if not speech.is_file():
        pytest.skip("Local Portuguese speech fixture not available")
    monkeypatch.setattr(video_edit, "WHISPER_MODEL_DIR", ROOT / "backend/data/cache/whisper/models")
    src = tmp_path / "pt.mp4"
    subprocess.run([ffmpeg_binary(), "-v","error","-f","lavfi","-i","testsrc2=s=160x90:r=16",
                    "-i", str(speech), "-af","adelay=1600:all=1,apad","-vf","eq=brightness=-0.15",
                    "-t","10","-c:v","libx264","-c:a","aac",str(src)],check=True)
    asset = import_media(client, src)["id"]
    params = dict(clips=[dict(asset=asset,start=.2,end=9.8)],index=0)
    for op in ["color","speech","captions","words"]:
        r = client.post("/assist",json=dict(**params,operation=op))
        assert r.status_code == 200,r.text
        data = r.json()
        if op == "color":
            assert data["grade"]["brightness"] > 0
        elif op == "speech":
            assert 1 < data["clips"][0]["start"] < 2 and data["clips"][-1]["end"] < 9.6
        else:
            result = " ".join(c["text"] for c in data["cues"]).lower()
            print(op, result)
            assert all(word in result for word in ("hoje","testar","legenda","voz"))
            assert all(.2 <= c["start"] < c["end"] <= 9.8 for c in data["cues"])
            if op == "words":
                assert len(data["cues"]) >= 10
    quiet = client.post("/assist",json=dict(clips=[dict(asset=asset,start=0,end=1)],index=0,operation="speech"))
    assert quiet.status_code == 422 and "No speech" in quiet.text
    actor.id = "other"
    assert client.post("/discard",json=dict(media=[asset],exports=[])).status_code == 200
    actor.id = "alice"
    assert client.get("/media/"+asset).status_code == 200
    client.post("/discard",json=dict(media=[asset],exports=[])).raise_for_status()
    assert client.get("/media/"+asset).status_code == 404 and src.is_file()


@pytest.mark.parametrize("animation", ["rise","drop","type","pulse","wave","fade","slide","zoom","blur","spin"])
def test_animated_caption_changes_pixels_in_mp4_only(app,tmp_path,animation):
    client,_ = app
    src = tmp_path / "black.mp4"
    subprocess.run([ffmpeg_binary(),"-v","error","-f","lavfi","-i","color=black:s=160x90:r=30","-t","1",
                    "-c:v","libx264",str(src)],check=True)
    id = import_media(client,src)["id"]
    timeline = dict(height=480,clips=[dict(asset=id,start=0,end=1)],
                    captions=[dict(asset=id,start=0,end=1,text="Neve Studio")],
                    captionStyle=dict(position="top",animation=animation,font="Verdana"))
    job = client.post("/exports",json=timeline).json()["id"]
    assert wait_export(client,job)["status"]=="done"
    assert client.get(f"/exports/{job}/srt").status_code == 404
    with av.open(BytesIO(client.get(f"/exports/{job}/mp4").content)) as stream:
        frames=[f.to_ndarray(format="gray") for f in stream.decode(video=0)]
    assert np.abs(frames[0].astype(float)-frames[10]).sum()>1000 and frames[10][:200].max()>150


@pytest.mark.parametrize("rate", [128,192,256,320])
def test_audio_export_rate_content_and_timeline_gap(app,tmp_path,rate):
    client,_ = app
    src = tmp_path / "tone.mp4"
    subprocess.run([ffmpeg_binary(),"-v","error","-f","lavfi","-i","color=s=128x72:r=10",
                    "-f","lavfi","-i","sine=frequency=440","-t","1","-c:v","libx264","-c:a","aac",str(src)],check=True)
    asset=import_media(client,src)["id"]
    req=dict(format="mp3",bitrate=rate,clips=[dict(asset=asset,start=.2,end=.8,at=.4,audioOnly=True)])
    job=client.post("/exports",json=req).json()["id"]
    assert wait_export(client,job)["status"]=="done"
    assert client.get(f"/exports/{job}/mp4").status_code==404
    res=client.get(f"/exports/{job}/mp3")
    assert res.headers["content-type"]=="audio/mpeg"
    with av.open(BytesIO(res.content)) as stream:
        assert not stream.streams.video and stream.streams.audio[0].bit_rate==rate*1000
        wave=np.concatenate([f.to_ndarray()[0] for f in stream.decode(audio=0)])
        assert abs(len(wave)-48000)<100
        assert np.max(np.abs(wave[:16000]))<.001 and np.max(np.abs(wave[24000:]))>.01


def test_speaker_words_follow_turns_not_sentence_boundaries():
    from neveai.utils.video_edit_speakers import label_words
    words = [dict(start=a, end=a+.3, text=t) for a,t in [(0,"Olá"),(.4,"pessoal."),(.8,"Bom"),(1.2,"dia!"),(2,"Obrigado."),(5,"Fim.")]]
    cues = label_words(words,[(0,.74,8),(.75,1.75,3),(1.99,2.6,8)])
    assert [(c.get("speaker"),c["text"]) for c in cues] == [(1,"Olá pessoal."),(2,"Bom dia!"),(1,"Obrigado."),(None,"Fim.")]


def test_incremental_transcription_preserves_existing_text(app,tmp_path,monkeypatch):
    client,_=app
    fixture=ROOT/"logs/studio-speakers-fixture.mp4"
    if not fixture.exists():
        pytest.skip("requires local speaker voices fixture")
    monkeypatch.setattr(video_edit,"WHISPER_MODEL_DIR",ROOT/"backend/data/cache/whisper/models")
    real=video_edit.run_process
    plans=[]
    async def inspect(cmd,*args,**kwargs):
        if "neveai.utils.video_edit_assist" in cmd:
            plans.append(json.loads(Path(cmd[-1]).read_text()))
        return await real(cmd,*args,**kwargs)
    monkeypatch.setattr(video_edit,"run_process",inspect)
    asset=import_media(client,fixture)["id"]
    def call(op,end,captions,covered):
        payload=dict(clips=[dict(asset=asset,start=0,end=end)],operation=op,index=0,captions=captions,transcriptCoverage=covered)
        return client.post("/assist",json=payload).raise_for_status().json()["cues"]
    first=call("captions",12,[],[])
    assert first and plans[-1]["gaps"]==[[0,12]]
    first[0]["text"]="Manually edited"
    old=[dict(c,asset=asset) for c in first]
    coverage=[dict(asset=asset,start=0,end=12)]
    assert call("captions",12,old,coverage)==[] and len(plans)==1
    speakers=call("speakers",12,old,coverage)
    assert plans[-1]["gaps"]==[]
    assert [c["text"] for c in speakers]==[c["text"] for c in old]
    assert all(c["existingIndex"]==i for i,c in enumerate(speakers))
    assert any(c.get("speaker") for c in speakers)
    extra=call("speakers",23,old,coverage)
    assert plans[-1]["gaps"]==[[12,23]]
    assert all(c["start"]>=12 for c in extra if "existingIndex" not in c)
    assert any("existingIndex" not in c and c.get("speaker") for c in extra)


def test_global_speakers_recurrent_real_three_voices(tmp_path):
    from neveai.utils.video_edit_speakers import SessionSpeakers,label_words
    from faster_whisper.audio import decode_audio
    fixture=ROOT/"logs/studio-speakers-fixture.wav"
    third=ROOT/"logs/haru-quality-4.wav"
    if not fixture.exists() or not third.exists(): pytest.skip("requires three local test voices")
    pair=decode_audio(str(fixture))
    sources=[pair[:64000],pair[96000:146000],decode_audio(str(third))]
    session=SessionSpeakers(ROOT/"backend/data/cache/video_edit_speakers")
    turns=[];words=[];truth=[];offset=0
    rng=np.random.default_rng(173)
    for i in range(8):
        parts=[]
        for speaker in rng.permutation(3):
            start=offset+sum(map(len,parts))/16000
            utterance=sources[speaker]*rng.uniform(.55,1)
            parts.extend([utterance,np.zeros(16000)])
            words.append(dict(text="Test.",start=start+.5,end=start+1.8))
            truth.append(speaker)
        pcm=np.concatenate(parts)
        wav=tmp_path/"block.wav"
        with wave.open(str(wav),"wb") as f:
            f.setparams((1,2,16000,0,"NONE","not compressed"))
            f.writeframes((pcm*32767).clip(-32768,32767).astype("<i2").tobytes())
        turns.extend(session.turns(wav,offset,offset,offset+len(pcm)/16000))
        offset+=1800
    for count in (None,3):
        previews={}
        cues=label_words(words,session.resolve(turns,count),previews)
        labels={}
        pairs=[(int(speaker),cue.get("speaker")) for cue,speaker in zip(cues,truth)]
        for speaker,predicted in pairs:
            assert labels.setdefault(speaker,predicted)==predicted,(count,pairs)
        assert len(set(labels.values()))==3
        assert len(previews)==3 and all(.5<=b-a<=3.001 for a,b in previews.values())


@pytest.mark.skipif(os.name!="nt",reason="requires offline Windows test voices")
def test_three_named_test_voices_vary_utterances(tmp_path):
    from faster_whisper.audio import decode_audio
    from neveai.utils.video_edit_speakers import SessionSpeakers,label_words
    command=r"""
    $ErrorActionPreference='Stop'
    $v=New-Object -ComObject SAPI.SpVoice
    $c=New-Object -ComObject SAPI.SpObjectTokenCategory
    $c.SetId('HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices',$false)
    $voices=@(@($c.EnumerateTokens())+@($v.GetVoices()) | Where-Object { $_.GetDescription() -match 'Daniel -|Maria -|Zira Desktop' })
    if ($voices.Count -ne 3){exit 77}
    $sentences=@('Hoje vamos conversar sobre as primeiras imagens da cidade.','Depois da chuva apareceu um arco colorido no horizonte.','Eles trabalharam com cuidado para terminar o projeto.','Quanto tempo demora para chegar ao outro lado da ponte?')
    foreach ($i in 0..2){
        $v.Voice=$voices[$i]
        foreach($j in 0..3){
            $file=New-Object -ComObject SAPI.SpFileStream
            $file.Open((Join-Path $pwd "$i-$j.wav"),3)
            $v.AudioOutputStream=$file
            [void]$v.Speak($sentences[($i+$j)%4])
            $file.Close()
        }
    }
    """
    proc=subprocess.run(["powershell","-NoProfile","-NonInteractive","-Command",command],cwd=tmp_path,capture_output=True)
    if proc.returncode==77:pytest.skip("requires three distinct installed SAPI voices")
    assert proc.returncode==0,proc.stderr
    session=SessionSpeakers(ROOT/"backend/data/cache/video_edit_speakers")
    rng=np.random.default_rng(42)
    turns=[];words=[];truth=[]
    for k in range(8):
        parts=[];offset=k*1800
        for who in rng.permutation(3):
            sample=decode_audio(str(tmp_path/f"{who}-{k%4}.wav"))
            t=offset+sum(map(len,parts))/16000
            parts.extend([sample*rng.uniform(.5,1),np.zeros(12000)])
            words.append(dict(start=t+.45,end=t+1.35,text="Test."))
            truth.append(int(who))
        pcm=np.concatenate(parts)
        wav=tmp_path/"mixed.wav"
        with wave.open(str(wav),"wb") as f:
            f.setparams((1,2,16000,0,"NONE","not compressed"))
            f.writeframes((pcm*32767).astype("<i2").tobytes())
        turns.extend(session.turns(wav,offset,offset,offset+len(pcm)/16000))
    for count in (None,3):
        predicted=[cue.get("speaker") for cue in label_words(words,session.resolve(turns,count))]
        assert len(set(predicted))==3 and None not in predicted,(count,predicted)
        assert all(len({p for p,a in zip(predicted,truth) if a==who})==1 for who in set(truth)),(count,predicted)


@pytest.mark.parametrize("count",[1,2,3,7,12])
def test_recording_wide_groups_are_not_a_three_person_cap(count):
    from neveai.utils.video_edit_speakers import recording_speakers
    rng=np.random.default_rng(244)
    vectors=np.eye(24)[:count].repeat(60,axis=0)+rng.normal(0,.13,(60*count,24))
    vectors/=np.linalg.norm(vectors,axis=1)[:,None]
    labels=recording_speakers(vectors,np.ones(len(vectors))).reshape(count,-1)
    assert len(np.unique(labels))==count
    assert all(len(set(turns))==1 for turns in labels)


def test_speaker_sample_is_bounded_audio_only(app,tmp_path):
    client,_=app
    src=ROOT/"logs/studio-speakers-fixture.mp4"
    if not src.exists(): pytest.skip("requires local audio fixture")
    asset=import_media(client,src)["id"]
    route=f"/media/{asset}/speaker-sample"
    output=client.get(route,params=dict(start=6,end=9)).raise_for_status()
    with wave.open(BytesIO(output.content),"rb") as f:
        assert f.getnframes()/f.getframerate()==3 and f.getnchannels()==1
        assert np.max(np.abs(np.frombuffer(f.readframes(f.getnframes()),dtype="<i2")))>100
    assert client.get(route,params=dict(start=0,end=15)).status_code==422


def test_real_five_hour_grade(app,tmp_path):
    from neveai.utils.video_edit import Grade
    client,_=app
    src=tmp_path/"five-hours.mp4"
    subprocess.run([ffmpeg_binary(),"-v","error","-f","lavfi","-i","testsrc2=s=80x48:r=1/10",
                    "-frames:v","1800","-c:v","libx264","-g","5",str(src)],check=True)
    asset=import_media(client,src)
    assert asset["duration"]==18000
    r=client.post("/assist",json=dict(clips=[dict(asset=asset["id"],start=0,end=18000)],operation="color",index=0))
    grade=Grade(**r.raise_for_status().json()["grade"])
    assert len(grade.samples)==16 and grade.samples[0].time<900 and grade.samples[-1].time>17000


def test_five_hours_of_audio_keep_voices_and_absolute_times(tmp_path):
    from neveai.utils.video_edit_assist import assist
    fixture=ROOT/"logs/studio-speakers-fixture.wav"
    if not fixture.exists(): pytest.skip("local reference voices required")
    source=tmp_path/"five-hour-audio.mkv"
    subprocess.run([ffmpeg_binary(),"-v","error","-i",str(fixture),"-i",str(fixture),
                    "-filter_complex","[0:a]atrim=duration=23,apad=whole_dur=17977[a];[1:a]atrim=duration=23[b];[a][b]concat=n=2:v=0:a=1",
                    "-ar","16000","-ac","1","-c:a","flac",str(source)],check=True)
    cache=ROOT/"backend/data/cache"
    def run(op,plan=None):
        return assist(source,0,18000,op,cache/"whisper/models",tmp_path,cache/"video_edit_speakers",plan)
    windows=run("speech")["speech"]
    assert windows[0][0]<10 and windows[-1][1]>17990
    cues=run("captions")["cues"]
    assert cues[0]["start"]<10 and cues[-1]["end"]>17990
    labeled=run("speakers",{"gaps":[],"existing":[dict(c,existingIndex=i) for i,c in enumerate(cues)]})["cues"]
    assert [c["text"] for c in labeled]==[c["text"] for c in cues]
    early=[c["speaker"] for c in labeled if c["end"]<24]
    late=[c["speaker"] for c in labeled if c["start"]>17976]
    from itertools import groupby
    assert [s for s,_ in groupby(early)]==[s for s,_ in groupby(late)]==[1,2,1,2]


def test_speaker_parallel_fallback_preserves_window_offsets(tmp_path,monkeypatch):
    import concurrent.futures as futures
    from concurrent.futures.process import BrokenProcessPool
    from neveai.utils import video_edit_assist as worker, video_edit_speakers as models
    blocks=list(worker.audio_blocks(0,1200))
    retried=[]
    def sample(block):
        a,b,*_=block
        return [a],[(a,b,0)]
    class Pool:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def map(self,fn,jobs):
            yield sample(next(iter(jobs))[1])
            raise BrokenProcessPool("worker unavailable")
    def serial(session,path,block,wav):
        retried.append(block)
        return sample(block)
    monkeypatch.setattr(futures,"ProcessPoolExecutor",Pool)
    monkeypatch.setattr(models,"SessionSpeakers",lambda cache:object())
    monkeypatch.setattr(worker,"extract_speaker_window",serial)
    obs,turns=worker.speaker_evidence(None,blocks,None,tmp_path,2)
    assert retried==blocks[1:]
    assert obs==[b[0] for b in blocks]
    assert turns==[(a,b,i) for i,(a,b,*_) in enumerate(blocks)]


def test_speaker_worker_module_on_four_windows(tmp_path):
    fixture=ROOT/"logs/studio-speakers-fixture.mp4"
    if not fixture.exists(): pytest.skip("requires local speaker voices fixture")
    source=tmp_path/"repeat.mkv"
    # Repeat the same real two-voice signal after a long quiet interval in each window.
    subprocess.run([ffmpeg_binary(),"-v","error","-i",str(fixture),"-vn","-af",
                    "aresample=16000,apad=whole_dur=300,aloop=loop=3:size=4800000","-ac","1",
                    "-t","1200","-c:a","flac",str(source)],check=True)
    words=[dict(start=t+1,end=t+2,text="Example",existingIndex=i) for i,t in enumerate(range(0,1200,300))]
    plan=tmp_path/"plan.json"
    plan.write_text(json.dumps(dict(gaps=[],existing=words)))
    cache=ROOT/"backend/data/cache"
    output=tmp_path/"out.json"
    subprocess.run([sys.executable,"-m","neveai.utils.video_edit_assist",str(source),"0","1200","speakers",
                    str(cache/"whisper/models"),str(output),str(cache/"video_edit_speakers"),str(plan)],
                   cwd=ROOT/"backend",check=True,timeout=180)
    cues=json.loads(output.read_text())["cues"]
    assert [c["existingIndex"] for c in cues]==list(range(4))
    from tempfile import TemporaryDirectory
    from neveai.utils.video_edit_assist import audio_blocks, speaker_evidence
    from neveai.utils.video_edit_speakers import label_words, resolve_turns
    with TemporaryDirectory(dir=tmp_path) as work:
        obs,turns=speaker_evidence(source,list(audio_blocks(0,1200)),cache/"video_edit_speakers",Path(work),1)
    baseline=label_words(words,resolve_turns(obs,turns))
    assert all(c.get("speaker") for c in baseline)
    assert cues==baseline


def test_speaker_workers_reserve_memory(monkeypatch):
    import psutil
    from neveai.utils.video_edit_assist import speaker_workers
    monkeypatch.setattr(psutil,"cpu_count",lambda logical=False:12)
    for available,expected in [(1,1),(6,2),(12,3)]:
        monkeypatch.setattr(psutil,"virtual_memory",lambda:SimpleNamespace(available=available*1024**3))
        assert speaker_workers(48)==expected
        assert speaker_workers(2)==1
    monkeypatch.setattr(psutil,"cpu_count",lambda logical=False:2)
    assert speaker_workers(48)==1


def test_real_block_speakers_and_speech(tmp_path,monkeypatch):
    from neveai.utils import video_edit_assist as worker
    fixture=ROOT/"logs/studio-speakers-fixture.mp4"
    if not fixture.is_file(): pytest.skip("local reference voices required")
    monkeypatch.setattr(worker,"BLOCK_SECONDS",11.5)
    cache=ROOT/"backend/data/cache"
    for op in ("speech","speakers"):
        result=worker.assist(fixture,0,23,op,cache/"whisper/models",tmp_path,cache/"video_edit_speakers")
        if op=="speech":
            spans=result["speech"]
            assert spans and all(0<=x<y<=23 for x,y in spans) and all(b<c for (_,b),(c,_) in zip(spans,spans[1:]))
        else:
            from itertools import groupby
            cues=result["cues"]
            assert [k for k,_ in groupby(c["speaker"] for c in cues)]==[1,2,1,2]
            assert all(0<=c["start"]<c["end"]<=23 for c in cues)
    blocks=list(worker.audio_blocks(0,18000))
    assert blocks[0][0]==0 and blocks[-1][1]==18000 and all(x[1]==y[0] for x,y in zip(blocks,blocks[1:]))
    assert max(b-a for _,_,a,b in blocks)<=worker.BLOCK_SECONDS+2*worker.CONTEXT_SECONDS


@pytest.mark.parametrize(("op","limit"),[("vocals",3600),("instrumental",3600),("erase",1800),("fps60",300)])
def test_processor_duration_boundaries(op,limit,tmp_path,monkeypatch):
    from neveai.utils import video_edit_media_tools as m
    monkeypatch.setattr(m,"available",lambda root:[op])
    monkeypatch.setattr(m.shutil,"disk_usage",lambda _:SimpleNamespace(free=0))
    async def run(seconds):
        await m.process_tool(op,dict(duration=18000),0,seconds,tmp_path,tmp_path,tmp_path/"out",None)
    with pytest.raises(ValueError,match="disk space"):
        asyncio.run(run(limit))
    with pytest.raises(ValueError,match="Select a clip of up to"):
        asyncio.run(run(limit+.01))


@pytest.mark.parametrize("operation",["vocals","instrumental"])
def test_hour_stem_including_long_silence(app,tmp_path,monkeypatch,operation):
    client,user=app
    root=ROOT/"backend/data/cache/video_edit_tools"
    monkeypatch.setattr(video_edit,"TOOL_ROOT",root)
    src=ROOT/"logs/studio-speakers-fixture.mp4"
    if not src.exists() or operation not in client.get("/clip-tools").json():
        pytest.skip("requires installed local separator and fixture")
    sample=tmp_path/"hour.mp4"
    subprocess.run([ffmpeg_binary(),"-v","error","-f","lavfi","-i","color=s=32x32:r=1",
                    "-i",str(src),"-map","0:v","-map","1:a","-af","apad","-t","3600",
                    "-c:v","libx264","-c:a","aac",str(sample)],check=True)
    item=import_media(client,sample)
    res=client.post("/media/"+item["id"]+"/process",json=dict(start=0,end=3600,operation=operation)).raise_for_status().json()
    assert abs(res["duration"]-3600)<.08 and res["audio"]
    out=video_edit.workspace(user)/(res["id"]+".source")
    with av.open(str(out)) as c:
        stream=c.streams.audio[0]
        assert any(np.abs(frame.to_ndarray()).max()>1e-6 for frame in c.decode(stream))
        c.seek(int(3590/stream.time_base),stream=stream)
        frames=list(c.decode(stream))
        assert frames and frames[-1].time>3599 and np.abs(frames[-1].to_ndarray()).max()<1e-6


def test_cancel_owned_clip_cleans_worker_and_temps(app,tmp_path,monkeypatch):
    import psutil
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4
    client,user=app
    fixture=ROOT/"logs/studio-speakers-fixture.mp4"
    if not fixture.exists(): pytest.skip("requires a local clip")
    asset=import_media(client,fixture)
    async def fake(op,info,start,end,root,work,dest,run,**kwargs):
        program="import subprocess,time,pathlib,sys;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);pathlib.Path('pid').write_text(str(p.pid));time.sleep(60)"
        await run([sys.executable,"-c",program],work)
    monkeypatch.setattr(video_edit,"process_tool",fake)
    directory=video_edit.workspace(user)
    op=str(uuid4())
    with ThreadPoolExecutor(1) as pool:
        resp=pool.submit(client.post,"/media/"+asset["id"]+"/process",json=dict(requestId=op,operation="vocals",start=0,end=1))
        for _ in range(100):
            f=next(directory.glob("clip-*/pid"),None)
            if f and f.stat().st_size: break
            time.sleep(.05)
        child=psutil.Process(int(f.read_text()))
        assert client.delete("/operations/"+op).raise_for_status().json()["cancelled"]
        assert resp.result(timeout=10).status_code==499
        assert not child.is_running() or child.status()==psutil.STATUS_ZOMBIE
        assert not list(directory.glob("clip-*"))
        assert [p.stem for p in directory.glob("*.source")]==[asset["id"]]


def test_speaker_names_survive_projection():
    from neveai.utils.video_edit import Timeline, projected_captions
    data = Timeline(clips=[dict(asset="clip",start=0,end=4)],captions=[
        dict(asset="clip",start=i,end=i+.8,text="Bom dia",speakerName=name)
        for i,name in enumerate(["Ana","Pessoa 2","Ana"])])
    assert [cue[2] for cue in projected_captions(data.clips,data.captions,styled=True)] == ["Ana: Bom dia","Pessoa 2: Bom dia","Ana: Bom dia"]


def test_opacity_blends_tracks_and_captions_keep_separate_positions(app,tmp_path):
    client,_=app
    clips=[]
    for lane,color in enumerate(["red","blue"]):
        path=tmp_path/f"{color}.mp4"
        subprocess.run([ffmpeg_binary(),"-v","error","-f","lavfi","-i",f"color={color}:s=160x90:r=30","-t","1",str(path)],check=True)
        id=import_media(client,path)["id"]
        clips.append(dict(asset=id,at=0,lane=lane,start=0,end=1,opacity=.5 if lane else 1))
    timeline=dict(height=480,clips=clips,captions=[
        dict(asset=id,start=0,end=.5,text="Same text",horizontal="left",position="top"),
        dict(asset=id,start=.5,end=1,text="Same text",horizontal="right",position="bottom")])
    job=client.post("/exports",json=timeline).json()["id"]
    assert wait_export(client,job)["status"]=="done"
    with av.open(BytesIO(client.get(f"/exports/{job}/mp4").content)) as stream:
        frames=[f.to_ndarray(format="rgb24") for f in stream.decode(video=0)]
    a,b=frames[5],frames[23]
    r,g,blue=a[240,400]
    assert 95<r<160 and g<15 and 95<blue<160
    assert a[:220,:400,1].max()>180 and a[240:,430:,1].max()<30
    assert b[:220,:400,1].max()<30 and b[240:,430:,1].max()>180


def test_assist_matches_exposure_over_time_in_export(app,tmp_path):
    client,_ = app
    src = tmp_path / "exposure.mp4"
    subprocess.run([ffmpeg_binary(),"-v","error","-f","lavfi","-i","testsrc2=size=160x90:rate=12",
                    "-vf","eq=brightness='if(lt(t,2),-0.22,0.2)':eval=frame","-t","4","-c:v","libx264",str(src)],check=True)
    id = import_media(client,src)["id"]
    clip=dict(asset=id,start=.2,end=3.9)
    response = client.post("/assist",json=dict(clips=[clip],index=0,operation="color"))
    response.raise_for_status()
    grade = response.json()["grade"]
    assert grade["samples"][0]["brightness"] > grade["samples"][-1]["brightness"]
    results = []
    for params in (clip, {**clip,"grade":grade}):
        job=client.post("/exports",json=dict(height=480,clips=[params])).json()["id"]
        assert wait_export(client,job)["status"] == "done"
        with av.open(BytesIO(client.get(f"/exports/{job}/mp4").content)) as stream:
            levels=[f.to_ndarray(format="gray").mean() for f in stream.decode(video=0)]
        results.append(abs(np.mean(levels[-8:])-np.mean(levels[:8])))
    print("Exposure gap:",results)
    assert results[1] < results[0] - 4


def test_archive_survives_discard_and_can_be_cleared(app,tmp_path):
    from neveai.storage.provider import Storage
    from neveai.models.files import Files
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    client,_=app
    src=tmp_path/"original.mp4"
    subprocess.run([ffmpeg_binary(),"-v","error","-f","lavfi","-i","color=red:s=160x90","-t","1",str(src)],check=True)
    asset=import_media(client,src)
    client.post("/discard",json={"media":[asset["id"]],"exports":[]}).raise_for_status()
    with Session(create_engine(f"sqlite:///{tmp_path/'files.db'}")) as db:
        record=Files.get_file_by_id(asset["fileId"],db=db)
        assert record.filename==src.name and Path(record.path).read_bytes()==src.read_bytes()
        assert Files.delete_all_files(db=db)
        Storage.delete_all_files()
        assert not Path(record.path).exists() and src.is_file()


def test_discard_does_not_interrupt_an_existing_download(app):
    _, actor = app
    async def scenario():
        id = "4169d90d649448bcb4ee17e83c1cce15"
        path = video_edit.workspace(actor)/f"{id}.mp4"
        original = b"rendered video"*19000
        path.write_bytes(original)
        arrived, release = asyncio.Event(), asyncio.Event()
        delivered = bytearray()
        async def send(event):
            if event["type"] == "http.response.body":
                arrived.set()
                await release.wait()
                delivered.extend(event["body"])
        response = video_edit.PreviewResponse(path, media_type="video/mp4")
        transfer = asyncio.create_task(response({"type":"http","method":"GET","headers":[]},None,send))
        await asyncio.wait_for(arrived.wait(),2)
        await video_edit.discard_session(video_edit.Discard(media=[],exports=[id]), actor)
        assert path.exists() and not transfer.done()
        release.set()
        await transfer
        assert delivered == original and not path.exists()
    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["fps60", "vocals", "instrumental"])
def test_local_clip_tools_on_real_media(app, tmp_path, monkeypatch, operation):
    client, actor = app
    root = ROOT / "backend/data/cache/video_edit_tools"
    monkeypatch.setattr(video_edit, "TOOL_ROOT", root)
    fixture = ROOT / "videoteste/teste.mp4"
    if not fixture.exists() or operation not in client.get("/clip-tools").json():
        pytest.skip("Local runtime and video fixture required")
    asset = import_media(client, fixture)
    url = "/media/" + asset["id"] + "/process"
    params = {"start": 15.25, "end": 16.75, "operation": operation}
    actor.id = "bob"
    assert client.post(url, json=params).status_code == 404
    actor.id = "alice"
    assert client.post(url, json={**params, "end": 400}).status_code == 422
    response = client.post(url, json=params)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["id"] != asset["id"] and result["audio"] and result["browserReady"]
    length = 1.5
    assert abs(result["duration"] - length) < .09
    target = 60 if operation == "fps60" else 30
    assert abs(result["fps"] - target) < .1
    with av.open(BytesIO(client.get("/media/" + result["id"]).content)) as container:
        frames = list(container.decode(video=0))
        assert abs(len(frames) - length * target) <= 1
        assert np.std(frames[len(frames)//2].to_ndarray(format="gray")) > 10
    assert client.get("/media/" + result["id"] + "/thumbnail").status_code == 200
    assert max(client.get("/media/" + result["id"] + "/waveform").json()["samples"]) > 0


def test_masked_clip_tools_preserve_time_audio_and_non_target(app, tmp_path, monkeypatch):
    operation = "erase"
    from PIL import Image
    import base64
    client, _ = app
    monkeypatch.setattr(video_edit, "TOOL_ROOT", ROOT / "backend/data/cache/video_edit_tools")
    if operation not in client.get("/clip-tools").json():
        pytest.skip("Optional visual processors required")
    src = tmp_path / "subject.mp4"
    subprocess.run([ffmpeg_binary(), "-v","error","-f","lavfi","-i",
                    "color=c=gray:s=384x224:r=16,drawbox=x=130:y=44:w=92:h=106:color=red:t=fill,drawbox=x=18:y=30:w=23:h=48:color=blue:t=fill",
                    "-f","lavfi","-i","sine=frequency=480:sample_rate=44100","-t","1.1","-c:v","libx264","-c:a","aac",str(src)],check=True)
    asset = import_media(client, src)
    route = "/media/"+asset["id"]+"/selection"
    opts = {"operation":operation, "start":0}
    assert client.post(route,json=opts).json()["frame"].startswith("data:image/png;base64,")
    response = client.post(route,json={**opts,"points":[[.46,.43,1],[.08,.21,0]]})
    assert response.status_code == 200, response.text
    selection = response.json()["mask"].split(",")[1]
    with Image.open(BytesIO(base64.b64decode(selection))) as mask:
        assert mask.getpixel((165,92)) and not mask.getpixel((30,53))
    response = client.post("/media/"+asset["id"]+"/process", json={"operation":operation,"start":0,"end":1.0625,
        "selection":selection})
    assert response.status_code == 200,response.text
    result = response.json()
    assert result["audio"] and abs(result["duration"]-1.0625)<.1
    with av.open(BytesIO(client.get("/media/"+result["id"]).content)) as media:
        frames = [f.to_ndarray(format="rgb24").astype(float) for f in media.decode(video=0)]
    assert len(frames)==17
    for frame in frames:
        center = frame[75:110,155:194].mean(axis=(0,1))
        assert center[0]-center[1]<130, center
        assert frame[53,30,2] > 200 and frame[53,30,0]<25


def test_full_clip_tracks_moving_target_from_middle(app, tmp_path, monkeypatch):
    operation = "erase"
    import base64
    from PIL import Image
    client, _ = app
    monkeypatch.setattr(video_edit, "TOOL_ROOT", ROOT/"backend/data/cache/video_edit_tools")
    if operation not in client.get("/clip-tools").json():
        pytest.skip("Requires local media tool weights")
    # More than 120 frames, including content on both sides of the reference.
    fps, n = 24, 132
    src = tmp_path/"moving.mp4"
    subprocess.run([ffmpeg_binary(),"-v","error","-f","lavfi","-i",
        "color=gray:s=256x144:r=24,drawbox=x=12:y=10:w=20:h=20:color=blue:t=fill[bg];"
        "color=red:s=48x48:r=24[s];[bg][s]overlay=x='30+24*t':y=62",
        "-f","lavfi","-i","sine=frequency=330:sample_rate=48000","-t",str(n/fps),
        "-c:v","libx264","-c:a","aac",str(src)], check=True)
    url = "/media/"+import_media(client,src)["id"]
    anchor = 2.75
    opts = {"operation":operation,"start":anchor,"points":[[(30+24*anchor+24)/256,86/144,1]]}
    picked = client.post(url+"/selection",json=opts)
    assert picked.status_code==200, picked.text
    mask = picked.json()["mask"].split(",")[1]
    with Image.open(BytesIO(base64.b64decode(mask))) as im:
        assert im.getpixel((120,86)) and not im.getpixel((54,86))
    params = {"operation":operation,"start":0,"end":n/fps,"anchor":anchor,"selection":mask}
    assert client.post(url+"/process",json={**params,"anchor":-1}).status_code==422
    result = client.post(url+"/process",json=params)
    assert result.status_code==200,result.text
    assert result.json()["audio"]
    with av.open(BytesIO(client.get("/media/"+result.json()["id"]).content)) as container:
        frames = list(container.decode(video=0))
    assert len(frames)==n
    for i,f in enumerate(frames):
        image = f.to_ndarray(format="rgb24").astype(float)
        x = 30+i+24
        r,g,b = image[80:92,x-5:x+5].mean(axis=(0,1))
        assert r-g<145 and image[20,20,2]>190, (i,r,g,b)


def test_mdx_stems_recombine_across_window_boundary(tmp_path):
    from neveai.utils.video_edit_tool_assets import MDX
    weights = ROOT / "backend/data/cache/video_edit_tools" / MDX
    src = ROOT / "videoteste/teste.mp4"
    if not weights.exists() or not src.exists():
        pytest.skip("Local MDX weights and fixture required")
    audio = tmp_path / "mix.raw"
    subprocess.run([ffmpeg_binary(), "-v","error","-ss","12","-i",str(src),"-t","8","-map","0:a:0",
                    "-ac","2","-ar","44100","-f","f32le",str(audio)], check=True)
    mix = np.fromfile(audio, dtype="<f4")
    stems = []
    for op in ("vocals","instrumental"):
        dst = tmp_path / op
        subprocess.run([sys.executable,str(ROOT/"backend/neveai/utils/video_edit_mdx.py"),str(weights),str(audio),str(dst),op],check=True)
        stems.append(np.fromfile(dst,dtype="<f4"))
    assert all(s.shape==mix.shape and np.isfinite(s).all() and np.std(s)>.001 for s in stems)
    assert not np.allclose(stems[0],stems[1],atol=.001)
    assert np.allclose(stems[0]+stems[1],mix,atol=1e-6)


def test_clip_worker_cancel_releases_descendant(tmp_path):
    import psutil
    async def run():
        # The worker starts another process just like the Windows venv launcher.
        cmd = "import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);pathlib.Path('pid').write_text(str(p.pid));time.sleep(60)"
        task = asyncio.create_task(video_edit.run_process([sys.executable,"-c",cmd],tmp_path,kill_tree=True))
        for _ in range(100):
            if (tmp_path/"pid").is_file() and (tmp_path/"pid").stat().st_size:
                break
            await asyncio.sleep(.05)
        child = psutil.Process(int((tmp_path/"pid").read_text()))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task,10)
        assert not child.is_running() or child.status()==psutil.STATUS_ZOMBIE
    asyncio.run(run())


@pytest.mark.parametrize("operation", ["background", "replace"])
def test_retired_clip_tools_rejected(app, operation):
    client, _ = app
    assert operation not in client.get("/clip-tools").json()
    route = "/media/01234567-89ab-4def-8123-456789abcdef"
    for endpoint in ("process", "selection"):
        assert client.post(route + "/" + endpoint, json={"operation":operation,"start":0,"end":1}).status_code == 422


def test_clip_tool_request_routing_live():
    if os.environ.get("NEVE_TEST_MAKER_TOOL_DIRECTOR") != "1":
        pytest.skip("Opt-in local model test")
    async def run():
        async with video_edit.director_model(lambda *_:None) as (_,model):
            for prompt, op in [("Separe a voz da trilha sonora deste clipe.","vocals"),
                               ("Retire o vocal, deixe apenas o acompanhamento.","instrumental"),
                               ("Converta este clipe para 60 FPS.","fps60"),
                               ("Apague o carro da imagem sem remover nenhum trecho.","erase")]:
                edit = video_edit.Plan(clips=[Clip(asset="a",start=0,end=1)],prompt=prompt,useClipTools=True)
                with pytest.raises(director.RequestedClipTool) as result:
                    await director.direct_edit(edit,prompt,{"a":{"duration":1}},model,None,lambda *_:None)
                assert result.value.args == (op,)
    asyncio.run(run())


@pytest.mark.parametrize("height,position,expected_y", [(480,"top",.14),(720,"center",.5),(1080,"bottom",.86)])
def test_export_resolution_and_burned_caption_position(app, tmp_path, height, position, expected_y):
    client, _ = app
    src = tmp_path / "black.mp4"
    subprocess.run([ffmpeg_binary(), "-v","error","-f","lavfi","-i","color=black:s=320x180:r=12","-t","1","-c:v","libx264",str(src)], check=True)
    asset = import_media(client, src)["id"]
    req = {"clips":[{"asset":asset,"start":0,"end":1}],"height":height,
           "captionStyle":{"position":position},"captions":[{"asset":asset,"start":0,"end":1,"text":"Studio"}]}
    job = client.post("/exports", json=req).json()["id"]
    assert wait_export(client, job)["status"] == "done"
    with av.open(BytesIO(client.get(f"/exports/{job}/mp4").content)) as media:
        frame = next(media.decode(video=0)).to_ndarray(format="gray")
    y, x = np.nonzero(frame > 128)
    assert frame.shape[0] == height and len(x) > 20
    assert abs(x.mean()/frame.shape[1] - .5) < .03
    assert abs(y.mean()/height - expected_y) < .10


@pytest.mark.parametrize("size", [(320, 240), (150, 264), (357, 193)])
def test_original_mp4_keeps_exact_source_dimensions(app, tmp_path, size):
    client, _ = app
    w, h = size
    src = tmp_path / "source.mp4"
    subprocess.run([ffmpeg_binary(), "-v", "error", "-f", "lavfi", "-i", f"testsrc=s={w}x{h}:r=15",
                    "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv444p", str(src)], check=True)
    asset = import_media(client, src)["id"]
    req = {"height": "original", "clips": [{"asset": asset, "start": .2, "end": .8}],
           "captions": [{"asset": asset, "start": .2, "end": .8, "text": "Studio"}]}
    job = client.post("/exports", json=req).json()["id"]
    assert wait_export(client, job)["status"] == "done"
    with av.open(BytesIO(client.get(f"/exports/{job}/mp4").content)) as media:
        frame = next(media.decode(video=0))
        assert (frame.width, frame.height) == size
        assert .5 <= media.duration / av.time_base <= .75


def test_real_export_reorder_subtitles_auth_and_streaming(app, tmp_path):
    client, actor = app
    src = tmp_path / "fixture.mp4"
    subprocess.run([ffmpeg_binary(), "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=240x136:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=450:sample_rate=48000", "-t", "4",
                    "-c:v", "libx264", "-c:a", "aac", str(src)], check=True)
    asset = import_media(client, src)
    url = "/media/" + asset["id"]
    assert client.get(url, headers={"Range": "bytes=0-127"}).status_code == 206
    assert client.get(url + "/thumbnail").content.startswith(b"\xff\xd8")
    waveform = client.get(url + "/waveform").json()["samples"]
    assert len(waveform) == 240 and 0 < max(waveform) <= 1
    actor.id = "bob"
    assert client.get(url).status_code == 404
    assert client.get(url + "/waveform").status_code == 404
    actor.id = "alice"
    edit = {"clips": [{"asset": asset["id"], "start": 2, "end": 3.5, "zoom": 1.2},
                      {"asset": asset["id"], "start": .25, "end": 1.25, "gain": .5}],
            "height": 720, "normalize": True,
            "captions": [{"asset": asset["id"], "start": .5, "end": 1, "text": "Closed captions"}]}
    assert client.post("/exports", json={**edit, "height": 100}).status_code == 422
    job = client.post("/exports", json=edit).json()["id"]
    assert wait_export(client, job)["status"] == "done"
    from neveai.utils.video_edit import Timeline, projected_captions
    parsed = Timeline(**edit)
    assert list(projected_captions(parsed.clips,parsed.captions)) == [(1.75,2.25,"Closed captions")]
    out = tmp_path / "result.mp4"
    out.write_bytes(client.get(f"/exports/{job}/mp4").content)
    with av.open(str(out)) as media:
        assert len(media.streams.audio) == 1
        assert media.streams.video[0].height == 720
        assert abs(media.duration / av.time_base - 2.5) < .16
        assert len(list(media.decode(video=0))) >= 73
    actor.id = "bob"
    assert client.get(f"/exports/{job}/mp4").status_code == 404


def test_director_stream_uses_visual_evidence_and_retries_missing_requirements(app, tmp_path, monkeypatch):
    client, _ = app
    source = tmp_path / "source.mp4"
    subprocess.run([ffmpeg_binary(), "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=24",
                    "-t", "6", "-c:v", "libx264", str(source)], check=True)
    media = import_media(client, source)
    attempts = 0
    saw_photos = False

    async def complete(messages, **kwargs):
        nonlocal attempts, saw_photos
        kind = kwargs["response_format"]["json_schema"]["name"]
        if kind == "VisualNotes":
            payload = messages[-1]["content"]
            saw_photos = payload[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
            ids = json.loads(payload[0]["text"].split(": ")[-1])
            value = {"scenes": [{"id": i, "action": "Moving pattern", "material": "scene"} for i in ids]}
        elif kind == "Commission":
            value = {"scope": "modify existing cut", "requested_deliverable": "Reverse the specified shots", "visual_treatment": "editor chooses", "no_fx_instruction": ""}
        elif kind == "Brief":
            value = {"reorder": True, "overlay": True, "layout": "inset", "effects": ["glitch"], "captions": "optional",
                     "minSeconds": 3, "maxSeconds": 3}
        elif kind == "LayerPlan":
            picks = kwargs["response_format"]["json_schema"]["schema"]["$defs"]["LayerPick"]["properties"]
            value = {"layers": [{"scene": picks["scene"]["enum"][0], "duration": 1,
                                 "over": picks["over"]["enum"][0], "layout": "inset"}]}
        else:
            attempts += 1
            shot = {"source": 0, "start": 0, "end": 1, "at": 0, "track": 0, "layout": "full",
                    "volume": 0, "crop": 1, "color": "none", "fx": "none"}
            value = {"shots": [shot], "captions": "keep", "aspect": "source", "title": "", "summary": "Cut around the action."}
            if attempts > 1:
                assert "later source scene" in messages[-1]["content"]
                value["shots"] = [{**shot, "start": 3, "end": 4.5, "fx": "glitch"},
                                  {**shot, "start": 0, "end": 1.5}]
        return {"choices": [{"message": {"content": json.dumps(value)}}]}

    payload = {"clips": [{"asset": media["id"], "start": 0, "end": 6}], "prompt": "Put the end first and add an inset."}
    monkeypatch.setattr(video_edit_model, "DATA_DIR", tmp_path / "missing")
    unavailable = client.post("/plan", json=payload)
    assert unavailable.status_code == 503 and "Neve Studio weights" in unavailable.json()["detail"]

    @asynccontextmanager
    async def fixture_model(progress):
        yield {"n_ctx": 8192, "filename": "test.gguf"}, complete

    monkeypatch.setattr(video_edit, "director_model", fixture_model)
    rows = [json.loads(line) for line in client.post("/plan/progress", json=payload).text.splitlines()]
    assert saw_photos and attempts == 2
    assert any(row.get("progress", {}).get("phase") == "Checking and refining the timeline..." for row in rows)
    edit = rows[-1]["result"]
    assert [c["start"] for c in edit["clips"]] == [3, 0, 0]
    assert edit["clips"][2]["layout"] == "inset"


@pytest.mark.parametrize("layout", ["inset", "left", "right", "dissolve"])
def test_composition_pixels_and_audio_survive_export(app, tmp_path, layout):
    client, _ = app
    assets = []
    for color, tone in (("red", 440), ("blue", 880)):
        src = tmp_path / (color + ".mp4")
        subprocess.run([ffmpeg_binary(), "-v", "error", "-f", "lavfi", "-i", f"color={color}:s=160x90:r=24",
                        "-f", "lavfi", "-i", f"sine=frequency={tone}:sample_rate=48000", "-t", "3",
                        "-c:v", "libx264", "-c:a", "aac", str(src)], check=True)
        assets.append(import_media(client, src)["id"])
    edit = {"height": 720, "clips": [
        {"asset": assets[0], "start": 0, "end": 3, "at": 0},
        {"asset": assets[1], "start": .2, "end": 2.2, "at": .5, "lane": 1, "layout": layout, "gain": 0}],
        "captions": [{"asset": assets[0], "start": .6, "end": 2, "text": "Dialogue continues under the cutaway"}]}
    job = client.post("/exports", json=edit).json()["id"]
    assert wait_export(client, job)["status"] == "done"
    raw = client.get(f"/exports/{job}/mp4").content
    with av.open(BytesIO(raw)) as movie:
        frames = [frame.reformat(32, 24).to_ndarray(format="rgb24") for frame in movie.decode(video=0)]
        assert len(frames) == 72
        assert frames[5][2, 25].argmax() == 0 and frames[67][2, 25].argmax() == 0
        mid = frames[35]
        if layout == "inset":
            assert mid[3, 25].argmax() == 2 and mid[15, 8].argmax() == 0
        elif layout == "left":
            assert mid[10, 4].argmax() == 2 and mid[10, 25].argmax() == 0
        elif layout == "right":
            assert mid[10, 4].argmax() == 0 and mid[10, 25].argmax() == 2
        else:
            assert np.all(mid[3, 25] == mid[10, 4]) and mid[3, 25].argmax() == 2
            assert int(frames[17][2, 25, 0]) > int(mid[2, 25, 0])
    with av.open(BytesIO(raw)) as movie:
        samples = np.concatenate([frame.to_ndarray()[0] for frame in movie.decode(audio=0)])
        window = samples[48000:72000]
        spectrum = np.abs(np.fft.rfft(window * np.hanning(len(window))))
        assert spectrum[220] > spectrum[440] * 30
    assert client.get(f"/exports/{job}/srt").status_code == 404


@pytest.mark.parametrize("motion", ["push", "whip", "glitch", "dip", "flash"])
def test_effect_changes_rendered_frames_on_a_static_source(app, tmp_path, motion):
    client, _ = app
    src = tmp_path / "bars.mp4"
    subprocess.run([ffmpeg_binary(), "-v", "error", "-f", "lavfi", "-i", "smptebars=size=160x90:rate=24",
                    "-t", "2", "-c:v", "libx264", str(src)], check=True)
    asset = import_media(client, src)["id"]
    edit = {"height": 720, "clips": [{"asset": asset, "start": 0, "end": 2, "at": 0, "motion": motion}]}
    job = client.post("/exports", json=edit).json()["id"]
    assert wait_export(client, job)["status"] == "done"
    with av.open(BytesIO(client.get(f"/exports/{job}/mp4").content)) as movie:
        frames = [frame.reformat(64, 36).to_ndarray(format="rgb24").astype(float) for frame in movie.decode(video=0)]
        assert len(frames) == 48
        assert max(np.abs(frame - frames[-1]).mean() for frame in frames[:-1]) > 2, motion


def test_proxy_and_cancel_allow_later_exports(app, tmp_path, monkeypatch):
    client, _ = app
    rejected = client.post("/media", files={"file": ("invalid.mp4", b"not a video", "video/mp4")})
    assert rejected.status_code == 422
    assert not list(video_edit.ROOT.rglob("*.source"))

    source = tmp_path / "portrait.webm"
    subprocess.run([ffmpeg_binary(), "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=136x240:rate=30",
                    "-t", "2", "-c:v", "libvpx-vp9", str(source)], check=True)
    asset = import_media(client, source)
    assert not asset["browserReady"] and not asset["audio"]
    assert client.get("/media/" + asset["id"], headers={"Range": "bytes=0-127"}).content[4:8] == b"ftyp"
    edit = {"clips": [{"asset": asset["id"], "start": 0, "end": 1}], "height": 720}

    original = video_edit.run_process

    async def blocked(*args, **kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr(video_edit, "run_process", blocked)
    cancelled = client.post("/exports", json=edit).json()["id"]
    assert client.post("/exports", json=edit).status_code == 409
    assert client.delete(f"/exports/{cancelled}").json()["status"] == "cancelled"
    assert client.get(f"/exports/{cancelled}/mp4").status_code == 404

    monkeypatch.setattr(video_edit, "run_process", original)
    job = client.post("/exports", json=edit).json()["id"]
    assert wait_export(client, job)["status"] == "done"
    with av.open(BytesIO(client.get(f"/exports/{job}/mp4").content)) as video:
        assert video.streams.video[0].width < video.streams.video[0].height


def test_layered_video_mixes_audio_and_keeps_absolute_positions(app, tmp_path):
    import numpy as np
    from faster_whisper.audio import decode_audio

    client, _ = app
    sources = []
    for color, tone in [("red", 440), ("blue", 880), ("green", 1250)]:
        path = tmp_path / f"{color}.mp4"
        subprocess.run([ffmpeg_binary(), "-v", "error", "-f", "lavfi", "-i", f"color={color}:s=160x90:r=24",
                        "-f", "lavfi", "-i", f"sine=frequency={tone}:sample_rate=48000",
                        "-t", "3", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac", str(path)], check=True)
        sources.append(import_media(client, path))
    edit = {"height": 720, "clips": [
        {"asset": sources[0]["id"], "start": 0, "end": 3, "at": 0},
        {"asset": sources[1]["id"], "start": .2, "end": 1.2, "at": 1, "lane": 1, "effect": "vivid"},
        {"asset": sources[2]["id"], "start": 0, "end": 1, "at": 1, "lane": 2, "audioOnly": True}],
        "captions": [{"asset": sources[1]["id"], "start": .25, "end": 1, "text": "Layered caption"}],
        "captionStyle": {"font": "Georgia", "size": 24, "theme": "highlight"}}
    result = client.post("/exports", json=edit)
    assert result.status_code == 202, result.text
    job = result.json()["id"]
    assert wait_export(client, job)["status"] == "done"
    path = tmp_path / "layered.mp4"
    path.write_bytes(client.get(f"/exports/{job}/mp4").content)
    with av.open(str(path)) as media:
        assert abs(media.duration / av.time_base - 3) < .17
        colors = []
        for time_offset in (.4, 1.4, 2.4):
            media.seek(round(time_offset * av.time_base))
            frame = next(frame for frame in media.decode(video=0) if frame.time >= time_offset)
            colors.append(frame.to_ndarray(format="rgb24")[130, 500].argmax())
        assert colors == [0, 2, 0]
    signal = decode_audio(str(path), sampling_rate=16000)[19200:27200]
    peaks = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
    assert all(max(peaks[round(hz / 2) - 2:round(hz / 2) + 3]) > 10 for hz in (440, 880, 1250))
    assert client.get(f"/exports/{job}/srt").status_code == 404
