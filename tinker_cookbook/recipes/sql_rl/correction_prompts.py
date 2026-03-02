from tinker_cookbook.renderers import Message

question_evidence_equivalence_prompt = """Reference question: {reference_question} ({reference_evidence})
Revised question: {revised_question} ({revised_evidence})

Decide whether the two questions are semantically equivalent.
They are equivalent only if they would necessarily produce the same correct answer under the same database/context (i.e., each question implies the other; the revised question neither strengthens nor weakens the reference).

Return "Yes" ONLY if they must have the same correct answer (same constraints and same output requirements).
Return "No" if:
- the revised question adds/removes any constraint (time, location, entity, condition, threshold, etc.), OR
- they differ in aggregation (COUNT/SUM/AVG/MIN/MAX), DISTINCT/unique/"number of different", OR
- they differ in grouping/granularity ("by/per each"), OR
- they differ in ordering, top-k/limit, superlatives, ties, OR
- they differ in negation/exceptions ("not", "except", "without"), OR
- they request different outputs (different attributes/columns), OR
- either question is ambiguous/underspecified, OR
- you are not completely sure.

Output EXACTLY one line:
Yes
or
No
"""

system_prompt = """Role:
You are an expert data curator for text-to-SQL training data.

Goal:
Given (1) a SQLite database schema, (2) an external knowledge snippet, (3) a natural-language question, and (4) a SQL query, you will:
- Diagnose whether each of {{external knowledge, question, SQL}} is correct.
- Produce corrected versions when needed.
The end result should be a clean, internally consistent triple (question, external knowledge, SQL) that is answerable from the given schema.

Input Format:
Database Engine:
SQLite

Database Schema:
<<db_details>>
(Contains tables, columns, keys, and relationships.)

External Knowledge:
<<external_knowledge>>

Question:
<<question>>

SQL query:
<<sql_query>>

Definitions (be strict):
- "Correct external knowledge" means:
  - It is NOT ambiguous, self-contradictory, or logically wrong.
  - It is consistent with the schema (does not mention non-existent tables/columns).
  - It does not need to be comprehensive; it may be empty. It should only include verifiable, relevant constraints/facts.
- "Correct question" means:
  - It is unambiguous and logically well-defined.
  - It specifies the intended output clearly (what to return, grouping/ordering/top-k if required).
  - It is consistent with the schema and external knowledge.
- "Correct SQL" means:
  - Valid SQLite syntax; executable without errors.
  - Uses only tables/columns in the schema.
  - Returns exactly the information requested by the (corrected) question, respecting external knowledge constraints.
  - No missing information and no extra columns/rows beyond what the question asks.

High-level policy:
1) Prefer minimal edits:
   - If something is already correct, do not rewrite it.
   - When revising, change only what is necessary to remove ambiguity/incorrectness.
2) Priority when there is disagreement:
   - If SQL disagrees with the question, PREFER revising the SQL to match the question (and external knowledge), rather than revising the question.
   - Revise the question ONLY if it is ambiguous, logically incorrect, contradicts itself, or cannot be answered from the schema even with a corrected SQL.
3) Handling contradictions involving external knowledge:
   - If external knowledge contradicts the question, treat that as an error.
   - Prefer correcting external knowledge first IF it is ambiguous/incorrect/misleading.
   - If external knowledge is irrelevant to the question, it may be kept if correct; otherwise revise it to be empty/neutral to avoid misleading constraints.
4) Ambiguity handling:
   - If multiple interpretations of the question lead to different SQL/results, the question is ambiguous. You must revise the question to be specific.
   - If external knowledge has multiple incompatible interpretations, you must revise it or remove ambiguous parts.
5) SQL requirements:
   - Use correct JOIN paths using schema foreign keys when applicable.
   - Match aggregation semantics to the question (COUNT vs COUNT(DISTINCT), GROUP BY, HAVING vs WHERE).
   - If asked for ordering/top-k/most/least, include ORDER BY + LIMIT as needed.
   - Return only what the question asks for (no extra columns; correct granularity).
   - Do not invent filters not present in question/external knowledge.
6) Do NOT hallucinate:
   - Do not invent tables/columns not in the schema.
   - Do not assume values exist unless verified via SQL tool.

Tool use:
- You may call the SQL tool to validate syntax, test assumptions, or compare results.
- Call the SQL tool only when it materially improves correctness (e.g., to confirm columns, verify joins, validate that a filter makes sense, check result shape).
- You can only call the SQL tool once per turn.
- The returned dataframe may be truncated to 50 rows.
- The format of calling the SQL tool is: {sql_tool_calling}

Process discipline:
- Internally reason step-by-step, but do NOT output long chain-of-thought.
- If helpful, you may include brief, high-level notes in your own planning, but final outputs must follow the submit tool schema.

Action rules:
- Either:
  (A) Call the SQL tool with exactly one query, OR
  (B) Call the submit tool with the final decisions/revisions.
- Do not request SQL tool execution and submit a final report in the same response.

What to submit:
Use the submit tool with:
- external_knowledge_correctness: "True" if external knowledge needs no change, else "False"
- external_knowledge_revision: corrected external knowledge text, or "None" if no change
- question_correctness: "True" if question needs no change, else "False"
- question_revision: corrected question text, or "None" if no change
- SQL_correctness: "True" if SQL needs no change, else "False"
- SQL_revision: corrected SQL, or "None" if no change
The format of calling the submit tool is: 
{submit_tool_calling}

Important:
- If you revise the question or external knowledge, the SQL must match the revised versions.
- If everything is already consistent and correct, mark all correctness fields True and all revisions None.
"""

