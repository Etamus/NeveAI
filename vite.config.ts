import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

import { viteStaticCopy } from 'vite-plugin-static-copy';
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig({
	plugins: [
		sveltekit(),
		viteStaticCopy({
			targets: [
				{
					src: 'node_modules/onnxruntime-web/dist/*.jsep.*',

					dest: 'wasm'
				}
			]
		}),
		visualizer({
			filename: 'build/stats.html',
			open: false,
			gzipSize: true,
			brotliSize: true
		})
	],
	define: {
		APP_VERSION: JSON.stringify(process.env.npm_package_version),
		APP_BUILD_HASH: JSON.stringify(process.env.APP_BUILD_HASH || 'dev-build')
	},
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
				'**/backend/**',
				'**/cypress/**',
				'**/test/**',
				'**/static/pyodide/**',
				'**/static/sql.js/**',
				'**/static/audio/**'
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
			'/ollama': {
				target: 'http://localhost:8080',
				changeOrigin: true
			},
			'/openai': {
				target: 'http://localhost:8080',
				changeOrigin: true
			},
			'/audio': {
				target: 'http://localhost:8080',
				changeOrigin: true
			},
			'/images': {
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
