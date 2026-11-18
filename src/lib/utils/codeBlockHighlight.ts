import hljs from 'highlight.js';

// One-entry cache per block; never retain code from other chats globally.
export function createCodeBlockHighlighter() {
	let previousCode: string | undefined;
	let previousLanguage: string | undefined;
	let html: string | null = null;
	return (code: string, language: string) => {
		if (code === previousCode && language === previousLanguage) return html;
		const known = hljs.getLanguage(language);
		html = known ? hljs.highlight(code, { language, ignoreIllegals: true }).value : null;
		previousCode = code;
		previousLanguage = language;
		return html;
	};
}

type Job = { code: string; deliver: ((html: string) => void) | null };
const queue = new Set<Job>();
let active: Job | undefined;
let worker: Worker | undefined;
let idle: ReturnType<typeof setTimeout>;
function drain() {
	if (active || !queue.size) return;
	clearTimeout(idle);
	const job = queue.values().next().value!;
	queue.delete(job);
	try {
		worker ??= new Worker(new URL('./autoHighlight.worker.ts', import.meta.url), { type: 'module' });
		active = job;
		worker.onmessage = ({ data }) => {
			if (typeof data === 'string') job.deliver?.(data);
			active = undefined;
			idle = setTimeout(() => { worker?.terminate(); worker = undefined; }, 30000);
			drain();
		};
		worker.onerror = () => {
			worker?.terminate(); worker = undefined; active = undefined; queue.clear();
		};
		worker.postMessage(job.code);
	} catch {
		active = undefined; queue.clear();
	}
}

export function detectCodeLanguage(code: string, deliver: (html: string) => void) {
	const job: Job = { code, deliver };
	// Streaming revisions coalesce; text is already visible. Bound expensive auto-detection.
	const timer = typeof Worker !== 'undefined' && code && code.length <= 100_000
		? setTimeout(() => { queue.add(job); drain(); }, 160) : undefined;
	return () => { clearTimeout(timer); queue.delete(job); job.deliver = null; };
}
