import json
import pandas as pd
import asyncio
import chz
import tinker
from tinker import ModelInput
from tinker_cookbook.completers import (
    StopCondition,
)
from tinker_cookbook.renderers import Message, Renderer, get_renderer, ToolCall
from tinker_cookbook.rl.types import (
    Action,
    Env,
    EnvGroupBuilder,
    RLDataset,
    RLDatasetBuilder,
    StepResult
)
from tinker_cookbook.tokenizer_utils import get_tokenizer
from tinker_cookbook.recipes.sql_rl.sql_utils import verify_format_and_extract, execute_sql_wrapper_single
from tinker_cookbook.recipes.sql_rl.grader import grade
from tinker_cookbook import renderers
from tinker_cookbook.rl.problem_env import ProblemGroupBuilder
from tinker_cookbook.recipes.sql_rl.correction_prompts import system_prompt, question_evidence_equivalence_prompt, qwen_one_shot_prompt, qwen_sql_tool_calling, qwen_submit_tool_calling
from tinker_cookbook.model_info import get_recommended_renderer_name
from datasets import load_dataset, Dataset, concatenate_datasets
from typing import Literal, cast, Tuple, Any
from functools import partial
import math
import re
import logging
from typing import List
from copy import deepcopy


logger = logging.getLogger(__name__)

