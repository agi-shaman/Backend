import time

from llama_index.core.agent.workflow import FunctionAgent
import shutil
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.llms.gemini import Gemini
from .rate_limited_gemini import RateLimitedGemini
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
)
from llama_index.readers.file import PyMuPDFReader
import re 
from datetime import datetime

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

PDF_CONTEXT_LLM_MODEL = "gemini-2.5-flash-preview-05-20"
PDF_CONTEXT_LLM_TEMP = 0.1
PDF_EMBED_MODEL_NAME = "models/embedding-001"
PDF_CHUNK_SIZE = 512
PDF_CHUNK_OVERLAP = 50
PDF_SIMILARITY_TOP_K = 4
PDF_PERSIST_BASE_DIR_NAME = "agent_pdf_storage"
WRITING_LLM_MODEL = "gemini-2.5-flash-preview-05-20"  # Can be same as PDF_CONTEXT_LLM_MODEL or different
WRITING_LLM_TEMP = 0.7 # Temperature for creative document generation
WRITING_OUTPUT_BASE_DIR_NAME = "agent_generated_documents"

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
8.  **Signature Section (Conditional - AI Decision):**
    *   **Decision:** Based on the user's document request, YOU (the AI) must decide if a signature section is contextually appropriate and necessary (e.g., for agreements, formal proposals, letters requiring sign-off, meeting minutes for approval, etc.).
    *   **Implementation:** If a signature section is deemed necessary, include a final section explicitly titled: `## Signatures` or `## Approval Section`.
    *   Under this specific heading, provide clear placeholders for signatures. For each signatory, use the format:
        `**Printed Name:** _________________________` (The underscores should be plentiful to create a visible line)
        `**Signature:** _________________________`
        `**Date:** _________________________`
        (If there are multiple signatories, repeat this block for each. You can optionally add a `---` separator between blocks for multiple signatories if it enhances clarity.)
    *   If a signature section is NOT appropriate for the document type, DO NOT include it.

CONTENT REQUIREMENTS:
1.  **Direct Output:** Start your response DIRECTLY with the H1 markdown title. NO conversational filler, introductions like "Okay, here is the document...", or self-referential statements ("As an AI...").
2.  **Density and Efficiency:** The document must be as compact and information-dense as possible while remaining perfectly readable and comprehensive. Your goal is to convey all necessary information in the fewest possible words and pages. Prioritize impactful information over lengthy explanations.
3.  **Professional Tone:** Maintain a highly formal, objective, and polished tone throughout the entire document.
4.  **Completeness:** Ensure the document is self-contained and thoroughly covers the requested topic from introduction to conclusion, as appropriate for the document type.
5.  **Handle Autonomous Fillings:** The input text may contain sections marked like `[AI AUTONOMOUSLY FILLED: Some generated text]`. When you encounter this pattern, render *only* the text inside the brackets (`Some generated text`) in the final markdown output, replacing the original placeholder text entirely. Do NOT include the `[AI AUTONOMOUSLY FILLED: ]` part in the output markdown.

USER'S DOCUMENT REQUEST: "{user_document_request}"

