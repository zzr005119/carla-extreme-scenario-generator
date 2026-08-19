"""对抗性测试代理 V1 的无 CARLA CLI 契约入口。"""

import argparse
import json
import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.adversarial_agent import (  # noqa: E402
    AdversarialTestAgentV1,
    action_space_spec,
    build_observation,
    load_agent_config,
    observation_space_spec,
)
from core.scenario_validator import load_json  # noqa: E402


def _read_action(path):
    value = load_json(path)
    if isinstance(value, dict):
        value = value.get("action")
    return value


def _write_output(value, path=None):
    payload = json.dumps(value, ensure_ascii=False, indent=2)
    if path:
        with open(path, "w", encoding="utf-8") as file:
            file.write(payload)
            file.write("\n")
    print(payload)


def parse_args():
    parser = argparse.ArgumentParser(description="对抗性测试代理 V1 契约工具")
    parser.add_argument("--config", default=os.path.join(PROJECT_ROOT, "configs", "adversarial_agent_v1.json"))
    parser.add_argument("--record", help="输入场景 JSON；与 --action 一起输出候选")
    parser.add_argument("--action", help="动作 JSON 数组或包含 action 字段的 JSON")
    parser.add_argument("--result", help="外部 CARLA 结果 JSON；提供后输出完整 transition")
    parser.add_argument("--output", help="可选输出 JSON 路径")
    parser.add_argument("--spec", action="store_true", help="只输出观测/动作空间规格")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_agent_config(args.config)
    if args.spec:
        _write_output({"action_space": action_space_spec(config), "observation_space": observation_space_spec(config)}, args.output)
        return 0
    if not args.record or not args.action:
        raise SystemExit("--record 和 --action 必须同时提供")
    record = load_json(args.record)
    action = _read_action(args.action)
    agent = AdversarialTestAgentV1(config)
    initial_observation = agent.reset(record)
    proposal = agent.propose(action)
    if args.result:
        result = load_json(args.result)
        transition = agent.record_result(result)
        _write_output({"initial_observation": initial_observation, "proposal": proposal, "transition": transition.to_dict()}, args.output)
    else:
        _write_output({"initial_observation": initial_observation, "proposal": proposal}, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
