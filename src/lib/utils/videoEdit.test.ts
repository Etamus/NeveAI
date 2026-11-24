import { describe, expect, it } from 'vitest';
import { timelineSrt, applySpeakerCues, translatedCue, coverageAfterCueDeletion } from './videoEdit';

it('reopens only deleted transcript gaps, retaining other clips and the undo snapshot',()=>{
	const span=(start:number,end:number,asset='a')=>({asset,start,end});
	const coverage=[span(0,20),span(45,55),span(0,20,'b')];
	const cues=[span(1,3),span(6,8),span(12,14),span(49,50),span(2,3,'b')].map(c=>({...c,text:'cue'}));
	expect(coverageAfterCueDeletion(coverage,cues,new Set([1]))).toEqual([span(0,3),span(12,20),...coverage.slice(1)]);
	expect(coverageAfterCueDeletion(coverage,cues,new Set([0,1,2]))).toEqual(coverage.slice(1));
	expect(coverageAfterCueDeletion(coverage,cues,new Set([0,1,2,3,4]))).toEqual([]);
	expect(coverage[0]).toEqual(span(0,20));
});

it('fits translated text to the export limit without losing text, speaker, style or time',()=>{
	const cue={asset:'a',start:4,end:9,text:'Original',speakerName:'Ana',style:{size:20}};
	const text='Uma legenda traduzida. '.repeat(11).trim();
	const result=translatedCue(cue,text);
	expect(result.map(c=>c.text).join(' ')).toBe(text);
	expect(result[0].start).toBe(4);expect(result.at(-1)?.end).toBe(9);
	expect(result[0].end).toBe(result[1].start);
	expect(result.every(c=>c.text.length<=180 && c.speakerName==='Ana' && c.style===cue.style)).toBe(true);
	expect(cue.text).toBe('Original');
});

it('replaces obsolete speaker groups without modifying edited text, timestamps or unrelated captions',()=>{
	const previous=Array.from({length:295},(_,i)=>({asset:'a',start:i,end:i+1,text:'Edited '+i,speakerKey:'old:'+i,speakerName:i===0?'Ana':'Falante '+(i+1)}));
	const outside={...previous[0],asset:'b'};
	const cues=previous.map((c,i)=>({...c,existingIndex:i,speaker:1+i%3}));
	const next=applySpeakerCues([...previous,outside],cues,{1:[4,7]},'a','new',id=>'Falante '+id);
	expect(new Set(next.slice(0,-1).map(c=>c.speakerKey)).size).toBe(3);
	expect(next[3].speakerName).toBe('Ana');
	expect(next.at(-1)).toBe(outside);
	expect(next.slice(0,-1).map(c=>[c.text,c.start,c.end])).toEqual(previous.map(c=>[c.text,c.start,c.end]));
});
import { adjustCaption, atPlayhead, captionRuns, editDuration, editOffsets, editTime, insertEdit, motionLook, placeLayer, splitEdit, splitSelected, waveformPath, type EditClip } from './videoEdit';

const clips: EditClip[] = [
	{ asset: 'a', start: 2, end: 4, zoom: 1, gain: 0 },
	{ asset: 'b', start: 4, end: 8, zoom: 1.2, gain: -3 }
];

