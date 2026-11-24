<script lang="ts">
	import { getContext, onMount, onDestroy, tick, type Component } from 'svelte';
	import { DropdownMenu } from 'bits-ui';
	import { v4 as uuidv4 } from 'uuid';
	import { ChevronLeft, Languages, AudioLines, Eraser, Gauge, Mic, Users, Palette, ScanLine, Type, Captions, Download, Film, Folder, MonitorPlay, Pause, Play, Plus,
		Redo2, Scissors, Square, Trash2, Undo2, Upload, Volume2, VolumeX, StepBack, StepForward, ZoomIn, ZoomOut } from '@lucide/svelte';
	import { fly } from 'svelte/transition';
	import { toast } from 'svelte-sonner';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import MakerSubjectPicker from './MakerSubjectPicker.svelte';
	import StudioCaptionInput from './StudioCaptionInput.svelte';
	import FxFileExplorer from '$lib/components/icons/FxFileExplorer.svelte';
	import JanNumberControl from '$lib/components/chat/Settings/Advanced/JanNumberControl.svelte';
	import { modelGridWheel } from '$lib/utils/modelGridWheel';
	import { retryStudioPreview, studioPreview } from '$lib/utils/studioPreview';
	import { applySpeakerCues, coverTranscript, coverageAfterCueDeletion, translatedCue, visibleCaptionEntries } from '$lib/utils/videoEdit';
	import MobileModalTitle from '$lib/components/common/MobileModalTitle.svelte';
	import OrbitingSpheres from '$lib/components/common/OrbitingSpheres.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import { slowTooltipDelay } from '$lib/utils/tooltipTiming';
	import { downloadChatFile } from '$lib/utils/chatFileSave';
	import { timelineSrt } from '$lib/utils/videoEdit';
	import { mobile, user } from '$lib/stores';
	import type { I18nStore } from '$lib/i18n';
	import { adjustCaption, atPlayhead, captionRuns, clipLength, defaultCaptionStyle, editDuration, editOffsets, editTime, emptyTimeline, insertEdit, isLayered, motionLook, placeLayer, splitSelected, videoEditMediaUrl, waveformPath,
		type CaptionStyle, type EditAsset, type EditCaption, type EditClip, type EditTimeline } from '$lib/utils/videoEdit';

	export let show = false;
	export let hasComposerAttachment = false;
	export let onDiscard: () => void = () => {};
	let confirmDiscard = false, menuLabel = '', derivedIds: string[] = [];
	const exportIds = new Set<string>();
	function requestClose() {
		if (runningTool) { pause(); confirmDiscard=true; return; }
		if (exportMenuOpen) { exportMenuOpen=false; return; }
		if (picking) { picking=null; return; }
		if ((timeline.clips.length || timeline.captions.length) && projectSnapshot(timeline) !== cleanSnapshot) { pause(); confirmDiscard = true; }
		else discard();
	}
	function discard() {
		cancelOperation();
		show = false;
		onDiscard();
	}
	export let onRemoveAsset: (id: string) => void = () => {};
	export let onFileDragHandled: () => void = () => {};
	const i18n = getContext<I18nStore>('i18n');
	const api = '/api/v1/video-edit';
	const iconClass = 'inline-grid size-8 shrink-0 place-items-center rounded-md text-gray-600 hover:bg-gray-100 focus-visible:bg-gray-100 disabled:opacity-35 disabled:hover:bg-transparent dark:text-gray-300 dark:hover:bg-gray-800 dark:focus-visible:bg-gray-800 dark:disabled:hover:bg-transparent';
	const tabs = [{ id: 'tools',label:'Tools',icon:FxFileExplorer }, { id: 'media', label: 'Media', icon: Folder }, { id: 'captions', label: 'Captions', icon: Captions }] as const;
	const transportTooltip = { delay: [slowTooltipDelay, 0] as [number, number] };
	let assets: EditAsset[] = [];
	let timeline = emptyTimeline();
	$: showCaptionTab = captionIndices.length > 0 || speakers.length > 0;
	$: showToolsTab = timeline.clips.length > 0 || hasExportCaptions;
	$: visibleTabs = tabs.filter(tab => tab.id === 'tools' ? showToolsTab : tab.id !== 'captions' || showCaptionTab);
	$: if ((editingPanel === 'captions' && !showCaptionTab) || (editingPanel === 'tools' && !showToolsTab)) editingPanel = showToolsTab ? 'tools' : 'media';
	let past: EditTimeline[] = [];
	let future: EditTimeline[] = [];
	let waves: Record<string, number[]> = {};
	const requestedWaves = new Set<string>();
	const pendingWaves = new Map<string,AbortController>();
	let fileInput: HTMLInputElement;
	let monitor: HTMLVideoElement;
	let editingPanel: (typeof tabs)[number]['id'] = 'tools';
	const clipTools = { remaster: 'Enhance video', fps60: 'Interpolate to 60 FPS', vocals: 'Isolate voice', instrumental: 'Remove vocals',
		erase: 'Erase object' } as const;
	type ClipTool = keyof typeof clipTools;
	let installedTools: ClipTool[] = [];
	let toolCatalog: Promise<void> | undefined;
	function prepareTools() {
		return toolCatalog ??= call<ClipTool[]>('/clip-tools',{signal:AbortSignal.timeout(4000)})
			.then(keys => { installedTools = keys.filter(key => key in clipTools); })
			.catch(() => { toolCatalog = undefined; });
	}
	let picking: 'erase' | null = null;
	let selection = '', pickClip: EditClip | undefined;
	let pickPending=false;
	let runningTool: Assist | ClipTool | null = null;
	$: activeTool = picking ?? runningTool;
	// Seek the displayed source frame, not the next one (or EOF on the final tick).
	$: pickFps = activeAsset?.fps || 30;
	$: pickTime = picking && pickClip
		? Math.max(pickClip.start, Math.floor((Math.min(pickClip.end - .00001, pickClip.start + playhead - offsets[current])) * pickFps + .000001) / pickFps)
		: 0;
	function chooseTool(op: ClipTool) {
		if (op === 'erase') {
			if (picking) { picking=null; return; }
			pickClip = timeline.clips[current];
			if (!pickClip || pickClip.audioOnly || !withinToolLimits(op,pickClip)) return;
			pause();
			mobilePanel = 'monitor';
			selection = ''; picking = op;
		} else void processClip(op);
	}
	let mobilePanel: 'monitor' | 'inspector' = 'monitor';
	let selected = -1, current = 0, playhead = 0, zoom = 1;
	let marked: number[] = [], part: 'video'|'audio'|'caption'='video', cueIndex=-1;
	let group: string[] = [];
	let marquee: { x: number; y: number; endX: number; endY: number; base: string[] } | null = null;
	let skipTrackClick = false, fromMovable=false;
	let captionDrag: { index: number; x: number; min: number; max: number; edge: 'move' | 'start' | 'end'; cue: EditCaption } | null = null;
	let skipCaptionClick = false;
	let rulerEnd = 12;
	let previewSrc = '', pendingSeek = 0, currentCaption = '';
	let playing = false, animation = 0, disposed = false;
	let transportRevision=0;
	let notice = '', loading = '';
	
	let activeRequest: AbortController | undefined;
	let operationId: string | undefined, cancelling: Promise<unknown> | undefined;
	function cancelOperation() {
		if(operationId && !cancelling)
			cancelling=call('/operations/'+operationId,{method:'DELETE',keepalive:true}).catch(e=>console.warn('Studio cancellation:',e));
		activeRequest?.abort();
	}
	let exportMenuOpen=false;
	let exportPage:'mp3'|'mp4'|null=null;
	$: if(!exportMenuOpen) exportPage=null;
	async function switchExportPage(event:Event,page:'mp3'|'mp4'|null) {
		event.preventDefault();
		const previous=exportPage;
		exportPage=page;
		await tick();
		const original=(event as CustomEvent).detail?.originalEvent;
		const underPointer=original?.detail>0 ? document.elementFromPoint(original.clientX,original.clientY)?.closest<HTMLElement>('[role="menuitem"]') : null;
		(underPointer?.closest('[data-export-menu]') ? underPointer : document.querySelector<HTMLElement>(page?'[data-export-option]':`[data-export-format="${previous}"]`))?.focus();
	}
	type ExportJob = { id: string; format?: 'mp4'|'mp3'; status: 'queued' | 'exporting' | 'done' | 'failed' | 'cancelled'; progress: number; captions?: boolean; error?: string };
	let job: ExportJob | null = null;
	function projectSnapshot(edit: EditTimeline) {
		return JSON.stringify({...edit, audioMuted: !!edit.audioMuted, mutedAudioLanes: [...(edit.mutedAudioLanes ?? [])].sort(),
			audioLaneGains: Object.entries(edit.audioLaneGains ?? {}).filter(([,gain])=>gain !== 1).sort(),
			hiddenAssets: [...(edit.hiddenAssets ?? [])].sort()});
	}
	let cleanSnapshot = projectSnapshot(timeline), exportingSnapshot: EditTimeline | null = null;
	let poll: ReturnType<typeof setTimeout>;
	let lastShow = false;
	let drag: { asset: string } | { index: number; audio?: boolean } | null = null;
	let markedAssets: string[] = [];
	let draggedAsset = '';
	let dropLane: string | null = null;
	
	let layerClock = 0, layerOrigin = 0;
	const mixedAudio = new Map<number, HTMLAudioElement>();
	let dropMarker: number | null = null;
	let trackGrid: HTMLDivElement, gridWidth=0;
	let trackScroll: HTMLDivElement;
	let viewportWidth=0;
	// Keep 80 ms edits grabbable even at the end of a multi-hour timeline.
	$: maxTimelineZoom=Math.max(16, Math.min(16000000, rulerEnd*800)/Math.max(1,viewportWidth));
	let laneScroll: HTMLDivElement;
	let marqueeFrame = 0, pointerX = 0, pointerY = 0;
	let scrollOffset = 0, scrollLimit = 0, thumbFraction = 1, thumbGrab = 0;
	function rulerTicks(range:number,width:number,viewport:number,offset:number){
		if(!width||!viewport)return [];
		const target=range*100/width;
		const scale=10**Math.floor(Math.log10(target));
		const step=([1,2,5,10].find(n=>n*scale>=target)??10)*scale;
		const first=Math.max(0,Math.floor(offset/width*range/step));
		const last=Math.min(Math.floor(range/step),Math.ceil((offset+viewport)/width*range/step));
		return Array.from({length:Math.max(0,last-first+1)},(_,i)=>(first+i)*step);
	}
	$: ticks=rulerTicks(rulerEnd,gridWidth,viewportWidth,scrollOffset);
	let trim: { index: number; edge: 'start' | 'end'; x: number; width: number; range: number; value: number } | null = null;

	const mediaUrl = videoEditMediaUrl;
	function playbackUrl(id:string,audio=false) {
		return mediaUrl(id)+(assets.find(item=>item.id===id)?.browserReady===false ? '/preview.m3u8'+(audio?'?audio=true':'') : '');
	}
	const audioStreams=new WeakMap<HTMLMediaElement,ReturnType<typeof studioPreview>>();
	$: offsets = editOffsets(timeline.clips);
	$: cueRuns = [
		...(timeline.captions.some(c=>c.asset==='timeline') ? [{asset:'timeline',start:0,at:0,end:duration,lane:0,speechOnly:false}] : []),
		...(timeline.captions.some(c => !c.speechOnly) ? captionRuns(timeline.clips, offsets).map(r => ({ ...r, speechOnly: false })) : []),
		...(timeline.captions.some(c => c.speechOnly) ? captionRuns(timeline.clips, offsets, true).map(r => ({ ...r, speechOnly: true })) : [])
	];
	$: duration = timeline.captions.reduce((d,c)=>c.asset==='timeline'?Math.max(d,c.end):d, editDuration(timeline.clips));
	$: visibleCaptions=visibleCaptionEntries(timeline.captions,cueRuns);
	$: hasExportCaptions = visibleCaptions.some(({cue})=>cue.text.trim());
	$: exportKinds = [
		...(timeline.clips.some(c=>!c.audioOnly) ? ['mp4' as const] : []),
		...(timeline.clips.some(c=>!c.noAudio && assets.some(a=>a.id===c.asset && a.audio)) ? ['mp3' as const] : []),
		...(hasExportCaptions ? ['srt' as const] : [])
	];
	const exportItemClass='flex items-center justify-between gap-2 cursor-pointer rounded-md px-2 py-2 outline-none data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-800';
	const exportMenuClass='z-20 w-28 rounded-lg border border-gray-200 bg-white p-1 text-sm shadow-md dark:border-gray-800 dark:bg-gray-850';
	function downloadSrt(){
		return downloadChatFile('Neve-Studio.srt',()=>new Blob([timelineSrt(timeline.captions,cueRuns)],{type:'application/x-subrip;charset=utf-8'}));
	}
	$: layeredTimeline = isLayered(timeline.clips);
	$: videoLaneCount = Math.max(1, ...timeline.clips.filter(item => !item.audioOnly).map(item => 1 + (item.lane ?? 0)));
	$: audioLaneCount = Math.max(1, ...timeline.clips.map(item => 1 + (item.lane ?? 0)));
	$: videoLanes = Array.from({ length: videoLaneCount }, (_, index) => videoLaneCount - index - 1);
	$: audioLanes = Array.from({ length: audioLaneCount }, (_, index) => index);
	$: captionStyle = timeline.captionStyle ?? defaultCaptionStyle;
	$: if (duration * 1.12 > rulerEnd) rulerEnd = duration * 1.12;
	$: active = timeline.clips[current];
	$: overlays = timeline.clips.flatMap((clip, index) => {
		const t = playhead - offsets[index];
		return clip.layout && clip.layout !== 'full' && !clip.audioOnly && t >= 0 && t < clipLength(clip)
			? [{ clip, index, t }] : [];
	}).slice(-1);
	$: look = motionLook(active, playhead - (offsets[current] ?? 0));
	$: introOpacity = Math.max(0, Math.min(1, playhead / .19, (Math.min(2.7, duration) - playhead) / .26));
	$: activeAsset = assets.find(item => item.id === active?.asset);
	$: visibleAssets = assets.filter(asset => !derivedIds.includes(asset.id) && !timeline.hiddenAssets?.includes(asset.id));
	$: wavePaths = timeline.clips.map(item => item.noAudio ? '' : waveformPath(waves[item.asset] ?? [], item.start, item.end,
		assets.find(asset => asset.id === item.asset)?.duration ?? item.end));
	$: requestWaveforms(show ? timeline.clips : [], assets, waves);
	$: exportRunning = job?.status === 'queued' || job?.status === 'exporting';
	$: if (monitor) {
		monitor.muted = trackMuted(timeline, active?.lane ?? 0);
		monitor.volume = Math.min(1, audibleGain(timeline, active, false));
	}
	$: if (show !== lastShow) {
		lastShow = show;
		if (!show) { stopSample(); pause(); picking = null;  }
		else openPanel(hasComposerAttachment && showToolsTab ? 'tools' : 'media');
	}


	function storageKey() { return `neveai.video-edit.${$user?.id ?? 'local'}`; }
	function openPanel(tab: typeof editingPanel) {
		if(tab!=='captions') stopSample();
		if (tab!=='media') markedAssets=[];
		editingPanel = tab;
		mobilePanel = 'inspector';
	}
	function setCaptionStyle<K extends 'font'|'theme'|'size'>(key: K, value: CaptionStyle[K]) {
		if (!styleTargets.size || !targetStyles.some(style => style[key] !== value)) return;
		recordEdit();
		timeline = { ...timeline, captions: timeline.captions.map((cue,i) => styleTargets.has(i)
			? {...cue, style:{...cue.style,[key]:value}} : cue) };
	}
	let releasing = false;
	function releaseSession() {
		if (releasing || (!assets.length && !exportIds.size)) return;
		releasing = true;
		void call('/discard', { method: 'POST', keepalive:true, headers:{'Content-Type':'application/json'},
			body: JSON.stringify({ media: assets.map(a => a.id), exports:[...exportIds] }) }).catch(error => console.warn('Neve Studio cleanup:',error));
	}
	onMount(() => {
		try { localStorage.removeItem(storageKey()); } catch {}
		const leaving = (e: PageTransitionEvent) => { if (!e.persisted) releaseSession(); };
		window.addEventListener('pagehide',leaving);
		return () => window.removeEventListener('pagehide',leaving);
	});
	onDestroy(() => {
		disposed = true;
		stopSample();
		for (const controller of pendingWaves.values()) controller.abort();
		stopEdgeScroll();
		pause();
		clearTimeout(poll);
		cancelOperation();
		void Promise.all([tick(),cancelling]).then(releaseSession);
	});

	async function call<T>(route: string, options: RequestInit = {}): Promise<T> {
		const headers = new Headers(options.headers);
		if (localStorage.token) headers.set('Authorization', `Bearer ${localStorage.token}`);
		const response = await fetch(api + route, { ...options, headers });
		if (!response.ok) {
			const body = await response.json().catch(() => null);
			throw new Error(typeof body?.detail === 'string' ? body.detail : 'Neve Studio request failed.');
		}
		return await response.json();
	}
	function setError(cause: unknown) {
		const message = cause instanceof Error ? cause.message : 'Neve Studio request failed.';
		if (show) toast.error($i18n.t(message));
	}
	function requestWaveforms(clips: EditClip[], media: EditAsset[], cached: Record<string, number[]>) {
		const needed=new Set(clips.filter(clip=>!clip.noAudio).map(clip => clip.asset));
		for (const [id,controller] of pendingWaves) if(!needed.has(id)){
			controller.abort();pendingWaves.delete(id);requestedWaves.delete(id);
		}
		for (const id of needed) {
			if (id in cached || requestedWaves.has(id) || !media.find(asset => asset.id === id)?.audio) continue;
			requestedWaves.add(id);
			const controller=new AbortController();pendingWaves.set(id,controller);
			void call<{ samples: number[] }>(`/media/${id}/waveform`,{signal:controller.signal}).then(({ samples }) => {
				if (!disposed && !controller.signal.aborted && !(id in waves)) waves = { ...waves, [id]: samples };
			}).catch(() => {}).finally(()=>{if(pendingWaves.get(id)===controller) pendingWaves.delete(id);});
		}
	}
	function recordEdit() {
		past = [...past.slice(-39), timeline];
		future = [];
	}
	function push(next: EditTimeline, reset = false) {
		recordEdit();
		change(next, reset);
	}
	function trackMuted(edit: EditTimeline, lane: number) {
		return edit.mutedAudioLanes?.includes(lane) ?? !!edit.audioMuted;
	}
	function audibleGain(edit: EditTimeline, clip?: EditClip, applyMute = true) {
		const lane = clip?.lane ?? 0;
		if (clip?.noAudio) return 0;
		if (applyMute && trackMuted(edit, lane)) return 0;
		return (clip?.gain ?? 1) * (edit.audioLaneGains?.[lane] ?? 1);
	}
	function setTrackGain(lane:number,gain:number) {
		const muted = timeline.mutedAudioLanes ?? (timeline.audioMuted ? audioLanes : []);
		timeline = { ...timeline, audioLaneGains: { ...timeline.audioLaneGains, [lane]: gain },
			audioMuted: false, mutedAudioLanes: gain > 0 ? muted.filter(item => item !== lane) : muted };
	}
	function toggleAudioTrack(lane: number) {
		recordEdit();
		const muted = timeline.mutedAudioLanes ?? (timeline.audioMuted ? audioLanes : []);
		timeline = { ...timeline, audioMuted: false, mutedAudioLanes: muted.includes(lane) ? muted.filter(item => item !== lane) : [...muted, lane] };
	}
	function change(next: EditTimeline, reset = false) {
		if (next.hiddenAssets !== timeline.hiddenAssets) markedAssets=markedAssets.filter(id=>!next.hiddenAssets?.includes(id));
		if (show && timeline.clips.length && !next.clips.length) void tick().then(()=>trackGrid?.focus({preventScroll:true}));
		if (timeline.clips !== next.clips || timeline.captions !== next.captions) group=[];
		if (timeline.clips !== next.clips) marked = [];
		if (timeline.captions !== next.captions) cueIndex=-1;
		timeline = next;
		selected = next.clips.length ? Math.max(0, Math.min(selected, next.clips.length - 1)) : -1;
		seek(reset ? 0 : playhead);
	}
	function undo() {
		if (!past.length || loading) return;
		future = [timeline, ...future];
		const next = past[past.length - 1];
		past = past.slice(0, -1);
		change(next);
	}
	function redo() {
		if (!future.length || loading) return;
		past = [...past, timeline];
		const next = future[0];
		future = future.slice(1);
		change(next);
	}
	function addClip(asset: EditAsset, at: number, initial = false) {
		if (layeredTimeline) {
			placeOnLane({ asset: asset.id, start: 0, end: asset.duration, zoom: 1, gain: 1 }, at, 0, false);
			return;
		}
		const edit = insertEdit(timeline.clips, at, { asset: asset.id, start: 0, end: asset.duration, zoom: 1, gain: 1 });
		(initial ? change : push)({ ...timeline, clips: edit.clips });
		if (initial) cleanSnapshot = projectSnapshot(timeline);
		selected = edit.index;
		seek(editOffsets(edit.clips)[selected]);
		if ($mobile) mobilePanel = 'monitor';
	}
	export async function importFiles(files: FileList | File[], appendToTimeline = false): Promise<EditAsset[]> {
		if (loading || !files.length) return [];
		notice = ''; loading = 'Importing video...';
		activeRequest = new AbortController();
		const imported: EditAsset[] = [];
		const catalog = prepareTools();
		try {
			for (const file of Array.from(files)) {
				const asset = await call<EditAsset>('/media', { method:'POST', body:file, signal:activeRequest.signal,
					headers:{'Content-Type':'application/octet-stream','X-Studio-Filename':encodeURIComponent(file.name)} });
				if (disposed) { await call('/discard', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({media:[asset.id],exports:[]})}); break; }
				assets = [...assets, asset];
				imported.push(asset);
				if (appendToTimeline) addClip(asset,editDuration(timeline.clips),assets.length === 1 && !timeline.clips.length);
				else openPanel('media');
			}
		} catch (cause) { if (!disposed) { setError(cause); if (!show) throw cause; } }
		finally { loading = ''; activeRequest = undefined; if (fileInput) fileInput.value = ''; }
		await catalog;
		return imported;
	}
	function acceptFileDrag(event: DragEvent) {
		if (!event.dataTransfer?.types.includes('Files')) return;
		event.preventDefault();
		event.stopPropagation();
		onFileDragHandled();
		if (event.type === 'dragover') event.dataTransfer.dropEffect = loading ? 'none' : 'copy';
		else if (event.dataTransfer.files.length) void importFiles(event.dataTransfer.files);
	}
	function detachMedia(node: HTMLMediaElement) {
		const stream=audioStreams.get(node);
		if(stream){stream.destroy();audioStreams.delete(node);return;}
		node.pause(); node.removeAttribute('src'); node.load();
	}
	function pause() {
		transportRevision++;
		playing = false;
		cancelAnimationFrame(animation);
		monitor?.pause();
		for (const audio of mixedAudio.values()) { detachMedia(audio); }
		mixedAudio.clear();
	}
	function seek(seconds: number, keepPlaying = false) {
		const length = editDuration(timeline.clips);
		if (!keepPlaying) pause();
		playhead = Math.max(0, Math.min(Math.max(length, rulerEnd), seconds));
		const position = atPlayhead(timeline.clips, playhead);
		if (!position) { previewSrc=''; current=-1; picking=null; audioCaption(seconds); return; }
		current = position.index;
		const target = timeline.clips[current];
		if (picking && pickClip!==target) {
			pickClip=target; selection='';
		}
		pendingSeek = position.sourceTime;
		const url = playbackUrl(target.asset);
		if (isLayered(timeline.clips)) updateLayerCaption(seconds, target, pendingSeek);
		else updateCaption(target.asset, pendingSeek);
		if (url !== previewSrc) previewSrc = url;
		else if (monitor?.readyState) {
			monitor.currentTime = pendingSeek;
			monitor.volume = Math.min(1, audibleGain(timeline, target, false));
		}
	}
	function updateCaption(asset: string, time: number, audible = !!audibleGain(timeline, timeline.clips[current])) {
		const cue = timeline.captions.find(cue => cue.asset === 'timeline' ? playhead>=cue.start && playhead<cue.end : cue.asset === asset && time >= cue.start && time < cue.end);
		shownIndex = cue ? timeline.captions.indexOf(cue) : -1;
		const value=captionLabel(cue);
		if (currentCaption !== value) currentCaption = value;
	}
	function audioCaption(seconds:number) {
		const i=timeline.clips.findIndex((c,i)=>c.audioOnly && seconds>=offsets[i] && seconds<offsets[i]+clipLength(c));
		if(i>=0) updateCaption(timeline.clips[i].asset,timeline.clips[i].start+seconds-offsets[i]); else updateCaption('timeline',seconds);
	}
	function updateLayerCaption(seconds: number, main: EditClip, time: number) {
		let gain = 0;
		let asset = main.asset;
		timeline.clips.forEach((clip, index) => {
			const at = offsets[index];
			const volume = audibleGain(timeline, clip);
			const sourceTime = clip.start + seconds - at;
			if (clip.audioOnly && seconds >= at && seconds < at + clipLength(clip) && volume >= gain
				&& timeline.captions.some(cue => cue.asset === clip.asset && cue.start <= sourceTime && cue.end > sourceTime)) {
				asset = clip.asset; time = sourceTime; gain = volume;
			}
		});
		updateCaption(asset, time, gain > 0 || audibleGain(timeline, main) > 0);
	}
	function loadedMonitor() {
		if (!monitor || !timeline.clips[current]) return;
		monitor.currentTime = pendingSeek;
		monitor.volume = Math.min(1, audibleGain(timeline, timeline.clips[current], false));
		if (playing) startMonitor(monitor);
	}
	function startMonitor(node: HTMLVideoElement) {
		const revision=transportRevision, url=previewSrc;
		void node.play().catch(()=>{
			if(playing && revision===transportRevision && monitor===node && previewSrc===url) pause();
		});
	}
	function overlayVideo(node: HTMLVideoElement, state: { playing: boolean; time: number }) {
		const sync = () => {
			if (!node.readyState) return;
			if (!node.seeking && Math.abs(node.currentTime - state.time) > (state.playing ? .2 : .015)) node.currentTime = state.time;
			if (!state.playing) node.pause();
			else if (node.paused) void node.play().catch(() => {});
		};
		node.addEventListener('loadedmetadata', sync);
		sync();
		return { update(next: typeof state) { state = next; sync(); },
			destroy() { node.removeEventListener('loadedmetadata', sync); detachMedia(node); } };
	}
	function stepPlayback() {
		if (!playing) return;
		if (layeredTimeline) { stepLayered(); return; }
		const playingClip = timeline.clips[current];
		if (!playingClip || !monitor) { pause(); return; }
		if (monitor.readyState && !monitor.seeking && monitor.dataset.previewUrl===playbackUrl(playingClip.asset)) {
			const localTime = monitor.currentTime;
			const position = offsets[current] ?? 0;
			const next = timeline.clips[current + 1];
			const continuous = next?.asset === playingClip.asset && Math.abs(next.start - playingClip.end) < .001;
			if (localTime >= playingClip.end - (continuous ? 0 : .018) || monitor.ended) {
				if (current + 1 >= timeline.clips.length) { seek(duration); return; }
				if (continuous && !monitor.ended) {
					current += 1;
					playhead = position + localTime - playingClip.start;
					monitor.volume = Math.min(1, audibleGain(timeline, next, false));
					updateCaption(next.asset, localTime);
				} else seek(position + clipLength(playingClip) + .00001, true);
				if (monitor.paused && previewSrc === playbackUrl(playingClip.asset)) startMonitor(monitor);
			} else {
				playhead = position + Math.max(0, localTime - playingClip.start);
				updateCaption(playingClip.asset, localTime);
			}
		}
		animation = requestAnimationFrame(stepPlayback);
	}
	function stepLayered() {
		const time = layerOrigin + (performance.now() - layerClock) / 1000;
		if (time >= duration) { seek(duration); return; }
		const position = atPlayhead(timeline.clips, time);
		if ((position?.index ?? -1) !== current) {
			seek(time, true);
			if (monitor?.paused) void monitor.play().catch(() => {});
		} else {
			playhead = time;
			if (position) {
				const item = timeline.clips[position.index];
				if (monitor?.readyState && !monitor.seeking && Math.abs(monitor.currentTime - position.sourceTime) > .22)
					monitor.currentTime = position.sourceTime;
				updateLayerCaption(time, item, position.sourceTime);
			} else audioCaption(time);
		}
		const audible = new Set<number>();
		timeline.clips.forEach((item, index) => {
			const offset = offsets[index];
			const gain = audibleGain(timeline, item);
			if (index === current || !gain || time < offset || time >= offset + clipLength(item)
				|| !assets.find(asset => asset.id === item.asset)?.audio) return;
			audible.add(index);
			let audio = mixedAudio.get(index);
			if (!audio) {
				audio = new Audio();
				audioStreams.set(audio,studioPreview(audio,playbackUrl(item.asset,true)));
				const newAudio=audio;
				audio.addEventListener('loadedmetadata',()=>{if(playing && mixedAudio.get(index)===newAudio){
					newAudio.currentTime=item.start+playhead-offset; void newAudio.play().catch(()=>{});
				}},{once:true});
				audio.currentTime = item.start + time - offset;
				mixedAudio.set(index, audio);
				void audio.play().catch(() => {});
			}
			audio.volume = Math.min(1, gain);
			if (audio.readyState && !audio.seeking && Math.abs(audio.currentTime - (item.start + time - offset)) > .22)
				audio.currentTime = item.start + time - offset;
		});
		for (const [index, audio] of mixedAudio) if (!audible.has(index)) {
			detachMedia(audio); mixedAudio.delete(index);
		}
		animation = requestAnimationFrame(stepPlayback);
	}
	async function togglePlayback() {
		stopSample();
		if (playing) { pause(); return; }
		if (picking || !duration) return;
		if (playhead >= duration - .025) seek(0);
		const revision=++transportRevision;
		playing = true;
		await tick();
		if(revision!==transportRevision || !playing) return;
		if (!monitor && !layeredTimeline) { pause(); return; }
		if (layeredTimeline) { layerOrigin=playhead; layerClock=performance.now(); }
		if(monitor){
			pendingSeek=atPlayhead(timeline.clips,playhead)?.sourceTime ?? 0;
			if(!retryStudioPreview(monitor,pendingSeek)) startMonitor(monitor);
		}
		animation=requestAnimationFrame(stepPlayback);
	}
	function select(index: number, at = offsets[index] ?? 0) {
		selected = index;
		marked = [index];
		seek(at);
	}
	function selectClip(event: MouseEvent, index: number, kind:'audio'|'video'='video') {
		if (skipTrackClick) return;
		if(event.shiftKey){addSelection(kind,index);return;}
		group=[];
		if (part!==kind) { marked=[]; selected=-1; }
		part=kind; cueIndex=-1;
		if (event.ctrlKey || event.metaKey) {
			marked = marked.includes(index) ? marked.filter(item => item !== index) : [...marked, index];
			selected = marked.at(-1) ?? -1;
		} else select(index, event.detail ? timelineTime(event.clientX) : undefined);
	}
	function selectionKeys(){
		return group.length ? group : part==='caption' ? (cueIndex<0?[]:['caption:'+cueIndex]) : marked.map(i=>part+':'+i);
	}
	function addSelection(kind:typeof part,index:number){
		group=[...new Set([...selectionKeys(),kind+':'+index])];
		part=kind; cueIndex=kind==='caption'?index:-1;
		marked=[...new Set(group.filter(k=>!k.startsWith('caption:')).map(k=>Number(k.split(':')[1])))];
		selected=kind==='caption' ? marked.at(-1)??-1 : index;
	}
	function startMarquee(event: PointerEvent) {
		stopEdgeScroll();
		const target = event.target as HTMLElement;
		if (loading || event.button !== 0 || event.pointerType !== 'mouse' || target.closest('.edit-trim,.edit-level,.edit-ruler')) return;
		fromMovable=!!target.closest('[draggable=true],[data-key^="caption:"][aria-pressed=true]') && !event.shiftKey;
		trackGrid.focus({ preventScroll: true });
		skipTrackClick = false;
		const bounds = trackGrid.getBoundingClientRect();
		const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
		marquee = { x, y, endX: x, endY: y, base: event.ctrlKey || event.metaKey || event.shiftKey ? selectionKeys() : [] };
	}
	function moveMarquee(event: PointerEvent) {
		if (!marquee) return;
		const bounds = trackGrid.getBoundingClientRect();
		const endX = event.clientX - bounds.left, endY = event.clientY - bounds.top;
		if (!skipTrackClick && Math.hypot(endX - marquee.x, endY - marquee.y) < 4) return;
		if (fromMovable && !skipTrackClick && Math.abs(endX-marquee.x)>Math.abs(endY-marquee.y)*2) return;
		skipTrackClick = true;
		captionDrag=null;
		if (!trackGrid.hasPointerCapture(event.pointerId)) trackGrid.setPointerCapture(event.pointerId);
		marquee = { ...marquee, endX, endY };
		pointerX=event.clientX; pointerY=event.clientY;
		if (!marqueeFrame) marqueeFrame=requestAnimationFrame(scrollMarquee);
	}
	function stopEdgeScroll() {
		cancelAnimationFrame(marqueeFrame); marqueeFrame=0;
	}
	function scrollMarquee() {
		marqueeFrame=0;
		if (!marquee || !show || !skipTrackClick || !laneScroll || !trackScroll) return;
		const x=trackScroll.getBoundingClientRect(), y=laneScroll.getBoundingClientRect();
		const speed=(p:number,lo:number,hi:number) => p<lo+20 ? -Math.min(16,Math.ceil((lo+20-p)/2)) : p>hi-20 ? Math.min(16,Math.ceil((p-hi+20)/2)) : 0;
		const left=trackScroll.scrollLeft, top=laneScroll.scrollTop;
		trackScroll.scrollLeft+=speed(pointerX,x.left,x.left+trackScroll.clientWidth);
		laneScroll.scrollTop+=speed(pointerY,y.top,y.top+laneScroll.clientHeight);
		if (left===trackScroll.scrollLeft && top===laneScroll.scrollTop) return;
		const grid=trackGrid.getBoundingClientRect();
		marquee={...marquee,endX:Math.min(trackGrid.clientWidth,Math.max(0,pointerX-grid.left)),endY:Math.min(trackGrid.clientHeight,Math.max(0,pointerY-grid.top))};
		marqueeFrame=requestAnimationFrame(scrollMarquee);
	}
	function clearSelection() { group=[]; marked=[]; cueIndex=-1; }
	function clearOnTimelineBackground(event: PointerEvent) {
		const el=event.target;
		if (event.button === 0 && el instanceof Element && !el.closest('.edit-track-grid,button,input,[role="scrollbar"]')) clearSelection();
	}
	function finishMarquee() {
		stopEdgeScroll();
		if (marquee && skipTrackClick) {
			const box = trackGrid.getBoundingClientRect();
			const { x, y, endX, endY, base } = marquee;
			const hits = [...trackGrid.querySelectorAll<HTMLElement>('[data-key]')].filter(node => {
				const rect = node.getBoundingClientRect();
				return rect.left < box.left + Math.max(x, endX) && rect.right > box.left + Math.min(x, endX)
					&& rect.top < box.top + Math.max(y, endY) && rect.bottom > box.top + Math.min(y, endY);
			}).map(node => node.dataset.key!);
			group=[...new Set([...base,...hits])];
			part='video'; cueIndex=-1;
			marked=[...new Set(group.filter(k=>!k.startsWith('caption:')).map(k=>Number(k.split(':')[1])))];
			trackGrid.focus({preventScroll:true});
			selected = marked.at(-1) ?? -1;
		}
		marquee = null;
	}
	function split() {
		const clips = splitSelected(timeline.clips, playhead, marked);
		if (clips) push({ ...timeline, clips });
	}
	function removeSelected() {
		const keys=new Set(group.length ? group : part==='caption' ? (cueIndex<0?[]:['caption:'+cueIndex]) : marked.map(i=>part+':'+i));
		if (!keys.size) return;
		const removedCues=new Set([...keys].filter(k=>k.startsWith('caption:')).map(k=>Number(k.slice(8))));
		const clips=timeline.clips.flatMap((c,i):EditClip[]=>{
			const video=keys.has('video:'+i), audio=keys.has('audio:'+i), at=offsets[i];
			if (!audio && !video) return [{...c,at}];
			if (video) return !audio && !c.noAudio && assets.find(a=>a.id===c.asset)?.audio ? [{...c,at,audioOnly:true}] : [];
			return c.audioOnly ? [] : [{...c,at,noAudio:true,gain:0}];
		});
		push({...timeline,clips: [...keys].every(k=>k.startsWith('caption:')) ? timeline.clips:clips,
			transcriptCoverage:coverageAfterCueDeletion(timeline.transcriptCoverage??[],timeline.captions,removedCues),
			captions:timeline.captions.flatMap((cue,i)=>{
				if(keys.has('caption:'+i)) return [];
				if(cue.asset==='timeline' || clips.some(c=>c.asset===cue.asset && (cue.speechOnly || !c.audioOnly) && cue.start<c.end && cue.end>c.start)) return [cue];
				// Keep independent CC at its edited time when its final supporting track is deleted.
				return cueRuns.filter(r=>r.asset===cue.asset && r.speechOnly===!!cue.speechOnly && cue.start<r.end && cue.end>r.start)
					.map(r=>({...cue,asset:'timeline',speechOnly:false,start:r.at+Math.max(r.start,cue.start)-r.start,end:r.at+Math.min(r.end,cue.end)-r.start}));
			})}); marked=[]; group=[]; cueIndex=-1;
		void tick().then(()=>trackGrid?.focus({preventScroll:true}));
	}
		function reorder(from: number, to: number) {
		if (from === to || from < 0 || to < 0 || from >= timeline.clips.length || to >= timeline.clips.length) return;
		const clips = [...timeline.clips];
		clips.splice(to, 0, ...clips.splice(from, 1));
		push({ ...timeline, clips });
		select(to);
	}
	function setDrag(event: DragEvent, item: NonNullable<typeof drag>) {
		if (skipTrackClick && marquee) {event.preventDefault();return;}
		marquee=null;
		if (!event.dataTransfer || loading) return;
		drag = item;
		event.dataTransfer.effectAllowed = 'asset' in item ? 'copy' : 'move';
		event.dataTransfer.setData('application/neve-video-edit', JSON.stringify(item));
		if ('asset' in item) {
			draggedAsset=item.asset;
			const image = (event.currentTarget as HTMLElement).querySelector('img');
			if (image?.complete && image.naturalWidth) event.dataTransfer.setDragImage(image, image.width / 2, image.height / 2);
		}
	}
	function toggleMedia(id:string, event:MouseEvent) {
		if (event.detail && draggedAsset===id) return;
		markedAssets=markedAssets.includes(id) ? markedAssets.filter(key=>key!==id) : [...markedAssets,id];
	}
	function removeMarkedMedia() {
		if (loading || !markedAssets.length) return;
		const ids=new Set(markedAssets);
		push({...timeline,hiddenAssets:[...new Set([...(timeline.hiddenAssets??[]),...ids])],clips:timeline.clips.filter(c=>!ids.has(c.asset)),captions:timeline.captions.filter(c=>!ids.has(c.asset))});
		markedAssets=[];
	}
	export function removeStagedAsset(id: string) {
		if (show || loading || !assets.some(item => item.id === id)) return;
		change({...timeline, clips:timeline.clips.filter(c => c.asset !== id), captions:timeline.captions.filter(c => c.asset !== id)},true);
		assets = assets.filter(item => item.id !== id);
		past = []; future = []; cleanSnapshot = projectSnapshot(timeline);
		void call('/discard',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({media:[id],exports:[]})})
			.catch(error => console.warn('Neve Studio cleanup:',error));
	}
	function clearDrag() { drag = null; dropMarker = null; dropLane = null; }
	function timelineTime(x: number) {
		const bounds = trackGrid.getBoundingClientRect();
		return Math.max(0, Math.min(rulerEnd, (x - bounds.left) / Math.max(1, bounds.width) * rulerEnd));
	}
	function pointerTime(x: number) { return Math.min(duration, timelineTime(x)); }
	function moveSlot(at: number) {
		return [...offsets, duration].reduce((best, cut, i, cuts) =>
			Math.abs(at - cut) < Math.abs(at - cuts[best]) ? i : best, 0);
	}
	function dragOver(event: DragEvent, lane = 0, audio = false) {
		if (!drag || !event.dataTransfer || loading) return;
		if ('index' in drag && drag.audio && !audio) return;
		event.preventDefault();
		const viewport = trackScroll?.parentElement;
		const bounds = viewport?.getBoundingClientRect();
		if (viewport && bounds && viewport.scrollHeight > viewport.clientHeight) {
			if (event.clientY > bounds.bottom - 20) viewport.scrollTop += 10;
			else if (event.clientY < bounds.top + 20) viewport.scrollTop -= 10;
		}
		dropLane = `${audio ? 'a' : 'v'}${lane}`;
		const at = pointerTime(event.clientX);
		event.dataTransfer.dropEffect = 'asset' in drag ? 'copy' : 'move';
		dropMarker = layeredTimeline || audio || lane ? timelineTime(event.clientX)
			: 'asset' in drag ? at : ([...offsets, duration][moveSlot(at)] ?? 0);
	}
	function placeOnLane(item: EditClip, at: number, lane: number, audioOnly: boolean, from = -1) {
		const clips = placeLayer(timeline.clips, item, at, lane, audioOnly, from);
		if (editDuration(clips) > 18000 || clips.length > 8192) return;
		push({ ...timeline, clips });
		selected = clips.length - 1;
		seek(clips[selected].at ?? 0);
	}
	function dropClip(event: DragEvent, lane = 0, audio = false) {
		if (!drag || loading) return;
		event.preventDefault();
		const at = pointerTime(event.clientX);
		if (layeredTimeline || lane || audio) {
			const from = 'index' in drag ? drag.index : -1;
			const asset = 'asset' in drag ? assets.find(item => item.id === (drag as { asset: string }).asset) : undefined;
			const item = from >= 0 ? timeline.clips[from] : asset && { asset: asset.id, start: 0, end: asset.duration, zoom: 1, gain: 1 };
			if (item && (!audio || assets.find(asset => asset.id === item.asset)?.audio) && (audio || !item.audioOnly))
				placeOnLane(item, timelineTime(event.clientX), lane, audio, from);
			clearDrag();
			return;
		}
		if ('asset' in drag) {
			const { asset: id } = drag;
			const asset = assets.find(item => item.id === id);
			if (asset) addClip(asset, at);
		} else {
			const from = drag.index, slot = moveSlot(at);
			reorder(from, slot > from ? slot - 1 : slot);
		}
		clearDrag();
	}
	let level: {index:number; audio:boolean; y:number; height:number; start:number; edited:boolean} | null=null;
	function levelPointer(e:PointerEvent,index:number,audio:boolean) {
		const el=e.currentTarget as HTMLElement, clip=timeline.clips[index], lane=clip.lane ?? 0;
		if(e.type==='pointerdown'){
			if(e.button!==0 || loading) return;
			e.stopPropagation();e.preventDefault();el.setPointerCapture(e.pointerId);
			level={index,audio,y:e.clientY,height:el.parentElement!.clientHeight,start:audio?Math.min(1,clip.gain):clip.opacity??1,edited:false};
		} else if(level && el.hasPointerCapture(e.pointerId)){
			const delta=(level.y-e.clientY)/Math.max(1,level.height-6);
			if(delta!==0 || level.edited){
				if(!level.edited){recordEdit();level.edited=true;}
				const value=Math.round(100*Math.max(0,Math.min(1,level.start+delta)))/100;
				timeline={...timeline,clips:timeline.clips.map((c,i)=>i===index?{...c,[audio?'gain':'opacity']:value}:c)};
			}
			if(e.type==='pointerup')level=null;
		}
	}
	function startTrim(event: PointerEvent, index: number, edge: 'start' | 'end') {
		if (loading || event.button !== 0) return;
		event.preventDefault();
		event.stopPropagation();
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
		pause();
		const clip = timeline.clips[index];
		selected = index;
		seek((offsets[index] ?? 0)+(edge==='end'?clipLength(clip):0));
		trim = { index, edge, x: event.clientX, width: trackGrid.getBoundingClientRect().width, range: rulerEnd, value: clip[edge] };
	}
	function moveTrim(event: PointerEvent) {
		if (!trim) return;
		const target = timeline.clips[trim.index];
		const asset = assets.find(a => a.id === target.asset);
		if (!asset) return;
		const next = target[trim.edge] + (event.clientX - trim.x) / Math.max(1, trim.width) * trim.range;
		const value = trim.edge === 'start' ? Math.max(0, Math.min(target.end - .08, next)) : Math.max(target.start + .08, Math.min(asset.duration, next));
		trim = { ...trim, value };
	}
	function endTrim(event: PointerEvent) {
		if (!trim) return;
		moveTrim(event);
		const { index, edge, value } = trim;
		trim = null;
		if (Math.abs(timeline.clips[index][edge] - value) > .001) modify(edge, value);
	}
	function wheelTimeline(event: WheelEvent) {
		if (!trackScroll || !trackGrid || event.altKey || (!event.deltaX && !event.deltaY)) return;
		const scale = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? trackScroll.clientWidth : 1;
		const amount = (Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY) * scale;
		event.preventDefault();
		const bounds = trackScroll.getBoundingClientRect();
		if (event.ctrlKey || event.metaKey) changeZoom(zoom * Math.exp(-amount * .0025), event.clientX - bounds.left);
		else trackScroll.scrollLeft += amount;
	}
	function changeZoom(value: number, anchor?: number) {
		if (!trackScroll || !trackGrid) return;
		const cursor = playhead / rulerEnd * trackGrid.clientWidth - trackScroll.scrollLeft;
		const x = Math.max(0, Math.min(trackScroll.clientWidth, anchor ?? cursor));
		const ratio = (trackScroll.scrollLeft + x) / trackGrid.clientWidth;
		zoom = Math.min(maxTimelineZoom, Math.max(1, value));
		void tick().then(() => { if (trackScroll && trackGrid) trackScroll.scrollLeft = ratio * trackGrid.clientWidth - x; });
	}
	function measureTimelineScroll() {
		if (!trackScroll) return;
		const { clientWidth, scrollWidth, scrollLeft } = trackScroll;
		scrollOffset = scrollLeft;
		scrollLimit = Math.max(0, scrollWidth - clientWidth);
		thumbFraction = scrollLimit ? Math.max(.09, clientWidth / scrollWidth) : 1;
	}
	function observeTimelineScroll(node: HTMLElement) {
		const observer = new ResizeObserver(measureTimelineScroll);
		observer.observe(node);
		if (node.firstElementChild) observer.observe(node.firstElementChild);
		return { destroy: () => observer.disconnect() };
	}
	function dragTimelineScroll(event: PointerEvent) {
		const rail = event.currentTarget as HTMLElement;
		if (!scrollLimit || (event.type !== 'pointerdown' && !rail.hasPointerCapture(event.pointerId))) return;
		const bounds = rail.getBoundingClientRect();
		const thumbSize = bounds.width * thumbFraction;
		const offset = event.clientX - bounds.left;
		if (event.type === 'pointerdown') {
			const left = scrollOffset / scrollLimit * (bounds.width - thumbSize);
			thumbGrab = offset >= left && offset <= left + thumbSize ? offset - left : thumbSize / 2;
			rail.setPointerCapture(event.pointerId);
		}
		trackScroll.scrollLeft = (offset - thumbGrab) / (bounds.width - thumbSize) * scrollLimit;
	}
	function scrollTimelineKey(event: KeyboardEvent) {
		const offset = { ArrowLeft: -48, ArrowRight: 48, Home: -scrollLimit, End: scrollLimit }[event.key];
		if (offset === undefined) return;
		event.preventDefault();
		trackScroll.scrollLeft += offset;
	}
	function modify(field: 'start' | 'end', value: number) {
		const index = selected;
		const clip = timeline.clips[index];
		if (!clip || !Number.isFinite(value) || loading) return;
		const source = assets.find(asset => asset.id === clip.asset);
		if (!source) return;
		const result: EditClip = { ...clip, [field]: value };
		if (field === 'start') result.start = Math.max(0, Math.min(clip.end - .08, value));
		if (field === 'end') result.end = Math.min(source.duration, Math.max(clip.start + .08, value));
		push({ ...timeline, clips: timeline.clips.map((item, i) => i === index ? result : item) });
	}
	function scrub(event: PointerEvent) {
		const target = event.currentTarget as HTMLElement;
		if (event.type === 'pointerdown') target.setPointerCapture(event.pointerId);
		if (event.type !== 'pointerdown' && !target.hasPointerCapture(event.pointerId)) return;
		const box = target.getBoundingClientRect();
		seek((event.clientX - box.left) / Math.max(1, box.width) * rulerEnd);
	}
	function keydown(event: KeyboardEvent) {
		const target = event.target as Element | null;
		if (!show || event.defaultPrevented || !target?.closest('.edit-shell')
			|| target.closest('input,textarea,select,[contenteditable="true"],[role="menu"]')) return;
		if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
			event.preventDefault(); if (event.shiftKey) redo(); else undo();
		} else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
			event.preventDefault(); if (!loading && !event.repeat) split();
		} else if (event.code === 'Space' && !target.closest('button,a')) {
			event.preventDefault(); void togglePlayback();
		} else if (event.key === 'Delete' && !loading && target.closest('.edit-sequence')) {
			event.preventDefault(); removeSelected();
		}
	}
	async function processClip(operation: ClipTool) {
		const index = picking ? timeline.clips.indexOf(pickClip!) : selected, clip = timeline.clips[index], before = timeline;
		const start = clip?.start, stop = clip?.end, anchor = picking ? pickTime : null;
		if (!clip || start == null || stop == null || loading || !withinToolLimits(operation,clip)) return;
		picking = null;
		runningTool = operation;
		pause(); mobilePanel = 'monitor'; notice = ''; loading = 'Processing clip...';
		activeRequest = new AbortController();
		operationId=uuidv4();
		try {
			const asset = await call<EditAsset>(`/media/${clip.asset}/process`, { method: 'POST',
				headers: { 'Content-Type': 'application/json' }, signal: activeRequest.signal,
				body: JSON.stringify({ requestId:operationId, start, end: stop, anchor, operation, selection: operation === 'erase' ? selection.split(',')[1] : null }) });
			if (disposed || activeRequest.signal.aborted) return;
			assets = [...assets, asset];
			derivedIds = [...derivedIds, asset.id];
			if (timeline !== before) return;
			const end = Math.min(asset.duration, stop-start);
			const cues = timeline.captions.filter(c => c.asset === clip.asset && c.end > start && c.start < stop)
				.map(c => ({ ...c, asset: asset.id, start: Math.max(0, c.start - start),
					voiceSample:c.voiceSample && c.voiceSample[0]>=start && c.voiceSample[1]<=start+end
						? [c.voiceSample[0]-start,c.voiceSample[1]-start] as [number,number] : undefined,
					end: Math.min(end, c.end - start) })).filter(c => c.end > c.start);
			push({ ...timeline, clips: timeline.clips.map((c,i) => i === index ? {...clip,asset:asset.id,start:0,end} : c),
				captions: [...timeline.captions, ...cues] });
		} catch (cause) { if (!disposed && !activeRequest?.signal.aborted) setError(cause); }
		finally { await cancelling; cancelling=undefined; operationId=undefined; loading = ''; activeRequest = undefined; runningTool = null; }
	}
	const assistNames = { captions: 'Transcribe speech', speakers:'Identify speakers', translate:'Translate captions', speech: 'Keep speech', color: 'Balance color' } as const;
	let translateOpen = false, sourceLanguage = 'en', targetLanguage = 'pt';
	const languageNames = { en:'English', pt:'Portuguese', es:'Spanish', fr:'French', it:'Italian', de:'German', ja:'Japanese' };
	$: translationChoices = Object.entries(languageNames).map(([value,name])=>({value,label:$i18n.t(name)}));
	async function translateCaptions() {
		const before=timeline;
		const indices=[...new Set(visibleCaptions.filter(entry=>entry.cue.text.trim()).map(entry=>entry.index))];
		if (!indices.length || loading || sourceLanguage===targetLanguage) return;
		pause(); runningTool='translate'; loading='Translating captions...';
		activeRequest=new AbortController(); operationId=uuidv4();
		try {
			const result=await call<{texts:string[]}>('/translate',{method:'POST',headers:{'Content-Type':'application/json'},signal:activeRequest.signal,
				body:JSON.stringify({requestId:operationId, source:sourceLanguage,target:targetLanguage,texts:indices.map(i=>before.captions[i].text)})});
			if (disposed || activeRequest.signal.aborted || timeline!==before) return;
			if(result.texts.length!==indices.length || result.texts.some(t=>typeof t!=='string' || !t.trim())) throw Error('Could not translate captions.');
			const byIndex=new Map(indices.map((i,n)=>[i,result.texts[n]]));
			const captions=before.captions.flatMap((cue,i)=>byIndex.has(i)?translatedCue(cue,byIndex.get(i)!):[cue]);
			if(captions.length>32768) throw Error('Too many captions. Select a shorter clip.');
			push({...before,captions});
		} catch(error) { if(!disposed && !activeRequest?.signal.aborted) setError(error); }
		finally {await cancelling; cancelling=undefined; operationId=undefined; loading=''; activeRequest=undefined; runningTool=null;}
	}
	type Assist = keyof typeof assistNames;
	function withinToolLimits(operation: Assist | ClipTool, clip: EditClip) {
		const duration=clip.end-clip.start;
		const asset=assets.find(a=>a.id===clip.asset);
		let reason='';
		const [limit,message]=operation in assistNames ? [18000,'Select a clip of up to 5 hours.'] as const
			: operation==='erase' ? [1800,'Select a clip of up to 30 minutes.'] as const
			: operation==='fps60' || operation==='remaster' ? [300,'Select a clip of up to 5 minutes.'] as const : [3600,'Select a clip of up to 1 hour.'] as const;
		if (duration<.08 || duration>limit) reason=message;
		else if (operation==='fps60' && asset) {
			if (asset.width*asset.height>1920*1080) reason='Frame interpolation supports clips up to 1080p.';
			else if (asset.fps>=59.5) reason='This clip is already at 60 FPS or higher.';
		}
		if (reason) setError(new Error(reason));
		return !reason;
	}
	const toolIcons = { translate:Languages, speakers:Users, remaster:ScanLine, fps60: Gauge, vocals: Mic, instrumental: AudioLines, erase: Eraser, captions: Captions, words: Type, speech: Scissors, color: Palette };
	const assistKeys = Object.keys(assistNames) as Assist[];
	$: toolClip = marked.length <= 1 && !(part==='caption' && cueIndex>=0) && !group.some(k=>k.startsWith('caption:'))
		? timeline.clips[selected] : undefined;
	$: videoToolsAllowed = !!toolClip && !toolClip.audioOnly && (group.length
		? group.includes('video:'+selected) : !(part==='audio' && marked.length));
	$: audioToolsAllowed = !!toolClip && !toolClip.noAudio && !!assets.find(asset=>asset.id===toolClip.asset)?.audio;
	async function assist(operation: Assist) {
		const index = selected, clip = timeline.clips[index], before = timeline;
		if (!clip || loading || picking || !withinToolLimits(operation,clip)) return;
		runningTool = operation;
		pause(); mobilePanel = 'monitor'; loading = 'Analyzing video...';
		activeRequest = new AbortController();
		operationId=uuidv4();
		try {
			const data = await call<{ clips?: EditClip[]; cues?: (EditCaption & {speaker?:number;existingIndex?:number})[]; samples?:Record<number,[number,number]>; grade?: EditClip['grade'] }>('/assist', {
				method:'POST', headers:{ 'Content-Type':'application/json' }, signal:activeRequest.signal,
				body:JSON.stringify({ ...timeline, requestId:operationId, index, operation })
			});
			if (disposed || activeRequest.signal.aborted || timeline !== before) return;
			if (data.clips) push({ ...timeline, clips: data.clips.map(c => ({ ...c, at: c.at ?? undefined })) }, true);
			else if (data.grade) push({ ...timeline, clips: timeline.clips.map((c,i) => i === index ? {...c, grade:data.grade} : c) });
			else if (data.cues) {
				const captions=operation==='speakers'
					? applySpeakerCues(timeline.captions,data.cues,data.samples??{},clip.asset,uuidv4(),id=>$i18n.t('Speaker')+' '+id)
					: [...timeline.captions,...data.cues.filter(c=>c.existingIndex===undefined).map(c=>({...c,asset:clip.asset,speechOnly:true}))];
				const previous=timeline.transcriptCoverage??[];
				if(!previous.some(s=>s.asset===clip.asset && s.start<=clip.start && s.end>=clip.end) ||
					captions.length!==timeline.captions.length || captions.some((c,i)=>c!==timeline.captions[i]))
					push({...timeline,captions,transcriptCoverage:coverTranscript(previous,clip)});
				openPanel('captions');
			}
		} catch (err) { if (!disposed && !activeRequest?.signal.aborted) setError(err); }
		finally { await cancelling; cancelling=undefined; operationId=undefined; loading = ''; activeRequest = undefined; runningTool = null; }
	}
	let snapX: CaptionStyle['horizontal'];
	let snap: CaptionStyle['position'], dragBounds: DOMRect | null = null;
	function dragSubtitle(e: PointerEvent) {
		const el = e.currentTarget as HTMLElement;
		if (e.type === 'pointerdown') {
			pause(); dragBounds = el.parentElement!.getBoundingClientRect(); el.setPointerCapture(e.pointerId);
			snapX=shownHorizontal; snap=shownPosition; return;
		}
		if (!dragBounds || !el.hasPointerCapture(e.pointerId)) return;
		const ratio = (e.clientY - dragBounds.top) / dragBounds.height;
		snap = ratio < (snap === 'top' ? .36 : .29) ? 'top' : ratio > (snap === 'bottom' ? .64 : .71) ? 'bottom' : 'center';
		const x=(e.clientX-dragBounds.left)/dragBounds.width;
		snapX=x < (snapX==='left'?.36:.29) ? 'left' : x > (snapX==='right'?.64:.71) ? 'right' : 'center';
		if (e.type === 'pointerup') { if (snap!==shownPosition || snapX!==shownHorizontal) positionCaptions(snap,snapX); snapX=undefined; snap = undefined; dragBounds = null; }
	}
	let shownIndex=-1;
	$: previewStyle = {...captionStyle, ...timeline.captions[shownIndex]?.style};
	$: shownHorizontal=timeline.captions[shownIndex]?.horizontal ?? captionStyle.horizontal ?? 'center';
	$: shownPosition=timeline.captions[shownIndex]?.position ?? captionStyle.position ?? 'bottom';
	function positionCaptions(position:CaptionStyle['position'], horizontal:CaptionStyle['horizontal']) {
		if (shownIndex < 0) return;
		const included=new Set(group); const moveGroup=included.has('caption:'+shownIndex);
		recordEdit(); timeline={...timeline,captions:timeline.captions.map((c,i)=>i===shownIndex || (moveGroup && included.has('caption:'+i)) ? {...c,position,horizontal}:c)};
	}
	async function checkExport(id: string) {
		if (disposed) return;
		try {
			const result = await call<ExportJob>(`/exports/${id}`);
			if (disposed || job?.id !== id) return;
			job = result;
			if (job.status === 'done') {
				const format = job.format ?? 'mp4';
				const link = document.createElement('a'); link.href = `${api}/exports/${id}/${format}`; link.download = `Neve-Studio.${format}`;
				document.body.append(link); link.click(); link.remove(); if (exportingSnapshot) cleanSnapshot = projectSnapshot(exportingSnapshot);
			}
			if (job.status === 'queued' || job.status === 'exporting') poll = setTimeout(() => checkExport(id), 550);
			if (job.status === 'failed') setError(new Error(job.error ?? 'Could not render this video.'));
		} catch (cause) { if (!disposed) { setError(cause); job = null; } }
	}
	async function exportMedia(format:'mp4'|'mp3', option:number|'original') {
		if (!duration || exportRunning || loading) return;
		loading = 'Preparing export...';
		try {
			exportingSnapshot = timeline;
			const edit = { ...timeline, format, ...(format==='mp4'?{height:option}:{bitrate:option}), clips: timeline.clips.map(clip => ({ ...clip, gain: audibleGain(timeline, clip) })) };
			job = await call<ExportJob>('/exports', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(edit) });
			exportIds.add(job.id);
			if (disposed) { await call("/discard", { method: "POST", headers: { "Content-Type":"application/json" }, body: JSON.stringify({ media: [], exports:[job.id] }) }); return; }
			void checkExport(job.id);
		} catch (cause) { setError(cause); }
		finally { loading = ''; }
	}
	async function cancelExport() {
		if (!job || !exportRunning) return;
		clearTimeout(poll);
		try { job = await call<ExportJob>(`/exports/${job.id}`, { method: 'DELETE' }); }
		catch (cause) { setError(cause); }
	}
	function addCaption() {
		const location = atPlayhead(timeline.clips, playhead);
		if (!location) return;
		const target = timeline.clips[location.index];
		const start = Math.min(location.sourceTime, target.end - .08);
		push({ ...timeline, captions: [...timeline.captions,
			{ asset: target.asset, start, end: Math.min(target.end, start + 2), text: $i18n.t('Caption') }] });
		part='caption'; cueIndex=timeline.captions.length-1; group=[]; marked=[];
		openPanel('captions');
	}
	$: captionIndices = group.length ? group.filter(k=>k.startsWith('caption:')).map(k=>Number(k.slice(8)))
		: part==='caption' && timeline.captions[cueIndex] ? [cueIndex] : [];
	$: selectedCues = captionIndices.length === 1 ? [{cue:timeline.captions[captionIndices[0]],index:captionIndices[0]}] : [];
	$: styleTargets = new Set(captionIndices.length===1 || (captionIndices.length>1 && timeline.captions.every((cue,i)=>
		captionIndices.includes(i) || !cueRuns.some(run=>run.asset===cue.asset && run.speechOnly===!!cue.speechOnly && cue.start<run.end && cue.end>run.start)))
		? captionIndices : []);
	$: targetStyles = Array.from(styleTargets, i=>({...captionStyle,...timeline.captions[i]?.style}));
	$: chosenFont = targetStyles.every(s=>s.font===targetStyles[0]?.font) ? targetStyles[0]?.font : '';
	$: chosenTheme = targetStyles.every(s=>s.theme===targetStyles[0]?.theme) ? targetStyles[0]?.theme : '';
	$: speakers=[...new Map(timeline.captions.filter(c=>c.speakerKey).map(c=>[c.speakerKey!,c.speakerName!])).entries()];
	let sampleAudio:HTMLAudioElement|undefined, sampleKey='', sampleURL='', sampleRequest:AbortController|undefined;
	function stopSample(){
		sampleRequest?.abort();sampleRequest=undefined;
		if(sampleAudio){sampleAudio.onended=null;sampleAudio.onerror=null;sampleAudio.pause();sampleAudio.removeAttribute('src');sampleAudio.load();sampleAudio=undefined;}
		if(sampleURL)URL.revokeObjectURL(sampleURL);
		sampleURL='';sampleKey='';
	}
	async function playSample(key:string){
		const same=key===sampleKey;stopSample();if(same)return;
		const cue=timeline.captions.find(c=>c.speakerKey===key && c.voiceSample)??timeline.captions.find(c=>c.speakerKey===key);
		if(!cue)return;
		pause();sampleKey=key;
		const request=new AbortController();sampleRequest=request;
		const [start,end]=cue.voiceSample??[cue.start,Math.min(cue.end,cue.start+3)];
		try{
			const r=await fetch(mediaUrl(cue.asset)+'/speaker-sample?'+new URLSearchParams({start:String(start),end:String(end)}),
				{signal:request.signal,headers:localStorage.token?{Authorization:'Bearer '+localStorage.token}:{}});
			if(!r.ok)throw Error('Could not play speaker sample.');
			const blob=await r.blob();if(request.signal.aborted)return;
			sampleURL=URL.createObjectURL(blob);sampleAudio=new Audio(sampleURL);
			sampleAudio.onended=stopSample;sampleAudio.onerror=()=>{stopSample();setError(Error('Could not play speaker sample.'));};
			await sampleAudio.play();
		}catch(e){if(!request.signal.aborted){stopSample();setError(e);}}
	}
	function captionLabel(c?: EditCaption) { return !c?'':c.speakerName?c.speakerName+': '+c.text:c.text; }
	const speakerSegments=new Intl.Segmenter(undefined,{granularity:'grapheme'});
	function speakerField(input:HTMLInputElement, name:string) {
		const ctx=document.createElement('canvas').getContext('2d');
		let composing=false;
		function fit() {
			if(!ctx || !input.clientWidth) return;
			const style=getComputedStyle(input);
			ctx.font=style.fontWeight+' 14px '+style.fontFamily;
			const room=input.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight)-3;
			const width=ctx.measureText(input.value).width;
			let size=width>room && room>0 ? Math.floor(140*room/width)/10 : 14;
			// Hinting rounds individual glyphs at the new size. Measure the actual
			// input as well so the caret and right padding still fit beside the sample button.
			input.style.fontSize=size<14?size+'px':'';
			while(size>5 && input.scrollWidth>input.clientWidth){
				size-=.3;
				input.style.fontSize=size+'px';
			}
			input.scrollLeft=0;
		}
		function limit() {
			if(composing) return;
			const chars=Array.from(speakerSegments.segment(input.value));
			const caret=input.selectionEnd??input.value.length;
			let end=chars.findIndex(s=>s.index>=caret);
			if(end<0) end=chars.length;
			// Reject surplus characters at the insertion, preserving the suffix on paste.
			const text=input.value;
			let count=Array.from(text).length,first=end;
			while(first>0 && (chars.length-(end-first)>22 || count>80))
				count-=Array.from(chars[--first].segment).length;
			if(first<end) {
				const left=chars[first].index, right=chars[end]?.index??text.length;
				input.value=text.slice(0,left)+text.slice(right);
				input.setSelectionRange(left,left);
			}
			fit();
		}
		function start(){composing=true;}
		function finish(){composing=false;limit();}
		const observer=new ResizeObserver(fit);
		observer.observe(input);
		input.addEventListener('input',limit);
		input.addEventListener('compositionstart',start);
		input.addEventListener('compositionend',finish);
		fit();
		return {update(value:string){if(value!==name){name=value;void tick().then(fit);}},destroy(){
			observer.disconnect();input.removeEventListener('input',limit);
			input.removeEventListener('compositionstart',start);input.removeEventListener('compositionend',finish);
		}};
	}
	function renameSpeaker(key:string,input:HTMLInputElement) {
		const current=speakers.find(([k])=>k===key)?.[1] ?? '';
		const value=input.value.trim(); input.value=value;
		if (value!==current) updateCues(timeline.captions.map(c=>c.speakerKey===key?{...c,speakerName:value}:c));
	}
	function updateCues(captions: EditCaption[]) {
		recordEdit();
		timeline = {...timeline,captions};
		seek(playhead);
	}
	function editCaption(index: number, text: string) {
		if (text.trim() && text.trim() !== timeline.captions[index].text) updateCues(timeline.captions.map((cue, i) => i === index ? { ...cue, text: text.trim() } : cue));
	}
	function jumpToCaption(index: number) {
		const cue = timeline.captions[index];
		const segment = timeline.clips.findIndex(item => item.asset === cue.asset && item.end > cue.start && item.start < cue.end);
		if (segment >= 0) { selected = segment; seek(offsets[segment] + Math.max(0, cue.start - timeline.clips[segment].start)); }
	}
	function startCaption(event: PointerEvent, index: number, run: { start: number; end: number; at:number }, edge: 'move' | 'start' | 'end') {
		if (loading || event.button !== 0) return;
		skipCaptionClick=false;
		const mouseMove=edge==='move' && event.pointerType==='mouse';
		if(mouseMove && (event.shiftKey || !(cueIndex===index || group.includes('caption:'+index)))) return;
		if(!mouseMove) event.stopPropagation();
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
		const cue = timeline.captions[index];
		if(edge!=='move')seek(run.at-run.start+(edge==='end'?Math.min(run.end,cue.end):Math.max(run.start,cue.start)));
		captionDrag = { index, x: event.clientX, edge, cue, min: Math.min(run.start, cue.start), max: Math.max(run.end, cue.end) };
	}
	function moveCaption(event: PointerEvent) {
		if (marquee && !skipCaptionClick && Math.abs(event.clientY-trackGrid.getBoundingClientRect().top-marquee.y)*2>Math.abs(event.clientX-trackGrid.getBoundingClientRect().left-marquee.x)) return;
		if (!captionDrag || Math.abs(event.clientX - captionDrag.x) < 3 && !skipCaptionClick) return;
		pause();
		skipCaptionClick = true;
		const { index, x, min, max, edge } = captionDrag;
		const cue = timeline.captions[index];
		// Captions are kept in source time so they follow trims and moves of the video.
		const adjusted = adjustCaption(cue, (event.clientX - x) * rulerEnd / trackGrid.clientWidth, min, max, edge);
		captionDrag = { ...captionDrag, cue: adjusted };
	}
	function finishCaption(event: PointerEvent) {
		moveCaption(event);
		if (captionDrag && skipCaptionClick) {
			const { index, cue } = captionDrag;
			push({ ...timeline, captions: timeline.captions.map((item, i) => i === index ? cue : item) });
		}
		captionDrag = null;
	}
