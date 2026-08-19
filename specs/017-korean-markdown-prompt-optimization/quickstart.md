# Quickstart Validation Guide: 017-korean-markdown-prompt-optimization

## 1. Unit Test for Korean Markdown Sanitizer

```bash
# Execute unit test for normalize_korean_markdown
python tests/unit/test_korean_markdown_sanitizer.py
```

## 2. Integration Test with Live RAG Pipeline

```bash
# Execute integration test to check LLM response markdown quality
python -c "
from oliview_core.pipeline import prepare_pipeline_stream
token_gen, meta = prepare_pipeline_stream('식물나라 토너 자극성과 기능/효과 분석해줘')
full_ans = ''.join(list(token_gen))
assert '**\"' not in full_ans, 'Raw quote bold syntax detected!'
print('Pass! Generated Answer Sample:\n', full_ans[:200])
"
```
