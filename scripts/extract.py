#!/usr/bin/env python3
"""
Session Knowledge Extractor for Second Brain System

Reads JSONL session files from OpenClaw agents and extracts structured
knowledge using the configured LLM provider.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from utils.memory_io import load_config
from utils.llm_client import create_llm_client



# Constants
DEFAULT_MODEL = "claude-sonnet-4-20250514"
CHARS_PER_TOKEN = 4
MAX_TOKENS_PER_CHUNK = 100_000
TARGET_CHARS_PER_CHUNK = 300_000  # Conservative estimate
DEFAULT_SESSIONS_DIR = Path.home() / ".openclaw/agents/main/sessions"


EXTRACTION_PROMPT = """Analyze this conversation transcript and extract structured knowledge.

Be THOROUGH — extract specific facts, decisions, and details rather than summaries.

Extract:

1. **Facts & Preferences** — Concrete facts about people, their preferences, possessions, or characteristics
   - Format: "Person has/likes/uses/prefers X"
   - Include specific details like product names, versions, etc.

2. **Decisions Made** — Concrete decisions or choices made during the conversation
   - Format: Clear statement of what was decided and why (if given)
   - Include technical choices, approach decisions, etc.

3. **Action Items** — Tasks or todos mentioned
   - Format: Clear actionable statement
   - Note if item was marked completed in conversation
   - Use [x] for completed, [ ] for pending

4. **Technical Details** — Configuration, commands, setups, architectures discussed
   - Include code snippets, file paths, commands
   - Capture technical context and setup details

5. **People Mentioned** — Names of people referenced
   - Format: "**Name**: context about them or their relationship"

6. **Key Topics & Projects** — Main subjects and projects discussed
   - Brief description of each topic/project

Return your extraction in this exact format:

## Facts & Preferences
- fact 1
- fact 2

## Decisions Made
- decision 1
- decision 2

## Action Items
- [ ] pending item
- [x] completed item

## Technical Details
- detail 1
- detail 2

## People Mentioned
- **Name**: context
- **Name**: context

## Key Topics & Projects
- topic 1: description
- topic 2: description

If a section has no items, write "- None"

TRANSCRIPT:
"""


def get_default_llm_client() -> Any:
    """Create client from config.yaml, with sane defaults for legacy usage."""
    try:
        config = load_config()
    except Exception:
        config = {"api": {"provider": "anthropic", "model": DEFAULT_MODEL}}
    return create_llm_client(config)


def extract_text_content(content: Any) -> str:
    """Extract text from message content (handles both string and list formats)."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif isinstance(block, str):
                text_parts.append(block)
        return "\n".join(text_parts)

    return str(content)


def parse_session_file(session_path: Path) -> Dict[str, Any]:
    """Parse JSONL session file and extract metadata and messages."""
    session_id = None
    session_timestamp = None
    messages = []

    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"Warning: Skipping invalid JSON on line {line_num}: {e}", file=sys.stderr)
                    continue

                obj_type = obj.get("type")

                # Extract session metadata
                if obj_type == "session":
                    session_id = obj.get("id")
                    session_timestamp = obj.get("timestamp")

                # Extract messages (user and assistant only, skip toolResult)
                elif obj_type == "message":
                    message = obj.get("message", {})
                    role = message.get("role")

                    if role in ("user", "assistant"):
                        content = message.get("content", "")
                        text = extract_text_content(content)

                        if text.strip():
                            messages.append({
                                "role": role,
                                "text": text
                            })

    except FileNotFoundError:
        print(f"Error: File not found: {session_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading session file: {e}", file=sys.stderr)
        sys.exit(1)

    return {
        "session_id": session_id or session_path.stem,
        "session_timestamp": session_timestamp,
        "messages": messages,
        "file_path": str(session_path)
    }


def build_transcript(messages: List[Dict[str, str]]) -> str:
    """Build a formatted conversation transcript."""
    transcript_lines = []

    for msg in messages:
        role = msg["role"]
        text = msg["text"]

        label = "[User]" if role == "user" else "[Assistant]"
        transcript_lines.append(f"{label}: {text}")
        transcript_lines.append("")  # Empty line between messages

    return "\n".join(transcript_lines)


def chunk_transcript(transcript: str) -> List[str]:
    """Split transcript into chunks that fit within token limits."""
    if len(transcript) <= TARGET_CHARS_PER_CHUNK:
        return [transcript]

    chunks = []
    lines = transcript.split("\n")
    current_chunk = []
    current_size = 0

    for line in lines:
        line_size = len(line) + 1  # +1 for newline

        # If adding this line would exceed the limit, start a new chunk
        if current_size + line_size > TARGET_CHARS_PER_CHUNK and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_size = 0

        current_chunk.append(line)
        current_size += line_size

    # Add remaining chunk
    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def extract_with_llm(client: Any, transcript_chunk: str) -> str:
    """Send transcript chunk to configured LLM provider for extraction."""
    try:
        return client.generate(EXTRACTION_PROMPT + transcript_chunk, max_tokens=4096, temperature=0.1)
    except Exception as e:
        print(f"Error calling LLM provider: {e}", file=sys.stderr)
        raise


