"""Smart memory service for session context and deduplication."""

from __future__ import annotations

import hashlib
import time

import codeup.config as _config
from codeup.storage import load_html_memory, memory_lock, save_html_memory


def hash_content(content: str) -> str:
    return hashlib.sha256(content.strip().lower().encode()).hexdigest()[:16]


def is_meaningful_memory(content: str) -> bool:
    stripped = content.strip()
    if len(stripped) < 5:
        return False
    filler_patterns = (
        "um",
        "uh",
        "like",
        "you know",
        "okay",
        "ok",
        "hmm",
        "hm",
        "yeah",
        "yes",
        "no",
        "hey",
        "hi",
        "hello",
    )
    if stripped.lower() in filler_patterns:
        return False
    return True


def deduplicate_memory_entry(hashes: list[str], content: str) -> bool:
    return hash_content(content) in hashes


def build_context(session_id: str, user_input: str) -> str:
    memory = load_html_memory(session_id)
    history = memory.history
    recent = history[-15:]
    relevant: list[str] = []
    input_words = set(user_input.lower().split())
    for entry in recent:
        entry_text = str(entry.get("prompt") or entry.get("note") or "")
        if not entry_text:
            continue
        entry_words = set(entry_text.lower().split())
        if input_words & entry_words or len(relevant) < 5:
            relevant.append(entry_text)
    smart_entries = memory.smart_memory
    relevant_smart: list[str] = []
    for entry in smart_entries[-20:]:
        entry_content = entry.get("content", "")
        entry_words = set(entry_content.lower().split())
        if input_words & entry_words:
            relevant_smart.append(f"[{entry.get('type', 'context')}] {entry_content}")
    context_parts: list[str] = []
    if relevant_smart:
        context_parts.append("Remembered context:\n" + "\n".join(relevant_smart[-5:]))
    if relevant:
        context_parts.append("Recent interactions:\n" + "\n".join(f"- {r}" for r in relevant[-8:]))
    context = "\n\n".join(context_parts)
    if len(context) > 2000:
        context = context[:2000]
    return context


def store_smart_memory(session_id: str, content: str, memory_type: str = "context") -> dict:
    if not is_meaningful_memory(content):
        return load_html_memory(session_id).to_dict()
    if memory_type not in _config.MEMORY_TYPES:
        memory_type = "context"
    with memory_lock(session_id):
        memory = load_html_memory(session_id)
        if deduplicate_memory_entry(memory._hashes, content):
            return memory.to_dict()
        content_hash = hash_content(content)
        memory._hashes.append(content_hash)
        memory._hashes = memory._hashes[-200:]
        memory.smart_memory.append(
            {
                "type": memory_type,
                "content": content.strip()[:500],
                "timestamp": time.time(),
            }
        )
        if len(memory.smart_memory) > _config.MAX_MEMORY_ENTRIES:
            memory.smart_memory = memory.smart_memory[-_config.MAX_MEMORY_ENTRIES :]
        save_html_memory(memory, session_id)
        return memory.to_dict()
