import os
from pathlib import Path
from dotenv import load_dotenv

# 0. (Optional but recommended) Set Google API Key
# Make sure your GOOGLE_API_KEY is set in your environment variables
# or uncomment and set it here:
# os.environ["GOOGLE_API_KEY"] = "your_google_api_key_here"
load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    raise ValueError("GOOGLE_API_KEY environment variable not set. Please set it to your Google API key.")

# Import LlamaIndex components
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    load_index_from_storage,
    Settings, # For global configuration
)
from llama_index.llms.gemini import Gemini # Import Gemini LLM
from llama_index.embeddings.gemini import GeminiEmbedding # Import Gemini Embeddings

# --- Configuration (Newer LlamaIndex approach using Settings) ---

# For "cheap" Gemini models:
# LLM: "models/gemini-pro" is a good general-purpose and relatively cost-effective model.
#      "models/gemini-1.5-flash-latest" is even more cost-effective and faster if available and suitable.
# Embedding: "models/embedding-001" is Google's general text embedding model.
#            "models/text-embedding-004" is a newer embedding model.
# Check Google's documentation for the latest and most cost-effective models.

# Settings.llm = Gemini(model="models/gemini-pro", temperature=0.1)
# You can explicitly pass the api_key here if not using env var, but env var is preferred:
Settings.llm = Gemini(model="models/gemini-pro", temperature=0.1, api_key=os.getenv("GOOGLE_API_KEY"))

Settings.embed_model = GeminiEmbedding(model_name="models/embedding-001")
# Settings.embed_model = GeminiEmbedding(model_name="models/text-embedding-004") # Newer option
# You can also explicitly pass the api_key here:
# Settings.embed_model = GeminiEmbedding(model_name="models/embedding-001", api_key=os.getenv("GOOGLE_API_KEY"))


# You can also adjust chunk_size and chunk_overlap if needed
# Settings.chunk_size = 1024 # Gemini models often handle larger contexts
# Settings.chunk_overlap = 200

# --- Define paths ---
PDF_FILE_PATH = Path("./data/my_document.pdf") # Ensure this PDF exists
PERSIST_DIR = Path("./storage_gemini") # Directory to store the index (use a different one for Gemini)

# --- 1. Load Documents ---
# Check if the PDF file exists
if not PDF_FILE_PATH.exists():
    print(f"Error: PDF file not found at {PDF_FILE_PATH}")
    # Create a dummy PDF for the example to run
    PDF_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PDF_FILE_PATH, "w") as f: # Use 'w' for text mode
        f.write("This is a dummy PDF created for demonstration.\n")
        f.write("The Llama is a domesticated South American camelid, widely used as a meat and pack animal by Andean cultures since the Pre-Columbian era.\n")
        f.write("Llamas are very social animals and live with other llamas as a herd.\n")
        f.write("Their wool is soft and lanolin-free. Llamas can learn simple tasks after a few repetitions.\n")
        f.write("When used as pack animals, they can carry about 25 to 30% of their body weight for 8 to 13 km (5–8 miles).\n")
    print(f"Created a dummy PDF: {PDF_FILE_PATH}")


# Use SimpleDirectoryReader to load your PDF
try:
    print(f"Loading documents from {PDF_FILE_PATH.parent}...")
    reader = SimpleDirectoryReader(input_files=[PDF_FILE_PATH])
    documents = reader.load_data()
    if not documents:
        print("No documents were loaded. Check the PDF content and path.")
        exit()
    print(f"Loaded {len(documents)} document(s).")
except Exception as e:
    print(f"Error loading documents: {e}")
    exit()

# --- 2. Create or Load Index ---
if not PERSIST_DIR.exists():
    print(f"Creating new Gemini index and persisting to {PERSIST_DIR}...")
    PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    # Create the index from the loaded documents
    # LlamaIndex will use the global Settings for LLM and embed_model
    index = VectorStoreIndex.from_documents(documents)

    # Persist the index to disk
    index.storage_context.persist(persist_dir=PERSIST_DIR)
    print("Gemini index created and saved.")
else:
    print(f"Loading existing Gemini index from {PERSIST_DIR}...")
    # Load the existing index
    storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
    # Important: When loading an index, LlamaIndex needs to know which LLM and embed_model
    # were used to create it if they are not the current global defaults in Settings.
    # Since we set them in Settings globally before this block, it should pick them up.
    # If you had different settings during creation, you might need to pass them explicitly:
    # index = load_index_from_storage(storage_context, embed_model=Settings.embed_model)
    index = load_index_from_storage(storage_context)
    print("Gemini index loaded.")

# --- 3. Create Query Engine ---
print("Creating query engine with Gemini...")
query_engine = index.as_query_engine(
    similarity_top_k=3,
    # You can add response_mode="compact" or other modes if desired
)
print("Query engine created.")

# --- 4. Query the Index ---
print("\n--- Querying with Gemini ---")
queries = [
    "What is a Llama?",
    "How much weight can a Llama carry?",
    "Describe the wool of a Llama."
]

for q_text in queries:
    print(f"\nQuery: {q_text}")
    try:
        response = query_engine.query(q_text)
        print("Response:")
        print(str(response)) # The actual answer
        # print("\nSource Nodes:")
        # for node in response.source_nodes:
        #     print(f"  ID: {node.node_id}, Score: {node.score:.4f}")
        #     print(f"  Text: {node.text[:100]}...")
    except Exception as e:
        print(f"Error during query: {e}")
        # Gemini API can sometimes throw specific errors (e.g., content filtering)
        # Check e for more details if this happens.

print("\nDone.")