def merge_extractions(extractions: List[str]) -> str:
    """Merge multiple extraction results into a single unified output."""
    if len(extractions) == 1:
        return extractions[0]

    # Parse each extraction into sections
    sections = {
        "Facts & Preferences": [],
        "Decisions Made": [],
        "Action Items": [],
        "Technical Details": [],
        "People Mentioned": [],
        "Key Topics & Projects": []
    }

    for extraction in extractions:
        current_section = None

        for line in extraction.split("\n"):
            line = line.strip()

            # Check if this is a section header
            if line.startswith("## "):
                section_name = line[3:].strip()
                if section_name in sections:
                    current_section = section_name

            # Add content to current section
            elif line.startswith("- ") and current_section:
                item = line[2:].strip()
                if item and item != "None":
                    sections[current_section].append(item)

    # Build merged output
    output_lines = []

    for section_name, items in sections.items():
        output_lines.append(f"## {section_name}")

        if items:
            # Deduplicate while preserving order
            seen = set()
            unique_items = []
            for item in items:
                # Normalize for comparison (but keep original for output)
                normalized = item.lower().strip()
                if normalized not in seen:
                    seen.add(normalized)
                    unique_items.append(item)

            for item in unique_items:
                output_lines.append(f"- {item}")
        else:
            output_lines.append("- None")

        output_lines.append("")  # Empty line after section

    return "\n".join(output_lines).strip()


def parse_session(session_path) -> Dict[str, Any]:
    """Alias for parse_session_file (used by digest.py)."""
    return parse_session_file(Path(session_path))


def extract_memories(session_data: Dict[str, Any], client: Any = None) -> Dict[str, list]:
    """Extract structured memories from parsed session data.

    Returns a dict with keys: facts_preferences, decisions, action_items,
    technical_details, people, topics_projects.
    Used by digest.py for merging across sessions.
    """
    if client is None:
        client = get_default_llm_client()

    messages = session_data.get("messages", [])
    if not messages:
        return {k: [] for k in [
            "facts_preferences", "decisions", "action_items",
            "technical_details", "people", "topics_projects"
        ]}

    transcript = build_transcript(messages)
    chunks = chunk_transcript(transcript)

    extractions = []
    for chunk in chunks:
        extraction = extract_with_llm(client, chunk)
        extractions.append(extraction)

    merged = merge_extractions(extractions)

    # Parse the merged markdown into structured dict
    section_map = {
        "Facts & Preferences": "facts_preferences",
        "Decisions Made": "decisions",
        "Action Items": "action_items",
        "Technical Details": "technical_details",
        "People Mentioned": "people",
        "Key Topics & Projects": "topics_projects",
    }

    result = {v: [] for v in section_map.values()}
    current_key = None

    for line in merged.split("\n"):
        line = line.strip()
        if line.startswith("## "):
            section_name = line[3:].strip()
            current_key = section_map.get(section_name)
        elif line.startswith("- ") and current_key:
            item = line[2:].strip()
            if item and item != "None":
                result[current_key].append(item)

    return result


def process_session(client: Any, session_path: Path) -> str:
    """Process a single session file and return extracted markdown."""
    print(f"Processing: {session_path}", file=sys.stderr)

    # Parse session file
    session_data = parse_session_file(session_path)
    session_id = session_data["session_id"]
    session_timestamp = session_data["session_timestamp"]
    messages = session_data["messages"]

    print(f"  Session ID: {session_id}", file=sys.stderr)
    print(f"  Messages: {len(messages)}", file=sys.stderr)

    if not messages:
        print("  Warning: No messages found in session", file=sys.stderr)
        return format_output(session_id, session_timestamp, "## Facts & Preferences\n- None\n\n## Decisions Made\n- None\n\n## Action Items\n- None\n\n## Technical Details\n- None\n\n## People Mentioned\n- None\n\n## Key Topics & Projects\n- None")

    # Build transcript
    transcript = build_transcript(messages)
    print(f"  Transcript length: {len(transcript):,} chars", file=sys.stderr)

    # Chunk transcript if needed
    chunks = chunk_transcript(transcript)
    print(f"  Chunks: {len(chunks)}", file=sys.stderr)

    # Extract from each chunk
    extractions = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  Processing chunk {i}/{len(chunks)}...", file=sys.stderr)
        extraction = extract_with_llm(client, chunk)
        extractions.append(extraction)

    # Merge extractions
    print("  Merging results...", file=sys.stderr)
    merged = merge_extractions(extractions)

    # Format final output
    output = format_output(session_id, session_timestamp, merged)

    print(f"  Done!", file=sys.stderr)
    return output


def format_output(session_id: str, session_timestamp: Optional[str], extraction: str) -> str:
    """Format the final markdown output."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    output_lines = [
        f"# Session Memory: {session_id}",
        f"*Extracted: {now}*",
    ]

    if session_timestamp:
        output_lines.append(f"*Session date: {session_timestamp}*")

    output_lines.append("")
    output_lines.append(extraction)

    return "\n".join(output_lines)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract structured knowledge from OpenClaw session files ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 extract.py session.jsonl
  python3 extract.py session.jsonl --output memory.md
  python3 extract.py session1.jsonl session2.jsonl --output combined.md
        """
    )

    parser.add_argument(
        "session_files",
        nargs="+",
        type=Path,
        help="Session JSONL file(s) to process"
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file (default: stdout)"
    )

    args = parser.parse_args()

    # Initialize configured LLM client
    client = get_default_llm_client()

    # Process each session file
    all_outputs = []

    for session_file in args.session_files:
        try:
            output = process_session(client, session_file)
            all_outputs.append(output)
        except Exception as e:
            print(f"Error processing {session_file}: {e}", file=sys.stderr)
            continue

    if not all_outputs:
        print("Error: No sessions were successfully processed", file=sys.stderr)
        sys.exit(1)

    # Combine outputs
    final_output = "\n\n---\n\n".join(all_outputs)

    # Write output
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(final_output)
        print(f"\nOutput written to: {args.output}", file=sys.stderr)
    else:
        print(final_output)


if __name__ == "__main__":
    main()
