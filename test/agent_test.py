from pathlib import Path
from ..lib import agent
import asyncio

async def run_agent():
    """Asynchronous function to initialize and run the agent."""
    test_pdf_path = Path("test_document.pdf")

    my_agent = agent.Agent(
        system_prompt=
            "You are a helpful assistant with advanced capabilities, including managing sub-agents "
            "and processing PDF documents. You can load PDFs, list them, and query their content. "
            "When asked about a PDF, first ensure it's loaded using its file path and a chosen ID. "
            "Then, use that ID to query the PDF."
        ,verbose=True)
    
    # Test 1: List currently (empty) loaded PDFs
    response = await my_agent.run("List all loaded PDF documents.")
    print(f"Test 1 Response: {response}") # Expected: No PDFs loaded.

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
