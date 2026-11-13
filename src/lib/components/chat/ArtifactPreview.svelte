<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { artifactAssetBase } from '$lib/utils/artifacts/assets';
	import { artifactPanelActive } from '$lib/stores';
	import { ArtifactCompiler } from '$lib/utils/artifacts/compiler';
	import type { ArtifactResult } from '$lib/utils/artifactResults';
	import type { PreviewPacket } from '$lib/utils/artifacts/types';

	export let artifact: ArtifactResult;
	export let requestedCode: string | null = null;
	export let running: boolean | undefined = undefined;
	export let iframeElement: HTMLIFrameElement;
	export let allowForms = false;
	let mounted = false;
	let active = false;
	let channel: MessageChannel;
	let connected = false;
	let compiler: ArtifactCompiler;
	let compiling = false;
	let pending = false;
	let timer: ReturnType<typeof setTimeout>;
	let packet: PreviewPacket | null = null;
	let error = '';
	let page: string | undefined;
	let session = '';
	let generation = 0;
	let lastRequestedCode: string | null | undefined;
	let srcdoc = '';

	function connect() {
		channel?.port1.close();
		connected = false;
		channel = new MessageChannel();
		channel.port1.onmessage = ({ data }) => {
			if (data.type === 'ready') {
				connected = true;
				channel.port1.postMessage({
					type: 'live',
					value: active && (running ?? artifact.live === true)
				});
				send();
			}
			if (data.type === 'error') error = String(data.message).slice(0, 500);
			if (
				data.type === 'navigate' &&
				artifact.files?.some((file) => file.path === data.path && file.language === 'html')
			) {
				page = data.path;
				schedule(artifact);
			}
		};
		channel.port1.start();
		iframeElement.contentWindow?.postMessage({ type: 'neve-preview-connect' }, '*', [
			channel.port2
		]);
	}
	function send() {
		if (!active || !connected || !packet) return;
		channel.port1.postMessage({ type: 'page', path: page ?? artifact.entry ?? 'index.html' });
		channel.port1.postMessage({
			type: 'update',
			packet: { ...packet, live: running ?? artifact.live === true }
		});
	}
	function schedule(value: ArtifactResult, code = requestedCode, isRunning = running) {
		if (!mounted || !active) {
			pending = true;
			return;
		}
		if (connected)
			channel.port1.postMessage({ type: 'live', value: isRunning ?? value.live === true });
		if (session !== value.id) {
			session = value.id;
			lastRequestedCode = undefined;
			page = undefined;
			packet = null;
			error = '';
			connected = false;
			compiler?.destroy();
			compiler = new ArtifactCompiler();
			generation++;
			const assets = artifactAssetBase();
			srcdoc = `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><script>window.__neveAssets=${JSON.stringify(assets)}<\/script><script src="${assets}/frame.js"><\/script></head><body></body></html>`;
		}
		if (lastRequestedCode !== code) {
			page = code
				? value.files?.find((file) => file.language === 'html' && file.content.includes(code))?.path
				: undefined;
			lastRequestedCode = code;
		}
		pending = true;
		if (!compiling && !timer) timer = setTimeout(update, 120);
	}
	async function update() {
		timer = null;
		if (!mounted || !active || compiling) return;
		pending = false;
		compiling = true;
		const revision = generation;
		const current = artifact;
		try {
			const result = await compiler.compile(current, page);
			if (mounted && active && revision === generation) {
				packet = result;
				error = '';
				send();
			}
		} catch (cause) {
			// An unfinished expression must not replace the last executable preview.
			if (mounted && active && revision === generation && !current.live)
				error = String(cause.message ?? cause).slice(0, 500);
		} finally {
			compiling = false;
			if (mounted && active && pending) timer = setTimeout(update, 120);
		}
	}
	function setActivity(value: boolean) {
		if (active === value) return;
		active = value;
		if (connected)
			channel.port1.postMessage({
				type: 'live',
				value: active && (running ?? artifact.live === true)
			});
		if (!active) {
			clearTimeout(timer);
			timer = null;
			pending = true;
			generation++;
			compiler?.destroy();
			compiler = null;
		} else {
			compiler ??= new ArtifactCompiler();
			schedule(artifact);
		}
	}
	$: setActivity(mounted && $artifactPanelActive);
	$: schedule(artifact, requestedCode, running);
	onMount(() => {
		mounted = true;
		setActivity($artifactPanelActive);
	});
	onDestroy(() => {
		mounted = false;
		clearTimeout(timer);
		compiler?.destroy();
		channel?.port1.close();
	});
</script>

<div class="relative h-full w-full overflow-hidden" data-artifact-preview>
	{#key session}
		<iframe
			bind:this={iframeElement}
			title="Content"
			{srcdoc}
			on:load={connect}
			class="h-full w-full border-0 bg-white"
			sandbox="allow-scripts allow-downloads{allowForms ? ' allow-forms' : ''}"
			referrerpolicy="no-referrer"
		></iframe>
	{/key}
	{#if error}
		<div
			role="status"
			class="absolute bottom-3 left-3 right-3 max-h-24 overflow-auto rounded-lg border border-red-200 bg-white/95 px-3 py-2 text-xs text-red-700 shadow-sm dark:border-red-900 dark:bg-gray-900/95 dark:text-red-300"
		>
			{error}
		</div>
	{/if}
</div>
