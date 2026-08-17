"""Write an EPUB 3 package that reads well on a Kobo Libra 2.

Choices made for that device:

  * No font is embedded and no body font size is set, so the reader's own font and size
    controls keep working.
  * Mathematics is SVG drawn in `currentColor` and sized in `em`, so it grows with the text
    and stays correct in both light and dark mode.
  * Figures are 300 ppi grayscale, matching the panel's 300 ppi and 16 grey levels.
  * A toc.ncx is written next to the EPUB 3 navigation document, because Kobo still reads it.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

XHTML_HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" \
lang="en" xml:lang="en">
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<link rel="stylesheet" type="text/css" href="../css/style.css"/>
</head>
<body>
{body}
</body>
</html>
"""

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

STYLESHEET = """/* ISLP - reflowable EPUB tuned for a 7 inch e-ink screen.
   No font-family and no absolute font-size on body: the reader stays in control. */

html { -webkit-hyphens: auto; hyphens: auto; }

body {
  margin: 0 0.35em;
  line-height: 1.4;
  text-align: justify;
  widows: 2;
  orphans: 2;
}

h1, h2, h3, h4, h5 {
  text-align: left;
  line-height: 1.25;
  page-break-after: avoid;
  break-after: avoid;
  -webkit-hyphens: none;
  hyphens: none;
}

h1 { font-size: 1.6em; margin: 1.2em 0 0.8em; }
h2 { font-size: 1.3em; margin: 1.4em 0 0.5em; }
h3 { font-size: 1.12em; margin: 1.2em 0 0.4em; font-style: italic; }
h4 { font-size: 1em;    margin: 1.1em 0 0.3em; }

h1 .chapnum {
  display: block;
  font-size: 0.6em;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  margin-bottom: 0.5em;
  font-weight: normal;
}

/* Indentation follows the printed page rather than a sibling rule, so a paragraph is
   indented here exactly when it was indented there. */
p { margin: 0; text-indent: 1.2em; }
p.noindent { text-indent: 0; }

p.li         { text-indent: -1.1em; margin-left: 1.6em; margin-top: 0.35em; }
p.li-cont    { text-indent: 0;      margin-left: 1.6em; }
p.li-cont-in { text-indent: 1.2em;  margin-left: 1.6em; }
p.li2         { text-indent: -1.1em; margin-left: 2.9em; margin-top: 0.35em; }
p.li2-cont    { text-indent: 0;      margin-left: 2.9em; }
p.li2-cont-in { text-indent: 1.2em;  margin-left: 2.9em; }
p.li3         { text-indent: -1.3em; margin-left: 4.4em; margin-top: 0.3em; }
p.li3-cont    { text-indent: 0;      margin-left: 4.4em; }
p.li3-cont-in { text-indent: 1.2em;  margin-left: 4.4em; }
p.li .marker, p.li2 .marker, p.li3 .marker { font-weight: bold; }

/* Display equations. The number is pushed to the right of its own line. */
div.eq {
  margin: 0.9em 0;
  text-align: center;
  page-break-inside: avoid;
  break-inside: avoid;
}
div.eq img, div.eq svg { max-width: 100%; height: auto; vertical-align: middle; }
div.eq .eqno { font-size: 0.85em; margin-left: 0.7em; vertical-align: middle; }

img.mi { vertical-align: baseline; max-width: 100%; }

/* Figures and tables */
div.figure {
  margin: 1.1em 0;
  text-align: center;
  page-break-inside: avoid;
  break-inside: avoid;
}
div.figure img { max-width: 100%; height: auto; }
p.caption {
  font-size: 0.82em;
  font-style: italic;
  text-align: left;
  text-indent: 0;
  margin: 0.45em 0 0;
  line-height: 1.35;
}
p.caption .label { font-style: normal; font-weight: bold; }

/* Jupyter cells from the labs */
div.codeblock {
  margin: 0.8em 0;
  page-break-inside: avoid;
  break-inside: avoid;
}
pre {
  font-family: monospace;
  font-size: 0.68em;
  line-height: 1.32;
  white-space: pre-wrap;
  word-wrap: break-word;
  overflow-wrap: break-word;
  margin: 0;
  padding: 0.4em 0.5em;
  text-align: left;
  -webkit-hyphens: none;
  hyphens: none;
}
pre.input  { border-left: 3px solid #999; background: #f4f4f4; }
pre.output { border-left: 3px solid #ddd; }

code { font-family: monospace; font-size: 0.88em; -webkit-hyphens: none; hyphens: none; }

/* Margin notes become small asides, since a 7 inch page has no margin to spare */
p.marginnote {
  font-size: 0.78em;
  font-style: italic;
  text-align: right;
  text-indent: 0;
  margin: 0.15em 0 0.5em;
  color: #555;
  line-height: 1.3;
  -webkit-hyphens: none;
  hyphens: none;
}

aside.footnote {
  display: block;
  font-size: 0.84em;
  line-height: 1.4;
  margin: 1em 0 0.8em;
  padding-top: 0.5em;
  border-top: 1px solid #bbb;
  text-indent: 0;
  text-align: left;
}

/* Tables. On a narrow screen a table has to give up its rules and lean on spacing. */
table {
  border-collapse: collapse;
  margin: 0 auto;
  font-size: 0.82em;
  line-height: 1.35;
  -webkit-hyphens: none;
  hyphens: none;
}
th, td {
  padding: 0.28em 0.5em;
  text-align: left;
  vertical-align: top;
}
thead th {
  border-bottom: 1px solid #999;
  font-weight: bold;
}
tbody tr:first-child td, tbody tr:first-child th { padding-top: 0.4em; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr.grouphead th, tr.grouphead td {
  font-style: italic;
  padding-top: 0.6em;
  border-bottom: 1px solid #ddd;
}
p.tablepart {
  text-align: center;
  text-indent: 0;
  font-size: 0.86em;
  margin: 0.8em 0 0.3em;
}

/* Index */
p.index-entry { text-indent: -1em; margin-left: 1em;   text-align: left; font-size: 0.92em; }
p.index-sub   { text-indent: -1em; margin-left: 2.2em; text-align: left; font-size: 0.92em; }

div.cover { text-align: center; margin: 0; padding: 0; }
div.cover img { max-width: 100%; max-height: 100%; }

p.dedication { text-align: center; text-indent: 0; margin: 0.4em 0; font-style: italic; }
"""


