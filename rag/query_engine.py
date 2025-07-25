from llama_index.core import SQLDatabase
from llama_index.core.retrievers import NLSQLRetriever
from sqlalchemy import MetaData
from typing import List, Dict, Optional, Any
import os
from dotenv import load_dotenv

# Add logging for SQL queries
import logging
logging.basicConfig(level=logging.INFO)
sql_logger = logging.getLogger("sql_queries")

# Enable SQLAlchemy logging to see SQL queries
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

def setup_llm():
    """Setup the LLM with OpenAI"""
    load_dotenv()
    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
    
    from llama_index.llms.openai import OpenAI
    from llama_index.core import Settings
    
    llm = OpenAI(model="gpt-4o-mini")
    Settings.llm = llm
    return llm

def create_sql_database(engine):
    """Create SQL database connection for LlamaIndex"""
    if engine is not None:
        # Load metadata
        metadata_obj = MetaData()
        metadata_obj.create_all(engine)
        
        # Connect to LlamaIndex
        sql_database = SQLDatabase(engine, include_tables=["chefs", "recipes", "recipe_allergens", "ingredients"])
        return sql_database
    else:
        print("Failed to create database engine. Cannot proceed.")
        return None

def create_nl_retriever(sql_database):
    """Create natural language SQL retriever"""
    nl_sql_retriever = NLSQLRetriever(
        sql_database, 
        tables=["chefs", "recipes", "recipe_allergens", "ingredients"], 
        return_raw=True, 
        verbose=True
    )
    return nl_sql_retriever


def sql_query(prompt, engine) -> List[Dict[str, Any]] | None:
    """
    Query the SQL database containing recipes and chefs using a prompt 
    Args:
        prompt (str): The prompt to query the SQL database
    Returns:
        List[Dict[str, Any]]: Query results 
    """
    try:
        #from rag.query_engine import create_sql_database, create_nl_retriever, get_safe_recipes_and_chefs_prompt
        sql_database = create_sql_database(engine)
        nl_retriever = create_nl_retriever(sql_database)
        results = nl_retriever.retrieve(prompt)
       
        return results
    except Exception as e:
        #logger.error(f"Error querying SQL database: {e}")
        print(f"Error querying SQL database: {e}")
        return None

