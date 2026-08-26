from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def locate_phrase(
    raw_text: str,
    phrase: str,
    used: set[tuple[int, int, str]],
    aspect: str,
) -> tuple[int, int] | None:
    start = 0
    while True:
        found = raw_text.find(phrase, start)
        if found < 0:
            return None
        span = (found, found + len(phrase), aspect)
        if span not in used:
            used.add(span)
            return found, found + len(phrase)
        start = found + 1


def convert_split(
    input_path: Path,
    output_path: Path,
    unmatched_path: Path,
) -> dict[str, int]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(input_path):
        grouped[row["review_id"]].append(row)

    records: list[dict] = []
    unmatched: list[dict[str, str]] = []
    span_count = 0

    for review_id, rows in grouped.items():
        raw_text = compact(rows[0]["raw_text"])
        used: set[tuple[int, int, str]] = set()
        spans = []

        for row in rows:
            phrase = compact(row["sentiment_text"])
            location = locate_phrase(raw_text, phrase, used, row["aspect"])
            if location is None:
                unmatched.append({
                    "review_id": review_id,
                    "aspect": row["aspect"],
                    "sentiment_text": phrase,
                    "raw_text": raw_text,
                })
                continue
            start, end = location
            spans.append({
                "aspect": row["aspect"],
                "text": phrase,
                "start": start,
                "end": end,
            })
            span_count += 1

        if spans:
            records.append({
                "review_id": review_id,
                "category": rows[0]["category"],
                "text": raw_text,
                "spans": spans,
            })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    unmatched_path.parent.mkdir(parents=True, exist_ok=True)
    with unmatched_path.open("w", encoding="utf-8-sig", newline="") as file:
        fields = ["review_id", "aspect", "sentiment_text", "raw_text"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(unmatched)

    return {
        "reviews": len(records),
        "spans": span_count,
        "unmatched": len(unmatched),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    args = parser.parse_args()

    settings = json.loads(args.config.read_text(encoding="utf-8"))
    source_dir = (ROOT / settings["source_data_dir"]).resolve()
    output_dir = ROOT / settings["prepared_data_dir"]
    report_dir = output_dir / "reports"

    labels = json.loads(
        (source_dir / "label2id.json").read_text(encoding="utf-8")
    )
    (output_dir / "labels.json").parent.mkdir(parents=True, exist_ok=True)
    (output_dir / "labels.json").write_text(
        json.dumps(sorted(labels), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = {}
    for split in ("train", "validation", "test"):
        summary[split] = convert_split(
            source_dir / f"{split}.csv",
            output_dir / f"{split}.jsonl",
            report_dir / f"{split}_unmatched.csv",
        )

    (report_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

