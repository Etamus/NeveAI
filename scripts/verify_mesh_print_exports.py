"""Round-trip generated GLBs using the isolated print-export interpreter."""
import sys
import os
import subprocess
import tempfile
import time
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend/neveai/utils"))
from mesh_export_worker import bed_contact, convert, flatten_print_base, off_balance, printing_mesh, print_checks


def read_3mf(path):
    vertices, faces = [], []
    with ZipFile(path) as archive, archive.open("3D/3dmodel.model") as stream:
        for _, el in ET.iterparse(stream):
            if el.tag.endswith("}vertex"):
                vertices.append(tuple(float(el.attrib[k]) for k in ("x", "y", "z")))
            elif el.tag.endswith("}triangle"):
                faces.append(tuple(int(el.attrib[k]) for k in ("v1", "v2", "v3")))
            el.clear()
    return trimesh.Trimesh(vertices, faces, process=False)


def verify(glb, tmp, flat=False):
    for fmt in ("stl", "3mf"):
        start = time.perf_counter()
        output = tmp / ("print." + fmt)
        convert(glb, output, fmt, 100, flat_base=flat)
        mesh = read_3mf(output) if fmt == "3mf" else trimesh.load_mesh(output)
        assert mesh.is_volume and mesh.is_watertight and mesh.is_winding_consistent, (glb, fmt)
        assert np.allclose([mesh.bounds[0, 2], mesh.extents[2]], [0, 100], atol=0.001)
        if flat:
            assert bed_contact(mesh) > 0
        if os.environ.get("NEVE_TEST_SLICER"):
            toolpath = tmp / "verify.gcode"
            toolpath.unlink(missing_ok=True)
            subprocess.run([os.environ["NEVE_TEST_SLICER"], "--datadir", str(tmp / "slicer-profile"),
                            "--export-gcode", "--center", "100,100", "--layer-height", "0.2",
                            "--nozzle-diameter", "0.4", "--output", str(toolpath), str(output)],
                           capture_output=True, check=True, timeout=150)
            with toolpath.open(encoding="utf-8", errors="replace") as gcode:
                layers = sum(";LAYER_CHANGE" in line for line in gcode)
            assert layers > 100 and toolpath.stat().st_size > 100_000
            print("Sliced", fmt, "flat" if flat else "original", layers, "layers")
        print(glb.name, fmt, len(mesh.faces), round(time.perf_counter() - start, 2), flush=True)


def verify_recovery():
    import point_cloud_utils as pcu
    from unittest.mock import patch

    box = trimesh.creation.box()
    box.update_faces(np.arange(6))
    make_solid = pcu.make_mesh_watertight
    requests = []

    def limited(v, f, density):
        requests.append(density)
        if len(requests) == 1:
            raise MemoryError("test budget")
        return make_solid(v, f, density)

    with patch.object(pcu, "make_mesh_watertight", limited):
        assert printing_mesh(trimesh.Scene(box), 100).is_volume and requests == [150000, 70000]

    degenerate = trimesh.Trimesh(vertices=[[0, 0, 0]] * 3, faces=[[0, 1, 2]], process=False)
    try:
        printing_mesh(trimesh.Scene(degenerate), 100)
    except ValueError:
        pass
    else:
        raise AssertionError("Degenerate geometry was accepted for printing")


def verify_digital(source, tmp):
    import bpy
    import bmesh

    def metrics():
        objects = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        boundaries = 0
        for ob in objects:
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            boundaries += sum(e.is_boundary for e in bm.edges)
            bm.free()
        return (sum(len(o.data.polygons) for o in objects), boundaries,
                sum(len(o.data.uv_layers) for o in objects), sum(bool(i.packed_file) for i in bpy.data.images))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    before = metrics()

    for fmt in ("obj", "fbx", "blend"):
        directory = tmp / fmt
        directory.mkdir()
        output = directory / ("model.zip" if fmt == "obj" else "model." + fmt)
        convert(source, output, fmt, 100)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if fmt == "obj":
            with ZipFile(output) as archive:
                assert archive.testzip() is None and "modelo.obj" in archive.namelist()
                archive.extractall(directory / "verify")
            bpy.ops.wm.obj_import(filepath=str(directory / "verify/modelo.obj"))
        elif fmt == "fbx":
            bpy.ops.import_scene.fbx(filepath=str(output))
        else:
            bpy.ops.wm.open_mainfile(filepath=str(output))
            after = metrics()
            assert after[0] == before[0] and after[1] <= before[1] and after[2:] == before[2:], (before, after)
            print("Editable mesh (faces, boundaries, UV maps, packed images):", before, after)
        faces = sum(len(ob.data.polygons) for ob in bpy.context.scene.objects if ob.type == "MESH")
        assert faces > 0
        print(source.name, fmt, faces, flush=True)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        if sys.argv[1:2] == ["--digital"]:
            verify_digital(Path(sys.argv[2]).resolve(), tmp)
            sys.exit(0)
        thick = trimesh.creation.box(extents=[3, 5, 4])
        assert not off_balance(thick)
        leaning = thick.copy()
        leaning.vertices[leaning.vertices[:, 2] > 0, 0] += 12
        assert off_balance(leaning)
        assert not off_balance(flatten_print_base(leaning))
        thin = trimesh.creation.box(extents=[12, 10, 0.4])
        assert print_checks(thick) == {"components": 1, "thin": False}
        assert print_checks(thin) == {"components": 1, "thin": True}
        thin.apply_translation([30, 0, 0])
        assert print_checks(thick + thin) == {"components": 2, "thin": True}
        verify_recovery()
        sphere = trimesh.creation.icosphere()
        sphere.apply_translation([0, 0, 1])
        base = flatten_print_base(sphere)
        assert bed_contact(sphere) == 0 and bed_contact(base) > 0 and base.is_volume
        assert np.isclose(base.extents[2], sphere.extents[2]) and abs(base.bounds[0, 2]) < 1e-8
        tiny = trimesh.creation.box(extents=[.01, .01, .01])
        tiny.apply_translation([3, 0, .005])
        try:
            flatten_print_base(sphere + tiny)
        except ValueError:
            pass
        else:
            raise AssertionError("Flat base silently removed a separate part")
        for name in sys.argv[1:]:
            verify(Path(name), tmp)
            verify(Path(name), tmp, flat=True)
        box = trimesh.creation.box()
        for name in ("closed", "open"):
            if name == "open":
                box.update_faces(np.arange(len(box.faces))[:-4])
            source = tmp / (name + ".glb")
            box.export(source)
            verify(source, tmp)
