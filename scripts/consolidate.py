#!/usr/bin/env python3
"""
Auto-Consolidation Engine for Second Brain v2

Automatically consolidates daily memories into MEMORY.md with smart deduplication.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

# Add utils to path
sys.path.append(str(Path(__file__).parent))

from utils.memory_io import (
    load_config, get_memory_files, read_memory_file,
    write_memory_file, load_memory_index, parse_memory_sections
)
from utils.llm_client import create_llm_client


CONSOLIDATION_PROMPT = """You are a memory consolidation assistant. Your job is to merge new memories into existing long-term memory while avoiding duplication.

EXISTING LONG-TERM MEMORY:
{existing_memory}

NEW MEMORIES TO CONSOLIDATE:
{new_memories}

TASK:
1. **Identify high-value memories** from the new memories that should be preserved long-term
2. **Avoid duplication** - don't add information that's already in existing memory
3. **Merge related information** - update existing entries rather than creating duplicates
4. **Categorize properly** - organize into the standard memory sections
5. **Preserve important details** - keep specific facts, decisions, preferences, names, dates

CATEGORIES TO USE:
- **Facts & Preferences**: Concrete facts about people, their preferences, tools they use
- **Decisions Made**: Important decisions with reasoning 
- **Key People**: People mentioned with context about relationships/roles
- **Projects & Tools**: Software projects, tools, systems being worked on
- **Technical Knowledge**: Commands, configurations, architectures
- **Action Items**: Important ongoing or completed tasks
- **Insights & Lessons**: Valuable insights learned

RULES:
- Only include memories with lasting value (skip temporary notes, casual chat)
- If something exists in current memory, enhance it rather than duplicate
- Use specific names, dates, and details - avoid generic statements
- Mark completed action items with [x]
- Keep entries concise but informative

Return your response in this exact format:

## Facts & Preferences
- Updated fact 1
- New fact 2

## Decisions Made
- Decision with date and reasoning

## Key People
- **Name**: Updated context

## Projects & Tools
- Project: Updated status/info

## Technical Knowledge
- Technical detail with specifics

## Action Items
- [ ] Pending action
- [x] Completed action

## Insights & Lessons
- Valuable lesson learned

For each section, include ONLY the changes/additions. If no changes are needed for a section, write "- No changes"
"""


def load_existing_memory(memory_md_path: Path) -> Dict[str, Any]:
    """Load and parse existing MEMORY.md file."""
    if not memory_md_path.exists():
        return {
            'content': '',
            'sections': {},
            'last_modified': None
        }
    
    with open(memory_md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    sections = parse_memory_sections(content)
    stat = memory_md_path.stat()
    
    return {
        'content': content,
        'sections': sections,
        'last_modified': datetime.fromtimestamp(stat.st_mtime)
    }


def collect_recent_memories(
    memory_dir: Path,
    days_back: int = 7,
    min_score: float = 0.5
) -> List[Dict[str, Any]]:
    """Collect recent memory files for consolidation."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)
    
    memory_files = get_memory_files(memory_dir, (start_date, end_date))
    
    recent_memories = []
    for file_path in memory_files:
        memory_data = read_memory_file(file_path)
        
        # Add score information if available from memory index
        memory_data['score'] = 1.0  # Default score
        
        recent_memories.append(memory_data)
    
    return recent_memories


def format_memories_for_consolidation(memories: List[Dict[str, Any]]) -> str:
    """Format memories for the consolidation prompt."""
    output = []
    
    for memory in memories:
        file_name = Path(memory['path']).name
        sections = memory.get('sections', {})
        
        if not sections:
            continue
        
        output.append(f"### {file_name}")
        
        for section_name, items in sections.items():
            if not items:
                continue
            
            # Format section header
            header = section_name.replace('_', ' ').title()
            output.append(f"**{header}:**")
            
            for item in items[:10]:  # Limit to top 10 items per section
                output.append(f"- {item}")
            
            if len(items) > 10:
                output.append(f"- ... and {len(items) - 10} more items")
            
            output.append("")
        
        output.append("")
    
    return "\n".join(output)


def detect_duplicates(existing_memory: str, new_item: str, threshold: float = 0.8) -> bool:
    """Detect if a new memory item is a duplicate of existing content."""
    # Simple similarity check based on word overlap
    existing_lower = existing_memory.lower()
    new_lower = new_item.lower()
    
    # Extract key words (remove common words)
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    
    def extract_key_words(text):
        words = re.findall(r'\b\w+\b', text.lower())
        return set(w for w in words if len(w) > 2 and w not in stop_words)
    
    existing_words = extract_key_words(existing_memory)
    new_words = extract_key_words(new_item)
    
    if not new_words:
        return False
    
    # Calculate overlap
    overlap = len(existing_words & new_words)
    overlap_ratio = overlap / len(new_words)
    
    return overlap_ratio >= threshold


