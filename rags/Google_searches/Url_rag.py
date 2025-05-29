import os
from llama_index.core import VectorStoreIndex, Settings, Document
from llama_index.readers.web import SimpleWebPageReader # For reading web pages
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding
from dotenv import load_dotenv # To load .env file for API key

# --- Configuration ---
# 1. Set up your Google API Key
# This script will try to load it from a .env file
load_dotenv()
google_api_key = os.getenv("GOOGLE_API_KEY")

if not google_api_key:
    raise ValueError(
        "GOOGLE_API_KEY not found. Please set it in your environment or a .env file. "
        "You can get a key from Google AI Studio: https://aistudio.google.com/app/apikey"
    )

# 2. Specify the Gemini model you want to use
# The user mentioned "gemini-2.0-flash".
# As of mid-2024, "models/gemini-1.5-flash-latest" is the common API identifier for the Flash model.
# Please use the exact model identifier provided by Google for "gemini-2.0-flash" if it differs.
LLM_MODEL_NAME = "models/gemini-2.0-flash"
EMBEDDING_MODEL_NAME = "models/embedding-001" # Standard Google embedding model

# 3. The URL you want to process
# Replace with your desired URL. For example, a blog post or a documentation page.
TARGET_URL = "https://lilianweng.github.io/posts/2023-06-23-agent/" # Example URL about LLM Agents

# --- LlamaIndex Setup ---
def run_rag_on_url(url: str, query: str):
    """
    Performs RAG on content from a given URL using Gemini and LlamaIndex.
    """
    try:
        # 1. Configure the LLM
        # We use Settings to make these global for LlamaIndex operations
        Settings.llm = Gemini(model_name=LLM_MODEL_NAME, api_key=google_api_key)
        print(f"LLM configured: {LLM_MODEL_NAME}")

        # 2. Configure the Embedding Model
        Settings.embed_model = GeminiEmbedding(
            model_name=EMBEDDING_MODEL_NAME, api_key=google_api_key
        )
        print(f"Embedding model configured: {EMBEDDING_MODEL_NAME}")

        # --- RAG Pipeline ---
        # 3. Load data from the URL
        print(f"\nLoading data from URL: {url}...")
        # The documentation you provided is for FILE readers.
        # For URLs, we use a web reader like SimpleWebPageReader.
        # html_to_text=True helps get cleaner text content.
        loader = SimpleWebPageReader(html_to_text=True)
        documents = loader.load_data(urls=[url])

        if not documents:
            print(f"No documents were loaded from {url}. Check the URL or its content.")
            return

        print(f"Loaded {len(documents)} document(s) from the URL.")
        # For demonstration, print a snippet of the first document's content
        if documents and documents[0].text: # Check if text attribute exists and is not empty
            print(f"Snippet of first document: {documents[0].text[:300]}...")
        elif documents and documents[0].get_content(): # Fallback to get_content()
             print(f"Snippet of first document: {documents[0].get_content()[:300]}...")
        else:
            print("First document seems empty or has no text attribute.")


        # 4. Create an index from the loaded documents
        # This will automatically use the configured embedding model (Settings.embed_model)
        print("\nCreating vector store index...")
        index = VectorStoreIndex.from_documents(documents)
        print("Index created successfully.")

        # 5. Create a query engine
        # This allows us to ask questions about the indexed content.
        # The LLM configured in Settings (Settings.llm) will be used for synthesizing the answer.
        query_engine = index.as_query_engine(
            similarity_top_k=3 # Retrieve top 3 most similar chunks
        )
        print("Query engine ready.")

        # 6. Ask a question (RAG in action)
        print(f"\nQuerying the index with: '{query}'")
        response = query_engine.query(query)

        print("\nLLM Response:")
        print(str(response))

        print("\n--- Retrieved Source Chunks ---")
        for i, node in enumerate(response.source_nodes):
            print(f"\nSource Chunk {i+1} (Score: {node.score:.4f}):")
            print(f"ID: {node.node_id}")
            # print(f"Text: {node.get_content()[:500]}...") # Uncomment to see source text
            print("-" * 20)

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        print("\nPlease ensure:")
        print("1. You have installed all required packages: llama-index, llama-index-llms-gemini, llama-index-embeddings-gemini, llama-index-readers-web, python-dotenv")
        print("   Run: pip install llama-index llama-index-llms-gemini llama-index-embeddings-gemini llama-index-readers-web python-dotenv")
        print("2. Your GOOGLE_API_KEY is correctly set in a .env file or environment variable and has access to the Gemini API.")
        print(f"3. The model names '{LLM_MODEL_NAME}' and '{EMBEDDING_MODEL_NAME}' are correct and available for your API key.")
        print(f"4. The URL '{url}' is accessible and contains text content.")
        import traceback
        traceback.print_exc()

# --- Main Execution ---
if __name__ == "__main__":
    # Example usage:
    # You can change the URL and the query as needed.
    custom_url = TARGET_URL
    # custom_url = "https://en.wikipedia.org/wiki/Retrieval-augmented_generation" # Another example

    # Ask a question relevant to the content of the TARGET_URL
    # For the Lilian Weng blog post:
    custom_query = "What are the main components of an LLM-powered autonomous agent system?"
    # For the Wikipedia RAG page:
    # custom_query = "What is Retrieval-Augmented Generation?"

    if not custom_url:
        print("Please set a TARGET_URL in the script.")
    else:
        run_rag_on_url(url=custom_url, query=custom_query)

    print("\nScript finished.")
