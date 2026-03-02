"""Generate spider2sqlite_tables.json by introspecting SQLite databases.

Follows the exact schema from ../noisy-rl/data/dev/dev_tables.json:
- db_id, table_names_original, table_names
- column_names_original, column_names (with [-1, "*"] sentinel)
- column_types, primary_keys, foreign_keys
"""

import argparse
import json
import os
import re
import sqlite3


def humanize_name(name: str) -> str:
    """Convert a column/table name to a more human-readable form.

    Examples:
        CustomerID -> Customer ID
        gas_station -> gas station
        TransactionID -> Transaction ID
        order_items -> order items
    """
    # Replace underscores with spaces
    name = name.replace("_", " ")
    # Insert space before uppercase letters that follow lowercase letters (CamelCase splitting)
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    # Insert space before uppercase letter followed by uppercase+lowercase (e.g., "HTMLParser" -> "HTML Parser")
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name)
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name).strip()
    return name


def normalize_type(sqlite_type: str) -> str:
    """Map SQLite column types to the simplified type system used in spider tables.json."""
    t = sqlite_type.upper().strip() if sqlite_type else ""

    if not t:
        return "text"

    if "INT" in t:
        return "integer"
    if "REAL" in t or "FLOAT" in t or "DOUBLE" in t or "NUMERIC" in t or "DECIMAL" in t:
        return "real"
    if "DATE" in t or "TIME" in t:
        # DATE, DATETIME, TIMESTAMP all map to "text" in some spider schemas,
        # but in the reference they sometimes use "date". We'll use "text" for
        # DATETIME/TIMESTAMP and "date" for DATE-only.
        if t == "DATE":
            return "date"
        return "text"
    if "BOOL" in t:
        return "integer"
    if "BLOB" in t:
        return "text"
    # TEXT, VARCHAR, CHAR, CLOB, etc.
    return "text"


def get_db_schema(db_path: str, db_id: str) -> dict:
    """Introspect a SQLite database and return its schema in spider tables.json format."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all user tables (excluding sqlite internal tables)
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    table_names_original = tables
    table_names = [humanize_name(t) for t in tables]

    # Build column lists
    # Start with the [-1, "*"] sentinel
    column_names_original = [[-1, "*"]]
    column_names = [[-1, "*"]]
    column_types = ["text"]  # type for the "*" sentinel

    # Track primary keys and build a mapping from (table_idx, col_name) -> flat column index
    primary_keys = []
    col_lookup = {}  # (table_name, col_name) -> flat_index

    for table_idx, table_name in enumerate(tables):
        cursor.execute(f"PRAGMA table_info(`{table_name}`)")
        columns = cursor.fetchall()
        # columns: (cid, name, type, notnull, dflt_value, pk)

        pk_cols_for_table = []
        for col in columns:
            cid, col_name, col_type, notnull, dflt_value, pk_flag = col
            flat_idx = len(column_names_original)

            column_names_original.append([table_idx, col_name])
            column_names.append([table_idx, humanize_name(col_name)])
            column_types.append(normalize_type(col_type))

            col_lookup[(table_name, col_name)] = flat_idx

            if pk_flag > 0:
                pk_cols_for_table.append((pk_flag, flat_idx))

        # Sort by pk order and add to primary_keys
        if pk_cols_for_table:
            pk_cols_for_table.sort(key=lambda x: x[0])
            pk_indices = [idx for _, idx in pk_cols_for_table]
            if len(pk_indices) == 1:
                primary_keys.append(pk_indices[0])
            else:
                # Composite primary key: stored as a list
                primary_keys.append(pk_indices)

    # Build foreign keys
    foreign_keys = []
    for table_idx, table_name in enumerate(tables):
        cursor.execute(f"PRAGMA foreign_key_list(`{table_name}`)")
        fk_rows = cursor.fetchall()
        # fk_rows: (id, seq, table, from, to, on_update, on_delete, match)
        for fk in fk_rows:
            fk_id, seq, ref_table, from_col, to_col, *_ = fk
            from_idx = col_lookup.get((table_name, from_col))
            to_idx = col_lookup.get((ref_table, to_col))
            if from_idx is not None and to_idx is not None:
                foreign_keys.append([from_idx, to_idx])

    conn.close()

    return {
        "db_id": db_id,
        "table_names_original": table_names_original,
        "table_names": table_names,
        "column_names_original": column_names_original,
        "column_names": column_names,
        "column_types": column_types,
        "primary_keys": primary_keys,
        "foreign_keys": foreign_keys,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_path", type=str, required=True, help="Path to spider_databases/ directory")
    parser.add_argument("--output", type=str, default="data/spider2sqlite_tables.json", help="Output JSON path")
    args = parser.parse_args()

    DB_DIR = args.db_path
    OUTPUT_PATH = args.output

    results = []

    # Find all directories ending with "spider2"
    db_dirs = sorted([
        d for d in os.listdir(DB_DIR)
        if os.path.isdir(os.path.join(DB_DIR, d)) and d.endswith("spider2")
    ])

    print(f"Found {len(db_dirs)} spider2 databases")

    for db_dir in db_dirs:
        db_id = db_dir
        db_path = os.path.join(DB_DIR, db_dir, f"{db_dir}.sqlite")
        if not os.path.exists(db_path):
            print(f"  WARNING: {db_path} not found, skipping")
            continue

        print(f"  Processing {db_id}...")
        schema = get_db_schema(db_path, db_id)
        results.append(schema)
        print(f"    {len(schema['table_names_original'])} tables, "
              f"{len(schema['column_names_original']) - 1} columns, "
              f"{len(schema['primary_keys'])} PKs, "
              f"{len(schema['foreign_keys'])} FKs")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=4)

    print(f"\nWrote {len(results)} database schemas to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
