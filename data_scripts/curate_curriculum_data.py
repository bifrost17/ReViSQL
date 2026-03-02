from data.prompts import system_prompt, user_prompt
import pandas as pd
import datasets
import json
from copy import deepcopy

def load_data():
    with open("data/bird-plat-2k.json") as f:
        correct_train = json.load(f)

    with open("curriculum_stage_1_questions.json") as f:
        stage_1_questions = json.load(f)
    with open("curriculum_stage_2_questions.json") as f:
        stage_2_questions = json.load(f)
    with open("curriculum_stage_3_questions.json") as f:
        stage_3_questions = json.load(f)
    with open("curriculum_stage_4_questions.json") as f:
        stage_4_questions = json.load(f)

    stage_1_data = []
    stage_2_data = []
    stage_3_data = []
    stage_4_data = []

    for data in correct_train:
        if "SQL" in data and "question" in data:
            if data['question_id'] in stage_1_questions:
                data["split"] = "curriculum_stage_1"
                stage_1_data.append(data)
            elif data['question_id'] in stage_2_questions:
                data["split"] = "curriculum_stage_2"
                stage_2_data.append(data)
            elif data['question_id'] in stage_3_questions:
                data["split"] = "curriculum_stage_3"
                stage_3_data.append(data)
            elif data['question_id'] in stage_4_questions:
                data["split"] = "curriculum_stage_4"
                stage_4_data.append(data)

    stage_1_data = pd.DataFrame(stage_1_data)
    stage_2_data = pd.DataFrame(stage_2_data)
    stage_3_data = pd.DataFrame(stage_3_data)
    stage_4_data = pd.DataFrame(stage_4_data)

    return stage_1_data, stage_2_data, stage_3_data, stage_4_data

def convert_data(data: pd.DataFrame):
    """
    format of the output dataframe:
    - data_source: "clean", "noisy", or "unknown
    - prompt: []
    - question_id: int
    -
    """
    converted_data = []
    for i, d in data.iterrows():
        db_name = d['db_id']
        with open(f"data/ddls/{db_name}.sql", "r", encoding="cp1252") as f:
            schema = f.read()
        converted_d = {
            'data_source': d['split'],
            'prompt': [
                {
                    'content': system_prompt,
                    'role': 'system'
                },
                {
                    'content': user_prompt.format(
                        schema=schema,
                        external_knowledge=d['evidence'],
                        question=d['question'],),
                    'role': 'user'
                }
            ],
            'env_class': 'text2sql',
            'db_id': d['db_id'],
            'data': 'bird-verified',
            'reward_spec': {
                'ground_truth': d['SQL'],
                'method': d['grading_method'] if 'grading_method' in d else 'multiset'
            },
            'extra_info': {'index': 0, 'split': 'dummy'},
            'question_id': d['question_id']
        }
        converted_data.append(converted_d)
    return pd.DataFrame(converted_data)

def convert_data_no_ek(data: pd.DataFrame):
    """
    Convert the DataFrame to the desired format without external knowledge.
    """
    converted_data = []
    for i, d in data.iterrows():
        db_name = d['db_id']
        with open(f"data/ddls/{db_name}.sql", "r", encoding="cp1252") as f:
            schema = f.read()
        converted_d = {
            'data_source': d['split'],
            'prompt': [
                {
                    'content': system_prompt,
                    'role': 'system'
                },
                {
                    'content': user_prompt.format(
                        schema=schema,
                        external_knowledge="",
                        question=d['question'],),
                    'role': 'user'
                }
            ],
            'env_class': 'text2sql',
            'db_id': d['db_id'],
            'data': 'bird-verified',
            'reward_spec': {
                'ground_truth': d['SQL'],
                'method': d['grading_method'] if 'grading_method' in d else 'multiset'
            },
            'extra_info': {'index': 0, 'split': 'dummy'},
            'question_id': d['question_id']
        }
        converted_data.append(converted_d)
    return pd.DataFrame(converted_data)

def curate_sanity_check_dataset():
    stage_1_data, stage_2_data, stage_3_data, stage_4_data = load_data()
    stage_1_data['split'] = 'curriculum_stage_1'
    stage_2_data['split'] = 'curriculum_stage_2'
    stage_3_data['split'] = 'curriculum_stage_3'
    stage_4_data['split'] = 'curriculum_stage_4'

    stage_1_data = convert_data(stage_1_data)
    stage_2_data = convert_data(stage_2_data)
    stage_3_data = convert_data(stage_3_data)
    stage_4_data = convert_data(stage_4_data)

    stage_1_data.to_json("data/stage_1.json", orient="records", lines=True, indent=4)
    stage_2_data.to_json("data/stage_2.json", orient="records", lines=True, indent=4)
    stage_3_data.to_json("data/stage_3.json", orient="records", lines=True, indent=4)
    stage_4_data.to_json("data/stage_4.json", orient="records", lines=True, indent=4)

    stage_1_dataset = datasets.Dataset.from_pandas(stage_1_data)
    stage_2_dataset = datasets.Dataset.from_pandas(stage_2_data)
    stage_3_dataset = datasets.Dataset.from_pandas(stage_3_data)
    stage_4_dataset = datasets.Dataset.from_pandas(stage_4_data)

    stage_1_dataset.to_parquet("data/stage_1.parquet")
    stage_2_dataset.to_parquet("data/stage_2.parquet")
    stage_3_dataset.to_parquet("data/stage_3.parquet")
    stage_4_dataset.to_parquet("data/stage_4.parquet")


if __name__ == "__main__":
    curate_sanity_check_dataset()
