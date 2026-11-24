<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { DropdownMenu } from 'bits-ui';
	import { toast } from 'svelte-sonner';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import Trash from '$lib/components/icons/Trash.svelte';
	import Upload from '$lib/components/icons/Upload.svelte';
	import type { I18nStore } from '$lib/i18n';
	import Modal from '$lib/components/common/Modal.svelte';
	import OrbitingSpheres from '$lib/components/common/OrbitingSpheres.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import VoiceMode from '$lib/components/icons/VoiceMode.svelte';
	import captureModule from '$lib/workers/haruCapture.js?url';

	export let show = true;
	const i18n = getContext<I18nStore>('i18n');
	let phase: 'connecting' | 'active' | 'ended' | 'error' = 'connecting';
	let status = 'Preparing Neve...';
	const languagePreference = 'neveai.voice.language';
	const languages = [
		{ value: 'pt', label: 'Portuguese' },
		{ value: 'en', label: 'English' }
	] as const;
	let language: 'pt' | 'en' = 'pt';
	const roundControlClass = 'grid size-11 shrink-0 place-items-center rounded-full bg-gray-100 hover:bg-gray-200 disabled:opacity-50 dark:bg-gray-800 dark:hover:bg-gray-700';
	const headerControlClass = 'grid size-8 shrink-0 place-items-center rounded-lg p-0 text-gray-500 hover:bg-gray-100 disabled:opacity-50 dark:text-gray-400 dark:hover:bg-gray-800';
	let muted = false;
	let disposed = false;
	let microphoneReady = false;
	let audio: AudioContext;
	let chime: AudioBufferSourceNode | undefined;
	let mic: MediaStream;
	let source: MediaStreamAudioSourceNode;
	let capture: AudioNode;
	let worklet: AudioWorkletNode | undefined;
	let captureWatchdog: ReturnType<typeof setTimeout> | undefined;
	let recoverCapture: (() => void) | undefined;
	let socket: WebSocket;
	let playbackRate = 24000;
	let playbackEnd = 0;
	let sentSeconds = 0;
	let heardSeconds = 0;
	let outputMeter: AnalyserNode;
	const outputSamples = new Float32Array(1024);
	let waveform: number[] | null = null;
	let waveformFrame = 0;
	let waveformUntil = 0;
	let lastPaint = 0;
	const playing = new Set<AudioBufferSourceNode>();
	const voiceProfileUrl = '/api/v1/audio/voice/profile';
	const profileRequest = new AbortController();
	let importInput: HTMLInputElement;
	let customVoice = false;
	let profileOperation: 'POST' | 'DELETE' | undefined;
	let reconfiguring = false;
	let profileNotice = '';
	let stopAck: (() => void) | undefined;

	async function voiceProfile(method = 'GET', file?: File) {
		const headers = localStorage.token ? { Authorization: `Bearer ${localStorage.token}` } : undefined;
		const body = file ? new FormData() : undefined;
		if (file) body?.append('file', file);
		const response = await fetch(voiceProfileUrl, { method, headers, body, signal: profileRequest.signal });
		const result = await response.json();
		if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not update the voice.');
		if (!disposed && (method !== 'GET' || !profileOperation)) customVoice = result.custom === true;
	}

	async function restartConversation(update: () => Promise<void>) {
		if (reconfiguring || phase === 'connecting') return;
		reconfiguring = true;
		profileNotice = '';
		const resume = phase === 'active' && socket.readyState === WebSocket.OPEN;
		let stopped = false;
		try {
			if (resume) {
				phase = 'connecting';
				status = 'Preparing Neve...';
				releaseGraph();
				await stopRuntime();
				stopped = true;
			}
			await update();
		} catch (error) {
			if (!disposed) {
				profileNotice = error instanceof Error ? error.message : 'Could not update the voice.';
				if (resume && !stopped) fail('Could not start or continue voice mode.');
			}
		} finally {
			if (stopped && !disposed && socket.readyState === WebSocket.OPEN) beginConversation();
			reconfiguring = false;
		}
	}

	async function changeVoice(method: 'POST' | 'DELETE', file?: File) {
		if (reconfiguring || phase === 'connecting') return;
		profileOperation = method;
		try {
			await restartConversation(() => voiceProfile(method, file));
		} finally {
			profileOperation = undefined;
			if (importInput) importInput.value = '';
		}
	}

	function changeLanguage(value: string) {
		if ((value !== 'pt' && value !== 'en') || language === value) return;
		void restartConversation(async () => {
			language = value;
			localStorage.setItem(languagePreference, value);
		});
	}

	function stopRuntime() {
		return new Promise<void>((resolve, reject) => {
			const timeout = setTimeout(() => {
				stopAck = undefined;
				reject(new Error('Could not update the voice.'));
			}, 8000);
			stopAck = () => {
				clearTimeout(timeout);
				stopAck = undefined;
				resolve();
			};
			socket.send('stop');
		}).then(() => {
			if (disposed || socket.readyState !== WebSocket.OPEN || phase !== 'connecting') {
				throw new Error('Could not update the voice.');
			}
		});
	}

	function beginConversation() {
		clearTimeout(captureWatchdog);
		playbackEnd = 0;
		waveformUntil = 0;
		sentSeconds = 0;
		heardSeconds = 0;
		socket.send(JSON.stringify({
			sample_rate: audio.sampleRate, language
		}));
	}

	function releaseGraph() {
		clearTimeout(captureWatchdog);
		recoverCapture = undefined;
		cancelAnimationFrame(waveformFrame);
		waveformFrame = 0;
		waveform = null;
		if (worklet) {
			worklet.port.onmessage = null;
			worklet.onprocessorerror = null;
			worklet = undefined;
		} else if (capture) {
			(capture as ScriptProcessorNode).onaudioprocess = null;
		}
		capture?.disconnect();
		source?.disconnect();
		outputMeter?.disconnect();
		for (const node of playing) node.stop();
		playing.clear();
	}

	function playChime(opening: boolean) {
		chime?.stop();
		const rate = 24000;
		const buffer = audio.createBuffer(1, rate / 4, rate);
		const samples = buffer.getChannelData(0);
		const notes = opening ? [440, 659.25] : [659.25, 440];
		for (const [index, pitch] of notes.entries()) {
			const offset = index * 1800;
			for (let i = 0; i < 4200; i++) {
				const time = i / rate;
				const level = time < 0.02 ? 0.065 * time / 0.02 : 0.065 * Math.exp(-33 * (time - 0.02));
				samples[offset + i] += Math.sin(time * 2 * Math.PI * pitch) * level *
					Math.min(1, (4200 - i) / 120);
			}
		}
		const node = audio.createBufferSource();
		chime = node;
		node.buffer = buffer;
		node.connect(audio.destination);
		return new Promise<void>((resolve) => {
			const finish = () => {
				clearTimeout(timeout);
				node.onended = null;
				node.disconnect();
				if (chime === node) chime = undefined;
				// The audio device can still have samples queued after the source ends.
				const drain = ((audio.baseLatency || 0) + (audio.outputLatency || 0)) * 1000;
				setTimeout(resolve, Math.min(100, Math.max(20, drain)));
			};
			const timeout = setTimeout(finish, 500);
			node.onended = finish;
			node.start(audio.currentTime + (opening ? 0.045 : 0.01));
		});
	}

	function cleanup(withChime = false) {
		if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
		stopAck?.();
		releaseGraph();
		mic?.getTracks().forEach(track => track.stop());
		if (audio && audio.state !== 'closed') {
			const closeAudio = () => void audio.close().catch(() => {});
			if (withChime && audio.state === 'running') {
				void playChime(false).finally(closeAudio);
			} else closeAudio();
		}
	}

	function fail(message: string) {
		if (disposed || phase === 'error') return;
		status = message;
		phase = 'error';
		cleanup();
	}

	function paintWaveform(now: number) {
		waveformFrame = 0;
		if (audio.currentTime > waveformUntil || phase !== 'active') {
			waveform = null;
			return;
		}
		if (now - lastPaint >= 30) {
			lastPaint = now;
			outputMeter.getFloatTimeDomainData(outputSamples);
			const levels = [];
			let total = 0;
			const width = Math.floor(outputSamples.length / 5);
			for (let bar = 0; bar < 5; bar++) {
				let energy = 0;
				for (let i = bar * width; i < (bar + 1) * width; i++) energy += outputSamples[i] ** 2;
				const rms = Math.sqrt(energy / width);
				total += rms;
				const scale = Math.min(1.55, 0.5 + 29 * rms);
				levels.push(scale);
			}
			waveform = total > 0.0015 ? levels : null;
		}
		waveformFrame = requestAnimationFrame(paintWaveform);
	}

	function play(frame: ArrayBuffer) {
		if (frame.byteLength % 2 || !frame.byteLength || phase !== 'active') return;
		const samples = new DataView(frame);
		const buffer = audio.createBuffer(1, frame.byteLength / 2, playbackRate);
		const channel = buffer.getChannelData(0);
		let peak = 0;
		for (let i = 0; i < channel.length; i++) {
			channel[i] = samples.getInt16(i * 2, true) / 32768;
			peak = Math.max(peak, Math.abs(channel[i]));
		}
		heardSeconds += buffer.duration;
		if (playbackEnd > audio.currentTime + 0.9) return fail('Voice playback fell behind.');
		const node = audio.createBufferSource();
		node.buffer = buffer;
		node.connect(outputMeter);
		playing.add(node);
		node.onended = () => { playing.delete(node); node.disconnect(); };
		if (playbackEnd < audio.currentTime) playbackEnd = audio.currentTime + 0.055;
		node.start(playbackEnd);
		playbackEnd += buffer.duration;
		if (peak >= 0.001) {
			waveformUntil = playbackEnd + 0.04;
			if (!waveformFrame) waveformFrame = requestAnimationFrame(paintWaveform);
		}
	}

	function attachCapture(workletReady: boolean) {
		outputMeter = audio.createAnalyser();
		outputMeter.fftSize = outputSamples.length;
		outputMeter.connect(audio.destination);
		source = audio.createMediaStreamSource(mic);
		const send = (frame: ArrayBuffer) => {
			if (socket?.readyState !== WebSocket.OPEN || phase !== 'active') return;
			clearTimeout(captureWatchdog);
			if (sentSeconds - heardSeconds > 1.5 || socket.bufferedAmount > audio.sampleRate * 2) {
				fail('Voice playback fell behind.');
				return;
			}
			sentSeconds += frame.byteLength / (2 * audio.sampleRate);
			socket.send(frame);
		};
		const attachFallback = () => {
			clearTimeout(captureWatchdog);
			recoverCapture = undefined;
			const fallback = audio.createScriptProcessor(2048, 1, 1);
			fallback.onaudioprocess = ({ inputBuffer, outputBuffer }) => {
				outputBuffer.getChannelData(0).fill(0);
				const samples = inputBuffer.getChannelData(0);
				const frame = new ArrayBuffer(samples.length * 2);
				const pcm = new DataView(frame);
				if (!muted) for (let i = 0; i < samples.length; i++) {
					const value = Math.max(-1, Math.min(1, samples[i]));
					pcm.setInt16(2 * i, value * (value < 0 ? 32768 : 32767), true);
				}
				send(frame);
			};
			fallback.connect(audio.destination);
			capture = fallback;
			source.connect(capture);
		};
		if (!workletReady) {
			attachFallback();
			return;
		}
		try {
			const node = new AudioWorkletNode(audio, 'haru-capture', { numberOfOutputs: 0, channelCount: 1 });
			worklet = node;
			node.port.onmessage = ({ data }: MessageEvent<ArrayBuffer>) => send(data);
			node.port.postMessage(muted);
			capture = node;
			recoverCapture = () => {
				if (disposed || worklet !== node) return;
				node.port.onmessage = null;
				node.onprocessorerror = null;
				node.disconnect();
				source.disconnect(node);
				worklet = undefined;
				try { attachFallback(); }
				catch { fail('Microphone access was not available.'); }
			};
			node.onprocessorerror = recoverCapture;
			source.connect(node);
		} catch {
			worklet?.disconnect();
			worklet = undefined;
			attachFallback();
		}
	}

	async function start() {
		let stream: MediaStream | undefined;
		try {
			stream = await navigator.mediaDevices?.getUserMedia?.({
				audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
			});
		} catch {
			// The microphone can be absent, unavailable, or blocked by permissions.
		}
		const hasMicrophone = stream?.getAudioTracks().some(track => track.readyState === 'live');
		if (disposed || !stream || !hasMicrophone) {
			stream?.getTracks().forEach(track => track.stop());
			if (!disposed) {
				toast.error($i18n.t('Microphone access was not available.'));
				show = false;
			}
			return;
		}

		mic = stream;
		for (const track of mic.getAudioTracks()) {
			track.addEventListener('ended', () => fail('Microphone access was not available.'), {once: true});
		}
		microphoneReady = true;
		void voiceProfile().catch(() => {});
		try {
			audio = new AudioContext({ latencyHint: 'interactive' });
			await audio.resume();
			if (disposed) return;
			await playChime(true);
			if (disposed) return;
			let workletReady = false;
			if (audio.audioWorklet && window.AudioWorkletNode) {
				let timeout: ReturnType<typeof setTimeout> | undefined;
				try {
					workletReady = await Promise.race([
						audio.audioWorklet.addModule(captureModule).then(() => true),
						new Promise<false>(resolve => { timeout = setTimeout(() => resolve(false), 1500); })
					]);
				} catch {
					// Some devices cannot start the worklet; fall back to short PCM buffers.
				} finally {
					clearTimeout(timeout);
				}
			}
			if (disposed) return;
			const url = new URL('/api/v1/audio/voice', window.location.href);
			url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
			socket = new WebSocket(url);
			socket.binaryType = 'arraybuffer';
			socket.onopen = beginConversation;
			socket.onclose = () => { if (phase !== 'ended') fail('Could not start or continue voice mode.'); };
			socket.onmessage = ({ data }) => {
				if (disposed) return;
				if (data instanceof ArrayBuffer) { play(data); return; }
				const event = JSON.parse(data);
				if (event.type === 'stopped') { stopAck?.(); return; }
				if (event.type === 'error') fail(event.message);
				if (event.type === 'end') { phase = 'ended'; status = 'Voice session ended.'; cleanup(); }
				if (event.type === 'started') {
					playbackRate = event.sample_rate;
					try { attachCapture(workletReady); }
					catch { fail('Microphone access was not available.'); return; }
					phase = 'active';
					status = 'Go ahead...';
					if (recoverCapture) {
						clearTimeout(captureWatchdog);
						captureWatchdog = setTimeout(() => recoverCapture?.(), 900);
					}
				}
			};
		} catch {
			fail('Could not start or continue voice mode.');
		}
	}

	function toggleMute() {
		muted = !muted;
		worklet?.port.postMessage(muted);
	}

	onMount(() => {
		language = localStorage.getItem(languagePreference) === 'en' ? 'en' : 'pt';
		void start();
		return () => { disposed = true; profileRequest.abort(); cleanup(true); };
	});
