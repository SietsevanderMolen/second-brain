# Second Brain v2 — OpenClaw Memory Intelligence Skill

**Transform your agent from forgetful to brilliant with automated memory management.**

## Overview

Second Brain v2 is an OpenClaw skill that solves the #1 AI agent problem in 2026: memory loss between sessions. Your agent wakes up fresh every time, relying on manually-written memory files that quickly become stale. This skill automates the entire memory lifecycle:

- **Extract** memories from session logs using the configured LLM provider
- **Search** memories with natural language queries  
- **Consolidate** daily memories into long-term storage automatically
- **Score** memories by relevance with smart decay algorithms
- **Track** memory health with detailed statistics
- **Graph** entity relationships across all memories

## Key Features

### 🔍 Semantic Memory Search
Query your memories naturally: `remember search "when did we decide on GPT-4.1?"` 

### 🧠 Auto-Consolidation  
Automatically distills daily memories into your MEMORY.md file with smart deduplication

### 📊 Memory Scoring & Decay
Relevance scoring with configurable decay (decisions matter more than transient notes)

### 🔄 Nightly Pipeline
Fully automated memory processing that runs in background via cron

### 📈 Health Dashboard
Track memory growth, coverage gaps, and consolidation freshness

### 🕸️ Entity Graph
Visualize relationships between people, projects, and decisions

## Installation

```bash
# Install the skill (if using OpenClaw skill manager)
openclaw skill install second-brain

# Or clone directly
git clone <repo> ~/workspace/skills/second-brain
```

## Dependencies

- Python 3.12+
- PyYAML (`pip install pyyaml`)
- anthropic SDK (`pip install anthropic`) only when using `api.provider: anthropic` 
- qmd (optional, for enhanced search)

## Quick Start

### 1. Configure Your API Key

Set your provider configuration (examples below):
```bash
# Option A: Anthropic
export ANTHROPIC_API_KEY="your_key_here"

# Option B: LM Studio (OpenAI-compatible local model)
# In config.yaml set: api.provider: openai_compatible
# and api.model to your local model id (for example qwen/qwen3-14b)

# Option C: OpenClaw endpoint
# In config.yaml set: api.provider: openclaw
# and api.openclaw.chat_url (+ optional api.openclaw.agent)
```

Or configure it in OpenClaw auth profiles at `~/.openclaw/agents/main/agent/auth-profiles.json`.

### 2. Search Existing Memories

```bash
python3 scripts/search.py "DPU debugging decisions"
python3 scripts/search.py --date-range "2026-02-01,2026-02-14" "Discord bot features"
```

### 3. Run Memory Health Check

```bash
python3 scripts/stats.py
```

### 4. Extract Memories from Recent Sessions

```bash
# Extract from today's sessions
python3 scripts/extract_v2.py --date today

# Extract specific session
python3 scripts/extract_v2.py ~/path/to/session.jsonl
```

### 5. Auto-Consolidate Recent Memories

```bash
# Dry run (see proposed changes)
python3 scripts/consolidate.py --days 7 --dry-run

# Apply consolidation
python3 scripts/consolidate.py --days 7 --apply
```

### 6. Set Up Nightly Pipeline

```bash
# Test the full pipeline
python3 scripts/pipeline.py --dry-run

# Schedule via OpenClaw cron (recommended)
# Add to your agent's cron config
```

## Commands Reference

### Memory Search
```bash
# Natural language search
python3 scripts/search.py "your query here"

# Advanced options
python3 scripts/search.py \
    --date-range "2026-02-01,2026-02-14" \
    --limit 5 \
    --format json \
    "decision about model choice"
```

### Memory Extraction
```bash
# Extract from date
python3 scripts/extract_v2.py --date 2026-02-14

# Extract specific session
python3 scripts/extract_v2.py session_123.jsonl

# Enhanced output with entities
python3 scripts/extract_v2.py --structured session.jsonl
```

### Memory Consolidation
```bash
# Dry run (preview only)
python3 scripts/consolidate.py --dry-run

# Consolidate last 7 days
python3 scripts/consolidate.py --days 7 --apply

# Interactive mode
python3 scripts/consolidate.py --interactive
```

### Memory Scoring
```bash
# Score all memories
python3 scripts/score.py --reindex

# Show top-scored memories
python3 scripts/score.py --show-top 20

# Update scores only
python3 scripts/score.py --update-only
```

### Health & Statistics  
```bash
# Memory health dashboard
python3 scripts/stats.py

# Detailed breakdown
python3 scripts/stats.py --detailed

# Export for external tools
python3 scripts/stats.py --format json
```

### Entity Graph
```bash
# Build entity relationship graph
python3 scripts/graph.py --build

# Query graph
python3 scripts/graph.py --query "DpuDebugAgent"

# Export graph data
python3 scripts/graph.py --export graph.json
```

