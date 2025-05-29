from ..lib import agent
import asyncio

async def run_agent():
    """Asynchronous function to initialize and run the agent."""
    main_agent = agent.Agent()  # Or however your Agent class is initialized
    # Assuming main_agent.agent.run is an async method
    response = await main_agent.agent.run(user_msg="test")
    print(str(response))

if __name__ == "__main__":
    # asyncio.run() is the standard way to call an async function
    # from synchronous code. It takes care of managing the event loop.
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
