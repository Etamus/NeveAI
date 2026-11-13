import { artifactAssetBase } from './assets';
import { ArtifactCompiler } from './compiler';
import type { ArtifactResult } from '../artifactResults';

const script = (value: string) => value.replace(/<\/script/gi, '<\\/script');

export async function exportArtifact(artifact: ArtifactResult): Promise<string> {
	const compiler = new ArtifactCompiler();
	try {
		const packet = await compiler.compile({ ...artifact, live: false });
		const pages: Record<string, typeof packet> = {};
		for (const path of packet.files)
			pages[path] =
				path === artifact.entry
					? packet
					: await compiler.compile({ ...artifact, live: false }, path);
		const assets = artifactAssetBase();
		const read = async (path: string) => {
			const response = await fetch(assets + '/' + path);
			if (!response.ok) throw new Error('Could not prepare artifact download');
			return response.text();
		};
		const runtime = await read('frame.js');
		const react = [packet, ...Object.values(pages)].some((page) => page.react)
			? await read('react.js')
			: '';
		const licenses = await read('THIRD-PARTY-LICENSES.txt');
		const tailwind = [packet, ...Object.values(pages)].some((page) => page.tailwind)
			? await read('tailwind.js')
			: '';
		return `<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"></head><body><script>window.__neveVendorSources=${script(JSON.stringify({ react, tailwind }))};\n${script(runtime)}<\/script><script>
const pages=${script(JSON.stringify(pages))};const channel=new MessageChannel();channel.port1.onmessage=event=>{if(event.data.type==='ready'){channel.port1.postMessage({type:'page',path:${script(JSON.stringify(artifact.entry ?? 'index.html'))}});channel.port1.postMessage({type:'update',packet:${script(JSON.stringify(packet))}})}else if(event.data.type==='navigate'&&pages[event.data.path]){channel.port1.postMessage({type:'page',path:event.data.path});channel.port1.postMessage({type:'update',packet:pages[event.data.path]})}};channel.port1.start();window.postMessage({type:'neve-preview-connect'},'*',[channel.port2]);
<\/script><!-- ${licenses.replace(/-->/g, '-- >')} --></body></html>`;
	} finally {
		compiler.destroy();
	}
}
