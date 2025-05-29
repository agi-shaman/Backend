from pathlib import Path
# Assuming 'agent' is in 'lib' and 'agent_test.py' is in 'scripts',
# and the script is run as a module from the directory *above* 'scripts' and 'lib'.
# Example: python -m scripts.agent_test
# Adjust the import based on your actual project structure if this template doesn't match.
from ..lib import agent 


import asyncio
from unittest.mock import patch, MagicMock

# Add imports for Gmail API components needed for mocking
# These might not be strictly necessary if we mock the build function directly,
# but good to have for clarity or if mocking at a different level.
# We'll mock the build function, so we primarily need MagicMock and patch.
# from googleapiclient.discovery import build
# from google.oauth2.credentials import Credentials as GoogleCredentials
# from googleapiclient.errors import HttpError


async def run_agent():
    """Asynchronous function to initialize and run the agent."""
    my_agent = agent.Agent(
        verbose=True
    )

    user_task = "load Backend/test.pdf at the current dir, and write me a .xlsx file including all of the needed information for filling it"

    print(f"\n--- [Test Script] Task for agent: {user_task} ---")
    response = await my_agent.run(user_task)
    print(f"\n--- [Test Script] Final Agent Response from run_agent: ---")
    print(response)
    print(f"--- [Test Script] End of Final Agent Response ---")

if __name__ == "__main__":
    try: 
       asyncio.run(run_agent())
    except ImportError as e:
        if "attempted relative import with no known parent package" in str(e) or ".." in str(e):
            print(f"ImportError: {e}")
            print("This script might be run directly instead of as a module, or the package structure is not standard.")
            print("Try running it as a module from the directory *above* 'scripts' (e.g., your project root).")
            print("Example: If structure is ProjectRoot/scripts/agent_test.py and ProjectRoot/lib/agent.py:")
            print("  cd ProjectRoot")
            print("  python -m scripts.agent_test")
            print("Ensure 'lib' directory is correctly recognized as a package (e.g. has __init__.py if needed).")
        else:
            print(f"An other ImportError occurred: {e}")
        import traceback
        traceback.print_exc()

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
