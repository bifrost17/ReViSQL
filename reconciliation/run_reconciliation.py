from reconciliation import determine_one_generation_defensive
import json
from tqdm import tqdm
import argparse
import os
import dotenv

dotenv.load_dotenv()

def check_query_match(query, candidates):
    for i, candidate in enumerate(candidates):
        candidate_no_whitespace = candidate.replace(" ", "").replace("\n", "").lower()
        query_no_whitespace = query.replace(" ", "").replace("\n", "").lower()
        if candidate_no_whitespace == query_no_whitespace:
            return i
    return -1

parser = argparse.ArgumentParser()
parser.add_argument("--graded_result_path", type=str, required=True, help="Path to the graded results json file.")
parser.add_argument("--output_path", type=str, required=True, help="Path to save the model decisions jsonl file.")
parser.add_argument("--max_retries", type=int, default=3, help="Maximum number of retries for model decision.")
parser.add_argument("--dry_run", action="store_true", help="If set, the script will only print the questions and candidates without making model calls.")
parser.add_argument("--model_name", type=str, default="claude-opus-4-6", help="Model name to use for evaluation.")
parser.add_argument("--include_all_errors", action="store_true", help="If set, the script will include all error cases instead of just those without any correct generations.")
parser.add_argument("--data_file", type=str, default="./data/arcwise_full_augmented.json", help="Path to the input data file containing questions and evidence.")
args = parser.parse_args()

raw_response_path = args.output_path.replace(".jsonl", "_raw_responses")
os.makedirs(raw_response_path, exist_ok=True)

with open(args.data_file) as f:
    arcwise_data = json.load(f)

finished_qids = set()
if os.path.exists(args.output_path):
    with open(args.output_path) as f:
        for line in f:
            data = json.loads(line)
            finished_qids.add(str(data["question_id"]))
    print(f"Found {len(finished_qids)} finished question IDs in the output file. These will be skipped.")
    
n_model_calls = 0
for item in tqdm(arcwise_data):
    question_id = str(item['question_id'])
    evidence = item['evidence']
    question = item['question']
    
    if "sql_corrected" in question_id or "original" in question_id:
        # print(f"Skipping question_id: {question_id} as it belongs to sql_corrected or sql_only category.")
        continue
    
    if question_id in finished_qids:
        print(f"Skipping question_id: {question_id} as it is already processed.")
        continue
    
    if not os.path.exists(f"{args.graded_result_path}/{question_id}.json"):
        print(f"Missing results for question_id: {question_id}")
        continue
    
    with open(f"{args.graded_result_path}/{question_id}.json") as f:
        results = json.load(f)
    
    if "matches_gt" not in results:
        print(f"Missing results for question_id: {question_id}")
        continue
    
    if not args.include_all_errors and len(results["matches_gt"]) == 0:
        print(f"No correct results for question_id: {question_id}")
        continue

    if len(results["others"]) == 0:
        if len(results["matches_gt"]) != 0:
            with open(f"{args.output_path}", "a+") as f:
                f.write(json.dumps({
                    "question_id": question_id,
                    "decisions": [False],
                    "candidate_names": ["matches_gt"],
                    "candidate_popularity": [len(results["matches_gt"])]
                }) + "\n")
        continue
    
    if len(results["matches_gt"]) > 0:
        query_candidates = [[results["matches_gt"][0]]]
        candidate_names = ["matches_gt"]
        candidate_popularity = [[1]]
        for query_gen in results["matches_gt"][1:]:
            candidate_id = check_query_match(query_gen, query_candidates[0])
            if candidate_id != -1:
                candidate_popularity[0][candidate_id] += 1
            else:
                candidate_popularity[0].append(1)
                query_candidates[0].append(query_gen)
    else:
        query_candidates = []
        candidate_names = []
        candidate_popularity = []

    for i, other_group in enumerate(results["others"]):
        candidate_names.append(f"other_group_{i}")
        candidate_popularity.append([1])
        query_candidates.append([other_group[0]])
        for query_gen in other_group[1:]:
            candidate_id = check_query_match(query_gen, query_candidates[-1])
            if candidate_id != -1:
                candidate_popularity[-1][candidate_id] += 1
            else:
                candidate_popularity[-1].append(1)
                query_candidates[-1].append(query_gen)
                
    n_model_calls += len(query_candidates)

    if args.dry_run:
        continue

    decisions = []
    raw_responses = []
    for candidate_group in query_candidates:
        # for query_gen in candidate_group:
        #     model_decision = None
        #     retries = 0
        #     while str(model_decision).lower() not in ["correct", "incorrect", "unsure"]:
        #         retries += 1
        #         model_decision = determine_one_generation(question, evidence, query_gen)
        #         if retries >= args.max_retries:
        #             model_decision = "Unsure"
        #             break
        #     decisions.append(model_decision)
        query_str = ""
        for i, query_gen in enumerate(candidate_group):
            query_gen = query_gen.replace("\n", " ")
            query_str += f"Query {i}: {query_gen}\n"
        model_decision = None
        retries = 0
        while str(model_decision).lower() not in ["correct", "incorrect", "unsure"]:
            retries += 1
            model_decision, raw_response, raw_prompt = determine_one_generation_defensive(question, evidence, query_str, model_name=args.model_name)
            if retries >= args.max_retries:
                model_decision = "Unsure"
                break
        decisions.append(model_decision)
        raw_responses.append({
            "raw_response": raw_response,
            "raw_prompt": raw_prompt
        })

    with open(f"{args.output_path}", "a+") as f:
        f.write(json.dumps({
            "question_id": question_id,
            "decisions": decisions,
            "candidate_names": candidate_names,
            "candidate_popularity": candidate_popularity
        }) + "\n")
    
    with open(f"{raw_response_path}/{question_id}.json", "a+") as f:
        json.dump(raw_responses, f, indent=4)

print(f"Total model calls made: {n_model_calls}")