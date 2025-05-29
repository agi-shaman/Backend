from pathlib import Path
from ..lib import agent
import asyncio

async def run_agent():
    """Asynchronous function to initialize and run the agent."""
    enhanced_system_prompt = (
        "You are a helpful assistant with advanced capabilities, including managing sub-agents "
        "and processing PDF documents. You can load PDFs, list them, and query their content. "
        "When asked about a PDF, first ensure it's loaded using its file path and a chosen ID. "
        "Then, use that ID to query the PDF.\n\n"
        "If a user asks to modify, edit, or fill in an existing PDF:\n"
        "1. Clearly state that you cannot directly edit or alter PDF files, as this is beyond your current tool capabilities for existing files.\n"
        "2. Propose a constructive workaround: Offer to create a *new* PDF document that incorporates the content of the original PDF along with the user's desired changes or filled-in information.\n"
        "3. Explain the general process you would follow:\n"
        "   a. You will first need to load the original PDF (e.g., `Backend/test.pdf`) using your `load_pdf_document` tool to access its content.\n"
        "   b. Then, you will need to understand its content. This might involve you querying the PDF for its text or structure. You may need to ask the user for key information about the original document or to provide specific text segments.\n"
        "   c. Crucially, you must ask the user for the specific information they want to fill in or change. This includes identifying the 'placeholders' (e.g., specific text like `[NAME]`, `_________`, or sections to be updated) and the new content for each.\n"
        "   d. After gathering all necessary information (original content to be preserved, user's new data, and clear instructions on where changes go), you will use your `create_document_from_description` tool. The 'document_description' you formulate for this tool should be a comprehensive instruction set for generating the *new* document, effectively telling the writer AI how to construct the new PDF with the original structure and the new information integrated.\n"
        "Remember to emphasize that this process results in a brand new PDF document, generated based on markdown content. While you aim for professional formatting, the layout and appearance of the new PDF might differ from the original PDF. You are not 'copying' or 'editing' the original file itself."
    )

    my_agent = agent.Agent(system_prompt=enhanced_system_prompt,verbose=True)
    

    user_task = "load Backend/test.pdf at the current dir, and fill in the information needed with place holders, in a new pdf file(copy the current file and change the fields needed for change)"

    user_task = "load Backend/test.pdf at the current dir, and fill in the information needed with place holders, in a new pdf file(copy the current file and change the fields needed for change)"
    
    print(f"--- [Main_Agent] Task for agent: {user_task} ---")
    response = await my_agent.run(user_task)
    print(f"Agent Response: {response}")

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
