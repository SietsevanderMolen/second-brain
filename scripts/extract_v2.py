#!/usr/bin/env python3
"""
Enhanced Memory Extraction for Second Brain v2

Extends original extract.py with structured JSON output, entity extraction,
and better chunking for large sessions.
"""

import argparse
import json
import os
import sys
import re
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Add utils to path
sys.path.append(str(Path(__file__).parent))

from utils.memory_io import (
    load_config, extract_text_content,
    find_session_files, ensure_memory_dir
)
from utils.llm_client import create_llm_client


# Enhanced extraction prompt with entity extraction
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

7. **Entities** — Extract key entities for relationship mapping
   - People: All names mentioned
   - Projects: Software projects, initiatives, tools
   - Technologies: Programming languages, frameworks, APIs
   - Locations: Cities, places, servers, URLs
   - Organizations: Companies, teams, groups

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

## Entities
**People**: Name1, Name2, Name3
**Projects**: Project1, Project2
**Technologies**: Tech1, Tech2, Tech3
**Locations**: Location1, Location2
**Organizations**: Org1, Org2

If a section has no items, write "- None"

TRANSCRIPT:
"""


def parse_session(session_path: Path) -> List[Dict[str, Any]]:
    """Parse a JSONL session file into messages."""
    messages = []
    
    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    messages.append(data)
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON on line {line_num} in {session_path}: {e}", 
                          file=sys.stderr)
                    continue
    
    except IOError as e:
        print(f"Error reading session file {session_path}: {e}", file=sys.stderr)
        return []
    
    return messages


def extract_entities_from_text(text: str) -> Dict[str, List[str]]:
    """Extract entities from text using pattern matching."""
    entities = {
        'people': [],
        'projects': [],
        'technologies': [],
        'locations': [],
        'organizations': []
    }
    
    # Simple patterns for entity extraction
    # People: Names (capitalized words, common name patterns)
    name_patterns = [
        r'\b([A-Z][a-z]+ [A-Z][a-z]+)\b',  # First Last
        r'\b([A-Z][a-z]{2,})\b',           # Single names
    ]
    
    # Technologies: Common tech keywords
    tech_keywords = [
        'python', 'javascript', 'typescript', 'java', 'rust', 'go', 'c++',
        'react', 'vue', 'angular', 'django', 'flask', 'fastapi', 'express',
        'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'github', 'git',
        'openai', 'anthropic', 'claude', 'gpt', 'llm', 'api', 'rest', 'graphql',
        'postgres', 'mysql', 'redis', 'mongodb', 'sqlite'
    ]
    
    # Projects: Words ending in common project suffixes or starting with common prefixes
    project_patterns = [
        r'\b([A-Z][a-zA-Z]*(?:Bot|Agent|App|Tool|Service|API|SDK))\b',
        r'\b(second-brain|openclaw|clawdbot|dpudebugagent)\b',
    ]
    
    # Extract using patterns
    text_lower = text.lower()
    
    # Extract people names
    for pattern in name_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if len(match) > 2 and match.lower() not in ['the', 'and', 'for', 'but']:
                entities['people'].append(match)
    
    # Extract technologies
    for tech in tech_keywords:
        if tech in text_lower:
            entities['technologies'].append(tech.title())
    
    # Extract projects
    for pattern in project_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        entities['projects'].extend(matches)
    
    # Deduplicate
    for key in entities:
        entities[key] = list(set(entities[key]))
    
    return entities


def parse_extracted_sections(content: str) -> Dict[str, Any]:
    """Parse the extracted content into structured sections."""
    sections = {}
    current_section = None
    current_items = []
    
    lines = content.split('\n')
    
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
            current_section = line[3:].strip().lower().replace(' & ', '_').replace(' ', '_')
            current_items = []
        
        elif line.startswith('- ') and current_section:
            item = line[2:].strip()
            if item and item != "None":
                current_items.append(item)
        
        elif current_section == "entities":
            # Parse entity lists
            if line.startswith('**') and ':' in line:
                entity_type, entity_list = line.split(':', 1)
                entity_type = entity_type.strip('*').lower()
                entities = [e.strip() for e in entity_list.split(',') if e.strip()]
                sections[f"entities_{entity_type}"] = entities
    
    # Don't forget the last section
    if current_section and current_section != "entities":
        sections[current_section] = current_items
    
    return sections


def chunk_messages(
    messages: List[Dict[str, Any]], 
    max_chars: int = 300000,
    overlap_chars: int = 1000
) -> List[str]:
    """Split messages into chunks for processing."""
    chunks = []
    current_chunk = []
    current_size = 0
    
    for message in messages:
        # Extract message content
        content = ""
        if 'role' in message and 'content' in message:
            content = extract_text_content(message['content'])
        elif 'messages' in message:  # Nested structure
            for msg in message['messages']:
                content += extract_text_content(msg.get('content', '')) + "\n"
        
        message_size = len(content)
        
        # If single message is too large, split it
        if message_size > max_chars:
            # Save current chunk if not empty
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_size = 0
            
            # Split large message
            words = content.split()
            chunk_words = []
            chunk_size = 0
            
            for word in words:
                word_size = len(word) + 1  # +1 for space
                if chunk_size + word_size > max_chars and chunk_words:
                    chunks.append(" ".join(chunk_words))
                    
                    # Keep overlap
                    overlap_words = chunk_words[-overlap_chars//10:]  # Rough overlap
                    chunk_words = overlap_words + [word]
                    chunk_size = sum(len(w) + 1 for w in chunk_words)
                else:
                    chunk_words.append(word)
                    chunk_size += word_size
            
            if chunk_words:
                chunks.append(" ".join(chunk_words))
        
        # Add to current chunk if it fits
        elif current_size + message_size <= max_chars:
            current_chunk.append(content)
            current_size += message_size
        else:
            # Save current chunk and start new one
            if current_chunk:
                chunks.append("\n".join(current_chunk))
            
            # Start new chunk with overlap
            if chunks and overlap_chars > 0:
                last_chunk = chunks[-1][-overlap_chars:]
                current_chunk = [last_chunk, content]
                current_size = len(last_chunk) + message_size
            else:
                current_chunk = [content]
                current_size = message_size
    
    # Don't forget the last chunk
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    
    return chunks


def extract_memories_from_chunk(chunk: str, client: Any, config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured memories from a text chunk."""
    api_config = config.get('api', {})
    model = api_config.get('model', 'claude-sonnet-4-20250514')
    max_retries = api_config.get('max_retries', 3)
    temperature = api_config.get('temperature', 0.1)
    
    for attempt in range(max_retries):
        try:
            response_text = client.generate(
                EXTRACTION_PROMPT + chunk,
                max_tokens=4000,
                temperature=temperature
            )
            
            # Parse extracted sections
            sections = parse_extracted_sections(response_text)
            
            # Extract additional entities from original text
            text_entities = extract_entities_from_text(chunk)
            
            return {
                'raw_extraction': response_text,
                'sections': sections,
                'entities': text_entities,
                'chunk_size': len(chunk),
                'model_used': model
            }
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Extraction attempt {attempt + 1} failed, retrying: {e}", file=sys.stderr)
                continue
            else:
                print(f"Extraction failed after {max_retries} attempts: {e}", file=sys.stderr)
                return {
                    'error': str(e),
                    'sections': {},
                    'entities': {},
                    'chunk_size': len(chunk)
                }


