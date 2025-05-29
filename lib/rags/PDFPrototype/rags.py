from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path
import time
import shutil

# --- LlamaIndex and Gemini Imports ---
from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage,
    Settings,
    Document,
)
from llama_index.readers.file import PyMuPDFReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding

# --- Global variables ---
query_engine_global = None
index_global = None

# --- Configuration ---
GEMINI_MODEL_NAME = "models/gemini-2.0-flash" # CONFIRMED MODEL FOR YOUR LAB

PDF_FILE_PATH = Path("./data/my_document.pdf") # Ensure your User Agreement PDF is here
PERSIST_DIR = Path("./storage_code_sharing_agreement_gemini_2_0_flash") # Specific persist dir

# !!! RECOMMENDED: Set to True for the first run with this specific PDF !!!
FORCE_REINDEX = True # Set to True to rebuild index with the new PDF content

# --- TUNING PARAMETERS ---
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
SIMILARITY_TOP_K = 4
# --- END TUNING PARAMETERS ---

def setup_llm_and_embed_model():
    """Sets up the LLM, Embedding model, and Node Parser in LlamaIndex Settings."""
    print(f"Attempting to configure LLM with model: {GEMINI_MODEL_NAME}")
    try:
        Settings.llm = Gemini(model=GEMINI_MODEL_NAME, temperature=0.1)
        print(f"Successfully configured LLM with model: {GEMINI_MODEL_NAME}")
    except Exception as e:
        print(f"ERROR: Could not initialize Gemini LLM with model '{GEMINI_MODEL_NAME}'. Details: {e}")
        exit()

    Settings.embed_model = GeminiEmbedding(model_name="models/embedding-001")
    Settings.node_parser = SentenceSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    print(f"LLM, Embedding model, and Node Parser (chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}) configured.")


def load_and_parse_pdf_with_pymupdf():
    """Loads the PDF using PyMuPDFReader and parses it into nodes."""
    if not PDF_FILE_PATH.exists():
        print(f"ERROR: PDF file not found at '{PDF_FILE_PATH}'.")
        print(f"Please ensure your 'Code Sharing Platform User Agreement' PDF is at this location.")
        exit()

    try:
        print(f"\n--- Loading PDF with PyMuPDFReader: {PDF_FILE_PATH} ---")
        pdf_reader = PyMuPDFReader()
        documents = pdf_reader.load_data(file_path=PDF_FILE_PATH, metadata=True)

        if not documents:
            print("ERROR: PyMuPDFReader loaded no documents from the PDF.")
            exit()
        print(f"Successfully loaded {len(documents)} Document object(s) using PyMuPDFReader.")

        #print("\n--- DIAGNOSTIC: First 1000 characters of the first loaded Document object ---")
        full_text_sample = ""
        if documents and documents[0].text and documents[0].text.strip():
            full_text_sample = documents[0].text.strip()
            #print(full_text_sample[:1000])
            if len(full_text_sample) > 1000: print("...")
        else:
            print("The first Document object from PyMuPDFReader appears to have no text or only whitespace.")
            exit()
        print("--- End of Document sample ---")

        if Settings.node_parser:
            nodes = Settings.node_parser.get_nodes_from_documents(documents, show_progress=True)
        else:
            print("CRITICAL ERROR: Settings.node_parser not configured.")
            exit()

        if not nodes:
            print("ERROR: No Nodes were created after parsing the documents.")
            exit()
        print(f"Successfully parsed into {len(nodes)} Node object(s) (chunks).")

        #print("\n--- DIAGNOSTIC: Content of the first Node (chunk) ---")
        print(nodes[0].get_content()[:1000] + ("..." if len(nodes[0].get_content()) > 1000 else ""))
        print("--- End of Node sample ---")
        if len(nodes) > 1:
            middle_node_index = len(nodes) // 2
            #print("\n--- DIAGNOSTIC: Content of a middle Node (chunk) if available ---")
            #print(nodes[middle_node_index].get_content()[:1000] + ("..." if len(nodes[middle_node_index].get_content()) > 1000 else ""))
            #print("--- End of Node sample ---")
        return nodes

    except Exception as e:
        print(f"ERROR: An exception occurred during PDF loading or parsing with PyMuPDFReader.")
        print(f"Details: {e}")
        exit()


def create_or_load_index_and_query_engine(nodes_from_pdf):
    """Creates or loads the index from parsed nodes and sets up the query engine."""
    global index_global, query_engine_global

    if FORCE_REINDEX and PERSIST_DIR.exists():
        print(f"FORCE_REINDEX is True. Deleting existing index at: {PERSIST_DIR}")
        shutil.rmtree(PERSIST_DIR)

    if not PERSIST_DIR.exists():
        print(f"\n--- Creating New Index ---")
        print(f"Persisting to: {PERSIST_DIR}")
        PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        index_global = VectorStoreIndex(nodes_from_pdf, show_progress=True)
        index_global.storage_context.persist(persist_dir=PERSIST_DIR)
        print("Index created and saved.")
    else:
        print(f"\n--- Loading Existing Index ---")
        print(f"Loading from: {PERSIST_DIR}")
        storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
        index_global = load_index_from_storage(storage_context)
        print("Index loaded.")

    print("\n--- Creating Query Engine ---")
    query_engine_global = index_global.as_query_engine(
        similarity_top_k=SIMILARITY_TOP_K,
    )
    print(f"Query engine created (similarity_top_k={SIMILARITY_TOP_K}).")


