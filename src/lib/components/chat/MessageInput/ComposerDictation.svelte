<script module lang="ts">
	export async function openDictationRecorder() {
		const formats = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'];
		const mimeType = typeof MediaRecorder === 'undefined'
			? undefined
			: formats.find((format) => MediaRecorder.isTypeSupported(format));
		if (!mimeType) throw new Error('Audio recording is not available');
		const media = await navigator.mediaDevices.getUserMedia({
			audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }
		});
		try {
			if (!media.getAudioTracks().some((track) => track.readyState === 'live')) {
				throw new Error('No live microphone track');
			}
			return new MediaRecorder(media, { mimeType, audioBitsPerSecond: 48000 });
		} catch (error) {
			media.getTracks().forEach((track) => track.stop());
			throw error;
		}
	}
</script>

<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { transcribeDictation } from '$lib/apis/audio';
	import Check from '$lib/components/icons/Check.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import OrbitingSpheres from '$lib/components/common/OrbitingSpheres.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	export let compact: boolean;
	export let composer: HTMLElement;
	export let onClose: (text?: string) => void;
	export let recorder: MediaRecorder;

	const i18n = getContext('i18n');
	const request = new AbortController();
	let phase: 'requesting' | 'recording' | 'recorded' | 'transcribing' = 'requesting';
	let cancelButton: HTMLButtonElement;
	let panel: HTMLDivElement;
	let canvas: HTMLCanvasElement;
	let audio: AudioContext;
	let animation = 0;
	let recordingLimit: ReturnType<typeof setTimeout>;
	let recording: Promise<Blob | undefined>;
	let resolveRecording: (blob?: Blob) => void;

	function stopMeter() {
		clearTimeout(recordingLimit);
		cancelAnimationFrame(animation);
		recorder.stream.getTracks().forEach((track) => track.stop());
		if (audio && audio.state !== 'closed') void audio.close().catch(() => {});
	}

	function dispose() {
		request.abort();
		if (recorder && recorder.state !== 'inactive') recorder.stop();
		resolveRecording?.();
		stopMeter();
	}

	function close(text?: string) {
		if (request.signal.aborted) return;
		dispose();
		onClose(text);
	}

	function startMeter() {
		if (!window.AudioContext || !canvas) return;
		audio = new AudioContext();
		void audio.resume().catch(() => {});
		const analyser = audio.createAnalyser();
		analyser.fftSize = 512;
		audio.createMediaStreamSource(recorder.stream).connect(analyser);
		const samples = new Uint8Array(analyser.fftSize);
		const ctx = canvas.getContext('2d');
		if (!ctx) return;
		const color = getComputedStyle(canvas).color;
		function draw() {
			const { clientWidth, clientHeight } = canvas;
			const dpr = window.devicePixelRatio || 1;
			const width = Math.round(clientWidth * dpr);
			const height = Math.round(clientHeight * dpr);
			if (canvas.width !== width || canvas.height !== height) {
				canvas.width = width;
				canvas.height = height;
			}
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
			ctx.clearRect(0, 0, clientWidth, clientHeight);
			ctx.fillStyle = color;
			analyser.getByteTimeDomainData(samples);
			const bars = Math.max(1, Math.floor(clientWidth / 4.5));
			for (let bar = 0; bar < bars; bar++) {
				const from = Math.floor(bar * samples.length / bars);
				const to = Math.floor((bar + 1) * samples.length / bars);
				let amplitude = 0;
				for (let i = from; i < to; i++) amplitude = Math.max(amplitude, Math.abs(samples[i] - 128));
				const length = Math.min(clientHeight, 4 + amplitude * 0.4);
				ctx.fillRect(bar * clientWidth / bars, (clientHeight - length) / 2, 1.5, length);
			}
			animation = requestAnimationFrame(draw);
		}
		draw();
	}

	function start() {
		try {
			const chunks: Blob[] = [];
			recording = new Promise((resolve) => { resolveRecording = resolve; });
			recorder.ondataavailable = ({ data }) => {
				if (data.size && !request.signal.aborted) chunks.push(data);
			};
			recorder.onstop = () => {
				stopMeter();
				resolveRecording(chunks.length ? new Blob(chunks, { type: recorder.mimeType }) : undefined);
				if (phase === 'recording') phase = 'recorded';
			};
			recorder.onerror = () => {
				if (request.signal.aborted) return;
				toast.error($i18n.t('Could not transcribe dictation.'));
				close();
			};
			recorder.start(1000);
			phase = 'recording';
			recordingLimit = setTimeout(() => {
				if (recorder.state === 'recording') recorder.stop();
			}, 90_000);
			try { startMeter(); } catch { /* A visual meter is optional. */ }
		} catch {
			if (request.signal.aborted) return;
			toast.error($i18n.t('Microphone access was not available.'));
			close();
		}
	}

	async function confirm() {
		if (phase !== 'recording' && phase !== 'recorded') return;
		phase = 'transcribing';
		try {
			if (recorder.state !== 'inactive') recorder.stop();
			const clip = await recording;
			if (request.signal.aborted) return;
			const extension = clip?.type.split(/[;/]/)[1] || 'webm';
			const text = clip && await transcribeDictation(
				new File([clip], `dictation.${extension}`, { type: clip.type }),
				$i18n.language,
				request.signal
			);
			if (request.signal.aborted) return;
			if (!text) toast.info($i18n.t('No speech was detected.'));
			close(text);
		} catch {
			if (request.signal.aborted) return;
			toast.error($i18n.t('Could not transcribe dictation.'));
			close();
		}
	}

	function handleEscape(event: KeyboardEvent) {
		if (event.key !== 'Escape') return;
		event.stopPropagation();
		event.preventDefault();
		close();
	}

	onMount(() => {
		const alignActions = () => {
			const button = composer.querySelector<HTMLElement>('#send-message-button');
			if (!button) return;
			const outer = composer.getBoundingClientRect();
			const bounds = button.getBoundingClientRect();
			const onLeft = bounds.left + bounds.width / 2 < outer.left + outer.width / 2;
			panel.style.setProperty('--dictation-action-size', `${bounds.width}px`);
			panel.style.setProperty('--dictation-action-bottom', compact ? `${outer.bottom - bounds.bottom}px` : '10px');
			panel.style.setProperty('--dictation-action-edge', `${onLeft ? bounds.left - outer.left : outer.right - bounds.right}px`);
			panel.classList.toggle('actions-reversed', onLeft);
		};
		const observer = new ResizeObserver(alignActions);
		observer.observe(composer);
		window.addEventListener('resize', alignActions);
		alignActions();
		cancelButton.focus({ preventScroll: true });
		void start();
		return () => {
			observer.disconnect();
			window.removeEventListener('resize', alignActions);
			dispose();
		};
	});
