query_reconciliation_template = """You are an expert SQL query reviewer. Given a natural language question, a external knowledge hint, and a SQL query, you task is to determine whether the SQL query answers the question correctly, covers the provided hint comprehensively, and does not introduce extra unrelated calculation, predicates, or logic. 

Requirement:
1. You can be unsure if you are not confident.
2. Only respond with one of the three labels: "Correct", "Incorrect", or "Unsure".
3. "Correct" means the SQL query answers the question correctly and covers the hint comprehensively without introducing extra unrelated calculation, predicates, or logic.
4. "Incorrect" means the SQL query does not answer the question correctly, or misses any part of the hint, or introduces extra unrelated calculation, predicates, or logic.
5. "Unsure" means you are not confident to determine whether the SQL query is correct or incorrect based on the provided question and hint.

Question: {question}
Hint: {hint}
SQL Query: {sql_query}

Your answer:"""

query_set_reconciliation_template = """You are an expert SQL query reviewer. Given a natural language question, a external knowledge hint, and a set of SQL queries (with the same execution result), you task is to determine whether any SQL query from the provided set answers the question correctly, covers the provided hint comprehensively, and does not introduce extra unrelated calculation, predicates, or logic. 

Requirement:
1. You can be unsure if you are not confident.
2. Only respond with one of the three labels: "Correct", "Incorrect", or "Unsure".
3. "Correct" means the SQL query answers the question correctly and covers the hint comprehensively without introducing extra unrelated calculation, predicates, or logic.
4. "Incorrect" means the SQL query does not answer the question correctly, or misses any part of the hint, or introduces extra unrelated calculation, predicates, or logic.
5. "Unsure" means you are not confident to determine whether the SQL query is correct or incorrect based on the provided question and hint.

Question: {question}
Hint: {hint}
A set of SQL Queries with the same execution result: 
{sql_queries}

Your answer:"""

