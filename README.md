# Second Brain v2 — OpenClaw Memory Intelligence Skill

**Transform your AI agent from forgetful to brilliant with automated memory management.**

## 🧠 Problem Solved

AI agent memory management is the #1 pain point in 2026. Your OpenClaw agent wakes up fresh each session, relying on manually-written memory files that quickly become stale. Second Brain v2 automates the entire memory lifecycle:

- ✅ **Extract** memories from session logs using the configured LLM provider
- ✅ **Search** memories with natural language queries  
- ✅ **Consolidate** daily memories into long-term storage automatically
- ✅ **Score** memories by relevance with smart decay algorithms
- ✅ **Track** memory health with detailed statistics
- ✅ **Graph** entity relationships across all memories
- ✅ **Automate** everything with nightly pipeline
- ✅ **Integrate** with qmd for enhanced search

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install pyyaml anthropic  # anthropic only needed if provider=anthropic
```

### 2. Configure API Key

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

Or configure in OpenClaw auth profiles.

### 3. Search Your Memories

```bash
cd ~/workspace/skills/second-brain
python3 scripts/search.py "decisions about model choice"
```

### 4. Check Memory Health

```bash
python3 scripts/stats.py
```

### 5. Set Up Nightly Pipeline

```bash
# Test the pipeline
python3 scripts/pipeline.py --dry-run

# Run live
python3 scripts/pipeline.py --apply
```

## 📊 Core Features

### 🔍 Semantic Memory Search (`search.py`)
- Natural language queries over all memory files
- Hybrid search: qmd semantic + BM25 fallback
- Smart relevance ranking with memory scores
- Date range filtering and result highlighting

```bash
python3 scripts/search.py "when did we decide on GPT-4.1?"
python3 scripts/search.py --date-range "2026-02-01,2026-02-14" "Discord features"
```

### 🧠 Auto-Consolidation (`consolidate.py`)
- Automatically distills daily memories into MEMORY.md
- AI-powered deduplication and merging
- Smart categorization and importance ranking
- Safe dry-run mode with preview

```bash
python3 scripts/consolidate.py --dry-run          # Preview changes
python3 scripts/consolidate.py --apply           # Apply changes
python3 scripts/consolidate.py --interactive     # Confirm each section
```

### 📈 Memory Scoring (`score.py`)
- Relevance scoring with configurable decay
- Category weights (decisions > facts > transient)
- Frequency boosting for repeated mentions
- Entity importance calculation

```bash
python3 scripts/score.py --reindex              # Rebuild scoring index
python3 scripts/score.py --show-top 10         # Top memories
python3 scripts/score.py --decay 7             # Apply time decay
```

### 🔬 Enhanced Extraction (`extract_v2.py`)
- Structured JSON + Markdown output
- Entity extraction (people, projects, technologies)
- Smart chunking for large sessions
- Better categorization and context

```bash
python3 scripts/extract_v2.py --date today     # Extract today's sessions
python3 scripts/extract_v2.py --structured session.jsonl  # Full extraction
```

### 🔄 Nightly Pipeline (`pipeline.py`)
- Fully automated memory processing
- Extract → Score → Index → Consolidate → Report
- Configurable thresholds and safety checks
- Comprehensive logging and error handling

```bash
python3 scripts/pipeline.py --dry-run          # Test pipeline
python3 scripts/pipeline.py --apply            # Run live
```

### 📊 Health Dashboard (`stats.py`)
- Memory growth tracking and coverage analysis
- Content statistics and category distributions
- Pipeline health monitoring
- Issue detection and recommendations

```bash
python3 scripts/stats.py                       # Health overview
python3 scripts/stats.py --detailed            # Full statistics
python3 scripts/stats.py --issues-only         # Just problems
```

### 🕸️ Entity Graph (`graph.py`)
- Build relationship graphs from memories
- Connect people, projects, decisions, technologies
- Query entity connections and explore relationships
- Export graph data for visualization

```bash
python3 scripts/graph.py --build               # Build entity graph
python3 scripts/graph.py --query "DpuDebugAgent"  # Explore connections
python3 scripts/graph.py --stats               # Graph statistics
```

## ⚙️ Configuration

Edit `config.yaml` to customize behavior:

```yaml
memory_dir: ~/workspace/memory
session_dir: ~/.openclaw/agents/main/sessions
memory_md: ~/workspace/MEMORY.md

consolidation:
  interval_days: 7
  dry_run: true            # Safety first!
  min_score: 0.5

scoring:
  decay_half_life_days: 14
  category_weights:
    decisions: 1.5         # Most important
    preferences: 1.3
    facts: 1.0
    action_items: 1.2
    transient: 0.5         # Least important

search:
  use_qmd: true           # Use qmd if available
  fallback: bm25          # Pure Python fallback
  max_results: 10

pipeline:
  extract_recent: true
  update_qmd: true
  consolidate: false      # Require explicit enable
  generate_report: true