def run_queries():
    """Runs queries against the loaded query engine and provides diagnostics."""
    if query_engine_global is None or index_global is None:
        print("ERROR: Query engine or index not initialized. Cannot run queries.")
        return

    print("\n--- Running Queries on Code Sharing Platform User Agreement ---")
    # --- QUERIES RELEVANT TO THE PROVIDED USER AGREEMENT ---
    queries = [
        "What information is required for account registration?",
        "Who is responsible for maintaining account confidentiality?",
        "What rights do users retain over their User Content?",
        "What license does a user grant by uploading User Content to the platform?",
        "List three examples of unacceptable uses of the platform.",
        "Can a user copy or modify the platform's content without permission?",
        "What kind of warranties are provided for the platform?",
        "What is the extent of the company's liability for damages arising from platform use?",
        "How can this Agreement be terminated by the user?",
        "What governing law applies to this Agreement?",
        "How are users notified of changes to this Agreement?"
    ]
    # --- END OF RELEVANT QUERIES ---

    INTER_QUERY_DELAY_SECONDS = 3
    RATE_LIMIT_WAIT_SECONDS = 60

    for i, q_text in enumerate(queries):
        print(f"\n\n==================== Query {i+1}/{len(queries)} ====================")
        print(f"QUERY: \"{q_text}\"")
        print("----------------------------------------------------")

        try:
            #print("--- DIAGNOSTIC: Retrieving nodes directly from index... ---")
            retriever = index_global.as_retriever(similarity_top_k=SIMILARITY_TOP_K)
            retrieved_nodes_with_scores = retriever.retrieve(q_text)

            if not retrieved_nodes_with_scores:
                print("WARNING: No relevant text chunks (nodes) found by the retriever for this query.")
            else:
                print(f"Retriever found {len(retrieved_nodes_with_scores)} node(s) for the query:")
                for k, node_with_score in enumerate(retrieved_nodes_with_scores):
                    """print(f"\n  Retrieved Node {k+1} (Score: {node_with_score.score:.4f}):")
                    print("  --------------------------------------------------")
                    node_text = node_with_score.get_content()
                    print(node_text[:1000] + ("..." if len(node_text) > 1000 else ""))
                    print("  --------------------------------------------------")"""
            #print("--- End of Direct Node Retrieval Diagnostic ---")

            print("\n--- Asking LLM (via Query Engine) for response... ---")
            response_object = query_engine_global.query(q_text)
            llm_response_text = str(response_object)
            print("\nLLM Response:")
            print("----------------------------------------------------")
            print(llm_response_text)
            print("----------------------------------------------------")

            if response_object.source_nodes:
                #print("\n--- DIAGNOSTIC: Source Nodes used by Query Engine for this response: ---")
                for k, R_node_with_score in enumerate(response_object.source_nodes):
                    print(f"\n  Query Engine Source Node {k+1} (ID: {R_node_with_score.node.node_id}, Score: {R_node_with_score.score:.4f}):")
                    print("  --------------------------------------------------")
                    source_node_text = R_node_with_score.node.get_content()
                    #print(source_node_text[:1000] + ("..." if len(source_node_text) > 1000 else ""))
                    print("  --------------------------------------------------")
            else:
                print("\nDIAGNOSTIC: No source_nodes attribute found in the response object.")

        except Exception as e:
            print(f"\n!!!!!!!!!! ERROR DURING QUERY PROCESSING !!!!!!!!!!")
            print(f"Query: \"{q_text}\"")
            print(f"Error details: {e}")
            error_message = str(e).lower()
            if "429" in error_message or "resource has been exhausted" in error_message or "rate limit" in error_message:
                print(f"Rate limit likely hit. Pausing for {RATE_LIMIT_WAIT_SECONDS} seconds...")
                time.sleep(RATE_LIMIT_WAIT_SECONDS)
            elif "model" in error_message and ("not found" in error_message or "invalid" in error_message):
                 print(f"ERROR: The model '{GEMINI_MODEL_NAME}' caused an issue during query.")
            else:
                print(f"An unexpected error occurred. Pausing for {INTER_QUERY_DELAY_SECONDS} seconds.")
                time.sleep(INTER_QUERY_DELAY_SECONDS)
        finally:
            if i < len(queries) - 1:
                print(f"\nPausing for {INTER_QUERY_DELAY_SECONDS} seconds before next query...")
                time.sleep(INTER_QUERY_DELAY_SECONDS)

    print("\n==================== All Queries Processed ====================")


def main():
    if not os.getenv("GOOGLE_API_KEY"):
        print("ERROR: GOOGLE_API_KEY environment variable not set.")
        exit()
    print("GOOGLE_API_KEY found.")

    setup_llm_and_embed_model()
    parsed_nodes = load_and_parse_pdf_with_pymupdf()
    create_or_load_index_and_query_engine(parsed_nodes)
    run_queries()

    print("\nScript finished.")

if __name__ == "__main__":
    main()
