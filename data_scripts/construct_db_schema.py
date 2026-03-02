import glob
import csv
import sqlite3

dbs = glob.glob("correct-dev/dev_databases/*/database_description")
print(dbs)

table_ddl = """CREATE TABLE {table_name} (
{columns}
{key_constraints}
);

"""

column_ddl = "    `{column_name}` {data_type}, -- {column_description}"

def find_wired_characters(s: str):
    normal_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:.,;!?@#$%^&*()-+=[]{}|<>/\\\"' \n")
    found = set()
    for char in s:
        if char not in normal_chars:
            found.add(char)
    return found

for db in dbs:
    db_name = db.split("/")[-2]
    tables = glob.glob(f"{db}/*.csv")
    db_ddl = ""
    db_file = f"correct-dev/dev_databases/{db_name}/{db_name}.sqlite"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    print(f"Database: {db_name}")
    for table in tables:
        cursor.execute("SELECT * FROM sqlite_master WHERE type='table' AND name=?", (table.split("/")[-1].replace(".csv", ""),))
        table_schema = cursor.fetchone()
        
        # extract key information from table_schema
        if not table_schema:
            exit()
        table_schema_lines = table_schema[4].split("\n")
        key_constraints = []
        last_line = ""
        for line in table_schema_lines:
            line = line.strip()
            if " key (" in line.lower():
                # line = line.replace("(", "(`")
                # line = line.replace(")", "`),")
                line = line.replace("`", "")
                key_constraints.append(line)
            elif "primary key" in line.lower():
                if line.strip().startswith("primary key"):
                    column_name = last_line.strip().split(" ")[0].strip("`")
                else:
                    column_name = line.strip().split()[0].strip("`")    
                column_name = column_name.replace("`", "")
                key_constraints.append(f"primary key ({column_name}),")
            if not line.strip().startswith("constraint"):
                last_line = line
        key_constraints_str = ""
        if key_constraints:
            key_constraints_str = "\n".join(["    " + kc for kc in key_constraints])
            key_constraints_str = key_constraints_str.rstrip(",\n")
        
        print(f"Table schema: {table_schema[4]}, {key_constraints_str}")

        table_name = table.split("/")[-1].replace(".csv", "")
        print(f"Processing table: {table}")
        with open(table, "r", encoding="cp1252") as f:
            reader = csv.reader(f)
            rows = list(reader)
        column_ddls = []
        for row in rows[1:]:
            if len(row) < 5:
                print(f"Row too short in {table}: {row}")
                continue
            try:
                original_column_name, column_name, column_description, data_type, value_description = row[:5]
                assert data_type.strip()
            except:
                print(f"Error parsing row in {table}: {row}")
                exit()
            assert '\u00a0' not in value_description
            column_name = column_name.strip()
            column_description = column_description.strip()
            value_description = value_description.strip().replace("commonsense evidence:", "")
            if column_description == column_name:
                column_description = ""
            if value_description == column_name:
                value_description = ""
            if value_description == column_description:
                value_description = ""
            if column_name == original_column_name:
                column_name = ""
            # add a period at the end of line for each description if not exists
            column_description_lines = column_description.split("\n")
            column_description_lines = [line.strip() for line in column_description_lines if line.strip()]
            column_description_lines = [line + "." if not line.endswith((".", ";", "?", "!")) else line for line in column_description_lines]
            column_description = " ".join(column_description_lines)
            value_description_lines = value_description.split("\n")
            value_description_lines = [line.strip() for line in value_description_lines if line.strip()]
            value_description_lines = [line + "." if not line.endswith((".", ";", "?", "!")) else line for line in value_description_lines]
            value_description = " ".join(value_description_lines)
            # remove any space more than 1
            column_description = " ".join(column_description.split())
            value_description = " ".join(value_description.split())
            
            comment = ""
            if column_name:
                comment += f"{column_name}."
            if column_description and column_description.strip() != ".":
                if comment:
                    comment += " "
                comment += column_description
            if value_description and value_description.strip() != ".":
                if comment:
                    comment += " "
                comment += value_description

            column_ddl_str = column_ddl.format(
                column_name=original_column_name,
                data_type=data_type,
                column_description=comment if comment else "No description."
            )
            column_ddls.append(column_ddl_str)
        table_ddl_str = table_ddl.format(
            table_name=table_name,
            columns="\n".join(column_ddls),
            key_constraints=key_constraints_str
        )
        db_ddl += table_ddl_str
    with open(f"data/ddls/{db_name}.sql", "w", encoding="cp1252") as f:
        f.write(db_ddl)
        
    