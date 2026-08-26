"""전체 카테고리에서 서비스용 속성만 추출해 학습 CSV를 만드는 전처리 코드"""

import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "aspect_labels.json").read_text(encoding="utf-8"))
RAW_DIR = ROOT / SETTINGS["raw_data_dir"]
OUTPUT_DIR = ROOT / SETTINGS["data_dir"]
SENTIMENT_DIR = ROOT / "data" / "sentiment"
REPORT_DIR = ROOT / "data" / "reports"
FIELDS = [
    "review_id", "source", "category", "product_name", "raw_text", "aspect",
    "sentiment_text", "sentiment_polarity", "model_input", "label",
    "original_aspect", "normalization_reason",
]


def compact(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def read_raw(name):
    return json.loads((RAW_DIR / name).read_text(encoding="utf-8-sig"))


def extract(records, split):
    allowed = set(SETTINGS["target_original_labels"])
    rename = SETTINGS["rename_labels"]
    rows = []
    changes = Counter()
    for review in records:
        for item in review.get("Aspects", []):
            original = compact(item.get("Aspect"))
            if original not in allowed:
                continue
            text = compact(item.get("SentimentText"))
            if not text:
                continue
            aspect = rename.get(original, original)
            reason = "merged_duplicate_label" if aspect != original else "unchanged"
            changes[(split, original, aspect, reason)] += 1
            rows.append({
                "review_id": review.get("Index", ""),
                "source": review.get("Source", ""),
                "category": review.get("MainCategory", ""),
                "product_name": review.get("ProductName", ""),
                "raw_text": compact(review.get("RawText")),
                "aspect": aspect,
                "sentiment_text": text,
                "sentiment_polarity": item.get("SentimentPolarity", ""),
                "model_input": f"[속성] {aspect} [문장] {text}",
                "label": "",
                "original_aspect": original,
                "normalization_reason": reason,
            })
    return rows, changes


def split_validation(records, seed=42):
    """리뷰 단위·카테고리별로 원본 Validation을 Validation/Test 50:50 분리."""
    groups = defaultdict(list)
    for record in records:
        groups[record.get("MainCategory", "")].append(record)
    validation, test = [], []
    for category in sorted(groups):
        items = list(groups[category])
        random.Random(f"{seed}:{category}").shuffle(items)
        cut = (len(items) + 1) // 2
        validation.extend(items[:cut])
        test.extend(items[cut:])
    return validation, test


def remove_conflicts_and_duplicates(rows):
    phrase_aspects = defaultdict(set)
    for row in rows:
        phrase_aspects[compact(row["sentiment_text"])].add(row["aspect"])
    conflicts = {text for text, aspects in phrase_aspects.items() if len(aspects) > 1}
    clean, conflict_rows, seen = [], [], set()
    for row in rows:
        text = compact(row["sentiment_text"])
        if text in conflicts:
            conflict_rows.append(row)
            continue
        key = (text, row["aspect"])
        if key not in seen:
            clean.append(row)
            seen.add(key)
    return clean, conflict_rows


def prepare_sentiment_rows(rows):
    """감성 학습용 정답을 만들고 충돌·중복 문장을 정리한다."""
    polarities = defaultdict(set)
    for row in rows:
        polarities[row["model_input"]].add(int(row["sentiment_polarity"]))

    # 속성과 문장이 완전히 같은데 감성 정답이 다른 경우에는 학습에서 제외
    conflict_inputs = {
        model_input
        for model_input, values in polarities.items()
        if len(values) > 1
    }
    label_map = {
        1: 0,   # 긍정
        -1: 1,  # 부정
        0: 2,   # 중립
    }
    clean, conflicts, seen = [], [], set()
    for row in rows:
        item = dict(row)
        polarity = int(item["sentiment_polarity"])
        if item["model_input"] in conflict_inputs:
            conflicts.append(item)
            continue
        key = (item["model_input"], polarity)
        if key in seen:
            continue
        seen.add(key)
        item["label"] = label_map[polarity]
        clean.append(item)
    return clean, conflicts


def remove_cross_split_duplicates(data, key_field):
    """Train을 우선 보존하고 Validation/Test에서 같은 모델 입력을 제거한다."""
    seen = {}
    cleaned = {}
    removed = []
    for split in ("train", "validation", "test"):
        kept = []
        for row in data[split]:
            key = compact(row[key_field])
            if key in seen:
                removed.append({
                    **row,
                    "split": split,
                    "duplicate_of_split": seen[key],
                    "duplicate_key": key,
                })
                continue
            seen[key] = split
            kept.append(row)
        cleaned[split] = kept
    return cleaned, removed


def write_csv(path, rows, fields=FIELDS):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    train_records = read_raw("train.json")
    validation_records, test_records = split_validation(read_raw("validation.json"))
    record_sets = {
        "train": train_records,
        "validation": validation_records,
        "test": test_records,
    }

    extracted = {}
    sentiment_data = {}
    all_changes = Counter()
    summary = []
    sentiment_summary = []
    conflict_outputs = []
    sentiment_conflict_outputs = []
    for split, records in record_sets.items():
        rows, changes = extract(records, split)
        clean, conflicts = remove_conflicts_and_duplicates(rows)
        sentiment_clean, sentiment_conflicts = prepare_sentiment_rows(rows)
        extracted[split] = clean
        sentiment_data[split] = sentiment_clean
        all_changes.update(changes)
        conflict_outputs.extend(dict(row, split=split) for row in conflicts)
        sentiment_conflict_outputs.extend(
            dict(row, split=split) for row in sentiment_conflicts
        )
        summary.append({
            "split": split,
            "source_reviews": len(records),
            "target_rows_before_cleanup": len(rows),
            "output_rows": len(clean),
            "conflict_rows": len(conflicts),
            "categories": len({row["category"] for row in clean}),
        })
        sentiment_summary.append({
            "split": split,
            "source_reviews": len(records),
            "target_rows_before_cleanup": len(rows),
            "output_rows": len(sentiment_clean),
            "conflict_rows": len(sentiment_conflicts),
            "categories": len({row["category"] for row in sentiment_clean}),
        })

    # 모델이 실제로 받는 입력이 분할 사이에 반복되지 않도록 한다.
    # 속성 모델 입력은 sentiment_text, 감성 모델 입력은 aspect+sentiment_text이다.
    extracted, aspect_cross_split_duplicates = remove_cross_split_duplicates(
        extracted, "sentiment_text"
    )
    sentiment_data, sentiment_cross_split_duplicates = remove_cross_split_duplicates(
        sentiment_data, "model_input"
    )

    for row in summary:
        split = row["split"]
        row["output_rows"] = len(extracted[split])
        row["cross_split_duplicate_rows"] = sum(
            item["split"] == split for item in aspect_cross_split_duplicates
        )
    for row in sentiment_summary:
        split = row["split"]
        row["output_rows"] = len(sentiment_data[split])
        row["cross_split_duplicate_rows"] = sum(
            item["split"] == split for item in sentiment_cross_split_duplicates
        )

    labels = sorted({row["aspect"] for rows in extracted.values() for row in rows})
    expected = len({
        SETTINGS["rename_labels"].get(label, label)
        for label in SETTINGS["target_original_labels"]
    })
    if len(labels) != expected:
        raise ValueError(f"최종 라벨 수 불일치: expected={expected}, actual={len(labels)}, labels={labels}")
    label2id = {label: index for index, label in enumerate(labels)}
    id2label = {str(index): label for label, index in label2id.items()}
    for split, rows in extracted.items():
        for row in rows:
            row["label"] = label2id[row["aspect"]]
        write_csv(OUTPUT_DIR / f"{split}.csv", rows)
    for split, rows in sentiment_data.items():
        write_csv(SENTIMENT_DIR / f"{split}.csv", rows)

    (OUTPUT_DIR / "label2id.json").write_text(
        json.dumps(label2id, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "id2label.json").write_text(
        json.dumps(id2label, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(
        OUTPUT_DIR / "preparation_summary.csv",
        summary,
        [
            "split", "source_reviews", "target_rows_before_cleanup", "output_rows",
            "conflict_rows", "cross_split_duplicate_rows", "categories",
        ],
    )
    change_rows = [
        {"split": split, "original_aspect": old, "normalized_aspect": new, "reason": reason, "count": count}
        for (split, old, new, reason), count in sorted(all_changes.items())
    ]
    write_csv(
        OUTPUT_DIR / "label_change_counts.csv",
        change_rows,
        ["split", "original_aspect", "normalized_aspect", "reason", "count"],
    )
    write_csv(
        OUTPUT_DIR / "normalization_conflicts.csv",
        conflict_outputs,
        ["split", *FIELDS],
    )
    write_csv(
        SENTIMENT_DIR / "preparation_summary.csv",
        sentiment_summary,
        [
            "split", "source_reviews", "target_rows_before_cleanup", "output_rows",
            "conflict_rows", "cross_split_duplicate_rows", "categories",
        ],
    )
    write_csv(
        REPORT_DIR / "sentiment_conflicts.csv",
        sentiment_conflict_outputs,
        ["split", *FIELDS],
    )
    write_csv(
        REPORT_DIR / "aspect_cross_split_duplicates.csv",
        aspect_cross_split_duplicates,
        ["split", "duplicate_of_split", "duplicate_key", *FIELDS],
    )
    write_csv(
        REPORT_DIR / "sentiment_cross_split_duplicates.csv",
        sentiment_cross_split_duplicates,
        ["split", "duplicate_of_split", "duplicate_key", *FIELDS],
    )
    print(f"labels={len(labels)}")
    for row in summary:
        print(row)
    print("sentiment")
    for row in sentiment_summary:
        print(row)


if __name__ == "__main__":
    main()
