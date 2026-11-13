import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from neveai.routers import stable_diffusion as sd
from neveai.routers.image_fast_generation import SIGMAS


class ImageRetirementTests(unittest.IsolatedAsyncioTestCase):
    def test_retired_and_unknown_preferences_resolve_to_active_qwen(self):
        for quality in (None, '', 'neve_image', 'neve_image_2', 'unknown'):
            self.assertEqual(sd.normalize_image_quality(quality), 'qwen_image_2s')
        for quality in ('qwen_image_2s','qwen_image_2_1_official','minimax_h3_image'):
            self.assertEqual(sd.normalize_image_quality(quality), quality)
        self.assertEqual(sd.normalize_image_style('manga'),'none')
        self.assertEqual(sd.GenerateForm(prompt='test').quality,'qwen_image_2s')

    async def test_shared_amd_command_keeps_steps_sigmas_and_references(self):
        for count in (0,1,4,10):
            with self.subTest(references=count), tempfile.TemporaryDirectory() as temporary:
                folder=Path(temporary)
                refs=[]
                for index in range(count):
                    path=folder/f'ref{index}.png';path.write_bytes(b'ref')
                    refs.append(sd._InitImage(path,640,480))
                pipeline=sd._NativeQwenPipeline()
                pipeline._resources=sd._NativeImageResources(Path('sd-cli'),Path('model'),Path('encoder'),Path('vae'),Path('vision') if count else None)
                commands=[]
                async def spawn(*command,**kwargs):
                    commands.append(list(command));Path(command[command.index('-o')+1]).write_bytes(b'png')
                    return SimpleNamespace(returncode=0,stdout=None,stderr=None,wait=AsyncMock())
                dimensions=AsyncMock()
                with patch.object(sd,'IMAGE_OUTPUT_DIR',folder), patch.object(sd,'_prepare_reference_images',AsyncMock(return_value=refs)), patch.object(sd,'_supports_native_sage_attention',return_value=False), patch.object(sd,'_qwen_image_memory_args',return_value=['--auto-fit','on','--vae-tiling']), patch.object(sd,'_preferred_sd_cpp_windows_backend',return_value='cuda12'), patch.object(sd.asyncio,'create_subprocess_exec',side_effect=spawn):
                    result=await pipeline.generate('Preserve this request',resolution='16:9',init_image_references=[str(i) for i in range(count)],dimensions_callback=dimensions)
                self.assertTrue(result.startswith('data:image/png;base64,'))
                command=commands[0]
                for flag,value in (('--steps','8'),('--cfg-scale','1'),('--sigmas',SIGMAS),('--sampling-method','euler'),('-p','Preserve this request')):
                    self.assertEqual(command[command.index(flag)+1],value)
                self.assertEqual(command.count('-r'),count)
                self.assertEqual('--llm_vision' in command,bool(count))
                self.assertNotIn('--lora-model-dir',command)
                dimensions.assert_awaited_once_with(*sd.qwen_image_dimensions('16:9'))
                self.assertTrue(all(not ref.path.exists() for ref in refs))

    async def test_native_loader_rejects_other_models_without_download(self):
        pipeline=sd._NativeQwenPipeline()
        with self.assertRaises(ValueError):await pipeline.load('retired',quality='neve_image_2')


if __name__=='__main__':unittest.main()
