"""Local speaker turns, aligned to Whisper word timestamps (not speaker identity)."""
from pathlib import Path


def model_paths(cache, local_only=True):
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    def weight(repo, revision, filename):
        args = dict(repo_id=repo, revision=revision, filename=filename, cache_dir=str(cache))
        try:
            return hf_hub_download(**args, local_files_only=True)
        except LocalEntryNotFoundError:
            if local_only:
                raise
            return hf_hub_download(**args)

    return (
        weight("csukuangfj/sherpa-onnx-reverb-diarization-v1", "d6a516efb21b1d22cb1c7baae704acacaa3ff71a", "model.onnx"),
        weight("csukuangfj/speaker-embedding-models", "a8055d6daef723a6a4ecf4de233708575bf4994f", "nemo_en_titanet_small.onnx"),
    )


def label_words(words, turns, previews=None, offset=0, *, group=True):
    """Choose by overlap. Keep unsupported words as text, without inventing a speaker."""
    from neveai.utils.studio_subtitles import compose_subtitles
    turns = sorted(turns)
    first = 0
    labels = {}
    cues = []
    for word in words:
        a, b = word["start"], word["end"]
        while first < len(turns) and turns[first][1] < a - .25:
            first += 1
        best, speaker = -.251, None
        for i in range(first, len(turns)):
            start, end, tag = turns[i]
            if start > b + .25:
                break
            overlap = min(b, end) - max(a, start)
            if overlap > best:
                best, speaker = overlap, tag
        label = labels.setdefault(speaker, len(labels) + 1) if speaker is not None else None
        cue = dict(word)
        if label is not None:
            cue["speaker"] = label
        cues.append(cue)
    if previews is not None:
        # Prefer uninterrupted audio, away from turn boundaries and overlapping voices.
        prior_end=-1
        quality={}
        for i,(a,b,tag) in enumerate(turns):
            left=max(a,prior_end)
            right=min(b,turns[i+1][0]) if i+1<len(turns) else b
            prior_end=max(prior_end,b)
            if tag not in labels or right-left<=quality.get(tag,0): continue
            quality[tag]=right-left
            mid=(left+right)/2+offset
            half=min(3,right-left)/2
            previews[labels[tag]]=[mid-half,mid+half]
    return compose_subtitles(cues) if group else cues


def speaker_models(cache, count=None):
    import sherpa_onnx as so

    seg, emb = model_paths(Path(cache))
    config = so.OfflineSpeakerDiarizationConfig(
        segmentation=so.OfflineSpeakerSegmentationModelConfig(
            pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=seg), num_threads=2),
        embedding=so.SpeakerEmbeddingExtractorConfig(model=emb, num_threads=2),
        clustering=so.FastClusteringConfig(num_clusters=count or -1, threshold=.5),
        min_duration_on=.18, min_duration_off=.3)
    return so.OfflineSpeakerDiarization(config), emb


def identify(path, words, cache, previews=None, offset=0, count=None, *, group=True):
    if not words:
        return []
    from faster_whisper.audio import decode_audio

    diarizer,_ = speaker_models(cache,count)
    turns = diarizer.process(decode_audio(str(path), sampling_rate=16000)).sort_by_start_time()
    if not turns:
        raise ValueError("No speakers detected.")
    return label_words(words, [(t.start,t.end,t.speaker) for t in turns], previews, offset, group=group)


class SessionSpeakers:
    """Local clusters are renumbered in every window; match their acoustic embeddings, not IDs."""
    def __init__(self, cache):
        import sherpa_onnx as so
        self.diarizer, model = speaker_models(cache)
        self.encoder = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(model=model,num_threads=2))
        self.observations = []

    def turns(self,path,offset,left,right):
        from faster_whisper.audio import decode_audio
        from faster_whisper.vad import get_speech_timestamps,VadOptions
        from bisect import bisect_right
        import math
        import numpy as np

        audio = decode_audio(str(path),sampling_rate=16000)
        local=self.diarizer.process(audio).sort_by_start_time()
        speech=get_speech_timestamps(audio,VadOptions(min_speech_duration_ms=150,min_silence_duration_ms=280,speech_pad_ms=50))
        ends=[s["end"]/16000 for s in speech]
        turns=[]
        for t in local:
            if offset+t.end<=left or offset+t.start>=right: continue
            for i in range(bisect_right(ends,t.start),len(speech)):
                a=max(t.start,speech[i]["start"]/16000)
                b=min(t.end,ends[i])
                if a>=t.end:break
                if b<=a:continue
                cuts=np.linspace(a,b,1+math.ceil((b-a)/4.5))
                turns.extend((x,y,t.speaker) for x,y in zip(cuts,cuts[1:]) if offset+y>left and offset+x<right)
        turns.sort()
        groups=[]
        assigned={}
        by_tag={}
        # One local ID can contain several voices. Embed individual utterances before
        # pooling; combine near-identical examples only, keeping the global pass small.
        previous_end=0
        for i,(a,b,tag) in enumerate(turns):
            lo,hi=max(a,previous_end),min(b,turns[i+1][0] if i+1<len(turns) else b)
            previous_end=max(previous_end,b)
            if hi-lo<.8: continue
            mid=(hi+lo)/2
            st=self.encoder.create_stream()
            st.accept_waveform(16000,audio[int(16000*max(lo,mid-3)):int(16000*min(hi,mid+3))])
            st.input_finished()
            if not self.encoder.is_ready(st): continue
            v=np.asarray(self.encoder.compute(st))
            norm=np.linalg.norm(v)
            if not np.isfinite(norm) or norm<1e-6:continue
            v=v/norm
            sims=[g[0]@v for g in groups]
            best=int(np.argmax(sims)) if sims else -1
            weight=min(hi-lo,6)
            if best<0 or sims[best]<.94:
                best=len(groups);groups.append([v,weight,0.])
            else:
                center,total,seconds=groups[best]
                center=center*total+v*weight
                groups[best]=[center/np.linalg.norm(center),total+weight,seconds]
            assigned[i]=best
            groups[best][2]+=b-a
            by_tag.setdefault(tag,[]).append((i,best))
        base=len(self.observations)
        self.observations.extend((v,seconds,left) for v,_,seconds in groups)
        result=[]
        for i,(a,b,tag) in enumerate(turns):
            idx=assigned.get(i)
            if idx is None:
                # A breath/noisy fragment is not evidence for a new person.
                near=min(by_tag.get(tag,()),key=lambda p:abs(turns[p[0]][0]-a),default=None)
                if near is None or abs(turns[near[0]][0]-a)>12:continue
                idx=near[1]
            result.append((max(left,offset+a),min(right,offset+b),base+idx))
        return result

    def resolve(self,turns,count=None):
        return resolve_turns(self.observations,turns,count)


