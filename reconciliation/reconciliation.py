from anthropic import Anthropic
import re

DEFAULT_MODEL = "claude-opus-4-6"

reconciliation_template = """You are an expert SQL query reviewer. Given a natural language question, an external knowledge hint, and a set of SQL queries (which all share the same execution result), your task is to determine whether the SQL query set answers the question correctly and covers the provided hint comprehensively.

### Instructions:
1. **Analyze the Hint:** The natural language question might be ambiguous. Use the provided hint to clarify the intent.
2. **Strict Adherence:** The SQL query must fully incorporate the specific logic, formulas, and definitions provided in the hint or the natural language question.
3.  **Handling "Extra" Elements:**
    -. *Output Columns:* Extra columns in the SELECT statement is **Correct** if they do not change the correctness of the answer to the question. However, missing any column that is explicitly required by the question or hint is **Incorrect**.
    -. *Filtering/Logic:* Extra logic (like casting types, handling NULLs, or joining tables to reach attributes) is **Correct** if it ensures data integrity.
4.  **Set Evaluation:** If *any* query in the provided set meets these criteria, the entire set should be labeled "Correct".

### Evaluation Criteria & Examples:
The provided hint will include following type of information. For each type, the SQL query must address it completely.

1. Computation formulas:
    - Example hint 1: percentage refers to DIVIDE(COUNT(student_id where type = 'TPG' and first_name = 'Ogdon', last_name = 'Zywicki'), COUNT(first_name = 'Ogdon', last_name = 'Zywicki')) * 100
    - Example correct SQL: SELECT CAST(SUM(CASE WHEN T3.type = 'TPG' THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(T1.student_id) FROM RA AS T1 INNER JOIN prof AS T2 ON T1.prof_id = T2.prof_id INNER JOIN student AS T3 ON T1.student_id = T3.student_id WHERE T2.first_name = 'Ogdon' AND T2.last_name = 'Zywicki'
    - Example incorrect SQL: SELECT CAST(SUM(CASE WHEN T3.type = 'TPG' THEN 1 ELSE 0 END) AS REAL) * 100 / CAST(SUM(CASE WHEN T2.first_name = 'Ogdon' AND T2.last_name = 'Zywicki' THEN 1 ELSE 0 END) AS REAL) FROM RA AS T1 INNER JOIN prof AS T2 ON T1.prof_id = T2.prof_id INNER JOIN student AS T3 ON T1.student_id = T3.student_id
    - Example hint 2: percentage = DIVIDE(count(SalesOrderID(OrderQty<3 & UnitPriceDiscount = 0)), count(SalesOrderID))*100%
    - Example correct SQL: WITH total_orders AS (SELECT DISTINCT `SalesOrderID` FROM `SalesOrderDetail`), qual_orders AS ( SELECT DISTINCT `SalesOrderID` FROM `SalesOrderDetail` WHERE `OrderQty` <= 3 AND `UnitPriceDiscount` = 0) SELECT 100.0 * (SELECT COUNT(*) FROM qual_orders) / NULLIF((SELECT COUNT(*) FROM total_orders),0) AS percentage;
    - Example incorrect SQL: SELECT CAST(SUM(CASE WHEN OrderQty < 3 AND UnitPriceDiscount = 0 THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(SalesOrderID) FROM SalesOrderDetail
2. Specific filtering conditions:
    - Example hint 1: in Middle Atlantic refers to division = 'Middle Atlantic'; female refers to sex = 'Female'; no more than 18 refers to age <= 18
    - Example correct SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.sex = 'Female' AND T1.age <= 18
    - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.sex = 'Female' AND T1.age < 18
    - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.age < 18
    - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division LIKE '%Middle Atlantic%' AND T1.sex = 'Female' AND T1.age < 18
3. Strict string predicate handling (distinguishing between exact match and partial match):
    - Example hint 1: in Middle Atlantic refers to division = 'Middle Atlantic'; female refers to sex = 'Female'; no more than 18 refers to age <= 18
    - Example correct SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.sex = 'Female' AND T1.age <= 18
    - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division LIKE '%Middle Atlantic%' AND T1.sex = 'Female' AND T1.age < 18
    - Example hint 2: winning teams' refers to Match_Winner; played in St George's Park refers to Venue_Name like 'St George%'
    - Example correct SQL: SELECT DISTINCT M.`Match_Winner` FROM `Match` AS M JOIN `Venue` AS V ON V.`Venue_Id` = M.`Venue_Id` WHERE V.`Venue_Name` LIKE 'St George%';
    - Example incorrect SQL: SELECT DISTINCT M.`Match_Winner` FROM `Match` AS M JOIN `Venue` AS V ON V.`Venue_Id` = M.`Venue_Id` WHERE V.`Venue_Name` = 'St George';
    - Example incorrect SQL: SELECT DISTINCT M.`Match_Winner` FROM `Match` AS M JOIN `Venue` AS V ON V.`Venue_Id` = M.`Venue_Id` WHERE V.`Venue_Name` = 'St George%';
4. Specific output columns:
    - Example question 1: Please list the full names of all employees.
    - Example hint 1: full name refers to FirstName, LastName
    - Example correct SQL: SELECT FirstName, LastName FROM Employees
    - Example correct SQL: SELECT FirstName, LastName, Title FROM Employees
    - Example incorrect SQL: SELECT FirstName FROM Employees
    - Example question 2: Please list the countries on the European Continent that have a population growth of more than 3%.
    - Example hint 2: Country refers to Code
    - Example correct SQL: SELECT T1.Code FROM country AS T1 INNER JOIN encompasses AS T2 ON T1.Code = T2.Country INNER JOIN continent AS T3 ON T3.Name = T2.Continent INNER JOIN population AS T4 ON T4.Country = T1.Code WHERE T3.Name = 'Europe' AND T4.Population_Growth > 0.03
    - Example incorrect SQL: SELECT T1.Name FROM country AS T1 INNER JOIN encompasses AS T2 ON T1.Code = T2.Country INNER JOIN continent AS T3 ON T3.Name = T2.Continent INNER JOIN population AS T4 ON T4.Country = T1.Code WHERE T3.Name = 'Europe' AND T4.Population_Growth > 0.03
5. Specific output formats:
    - Example question 1: Which repository has the longest amount of processed time of downloading? Indicate whether the solution paths in the repository can be implemented without needs of compilation, Yes or No.
    - Example hint 1: longest amount of processed time refers to max(ProcessedTime); the repository can be implemented without needs of compilation refers to WasCompiled = 1 for all solutions;
    - Example correct SQL: SELECT r.Id AS RepoId, CASE WHEN MIN(CASE WHEN s.WasCompiled = 1 THEN 1 ELSE 0 END) = 1 THEN 'Yes' ELSE 'No' END AS CanRunWithoutCompilation FROM Repo r LEFT JOIN Solution s ON s.RepoId = r.Id WHERE r.ProcessedTime = (SELECT MAX(ProcessedTime) FROM Repo) GROUP BY r.Id;
    - Example incorrect SQL: SELECT DISTINCT T1.id, T2.WasCompiled FROM Repo AS T1 INNER JOIN Solution AS T2 ON T1.Id = T2.RepoId WHERE T1.ProcessedTime = ( SELECT MAX(ProcessedTime) FROM Repo )

Requirement:
1. Analyze the question and hint against the queries.
2. If you are unsure due to ambiguity, answer "Unsure".
3. Think through your reasoning step-by-step.
4. Conclude with one of three labels wrapped in tags: `<answer>Correct</answer>`, `<answer>Incorrect</answer>`, or `<answer>Unsure</answer>`.

**Question:** {question}
**Hint:** {hint}
**SQL Query set:**
{sql_query}"""