qwen_sql_tool_calling = """<function_call>{"name":"sql","args":{"query":"YOUR_SQL_QUERY_HERE"}}</function_call>"""

qwen_submit_tool_calling = """<function_call>{"name":"submit","args":{
  "external_knowledge_correctness": True or False,
  "external_knowledge_revision":"your correction or None",
  "question_correctness": True or False,
  "question_revision":"your correction or None",
  "SQL_correctness": True or False,
  "SQL_revision":"your correction or None"
}}</function_call>"""

qwen_one_shot_prompt = [
    Message(role="user", content="""Database Engine:
SQLite

Database Schema:
CREATE TABLE course (
    `course_id` integer, -- course id. unique id representing the course.
    `name` text, -- name of the course.
    `credit` integer, -- credit of the course. higher means more important.
    `diff` integer, -- difficulty. difficulty of the course. higher --> more difficult. smaller --> less difficult.
    primary key (course_id)
);

CREATE TABLE RA (
    `student_id` integer, -- student id. the id numbe representing each student.
    `capability` integer, -- the capability of student on research. (Evaluated by the professor). higher --> higher research ability / capability.
    `prof_id` integer, -- professor id. professor who advises this student. this value may be repetitive since one professor may advise many students in this semester. if a professor advise > 2 students in this semester, it means this professor's research work is heavy. or: this professor's popularity on research is higher.
    `salary` text, -- the salary of this student. med: average salary. high: higher salary than others. low: lower salary. free: unpaid RA.
    primary key (student_id, prof_id),
    foreign key (prof_id) references prof(prof_id),
    foreign key (student_id) references student(student_id)
);

CREATE TABLE prof (
    `prof_id` integer, -- professor id. unique id for professors.
    `gender` text, -- gender of the professor.
    `first_name` text, -- first name. the first name of the professor.
    `last_name` text, -- last name. the last name of the professor. full name: first name, last name.
    `email` text, -- email of the professor.
    `popularity` integer, -- popularity of the professor. higher --> more popular.
    `teachingability` integer, -- teaching ability. the teaching ability of the professor. higher --> more teaching ability, his / her lectures may have better quality.
    `graduate_from` text, -- graduate from. the school where the professor graduated from.
    primary key (prof_id)
);

CREATE TABLE registration (
    `course_id` integer, -- course id. the id of courses.
    `student_id` integer, -- student id. the id of students.
    `grade` text, -- the grades that the students acquire in this course.  A: excellent -- 4.  B: good -- 3.  C: fair -- 2.  D: poorly pass -- 1.  null or empty: this student fails to pass this course.  gpa of students for this semester = sum (credits x grade) / sum (credits).
    `sat` integer, -- satisfying degree. student satisfaction with the course.
    primary key (course_id, student_id),
    foreign key (course_id) references course(course_id),
    foreign key (student_id) references student(student_id)
);

CREATE TABLE student (
    `student_id` integer, -- student id. the unique id to identify students.
    `f_name` text, -- first name. the first name of the student.
    `l_name` text, -- last name. the last name of the student. full name: f_name, l_name.
    `phone_number` text, -- phone number.
    `email` text, -- email.
    `intelligence` integer, -- intelligence of the student. higher --> more intelligent.
    `gpa` real, -- graduate point average. gpa.
    `type` text, -- type of the student.  TPG: taught postgraduate student(master).  RPG: research postgraduate student (master).  UG: undergraduate student(bachelor). both TPG and RPG are students pursuing a masters degree; UG are students pursuing the bachelor degree.
    primary key (student_id)
);

External Knowledge:
full name of students = f_name, l_name; failed refers to grade IS NULL;

Question:
How many students who have a capability of 2 or 3 failed in any courses?

SQL query:
SELECT COUNT(T1.student_id) FROM RA AS T1 INNER JOIN student AS T2 ON T2.student_id = T1.student_id INNER JOIN registration AS T3 ON T2.student_id = T3.student_id WHERE T1.capability IN (2, 3) AND (T3.grade IS NULL OR T3.grade = '');
"""),
    Message(role="assistant", content="""I will check correctness of (1) external knowledge, (2) question, (3) SQL, and then apply minimal revisions. 

Step 1: Understand intent from the question.
- The question asks: count students with capability in {2,3} who failed in any course.
- Capability exists only in RA table, so the intended students are those appearing in RA (i.e., RA students). The question is ambiguous. I need to rewrite it to "RAs" for disambiguation.

Step 2: Check external knowledge.
- It states: "failed refers to grade IS NULL".
- However, the schema description for registration.grade says: "null or empty: this student fails to pass this course."
- Therefore the external knowledge is incomplete/inconsistent with the schema. For clean data, I should revise it to: failed referst to grade IS NULL OR grade=''.

Step 3: Check the SQL.
- The SQL joins RA, student, registration, and counts COUNT(T1.student_id).
- Problem A (semantics): "failed in any courses" means a student may have multiple failing registrations; counting raw rows will overcount. We need COUNT(DISTINCT student_id).
- Problem B (duplication): RA has primary key (student_id, prof_id), so a student can appear multiple times (multiple advisors). Joining can multiply rows further, reinforcing the need for DISTINCT.

Before finalizing, I will verify whether empty-string grades exist in this DB instance (even though schema suggests it is possible). This helps decide whether the current SQL’s `OR grade = ''` changes results on this instance, but regardless, the cleaned external knowledge should match the schema definition.

I will call the SQL tool to count NULL vs empty-string grades in registration.
<function_call>{"name":"sql","args":{"query":"SELECT SUM(CASE WHEN grade IS NULL THEN 1 ELSE 0 END), SUM(CASE WHEN grade = '' THEN 1 ELSE 0 END) FROM registration;"}}</function_call>"""),
    Message(role="user", content="0\t1\n5\t0"),
    Message(role="assistant", content="""The DB instance has 0 student with grade='', but the schema definition still says empty grade indicates failure. Therefore:
- External knowledge should be revised to include both NULL and empty-string.
- SQL can keep the condition `(grade IS NULL OR grade = '')` for schema-consistency; it will not harm correctness on this instance.

Next, I will verify that the current SQL overcounts relative to DISTINCT student count, to justify the correction clearly.
<function_call>{"name":"sql","args":{"query":"SELECT COUNT(T1.student_id), COUNT(DISTINCT T1.student_id) FROM RA AS T1 INNER JOIN student AS T2 ON T2.student_id = T1.student_id INNER JOIN registration AS T3 ON T2.student_id = T3.student_id WHERE T1.capability IN (2, 3) AND (T3.grade IS NULL OR T3.grade = '');"}}</function_call>"""),
    Message(role="user", content="0\t1\n6\t4"),
    Message(role="assistant", content="""The result shows a difference in student counts, confirming the original SQL overcounts. Therefore SQL must be revised to count DISTINCT students.

Final decisions:
- External knowledge: revise to match schema definition of failure.
- Question: rewrite to "RAs"
- SQL: revise to avoid overcounting and remove unnecessary join.

Now I will submit the corrected triple.
<function_call>{"name":"submit","args":{
  "external_knowledge_correctness": False,
  "external_knowledge_revision":"full name of students = f_name, l_name; failed refers to grade IS NULL OR grade = '';",
  "question_correctness": False,
  "question_revision":"How many RAs who have a capability of 2 or 3 failed in any courses?",
  "SQL_correctness": False,
  "SQL_revision":"SELECT COUNT(DISTINCT T1.student_id) FROM RA AS T1 INNER JOIN student AS T2 ON T2.student_id = T1.student_id INNER JOIN registration AS T3 ON T2.student_id = T3.student_id WHERE T1.capability IN (2, 3) AND (T3.grade IS NULL OR T3.grade = '');"
}}</function_call>""")
]

general_one_shot_prompt = None # todo

kimi_one_shot_prompt = None # todo