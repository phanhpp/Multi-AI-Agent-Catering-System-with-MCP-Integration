import asyncio
from llama_index.tools.mcp import McpToolSpec
from llama_index.llms.openai import OpenAI
from llama_index.tools.mcp import BasicMCPClient
from llama_index.core.workflow import (
    StartEvent,
    StopEvent,
    Workflow,
    step,
    Event,
    Context
)
from llama_index.core.agent.workflow import FunctionAgent
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import os 
import dotenv

# Load environment variables
dotenv.load_dotenv()

# Initialize OpenAI LLM
llm = OpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))

# Define Pydantic models for dietary analysis
class UniversalRequirement(BaseModel): 
    dietary_restrictions: List[str]  
    allergens: List[str] = Field(default_factory=list)

    class Config:
        extra = "forbid"

class AlternativeRequirement(BaseModel):
    dietary_restrictions: List[str] 
    allergens: List[str] = Field(default_factory=list)
    quantity_needed: int

    class Config:
        extra = "forbid"

class DietaryAnalysisOutput(BaseModel):
    total_guests: int
    universal_requirement: UniversalRequirement 
    alternatives_needed: List[AlternativeRequirement]
    
    class Config:
        extra = "forbid"

# Define workflow events
class DietaryAnalysisEvent(Event):
    guest_list: list

class FindExistingRecipeEvent(Event):
    requirement: dict

class SearchRecipeEvent(Event):
    requirement: dict

class MatchChefEvent(Event):
    recipes_found: str

class ReviewEvent(Event):
    requirement: dict
    search_result: str

class FinalizeEvent(Event):
    result: str

# Web search function
async def search_web(query: str) -> str:
    """Useful for using the web to answer questions."""
    from tavily import AsyncTavilyClient
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    client = AsyncTavilyClient(api_key=tavily_api_key)
    return str(await client.search(query))

# Main workflow class
class CateringMultiAgentFlow(Workflow):
    retry_step1 = 0
    llm = llm

    @step
    async def setup(self, ctx: Context, ev: StartEvent) -> DietaryAnalysisEvent:
        await ctx.store.set("search_result", False)
        self.diet_analyze_agent = ev.diet_analyze_agent
        self.find_existing_recipes_agent = ev.find_existing_recipe_agent
        self.chef_matching_agent = ev.chef_matching_agent
        self.research_agent = ev.research_agent
        self.filesystem_agent = ev.filesystem_agent
        return DietaryAnalysisEvent(guest_list=ev.guest_list)

    @step
    async def diet_analyze(self, ctx: Context, ev: DietaryAnalysisEvent) -> FindExistingRecipeEvent | StopEvent:
        guest_list = ev.guest_list
        response = await self.diet_analyze_agent.run(f"Analyze the guests: {guest_list}, just directly put the input as argument to the tool")

        if not response:
            return StopEvent(result="No response from diet_analyze_agent")
        if not response.structured_response:
            return StopEvent(result="No structured response from diet_analyze_agent")
        
        try:
            analysis = response.structured_response
            requirements = []

            if "universal_requirement" in analysis:
                requirements.append({
                    'dietary_restrictions': analysis["universal_requirement"]["dietary_restrictions"],
                    'allergens': analysis["universal_requirement"]["allergens"]
                })
                
            if "alternatives_needed" in analysis:
                for alt in analysis["alternatives_needed"]:
                    requirements.append({
                        'dietary_restrictions': alt["dietary_restrictions"],
                        'allergens': alt["allergens"]
                    })

            print("Requirements:", requirements)
            
            if not requirements:
                return StopEvent(result="No requirements generated in diet_analyze")
            
            await ctx.store.set("requirements count", len(requirements))
            for requirement in requirements:
                ctx.send_event(FindExistingRecipeEvent(requirement=requirement))
            
        except Exception as e:
            print("Error", e)
            return StopEvent(result="Failed in diet_analyze")
        
    @step
    async def find_existing_recipes(self, ctx: Context, ev: FindExistingRecipeEvent) -> SearchRecipeEvent | FinalizeEvent:
        print("=== find_existing_recipes ===")
        diet_requirements = ev.requirement
        result = await self.find_existing_recipes_agent.run(f"Find the best recipes and matching chefs for the given requirements: {diet_requirements}")
        print("find existing recipes result", str(result))
        if "failed" in str(result).lower():
            return SearchRecipeEvent(requirement=diet_requirements)
        else:
            return FinalizeEvent(result=str(result))

    @step 
    async def search_new_recipes(self, ctx: Context, ev: SearchRecipeEvent) -> ReviewEvent:
        print("=== search_new_recipes ===")
        diet_requirements = ev.requirement
        result = await self.research_agent.run(f"Search for new recipes online that match the given requirements: {diet_requirements}. Make sure to match the recipe's specialization with one of the existing chefs' specializations found from the list_all_specializations tool")
        print("search_new_recipes result", str(result))
        return ReviewEvent(search_result=str(result), requirement=diet_requirements)
    
    @step
    async def review_search_result(self, ctx: Context, ev: ReviewEvent) -> SearchRecipeEvent | MatchChefEvent:
        requirement = ev.requirement
        search_result = ev.search_result
        review_result = self.llm.complete(
            f"Review whether the following recipes meet the guests' dietary requirements: \n\n Dietary requirements: {requirement} \n\n Recipes: {search_result}"
            "Additionally, check if the recipe names include specific ingredients (e.g., 'Fresh mango salad' or 'French chicken stew with lentils') instead of a generic collection of recipes like 'Dairy-Free, Gluten-Free and Nut-Free Recipes'."
            "If no, output 'Failed'"
            "If yes, output 'Success'"
            "Plus justification for your answer"
            )
        print("review_result", review_result)
        if "failed" in str(review_result).lower():
            return SearchRecipeEvent(requirement=requirement + "feedback for previous result: " + str(review_result))
        else:
            return MatchChefEvent(recipes_found=str(search_result))        

    @step
    async def match_chef(self, ctx: Context, ev: MatchChefEvent) -> FinalizeEvent:
        result = await self.chef_matching_agent.run(f"Match the recipes with chefs that have the same specializations in the following list: {ev.recipes_found}")
        print("matching chef result", str(result))
        return FinalizeEvent(result=f'recipes: {ev.recipes_found}\n\nchefs: {str(result)}')
    
    @step
    async def finalize(self, ctx: Context, ev: FinalizeEvent) -> StopEvent:
        requirements_count = await ctx.store.get("requirements count")
        data = ctx.collect_events(ev, [FinalizeEvent] * requirements_count)
        if data is None:
            print("Not all requirements are met yet.")
            return None
        result = llm.complete(f"Finalize this result: {data} by formatting it in an easy-to-read format. Do not make up any information. Just use the information provided.")
        save_file_msg = await self.filesystem_agent.run(f"Write the final result to the a file called 'catering_result.txt': {result} and output a brief confirmation message")
        return StopEvent(result=str(result) + "\n" + str(save_file_msg))