describe('Neve Edit timeline', () => {
	it('exports trimmed and repeated captions at timeline times, retaining speaker names', () => {
		const run={asset:'a',start:10,end:12,at:.025,lane:0,speechOnly:true};
		const cue={asset:'a',start:9,end:11.25,text:'Oi',speakerName:'Ana',speechOnly:true};
		expect(timelineSrt([cue,{...cue,start:20,end:23}], [run,run,{...run,at:60}])).toBe(
			'1\n00:00:00,025 --> 00:00:01,275\nAna: Oi\n\n2\n00:01:00,000 --> 00:01:01,250\nAna: Oi\n\n'
		);
	});
	it('preserves the primary positions, renders the upper visible track and detaches audio', () => {
		const stack = placeLayer(clips, { ...clips[0], asset: 'overlay' }, 1, 1, false);
		expect(editOffsets(stack)).toEqual([0, 2, 1]);
		expect(editDuration(stack)).toBe(6);
		expect(atPlayhead(stack, 2.5)?.index).toBe(2);
		expect(atPlayhead(stack, 3.5)?.index).toBe(1);
		const detached = placeLayer(stack, { ...stack[2], gain: .5 }, .5, 2, true, 2);
		expect(detached[2].gain).toBe(0);
		expect(detached[3]).toMatchObject({ at: .5, lane: 2, gain: .5, audioOnly: true });
		expect(atPlayhead(detached, .75)?.index).toBe(0);
	});
	it('seeks in the source of the next clip at a cut', () => {
		expect(editOffsets(clips)).toEqual([0, 2]);
		expect(atPlayhead(clips, 2)).toEqual({ index: 1, sourceTime: 4 });
		expect(atPlayhead(clips, 100)).toEqual({ index: 1, sourceTime: 8 });
		expect(atPlayhead([], 1)).toBeNull();
	});

	it('splits without changing the source, effects or duration', () => {
		const result = splitEdit(clips, 3);
		expect(result).toEqual([clips[0], { ...clips[1], end: 5 }, { ...clips[1], start: 5 }]);
		expect(clips).toHaveLength(2);
		expect(splitEdit(clips, 1.96)).toBeNull();
		expect(splitEdit(clips, 2)).toBeNull();
		expect(splitEdit(clips, 6)).toBeNull();
	});

	it('splits only the selected tracks at the shared playhead', () => {
		const layered = [...clips.map((clip, lane) => ({ ...clip, at: 0, lane })), { ...clips[0], at: 0, lane: 3 }];
		const result = splitSelected(layered, 1, [0, 1])!;
		expect(result).toHaveLength(5);
		expect(result.map(clip => clip.at)).toEqual([0, 1, 0, 1, 0]);
		expect(result.at(-1)).toBe(layered[2]);
		expect(editDuration(result)).toBe(editDuration(layered));
		expect(splitSelected(layered, 3, [0])).toBeNull();
	});

	it('moves and trims a caption without crossing the selected bounds', () => {
		const cue = { asset: 'a', start: 2, end: 4, text: 'caption' };
		expect(adjustCaption(cue, 9, 0, 6, 'move')).toEqual({ ...cue, start: 4, end: 6 });
		expect(adjustCaption(cue, -5, 1, 6, 'start')).toEqual({ ...cue, start: 1 });
		expect(adjustCaption(cue, 3, 0, 6, 'end')).toEqual({ ...cue, end: 6 });
	});

	it('updates the monitor preview over the duration of the effect', () => {
		const clip = { ...clips[0], motion: 'whip' } as const;
		expect(motionLook(clip, .05).filter).toContain('blur');
		expect(motionLook(clip, .1).transform).not.toBe(motionLook(clip, .35).transform);
		expect(motionLook({ ...clip, motion: 'flash' }, .2).light).toBe(0);
	});

	it('lets captions cross effects on a continuous source, but not jump cuts', () => {
		const shot: EditClip[] = [
			{...clips[0], start: 0, end: 3},
			{...clips[0], start: 3, end: 4, motion: 'flash'},
			{...clips[0], start: 7, end: 9}
		];
		expect(captionRuns(shot, editOffsets(shot))).toEqual([
			{asset: 'a', start: 0, end: 4, at: 0, lane: 0},
			{asset: 'a', start: 7, end: 9, at: 4, lane: 0}
		]);
	});

	it('displays media time in minutes, seconds and hundredths', () => {
		expect(editTime(94.854)).toBe('01:34:85');
		expect(editTime(-3)).toBe('00:00:00');
	});

	it('inserts media at the drop time without losing any source range', () => {
		const added = { asset: 'c', start: 0, end: 1, zoom: 1, gain: 1 };
		expect(insertEdit(clips, 3, added)).toEqual({
			index: 2, clips: [clips[0], { ...clips[1], end: 5 }, added, { ...clips[1], start: 5 }]
		});
		expect(insertEdit(clips, 2.03, added)).toEqual({ index: 1, clips: [clips[0], added, clips[1]] });
		expect(insertEdit(clips, 6, added)).toEqual({ index: 2, clips: [...clips, added] });
		expect(insertEdit([], 0, added)).toEqual({ index: 0, clips: [added] });
	});

	it('draws a continuous waveform for just the visible source range', () => {
		expect(waveformPath([], 0, 1, 1)).toBe('');
		const path = waveformPath([1, 0, .5, 1], 1, 3, 4);
		expect(path).toMatch(/^M 0 50 L 250\.0 50\.0 C/);
		expect(path).toContain('750.0 28.5');
		expect(path).toContain('750.0 71.5');
		expect(path).not.toContain('7.0');
	});
});
