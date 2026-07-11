<script lang="ts">
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import JanNumberControl from './JanNumberControl.svelte';
	import { getContext } from 'svelte';

	const i18n = getContext('i18n');

	export let onChange: (params: any) => void = () => {};

	export let admin = false;
	export let custom = false;
	export let separators = false;
	export let janStyle = false;
	export let tooltipsEnabled = true;
	export let disabledParams: string[] = [];

	const isParamDisabled = (key: string) => disabledParams.includes(key);
	const disabledRowClass = (key: string) =>
		isParamDisabled(key) ? 'opacity-50 grayscale pointer-events-none select-none' : '';
	const MAX_TOKENS_LIMIT = 262144;

	const defaultParams = {
		// Advanced - llama.cpp compatible params only
		seed: -1,
		stop: null,
		temperature: null,
		max_tokens: null,
		top_k: 0,
		top_p: 1,
		min_p: null,
		frequency_penalty: 0,
		presence_penalty: 0,
		mirostat: null,
		mirostat_eta: null,
		mirostat_tau: null,
		repeat_penalty: 1,
		xtc_threshold: null,
		xtc_probability: null,
		dry_multiplier: null,
		dry_allowed_length: null,
		dry_base: null
	};

	export let params = defaultParams;
	$: if (params && (params?.max_tokens ?? null) !== null) {
		const maxTokens = Number(params.max_tokens);
		if (Number.isFinite(maxTokens) && maxTokens > MAX_TOKENS_LIMIT) {
			params.max_tokens = MAX_TOKENS_LIMIT;
		}
	}
	$: if (params) {
		onChange(params);
	}