class SQLCorrectionEnv(Env):
    def __init__(self, question_id: str, question: str, ground_truth: str, 
                 renderer: Renderer, db_file, timeout, 
                 reward_client: tinker.SamplingClient, reward_renderer: Renderer,
                 dump_path: str | None = None, use_convo_prefix: bool = True, 
                 max_output_tokens_per_turn: int = 3072,
                 max_input_tokens: int = 32768, model_name: str = "qwen", 
                 max_turns: int = 5):
        
        self.renderer: Renderer = renderer
        self.turns: list[Message] = []
        self.ground_truth: str = ground_truth
        self.db_file = db_file
        self.timeout = timeout
        self.num_turn = 0
        self.question = question
        self.question_id = question_id
        self.dump_path = dump_path
        self.use_convo_prefix = use_convo_prefix
        self.max_output_tokens_per_turn = max_output_tokens_per_turn
        self.max_input_tokens = max_input_tokens
        self.model_name = model_name
        self.max_turns = max_turns
        self.reward_client = reward_client
        self.reward_renderer = reward_renderer

        if "Qwen3" in self.model_name:
            self.sql_tool_calling = qwen_sql_tool_calling
            self.submit_tool_calling = qwen_submit_tool_calling
            self.convo_prefix = qwen_one_shot_prompt
        elif "Kimi" in self.model_name:
            raise NotImplementedError("One-shot prompt has not been supported for Kimi models yet.")
        else:
            raise NotImplementedError("One-shot prompt has not been supported for general models yet.")

    @property
    def stop_condition(self) -> StopCondition:
        return self.renderer.get_stop_sequences()

    @property
    def _obs(self) -> ModelInput:
        """Get the observation for the player in tokenized form"""
        system_prompt_formatted = system_prompt.format(
            sql_tool_calling=self.sql_tool_calling,
            submit_tool_calling=self.submit_tool_calling)

        if self.use_convo_prefix:
            convo = [Message(role="system", content=system_prompt_formatted)] + self.convo_prefix + [Message(role="assistant", content=self.question)] + self.turns
        elif not self.use_convo_prefix:
            convo = [Message(role="system", content=system_prompt_formatted), Message(role="assistant", content=self.question)] + self.turns

        return self.renderer.build_generation_prompt(convo)

    async def initial_observation(self) -> tuple[ModelInput, StopCondition]:
        return self._obs, self.stop_condition

    def _parse_action_general(self, action: str) -> Tuple[str|None, List[dict]|None, bool]:
        raise NotImplementedError("General parsing is handled in _get_user_turn directly.")

    def _parse_action_qwen(self, action: str) -> Tuple[str|None, List[dict]|None, bool]:
        matches = re.findall(r"<function_call>(.*?)</function_call>", action, re.DOTALL)
        tool_input = matches[-1] if matches else None
        tool_calls = []
        if tool_input is None:
            return f"No function call found in action. You must output a function call to use the sql tool or submit your final report.", None, False
        try:
            json_error = None
            eval_error = None

            try:
                tool_input_dict = json.loads(tool_input)
            except Exception as e:
                json_error = str(e)

            if json_error is not None:
                try:
                    tool_input_dict = eval(tool_input)
                except Exception as e:
                    eval_error = str(e)

            if json_error is not None and eval_error is not None:
                raise Exception(json_error)

            if tool_input_dict["name"] == "submit":
                tool_calls = [tool_input_dict]
                return None, tool_calls, True
            elif tool_input_dict["name"] == "sql":
                tool_calls.append(tool_input_dict)
                
        except Exception as e:
            # logging.info(f"got malformed function call: {tool_input}")
            return f"Error in parsing function call: {e}", None, False
        return None, tool_calls, False
        
    def _parse_tool_calls_qwen(self, tool_calls: List[ToolCall]) -> Tuple[str|None, List[dict]|None, bool]:
        args = tool_calls[-1].function.arguments
        name = tool_calls[-1].function.name
        try:
            json_error = None
            eval_error = None
            try:
                tool_input_dict = json.loads(args)
            except Exception as e:
                json_error = str(e)
            if json_error is not None:
                try:
                    tool_input_dict = eval(args)
                except Exception as e:
                    eval_error = str(e)
            if json_error is not None and eval_error is not None:
                raise Exception(json_error + "; " + eval_error)
            if name == "submit":
                return None, [{"name": "submit", "args": tool_input_dict}], True
            elif name == "sql":
                return None, [{"name": "sql", "args": tool_input_dict}], False
        except Exception as e:
            return f"Error in parsing function call: {e}", None, False

    def _parse_action_kimi(self, tool_calls: List[ToolCall] = []) -> Tuple[str|None, List[dict]|None, bool]:
        raise NotImplementedError("Kimi parsing is handled in _get_user_turn directly.")

    def _parse_action(self, action: str, tool_calls: List[ToolCall] = []) -> Tuple[str|None, List[dict]|None, bool]:
        if "Qwen3" in self.model_name:
            if len(tool_calls) > 0:
                return self._parse_tool_calls_qwen(tool_calls)
            else:
                return self._parse_action_qwen(action)
        elif "Kimi" in self.model_name:
            return self._parse_action_kimi(tool_calls)
        else:
            return self._parse_action_general(action)
        
    def _verify_format_and_extract_report(self, report: dict):
        if 'args' not in report or not isinstance(report['args'], dict):
            return f"Missing key in report: args", False
        
        required_keys = [
            "external_knowledge_correctness", "external_knowledge_revision",
            "question_correctness", "question_revision",
            "SQL_correctness", "SQL_revision"
        ]
        for key in required_keys:
            if key not in report["args"]:
                return f"Missing key in report: {key}", None
        for key in required_keys:
            if key.endswith("_correctness"):
                if report["args"][key] not in ["True", "False", True, False]:
                    return f"Invalid value for {key}: {report['args'][key]}. Must be True or False.", None
                report["args"][key] = True if report["args"][key] in ['True', True] else False
            elif key.endswith("_revision"):
                if not (isinstance(report["args"][key], str) or report["args"][key] is None):
                    return f"Invalid value for {key}: {report['args'][key]}. Must be a string or None.", None
        return None, report["args"]
    
    def _verify_format_and_extract_sql(self, sql_tool: dict):
        if 'args' not in sql_tool or not isinstance(sql_tool['args'], dict):
            return f"Missing key in sql tool call: args", None

        if "query" not in sql_tool['args']:
            return f"Missing 'query' in sql tool call.", None
        return None, sql_tool['args']['query']
    
    async def _judge_semantic_equivalence(self, reference_question, reference_evidence, generated_question, generated_evidence, max_retry=5):
        # logging.info("-"*100)
        prompt = question_evidence_equivalence_prompt.format(
            reference_question=reference_question,
            reference_evidence=reference_evidence,
            revised_question=generated_question,
            revised_evidence=generated_evidence
        )
        # logging.info(f"Prompt for equivalence judging:\n{prompt}")
        messages = [Message(role="user", content=prompt)]
        for _ in range(max_retry):
            model_input = self.reward_renderer.build_generation_prompt(
                messages
            )
            response = await self.reward_client.sample_async(
                prompt=model_input, num_samples=1, sampling_params=tinker.types.SamplingParams(
                    max_tokens=10,
                    temperature=0.7,
                    top_p=0.95,
                    stop=self.reward_renderer.get_stop_sequences(),
                )
            )
            response_message, _ = self.reward_renderer.parse_response(response.sequences[0].tokens)
            # logging.info(f"Model response for equivalence judging: {response_message['content']}")
            if response_message['content'].strip().lower() == 'yes':
                # logging.info("Equivalence judged to True")
                return True
            elif response_message['content'].strip().lower() == 'no':
                # logging.info("Equivalence judged to False")
                return False
            else:
                messages += [
                    response_message,
                    Message(role="user", content="Please answer with either 'Yes' or 'No' only. Do not provide any additional explanation.")
                ]
                # logging.info("try again ...")
        # logging.info('-'*100)
        return False
    
    async def get_reward(self, generation, ground_truth) -> float:
        # compute reward based on the report and ground truth
        reward = 0
        
        assert isinstance(ground_truth["question_correctness"], bool)
        assert isinstance(ground_truth["external_knowledge_correctness"], bool)
        assert isinstance(generation["question_correctness"], bool)
        
        if ground_truth["question_correctness"] == generation["question_correctness"]:
            # logging.info("reward+0.5 for correct question checking")
            reward += 0.5
        if ground_truth["external_knowledge_correctness"] == generation["external_knowledge_correctness"]:
            # logging.info("reward+0.5 for correct evidence checking")
            reward += 0.5
        if (generation["question_correctness"] == False or generation["external_knowledge_correctness"] == False) and (ground_truth["question_correctness"] == False or ground_truth["external_knowledge_correctness"] == False):
            # call model to judge semantic equivalence
            if await self._judge_semantic_equivalence(
                ground_truth["question_revision"],
                ground_truth["external_knowledge_revision"],
                generation["question_revision"] if not generation["question_correctness"] else ground_truth["original_question"],
                generation["external_knowledge_revision"] if not generation["external_knowledge_correctness"] else ground_truth["original_external_knowledge"]
            ):
                # logging.info("reward+0.5 for correct question/evidence correction")
                reward += 0.5
        elif ground_truth["question_correctness"] == True and ground_truth["external_knowledge_correctness"] == True:
            # logging.info("reward+0.5 for default question/evidence correction")
            # default to 0.5 if none of them needs correction
            reward += 0.5
        
        if ground_truth["SQL_correctness"] == generation["SQL_correctness"]:
            # logging.info("reward+0.5 for correct SQL checking")
            reward += 0.5
            if ground_truth["SQL_correctness"] == False and generation["SQL_revision"] is not None and generation["SQL_revision"] != "None":
                pred_result, pred_error = await execute_sql_wrapper_single(self.db_file, generation["SQL_revision"], self.timeout)
                gt_result, gt_error = await execute_sql_wrapper_single(self.db_file, ground_truth["SQL_revision"], self.timeout)
                if pred_result is not None and gt_result is not None:
                    if grade(gt_result, pred_result, 
                             ground_truth["grading_method"] if ground_truth["grading_method"] != 'multiset' else 'set')[0]:
                        # logging.info("reward+0.5 for correct SQL revision")
                        reward += 1
            elif ground_truth["SQL_correctness"] == True:
                # logging.info("reward+0.5 for default question/evidence correction")
                # default to 1 if the SQL does not need correction
                reward += 1
        
        reward = reward / 3 # normalize to [0, 1]
        
        return reward
        

    async def _get_user_turn(self, action_text: str, tool_calls: List[ToolCall] = []) -> tuple[List[Message]|None, float, bool]:
        error, parsed_action, is_final = self._parse_action(action_text, tool_calls)
        # logging.info("="*100)
        # logging.info(f"Raw model action: {action_text}")
        # logging.info(f"Parsing model actions:\nError: {error}\nActions: {parsed_action}\nis_final: {is_final}")
        if error is not None:
            return [Message(role="user", content=f"{error}\nYou have {self.max_turns - self.num_turn} turns left to complete the task.")], 0.0, False
        assert parsed_action is not None
        if is_final:
            # final submission
            error, report = self._verify_format_and_extract_report(parsed_action[0])
            if error is not None:
                return [Message(role="user", content=f"{error}\nYou have {self.max_turns - self.num_turn} turns left to complete the task.")], -1.0, True
            reward = await self.get_reward(report, self.ground_truth)
            logging.info(f"Report submission for question {self.question_id} (reward={reward}): {report}")
            return None, reward, True
        else:
            if len(parsed_action) > 1:
                return [Message(role="user", content=f"You can only call one SQL tool at a time. Please revise your action.\nYou have {self.max_turns - self.num_turn} turns left to complete the task.")], 0.0, False
            error, query = self._verify_format_and_extract_sql(parsed_action[0])
            if error is not None:
                return [Message(role="user", content=f"{error}\nYou have {self.max_turns - self.num_turn} turns left to complete the task.")], 0.0, False
            results, error = await execute_sql_wrapper_single(self.db_file, query, self.timeout)
            if results is None:
                return [Message(role="user", content=f"{error}\nYou have {self.max_turns - self.num_turn} turns left to complete the task.")], 0.0, False
            else:
                df = pd.DataFrame(results)
                res = df.to_string(index=False)
                if len(df) > 50:
                    # just truncate
                    truncated_df = df.head(50)
                    res = "Truncated to 50 lines since returned response too long: " + truncated_df.to_string(
                        index=False
                    )  # or index=True if you want row numbers
                else:
                    res = "SQL execution results: " + res
                # print(f"SQL output: {res}")
                response = f"{res}\nYou have {self.max_turns - self.num_turn} turns left to complete the task."
                return [Message(role="user", content=response)], 0.0, False

    def _is_done(self, action: str) -> bool:
        if self.num_turn == self.max_turns:
            return True
        return "<solution>" in action and "</solution>" in action
    
    def _preprocess_action_message(self, action_message: Message):
        content = action_message["content"]
        tool_calls = action_message.get("tool_calls", [])
        if isinstance(content, list):
            last_content_part = ""
            for content_part in content:
                if content_part["type"] == "text":
                    last_content_part = content_part["text"]
            content = last_content_part
        return content, tool_calls

    async def step(self, action: Action) -> StepResult:
        self.num_turn += 1

        # step 1: parse the action tokens into a message
        # this step is specific to our library, but usually templated, so you can just copy it.
        (action_message, _parse_success) = self.renderer.parse_response(action)
        content, tool_calls = self._preprocess_action_message(action_message)
        # print("=" * 100)
        # print(f"Action: {action_message['content']}")
        # if "tool_calls" in action_message:
        #     for tool_call in action_message["tool_calls"]:
        #         print(f"Tool Call (id={tool_call.id}): {tool_call.function.name} with arguments {tool_call.function.arguments}")

        # step 2: based on the string answer, we compute the reward and the user turn.
        user_turn, reward, is_final = await self._get_user_turn(
            content,
            tool_calls
        )

        # step 3: update the conversation history
        self.turns.append({"role": "assistant", "content": action_message["content"]})
        if "tool_calls" in action_message and action_message["tool_calls"] != []:
            self.turns[-1]["tool_calls"] = action_message["tool_calls"]
    
        if user_turn is not None:
            self.turns += user_turn
        episode_done = is_final or self.num_turn == self.max_turns or \
            self._obs.length + self.max_output_tokens_per_turn > self.max_input_tokens
        
        # print(f"Current reward: {reward}")
        # print(f"Is done: {self._is_done(action_message['content'])}")
        # print(f"number of turns left: {self.max_turns - self.num_turn}")
        # print("=" * 100)

        # step 4: return the step result
        step_result = StepResult(
            next_observation=self._obs,
            next_stop_condition=self.stop_condition,
            episode_done=episode_done,
            reward= 0 if not episode_done else reward
        )

        return step_result

