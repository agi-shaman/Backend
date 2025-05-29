import time
from email import encoders
from llama_index.core.agent.workflow import FunctionAgent
import shutil
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.readers.web import SimpleWebPageReader

from .QueryTypes import QueryTypes
from .rate_limited_gemini import RateLimitedGemini
from .FileDecoder import get_file_content
from dotenv import load_dotenv
import os
from llama_index.core.tools import FunctionTool
from llama_index.core.memory import ChatMemoryBuffer
from pathlib import Path
from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage,
    Settings,
Document,
)
from .firebase import get_user_google_access_token
from llama_index.readers.file import PyMuPDFReader
import re
import json
from datetime import datetime
import base64
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
import mimetypes
from google.oauth2.credentials import Credentials as GoogleCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import traceback # Ensure traceback is imported for error logging

try:
    from .pdf_writer_utility import create_styled_pdf_from_markdown
except ImportError:
    try:
        from .pdf_writer_utility import create_styled_pdf_from_markdown
    except ImportError as e_inner:
        raise ImportError(
            "Could not import 'create_styled_pdf_from_markdown' from 'pdf_writer_utility'. "
            "Ensure 'pdf_writer_utility.py' is in the Python path or the same directory. Original error: " + str(e_inner)
        )

load_dotenv()
GeminiKey = os.getenv("GeminiKey")

AGENT_WORKER_LLM_MODEL = "gemini-2.5-flash-preview-05-20"

llm = RateLimitedGemini(
    model=AGENT_WORKER_LLM_MODEL,
    api_key=GeminiKey,
)


autonomous_system_prompt = (
    "You are a highly capable assistant skilled in PDF processing and task delegation. You can load PDFs, query their content, generate new documents, and manage sub-agents for complex tasks. Your primary directive is to ensure accuracy, completeness, and adherence to instructions in all your operations through rigorous self-assessment and verification, and to complete all planned actions for a user's request within a turn before responding.\n\n"

    "**GATHERING REQUIRED INFORMATION FROM USER:**\n"
    "If, at any point during a task, you determine that you need specific information from the user to proceed or complete the task, you MUST use the `get_text_input` tool.\n"
    "If you need *multiple* distinct pieces of information, you MUST ask for EACH piece INDIVIDUALLY using a separate call to `get_text_input`.\n"
    "For each call to `get_text_input`, formulate a clear and specific prompt that asks for *only* one piece of information.\n"
    "For example, instead of asking \"Please provide the name and address:\", you should make two separate calls:\n"
    "1. Use `get_text_input` with the prompt: \"Please provide the full name:\"\n"
    "2. After receiving the response, use `get_text_input` again with the prompt: \"Please provide the address:\"\n"
    "Identify all necessary information you need and collect it piece by piece using individual, specific prompts via `get_text_input` before proceeding with the task that requires this information.\n\n"
    "When a task requires filling in information (e.g., in a document, email, or other output), you MUST first identify *all* the specific pieces of information needed from the user.\n"
    "To identify needed information, carefully analyze the user's request and, if applicable, the content of any relevant documents (like PDFs loaded using `load_pdf_document`). You may need to use `query_pdf_document` to extract details about required fields or placeholders.\n"
    "Once you have identified the distinct pieces of information required, you MUST use the `get_text_input` tool to ask for EACH piece INDIVIDUALLY. Formulate a clear and specific prompt for each single piece of information you need.\n"
    "For example, if you need a name, an address, and a date, you would make three separate calls to `get_text_input`:\n"
    "1. Use `get_text_input` with the prompt: \"Please provide the full name:\"\n"
    "2. After receiving the response, use `get_text_input` again with the prompt: \"Please provide the full address:\"\n"
    "3. After receiving that response, use `get_text_input` again with the prompt: \"Please provide the date (YYYY-MM-DD):\"\n"
    "Collect *all* necessary information from the user using this individual prompting method before proceeding with any steps that require this collected data (e.g., creating a document, sending an email).\n\n"

    "**FILE PATHS:**\n"
    "When a user provides a file path like 'Dir/file.pdf' or 'file.pdf', use that path directly with your tools. Your tools resolve paths relative to the agent's current working directory (CWD). For example, if the user says 'load Backend/test.pdf' and your CWD is '/home/dev/Projects/MyProject', your tools will look for '/home/dev/Projects/MyProject/Backend/test.pdf'. If the user says 'load test.pdf' and your CWD is '/home/dev/Projects/Backend', tools will look for '/home/dev/Projects/Backend/test.pdf'. Do not try to second-guess paths unless a tool returns a file not found error, in which case, state the path you tried.\n\n"

    "**TASK ANALYSIS AND DELEGATION (PLANNING PHASE):**\n"
    "For each user request, first analyze its complexity and plan your actions:\n"
    "1.  **Analyze Goal:** Thoroughly understand the user's overall goal.\n"
    "2.  **Identify Sub-tasks:** Determine if the request can be broken down into smaller, distinct sub-tasks. For each sub-task, decide if it requires delegation to a sub-agent, direct execution by you using a tool (e.g., `create_document_from_description`), or direct processing by you.\n"
    "3.  **Formulate Plan:** Create a logical sequence of these sub-tasks necessary to fulfill the user's request for the current turn.\n\n"

    "**TURN EXECUTION AND FINAL RESPONSE PROTOCOL:**\n"
    "You MUST process the user's request by executing your plan fully within the current interaction turn, if feasible. Your interaction with the user should appear synchronous per turn.\n"
    "1.  **Sequential Execution of Plan:** Execute the sub-tasks in your plan one by one.\n"
    "2.  **Await Tool/Sub-agent Completion:** When you call any tool (e.g., `create_document_from_description`, `query_pdf_document`, `send_email`) or a sub-agent (`call_specific_sub_agent`), you MUST wait for that tool or sub-agent to fully complete its operation and return its actual result string (e.g., a success message with a file path, data extracted, an error message, or a sub-agent's response). Tools and sub-agents will signal their completion through their return value.\n"
    "3.  **Use Actual Tool/Sub-agent Results:** The string returned by a tool or sub-agent is its definitive output for that call. You MUST use this specific output (e.g., an actual file path from a document creation tool, data from a query tool) to inform your next action, for verification, or to populate arguments for subsequent tool calls (like using an actual file path for an email attachment). Do not guess or assume outputs before they are returned by the tool/sub-agent.\n"
    "4.  **Verify Each Sub-task:** After each sub-task (tool call, sub-agent call, or internal processing step) completes and returns its result, you MUST critically evaluate this result using the 'COMPREHENSIVE VERIFICATION AND SELF-CORRECTION' checklist below. Ensure it is complete, correct, relevant, and adheres to instructions *before proceeding to the next step in your plan* or to formulating the final response.\n"
    "5.  **Comprehensive Final Response for the Turn:** Only after all planned sub-tasks for the user's request in the current turn have been executed, their actual results obtained, and each result verified, should you synthesize all information and generate a single, comprehensive final response to the user. This response should clearly state what was achieved (e.g., 'The document 'X.pdf' has been created at [full_path_to_X.pdf] and an email with this attachment has been sent to Y.') or report any unrecoverable errors that prevented completion of parts of the request.\n"
    "6.  **No Premature Status Updates as Final Response:** CRITICALLY, do NOT provide interim status updates (e.g., 'I am currently creating the document, please wait.' or 'Processing your request...') as your *final answer for the turn*. Your final answer must reflect the *outcome* of all completed work for that turn. If a complex, multi-step user request is genuinely too large to fully complete in one turn, your final response should detail what specific sub-tasks *were fully completed and verified*, what their outputs were, and what explicitly remains for a subsequent turn. However, always aim to complete the user's immediate request fully within the current turn if feasible.\n\n"

    "**SUB-AGENT MANAGEMENT (If delegating):**\n"
    "1.  **Check Existing Sub-agents:** Use the `list_sub_agents` tool to see if a suitable sub-agent already exists for a sub-task.\n"
    "2.  **Create Sub-agent (if needed):** If no suitable sub-agent exists, use the `create_new_sub_agent` tool. Provide a descriptive name and a clear `system_prompt_for_subagent` defining its specific role and expertise for the sub-task.\n"
    "3.  **Call Sub-agent:** Use the `call_specific_sub_agent` tool, providing the sub-agent's name and the specific `task_for_subagent`. Await its completion and result as per 'TURN EXECUTION AND FINAL RESPONSE PROTOCOL'.\n"
    "4.  **Synthesize Results:** Once all necessary sub-tasks (including those by sub-agents) are completed and verified, synthesize their results to form the final response to the user.\n\n"

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
    "4.  **Identify Missing Information:** Analyze the extracted text content (obtained and verified in step 3) to identify any sections, fields, or placeholders that appear incomplete or require information. **PAY SPECIAL ATTENTION to explicit placeholders like sequences of 3 or more underscores (`___`), bracketed terms (`[]` or `{{}}`),** as well as sections that are clearly meant to contain specific details but are currently empty or generic.\n"
    "5.  **Generate and Substitute Generic Information:** For each identified section or field requiring information, ask for data based on the document's context (e.g., trip details, contact info, approval fields). **Replace the original placeholder text (especially the underscore sequences) with the information you got from the user."
    "6.  **Construct New Document Description:** The *entire modified text content* (i.e., the original text with your substitutions made) becomes the 'document_description' for creating the new PDF.\n"
    "7.  **Create New PDF:** Use the `create_document_from_description` tool, providing the 'document_description' constructed in step 6. For the `requested_filename` argument, derive a name from the original, like `originalFilename_filled_autonomously` (e.g., if original was `test.pdf`, use `test_filled_autonomously`). Note the exact path of the newly created PDF. Critically evaluate the output of this tool call based on the **RESPONSE VERIFICATION AND QUALITY CONTROL** guidelines, specifically checking the reported success/failure and the path to the generated file.\n"
    "8.  **Verify Generated PDF:** Load the newly created PDF (using the path noted in step 7) using `load_pdf_document` with a unique verification ID (e.g., 'generated_doc_verification'). Then, use `query_pdf_document` on this verification ID with a detailed query to check if *all* the intended substitutions (based on the analysis in step 4 and substitutions in step 5) are present and correctly formatted in the generated PDF. The query should be specific, e.g., 'Verify if the following information was correctly inserted: [list the specific substituted data points]. Report any missing or incorrect information.' Critically evaluate the output of this verification query based on the **RESPONSE VERIFICATION AND QUALITY CONTROL** guidelines to assess if the writing model performed as intended and if any further changes are needed.\n"
    "9.  **Report Outcome:** Your final response to the user must confirm task completion. State the path to the NEWLY created PDF. Briefly mention that placeholders were identified (or an attempt was made), Crucially, report the outcome of the detailed PDF verification step (step 8), noting if all intended changes were found or if any were missing/incorrect. execute the entire process autonomously except information requests.\n\n"
)