</script>

<div bind:this={panel} class="dictation" data-composer-dictation role="group" aria-label={$i18n.t('Dictate')}>
	<div role="status" class:sr-only={compact} class="dictation-status">
		{#if phase === 'recording'}
			{$i18n.t('Listening...', { context: 'dictation' })}
		{:else if phase === 'transcribing'}
			{$i18n.t('Transcribing...')}
		{:else if phase === 'recorded'}
			{$i18n.t('Recording finished.')}
		{/if}
	</div>
	<div class="dictation-actions">
		<Tooltip content={$i18n.t('Cancel')}>
			<button bind:this={cancelButton} type="button" aria-label={$i18n.t('Cancel')} on:click={() => close()} on:keydown={handleEscape}
				class="grid size-8 shrink-0 place-items-center rounded-full hover:bg-black/5 dark:hover:bg-white/10">
				<XMark className="size-4" />
			</button>
		</Tooltip>
		<div class="dictation-wave" aria-hidden="true">
			<canvas bind:this={canvas}></canvas>
		</div>
		<Tooltip content={$i18n.t('Confirm')}>
			<button type="button" aria-label={$i18n.t('Confirm')} on:click={confirm} on:keydown={handleEscape}
				disabled={phase === 'requesting' || phase === 'transcribing'}
				class="grid size-8 shrink-0 place-items-center rounded-full bg-black p-0 text-white enabled:hover:bg-gray-900 dark:bg-white dark:text-black dark:enabled:hover:bg-gray-100"
				class:opacity-60={phase === 'transcribing'}>
				{#if phase === 'transcribing'}<OrbitingSpheres className="size-4" />
				{:else}<Check className="size-[18px]" />{/if}
			</button>
		</Tooltip>
	</div>
</div>

<style>
	.dictation {
		position: absolute;
		inset: 0;
		z-index: 41;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		padding: 0.625rem 0.75rem 0.5rem;
	}
	.dictation-status { align-self: flex-start; padding: 0.375rem 0.25rem; font-size: 0.875rem; opacity: 0.65; }
	.dictation-actions {
		position: absolute;
		bottom: var(--dictation-action-bottom, 0.5rem);
		left: 0.75rem;
		right: var(--dictation-action-edge, 0.75rem);
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	.dictation:global(.actions-reversed) .dictation-actions {
		direction: rtl;
		left: var(--dictation-action-edge, 0.75rem);
		right: 0.75rem;
	}
	.dictation-actions button {
		width: var(--dictation-action-size, 36px);
		height: var(--dictation-action-size, 36px);
	}
	.dictation-wave {
		flex: 1 1 0;
		min-width: 0;
		mask-image: linear-gradient(90deg, transparent, black 8%, black 92%, transparent);
	}
	canvas { display: block; width: 100%; height: 1.125rem; }
	@media (max-width: 767px) {
		.dictation-actions { gap: 0.5rem; }
	}
</style>