async def setup_tools():
    # RAG server for guests and recipes
    catering_client = BasicMCPClient("uv", args=["run", "catering_server.py"])
    
    # Fetch server for web search
    fetch_client = BasicMCPClient("uvx", args=["mcp-server-fetch"])
    
    file_system_client = BasicMCPClient("npx",
            args= [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                "/Users/dangphuonganh/Documents/mcp/cleanver/catering_service" #allowed directory
            ])
    
    # Create tool specs
    catering_tools = McpToolSpec(client=catering_client, 
                            allowed_tools=['dietary_strategy_analyzer','get_all_recipes', 'list_all_specializations', 'get_safe_recipes_and_chefs', 'get_chefs_by_specialization'], 
                            include_resources=True)
    
    fetch_tools = McpToolSpec(client=fetch_client, include_resources=False)
    
    filesystem_tools = McpToolSpec(
        client=file_system_client,
        allowed_tools=['list_allowed_directories', 'read_file', 'write_file', 'create_directory'],
        include_resources=False
    )
    
    # Get all tools
    catering_function_tools = await catering_tools.to_tool_list_async()
    fetch_function_tools = await fetch_tools.to_tool_list_async()
    filesystem_function_tools = await filesystem_tools.to_tool_list_async()
    return catering_function_tools, fetch_function_tools, filesystem_function_tools