query_reconciliation_detailed_template = """You are an expert SQL query reviewer. Given a natural language question, a external knowledge hint, and a SQL query, you task is to determine whether the SQL query answers the question correctly, covers the provided hint comprehensively, and does not introduce extra unrelated calculation, predicates, or logic. 

Instructions:
1. The natural language question might be ambiguous or underspecified on its own. The provided hint is intended to clarify or disambiguate the question.
2. Carefully analyze whether the SQL query fully incorporates the information from the hint in order to accurately answer the question.
3. If the SQL query misses any part of the hint, or introduces extra unrelated calculation, predicates, or logic, it should be considered incorrect.
4. The provided hint will include following type of information. For each type, the SQL query must address it completely.
    i. computation formulas or specific calculation methods: 
        - Example hint 1: percentage refers to DIVIDE(COUNT(student_id where type = 'TPG' and first_name = 'Ogdon', last_name = 'Zywicki'), COUNT(first_name = 'Ogdon', last_name = 'Zywicki')) * 100
        - Example correct SQL: SELECT CAST(SUM(CASE WHEN T3.type = 'TPG' THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(T1.student_id) FROM RA AS T1 INNER JOIN prof AS T2 ON T1.prof_id = T2.prof_id INNER JOIN student AS T3 ON T1.student_id = T3.student_id WHERE T2.first_name = 'Ogdon' AND T2.last_name = 'Zywicki'
        - Example incorrect SQL: SELECT CAST(SUM(CASE WHEN T3.type = 'TPG' THEN 1 ELSE 0 END) AS REAL) * 100 / CAST(SUM(CASE WHEN T2.first_name = 'Ogdon' AND T2.last_name = 'Zywicki' THEN 1 ELSE 0 END) AS REAL) FROM RA AS T1 INNER JOIN prof AS T2 ON T1.prof_id = T2.prof_id INNER JOIN student AS T3 ON T1.student_id = T3.student_id 
        - Example hint 2: percentage = DIVIDE(count(SalesOrderID(OrderQty<3 & UnitPriceDiscount = 0)), count(SalesOrderID))*100%
        - Example correct SQL: WITH total_orders AS (SELECT DISTINCT `SalesOrderID` FROM `SalesOrderDetail`), qual_orders AS ( SELECT DISTINCT `SalesOrderID` FROM `SalesOrderDetail` WHERE `OrderQty` <= 3 AND `UnitPriceDiscount` = 0) SELECT 100.0 * (SELECT COUNT(*) FROM qual_orders) / NULLIF((SELECT COUNT(*) FROM total_orders),0) AS percentage;
        - Example incorrect SQL: SELECT CAST(SUM(CASE WHEN OrderQty < 3 AND UnitPriceDiscount = 0 THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(SalesOrderID) FROM SalesOrderDetail
    ii. specific filtering conditions or predicates:
        - Example hint 1: in Middle Atlantic refers to division = 'Middle Atlantic'; female refers to sex = 'Female'; no more than 18 refers to age <= 18
        - Example correct SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.sex = 'Female' AND T1.age <= 18
        - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.sex = 'Female' AND T1.age < 18
        - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.age < 18
        - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division LIKE '%Middle Atlantic%' AND T1.sex = 'Female' AND T1.age < 18
    iii. specific output columns:
        - Example question 1: Please list the full names of all employees.
        - Example hint 1: full name refers to FirstName, LastName
        - Example correct SQL: SELECT FirstName, LastName FROM Employees
        - Example incorrect SQL: SELECT FirstName, LastName, Title FROM Employees
        - Example incorrect SQL: SELECT FirstName FROM Employees
        - Example question 2: Please list the countries on the European Continent that have a population growth of more than 3%.
        - Example hint 2: Country refers to Code
        - Example correct SQL: SELECT T1.Code FROM country AS T1 INNER JOIN encompasses AS T2 ON T1.Code = T2.Country INNER JOIN continent AS T3 ON T3.Name = T2.Continent INNER JOIN population AS T4 ON T4.Country = T1.Code WHERE T3.Name = 'Europe' AND T4.Population_Growth > 0.03
        - Example incorrect SQL: SELECT T1.Name FROM country AS T1 INNER JOIN encompasses AS T2 ON T1.Code = T2.Country INNER JOIN continent AS T3 ON T3.Name = T2.Continent INNER JOIN population AS T4 ON T4.Country = T1.Code WHERE T3.Name = 'Europe' AND T4.Population_Growth > 0.03
    iv. specific output formats:
        - Example question 1: Which repository has the longest amount of processed time of downloading? Indicate whether the solution paths in the repository can be implemented without needs of compilation, Yes or No.
        - Example hint 1: longest amount of processed time refers to max(ProcessedTime); the repository can be implemented without needs of compilation refers to WasCompiled = 1 for all solutions;
        - Example correct SQL: SELECT r.Id AS RepoId, CASE WHEN MIN(CASE WHEN s.WasCompiled = 1 THEN 1 ELSE 0 END) = 1 THEN 'Yes' ELSE 'No' END AS CanRunWithoutCompilation FROM Repo r LEFT JOIN Solution s ON s.RepoId = r.Id WHERE r.ProcessedTime = (SELECT MAX(ProcessedTime) FROM Repo) GROUP BY r.Id;
        - Example incorrect SQL: SELECT DISTINCT T1.id, T2.WasCompiled FROM Repo AS T1 INNER JOIN Solution AS T2 ON T1.Id = T2.RepoId WHERE T1.ProcessedTime = ( SELECT MAX(ProcessedTime) FROM Repo )

Requirement:
1. You can be unsure if you are not confident.
2. Only respond with one of the three labels: "Correct", "Incorrect", or "Unsure".
3. "Correct" means the SQL query answers the question correctly and covers the hint comprehensively without introducing extra unrelated calculation, predicates, or logic.
4. "Incorrect" means the SQL query does not answer the question correctly, or misses any part of the hint, or introduces extra unrelated calculation, predicates, or logic.
5. "Unsure" means you are not confident to determine whether the SQL query is correct or incorrect based on the provided question and hint.

Format:
1. Please thinking thoroughly before you answer.
2. Please wrap your answer with <answer> and </answer> tags. For example, if you think the SQL query is correct, please answer <answer>Correct</answer>.

Question: {question}
Hint: {hint}
SQL Query: {sql_query}"""

