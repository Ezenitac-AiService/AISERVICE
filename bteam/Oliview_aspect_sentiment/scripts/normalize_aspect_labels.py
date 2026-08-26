"""속성 라벨 정리

- 입력: --input-dir 아래 train_clean.csv, validation_clean.csv, test_clean.csv
- 라벨 통합: aspect_labels.json의 rename_labels 적용
- 복합 라벨 분리: 문장에 쿨링 표현이 있으면 쿨링감, 없으면 보습력/수분감
- 학습 제외: 원래 속성이 기능/효과인 행 전체
- 출력: --output-dir 아래 정규화 데이터, 제외·충돌 검토 자료, 라벨 번호표
"""

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

# '보습력/수분감/쿨링감' 문장에서 쿨링감 여부를 판별할 핵심 표현
COOLING = ["쿨링", "쿨감", "시원", "열감", "쿨한 느낌"]
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "aspect_labels.json"


def has(text, words):
    # UV, uv처럼 영문 대소문자가 달라도 같은 표현으로 확인
    text = text.casefold()
    return any(word.casefold() in text for word in words)


def normalize(aspect, text, rename_labels, exclude_labels, protected_exclusions):
    # 복합 라벨은 리뷰 문장에 COOLING 표현이 있는 경우만 '쿨링감'으로 분리
    if aspect == "보습력/수분감/쿨링감":
        aspect = "쿨링감" if has(text, COOLING) else "보습력/수분감"

    # 기능/효과는 키워드로 다른 속성에 억지 배정하지 않고 학습 데이터에서 전부 제외
    if aspect in protected_exclusions:
        return None, "function_excluded"

    # 설정 파일에서 이름 변경·통합 후 제외 목록 적용
    normalized = rename_labels.get(aspect, aspect)
    if aspect in exclude_labels or normalized in exclude_labels:
        return None, "configured_exclusion"
    if normalized != aspect:
        return normalized, "configured_rename"
    if aspect in {"쿨링감", "보습력/수분감"}:
        return aspect, "split_combined_label"
    return normalized, "unchanged"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def process(input_path, output_dir, rename_labels, exclude_labels, protected_exclusions):
    rows = read(input_path)
    converted, excluded, changes = [], [], Counter()

    # 각 행에 원래 라벨(original_aspect)과 처리 사유(normalization_reason) 추가
    # 기능/효과 행은 converted가 아닌 excluded에 보관
    for row in rows:
        old = row["aspect"]
        new, reason = normalize(
            old,
            row["sentiment_text"],
            rename_labels,
            exclude_labels,
            protected_exclusions,
        )
        item = dict(row, original_aspect=old, aspect=new, normalization_reason=reason)
        if new is None:
            excluded.append(item)
            changes[(old, "", reason)] += 1
            continue
        converted.append(item)
        changes[(old, new, reason)] += 1

    # 공백 차이를 제거한 같은 sentiment_text에 속성이 둘 이상이면 라벨 충돌로 판단
    phrase_aspects = defaultdict(set)
    for row in converted:
        phrase_aspects[re.sub(r"\s+", " ", row["sentiment_text"]).strip()].add(row["aspect"])
    conflict_keys = {key for key, values in phrase_aspects.items() if len(values) > 1}
    # 충돌 문장은 별도 검토 CSV로 이동
    # 충돌이 없는 행은 같은 (문장, 속성) 조합을 한 번만 유지
    conflicts, clean, seen = [], [], set()
    for row in converted:
        phrase = re.sub(r"\s+", " ", row["sentiment_text"]).strip()
        if phrase in conflict_keys:
            conflicts.append(row)
        elif (phrase, row["aspect"]) not in seen:
            clean.append(row)
            seen.add((phrase, row["aspect"]))

    # 출력 열: 기존 열 + 변경 전 라벨 + 라벨 처리 사유
    fields = list(rows[0]) + ["original_aspect", "normalization_reason"]
    split = input_path.stem.replace("_clean", "")
    write(output_dir / f"{split}_normalized.csv", clean, fields)
    write(output_dir / f"{split}_normalization_conflicts.csv", conflicts, fields)
    write(output_dir / f"{split}_function_review.csv", excluded, fields)
    return split, len(rows), len(clean), len(conflicts), len(excluded), changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # 학습 노트북과 같은 라벨 이름 변경·제외 설정 사용
    settings = json.loads(args.config.read_text(encoding="utf-8"))
    rename_labels = settings.get("rename_labels", {})
    exclude_labels = set(settings.get("exclude_labels", []))
    # 입력 CSV가 이미 변경 후 이름이어도 이전 이름으로 제외 가능
    exclude_labels |= {
        rename_labels.get(aspect, aspect) for aspect in exclude_labels
    }
    protected_exclusions = set(settings.get("protected_original_exclusions", []))
    protected_exclusions.add("기능/효과")

    # Train·Validation·Test에 동일 규칙 적용
    # 분할마다 정규화 데이터, 충돌 데이터, 기능/효과 제외 데이터 생성
    results = [
        process(
            args.input_dir / f"{split}_clean.csv",
            args.output_dir,
            rename_labels,
            exclude_labels,
            protected_exclusions,
        )
        for split in ["train", "validation", "test"]
    ]
    all_rows = {
        split: read(args.output_dir / f"{split}_normalized.csv")
        for split, *_ in results
    }
    # 세 분할에 등장하는 모든 최종 속성을 가나다순 정렬 후 0부터 번호 부여
    # 모든 분할과 모델 config에서 동일한 라벨 번호 사용
    labels = sorted({row["aspect"] for rows in all_rows.values() for row in rows})
    label2id = {label: index for index, label in enumerate(labels)}
    id2label = {str(index): label for label, index in label2id.items()}
    for split, rows in all_rows.items():
        for row in rows:
            row["label"] = str(label2id[row["aspect"]])
        write(args.output_dir / f"{split}_normalized.csv", rows, list(rows[0]))

    (args.output_dir / "label2id.json").write_text(json.dumps(label2id, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "id2label.json").write_text(json.dumps(id2label, ensure_ascii=False, indent=2), encoding="utf-8")

    # normalization_summary.csv: 분할별 원본·최종·충돌·기능/효과 제외 행 수
    with (args.output_dir / "normalization_summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["split", "input_rows", "output_rows", "conflict_rows", "excluded_function_rows"])
        writer.writerows([result[:5] for result in results])
    # label_change_counts.csv: 기존 라벨이 어떤 최종 라벨로 몇 건 바뀌었는지 집계
    changes = Counter()
    for *_, split_changes in results:
        changes.update(split_changes)
    with (args.output_dir / "label_change_counts.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["original_aspect", "normalized_aspect", "reason", "count"])
        for (old, new, reason), count in sorted(changes.items()):
            writer.writerow([old, new, reason, count])

    print(f"labels={len(labels)}")
    for result in results:
        print(result[:5])


if __name__ == "__main__":
    main()