### Nightly Pipeline
```bash
# Full pipeline (recommended for cron)
python3 scripts/pipeline.py

# Pipeline with custom config
python3 scripts/pipeline.py --config my_config.yaml

# Dry run mode
python3 scripts/pipeline.py --dry-run
```

## Configuration

Default config is in `config.yaml`. Override by creating your own config file:

```yaml
memory_dir: ~/workspace/memory
session_dir: ~/.openclaw/agents/main/sessions
memory_md: ~/workspace/MEMORY.md

consolidation:
  interval_days: 7
  dry_run: false
  min_score: 0.5
  backup_memory_md: true

scoring:
  decay_half_life_days: 14
  category_weights:
    decisions: 1.5
    preferences: 1.3
    facts: 1.0
    action_items: 1.2
    transient: 0.5

search:
  use_qmd: true
  fallback: bm25
  max_results: 10
  highlight_matches: true

pipeline:
  extract_recent: true
  update_qmd: true
  generate_report: true
  consolidate_threshold: 5  # Min new memories before consolidation
```

## Integration with OpenClaw

### Cron Integration

Add to your OpenClaw agent's cron configuration:
```yaml
jobs:
  - name: "memory-pipeline"
    schedule: "0 2 * * *"  # 2 AM daily
    command: "python3 ~/workspace/skills/second-brain/scripts/pipeline.py"
    enabled: true
```

### Using in Agent Sessions

The skill is designed to work seamlessly with OpenClaw agents. Commands can be called directly from sessions:

```python
# In your agent code
exec(command="python3 ~/workspace/skills/second-brain/scripts/search.py 'recent decisions'")
```

## File Structure

```
~/workspace/skills/second-brain/
├── SKILL.md              # This file
├── README.md             # Full documentation
├── config.yaml           # Default configuration
├── scripts/
│   ├── search.py         # Semantic memory search
│   ├── consolidate.py    # Auto-consolidation engine
│   ├── score.py          # Memory scoring & decay
│   ├── extract_v2.py     # Enhanced extraction
│   ├── pipeline.py       # Nightly automation
│   ├── stats.py          # Health dashboard  
│   ├── graph.py          # Entity relationships
│   ├── extract.py        # Original extractor (legacy)
│   ├── digest.py         # Original digester (legacy)
│   ├── weekly.py         # Weekly analysis (legacy)
│   └── utils/
│       ├── memory_io.py  # Memory file operations
│       ├── scoring.py    # Scoring algorithms
│       ├── qmd_bridge.py # qmd search integration
│       └── bm25.py       # Pure Python BM25 implementation
├── tests/
│   ├── test_search.py
│   ├── test_scoring.py
│   ├── test_consolidation.py
│   └── test_pipeline.py
└── examples/
    ├── sample_config.yaml
    └── cron_setup.md
```

## Memory Files Layout

The skill works with OpenClaw's standard memory organization:

```
~/workspace/memory/
├── 2026-02-01.md         # Daily memory files
├── 2026-02-02.md
├── ...
├── .memory-index.json    # Scored memory index
├── .pipeline-log.json    # Pipeline execution log
└── .entity-graph.json    # Entity relationships
```

Plus your main memory file:
```
~/workspace/MEMORY.md     # Long-term consolidated memories
```

## Troubleshooting

### Search Returns No Results
1. Check if memory files exist in `~/workspace/memory/`
2. Try rebuilding search index: `python3 scripts/score.py --reindex`
3. If using qmd, run: `qmd update && qmd embed`

### Consolidation Not Working
1. Check API key is configured: `python3 -c "from scripts.utils.memory_io import get_api_key; print('OK')"`
2. Run with `--dry-run` first to see what would be consolidated
3. Check minimum score threshold in config

### Pipeline Failing
1. Run `python3 scripts/pipeline.py --dry-run` to see what would happen
2. Check logs in `~/workspace/memory/.pipeline-log.json`
3. Verify all dependencies are installed

### Permission Errors
1. Ensure OpenClaw agent has write access to `~/workspace/memory/`
2. Check that `MEMORY.md` is writable
3. Backup files before running consolidation with `--apply`

## Performance Notes

- Memory search is optimized for up to 10,000 daily memory files
- Consolidation processes last 7 days by default (configurable)
- Entity graph rebuilds are expensive - run weekly max
- qmd integration provides much faster search than BM25 fallback

## Contributing

This is an OpenClaw skill. Improvements welcome:
1. Add new memory categories
2. Improve scoring algorithms  
3. Better entity extraction
4. Enhanced search capabilities

## License

MIT License - Use freely in your OpenClaw setups.