query_reconciliation_flexible_detailed_template = """You are an expert SQL query reviewer. Given a natural language question, a external knowledge hint, and a SQL query, you task is to determine whether the SQL query answers the question correctly and covers the provided hint comprehensively.

Instructions:
1. The natural language question might be ambiguous or underspecified on its own. The provided hint is intended to clarify or disambiguate the question.
2. Carefully analyze whether the SQL query fully incorporates the information from the hint in order to accurately answer the question.
3. If the SQL query misses any part of the hint, it should be considered incorrect. If the query introduces extra unrelated calculation, predicates, or logic, this may be because necessary data properties or relationships are not explicitly stated in the hint or question. In such cases, you can ignore the extra parts as long as all aspects of the hint are covered.
4. The provided hint will include following type of information. For each type, the SQL query must address it completely.
    i. computation formulas or specific calculation methods: 
        - Example hint 1: percentage refers to DIVIDE(COUNT(student_id where type = 'TPG' and first_name = 'Ogdon', last_name = 'Zywicki'), COUNT(first_name = 'Ogdon', last_name = 'Zywicki')) * 100
        - Example correct SQL: SELECT CAST(SUM(CASE WHEN T3.type = 'TPG' THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(T1.student_id) FROM RA AS T1 INNER JOIN prof AS T2 ON T1.prof_id = T2.prof_id INNER JOIN student AS T3 ON T1.student_id = T3.student_id WHERE T2.first_name = 'Ogdon' AND T2.last_name = 'Zywicki'
        - Example incorrect SQL: SELECT CAST(SUM(CASE WHEN T3.type = 'TPG' THEN 1 ELSE 0 END) AS REAL) * 100 / CAST(SUM(CASE WHEN T2.first_name = 'Ogdon' AND T2.last_name = 'Zywicki' THEN 1 ELSE 0 END) AS REAL) FROM RA AS T1 INNER JOIN prof AS T2 ON T1.prof_id = T2.prof_id INNER JOIN student AS T3 ON T1.student_id = T3.student_id 
        - Example hint 2: percentage = DIVIDE(count(SalesOrderID(OrderQty<3 & UnitPriceDiscount = 0)), count(SalesOrderID))*100%
        - Example correct SQL: WITH total_orders AS (SELECT DISTINCT `SalesOrderID` FROM `SalesOrderDetail`), qual_orders AS ( SELECT DISTINCT `SalesOrderID` FROM `SalesOrderDetail` WHERE `OrderQty` <= 3 AND `UnitPriceDiscount` = 0) SELECT 100.0 * (SELECT COUNT(*) FROM qual_orders) / NULLIF((SELECT COUNT(*) FROM total_orders),0) AS percentage;
        - Example incorrect SQL: SELECT CAST(SUM(CASE WHEN OrderQty < 3 AND UnitPriceDiscount = 0 THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(SalesOrderID) FROM SalesOrderDetail
    ii. specific filtering conditions or predicates:
        - Example hint 1: in Middle Atlantic refers to division = 'Middle Atlantic'; female refers to sex = 'Female'; no more than 18 refers to age <= 18
        - Example correct SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.sex = 'Female' AND T1.age <= 18
        - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.sex = 'Female' AND T1.age < 18
        - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.age < 18
        - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division LIKE '%Middle Atlantic%' AND T1.sex = 'Female' AND T1.age < 18
    iii. specific output columns:
        - Example question 1: Please list the full names of all employees.
        - Example hint 1: full name refers to FirstName, LastName
        - Example correct SQL: SELECT FirstName, LastName FROM Employees
        - Example incorrect SQL: SELECT FirstName, LastName, Title FROM Employees
        - Example incorrect SQL: SELECT FirstName FROM Employees
        - Example question 2: Please list the countries on the European Continent that have a population growth of more than 3%.
        - Example hint 2: Country refers to Code
        - Example correct SQL: SELECT T1.Code FROM country AS T1 INNER JOIN encompasses AS T2 ON T1.Code = T2.Country INNER JOIN continent AS T3 ON T3.Name = T2.Continent INNER JOIN population AS T4 ON T4.Country = T1.Code WHERE T3.Name = 'Europe' AND T4.Population_Growth > 0.03
        - Example incorrect SQL: SELECT T1.Name FROM country AS T1 INNER JOIN encompasses AS T2 ON T1.Code = T2.Country INNER JOIN continent AS T3 ON T3.Name = T2.Continent INNER JOIN population AS T4 ON T4.Country = T1.Code WHERE T3.Name = 'Europe' AND T4.Population_Growth > 0.03
    iv. specific output formats:
        - Example question 1: Which repository has the longest amount of processed time of downloading? Indicate whether the solution paths in the repository can be implemented without needs of compilation, Yes or No.
        - Example hint 1: longest amount of processed time refers to max(ProcessedTime); the repository can be implemented without needs of compilation refers to WasCompiled = 1 for all solutions;
        - Example correct SQL: SELECT r.Id AS RepoId, CASE WHEN MIN(CASE WHEN s.WasCompiled = 1 THEN 1 ELSE 0 END) = 1 THEN 'Yes' ELSE 'No' END AS CanRunWithoutCompilation FROM Repo r LEFT JOIN Solution s ON s.RepoId = r.Id WHERE r.ProcessedTime = (SELECT MAX(ProcessedTime) FROM Repo) GROUP BY r.Id;
        - Example incorrect SQL: SELECT DISTINCT T1.id, T2.WasCompiled FROM Repo AS T1 INNER JOIN Solution AS T2 ON T1.Id = T2.RepoId WHERE T1.ProcessedTime = ( SELECT MAX(ProcessedTime) FROM Repo )

Requirement:
1. You can be unsure if you are not confident.
2. Only respond with one of the three labels: "Correct", "Incorrect", or "Unsure".
3. "Correct" means the SQL query answers the question correctly and covers the hint comprehensively without introducing extra unrelated calculation, predicates, or logic.
4. "Incorrect" means the SQL query does not answer the question correctly, or misses any part of the hint, or introduces extra unrelated calculation, predicates, or logic.
5. "Unsure" means you are not confident to determine whether the SQL query is correct or incorrect based on the provided question and hint.

Format:
1. Please thinking thoroughly before you answer.
2. Please wrap your answer with <answer> and </answer> tags. For example, if you think the SQL query is correct, please answer <answer>Correct</answer>.

Question: {question}
Hint: {hint}
SQL Query: {sql_query}"""

