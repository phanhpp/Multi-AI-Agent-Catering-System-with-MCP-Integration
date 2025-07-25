import pandas as pd
from database import init_database, populate_data, verify_data
from query_engine import setup_llm, create_sql_database, create_nl_retriever, get_allergy_safe_recipes_prompt
from llama_index.core.response.notebook_utils import display_source_node

def main():
    # 1. Setup LLM
    llm = setup_llm()
    
    # 2. Initialize database
    engine = init_database()
    
    # 3. Load data
    chefs = pd.read_csv("./rag/data/chefs.csv")
    recipes = pd.read_csv("./rag/data/recipes.csv")
    
    # 4. Populate database
    populate_data(engine, chefs, recipes)
    
    # 5. Verify data
    verify_data(engine)
    
    

if __name__ == "__main__":
    main() 