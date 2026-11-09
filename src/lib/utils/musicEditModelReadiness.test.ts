import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { resolve } from 'node:path';
import ts from 'typescript';
import { describe, expect, it, vi } from 'vitest';
import { getVideoGenerationFeatures, snapshotVideoRequestFeatures } from './videoGeneration';
import { normalizeLearningRequestFeatures } from './guidedLearning';

function sourceFunction(file: string, name: string, prefix = false) {
	const source = Array.from(readFileSync(resolve(file), 'utf8').matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g), match => match[1]).join('\n');
	const tree = ts.createSourceFile(file + '.ts', source, ts.ScriptTarget.Latest, true);
	let arrow: ts.ArrowFunction | undefined;
	function visit(node: ts.Node) {
		if (ts.isVariableDeclaration(node) && node.name.getText(tree) === name && node.initializer && ts.isArrowFunction(node.initializer)) arrow = node.initializer;
		ts.forEachChild(node, visit);
	}
	visit(tree);
	if (!arrow || !ts.isBlock(arrow.body)) throw new Error('Missing source function: ' + name);
	if (!prefix) return arrow.getText(tree);
	const loop = arrow.body.statements.findIndex(ts.isForOfStatement);
	if (loop < 0) throw new Error('Missing response creation loop');
	return arrow.getText(tree).slice(0, arrow.body.getStart(tree) - arrow.getStart(tree)) + '{\n' +
		arrow.body.statements.slice(0, loop).map(node => node.getText(tree)).join('\n') + '\nreturn selectedModelIds;\n}';
}

function compile(source: string, globals: Record<string, unknown>) {
	const js = ts.transpile(`const action = ${source};`, {target: ts.ScriptTarget.ES2022});
	return runInNewContext(js + '\naction;', {structuredClone, getVideoGenerationFeatures, snapshotVideoRequestFeatures, normalizeLearningRequestFeatures, ...globals});
}

const sendSource = sourceFunction('src/lib/components/chat/Chat.svelte', 'sendMessage', true);
const editSource = sourceFunction('src/lib/components/chat/Messages.svelte', 'editMessage');

function setup(features: Record<string, boolean>, ensure: ReturnType<typeof vi.fn>) {
	const history: any = {currentId: 'reply', messages: {
		original: {id: 'original', parentId: null, role: 'user', content: 'Original music request', childrenIds: ['reply']},
		reply: {id: 'reply', parentId: 'original', role: 'assistant', done: true, content: '', files: [{type: 'audio'}]}
	}};
	const sent = vi.fn();
	const send = compile(sendSource, {
		$mobile: false,
		normalizeExclusiveFeatureToggles() {}, getFeatures: () => features,
		$chatId: 'local:music-edit-test', atSelectedModel: undefined, selectedModels: ['local/qwen'],
		ensureLocalModelsReady: ensure
	});
	const edit = compile(editSource, {
		selectedModels: ['local/qwen'], history, uuidv4: () => 'edited', tick: async () => {},
		sendMessage: async (...args: unknown[]) => {const ready = await send(...args); if (ready) sent(ready);},
		toast: {error: vi.fn()}, $i18n: {t: (value: string) => value}
	});
	return {edit, send, sent, history};
}

describe('edited music requests reload the selected planner model', () => {
	it('waits for the unloaded model before submitting the edited branch', async () => {
		let ready!: (value: boolean) => void;
		const ensure = vi.fn(() => new Promise<boolean>(resolve => {ready = resolve;}));
		const test = setup({music_generation: true}, ensure);
		const files = [{id: 'lyrics', type: 'file'}];
		const pending = test.edit('original', {content: 'Edited music request', files});
		await vi.waitFor(() => expect(ensure).toHaveBeenCalledOnce());
		expect(ensure).toHaveBeenCalledWith(['local/qwen'], {textOnly: true});
		expect(test.sent).not.toHaveBeenCalled();
		ready(true);
		await pending;
		expect(test.sent).toHaveBeenCalledWith(['local/qwen']);
		expect(test.history.messages.edited.content).toBe('Edited music request');
		expect(test.history.messages.edited.files).toEqual(files);
		expect(test.history.messages.original.content).toBe('Original music request');
	});
	it('does not start planning if loading fails', async () => {
		const test = setup({music_generation: true}, vi.fn().mockResolvedValue(false));
		await test.edit('original', {content: 'Edited request', files: []});
		expect(test.sent).not.toHaveBeenCalled();
	});
	it.each([{}, {stable_diffusion: true}, {video_generation: true}])('leaves non-music send paths unchanged: %j', async features => {
		const ensure = vi.fn().mockResolvedValue(true);
		const test = setup(features, ensure);
		await test.edit('original', {content: 'Edited request', files: []});
		expect(ensure).not.toHaveBeenCalled();
		expect(test.sent).toHaveBeenCalledOnce();
	});
	it('loads an explicitly selected model, not a different chat selection', async () => {
		const ensure = vi.fn().mockResolvedValue(true);
		const test = setup({music_generation: true}, ensure);
		await test.send(test.history, 'original', {modelId: 'local/other'});
		expect(ensure).toHaveBeenCalledWith(['local/other'], {textOnly: true});
	});
});
