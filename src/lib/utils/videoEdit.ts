export type EditAsset = {
	id: string; name: string; duration: number; width: number; height: number; fps: number; audio: boolean; browserReady?: boolean;
};
export type EditEffect = 'none' | 'vivid' | 'cinema' | 'mono' | 'fade';
export type EditMotion = 'none' | 'push' | 'whip' | 'glitch' | 'dip' | 'flash';
type ColorValues = { contrast: number; brightness: number; saturation: number };
export type Grade = ColorValues & { samples?: (ColorValues & { time: number })[] };
function colorAt(grade: Grade | undefined, time: number) {
	const points = grade?.samples;
	if (!points?.length) return grade;
	const i = points.findIndex(p => p.time >= time);
	if (i < 0) return points[points.length-1];
	if (!i) return points[0];
	const a=points[i-1], b=points[i], t=(time-a.time)/Math.max(.00001,b.time-a.time);
	return { brightness:a.brightness+(b.brightness-a.brightness)*t,
		contrast:a.contrast+(b.contrast-a.contrast)*t,saturation:a.saturation+(b.saturation-a.saturation)*t };
}
export type EditClip = { opacity?: number; noAudio?: boolean; grade?: Grade; asset: string; start: number; end: number; zoom: number; gain: number; gainBeforeMute?: number; at?: number; lane?: number; audioOnly?: boolean; effect?: EditEffect; motion?: EditMotion; layout?: 'full' | 'inset' | 'left' | 'right' | 'dissolve' };
export type EditCaption = { style?: Partial<Pick<CaptionStyle, 'font' | 'theme' | 'size'>>; voiceSample?:[number,number]; speakerKey?: string; speakerName?: string; horizontal?: CaptionStyle['horizontal']; position?: CaptionStyle['position']; asset: string; start: number; end: number; text: string; speechOnly?: boolean };
export type CaptionStyle = { horizontal?: 'left' | 'center' | 'right'; animation?: 'none' | 'rise' | 'drop' | 'type' | 'pulse' | 'wave' | 'fade' | 'slide' | 'zoom' | 'blur' | 'spin'; position?: 'top' | 'center' | 'bottom'; font: 'Arial' | 'Georgia' | 'Consolas' | 'Segoe UI' | 'Tahoma' | 'Verdana' | 'Trebuchet MS' | 'Times New Roman' | 'Impact'; size: number; theme: 'outline' | 'box' | 'highlight' };
type TranscriptSpan = Pick<EditClip,'asset'|'start'|'end'>;
export type EditTimeline = { transcriptCoverage?: TranscriptSpan[]; clips: EditClip[]; captions: EditCaption[]; height: number; normalize: boolean; audioMuted?: boolean; mutedAudioLanes?: number[]; audioLaneGains?: Record<number, number>; hiddenAssets?: string[]; captionStyle?: CaptionStyle; aspect?: 'source' | 'portrait' | 'landscape'; title?: string | null };

export function coverTranscript(previous: TranscriptSpan[], {asset,start,end}: TranscriptSpan) {
	const sorted = [...previous.filter(s=>s.asset===asset),{asset,start,end}].sort((a,b)=>a.start-b.start);
	const merged: TranscriptSpan[]=[];
	for(const span of sorted) {
		const last=merged.at(-1);
		if(last && span.start<=last.end) last.end=Math.max(last.end,span.end);
		else merged.push({...span});
	}
	return [...previous.filter(s=>s.asset!==asset),...merged];
}

export const emptyTimeline = (): EditTimeline => ({ clips: [], captions: [], height: 1080, normalize: false });
export const defaultCaptionStyle: CaptionStyle = { font: 'Arial', size: 18, theme: 'outline' };
export const clipLength = (clip: EditClip) => clip.end - clip.start;
export const isLayered = (clips: EditClip[]) => clips.some(clip => clip.at != null || clip.audioOnly || clip.lane);
export const effectFilter = (effect?: EditEffect) =>
	({ vivid: 'saturate(1.34) contrast(1.10)', cinema: 'saturate(.82) contrast(1.16) brightness(.97)', mono: 'grayscale(1)', fade: 'none', none: 'none' }[effect ?? 'none']);