</script>

<svelte:window on:keydown={keydown} on:keydown|capture={event=>{
	if(show && exportMenuOpen && event.key==='Escape'){
		event.preventDefault();
		event.stopImmediatePropagation();
		exportMenuOpen=false;
		document.querySelector<HTMLButtonElement>('[data-studio-export]')?.focus();
	}
}} />

{#snippet tool(Icon: Component<{ size?: number; strokeWidth?: number; fill?: string }>, label: string, action: () => void, disabled = false, transport = false, slow = false)}
	<Tooltip content={$i18n.t(label)} placement={transport ? 'bottom' : 'top'} tippyOptions={transport || slow ? transportTooltip : {}}>
		<button type="button" class={iconClass} aria-label={$i18n.t(label)} on:click={action} {disabled}>{#key Icon}<Icon size={16} strokeWidth={1.7} fill={transport ? 'currentColor' : 'none'} />{/key}</button>
	</Tooltip>
{/snippet}

{#snippet panelTab(Icon: Component<{ size?: number; strokeWidth?: number }>, label: string, selected: boolean, action: () => void)}
	<Tooltip content={$i18n.t(label)} tippyOptions={label==='Preview' ? {} : transportTooltip}>
		<button type="button" class="edit-panel-tab" aria-label={$i18n.t(label)} aria-pressed={selected} on:click={action}>
			<Icon size={17} strokeWidth={1.7} />
		</button>
	</Tooltip>
{/snippet}

{#snippet handles(index:number,audio:boolean,value:number)}
	<span role="presentation" class="edit-level" class:lowered={value<1} style:top={'calc((100% - 7px) * '+(1-value)+')'}
		on:pointerdown={e=>levelPointer(e,index,audio)} on:pointermove={e=>levelPointer(e,index,audio)} on:pointerup={e=>levelPointer(e,index,audio)} on:pointercancel={()=>level=null}></span>
	{#if level?.index===index && level.audio===audio}<span class="level-value" aria-hidden="true">{Math.round(value*100)}%</span>{/if}
									{#each ['start', 'end'] as edge}
										<span role="presentation" class="edit-trim" class:edge-end={edge === 'end'} data-trim-edge={edge}
											on:pointerdown={event => startTrim(event, index, edge === 'end' ? 'end' : 'start')}
											on:pointermove={moveTrim} on:pointerup={endTrim} on:pointercancel={() => trim = null}></span>
									{/each}
{/snippet}

{#snippet exportOptions(kind:'mp3'|'mp4')}
	{#if kind==='mp4'}
		<DropdownMenu.Item data-export-option class={exportItemClass} on:click={()=>exportMedia(kind,'original')}>Original</DropdownMenu.Item>
	{/if}
	{#each kind==='mp4' ? [480,720,1080] : [128,192,256,320] as option}
		<DropdownMenu.Item data-export-option class={exportItemClass} on:click={()=>exportMedia(kind,option)}>{option}{kind==='mp4'?'p':' kbps'}</DropdownMenu.Item>
	{/each}
{/snippet}
{#snippet exportMenu()}
		<DropdownMenu.Root bind:open={exportMenuOpen} portal={null} preventScroll={false}>
			<Tooltip content={$i18n.t('Export')}><DropdownMenu.Trigger data-studio-export type="button" aria-label={$i18n.t('Export')} class={iconClass}><Download size={16} strokeWidth={1.7} /></DropdownMenu.Trigger></Tooltip>
			<DropdownMenu.Content side="bottom" align="end" sideOffset={6} strategy="fixed" transition={fly} transitionConfig={{ y: -5, duration: 150 }}
				data-export-menu class={exportMenuClass}>
				{#if exportPage}
					<DropdownMenu.Item class={exportItemClass} on:click={e=>switchExportPage(e,null)}><span class="flex items-center gap-1.5"><ChevronLeft size={14}/>{$i18n.t('Back')}</span></DropdownMenu.Item>
					{@render exportOptions(exportPage)}
				{:else}
				{#each exportKinds as kind}
					{#if kind==='srt'}
						<DropdownMenu.Item class={exportItemClass} on:click={downloadSrt}>SRT</DropdownMenu.Item>
					{:else if exportKinds.length===1}
						{@render exportOptions(kind)}
					{:else}
						<DropdownMenu.Item data-export-format={kind} class={exportItemClass} on:click={e=>switchExportPage(e,kind)}>{kind.toUpperCase()}</DropdownMenu.Item>
					{/if}
				{/each}
				{/if}
			</DropdownMenu.Content>
		</DropdownMenu.Root>
{/snippet}

{#snippet transportStep(next:boolean)}
<Tooltip content={$i18n.t(next?'Next frame':'Previous frame')} placement="bottom" tippyOptions={transportTooltip}>
	<button type="button" class={iconClass} disabled={!duration||!!loading} aria-label={$i18n.t(next?'Next frame':'Previous frame')} on:click={()=>seek(Math.min(duration,playhead+(next ? 0.03 : -0.03)))}>
		<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" style:transform={next?'none':'scaleX(-1)'}><path d="M5 5.5a1 1 0 0 1 1.55-.83l9 6.5a1 1 0 0 1 0 1.66l-9 6.5A1 1 0 0 1 5 18.5zM18 5h2v14h-2z"/></svg>
	</button>
</Tooltip>
{/snippet}

{#snippet panelAction()}
	<div class="ml-auto flex shrink-0 gap-1">
		{#if editingPanel === 'media'}
			{#if markedAssets.length}{@render tool(Trash2, 'Delete media', removeMarkedMedia, !!loading)}{/if}
			{@render tool(Upload, 'Import', () => fileInput.click(), !!loading)}
		{/if}
	</div>
{/snippet}

{#snippet captionMenu(label: string, value: string, options: { value: string; label: string }[], changeValue: (value: string) => void)}
	<div class="edit-caption-setting">
		<span>{$i18n.t(label)}</span>
		<DropdownMenu.Root portal={null} preventScroll={false} onOpenChange={open => { if (open) menuLabel=label; else if (menuLabel===label) menuLabel=""; }}>
			<DropdownMenu.Trigger type="button" aria-label={$i18n.t(label)} disabled={!!loading}
				class="studio-caption-trigger group flex min-w-0 items-center justify-between gap-1 rounded-full px-2 py-1.5 text-[0.8125rem] text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800">
				<span class="truncate">{options.find(option => option.value === value)?.label ?? '–'}</span>
				<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"
					class="size-3.5 shrink-0 transition-transform duration-150 {menuLabel === label ? '' : 'rotate-180'}">
					<path fill-rule="evenodd" clip-rule="evenodd" d="M14.78 12.78a.75.75 0 0 1-1.06 0L10 9.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06l4.25-4.25a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06Z" />
				</svg>
			</DropdownMenu.Trigger>
			<DropdownMenu.Content side="bottom" align="end" sideOffset={5} strategy="fixed" inTransition={fly} inTransitionConfig={{y:-5,duration:150}}
				class="studio-caption-menu z-20 min-w-32 rounded-lg border border-gray-200 bg-white p-1 text-sm shadow-md dark:border-gray-800 dark:bg-gray-850">
				<DropdownMenu.RadioGroup {value} onValueChange={changeValue}>
					{#each options as option}
						<DropdownMenu.RadioItem value={option.value} class="flex cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-2 outline-none data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-800">
							{option.label}
							{#if value === option.value}<CheckCircle className="size-4" strokeWidth="1.7" />{/if}
						</DropdownMenu.RadioItem>
					{/each}
				</DropdownMenu.RadioGroup>
			</DropdownMenu.Content>
		</DropdownMenu.Root>
	</div>
{/snippet}

<Modal bind:show onRequestClose={requestClose} mobileStep={confirmDiscard ? "discard" : ""} onMobileStepBack={() => confirmDiscard=false} size="w-[1260px]" className="file-preview-window" mobileFullscreen animated={false}>
	<section class="edit-shell" class:has-media={assets.length > 0} aria-label="Neve Studio"
		on:dragover={acceptFileDrag} on:drop={acceptFileDrag}>
		<input type="file" accept="video/*,.mkv,.avi,.mov,.webm,.mts,.m2ts" multiple hidden bind:this={fileInput}
			on:change={event => event.currentTarget.files && importFiles(event.currentTarget.files)} />
		<header class="edit-header flex justify-between px-5 pt-4 pb-3 border-b border-gray-200/30 dark:border-gray-700/20">
			<h2 class="self-center truncate text-lg font-medium dark:text-gray-100"><MobileModalTitle>Neve Studio</MobileModalTitle></h2>
			<div class="flex shrink-0 items-center gap-1 sm:gap-2">
				{#if assets.length}

					{#if exportRunning}
						<progress class="edit-export-progress" max="100" value={job?.progress ?? 0} aria-label={$i18n.t('Export progress')}></progress>
						<span class="edit-export-value text-xs tabular-nums">{job?.progress ?? 0}%</span>
						{@render tool(Square, 'Cancel export', cancelExport)}
					{:else if !duration || loading}
						<button type="button" class={iconClass} aria-label={$i18n.t('Export')} disabled><Download size={16} strokeWidth={1.7} /></button>
					{:else}
						{@render exportMenu()}
					{/if}
				{/if}
				<button data-mobile-modal-close type="button" class="self-center text-gray-500 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white" aria-label={$i18n.t('Close')} on:click={requestClose}><XMark className="size-5" /></button>
			</div>
		</header>
			<nav class="edit-mobile-tabs" aria-label={$i18n.t('Editing panels')}>
				{@render panelTab(MonitorPlay, 'Preview', mobilePanel === 'monitor', () => mobilePanel = 'monitor')}
				{#each visibleTabs as tab (tab.id)}
					{@render panelTab(tab.icon, tab.label, mobilePanel === 'inspector' && editingPanel === tab.id, () => openPanel(tab.id))}
				{/each}
				{#if mobilePanel === 'inspector'}{@render panelAction()}{/if}
			</nav>
		<div class="edit-workbench">
			<div class="edit-program" class:mobile-visible={mobilePanel === 'monitor'}>
				<div class="edit-monitor" class:has-video={!!previewSrc || duration > 0} role="region" aria-label={$i18n.t('Preview')} aria-busy={!!loading}>
					{#if previewSrc || duration}
						<div class="edit-preview-viewport" class:audio-canvas={!previewSrc} style:--ratio={(activeAsset?.width || 16)/(activeAsset?.height || 9)} class:portrait={timeline.aspect === 'portrait'} class:landscape={timeline.aspect === 'landscape'}>
						{#if (active?.opacity??1)<1}
						{#each timeline.clips.map((clip,index)=>({clip,index})).filter(({clip,index})=>!clip.audioOnly && (!clip.layout || clip.layout==='full') && (clip.lane??0)<(active?.lane??0) && playhead>=offsets[index] && playhead<offsets[index]+clipLength(clip)).sort((a,b)=>(a.clip.lane??0)-(b.clip.lane??0)) as under (under.index)}
							<div class="edit-preview-layer" style:opacity={under.clip.opacity??1}><video muted playsinline use:studioPreview={playbackUrl(under.clip.asset)} use:overlayVideo={{playing,time:under.clip.start+playhead-offsets[under.index]}}></video></div>
						{/each}{/if}
						{#if previewSrc}<!-- svelte-ignore a11y-media-has-caption -->
						<video use:studioPreview={previewSrc} bind:this={monitor} on:loadedmetadata={loadedMonitor} on:error={() => {pause(); setError(new Error('Could not open this video.'));}}
							playsinline preload="metadata" style:position="relative" style:transform={look.transform}
							style:filter={look.filter}
							style:opacity={(active?.opacity??1)*(active?.effect === 'fade' ? Math.max(0, Math.min(1, (playhead - offsets[current]) / Math.min(.45, clipLength(active) / 3), (offsets[current] + clipLength(active) - playhead) / Math.min(.45, clipLength(active) / 3))) : 1)}></video>{/if}
						{#if look.light}<span class="edit-preview-flash" style:background={look.light > 0 ? 'white' : 'black'} style:opacity={Math.abs(look.light)}></span>{/if}
						{#each overlays as {clip, index, t} (index)}
							{@const overlay = motionLook(clip, t)}
							{@const span = clipLength(clip)}
							<div class={`edit-preview-layer layout-${clip.layout}`}
								style:opacity={(clip.opacity??1)*(clip.layout === 'dissolve' ? Math.max(0, Math.min(1, t / Math.min(.6, span / 2), (span - t) / Math.min(.6, span / 2))) : 1)}>
								<!-- svelte-ignore a11y-media-has-caption -->
								<video muted playsinline use:studioPreview={playbackUrl(clip.asset)} use:overlayVideo={{ playing, time: clip.start + t }}
									style:transform={overlay.transform} style:filter={overlay.filter}></video>
								{#if overlay.light}<span class="edit-preview-flash" style:background={overlay.light > 0 ? 'white' : 'black'} style:opacity={Math.abs(overlay.light)}></span>{/if}
							</div>
						{/each}
						{#if timeline.title && introOpacity > 0}
							<span class="edit-preview-intro" style:opacity={introOpacity}
								style:transform={`translateX(${-13 * Math.max(0, 1 - playhead / .27)}px)`}>{timeline.title}</span>
						{/if}
						{#if currentCaption}<button type="button" aria-label={$i18n.t('Move caption')} class="edit-preview-caption" on:pointerdown={dragSubtitle} on:pointermove={dragSubtitle} on:pointerup={dragSubtitle} on:pointercancel={() => { snapX=undefined; snap=undefined; dragBounds=null; }}
							on:keydown={e => { if (['ArrowLeft','ArrowRight'].includes(e.key)) { e.preventDefault(); const positions=['left','center','right'] as const; positionCaptions(shownPosition,positions[Math.max(0,Math.min(2,positions.indexOf(shownHorizontal)+(e.key==='ArrowLeft'?-1:1)))]); } else if (['ArrowUp','ArrowDown'].includes(e.key)) { e.preventDefault(); const pos = ['top','center','bottom'] as const; positionCaptions(pos[Math.max(0,Math.min(2,pos.indexOf(shownPosition)+(e.key === 'ArrowUp' ? -1 : 1)))],shownHorizontal); } }}
							data-horizontal={snapX ?? shownHorizontal} data-position={snap ?? shownPosition} class:boxed={previewStyle.theme === 'box'} class:highlight={previewStyle.theme === 'highlight'}
							style:font-family={previewStyle.font} style:font-size={`${previewStyle.size * .78}px`}>{currentCaption}</button>{/if}
					{#if picking && pickClip}
						<div class="absolute inset-0 z-10 text-gray-100">
							<MakerSubjectPicker frameKey={pickClip.asset+':'+pickTime} width={activeAsset?.width || 1} height={activeAsset?.height || 1}
								transform={look.transform} crop={timeline.aspect==='portrait' || timeline.aspect==='landscape'} bind:pending={pickPending} bind:selection request={(points, signal) =>
									call(`/media/${pickClip!.asset}/selection`, {method:'POST', signal, headers:{'Content-Type':'application/json'},
										body:JSON.stringify({operation:picking, start:pickTime, points})})}/>
							<div class="absolute bottom-2 right-2 flex items-center gap-1.5 text-xs">
								<button type="button" class="rounded-lg bg-gray-100 px-4 py-1.5 font-medium text-gray-900 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700" on:click={() => picking = null}>{$i18n.t('Cancel')}</button>
								{#if selection}<button type="button" class="rounded-lg bg-black px-4 py-1.5 font-medium text-white hover:opacity-90 dark:bg-white dark:text-black" disabled={pickPending} on:click={() => picking && processClip(picking)}>{$i18n.t('Apply')}</button>{/if}
							</div>
						</div>
					{/if}
						</div>
					{/if}
					{#if loading && assets.length}
						<div class="edit-monitor-loading" class:bounded={!!duration} style:--ratio={timeline.aspect==='portrait'?9/16:timeline.aspect==='landscape'?16/9:(activeAsset?.width || 16)/(activeAsset?.height || 9)} role="status">
							<OrbitingSpheres className="size-7" />
							<span>{$i18n.t(loading)}</span>
							{#if activeRequest}
								<button type="button" class={iconClass} aria-label={$i18n.t('Cancel')} on:click={cancelOperation}><XMark className="size-4" /></button>
							{/if}
						</div>
					{/if}
				</div>
				{#if assets.length}
				<div class="edit-transport">
					<div class="edit-frame-buttons flex items-center justify-center gap-1">
						{@render transportStep(false)}
						<Tooltip content={$i18n.t(playing ? 'Pause' : 'Play')} placement="bottom" tippyOptions={transportTooltip}>
							<button type="button" class={iconClass} aria-label={$i18n.t(playing ? 'Pause' : 'Play')} on:click={togglePlayback} disabled={!duration || !!loading || !!picking}>
								<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">{#if playing}<rect x="5" y="4" width="5" height="16" rx="1"/><rect x="14" y="4" width="5" height="16" rx="1"/>{:else}<path d="M6 4.6a1.2 1.2 0 0 1 1.8-1l12 7.4a1.2 1.2 0 0 1 0 2l-12 7.4a1.2 1.2 0 0 1-1.8-1z"/>{/if}</svg>
							</button>
						</Tooltip>
						{@render transportStep(true)}
					</div>
					{#if activeAsset}<span class="edit-preview-resolution justify-self-end text-xs tabular-nums text-gray-500 dark:text-gray-400">{activeAsset.width} × {activeAsset.height}</span>{/if}
				</div>
				{/if}
			</div>
			<aside class="edit-side" class:mobile-visible={mobilePanel === 'inspector'}>
				<nav class="edit-tabs" aria-label={$i18n.t('Editing panels')}>
					{#each visibleTabs as tab (tab.id)}
						{@render panelTab(tab.icon, tab.label, editingPanel === tab.id, () => openPanel(tab.id))}
					{/each}
					{@render panelAction()}
				</nav>
				<div class="edit-properties" class:tool-properties={editingPanel==='tools'} class:caption-properties={editingPanel==='captions'}
					role="region" aria-label={$i18n.t(editingPanel==='tools'?'Tools':editingPanel === 'media' ? 'Media bin' : 'Captions')}>
					{#if editingPanel === 'media'}
						<div class="edit-assets">
							{#each visibleAssets as asset (asset.id)}
								<button type="button" class="edit-asset" data-video-edit-asset={asset.id} draggable={!loading}
									aria-label={asset.name} disabled={!!loading}
									aria-pressed={markedAssets.includes(asset.id)} class:dragging={drag && 'asset' in drag && drag.asset===asset.id}
									on:pointerdown={()=>draggedAsset=''} on:click={e=>toggleMedia(asset.id,e)}
									on:dragstart={event => setDrag(event, { asset: asset.id })} on:dragend={clearDrag}
									on:keydown={event => { if (event.key === 'Enter' && event.shiftKey) { event.preventDefault(); addClip(asset, playhead); } }}>
									<span class="block"><img src={mediaUrl(asset.id) + '/thumbnail'} alt="" loading="lazy" draggable="false" /></span>
									<Tooltip as="span" className="block w-fit max-w-full min-w-0" content={asset.name} allowHTML={false}
										tippyOptions={{ ...transportTooltip, trigger: 'mouseenter' }}><span class="block truncate text-xs">{asset.name}</span></Tooltip>
								</button>
							{/each}
						</div>
					{:else if editingPanel==='tools'}
						<div class="studio-tool-grid" data-model-grid use:modelGridWheel>{#each [...assistKeys,...installedTools] as op}
						{@const Icon=toolIcons[op]}
						{@const applicable = op==='translate' ? hasExportCaptions : op==='remaster' || op==='fps60' || op==='color' || op==='erase' ? videoToolsAllowed : audioToolsAllowed}
						{@const inactive = !applicable || (!!activeTool && activeTool!==op) || (!!loading && activeTool!==op)}
						<button type="button" disabled={inactive || !!loading} class:inactive on:click={() => op==='translate' ? translateOpen=true : op in assistNames ? assist(op as Assist) : chooseTool(op as ClipTool)}
							class="edit-tool-card rounded-md outline-none">
							{#if timeline.clips[selected]}<img class="edit-tool-poster" src={mediaUrl(timeline.clips[selected].asset)+"/thumbnail"} alt="" draggable="false"/>{/if}
							<span class="edit-tool-image"><Icon size={17} strokeWidth={1.7}/></span>
							<span class="edit-tool-label">{$i18n.t(({...assistNames,...clipTools})[op])}</span>
						</button>
					{/each}</div>
					{:else}
						{#if styleTargets.size}<div class="edit-caption-style">
							{@render captionMenu('Font', chosenFont ?? '', ['Arial','Georgia','Consolas','Impact','Tahoma','Verdana'].map(value => ({ value, label: value })),
								value => setCaptionStyle('font', value as CaptionStyle['font']))}
							{@render captionMenu('Style', chosenTheme ?? '', [{value:'outline', label:$i18n.t('Outline')}, {value:'box', label:$i18n.t('Caption background')}, {value:'highlight', label:$i18n.t('Caption highlight')}],
								value => setCaptionStyle('theme', value as CaptionStyle['theme']))}
							<div class="edit-caption-setting"><span>{$i18n.t('Font size')}</span>
								<div class="cue-size justify-self-end"><JanNumberControl label={$i18n.t('Font size')} value={targetStyles[0].size} min={12} max={36} step={1} disabled={!!loading}
									onCommit={size => setCaptionStyle('size',size)} /></div>
							</div>
						</div>{/if}
						<div class="caption-details">
						{#if speakers.length}<div class="edit-caption-style edit-speakers">
							{#each speakers as [key,name], i (key)}
								<div class="edit-caption-setting"><span>{$i18n.t('Speaker')} {i+1}</span><input type="text" aria-label={`${$i18n.t('Speaker')} ${i+1}`} value={name} use:speakerField={name} disabled={!!loading} on:change={e=>renameSpeaker(key,e.currentTarget)} />
									{@render tool(sampleKey===key?Square:Volume2,sampleKey===key?'Stop':'Listen',()=>playSample(key),false,false,true)}
								</div>
							{/each}
						</div>{/if}
						{#each selectedCues as {cue,index} (index)}
							<div class="edit-cue">
								<button type="button" class="edit-cue-time" on:click={() => jumpToCaption(index)}>{editTime(cue.start)}</button>
								<StudioCaptionInput label={$i18n.t('Caption')} value={cue.text} disabled={!!loading} commit={text=>editCaption(index,text)} />
							</div>
						{/each}
						</div>
					{/if}
				</div>
			</aside>
		</div>
		<div class="edit-sequence">
			<div class="edit-sequence-toolbar">
				<span class="edit-sequence-time">{editTime(playhead)}</span>
				<div class="flex min-w-0 items-center gap-0.5">
					{@render tool(ZoomOut, 'Zoom out timeline', () => changeZoom(zoom / 1.4), zoom <= 1, false, true)}
					{@render tool(ZoomIn, 'Zoom in timeline', () => changeZoom(zoom * 1.6), zoom >= maxTimelineZoom, false, true)}
					<span class="edit-divider"></span>
					{@render tool(Undo2, 'Undo', undo, !past.length || !!loading, false, true)}
					{@render tool(Redo2, 'Redo', redo, !future.length || !!loading, false, true)}
					<span class="edit-divider"></span>
					<Tooltip content={`${$i18n.t('Split')} (Ctrl+S)`} tippyOptions={transportTooltip}>
						<button type="button" class={iconClass} aria-label={$i18n.t('Split at playhead')} aria-keyshortcuts="Control+S Meta+S" disabled={!duration || !!loading} on:click={split}><Scissors size={16} strokeWidth={1.7} /></button>
					</Tooltip>
					{@render tool(Trash2, 'Remove', removeSelected, (!group.length && (part==='caption'?cueIndex<0:!marked.length)) || !!loading, false, true)}
				</div>
			</div>
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div class="edit-timeline-frame" on:wheel|nonpassive={wheelTimeline} on:pointerdown={clearOnTimelineBackground}>
			<div class="fixed-ruler"><div class="ruler-clip"><div class="edit-ruler" style:width={gridWidth ? gridWidth+'px' : '100%'} style:transform={'translateX(-'+scrollOffset+'px)'} role="slider" tabindex="0" aria-label={$i18n.t('Playhead')} aria-valuenow={Math.round(playhead * 100) / 100}
							aria-valuemin={0} aria-valuemax={rulerEnd}
							on:pointerdown={scrub} on:pointermove={scrub}
							on:keydown={e => { if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); seek(playhead + (e.key === 'ArrowRight' ? .1 : -.1)); } }}>
							{#each ticks as mark (mark)}
								<span style:left={`${mark/rulerEnd*100}%`}>{gridWidth>rulerEnd*90?editTime(mark):editTime(mark).split(':').slice(0,2).join(':')}</span>
							{/each}<i class="edit-ruler-head" style:left={playhead/rulerEnd*100+'%'}></i>
						</div></div></div>
			<div class="edit-timeline" bind:this={laneScroll}>
				<div class="edit-track-labels">
					
					{#if videoLaneCount < 6}<div class="edit-add-lane-label"></div>{/if}
					{#each videoLanes as lane}
						<div class="edit-video-label"><span>V{lane + 1}</span></div>
					{/each}
					{#each audioLanes as lane}
						{@const enabled = timeline.clips.some(clip => (clip.lane ?? 0) === lane && assets.find(asset => asset.id === clip.asset)?.audio)}
						{@const muted = trackMuted(timeline, lane)}
						{@const gain = muted ? 0 : Math.round((timeline.audioLaneGains?.[lane] ?? 1) * 100)}
						<div class="edit-audio-label">
							<span>A{lane + 1}</span>
							{#if timeline.clips.length}<div class="edit-volume" style:--gain={`${gain}%`}>
								{@render tool(muted ? VolumeX : Volume2, muted ? 'Unmute audio track' : 'Mute audio track', () => toggleAudioTrack(lane), !enabled || !!loading)}
								<input type="range" min="0" max="100" step="1" aria-label={`${$i18n.t('Volume')} A${lane + 1}`}
									value={gain} disabled={!enabled || !!loading}
									on:input={event => event.currentTarget.parentElement?.style.setProperty('--gain', `${event.currentTarget.value}%`)}
									on:change={event => { recordEdit(); setTrackGain(lane,event.currentTarget.valueAsNumber/100); }} />
								<span class="tabular-nums">{gain}%</span>
							</div>{/if}
						</div>
					{/each}
					{#if audioLaneCount < 6}<div class="edit-add-lane-label"></div>{/if}
					<div class="edit-caption-label"><span>CC</span><button type="button" class={iconClass} aria-label={$i18n.t('Add caption')} disabled={!duration || !!loading || !!picking} on:click={addCaption}><Plus size={16} strokeWidth={1.7}/></button></div>
				</div>
				<div class="edit-timeline-scroll" id="maker-timeline-scroll" bind:this={trackScroll} bind:clientWidth={viewportWidth} use:observeTimelineScroll on:scroll={measureTimelineScroll}>
					<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
					<div class="edit-track-grid" tabindex="-1" bind:clientWidth={gridWidth} bind:this={trackGrid} style:width={`${zoom * 100}%`}
						on:pointerdown={startMarquee} on:pointermove={moveMarquee} on:pointerup={finishMarquee}
						on:pointerleave={() => { if (!skipTrackClick) marquee = null; }}
						on:pointercancel={() => { stopEdgeScroll(); marquee = null; skipTrackClick = false; }}
						on:click={event => { if (!skipTrackClick && !(event.target as Element).closest('button,.edit-ruler,.edit-trim,.edit-level')) {clearSelection(); seek(timelineTime(event.clientX));} skipTrackClick = false; }}>
						
						{#if videoLaneCount < 6}
							<div class="edit-add-lane" class:drop-target={dropLane === `v${videoLaneCount}`} role="region" aria-label={$i18n.t('New video track')}
								on:dragleave={() => { if (dropLane === `v${videoLaneCount}`) { dropLane = null; dropMarker = null; } }}
								on:dragover={event => dragOver(event, videoLaneCount)} on:drop={event => dropClip(event, videoLaneCount)}></div>
						{/if}
						{#each videoLanes as lane}
						<div class="edit-track edit-video-track" role="group" data-video-lane={lane}
							aria-label={lane ? `${$i18n.t('Video track')} ${lane + 1}` : $i18n.t('Video track')}
							on:dragover={event => dragOver(event, lane)} on:drop={event => dropClip(event, lane)}>
							{#each timeline.clips as item, index}
								{#if !item.audioOnly && (item.lane ?? 0) === lane}
								<div class="edit-clip-item" style:width={`${clipLength(item) / rulerEnd * 100}%`} style:left={`${(offsets[index] ?? 0) / rulerEnd * 100}%`}>
									<button type="button" class:chosen={group.length ? group.includes('video:'+index) : part==='video' && marked.includes(index)} draggable={!loading && (group.length ? group.includes('video:'+index) : part==='video' && marked.includes(index))} data-key={'video:'+index} data-video-edit-clip={index} data-clip-selection={index}
										on:dragstart={event => setDrag(event, { index })} on:dragend={clearDrag}
										aria-pressed={group.length ? group.includes('video:'+index) : part==='video' && marked.includes(index)} on:click={event => selectClip(event, index)}>
										<img src={mediaUrl(item.asset) + '/thumbnail'} alt="" loading="lazy" draggable="false" /><span>{assets.find(a => a.id === item.asset)?.name}</span>
									</button>
									{@render handles(index,false,item.opacity??1)}
								</div>
								{/if}
							{/each}
						</div>
						{/each}
						{#each audioLanes as lane}
						<div class="edit-track edit-audio-track" class:muted={trackMuted(timeline, lane)} role="group" data-audio-lane={lane}
							aria-label={lane ? `${$i18n.t('Audio track')} ${lane + 1}` : $i18n.t('Audio track')}
							on:dragover={event => dragOver(event, lane, true)} on:drop={event => dropClip(event, lane, true)}>
							{#each timeline.clips as item, index}
								{#if (item.lane ?? 0) === lane && !item.noAudio && assets.find(asset => asset.id === item.asset)?.audio}
								<div class="edit-clip-item" style:width={clipLength(item)/rulerEnd*100+'%'} style:left={(offsets[index]??0)/rulerEnd*100+'%'}>
								<button type="button" data-key={'audio:'+index} aria-label={`${$i18n.t('Audio track')} ${index + 1}`} class:chosen={group.length ? group.includes('audio:'+index) : part==='audio' && marked.includes(index)}
									aria-pressed={group.length ? group.includes('audio:'+index) : part==='audio' && marked.includes(index)} data-clip-selection={index}
									class:muted={item.gain === 0} draggable={!loading && (group.length ? group.includes("audio:"+index) : part==="audio" && marked.includes(index))}
									on:dragstart={event => setDrag(event, { index, audio: true })} on:dragend={clearDrag}
									on:click={event => selectClip(event, index,"audio")}>
									{#if wavePaths[index]}
										<svg class="edit-wave" style:transform={`scaleY(${item.gain})`} viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true"><path d={wavePaths[index]} /></svg>
									{:else if assets.find(a => a.id === item.asset)?.audio}<span class="pl-2"><Volume2 size={12} aria-hidden="true" /></span>{/if}
								</button>
								{@render handles(index,true,Math.min(1,item.gain))}
								</div>
								{/if}
							{/each}
						</div>
						{/each}
						{#if audioLaneCount < 6}
							<div class="edit-add-lane" class:drop-target={dropLane === `a${audioLaneCount}`} role="region" aria-label={$i18n.t('New audio track')}
								on:dragleave={() => { if (dropLane === `a${audioLaneCount}`) { dropLane = null; dropMarker = null; } }}
								on:dragover={event => dragOver(event, audioLaneCount, true)} on:drop={event => dropClip(event, audioLaneCount, true)}></div>
						{/if}
						<div class="edit-track edit-caption-track">
							{#each visibleCaptions as {run,cue,index}}
										{@const shownCue = captionDrag?.index === index ? captionDrag.cue : cue}
										<div class="edit-caption-item" data-caption-index={index}
											style:left={`${(run.at + Math.max(0, shownCue.start - run.start)) / rulerEnd * 100}%`}
											style:width={`${Math.max(0, Math.min(run.end, shownCue.end) - Math.max(run.start, shownCue.start)) / rulerEnd * 100}%`}>
											<button type="button" data-key={'caption:'+index} class:chosen={group.includes('caption:'+index) || cueIndex===index} aria-label={captionLabel(cue)} aria-pressed={group.length ? group.includes('caption:'+index) : part==='caption' && cueIndex===index}
												on:pointerdown={event => startCaption(event, index, run, 'move')}
												on:pointermove={moveCaption} on:pointerup={finishCaption} on:pointercancel={() => captionDrag = null}
												on:click={event => { if (skipTrackClick || (event.detail && skipCaptionClick)) return; if(event.shiftKey){addSelection('caption',index);return;} group=[]; part='caption'; cueIndex=index; marked=[]; if (event.detail) seek(timelineTime(event.clientX)); else jumpToCaption(index); }}>{captionLabel(cue)}</button>
											{#each ['start', 'end'] as edge}
												<span role="presentation" class="edit-trim" class:edge-end={edge === 'end'} data-caption-edge={edge}
													on:pointerdown={event => startCaption(event, index, run, edge === 'end' ? 'end' : 'start')}
													on:pointermove={moveCaption} on:pointerup={finishCaption} on:pointercancel={() => captionDrag = null}></span>
											{/each}
										</div>
							{/each}
						</div>
						{#if dropMarker !== null && dropLane !== `v${videoLaneCount}` && dropLane !== `a${audioLaneCount}`}<span class="edit-drop-marker" style:left={`${dropMarker / rulerEnd * 100}%`} aria-hidden="true"></span>{/if}
						{#if marquee && skipTrackClick}
							<span class="edit-marquee" style:left={`${Math.min(marquee.x, marquee.endX)}px`} style:top={`${Math.min(marquee.y, marquee.endY)}px`}
								style:width={`${Math.abs(marquee.endX - marquee.x)}px`} style:height={`${Math.abs(marquee.endY - marquee.y)}px`}></span>
						{/if}
						{#if trim}<span class="edit-drop-marker" style:left={`${((offsets[trim.index] ?? 0) + trim.value - timeline.clips[trim.index].start) / rulerEnd * 100}%`} aria-hidden="true"></span>{/if}
						<span class="edit-playhead" style:left={`${playhead / rulerEnd * 100}%`} aria-hidden="true"></span>
					</div>
				</div>
				</div>
				<div class="edit-timeline-bar" role="scrollbar" aria-label={$i18n.t('Timeline scroll')}
					aria-controls="maker-timeline-scroll" aria-orientation="horizontal" aria-valuemin={0}
					aria-valuemax={Math.round(scrollLimit)} aria-valuenow={Math.round(scrollOffset)}
					tabindex={scrollLimit ? 0 : -1} aria-disabled={!scrollLimit}
					on:pointerdown={dragTimelineScroll} on:pointermove={dragTimelineScroll} on:keydown={scrollTimelineKey}>
					<span style:width={`${thumbFraction * 100}%`} style:left={`${scrollLimit ? scrollOffset / scrollLimit * (1 - thumbFraction) * 100 : 0}%`}></span>
				</div>
			</div>
		</div>
		
		<div class="sr-only" aria-live="polite">{#if notice}{$i18n.t(notice)}{/if}</div>
	</section>
</Modal>
{#if translateOpen}<Modal bind:show={translateOpen} size="w-[25rem]">
	<div class="translation-dialog px-7 py-6">
		<h2 class="mb-3 text-lg font-medium dark:text-gray-200">{$i18n.t('Translate captions')}</h2>
		{@render captionMenu('Original language',sourceLanguage,translationChoices,v=>sourceLanguage=v)}
		{@render captionMenu('Translate to',targetLanguage,translationChoices,v=>targetLanguage=v)}
		<div class="mt-6 flex justify-end gap-1.5"><button type="button" class="rounded-lg bg-gray-100 px-4 py-1.5 text-xs font-medium transition hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700" on:click={()=>translateOpen=false}>{$i18n.t('Cancel')}</button>
			<button type="button" class="rounded-lg bg-black px-4 py-1.5 text-xs font-medium text-white transition hover:opacity-90 disabled:opacity-40 dark:bg-white dark:text-black" disabled={sourceLanguage===targetLanguage}
				on:click={()=>{translateOpen=false;void translateCaptions()}}>{$i18n.t('Translate')}</button></div>
	</div>
</Modal>{/if}
<ConfirmDialog animated={false} bind:show={confirmDiscard} title={$i18n.t("Discard edits?")} message={$i18n.t("Media and edits will be removed from this session. Original files are kept.")} confirmLabel={$i18n.t("Discard")} onConfirm={discard} />

<style>
	.translation-dialog :global(.edit-caption-setting) {grid-template-columns:auto minmax(0,1fr);min-height:36px;color:inherit;}
	.translation-dialog :global(.edit-caption-setting > span) {font-size:15px;color:color-mix(in srgb,currentColor 82%,transparent);}
	.translation-dialog :global(.studio-caption-trigger) {justify-self:end;}
	.audio-canvas {background:#000}
	.edit-footer:empty {display:none}
	.edit-video-label {background:color-mix(in srgb,#438bc7 15%,transparent)}
	.edit-audio-label {background:color-mix(in srgb,#23987d 15%,transparent)}
	.edit-caption-label, .edit-add-lane-label:has(+.edit-caption-label) {background:color-mix(in srgb,#a67bcc 15%,transparent)}
	.edit-caption-item button[aria-pressed=true] {outline:none}
	.edit-properties.tool-properties {container:tools / size;overflow:hidden;}
	.studio-tool-grid {--rows:3;display:grid;align-content:start;height:100%;grid-template-columns:repeat(2,minmax(0,1fr));grid-auto-rows:calc((100% + 8px) / var(--rows) - 8px);gap:8px;padding-inline-end:6px;overflow-y:auto;overscroll-behavior:contain;scroll-snap-type:y mandatory;scrollbar-gutter:stable;}
	@container tools (max-height:225px) {.studio-tool-grid {--rows:2;}}
	@container tools (max-height:145px) {.studio-tool-grid {--rows:1;}}
	@container tools (min-height:516px) {.studio-tool-grid {--rows:4;}}
	.studio-tool-grid .edit-tool-card {aspect-ratio:auto;min-height:0;display:block;scroll-snap-align:start;}
	.studio-tool-grid .edit-tool-card.inactive {opacity:.4;cursor:default;}
	.studio-tool-grid .edit-tool-card:enabled:is(:hover,:focus-visible)::after {
		content:''; position:absolute; inset:0; border-radius:inherit; pointer-events:none;
		background:color-mix(in srgb,var(--quiet) 9%,transparent);
		box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--quiet) 50%,transparent);
	}
	.edit-monitor-loading.bounded {inset:auto;position:absolute;width:min(100cqw,calc(100cqh * var(--ratio)));aspect-ratio:var(--ratio)}
	.edit-preview-caption[data-horizontal=left] {left:6%;--dx:0%}
	.edit-preview-caption[data-horizontal=right] {left:94%;--dx:-100%}

	.edit-shell {
		--line:color-mix(in srgb,var(--color-gray-200) 55%, transparent); --surface:var(--color-gray-100);
		--quiet:var(--color-gray-600); --blue:var(--color-blue-600);
		--foreground:var(--color-gray-900); --canvas:white;
		display:grid; grid-template-columns:minmax(0,1fr);
		grid-template-rows:auto minmax(0,1fr) auto auto;
		height:min(88dvh,780px);
	}
	.edit-shell.has-media { height:min(88dvh,780px); }
	:global(.dark) .edit-shell {
		--line:color-mix(in srgb,var(--color-gray-700) 20%, transparent); --surface:var(--color-gray-850);
		--quiet:var(--color-gray-400); --blue:var(--color-blue-400);
		--foreground:var(--color-gray-100); --canvas:var(--color-gray-900);
	}
	.edit-header { gap:8px; }



	.edit-export-progress { appearance:none; width:68px; height:5px; overflow:hidden; border:0; border-radius:3px; background:var(--surface); color:var(--color-blue-600); }
	.edit-export-progress::-webkit-progress-bar { background:var(--surface); border-radius:3px; }
	.edit-export-progress::-webkit-progress-value { background:var(--color-blue-600); border-radius:3px; }
	.edit-export-progress::-moz-progress-bar { background:var(--color-blue-600); border-radius:3px; }
	.edit-export-value { width:35px; text-align:right; }
	.edit-mobile-tabs { display:none; }
	.edit-workbench { display:grid; grid-template-areas:"side program"; grid-template-columns:minmax(225px,26%) minmax(0,1fr); min-height:0; }
	.edit-workbench.empty { grid-template-areas:"program"; grid-template-columns:minmax(0,1fr); }
	.edit-program, .edit-side { min-width:0; min-height:0; display:grid; }
	.edit-program { grid-area:program; grid-template-rows:minmax(0,1fr) 45px; padding:12px 14px 0; }
	.empty .edit-program { grid-template-rows:minmax(0,1fr); padding:16px; }
	.edit-monitor { position:relative; display:grid; place-items:center; overflow:hidden; border-radius:8px; background:transparent; container-type:size; }
	.edit-monitor.has-video { background:transparent; }
	.edit-monitor-loading { position:absolute; inset:0; display:flex; flex-direction:column; gap:10px; align-items:center; justify-content:center; background:var(--surface); color:inherit; font-size:16px; font-weight:700; }
	.edit-import { display:inline-flex; align-items:center; gap:9px; min-height:38px; padding:0 13px; border:1px solid var(--line); border-radius:8px; background:var(--canvas); font-size:13px; font-weight:500; }
	.edit-import:hover:not(:disabled) { border-color:var(--quiet); }
	.edit-import:disabled { color:var(--quiet); }
	.edit-monitor video { position:absolute; inset:0; margin:auto; height:100%; width:100%; object-fit:contain; }
	.edit-preview-viewport { background:black;position:relative; width:min(100cqw,calc(100cqh * var(--ratio))); aspect-ratio:var(--ratio); overflow:hidden; }
	.edit-preview-viewport.portrait { width:min(100%,56.25cqh); height:min(100%,177.78cqw); }
	.edit-preview-viewport.landscape { width:min(100%,177.78cqh); height:min(100%,56.25cqw); }
	.edit-preview-viewport:is(.portrait,.landscape) video { object-fit:cover; }
	.edit-preview-flash { position:absolute; inset:0; pointer-events:none; }
	.edit-preview-layer { position:absolute; inset:0; overflow:hidden; pointer-events:none; }
	.edit-preview-layer video { object-fit:cover; }
	.edit-preview-layer.layout-inset { inset:4% 4% auto auto; width:38%; height:38%; }
	.edit-preview-layer.layout-left { inset-inline-end:50%; }
	.edit-preview-layer.layout-right { inset-inline-start:50%; }
	.edit-stage-model { max-width:92%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--quiet); font-size:11px; font-weight:400; }
	.edit-preview-intro { position:absolute; left:6%; bottom:26%; max-width:88%; color:white; font-size:clamp(14px,7cqh,27px); font-weight:700; overflow-wrap:anywhere; text-shadow:0 1px 4px #000; pointer-events:none; }
	.edit-preview-caption { touch-action:none; user-select:none; cursor:move; position:absolute; left:50%; transform:translateX(var(--dx,-50%)); width:max-content; bottom:7%; max-width:88%; padding:3px 7px; text-align:center; color:white; text-shadow:0 1px 3px #000,0 0 2px #000; border-radius:4px; overflow-wrap:anywhere; }
	.edit-preview-caption[data-position='top'] { top:7%; bottom:auto; }
	.edit-preview-caption[data-position='center'] { top:50%; bottom:auto; transform:translate(var(--dx,-50%),-50%); }
	.edit-preview-caption.boxed { background:#111c; }
	.edit-preview-caption.highlight { color:#ffe45e; }
	.edit-transport { display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); align-items:center; gap:6px; padding-inline:3px; }
	.edit-frame-buttons { grid-column:2; }
	.edit-preview-resolution { grid-column:3; white-space:nowrap; }
	.edit-side { grid-area:side; grid-template-rows:44px minmax(0,1fr); border-right:1px solid var(--line); }
	.edit-tabs, .edit-mobile-tabs { align-items:center; gap:4px; padding:0 12px; border-bottom:1px solid var(--line); }
	.edit-tabs { display:flex; }
	.edit-panel-tab { display:grid; place-items:center; width:32px; height:32px; flex:none; border-radius:6px; color:var(--quiet); }
	.edit-panel-tab:is(:hover, :focus-visible, [aria-pressed='true']) { background:var(--surface); color:var(--foreground); }
	.edit-properties { min-height:0; min-width:0; overflow:auto; padding:12px; }
	.edit-properties.caption-properties {display:flex;flex-direction:column;overflow:hidden;}
	.caption-properties > .edit-caption-style {flex:none;}
	.caption-details {display:flex;flex-direction:column;flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:auto;}
	.caption-details::-webkit-scrollbar {width:calc(.45rem + 6px);}
	.caption-details::-webkit-scrollbar-thumb {border-inline-start:6px solid transparent;background-clip:padding-box;}
	.caption-details > .edit-speakers {flex:none;grid-template-columns:max-content minmax(0,1fr) auto;column-gap:8px;}
	.edit-speakers .edit-caption-setting {grid-column:1/-1;grid-template-columns:subgrid;column-gap:inherit;}
	.edit-speakers:last-child {border-bottom:0;}
	.edit-assets { display:grid; grid-template-columns:repeat(auto-fill,minmax(94px,1fr)); gap:7px; }
	.edit-asset { display:grid; width:100%; gap:3px; min-width:0; padding:5px; text-align:left; border-radius:6px; cursor:pointer; }
	.edit-asset.dragging { cursor:grabbing; }
	.edit-asset[aria-pressed="true"] { background:var(--surface); }
	.edit-asset img { width:100%; aspect-ratio:16 / 9; object-fit:cover; border-radius:4px; }




	.edit-speakers input { min-width:0; height:29px; padding:0 8px; border:1px solid var(--line); border-radius:6px; background:var(--canvas); font-size:14px; color:inherit; }
	.edit-caption-style { display:grid; gap:7px; padding:1px 0 10px; border-bottom:1px solid var(--line); margin-bottom:8px; }
	.edit-caption-setting { display:grid; grid-template-columns:minmax(0,1fr) minmax(92px,110px); align-items:center; gap:8px; color:var(--quiet); font-size:14px; }
	.edit-speakers input:focus { outline:none; border-color:color-mix(in srgb,var(--quiet) 35%, transparent); box-shadow:none; }
	.edit-cue { display:grid; grid-template-columns:minmax(0,1fr); grid-template-rows:max-content minmax(0,1fr); min-height:0; flex:1 0 9rem; gap:6px; padding-top:2px; }
	.edit-speakers input {color:var(--foreground);}
	.cue-size :global(.border), .cue-size :global(.divide-x > *) {border-color:var(--line);}
	:global(.studio-caption-menu) {max-height:calc(100dvh - 16px);overflow-y:auto;scrollbar-width:none;}
	.edit-cue-time { justify-self:start; font-size:13px; font-variant-numeric:tabular-nums; color:var(--quiet); }
	.edit-cue-time:hover { color:var(--blue); }
	.edit-sequence { border-top:1px solid var(--line); padding:0 14px 8px; }
	.edit-sequence-toolbar { display:flex; align-items:center; gap:10px; min-height:41px; }
	.edit-sequence-time { font-family:inherit; flex:1; font-size:16px; font-weight:400; user-select:none; }
	.edit-divider { width:1px; height:16px; background:var(--line); margin:0 3px; }
	.edit-timeline-frame { --track-label-width:132px; border:1px solid var(--line); border-radius:7px; background:var(--surface); overflow:hidden; }
	.edit-timeline { display:grid; grid-template-columns:var(--track-label-width) minmax(0,1fr); height:calc(114px + clamp(44px,7dvh,70px)); align-content:start; overflow:auto; overscroll-behavior:contain; }
	.edit-track-labels { border-right:1px solid var(--line); }
	.edit-track-labels > div { display:grid; place-items:center; font-size:10px; color:var(--quiet); border-bottom:1px solid var(--line); }
	.edit-track-labels .edit-ruler-label, .edit-ruler { height:24px; }
	.edit-track-labels .edit-video-label, .edit-video-track { height:clamp(44px,7dvh,70px); }
	.edit-track-labels .edit-audio-label, .edit-audio-track { height:49px; }
	.edit-track-labels :is(.edit-video-label, .edit-audio-label) { align-content:center; padding-inline:5px; gap:1px; }
	.edit-volume { display:grid; width:100%; grid-template-columns:22px minmax(0,1fr) 27px; align-items:center; gap:4px; }
	.edit-volume input { appearance:none; min-width:0; width:100%; height:14px; cursor:pointer; background:transparent; }
	.edit-volume input::-webkit-slider-runnable-track { height:3px; border-radius:6px; background:linear-gradient(90deg,var(--quiet) var(--gain),var(--line) var(--gain)); }
	.edit-volume input::-webkit-slider-thumb { appearance:none; width:9px; height:9px; margin-top:-3px; border-radius:50%; background:var(--foreground); }
	.edit-volume input::-moz-range-track { height:3px; border-radius:6px; background:var(--line); }
	.edit-volume input::-moz-range-progress { height:3px; border-radius:6px; background:var(--quiet); }
	.edit-volume input::-moz-range-thumb { width:9px; height:9px; border:0; border-radius:50%; background:var(--foreground); }
	.edit-volume input:disabled { opacity:.4; cursor:default; }
	.edit-audio-label :global(button) { width:22px; height:20px; }
	.edit-audio-label :global(button svg) { width:13px; height:13px; }
	.edit-track-labels .edit-caption-label, .edit-caption-track { height:49px; border-bottom:none; }
	.edit-track-labels .edit-caption-label {display:flex;align-items:center;justify-content:center;gap:4px;}
	.edit-add-lane-label + .edit-caption-label {padding-bottom:8px;}
	.edit-caption-label :global(button) {width:24px;height:24px;}
	.edit-timeline-scroll { align-self:start; overflow-x:auto; min-width:0; scrollbar-width:none; }
	.edit-timeline-bar { position:relative; margin:3px 5px 4px calc(var(--track-label-width) + 5px); height:6px; background:var(--line); border-radius:999px; touch-action:none; }
	.edit-timeline-bar span { position:absolute; inset-block:0; background:rgba(215,215,215,.6); border-radius:inherit; }
	:global(.dark) .edit-timeline-bar span { background:rgba(67,67,67,.6); }
	.edit-timeline-bar[aria-disabled='false'] { cursor:grab; }
	.edit-timeline-bar[aria-disabled='false']:active { cursor:grabbing; }
	.edit-timeline-bar[aria-disabled='true'] span { opacity:.65; }
	.edit-track-grid { position:relative; min-width:100%; user-select:none; outline:none; }
	.edit-ruler { position:relative; cursor:ew-resize; border-bottom:1px solid var(--line); touch-action:none; }
	.fixed-ruler {-webkit-user-select:none;user-select:none;padding-left:var(--track-label-width);height:24px}
	.ruler-clip {overflow:hidden;height:24px}
	.edit-ruler-head {position:absolute;bottom:0;width:9px;height:7px;transform:translateX(-50%);background:var(--blue);clip-path:polygon(0 0,100% 0,100% 45%,50% 100%,0 45%)}
	.edit-ruler span { position:absolute; padding:3px 0 0 4px; border-left:1px solid var(--line); height:100%; font-size:10px; color:var(--quiet); font-variant-numeric:tabular-nums; }
	.edit-track { display:flex; border-bottom:1px solid var(--line); position:relative; overflow:hidden; }
	.edit-track button { display:flex; align-items:center; min-width:0; overflow:hidden; font-size:11px; text-align:left; border-radius:4px; flex-shrink:0; border:1px solid var(--surface); margin-block:1px; }
	.edit-clip-item { position:absolute; inset-block:0; min-width:0; }
	.edit-video-track button { width:100%; height:calc(100% - 2px); background:color-mix(in srgb,var(--canvas) 80%,var(--blue)); gap:6px; cursor:grab; }
	.edit-video-track img { width:56px; max-width:65%; height:100%; object-fit:cover; }
	.edit-video-track span { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
	.edit-trim { position:absolute; inset:3px auto 3px 0; width:min(8px,25%); border-radius:3px; cursor:ew-resize; touch-action:none; }
	.edit-trim.edge-end { inset-inline:auto 0; }
	.edit-trim:hover { background:color-mix(in srgb,var(--blue) 55%,transparent); }
	.edit-level {position:absolute;left:8px;right:8px;height:7px;cursor:ns-resize;touch-action:none}
	.edit-video-track .edit-level {overflow:visible}
	.level-value {position:absolute;right:9px;top:50%;transform:translateY(-50%);padding:1px 4px;border-radius:3px;color:white;background:#202020;font-size:10px;font-variant-numeric:tabular-nums;pointer-events:none}
	.edit-level::before {content:'';position:absolute;left:-8px;right:-8px;top:2px;pointer-events:none}
	.edit-level.lowered::before,.edit-level:hover::before,.edit-level:active::before {border-top:2px solid var(--blue)}
	.edit-clip-item {overflow:hidden}
	.edit-audio-track button { width:100%;position:absolute; inset-block:0; background:color-mix(in srgb,var(--canvas) 87%,#329477); }
	.edit-audio-track.muted button, .edit-audio-track button.muted { opacity:.4; }
	.edit-track button.chosen { border-color:var(--blue); }
	.edit-track button[data-key]:focus-visible { outline:none; box-shadow:inset 0 0 0 1px var(--blue); }
	.edit-track-grid:focus-visible { outline:none; box-shadow:none; }
	.edit-wave { display:block; width:100%; height:85%; padding:0 2px; fill:#57a48e; pointer-events:none; }
	.edit-caption-item { position:absolute; inset-block:0; overflow:hidden; }
	.edit-caption-track button { width:100%; height:calc(100% - 2px); white-space:nowrap; display:block; background:var(--canvas); border-color:var(--line); padding:0 min(9px,8%); text-overflow:ellipsis; cursor:grab; touch-action:none; }
	.edit-caption-track button:active { cursor:grabbing; }
	.edit-add-lane, .edit-track-labels .edit-add-lane-label { height:8px; position:relative; border:0; }
	.edit-add-lane.drop-target::after { content:''; position:absolute; inset:3px 0 auto; height:2px; background:var(--blue); pointer-events:none; }
	.edit-marquee { position:absolute; z-index:2; border:1px solid var(--blue); background:color-mix(in srgb,var(--blue) 18%,transparent); pointer-events:none; }
	.edit-playhead { position:absolute; top:0; bottom:0; width:1px; background:var(--blue); pointer-events:none; }
	.edit-drop-marker { position:absolute; inset-block:24px 0; width:2px; background:var(--foreground); pointer-events:none; z-index:1; }
	.edit-playhead::before { display:none; content:''; position:absolute; left:-4px; width:9px; height:7px; background:var(--blue); clip-path:polygon(0 0,100% 0,100% 45%,50% 100%,0 45%); }
	.edit-footer { display:flex; align-items:center; min-height:50px; gap:8px; padding:6px 14px; }
	.edit-footer .edit-downloads { margin-inline-start:auto; }
	:global(.edit-tools-trigger) { display:grid; place-items:center; width:34px; height:34px; border-radius:50%; }
	:global(.edit-tools-trigger:hover:not(:disabled)) { background:var(--surface); }
	:global(.edit-tools-trigger:disabled) { opacity:.4; }
	:global(.edit-tool-menu) { display:grid; grid-auto-flow:column; grid-auto-columns:calc((100% - 24px)/5); width:min(640px,calc(100vw - 24px)); gap:6px; overflow-x:auto; overscroll-behavior:contain; }
	:global(.edit-tool-card) { position:relative; overflow:hidden; aspect-ratio:4/5; background:var(--surface); cursor:pointer; }
	:global(.edit-tool-card[data-highlighted]) { box-shadow:inset 0 0 0 1px var(--quiet); }
	.edit-tool-poster { position:absolute; inset:0 0 auto; width:100%; height:61%; object-fit:cover; }
	.edit-tool-image { position:absolute; top:6px; left:6px; display:grid; place-items:center; width:26px; height:26px; border-radius:5px; color:white; background:rgb(0 0 0 / 65%); }
	.edit-tool-label { position:absolute; bottom:7px; left:8px; right:7px; text-align:left; font-size:13px; line-height:1.25; font-weight:500; }
	@media(max-width:767px) { :global(.edit-tool-menu) { grid-auto-columns:calc((100% - 12px)/3); } }







	.edit-downloads { display:flex; justify-content:flex-end; gap:5px; font-size:12px; color:var(--quiet); }
	.edit-file { display:inline-flex; align-items:center; gap:5px; min-height:29px; padding:0 7px; border-radius:6px; font-weight:500; }
	.edit-file:hover { background:var(--surface); color:var(--foreground); }
	@media (max-width: 767px) {
		.edit-shell, .edit-shell.has-media { grid-template-rows:auto auto minmax(0,1fr) auto auto; height:calc(100dvh - env(safe-area-inset-top,0px) - env(safe-area-inset-bottom,0px)); }
		.edit-header { padding-inline-start:4px; }
		.edit-export-progress { display:none; }
		.edit-mobile-tabs { display:flex; overflow-x:auto; min-height:37px; padding-inline:9px; }
		.edit-workbench { grid-row:3; grid-template-areas:"program"; grid-template-columns:minmax(0,1fr); }
		.edit-workbench > :not(.mobile-visible) { display:none; }
		.edit-side { grid-area:program; grid-template-rows:minmax(0,1fr); border:0; }
		.edit-tabs { display:none; }
		.edit-program { grid-template-rows:minmax(0,1fr) 39px; padding:8px 8px 0; }
		.edit-sequence { grid-row:4; padding-inline:8px; }
		.edit-timeline-frame { --track-label-width:101px; }
		.edit-sequence-toolbar { gap:5px; }
		.edit-footer { grid-row:5; grid-template-columns:minmax(0,1fr); gap:4px; padding:7px 8px 9px; }
	}
	@media (hover: none) {

	}
</style>
