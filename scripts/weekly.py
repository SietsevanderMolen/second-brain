#!/usr/bin/env python3
"""
Weekly analysis script for second brain system.
Analyzes daily memory files from the past 7 days and produces a weekly summary.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.memory_io import load_config
from utils.llm_client import create_llm_client


def get_week_number(date: datetime) -> str:
    """
    Get ISO week number in format WNN.

    Args:
        date: The date to get the week number for

    Returns:
        str: Week number in format WNN (e.g., W06)
    """
    return f"W{date.isocalendar()[1]:02d}"


def get_date_range(end_date: datetime) -> List[datetime]:
    """
    Get list of dates for the 7 days leading up to and including end_date.

    Args:
        end_date: The last day of the week

    Returns:
        List of datetime objects for each day in the week
    """
    return [end_date - timedelta(days=i) for i in range(6, -1, -1)]


def find_memory_files(dates: List[datetime], memory_dir: Path) -> List[Tuple[datetime, Path]]:
    """
    Find memory files that exist for the given dates.

    Args:
        dates: List of dates to look for
        memory_dir: Directory containing memory files

    Returns:
        List of tuples (date, file_path) for files that exist
    """
    found_files = []
    for date in dates:
        filename = f"{date.strftime('%Y-%m-%d')}.md"
        filepath = memory_dir / filename
        if filepath.exists():
            found_files.append((date, filepath))
    return found_files


def read_memory_files(files: List[Tuple[datetime, Path]]) -> str:
    """
    Read and concatenate memory files with date headers.

    Args:
        files: List of tuples (date, file_path)

    Returns:
        Concatenated content of all files with date headers
    """
    content_parts = []
    for date, filepath in files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                file_content = f.read()
                content_parts.append(f"# {date.strftime('%Y-%m-%d')}\n\n{file_content}")
        except Exception as e:
            print(f"Warning: Failed to read {filepath}: {e}", file=sys.stderr)

    return "\n\n---\n\n".join(content_parts)


def create_analysis_prompt(content: str, start_date: datetime, end_date: datetime) -> str:
    """
    Create the prompt for Claude to analyze the weekly memory files.

    Args:
        content: Concatenated memory file contents
        start_date: First day of the week
        end_date: Last day of the week

    Returns:
        The prompt string
    """
    return f"""You are analyzing a week of daily memory entries from a personal "second brain" system.

The entries cover {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}.

Please analyze these entries and provide a comprehensive weekly summary with the following sections:

1. **Key Decisions**: Important decisions made this week and their outcomes (if mentioned)
2. **Open Action Items**: Tasks or items that are still pending or in progress
3. **Facts & Preferences Learned**: New information, preferences, or insights discovered
4. **Projects & Progress**: Projects worked on, organized by project name, with progress notes
5. **Patterns & Observations**: Notable patterns such as what takes most time, recurring blockers, work habits
6. **Recommendations for Next Week**: Actionable suggestions based on the week's patterns

Format your response as markdown with clear headers and bullet points. For open action items, use markdown checkboxes (- [ ]).

Here are the daily entries:

{content}
"""


def analyze_week(content: str, start_date: datetime, end_date: datetime, llm_client) -> str:
    """Send memory files to the configured LLM provider for weekly analysis."""
    prompt = create_analysis_prompt(content, start_date, end_date)

    print("Sending to configured LLM provider for analysis...", file=sys.stderr)

    return llm_client.generate(prompt, max_tokens=4096, temperature=0.1)


def format_output(
    analysis: str,
    start_date: datetime,
    end_date: datetime,
    days_with_entries: int
) -> str:
    """
    Format the final output with header information.

    Args:
        analysis: Claude's analysis text
        start_date: First day of the week
        end_date: Last day of the week
        days_with_entries: Number of days that had memory entries

    Returns:
        Formatted markdown output
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    header = f"""# Weekly Summary: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}
*Generated: {now}*
*Days with entries: {days_with_entries}/7*

"""

    return header + analysis


def main():
    """Main entry point for the weekly analysis script."""
    parser = argparse.ArgumentParser(
        description="Generate weekly analysis of daily memory files"
    )
    parser.add_argument(
        "--date",
        type=str,
        help="End date for the week (YYYY-MM-DD format, default: today)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Override output file path"
    )

    args = parser.parse_args()

    # Parse end date
    if args.date:
        try:
            end_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"Error: Invalid date format '{args.date}'. Use YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
    else:
        end_date = datetime.now()

    # Get date range
    dates = get_date_range(end_date)
    start_date = dates[0]

    # Find memory files
    memory_dir = Path.home() / "workspace" / "memory"
    if not memory_dir.exists():
        print(f"Error: Memory directory not found: {memory_dir}", file=sys.stderr)
        sys.exit(1)

    files = find_memory_files(dates, memory_dir)

    if not files:
        print(f"Error: No memory files found for the week {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} memory files for analysis:", file=sys.stderr)
    for date, filepath in files:
        print(f"  - {date.strftime('%Y-%m-%d')}", file=sys.stderr)

    # Read files
    content = read_memory_files(files)

    if not content.strip():
        print("Error: No content found in memory files", file=sys.stderr)
        sys.exit(1)

    # Initialize configured LLM client
    try:
        config = load_config()
        llm_client = create_llm_client(config)
    except Exception as e:
        print(f"Error initializing LLM client: {e}", file=sys.stderr)
        sys.exit(1)

    # Analyze
    try:
        analysis = analyze_week(content, start_date, end_date, llm_client)
    except Exception as e:
        print(f"Error during API call: {e}", file=sys.stderr)
        sys.exit(1)

    # Format output
    output_text = format_output(analysis, start_date, end_date, len(files))

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        weekly_dir = memory_dir / "weekly"
        weekly_dir.mkdir(exist_ok=True)
        week_number = get_week_number(end_date)
        output_filename = f"{end_date.year}-{week_number}.md"
        output_path = weekly_dir / output_filename

    # Write output
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"\nWeekly summary written to: {output_path}", file=sys.stderr)
    except Exception as e:
        print(f"Error writing output file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
