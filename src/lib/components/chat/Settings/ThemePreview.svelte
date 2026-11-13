<script lang="ts">
	export let mode: string;
</script>

<div class="theme-preview {mode}" aria-hidden="true">
	{#each mode === 'system' ? ['light', 'dark'] : [mode] as palette}
		<div class="preview-pane {palette}" class:split={mode === 'system'}>
			<div class="preview-sidebar"><span></span><i></i><i></i><i></i></div>
			<div class="preview-content">
				<div class="preview-user"></div>
				<div class="preview-line"></div>
				<div class="preview-line short"></div>
				<div class="preview-line"></div>
				<div class="preview-code"><span></span><span></span></div>
				<div class="preview-input"><b></b></div>
			</div>
		</div>
	{/each}
</div>

<style>
	.theme-preview {
		position: relative;
		width: 78px;
		height: 58px;
		overflow: hidden;
		border-radius: inherit;
		background: #f7f7f7;
	}
	.theme-preview.dark {
		background: #242424;
	}
	.theme-preview.system {
		background: linear-gradient(to right, #f7f7f7 50%, #242424 50%);
	}
	.preview-pane {
		position: absolute;
		inset: 0;
		overflow: hidden;
		--preview-ink: #d9d9d9;
		--preview-surface: #fff;
	}
	.preview-pane.dark {
		--preview-ink: #4b4b4b;
		--preview-surface: #171717;
	}
	.preview-pane.split.dark {
		clip-path: inset(0 0 0 50%);
	}
	.preview-pane.split.light {
		clip-path: inset(0 50% 0 0);
	}
	.preview-sidebar {
		position: absolute;
		inset: 7px auto 7px 7px;
		width: 12px;
		border-radius: 3px;
		background: var(--preview-ink);
		opacity: 0.6;
		padding: 3px;
	}
	.preview-sidebar span {
		display: block;
		width: 5px;
		height: 5px;
		border-radius: 50%;
		background: var(--preview-surface);
		margin-bottom: 4px;
	}
	.preview-sidebar i {
		display: block;
		height: 1px;
		margin-top: 3px;
		background: var(--preview-surface);
	}
	.preview-content {
		position: absolute;
		inset: 7px 7px 7px 22px;
		border-radius: 3px;
		padding: 5px 4px;
		background: var(--preview-surface);
		box-shadow: 0 1px 3px #0001;
	}
	.preview-user {
		width: 66%;
		height: 2px;
		margin: 0 0 4px auto;
		background: #1685ff;
	}
	.preview-line {
		height: 1px;
		margin-top: 3px;
		width: 85%;
		background: var(--preview-ink);
	}
	.preview-line.short {
		width: 63%;
	}
	.preview-code {
		margin-top: 4px;
		padding: 2px 3px;
		border-radius: 2px;
		border: 1px solid var(--preview-ink);
	}
	.preview-code span {
		display: block;
		height: 1px;
		margin: 1px 0;
		background: #1685ff;
	}
	.preview-code span:last-child {
		width: 65%;
	}
	.preview-input {
		position: absolute;
		bottom: 4px;
		left: 4px;
		right: 4px;
		height: 6px;
		border: 1px solid var(--preview-ink);
		border-radius: 3px;
	}
	.preview-input b {
		position: absolute;
		right: 2px;
		top: 1px;
		width: 2px;
		height: 2px;
		background: #1685ff;
		border-radius: 50%;
	}
	@media (max-width: 380px) {
		.theme-preview {
			width: 60px;
			height: 52px;
		}
	}
</style>