PDF_CONTEXT_LLM_MODEL = "gemini-2.5-flash-preview-05-20"
PDF_CONTEXT_LLM_TEMP = 0.1
PDF_EMBED_MODEL_NAME = "models/embedding-001"
PDF_CHUNK_SIZE = 512
PDF_CHUNK_OVERLAP = 50
ITEM_SIMILARITY_TOP_K = 4
PDF_PERSIST_BASE_DIR_NAME = "agent_pdf_storage"
WRITING_LLM_MODEL = "gemini-2.5-flash-preview-05-20"  # Can be same as PDF_CONTEXT_LLM_MODEL or different
WRITING_LLM_TEMP = 0.7 # Temperature for creative document generation
WRITING_OUTPUT_BASE_DIR_NAME = "agent_generated_documents"

PDF_TYPE = "pdf"
FILE_TYPE = "file"
URL_TYPE = "url"

WRITING_SYSTEM_PROMPT_TEMPLATE = """
You are an expert AI document author, specializing in creating dense, well-structured, and professionally formatted documents suitable for formal use. Your output MUST be pure markdown, adhering strictly to the following guidelines.

DOCUMENT STRUCTURE & FORMATTING (MANDATORY MARKDOWN):
1.  **Main Title (Implicit from first H1):** Your response MUST begin directly with the main title of the document, formatted as `# Document Title`. This title should be descriptive and formal. Do NOT output any text before this H1 title.
2.  **Sections (H2):** Use `## Section Title` for all primary sections. Ensure logical flow.
3.  **Subsections (H3):** Use `### Subsection Title` for sub-topics within sections.
4.  **Emphasis:**
    *   Use `**bold text**` for strong emphasis on key terms, definitions, or critical points.
    *   Use `*italic text*` or `_italic text_` for mild emphasis (e.g., foreign words, titles of works, or subtle highlights).
5.  **Lists:**
    *   Use `* List item` or `- List item` for unordered bulleted lists. Ensure consistent formatting. Indent sub-lists if necessary (e.g. two spaces before the asterisk).
6.  **Paragraphs:** Write concise, information-dense paragraphs with clear topic sentences. Aim for maximum clarity and efficiency with minimal word count. Avoid redundancy and unnecessary adjectives or adverbs. Every sentence must contribute significant value.
7.  **Horizontal Rules:** If a strong visual separation is absolutely essential between major distinct content blocks (not typically between H2/H3 sections, but perhaps to delineate a completely different part of the document like an appendix from the main body, or before a signature block if it's not under a ## Signatures heading), use `---` on its own line. Use VERY sparingly.

CONTENT REQUIREMENTS:
1.  **Direct Output:** Start your response DIRECTLY with the H1 markdown title. NO conversational filler, introductions like "Okay, here is the document...", or self-referential statements ("As an AI...").
2.  **Density and Efficiency:** The document must be as compact and information-dense as possible while remaining perfectly readable and comprehensive. Your goal is to convey all necessary information in the fewest possible words and pages. Prioritize impactful information over lengthy explanations.
3.  **Professional Tone:** Maintain a highly formal, objective, and polished tone throughout the entire document.
4.  **Completeness:** Ensure the document is self-contained and thoroughly covers the requested topic from introduction to conclusion, as appropriate for the document type.
5.  **Handle Autonomous Fillings:** The input text will contain sections marked like `[AI AUTONOMOUSLY FILLED: Some generated text]`. **CRITICAL:** When you encounter this pattern, you MUST render *only* the text inside the brackets (`Some generated text`) in the final markdown output. This generated text should **completely replace** the original text that was within the brackets, including any placeholder characters like underscores (`___`) or bracketed terms (`[]`, `{{}}`). Ensure the surrounding labels (e.g., "Printed Name:", "Signature:", "Date:") are preserved and the generated text is placed immediately after them, replacing the original placeholder line. Do NOT include the `[AI AUTONOMOUSLY FILLED: ]` part in the output markdown.

USER'S DOCUMENT REQUEST: "{user_document_request}"

Remember: Begin your response *immediately* with the H1 markdown title.
"""

