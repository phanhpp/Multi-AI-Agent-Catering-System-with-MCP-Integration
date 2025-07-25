from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, func, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Chef(Base):
    __tablename__ = 'chefs'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    specialization = Column(String, nullable=False)
    rating = Column(Float, nullable=True)

class Recipe(Base):
    __tablename__ = 'recipes'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    short_description = Column(String, nullable=False)
    specialization = Column(String, nullable=False)
    time_to_cook = Column(Integer, nullable=False)
    servings = Column(Integer, nullable=False)
    utensils = Column(String, nullable=True)
    protein_type = Column(String, nullable=True)  # pork, poultry, beef, fish, veggies
    is_vegan = Column(Boolean, nullable=False)
    is_vegetarian = Column(Boolean, nullable=False)
    is_gluten_free = Column(Boolean, nullable=False)
    is_dairy_free = Column(Boolean, nullable=False)

    # Relationships
    ingredients = relationship("Ingredient", back_populates="recipe")
    allergens = relationship("RecipeAllergen", back_populates="recipe")

class Ingredient(Base):
    __tablename__ = 'ingredients'
    
    id = Column(Integer, primary_key=True)
    recipe_id = Column(Integer, ForeignKey('recipes.id'))
    ingredient = Column(String, nullable=False)
    
    # Relationship
    recipe = relationship("Recipe", back_populates="ingredients")

class RecipeAllergen(Base):
    __tablename__ = 'recipe_allergens'
    
    id = Column(Integer, primary_key=True)
    recipe_id = Column(Integer, ForeignKey('recipes.id'))
    allergen = Column(String, nullable=False)
    
    # Relationship
    recipe = relationship("Recipe", back_populates="allergens")
