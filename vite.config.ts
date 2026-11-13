import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

import { viteStaticCopy } from 'vite-plugin-static-copy';
import { build as buildArtifactRuntime } from 'esbuild-wasm';
import { readFile, writeFile } from 'node:fs/promises';
import { readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';

const artifactRuntimeHash = createHash('sha256');
for (const name of readdirSync('src/lib/utils/artifacts').filter(name => name.endsWith('.ts') && !name.endsWith('.test.ts')).sort()) {
	artifactRuntimeHash.update(name).update(readFileSync(`src/lib/utils/artifacts/${name}`));
}
const artifactRuntimeVersion = artifactRuntimeHash
	.update(readFileSync('package-lock.json'))
	.update(readFileSync('vite.config.ts'))
	.digest('hex').slice(0, 16);

export default defineConfig({
	plugins: [
		{
			name: 'neve-artifact-runtime',
			async buildStart() {
				await buildArtifactRuntime({
					entryPoints: { frame: 'src/lib/utils/artifacts/frame.ts', react: 'src/lib/utils/artifacts/react-runtime.ts', tailwind: 'node_modules/@tailwindcss/browser/dist/index.global.js' },
					bundle: true, platform: 'browser', format: 'iife', target: 'es2022', minify: true,
					outdir: `static/artifacts/${artifactRuntimeVersion}`, define: { 'process.env.NODE_ENV': '"development"' },
					legalComments: 'linked'
				});
				const notices: string[] = [];
				for (const name of ['morphdom', 'react', 'react-dom', 'react-refresh', 'scheduler', '@tailwindcss/browser']) {
					notices.push(`${name}\n${await readFile(`node_modules/${name}/LICENSE`, 'utf8')}`);
				}
				await writeFile(`static/artifacts/${artifactRuntimeVersion}/THIRD-PARTY-LICENSES.txt`, notices.join('\n\n'));
			}
		},
		sveltekit(),
		viteStaticCopy({
			targets: [
				{
					src: 'node_modules/onnxruntime-web/dist/*.jsep.*',

					dest: 'wasm'
				}
			]
		})
	],
	define: {
		__NEVE_ARTIFACT_VERSION__: JSON.stringify(artifactRuntimeVersion),
		APP_VERSION: JSON.stringify(process.env.npm_package_version),
		APP_BUILD_HASH: JSON.stringify(process.env.APP_BUILD_HASH || 'dev-build')
	},
	optimizeDeps: { include: ['esbuild-wasm'] },
	build: {
		sourcemap: false,
		// esbuild é muito mais rápido e leve que o Terser (minificador padrão do rollup)
		minify: 'esbuild',
		// Desativa o cálculo de tamanho comprimido (re-lê todos os arquivos gerados — desnecessário)
		reportCompressedSize: false,
		rollupOptions: {
			// Limita I/O paralelo para não saturar o disco (padrão é ilimitado)
			maxParallelFileOps: 15
		}
	},
	worker: {
		format: 'es'
	},
	esbuild: {
		pure: process.env.ENV === 'dev' ? [] : ['console.log', 'console.debug', 'console.warn', 'console.error']
	},
	server: {
		// Impede que o Vite/chokidar vasculhe pastas que não são código frontend
		// (backend/venv tem 2GB/56k arquivos — sem isso o build trava o sistema)
		watch: {
			ignored: [
				'**/.desktop/**',
				'**/backend/**',
				'**/test/**',
				'**/static/pyodide/**',
				'**/static/sql.js/**',
				'**/static/audio/**',
				'**/static/artifacts/**'
			]
		},
		proxy: {
			'/dbg': {
				target: 'http://localhost:8080',
				changeOrigin: true
			},
			'/api': {
				target: 'http://localhost:8080',
				changeOrigin: true
			},
			'/llamacpp': {
				target: 'http://localhost:8080',
				changeOrigin: true
			},
			'/ws': {
				target: 'http://localhost:8080',
				changeOrigin: true,
				ws: true
			},
			'/openai': {
				target: 'http://localhost:8080',
				changeOrigin: true
			},
			'/audio': {
				target: 'http://localhost:8080',
				changeOrigin: true
			},
			'/retrieval': {
				target: 'http://localhost:8080',
				changeOrigin: true
			},
			'/health': {
				target: 'http://localhost:8080',
				changeOrigin: true
			},
			'/static': {
				target: 'http://localhost:8080',
				changeOrigin: true
			}
		}
	}
});
