#!/usr/bin/env python3
"""
Daily Digest Builder for Second Brain System

Scans all session files modified on a given date, extracts memories from each,
deduplicates and merges them into a single daily digest, then appends to the
daily memory file.

Usage:
    python3 digest.py [--date YYYY-MM-DD]
"""

import sys
import os
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Set
import json

# Import from extract.py in the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import parse_session, extract_memories


SESSIONS_DIR = Path.home() / ".openclaw" / "agents" / "main" / "sessions"
MEMORY_DIR = Path.home() / "workspace" / "memory"


def get_sessions_for_date(target_date: date) -> List[Path]:
    """
    Find all .jsonl session files modified on the given date.

    Args:
        target_date: The date to filter by

    Returns:
        List of Path objects for matching session files
    """
    if not SESSIONS_DIR.exists():
        print(f"Warning: Sessions directory does not exist: {SESSIONS_DIR}", file=sys.stderr)
        return []

    matching_sessions = []

    for session_file in SESSIONS_DIR.glob("*.jsonl"):
        if not session_file.is_file():
            continue

        # Get modification time
        mtime = datetime.fromtimestamp(session_file.stat().st_mtime)

        # Check if it matches the target date
        if mtime.date() == target_date:
            matching_sessions.append(session_file)

    # Sort by modification time
    matching_sessions.sort(key=lambda p: p.stat().st_mtime)

    return matching_sessions


def normalize_text(text: str) -> str:
    """Normalize text for deduplication (lowercase, strip whitespace)."""
    return text.lower().strip()