# define agents
async def define_agents():
    catering_tools, fetch_tools, filesystem_tools = await setup_tools()

    # Filter tools by name
    dietary_tools = [tool for tool in catering_tools if 'dietary_strategy_analyzer' in tool.metadata.name]
    find_existing_recipe_tools = [tool for tool in catering_tools if 'get_safe_recipes_and_chefs' in tool.metadata.name]
    list_all_specializations_tool = [tool for tool in catering_tools if 'list_all_specializations' in tool.metadata.name]
    get_chefs_by_specialization_tool = [tool for tool in catering_tools if 'get_chefs_by_specialization' in tool.metadata.name]

    # Initialize agents
    diet_analyze_agent = FunctionAgent(
        name="DietAnalyzeAgent",
        description="Comprehensively analyze guest dietary restrictions and allergies to determine optimal menu requirements.",
        system_prompt="""You are an agent that analyzes guest dietary restrictions and allergies.
        You will be given only ONE guest list, containing dictionaries with dietary information for each guest.
        Simply pass this input directly to the dietary_strategy_analyzer tool
        Return the tool's output as it is. DO NOT modify it.""",
        llm=llm,
        verbose=True,
        output_cls=DietaryAnalysisOutput,
        tools=dietary_tools 
    )

    find_existing_recipes_agent = FunctionAgent(
        name="FindExistingRecipeAgent",
        description="Find existing recipes and matching chefs for the given menu requirements based on dietary analysis.",
        system_prompt="""You are an expert in finding recipes that meet the dietary requirements and match them with the best available chefs.
        Simply pass this input directly to the get_safe_recipes_and_chefs tool and return the tool's output as it is without modification
        If no recipes are found, just output 'Failed'. Nothing else.""",
        tools=find_existing_recipe_tools
    )

    chef_matching_agent = FunctionAgent(
        name="ChefMatchingAgent",
        description="Given a specialization, find matching chef in the database.",
        system_prompt="""You are an agent that matches recipes with chefs based on 'specialization'
        1. you must start by using the list_all_specializations tool to get the list of existing chefs' specializations.
        2. Input processing: You will be given a recipe, you must categorize the recipe as one of the found specialization
        3. Finally, use the get_chefs_by_specialization tool to find chefs with that specialization""",
        tools=get_chefs_by_specialization_tool + list_all_specializations_tool,
    )

    research_agent = FunctionAgent(
        name="ResearchAgent",
        description="Create recipe(s) that satify dietary requirements",
        system_prompt="""You are an agent that finds specific recipe(s) that satify dietary requirements.
        
        # Input: You will be given a requirement (Dict) containing 2 fields: dietary_restrictions and allergens
        
        # You have the following tasks:
        Create new and detailed recipe(s) that satisfies the {{dietary_restrictions}} and contains none of these allergens {{allergens}} from the input
        Use can use the **search_web** or **fetch** tool to get ideas for the recipe.
        
        ## Output format: You must output all of the following fields for each recipe:
        1. Recipe's name: [Must contain specific ingredients e.g a veggie or kind of meat ...]
        2. Short description [Must not indicate this is a collection of recipes]
        3. Ingredients: List of ingredients needed including *detailed quantity*
        4. Source: The source of the recipe

        ## Output validation: Make sure the recipe(s) meet the following criteria:
        1. Each of the recipes' name must include specific ingredients e.g. 'Fresh mango salad' or 'Frech Chicken stew with lentils'
        2. if the name or description indicates the founded link is a collection of recipes like 'Dairy-Free, Gluten-Free and Nut-Free Recipes'" >> INVALID
        3. You must be able to specify the ingredients list e.g '3 ripe mangos, diced, 1 medium red bell pepper, chopped..'
        
        If any of the above criteria are not met, mean your recipes are invalid.
        """,
        tools=[search_web] + fetch_tools,
        verbose=True,
    )

    filesystem_agent = FunctionAgent(
        name="File System Agent",
        description="Agent using file system tools",
        tools=filesystem_tools,
        system_prompt="""You are an AI assistant for Tool Calling having access to the file system""",
    )

    return diet_analyze_agent, find_existing_recipes_agent, chef_matching_agent, research_agent, filesystem_agent
async def main():
    # Get agent
    diet_analyze_agent, find_existing_recipes_agent, chef_matching_agent, research_agent, filesystem_agent = await define_agents()
   
    # Sample guest list
    guest_list = [
        {
            "is_gluten_free": True,
            "allergens": ["nuts"]
        },
        {
            "is_gluten_free": True,
            "is_vegetarian": True,
            "allergens": ["nuts"]
        },
        {
            "allergens": ["chicken"]
        }
    ]

    # Initialize and run workflow
    workflow = CateringMultiAgentFlow(timeout=130, verbose=True)
    handler = workflow.run(
        guest_list=guest_list,
        diet_analyze_agent=diet_analyze_agent,
        find_existing_recipe_agent=find_existing_recipes_agent,
        chef_matching_agent=chef_matching_agent,
        research_agent=research_agent,
        filesystem_agent=filesystem_agent,
        llm=llm
    )

    # Stream and print events
    async for event in handler.stream_events():
        if isinstance(event, DietaryAnalysisEvent):
            print("===DietaryAnalysisEvent===")
            print(event.guest_list)
        elif isinstance(event, FindExistingRecipeEvent):
            print("===FindExistingRecipeEvent===")
            print(event.requirement)
        elif isinstance(event, SearchRecipeEvent):
            print("===SearchRecipeEvent===")
            print(event.requirement)
        elif isinstance(event, ReviewEvent):
            print("===ReviewEvent===")
        elif isinstance(event, MatchChefEvent): 
            print("===MatchChefEvent===")
            print(event.recipes_found)
        elif isinstance(event, FinalizeEvent):
            print("===FinalizeEvent===")
            print(event.result)

    final_result = await handler
    print(final_result)

if __name__ == "__main__":
    asyncio.run(main()) 