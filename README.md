# LlamaIndex Multi-Agent Catering System with MCP Servers Integration

## Project Overview
An advanced multi-agent system built with LlamaIndex that automates catering menu planning by analyzing guests' dietary requirements and matching them with suitable recipes and chefs. The system orchestrates multiple MCP (Model Context Protocol) servers to handle different aspects of the workflow.

## Features
- Analyzes group dietary restrictions and allergies
- Identifies universal requirements (affecting 30%+ of guests)
- Finds safe recipes matching all dietary requirements
- Automatically researches alternatives when needed
- Matches recipes with specialized chefs based on cuisine type
- Saves final recommendations to files

## Architecture

### MCP Server Components
1. **Catering Management Server** (`uv run catering_server.py`)
   - SQLite-based recipe and chef database
   - Core functionality:
     - Dietary analysis and requirements processing
     - Recipe and chef database management
     - Menu planning and chef matching
   - Tools:
     - `dietary_strategy_analyzer`: Smart analysis of group dietary needs
     - `get_safe_recipes_and_chefs`: Recipe-chef matching with dietary compliance
     - `list_all_specializations`: Chef specialization management
     - `get_chefs_by_specialization`: Specialized chef lookup

2. **Filesystem Server** (`npx @modelcontextprotocol/server-filesystem`)
   - Handles result persistence
   - Saves recommendations to files

3. **Web Search Integration**
   - Integrates with Tavily API
   - Researches new recipes when database matches fail

### Multi-Agent System
- **Diet Analysis Agent**: Processes guest requirements and determines universal/alternative needs
- **Recipe Finding Agent**: Queries database for matching recipes
- **Research Agent**: Searches web for new recipes when needed
- **Chef Matching Agent**: Pairs recipes with qualified chefs
- **Filesystem Agent**: Handles data persistence

## Setup

### Environment Setup
```bash
# Install uv (fast Python package installer)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create isolated Python environment
uv venv                        # Uses current Python version
# OR
uv venv --python=python3.12    # Specific Python version

# Activate environment
source .venv/bin/activate      # Unix/macOS
# OR
.venv\Scripts\activate         # Windows

# Install dependencies
uv pip install --all          # Installs all dependencies from pyproject.toml
```

### Configuration
Create `.env` file with required API keys:
```bash
OPENAI_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here
```

### Start Services
```bash
# Start Catering Management Server
uv run catering_server.py

# Start filesystem server
npx @modelcontextprotocol/server-filesystem <workspace_path>
```

## Tech Stack
- **Core Framework**: LlamaIndex for agent orchestration
- **Language Model**: OpenAI GPT-4 for intelligent decision making
- **Database**: SQLite + SQLAlchemy for recipe/chef data
- **API Integration**: Tavily for recipe research
- **Data Validation**: Pydantic for type safety
- **Protocol**: Model Context Protocol (MCP) for service communication
- **Package Management**: uv + pyproject.toml for modern Python dependency management

## Usage Example
```python
# Initialize workflow
workflow = CateringMultiAgentFlow(timeout=130)

# Define guest dietary requirements
guests = [
    {
        "is_vegan": True,
        "is_vegetarian": True,
        "allergens": ["nuts"]
    },
    {
        "is_gluten_free": True,
        "allergens": ["eggs", "dairy"]
    }
]

# Run the workflow
result = await workflow.run(
    guest_list=guests,
    diet_analyze_agent=diet_analyze_agent,
    find_existing_recipe_agent=find_existing_recipes_agent,
    chef_matching_agent=chef_matching_agent,
    research_agent=research_agent,
    filesystem_agent=filesystem_agent
)
```

## Output Format
The system generates a structured recommendation in `catering_result.txt`:
```
### Dietary Analysis
- Universal Requirements: [list of requirements affecting >30% guests]
- Alternative Needs: [list of special cases]

### Recipe Recommendations
- [Recipe Name]
  - Description
  - Ingredients
  - Dietary Compliance

### Chef Matches
- [Chef Name]
  - Specialization
  - Rating
  - Matching Recipes
```

## Development

### Updating Dependencies
```bash
# Update dependencies to latest compatible versions
uv pip compile pyproject.toml

# Install in development mode
uv pip install --all --editable .
```