def deduplicate_list(items: List[str]) -> List[str]:
    """
    Remove duplicate items from a list while preserving order.
    Uses normalized text for comparison but keeps original formatting.

    Args:
        items: List of strings to deduplicate

    Returns:
        Deduplicated list preserving original formatting
    """
    seen: Set[str] = set()
    result: List[str] = []

    for item in items:
        normalized = normalize_text(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(item)

    return result


def merge_memories(all_memories: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Merge and deduplicate memories from multiple sessions.

    Args:
        all_memories: List of memory dictionaries from different sessions

    Returns:
        Merged dictionary with deduplicated lists
    """
    merged = {
        "facts_preferences": [],
        "decisions": [],
        "action_items": [],
        "technical_details": [],
        "people": [],
        "topics_projects": []
    }

    # Collect all items from each category
    for memories in all_memories:
        for key in merged.keys():
            if key in memories and isinstance(memories[key], list):
                merged[key].extend(memories[key])

    # Deduplicate each category
    for key in merged.keys():
        merged[key] = deduplicate_list(merged[key])

    return merged


def format_digest(merged_memories: Dict[str, List[str]],
                  session_count: int,
                  session_files: List[Path]) -> str:
    """
    Format the merged memories into a markdown digest.

    Args:
        merged_memories: Deduplicated and merged memories
        session_count: Number of sessions processed
        session_files: List of session file paths

    Returns:
        Formatted markdown string
    """
    timestamp = datetime.now().isoformat(timespec='seconds')

    lines = [
        "",
        "## Auto-Extracted from Sessions",
        f"*Generated: {timestamp}*",
        f"*Sessions processed: {session_count}*",
        ""
    ]

    # Add session file names for reference
    if session_files:
        lines.append("<details>")
        lines.append("<summary>Session files processed</summary>")
        lines.append("")
        for session_file in session_files:
            lines.append(f"- `{session_file.name}`")
        lines.append("</details>")
        lines.append("")

    # Facts & Preferences
    if merged_memories["facts_preferences"]:
        lines.append("### Facts & Preferences")
        for item in merged_memories["facts_preferences"]:
            lines.append(f"- {item}")
        lines.append("")

    # Decisions Made
    if merged_memories["decisions"]:
        lines.append("### Decisions Made")
        for item in merged_memories["decisions"]:
            lines.append(f"- {item}")
        lines.append("")

    # Action Items
    if merged_memories["action_items"]:
        lines.append("### Action Items")
        for item in merged_memories["action_items"]:
            # Check if item already has checkbox format
            if item.strip().startswith("- [ ]") or item.strip().startswith("- [x]"):
                lines.append(item)
            else:
                lines.append(f"- [ ] {item}")
        lines.append("")

    # Technical Details
    if merged_memories["technical_details"]:
        lines.append("### Technical Details")
        for item in merged_memories["technical_details"]:
            lines.append(f"- {item}")
        lines.append("")

    # People Mentioned
    if merged_memories["people"]:
        lines.append("### People Mentioned")
        for item in merged_memories["people"]:
            # Check if already formatted as "**Name**: context"
            if "**" in item and ":" in item:
                lines.append(f"- {item}")
            else:
                lines.append(f"- {item}")
        lines.append("")

    # Key Topics & Projects
    if merged_memories["topics_projects"]:
        lines.append("### Key Topics & Projects")
        for item in merged_memories["topics_projects"]:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def append_to_memory_file(target_date: date, digest_content: str) -> None:
    """
    Append the digest to the daily memory file, creating it if necessary.

    Args:
        target_date: The date for the memory file
        digest_content: The formatted digest content to append
    """
    # Ensure memory directory exists
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    # Format: YYYY-MM-DD.md
    filename = f"{target_date.isoformat()}.md"
    memory_file = MEMORY_DIR / filename

    # Check if file exists
    if memory_file.exists():
        # Append to existing file
        with open(memory_file, "a", encoding="utf-8") as f:
            f.write(digest_content)
        print(f"Appended digest to existing memory file: {memory_file}")
    else:
        # Create new file with a basic header
        with open(memory_file, "w", encoding="utf-8") as f:
            f.write(f"# Memory - {target_date.isoformat()}\n")
            f.write(digest_content)
        print(f"Created new memory file: {memory_file}")


def main():
    """Main entry point for the digest builder."""
    parser = argparse.ArgumentParser(
        description="Build a daily digest from session files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 digest.py                    # Process sessions from today
  python3 digest.py --date 2026-02-11  # Process sessions from a specific date
        """
    )

    parser.add_argument(
        "--date",
        type=str,
        help="Target date in YYYY-MM-DD format (default: today)"
    )

    args = parser.parse_args()

    # Determine target date
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"Error: Invalid date format '{args.date}'. Use YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
    else:
        target_date = date.today()

    print(f"Building digest for: {target_date.isoformat()}")

    # Find all sessions for the target date
    session_files = get_sessions_for_date(target_date)

    if not session_files:
        print(f"No session files found for {target_date.isoformat()}")
        print(f"Searched in: {SESSIONS_DIR}")
        return

    print(f"Found {len(session_files)} session(s)")

    # Process each session
    all_memories = []
    processed_count = 0

    for i, session_file in enumerate(session_files, 1):
        print(f"[{i}/{len(session_files)}] Processing: {session_file.name}")

        try:
            # Parse session
            session_data = parse_session(str(session_file))

            # Extract memories
            memories = extract_memories(session_data)

            if memories and any(memories.values()):
                all_memories.append(memories)
                processed_count += 1
            else:
                print(f"  Warning: No memories extracted from {session_file.name}")

        except Exception as e:
            print(f"  Error processing {session_file.name}: {e}", file=sys.stderr)
            continue

    if not all_memories:
        print("No memories extracted from any session.")
        return

    print(f"\nMerging memories from {processed_count} session(s)...")

    # Merge and deduplicate
    merged_memories = merge_memories(all_memories)

    # Count total items
    total_items = sum(len(items) for items in merged_memories.values())
    print(f"Total unique items extracted: {total_items}")

    # Format digest
    digest_content = format_digest(merged_memories, processed_count, session_files)

    # Append to memory file
    append_to_memory_file(target_date, digest_content)

    print("\nDigest complete!")
    print(f"Memory file: {MEMORY_DIR / f'{target_date.isoformat()}.md'}")


if __name__ == "__main__":
    main()
