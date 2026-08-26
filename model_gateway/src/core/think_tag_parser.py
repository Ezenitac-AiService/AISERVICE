"""
LLM Response <think> Tag Parser & Streaming Filter Helper Module (047-think-tag-stripping).
Extracts and strips <think>...</think> reasoning traces for clean response rendering.
"""

import re
from typing import Tuple, Optional


def parse_think_tags(text: str) -> Tuple[str, Optional[str]]:
    """
    Parses <think>...</think> tags from LLM response text.

    Returns:
        tuple[clean_text, thinking_text]:
        - clean_text: Text with <think>...</think> tags stripped.
        - thinking_text: Extracted reasoning trace string, or None if no <think> tag was present.
        - If <think> tag is unclosed (truncated), clean_text is "[Truncated during thinking process]".
    """
    if not text:
        return "", None

    if "<think>" in text:
        if "</think>" in text:
            pattern = re.compile(r'<think>(.*?)</think>', re.DOTALL)
            matches = pattern.findall(text)
            thinking_text = "\n\n".join(m.strip() for m in matches if m.strip())
            clean_text = pattern.sub('', text).strip()
            return clean_text, thinking_text if thinking_text else None
        else:
            # Unclosed <think> tag scenario (truncation)
            parts = text.split("<think>", 1)
            thinking_text = parts[1].strip() if len(parts) > 1 else ""
            return "[Truncated during thinking process]", thinking_text if thinking_text else None

    return text.strip(), None


class ThinkTagStreamFilter:
    """
    State-machine filter for processing SSE streaming response chunks in real-time.
    Suppresses tokens inside <think>...</think> from client output stream.
    """

    def __init__(self):
        self.buffer = ""
        self.in_think = False
        self.thinking_chunks = []
        self.think_closed = False

    def process_chunk(self, chunk: str) -> str:
        if not chunk:
            return ""

        self.buffer += chunk
        output = ""

        while self.buffer:
            if not self.in_think:
                if "<think>" in self.buffer:
                    idx = self.buffer.find("<think>")
                    output += self.buffer[:idx]
                    self.buffer = self.buffer[idx + 7:]
                    self.in_think = True
                else:
                    # Check partial "<think>" at end of buffer
                    partial_match = False
                    for i in range(1, 7):
                        if "<think>"[:i] == self.buffer[-i:]:
                            partial_match = True
                            output += self.buffer[:-i]
                            self.buffer = self.buffer[-i:]
                            break
                    if not partial_match:
                        output += self.buffer
                        self.buffer = ""
            else:
                if "</think>" in self.buffer:
                    idx = self.buffer.find("</think>")
                    self.thinking_chunks.append(self.buffer[:idx])
                    self.buffer = self.buffer[idx + 8:]
                    self.in_think = False
                    self.think_closed = True
                else:
                    # Collect thinking text, keeping room for partial "</think>"
                    partial_match = False
                    for i in range(1, 8):
                        if "</think>"[:i] == self.buffer[-i:]:
                            partial_match = True
                            self.thinking_chunks.append(self.buffer[:-i])
                            self.buffer = self.buffer[-i:]
                            break
                    if not partial_match:
                        self.thinking_chunks.append(self.buffer)
                        self.buffer = ""

        return output

    def get_thinking_text(self) -> Optional[str]:
        full_think = "".join(self.thinking_chunks).strip()
        return full_think if full_think else None
