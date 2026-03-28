"""Validate that chapter item schemas stay compatible with book-level schemas."""

from pipeline_common import read_json, write_json
from pipeline_params import (
    DATA_DIR,
    PASS_01_ITEM_SCHEMA_FILE,
    PASS_01_SCHEMA_FILE,
    PASS_02_ITEM_SCHEMA_FILE,
    PASS_02_SCHEMA_FILE,
    SCHEMA_CONTRACT_VALIDATION_FILE,
)


def _as_type_set(schema: dict) -> set[str]:
    """Normalize schema type declarations into a set of type names."""
    schema_type = schema.get("type")
    if schema_type is None:
        return set()
    if isinstance(schema_type, list):
        return set(schema_type)
    return {schema_type}


def _compare_node(
    item_node: dict,
    general_node: dict,
    errors: list[str],
    path: str,
) -> None:
    """Recursively compare item and general schema nodes for compatibility."""
    item_types = _as_type_set(item_node)
    general_types = _as_type_set(general_node)
    if item_types and general_types and not item_types.issubset(general_types):
        errors.append(
            f"{path}: item types {sorted(item_types)} not subset of general types {sorted(general_types)}"
        )

    item_enum = item_node.get("enum")
    general_enum = general_node.get("enum")
    if item_enum is not None and general_enum is not None:
        if not set(item_enum).issubset(set(general_enum)):
            errors.append(f"{path}: item enum not subset of general enum")

    item_ref = item_node.get("$ref")
    general_ref = general_node.get("$ref")
    if item_ref is not None and general_ref is not None and item_ref != general_ref:
        errors.append(
            f"{path}: item $ref '{item_ref}' differs from general $ref '{general_ref}'"
        )

    item_required = set(item_node.get("required", []))
    general_required = set(general_node.get("required", []))
    if not item_required.issubset(general_required):
        errors.append(
            f"{path}: item required fields not subset of general required fields"
        )

    item_properties = item_node.get("properties", {})
    general_properties = general_node.get("properties", {})
    for prop_name, item_prop_schema in item_properties.items():
        if prop_name not in general_properties:
            errors.append(f"{path}: property '{prop_name}' missing in general schema")
            continue
        _compare_node(
            item_prop_schema,
            general_properties[prop_name],
            errors,
            f"{path}.properties.{prop_name}",
        )


def validate_phase_contract(
    item_schema: dict, general_schema: dict, phase_name: str
) -> list[str]:
    """Return compatibility errors for one pipeline phase."""
    errors: list[str] = []

    general_item = general_schema.get("properties", {}).get("chapters", {}).get("items")
    if general_item is None:
        return [f"{phase_name}: general schema is missing properties.chapters.items"]

    _compare_node(item_schema, general_item, errors, f"{phase_name}.chapter_item")

    item_defs = item_schema.get("$defs", {})
    general_defs = general_schema.get("$defs", {})
    for def_name, item_def in item_defs.items():
        if def_name not in general_defs:
            errors.append(f"{phase_name}: $defs.{def_name} missing in general schema")
            continue
        _compare_node(
            item_def, general_defs[def_name], errors, f"{phase_name}.$defs.{def_name}"
        )

    return errors


def run_validation() -> dict:
    """Validate both phase contracts and return a structured report."""
    pass_01_item_schema = read_json(PASS_01_ITEM_SCHEMA_FILE)
    pass_01_general_schema = read_json(PASS_01_SCHEMA_FILE)
    pass_02_item_schema = read_json(PASS_02_ITEM_SCHEMA_FILE)
    pass_02_general_schema = read_json(PASS_02_SCHEMA_FILE)

    pass_01_errors = validate_phase_contract(
        pass_01_item_schema, pass_01_general_schema, "pass_01"
    )
    pass_02_errors = validate_phase_contract(
        pass_02_item_schema, pass_02_general_schema, "pass_02"
    )

    all_errors = pass_01_errors + pass_02_errors
    return {
        "is_valid": len(all_errors) == 0,
        "pass_01_errors": pass_01_errors,
        "pass_02_errors": pass_02_errors,
        "errors": all_errors,
    }


def main() -> None:
    """Write validation report and fail fast if incompatibilities exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    report = run_validation()
    write_json(SCHEMA_CONTRACT_VALIDATION_FILE, report)
    if report["is_valid"]:
        print("Schema contract validation passed.")
        return
    print("Schema contract validation failed.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
