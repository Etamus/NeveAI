import type { Token } from 'marked';

export type StreamingPaintContext = { suppress: boolean };

// Reparenting parsed text must not replay the new-text fade over existing words.
export function changesVisibleStructure(previous: Token[], next: Token[]): boolean {
	const changed = (before: any, after: any): boolean => {
		if (before === after) return false;
		if (Array.isArray(before)) {
			return !Array.isArray(after) || before.some((item, index) => changed(item, after[index]));
		}
		if (!before || typeof before !== 'object') return false;
		if (!after || before.type !== after.type) return true;
		const text = before.raw ?? before.text;
		const updated = after.raw ?? after.text;
		if (typeof text === 'string' && (typeof updated !== 'string' || !updated.startsWith(text))) return true;
		return ['tokens', 'items', 'header', 'rows'].some(key =>
			Array.isArray(before[key]) && changed(before[key], after[key]));
	};
	return changed(previous, next);
}
