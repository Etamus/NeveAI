import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree
from zipfile import ZipFile

from neveai.routers.model3d_generation import workflow
from neveai.utils.mesh_export_worker import write_3mf


class MeshContractTests(unittest.TestCase):
    def test_quality_refines_shape_and_preserves_texture_mapping(self):
        for compact in (False, True):
            standard = workflow("reference.png", 41, alpha=True, compact=compact)
            high = workflow("reference.png", 41, alpha=True, compact=compact, quality="high")
            diff = {k for k in standard if standard[k] != high[k]}
            self.assertEqual(diff, {"solid", "reduced", "uv", "bake", "refine"} | (set() if compact else {"crop", "refined"}))
            self.assertEqual(high["refine"]["inputs"]["target_resolution"], 1536 if compact else 1792)
            for graph, expected in [
                (standard, (384, 85000, 1024) if compact else (512, 160000, 2048)),
                (high, (640, 240000, 2048) if compact else (1024, 550000, 4096)),
            ]:
                self.assertEqual((graph["solid"]["inputs"]["resolution"],
                                  graph["reduced"]["inputs"]["target_face_count"],
                                  graph["bake"]["inputs"]["texture_size"]), expected)
                self.assertEqual(graph["uv"]["inputs"]["resolution"], expected[2])
            self.assertEqual(workflow("reference.png", 41, alpha=True, compact=compact, quality="unknown"), standard)

    def test_draft_reduces_diffusion_and_keeps_textured_output(self):
        for compact in (True, False):
            graph = workflow("reference.png", 41, quality="draft", compact=compact)
            self.assertEqual([graph[k]["inputs"]["steps"] for k in ("structure", "coarse", "refined", "tex_latent")], [8, 10, 6, 6])
            self.assertEqual(graph["refine"]["inputs"]["target_resolution"], 1024)
            self.assertEqual(graph["export"]["inputs"]["mesh"], ["material", 0])

    def test_workflow_profiles_do_not_require_the_other_model(self):
        for alpha in (True, False):
            for compact in (True, False):
                graph = workflow("reference.png", 41, alpha=alpha, compact=compact)
                self.assertEqual(graph["export"]["class_type"], "SaveGLB")
                self.assertEqual(graph["unet"]["inputs"]["unet_name"], "pixal3d_int8_convrot.safetensors")
                self.assertEqual(graph["bake"]["inputs"]["texture_size"], 1024 if compact else 2048)
                self.assertEqual("bg" in graph, not alpha)
                for task in graph.values():
                    for value in task["inputs"].values():
                        if isinstance(value, list):
                            self.assertIn(value[0], graph)

    def test_3mf_has_units_geometry_and_build_item(self):
        from types import SimpleNamespace
        tetrahedron = SimpleNamespace(vertices=[(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)],
                                      faces=[(0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2)])
        with TemporaryDirectory() as directory:
            output = Path(directory) / "model.3mf"
            write_3mf(tetrahedron, output)
            with ZipFile(output) as package:
                self.assertIsNone(package.testzip())
                self.assertIn("_rels/.rels", package.namelist())
                mesh = ElementTree.fromstring(package.read("3D/3dmodel.model"))
        self.assertEqual(mesh.attrib["unit"], "millimeter")
        self.assertEqual(len(mesh.findall(".//{*}triangle")), 4)
        self.assertEqual(mesh.find(".//{*}item").attrib["objectid"], "1")
