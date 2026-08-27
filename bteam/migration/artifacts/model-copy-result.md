# Green Model Copy Result

- Date: 2026-08-27
- Mode: non-destructive copy to Green candidate paths
- Blue source paths: unchanged
- Copy script: `migration/prepare_models.py`
- Verification: every copied file was checksum-verified before replacement

| Model set | Green destination | Files | Bytes | Result |
|---|---|---:|---:|---|
| Sentence split | `models/sentence_split` | 33 | 4,405,105,090 | PASS |
| Sentiment | `models/sentiment` | 21 | 1,332,105,276 | PASS |

The optional ChatA embedding model set was not copied because it is not required
for the current Green validation image and would expand the migration scope.
