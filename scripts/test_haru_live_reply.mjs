import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { setTimeout as wait } from 'node:timers/promises';
import { chromium } from '../logs/ui-image-26/node_modules/playwright/index.mjs';

// Deliver a spoken fixture after the live backend has initialized. The UI still
// uses the real capture worklet, WebSocket and playback graph.
const origin = process.env.NEVE_TEST_ORIGIN || 'http://localhost:8080';
const native = process.env.NEVE_VOICE_NATIVE === '1';
let browser, host;
try {
	if (native) {
		const installed = JSON.parse(await readFile('.desktop/installed.json', 'utf8'));
		const port = 9246;
		host = spawn(resolve('.desktop', installed.host), [
			'--root', process.cwd(), '--runtime', resolve('.desktop', installed.runtime),
			'--profile', resolve('logs/haru-spontaneous-webview/profile'), '--url', origin
		], {
			windowsHide: true,
			env: {...process.env, NEVE_WEBVIEW2_TEST_MODE: '1', NEVE_WEBVIEW2_DEBUG_PORT: String(port)}
		});
		for (let attempt = 0; attempt < 80 && !browser && host.exitCode === null; attempt++) {
			browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`, {timeout: 400}).catch(() => null);
			if (!browser) await wait(200);
		}
		assert(browser, 'Native WebView2 test window did not start');
	} else {
		browser = await chromium.launch({executablePath: process.env.NEVE_TEST_BROWSER});
	}
	const clip = (await readFile(process.env.NEVE_VOICE_TEST_WAV || 'logs/haru-question-2.wav')).toString('base64');
	const lead = Number(process.env.NEVE_VOICE_TEST_LEAD ?? 6);
	const context = native ? browser.contexts()[0] : undefined;
	const page = context ? context.pages()[0] ?? await context.waitForEvent('page') : await browser.newPage();
	if (native) await page.getByRole('button', { name: /^(Voice mode|Modo de voz)$/i }).waitFor();
	await page.addInitScript(({encoded, lead}) => {
		localStorage.setItem('neveai.voice.language', 'pt');
		window.haruPlaybackTiming = [];
		const start = AudioBufferSourceNode.prototype.start;
		AudioBufferSourceNode.prototype.start = function (when, ...args) {
			if (this.buffer?.sampleRate === 24000 && this.buffer.length === 3200) {
				const samples = this.buffer.getChannelData(0);
				if (samples.some(value => Math.abs(value) > 500 / 32768)) {
					window.haruPlaybackTiming.push(Math.max(0, when - this.context.currentTime) * 1000);
				}
			}
			return start.call(this, when, ...args);
		};
		navigator.mediaDevices.getUserMedia = async () => {
			const context = new AudioContext();
			const input = context.createMediaStreamDestination();
			const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
			const buffer = await context.decodeAudioData(bytes.buffer);
			const source = context.createBufferSource();
			source.buffer = buffer;
			source.connect(input);
			window.speakFixture = () => new Promise(resolve => {
				source.onended = resolve;
				source.start(context.currentTime + lead);
			});
			void context.resume();
			return input.stream;
		};
	}, {encoded: clip, lead});
	if (native) await page.reload({waitUntil: 'networkidle'});
	else await page.goto(origin, {waitUntil: 'networkidle'});
	if (native) assert(await page.evaluate(() => window.__NEVE_WEBVIEW2__ === true));
	const connected = page.waitForEvent('websocket', { predicate: ws => ws.url().endsWith('/api/v1/audio/voice') });
	await page.getByRole('button', { name: /^(Voice mode|Modo de voz)$/i }).click();
	const ws = await connected;
	const above = ({payload}) => {
		if (!Buffer.isBuffer(payload)) return false;
		for (let i = 0; i + 1 < payload.length; i += 2) {
			if (Math.abs(payload.readInt16LE(i)) > 500) return true;
		}
		return false;
	};
	let speakingInput = false, utteranceEnded, firstReply, openingFrames = 0, replyFrames = 0;
	const mic = ws.waitForEvent('framesent', {
		timeout: 48000,
		predicate: frame => (speakingInput ||= above(frame))
	});
	ws.on('framereceived', frame => {
		if (!above(frame)) return;
		if (!speakingInput) openingFrames++;
		if (utteranceEnded !== undefined) {
			firstReply ??= performance.now();
			replyFrames++;
		}
	});
	await page.getByText(/^(Pode falar|Go ahead)\.\.\.$/).waitFor({ timeout: 35000 });
	const playback = page.locator('[data-haru-waveform] svg.speaking');
	const spokenInput = page.evaluate(() => window.speakFixture());
	await playback.waitFor({timeout: Math.ceil(lead * 1000) - 200});
	assert(!speakingInput, 'Opening must reach audio output before the microphone receives speech');
	await mic;
	await spokenInput;
	utteranceEnded = performance.now();
	await ws.waitForEvent('framereceived', {timeout: 12000, predicate: () => replyFrames >= 5});
	await playback.waitFor({timeout: 5000});
	assert(openingFrames >= 5, 'Expected sustained audio in the opening');
	const playbackTiming = await page.evaluate(() => window.haruPlaybackTiming);
	assert(playbackTiming.length >= 5, 'Expected audible buffers scheduled on the output graph');
	assert(await page.getByText(/^(Pode falar|Go ahead)\.\.\.$/).isVisible());
	await page.getByRole('button', { name: /^(End voice mode|Encerrar)$/i }).click();
	console.log(`PASS (${native ? 'WebView2 Fixed' : 'browser'}): ${openingFrames} audible packets before speech, ${replyFrames} after speech, and playback analyser detected output`);
	console.log(JSON.stringify({
		firstOutputAfterUtteranceMs: Math.round(firstReply - utteranceEnded),
		playbackQueueMaxMs: Math.round(Math.max(...playbackTiming)),
		audibleBuffersScheduled: playbackTiming.length
	}));
} finally {
	await browser?.close();
	host?.kill();
}