Remember: Begin your response *immediately* with the H1 markdown title.
"""

class Agent:
    def __init__(self, system_prompt: str, name: str = "Main_Agent", verbose: bool = False):
        self.name = name
        self.tools = []
        self.verbose = verbose
        self.SubWorkers = {}
        self._add_tools()
        self.pdf_query_engines = {}
        self.pdf_persist_base_dir = Path(f"./{PDF_PERSIST_BASE_DIR_NAME}")
        self.pdf_persist_base_dir.mkdir(parents=True, exist_ok=True)
        self._pdf_settings_configured = False
        self.writing_output_dir = Path(f"./{WRITING_OUTPUT_BASE_DIR_NAME}")
        self.writing_output_dir.mkdir(parents=True, exist_ok=True)

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
        print(f"Initialized '{self.name}' with system prompt: '{system_prompt}' and {len(self.tools)} tools.")

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

        # --- PDF Functionality Tools ---
        def _load_pdf_document_tool_func(pdf_file_path: str, pdf_id: str, force_reindex: bool = False) -> str:
            if self.verbose: print(f"--- [{self.name}] Tool 'load_pdf_document' called with path: {pdf_file_path}, id: {pdf_id}, force_reindex: {force_reindex} ---")
            return self.load_and_index_pdf(pdf_file_path_str=pdf_file_path, pdf_id=pdf_id, force_reindex=force_reindex)

        load_pdf_tool = FunctionTool.from_defaults(
            fn=_load_pdf_document_tool_func,
            name="load_pdf_document",
            description=(
                "Loads and indexes a PDF document from a given file path for future querying. "
                "Required arguments: 'pdf_file_path' (string, the full or relative path to the PDF file), "
                "'pdf_id' (string, a unique identifier you assign to this PDF, e.g., 'doc1', 'user_agreement_v2'). This ID will be used for querying and listing. create one yourself without asking"
                "Optional argument: 'force_reindex' (boolean, defaults to False. If True, any existing index for this pdf_id will be deleted and rebuilt from the PDF file). "
                "Returns a status message. After successful loading, the PDF can be queried using its 'pdf_id'."
            )
        )
        self.tools.append(load_pdf_tool)

        def _query_pdf_document_tool_func(pdf_id: str, query_text: str) -> str:
            if self.verbose: print(f"--- [{self.name}] Tool 'query_pdf_document' called with id: {pdf_id}, query: '{query_text[:70]}...' ---")
            return self.query_indexed_pdf(pdf_id=pdf_id, query_text=query_text)

        query_pdf_tool = FunctionTool.from_defaults(
            fn=_query_pdf_document_tool_func,
            name="query_pdf_document",
            description=(
                "Queries a previously loaded PDF document using its assigned 'pdf_id'. "
                "Required arguments: 'pdf_id' (string, the identifier used when loading the PDF), "
                "'query_text' (string, the question or query about the PDF content). "
                "Returns the answer found in the PDF or an error message if the pdf_id is not found or an error occurs during querying."
            )
        )
        self.tools.append(query_pdf_tool)

        def _list_loaded_pdfs_tool_func() -> str:
            if self.verbose: print(f"--- [{self.name}] Tool 'list_loaded_pdfs' called ---")
            return self.list_loaded_pdfs()

        list_pdfs_tool = FunctionTool.from_defaults(
            fn=_list_loaded_pdfs_tool_func,
            name="list_loaded_pdfs",
            description="Lists the unique IDs of all PDF documents that are currently active in memory and available for querying."
        )
        self.tools.append(list_pdfs_tool)

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

        def _create_document_tool_func(document_description: str, requested_filename: str) -> str:
            if self.verbose: print(f"--- [{self.name}] Tool 'create_document_from_description' called with description: '{document_description[:70]}...' ---")
            return self._create_document_from_description_internal(
                document_description=document_description,
                requested_filename=requested_filename
            )

        create_document_tool = FunctionTool.from_defaults(
            fn=_create_document_tool_func,
            name="create_document_from_description",
            description=(
                "Generates a styled PDF document based on a textual 'document_description'. "
                "The document will be formatted professionally using markdown generated by an AI writer. "
                "Required argument: 'document_description' (string, a detailed description of the document to be created, e.g., 'a non-disclosure agreement between two parties', 'a quarterly business review presentation outline', 'a formal complaint letter regarding product X'). "
                "Optional argument: 'requested_filename' (string, a desired filename for the PDF, without the .pdf extension. If not provided, a name will be generated based on the document title or description). "
                "Returns a message indicating success and the path to the generated PDF, or an error message."
            )
        )
        self.tools.append(create_document_tool)

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
            success, message = create_styled_pdf_from_markdown(
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

    def load_and_index_pdf(self, pdf_file_path_str: str, pdf_id: str, force_reindex: bool = False) -> str:
        """
        Loads a PDF from the given path, processes it, creates/loads a vector index,
        and stores a query engine for it.
        """
        self._ensure_pdf_settings_configured() # Crucial for PDF operations
        
        pdf_file_path = Path(pdf_file_path_str).resolve() # Resolve to absolute path
        print(f"loading pdf - {pdf_file_path}")
        if not pdf_file_path.exists() or not pdf_file_path.is_file():
            return f"Error: PDF file not found at '{pdf_file_path_str}' (resolved to '{pdf_file_path}')."
        # Basic sanitization for pdf_id to be used as a directory name
        sane_pdf_id = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in pdf_id)
        if not sane_pdf_id: # Should not happen if pdf_id is not empty
             sane_pdf_id = "default_pdf_id" 
        if pdf_id != sane_pdf_id and self.verbose:
            print(f"--- [{self.name}] Sanitized pdf_id from '{pdf_id}' to '{sane_pdf_id}' for directory naming. ---")
        
        persist_dir = self.pdf_persist_base_dir / sane_pdf_id

        try:
            if sane_pdf_id in self.pdf_query_engines and not force_reindex:
                return f"PDF '{pdf_id}' (ID: {sane_pdf_id}) is already loaded in memory. Use force_reindex=True to reload from file."

            if force_reindex and persist_dir.exists():
                if self.verbose:
                    print(f"--- [{self.name}] FORCE_REINDEX: Deleting existing index for '{sane_pdf_id}' at {persist_dir} ---")
                shutil.rmtree(persist_dir)
            
            index = None
            if persist_dir.exists():
                if self.verbose:
                    print(f"--- [{self.name}] Loading existing index for '{sane_pdf_id}' from {persist_dir} ---")
                storage_context = StorageContext.from_defaults(persist_dir=str(persist_dir))
                index = load_index_from_storage(storage_context) # Uses Settings.embed_model
                if self.verbose:
                    print(f"--- [{self.name}] Index for '{sane_pdf_id}' loaded successfully. ---")
            else:
                if self.verbose:
                    print(f"--- [{self.name}] Creating new index for '{sane_pdf_id}' from PDF: {pdf_file_path} ---")
                
                persist_dir.mkdir(parents=True, exist_ok=True)
                
                pdf_reader = PyMuPDFReader()
                documents = pdf_reader.load_data(file_path=pdf_file_path, metadata=True)
                if not documents:
                    return f"Error: No documents were loaded from PDF '{pdf_file_path_str}'."
                if self.verbose:
                    print(f"--- [{self.name}] Loaded {len(documents)} document object(s) from PDF. ---")

                nodes = Settings.node_parser.get_nodes_from_documents(documents, show_progress=self.verbose)
                if not nodes:
                    return f"Error: No nodes (chunks) were created from the PDF '{pdf_file_path_str}'."
                if self.verbose:
                    print(f"--- [{self.name}] Parsed into {len(nodes)} Node object(s). ---")

                index = VectorStoreIndex(nodes, show_progress=self.verbose) # Uses Settings.embed_model
                index.storage_context.persist(persist_dir=str(persist_dir))
                if self.verbose:
                    print(f"--- [{self.name}] Index for '{sane_pdf_id}' created and persisted to {persist_dir}. ---")

            if index:
                # Query engine uses Settings.llm by default if not overridden
                query_engine = index.as_query_engine(similarity_top_k=PDF_SIMILARITY_TOP_K)
                self.pdf_query_engines[sane_pdf_id] = query_engine
                return f"PDF '{pdf_file_path_str}' (ID: {sane_pdf_id}) processed. Query engine ready."
            else: # Should not be reached if logic is correct
                return f"Error: Failed to load or create index for PDF '{pdf_file_path_str}' (ID: {sane_pdf_id})."

        except Exception as e:
            error_msg = f"Error processing PDF '{pdf_file_path_str}' (ID: {pdf_id}): {str(e)}"
            if self.verbose:
                print(f"--- [{self.name}] {error_msg} ---")
                import traceback
                traceback.print_exc()
            return error_msg

    def query_indexed_pdf(self, pdf_id: str, query_text: str) -> str:
        """
        Queries a previously loaded and indexed PDF using its ID.
        """
        self._ensure_pdf_settings_configured() # Ensure settings are ready

        sane_pdf_id = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in pdf_id)
        if not sane_pdf_id: sane_pdf_id = "default_pdf_id"

        if sane_pdf_id not in self.pdf_query_engines:
            persist_dir = self.pdf_persist_base_dir / sane_pdf_id
            if persist_dir.exists():
                if self.verbose:
                    print(f"--- [{self.name}] PDF ID '{sane_pdf_id}' not in memory, attempting to load from storage: {persist_dir} ---")
                try:
                    # This re-loading essentially re-runs part of load_and_index_pdf logic
                    # It's a simplified auto-load. For full state persistence, Agent state would need saving/loading.
                    storage_context = StorageContext.from_defaults(persist_dir=str(persist_dir))
                    index = load_index_from_storage(storage_context) # Uses Settings.embed_model
                    query_engine = index.as_query_engine(similarity_top_k=PDF_SIMILARITY_TOP_K) # Uses Settings.llm
                    self.pdf_query_engines[sane_pdf_id] = query_engine
                    if self.verbose:
                        print(f"--- [{self.name}] Successfully loaded index and query engine for '{sane_pdf_id}' from storage. ---")
                except Exception as e:
                    msg = f"Error: PDF ID '{pdf_id}' (sanitized: {sane_pdf_id}) not in active query engines, and failed to auto-load from storage {persist_dir}: {e}"
                    if self.verbose: print(f"--- [{self.name}] {msg} ---")
                    return msg
            else:
                return f"Error: PDF ID '{pdf_id}' (sanitized: {sane_pdf_id}) not found. Please load it first using 'load_pdf_document'."

        query_engine = self.pdf_query_engines[sane_pdf_id]
        try:
            if self.verbose:
                print(f"--- [{self.name}] Querying PDF '{sane_pdf_id}' with: '{query_text}' ---")
            response = query_engine.query(query_text) # Uses Settings.llm via the query_engine
            response_str = str(response)
            if self.verbose:
                print(f"--- [{self.name}] Response from PDF '{sane_pdf_id}': '{response_str}' ---")
            return response_str
        except Exception as e:
            error_msg = f"Error querying PDF '{sane_pdf_id}': {str(e)}"
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
        if not self.pdf_query_engines:
            return "No PDFs are currently active in memory."
        return f"Active PDF IDs in memory: {list(self.pdf_query_engines.keys())}"

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
