from reconciliation import determine_one_generation_detailed
import json
import multiprocessing

with open("../data/arcwise_plat_sql.json") as f:
    arcwise_data = json.load(f)

n_correct = 0

def run_one_data(item):
    question_id = item['question_id']
    evidence = item['evidence']
    question = item['question']
    
    with open(f"../dumps/qwen3_cispo-maxturns-7-evals/arcwise_plat_{question_id}_grouped_results.json") as f:
        results = json.load(f)
    
    if "matches_arcwise_gt" not in results:
        print(f"Missing results for question_id: {question_id}")
        return
    
    if len(results["matches_arcwise_plat_gt"]) == 0:
        print(f"No correct results for question_id: {question_id}")
        return
    
    with open(f"model_decisions_query_detailed_cispo.jsonl", "r") as f:
        existing_records = [json.loads(line) for line in f.readlines()]
    for record in existing_records:
        if record["question_id"] == question_id:
            print(f"Already processed question_id: {question_id}")
            return

    if len(results["matches_arcwise_plat_gt"]) == len(results["matches_arcwise_gt"]) and len(results["others"]) == 0:
        print(f"Question ID: {question_id}, Correct so far: {n_correct}/{len(arcwise_data)}")
        with open(f"model_decisions_query_detailed_cispo.jsonl", "a+") as f:
            f.write(json.dumps({
                "question_id": question_id,
                "decisions": [False],
                "candidate_names": ["arcwise_plat_gt"],
                "candidate_popularity": [len(results["matches_arcwise_plat_gt"])]
            }) + "\n")
        return

    candidate_popularity = [len(results["matches_arcwise_plat_gt"])]
    group_1_queries = [list(v.values())[0] for v in results["matches_arcwise_plat_gt"]]
    query_candidates = [list(set(group_1_queries))]
    candidate_group_popularity = [[group_1_queries.count(q) for q in query_candidates[0]]]
    candidate_names = ["arcwise_plat_gt"]
    if len(results["matches_arcwise_gt"]) != len(results["matches_arcwise_plat_gt"]) and len(results["matches_arcwise_gt"]) > 0:
        candidate_popularity.append(len(results["matches_arcwise_gt"]))
        group_queries = [list(v.values())[0] for v in results["matches_arcwise_gt"]]
        query_candidates.append(list(set(group_queries)))
        candidate_group_popularity.append([group_queries.count(q) for q in query_candidates[-1]])
        candidate_names.append("arcwise_gt")
    for i, other_group in enumerate(results["others"]):
        candidate_popularity.append(len(other_group))
        group_queries = list(other_group.values())
        query_candidates.append(list(set(group_queries)))
        candidate_group_popularity.append([group_queries.count(q) for q in query_candidates[-1]])
        candidate_names.append(f"incorrect_{i}")

    decisions = []
    
    for candidate_id, query_candidate in enumerate(query_candidates):
        group_decision = []
        for query_id, query in enumerate(query_candidate):
            model_decision = None
            retries = 0
            while str(model_decision).lower() not in ["correct", "incorrect", "unsure"]:
                retries += 1
                model_decision, raw_response = determine_one_generation_detailed(question, evidence, query)
                if retries >= 3:
                    model_decision = "Unsure"
                    break
            with open(f"reconciliation_detailed_cispo_7/{question_id}_candidate_{candidate_id}_query_{query_id}.json", "w") as f:
                json.dump({
                    "question": question,
                    "evidence": evidence,
                    "sql_query": query,
                    "model_decision": model_decision,
                    "raw_response": raw_response
                }, f, indent=4)
            group_decision.append(model_decision)
        decisions.append(group_decision)

    with open(f"model_decisions_query_detailed_cispo.jsonl", "a+") as f:
        f.write(json.dumps({
            "question_id": question_id,
            "decisions": decisions,
            "candidate_names": candidate_names,
            "candidate_popularity": candidate_popularity,
            "candidate_group_popularity": candidate_group_popularity
        }) + "\n")

num_process = 16
with multiprocessing.Pool(num_process) as pool:
    pool.map(run_one_data, arcwise_data)