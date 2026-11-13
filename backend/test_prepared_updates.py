import asyncio
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from neveai.utils.prepared_updates import PreparedUpdates, validate_archive, validate_package, RELEASE_FILES


def archive(name=None, content='new'):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as result:
        for entry in ([name] if name else ['release/'+name for name in RELEASE_FILES]):
            result.writestr(entry, content)
    return stream.getvalue()


class PreparedUpdateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager = PreparedUpdates(self.root)
        (self.root / 'version.txt').write_text('v1.0.0')

    async def test_neve_prepare_does_not_change_installation(self):
        payload = archive()
        async def handler(request):
            if request.url.path.endswith('/latest'):
                return httpx.Response(200, json={'tag_name':'v1.1.0','zipball_url':'https://codeload.github.com/test.zip'})
            return httpx.Response(200, content=payload)
        factory = httpx.AsyncClient
        with patch('neveai.utils.prepared_updates.httpx.AsyncClient', side_effect=lambda **kw: factory(transport=httpx.MockTransport(handler), **kw)):
            state = await self.manager.start(['neve'], 'owner')
            await self.manager.task
        self.assertEqual(self.manager.state('owner')['status'], 'ready')
        self.assertEqual(self.manager.state('other')['status'], 'idle')
        self.assertEqual((self.root / 'version.txt').read_text(), 'v1.0.0')
        manifest = json.loads((self.manager.directory / state['id'] / 'manifest.json').read_text())
        self.assertEqual(manifest['packages'][0]['sha256'], hashlib.sha256(payload).hexdigest())
        with self.assertRaises(ValueError):
            await self.manager.start(['llama'], 'owner')

    async def test_llama_only_preserves_backend_and_neve(self):
        binary=self.root/'llamacpp-server';binary.mkdir()
        (binary/'version.txt').write_text('b100\ncuda-13\nllama-b100-bin-win-cuda-13.4-x64.zip')
        async def handler(request):
            if request.url.host=='api.github.com':
                return httpx.Response(200,json=[{'tag_name':'b101','assets':[
                    {'name':'llama-b101-bin-win-cpu-x64.zip','browser_download_url':'https://github.com/cpu.zip'},
                    {'name':'llama-b101-bin-win-cuda-13.4-x64.zip','browser_download_url':'https://github.com/cuda.zip'},
                    {'name':'cudart-llama-bin-win-cuda-13.4-x64.zip','browser_download_url':'https://github.com/runtime.zip'}]}])
            self.assertNotIn('cpu.zip',str(request.url))
            return httpx.Response(200,content=archive('cudart.dll' if str(request.url).endswith('runtime.zip') else 'llama-server.exe'))
        factory=httpx.AsyncClient
        with patch('neveai.utils.prepared_updates.httpx.AsyncClient',side_effect=lambda **kw:factory(transport=httpx.MockTransport(handler),**kw)):
            await self.manager.start(['llama'],'owner');await self.manager.task
        state=self.manager.state('owner')
        self.assertEqual(state['status'],'ready');self.assertEqual(state['versions'],{'llama':'b101'})
        self.assertEqual((self.root/'version.txt').read_text(),'v1.0.0')

    async def test_failed_download_cleans_only_its_packages(self):
        with patch.object(self.manager,'_neve_release',AsyncMock(return_value={'tag_name':'v1.2.0','zipball_url':'https://github.com/pkg.zip'})), patch.object(self.manager,'_download',AsyncMock(side_effect=ValueError('invalid'))):
            state=await self.manager.start(['neve'],'owner');await self.manager.task
        self.assertEqual(self.manager.state('owner')['status'],'failed')
        self.assertEqual(list((self.manager.directory/state['id']).glob('*.zip')),[])
        self.assertTrue((self.root/'version.txt').exists())

    async def test_redirect_to_untrusted_host_is_rejected(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(302,headers={'location':'https://evil.test/file'}))) as client:
            with self.assertRaises(ValueError):await self.manager._get(client,'https://github.com/test')

    async def test_transient_download_retries(self):
        destination=self.root/'package.zip'
        with patch.object(self.manager,'_download_once',AsyncMock(side_effect=[httpx.ReadError('offline'),('sha',1)])), patch('asyncio.sleep',AsyncMock()):
            self.assertEqual(await self.manager._download(None,'https://github.com/test',destination,lambda _:None),('sha',1))

    async def test_invalid_targets_and_restart_are_rejected(self):
        for targets in ([],['other']):
            with self.assertRaises(ValueError):await self.manager.start(targets,'owner')
        with self.assertRaises(ValueError):self.manager.restart('owner')

    async def test_both_targets_are_prepared_without_applying_either(self):
        release={'tag_name':'b101','assets':[{'name':'llama-b101-bin-win-cpu-x64.zip','browser_download_url':'https://github.com/llama.zip'}]}
        async def download(client,url,path,progress):
            payload=archive('llama-server.exe') if url.endswith('llama.zip') else archive()
            path.write_bytes(payload);progress(1)
            return hashlib.sha256(payload).hexdigest(),len(payload)
        with patch.object(self.manager,'_neve_release',AsyncMock(return_value={'tag_name':'v1.1.0','zipball_url':'https://github.com/neve.zip'})), patch.object(self.manager,'_llama_releases',AsyncMock(return_value=[release])), patch.object(self.manager,'_download',side_effect=download):
            await self.manager.start(['neve','llama'],'owner');await self.manager.task
        self.assertEqual(self.manager.state('owner')['versions'],{'neve':'v1.1.0','llama':'b101'})
        self.assertEqual(self.manager.state('owner')['status'],'ready')
        with self.assertRaises(ValueError):await self.manager.start(['neve'],'other-admin')
        self.assertEqual((self.root/'version.txt').read_text(),'v1.0.0')

    async def test_no_downgrade_and_no_download_for_current_release(self):
        with patch.object(self.manager,'_neve_release',AsyncMock(return_value={'tag_name':'v1.0.0','zipball_url':'https://github.com/pkg.zip'})), patch.object(self.manager,'_download',AsyncMock()) as download:
            await self.manager.start(['neve'],'owner');await self.manager.task
        download.assert_not_awaited();self.assertEqual(self.manager.state('owner')['status'],'failed')

    async def test_official_digest_mismatch_is_rejected(self):
        release={'tag_name':'b101','assets':[{'name':'llama-b101-bin-win-cpu-x64.zip','browser_download_url':'https://github.com/llama.zip','digest':'sha256:'+'0'*64}]}
        async def download(client,url,path,progress):
            payload=archive();path.write_bytes(payload);return hashlib.sha256(payload).hexdigest(),len(payload)
        with patch.object(self.manager,'_llama_releases',AsyncMock(return_value=[release])), patch.object(self.manager,'_download',side_effect=download):
            state=await self.manager.start(['llama'],'owner');await self.manager.task
        self.assertEqual(self.manager.state('owner')['status'],'failed')
        self.assertFalse((self.manager.directory/state['id']/'llama.zip').exists())

    async def test_official_html_fallback_when_api_is_rate_limited(self):
        def handler(request):
            if request.url.host=='api.github.com':return httpx.Response(403)
            if request.url.path.endswith('/latest'):return httpx.Response(302,headers={'location':'/Etamus/NeveAI/releases/tag/v1.2.0'})
            return httpx.Response(200,text='release')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            release=await self.manager._neve_release(client)
        self.assertEqual(release['tag_name'],'v1.2.0')
        self.assertTrue(release['zipball_url'].startswith('https://codeload.github.com/Etamus/NeveAI/'))

    async def test_llama_html_fallback_uses_published_asset_names(self):
        def handler(request):
            if request.url.host=='api.github.com':return httpx.Response(403)
            if 'expanded_assets' in request.url.path:
                return httpx.Response(200,text='<a href="/ggml-org/llama.cpp/releases/download/b200/llama-b200-bin-win-cpu-x64.zip">CPU</a>')
            return httpx.Response(200,text='<a href="/ggml-org/llama.cpp/releases/tag/b200">release</a>')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            releases=await self.manager._llama_releases(client)
        self.assertEqual(releases[0]['assets'][0]['name'],'llama-b200-bin-win-cpu-x64.zip')
        self.assertTrue(releases[0]['assets'][0]['browser_download_url'].endswith('/b200/llama-b200-bin-win-cpu-x64.zip'))

    def test_restart_is_owned_and_launches_only_this_root(self):
        job={'id':'a'*32,'owner':'owner','root':str(self.root),'status':'ready'};self.manager._write(job)
        with patch('subprocess.Popen') as launch:
            self.assertEqual(self.manager.restart('owner'),{'status':'restarting'})
        self.assertEqual(launch.call_args.kwargs['cwd'],self.root.resolve())
        self.assertIn(str(self.root.resolve()/'launchers/iniciar.ps1'),launch.call_args.args[0])
        self.assertIn('-UpdateJob',launch.call_args.args[0])

    def test_interrupted_job_and_failed_restart_remain_recoverable(self):
        job={'id':'a'*32,'owner':'owner','root':str(self.root),'status':'downloading'}
        self.manager._write(job)
        self.assertEqual(self.manager.state('owner')['status'],'failed')
        job['status']='ready';self.manager._write(job)
        with patch('subprocess.Popen',side_effect=OSError('blocked')):
            with self.assertRaises(OSError):self.manager.restart('owner')
        self.assertEqual(self.manager.state('owner')['status'],'ready')

    def test_archives_reject_traversal_absolute_drive_and_symlinks(self):
        path=self.root/'package.zip'
        for name in ('../escape','/absolute','C:/drive','a/../../escape','a\\..\\..\\escape'):
            path.write_bytes(archive(name))
            with self.assertRaises(ValueError):validate_archive(path)
        path.write_bytes(archive());validate_archive(path)
        with zipfile.ZipFile(path,'w') as result:
            item=zipfile.ZipInfo('link');item.external_attr=0o120777<<16;result.writestr(item,'target')
        with self.assertRaises(ValueError):validate_archive(path)

    def test_incomplete_packages_fail_before_restart(self):
        path=self.root/'package.zip'
        path.write_bytes(archive('release/README.md'))
        for kind in ('neve.zip','llama.zip','runtime.zip'):
            with self.assertRaises(ValueError):validate_package(path,kind)
        path.write_bytes(archive());validate_package(path,'neve.zip')
        path.write_bytes(archive('bin/llama-server.exe'));validate_package(path,'llama.zip')
        path.write_bytes(archive('cudart.dll'));validate_package(path,'runtime.zip')

if __name__=='__main__':unittest.main()
