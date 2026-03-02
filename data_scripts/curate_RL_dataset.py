from data.prompts import system_prompt, user_prompt
import pandas as pd
import datasets
import json
from copy import deepcopy

def load_data():
    with open("data/arcwise_plat_sql.json") as f:
        arcwise_minidev = json.load(f)

    with open("data/bird-plat-2.5k-v1.json") as f:
        correct_train = json.load(f)

    with open("data/arcwise_plat_full.json") as f:
        correct_dev = json.load(f)

    train_data = []
    test_data = []
    qids = set()

    for data in arcwise_minidev:
        data["split"] = "arcwise-plat"
        test_data.append(data)
        qids.add(data['question_id'])

    for data in correct_dev:
        if data['question_id'] in qids:
            continue
        data["split"] = "correct_dev"
        test_data.append(data)

    for data in correct_train:
        assert 'SQL' in data and 'evidence' in data and 'question' in data, f"Missing fields in question_id {data['question_id']}"
        data["split"] = "train"
        train_data.append(data)

    return pd.DataFrame(train_data), pd.DataFrame(test_data)

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

def curate_sanity_check_dataset():
    train_data, test_data = load_data()
    train_data = convert_data(train_data)
    test_data = convert_data(test_data)

    train_data.to_json("data/train.json", orient="records", lines=True, indent=4)
    test_data.to_json("data/test.json", orient="records", lines=True, indent=4)
    # new_dev_data.to_json("data/new_dev.json", orient="records", lines=True, indent=4)

    train_dataset = datasets.Dataset.from_pandas(train_data)
    test_dataset = datasets.Dataset.from_pandas(test_data)
    # new_dev_dataset = datasets.Dataset.from_pandas(new_dev_data)

    train_dataset.to_parquet("data/train.parquet")
    test_dataset.to_parquet("data/test.parquet")
    # new_dev_dataset.to_parquet("data/new_dev.parquet")


if __name__ == "__main__":
    curate_sanity_check_dataset()
