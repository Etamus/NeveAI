<script lang="ts">
	import { onDestroy, onMount, tick, setContext } from 'svelte';
	import { fade } from 'svelte/transition';

	import { flyAndScale } from '$lib/utils/transitions';
	import * as FocusTrap from 'focus-trap';
	import { mobile } from '$lib/stores';
	import { page } from '$app/stores';
	import { get } from 'svelte/store';
	import { mobileDialogHistory, MOBILE_DIALOG_STATE } from '$lib/utils/mobileDialogNavigation';
	export let show = true;
	export let size = 'md';
	export let containerClassName = 'p-3';
	export let className = 'bg-white dark:bg-gray-900 rounded-xl';
	export let keepMounted = false;
	export let animated = true;
	export let initialFocus: string | undefined = undefined;
	export let onOutsideClick: (() => boolean | void) | null = null;
	export let mobileFullscreen = false;
	export let mobileStep = '';
	export let onMobileStepBack: () => void = () => {};
	setContext('mobile-modal-back', () => {
		if (mobileStep) onMobileStepBack();
		else show = false;
	});
	let releaseMobileDialog: (() => void) | null = null;
	let releaseMobileStep: (() => void) | null = null;
	$: if (mounted && mobileFullscreen) {
		// Multiple mounted dialogs can observe the same shallow navigation. Read the
		// settled page state, not an earlier sibling's snapshot from this update.
		void $page.state;
		void tick().then(() => {
			if (mounted) mobileDialogHistory.synchronize((get(page).state as Record<string, string>)[MOBILE_DIALOG_STATE]);
		});
	}
	$: if (mounted && show && mobileFullscreen && $mobile) {
		if (!releaseMobileDialog) releaseMobileDialog = mobileDialogHistory.open(() => {
			releaseMobileDialog = null;
			show = false;
		});
		if (mobileStep && !releaseMobileStep) releaseMobileStep = mobileDialogHistory.open(() => {
			releaseMobileStep = null;
			onMobileStepBack();
		});
		else if (!mobileStep && releaseMobileStep) {
			releaseMobileStep(); releaseMobileStep = null;
		}
	} else {
		releaseMobileStep?.(); releaseMobileStep = null;
		releaseMobileDialog?.(); releaseMobileDialog = null;
	}

	let modalElement = null;
	let mounted = false;
	// Create focus trap to trap user tabs inside modal
	// https://www.w3.org/WAI/WCAG21/Understanding/focus-order.html
	// https://www.w3.org/WAI/WCAG21/Understanding/keyboard.html
	let focusTrap: FocusTrap.FocusTrap | null = null;
	let modalInBody = false;

	const sizeToWidth = (size) => {
		if (size === 'full') {
			return 'w-full';
		}
		if (typeof size === 'string' && size.startsWith('w-')) {
			return size;
		}
		if (size === 'xs') {
			return 'w-[16rem]';
		} else if (size === 'sm') {
			return 'w-[30rem]';
		} else if (size === 'md') {
			return 'w-[42rem]';
		} else if (size === 'lg') {
			return 'w-[56rem]';
		} else if (size === 'xl') {
			return 'w-[70rem]';
		} else if (size === '2xl') {
			return 'w-[84rem]';
		} else if (size === '3xl') {
			return 'w-[100rem]';
		} else {
			return 'w-[56rem]';
		}
	};

	const handleKeyDown = (event: KeyboardEvent) => {
		if (event.key === 'Escape' && isTopModal()) {
			console.log('Escape');
			show = false;
		}
	};

	const isTopModal = () => {
		const modals = document.getElementsByClassName('modal');
		return modals.length && modals[modals.length - 1] === modalElement;
	};

	const appendModalElement = () => {
		if (!modalElement || modalInBody) return;
		document.body.appendChild(modalElement);
		modalInBody = true;
	};

	const removeModalElement = () => {
		if (!modalElement || !modalInBody) return;
		if (modalElement.parentElement === document.body) {
			document.body.removeChild(modalElement);
		}
		modalInBody = false;
	};

	onMount(() => {
		mounted = true;
	});

	$: if (keepMounted && modalElement && !modalInBody) {
		appendModalElement();
	}

	$: if (show && modalElement) {
		appendModalElement();
		focusTrap = FocusTrap.createFocusTrap(modalElement, {
			initialFocus,
			checkCanFocusTrap: initialFocus ? () => tick() : undefined,
			allowOutsideClick: (e) => {
				const target = e.target as Element;
				return (
					target.closest('[data-sonner-toast]') !== null ||
					target.closest('.modal-content') === null
				);
			},
			fallbackFocus: modalElement
		});
		focusTrap.activate();
		window.addEventListener('keydown', handleKeyDown);
		document.body.style.overflow = 'hidden';
	} else if (modalElement) {
		focusTrap?.deactivate();
		focusTrap = null;
		window.removeEventListener('keydown', handleKeyDown);
		if (!keepMounted) {
			removeModalElement();
		}
		document.body.style.overflow = 'unset';
	}

	onDestroy(() => {
		mounted = false;
		releaseMobileStep?.();
		releaseMobileDialog?.();
		show = false;
		if (focusTrap) {
			focusTrap.deactivate();
		}
		removeModalElement();
	});