@dataclass
class Resource:
    path: str  # inside OEBPS
    media_type: str
    data: bytes
    ident: str
    properties: str = ""


@dataclass
class NavPoint:
    title: str
    href: str
    level: int
    children: list["NavPoint"] = field(default_factory=list)


class EpubBuilder:
    def __init__(self, identifier: str, title: str, language: str = "en") -> None:
        self.identifier = identifier
        self.title = title
        self.language = language
        self.authors: list[str] = []
        self.description = ""
        self.publisher = ""
        self.source = ""
        self.rights = ""
        self.modified = "2026-08-17T00:00:00Z"
        self.resources: list[Resource] = []
        self.spine: list[str] = []
        self.nav: list[NavPoint] = []
        self.cover_id: str | None = None
        self.bodymatter_href: str = ""

    def add_document(self, name: str, title: str, body: str, ident: str,
                     spine: bool = True) -> str:
        path = f"text/{name}"
        data = XHTML_HEAD.format(title=_escape(title), body=body).encode("utf-8")
        self.resources.append(Resource(path, "application/xhtml+xml", data, ident))
        if spine:
            self.spine.append(ident)
        return path

    def add_resource(self, path: str, media_type: str, data: bytes, ident: str,
                     properties: str = "") -> None:
        self.resources.append(Resource(path, media_type, data, ident, properties))

    def set_cover(self, ident: str) -> None:
        self.cover_id = ident

    # -- package documents -------------------------------------------------------------

    def _opf(self) -> str:
        items = []
        for resource in self.resources:
            properties = f' properties="{resource.properties}"' if resource.properties else ""
            items.append(
                f'    <item id="{resource.ident}" href="{resource.path}" '
                f'media-type="{resource.media_type}"{properties}/>'
            )
        spine = "\n".join(f'    <itemref idref="{ident}"/>' for ident in self.spine)
        creators = "\n".join(
            f'    <dc:creator id="creator{index}">{_escape(name)}</dc:creator>'
            for index, name in enumerate(self.authors)
        )
        cover_meta = (f'    <meta name="cover" content="{self.cover_id}"/>\n'
                      if self.cover_id else "")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" \
xml:lang="{self.language}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{_escape(self.identifier)}</dc:identifier>
    <dc:title>{_escape(self.title)}</dc:title>
    <dc:language>{self.language}</dc:language>
{creators}
    <dc:publisher>{_escape(self.publisher)}</dc:publisher>
    <dc:source>{_escape(self.source)}</dc:source>
    <dc:rights>{_escape(self.rights)}</dc:rights>
    <dc:description>{_escape(self.description)}</dc:description>
    <meta property="dcterms:modified">{self.modified}</meta>
{cover_meta}  </metadata>
  <manifest>
{chr(10).join(items)}
  </manifest>
  <spine toc="ncx">
{spine}
  </spine>
