"""CPU-side conversion, invoked in an isolated environment only on export."""
import json
import sys
import zipfile
from pathlib import Path
from io import BufferedWriter


def repair_touching_seams(mesh, height_mm):
    """Separate touching sheets locally, before falling back to surface reconstruction."""
    import numpy as np
    import trimesh

    try:
        import manifold3d as md
    except ImportError:
        return None
    if not mesh.is_winding_consistent or mesh.extents[2] <= 0:
        return None
    solid = md.Manifold(md.Mesh64(np.ascontiguousarray(mesh.vertices, dtype=np.float64),
                                  np.ascontiguousarray(mesh.faces, dtype=np.uint64)))
    if solid.is_empty() or solid.num_tri() != len(mesh.faces):
        return None
    output = solid.to_mesh64()
    vertices = np.array(output.vert_properties[:, :3])
    faces = np.asarray(output.tri_verts)
    _, inverse, counts = np.unique(vertices, axis=0, return_inverse=True, return_counts=True)
    split = counts[inverse] > 1
    if not split.any() or split.sum() > max(32, len(vertices) // 100):
        return None
    # STL has no vertex indices. Without a tiny separation, a slicer welds
    # the coincident sheets again. Move only split vertices toward their own fan.
    centers = vertices[faces].mean(axis=1)
    offsets = np.zeros_like(vertices)
    for indices in faces.T:
        np.add.at(offsets, indices, centers - vertices[indices])
    vectors = offsets[split]
    lengths = np.linalg.norm(vectors, axis=1)
    if np.any(lengths == 0):
        return None
    step = min(.01 / height_mm * mesh.extents[2], 1e-5 * mesh.extents.max())
    vertices[split] += vectors / lengths[:, None] * step
    # Validate after STL precision loss and positional welding, not just in memory.
    checked = trimesh.Trimesh(vertices.astype(np.float32), faces, process=True, validate=True)
    if checked.is_volume and len(checked.faces) == len(mesh.faces) and np.isclose(checked.volume, mesh.volume, rtol=1e-5, atol=0):
        return checked
    return None


def printing_mesh(scene, height_mm):
    import numpy as np
    import trimesh

    original = scene.to_mesh()
    if not len(original.faces) or not np.isfinite(original.vertices).all():
        raise ValueError("O arquivo nao contem uma superficie valida.")
    # Reconstruct adjacency across texture seams, without changing the GLB.
    mesh = trimesh.Trimesh(vertices=original.vertices, faces=original.faces, process=True, validate=True)
    if not len(mesh.faces) or not np.isfinite(mesh.extents).all():
        raise ValueError("O arquivo nao contem uma superficie valida.")
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    if not mesh.is_watertight:
        mesh.fill_holes()
    if not mesh.is_volume:
        mesh.fix_normals(multibody=True)
    if not mesh.is_volume:
        try:
            repaired = repair_touching_seams(mesh, height_mm)
        except (MemoryError, RuntimeError, ValueError):
            repaired = None
        if repaired is not None:
            mesh = repaired
    if not mesh.is_volume and np.all(mesh.extents > 0):
        import point_cloud_utils as pcu

        # Reconstruct only the print copy. Normalization makes the repair
        # independent of GLB units; cap the resolution for desktop CPUs.
        span = mesh.extents.max()
        center = mesh.bounds.mean(axis=0)
        vertices = np.ascontiguousarray((mesh.vertices - center) / span, dtype=np.float64)
        faces = np.ascontiguousarray(mesh.faces, dtype=np.int32)
        for density in (150_000, 70_000):
            try:
                v, f = pcu.make_mesh_watertight(vertices, faces, density)
            except (MemoryError, RuntimeError):
                if density == 70_000:
                    raise
                continue
            if not len(f) or not np.isfinite(v).all():
                continue
            repaired = trimesh.Trimesh(v * span + center, f, process=False)
            if repaired.is_volume:
                mesh = repaired
                if len(mesh.faces) > 250000 and mesh.extents[2] > 0:
                    # Reconstructed surfaces can contain hundreds of thousands of
                    # redundant facets. Bound deviation in final print units.
                    try:
                        import manifold3d as md
                        solid = md.Manifold(md.Mesh64(np.ascontiguousarray(mesh.vertices),
                                                      np.ascontiguousarray(mesh.faces, dtype=np.uint64)))
                        data = solid.simplify(mesh.extents[2] * .015 / height_mm).to_mesh64()
                        if len(data.tri_verts) and len(data.tri_verts) < len(mesh.faces):
                            candidate = trimesh.Trimesh(data.vert_properties[:, :3].astype(np.float32),
                                                        data.tri_verts, process=True, validate=True)
                            if (candidate.is_volume and candidate.euler_number == mesh.euler_number
                                    and np.isclose(candidate.volume, mesh.volume, rtol=.001, atol=0)
                                    and np.max(np.abs(candidate.bounds - mesh.bounds)) * height_mm / mesh.extents[2] <= .02):
                                mesh = candidate
                    except (ImportError, MemoryError, RuntimeError, ValueError):
                        pass
                break
    if not mesh.is_volume or not np.isfinite(mesh.vertices).all() or mesh.extents[2] <= 0:
        raise ValueError("A malha nao forma um volume fechado. Nao foi exportada para impressao.")
    mesh.apply_scale(height_mm / mesh.extents[2])
    mesh.apply_translation([-mesh.centroid[0], -mesh.centroid[1], -mesh.bounds[0, 2]])
    return mesh


def print_checks(mesh, wall_mm=0.8):
    """Advisory normal-ray sampling on the final scaled/closed print copy."""
    import numpy as np
    import trimesh
    import point_cloud_utils as pcu

    labels = trimesh.graph.connected_component_labels(mesh.face_adjacency, node_count=len(mesh.faces))
    components = int(labels.max()) + 1
    # Sample by area so tessellation density does not bias an entire side.
    areas = np.cumsum(mesh.area_faces)
    n = min(1024, len(mesh.faces) * 3)
    selected = np.unique(np.searchsorted(areas, (np.arange(n) + 0.5) * areas[-1] / n))
    normals = mesh.face_normals[selected]
    eps = max(1e-5, float(mesh.extents.max()) * 1e-6)
    origins = mesh.triangles_center[selected] - normals * eps
    rays = pcu.RayMeshIntersector(np.ascontiguousarray(mesh.vertices, dtype=np.float64),
                                  np.ascontiguousarray(mesh.faces, dtype=np.int32))
    hits, _, distances = rays.intersect_rays(np.ascontiguousarray(origins), np.ascontiguousarray(-normals),
                                             ray_near=eps, ray_far=wall_mm)
    hits, distances = np.asarray(hits).reshape(-1), np.asarray(distances).reshape(-1)
    valid = (hits >= 0) & (hits != selected) & (distances + eps < wall_mm)
    facing = np.einsum("ij,ij->i", normals[valid], mesh.face_normals[hits[valid]]) < -0.5
    return {"components": components, "thin": bool(facing.any())}


def bed_contact(mesh):
    """Area of triangles actually on the bed, in square millimetres."""
    import numpy as np
    plane = mesh.bounds[0, 2]
    on_bed = np.abs(mesh.vertices[:, 2] - plane) <= max(mesh.extents[2] * 1e-8, 1e-7)
    return float(mesh.area_faces[on_bed[mesh.faces].all(axis=1)].sum())


def off_balance(mesh):
    """Static check for one solid, assuming uniform density; not an adhesion test."""
    import numpy as np
    from scipy.spatial import ConvexHull, QhullError
    on_bed = np.abs(mesh.vertices[:, 2] - mesh.bounds[0, 2]) <= max(mesh.extents[2] * 1e-8, 1e-7)
    contact = mesh.vertices[on_bed, :2]
    if len(contact) < 3:
        return False
    try:
        planes = ConvexHull(contact).equations
    except QhullError:
        return False
    return bool(np.any(planes[:, :2] @ mesh.center_mass[:2] + planes[:, 2] > 1e-6))


def flatten_print_base(mesh):
    import manifold3d as md
    import numpy as np
    import trimesh

    height = mesh.extents[2]
    cut = mesh.bounds[0, 2] + min(1.0, height * .015)
    solid = md.Manifold(md.Mesh64(np.ascontiguousarray(mesh.vertices, dtype=np.float64),
                                  np.ascontiguousarray(mesh.faces, dtype=np.uint64)))
    if solid.is_empty() or any(part.bounding_box()[5] <= cut for part in solid.decompose()):
        raise ValueError("Flat base would remove a part or cannot be constructed.")
    cut_solid = solid.trim_by_plane((0, 0, 1), cut)
    result = cut_solid.to_mesh64()
    clipped = trimesh.Trimesh(result.vert_properties[:, :3], result.tri_verts, process=False)
    if not len(clipped.faces) or not clipped.is_volume or bed_contact(clipped) <= 0:
        raise ValueError("Flat base could not be closed.")
    # Coplanar contact alone does not keep a leaning figurine upright. For a
    # single solid, extend the footprint under both the foot and its mass center.
    if off_balance(clipped) and len(cut_solid.decompose()) == 1:
        feet = clipped.vertices[np.isclose(clipped.vertices[:, 2], cut, atol=1e-7, rtol=0), :2]
        points = np.vstack([feet, clipped.center_mass[:2]])
        center = (points.min(axis=0) + points.max(axis=0)) / 2
        radius = np.max(np.linalg.norm(points - center, axis=1)) + min(4, height * .05)
        thickness = min(3, height * .035)
        base = md.Manifold.cylinder(thickness * 1.2, radius, circular_segments=96)
        joined = cut_solid + base.translate((*center, cut - thickness))
        # This branch starts with one exterior shell. The union may enclose
        # tiny pockets at the joint; inward shells are not loose model parts.
        shells = [part for part in joined.decompose() if part.volume() > 0]
        if len(shells) != 1:
            raise ValueError("Flat base could not join the support.")
        data = shells[0].to_mesh64()
        plate = trimesh.Trimesh(data.vert_properties[:, :3], data.tri_verts, process=False)
        if not plate.is_volume or off_balance(plate):
            raise ValueError("Flat base could not stabilize this part.")
        clipped = plate
    clipped.apply_translation([0, 0, -clipped.bounds[0, 2]])
    clipped.apply_scale(height / clipped.extents[2])
    return clipped


def write_3mf(mesh, output):
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml",
                         '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                         '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
                         '</Types>')
        package.writestr("_rels/.rels",
                         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         '<Relationship Id="rel0" Target="/3D/3dmodel.model" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
                         '</Relationships>')
        with package.open("3D/3dmodel.model", "w") as part, BufferedWriter(part, 262144) as stream:
            stream.write(b'<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
                         b'<resources><object id="1" type="model"><mesh><vertices>')
            for v in mesh.vertices:
                stream.write(('<vertex x="%.12g" y="%.12g" z="%.12g"/>' % tuple(v)).encode())
            stream.write(b'</vertices><triangles>')
            for f in mesh.faces:
                stream.write(('<triangle v1="%d" v2="%d" v3="%d"/>' % tuple(f)).encode())
            stream.write(b'</triangles></mesh></object></resources><build><item objectid="1"/></build></model>')


