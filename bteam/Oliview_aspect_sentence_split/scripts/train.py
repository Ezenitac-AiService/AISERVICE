from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import precision_recall_fscore_support
from torch.utils.data import Dataset
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    Trainer,
    TrainingArguments,
)


ROOT = Path(__file__).resolve().parents[1]
TAG2ID = {"O": 0, "B": 1, "I": 2}
ID2TAG = {value: key for key, value in TAG2ID.items()}


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


class AspectSpanDataset(Dataset):
    def __init__(
        self,
        records: list[dict],
        aspects: list[str],
        tokenizer,
        max_length: int,
        negative_count: int,
        seed: int,
    ) -> None:
        self.examples: list[tuple[str, str, list[dict]]] = []
        rng = random.Random(seed)

        for record in records:
            by_aspect: dict[str, list[dict]] = {}
            for span in record["spans"]:
                by_aspect.setdefault(span["aspect"], []).append(span)

            for aspect, spans in by_aspect.items():
                self.examples.append((aspect, record["text"], spans))

            negative_aspects = [
                aspect for aspect in aspects if aspect not in by_aspect
            ]
            rng.shuffle(negative_aspects)
            for aspect in negative_aspects[:negative_count]:
                self.examples.append((aspect, record["text"], []))

        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict:
        aspect, text, spans = self.examples[index]
        encoded = self.tokenizer(
            aspect,
            text,
            truncation="only_second",
            max_length=self.max_length,
            return_offsets_mapping=True,
        )
        # KLUE-RoBERTa에서 쓰지 않는 문장 구분 번호 제거
        encoded.pop("token_type_ids", None)
        offsets = encoded.pop("offset_mapping")
        sequence_ids = encoded.sequence_ids()
        labels = []

        for token_index, ((start, end), sequence_id) in enumerate(
            zip(offsets, sequence_ids)
        ):
            if sequence_id != 1 or start == end:
                labels.append(-100)
                continue

            label = TAG2ID["O"]
            for span in spans:
                if end <= span["start"] or start >= span["end"]:
                    continue
                previous_is_same_span = (
                    token_index > 0
                    and sequence_ids[token_index - 1] == 1
                    and offsets[token_index - 1][1] > span["start"]
                )
                label = TAG2ID["I" if previous_is_same_span else "B"]
                break
            labels.append(label)

        encoded["labels"] = labels
        return encoded


def metrics(eval_prediction) -> dict[str, float]:
    logits, labels = eval_prediction
    predictions = np.argmax(logits, axis=-1)
    mask = labels != -100
    true = labels[mask]
    predicted = predictions[mask]
    precision, recall, f1, _ = precision_recall_fscore_support(
        true,
        predicted,
        labels=[1, 2],
        average="micro",
        zero_division=0,
    )
    return {"span_precision": precision, "span_recall": recall, "span_f1": f1}


def main() -> None:
    settings = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    data_dir = ROOT / settings["prepared_data_dir"]
    output_dir = ROOT / settings["model_output_dir"]
    aspects = json.loads((data_dir / "labels.json").read_text(encoding="utf-8"))

    tokenizer = AutoTokenizer.from_pretrained(settings["base_model"], use_fast=True)
    model = AutoModelForTokenClassification.from_pretrained(
        settings["base_model"],
        num_labels=len(TAG2ID),
        id2label=ID2TAG,
        label2id=TAG2ID,
    )

    train_dataset = AspectSpanDataset(
        read_jsonl(data_dir / "train.jsonl"),
        aspects,
        tokenizer,
        settings["max_length"],
        settings["negative_aspects_per_review"],
        settings["seed"],
    )
    validation_dataset = AspectSpanDataset(
        read_jsonl(data_dir / "validation.jsonl"),
        aspects,
        tokenizer,
        settings["max_length"],
        settings["negative_aspects_per_review"],
        settings["seed"] + 1,
    )

    arguments = TrainingArguments(
        output_dir=str(output_dir),
        learning_rate=2e-5,
        per_device_train_batch_size=4,
        per_device_eval_batch_size=4,
        gradient_accumulation_steps=4,
        num_train_epochs=3,
        weight_decay=0.01,
        bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="span_f1",
        greater_is_better=True,
        logging_steps=50,
        seed=settings["seed"],
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=arguments,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        data_collator=DataCollatorForTokenClassification(tokenizer),
        processing_class=tokenizer,
        compute_metrics=metrics,
    )
    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    (output_dir / "aspects.json").write_text(
        json.dumps(aspects, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
