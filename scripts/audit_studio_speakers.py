"""Run only the speaker pass on a local recording; do not change or transcribe the source."""
import argparse
import sys
import numpy as np
from time import perf_counter
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from neveai.utils.video_edit_assist import audio_blocks,speaker_evidence,speaker_workers
from neveai.utils.video_edit_speakers import resolve_turns
import av

def report(obs,turns,checks,count=None):
    clock=perf_counter()
    resolved=resolve_turns(obs,turns,count)
    print("resolve seconds",round(perf_counter()-clock,3),flush=True)
    secs=Counter()
    for a,b,k in resolved: secs[k]+=b-a
    print("mode",count or "auto","speakers",len(secs),"seconds per speaker",sorted(map(round,secs.values()),reverse=True),
          "unassigned seconds",round(sum(b-a for a,b,_ in turns)-sum(secs.values())),flush=True)
    labels={}
    for _,_,k in resolved:labels.setdefault(k,len(labels)+1)
    for at in checks:
        near=sorted(resolved,key=lambda t:max(0,t[0]-at,at-t[1]))[:2]
        print("check",at,[(round(a,2),round(b,2),labels[k]) for a,b,k in near],flush=True)
    return [(a,b,labels[k]) for a,b,k in resolved]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("source",type=Path)
    parser.add_argument("--jobs",type=int,choices=(1,2,3))
    parser.add_argument("--compare-blocks",type=int,default=0)
    parser.add_argument("--features",type=Path,help="Optional temporary test features for replaying cluster evaluation")
    parser.add_argument("--check",nargs="*",type=float,default=[])
    parser.add_argument("--count",type=int)
    args=parser.parse_args()
    with av.open(str(args.source)) as f: end=f.duration/av.time_base
    blocks=list(audio_blocks(0,end))
    cache=ROOT/"backend/data/cache/video_edit_speakers"
    with TemporaryDirectory() as d:
        work=Path(d)
        jobs=args.jobs or speaker_workers(len(blocks))
        print("duration",end,"blocks",len(blocks),"workers",jobs,flush=True)
        clock=perf_counter()
        observations,turns=speaker_evidence(args.source,blocks,cache,work,jobs)
        print("full speaker evidence seconds",round(perf_counter()-clock,2),flush=True)
        if args.features:
            vectors,weights,windows=zip(*observations)
            np.savez_compressed(args.features,vectors=vectors,weights=weights,windows=windows,turns=turns)
        auto=report(observations,turns,args.check)
        if args.count:
            fixed=report(observations,turns,args.check,args.count)
            print("same normalized turns",fixed==auto,flush=True)
        if args.compare_blocks:
            sample=blocks[:args.compare_blocks]
            clock=perf_counter()
            obs,part=speaker_evidence(args.source,sample,cache,work,1)
            serial=perf_counter()-clock
            clock=perf_counter()
            other,parallel=speaker_evidence(args.source,sample,cache,work,jobs)
            assert part==parallel and len(obs)==len(other)
            for (v,*w),(x,*y) in zip(obs,other):
                assert np.allclose(v,x) and w==y
            print("equal sample evidence; seconds serial, parallel",round(serial,2),round(perf_counter()-clock,2),flush=True)

if __name__=="__main__": main()
