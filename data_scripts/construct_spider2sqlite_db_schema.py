import argparse
import glob
import os
import json
import sqlite3

dbs_todo = set(['oracle_sql_spider2', 'modern_data_spider2', 'f1_spider2', 'WWE_spider2', 'EU_soccer_spider2', 'Baseball_spider2', 'chinook_spider2', 'sqlite-sakila_spider2', 'Db-IMDB_spider2', 'city_legislation_spider2', 'IPL_spider2', 'electronic_sales_spider2', 'AdventureWorks_spider2', 'complex_oracle_spider2', 'California_Traffic_Collision_spider2', 'EntertainmentAgency_spider2', 'imdb_movies_spider2', 'delivery_center_spider2', 'stacking_spider2', 'Brazilian_E_Commerce_spider2', 'northwind_spider2', 'bank_sales_trading_spider2', 'school_scheduling_spider2', 'music_spider2', 'education_business_spider2', 'Airlines_spider2', 'log_spider2', 'BowlingLeague_spider2', 'Pagila_spider2'])

parser = argparse.ArgumentParser()
parser.add_argument("--db_path", type=str, required=True, help="Path to spider_databases/ directory")
parser.add_argument("--output_dir", type=str, default="data/ddls", help="Output directory for DDL files")
args = parser.parse_args()

os.makedirs(args.output_dir, exist_ok=True)

for db_id in dbs_todo:
    db_path = f"{args.db_path}/{db_id}/{db_id}.sqlite"
    assert os.path.exists(db_path), f"DB file {db_path} does not exist."
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table';")
    table_schemas = list(cursor.fetchall())
    current_table = ""
    ignore_keys = ["CONSTRAINT ", "FOREIGN KEY ", "UNIQUE ", "PRIMARY KEY ", "ON DELETE ", "CHECK (", "-- ", ")", "(", "PRIMARY KEY(", "FOREIGN KEY("]
    for (i, (table_schema, )) in enumerate(table_schemas):
        table_schemas[i] = table_schema.split("\n")
        print(table_schema)
        for j, line in enumerate(table_schemas[i]):
            if line.strip().startswith("CREATE TABLE"):
                current_table = line.strip().split(" ")[2].strip("(")
                continue
            is_ignored = False
            for ignore_key in ignore_keys:
                if line.strip().startswith(ignore_key):
                    is_ignored = True
                    break
            if is_ignored:
                continue
            if line.strip(", \t").startswith('"'):
                end_index = line.strip(", \t").find('"', 1)
                col_name = "`" + line.strip(", \t")[1:end_index] + "`"
            else:
                col_name = line.strip(", \t").split(" ")[0].split('\t')[0]
            query = f"SELECT DISTINCT {col_name} FROM {current_table} WHERE {col_name} IS NOT NULL AND {col_name} != '' LIMIT 3;"
            cursor.execute(query)
            results = cursor.fetchall()
            # postprocess results
            results = [r[0] for r in results]
            processed_results = []
            is_truncated = False
            for r in results:
                if isinstance(r, str):
                    # replace newlines with \n
                    r = r.replace("\n", "\\n")
                    # truncate long strings to 100 characters
                    if len(r) > 100:
                        r = r[:100] + "..."
                        is_truncated = True
                    # quote with single quotes and escape single quotes
                    r = "'" + r.replace("'", "''") + "'"
                elif r is None:
                    r = "NULL"
                else:
                    r = str(r)
                processed_results.append(r)
            print(query)
            print(f"Results: {processed_results}")
            if not is_truncated:
                example_string = f"-- example: "
            else:
                example_string = f"-- example (truncated): "
                print(f'{db_id} column {col_name} has truncated values.')
            if len(processed_results) == 0:
                example_string += "NULL"
            elif len(processed_results) == 1:
                example_string += f"[{processed_results[0]}]"
            elif len(processed_results) == 2:
                example_string += f"[{processed_results[0]}, {processed_results[1]}]"
            elif len(processed_results) >= 3:
                example_string += f"[{processed_results[0]}, {processed_results[1]}, {processed_results[2]}]"
            line += " " + example_string
            table_schemas[i][j] = line
    conn.close()
    print(f"Wrote schema for DB {args.output_dir}/{db_id}")
    with open(f"{args.output_dir}/{db_id}.sql", "w") as f:
        for table_schema in table_schemas:
            for line in table_schema:
                f.write(line + "\n")
            f.write("\n")
