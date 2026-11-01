import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';
import {describe,expect,it,vi} from 'vitest';

const source=readFileSync('src/routes/(app)/library/+page.svelte','utf8');
const script=source.match(/<script[^>]*>([\s\S]*?)<\/script>/)![1];
const tree=ts.createSourceFile('library.ts',script,ts.ScriptTarget.Latest,true);
let loadSource='';
function visit(node:ts.Node){
	if(ts.isVariableDeclaration(node)&&node.name.getText(tree)==='load')loadSource=node.initializer!.getText(tree);
	ts.forEachChild(node,visit);
}
visit(tree);
function setup(files:any[],catalog:any[]){
	const scope:any={files,requestId:0,kind:'all',AbortController,localStorage:{token:'test'},
		loadController:undefined,loading:false,error:'',hasMore:false,settledEmpty:false,refreshQueued:false,refreshedAt:0,
		getGeneratedFiles:vi.fn(async(_token, _kind, _query, skip, _signal, limit)=>catalog.slice(skip,skip+limit))};
	scope.load=runInNewContext(ts.transpile(`(${loadSource})`,{target:ts.ScriptTarget.ES2022}),scope);
	return scope;
}
const rows=(count:number)=>Array.from({length:count},(_,id)=>({id,filename:`File ${id}`,meta:{content_type:'image/png'},updated_at:1}));
describe('library refresh batching',()=>{
	it('keeps unchanged object identity and refreshes 500 files in one request',async()=>{
		const files=rows(500),scope=setup(files,rows(550));
		await scope.load(false,true);
		expect(scope.files).toBe(files);expect(scope.hasMore).toBe(true);
		expect(scope.getGeneratedFiles).toHaveBeenCalledTimes(1);
		expect(scope.getGeneratedFiles.mock.calls[0].at(-1)).toBe(500);
	});
	it('bounds batches, keeps all pages and detects deletion and same-second edits',async()=>{
		const catalog=rows(1520);catalog[800].filename='Edited';catalog.splice(1200,1);
		const scope=setup(rows(1500),catalog);
		await scope.load(false,true);
		expect(scope.getGeneratedFiles.mock.calls.map((args:any[])=>[args[3],args[5]])).toEqual([[0,1000],[1000,500]]);
		expect(scope.files).toEqual(catalog.slice(0,1500));
		expect(scope.files[800].filename).toBe('Edited');
		expect(scope.files.some((file:any)=>file.id===1200)).toBe(false);
	});
	it('preserves 50-item initial loads, terminal pages and empty results',async()=>{
		const scope=setup([],rows(75));await scope.load();
		expect(scope.files).toHaveLength(50);expect(scope.hasMore).toBe(true);
		await scope.load(true);expect(scope.files).toHaveLength(75);expect(scope.hasMore).toBe(false);
		const empty=setup(rows(25),[]);await empty.load(false,true);
		expect(empty.files).toHaveLength(0);expect(empty.settledEmpty).toBe(true);
	});
	it('never commits a stale response after navigation',async()=>{
		const scope=setup(rows(5),[]);let finish:any;
		scope.getGeneratedFiles=vi.fn(()=>new Promise(resolve=>finish=resolve));
		const loading=scope.load();scope.requestId++;finish(rows(25));await loading;
		expect(scope.files).toHaveLength(5);
	});
});
