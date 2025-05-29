from ..lib import agent
import asyncio

async def run_agent():
    """Asynchronous function to initialize and run the agent."""
    main_agent = agent.Agent(system_prompt="You are a master orchestrator, you are created to test your ability to create sub agents",verbose=True)
    print(await main_agent.run(user_msg="Create two subagents named 'AgentA' and 'AgentB' with the functions you are provided with. Then, using the 'call_specific_sub_agent' tool, call 'Main_Agent/AgentA' and 'Main_Agent/AgentB', ask them how they are feeling, and respond to their answers."))

if __name__ == "__main__":
    try:
       asyncio.run(run_agent())
    except ImportError as e:
        print(f"ImportError: {e}")
        print("This script seems to be part of a package. "
              "Try running it as a module from the directory *above* your package.")
        print("For example, if your script is in 'my_package/scripts/this_script.py' "
              "and 'lib' is 'my_package/lib', run from the directory containing 'my_package':")
        print("  python -m my_package.scripts.this_script")
        print("Or, adjust your PYTHONPATH if 'lib' is not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
