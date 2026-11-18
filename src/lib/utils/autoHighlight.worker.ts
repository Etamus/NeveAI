import hljs from 'highlight.js';

self.onmessage = ({ data }: MessageEvent<string>) => {
	try { self.postMessage(hljs.highlightAuto(data).value); }
	catch { self.postMessage(null); }
};
