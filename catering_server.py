import json
import os
from typing import List, Dict, Optional, Union, Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from mcp.server.fastmcp import FastMCP
from rag.models import Recipe, Ingredient, RecipeAllergen
from rag.query_engine import setup_llm
from pydantic import BaseModel
import pandas as pd
from rag.database import init_database, populate_data, verify_data

# Initialize FastMCP server
mcp = FastMCP(name="rag", port=8001)

# add logging
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# to check the tables in db: sqlite3 rag/data/restaurant.db ".tables"

class RecipeInput(BaseModel):
    name: str
    short_description: str
    specialization: str
    time_to_cook: int
    servings: int
    utensils: Optional[str] = None
    protein_type: Optional[str] = None
    is_vegan: bool = False
    is_vegetarian: bool = False
    is_gluten_free: bool = False
    is_dairy_free: bool = False
    ingredients: List[str]
    allergens: List[str]

DATABASE_URL = 'sqlite:///rag/data/restaurant.db'
engine = create_engine(DATABASE_URL)
llm = setup_llm()

# initialize database
def init_session():
    # Create engine and session
    Session = sessionmaker(bind=engine)
    session = Session()
    return session

@mcp.tool()
def dietary_strategy_analyzer(guest_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes guest dietary restrictions and determines menu strategy.
    
    This function processes a list of guests and their dietary restrictions to determine:
    1. Universal requirements (restrictions affecting 30%+ of guests)
    2. Needed alternatives for minority restrictions
    3. Total guest count
    
    Args:
        guest_list (List[Dict[str, Any]]): List of guest dictionaries containing dietary requirements.
            Each guest dict can have any of these fields (all optional with default False):
            - is_vegan: bool
            - is_vegetarian: bool
            - is_gluten_free: bool
            - is_dairy_free: bool
            - allergens: List[str] (defaults to empty list)

    Call it like this: dietary_strategy_analyzer(guest_list={input_guest_list})
    """
    total_guests = len(guest_list)
    
    # Step 1: Count restriction types
    restriction_counts = {
        'vegan': 0,
        'vegetarian': 0,
        'gluten_free': 0,
        'dairy_free': 0,
        'allergens': {}
    }
    
    for guest in guest_list:
        # All dietary restrictions default to False if not specified
        if guest.get('is_vegan', False):
            restriction_counts['vegan'] += 1
        if guest.get('is_vegetarian', False):
            restriction_counts['vegetarian'] += 1
        if guest.get('is_gluten_free', False):
            restriction_counts['gluten_free'] += 1
        if guest.get('is_dairy_free', False):
            restriction_counts['dairy_free'] += 1
        
        # Allergens defaults to empty list if not specified
        allergens = guest.get('allergens', [])
        for allergen in allergens:
            restriction_counts['allergens'][allergen] = restriction_counts['allergens'].get(allergen, 0) + 1
    
    # Step 2: Determine universal requirements (30%+ of guests)
    import math
    threshold = math.ceil(total_guests * 0.3) if total_guests > 3 else 1
    universal_requirement = {
        'dietary_restrictions': [],
        'allergens': []
    }
    
    # Set universal dietary restrictions
    if restriction_counts['vegan'] >= threshold:
        universal_requirement['dietary_restrictions'].append('is_vegan')
    if restriction_counts['vegetarian'] >= threshold:
        universal_requirement['dietary_restrictions'].append('is_vegetarian')
    if restriction_counts['gluten_free'] >= threshold:
        universal_requirement['dietary_restrictions'].append('is_gluten_free')
    if restriction_counts['dairy_free'] >= threshold:
        universal_requirement['dietary_restrictions'].append('is_dairy_free')
    
    # Set universal allergens
    common_allergens = [allergen for allergen, count in restriction_counts['allergens'].items() 
                       if count >= threshold]
    universal_requirement['allergens'].extend(common_allergens)
    
    # Step 3: Group guests with similar requirements for alternatives
    alternatives_needed = []
    processed_guests = set()  # Track which guests we've accounted for
    
    # Helper function to create restriction signature for a guest
    def get_guest_signature(guest):
        return (
            guest.get('is_vegan', False),
            guest.get('is_vegetarian', False),
            guest.get('is_gluten_free', False),
            guest.get('is_dairy_free', False),
            tuple(sorted(guest.get('allergens', [])))
        )
    
    # Group similar guests together
    for i, guest in enumerate(guest_list):
        if i in processed_guests:
            continue
            
        signature = get_guest_signature(guest)
        similar_guests = 1
        processed_guests.add(i)
        
        # Count guests with same requirements
        for j in range(i + 1, len(guest_list)):
            if j not in processed_guests and get_guest_signature(guest_list[j]) == signature:
                similar_guests += 1
                processed_guests.add(j)
        
        # Only add as alternative if requirements differ from universal
        dietary_restrictions = []
        # Use get() with default False for all checks
        if guest.get('is_vegan', False) and 'is_vegan' not in universal_requirement['dietary_restrictions']:
            dietary_restrictions.append('is_vegan')
        if guest.get('is_vegetarian', False) and 'is_vegetarian' not in universal_requirement['dietary_restrictions']:
            dietary_restrictions.append('is_vegetarian')
        if guest.get('is_gluten_free', False) and 'is_gluten_free' not in universal_requirement['dietary_restrictions']:
            dietary_restrictions.append('is_gluten_free')
        if guest.get('is_dairy_free', False) and 'is_dairy_free' not in universal_requirement['dietary_restrictions']:
            dietary_restrictions.append('is_dairy_free')
            
        allergens = [a for a in guest.get('allergens', []) if a not in universal_requirement['allergens']]
        
        # Only add to alternatives if there are non-universal requirements
        if dietary_restrictions or allergens:
            alternatives_needed.append({
                'dietary_restrictions': dietary_restrictions,
                'allergens': allergens,
                'quantity_needed': similar_guests
            })
    
    result = {
        'total_guests': total_guests,
        'universal_requirement': universal_requirement,
        'alternatives_needed': alternatives_needed
    }
    
    return result

# Recipe management tools
@mcp.tool()
def save_recipe(recipe_name: str, short_description: str, ingredients: List[str], recipe_cook_time: int, allergens: List[str], specialization: str, servings: int, utensils: Optional[str] = None, protein_type: Optional[str] = None, is_vegan: bool = False, is_vegetarian: bool = False, is_gluten_free: bool = False, is_dairy_free: bool = False) -> str:
    """
    Save a new recipe to the SQL database.
    
    Args:
        recipe_name (str): Name of the recipe
        short_description (str): Brief description of the recipe
        ingredients (List[str]): List of ingredients needed
        recipe_cook_time (int): Time to cook in minutes
        allergens (List[str]): List of allergens present in the recipe
        specialization (str): Type of cuisine or cooking style
        servings (int): Number of servings the recipe makes
        utensils (Optional[str]): Required cooking utensils
        protein_type (Optional[str]): Type of protein used (e.g., pork, poultry, beef, fish, veggies)
        is_vegan (bool): Whether the recipe is vegan
        is_vegetarian (bool): Whether the recipe is vegetarian
        is_gluten_free (bool): Whether the recipe is gluten-free
        is_dairy_free (bool): Whether the recipe is dairy-free
    
    Returns:
        str: Success or error message
    """
    try:
        session = init_session()
        recipes = session.query(Recipe).all()

        # auto increment id
        recipe_id = len(recipes) + 1
        # Create the recipe
        recipe = Recipe(
            id=recipe_id,
            name=recipe_name,
            short_description=short_description,
            specialization=specialization,
            time_to_cook=recipe_cook_time,
            servings=servings,
            utensils=utensils,
            protein_type=protein_type,
            is_vegan=is_vegan,
            is_vegetarian=is_vegetarian,
            is_gluten_free=is_gluten_free,
            is_dairy_free=is_dairy_free
        )
        
        # Add ingredients
        for ingredient_name in ingredients:
            ingredient = Ingredient(
                recipe_id=recipe_id,
                ingredient=ingredient_name
            )
            recipe.ingredients.append(ingredient)
        
        # Add allergens
        for allergen_name in allergens:
            allergen = RecipeAllergen(
                recipe_id=recipe_id,
                allergen=allergen_name
            )
            recipe.allergens.append(allergen)
        
        print(f"Successfully created recipe {recipe_name}")
        session.add(recipe)
        session.commit()
        logger.info(f"Successfully created recipe {recipe_name}")
        return f"Successfully created recipe {recipe_name}"
    except Exception as e:
        logger.error(f"Error creating recipe: {e}")
        return f"Error creating recipe: {e}"
    finally:
        session.close()

@mcp.tool()
def list_all_specializations() -> List[str]:
    """
    List all specializations in the database.
    Return a set of specializations.
    """
    from rag.models import Chef
    try:
        session = init_session()
        chefs = session.query(Chef).all()
        return set([chef.specialization for chef in chefs])
    except Exception as e:
        logger.error(f"Error listing specializations: {e}")
        return 
    finally:
        session.close()


@mcp.tool()
def get_all_recipes() -> List[Dict[str, Any]]:
    """
    Get all recipes from the SQL database.

    Returns:
        List[Dict[str, Any]]: List of dictionaries containing recipe details including:
            - id: Recipe ID
            - name: Recipe name
            - short_description: Brief description of the recipe
            - specialization: Cuisine specialization
            - time_to_cook: Cooking time in minutes
            - servings: Number of servings
            - utensils: Required utensils (optional)
            - protein_type: Type of protein used (optional)
            - is_vegan: Whether recipe is vegan
            - is_vegetarian: Whether recipe is vegetarian  
            - is_gluten_free: Whether recipe is gluten-free
            - is_dairy_free: Whether recipe is dairy-free
            - ingredients: List of ingredients
            - allergens: List of allergens
        Returns empty list if no recipes found or on error.
    """
    try:
        session = init_session()
        recipes = session.query(Recipe).all()
        if recipes:
            recipe_dicts = []
            for recipe in recipes:
                recipe_dict = {
                    'id': recipe.id,
                    'name': recipe.name,
                    'short_description': recipe.short_description,
                    'specialization': recipe.specialization,
                    'time_to_cook': recipe.time_to_cook,
                    'servings': recipe.servings,
                    'utensils': recipe.utensils,
                    'protein_type': recipe.protein_type,
                    'is_vegan': recipe.is_vegan,
                    'is_vegetarian': recipe.is_vegetarian,
                    'is_gluten_free': recipe.is_gluten_free,
                    'is_dairy_free': recipe.is_dairy_free,
                    'ingredients': [i.ingredient for i in recipe.ingredients],
                    'allergens': [a.allergen for a in recipe.allergens]
                }
                recipe_dicts.append(recipe_dict)
            return recipe_dicts
        return []
    except Exception as e:
        logger.error(f"Error getting all recipes: {e}")
        return []
    finally:
        session.close()

@mcp.tool()
def get_safe_recipes_and_chefs(allergies: List[str], dietary_restrictions: Dict[str, bool]) -> List[Dict[str, Any]] | None:
    """
    Find recipes that are safe for guests (allergies and dietary restrictions) and best chefs that can cook them by querying the SQL database

    Args:
        allergies (List[str]): List of allergies to filter out
        dietary_restrictions (Dict[str, bool]): Dictionary of dietary restrictions like {'is_vegan': True}

    Returns:
        Dict[str, Any]: Dictionary containing:
            - result: List of tuples with (recipe_id, recipe_name, recipe_specialization, chef_name, chef_specialization)
            - col_keys: List of column names in order: ['recipe_id', 'recipe_name', 'recipe_specialization', 
                                                      'chef_name', 'chef_specialization']
        Returns None if no matches found or on error
    """
    filters = []
    
    if not allergies and not dietary_restrictions:
        filters.append("Choose all recipes")
    if allergies:
        filters.append(f"- Filter out recipes containing {allergies}")
    if dietary_restrictions:
        filters.append(f"- Only choose recipes that meet the dietary restrictions: {dietary_restrictions}")

    prompt = f"""Find safe recipes and chefs based on the following requirements:

    - REQUIREMENTS - 
    1. Recipe:
    {chr(10).join([x for x in filters])}


    2. Chef Matching:
    - Find chefs whose specialization matches the recipe's specialization
    - Sort matching chefs by rating (highest to lowest)

    Return the recipe id, recipe name, ingredients, recipe specialization, chef id, chef name, chef rating and time to cook.
    
    ## Example workflow:
    Given input:
    - allergies: ['nuts']
    - dietary_restrictions: {{'is_vegan': True, 'is_gluten_free': True}}

    Predicted SQL query should be:
    Predicted SQL query should be:
    WITH RankedChefs AS (
    SELECT 
        r.id,
        r.name,
        i.ingredient,
        r.specialization,
        c.id AS chef_id,
        c.name AS chef_name,
        c.rating,
        r.time_to_cook,
        ROW_NUMBER() OVER (PARTITION BY r.id ORDER BY c.rating DESC) as chef_rank
    FROM recipes r
    JOIN ingredients i ON r.id = i.recipe_id
    JOIN chefs c ON r.specialization = c.specialization
    WHERE r.is_vegan = 1 
    AND r.is_gluten_free = 1 
    AND r.id NOT IN (
        SELECT ra.recipe_id 
        FROM recipe_allergens ra 
        WHERE ra.allergen IN ('nuts', 'fish', 'quinoa')
    )
    AND r.id NOT IN (
        SELECT DISTINCT recipe_id
        FROM ingredients
        WHERE LOWER(ingredient) LIKE '%nuts%'
        OR LOWER(ingredient) LIKE '%fish%'
        OR LOWER(ingredient) LIKE '%quinoa%'
    )
    )
    SELECT 
        id,
        name,
        ingredient,
        specialization,
        chef_id,
        chef_name,
        rating,
        time_to_cook
    FROM RankedChefs
    WHERE chef_rank = 1
    ORDER BY rating DESC;
    ;

    
    Output:"""
    
    from rag.query_engine import sql_query
    results = sql_query(prompt, engine)

    if results and len(results) > 0:
        metadata = results[0].metadata
        return {
            'result': metadata['result'],
            'col_keys': metadata['col_keys']
        }

    return 

        
@mcp.tool()
def get_chefs_by_specialization(specialization: str) -> List[Dict[str, Any]]:
    """
    Find chefs who can cook specified specialization, ranked by their rating.
    
    Args:
        specialization (str): The cooking specialization to search for
    
    Returns:
        List[Dict[str, Any]]: List of chef objects matching the specialization,
            sorted by rating in descending order
    """
    from rag.models import Chef
    try:
        session = init_session()
        chef_query = session.query(Chef).filter(
            Chef.specialization == specialization
        )
        
        # Order by rating
        chefs = chef_query.order_by(Chef.rating.desc()).all()

        if chefs:
            # Convert SQLAlchemy objects to dictionaries
            chef_dicts = [
                {
                    'id': chef.id,
                    'name': chef.name,
                    'specialization': chef.specialization,
                    'rating': chef.rating
                }
                for chef in chefs
            ]
            
            return chef_dicts
        else:
            return []
    except Exception as e:
        print(f"Error in query: {e}")
        return []
    finally:
        session.close()


# @mcp.tool()
# def repopulate_database() -> str:
#     """
#     Repopulate the database with fresh data from CSV files.
    
#     This function will:
#     1. Drop all existing tables
#     2. Create new tables based on the current models
#     3. Load data from the CSV files in rag/data/
#     4. Populate the database with the loaded data
    
#     Returns:
#         str: Success or error message with details about the operation
#     """
#     try:
#         # Get the path to the data directory
#         current_dir = os.path.dirname(os.path.abspath(__file__))
#         data_dir = os.path.join(current_dir, 'rag', 'data')
        
#         # Load CSV files
#         chefs_file = os.path.join(data_dir, 'chefs.csv')
#         recipes_file = os.path.join(data_dir, 'recipes.csv')
        
#         if not os.path.exists(chefs_file):
#             return f"Error: Chefs CSV file not found at {chefs_file}"
#         if not os.path.exists(recipes_file):
#             return f"Error: Recipes CSV file not found at {recipes_file}"
        
#         # Load data
#         df_chefs = pd.read_csv(chefs_file)
#         df_recipes = pd.read_csv(recipes_file)
        
#         # Use the correct database URL that matches the working notebook
#         db_url = 'sqlite:///rag/data/restaurant.db'
        
#         # Initialize database (this will drop and recreate tables)
#         engine = init_database(db_url)
        
#         # Populate with fresh data
#         populate_data(engine, df_chefs, df_recipes)
        
#         # Verify the data was loaded correctly
#         verify_data(engine)
        
#         return f"Database successfully repopulated! Loaded {len(df_chefs)} chefs and {len(df_recipes)} recipes."
        
#     except Exception as e:
#         logger.error(f"Error repopulating database: {e}")
#         return f"Error repopulating database: {e}"


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')



    