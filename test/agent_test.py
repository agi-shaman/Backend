from pathlib import Path
# Assuming 'agent' is in 'lib' and 'agent_test.py' is in 'scripts',
# and the script is run as a module from the directory *above* 'scripts' and 'lib'.
# Example: python -m scripts.agent_test
# Adjust the import based on your actual project structure if this template doesn't match.
try:
    from ..lib import agent # If agent_test.py is in a subpackage like 'scripts'
except ImportError:
    # Fallback if run directly and lib is in PYTHONPATH or same dir (less common for packages)
    from lib import agent


import asyncio

async def run_agent():
    """Asynchronous function to initialize and run the agent."""

    autonomous_system_prompt = (
        "You are a highly autonomous assistant skilled in PDF processing. You can load PDFs, query their content, and generate new documents. "
        "Your primary goal is to complete tasks without asking for clarification, making reasonable assumptions where necessary.\n\n"
        "**FILE PATHS:**\n"
        "When a user provides a file path like 'Dir/file.pdf' or 'file.pdf', use that path directly with your tools. "
        "Your tools resolve paths relative to the agent's current working directory (CWD). "
        "For example, if the user says 'load Backend/test.pdf' and your CWD is '/home/dev/Projects/MyProject', your tools will look for '/home/dev/Projects/MyProject/Backend/test.pdf'. "
        "If the user says 'load test.pdf' and your CWD is '/home/dev/Projects/Backend', tools will look for '/home/dev/Projects/Backend/test.pdf'. "
        "Do not try to second-guess paths unless a tool returns a file not found error, in which case, state the path you tried.\n\n"
        "**TASK: AUTONOMOUS PDF MODIFICATION (CREATING A NEW PDF)**\n"
        "If a user asks to 'fill in placeholders', 'modify', 'edit', or 'copy and change fields' in an existing PDF, you MUST follow this autonomous procedure to create a NEW PDF. You CANNOT edit existing PDF files directly.\n"
        "1.  **Acknowledge & Plan (Briefly):** State that you will autonomously process the PDF as requested and create a new one.\n"
        "2.  **Load PDF:** Use the `load_pdf_document` tool. Provide the `pdf_file_path` exactly as given by the user. Assign a unique `pdf_id` yourself (e.g., 'original_doc_auto_process').\n"
        "3.  **Extract Full Text:** Use the `query_pdf_document` tool on the loaded PDF. Your `query_text` must be: 'Extract all text content from this document. Try to preserve line breaks and general structure if possible in the text output.' The quality of this extraction is critical for placeholder identification.\n"
        "4.  **Identify Missing Information:** Analyze the extracted text content to identify any sections, fields, or placeholders that appear incomplete or require information. This includes explicit placeholders (like sequences of 3 or more underscores `___`, bracketed terms `[]` or `{{}}`) as well as sections that are clearly meant to contain specific details but are currently empty or generic (e.g., 'Contact Information', 'Printed Name:', 'Signature:', 'Date:').\n"
        "5.  **Generate and Substitute Generic Information:** For each identified section or field requiring information, generate plausible, generic data based on the document's context (e.g., trip details, contact info, approval fields). Replace the original text in these identified areas with the generated generic information. Clearly mark the substituted content, for example: `[AI AUTONOMOUSLY FILLED: Generated Contact Details]`, `[AI AUTONOMOUSLY FILLED: John Doe]`, `[AI AUTONOMOUSLY FILLED: Signed]`, `[AI AUTONOMOUSLY FILLED: 2025-08-20]`.\n"
        "6.  **Construct New Document Description:** The *entire modified text content* (i.e., the original text with your substitutions made) becomes the 'document_description' for creating the new PDF.\n"
        "7.  **Create New PDF:** Use the `create_document_from_description` tool. For the `requested_filename` argument, derive a name from the original, like `originalFilename_filled_autonomously` (e.g., if original was `test.pdf`, use `test_filled_autonomously`).\n"
        "8.  **Report Outcome:** Your final response to the user must confirm task completion. State the path to the NEWLY created PDF. Briefly mention that placeholders were identified (or an attempt was made) and filled autonomously using generic data. Do NOT ask for user confirmation at any step; execute the entire process autonomously.\n\n"
        "**Output Expectations:**\n"
        "The new PDF will be generated from markdown. Its formatting and layout will likely differ significantly from the original PDF. This is an expected outcome of creating a new document based on extracted and modified text, rather than direct editing."
    )

    my_agent = agent.Agent(
        system_prompt=autonomous_system_prompt,
        verbose=True
    )
    
    # The user task as provided in the problem description
    user_task = "load Backend/test.pdf at the current dir, and fill in the information needed with place holders, in a new pdf file(copy the current file and change the fields needed for change)"
    
    print(f"\n--- [Test Script] Task for agent: {user_task} ---")

    # Determine CWD for context.
    # The problem log `(.venv) [dev@archlinux Backend]$ ./run.sh` implies CWD for `run.sh` is `.../Backend`.
    # If `run.sh` executes `python ../scripts/agent_test.py` (or similar, maintaining CWD),
    # then `Path.cwd()` in this script will be `.../Backend`.
    # The user's path "Backend/test.pdf" from this CWD would mean ".../Backend/Backend/test.pdf".
    # The agent's `load_pdf_document` tool resolves `Path("Backend/test.pdf")`.
    # So, the dummy PDF needs to be at this location for the agent to find it.
    
    cwd = Path.cwd()
    # Path for the dummy PDF as the agent will interpret "Backend/test.pdf" from the CWD
    # This assumes the CWD of the Python script is the 'Backend' directory mentioned in the shell prompt.
    # If the script is run from a project root, and 'Backend' is a subdir, this path will be ProjectRoot/Backend/test.pdf
    # The system prompt tells the LLM to use "Backend/test.pdf" literally.
    # So if CWD is /abs/path/to/ProjectRoot, tool will try to load /abs/path/to/ProjectRoot/Backend/test.pdf
    # This matches the dummy PDF creation path below.
    dummy_pdf_relative_path = "Backend/test.pdf"
    dummy_pdf_full_path = cwd / dummy_pdf_relative_path

    print(f"--- [Test Script] Ensuring dummy PDF exists at: {dummy_pdf_full_path.resolve()} (relative to CWD: {cwd}) ---")

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
