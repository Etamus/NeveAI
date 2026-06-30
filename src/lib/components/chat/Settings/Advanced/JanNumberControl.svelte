<script lang="ts">
	export let value: number = 0;
	export let min: number = 0;
	export let max: number = 1;
	export let step: number = 0.05;
	export let disabled = false;

	$: if (value !== null && value !== undefined) {
		const numericValue = Number(value);
		if (Number.isFinite(numericValue) && numericValue > max) {
			value = max;
		}
	}

	const adjust = (delta: number) => {
		if (disabled) return;
		const decimals = (step.toString().split('.')[1] || '').length;
		let newVal = Number((value + delta).toFixed(decimals));
		newVal = Math.max(min, Math.min(max, newVal));
		value = newVal;
	};
</script>

<div
	class="flex items-center overflow-hidden rounded-md border border-gray-200 dark:border-gray-700 divide-x divide-gray-200 dark:divide-gray-700 shrink-0 {disabled ? 'opacity-60' : ''}"
>
	<button
		type="button"
		class="h-7 w-6 flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400 transition disabled:opacity-30"
		on:click={() => adjust(-step)}
		disabled={disabled || value <= min}
		aria-label="Decrease"
	>
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="2.5"
			class="size-3"
			aria-hidden="true"
		>
			<path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14" />
		</svg>
	</button>
	<input
		type="number"
		class="h-7 w-12 text-center text-xs bg-transparent outline-none tabular-nums" style="font-family: 'Segoe UI', system-ui, sans-serif;"
		bind:value
		{min}
		{max}
		{step}
		{disabled}
	/>
	<button
		type="button"
		class="h-7 w-6 flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400 transition disabled:opacity-30"
		on:click={() => adjust(step)}
		disabled={disabled || value >= max}
		aria-label="Increase"
	>
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="2.5"
			class="size-3"
			aria-hidden="true"
		>
			<path stroke-linecap="round" stroke-linejoin="round" d="M12 5v14M5 12h14" />
		</svg>
	</button>
</div>
