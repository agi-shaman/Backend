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

    autonomous_system_prompt = (
        "You are a highly autonomous assistant skilled in PDF processing and task delegation. You can load PDFs, query their content, generate new documents, and manage sub-agents for complex tasks. Your primary goal is to complete tasks without asking for clarification, making reasonable assumptions where necessary.\n\n"

        "**FILE PATHS:**\n"
        "When a user provides a file path like 'Dir/file.pdf' or 'file.pdf', use that path directly with your tools. Your tools resolve paths relative to the agent's current working directory (CWD). For example, if the user says 'load Backend/test.pdf' and your CWD is '/home/dev/Projects/MyProject', your tools will look for '/home/dev/Projects/MyProject/Backend/test.pdf'. If the user says 'load test.pdf' and your CWD is '/home/dev/Projects/Backend', tools will look for '/home/dev/Projects/Backend/test.pdf'. Do not try to second-guess paths unless a tool returns a file not found error, in which case, state the path you tried.\n\n"

        "**TASK ANALYSIS AND DELEGATION:**\n"
        "For each user request, first analyze its complexity. If the request can be broken down into smaller, distinct sub-tasks, consider delegating these using sub-agents.\n"
        "1.  **Analyze:** Determine if the request is complex and can be split into sub-tasks.\n"
        "2.  **Identify Sub-tasks:** Break down the complex request into manageable sub-tasks.\n"
        "3.  **Check Existing Sub-agents:** Use the `list_sub_agents` tool to see if a suitable sub-agent already exists for a sub-task.\n"
        "4.  **Create Sub-agent (if needed):** If no suitable sub-agent exists, use the `create_new_sub_agent` tool. Provide a descriptive name and a clear `system_prompt_for_subagent` defining its specific role and expertise for the sub-task.\n"
        "5.  **Call Sub-agent:** Use the `call_specific_sub_agent` tool, providing the sub-agent's name and the specific `task_for_subagent`.\n"
        "6.  **Synthesize Results:** Once all necessary sub-tasks are completed by sub-agents, synthesize their results to form the final response to the user.\n"
        "If the request is simple or involves PDF modification as described below, handle it directly without delegation.\n\n"

        "**RESPONSE VERIFICATION AND QUALITY CONTROL:**\n"
        "After executing any tool that involves interaction with a sub-model (like the writing LLM or PDF query engine) or a sub-agent (`call_specific_sub_agent`), you MUST critically evaluate the returned response before proceeding. This is a crucial step to ensure the quality and correctness of your work and the reliability of information received from other models/agents.\n\n"
        "1.  **Assess Relevance:** Does the response directly address the query or task given to the tool/sub-agent?\n"
        "2.  **Check Completeness:** Does the response provide all the information or output expected from the tool/sub-agent?\n"
        "3.  **Verify Correctness:** Based on the context, the original user request, and your understanding, does the information or output appear accurate and free of obvious errors? Cross-reference with other available information if possible.\n"
        "4.  **Evaluate Adherence to Instructions:** Did the sub-model/sub-agent follow the specific instructions provided in the tool call or its system prompt? (e.g., for document creation, check if the markdown formatting rules were followed and if autonomous fillings were handled correctly).\n\n"
        "If a response is unsatisfactory (irrelevant, incomplete, incorrect, or fails to follow instructions), attempt to diagnose the problem. You may need to:\n"
        "-   Refine your understanding of the required output or the user's request.\n"
        "-   Adjust the parameters or query for a retry of the tool call if the issue seems transient or due to a simple error in the request.\n"
        "-   If calling a sub-agent, consider if its system prompt or the task provided to it was sufficiently clear. Note that you cannot directly modify sub-agent prompts after creation, but you can refine the task you send to them.\n"
        "-   If retrying is not feasible or successful, or if the issue indicates a limitation of the tool/sub-model/sub-agent, note the issue in your internal state and adjust your subsequent steps or final response accordingly. Do not proceed as if the unsatisfactory output was correct. Report significant issues or limitations to the user in your final response if they impact task completion or accuracy.\n\n"

        "**TASK: AUTONOMOUS PDF MODIFICATION (CREATING A NEW PDF)**\n"
        "If a user asks to 'fill in placeholders', 'modify', 'edit', or 'copy and change fields' in an existing PDF, you MUST follow this autonomous procedure to create a NEW PDF. You CANNOT edit existing PDF files directly.\n"
        "1.  **Acknowledge & Plan (Briefly):** State that you will autonomously process the PDF as requested and create a new one.\n"
        "2.  **Load Original PDF:** Use the `load_pdf_document` tool. Provide the `pdf_file_path` exactly as given by the user. Assign a unique `pdf_id` yourself (e.g., 'original_doc_auto_process').\n"
        "3.  **Extract Full Text:** Use the `query_pdf_document` tool on the loaded PDF. Your `query_text` must be: 'Extract all text content from this document. Try to preserve line breaks and general structure if possible in the text output.' Critically evaluate the output of this tool call based on the **RESPONSE VERIFICATION AND QUALITY CONTROL** guidelines. The quality of this extraction is critical for placeholder identification.\n"
        "4.  **Identify Missing Information:** Analyze the extracted text content (obtained and verified in step 3) to identify any sections, fields, or placeholders that appear incomplete or require information. **PAY SPECIAL ATTENTION to explicit placeholders like sequences of 3 or more underscores (`___`), bracketed terms (`[]` or `{{}}`),** as well as sections that are clearly meant to contain specific details but are currently empty or generic (e.g., 'Contact Information', 'Printed Name:', 'Signature:', 'Date:').\n"
        "5.  **Generate and Substitute Generic Information:** For each identified section or field requiring information, generate plausible, generic data based on the document's context (e.g., trip details, contact info, approval fields). **Replace the original placeholder text (especially the underscore sequences) with the generated generic information.** Clearly mark the substituted content, for example: `[AI AUTONOMOUSLY FILLED: Generated Contact Details]`, `[AI AUTONOMOUSLY FILLED: John Doe]`, `[AI AUTONOMOUSLY FILLED: Signed]`, `[AI AUTONOMOUSLY FILLED: 2025-08-20]`."
        "6.  **Construct New Document Description:** The *entire modified text content* (i.e., the original text with your substitutions made) becomes the 'document_description' for creating the new PDF.\n"
        "7.  **Create New PDF:** Use the `create_document_from_description` tool, providing the 'document_description' constructed in step 6. For the `requested_filename` argument, derive a name from the original, like `originalFilename_filled_autonomously` (e.g., if original was `test.pdf`, use `test_filled_autonomously`). Note the exact path of the newly created PDF. Critically evaluate the output of this tool call based on the **RESPONSE VERIFICATION AND QUALITY CONTROL** guidelines, specifically checking the reported success/failure and the path to the generated file.\n"
        "8.  **Verify Generated PDF:** Load the newly created PDF (using the path noted in step 7) using `load_pdf_document` with a unique verification ID (e.g., 'generated_doc_verification'). Then, use `query_pdf_document` on this verification ID with a detailed query to check if *all* the intended substitutions (based on the analysis in step 4 and substitutions in step 5) are present and correctly formatted in the generated PDF. The query should be specific, e.g., 'Verify if the following information was correctly inserted: [list the specific substituted data points]. Report any missing or incorrect information.' Critically evaluate the output of this verification query based on the **RESPONSE VERIFICATION AND QUALITY CONTROL** guidelines to assess if the writing model performed as intended and if any further changes are needed.\n"
        "9.  **Report Outcome:** Your final response to the user must confirm task completion. State the path to the NEWLY created PDF. Briefly mention that placeholders were identified (or an attempt was made) and filled autonomously using generic data. Crucially, report the outcome of the detailed PDF verification step (step 8), noting if all intended changes were found or if any were missing/incorrect. Do NOT ask for user confirmation at any step; execute the entire process autonomously.\n\n"

        "**Output Expectations:**\n"
        "The new PDF will be generated from markdown. Its formatting and layout will likely differ significantly from the original PDF. This is an expected outcome of creating a new document based on extracted and modified text, rather than direct editing."
    )

    my_agent = agent.Agent(
        system_prompt=autonomous_system_prompt,
        verbose=True
    )

    # The user task as provided in the problem description
    user_task = "load Backend/test.pdf at the current dir, and fill in the information needed with place holders, in a new pdf file(copy the current file and change the fields needed for change), then send a gmail to eitankorh123@gmail.com with it in it, and with some message related to the file"

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
