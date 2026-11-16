<script lang="ts">
	import { getContext } from 'svelte';
	import { autoUpdate, computePosition, flip, offset, shift } from '@floating-ui/dom';
	import type { I18nStore } from '$lib/i18n';
	import Info from '$lib/components/icons/ModelInfo.svelte';

	const i18n = getContext<I18nStore>('i18n');
	export let modelId: string;
	export let openId: string | null = null;
	export let active = true;
	export let description = '';
	export let size = '';
	export let onOpen: () => void = () => {};
	let button: HTMLButtonElement;
	$: shown = active && openId === modelId;
	$: panelId = `neve-model-information-${encodeURIComponent(modelId)}`;

	function close() { if (openId === modelId) openId = null; }
	function open() { if (active) { openId = modelId; onOpen(); } }
	function anchorLifetime(_element: HTMLElement) { return { destroy: close }; }
	function floatingPanel(node: HTMLElement) {
		let disposed = false, revision = 0;
		document.body.appendChild(node);
		const update = async () => {
			const current = ++revision;
			if (!button?.isConnected) { close(); return; }
			const { x, y } = await computePosition(button, node, {
				strategy: 'fixed', placement: 'bottom-end', middleware: [offset(5), flip(), shift({ padding: 8 })]
			});
			if (!disposed && current === revision) Object.assign(node.style, { left: `${x}px`, top: `${y}px`, visibility: 'visible' });
		};
		const cleanup = autoUpdate(button, node, update, { ancestorScroll: false });
		const outside = (event: PointerEvent) => { if (!button.contains(event.target as Node)) close(); };
		const move = (event: PointerEvent) => { if (event.pointerType !== 'touch') outside(event); };
		const key = (event: KeyboardEvent) => {
			if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); close(); }
		};
		window.addEventListener('pointermove', move, true);
		window.addEventListener('pointerdown', outside, true);
		window.addEventListener('scroll', close, true);
		window.addEventListener('blur', close);
		window.addEventListener('resize', close);
		window.addEventListener('keydown', key, true);
		return { destroy() {
			disposed = true; cleanup();
			window.removeEventListener('pointermove', move, true);
			window.removeEventListener('pointerdown', outside, true);
			window.removeEventListener('scroll', close, true);
			window.removeEventListener('blur', close);
			window.removeEventListener('resize', close);
			window.removeEventListener('keydown', key, true);
			node.remove();
		} };
	}
</script>

<button
	bind:this={button} use:anchorLifetime type="button"
	aria-label={$i18n.t('Model information')} aria-describedby={shown ? panelId : undefined}
	class="order-first grid size-7 shrink-0 place-items-center rounded-md p-0 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
	on:pointerenter={(event) => { if (event.pointerType !== 'touch') open(); }}
	on:pointerleave={(event) => { if (event.pointerType !== 'touch') close(); }}
	on:focus={() => { if (button.matches(':focus-visible')) open(); }}
	on:blur={close}
	on:click={(event) => { if (event.detail === 0 || ('pointerType' in event && event.pointerType === 'touch')) open(); }}
><Info className="block size-[20px]" /></button>

{#if shown}
	<div use:floatingPanel id={panelId} data-model-info-panel role="tooltip" aria-label={$i18n.t('Information')}
		style="position: fixed; visibility: hidden;"
		class="pointer-events-none z-[10002] w-64 max-w-[calc(100vw-2rem)] max-h-64 overflow-y-auto rounded-lg border border-gray-200 bg-white p-3 text-sm text-gray-700 shadow-lg dark:border-gray-800 dark:bg-gray-850 dark:text-gray-200">
		<p class="break-words">{description}</p>
		<div data-model-info-size class="mt-2 border-t border-gray-100 pt-2 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400">{size}</div>
	</div>
{/if}