</script>
<div class=" space-y-1 text-xs pb-safe-bottom">
	{#if janStyle}
		<div class="flex w-full items-center justify-between py-1.5 {disabledRowClass('temperature')}">
			<Tooltip
				content={tooltipsEnabled ? $i18n.t('The temperature of the model. Increasing the temperature will make the model answer more creatively.') : ""}
				placement="top-start"
				className="inline-tooltip"
			>
				{#if (params?.temperature ?? null) === null}
					<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t('temperature')}</div>
				{:else}
					<button type="button" disabled={isParamDisabled('temperature')} class="text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition" on:click={() => { params.temperature = null; }}>{$i18n.t('temperature')}</button>
				{/if}
			</Tooltip>
			{#if (params?.temperature ?? null) === null}
				<button
					type="button"
					class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700"
					disabled={isParamDisabled('temperature')}
					on:click={() => { params.temperature = 0.8; }}
				>{$i18n.t('Default')}</button>
			{:else}
				<JanNumberControl bind:value={params.temperature} min={0} max={2} step={0.05} disabled={isParamDisabled('temperature')} />
			{/if}
		</div>
	{:else}
		<div class=" py-0.5 w-full justify-between {disabledRowClass('temperature')}">
		<Tooltip
			content={tooltipsEnabled ? $i18n.t(
				'The temperature of the model. Increasing the temperature will make the model answer more creatively.'
			) : ""}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">
					{$i18n.t('temperature')}
				</div>
				<button
					class="p-1 px-3 text-xs flex rounded-sm transition shrink-0 outline-hidden"
					type="button"
					disabled={isParamDisabled('temperature')}
					on:click={() => {
						params.temperature = (params?.temperature ?? null) === null ? 0.8 : null;
					}}
				>
					{#if (params?.temperature ?? null) === null}
						<span class="ml-2 self-center"> {$i18n.t('Default')} </span>
					{:else}
						<span class="ml-2 self-center"> {$i18n.t('Custom')} </span>
					{/if}
				</button>
			</div>
		</Tooltip>

		{#if (params?.temperature ?? null) !== null}
			<div class="flex mt-0.5 space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="0"
						max="2"
						step="0.05"
						bind:value={params.temperature}
						disabled={isParamDisabled('temperature')}
						class="w-full h-2 rounded-lg appearance-none cursor-pointer bg-gray-200 dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.temperature}
						type="number"
						class=" bg-transparent text-center w-14"
						min="0"
						max="2"
						step="any"
						disabled={isParamDisabled('temperature')}
					/>
				</div>
			</div>
		{/if}
	</div>
	{/if}
	{#if janStyle}
		<div class="flex w-full items-center justify-between py-1.5">
			<Tooltip
				content={tooltipsEnabled ? $i18n.t('Esta opção define o número máximo de tokens que o modelo pode gerar em sua resposta.') : ""}
				placement="top-start"
				className="inline-tooltip"
			>
				{#if (params?.max_tokens ?? null) === null}
					<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t('max_tokens')}</div>
				{:else}
					<button type="button" class="text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition" on:click={() => { params.max_tokens = null; }}>{$i18n.t('max_tokens')}</button>
				{/if}
			</Tooltip>
			{#if (params?.max_tokens ?? null) === null}
				<button
					type="button"
					class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700"
					on:click={() => { params.max_tokens = 128; }}
				>{$i18n.t('Default')}</button>
			{:else}
				<JanNumberControl bind:value={params.max_tokens} min={128} max={MAX_TOKENS_LIMIT} step={128} adjustMode="double" />
			{/if}
		</div>
	{:else}
		<div class=" py-0.5 w-full justify-between">
		<Tooltip
			content={tooltipsEnabled ? $i18n.t(
				'This option sets the maximum number of tokens the model can generate in its response. Increasing this limit allows the model to provide longer answers, but it may also increase the likelihood of unhelpful or irrelevant content being generated.'
			) : ""}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">
					{$i18n.t('max_tokens')}
				</div>

				<button
					class="p-1 px-3 text-xs flex rounded-sm transition shrink-0 outline-hidden"
					type="button"
					on:click={() => {
						params.max_tokens = (params?.max_tokens ?? null) === null ? 128 : null;
					}}
				>
					{#if (params?.max_tokens ?? null) === null}
						<span class="ml-2 self-center">{$i18n.t('Default')}</span>
					{:else}
						<span class="ml-2 self-center">{$i18n.t('Custom')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>

		{#if (params?.max_tokens ?? null) !== null}
			<div class="flex mt-0.5 space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="128"
						max={MAX_TOKENS_LIMIT}
						step="128"
						bind:value={params.max_tokens}
						class="w-full h-2 rounded-lg appearance-none cursor-pointer bg-gray-200 dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.max_tokens}
						type="number"
						class=" bg-transparent text-center w-14"
						min="128"
						step="128"
					/>
				</div>
			</div>
		{/if}
	</div>
	{/if}
	{#if janStyle}
		<div class="flex w-full items-center justify-between py-1.5 {disabledRowClass('top_k')}">
			<Tooltip
				content={tooltipsEnabled ? $i18n.t('Limits token sampling to the top K most likely tokens. Use 0 to keep the default behavior.') : ""}
				placement="top-start"
				className="inline-tooltip"
			>
				{#if (params?.top_k ?? null) === null}
					<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t('top_k')}</div>
				{:else}
					<button type="button" disabled={isParamDisabled('top_k')} class="text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition" on:click={() => { params.top_k = null; }}>{$i18n.t('top_k')}</button>
				{/if}
			</Tooltip>
			{#if (params?.top_k ?? null) === null}
				<button type="button" disabled={isParamDisabled('top_k')} class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700" on:click={() => { params.top_k = 0; }}>{$i18n.t('Default')}</button>
			{:else}
				<JanNumberControl bind:value={params.top_k} min={0} max={200} step={0.05} disabled={isParamDisabled('top_k')} />
			{/if}
		</div>
	{:else}
		<div class=" py-0.5 w-full justify-between {disabledRowClass('top_k')}">
		<Tooltip
			content={tooltipsEnabled ? $i18n.t(
				'Limits token sampling to the top K most likely tokens. Use 0 to keep the default behavior.'
			) : ""}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">
					{$i18n.t('top_k')}
				</div>
				<button
					class="p-1 px-3 text-xs flex rounded-sm transition shrink-0 outline-hidden"
					type="button"
					disabled={isParamDisabled('top_k')}
					on:click={() => {
						params.top_k = (params?.top_k ?? null) === null ? 0 : null;
					}}
				>
					{#if (params?.top_k ?? null) === null}
						<span class="ml-2 self-center">{$i18n.t('Default')}</span>
					{:else}
						<span class="ml-2 self-center">{$i18n.t('Custom')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>

		{#if (params?.top_k ?? null) !== null}
			<div class="flex mt-0.5 space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="0"
						max="200"
						step="0.05"
						bind:value={params.top_k}
						disabled={isParamDisabled('top_k')}
						class="w-full h-2 rounded-lg appearance-none cursor-pointer bg-gray-200 dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.top_k}
						type="number"
						class=" bg-transparent text-center w-14"
						min="0"
						max="200"
						step="0.05"
						disabled={isParamDisabled('top_k')}
					/>
				</div>
			</div>
		{/if}
	</div>
	{/if}
	{#if janStyle}
		<div class="flex w-full items-center justify-between py-1.5 {disabledRowClass('top_p')}">
			<Tooltip
				content={tooltipsEnabled ? $i18n.t('Nucleus sampling probability. Lower values make generation more focused; 1 keeps the default behavior.') : ""}
				placement="top-start"
				className="inline-tooltip"
			>
				{#if (params?.top_p ?? null) === null}
					<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t('top_p')}</div>
				{:else}
					<button type="button" disabled={isParamDisabled('top_p')} class="text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition" on:click={() => { params.top_p = null; }}>{$i18n.t('top_p')}</button>
				{/if}
			</Tooltip>
			{#if (params?.top_p ?? null) === null}
				<button type="button" disabled={isParamDisabled('top_p')} class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700" on:click={() => { params.top_p = 1; }}>{$i18n.t('Default')}</button>
			{:else}
				<JanNumberControl bind:value={params.top_p} min={0} max={1} step={0.05} disabled={isParamDisabled('top_p')} />
			{/if}
		</div>
	{:else}
		<div class=" py-0.5 w-full justify-between {disabledRowClass('top_p')}">
		<Tooltip
			content={tooltipsEnabled ? $i18n.t(
				'Nucleus sampling probability. Lower values make generation more focused; 1 keeps the default behavior.'
			) : ""}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">
					{$i18n.t('top_p')}
				</div>
				<button
					class="p-1 px-3 text-xs flex rounded-sm transition shrink-0 outline-hidden"
					type="button"
					disabled={isParamDisabled('top_p')}
					on:click={() => {
						params.top_p = (params?.top_p ?? null) === null ? 1 : null;
					}}
				>
					{#if (params?.top_p ?? null) === null}
						<span class="ml-2 self-center">{$i18n.t('Default')}</span>
					{:else}
						<span class="ml-2 self-center">{$i18n.t('Custom')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>

		{#if (params?.top_p ?? null) !== null}
			<div class="flex mt-0.5 space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="0"
						max="1"
						step="0.05"
						bind:value={params.top_p}
						disabled={isParamDisabled('top_p')}
						class="w-full h-2 rounded-lg appearance-none cursor-pointer bg-gray-200 dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.top_p}
						type="number"
						class=" bg-transparent text-center w-14"
						min="0"
						max="1"
						step="any"
						disabled={isParamDisabled('top_p')}
					/>
				</div>
			</div>
		{/if}
	</div>
	{/if}
	{#if janStyle}
		<div class="flex w-full items-center justify-between py-1.5 {disabledRowClass('min_p')}">
			<Tooltip
				content={tooltipsEnabled ? $i18n.t('Alternative to the top_p, and aims to ensure a balance of quality and variety. The parameter p represents the minimum probability for a token to be considered, relative to the probability of the most likely token. For example, with p=0.05 and the most likely token having a probability of 0.9, logits with a value less than 0.045 are filtered out.') : ""}
				placement="top-start"
				className="inline-tooltip"
			>
				{#if (params?.min_p ?? null) === null}
					<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t('min_p')}</div>
				{:else}
					<button type="button" disabled={isParamDisabled('min_p')} class="text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition" on:click={() => { params.min_p = null; }}>{$i18n.t('min_p')}</button>
				{/if}
			</Tooltip>
			{#if (params?.min_p ?? null) === null}
				<button type="button" disabled={isParamDisabled('min_p')} class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700" on:click={() => { params.min_p = 0.0; }}>{$i18n.t('Default')}</button>
			{:else}
				<JanNumberControl bind:value={params.min_p} min={0} max={1} step={0.05} disabled={isParamDisabled('min_p')} />
			{/if}
		</div>
	{:else}
		<div class=" py-0.5 w-full justify-between {disabledRowClass('min_p')}">
		<Tooltip
			content={tooltipsEnabled ? $i18n.t(
				'Alternative to the top_p, and aims to ensure a balance of quality and variety. The parameter p represents the minimum probability for a token to be considered, relative to the probability of the most likely token. For example, with p=0.05 and the most likely token having a probability of 0.9, logits with a value less than 0.045 are filtered out.'
			) : ""}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">
					{$i18n.t('min_p')}
				</div>
				<button
					class="p-1 px-3 text-xs flex rounded-sm transition shrink-0 outline-hidden"
					type="button"
					disabled={isParamDisabled('min_p')}
					on:click={() => {
						params.min_p = (params?.min_p ?? null) === null ? 0.0 : null;
					}}
				>
					{#if (params?.min_p ?? null) === null}
						<span class="ml-2 self-center">{$i18n.t('Default')}</span>
					{:else}
						<span class="ml-2 self-center">{$i18n.t('Custom')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>

		{#if (params?.min_p ?? null) !== null}
			<div class="flex mt-0.5 space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="0"
						max="1"
						step="0.05"
						bind:value={params.min_p}
						disabled={isParamDisabled('min_p')}
						class="w-full h-2 rounded-lg appearance-none cursor-pointer bg-gray-200 dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.min_p}
						type="number"
						class=" bg-transparent text-center w-14"
						min="0"
						max="1"
						step="any"
						disabled={isParamDisabled('min_p')}
					/>
				</div>
			</div>
		{/if}
	</div>
	{/if}
	{#if janStyle}
		<div class="flex w-full items-center justify-between py-1.5">
			<Tooltip
				content={tooltipsEnabled ? $i18n.t('Limiar de amostragem XTC (eXclude Top Choices). Tokens com probabilidade acima deste valor são candidatos à exclusão. Intervalo 0–1. Padrão 0.1.') : ""}
				placement="top-start"
				className="inline-tooltip"
			>
				{#if (params?.xtc_threshold ?? null) === null}
					<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t('xtc_threshold')}</div>
				{:else}
					<button type="button" class="text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition" on:click={() => { params.xtc_threshold = null; }}>{$i18n.t('xtc_threshold')}</button>
				{/if}
			</Tooltip>
			{#if (params?.xtc_threshold ?? null) === null}
				<button type="button" class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700" on:click={() => { params.xtc_threshold = 0.1; }}>{$i18n.t('Default')}</button>
			{:else}
				<JanNumberControl bind:value={params.xtc_threshold} min={0} max={1} step={0.01} />
			{/if}
		</div>
	{:else}
		<div class=" py-0.5 w-full justify-between">
		<Tooltip
			content={tooltipsEnabled ? $i18n.t(
				'Limiar de amostragem XTC (eXclude Top Choices). Tokens com probabilidade acima deste valor são candidatos à exclusão. Intervalo 0–1. Padrão 0.1.'
			) : ""}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">
					{$i18n.t('xtc_threshold')}
				</div>
				<button
					class="p-1 px-3 text-xs flex rounded transition flex-shrink-0 outline-none"
					type="button"
					on:click={() => {
						params.xtc_threshold = (params?.xtc_threshold ?? null) === null ? 0.1 : null;
					}}
				>
					{#if (params?.xtc_threshold ?? null) === null}
						<span class="ml-2 self-center">{$i18n.t('Default')}</span>
					{:else}
						<span class="ml-2 self-center">{$i18n.t('Custom')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>
		{#if (params?.xtc_threshold ?? null) !== null}
			<div class="flex mt-0.5 space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="0"
						max="1"
						step="0.01"
						bind:value={params.xtc_threshold}
						class="w-full h-2 rounded-lg appearance-none cursor-pointer bg-gray-200 dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.xtc_threshold}
						type="number"
						class=" bg-transparent text-center w-14"
						min="0"
						max="1"
						step="any"
					/>
				</div>
			</div>
		{/if}
	</div>
	{/if}
	{#if janStyle}
		<div class="flex w-full items-center justify-between py-1.5">
			<Tooltip
				content={tooltipsEnabled ? $i18n.t('Probabilidade de amostragem XTC. Controla a chance de os tokens candidatos serem excluídos. Intervalo 0–1. Padrão 0.') : ""}
				placement="top-start"
				className="inline-tooltip"
			>
				{#if (params?.xtc_probability ?? null) === null}
					<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t('xtc_probability')}</div>
				{:else}
					<button type="button" class="text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition" on:click={() => { params.xtc_probability = null; }}>{$i18n.t('xtc_probability')}</button>
				{/if}
			</Tooltip>
			{#if (params?.xtc_probability ?? null) === null}
				<button type="button" class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700" on:click={() => { params.xtc_probability = 0; }}>{$i18n.t('Default')}</button>
			{:else}
				<JanNumberControl bind:value={params.xtc_probability} min={0} max={1} step={0.01} />
			{/if}
		</div>
	{:else}
		<div class=" py-0.5 w-full justify-between">
		<Tooltip
			content={tooltipsEnabled ? $i18n.t(
				'Probabilidade de amostragem XTC. Controla a chance de os tokens candidatos serem excluídos. Intervalo 0–1. Padrão 0.'
			) : ""}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">
					{$i18n.t('xtc_probability')}
				</div>
				<button
					class="p-1 px-3 text-xs flex rounded transition flex-shrink-0 outline-none"
					type="button"
					on:click={() => {
						params.xtc_probability = (params?.xtc_probability ?? null) === null ? 0 : null;
					}}
				>
					{#if (params?.xtc_probability ?? null) === null}
						<span class="ml-2 self-center">{$i18n.t('Default')}</span>
					{:else}
						<span class="ml-2 self-center">{$i18n.t('Custom')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>
		{#if (params?.xtc_probability ?? null) !== null}
			<div class="flex mt-0.5 space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="0"
						max="1"
						step="0.01"
						bind:value={params.xtc_probability}
						class="w-full h-2 rounded-lg appearance-none cursor-pointer bg-gray-200 dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.xtc_probability}
						type="number"
						class=" bg-transparent text-center w-14"
						min="0"
						max="1"
						step="any"
					/>
				</div>
			</div>
		{/if}
	</div>
	{/if}
	{#if janStyle}
		<div class="flex w-full items-center justify-between py-1.5 {disabledRowClass('dry_multiplier')}">
			<Tooltip
				content={tooltipsEnabled ? $i18n.t('Multiplicador de penalidade de repetição DRY (Não Se Repita). 0 desativa o DRY. Valores maiores penalizam sequências repetitivas com mais intensidade. Padrão 0.') : ""}
				placement="top-start"
				className="inline-tooltip"
			>
				{#if (params?.dry_multiplier ?? null) === null}
					<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t('dry_multiplier')}</div>
				{:else}
					<button type="button" disabled={isParamDisabled('dry_multiplier')} class="text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition" on:click={() => { params.dry_multiplier = null; }}>{$i18n.t('dry_multiplier')}</button>
				{/if}
			</Tooltip>
			{#if (params?.dry_multiplier ?? null) === null}
				<button type="button" disabled={isParamDisabled('dry_multiplier')} class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700" on:click={() => { params.dry_multiplier = 0; }}>{$i18n.t('Default')}</button>
			{:else}
				<JanNumberControl bind:value={params.dry_multiplier} min={0} max={3} step={0.05} disabled={isParamDisabled('dry_multiplier')} />
			{/if}
		</div>
	{:else}
		<div class=" py-0.5 w-full justify-between {disabledRowClass('dry_multiplier')}">
		<Tooltip
			content={tooltipsEnabled ? $i18n.t(
				'Multiplicador de penalidade de repetição DRY (Não Se Repita). 0 desativa o DRY. Valores maiores penalizam sequências repetitivas com mais intensidade. Padrão 0.'
			) : ""}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">
					{$i18n.t('dry_multiplier')}
				</div>
				<button
					class="p-1 px-3 text-xs flex rounded transition flex-shrink-0 outline-none"
					type="button"
					disabled={isParamDisabled('dry_multiplier')}
					on:click={() => {
						params.dry_multiplier = (params?.dry_multiplier ?? null) === null ? 0 : null;
					}}
				>
					{#if (params?.dry_multiplier ?? null) === null}
						<span class="ml-2 self-center">{$i18n.t('Default')}</span>
					{:else}
						<span class="ml-2 self-center">{$i18n.t('Custom')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>
		{#if (params?.dry_multiplier ?? null) !== null}
			<div class="flex mt-0.5 space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="0"
						max="3"
						step="0.05"
						bind:value={params.dry_multiplier}
						disabled={isParamDisabled('dry_multiplier')}
						class="w-full h-2 rounded-lg appearance-none cursor-pointer bg-gray-200 dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.dry_multiplier}
						type="number"
						class=" bg-transparent text-center w-14"
						min="0"
						max="3"
						step="any"
						disabled={isParamDisabled('dry_multiplier')}
					/>
				</div>
			</div>
		{/if}
	</div>
	{/if}
	{#if janStyle}
		<div class="flex w-full items-center justify-between py-1.5">
			<Tooltip
				content={tooltipsEnabled ? $i18n.t('Comprimento permitido pelo DRY. Sequências menores que este valor não são penalizadas pelo DRY. Padrão 2.') : ""}
				placement="top-start"
				className="inline-tooltip"
			>
				{#if (params?.dry_allowed_length ?? null) === null}
					<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t('dry_allowed_length')}</div>
				{:else}
					<button type="button" class="text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition" on:click={() => { params.dry_allowed_length = null; }}>{$i18n.t('dry_allowed_length')}</button>
				{/if}
			</Tooltip>
			{#if (params?.dry_allowed_length ?? null) === null}
				<button type="button" class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700" on:click={() => { params.dry_allowed_length = 2; }}>{$i18n.t('Default')}</button>
			{:else}
				<JanNumberControl bind:value={params.dry_allowed_length} min={1} max={10} step={1} />
			{/if}
		</div>
	{:else}
		<div class=" py-0.5 w-full justify-between">
		<Tooltip
			content={tooltipsEnabled ? $i18n.t(
				'Comprimento permitido pelo DRY. Sequências menores que este valor não são penalizadas pelo DRY. Padrão 2.'
			) : ""}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">
					{$i18n.t('dry_allowed_length')}
				</div>
				<button
					class="p-1 px-3 text-xs flex rounded transition flex-shrink-0 outline-none"
					type="button"
					on:click={() => {
						params.dry_allowed_length = (params?.dry_allowed_length ?? null) === null ? 2 : null;
					}}
				>
					{#if (params?.dry_allowed_length ?? null) === null}
						<span class="ml-2 self-center">{$i18n.t('Default')}</span>
					{:else}
						<span class="ml-2 self-center">{$i18n.t('Custom')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>
		{#if (params?.dry_allowed_length ?? null) !== null}
			<div class="flex mt-0.5 space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="1"
						max="10"
						step="1"
						bind:value={params.dry_allowed_length}
						class="w-full h-2 rounded-lg appearance-none cursor-pointer bg-gray-200 dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.dry_allowed_length}
						type="number"
						class=" bg-transparent text-center w-14"
						min="1"
						max="10"
						step="1"
					/>
				</div>
			</div>
		{/if}
	</div>
	{/if}
	{#if janStyle}
		<div class="flex w-full items-center justify-between py-1.5">
			<Tooltip
				content={tooltipsEnabled ? $i18n.t('Base exponencial do DRY. A penalidade cresce exponencialmente com o comprimento da sequência. Valores maiores penalizam mais repetições longas. Padrão 1.75.') : ""}
				placement="top-start"
				className="inline-tooltip"
			>
				{#if (params?.dry_base ?? null) === null}
					<div class="text-xs text-gray-700 dark:text-gray-300">{$i18n.t('dry_base')}</div>
				{:else}
					<button type="button" class="text-xs text-gray-700 dark:text-gray-300 underline decoration-dotted cursor-pointer hover:text-gray-500 dark:hover:text-gray-400 transition" on:click={() => { params.dry_base = null; }}>{$i18n.t('dry_base')}</button>
				{/if}
			</Tooltip>
			{#if (params?.dry_base ?? null) === null}
				<button type="button" class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition px-2 py-0.5 rounded-md border border-gray-200 dark:border-gray-700" on:click={() => { params.dry_base = 1.75; }}>{$i18n.t('Default')}</button>
			{:else}
				<JanNumberControl bind:value={params.dry_base} min={1} max={2.5} step={0.05} />
			{/if}
		</div>
	{:else}
		<div class=" py-0.5 w-full justify-between">
		<Tooltip
			content={tooltipsEnabled ? $i18n.t(
				'Base exponencial do DRY. A penalidade cresce exponencialmente com o comprimento da sequência. Valores maiores penalizam mais repetições longas. Padrão 1.75.'
			) : ""}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">
					{$i18n.t('dry_base')}
				</div>
				<button
					class="p-1 px-3 text-xs flex rounded transition flex-shrink-0 outline-none"
					type="button"
					on:click={() => {
						params.dry_base = (params?.dry_base ?? null) === null ? 1.75 : null;
					}}
				>
					{#if (params?.dry_base ?? null) === null}
						<span class="ml-2 self-center">{$i18n.t('Default')}</span>
					{:else}
						<span class="ml-2 self-center">{$i18n.t('Custom')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>
		{#if (params?.dry_base ?? null) !== null}
			<div class="flex mt-0.5 space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="1"
						max="2.5"
						step="0.05"
						bind:value={params.dry_base}
						class="w-full h-2 rounded-lg appearance-none cursor-pointer bg-gray-200 dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.dry_base}
						type="number"
						class=" bg-transparent text-center w-14"
						min="1"
						max="2.5"
						step="any"
					/>
				</div>
			</div>
		{/if}
	</div>
	{/if}

	{#if admin}
		{#if custom && admin}
			<div class="flex flex-col justify-center">
				{#each Object.keys(params?.custom_params ?? {}) as key}
					<div class=" py-0.5 w-full justify-between mb-1">
						<div class="flex w-full justify-between">
							<div class=" self-center text-xs">
								<input
									type="text"
									class=" text-xs w-full bg-transparent outline-none"
									placeholder={$i18n.t('Custom Parameter Name')}
									value={key}
									on:change={(e) => {
										const newKey = e.target.value.trim();
										if (newKey && newKey !== key) {
											params.custom_params[newKey] = params.custom_params[key];
											delete params.custom_params[key];
											params = {
												...params,
												custom_params: { ...params.custom_params }
											};
										}
									}}
								/>
							</div>
							<button
								class="p-1 px-3 text-xs flex rounded-sm transition shrink-0 outline-hidden"
								type="button"
								on:click={() => {
									delete params.custom_params[key];
									params = {
										...params,
										custom_params: { ...params.custom_params }
									};
								}}
							>
								{$i18n.t('Remove')}
							</button>
						</div>
						<div class="flex mt-0.5 space-x-2">
							<div class=" flex-1">
								<input
									bind:value={params.custom_params[key]}
									type="text"
									class="text-sm w-full bg-transparent outline-hidden outline-none"
									placeholder={$i18n.t('Custom Parameter Value')}
								/>
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</div>