def convert(source, output, format, height_mm, flat_base=False):
    if format in {"obj", "fbx", "blend"}:
        import bpy

        bpy.ops.wm.read_factory_settings(use_empty=True)
        # GLB duplicates vertices at UV seams; Blender can keep the UVs per loop.
        bpy.ops.import_scene.gltf(filepath=str(source), merge_vertices=True)
        if format == "blend":
            from mathutils import Vector
            objects = [ob for ob in bpy.context.scene.objects if ob.type == "MESH"]
            if not objects:
                raise ValueError("Scene has no editable mesh.")
            corners = [ob.matrix_world @ Vector(p) for ob in objects for p in ob.bound_box]
            center = Vector([(min(p[i] for p in corners) + max(p[i] for p in corners)) / 2 for i in range(3)])
            for area in bpy.context.screen.areas:
                if area.type == "VIEW_3D":
                    view = area.spaces.active
                    view.region_3d.view_location = center
                    view.region_3d.view_distance = max((p - center).length for p in corners) * 3
                    view.shading.color_type = "TEXTURE"
            bpy.context.view_layer.objects.active = max(objects, key=lambda ob: len(ob.data.polygons))
            bpy.context.view_layer.objects.active.select_set(True)
            bpy.ops.file.pack_all()
            bpy.ops.wm.save_as_mainfile(filepath=str(output), compress=True)
        elif format == "fbx":
            bpy.ops.export_scene.fbx(filepath=str(output), path_mode="COPY", embed_textures=True,
                                     bake_anim=False, object_types={"MESH"})
        else:
            # Blender's OBJ exporter cannot reference images packed inside a GLB.
            for index, image in enumerate(bpy.data.images):
                if image.packed_file:
                    extension = ".jpg" if image.file_format == "JPEG" else ".png"
                    texture = output.with_name(f"texture-{index}{extension}")
                    texture.write_bytes(image.packed_file.data)
                    image.unpack(method="REMOVE")
                    image.filepath = str(texture)
            obj = output.with_name("modelo.obj")
            bpy.ops.wm.obj_export(filepath=str(obj), path_mode="COPY", export_materials=True)
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
                for entry in output.parent.iterdir():
                    if entry.is_file() and entry != output:
                        package.write(entry, entry.name)
        return
    import trimesh

    scene = trimesh.load_scene(source, file_type="glb")
    mesh = printing_mesh(scene, height_mm)
    if flat_base:
        mesh = flatten_print_base(mesh)
    if format == "3mf":
        write_3mf(mesh, output)
    else:
        mesh.export(output, file_type="stl")
    try:
        diagnostics = print_checks(mesh)
    except (MemoryError, RuntimeError, ImportError, ValueError, OSError):
        diagnostics = {"unavailable": True}
    diagnostics["bed_contact_mm2"] = bed_contact(mesh)
    if diagnostics.get("components") == 1 and diagnostics["bed_contact_mm2"] > 0:
        diagnostics["off_balance"] = off_balance(mesh)
    print("NEVE_PRINT:" + json.dumps(diagnostics), flush=True)


if __name__ == "__main__":
    _, source, output, format, height, *options = sys.argv
    try:
        convert(Path(source), Path(output), format, float(height), "--flat-base" in options)
    except ValueError as exc:
        print(f"INVALID_MESH:{exc}", flush=True)
        sys.exit(2)
