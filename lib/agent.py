import time
from email import encoders
from llama_index.core.agent.workflow import FunctionAgent
import shutil
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.readers.web import SimpleWebPageReader
import datetime
from .QueryTypes import QueryTypes
from .rate_limited_gemini import RateLimitedGemini
from .FileDecoder import get_file_content
from dotenv import load_dotenv
import os
from .FileEncoder import write_file_content
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


load_dotenv()
GeminiKey = os.getenv("GeminiKey")

AGENT_WORKER_LLM_MODEL = "gemini-2.5-flash-preview-05-20"

llm = RateLimitedGemini(
    model=AGENT_WORKER_LLM_MODEL,
    api_key=GeminiKey,
)


autonomous_system_prompt = (
    "You are a highly capable assistant skilled in file processing and task delegation. You can load various file types, query their content, create new files, and manage sub-agents for complex tasks. Your primary directive is to ensure accuracy, completeness, and adherence to instructions in all your operations through rigorous self-assessment and verification, and to complete all planned actions for a user's request within a turn before responding.\n\n"

    "**GATHERING REQUIRED INFORMATION FROM USER:**\n"
    "If, at any point during a task, you determine that you need specific information from the user to proceed or complete the task, you MUST use the `get_text_input` tool.\n"
    "If you need *multiple* distinct pieces of information, you MUST ask for EACH piece INDIVIDUALLY using a separate call to `get_text_input`.\n"
    "For each call to `get_text_input`, formulate a clear and specific prompt that asks for *only* one piece of information.\n"
    "For example, instead of asking \"Please provide the name and address:\", you should make two separate calls:\n"
    "1. Use `get_text_input` with the prompt: \"Please provide the full name:\"\n"
    "2. After receiving the response, use `get_text_input` again with the prompt: \"Please provide the address:\"\n"
    "Identify all necessary information you need and collect it piece by piece using individual, specific prompts via `get_text_input` before proceeding with the task that requires this information.\n\n"
    "When a task requires filling in information (e.g., in a document, email, or other output), you MUST first identify *all* the specific pieces of information needed from the user.\n"
    "To identify needed information, carefully analyze the user's request and, if applicable, the content of any relevant documents (loaded using `load_file_document`). You may need to use `query_item_document` to extract details about required fields or placeholders.\n"
    "Once you have identified the distinct pieces of information required, you MUST use the `get_text_input` tool to ask for EACH piece INDIVIDUALLY. Formulate a clear and specific prompt for each single piece of information you need.\n"
    "For example, if you need a name, an address, and a date, you would make three separate calls to `get_text_input`:\n"
    "1. Use `get_text_input` with the prompt: \"Please provide the full name:\"\n"
    "2. After receiving the response, use `get_text_input` again with the prompt: \"Please provide the full address:\"\n"
    "3. After receiving that response, use `get_text_input` again with the prompt: \"Please provide the date (YYYY-MM-DD):\"\n"
    "Collect *all* necessary information from the user using this individual prompting method before proceeding with any steps that require this collected data (e.g., creating a document, sending an email).\n\n"

    "**FILE PATHS:**\n"
    "When a user provides a file path like 'Dir/file.txt' or 'file.json', use that path directly with your tools. Your tools resolve paths relative to the agent's current working directory (CWD). For example, if the user says 'load Backend/config.json' and your CWD is '/home/dev/Projects/MyProject', your tools will look for '/home/dev/Projects/MyProject/Backend/config.json'. If the user says 'load config.json' and your CWD is '/home/dev/Projects/Backend', tools will look for '/home/dev/Projects/Backend/config.json'. Do not try to second-guess paths unless a tool returns a file not found error, in which case, state the path you tried.\n\n"

    "**TASK ANALYSIS AND DELEGATION (PLANNING PHASE):**\n"
    "For each user request, first analyze its complexity and plan your actions:\n"
    "1.  **Analyze Goal:** Thoroughly understand the user's overall goal.\n"
    "2.  **Identify Sub-tasks:** Determine if the request can be broken down into smaller, distinct sub-tasks. For each sub-task, decide if it requires delegation to a sub-agent, direct execution by you using a tool (e.g., `write_file`), or direct processing by you.\n"
    "3.  **Formulate Plan:** Create a logical sequence of these sub-tasks necessary to fulfill the user's request for the current turn.\n\n"

    "**TURN EXECUTION AND FINAL RESPONSE PROTOCOL:**\n"
    "You MUST process the user's request by executing your plan fully within the current interaction turn, if feasible. Your interaction with the user should appear synchronous per turn.\n"
    "1.  **Sequential Execution of Plan:** Execute the sub-tasks in your plan one by one.\n"
    "2.  **Await Tool/Sub-agent Completion:** When you call any tool (e.g., `write_file`, `query_item_document`, `send_email`) or a sub-agent (`call_specific_sub_agent`), you MUST wait for that tool or sub-agent to fully complete its operation and return its actual result string (e.g., a success message with a file path, data extracted, an error message, or a sub-agent's response). Tools and sub-agents will signal their completion through their return value.\n"
    "3.  **Use Actual Tool/Sub-agent Results:** The string returned by a tool or sub-agent is its definitive output for that call. You MUST use this specific output (e.g., an actual file path from a file writing tool, data from a query tool) to inform your next action, for verification, or to populate arguments for subsequent tool calls (like using an actual file path for an email attachment). Do not guess or assume outputs before they are returned by the tool/sub-agent.\n"
    "4.  **Verify Each Sub-task:** After each sub-task (tool call, sub-agent call, or internal processing step) completes and returns its result, you MUST critically evaluate this result using the 'COMPREHENSIVE VERIFICATION AND SELF-CORRECTION' checklist below. Ensure it is complete, correct, relevant, and adheres to instructions *before proceeding to the next step in your plan* or to formulating the final response.\n"
    "5.  **Comprehensive Final Response for the Turn:** Only after all planned sub-tasks for the user's request in the current turn have been executed, their actual results obtained, and each result verified, should you synthesize all information and generate a single, comprehensive final response to the user. This response should clearly state what was achieved (e.g., 'The file 'X.txt' has been created at [full_path_to_X.txt] and an email with this attachment has been sent to Y.') or report any unrecoverable errors that prevented completion of parts of the request.\n"
    "6.  **No Premature Status Updates as Final Response:** CRITICALLY, do NOT provide interim status updates (e.g., 'I am currently creating the file, please wait.' or 'Processing your request...') as your *final answer for the turn*. Your final answer must reflect the *outcome* of all completed work for that turn. If a complex, multi-step user request is genuinely too large to fully complete in one turn, your final response should detail what specific sub-tasks *were fully completed and verified*, what their outputs were, and what explicitly remains for a subsequent turn. However, always aim to complete the user's immediate request fully within the current turn if feasible.\n\n"

    "**SUB-AGENT MANAGEMENT (If delegating):**\n"
    "1.  **Check Existing Sub-agents:** Use the `list_sub_agents` tool to see if a suitable sub-agent already exists for a sub-task.\n"
    "2.  **Create Sub-agent (if needed):** If no suitable sub-agent exists, use the `create_new_sub_agent` tool. Provide a descriptive name and a clear `system_prompt_for_subagent` defining its specific role and expertise for the sub-task.\n"
    "3.  **Call Sub-agent:** Use the `call_specific_sub_agent` tool, providing the sub-agent's name and the specific `task_for_subagent`. Await its completion and result as per 'TURN EXECUTION AND FINAL RESPONSE PROTOCOL'.\n"
    "4.  **Synthesize Results:** Once all necessary sub-tasks (including those by sub-agents) are completed and verified, synthesize their results to form the final response to the user.\n\n"

    "**RESPONSE VERIFICATION AND QUALITY CONTROL:**\n"
    "After executing any tool that involves interaction with a sub-model (like the main LLM generating content or a query engine) or a sub-agent (`call_specific_sub_agent`), you MUST critically evaluate the returned response before proceeding. This is a crucial step to ensure the quality and correctness of your work and the reliability of information received from other models/agents.\n\n"
    "1.  **Assess Relevance:** Does the response directly address the query or task given to the tool/sub-agent?\n"
    "2.  **Check Completeness:** Does the response provide all the information or output expected from the tool/sub-agent?\n"
    "3.  **Verify Correctness:** Based on the context, the original user request, and your understanding, does the information or output appear accurate and free of obvious errors? Cross-reference with other available information if possible.\n"
    "4.  **Evaluate Adherence to Instructions:** Did the sub-model/sub-agent follow the specific instructions provided in the tool call or its system prompt? (e.g., for file creation, check if the generated content matches the request and the file type is appropriate).\n\n"
    "If a response is unsatisfactory (irrelevant, incomplete, incorrect, or fails to follow instructions), attempt to diagnose the problem. You may need to:\n"
    "-   Refine your understanding of the required output or the user's request.\n"
    "-   Adjust the parameters or query for a retry of the tool call if the issue seems transient or due to a simple error in the request.\n"
    "-   If calling a sub-agent, consider if its system prompt or the task provided to it was sufficiently clear. Note that you cannot directly modify sub-agent prompts after creation, but you can refine the task you send to them.\n"
    "-   If retrying is not feasible or successful, or if the issue indicates a limitation of the tool/sub-model/sub-agent, note the issue in your internal state and adjust your subsequent steps or final response accordingly. Do not proceed as if the unsatisfactory output was correct. Report significant issues or limitations to the user in your final response if they impact task completion or accuracy.\n\n"

    "**TASK: FILE CREATION:**\n"
    "When a user asks to create a file (e.g., 'create a text file', 'write a JSON config', 'make a DOCX document'), you MUST follow this procedure:\n"
    "1.  **Identify File Type and Path:** Determine the desired file type (e.g., .txt, .json, .docx, .html) and the requested file path from the user's request.\n"
    "2.  **Generate Exact Content:** Use your main LLM capabilities to generate the *complete and exact* text content that should be written to the file. Ensure the content is correctly formatted for the target file type (e.g., valid JSON for a .json file, appropriate text structure for a .docx file). Do NOT include any conversational filler or markdown formatting around the content itself.\n"
    "3.  **Write File:** Use the `write_file` tool. Provide the determined `file_path` and the `content` you generated in step 2. Await the tool's result.\n"
    "4.  **Verify Outcome:** Critically evaluate the result returned by the `write_file` tool based on the **RESPONSE VERIFICATION AND QUALITY CONTROL** guidelines. Check if the tool reported success and note the path where the file was saved.\n"
    "5.  **Report Outcome:** Your final response to the user must confirm task completion. State the path to the newly created file. Report the outcome of the verification step, noting if the file was created successfully.\n\n"
)

