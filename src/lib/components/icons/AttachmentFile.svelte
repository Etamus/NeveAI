<script lang="ts">
	export let name: string | null | undefined = '';
	export let contentType: string | null | undefined = '';
	export let className = 'size-4';
	export let kindOverride: string | null | undefined = null;

	const spreadsheetExtensions = new Set([
		'csv',
		'fods',
		'gnumeric',
		'numbers',
		'ods',
		'ots',
		'slk',
		'tsv',
		'xls',
		'xlsb',
		'xlsm',
		'xlsx',
		'xlt',
		'xltm',
		'xltx'
	]);
	const audioExtensions = new Set([
		'aac',
		'aif',
		'aiff',
		'alac',
		'amr',
		'flac',
		'm4a',
		'mid',
		'midi',
		'mp3',
		'oga',
		'ogg',
		'opus',
		'wav',
		'webm',
		'wma'
	]);
	const presentationExtensions = new Set([
		'odp',
		'otp',
		'pot',
		'potm',
		'potx',
		'pps',
		'ppsm',
		'ppsx',
		'ppt',
		'pptm',
		'pptx'
	]);
	const documentExtensions = new Set([
		'doc',
		'docm',
		'docx',
		'dot',
		'dotm',
		'dotx',
		'epub',
		'md',
		'odt',
		'ott',
		'pages',
		'rtf',
		'tex',
		'txt'
	]);

	$: decodedName = (() => {
		try {
			return decodeURIComponent(name ?? '');
		} catch {
			return name ?? '';
		}
	})();
	$: normalizedName = decodedName.trim().toLowerCase();
	$: extension = normalizedName.split(/[?#]/, 1)[0].split('.').at(-1) ?? '';
	$: mime = (contentType ?? '').toLowerCase();
	$: kind =
		kindOverride ??
		(normalizedName === 'texto colado' || normalizedName === 'texto colado.txt'
			? 'note'
			: extension === 'pdf' || mime === 'application/pdf'
				? 'pdf'
				: mime.startsWith('audio/') || audioExtensions.has(extension)
					? 'audio'
					: presentationExtensions.has(extension) ||
						  mime.includes('presentation') ||
						  mime.includes('powerpoint')
						? 'presentation'
						: spreadsheetExtensions.has(extension) ||
							  mime.includes('spreadsheet') ||
							  mime.includes('excel') ||
							  mime.includes('csv') ||
							  mime.includes('tab-separated-values') ||
							  mime.includes('numbers')
							? 'spreadsheet'
							: documentExtensions.has(extension) ||
								  mime.includes('wordprocessing') ||
								  mime.includes('msword') ||
								  mime.includes('opendocument.text') ||
								  mime.includes('presentation') ||
								  mime.includes('powerpoint') ||
								  mime.startsWith('text/')
								? 'document'
								: 'file');
	$: colorClass =
		kind === 'note'
			? 'text-white'
			: kind === 'spreadsheet'
				? 'text-emerald-600 dark:text-emerald-400'
				: kind === 'presentation'
					? 'text-amber-500 dark:text-amber-400'
					: kind === 'audio'
						? 'text-purple-600 dark:text-purple-400'
						: kind === 'pdf'
							? 'text-red-600 dark:text-red-400'
							: kind === 'document'
								? 'text-blue-600 dark:text-blue-400'
								: 'text-gray-500 dark:text-gray-400';
</script>

<span class="inline-flex shrink-0 {colorClass}" aria-hidden="true">
	{#if kind === 'note'}
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
			stroke-linejoin="round"
			class={className}
		>
			<path
				d="M6.5 3.75h11a1.75 1.75 0 0 1 1.75 1.75v8.75l-5 5H6.5a1.75 1.75 0 0 1-1.75-1.75v-12A1.75 1.75 0 0 1 6.5 3.75Z"
			/>
			<path d="M14.25 19.25v-3.5a1.5 1.5 0 0 1 1.5-1.5h3.5M8.25 8h7.5M8.25 11h5.5" />
		</svg>
	{:else if kind === 'spreadsheet'}
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="1.7"
			stroke-linecap="round"
			stroke-linejoin="round"
			class={className}
		>
			<path d="M6.75 3.25h7.1l3.4 3.4v14.1H6.75a2 2 0 0 1-2-2V5.25a2 2 0 0 1 2-2Z" />
			<path d="M13.75 3.5v3.25h3.25M7.75 10.25h6.5v7h-6.5zM7.75 13.75h6.5M11 10.25v7" />
		</svg>
	{:else if kind === 'audio'}
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
			stroke-linejoin="round"
			class={className}
		>
			<path d="M9 18V6.6l9-1.85v10.9" />
			<path d="M9 9.5 18 7.7" />
			<ellipse cx="6.75" cy="18" rx="2.25" ry="1.75" />
			<ellipse cx="15.75" cy="15.65" rx="2.25" ry="1.75" />
		</svg>
	{:else if kind === 'presentation'}
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="1.7"
			stroke-linecap="round"
			stroke-linejoin="round"
			class={className}
		>
			<path d="M3.5 4.25h17M5 4.5v10.75h14V4.5" />
			<path d="M12 15.25v4.5M8.5 19.75h7M8.25 11.75V9.5M12 11.75V7.25M15.75 11.75V8.5" />
		</svg>
	{:else if kind === 'pdf'}
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="1.7"
			stroke-linecap="round"
			stroke-linejoin="round"
			class={className}
		>
			<path d="M6.75 3.25h7.1l3.4 3.4v14.1H6.75a2 2 0 0 1-2-2V5.25a2 2 0 0 1 2-2Z" />
			<path
				d="M13.75 3.5v3.25h3.25M7.5 16.75c2.3-3.8 3.35-6.2 3.1-7.1-.45-1.6-1.4 1.2.25 3.55 1.25 1.8 3.55 2.65 4.15 1.45.45-.9-2.5-1.05-7.5 2.1Z"
			/>
		</svg>
	{:else}
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="1.7"
			stroke-linecap="round"
			stroke-linejoin="round"
			class={className}
		>
			<path d="M6.75 3.25h7.1l3.4 3.4v14.1H6.75a2 2 0 0 1-2-2V5.25a2 2 0 0 1 2-2Z" />
			<path d="M13.75 3.5v3.25h3.25M8 11h6M8 14h6M8 17h4" />
		</svg>
	{/if}
</span>
