import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { describe, expect, it, vi } from 'vitest';
import { getVideoGenerationFeatures, normalizeVideoGenerationModel, snapshotVideoRequestFeatures, videoGenerationModels } from './videoGeneration';

const chat = readFileSync('src/lib/components/chat/Chat.svelte', 'utf8');
const input = readFileSync('src/lib/components/chat/MessageInput.svelte', 'utf8');

function sourceFunction(source: string, name: string) {
	const script = Array.from(source.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g), (match) => match[1]).join('\n');
	const tree = ts.createSourceFile('component.ts', script, ts.ScriptTarget.Latest, true);
	let result = '';
	function visit(node: ts.Node) {
		if (ts.isVariableDeclaration(node) && node.name.getText(tree) === name) result = node.initializer!.getText(tree);
		ts.forEachChild(node, visit);
	}
	visit(tree);
	if (!result) throw new Error(`Missing function ${name}`);
	return ts.transpile(`const action = ${result}; action;`, { target: ts.ScriptTarget.ES2022 });
}

const videoFeatures = (model = 'vdn_h3') => ({
	video_generation: true, video_generation_model: model,
	video_generation_resolution: '672p', video_generation_duration: '8s',
	video_generation_aspect_ratio: '9:16'
});

describe('video generation model selection', () => {
	it('exposes exactly the two supported models and defaults old/unknown values', () => {
		expect(videoGenerationModels).toEqual([
			{id: 'minimax_h3', label: 'Neve Video 1'}, {id: 'vdn_h3', label: 'Neve Video 1.5'}
		]);
		for (const value of [undefined, null, '', 'old', 'minimax_h3']) expect(normalizeVideoGenerationModel(value)).toBe('minimax_h3');
		expect(normalizeVideoGenerationModel('vdn_h3')).toBe('vdn_h3');
	});
	it('clones queued/explicit options so subsequent edits cannot change the request', () => {
		const features = {...videoFeatures(), nested: {value: 1}};
		const snapshot = snapshotVideoRequestFeatures(features);
		features.video_generation_model = 'minimax_h3';
		features.nested.value = 2;
		expect(snapshot.video_generation_model).toBe('vdn_h3');
		expect(snapshot.nested.value).toBe(1);
		expect(snapshotVideoRequestFeatures(videoFeatures('obsolete')).video_generation_model).toBe('minimax_h3');
		expect(snapshotVideoRequestFeatures({music_generation: true})).toEqual({music_generation: true});
	});
	it('send uses explicit or historical options before falling back to the current composer', async () => {
		const script = sourceFunction(chat, 'sendMessage');
		const prefix = script.slice(0, script.indexOf('let _chatId')) + 'return requestFeatures; }; action;';
		const current = videoFeatures('minimax_h3');
		const historical = videoFeatures();
		const send = runInNewContext(prefix, {$mobile: false, snapshotVideoRequestFeatures, getFeatures: () => current, normalizeExclusiveFeatureToggles() {}});
		const history = {messages: {user: {video_generation_features: historical}}};
		const restored = await send(history, 'user');
		expect(restored).toEqual(historical);
		historical.video_generation_model = 'minimax_h3';
		expect(restored.video_generation_model).toBe('vdn_h3');
		expect((await send(history, 'user', {features: videoFeatures()})).video_generation_model).toBe('vdn_h3');
		expect((await send({messages: {}}, 'user')).video_generation_model).toBe('minimax_h3');
	});
	it.each(['minimax_h3', 'vdn_h3'])('uses mobile defaults without mutating saved desktop choices: %s', async (model) => {
		const features = videoFeatures(model);
		const mobileFeatures = snapshotVideoRequestFeatures(features, true);
		expect(mobileFeatures).toEqual({...features, video_generation_resolution: '480p', video_generation_duration: '5s'});
		expect(snapshotVideoRequestFeatures(features, false)).toEqual(features);
		expect(features.video_generation_resolution).toBe('672p');
		expect(features.video_generation_duration).toBe('8s');
		const other = {music_generation: true, stable_diffusion: true};
		expect(snapshotVideoRequestFeatures(other, true)).toEqual(other);
		const script = sourceFunction(chat, 'sendMessage');
		const prefix = script.slice(0, script.indexOf('let _chatId')) + 'return requestFeatures; }; action;';
		const send = runInNewContext(prefix, {$mobile: true, snapshotVideoRequestFeatures, getFeatures: () => features, normalizeExclusiveFeatureToggles() {}});
		const history = {messages: {user: {video_generation_features: features}}};
		expect(await send(history, 'user')).toEqual(mobileFeatures);
		expect(await send(history, 'user', {features})).toEqual(mobileFeatures);
		expect(await send({messages: {}}, 'user')).toEqual(mobileFeatures);
	});
	it('restores persisted requests including failures without status, and legacy video statuses', () => {
		const saved = {video_generation_features: videoFeatures()};
		expect(getVideoGenerationFeatures(saved)).toEqual(videoFeatures());
		expect(getVideoGenerationFeatures({}, [saved])).toEqual(videoFeatures());
		expect(getVideoGenerationFeatures({statusHistory: [{action: 'video_generation', model: 'unknown'}]})).toEqual({
			video_generation: true, video_generation_model: 'minimax_h3',
			video_generation_resolution: '480p', video_generation_duration: '5s', video_generation_aspect_ratio: '16:9'
		});
		expect(getVideoGenerationFeatures({statusHistory: [{action: 'video_generation', model: 'vdn_h3'}]})?.video_generation_model).toBe('vdn_h3');
		expect(getVideoGenerationFeatures({statusHistory: [{action: 'music_generation'}]})).toBeNull();
	});
	it.each(['vdn_h3', 'obsolete', null])('restores local preferences with safe fallback: %s', (saved) => {
		const context = {localStorage: {getItem: (key: string) => key === 'neveai.videoModel' ? saved : null},
			normalizeVideoGenerationModel, videoResolutionOptions: ['480p', '672p'],
			videoGenerationModel: 'vdn_h3', videoGenerationResolution: '', videoGenerationDuration: '', videoGenerationAspectRatio: ''};
		runInNewContext(sourceFunction(input, 'restoreVideoPreferences'), context)();
		expect(context.videoGenerationModel).toBe(normalizeVideoGenerationModel(saved));
	});
	it('places the responsive model dropdown before resolution and removes it immediately on selection', () => {
		const start = input.indexOf('<div class="relative shrink-0" id="video-model-dropdown-container">');
		const end = input.indexOf('<div class="relative shrink-0" id="video-resolution-dropdown-container">');
		expect(start).toBeGreaterThan(0);
		expect(end).toBeGreaterThan(start);
		const selector = input.slice(start, end);
		expect(selector).toContain('use:viewportDropdown');
		expect(selector).toContain('in:fly=');
		expect(selector).not.toContain('transition:fly=');
		const click = selector.match(/on:click=\{(\(\) => \{[\s\S]*?)\}\}/)![1] + '}';
		const context = {model: {id: 'vdn_h3'}, videoGenerationModel: 'minimax_h3', showVideoModelDropdown: true, localStorage: {setItem: vi.fn()}};
		runInNewContext(`(${click})()`, context);
		expect(context.videoGenerationModel).toBe('vdn_h3');
		expect(context.showVideoModelDropdown).toBe(false);
		expect(context.localStorage.setItem).toHaveBeenCalledWith('neveai.videoModel', 'vdn_h3');
	});
	it('preserves the historical video model when editing a prompt', async () => {
		const source = readFileSync('src/lib/components/chat/Messages.svelte', 'utf8');
		const history: any = {messages: {original: {role: 'user', parentId: null, childrenIds: ['reply'], content: 'Original'},
			reply: {statusHistory: [{action: 'video_generation', model: 'vdn_h3', resolution: '672p'}]}}};
		const sendMessage = vi.fn();
		await runInNewContext(sourceFunction(source, 'editMessage'), {
			history, getVideoGenerationFeatures, selectedModels: ['local/model'], uuidv4: () => 'edited', tick: async () => {}, sendMessage
		})('original', {content: 'Edited', files: []});
		expect(history.messages.edited.video_generation_features.video_generation_model).toBe('vdn_h3');
		expect(history.messages.original.content).toBe('Original');
		expect(sendMessage).toHaveBeenCalledWith(history, 'edited');
	});
	it.each(['vdn_h3', undefined])('freezes regenerated video options before async work and restores composer state: %s', async (historicalModel) => {
		const message: any = {id: 'reply', parentId: 'user', model: 'local/model', statusHistory: [{action: 'video_generation', model: historicalModel}]};
		const history = {currentId: 'reply', messages: {user: {id: 'user'}, reply: message}};
		let ready!: (value: boolean) => void;
		const sendMessageSocket = vi.fn();
		const context: any = {history, getVideoGenerationFeatures, normalizeVideoGenerationModel, structuredClone,
			videoGenerationEnabled: false, videoGenerationModel: 'vdn_h3', videoGenerationResolution: '672p', videoGenerationDuration: '8s', videoGenerationAspectRatio: '9:16',
			stableDiffusionEnabled: false, musicGenerationEnabled: false, stableDiffusionQuality: 'neve_image_2', stableDiffusionStyle: 'none', stableDiffusionResolution: '1:1', stableDiffusionModeOptions: {mode: 'normal'},
			$models: [{id: 'local/model'}], $chatId: 'chat', localStorage: {}, $currentChatPage: 1,
			ensureLocalModelsReady: vi.fn(() => new Promise(resolve => {ready = resolve;})),
			stopContentFlush() {}, tick: async () => {}, anchorVisualMediaGeneration: async () => {}, saveChatHandler: async () => {},
			getChatEventEmitter: async () => null, createMessagesList: () => [], sendMessageSocket,
			currentChatPage: {set() {}}, chats: {set() {}}, getChatList: async () => []};
		const getFeatures = 'function getFeatures() { return { video_generation: videoGenerationEnabled, video_generation_model: videoGenerationModel, video_generation_resolution: videoGenerationResolution, video_generation_duration: videoGenerationDuration, video_generation_aspect_ratio: videoGenerationAspectRatio }; }\n';
		const pending = runInNewContext(getFeatures + sourceFunction(chat, 'regenerateResponse'), context)(message);
		expect(context.ensureLocalModelsReady).toHaveBeenCalledOnce();
		context.videoGenerationModel = 'minimax_h3';
		ready(true);
		await pending;
		expect(sendMessageSocket.mock.calls[0][5].video_generation_model).toBe(historicalModel ?? 'minimax_h3');
		expect(context.videoGenerationModel).toBe('vdn_h3');
		expect(context.videoGenerationEnabled).toBe(false);
		expect(history.messages.reply.video_generation_features.video_generation_model).toBe(historicalModel ?? 'minimax_h3');
	});
});
