import json
import snowflake.connector
import pandas as pd
import sys
import sqlglot
from copy import deepcopy

def remove_null_rows(results):
    return [row for row in results if not all(col is None for col in row)]

def quoting_identifier(sql, db_id):
    with open("./data/db_id_to_col_names.json") as f:
        db_id_to_col_names = json.load(f)
        col_names = db_id_to_col_names[db_id]
    for col_name in col_names:
        if col_name.isupper():
            continue
        
        allowed_prefix = [' ', '(', ',', '.', '\n', '\t']
        allowed_suffix = [' ', ')', ',', '\n', '[', '\t']
        for prefix in allowed_prefix:
            for suffix in allowed_suffix:
                sql = sql.replace(f"{prefix}{col_name}{suffix}", f'{prefix}"{col_name}"{suffix}')
        for prefix in allowed_prefix:
            if sql.endswith(f"{prefix}{col_name}"):
                sql = sql[:-len(col_name)] + f'"{col_name}"'
    return sql
def convert_sqlite_to_snowflake_sql(sqlite_sql):
    try:
        snowflake_sql = sqlglot.transpile(sqlite_sql, read='sqlite', write='snowflake')[0]
        return snowflake_sql
    except Exception as e:
        return sqlite_sql  # Return original SQL if conversion fails
    
def execute_snowflake_wrapper_single(database_id, sql_query, timeout):
    original_sql_query = deepcopy(sql_query)
    sql_query = convert_sqlite_to_snowflake_sql(sql_query)
    sql_query = quoting_identifier(sql_query, database_id)
    
    snowflake_credential = json.load(open('snowflake_credential.json'))
    connection_kwargs = {k: v for k, v in snowflake_credential.items() if k != "session_parameters"}
    session_parameters = snowflake_credential.get("session_parameters", {}).copy()
    session_parameters["STATEMENT_TIMEOUT_IN_SECONDS"] = timeout
    connection_kwargs["session_parameters"] = session_parameters

    conn = snowflake.connector.connect(
        database=database_id,
        **connection_kwargs
    )
    cursor = conn.cursor()
    
    try:
        cursor.execute(original_sql_query)
        results = cursor.fetchall()
        results = remove_null_rows(results)
        res = results, None
    except:
        try:
            cursor.execute(sql_query)
            results = cursor.fetchall()
            results = remove_null_rows(results)
            res = results, None
        except KeyboardInterrupt:
            sys.exit(0)
        except snowflake.connector.errors.ProgrammingError as e:
            error_message = str(e)
            if "STATEMENT_TIMEOUT" in error_message or "SQL execution canceled" in error_message:
                res = None, f"SQL query timeout after {timeout}s: {original_sql_query}"
            else:
                res = None, f"Error executing SQL: {e}, SQL: {original_sql_query}"
        except Exception as e:
            res = None, f"Error executing SQL: {e}, SQL: {original_sql_query}"
    finally:
        cursor.close()
        conn.close()

    return res