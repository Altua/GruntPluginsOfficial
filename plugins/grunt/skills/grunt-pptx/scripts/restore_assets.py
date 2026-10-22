#!/usr/bin/env python3
"""Recover exact Grunt SVG inputs and a credential-free final manifest from a PPTX.

No network requests. The saved deck, including its embedded capability-bearing SVGs,
is the recovery source after temporary chart downloads have been deleted. Treat the
restored SVG directory as temporary and private, just like the original downloads.
"""
import argparse
import hashlib
import json
import posixpath
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from download_chart import _write_private_file

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SVG = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")
COMMIT = re.compile(r"[0-9a-fA-F]{64}\Z")


def related_parts(archive, part):
    parent, name = posixpath.split(part)
    rel_path = posixpath.join(parent, "_rels", name + ".rels")
    if rel_path not in archive.namelist():
        return {}
    result = {}
    for rel in ET.fromstring(archive.read(rel_path)):
        if rel.get("TargetMode") == "External":
            continue
        target = rel.get("Target", "")
        path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join(parent, target))
        if path.startswith("../"):
            raise ValueError("Invalid package relationship")
        result[rel.get("Id")] = path
    return result


def tags_for(archive, element, relationships):
    tags = {}
    for ref in element.findall(f".//{{{P}}}tags"):
        part = relationships.get(ref.get(f"{{{R}}}id"))
        if part:
            for tag in ET.fromstring(archive.read(part)):
                tags[tag.get("name", "").upper()] = tag.get("val", "")
    return tags


def read_assets(pptx):
    """Return a safe manifest and filename->original bytes, without logging links."""
    charts, svg_files = [], {}
    with ZipFile(pptx) as archive:
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        relationships = related_parts(archive, "ppt/presentation.xml")
        project_tags = tags_for(archive, presentation, relationships)
        for slide_index, slide_ref in enumerate(presentation.findall(f"{{{P}}}sldIdLst/{{{P}}}sldId")):
            part = relationships[slide_ref.get(f"{{{R}}}id")]
            slide = ET.fromstring(archive.read(part))
            rels = related_parts(archive, part)
            grouped_shapes = {id(child) for group in slide.iter(f"{{{P}}}grpSp") for child in group.iter()}
            for shape in (el for el in slide.iter() if el.tag in (f"{{{P}}}pic", f"{{{P}}}sp")):
                tags = tags_for(archive, shape, rels)
                asset_id = tags.get("GRUNT-WEB-ASSETID")
                if not asset_id:
                    continue
                if id(shape) in grouped_shapes:
                    raise ValueError(f"Grouped Grunt shape on slide {slide_index + 1}: ungroup it before recovering slide placements.")
                commit = tags.get("GRUNT-WEB-ASSETCOMMIT", "")
                if not GUID.fullmatch(asset_id) or not COMMIT.fullmatch(commit):
                    raise ValueError(f"Invalid Grunt identity on slide {slide_index + 1}")
                svg_ref = shape.find(f".//{{{SVG}}}svgBlip")
                if svg_ref is None:
                    raise ValueError(f"Missing embedded SVG on slide {slide_index + 1}")
                svg_bytes = archive.read(rels[svg_ref.get(f"{{{R}}}embed")])
                if ET.fromstring(svg_bytes).tag != "{http://www.w3.org/2000/svg}svg":
                    raise ValueError("Chart media is not SVG")
                digest = hashlib.sha256(svg_bytes).hexdigest()
                filename = f"{asset_id.lower()}-{commit.lower()}-{digest[:16]}.svg"
                svg_files[filename] = svg_bytes
                identity = shape.find(f".//{{{P}}}cNvPr")
                xfrm = shape.find(f"{{{P}}}spPr/{{{A}}}xfrm")
                if identity is None or xfrm is None:
                    raise ValueError("Grunt picture has no identity or placement")
                off, ext = xfrm.find(f"{{{A}}}off"), xfrm.find(f"{{{A}}}ext")
                charts.append({
                    "slide": slide_index, "shapeId": identity.get("id"),
                    "assetId": asset_id.lower(), "commit": commit.lower(),
                    "filename": filename, "sha256": digest,
                    "revisionPolicy": tags.get("GRUNT-WEB-REVISION-POLICY", "latest"),
                    "hasEditLink": bool(tags.get("GRUNT-WEB-LINK")),
                    "boundsEmu": {"left": int(off.get("x")), "top": int(off.get("y")),
                                  "width": int(ext.get("cx")), "height": int(ext.get("cy"))},
                })
    return {
        "schemaVersion": 1, "sourceSha256": hashlib.sha256(Path(pptx).read_bytes()).hexdigest(),
        "project": {"id": project_tags.get("GRUNT-ASSET-PROJECT-ID"), "name": project_tags.get("GRUNT-ASSET-PROJECT-NAME")},
        "finalAssetIds": sorted({c["assetId"] for c in charts}), "charts": charts,
    }, svg_files


def restore_assets(pptx, output_dir=None, manifest_path=None):
    manifest, files = read_assets(pptx)
    if output_dir:
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            _write_private_file(str(directory / name), data)
    if manifest_path:
        Path(manifest_path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--output-dir", help="Optional temporary directory for exact embedded SVG inputs")
    parser.add_argument("--manifest", required=True, help="Final assets, revisions, hashes and placements; contains no capability URLs")
    args = parser.parse_args()
    result = restore_assets(args.pptx, args.output_dir, args.manifest)
    print(json.dumps({"charts": len(result["charts"]), "assets": len(result["finalAssetIds"]), "projectStamped": bool(result["project"]["id"])}))


if __name__ == "__main__":
    main()
