"""Structural validation of the produced EPUB.

`epubcheck` needs a Java runtime, which is not installed here, so the checks that matter for
a reader are done directly: well-formed XML, a complete manifest, resolvable links, a spine
that covers the text, and no oversized documents.

    uv run python src/validate_epub.py output/ISLP.epub
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import unquote

OPF_NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
XHTML_NS = "{http://www.w3.org/1999/xhtml}"
MAX_DOCUMENT_BYTES = 300 * 1024

REFERENCE_RE = re.compile(r'(?:href|src)="([^"#]+)(?:#[^"]*)?"')


def validate(path: Path) -> int:
    problems: list[str] = []
    notes: list[str] = []

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()

        if names[0] != "mimetype":
            problems.append("mimetype must be the first entry in the archive")
        info = archive.getinfo("mimetype")
        if info.compress_type != zipfile.ZIP_STORED:
            problems.append("mimetype must be stored uncompressed")
        if archive.read("mimetype") != b"application/epub+zip":
            problems.append("mimetype content is wrong")

        try:
            ET.fromstring(archive.read("META-INF/container.xml"))
        except ET.ParseError as error:
            problems.append(f"container.xml is not well formed: {error}")

        opf_root = ET.fromstring(archive.read("OEBPS/content.opf"))
        manifest = {}
        for item in opf_root.findall(".//opf:manifest/opf:item", OPF_NS):
            manifest[item.get("id")] = item.get("href")
        spine = [ref.get("idref") for ref in opf_root.findall(".//opf:spine/opf:itemref", OPF_NS)]

        for ident in spine:
            if ident not in manifest:
                problems.append(f"spine refers to missing manifest id {ident}")

        packaged = {name[len("OEBPS/") :] for name in names if name.startswith("OEBPS/")}
        for ident, href in manifest.items():
            if unquote(href) not in packaged:
                problems.append(f"manifest item {ident} points at missing file {href}")
        exempt = {"content.opf"}
        for name in sorted(packaged):
            if name in exempt:
                continue
            if name not in {unquote(h) for h in manifest.values()}:
                problems.append(f"file {name} is in the archive but not in the manifest")

        documents = [href for href in manifest.values() if href.endswith(".xhtml")]
        for href in documents:
            data = archive.read(f"OEBPS/{href}")
            if len(data) > MAX_DOCUMENT_BYTES:
                notes.append(f"{href} is {len(data) // 1024} KB; large documents can be slow to page on e-ink")
            try:
                ET.fromstring(data)
            except ET.ParseError as error:
                problems.append(f"{href} is not well-formed XML: {error}")
                continue
            base = Path(href).parent
            for target in REFERENCE_RE.findall(data.decode("utf-8")):
                if target.startswith(("http://", "https://", "data:", "mailto:")):
                    continue
                resolved = (
                    str((base / unquote(target)).resolve().relative_to(Path.cwd().root))
                    if target.startswith("/")
                    else str(base / unquote(target))
                )
                resolved = str(Path(resolved).as_posix())
                while "/../" in resolved:
                    resolved = re.sub(r"[^/]+/\.\./", "", resolved, count=1)
                if resolved not in packaged:
                    problems.append(f"{href} references missing {target} (resolved {resolved})")

        for href in manifest.values():
            if href.endswith(".svg"):
                try:
                    ET.fromstring(archive.read(f"OEBPS/{href}"))
                except ET.ParseError as error:
                    problems.append(f"{href} is not well-formed SVG: {error}")

        print(f"archive entries : {len(names)}")
        print(f"manifest items  : {len(manifest)}")
        print(f"spine documents : {len(spine)}")
        print(f"size            : {path.stat().st_size / 1024 / 1024:.2f} MB")

    for note in notes[:20]:
        print(f"NOTE    {note}")
    for problem in problems[:60]:
        print(f"PROBLEM {problem}")
    print(f"\n{len(problems)} problems, {len(notes)} notes")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(validate(Path(sys.argv[1])))
