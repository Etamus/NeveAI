import { describe, expect, it, vi } from 'vitest';
import { messageSnapshotEqual } from './messageSnapshot';

describe('message snapshots', () => {
	const message = () => ({
		id: 'reply', content: 'old text '.repeat(10000), done: true,
		files: [{ id: 'file', url: '/image', meta: { width: 1280 } }],
		statusHistory: [{ done: false, description: 'Searching' }],
		sources: [{ document: ['source'], metadata: [{ name: 'page' }] }],
		annotation: { rating: 1 }, childrenIds: ['next'], info: { total_tokens: 20 }
	});

	it('reuses an unchanged snapshot without JSON serialization', () => {
		const source = message(), snapshot = structuredClone(source);
		const stringify = vi.spyOn(JSON, 'stringify');
		expect(messageSnapshotEqual(snapshot, source)).toBe(true);
		expect(stringify).not.toHaveBeenCalled();
		stringify.mockRestore();
	});

	it.each([
		(m: ReturnType<typeof message>) => { m.content += 'new'; },
		(m: ReturnType<typeof message>) => { m.done = false; },
		(m: ReturnType<typeof message>) => { m.files[0].meta.width = 640; },
		(m: ReturnType<typeof message>) => { m.files.push({ id: 'new', url: '/new', meta: { width: 10 } }); },
		(m: ReturnType<typeof message>) => { m.statusHistory[0].done = true; },
		(m: ReturnType<typeof message>) => { m.sources[0].metadata[0].name = 'updated'; },
		(m: ReturnType<typeof message>) => { m.annotation.rating = -1; },
		(m: ReturnType<typeof message>) => { m.childrenIds[0] = 'branch'; },
		(m: ReturnType<typeof message>) => { m.info.total_tokens = 50; }
	])('detects in-place updates without relying on source identity', (mutate) => {
		const source = message(), snapshot = structuredClone(source);
		mutate(source);
		expect(messageSnapshotEqual(snapshot, source)).toBe(false);
	});

	it('detects new and removed fields including undefined', () => {
		expect(messageSnapshotEqual({ extra: undefined }, {})).toBe(false);
		expect(messageSnapshotEqual({}, { extra: undefined })).toBe(false);
		expect(messageSnapshotEqual({ a: null }, { a: {} })).toBe(false);
		expect(messageSnapshotEqual({ a: [] }, { a: {} })).toBe(false);
		expect(messageSnapshotEqual(new Array(1), [])).toBe(false);
		expect(messageSnapshotEqual({ a: 1, b: 2 }, { b: 2, a: 1 })).toBe(true);
	});

	it('does not invalidate historical messages for another response delta', () => {
		const old = message(), snapshot = structuredClone(old);
		const active = { content: '' };
		for (let index = 0; index < 100; index++) {
			active.content += 'delta';
			expect(messageSnapshotEqual(snapshot, old)).toBe(true);
		}
	});
});
