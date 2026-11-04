import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def namespace(memory=None, command=None):
    path = Path(__file__).parent / 'neveai/routers/llamacpp.py'
    nodes = [node for node in ast.parse(path.read_text(encoding='utf-8')).body
             if isinstance(node, ast.FunctionDef) and node.name in {'_get_system_ram_info', '_get_vram_info'}]
    psutil = SimpleNamespace(virtual_memory=Mock(return_value=memory or SimpleNamespace(total=32*1024**3, available=24*1024**3)))
    subprocess = SimpleNamespace(run=Mock(return_value=command or SimpleNamespace(stdout='', returncode=0)), CREATE_NO_WINDOW=0)
    result = {'psutil': psutil, 'subprocess': subprocess, 'sys': SimpleNamespace(platform='win32'), '_human_size': str}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), result)
    return result


class MemoryMeterTests(unittest.TestCase):
    def test_no_gpu_exposes_actual_ram_without_fabricating_vram(self):
        ns = namespace()
        ns['subprocess'].run.side_effect = FileNotFoundError('nvidia-smi')
        data = ns['_get_vram_info']()
        self.assertFalse(data['available'])
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['ram'], {'available': True, 'source': 'system', 'total': 32*1024**3, 'used': 8*1024**3, 'free': 24*1024**3})

    def test_empty_gpu_catalog_also_has_ram(self):
        data = namespace()['_get_vram_info']()
        self.assertFalse(data['available'])
        self.assertTrue(data['ram']['available'])

    def test_gpu_values_are_unchanged(self):
        data = namespace(command=SimpleNamespace(stdout='0, Example GPU, 16384, 4096, 12288\n', returncode=0))['_get_vram_info']()
        self.assertTrue(data['available'])
        self.assertEqual((data['total'], data['used'], data['free']), (16*1024**3, 4*1024**3, 12*1024**3))
        self.assertTrue(data['ram']['available'])

    def test_ram_failure_does_not_break_gpu_reporting(self):
        ns = namespace(command=SimpleNamespace(stdout='0, Example GPU, 16384, 4096, 12288\n', returncode=0))
        ns['psutil'].virtual_memory.side_effect = RuntimeError('unavailable')
        data = ns['_get_vram_info']()
        self.assertTrue(data['available'])
        self.assertFalse(data['ram']['available'])

    def test_published_frontend_mode_does_not_change_dev_or_explicit_overrides(self):
        source = Path(__file__).parent / 'neveai/env.py'
        assignments = [node for node in ast.parse(source.read_text(encoding='utf-8')).body
                       if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in {'_default_frontend', 'FRONTEND_BUILD_DIR'} for target in node.targets)]
        code = compile(ast.Module(body=assignments, type_ignores=[]), str(source), 'exec')
        base = Path('frontend-fixture').resolve()
        for environment, expected in [({}, base / 'build'), ({'NEVE_USE_PUBLISHED_FRONTEND': '1'}, base / 'backend/neveai/frontend'), ({'NEVE_USE_PUBLISHED_FRONTEND': '1', 'FRONTEND_BUILD_DIR': str(base / 'custom')}, base / 'custom')]:
            with self.subTest(environment=environment):
                ns = {'Path': Path, 'os': SimpleNamespace(getenv=lambda key, default=None: environment.get(key, default)), 'BASE_DIR': base, 'NEVEAI_DIR': base / 'backend/neveai'}
                exec(code, ns)
                self.assertEqual(ns['FRONTEND_BUILD_DIR'], expected)


if __name__ == '__main__':
    unittest.main()
