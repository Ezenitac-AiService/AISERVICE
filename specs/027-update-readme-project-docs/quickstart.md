# Quickstart & Verification Guide: 027-update-readme-project-docs

## 1. Documentation Validation Script

```python
import os

required_files = [
    "README.md",
    "LICENSE",
    "docs/architecture.md",
    "docs/model_gateway.md",
    "docs/bteam_oliview.md",
    "docs/ateam_pilos.md",
    "docs/security_guardrails.md",
]

for rf in required_files:
    assert os.path.exists(rf), f"Missing required documentation file: {rf}"
    with open(rf, "r", encoding="utf-8") as f:
        content = f.read()
        assert len(content) > 100, f"File {rf} is too short or empty"

print("ALL DOCUMENTATION FILES VALIDATED SUCCESSFULLY!")
```

## 2. Link Integrity Verification

```python
import re, os

with open("README.md", "r", encoding="utf-8") as f:
    readme = f.read()

links = re.findall(r'\[.*?\]\((docs/[a-zA-Z0-9_\-\.]+)\)', readme)
for link in links:
    assert os.path.exists(link), f"Broken link in README.md: {link}"

print(f"All {len(links)} documentation links in README.md are intact!")
```