export function motionLook(clip: EditClip | undefined, time: number) {
	const t = Math.max(0, time);
	const effect = effectFilter(clip?.effect);
	const grade=colorAt(clip?.grade,(clip?.start ?? 0)+t);
	let scale = clip?.zoom ?? 1, x = 0, y = 0, light = 0, accent = '';
	if (clip?.motion === 'push') scale *= 1 + .16 * Math.sin(Math.PI * Math.min(1, t / .95));
	if (clip?.motion === 'whip') {
		scale *= 1.14;
		x = -6.44 * Math.exp(-7 * t);
		if (t < .12) accent = 'blur(2px)';
	}
	if (clip?.motion === 'glitch') {
		scale *= 1.14;
		x = -6.02 * Math.sin(75 * t) * Math.exp(-4 * t);
		y = -5.32 * Math.sin(103 * t) * Math.exp(-4 * t);
		if (t < .23) accent = 'contrast(1.4) saturate(1.7)';
	}
	if (clip?.motion === 'dip') light = -.76 * Math.max(0, 1 - t / .26);
	if (clip?.motion === 'flash') light = .48 * Math.max(0, 1 - t / .13);
	return {
		transform: `translate(${x}%,${y}%) scale(${scale})`,
		filter: [grade ? `contrast(${grade.contrast}) brightness(${1+grade.brightness}) saturate(${grade.saturation})` : '', effect === 'none' ? '' : effect, accent].filter(Boolean).join(' ') || 'none',
		light
	};
}
export const videoEditMediaUrl = (id: string) => `/api/v1/video-edit/media/${id}`;

type LabeledCue=Pick<EditCaption,'start'|'end'|'text'> & {speaker?:number;existingIndex?:number};
export function applySpeakerCues(previous:EditCaption[], cues:LabeledCue[], samples:Record<number,[number,number]>, asset:string, run:string, defaultName:(id:number)=>string){
	const captions=[...previous], votes=new Map<number,Map<string,number>>();
	const names=new Map<string,string>();
	for(const {existingIndex,speaker} of cues){
		const old=existingIndex===undefined?undefined:previous[existingIndex];
		if (!speaker || !old?.speakerKey) continue;
		names.set(old.speakerKey,old.speakerName??'');
		const pool=votes.get(speaker)??new Map<string,number>();
		pool.set(old.speakerKey,(pool.get(old.speakerKey)??0)+old.end-old.start);
		votes.set(speaker,pool);
	}
	const known=new Map<number,string>(), used=new Set<string>();
	const candidates=[...votes].flatMap(([id,pool])=>[...pool].map(([key,weight])=>({id,key,weight})));
	for(const {id,key} of candidates.sort((a,b)=>b.weight-a.weight)){
		if(known.has(id)||used.has(key))continue;
		known.set(id,key);used.add(key);
	}
	for(const {existingIndex,speaker,...cue} of cues){
		const key=speaker?known.get(speaker):undefined, name=key?names.get(key):undefined;
		const label=speaker?{speakerKey:key??run+':'+speaker,speakerName:name===undefined||/^(Speaker|Falante) \d+$/.test(name)?defaultName(speaker):name,voiceSample:samples[speaker]}:{};
		if(existingIndex===undefined)captions.push({...cue,asset,speechOnly:true,...label});
		else if(captions[existingIndex]){
			const {speakerKey,speakerName,voiceSample,...original}=previous[existingIndex];
			captions[existingIndex]={...original,...label};
		}
	}
	return captions;
}

export function waveformPath(samples: number[], start: number, end: number, duration: number) {
	if (!samples.length || duration <= 0) return '';
	const range = samples.slice(Math.floor(start / duration * samples.length), Math.ceil(end / duration * samples.length));
	if (!range.length) return '';
	const points = range.map((value, index) => ({
		x: (index + .5) * 1000 / range.length,
		amplitude: Math.max(0, Math.min(1, value)) * 43
	}));
	const side = (direction: number) => {
		const ordered = direction < 0 ? points : [...points].reverse();
		return ordered.map(({ x, amplitude }, index) => {
			const y = (50 + direction * amplitude).toFixed(1);
			const prev = ordered[index - 1];
			if (!prev) return `L ${x.toFixed(1)} ${y}`;
			const mid = ((prev.x + x) / 2).toFixed(1);
			return `C ${mid} ${(50 + direction * prev.amplitude).toFixed(1)} ${mid} ${y} ${x.toFixed(1)} ${y}`;
		}).join(' ');
	};
	return `M 0 50 ${side(-1)} L 1000 50 ${side(1)} Z`;
}
export const editOffsets = (clips: EditClip[]) => {
	let position = 0;
	return clips.map(clip => {
		const start = clip.at ?? position;
		if (clip.at == null) position += clipLength(clip);
		return start;
	});
};
export const editDuration = (clips: EditClip[]) => editOffsets(clips).reduce((end, at, index) => Math.max(end, at + clipLength(clips[index])), 0);

