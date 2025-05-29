import os
from llama_index.core import VectorStoreIndex, Settings, Document
from llama_index.readers.web import SimpleWebPageReader # For reading web pages
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding
from dotenv import load_dotenv # To load .env file for API key
from googlesearch import search # For performing Google searches

# --- Configuration ---
# 1. Set up your Google API Key for Gemini
load_dotenv()
google_api_key = os.getenv("GOOGLE_API_KEY")

if not google_api_key:
    raise ValueError(
        "GOOGLE_API_KEY not found. Please set it in your environment or a .env file. "
        "You can get a key from Google AI Studio: https://aistudio.google.com/app/apikey"
    )

# 2. Specify the Gemini model you want to use
# IMPORTANT: Ensure "models/gemini-2.0-flash" is the correct and accessible model identifier for your API key.
# As of mid-2024, "models/gemini-1.5-flash-latest" is a common API identifier for the Flash model.
# Please verify the exact model identifier provided by Google if "gemini-2.0-flash" is different or causes errors.
LLM_MODEL_NAME = "models/gemini-2.0-flash"
# LLM_MODEL_NAME = "models/gemini-1.5-flash-latest" # Alternative if the above doesn't work
EMBEDDING_MODEL_NAME = "models/embedding-001" # Standard Google embedding model

# --- Helper Function for Google Search ---
def search_google_and_get_first_url(query: str) -> str | None:
    """
    Performs a Google search and returns the URL of the first result.
    Returns None if no results are found or an error occurs.
    """
    print(f"\nSearching Google for: '{query}'...")
    try:
        # num_results=1 to suggest we only need one.
        # The library will yield results; we take the first one.
        # pause=2.0 to be polite to Google's servers.
        search_results_generator = search(query, num_results=1, lang="en")

        # Get the first result from the generator
        first_url = next(search_results_generator, None)

        if first_url:
            print(f"Found URL: {first_url}")
            return first_url
        else:
            print("No results found on Google.")
            return None
    except StopIteration:
        # This can happen if the generator is empty (no results)
        print("No results found on Google (StopIteration).")
        return None
    except Exception as e:
        print(f"An error occurred during Google search: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging Google search issues
        return None

# --- LlamaIndex RAG Function (largely unchanged) ---
def run_rag_on_url(url: str, user_prompt_for_ai: str):
    """
    Performs RAG on content from a given URL using Gemini and LlamaIndex,
    based on the user's prompt for the AI.
    """
    try:
        # 1. Configure the LLM
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
        loader = SimpleWebPageReader(html_to_text=True)
        documents = []
        try:
            # It's good practice to set a timeout for web requests
            documents = loader.load_data(urls=[url])
        except Exception as e:
            print(f"Error loading data from URL {url}: {e}")
            print("This could be due to the website structure, content type (e.g., PDF instead of HTML), access restrictions, or timeout.")
            return

        if not documents:
            print(f"No documents were loaded from {url}. The page might be empty, inaccessible, or not parseable as text.")
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
        print("\nCreating vector store index...")
        index = VectorStoreIndex.from_documents(documents)
        print("Index created successfully.")

        # 5. Create a query engine
        query_engine = index.as_query_engine(
            similarity_top_k=3 # Retrieve top 3 most similar chunks
        )
        print("Query engine ready.")

        # 6. Ask a question (RAG in action) using the user's specific prompt
        print(f"\nQuerying the index with your prompt: '{user_prompt_for_ai}'")
        response = query_engine.query(user_prompt_for_ai)

        print("\nLLM Response:")
        print(str(response))

        print("\n--- Retrieved Source Chunks ---")
        for i, node in enumerate(response.source_nodes):
            print(f"\nSource Chunk {i+1} (Score: {node.score:.4f}):")
            print(f"ID: {node.node_id}")
            # print(f"Text: {node.get_content(metadata_mode='all')[:500]}...") # Uncomment to see source text
            print("-" * 20)

    except Exception as e:
        print(f"\nAn error occurred in the RAG process: {e}")
        print("\nPlease ensure:")
        print("1. You have installed all required packages: llama-index, llama-index-llms-gemini, llama-index-embeddings-gemini, llama-index-readers-web, python-dotenv, googlesearch-python")
        print("2. Your GOOGLE_API_KEY is correctly set in a .env file or environment variable and has access to the Gemini API.")
        print(f"3. The model names '{LLM_MODEL_NAME}' and '{EMBEDDING_MODEL_NAME}' are correct and available for your API key.")
        print(f"4. The URL '{url}' was accessible and contained processable text content.")
        import traceback
        traceback.print_exc()

# --- Main Execution ---
if __name__ == "__main__":
    # 1. Ask the user for a Google search query
    user_google_query = input("Enter your Google search query: ")

    if not user_google_query.strip():
        print("Search query cannot be empty.")
    else:
        # 2. Search Google and get the first URL
        retrieved_url = search_google_and_get_first_url(user_google_query)

        if retrieved_url:
            # 3. Ask the user for a prompt for the AI regarding the content of the retrieved URL
            ai_prompt = input(f"\nI will process the content from: {retrieved_url}\n"
                              "What would you like to ask or tell the AI about this content? (e.g., 'Summarize this page', 'What are the key points?', 'Extract all names mentioned'): ")
            if not ai_prompt.strip():
                print("The prompt for the AI cannot be empty.")
            else:
                # 4. Run the RAG process with the retrieved URL and the user's AI prompt
                run_rag_on_url(url=retrieved_url, user_prompt_for_ai=ai_prompt)
        else:
            print("Could not proceed without a URL from Google search.")

    print("\nScript finished.")