```

## 🏗️ Architecture

```
~/workspace/skills/second-brain/
├── SKILL.md              # OpenClaw skill documentation  
├── README.md             # This file
├── config.yaml           # Configuration
├── scripts/              # Main functionality
│   ├── search.py         # 🔍 Semantic search
│   ├── consolidate.py    # 🧠 Auto-consolidation  
│   ├── score.py          # 📈 Memory scoring
│   ├── extract_v2.py     # 🔬 Enhanced extraction
│   ├── pipeline.py       # 🔄 Nightly automation
│   ├── stats.py          # 📊 Health dashboard
│   ├── graph.py          # 🕸️ Entity relationships
│   └── utils/            # Core utilities
│       ├── memory_io.py  # File operations
│       ├── scoring.py    # Scoring algorithms
│       ├── bm25.py       # Pure Python search
│       └── qmd_bridge.py # qmd integration
├── tests/                # Unit tests
└── examples/             # Usage examples
```

## 🔗 Integration with OpenClaw

### Cron Integration

Add to your OpenClaw agent's cron config:

```yaml
jobs:
  - name: "memory-pipeline"
    schedule: "0 2 * * *"  # 2 AM daily
    command: "python3 ~/workspace/skills/second-brain/scripts/pipeline.py --apply"
    enabled: true
```

### Direct Usage

```python
# In agent sessions
exec(command="python3 ~/workspace/skills/second-brain/scripts/search.py 'recent decisions'")
```

### Memory File Organization

Works with standard OpenClaw memory layout:

```
~/workspace/memory/
├── 2026-02-01.md         # Daily memories (auto-generated)
├── 2026-02-02.md
├── ...
├── .memory-index.json    # Scoring index (auto-generated)
└── .entity-graph.json    # Entity relationships (auto-generated)

~/workspace/MEMORY.md     # Long-term consolidated memory
```

## 🧪 Testing

Run the test suite:

```bash
cd ~/workspace/skills/second-brain
python3 -m pytest tests/ -v
```

Or run individual test modules:

```bash
python3 tests/test_scoring.py
python3 tests/test_search.py  
python3 tests/test_consolidation.py
```

## 🛠️ Troubleshooting

### Search Returns No Results
```bash
# Rebuild search index
python3 scripts/score.py --reindex

# Update qmd if available
qmd update && qmd embed
```

### Consolidation Not Working
```bash
# Check API key
python3 -c "from scripts.utils.memory_io import get_api_key; print('API key OK')"

# Run dry-run first
python3 scripts/consolidate.py --dry-run
```

### Pipeline Failures
```bash
# Check what would run
python3 scripts/pipeline.py --dry-run --verbose

# Check recent logs
cat ~/workspace/memory/.pipeline-log.json | tail -n 20
```

## 🎯 Performance Notes

- **Memory files**: Optimized for up to 10,000 daily files
- **Search**: qmd provides 10x faster search than BM25 fallback
- **Consolidation**: Processes last 7 days by default (configurable)
- **Entity graph**: Rebuild weekly max (expensive operation)
- **Pipeline runtime**: Typically 30-60 seconds for full run

## 🔧 Development

### Adding New Memory Categories

1. Update `config.yaml` consolidation categories
2. Extend extraction prompts in `extract_v2.py`  
3. Add category weights in scoring config
4. Update consolidation prompt in `consolidate.py`

### Extending Search

1. Add new search methods in `utils/qmd_bridge.py`
2. Extend BM25 features in `utils/bm25.py`
3. Update search ranking in `search.py`

### Custom Scoring

1. Modify scoring algorithms in `utils/scoring.py`
2. Add new score factors in `calculate_memory_score()`
3. Update score distribution analysis in `stats.py`

## 📝 License

MIT License - Use freely in your OpenClaw setups.

## 🤝 Contributing

This is an OpenClaw skill package. Improvements welcome:

1. **Better entity extraction** - More accurate NLP for relationships
2. **Enhanced search** - Semantic similarity, question answering
3. **Smarter consolidation** - Better duplicate detection, importance ranking
4. **Visualization** - Graph visualization, timeline views
5. **Integration** - More OpenClaw framework features

## 🔍 Examples

### Daily Workflow

```bash
# Morning: Check memory health
python3 scripts/stats.py

# Search for specific information
python3 scripts/search.py "decisions about the Discord bot"

# Extract from yesterday's sessions
python3 scripts/extract_v2.py --date yesterday

# Update scores and consolidate
python3 scripts/score.py --update-only
python3 scripts/consolidate.py --dry-run

# Evening: Run full pipeline
python3 scripts/pipeline.py --apply
```

### Research Mode

```bash
# Build entity graph
python3 scripts/graph.py --build

# Explore project connections
python3 scripts/graph.py --query "second-brain"
python3 scripts/graph.py --query "DpuDebugAgent" 

# Export for analysis
python3 scripts/graph.py --export research_graph.json
python3 scripts/stats.py --format json --export memory_stats.json
```

### Debugging Mode

```bash
# Check what's in memory files
python3 scripts/search.py --verbose "anything" 

# See scoring details
python3 scripts/score.py --show-top 20

# Test pipeline components
python3 scripts/pipeline.py --dry-run --verbose --skip-consolidate
```

---

**Ready to upgrade your AI agent's memory? Start with `python3 scripts/stats.py` to see your current memory health!** 🧠✨