</script>

{#if show || keepMounted}
	<!-- svelte-ignore a11y-click-events-have-key-events -->
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
	<div
		bind:this={modalElement}
		aria-modal="true"
		role="dialog"
		tabindex="-1"
		aria-hidden={!show}
		class:mobile-fullscreen={mobileFullscreen}
		class="modal fixed top-0 right-0 left-0 bottom-0 bg-black/30 dark:bg-black/60 w-full h-screen max-h-[100dvh] {containerClassName} {show
			? 'flex'
			: 'hidden'} justify-center z-9999 overflow-y-auto overscroll-contain"
		style="scrollbar-gutter: stable;"
		in:fade={{ duration: animated ? 150 : 0 }}
		on:mousedown={() => {
			if (onOutsideClick?.() === true) return;
			show = false;
		}}
	>
		<div
			class="m-auto min-w-0 {size === 'full' ? 'max-w-full' : 'max-w-[calc(100%-1rem)]'} {sizeToWidth(size)} {size !== 'full'
				? 'mx-2'
				: ''} shadow-3xl min-h-fit scrollbar-hidden {className} border border-gray-200 dark:border-gray-800"
			in:flyAndScale={{ start: 1, y: animated && !(mobileFullscreen && $mobile) ? -8 : 0, duration: animated ? 150 : 0 }}
			on:mousedown={(e) => {
				e.stopPropagation();
			}}
		>
			<slot />
		</div>
	</div>
{/if}

<style>
	@media (max-width: 767px) {
		:global([data-mobile-modal-close]) { display: none !important; }
		.modal.mobile-fullscreen {
			padding: 0;
			overflow: hidden;
		}
		.modal.mobile-fullscreen > :global(div) {
			width: 100% !important;
			min-width: 100%;
			max-width: 100%;
			height: 100dvh;
			max-height: 100dvh;
			min-height: 0;
			margin: 0;
			border: 0;
			border-radius: 0;
			overflow: hidden;
			padding-top: env(safe-area-inset-top, 0px);
			padding-bottom: env(safe-area-inset-bottom, 0px);
		}
		.modal {
			height: 100dvh;
			padding: max(0.5rem, env(safe-area-inset-top, 0px)) 0.5rem max(0.5rem, env(safe-area-inset-bottom, 0px));
			scrollbar-gutter: auto !important;
		}
		.modal > :global(div) {
			width: 100%;
			max-width: 100%;
			max-height: calc(100dvh - 1rem - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px));
			margin-inline: 0;
		}
	}
	.modal-content {
		animation: scaleUp 0.1s ease-out forwards;
	}

	@keyframes scaleUp {
		from {
			transform: scale(0.985);
			opacity: 0;
		}
		to {
			transform: scale(1);
			opacity: 1;
		}
	}
</style>
