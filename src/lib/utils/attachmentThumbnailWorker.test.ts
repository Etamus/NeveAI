import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { describe, expect, it, vi } from 'vitest';

describe('thumbnail worker cancellation', () => {
	it('aborts active fetches and skips cancelled queued sources before fetching', async () => {
		const self: any = {postMessage:vi.fn()};
		const fetch = vi.fn((_url: string, {signal}: {signal: AbortSignal}) => new Promise((_resolve, reject) => {
			signal.addEventListener('abort', () => reject(new Error('cancelled')));
		}));
		const source = readFileSync('src/lib/workers/attachment-thumbnail.worker.ts', 'utf8');
		const js = ts.transpile(source.replace('export {};', ''), {target:ts.ScriptTarget.ES2022, module:ts.ModuleKind.None});
		runInNewContext(js, {self, fetch, AbortController, setTimeout, clearTimeout});
		self.onmessage({data:{id:1,source:'/active'}});
		self.onmessage({data:{id:2,source:'/queued'}});
		await Promise.resolve();
		expect(fetch).toHaveBeenCalledTimes(1);
		self.onmessage({data:{cancel:2}});
		self.onmessage({data:{cancel:1}});
		await new Promise(resolve => setTimeout(resolve, 10));
		expect(fetch).toHaveBeenCalledTimes(1);
		self.onmessage({data:{id:3,source:'/new'}});
		await Promise.resolve();
		expect(fetch).toHaveBeenCalledTimes(2);
		self.onmessage({data:{cancel:3}});
		await new Promise(resolve => setTimeout(resolve, 10));
	});
});
