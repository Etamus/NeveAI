import CompilerWorker from '$lib/workers/artifact-compiler.worker?worker';
import type { ArtifactResult } from '../artifactResults';
import { isReactFile, normalizeArtifactPath, type ArtifactFile } from './project';
import type { PreviewPacket } from './types';
import { isExecutableArtifactScript } from './scriptTypes';

export class ArtifactCompiler {
	private worker: Worker | null = null;
	private serial = 0;
	private pending = new Map<
		number,
		{ resolve: (value: any) => void; reject: (error: Error) => void }
	>();
	private disposed = false;

	async compile(artifact: ArtifactResult, page?: string): Promise<PreviewPacket> {
		if (this.disposed) throw new Error('Preview closed');
		const files = artifact.files ?? [];
		const entry = files.find((file) => file.path === (page ?? artifact.entry));
		let source = entry?.language === 'html' ? entry.content : artifact.content;
		if (artifact.live && source.lastIndexOf('<') > source.lastIndexOf('>'))
			source = source.slice(0, source.lastIndexOf('<'));
		const document = new DOMParser().parseFromString(source, 'text/html');
		const react =
			files.some(isReactFile) ||
			[...document.querySelectorAll('script')].some(
				(script) =>
					/^(?:text\/)?(?:babel|jsx|tsx)$/.test(script.getAttribute('type') ?? '') ||
					(isExecutableArtifactScript(script.getAttribute('type')) &&
						isReactFile({ path: 'inline.js', language: 'js', content: script.textContent ?? '' }))
			);
		const scripts: string[] = [];
		const classic: string[] = [];
		const directory = entry?.path.includes('/')
			? entry.path.slice(0, entry.path.lastIndexOf('/') + 1)
			: '';
		const imports: Record<string, string> = Object.create(null);
		for (const script of document.querySelectorAll('script[type="importmap"]')) {
			const map = JSON.parse(script.textContent || '{}');
			for (const [key, value] of Object.entries(map.imports ?? {})) {
				if (typeof value === 'string') {
					imports[key] = value.startsWith('//')
						? 'https:' + value
						: /^\.?\.?\//.test(value)
							? '/' +
								normalizeArtifactPath(value.startsWith('/') ? value : directory + value) +
								(value.endsWith('/') ? '/' : '')
							: value;
				}
			}
		}
		const virtualFiles: ArtifactFile[] = [...files];
		for (const link of document.querySelectorAll('link[rel="stylesheet"][href]')) {
			const href = link.getAttribute('href')!;
			if (/^(?:https?:|\/\/|data:)/i.test(href)) continue;
			const file = files.find(
				(file) =>
					file.path === normalizeArtifactPath(href.startsWith('/') ? href : directory + href)
			);
			if (file) {
				const style = document.createElement('style');
				style.textContent = file.content;
				link.replaceWith(style);
			}
		}
		for (const [index, script] of [...document.querySelectorAll('script')].entries()) {
			const type = (script.getAttribute('type') ?? '').split(';')[0].trim().toLowerCase();
			if (!isExecutableArtifactScript(type)) continue;
			const src = script.getAttribute('src');
			if (
				react &&
				src &&
				/(?:\/(?:react|react-dom)(?:@|\/)|react(?:-dom)?\.(?:development|production)(?:\.min)?\.js|@babel\/standalone)/i.test(
					src
				)
			) {
				script.remove();
				continue;
			}
			if (src && /^(?:https?:|\/\/)/i.test(src)) continue;
			if (src) {
				const path = normalizeArtifactPath(
					src.startsWith('/') ? src.replace(/[?#].*$/, '') : directory + src.replace(/[?#].*$/, '')
				);
				const file = files.find((file) => file.path === path);
				if (type !== 'module' && file?.language === 'js') classic.push(file.content);
				else scripts.push(`await import(${JSON.stringify('./' + path)});`);
			} else if (script.textContent?.trim() && type !== 'module') {
				classic.push(script.textContent);
			} else if (script.textContent?.trim()) {
				const path = `${directory}__inline_${index}.${/tsx|jsx|babel/.test(type) || react ? 'tsx' : /typescript/.test(type) ? 'ts' : 'js'}`;
				virtualFiles.push({ path, language: path.split('.').at(-1)!, content: script.textContent });
				scripts.push(`await import(${JSON.stringify('./' + path)});`);
			}
			script.remove();
		}
		if (classic.length) {
			const handlers = new Set<string>();
			for (const node of document.querySelectorAll('*'))
				for (const attr of node.attributes) {
					if (attr.name.startsWith('on'))
						for (const match of attr.value.matchAll(/(?:^|[;\s])([A-Za-z_$][\w$]*)\s*\(/g))
							handlers.add(match[1]);
				}
			scripts.unshift(
				classic.join('\n') +
					'\n' +
					[...handlers]
						.map((name) => `if(typeof ${name}==='function')window.${name}=${name};`)
						.join('\n')
			);
		}
		if (entry?.language !== 'html') {
			if (!react && entry) scripts.push(`await import(${JSON.stringify('./' + entry.path)});`);
			const styles = files
				.filter((file) => file.language === 'css' && !file.path.endsWith('.module.css'))
				.map((file) => file.content)
				.join('\n');
			if (styles) {
				const style = document.createElement('style');
				style.textContent = styles;
				document.head.append(style);
			}
		} else {
			for (const file of files.filter((file) => ['css', 'js', 'ts'].includes(file.language))) {
				if (
					file.language === 'css' &&
					!document.querySelector(`style[data-artifact-file="${CSS.escape(file.path)}"]`) &&
					!entry.content.includes(file.path)
				) {
					const style = document.createElement('style');
					style.dataset.artifactFile = file.path;
					style.textContent = file.content;
					document.head.append(style);
				} else if (file.path === 'main.js' && !entry.content.includes(file.path))
					scripts.push('await import("./main.js");');
			}
		}
		let output = { js: '', css: '' };
		let preserveJS = false;
		if (scripts.length || react) {
			this.worker ??= this.startWorker();
			const id = ++this.serial;
			try {
				output = await new Promise((resolve, reject) => {
					this.pending.set(id, { resolve, reject });
					this.worker!.postMessage({
						id,
						files: virtualFiles,
						entry:
							entry?.language === 'html'
								? (files.find((file) => ['jsx', 'tsx'].includes(file.language))?.path ?? entry.path)
								: (entry?.path ?? 'App.tsx'),
						scripts,
						react,
						imports
					});
				});
			} catch (error) {
				// HTML/CSS can keep rendering while a streamed script is still syntactically incomplete.
				if (this.disposed || !artifact.live || react || entry?.language !== 'html') throw error;
				preserveJS = true;
			}
		}
		const classLists = [...document.querySelectorAll('[class]')].map(
			(node) => node.getAttribute('class') ?? ''
		);
		for (const file of files.filter((file) => ['jsx', 'tsx', 'js', 'ts'].includes(file.language))) {
			for (const match of file.content.matchAll(
				/\bclassName\s*=\s*(?:"([^"]*)"|'([^']*)'|\{\s*["'`]([^"'`]*)["'`]\s*\})/g
			))
				classLists.push(match[1] ?? match[2] ?? match[3] ?? '');
		}
		const tailwind =
			classLists.some((value) =>
				value
					.split(/\s+/)
					.some((token) =>
						/^(?:[\w-]+:)*(?:flex|grid|(?:p|m|gap|text|bg|w|h|rounded|items|justify|font|border|space)-[\w[\]-]+)$/.test(
							token
						)
					)
			) &&
			![...document.querySelectorAll('script[src]')].some((script) =>
				/tailwind/i.test(script.getAttribute('src')!)
			);
		const shade = window.document.documentElement.classList.contains('dark') ? '600' : '500';
		const accent =
			getComputedStyle(window.document.documentElement)
				.getPropertyValue(`--color-blue-${shade}`)
				.trim() || '#3b82f6';
		return {
			html: '<!DOCTYPE html>\n' + document.documentElement.outerHTML,
			...output,
			react,
			tailwind,
			accent,
			imports: Object.fromEntries(
				Object.entries(imports).filter(([, url]) => /^https?:\/\//i.test(url))
			),
			live: artifact.live === true,
			...(preserveJS ? { preserveJS: true } : {}),
			files: files.filter((file) => file.language === 'html').map((file) => file.path)
		};
	}

	private startWorker() {
		const worker = new CompilerWorker();
		worker.onmessage = ({ data }) => {
			const pending = this.pending.get(data.id);
			this.pending.delete(data.id);
			if (data.error) pending?.reject(new Error(data.error));
			else pending?.resolve(data);
		};
		worker.onerror = (event) => {
			for (const value of this.pending.values()) value.reject(new Error(event.message));
			this.pending.clear();
		};
		return worker;
	}

	destroy() {
		this.disposed = true;
		this.worker?.terminate();
		for (const value of this.pending.values()) value.reject(new Error('Preview closed'));
		this.pending.clear();
	}
}
