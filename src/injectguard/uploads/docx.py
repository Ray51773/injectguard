from __future__ import annotations

import re
import zipfile
from collections.abc import Iterable
from xml.etree.ElementTree import Element

from injectguard.types import ContainerType
from injectguard.uploads.builder import SegmentBuilder
from injectguard.uploads.common import validate_zip
from injectguard.uploads.errors import UploadScanError
from injectguard.uploads.limits import UploadLimits
from injectguard.uploads.models import ExtractionResult

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def extract_docx(data: bytes, filename: str, limits: UploadLimits) -> ExtractionResult:
    archive = validate_zip(data, limits)
    try:
        names = set(archive.namelist())
        if "word/document.xml" not in names or "[Content_Types].xml" not in names:
            raise UploadScanError(
                "unsupported_type", "The uploaded file is not a DOCX document.", 415
            )
        if {"EncryptedPackage", "EncryptionInfo"} & names:
            raise UploadScanError(
                "encrypted_document",
                "Encrypted or password-protected DOCX files are not supported.",
            )
        if any(name.lower().endswith(("vbaproject.bin", ".exe", ".dll")) for name in names):
            raise UploadScanError(
                "unsupported_type", "Executable DOCX content is not supported.", 415
            )

        builder = SegmentBuilder(filename, limits)
        warnings: list[str] = []
        style_visibility = _extract_style_visibility(archive, names)
        part_names = _ordered_parts(names)
        for part_name in part_names:
            section = _section_for_part(part_name)
            root = _parse_xml(archive.read(part_name), part_name)
            _extract_part(root, part_name, section, builder, style_visibility)

        _extract_hyperlinks(archive, names, builder)
        _extract_properties(archive, names, builder)
        if not builder.segments:
            warnings.append("No extractable text was found in the DOCX document.")
        return ExtractionResult(
            file_type="docx",
            detected_mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            segments=builder.segments,
            warnings=warnings,
            truncated=builder.truncated,
        )
    finally:
        archive.close()


def _ordered_parts(names: set[str]) -> list[str]:
    candidates = [
        name
        for name in names
        if name == "word/document.xml"
        or re.fullmatch(r"word/(?:header|footer)\d+\.xml", name)
        or name
        in {
            "word/comments.xml",
            "word/footnotes.xml",
            "word/endnotes.xml",
            "word/glossary/document.xml",
        }
    ]
    return sorted(candidates, key=lambda name: (name != "word/document.xml", name))


def _section_for_part(part_name: str) -> str:
    if part_name == "word/document.xml":
        return "body"
    return part_name.removeprefix("word/").removesuffix(".xml")


def _parse_xml(data: bytes, part_name: str) -> Element:
    try:
        from defusedxml.ElementTree import fromstring
    except ImportError as exc:  # pragma: no cover - server extra provides it.
        raise UploadScanError(
            "extraction_failed", "Secure DOCX extraction support is not installed."
        ) from exc
    try:
        return fromstring(data)
    except Exception as exc:
        raise UploadScanError("extraction_failed", f"DOCX part {part_name} is malformed.") from exc


def _extract_part(
    root: Element,
    part_name: str,
    section: str,
    builder: SegmentBuilder,
    style_visibility: dict[str, str],
) -> None:
    parent_map = {child: parent for parent in root.iter() for child in parent}
    table_cells: dict[Element, tuple[int, int, int]] = {}
    for table_number, table in enumerate(root.iter(f"{W}tbl"), start=1):
        for row_number, row in enumerate(table.findall(f"{W}tr"), start=1):
            for column_number, table_cell in enumerate(row.findall(f"{W}tc"), start=1):
                table_cells[table_cell] = (table_number, row_number, column_number)

    for paragraph_number, paragraph in enumerate(root.iter(f"{W}p"), start=1):
        ancestor_cell = _ancestor(paragraph, parent_map, f"{W}tc")
        if ancestor_cell is not None and ancestor_cell in table_cells:
            table_number, row_number, column_number = table_cells[ancestor_cell]
            location = (
                f"{section}, table {table_number}, row {row_number}, "
                f"column {column_number}, paragraph {paragraph_number}"
            )
        else:
            location = f"{section}, paragraph {paragraph_number}"
        _extract_paragraph_runs(paragraph, location, section, builder, style_visibility)

    raw_number = 0
    for tag in (f"{W}instrText", f"{W}delText"):
        for node in root.iter(tag):
            if node.text and node.text.strip():
                raw_number += 1
                builder.add(
                    node.text,
                    ContainerType.UNKNOWN,
                    f"{part_name}, raw XML text {raw_number}",
                    "hidden",
                    "raw_xml",
                )


def _ancestor(node: Element, parent_map: dict[Element, Element], target_tag: str) -> Element | None:
    current = parent_map.get(node)
    while current is not None:
        if current.tag == target_tag:
            return current
        current = parent_map.get(current)
    return None