def parse_consolidation_output(output: str) -> Dict[str, List[str]]:
    """Parse the AI's consolidation output into sections."""
    sections = {}
    current_section = None
    current_items = []
    
    lines = output.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check for section headers
        if line.startswith('## '):
            # Save previous section
            if current_section:
                sections[current_section] = current_items
            
            # Start new section
            section_name = line[3:].strip().lower().replace(' & ', '_&_').replace(' ', '_')
            current_section = section_name
            current_items = []
        
        elif line.startswith('- ') and current_section:
            item = line[2:].strip()
            if item and item != "No changes":
                current_items.append(item)
    
    # Don't forget the last section
    if current_section:
        sections[current_section] = current_items
    
    return sections


def merge_memory_sections(
    existing_sections: Dict[str, List[str]],
    new_sections: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    """Merge new sections into existing memory sections."""
    merged = existing_sections.copy()
    
    for section_name, new_items in new_sections.items():
        if section_name not in merged:
            merged[section_name] = []
        
        existing_items = merged[section_name]
        
        # Add new items that aren't duplicates
        for item in new_items:
            is_duplicate = any(
                detect_duplicates(existing_item, item) 
                for existing_item in existing_items
            )
            
            if not is_duplicate:
                merged[section_name].append(item)
    
    return merged


def format_memory_md(sections: Dict[str, List[str]], metadata: Dict[str, Any] = None) -> str:
    """Format sections back into MEMORY.md format."""
    output = []
    
    # Add header
    output.append("# MEMORY.md - Long-Term Memory")
    output.append("")
    
    if metadata:
        last_updated = metadata.get('last_consolidated', datetime.now())
        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
        output.append(f"*Last consolidated: {last_updated.strftime('%Y-%m-%d %H:%M:%S')}*")
        output.append("")
    
    # Standard section order
    section_order = [
        'facts_&_preferences',
        'decisions_made',
        'key_people', 
        'projects_&_tools',
        'technical_knowledge',
        'action_items',
        'insights_&_lessons'
    ]
    
    # Output ordered sections
    for section in section_order:
        if section in sections and sections[section]:
            # Format header
            header = section.replace('_', ' ').title().replace('&', '&')
            output.append(f"## {header}")
            output.append("")
            
            # Add items
            for item in sections[section]:
                output.append(f"- {item}")
            output.append("")
    
    # Add any extra sections not in the standard order
    for section_name, items in sections.items():
        if section_name not in section_order and items:
            header = section_name.replace('_', ' ').title()
            output.append(f"## {header}")
            output.append("")
            for item in items:
                output.append(f"- {item}")
            output.append("")
    
    return "\n".join(output)


def consolidate_memories(
    config: Dict[str, Any],
    days_back: int = 7,
    dry_run: bool = True,
    interactive: bool = False
) -> Dict[str, Any]:
    """Main consolidation function."""
    
    memory_dir = Path(config['memory_dir']).expanduser()
    memory_md_path = Path(config['memory_md']).expanduser()
    
    # Load existing memory
    existing_memory = load_existing_memory(memory_md_path)
    
    # Collect recent memories
    consolidation_config = config.get('consolidation', {})
    min_score = consolidation_config.get('min_score', 0.5)
    
    recent_memories = collect_recent_memories(memory_dir, days_back, min_score)
    
    if not recent_memories:
        return {
            'status': 'no_memories',
            'message': f'No memories found in the last {days_back} days'
        }
    
    print(f"Found {len(recent_memories)} recent memory files to consolidate")
    
    # Format for AI prompt
    existing_content = existing_memory['content'] or "No existing long-term memory."
    new_memories_text = format_memories_for_consolidation(recent_memories)
    
    if not new_memories_text.strip():
        return {
            'status': 'no_content',
            'message': 'No consolidatable content found in recent memories'
        }
    
    # Get AI consolidation suggestions
    try:
        client = create_llm_client(config)
        
        prompt = CONSOLIDATION_PROMPT.format(
            existing_memory=existing_content,
            new_memories=new_memories_text
        )
        
        ai_output = client.generate(prompt, max_tokens=4000, temperature=0.1)
        
    except Exception as e:
        return {
            'status': 'error',
            'message': f'AI consolidation failed: {e}'
        }
    
    # Parse AI suggestions
    new_sections = parse_consolidation_output(ai_output)
    
    if not new_sections or all(not items for items in new_sections.values()):
        return {
            'status': 'no_suggestions',
            'message': 'AI found no new memories worth consolidating'
        }
    
    # Merge with existing memory
    merged_sections = merge_memory_sections(existing_memory['sections'], new_sections)
    
    # Generate new MEMORY.md content
    metadata = {
        'last_consolidated': datetime.now().isoformat(),
        'consolidated_files': [m['path'] for m in recent_memories],
        'total_additions': sum(len(items) for items in new_sections.values())
    }
    
    new_content = format_memory_md(merged_sections, metadata)
    
    result = {
        'status': 'success',
        'existing_sections': len(existing_memory['sections']),
        'new_sections': new_sections,
        'merged_sections': len(merged_sections),
        'total_additions': metadata['total_additions'],
        'new_content': new_content,
        'ai_output': ai_output
    }
    
    # Handle dry run
    if dry_run:
        print("\n📋 DRY RUN - Consolidation Preview")
        print("=" * 50)
        print(f"Would add {metadata['total_additions']} new memory items")
        print(f"Files processed: {len(recent_memories)}")
        print("\nProposed additions by section:")
        for section, items in new_sections.items():
            if items:
                section_name = section.replace('_', ' ').title()
                print(f"\n{section_name}: ({len(items)} items)")
                for item in items[:3]:  # Show first 3 items
                    print(f"  + {item}")
                if len(items) > 3:
                    print(f"  + ... and {len(items) - 3} more")
        
        print(f"\nTo apply these changes, run with --apply")
        return result
    
    # Interactive mode
    if interactive:
        print("\n🤔 Interactive Consolidation")
        print("=" * 40)
        
        for section, items in new_sections.items():
            if not items:
                continue
            
            section_name = section.replace('_', ' ').title()
            print(f"\n{section_name}: {len(items)} items")
            
            for item in items:
                print(f"  + {item}")
            
            while True:
                choice = input(f"\nAdd these {len(items)} items to {section_name}? [y/n/s(skip)]: ").lower()
                if choice in ['y', 'yes']:
                    break
                elif choice in ['n', 'no']:
                    new_sections[section] = []
                    break
                elif choice in ['s', 'skip']:
                    new_sections[section] = []
                    break
                else:
                    print("Please answer y, n, or s")
        
        # Re-merge after interactive filtering
        merged_sections = merge_memory_sections(existing_memory['sections'], new_sections)
        new_content = format_memory_md(merged_sections, metadata)
        
        final_additions = sum(len(items) for items in new_sections.values())
        if final_additions == 0:
            print("\nNo changes selected. Exiting.")
            return {'status': 'cancelled', 'message': 'User cancelled all changes'}
    
    # Apply changes
    backup = consolidation_config.get('backup_memory_md', True)
    write_memory_file(memory_md_path, new_content, backup)
    
    print(f"\n✅ Consolidation complete!")
    print(f"Added {metadata['total_additions']} new memory items")
    print(f"Updated: {memory_md_path}")
    
    if backup:
        print(f"Backup saved: {memory_md_path}.bak")
    
    return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Consolidate recent memories into MEMORY.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 consolidate.py --dry-run              # Preview consolidation
  python3 consolidate.py --days 7 --apply      # Consolidate last 7 days
  python3 consolidate.py --interactive         # Interactive consolidation
  python3 consolidate.py --apply --no-backup   # Apply without backup
        """
    )
    
    parser.add_argument(
        '--config',
        type=Path,
        help='Path to configuration file'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days back to consolidate (default: 7)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Preview changes without applying (default)'
    )
    
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Apply consolidation changes (overrides --dry-run)'
    )
    
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Interactive mode - confirm each section'
    )
    
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Do not create backup of MEMORY.md'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show verbose output including AI reasoning'
    )
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        config = load_config(args.config)
        
        # Override backup setting
        if args.no_backup:
            config.setdefault('consolidation', {})['backup_memory_md'] = False
        
        # Determine run mode
        dry_run = args.dry_run and not args.apply
        
        print(f"🧠 Memory Consolidation ({'DRY RUN' if dry_run else 'APPLY MODE'})")
        print(f"Processing memories from last {args.days} days")
        
        # Run consolidation
        result = consolidate_memories(
            config=config,
            days_back=args.days,
            dry_run=dry_run,
            interactive=args.interactive
        )
        
        # Show results
        status = result.get('status')
        if status == 'success':
            if args.verbose and 'ai_output' in result:
                print("\n🤖 AI Consolidation Reasoning:")
                print("-" * 40)
                print(result['ai_output'])
        elif status in ['no_memories', 'no_content', 'no_suggestions']:
            print(f"ℹ️  {result['message']}")
        elif status == 'error':
            print(f"❌ {result['message']}", file=sys.stderr)
            sys.exit(1)
        elif status == 'cancelled':
            print(f"🚫 {result['message']}")
        
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()