def resolve_turns(observations,turns,count=None):
    import numpy as np
    if not turns: return []
    vectors=np.stack([v for v,_,_ in observations])
    weights=np.array([s for _,s,_ in observations])
    labels=recording_speakers(vectors,weights,count)
    return [(a,b,int(labels[i])) for a,b,i in turns if labels[i]>=0]


def recording_speakers(vectors,weights,count=None):
    """Estimate recording-wide groups from the eigengap of a speaker-neighbour graph.

    Inspired by Park et al., doi:10.1109/LSP.2019.2961071. Bound the graph even
    on five-hour recordings; propagate labels by local votes, not a single prototype.
    """
    import numpy as np
    from scipy.linalg import eigh
    from scipy.cluster.hierarchy import linkage,fcluster
    from scipy.sparse.csgraph import laplacian
    n=len(vectors)
    if n==1 or count==1:return np.zeros(n,dtype=int)
    if count and n<=640:return known_speaker_groups(vectors,weights,count)
    if n<8:
        return fcluster(linkage(vectors,method="average",metric="cosine"),.50,criterion="distance")
    rng=np.random.default_rng(0)
    ids=np.arange(n)
    if n>640:
        probs=np.clip(weights,.5,8)
        ids=np.sort(rng.choice(n,640,replace=False,p=probs/probs.sum()))
    x=vectors[ids]
    similarities=x@x.T
    np.fill_diagonal(similarities,-np.inf)
    order=np.argsort(-similarities,axis=1)
    m=len(x)
    candidates=min(m-1,max(count or 0,min(32,max(2,m//3))))
    best=None
    for neighbours in sorted({min(m-1,max(2,round(m*f))) for f in (.035,.07,.12,.18)}):
        adjacency=np.zeros((m,m),dtype=np.float64)
        np.put_along_axis(adjacency,order[:,:neighbours],1.,axis=1)
        # Retain exceptionally similar voices even if dense neighbours displaced
        # them from top-p; otherwise identical recordings can split by microphone.
        graph=laplacian(np.maximum((adjacency+adjacency.T)/2,similarities>.87),normed=True)
        vals,vecs=eigh(graph,subset_by_index=(0,candidates),check_finite=False)
        gaps=np.diff(vals)
        k=min(count or (1+int(np.argmax(gaps))),candidates)
        merit=gaps[k-1]/np.sqrt(neighbours)
        if best is None or merit>best[0]:best=(merit,k,vecs[:,:k])
    _,k,spectral=best
    if k==1:return np.zeros(n,dtype=int)
    spectral=spectral/np.linalg.norm(spectral,axis=1,keepdims=True).clip(1e-9)
    anchors=known_speaker_groups(spectral,weights[ids],k)
    result=np.empty(n,dtype=int)
    for start in range(0,n,256):
        scores=vectors[start:start+256]@x.T
        top=np.argsort(-scores,axis=1)[:,:min(7,len(x))]
        sim=np.take_along_axis(scores,top,axis=1)
        votes=np.zeros((len(scores),k))
        np.add.at(votes,(np.arange(len(scores))[:,None],anchors[top]),np.exp(12*(sim-1)))
        result[start:start+len(scores)]=np.where(sim[:,0]>=.23,votes.argmax(axis=1),-1)
    result[ids]=anchors
    return result


def known_speaker_groups(vectors,durations,count):
    """Weighted spherical k-means; weak local fragments need not seed a new identity."""
    import numpy as np
    weights=np.clip(durations,.1,30)
    count=min(count,len(vectors))
    rng=np.random.default_rng(0)
    best=None
    for _ in range(8):
        centers=[vectors[rng.choice(len(vectors),p=weights/weights.sum())]]
        while len(centers)<count:
            distance=np.maximum(0,1-(vectors@np.stack(centers).T).max(axis=1))
            prob=weights*distance**2
            if prob.sum()<1e-10: break
            centers.append(vectors[rng.choice(len(vectors),p=prob/prob.sum())])
        centers=np.stack(centers)
        for _ in range(25):
            scores=vectors@centers.T
            labels=scores.argmax(axis=1)
            sums=np.zeros_like(centers)
            np.add.at(sums,labels,vectors*weights[:,None])
            updated=sums/np.linalg.norm(sums,axis=1,keepdims=True).clip(1e-9)
            if np.allclose(centers,updated,atol=1e-4): break
            centers=updated
        scores=vectors@centers.T
        quality=weights@scores.max(axis=1)
        if best is None or quality>best[0]: best=(quality,scores.argmax(axis=1))
    return best[1]