</package>
"""

    def _nav_document(self) -> str:
        def render(points: list[NavPoint]) -> str:
            parts = ["<ol>"]
            for point in points:
                inner = render(point.children) if point.children else ""
                parts.append(f'<li><a href="{point.href}">{_escape(point.title)}</a>{inner}</li>')
            parts.append("</ol>")
            return "".join(parts)

        start = self.bodymatter_href or (self.nav[0].href if self.nav else "text/cover.xhtml")
        cover_href = self.nav[0].href if self.nav else start
        body = f"""<nav epub:type="toc" id="toc">
<h1>Contents</h1>
{render(self.nav)}
</nav>
<nav epub:type="landmarks" hidden="hidden">
<ol>
<li><a epub:type="cover" href="{cover_href}">Cover</a></li>
<li><a epub:type="bodymatter" href="{start}">Begin reading</a></li>
</ol>
</nav>"""
        return XHTML_HEAD.format(title="Contents", body=body).replace(
            'href="../css/style.css"', 'href="css/style.css"'
        )

    def _ncx(self) -> str:
        counter = [0]

        def render(points: list[NavPoint]) -> str:
            parts = []
            for point in points:
                counter[0] += 1
                order = counter[0]
                inner = render(point.children) if point.children else ""
                parts.append(
                    f'<navPoint id="np{order}" playOrder="{order}">'
                    f"<navLabel><text>{_escape(point.title)}</text></navLabel>"
                    f'<content src="{point.href}"/>{inner}</navPoint>'
                )
            return "".join(parts)

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{_escape(self.identifier)}"/>
    <meta name="dtb:depth" content="3"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{_escape(self.title)}</text></docTitle>
  <navMap>{render(self.nav)}</navMap>
</ncx>
"""

    def write(self, target: Path) -> None:
        self.add_resource("css/style.css", "text/css", STYLESHEET.encode("utf-8"), "css")
        self.resources.append(
            Resource("nav.xhtml", "application/xhtml+xml", self._nav_document().encode("utf-8"),
                     "nav", "nav")
        )
        self.resources.append(
            Resource("toc.ncx", "application/x-dtbncx+xml", self._ncx().encode("utf-8"), "ncx")
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr(
                zipfile.ZipInfo("mimetype"), "application/epub+zip",
                compress_type=zipfile.ZIP_STORED,
            )
            archive.writestr("META-INF/container.xml", CONTAINER, zipfile.ZIP_DEFLATED)
            archive.writestr("OEBPS/content.opf", self._opf(), zipfile.ZIP_DEFLATED)
            for resource in self.resources:
                archive.writestr(f"OEBPS/{resource.path}", resource.data, zipfile.ZIP_DEFLATED)


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))
