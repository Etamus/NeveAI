<script lang="ts">
	export let value: string;
	export let label: string;
	export let disabled = false;
	export let commit: (text: string) => void;

	const limit = 180;
	const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
	let composing = false;
	$: draft = value;
	// Reserve the unused character slots without adding anything to the saved cue.
	$: remaining = Math.max(0, limit - Array.from(segmenter.segment(draft)).length);

	function limitInput(input: HTMLTextAreaElement) {
		const text = input.value;
		const segments = Array.from(segmenter.segment(text));
		if (segments.length > limit) {
			// Discard the overflow at the insertion, not the text after the caret.
			const end = input.selectionEnd;
			const after = segments.findIndex(s => s.index >= end);
			const boundary = after < 0 ? segments.length : after;
			const first = Math.max(0, boundary - (segments.length - limit));
			const start = segments[first].index;
			const suffix = segments[Math.min(segments.length, first + segments.length - limit)]?.index ?? text.length;
			input.value = text.slice(0, start) + text.slice(suffix);
			input.setSelectionRange(start, start);
		}
		draft = input.value;
	}

	function finish(input: HTMLTextAreaElement) {
		limitInput(input);
		draft = input.value = draft.trim() || value;
		if (draft !== value) commit(draft);
	}
</script>

<div class="cue-editor">
	<span aria-hidden="true" class="cue-measure">{draft}{'0'.repeat(remaining)}{'\u200b'}</span>
	<textarea class="cue-field" rows="1" wrap="soft" aria-label={label} value={draft} maxlength="4096" {disabled}
	on:compositionstart={() => composing = true}
	on:compositionend={e => { composing = false; limitInput(e.currentTarget); }}
	on:input={e => { if (!composing) limitInput(e.currentTarget); }}
	on:change={e => finish(e.currentTarget)}></textarea>
</div>

<style>
	.cue-editor {position:relative;align-self:start;max-height:100%;min-height:0;min-width:0;overflow:hidden;}
	.cue-field,.cue-measure {display:block;box-sizing:border-box;width:100%;white-space:pre-wrap;word-break:break-all;overflow-wrap:anywhere;padding:8px 10px;border:1px solid transparent;font:inherit;font-family:"Segoe UI",sans-serif;font-size:14px;line-height:1.45;}
	.cue-measure {visibility:hidden;pointer-events:none;}
	.cue-field {position:absolute;inset:0;height:100%;field-sizing:fixed;resize:none;overflow-y:auto;scrollbar-gutter:auto;border-color:var(--line);border-radius:6px;background:transparent;color:var(--foreground);}
	.cue-field:focus {outline:none;border-color:color-mix(in srgb,var(--quiet) 35%,transparent);box-shadow:none;}
</style>
