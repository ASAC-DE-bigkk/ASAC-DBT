"""Internal _schema_contract resources responsibility."""

from __future__ import annotations

from .descriptions import (
    _description_evidence,
    _scalar,
)

from .types import (
    MapEntry,
    Node,
    ScanError,
)


def _is_selected(name: str, selected: set[str] | None) -> bool:
    return selected is None or name in selected


def _scan_columns(
    resource: Node,
    *,
    path: str,
    resource_kind: str,
    resource_name: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    descriptions: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    columns_entry = resource.entry("columns")
    if columns_entry is None:
        return descriptions, errors
    if columns_entry.value.kind != "seq":
        raise ScanError("columns must be a block sequence", line=columns_entry.line)
    seen: dict[str, int] = {}
    for column_node in columns_entry.value.sequence:
        if column_node.kind != "map":
            raise ScanError(
                "column item must be a mapping",
                line=column_node.line,
                code="MISSING_COLUMN_NAME",
            )
        name_entry = column_node.entry("name")
        column_name = _scalar(name_entry, context="column name")
        if not column_name or name_entry is None:
            errors.append(
                {
                    "code": "MISSING_COLUMN_NAME",
                    "file": path,
                    "line": column_node.line,
                    "message": f"column in {resource_kind} '{resource_name}' has no scalar name",
                    "resource_kind": resource_kind,
                    "resource_name": resource_name,
                }
            )
            continue
        if column_name in seen:
            errors.append(
                {
                    "code": "DUPLICATE_COLUMN",
                    "column": column_name,
                    "file": path,
                    "lines": [seen[column_name], name_entry.line],
                    "message": f"duplicate column '{column_name}' in {resource_kind} '{resource_name}'",
                    "resource_kind": resource_kind,
                    "resource_name": resource_name,
                }
            )
        else:
            seen[column_name] = name_entry.line
        evidence, error = _description_evidence(
            path=path,
            resource_kind=resource_kind,
            resource_name=resource_name,
            entity_kind="column",
            identifier=column_name,
            description=column_node.entry("description"),
            entity_line=name_entry.line,
            column=column_name,
        )
        descriptions.append(evidence)
        if error:
            errors.append(error)
    return descriptions, errors


def _scan_resource(
    node: Node,
    *,
    path: str,
    kind: str,
    name: str,
    name_line: int,
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    resource = {"file": path, "kind": kind, "line": name_line, "name": name}
    description, error = _description_evidence(
        path=path,
        resource_kind=kind,
        resource_name=name,
        entity_kind="resource",
        identifier=name,
        description=node.entry("description"),
        entity_line=name_line,
    )
    descriptions = [description]
    errors = [error] if error else []
    column_descriptions, column_errors = _scan_columns(
        node, path=path, resource_kind=kind, resource_name=name
    )
    descriptions.extend(column_descriptions)
    errors.extend(column_errors)
    return resource, descriptions, errors


def _named_items(entry: MapEntry, context: str) -> list[tuple[Node, str, int]]:
    if entry.value.kind != "seq":
        raise ScanError(f"{context} must be a block sequence", line=entry.line)
    result: list[tuple[Node, str, int]] = []
    for node in entry.value.sequence:
        if node.kind != "map":
            raise ScanError(
                f"{context} item must be a mapping",
                line=node.line,
                code="MISSING_RESOURCE_NAME",
            )
        name_entry = node.entry("name")
        name = _scalar(name_entry, context=f"{context} name")
        if not name or name_entry is None:
            raise ScanError(
                f"{context} item requires a scalar name",
                line=node.line,
                code="MISSING_RESOURCE_NAME",
            )
        result.append((node, name, name_entry.line))
    return result


def _duplicate_resource_error(
    *, path: str, kind: str, name: str, first_line: int, second_line: int
) -> dict[str, object]:
    return {
        "code": "DUPLICATE_RESOURCE",
        "file": path,
        "lines": [first_line, second_line],
        "message": f"duplicate {kind} resource '{name}'",
        "resource_kind": kind,
        "resource_name": name,
    }


def _extract_resources(
    root: Node, path: str, selected: set[str] | None
) -> tuple[
    list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], set[str]
]:
    resources: list[dict[str, object]] = []
    descriptions: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    discovered: set[str] = set()

    for section, kind in (("models", "model"), ("seeds", "seed")):
        section_entry = root.entry(section)
        if section_entry is None:
            continue
        items = _named_items(section_entry, section)
        seen: dict[str, int] = {}
        for node, name, line in items:
            discovered.add(name)
            selected_here = _is_selected(name, selected)
            if selected_here and name in seen:
                errors.append(
                    _duplicate_resource_error(
                        path=path,
                        kind=kind,
                        name=name,
                        first_line=seen[name],
                        second_line=line,
                    )
                )
            elif selected_here:
                seen[name] = line
            if not selected_here:
                continue
            resource, evidence, resource_errors = _scan_resource(
                node, path=path, kind=kind, name=name, name_line=line
            )
            resources.append(resource)
            descriptions.extend(evidence)
            errors.extend(resource_errors)

    sources_entry = root.entry("sources")
    if sources_entry is not None:
        sources = _named_items(sources_entry, "sources")
        seen_sources: dict[str, int] = {}
        for source_node, source_name, source_line in sources:
            canonical_source = f"source:{source_name}"
            discovered.add(canonical_source)
            source_selected = _is_selected(canonical_source, selected)
            if source_selected and source_name in seen_sources:
                errors.append(
                    _duplicate_resource_error(
                        path=path,
                        kind="source",
                        name=canonical_source,
                        first_line=seen_sources[source_name],
                        second_line=source_line,
                    )
                )
            elif source_selected:
                seen_sources[source_name] = source_line
            if source_selected:
                resource, evidence, resource_errors = _scan_resource(
                    source_node,
                    path=path,
                    kind="source",
                    name=canonical_source,
                    name_line=source_line,
                )
                resources.append(resource)
                descriptions.extend(evidence)
                errors.extend(resource_errors)

            tables_entry = source_node.entry("tables")
            if tables_entry is None:
                continue
            tables = _named_items(tables_entry, f"tables for source {source_name}")
            seen_tables: dict[str, int] = {}
            for table_node, table_name, table_line in tables:
                canonical_table = f"source:{source_name}.{table_name}"
                discovered.add(canonical_table)
                table_selected = _is_selected(canonical_table, selected)
                if table_selected and table_name in seen_tables:
                    errors.append(
                        _duplicate_resource_error(
                            path=path,
                            kind="source_table",
                            name=canonical_table,
                            first_line=seen_tables[table_name],
                            second_line=table_line,
                        )
                    )
                elif table_selected:
                    seen_tables[table_name] = table_line
                if not table_selected:
                    continue
                resource, evidence, resource_errors = _scan_resource(
                    table_node,
                    path=path,
                    kind="source_table",
                    name=canonical_table,
                    name_line=table_line,
                )
                resources.append(resource)
                descriptions.extend(evidence)
                errors.extend(resource_errors)
    return resources, descriptions, errors, discovered
