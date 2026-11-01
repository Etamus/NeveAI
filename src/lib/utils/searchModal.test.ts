import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';
import {describe, expect, it, vi} from 'vitest';

const source = readFileSync('src/lib/components/layout/SearchModal.svelte', 'utf8');
function action(name: string, scope: Record<string, any>) {
	const script = Array.from(source.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g), match => match[1]).join('\n');
	const tree = ts.createSourceFile('SearchModal.ts', script, ts.ScriptTarget.Latest, true);
	let arrow = '';
	function visit(node: ts.Node) {
		if (ts.isVariableDeclaration(node) && node.name.getText(tree) === name) arrow = node.initializer!.getText(tree);
		ts.forEachChild(node, visit);
	}
	visit(tree);
	return runInNewContext(ts.transpile(`const action = ${arrow}; action;`, {target: ts.ScriptTarget.ES2022}), scope);
}
function keyboardScope(extra = {}) {
	return {show: true, query: 'viagem', keyboardSelection: false, selectedIdx: 0,
		chatListLoading: false, chatList: [{id: 'one'}], actions: [{}],
		searchShell: {querySelector: vi.fn(() => ({click: vi.fn(), scrollIntoView: vi.fn()}))},
		searchHandler: vi.fn(), onClose: vi.fn(), tick: async () => {}, ...extra};
}
const key = (key: string, extra = {}) => ({key, isComposing: false, preventDefault: vi.fn(), stopPropagation: vi.fn(), target: {closest: () => null}, ...extra});

describe('Search modal event isolation', () => {
	it('plain Enter searches instead of choosing the new-conversation action', () => {
		const scope = keyboardScope();
		const event = key('Enter');
		action('onKeyDown', scope)(event);
		expect(scope.searchHandler).toHaveBeenCalledWith(true);
		expect(scope.searchShell.querySelector).not.toHaveBeenCalled();
		expect(scope.show).toBe(true);
		expect(event.preventDefault).toHaveBeenCalledOnce();
		expect(event.stopPropagation).toHaveBeenCalledOnce();
	});
	it('Enter activates only an explicitly selected current result', () => {
		const click = vi.fn();
		const scope = keyboardScope({keyboardSelection: true, searchShell: {querySelector: vi.fn(() => ({click}))}});
		action('onKeyDown', scope)(key('Enter'));
		expect(click).toHaveBeenCalledOnce();
		expect(scope.searchHandler).not.toHaveBeenCalled();
	});
	it('a pending query cannot open stale results', () => {
		const scope = keyboardScope({keyboardSelection: true, chatListLoading: true});
		action('onKeyDown', scope)(key('Enter'));
		expect(scope.searchHandler).toHaveBeenCalledWith(true);
		expect(scope.searchShell.querySelector).not.toHaveBeenCalled();
	});
	it('first ArrowDown selects a matching chat, not the new-conversation action', async () => {
		const scope = keyboardScope({selectedIdx: null});
		action('onKeyDown', scope)(key('ArrowDown'));
		await Promise.resolve();
		expect(scope.selectedIdx).toBe(1);
		expect(scope.keyboardSelection).toBe(true);
	});
	it('does not hijack composition or native Enter on focused buttons', () => {
		const scope = keyboardScope();
		const composing = key('Enter', {isComposing: true});
		const handler = action('onKeyDown', scope);
		handler(composing);
		expect(composing.preventDefault).not.toHaveBeenCalled();
		const button = key('Enter', {target: {closest: () => ({})}});
		handler(button);
		expect(button.preventDefault).not.toHaveBeenCalled();
		expect(button.stopPropagation).toHaveBeenCalledOnce();
		expect(scope.searchHandler).not.toHaveBeenCalled();
	});
	it('Escape closes only the search and is contained there', () => {
		const scope = keyboardScope();
		const event = key('Escape');
		action('onKeyDown', scope)(event);
		expect(scope.show).toBe(false);
		expect(scope.onClose).toHaveBeenCalledOnce();
		expect(event.stopPropagation).toHaveBeenCalledOnce();
	});
	it('submits the complete query on page one, ignoring stale outer pagination', async () => {
		const scope = {show: true, query: 'viagem completa', page: 9, searchRequestId: 0, previewRequestId: 0,
			searchDebounceTimeout: null, chatList: null, localStorage: {token: 'fixture'}, clearTimeout() {},
			getChatListBySearchText: vi.fn(async () => [{id: 'one'}]), getChatList: vi.fn(), persistSearchCache: vi.fn()};
		await action('searchHandler', scope)(true);
		expect(scope.getChatListBySearchText).toHaveBeenCalledWith('fixture', 'viagem completa', 1);
		expect(scope.chatList).toEqual([{id: 'one'}]);
	});
	it('the input passes its current value explicitly before the parent starts searching', () => {
		const input = readFileSync('src/lib/components/layout/Sidebar/SearchInput.svelte', 'utf8');
		expect(input).toContain('value = event.currentTarget.value;');
		expect(input).toContain("dispatch('input', value)");
		expect(source).toContain('query = event.detail; void searchHandler();');
		expect(input).not.toContain('search-option-');
	});
});
