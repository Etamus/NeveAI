import assert from 'node:assert/strict';
import {once} from 'node:events';
import {resolve} from 'node:path';
import {chromium} from '../logs/ui-image-26/node_modules/playwright/index.mjs';

const origin = process.env.NEVE_TEST_ORIGIN || 'http://localhost:8080';
const readyToTalk = /^(Go ahead|Pode falar)\.\.\.$/;
let mockServer;
if (process.env.NEVE_VOICE_MOCK_SOCKET) {
	const {WebSocketServer} = await import('ws');
	mockServer = new WebSocketServer({host:'127.0.0.1',port:0});
	await once(mockServer, 'listening');
	mockServer.on('connection', ws => {
		let bytes = 0;
		let frameBytes = 0;
		ws.on('message', (message, binary) => {
			if (binary) {
				bytes += message.length;
				while (frameBytes && bytes >= frameBytes) {
					ws.send(Buffer.alloc(6400));
					bytes -= frameBytes;
				}
			} else if (message.toString() === 'stop') {
				ws.send(JSON.stringify({type:'stopped'}));
			} else {
				frameBytes = Math.round(JSON.parse(message.toString()).sample_rate * 3200 / 24000) * 2;
				bytes = 0;
				ws.send(JSON.stringify({type:'preparing'}));
				setTimeout(() => {
					if (ws.readyState !== ws.OPEN) return;
					ws.send(JSON.stringify({type:'started',sample_rate:24000}));
					ws.send(Buffer.alloc(6400));
				}, 220);
			}
		});
	});
}
const browser = await chromium.launch({ executablePath: process.env.NEVE_TEST_BROWSER, args: [
	'--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
	'--use-file-for-fake-audio-capture=' + resolve(process.env.NEVE_VOICE_TEST_WAV || 'logs/haru-question-0.wav')
] });
try {
	for (const width of (mockServer ? [1440, 390, 320] : [1440, 390])) {
		const page = await browser.newPage({viewport:{width,height:860}, permissions:['microphone']});
		if (mockServer) {
			await page.addInitScript(port => {
				window.WebSocket = class extends window.WebSocket {
					constructor(url, ...args) {
						const endpoint = new URL(url, location.href);
						super(endpoint.pathname === '/api/v1/audio/voice'
							? `ws://127.0.0.1:${port}${endpoint.pathname}` : url, ...args);
					}
				};
			}, mockServer.address().port);
		}
		await page.addInitScript(theme => {
			localStorage.setItem('theme', theme);
			window.voiceAudioTest = { timeline: [], microphoneGraphs: 0 };
			const createSource = AudioContext.prototype.createBufferSource;
			AudioContext.prototype.createBufferSource = function () {
				const node = createSource.call(this);
				const start = node.start.bind(node);
				node.start = when => {
					if (node.buffer?.length === 6000 && node.buffer.sampleRate === 24000) {
						window.voiceAudioTest.timeline.push('chime-started');
						node.addEventListener('ended', () => window.voiceAudioTest.timeline.push('chime-ended'));
					}
					return start(when);
				};
				return node;
			};
			const createMicSource = AudioContext.prototype.createMediaStreamSource;
			AudioContext.prototype.createMediaStreamSource = function (stream) {
				window.voiceAudioTest.microphoneGraphs++;
				return createMicSource.call(this, stream);
			};
			const getUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
			navigator.mediaDevices.getUserMedia = constraints => {
				window.voiceAudioTest.timeline.push('microphone-requested');
				return getUserMedia(constraints);
			};
		}, width === 320 ? 'light' : 'dark');
		let custom = false;
		let rejectImport = false;
		let completeImport;
		const importGate = new Promise(resolve => { completeImport = resolve; });
		const changes = [];
		await page.route('**/api/v1/audio/voice/profile', async route => {
			if (route.request().method() === 'POST') {
				assert(route.request().headers()['content-type'].includes('multipart/form-data'));
				if (rejectImport) {
					changes.push('rejected');
					return route.fulfill({status:422,json:{detail:'Could not read this voice recording.'}});
				}
				changes.push('import');
				await importGate;
				custom = true;
			} else if (route.request().method() === 'DELETE') {
				changes.push('remove');
				custom = false;
			}
			return route.fulfill({json:{custom}});
		});
		const errors = [];
		page.on('pageerror', error => errors.push(error.message));
		await page.goto(origin, {waitUntil:'networkidle'});
		const voice = page.getByRole('button', {name:/^(Voice mode|Modo de voz)$/i});
		await voice.waitFor();
		const prompt = page.locator('#chat-input');
		await prompt.fill('Test message');
		await voice.waitFor({state:'hidden'});
		await prompt.fill('');
		await voice.waitFor();
		const stream = page.waitForEvent('websocket', {timeout:8000,predicate: ws => ws.url().endsWith('/api/v1/audio/voice')});
		void stream.catch(() => {});
		await voice.click();
		const preparing = page.getByText(/^(Preparing Neve|Preparando Neve)\.\.\.$/);
		await preparing.waitFor();
		const mute = page.getByRole('button',{name:/^(Mute microphone|Silenciar)$/i});
		const end = page.getByRole('button',{name:/^(End voice mode|Encerrar)$/i});
		const language = page.getByRole('button',{name:/^(Voice language|Idioma da voz)$/i});
		const [prepEnd, prepStatus, prepWave] = await Promise.all([
			end.boundingBox(), preparing.boundingBox(), page.locator('[data-haru-waveform]').boundingBox()
		]);
		assert.equal(await language.count(), 0);
		assert.equal(await mute.count(), 0);
		assert(Math.abs(prepEnd.x + prepEnd.width/2 - prepWave.x - prepWave.width/2) < 1);
		assert(prepEnd.y >= prepStatus.y + prepStatus.height);
		const statusLift = await preparing.evaluate(el => {
			const raised = el.getBoundingClientRect().top;
			el.classList.remove('-translate-y-2');
			const original = el.getBoundingClientRect().top;
			el.classList.add('-translate-y-2');
			return original - raised;
		});
		assert(statusLift >= 7 && statusLift <= 11);
		if (width === 1440) {
			const [panelWidth, bottomPadding] = await page.locator('[data-haru-waveform]').evaluate(el => {
				const content = el.parentElement;
				const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
				return [content.parentElement.getBoundingClientRect().width / rem,
					parseFloat(getComputedStyle(content).paddingBottom) / rem];
			});
			assert(Math.abs(panelWidth - 28.5) < 0.05);
			assert.equal(bottomPadding, 2.5);
		}
		await page.screenshot({path:`logs/haru-controls-preparing-${width}.png`});
		const ws = await stream.catch(async error => {
			console.error('Voice modal:', await page.getByRole('dialog').allTextContents(), errors);
			throw error;
		});
		const captured = ws.waitForEvent('framesent', {predicate: e => Buffer.isBuffer(e.payload) && e.payload.length > 0});
		const playback = ws.waitForEvent('framereceived', {predicate: e => Buffer.isBuffer(e.payload) && e.payload.length === 6400});
		await page.getByText(readyToTalk).waitFor({timeout:90000});
		const defaultVoice = page.getByText(/^(Default voice|Voz padrão)$/);
		const importedVoice = page.getByText(/^(Imported voice|Voz importada)$/);
		await defaultVoice.waitFor();
		await Promise.all([captured,playback]);
		ws.on('framereceived', ({payload}) => {
			if (typeof payload !== 'string') return;
			const type = JSON.parse(payload).type;
			if (type === 'stopped' || type === 'started') changes.push(type);
		});
		assert.equal(await page.getByRole('button',{name:/Opening for the next conversation|Abertura da pr.xima conversa/i}).count(), 0);
		assert.equal(await page.getByRole('dialog').getByRole('button', {name:/^(Close|Fechar)$/i}).count(), 0);
		const heading = page.getByRole('heading', {name:/^(Voice mode|Modo de voz)$/i});
		assert.equal(await heading.evaluate(el => el.getBoundingClientRect().width), 1);
		assert(await page.locator('[data-haru-waveform]').evaluate(el => {
			const {width, height} = el.getBoundingClientRect();
			const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
			return Math.abs(width - height) < 0.5 &&
				Math.abs(height - 6.5 * rem) < 0.5 &&
				Math.abs(el.querySelector('svg').getBoundingClientRect().width - 3.5 * rem) < 0.5;
		}));
		const importVoice = page.getByRole('button',{name:/^Import voice$|^Importar voz$/i});
		assert((await language.boundingBox()).x < (await importVoice.boundingBox()).x);
		const chooser = page.waitForEvent('filechooser');
		await importVoice.click();
		await (await chooser).setFiles(resolve('logs/haru-question-0.wav'));
		const cloning = page.getByRole('status').filter({hasText:/^(Cloning voice|Clonando voz)\.\.\.$/});
		await cloning.waitFor();
		assert.equal(await language.count(), 0);
		assert.equal(await importVoice.count(), 0);
		completeImport();
		const remove = page.getByRole('button',{name:/^Remove voice$|^Remover voz$/i});
		await remove.waitFor();
		await page.getByText(readyToTalk).waitFor();
		await importedVoice.waitFor();
		assert.equal(await defaultVoice.count(), 0);
		assert.deepEqual(changes, ['stopped', 'import', 'started']);
		await ws.waitForEvent('framesent', {predicate: ({payload}) => Buffer.isBuffer(payload) && payload.some(byte => byte !== 0)});
		const verifyAudio = async microphoneGraphs => assert.deepEqual(
			await page.evaluate(() => window.voiceAudioTest),
			{timeline: ['microphone-requested', 'chime-started', 'chime-ended'], microphoneGraphs}
		);
		await verifyAudio(2);
		await page.screenshot({path:`logs/haru-controls-imported-${width}.png`});
		if (width === 1440) {
			rejectImport = true;
			const replacement = page.waitForEvent('filechooser');
			await page.getByRole('button',{name:/^Replace voice$|^Trocar voz$/i}).click();
			await (await replacement).setFiles(resolve('logs/haru-question-0.wav'));
			await page.getByText(/^(Could not read this voice recording|Não foi possível ler essa gravação)\.$/i).waitFor();
			await page.getByText(readyToTalk).waitFor();
			assert.deepEqual(changes.splice(3), ['stopped', 'rejected', 'started']);
			assert(custom, 'rejected replacement must keep the previous profile');
			await verifyAudio(3);
		}
		await remove.click();
		await remove.waitFor({state:'hidden'});
		await page.getByText(readyToTalk).waitFor();
		await defaultVoice.waitFor();
		assert.equal(await importedVoice.count(), 0);
		assert.deepEqual(changes, ['stopped', 'import', 'started', 'stopped', 'remove', 'started']);
		await verifyAudio(width === 1440 ? 4 : 3);
		const active = page.getByRole('status').filter({hasText:readyToTalk});
		const [endBox, langBox, statusBox, muteBox, waveBox, importBox] = await Promise.all([
			end.boundingBox(), language.boundingBox(), active.boundingBox(), mute.boundingBox(),
			page.locator('[data-haru-waveform]').boundingBox(), importVoice.boundingBox()
		]);
		assert(endBox.x < statusBox.x && statusBox.x < muteBox.x);
		assert(Math.abs(statusBox.x + statusBox.width/2 - waveBox.x - waveBox.width/2) < 1);
		assert(Math.abs((statusBox.x - endBox.x - endBox.width) - (muteBox.x - statusBox.x - statusBox.width)) < 1);
		assert(Math.abs(endBox.y - muteBox.y) < 1);
		const rem = await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
		for (const button of [endBox, muteBox]) {
			assert(Math.abs(button.width - 2.75 * rem) < 0.5);
			assert(Math.abs(button.height - button.width) < 0.5);
		}
		const defaultVoiceBox = await defaultVoice.boundingBox();
		assert(defaultVoiceBox.y + defaultVoiceBox.height < statusBox.y);
		assert(langBox.x + langBox.width < waveBox.x && importBox.x > waveBox.x + waveBox.width);
		assert(Math.abs(langBox.y + langBox.height/2 - importBox.y - importBox.height/2) < 1);
		assert(langBox.y + langBox.height < waveBox.y);
		const readHeaderButtonStyle = el => {
			const style = getComputedStyle(el);
			const icon = el.querySelector('svg');
			return [style.backgroundColor, style.color, style.borderRadius, el.offsetWidth, el.offsetHeight,
				icon.getBoundingClientRect().width, icon.getAttribute('stroke-width')];
		};
		await page.mouse.move(0, 0);
		const normalStyle = await importVoice.evaluate(readHeaderButtonStyle);
		assert.deepEqual(await language.evaluate(readHeaderButtonStyle), normalStyle);
		await importVoice.hover();
		const hoverStyle = await importVoice.evaluate(readHeaderButtonStyle);
		assert.notEqual(hoverStyle[0], normalStyle[0]);
		await language.hover();
		assert.deepEqual(await language.evaluate(readHeaderButtonStyle), hoverStyle);
		await page.mouse.move(0, 0);
		await page.screenshot({path:`logs/haru-controls-${width}.png`});
		if (width === 1440) {
			await language.click();
			const nextLanguage = ws.waitForEvent('framesent', {predicate: ({payload}) =>
				typeof payload === 'string' && payload.startsWith('{') && JSON.parse(payload).language === 'en'});
			await page.getByRole('menuitemradio',{name:/^English$|^Ingl.s$/i}).click();
			await nextLanguage;
			await active.waitFor({timeout:90000});
			await ws.waitForEvent('framesent', {predicate: ({payload}) => Buffer.isBuffer(payload) && payload.some(byte => byte !== 0)});
			assert.equal(await page.evaluate(() => localStorage.getItem('neveai.voice.language')), 'en');
			await verifyAudio(5);
		}
		await mute.click();
		const unmute = page.getByRole('button',{name:/^(Unmute microphone|Dessilenciar)$/i});
		await unmute.waitFor();
		await page.getByRole('status').filter({hasText:/^(Muted|Silenciado)\.$/}).waitFor();
		await defaultVoice.waitFor();
		await unmute.click();
		await active.waitFor();
		const closed = ws.waitForEvent('close');
		await end.evaluate(el => {
			const rect = el.getBoundingClientRect();
			const icon = el.querySelector('svg').getBoundingClientRect();
			if (Math.abs(rect.x + rect.width / 2 - icon.x - icon.width / 2) > 0.5 ||
				Math.abs(rect.y + rect.height / 2 - icon.y - icon.height / 2) > 0.5) throw new Error('Off-center hang-up icon');
		});
		await end.click();
		await closed;
		await page.waitForFunction(() => window.voiceAudioTest.timeline.filter(event => event === 'chime-ended').length === 2);
		if (width === 1440) {
			await new Promise(resolve => setTimeout(resolve, 600));
			const next = page.waitForEvent('websocket', {predicate: ws => ws.url().endsWith('/api/v1/audio/voice')});
			await voice.click();
			const session = await next;
			const options = await session.waitForEvent('framesent', {predicate: e => typeof e.payload === 'string'});
			assert(!Object.hasOwn(JSON.parse(options.payload), 'spontaneous'));
			assert.equal(JSON.parse(options.payload).language, 'en');
			await page.getByText(readyToTalk).waitFor();
			await end.click();
		}
		assert.deepEqual(errors, []);
		await page.close();
		await new Promise(resolve => setTimeout(resolve,600));
		console.log('PASS: built composer, duplex PCM, mute, hang-up;',width);
	}
	const animation = await browser.newPage({
		viewport:{width:900,height:700}, permissions:['microphone'], reducedMotion:'reduce'
	});
	const voicedFrame = Buffer.alloc(6400);
	for (let i = 0; i < voicedFrame.length; i += 2) {
		const amplitude = 85 + Math.floor(i / 1280) * 28;
		voicedFrame.writeInt16LE(i % 64 < 32 ? amplitude : -amplitude, i);
	}
	await animation.routeWebSocket('**/api/v1/audio/voice', ws => {
		let count = 0;
		ws.onMessage(message => {
			if (typeof message === 'string') ws.send(JSON.stringify({type:'started',sample_rate:24000}));
			else if (++count % 3 === 0) ws.send(count >= 9 && count <= 21 ? voicedFrame : Buffer.alloc(6400));
		});
	});
	await animation.goto(origin, {waitUntil:'networkidle'});
	await animation.getByRole('button', {name:/^(Voice mode|Modo de voz)$/i}).click();
	const waveform = animation.locator('[data-haru-waveform] svg.speaking');
	await waveform.waitFor();
	const bar = waveform.locator('path').first();
	const first = await bar.getAttribute('style');
	assert(first.includes('scaleY'));
	await animation.waitForFunction(first => {
		const path = document.querySelector('[data-haru-waveform] svg.speaking path');
		return path && path.getAttribute('style') !== first;
	}, first);
	await waveform.waitFor({state:'detached'});
	console.log('PASS: waveform follows quiet PCM with reduced motion and stops on silence');
	await animation.close();

	const fallbackCapture = await browser.newPage({ permissions: ['microphone'] });
	await fallbackCapture.addInitScript(() => {
		const Worklet = window.AudioWorkletNode;
		window.AudioWorkletNode = class extends Worklet {
			constructor(context, name, options) {
				super(context, name, options);
				if (name === 'haru-capture') {
					Object.defineProperty(this.port, 'onmessage', { set() {}, get: () => null });
				}
			}
		};
	});
	let deliveredMicAudio;
	const nonSilentMic = new Promise(resolve => { deliveredMicAudio = resolve; });
	await fallbackCapture.routeWebSocket('**/api/v1/audio/voice', ws => {
		let bytes = 0;
		ws.onMessage(payload => {
			if (typeof payload === 'string') {
				ws.send(JSON.stringify({ type: 'started', sample_rate: 24000 }));
				return;
			}
			if (payload.some(byte => byte !== 0)) deliveredMicAudio();
			bytes += payload.length;
			if (bytes >= 6400) {
				ws.send(Buffer.alloc(6400));
				bytes -= 6400;
			}
		});
	});
	await fallbackCapture.goto(origin, {waitUntil:'networkidle'});
	await fallbackCapture.getByRole('button', {name:/^(Voice mode|Modo de voz)$/i}).click();
	let captureDeadline;
	try {
		await Promise.race([nonSilentMic, new Promise((_, reject) => {
			captureDeadline = setTimeout(() => reject(new Error('Fallback sent no audible mic input')), 10000);
		})]);
	} finally {
		clearTimeout(captureDeadline);
		await fallbackCapture.close();
	}
	console.log('PASS: actual PCM reached the websocket after a silent worklet was replaced');

	for (const error of ['NotFoundError', 'NotAllowedError']) {
		const unavailable = await browser.newPage();
		await unavailable.addInitScript(errorName => {
			navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('', errorName); };
			window.voiceModalOpened = false;
			new MutationObserver(records => {
				if (records.some(record => [...record.addedNodes].some(node =>
					node instanceof Element && (node.matches('[data-haru-waveform]') || node.querySelector('[data-haru-waveform]'))
				))) window.voiceModalOpened = true;
			}).observe(document, {childList:true,subtree:true});
		}, error);
		let voiceConnections = 0;
		unavailable.on('websocket', ws => { if (ws.url().endsWith('/api/v1/audio/voice')) voiceConnections++; });
		await unavailable.goto(origin, {waitUntil:'networkidle'});
		await unavailable.getByRole('button', {name:/^(Voice mode|Modo de voz)$/i}).click();
		await unavailable.getByText(/^(Microphone access was not available|Não foi possível acessar o microfone)\.$/).waitFor();
		assert.equal(await unavailable.evaluate(() => window.voiceModalOpened), false);
		assert.equal(voiceConnections, 0);
		await unavailable.close();
	}
	console.log('PASS: missing microphone and denied permission show a toast without opening the modal or connecting to Haru');
} finally {
	await browser.close();
	if (mockServer) await new Promise(resolve => mockServer.close(resolve));
}
