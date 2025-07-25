import pandas as pd
from sqlalchemy import create_engine, MetaData
from rag.models import Base
import pandas as pd
from sqlalchemy import create_engine, MetaData


def init_database(db_url='sqlite:///restaurant.db'):
    """Initialize the database and create tables"""
    engine = create_engine(db_url)
    
    # Drop existing tables if they exist
    Base.metadata.drop_all(engine)
    print("Existing tables dropped successfully!")
    
    # Create Tables
    Base.metadata.create_all(engine)
    print("Database and tables created successfully!")
    
    return engine

def populate_data(engine, df_chefs, df_recipes):
    """Populate the database with data from DataFrames"""
    try:
        # Insert main tables
        df_chefs.to_sql('chefs', engine, if_exists='append', index=False)
        df_recipes_db = df_recipes.drop(['ingredients', 'allergens'], axis=1)
        df_recipes_db.to_sql('recipes', engine, if_exists='append', index=False)
        
        # Process and insert recipe allergens
        recipe_allergen_rows = []
        recipe_ingredient_rows = []

        for _, row in df_recipes.iterrows():
            if pd.notna(row['allergens']) and row['allergens'].strip():
                allergens = [a.strip() for a in row['allergens'].split(',')]
                #print("allergens", allergens)
                for allergen in allergens:
                    recipe_allergen_rows.append({'recipe_id': row['id'], 'allergen': allergen})
         # Handle ingredients
            if pd.notna(row['ingredients']) and row['ingredients'].strip():
                ingredients = [i.strip() for i in row['ingredients'].split(',')]
                for ingredient in ingredients:
                    recipe_ingredient_rows.append({'recipe_id': row['id'], 'ingredient': ingredient})
        
        if recipe_allergen_rows:
            pd.DataFrame(recipe_allergen_rows).to_sql('recipe_allergens', engine, if_exists='append', index=False)
        
        # Insert ingredients
        if recipe_ingredient_rows:
            pd.DataFrame(recipe_ingredient_rows).to_sql('ingredients', engine, if_exists='append', index=False)
        

        print("Data inserted and normalized successfully!")
        
    except Exception as e:
        print(f"Error: {e}")

def verify_data(engine):
    """Verify the data in the database"""
    try:
        chefs_check = pd.read_sql('SELECT * FROM chefs', engine)
        recipes_check = pd.read_sql('SELECT * FROM recipes', engine)
        ingredients_check = pd.read_sql('SELECT * FROM ingredients', engine)
        recipe_allergens_check = pd.read_sql('SELECT * FROM recipe_allergens', engine)
        
        # print("\nSample chef data:")
        # print(chefs_check.head(5))
        # print("\nSample recipe data:")
        # print(recipes_check.head(5))
        print("\nSample recipe ingredients:")
        print(ingredients_check.head(5))
        print("\nSample recipe allergens:")
        print(recipe_allergens_check.head(5))
        
    except Exception as e:
        print(f"Error verifying data: {e}") 