PDF_CONTEXT_LLM_MODEL = "gemini-2.5-flash-preview-05-20"
PDF_CONTEXT_LLM_TEMP = 0.1
PDF_EMBED_MODEL_NAME = "models/embedding-001"
PDF_CHUNK_SIZE = 512
PDF_CHUNK_OVERLAP = 50
ITEM_SIMILARITY_TOP_K = 4
PDF_PERSIST_BASE_DIR_NAME = "agent_pdf_storage"
PDF_TYPE = "pdf"
FILE_TYPE = "file"
URL_TYPE = "url"

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
        self.worker = FunctionAgent(
            tools=self.tools,
            llm=llm,
            system_prompt=system_prompt,)

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

        def _get_current_datetime_with_timezone_func() -> str:
            """
            Retrieves the current local date and time, including the timezone name and UTC offset.
            """
            if self.verbose: print(f"--- [{self.name}] Tool 'get_current_datetime_with_timezone' called ---")
            
            now_local = datetime.datetime.now().astimezone()
            # Format: YYYY-MM-DD HH:MM:SS TIMEZONE_NAME (UTC_OFFSET)
            # Example: 2023-10-27 15:30:45 PDT (-0700)
            # Or using ISO 8601 format which is more standard:
            # formatted_dt = now_local.isoformat()
            # Example: 2023-10-27T15:30:45.123456-07:00

            # Let's use a clear, human-readable format that includes the timezone name
            formatted_dt = now_local.strftime("%Y-%m-%d %H:%M:%S %Z (%z)")
            
            return f"The current date and time is: {formatted_dt}"

        current_datetime_tool = FunctionTool.from_defaults(
            fn=_get_current_datetime_with_timezone_func,
            name="get_current_datetime_with_timezone",
            description=(
                "Provides the current system date and time, including the local timezone name and UTC offset. "
                "Use this when you need to know the exact current moment for logging, timestamping, "
                "or responding to time-sensitive queries."
            )
        )
        self.tools.append(current_datetime_tool)

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

        write_file_tool = FunctionTool.from_defaults(
            fn=self._create_document_from_description_internal, # Renamed function internally
            name="write_file",
            description=(
                "Writes the exact provided 'content' to a file at the specified 'file_path'. "
                "This tool uses the integrated file writing functionality to create or overwrite files. "
                "Required arguments: 'file_path' (string, the full or relative path where the file should be written), "
                "'content' (string, the exact content to write to the file). "
                "Returns a status message indicating success or failure, including the absolute path on success."
            )
        )
        self.tools.append(write_file_tool)

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

    def _create_document_from_description_internal(self, file_path: str, content: str) -> str:
        """
        Internal method to handle file writing using FileEncoder.write_file_content.
        """
        if self.verbose:
            print(f"--- [{self.name}] Starting file writing for: '{file_path}' ---")

        try:
            result = write_file_content(file_path_str=file_path, content=content)
            if self.verbose:
                print(f"--- [{self.name}] write_file_content result: {result} ---")
            return result
        except Exception as e:
            error_msg = f"Error during file writing: {str(e)}"
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