export function captionRuns(clips: EditClip[], offsets: number[], speechOnly = false) {
	const parts = clips.flatMap((clip, index) => (!speechOnly && clip.audioOnly) ? [] :
		[{ asset: clip.asset, start: clip.start, end: clip.end, at: offsets[index], lane: clip.lane ?? 0 }]);
	parts.sort((a, b) => a.lane - b.lane || a.at - b.at);
	const runs: typeof parts = [];
	for (const part of parts) {
		const last = runs.at(-1);
		if (last?.asset === part.asset && last.lane === part.lane && Math.abs(last.end - part.start) < .001
			&& Math.abs(last.at + last.end - last.start - part.at) < .001) last.end = part.end;
		else runs.push(part);
	}
	return runs;
}

type CaptionRun=ReturnType<typeof captionRuns>[number] & {speechOnly:boolean};
export function visibleCaptionEntries(captions:EditCaption[],runs:CaptionRun[]) {
	const lists=new Map<string,{cue:EditCaption;index:number;maxEnd:number}[]>();
	const key=(asset:string,speech:boolean)=>asset+':'+Number(speech);
	captions.forEach((cue,index)=>{
		const id=key(cue.asset,!!cue.speechOnly),list=lists.get(id)??[];
		list.push({cue,index,maxEnd:0});lists.set(id,list);
	});
	for(const list of lists.values()){
		list.sort((a,b)=>a.cue.start-b.cue.start);
		let end=0;for(const item of list)item.maxEnd=end=Math.max(end,item.cue.end);
	}
	const matches:{run:CaptionRun;cue:EditCaption;index:number}[]=[];
	for(const run of runs){
		const list=lists.get(key(run.asset,run.speechOnly));
		if(!list)continue;
		let lo=0,hi=list.length;
		while(lo<hi){const mid=(lo+hi)>>>1;if(list[mid].maxEnd<=run.start)lo=mid+1;else hi=mid;}
		for(let i=lo;i<list.length && list[i].cue.start<run.end;i++)
			if(list[i].cue.end>run.start)matches.push({run,cue:list[i].cue,index:list[i].index});
	}
	return matches;
}
export function timelineSrt(captions: EditCaption[], runs: CaptionRun[]) {
	const stamp = (ms:number) => {
		const pad = (n:number,width=2) => String(n).padStart(width,'0');
		return pad(Math.floor(ms/3600000))+':'+pad(Math.floor(ms/60000)%60)+':'+pad(Math.floor(ms/1000)%60)+','+pad(ms%1000,3);
	};
	const entries: {start:number; end:number; text:string}[] = [];
	const seen = new Set<string>();
	for (const {run,index,cue} of visibleCaptionEntries(captions,runs)) {
		if (!cue.text.trim()) continue;
		const start = Math.round(1000 * (run.at + Math.max(run.start,cue.start) - run.start));
		const end = Math.round(1000 * (run.at + Math.min(run.end,cue.end) - run.start));
		const key = index+':'+start+':'+end;
		if (start >= end || seen.has(key)) continue;
		seen.add(key);
		entries.push({start,end,text:(cue.speakerName ? cue.speakerName+': ' : '')+cue.text.trim()});
	}
	return entries.sort((a,b)=>a.start-b.start || a.end-b.end).map((e,i)=>
		(i+1)+'\n'+stamp(e.start)+' --> '+stamp(e.end)+'\n'+e.text+'\n\n').join('');
}

