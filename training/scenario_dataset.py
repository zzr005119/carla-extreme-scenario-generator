"""场景 JSONL 到模型数组的只读数据接口。"""

from dataclasses import dataclass

from core.scenario_features import load_jsonl, records_to_arrays


@dataclass(frozen=True)
class ScenarioArrayDataset:
    records: list
    features: object
    conditions: object

    @classmethod
    def from_jsonl(cls, path):
        records = load_jsonl(path)
        features, conditions = records_to_arrays(records)
        return cls(records=records, features=features, conditions=conditions)

    def __len__(self):
        return len(self.records)