reconciliation_template = """You are an expert SQL query reviewer. Given a natural language question, a external knowledge hint, and a SQL query, you task is to determine whether the SQL query answers the question correctly and covers the provided hint comprehensively.

Instructions:
1. The natural language question might be ambiguous or underspecified on its own. The provided hint is intended to clarify or disambiguate the question.
2. Carefully analyze whether the SQL query fully incorporates the information from the hint in order to accurately answer the question.
3. If the SQL query misses any part of the hint, it should be considered incorrect. If the query introduces extra unrelated calculation, predicates, or logic, this is ok because necessary data properties or relationships are not explicitly stated in the hint or question. In such cases, you can ignore the extra parts as long as all aspects of the hint are covered.
4. The provided hint will include following type of information. For each type, the SQL query must address it completely.
    i. computation formulas or specific calculation methods: 
        - Example hint 1: percentage refers to DIVIDE(COUNT(student_id where type = 'TPG' and first_name = 'Ogdon', last_name = 'Zywicki'), COUNT(first_name = 'Ogdon', last_name = 'Zywicki')) * 100
        - Example correct SQL: SELECT CAST(SUM(CASE WHEN T3.type = 'TPG' THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(T1.student_id) FROM RA AS T1 INNER JOIN prof AS T2 ON T1.prof_id = T2.prof_id INNER JOIN student AS T3 ON T1.student_id = T3.student_id WHERE T2.first_name = 'Ogdon' AND T2.last_name = 'Zywicki'
        - Example incorrect SQL: SELECT CAST(SUM(CASE WHEN T3.type = 'TPG' THEN 1 ELSE 0 END) AS REAL) * 100 / CAST(SUM(CASE WHEN T2.first_name = 'Ogdon' AND T2.last_name = 'Zywicki' THEN 1 ELSE 0 END) AS REAL) FROM RA AS T1 INNER JOIN prof AS T2 ON T1.prof_id = T2.prof_id INNER JOIN student AS T3 ON T1.student_id = T3.student_id 
        - Example hint 2: percentage = DIVIDE(count(SalesOrderID(OrderQty<3 & UnitPriceDiscount = 0)), count(SalesOrderID))*100%
        - Example correct SQL: WITH total_orders AS (SELECT DISTINCT `SalesOrderID` FROM `SalesOrderDetail`), qual_orders AS ( SELECT DISTINCT `SalesOrderID` FROM `SalesOrderDetail` WHERE `OrderQty` <= 3 AND `UnitPriceDiscount` = 0) SELECT 100.0 * (SELECT COUNT(*) FROM qual_orders) / NULLIF((SELECT COUNT(*) FROM total_orders),0) AS percentage;
        - Example incorrect SQL: SELECT CAST(SUM(CASE WHEN OrderQty < 3 AND UnitPriceDiscount = 0 THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(SalesOrderID) FROM SalesOrderDetail
    ii. specific filtering conditions or predicates:
        - Example hint 1: in Middle Atlantic refers to division = 'Middle Atlantic'; female refers to sex = 'Female'; no more than 18 refers to age <= 18
        - Example correct SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.sex = 'Female' AND T1.age <= 18
        - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.sex = 'Female' AND T1.age < 18
        - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division = 'Middle Atlantic' AND T1.age < 18
        - Example incorrect SQL: SELECT COUNT(T1.sex) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.division LIKE '%Middle Atlantic%' AND T1.sex = 'Female' AND T1.age < 18
    iii. specific output columns:
        - Example question 1: Please list the full names of all employees.
        - Example hint 1: full name refers to FirstName, LastName
        - Example correct SQL: SELECT FirstName, LastName FROM Employees
        - Example incorrect SQL: SELECT FirstName, LastName, Title FROM Employees
        - Example incorrect SQL: SELECT FirstName FROM Employees
        - Example question 2: Please list the countries on the European Continent that have a population growth of more than 3%.
        - Example hint 2: Country refers to Code
        - Example correct SQL: SELECT T1.Code FROM country AS T1 INNER JOIN encompasses AS T2 ON T1.Code = T2.Country INNER JOIN continent AS T3 ON T3.Name = T2.Continent INNER JOIN population AS T4 ON T4.Country = T1.Code WHERE T3.Name = 'Europe' AND T4.Population_Growth > 0.03
        - Example incorrect SQL: SELECT T1.Name FROM country AS T1 INNER JOIN encompasses AS T2 ON T1.Code = T2.Country INNER JOIN continent AS T3 ON T3.Name = T2.Continent INNER JOIN population AS T4 ON T4.Country = T1.Code WHERE T3.Name = 'Europe' AND T4.Population_Growth > 0.03
    iv. specific output formats:
        - Example question 1: Which repository has the longest amount of processed time of downloading? Indicate whether the solution paths in the repository can be implemented without needs of compilation, Yes or No.
        - Example hint 1: longest amount of processed time refers to max(ProcessedTime); the repository can be implemented without needs of compilation refers to WasCompiled = 1 for all solutions;
        - Example correct SQL: SELECT r.Id AS RepoId, CASE WHEN MIN(CASE WHEN s.WasCompiled = 1 THEN 1 ELSE 0 END) = 1 THEN 'Yes' ELSE 'No' END AS CanRunWithoutCompilation FROM Repo r LEFT JOIN Solution s ON s.RepoId = r.Id WHERE r.ProcessedTime = (SELECT MAX(ProcessedTime) FROM Repo) GROUP BY r.Id;
        - Example incorrect SQL: SELECT DISTINCT T1.id, T2.WasCompiled FROM Repo AS T1 INNER JOIN Solution AS T2 ON T1.Id = T2.RepoId WHERE T1.ProcessedTime = ( SELECT MAX(ProcessedTime) FROM Repo )

Requirement:
1. You can be unsure if you are not confident.
2. Only respond with one of the three labels: "Correct", "Incorrect", or "Unsure".
3. "Correct" means the SQL query answers the question correctly and covers the hint comprehensively.
4. "Incorrect" means the SQL query does not answer the question correctly, or misses any part of the hint.
5. "Unsure" means you are not confident to determine whether the SQL query is correct or incorrect based on the provided question and hint.

Format:
1. Please thinking thoroughly before you answer.
2. Please wrap your answer with <answer> and </answer> tags. For example, if you think the SQL query is correct, please answer <answer>Correct</answer>.

Question: {question}
Hint: {hint}
SQL Query: {sql_query}"""