def _extract_paragraph_runs(
    paragraph: Element,
    location: str,
    section: str,
    builder: SegmentBuilder,
    style_visibility: dict[str, str],
) -> None:
    groups: list[tuple[str, list[str]]] = []
    for run in paragraph.iter(f"{W}r"):
        text = "".join(node.text or "" for node in run.iter(f"{W}t"))
        if not text:
            continue
        visibility = _run_visibility(run, paragraph, style_visibility)
        if groups and groups[-1][0] == visibility:
            groups[-1][1].append(text)
        else:
            groups.append((visibility, [text]))
    for group_number, (visibility, parts) in enumerate(groups, start=1):
        suffix = f", run group {group_number}" if len(groups) > 1 else ""
        builder.add(
            "".join(parts),
            ContainerType.UNKNOWN,
            f"{location}{suffix}",
            visibility,
            section,
        )


def _run_visibility(run: Element, paragraph: Element, style_visibility: dict[str, str]) -> str:
    properties = run.find(f"{W}rPr")
    if properties is not None:
        direct = _properties_visibility(properties)
        if direct == "hidden":
            return direct
        run_style = properties.find(f"{W}rStyle")
        if run_style is not None:
            style_id = run_style.get(f"{W}val", "")
            if style_visibility.get(style_id) == "hidden":
                return "hidden"
    paragraph_properties = paragraph.find(f"{W}pPr")
    if paragraph_properties is not None:
        paragraph_style = paragraph_properties.find(f"{W}pStyle")
        if paragraph_style is not None:
            style_id = paragraph_style.get(f"{W}val", "")
            if style_visibility.get(style_id) == "hidden":
                return "hidden"
    return "visible"


def _properties_visibility(properties: Element) -> str:
    if properties.find(f"{W}vanish") is not None or properties.find(f"{W}webHidden") is not None:
        return "hidden"
    color = properties.find(f"{W}color")
    if color is not None and _near_white(color.get(f"{W}val", "")):
        return "hidden"
    highlight = properties.find(f"{W}highlight")
    if highlight is not None and highlight.get(f"{W}val", "").lower() == "white":
        return "hidden"
    size = properties.find(f"{W}sz")
    if size is not None:
        try:
            if int(size.get(f"{W}val", "999")) <= 12:
                return "hidden"
        except ValueError:
            pass
    return "visible"


def _extract_style_visibility(archive: zipfile.ZipFile, names: set[str]) -> dict[str, str]:
    part_name = "word/styles.xml"
    if part_name not in names:
        return {}
    root = _parse_xml(archive.read(part_name), part_name)
    direct: dict[str, str] = {}
    parent_styles: dict[str, str] = {}
    for style in root.iter(f"{W}style"):
        style_id = style.get(f"{W}styleId", "")
        if not style_id:
            continue
        properties = style.find(f"{W}rPr")
        direct[style_id] = (
            _properties_visibility(properties) if properties is not None else "visible"
        )
        based_on = style.find(f"{W}basedOn")
        if based_on is not None:
            parent_styles[style_id] = based_on.get(f"{W}val", "")
    for style_id in direct:
        current = style_id
        visited: set[str] = set()
        while current and current not in visited:
            visited.add(current)
            if direct.get(current) == "hidden":
                direct[style_id] = "hidden"
                break
            current = parent_styles.get(current, "")
    return direct


def _near_white(value: str) -> bool:
    normalized = value.removeprefix("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", normalized):
        return False
    red, green, blue = (int(normalized[index : index + 2], 16) for index in (0, 2, 4))
    return min(red, green, blue) >= 240


def _extract_hyperlinks(
    archive: zipfile.ZipFile,
    names: set[str],
    builder: SegmentBuilder,
) -> None:
    relationships = "word/_rels/document.xml.rels"
    if relationships not in names:
        return
    root = _parse_xml(archive.read(relationships), relationships)
    index = 0
    for relationship in root.iter(f"{REL}Relationship"):
        if relationship.get("Type", "").endswith("/hyperlink"):
            index += 1
            builder.add(
                relationship.get("Target", ""),
                ContainerType.UNKNOWN,
                f"hyperlink target {index}",
                "metadata",
                "hyperlinks",
            )


def _extract_properties(
    archive: zipfile.ZipFile,
    names: set[str],
    builder: SegmentBuilder,
) -> None:
    property_parts: Iterable[str] = ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml")
    for part_name in property_parts:
        if part_name not in names:
            continue
        root = _parse_xml(archive.read(part_name), part_name)
        index = 0
        for node in root.iter():
            if node.text and node.text.strip() and len(list(node)) == 0:
                index += 1
                label = node.tag.rsplit("}", 1)[-1]
                builder.add(
                    node.text,
                    ContainerType.UNKNOWN,
                    f"{part_name}, {label} {index}",
                    "metadata",
                    "properties",
                )