class BIRDCorrectionDataset(RLDataset):
    def __init__(
        self,
        batch_size: int,
        group_size: int,
        renderer: renderers.Renderer,
        data_path: str,
        db_path: str|List[str]|None,
        timeout: int,
        model_name: str,
        split: Literal["train", "test"] = "train",
        n_epochs: int = 1,
        num_data: int = -1,
        use_convo_prefix: bool = True,
        max_output_tokens_per_turn: int = 3072,
        max_input_tokens: int = 32768,
        max_turns: int = 5,
        dump_path: str | None = None,
        reward_model: str = "Qwen/Qwen3-235B-A22B-Instruct-2507"
    ):
        if split not in ("train", "test"):
            raise ValueError("split must be 'train' or 'test'")

        # regular setup
        self.ds = cast(Dataset, load_dataset("parquet", data_files=data_path, keep_in_memory=True)["train"])
        if split == "train":
            self.ds = self.ds.shuffle(seed=0)
            if num_data > 0:
                self.ds = self.ds.select(range(num_data))
            if n_epochs > 1:
                self.ds = concatenate_datasets([self.ds for _ in range(n_epochs)])
        if split == "test":
            all_ds = []
            for i in range(n_epochs):
                ds = deepcopy(self.ds)
                # append i to data source
                ds = ds.map(lambda x: {"data_source": f"{x['data_source']}_{i}"})
                all_ds.append(ds)
            self.ds = concatenate_datasets(all_ds)
        self.group_sizes = [group_size for _ in range(len(self.ds))]

        self.batch_size = batch_size
        self.group_size = group_size if split == "train" else 1
        self.renderer = renderer
        self.db_path = db_path
        self.timeout = timeout
        self.dump_path = dump_path
        self.use_convo_prefix = use_convo_prefix
        self.max_output_tokens_per_turn = max_output_tokens_per_turn
        self.max_input_tokens = max_input_tokens
        self.model_name = model_name
        self.max_turns = max_turns
        service_client = tinker.ServiceClient(base_url=None)
        self.reward_client = service_client.create_sampling_client(base_model=reward_model)
        self.reward_renderer = renderers.get_renderer(name=get_recommended_renderer_name(reward_model), tokenizer=get_tokenizer(reward_model))

    @classmethod
    def question_suffix(cls) -> str:
        return ""

    def get_batch(self, index: int) -> list[EnvGroupBuilder]:
        batch_start = index * self.batch_size
        batch_end = min((index + 1) * self.batch_size, len(self.ds))
        group_sizes = self.group_sizes[batch_start: batch_end]
        assert batch_start < batch_end, "Incorrect batch size"
        return [
            builder
            for row, group_size in zip(self.ds.select(range(batch_start, batch_end)), group_sizes)
            if (builder := self._make_env_group_builder(row, group_size)) is not None  # pyright: ignore[reportArgumentType]
        ]

    def __len__(self) -> int:
        return math.ceil(len(self.ds) / self.batch_size)

    def set_dump_path(self, dump_path: str) -> None:
        self.dump_path = dump_path

    def _make_env_group_builder(
        self, x: dict[str, str], group_size: int
    ) -> ProblemGroupBuilder | None:
        # Extract problem and answer from the dataset
        problem_id = f"{x['data_source']}_{x['question_id']}"
        problem = x["prompt"][1]["content"]
        answer = x["reward_spec"]["ground_truth"]
        grading_method = x["reward_spec"].get("grading_method", "set")
        dataset_name = x["data_source"]
        db_id = x["db_id"]
        db_file = f"{self.db_path}/{db_id}/{db_id}.sqlite"
        if not (problem and answer):
            return None
        return ProblemGroupBuilder(
            env_thunk=partial(
                SQLCorrectionEnv, problem_id, problem, answer, self.renderer, db_file, self.timeout, self.reward_client, self.reward_renderer, self.dump_path, self.use_convo_prefix, self.max_output_tokens_per_turn, self.max_input_tokens, self.model_name, self.max_turns
            ),
            num_envs=group_size,
            dataset_name=dataset_name,
        )