class Agent:
    def __init__(self, system_prompt: str = autonomous_system_prompt, name: str = "Main_Agent", verbose: bool = False):
        self.name = name
        self.tools = []
        self.verbose = verbose
        self.SubWorkers = {}
        self._add_tools()
        self.query_engines = {}
        self.persist_base_dir = Path(f"./{PDF_PERSIST_BASE_DIR_NAME}")
        self.persist_base_dir.mkdir(parents=True, exist_ok=True)
        self._pdf_settings_configured = False
        self._email_settings_configured = False
        self.writing_output_dir = Path(f"./{WRITING_OUTPUT_BASE_DIR_NAME}")
        self.writing_output_dir.mkdir(parents=True, exist_ok=True)
        self.plan = ""

        self.writing_llm = RateLimitedGemini(
            model_name=WRITING_LLM_MODEL, # Corrected parameter name
            api_key=GeminiKey,
            temperature=WRITING_LLM_TEMP
        )

        self.worker = FunctionAgent(
            tools=self.tools,
            llm=llm,
            system_prompt=system_prompt,)
        if self.verbose:
            print(f"--- [{self.name}] Generated documents will be saved to: {self.writing_output_dir.resolve()} ---")

        self.memory = ChatMemoryBuffer.from_defaults(token_limit=390000)
        print(f"Initialized '{self.name}' and {len(self.tools)} tools.")

    def _add_tools(self):
        """Helper method to create and add tools for the agent."""

        # --- Sub-agent management tools (from original codebase) ---
        def _list_sub_agents_tool_func() -> str:
            if self.verbose: print(f"--- [{self.name}] Tool 'list_sub_agents' called ---")
            return self.ListSubAgents()

        list_sub_agents_tool = FunctionTool.from_defaults(
            fn=_list_sub_agents_tool_func,
            name="list_sub_agents",
            description="Lists the names of all currently available sub-agents that can be called for specialized tasks."
        )
        self.tools.append(list_sub_agents_tool)

        def _create_sub_agent_tool_func(name: str, system_prompt_for_subagent: str) -> str:
            if self.verbose: print(f"--- [{self.name}] Tool 'create_new_sub_agent' called with name: {name} ---")
            return self.CreateSubAgent(name=name, system_prompt=system_prompt_for_subagent)

        create_sub_agent_tool = FunctionTool.from_defaults(
            fn=_create_sub_agent_tool_func,
            name="create_new_sub_agent",
            description=(
                "Creates a new specialized sub-agent. Use this when a new, distinct expertise is required that existing sub-agents don't cover. "
                "You need to provide a unique 'name' for the new sub-agent (which will be prefixed by this agent's name, e.g., if this agent is 'Main' and you provide 'Math', it becomes 'Main/Math') "
                "and a 'system_prompt_for_subagent' that defines its role and expertise. "
                "Example: create_new_sub_agent(name='MathExpert', system_prompt_for_subagent='You are an expert in advanced calculus and algebra.')"
            )
        )
        self.tools.append(create_sub_agent_tool)

        async def _call_sub_agent_tool_func(sub_agent_name: str, task_for_subagent: str) -> str:
            if self.verbose: print(f"--- [{self.name}] Tool 'call_specific_sub_agent' called for '{sub_agent_name}' with task: '{task_for_subagent[:70]}...' ---")
            # Logic from original codebase to correctly qualify sub-agent name
            full_sub_agent_name = sub_agent_name if "/" in sub_agent_name else f"{self.name}/{sub_agent_name}"
            return await self.CallSubAgent(name=full_sub_agent_name, task=task_for_subagent)

        call_sub_agent_tool = FunctionTool.from_defaults(
            fn=_call_sub_agent_tool_func, # This is async
            name="call_specific_sub_agent",
            description=(
                "Delegates a specific 'task_for_subagent' to a sub-agent identified by 'sub_agent_name'. "
                "First, ensure the sub-agent exists (e.g., using 'list_sub_agents' or if it was recently created). "
                "Then, provide the name of the sub-agent (e.g., 'MathExpert' if it's a direct sub-agent, or a full path like 'ParentAgent/MathExpert' if known) and the detailed task for it to perform. "
                "This is useful for explicitly directing tasks to known sub-agents."
            )
        )
        self.tools.append(call_sub_agent_tool)

        # --- URL Functionality Tools ---
        def _load_url_document_tool_func(url: str, url_id: str) -> str:
            if self.verbose: print(f"--- [{self.name}] Tool 'load_url_document' called with path: {url}, id: {url_id} ---")
            ret = self.load_and_index_Url(url=url, url_id=url_id)
            if not ret:
                ret = "The load url document tool failed to return data"
            return ret

        load_url_tool = FunctionTool.from_defaults(
            fn=_load_url_document_tool_func,
            name="load_url",
            description=(
                "Loads and indexes a website from a given url for future querying. "
                "Required arguments: 'url' (string, the full or relative url to the website), "
                "'url_id' (string, a unique identifier you assign to this URL, e.g., 'site1', 'sportscars2'). This ID will be used for querying and listing. create one yourself without asking"
                "Returns a status message. After successful loading, the website can be queried using its 'url_id'."
            )
        )
        self.tools.append(load_url_tool)

        # --- PDF Functionality Tools ---
        # --- File Functionality Tools (replaces PDF tools) ---
        def _load_file_document_tool_func(file_path: str, item_id: str, force_reindex: bool = False) -> str:
            if self.verbose: print(f"--- [{self.name}] Tool 'load_file_document' called with path: {file_path}, id: {item_id}, force_reindex: {force_reindex} ---")
            return self.load_and_index_item(file_path_str=file_path, item_id=item_id, force_reindex=force_reindex)

        load_file_tool = FunctionTool.from_defaults(
            fn=_load_file_document_tool_func,
            name="load_file_document",
            description=(
                "Loads and indexes a document from a given file path for future querying. "
                "This tool uses FileDecoder to support various formats including PDF, DOCX, XLSX, PPTX, TXT, HTML, and others. "
                "Required arguments: 'file_path' (string, the full or relative path to the file), "
                "'item_id' (string, a unique identifier you assign to this file, e.g., 'report1', 'spreadsheet_data'). This ID will be used for querying and listing. create one yourself without asking"
                "Optional argument: 'force_reindex' (boolean, defaults to False. If True, any existing index for this item_id will be deleted and rebuilt from the file). "
                "Returns a status message. After successful loading, the file content can be queried using its 'item_id'."
            )
        )
        self.tools.append(load_file_tool)

        def _query_item_document_tool_func(item_id: str, query_text: str) -> str:
            if self.verbose: print(f"--- [{self.name}] Tool 'query_item_document' called with id: {item_id}, query: '{query_text[:70]}...' ---")
            return self.query_indexed_item(item_id=item_id, query_text=query_text)

        query_item_tool = FunctionTool.from_defaults(
            fn=_query_item_document_tool_func,
            name="query_item_document",
            description=(
                "Queries a previously loaded document using its assigned id. "
                "Required arguments: 'item_id' (string, the identifier used when loading the document), "
                "'query_text' (string, the question or query about the document content). "
                "Returns the answer found in the document or an error message if the item_id is not found or an error occurs during querying."
            )
        )
        self.tools.append(query_item_tool)

        def _list_loaded_items_tool_func() -> str:
            if self.verbose: print(f"--- [{self.name}] Tool 'list_loaded_items' called ---")
            return self.list_loaded_pdfs() # Note: Function name is still list_loaded_pdfs but now lists all items

        list_items_tool = FunctionTool.from_defaults(
            fn=_list_loaded_items_tool_func,
            name="list_loaded_items",
            description="Lists the unique IDs of all documents that are currently active in memory and available for querying."
        )
        self.tools.append(list_items_tool)

        # --- NEW WAIT TOOL ---
        def _wait_seconds_tool_func(seconds: int) -> str:
            """
            Pauses the agent's execution for a specified number of seconds.
            Args:
                seconds (int): The number of seconds to wait. Must be a positive integer.
            Returns:
                str: A confirmation message.
            """
            if self.verbose:
                print(f"--- [{self.name}] Tool 'wait_seconds' called, waiting for {seconds} seconds. ---")

            try:
                s = int(seconds)
                if s <= 0:
                    return "Error: Wait duration must be a positive number of seconds."
                if s > 300:  # Optional: Set a reasonable upper limit for safety
                    print(
                        f"--- [{self.name}] Warning: Wait duration {s} is very long. Capping at 300 seconds for safety. ---")
                    s = 300

                time.sleep(s)
                msg = f"Successfully waited for {s} seconds."
                if self.verbose:
                    print(f"--- [{self.name}] {msg} ---")
                return msg
            except ValueError:
                return "Error: Invalid input for seconds. Please provide an integer."
            except Exception as e:
                error_msg = f"Error during wait: {str(e)}"
                if self.verbose:
                    print(f"--- [{self.name}] {error_msg} ---")
                return error_msg

        wait_seconds_tool = FunctionTool.from_defaults(
            fn=_wait_seconds_tool_func,
            name="wait_seconds",
            description=(
                "Pauses the agent's execution for a specified number of seconds. "
                "Use this tool if you need to introduce a delay, for example, to wait for an external process to complete, "
                "to respect a rate limit not handled by other means, or to implement a cooldown period. "
                "Required argument: 'seconds' (integer, the duration to wait in seconds, e.g., 5 for five seconds). "
                "Keep the wait time reasonable (e.g., 1 to 60 seconds typically, max 300)."
            )
        )
        self.tools.append(wait_seconds_tool)

        # --- END OF NEW WAIT TOOL ---

        async def _create_document_tool_func(document_description: str, requested_filename: str) -> str:
            if self.verbose: print(f"--- [{self.name}] Tool 'create_document_from_description' called with description: '{document_description[:70]}...' ---")
            return self._create_document_from_description_internal(
                document_description=document_description,
                requested_filename=requested_filename
            )

        create_document_tool = FunctionTool.from_defaults(
            fn=_create_document_tool_func, # This is now async
            name="create_document_from_description",
            description=(
                "Generates a styled PDF document based on a textual 'document_description'. "
                "The document content is generated by an AI writer based on your description and then converted to PDF. "
                "YOU (the main agent) MUST construct the 'document_description' carefully. If the document needs to include specific user-provided data, "
                "you must first collect that data using the 'get_text_input' tool (for each piece of information individually). "
                "Then, you MUST incorporate this data into the 'document_description' string, typically by appending a 'User Data: ' section with a JSON object of the collected key-value pairs. "
                "Example: 'Create an approval form for an educational trip. User Data: {\"Participant Name\": \"John Doe\", \"Approval Date\": \"2024-05-20\"}'. "
                "This tool ITSELF DOES NOT ask the user for input; it relies on the 'document_description' you provide to be complete and correctly formatted for the underlying writing model. "
                "Required argument: 'document_description' (string, a detailed description of the document to be created, INCLUDING any user-provided data formatted as described above). "
                "Optional argument: 'requested_filename' (string, a desired filename for the PDF, without the .pdf extension. If not provided or empty, a name will be generated based on the document title or description). "
                "Returns a message starting with 'Successfully created document. Absolute path: /path/to/your_doc.pdf' on success, "
                "or a message starting with 'Error:' if generation failed (e.g., 'Error: Writing LLM returned empty content. Document creation failed.'). "
                "You MUST use the exact absolute path returned by this tool for any subsequent actions (e.g., attaching to an email)."
            )
        )
        self.tools.append(create_document_tool)

        # --- Email Functionality Tools ---
        # Note: These tools now signal if a Google Access Token is required.
        # The agent's LLM should be prompted to use the get_cli_text_input tool
        # to obtain the token from the user if the response indicates it's needed.
        def _send_email_tool_func(recipient: str, subject: str, body: str, attachment_paths: str = "") -> str:
            """Sends an email using the Gmail API."""
            if self.verbose: print(f"--- [{self.name}] Tool 'send_email' called to {recipient} ---")
            return self._send_email_internal(recipient=recipient, subject=subject, body=body, attachment_paths=attachment_paths)

        send_email_tool = FunctionTool.from_defaults(
            fn=_send_email_tool_func,
            name="send_email",
            description=(
                "Sends an email to a specified recipient with a given subject and body. "
                "Requires a valid Google access token for the user. "
                "Required arguments: 'recipient' (string, the email address of the recipient), "
                "'subject' (string, the subject line of the email), "
                "'body' (string, the main content of the email). "
                "Optional argument: 'attachment_paths' (string, a comma-separated string of file paths to attach, e.g., '/path/to/file1.pdf,/path/to/file2.txt'). "
            )
        )
        self.tools.append(send_email_tool)

        def _draft_email_tool_func(recipient: str, subject: str, body: str, attachment_paths: str = "") -> str:
            """Creates an email draft using the Gmail API."""
            if self.verbose: print(f"--- [{self.name}] Tool 'draft_email' called for {recipient} ---")
            return self._draft_email_internal(recipient=recipient, subject=subject, body=body, attachment_paths=attachment_paths)

        draft_email_tool = FunctionTool.from_defaults(
            fn=_draft_email_tool_func,
            name="draft_email",
            description=(
                "Creates an email draft for a specified recipient with a given subject and body. "
                "Requires a valid Google access token for the user. "
                "Required arguments: 'recipient' (string, the email address of the recipient), "
                "'subject' (string, the subject line of the email), "
                "'body' (string, the main content of the email). "
                "Optional argument: 'attachment_paths' (string, a comma-separated string of file paths to attach, e.g., '/path/to/file1.pdf,/path/to/file2.txt'). "
            )
        )
        self.tools.append(draft_email_tool)

        # --- CLI Input Tool ---
        cli_input_tool = FunctionTool.from_defaults(
            fn=self._get_text_input_tool_func,
            name="get_text_input",
            description=(
                "Prompts the user via the command line for additional text input. "
                "Use this tool when you need more information from the user to complete a task. "
                "Required argument: 'prompt' what info do you need?."
                "Returns a string containing the user's input"
            )
        )
        self.tools.append(cli_input_tool)

        def _create_plan_tool_func(self, plan: str) -> str:  # Added self here as it's a method
            """Creates/stores a plan for a task."""
            self.plan = plan  # Assuming self.plan is an attribute of your agent class
            return "Plan successfully created and stored."

        create_plan_tool = FunctionTool.from_defaults(
            fn=self._create_plan_tool_func,  # Corrected to use the intended function and made it a method call
            name="create_plan",  # Changed name to snake_case for consistency, but "create plan" works if preferred
            description=(
                "Stores a provided step-by-step plan for the agent's current task. "
                "Requires a 'plan' argument as a string containing the full, pre-defined plan text. "
                "Use this tool to explicitly set the agent's action sequence when the plan has "
                "already been determined or provided (e.g., by a user or another process), "
                "rather than requiring the agent to generate the plan itself. "
                "The agent will then use this stored plan to guide its execution."
            )
        )
        self.tools.append(create_plan_tool)

        def _view_check_tool_func(self, doCheck= bool) -> str:  # Added self here as it's a method
            """
            Reviews the current execution plan. Optionally marks the current 'NEXT' step as 'DONE'
            and advances to the subsequent step if 'mark_current_step_as_done' is True.
            """
            if not self.plan or not self.parsed_plan_steps:
                # This check handles the case where _create_plan was not called or failed to parse
                if not self.plan:
                    return "No plan has been created yet. Use 'create_plan' to set a plan first."
                else: # self.plan exists but self.parsed_plan_steps is empty
                    return "A plan string exists, but it could not be parsed into actionable steps. Please check the plan format or recreate it."

            num_steps = len(self.parsed_plan_steps)
            response_parts = []

            # Action: Mark step as done (if requested and applicable)
            if doCheck:
                if self.current_step_index < num_steps:
                    # The step at current_step_index is the one being marked done
                    completed_step_text = self.parsed_plan_steps[self.current_step_index]
                    response_parts.append(f"Marking Step {self.current_step_index + 1} ('{completed_step_text}') as DONE.")
                    self.last_completed_step_index = self.current_step_index
                    self.current_step_index += 1 # Advance to the next step
                elif self.current_step_index >= num_steps and self.last_completed_step_index == num_steps - 1:
                    response_parts.append("All plan steps have already been completed. No further steps to mark done.")
                else:
                    response_parts.append("Cannot mark step as done: Already at the end of the plan, or no steps were pending to be marked.")
            else:
                if self.last_completed_step_index == -1 and self.current_step_index == 0:
                    response_parts.append("Viewing initial plan. No steps marked done yet.")
                elif self.last_completed_step_index >= 0:
                    response_parts.append(f"Viewing plan. Last completed step was {self.last_completed_step_index + 1}. No new step marked as done in this call.")
                else: # current_step_index might be > 0 but nothing completed if mark_done was always false
                    response_parts.append("Viewing plan. No steps marked done yet.")


            # Display: Show the full plan with current status
            response_parts.append("\n--- Current Plan Status ---")
            if not self.parsed_plan_steps: # Should be caught earlier, but for safety
                 response_parts.append("  (No steps in plan to display)")
            else:
                for i, step_text in enumerate(self.parsed_plan_steps):
                    if i <= self.last_completed_step_index:
                         prefix = f"  [DONE] Step {i+1}:"
                    elif i == self.current_step_index and i < num_steps: # The new current/next step
                        prefix = f"  [NEXT] Step {i+1}:"
                    elif i > self.current_step_index and i < num_steps: # Upcoming steps
                        prefix = f"         Step {i+1}:"
                    else: # Only if all steps are done and i >= num_steps (should not be hit if list ends)
                        # This case might occur if parsed_plan_steps is empty after the check above.
                        # Or if current_step_index went past num_steps unexpectedly.
                        # For safety, we just list it.
                        prefix = f"         Step {i+1}:"
                    response_parts.append(f"{prefix} {step_text}")

            # Conclusion: Indicate next step or plan completion
            if self.current_step_index < num_steps:
                next_step_text = self.parsed_plan_steps[self.current_step_index]
                response_parts.append(f"\nNext action is Step {self.current_step_index + 1}: '{next_step_text}'")
            elif self.last_completed_step_index == num_steps -1 and num_steps > 0 : # All steps are actually done
                response_parts.append("\nPLAN COMPLETE: All steps have been processed.")
            elif num_steps == 0:
                response_parts.append("\nPlan is empty.")
            else: # current_step_index might be num_steps but last_completed not yet num_steps-1
                  # This means the "NEXT" pointer is past the end, implying completion.
                response_parts.append("\nPLAN COMPLETE: All steps have been processed.")

            return "\n".join(response_parts)

        view_check_tool = FunctionTool.from_defaults(
            fn=self._view_check_tool_func,  # Corrected to use the intended function and made it a method call
            name="view_check_plan",  # Changed name to snake_case for consistency, but "create plan" works if preferred
            description=(
                "Reviews the currently active multi-step execution plan and manages progress. "
                "Requires a boolean argument 'mark_current_step_as_done' (defaults to False). "
                "If True, the current 'NEXT' step is marked 'DONE', and the plan advances. "
                "If False (default), it only displays the plan with the current 'NEXT' step highlighted. "
                "Use to check current status and upcoming actions, or to confirm completion of a step."
            )
        )
        self.tools.append(view_check_tool)



    def _get_text_input_tool_func(self, prompt: str) -> str:
        additional_input = input(prompt)
        print("-------------------------------------------\n")
        return f"The user responded to the prompt '{prompt}' with: '{additional_input}'."

    def _create_document_from_description_internal(self, document_description: str, requested_filename: str) -> str:
        """
        Internal method to handle document creation.
        1. Uses an LLM to generate markdown content based on the description.
        2. Parses the markdown and title.
        3. Uses a utility to convert markdown to a styled PDF.
        4. Saves the PDF to the agent's writing output directory.
        """
        if self.verbose:
            print(f"--- [{self.name}] Starting document generation for: '{document_description}' ---")

        # 1. Generate content using the specialized writing LLM
        full_writing_prompt = WRITING_SYSTEM_PROMPT_TEMPLATE.format(user_document_request=document_description)
        try:
            if self.verbose:
                print(f"--- [{self.name}] Sending request to writing LLM (Model: {self.writing_llm.metadata.model_name}) ---")
            
            # Using .complete for synchronous call as this tool function is synchronous
            response = self.writing_llm.complete(full_writing_prompt)
            generated_markdown_content = response.text.strip()

            if not generated_markdown_content:
                msg = "Writing LLM returned empty content. Cannot create document."
                if self.verbose: print(f"--- [{self.name}] {msg} ---")
                return msg
            
            if self.verbose:
                print(f"--- [{self.name}] Received markdown from writing LLM (first 200 chars): '{generated_markdown_content[:200]}...' ---")

        except Exception as e:
            error_msg = f"Error during writing LLM call: {str(e)}"
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
                import traceback
                traceback.print_exc()
            return error_msg

        # 2. Extract title from markdown (first H1, as per WRITING_SYSTEM_PROMPT_TEMPLATE)
        document_title_from_llm = "Untitled Document"
        if generated_markdown_content:
            first_line = generated_markdown_content.split('\n', 1)[0]
            title_match = re.match(r"#\s*(.*)", first_line)
            if title_match:
                document_title_from_llm = title_match.group(1).strip()
            else: # Fallback title if no H1 is found in the first line
                # Use first few words of description for a fallback title, or a generic one
                fallback_title_base = re.sub(r'[^\w\s-]', '', document_description[:50]).strip()
                document_title_from_llm = re.sub(r'[-\s]+', '_', fallback_title_base) if fallback_title_base else "Generated_Document"
        
        if self.verbose:
            print(f"--- [{self.name}] Extracted/determined document title: '{document_title_from_llm}' ---")

        # 3. Generate filename
        filename_base = "Generated_Document"
        if requested_filename:
            # Sanitize requested_filename
            filename_base = re.sub(r'[^\w\s-]', '', requested_filename) # Allow alphanumeric, space, hyphen
            filename_base = re.sub(r'[-\s]+', '_', filename_base).strip('_') # Replace space/hyphen with underscore
            filename_base = filename_base[:70] # Max length
            if not filename_base: filename_base = "Custom_Name_Doc" # Fallback for empty sanitized name
        elif document_title_from_llm and document_title_from_llm.strip().lower() != "untitled document":
            sanitized_title = re.sub(r'[\*_#]', '', document_title_from_llm) # Remove markdown
            sanitized_title = re.sub(r'[^\w\s-]', '', sanitized_title)
            sanitized_title = re.sub(r'[-\s]+', '_', sanitized_title).strip('_')
            filename_base = sanitized_title[:70]
            if not filename_base: filename_base = "Titled_Doc"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"{filename_base}_{timestamp}.pdf"
        pdf_filepath = self.writing_output_dir / pdf_filename

        if self.verbose:
            print(f"--- [{self.name}] Determined output filepath: {pdf_filepath.resolve()} ---")

        # 4. Create PDF using the utility
        try:
            success, message, pdf_filepath_returned = create_styled_pdf_from_markdown(
                output_filepath=str(pdf_filepath.resolve()),
                markdown_content=generated_markdown_content,
                document_title=document_title_from_llm,
                verbose=self.verbose 
            )

            # The message from create_styled_pdf_from_markdown already includes success/error details
            return message
        except Exception as e:
            error_msg = f"Unexpected error during PDF generation utility call: {str(e)}"
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
                import traceback
                traceback.print_exc()
            return error_msg

    def _get_gmail_service(self):
        """Initializes and returns a Gmail API service object."""
        if not get_user_google_access_token():
            return "Error: Google access token is required to initialize Gmail service."

        creds = GoogleCredentials(token=get_user_google_access_token())
        try:
            # cache_discovery=False is important for performance and avoiding discovery doc download issues
            service = build('gmail', 'v1', credentials=creds, cache_discovery=False)
            if self.verbose:
                print(f"--- [{self.name}] Gmail API service initialized for user. ---")
            return service
        except Exception as e:
            error_msg = f"Failed to build Gmail service: {e}"
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
            return error_msg # Return error message instead of raising

    def _create_gmail_message_body(self, to_email: str, subject: str, message_text: str) -> dict:
        """Creates a Gmail API-compatible message body (base64url encoded) using EmailMessage."""
        message = EmailMessage()
        message.set_content(message_text)  # For plain text content
        message['To'] = to_email
        message['Subject'] = subject
        # 'From' will be set by Gmail API based on authenticated user (userId='me')

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {'raw': raw_message}

    def _create_message_with_attachment(self, to_email: str, subject: str, message_text: str, attachment_paths) -> dict:
        """Creates a Gmail API-compatible message body with optional attachments."""
        message = MIMEMultipart('mixed')
        message['To'] = to_email
        message['Subject'] = subject
        # 'From' will be set by Gmail API based on authenticated user (userId='me')

        # Attach the plain text body
        text_part = EmailMessage()
        text_part.set_content(message_text)
        message.attach(text_part)

        if attachment_paths != []:
            for file_path in attachment_paths:
                if file_path is None:
                    return {"raw":f"file '{file_path}' does not found"}
                if not os.path.exists(file_path):
                    if self.verbose:
                        print(f"--- [{self.name}] Warning: Attachment file not found: {file_path} ---")
                    continue # Skip this attachment if file not found

                try:
                    content_type, encoding = mimetypes.guess_type(file_path)
                    if content_type is None or encoding is not None:
                        content_type = 'application/octet-stream' # Default to binary if type is unknown or encoded

                    maintype, subtype = content_type.split('/', 1)

                    with open(file_path, 'rb') as f:
                        file_content = f.read()

                    part = MIMEBase(maintype, subtype)
                    part.set_payload(file_content)
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(file_path)}"')
                    message.attach(part)
                    if self.verbose:
                        print(f"--- [{self.name}] Attached file: {os.path.basename(file_path)} ---")

                except Exception as e:
                    if self.verbose:
                        print(f"--- [{self.name}] Error attaching file {file_path}: {e} ---")
                    continue # Continue with other attachments

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {'raw': raw_message}

    def ListSubAgents(self) -> str:
        """Lists the names of all created sub-agents."""
        return str(list(self.SubWorkers.keys()))

    def CreateSubAgent(self, name: str, system_prompt: str) -> str:
        """
        Creates a new sub-agent and adds a tool to the parent agent to call this sub-agent.

        Args:
            name: The name of the sub-agent.
            system_prompt: The system prompt for the sub-agent.

        Returns:
            The created sub-agent instance.
        """
        try:
            name = self.name + "/" + name
            if name in self.SubWorkers:
                msg = f"Warning: Sub-agent with name '{name}' already exists. Returning existing instance."
                print(msg)
                return msg
            if self.verbose:
                print(f"--- [{self.name}] Creating SubAgent: '{name}' ---")
            sub_agent = Agent(
                system_prompt=system_prompt,
                name=name,
                verbose=self.verbose
            )
            self.SubWorkers[name] = sub_agent
            return f"Sub-agent '{name}' created successfully with system prompt: '{system_prompt}'. It can now be called using its name."
        except Exception as e:
            msg = f"Error creating sub-agent '{name}': {str(e)}"
            print(msg)
            return msg

    def _send_email_internal(self, recipient: str, subject: str, body: str, attachment_paths: str = "") -> str:
        """
        Internal method to send an email using the Gmail API with optional attachments.
        Signals if Google Access Token is missing.
        Accepts attachment_paths as a comma-separated string.
        """
        if self.verbose:
            print(f"--- [{self.name}] Attempting to send email to: {recipient} with attachments string: {attachment_paths} ---")

        service = self._get_gmail_service()
        if isinstance(service, str): # Check if _get_gmail_service returned an error message
            return service # Return the error message

        try:
            # Split the comma-separated string into a list of paths
            paths_list = [p.strip() for p in attachment_paths.split(',') if p.strip()] if attachment_paths else None

            # Use the new function that handles attachments
            message_payload = self._create_message_with_attachment(
                to_email=recipient,
                subject=subject,
                message_text=body,
                attachment_paths=paths_list # Pass the list to the message creation function
            )
            sent_message = service.users().messages().send(userId='me', body=message_payload).execute()
            msg_id = sent_message.get('id', 'N/A')
            msg = f"Email sent successfully to {recipient}. Message ID: {msg_id}"
            if self.verbose:
                print(f"--- [{self.name}] {msg} ---")
            return msg
        except HttpError as error:
            error_msg = f"An API error occurred while sending email to {recipient}: {error.resp.status} - {error._get_reason()}"
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
                # Optional: Log more details from error.content if needed, but avoid logging sensitive info
            return error_msg
        except Exception as e:
            error_msg = f"Error sending email to {recipient}: {str(e)}"
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
                import traceback
                traceback.print_exc()
            return error_msg

    def _draft_email_internal(self, recipient: str, subject: str, body: str, attachment_paths: str = "") -> str:
        """
        Internal method to create an email draft using the Gmail API with optional attachments.
        Accepts attachment_paths as a comma-separated string.
        """
        if self.verbose:
            print(f"--- [{self.name}] Attempting to draft email to: {recipient} with attachments string: {attachment_paths} ---")

        service = self._get_gmail_service()
        if isinstance(service, str): # Check if _get_gmail_service returned an error message
            return service # Return the error message

        try:
            # Split the comma-separated string into a list of paths
            paths_list = [p.strip() for p in attachment_paths.split(',') if p.strip()] if attachment_paths else None

            # Use the new function that handles attachments
            message_payload = self._create_message_with_attachment(
                to_email=recipient,
                subject=subject,
                message_text=body,
                attachment_paths=paths_list # Pass the list to the message creation function
            )
            draft_body = {'message': message_payload}
            created_draft = service.users().drafts().create(userId='me', body=draft_body).execute()
            draft_id = created_draft.get('id', 'N/A')
            msg = f"Draft created successfully for {recipient}. Draft ID: {draft_id}"
            if self.verbose:
                print(f"--- [{self.name}] {msg} ---")
            return msg
        except HttpError as error:
            error_msg = f"An API error occurred while creating draft for {recipient}: {error.resp.status} - {error._get_reason()}"
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
                # Optional: Log more details from error.content if needed
            return error_msg
        except Exception as e:
            error_msg = f"Error creating draft for {recipient}: {str(e)}"
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
                import traceback
                traceback.print_exc()
            return error_msg

    async def CallSubAgent(self, name: str, task: str) -> str:
        """
        Allows direct programmatic calling of a sub-agent's run method.
        This is not for the LLM to use as a tool, but for direct orchestration from code.

        Args:
            name: The name of the sub-agent to call.
            task: The task string to pass to the sub-agent's run method.

        Returns:
            The result from the sub-agent's run method or an error message.
        """
        if name in self.SubWorkers:
            sub_agent = self.SubWorkers[name]
            if self.verbose:
                print(f"--- [{self.name}] Directly calling SubAgent '{name}' with task: {task} ---")
            return await sub_agent.run(task)
        else:
            error_msg = f"Error: Sub-agent '{name}' not found in '{self.name}'."
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
            return error_msg

    def _ensure_pdf_settings_configured(self):
        """
        Configures LlamaIndex.Settings for PDF processing if not already done.
        This uses specific models and settings as potentially defined in the PDF utility script.
        """
        if not self._pdf_settings_configured:
            if self.verbose:
                print(f"--- [{self.name}] Configuring LlamaIndex.Settings for PDF processing ---")
            
            if not GeminiKey: # Should have been caught earlier, but good for safety
                raise ValueError("GeminiKey (GOOGLE_API_KEY) not found. Cannot configure PDF embedding model.")

            # Configure Settings specifically for PDF operations
            Settings.llm = RateLimitedGemini(
                model=PDF_CONTEXT_LLM_MODEL,
                api_key=GeminiKey,
                temperature=PDF_CONTEXT_LLM_TEMP
            )
            Settings.embed_model = GeminiEmbedding(
                model_name=PDF_EMBED_MODEL_NAME, 
                api_key=GeminiKey
            )
            Settings.node_parser = SentenceSplitter(
                chunk_size=PDF_CHUNK_SIZE,
                chunk_overlap=PDF_CHUNK_OVERLAP,
            )
            self._pdf_settings_configured = True
            if self.verbose:
                print(f"--- [{self.name}] LlamaIndex.Settings configured for PDF.Embed: {PDF_EMBED_MODEL_NAME}, Parser: chunk_size={PDF_CHUNK_SIZE} ---")


    def load_and_index_Url(self, url: str, url_id: str):
        # --- RAG Pipeline ---
        # 3. Load data from the URL
        my_gemini_embed_model = Settings.embed_model
        if not isinstance(my_gemini_embed_model, GeminiEmbedding):
            print("CRITICAL: Settings.embed_model is not a GeminiEmbedding instance. Re-initializing for local use.")
            # Fallback if global settings failed, or for explicit local control
            try:
                Settings.embed_model = GeminiEmbedding(model_name="models/embedding-001")
            except Exception as e_embed_init:
                print(f"Failed to initialize GeminiEmbedding locally: {e_embed_init}")
                raise

        sane_url_id = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in url_id)
        if not sane_url_id: # Should not happen if pdf_id is not empty
             sane_url_id = "default_url_id"
        if url_id != sane_url_id and self.verbose:
            print(f"--- [{self.name}] Sanitized pdf_id from '{url_id}' to '{sane_url_id}' for directory naming. ---")

        persist_dir = self.persist_base_dir / sane_url_id

        try:
            if sane_url_id in self.query_engines:
                return f"PDF '{url_id}' (ID: {sane_url_id}) is already loaded in memory. Use force_reindex=True to reload from file."


            index = None
            if persist_dir.exists():
                if self.verbose:
                    print(f"--- [{self.name}] Loading existing index for '{sane_url_id}' from {persist_dir} ---")
                storage_context = StorageContext.from_defaults(persist_dir=str(persist_dir))
                index = load_index_from_storage(storage_context, embed_model=Settings.embed_model)  # Uses Settings.embed_model
                if self.verbose:
                    print(f"--- [{self.name}] Index for '{sane_url_id}' loaded successfully. ---")
            else:
                if self.verbose:
                    print(f"--- [{self.name}] Creating new index for '{sane_url_id}' from URL: {url} ---")

                persist_dir.mkdir(parents=True, exist_ok=True)

                loader = SimpleWebPageReader(html_to_text=True)
                documents = []
                try:
                    # It's good practice to set a timeout for web requests
                    documents = loader.load_data(urls=[url])
                except Exception as e:
                    print(f"Error loading data from URL {url}: {e}")
                    print(
                        "This could be due to the website structure, content type (e.g., PDF instead of HTML), access restrictions, or timeout.")
                    return

                # 4. Create an index from the loaded documents
                index = VectorStoreIndex.from_documents(documents, embed_model=Settings.embed_model)

            if index:
                # Query engine uses Settings.llm by default if not overridden
                query_engine = index.as_query_engine(similarity_top_k=ITEM_SIMILARITY_TOP_K)
                self.query_engines[sane_url_id] = QueryTypes(query_engine, URL_TYPE)
                return f"URL '{url}' (ID: {sane_url_id}) processed. Query engine ready."
            else:  # Should not be reached if logic is correct
                return f"Error: Failed to load or create index for URL '{url}' (ID: {sane_url_id})."
        except Exception as e:
            error_msg = f"Error processing URL '{url}' (ID: {url_id}): {str(e)}"
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
                import traceback
                traceback.print_exc()
            return error_msg


    def load_and_index_item(self, file_path_str: str, item_id: str, force_reindex: bool = False) -> str:
        """
        Loads a file from the given path, processes its text content,
        creates/loads a vector index, and stores a query engine for it.
        Uses FileDecoder to handle various file types.
        """
        self._ensure_pdf_settings_configured() # Settings are general for embedding/LLM

        file_path = Path(file_path_str).resolve() # Resolve to absolute path
        print(f"Attempting to load and index file: {file_path}")
        if not file_path.exists() or not file_path.is_file():
            return f"Error: File not found at '{file_path_str}' (resolved to '{file_path}')."

        # Use FileDecoder to get content
        content, error_msg = get_file_content(str(file_path))

        if error_msg:
            print(f"--- Error during file content extraction: {error_msg} ---")
            return f"Error extracting content from '{file_path_str}': {error_msg}"

        if not content or not content.strip():
             print(f"--- No text content extracted from file: {file_path} ---")
             return f"Error: No text content could be extracted from '{file_path_str}', or the file is not suitable for text summarization."

        # Basic sanitization for item_id to be used as a directory name
        sane_item_id = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in item_id)
        if not sane_item_id: # Should not happen if item_id is not empty
             sane_item_id = "default_item_id"
        if item_id != sane_item_id and self.verbose:
            print(f"--- [{self.name}] Sanitized item_id from '{item_id}' to '{sane_item_id}' for directory naming. ---")

        item_persist_dir = self.persist_base_dir / sane_item_id

        try:
            if sane_item_id in self.query_engines and not force_reindex:
                return f"Item '{item_id}' (ID: {sane_item_id}) is already loaded in memory. Use force_reindex=True to reload from file."

            if force_reindex and item_persist_dir.exists():
                if self.verbose:
                    print(f"--- [{self.name}] FORCE_REINDEX: Deleting existing index for '{sane_item_id}' at {item_persist_dir} ---")
                shutil.rmtree(item_persist_dir)

            index = None
            if item_persist_dir.exists():
                if self.verbose:
                    print(f"--- [{self.name}] Loading existing index for '{sane_item_id}' from {item_persist_dir} ---")
                storage_context = StorageContext.from_defaults(persist_dir=str(item_persist_dir))
                index = load_index_from_storage(storage_context) # Uses Settings.embed_model
                if self.verbose:
                    print(f"--- [{self.name}] Index for '{sane_item_id}' loaded successfully. ---")
            else:
                if self.verbose:
                    print(f"--- [{self.name}] Creating new index for '{sane_item_id}' from file: {file_path} ---")

                item_persist_dir.mkdir(parents=True, exist_ok=True)

                # Create a single Document from the extracted content
                documents = [Document(text=content, metadata={'file_path': str(file_path)})]

                if not documents: # Should not happen if content is not empty
                    return f"Error: Could not create document object from extracted content for '{file_path_str}'."
                if self.verbose:
                    print(f"--- [{self.name}] Created 1 document object from extracted text. ---")

                nodes = Settings.node_parser.get_nodes_from_documents(documents, show_progress=self.verbose)
                if not nodes:
                    return f"Error: No nodes (chunks) were created from the content of '{file_path_str}'."
                if self.verbose:
                    print(f"--- [{self.name}] Parsed into {len(nodes)} Node object(s). ---")

                index = VectorStoreIndex(nodes, show_progress=self.verbose) # Uses Settings.embed_model
                index.storage_context.persist(persist_dir=str(item_persist_dir))
                if self.verbose:
                    print(f"--- [{self.name}] Index for '{sane_item_id}' created and persisted to {item_persist_dir}. ---")

            if index:
                # Query engine uses Settings.llm by default if not overridden
                query_engine = index.as_query_engine(similarity_top_k=ITEM_SIMILARITY_TOP_K)
                self.query_engines[sane_item_id] = QueryTypes(query_engine, FILE_TYPE) # Use FILE_TYPE
                return f"File '{file_path_str}' (ID: {sane_item_id}) processed. Query engine ready."
            else: # Should not be reached if logic is correct
                return f"Error: Failed to load or create index for file '{file_path_str}' (ID: {sane_item_id})."

        except Exception as e:
            error_msg = f"Error processing file '{file_path_str}' (ID: {item_id}): {str(e)}"
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
                import traceback
                traceback.print_exc()
            return error_msg

    def query_indexed_item(self, item_id: str, query_text: str) -> str:
        """
        Queries a previously loaded and indexed PDF using its ID.
        """
        self._ensure_pdf_settings_configured() # Ensure settings are ready

        sane_item_id = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in item_id)
        if not sane_item_id: sane_item_id = "default_item_id"

        if sane_item_id not in self.query_engines:
            persist_dir = self.persist_base_dir / sane_item_id
            if persist_dir.exists():
                if self.verbose:
                    print(f"--- [{self.name}] ITEM ID '{sane_item_id}' not in memory, attempting to load from storage: {persist_dir} ---")
                try:
                    # This re-loading essentially re-runs part of load_and_index_pdf logic
                    # It's a simplified auto-load. For full state persistence, Agent state would need saving/loading.
                    storage_context = StorageContext.from_defaults(persist_dir=str(persist_dir))
                    index = load_index_from_storage(storage_context) # Uses Settings.embed_model
                    query_engine = index.as_query_engine(similarity_top_k=ITEM_SIMILARITY_TOP_K) # Uses Settings.llm
                    self.query_engines[sane_item_id] = query_engine
                    if self.verbose:
                        print(f"--- [{self.name}] Successfully loaded index and query engine for '{sane_item_id}' from storage. ---")
                except Exception as e:
                    msg = f"Error: ITEM ID '{item_id}' (sanitized: {sane_item_id}) not in active query engines, and failed to auto-load from storage {persist_dir}: {e}"
                    if self.verbose: print(f"--- [{self.name}] {msg} ---")
                    return msg
            else:
                return f"Error: ITEM '{item_id}' (sanitized: {sane_item_id}) not found. Please load it first using 'load_pdf_document'."

        query_engine = self.query_engines[sane_item_id].query_engine
        try:
            if self.verbose:
                print(f"--- [{self.name}] Querying ITEM '{sane_item_id}' with: '{query_text}' ---")
            response = query_engine.query(query_text) # Uses Settings.llm via the query_engine
            response_str = str(response)
            if self.verbose:
                print(f"--- [{self.name}] Response from ITEM '{sane_item_id}': '{response_str}' ---")
            return response_str
        except Exception as e:
            error_msg = f"Error querying ITEM '{sane_item_id}': {str(e)}"
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
                import traceback
                traceback.print_exc()
            return error_msg

    def list_loaded_pdfs(self) -> str:
        """
        Lists the IDs of all currently loaded and queryable PDFs.
        """
        # For more robustness, could also scan self.pdf_persist_base_dir for existing indexes
        # and report them as "available on disk, can be loaded/queried".
        # For now, just lists what's in memory.
        if not self.query_engines:
            return "No Items are currently active in memory."
        out = ""
        for key in self.query_engines.keys():
            out += key + " - " + self.query_engines[key].type + "\n"
        return f"Active ITEMs IDs in memory and their types: {out}"

    async def run(self, user_msg: str) -> str:
        if self.verbose: 
            print(f"\n--- [{self.name}] Task received: {user_msg} ---")
        try:
            # Ensure PDF settings are configured if any PDF tool might be called
            # This is a good place if tools might be used without explicit load first
            # However, individual PDF methods also call it for safety.
            # self._ensure_pdf_settings_configured() # Optional: configure preemptively

            agent_response = await self.worker.run(user_msg=user_msg, memory=self.memory)
            response = str(agent_response.response)

            if self.verbose: 
                print(f"--- [{self.name}] Response: {response} ---")
            return response
        except Exception as e:
            print(f"--- [{self.name}] Error during run: {e} ---")
            import traceback
            traceback.print_exc()
            return f"Error in {self.name}: {str(e)}"



