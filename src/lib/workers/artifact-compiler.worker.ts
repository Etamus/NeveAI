import { build, initialize } from 'esbuild-wasm';
import wasmURL from 'esbuild-wasm/esbuild.wasm?url';
import { normalizeArtifactPath } from '../utils/artifacts/path';
import { mappedArtifactImport } from '../utils/artifacts/importMap';
import type { CompileRequest } from '../utils/artifacts/types';

const ready = initialize({ wasmURL, worker: false });
let queue = Promise.resolve();
self.onmessage = ({ data }: MessageEvent<CompileRequest>) => {
	queue = queue.then(async () => {
		try {
			await ready;
			const files = new Map(data.files.map((file) => [file.path, file]));
			const entry =
				data.scripts.join('\n') +
				(data.react && !data.scripts.length
					? `\nimport * as app from ${JSON.stringify('./' + data.entry)}; export { app };`
					: '');
			const result = await build({
				stdin: {
					contents: entry,
					loader: 'tsx',
					sourcefile: '__preview_entry.tsx',
					resolveDir: '/'
				},
				bundle: true,
				write: false,
				format: 'esm',
				platform: 'browser',
				target: 'es2022',
				jsx: 'automatic',
				jsxImportSource: 'react',
				outfile: '/preview.js',
				logLevel: 'silent',
				define: { 'process.env.NODE_ENV': '"production"' },
				plugins: [
					{
						name: 'artifact-files',
						setup(api) {
							api.onResolve({ filter: /.*/ }, (args) => {
								if (/^(?:react(?:\/.*)?|react-dom(?:\/.*)?)$/.test(args.path))
									return { path: args.path, external: true };
								const request = mappedArtifactImport(args.path, data.imports);
								if (/^https?:\/\//.test(request)) return { path: request, external: true };
								if (/^(?:node:|file:|data:|javascript:)/i.test(request))
									return { errors: [{ text: 'Unsupported import: ' + request }] };
								const relative =
									request.startsWith('.') || request.startsWith('/') || request.startsWith('@/');
								if (!relative)
									return {
										path: `https://esm.sh/${request}?external=react,react-dom`,
										external: true
									};
								const directory = args.importer.includes('/')
									? args.importer.slice(0, args.importer.lastIndexOf('/') + 1)
									: '';
								const path = normalizeArtifactPath(
									request.startsWith('.') ? directory + request : request
								);
								const resolved = [
									path,
									...[
										'.tsx',
										'.ts',
										'.jsx',
										'.js',
										'.css',
										'.json',
										'/index.tsx',
										'/index.ts',
										'/index.jsx',
										'/index.js'
									].map((extension) => path + extension)
								].find((path) => files.has(path));
								return resolved
									? { path: resolved, namespace: 'artifact' }
									: { errors: [{ text: 'Missing file: ' + path }] };
							});
							api.onLoad({ filter: /.*/, namespace: 'artifact' }, (args) => {
								const file = files.get(args.path)!;
								const implicitApp =
									data.react && args.path === data.entry
										? '\nexport const __neveDefault = typeof App !== "undefined" ? App : typeof Component !== "undefined" ? Component : undefined;'
										: '';
								return {
									contents: file.content + implicitApp,
									loader: file.path.endsWith('.module.css')
										? 'local-css'
										: file.language === 'js' && data.react
											? 'jsx'
											: (file.language as any)
								};
							});
						}
					}
				]
			});
			self.postMessage({
				id: data.id,
				js: result.outputFiles.find((file) => file.path.endsWith('.js'))?.text ?? '',
				css: result.outputFiles.find((file) => file.path.endsWith('.css'))?.text ?? ''
			});
		} catch (error) {
			self.postMessage({ id: data.id, error: error.errors?.[0]?.text ?? String(error) });
		}
	});
};