def run_anthropic_model(prompt: str, model_name: str = DEFAULT_MODEL, temperature: float = 0.0, max_tokens: int = 512) -> str:
    client = Anthropic()
    response = client.messages.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.content[0].text

def determine_one_generation(question, evidence, sql):
    from prompt import query_reconciliation_template
    prompt = query_reconciliation_template.format(
        question=question,
        hint=evidence,
        sql_query=sql
    )
    response = run_anthropic_model(prompt, max_tokens=1024)
    return response.strip()

def determine_one_generation_defensive(question, evidence: str="", sql: str="", model_name=DEFAULT_MODEL):
    assert sql != "", "SQL query cannot be empty."
    prompt = reconciliation_template.format(
        question=question,
        hint=evidence,
        sql_query=sql
    )
    response = run_anthropic_model(prompt, model_name=model_name, max_tokens=4096)
    matches = re.findall(r'<answer>(.*?)</answer>', response, re.DOTALL)
    if matches:
        return matches[-1].strip(), response, prompt
    return "Unsure", response, prompt

def determine_one_generation_detailed(question, evidence, sql):
    from prompt import query_reconciliation_detailed_template
    prompt = query_reconciliation_detailed_template.format(
        question=question,
        hint=evidence,
        sql_query=sql
    )
    response = run_anthropic_model(prompt, max_tokens=4096)
    matches = re.findall(r'<answer>(.*?)</answer>', response, re.DOTALL)
    if matches:
        return matches[-1].strip(), response
    return "Unsure", response

def determine_one_generation_detailed_flexible(question, evidence, sql):
    from prompt import query_reconciliation_flexible_detailed_template
    prompt = query_reconciliation_flexible_detailed_template.format(
        question=question,
        hint=evidence,
        sql_query=sql
    )
    response = run_anthropic_model(prompt, max_tokens=4096)
    matches = re.findall(r'<answer>(.*?)</answer>', response, re.DOTALL)
    if matches:
        return matches[-1].strip(), response
    return "Unsure", response

def determine_one_set_of_generations(question, evidence, sql_list):
    from prompt import query_set_reconciliation_template
    sql_queries_formatted = "\n".join([f"- {i+1}:\n{sql}" for i, sql in enumerate(sql_list)])
    prompt = query_set_reconciliation_template.format(
        question=question,
        hint=evidence,
        sql_queries=sql_queries_formatted
    )
    response = run_anthropic_model(prompt, max_tokens=1024)
    return response.strip()

if __name__ == "__main__":
    question = "Among the Artifact cards, which are black color and comes with foreign languague translation?"
    hint = "Artifact card refers to originalType = 'Artifact'; black color refers to colors = 'B'; foreign language refers to language in foreign_data"
    sql_query = """SELECT DISTINCT c.name
FROM cards c JOIN foreign_data f
  ON c.uuid = f.uuid
WHERE c.originalType LIKE '%Artifact%' AND c.colors LIKE '%B%';"""
    result, response, prompt = determine_one_generation_defensive(question, hint, sql_query)
    print(f"Model determination: {result}")