@chz.chz
class BIRDCorrectionDatasetBuilder(RLDatasetBuilder):
    batch_size: int
    renderer_name: str
    train_group_size: int
    base_url: str | None = None
    model_name: str
    train_data_path: str | None
    test_data_path: str | None
    db_path: str | None
    timeout: int = 60
    add_noise: str | None = None
    n_epochs: int = 1
    num_data: int = -1
    use_convo_prefix: bool = True
    max_output_tokens_per_turn: int = 3072
    max_input_tokens: int = 32768
    max_turns: int = 5
    curriculum_learning: bool = False

    async def __call__(self) -> tuple[RLDataset, RLDataset]:
        sql_renderer = get_renderer(self.renderer_name, get_tokenizer(self.model_name))

        train_data_path = self.train_data_path
        if "db" in self.add_noise:
            assert "/databases" in self.db_path, "db_path must contain /databases if db noise is used"
            db_path = self.db_path.replace("/databases", "/original_databases")
        else:
            db_path = self.db_path

        test_data_path = self.test_data_path

        # log information about datasets
        logger.info(f"Training data path: {train_data_path}")
        logger.info(f"Test data path: {test_data_path}")
        logger.info(f"Database path: {db_path}")

        training_dataset = BIRDCorrectionDataset(
            batch_size=self.batch_size,
            group_size=self.train_group_size,
            renderer=sql_renderer,
            data_path=train_data_path,
            timeout=self.timeout,
            db_path=db_path,
            split="train",
            n_epochs=self.n_epochs,
            num_data=self.num_data,
            use_convo_prefix=self.use_convo_prefix,
            max_output_tokens_per_turn=self.max_output_tokens_per_turn,
            max_input_tokens=self.max_input_tokens,
            max_turns=self.max_turns,
            model_name=self.model_name
        )
        test_dataset = BIRDCorrectionDataset(
            batch_size=self.batch_size,
            group_size=1,
            renderer=sql_renderer,
            data_path=test_data_path,
            timeout=self.timeout,
            db_path=self.db_path,
            split="test",
            n_epochs=1,
            use_convo_prefix=self.use_convo_prefix,
            max_output_tokens_per_turn=self.max_output_tokens_per_turn,
            max_input_tokens=self.max_input_tokens,
            max_turns=self.max_turns,
            model_name=self.model_name
        )
        return training_dataset, test_dataset
