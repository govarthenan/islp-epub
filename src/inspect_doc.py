"""Dump the assembled document for a page range, to eyeball extraction quality."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from islp.document import assemble_document


def main() -> None:
    first = int(sys.argv[1]) - 1
    last = int(sys.argv[2])
    document = assemble_document(Path("ISLP_website.pdf"), first=first, last=last)
    for chapter in document.chapters:
        if not chapter.blocks:
            continue
        print(f"\n======== CHAPTER {chapter.ident}: {chapter.number} {chapter.title} ========")
        for block in chapter.blocks:
            if block.kind == "heading":
                print(f"\n[H{block.level}] {block.html}")
            elif block.kind == "para":
                notes = block.meta.get("margin_notes")
                marker = f"({block.list_marker}) " if block.list_marker else ""
                print(f"\n[P p{block.page + 1}] {marker}{block.html}")
                if notes:
                    print(f"     [margin] {notes}")
            elif block.kind == "display":
                item = document.math.items[block.math_id]
                print(f"\n[EQ {block.eq_number or '-'} p{block.page + 1}] raw={item.raw_text!r}")
                print(f"     guess={item.meta_guess!r}")
            elif block.kind == "code":
                print(f"\n[CODE {block.code_kind}]")
                for line in block.html.split("\n"):
                    print("    " + line)
            elif block.kind in ("figure", "table"):
                print(
                    f"\n[{block.kind.upper()} {block.number} bbox={tuple(round(v) for v in block.bbox)}] {block.html[:150]}"
                )
    print(f"\n--- math registry: {len(document.math.items)} items ---")


if __name__ == "__main__":
    main()
