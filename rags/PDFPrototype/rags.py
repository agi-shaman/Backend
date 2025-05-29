from dotenv import load_dotenv
load_dotenv()




import os
from pathlib import Path
import time # Import the time module

# 0. (Optional but recommended) Set Google API Key
# Make sure your GOOGLE_API_KEY is set in your environment variables
# or uncomment and set it here:
# os.environ["GOOGLE_API_KEY"] = "your_google_api_key_here"
if not os.getenv("GOOGLE_API_KEY"):
    raise ValueError("GOOGLE_API_KEY environment variable not set. Please set it to your Google API key.")



query_engine = 0

def create_dummy_pdf(PDF_FILE_PATH):
    print(f"Error: PDF file not found at {PDF_FILE_PATH}")
    PDF_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PDF_FILE_PATH, "w") as f:
        f.write("This is a dummy PDF created for demonstration.\n")
        f.write("The Llama is a domesticated South American camelid, widely used as a meat and pack animal by Andean cultures since the Pre-Columbian era.\n")
        f.write("Llamas are very social animals and live with other llamas as a herd.\n")
        f.write("Their wool is soft and lanolin-free. Llamas can learn simple tasks after a few repetitions.\n")
        f.write("When used as pack animals, they can carry about 25 to 30% of their body weight for 8 to 13 km (5–8 miles).\n")
    print(f"Created a dummy PDF: {PDF_FILE_PATH}")

def create_query_engine():
    global query_engine
    # Import LlamaIndex components
    from llama_index.core import (
        VectorStoreIndex,
        SimpleDirectoryReader,
        StorageContext,
        load_index_from_storage,
        Settings,
    )
    from llama_index.llms.gemini import Gemini
    from llama_index.embeddings.gemini import GeminiEmbedding

    # --- Configuration (Newer LlamaIndex approach using Settings) ---
    Settings.llm = Gemini(model="models/gemini-2.0-flash", temperature=0.1)
    Settings.embed_model = GeminiEmbedding(model_name="models/embedding-001")
    # Settings.chunk_size = 1024
    # Settings.chunk_overlap = 200

    # --- Define paths ---
    PDF_FILE_PATH = Path("./data/my_document.pdf")
    PERSIST_DIR = Path("./storage_gemini")

    # --- 1. Load Documents ---
    if not PDF_FILE_PATH.exists():
        create_dummy_pdf(PDF_FILE_PATH)

    try:
        print(f"Loading documents from {PDF_FILE_PATH.parent}...")
        reader = SimpleDirectoryReader(input_files=[PDF_FILE_PATH])
        documents = reader.load_data()
        if not documents:
            print("No documents were loaded. Check the PDF content and path.")
            # You might want to inspect the PDF or try a different one if this happens.
            if PDF_FILE_PATH.name == "my_document.pdf" and PDF_FILE_PATH.read_text().startswith("This is a dummy PDF"):
                 print("Note: The dummy PDF is being used. Replace './data/my_document.pdf' with your actual PDF.")
            exit()
        print(f"Loaded {len(documents)} document(s).")
        # --- You can uncomment this to inspect the loaded text ---
        # print("--- Sample of extracted text (first 500 chars) ---")
        # if documents and documents[0].text:
        #     print(documents[0].text[:500])
        # else:
        #     print("No text extracted from the first document.")
        # print("--- End of sample ---")

    except Exception as e:
        print(f"Error loading documents: {e}")
        exit()

    # --- 2. Create or Load Index ---
    if not PERSIST_DIR.exists():
        print(f"Creating new Gemini index and persisting to {PERSIST_DIR}...")
        PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        index = VectorStoreIndex.from_documents(
            documents,
            # service_context=service_context # Not needed if using global Settings
        )
        index.storage_context.persist(persist_dir=PERSIST_DIR)
        print("Gemini index created and saved.")
    else:
        print(f"Loading existing Gemini index from {PERSIST_DIR}...")
        storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
        index = load_index_from_storage(
            storage_context,
            # service_context=service_context # Not needed if using global Settings
        )
        print("Gemini index loaded.")

    # --- 3. Create Query Engine ---
    print("Creating query engine with Gemini...")
    query_engine = index.as_query_engine(
        similarity_top_k=3,
    )
    print("Query engine created.")




# --- 4. Query the Index ---
create_query_engine()
print("\n--- Querying with Gemini ---")
queries = [
    "What is a Llama?",
    "How much weight can a Llama carry?",
    "Describe the wool of a Llama.",
    "Are llamas social animals?" # Adding another query to test rate limiting
]

for q_text in queries:
    print(f"\nQuery: {q_text}")
    try:
        response = query_engine.query(q_text)
        print("Response:")
        print(str(response))
        # print("\nSource Nodes:")
        # for node in response.source_nodes:
        #     print(f"  ID: {node.node_id}, Score: {node.score:.4f}")
        #     print(f"  Text: {node.text[:100]}...")
    except Exception as e:
        print(f"Error during query: {e}")
        # Check if the error is a rate limit error (typically 429)
        if "429" in str(e) or "Resource has been exhausted" in str(e):
            print("Rate limit likely hit. Pausing for 60 seconds before trying next query...")
            time.sleep(60) # Wait for 60 seconds
            # Note: This implementation just skips to the next query.
            # A more robust solution might retry the current query or have a more complex backoff strategy.
        else:
            # For other errors, you might want to pause briefly too or handle differently
            print("An unexpected error occurred. Pausing for 5 seconds.")
            time.sleep(5)
    finally:
        # Add a small delay between all queries to be respectful of API limits
        # This helps even if no error occurred on the previous query
        print("Pausing for 5 seconds before next query...")
        time.sleep(5)


print("\nDone.")
