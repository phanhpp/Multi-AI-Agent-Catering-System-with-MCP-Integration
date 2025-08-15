## Project Structure

### Key Components:

**Client Layer:**
- `client.py` - Multi-agent workflow orchestrator using LlamaIndex
- `client.ipynb` - Jupyter notebook interface for testing

**MCP Server 1: Catering Server**
- `catering_server.py` - FastMCP server containing the RAG system
- `rag/models.py` - SQLAlchemy models (Chef, Recipe, Ingredient, RecipeAllergen)
- `rag/database.py` - Database initialization and CRUD operations
- `rag/query_engine.py` - Natural language to SQL conversion using LlamaIndex
- `rag/main.py` - Database setup and data population
- `rag/data/` - CSV files and SQLite database

**MCP Server 2: Filesystem Server**
- External npm package for file operations
- Handles saving final recommendations

**Workflow:**
1. Client orchestrates 5 specialized agents
2. Catering server analyzes dietary needs and queries recipe/chef database
3. If no database matches, client searches web via Tavily API
4. Filesystem server saves formatted results to `catering_result.txt`