def merge_extractions(extractions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge multiple extractions into a single result."""
    merged = {
        'sections': {},
        'entities': {'people': [], 'projects': [], 'technologies': [], 'locations': [], 'organizations': []},
        'total_chunks': len(extractions),
        'total_size': sum(e.get('chunk_size', 0) for e in extractions)
    }
    
    # Merge sections
    for extraction in extractions:
        if 'error' in extraction:
            continue
        
        sections = extraction.get('sections', {})
        for section_name, items in sections.items():
            if section_name not in merged['sections']:
                merged['sections'][section_name] = []
            merged['sections'][section_name].extend(items)
    
    # Merge entities
    for extraction in extractions:
        entities = extraction.get('entities', {})
        for entity_type, entity_list in entities.items():
            if entity_type in merged['entities']:
                merged['entities'][entity_type].extend(entity_list)
    
    # Deduplicate
    for section_name, items in merged['sections'].items():
        merged['sections'][section_name] = list(dict.fromkeys(items))  # Preserves order
    
    for entity_type, entities in merged['entities'].items():
        merged['entities'][entity_type] = list(set(entities))
    
    return merged


def format_extraction_output(extraction: Dict[str, Any], format_type: str = "markdown") -> str:
    """Format extraction results."""
    if format_type == "json":
        return json.dumps(extraction, indent=2, default=str)
    
    # Markdown format
    output = []
    sections = extraction.get('sections', {})
    
    # Standard sections
    section_order = [
        'facts_&_preferences',
        'decisions_made', 
        'action_items',
        'technical_details',
        'people_mentioned',
        'key_topics_&_projects'
    ]
    
    for section in section_order:
        if section in sections and sections[section]:
            # Format section header
            header = section.replace('_', ' ').title().replace('&', '&')
            output.append(f"## {header}")
            
            # Add items
            for item in sections[section]:
                output.append(f"- {item}")
            output.append("")
    
    # Add entities section
    entities = extraction.get('entities', {})
    if any(entities.values()):
        output.append("## Entities")
        for entity_type, entity_list in entities.items():
            if entity_list:
                formatted_type = entity_type.replace('_', ' ').title()
                output.append(f"**{formatted_type}**: {', '.join(sorted(entity_list))}")
        output.append("")
    
    # Add metadata
    total_chunks = extraction.get('total_chunks', 1)
    if total_chunks > 1:
        output.append(f"*Extracted from {total_chunks} chunks*")
    
    return "\n".join(output)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract memories from OpenClaw session files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 extract_v2.py session_123.jsonl
  python3 extract_v2.py --date 2026-02-14
  python3 extract_v2.py --date today --structured
  python3 extract_v2.py session.jsonl --output memories/2026-02-14.md
        """
    )
    
    parser.add_argument(
        'input',
        nargs='?',
        help='Session file path or date (YYYY-MM-DD, "today", "yesterday")'
    )
    
    parser.add_argument(
        '--config',
        type=Path,
        help='Path to configuration file'
    )
    
    parser.add_argument(
        '--date',
        help='Extract from sessions modified on this date (YYYY-MM-DD, "today", "yesterday")'
    )
    
    parser.add_argument(
        '--output',
        type=Path,
        help='Output file path (default: auto-generate in memory dir)'
    )
    
    parser.add_argument(
        '--format',
        choices=['markdown', 'json'],
        default='markdown',
        help='Output format'
    )
    
    parser.add_argument(
        '--structured',
        action='store_true',
        help='Generate both .md and .json files'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be processed without making API calls'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show verbose output'
    )
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        config = load_config(args.config)
        
        # Parse date if provided
        target_date = None
        if args.date:
            if args.date.lower() == 'today':
                target_date = date.today()
            elif args.date.lower() == 'yesterday':
                target_date = date.today() - timedelta(days=1)
            else:
                target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        
        # Determine input files
        session_files = []
        if args.input:
            # Direct file path
            input_path = Path(args.input)
            if input_path.exists():
                session_files = [input_path]
            else:
                print(f"Error: File not found: {input_path}", file=sys.stderr)
                sys.exit(1)
        elif target_date:
            # Find sessions for date
            session_dir = Path(config['session_dir']).expanduser()
            session_files = find_session_files(session_dir, target_date)
        else:
            parser.error("Must provide either input file or --date")
        
        if not session_files:
            print("No session files found to process")
            sys.exit(0)
        
        if args.verbose:
            print(f"Found {len(session_files)} session file(s) to process:")
            for f in session_files:
                print(f"  - {f}")
        
        if args.dry_run:
            print("Dry run - would process these files but not make API calls")
            sys.exit(0)
        
        # Initialize configured LLM client
        client = create_llm_client(config)
        
        # Process all session files
        all_extractions = []
        
        for session_file in session_files:
            if args.verbose:
                print(f"Processing: {session_file}")
            
            # Parse session
            messages = parse_session(session_file)
            if not messages:
                print(f"No messages found in {session_file}")
                continue
            
            # Chunk messages
            extraction_config = config.get('extraction', {})
            max_chars = extraction_config.get('target_chars_per_chunk', 300000)
            overlap_chars = extraction_config.get('chunk_overlap', 1000)
            
            chunks = chunk_messages(messages, max_chars, overlap_chars)
            
            if args.verbose:
                print(f"  Split into {len(chunks)} chunks")
            
            # Extract from each chunk
            chunk_extractions = []
            for i, chunk in enumerate(chunks):
                if args.verbose:
                    print(f"  Processing chunk {i+1}/{len(chunks)}")
                
                extraction = extract_memories_from_chunk(chunk, client, config)
                chunk_extractions.append(extraction)
            
            # Merge chunks for this session
            session_extraction = merge_extractions(chunk_extractions)
            session_extraction['source_file'] = str(session_file)
            all_extractions.append(session_extraction)
        
        # Merge all sessions
        final_extraction = merge_extractions(all_extractions)
        final_extraction['extracted_at'] = datetime.now().isoformat()
        final_extraction['source_files'] = [e['source_file'] for e in all_extractions]
        
        # Generate output
        if args.output:
            output_path = args.output
        else:
            # Auto-generate output path
            memory_dir = Path(config['memory_dir']).expanduser()
            ensure_memory_dir(memory_dir)
            
            if target_date:
                output_path = memory_dir / f"{target_date}.md"
            else:
                timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
                output_path = memory_dir / f"extracted-{timestamp}.md"
        
        # Write markdown output
        md_content = format_extraction_output(final_extraction, "markdown")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        print(f"✅ Extraction complete: {output_path}")
        
        # Write JSON if structured output requested
        if args.structured:
            json_path = output_path.with_suffix('.json')
            json_content = format_extraction_output(final_extraction, "json")
            with open(json_path, 'w', encoding='utf-8') as f:
                f.write(json_content)
            print(f"✅ Structured data saved: {json_path}")
        
        # Print summary
        sections = final_extraction.get('sections', {})
        entities = final_extraction.get('entities', {})
        total_items = sum(len(items) for items in sections.values())
        total_entities = sum(len(ents) for ents in entities.values())
        
        print(f"📊 Summary: {total_items} memories, {total_entities} entities extracted")
        
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