</script>

{#snippet languageIcon()}
	<svg class="block size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"
		stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
		<path d="m5 8 6 6M4 14l6-6 2-3M2 5h12M7 2v3m15 17-5-10-5 10m2-4h6" />
	</svg>
{/snippet}

{#snippet endControl()}
	<Tooltip content={$i18n.t('End voice mode')}>
		<button type="button" aria-label={$i18n.t('End voice mode')}
			class="grid size-11 shrink-0 place-items-center rounded-full bg-red-600 text-white hover:bg-red-700"
			on:click={() => show = false}>
			<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
				stroke-width="1.9" stroke-linecap="round" aria-hidden="true">
				<path d="m7 7 10 10M17 7 7 17" />
			</svg>
		</button>
	</Tooltip>
{/snippet}

{#snippet muteControl()}
	<Tooltip content={$i18n.t(muted ? 'Unmute microphone' : 'Mute microphone')}>
		<button type="button" aria-label={$i18n.t(muted ? 'Unmute microphone' : 'Mute microphone')}
			aria-pressed={muted} class={roundControlClass} on:click={toggleMute}>
			<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true">
				<rect x="9" y="3" width="6" height="12" rx="3" />
				<path d="M5 11v1a7 7 0 0 0 14 0v-1M12 19v3" />
				{#if muted}<path d="M3 3l18 18" />{/if}
			</svg>
		</button>
	</Tooltip>
{/snippet}

{#if microphoneReady}
<Modal bind:show size="w-[28.5rem]" animated={false}>
	<div class="flex flex-col items-center gap-5 px-3 pb-10 pt-2">
		<h2 class="sr-only">{$i18n.t('Voice mode')}</h2>
		<div class="flex min-h-10 w-full items-center justify-between gap-2">
			<div class="size-8 shrink-0">
				{#if phase !== 'connecting' && !profileOperation}
					<DropdownMenu.Root portal={null} preventScroll={false}>
						<DropdownMenu.Trigger aria-label={$i18n.t('Voice language')} class={headerControlClass}>
							{@render languageIcon()}
						</DropdownMenu.Trigger>
						<DropdownMenu.Content align="start" side="bottom" sideOffset={6} strategy="fixed"
							class="z-[10002] min-w-36 rounded-md border border-gray-100 bg-white p-1 text-sm text-gray-700 shadow-md dark:border-gray-800 dark:bg-gray-850 dark:text-gray-200">
							<DropdownMenu.RadioGroup value={language} onValueChange={changeLanguage}>
								{#each languages as option (option.value)}
									<DropdownMenu.RadioItem value={option.value}
										class="flex cursor-pointer items-center justify-between gap-3 rounded-sm px-3 py-1.5 outline-none data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-800">
										{$i18n.t(option.label)}
										<span class="size-3.5 shrink-0">{#if language === option.value}<CheckCircle className="size-3.5" />{/if}</span>
									</DropdownMenu.RadioItem>
								{/each}
							</DropdownMenu.RadioGroup>
						</DropdownMenu.Content>
					</DropdownMenu.Root>
				{/if}
			</div>
			<div class="flex shrink-0 items-center gap-1">
				<input bind:this={importInput} type="file" accept=".wav,.mp3,.flac,.ogg" hidden
					on:change={(event) => {
						const file = event.currentTarget.files?.[0];
						if (file) void changeVoice('POST', file);
					}} />
				{#if customVoice}
					<Tooltip content={$i18n.t('Remove voice')}>
						<button type="button" aria-label={$i18n.t('Remove voice')} disabled={!!profileOperation || phase === 'connecting'}
							class="grid size-8 place-items-center rounded-md text-gray-500 hover:bg-gray-100 disabled:opacity-50 dark:text-gray-400 dark:hover:bg-gray-800"
							on:click={() => changeVoice('DELETE')}><Trash className="size-4" /></button>
					</Tooltip>
				{/if}
				{#if phase === 'connecting' || profileOperation === 'POST'}
					<span class="size-8 shrink-0" aria-hidden="true"></span>
				{:else}
				<Tooltip content={$i18n.t(customVoice ? 'Replace voice' : 'Import voice')}>
					<button type="button" aria-label={$i18n.t(customVoice ? 'Replace voice' : 'Import voice')} disabled={!!profileOperation || phase === 'connecting'}
						class={headerControlClass}
						on:click={() => importInput.click()}>
						{#if profileOperation}<OrbitingSpheres className="size-5" />{:else}<Upload className="block size-5" />{/if}
					</button>
				</Tooltip>
				{/if}
			</div>
		</div>
		<div data-haru-waveform class="grid size-26 place-items-center rounded-full bg-gray-100 dark:bg-gray-800">
			{#if phase === 'connecting'}<OrbitingSpheres />{:else}<VoiceMode className="size-[3.5rem]" levels={waveform} />{/if}
		</div>
		{#if profileNotice}
			<p role="alert" class="max-w-full text-center text-xs text-red-500">{$i18n.t(profileNotice)}</p>
		{/if}
		<div class="grid w-full max-w-[18.5rem] grid-cols-[3.5rem_minmax(0,1fr)_3.5rem] grid-rows-[minmax(1.75rem,auto)_2.75rem] items-center gap-x-1"
			class:gap-y-4={phase === 'error' && status === 'Voice mode gives priority to chat and media generation.'}>
			<div class="row-start-2 {phase !== 'active' ? 'col-start-2 justify-self-center' : 'col-start-1 justify-self-start'}">
				{@render endControl()}
			</div>
			<div class="relative flex min-w-0 items-center justify-center text-center {phase !== 'active' ? 'col-span-3 col-start-1 row-start-1' : 'col-start-2 row-start-2'}"
				class:translate-y-2={phase === 'active'}>
				{#if phase === 'active'}
					<span class="absolute bottom-full mb-2 w-max text-xs text-gray-500 dark:text-gray-400 max-[375px]:mb-0.5">{$i18n.t(customVoice ? 'Imported voice' : 'Default voice')}</span>
				{/if}
					<p role="status" class="max-w-60 break-words {phase === 'active' && profileOperation !== 'POST' ? 'text-[0.9375rem]' : 'text-sm'} text-gray-600 dark:text-gray-300"
					class:-translate-y-2={phase === 'connecting'}>{$i18n.t(profileOperation === 'POST' ? 'Cloning voice...' : phase === 'active' && muted ? 'Muted.' : status)}</p>
			</div>
			{#if phase === 'active'}
				<div class="col-start-3 row-start-2 justify-self-end">
					{@render muteControl()}
				</div>
			{/if}
		</div>
	</div>
</Modal>
{/if}