export function atPlayhead(clips: EditClip[], seconds: number) {
	const offsets = editOffsets(clips);
	if (isLayered(clips)) {
		let found = -1;
		for (let i = 0; i < clips.length; i++) {
			const clip = clips[i];
			if (!clip.audioOnly && (!clip.layout || clip.layout === 'full') && seconds >= offsets[i] && seconds < offsets[i] + clipLength(clip)
				&& (found < 0 || (clip.lane ?? 0) >= (clips[found].lane ?? 0))) found = i;
		}
		return found < 0 ? null : { index: found, sourceTime: clips[found].start + seconds - offsets[found] };
	}
	for (let i = 0; i < clips.length; i++) {
		const clip = clips[i];
		if (seconds < offsets[i] + clipLength(clip) || i === clips.length - 1) {
			return { index: i, sourceTime: Math.max(clip.start, Math.min(clip.end, clip.start + seconds - offsets[i])) };
		}
	}
	return null;
}

export function splitEdit(clips: EditClip[], seconds: number, selected = -1) {
	const offset = editOffsets(clips)[selected];
	const cursor = isLayered(clips) && selected >= 0 && seconds >= offset && seconds < offset + clipLength(clips[selected])
		? { index: selected, sourceTime: clips[selected].start + seconds - offset } : atPlayhead(clips, seconds);
	if (!cursor) return null;
	const { index, sourceTime } = cursor;
	const clip = clips[index];
	if (sourceTime - clip.start < .08 || clip.end - sourceTime < .08) return null;
	return [...clips.slice(0, index), { ...clip, end: sourceTime },
		{ ...clip, start: sourceTime, ...(clip.at != null ? { at: seconds } : {}) }, ...clips.slice(index + 1)];
}

export function splitSelected(clips: EditClip[], seconds: number, selected: number[]) {
	if (!selected.length) return splitEdit(clips, seconds);
	const offsets = editOffsets(clips);
	const targets = new Set(selected);
	let changed = false;
	const result = clips.flatMap((clip, index) => {
		const source = clip.start + seconds - offsets[index];
		if (!targets.has(index) || source - clip.start < .08 || clip.end - source < .08) return [clip];
		changed = true;
		return [{ ...clip, end: source }, { ...clip, start: source, ...(clip.at != null ? { at: seconds } : {}) }];
	});
	return changed ? result : null;
}

export function adjustCaption(cue: EditCaption, delta: number, min: number, max: number, edge: 'move' | 'start' | 'end') {
	const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
	if (edge === 'start') return { ...cue, start: clamp(cue.start + delta, min, cue.end - .08) };
	if (edge === 'end') return { ...cue, end: clamp(cue.end + delta, cue.start + .08, max) };
	const shift = clamp(delta, min - cue.start, max - cue.end);
	return { ...cue, start: cue.start + shift, end: cue.end + shift };
}

export function placeLayer(clips: EditClip[], item: EditClip, at: number, lane: number, audioOnly: boolean, from = -1) {
	const offsets = editOffsets(clips);
	const result = clips.map((clip, index) => ({ ...clip, at: offsets[index] }));
	let position = Math.max(0, at);
	const detach = from >= 0 && audioOnly && !item.audioOnly;
	if (detach) result[from] = { ...result[from], gain: 0, noAudio: true };
	else if (from >= 0) result.splice(from, 1);
	for (const other of result.filter(other => !!other.audioOnly === audioOnly && (other.lane ?? 0) === lane).sort((a, b) => a.at - b.at)) {
		if (position < other.at + clipLength(other) - .001 && position + clipLength(item) > other.at + .001) position = other.at + clipLength(other);
	}
	result.push({ ...item, at: position, lane, audioOnly });
	return result;
}

export function insertEdit(clips: EditClip[], seconds: number, item: EditClip) {
	const offsets = editOffsets(clips);
	const total = clips.length ? offsets.at(-1)! + clipLength(clips.at(-1)!) : 0;
	const split = splitEdit(clips, seconds);
	const boundaries = split ? editOffsets(split) : offsets;
	const index = [...boundaries, total].reduce((best, cut, i, all) =>
		Math.abs(cut - seconds) < Math.abs(all[best] - seconds) ? i : best, 0);
	const result = [...(split ?? clips)];
	result.splice(index, 0, item);
	return { clips: result, index };
}

export function editTime(seconds: number) {
	const ticks = Math.floor(Math.max(0, seconds) * 100 + 1e-8);
	return [Math.floor(ticks / 6000), Math.floor(ticks / 100) % 60, ticks % 100]
		.map(value => String(value).padStart(2, '0')).join(':');
}
