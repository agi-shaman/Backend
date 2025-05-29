import os
import time
import re
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from llama_index.llms.gemini import Gemini

# from llama_index.core import Settings # Not strictly needed for this direct LLM use

# --- Configuration ---
NUM_INITIAL_SEARCH_RESULTS = 10
NUM_FINAL_RESULTS = 10
MAX_CONTENT_CHARS_FOR_SUMMARY = 3000
REQUEST_TIMEOUT_SECONDS = 10
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
# Number of search query suggestions to ask Gemini for
NUM_QUERY_SUGGESTIONS = 1  # Let's start with asking for one best query

# --- Load Environment Variables ---
load_dotenv()

GEMINI_API_KEY_AI_STUDIO = os.getenv("GOOGLE_API_KEY")
CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
CSE_ID = os.getenv("GOOGLE_CSE_ID")

# --- Validate Essential Configuration ---
if not GEMINI_API_KEY_AI_STUDIO:
    print("Error: GOOGLE_API_KEY (for AI Studio Gemini) not found in .env file.")
    exit()
if not CSE_API_KEY or not CSE_ID:
    print("Error: GOOGLE_CSE_API_KEY or GOOGLE_CSE_ID not found in .env file. These are required for web search.")
    exit()

# --- Initialize LlamaIndex Gemini LLM ---
llm = None
try:
    # You can specify the model explicitly, e.g., "models/gemini-1.5-flash-latest" or "models/gemini-pro"
    # Flash is faster and cheaper, good for tasks like query refinement.
    llm = Gemini(model_name="models/gemini-2.0-flash", api_key=GEMINI_API_KEY_AI_STUDIO)
    print("LlamaIndex Gemini LLM initialized (using Google AI Studio API key for query refinement and descriptions).")
except Exception as e:
    print(f"Error initializing LlamaIndex Gemini LLM: {e}")
    exit()


# --- Helper Functions ---

def refine_search_query_with_gemini(user_query: str, num_suggestions: int = 1) -> str | None:
    """
    Asks Gemini to refine a user's search query or suggest better ones.
    Returns the best suggested query, or the original query if generation fails.
    """
    prompt = f"""
User's initial search intention: "{user_query}"

Your task is to act as an expert search query crafter.
Based on the user's intention, generate {num_suggestions} concise and effective search query (or queries)
that would likely yield the best results on a search engine like Google.
Focus on keywords and clarity. Avoid conversational phrases in the output queries.
If you generate multiple, list each on a new line.
Return ONLY the search query/queries, nothing else.

Optimized Search Query/Queries:
"""
    print(f"\n🧠 Asking Gemini to refine search query for: \"{user_query}\"")
    try:
        response = llm.complete(prompt)
        suggested_queries_text = response.text.strip()

        if not suggested_queries_text:
            print("    Gemini did not return any query suggestions. Using original query.")
            return user_query

        # Split by newline and take the first valid one
        suggestions = [q.strip() for q in suggested_queries_text.split('\n') if q.strip()]

        if suggestions:
            best_suggestion = suggestions[0]  # Take the first suggestion
            # Basic cleanup: remove potential "Optimized Search Query:" prefix if LLM includes it
            prefixes_to_remove = ["Optimized Search Query:", "Optimized Search Queries:", "Search Query:"]
            for prefix in prefixes_to_remove:
                if best_suggestion.lower().startswith(prefix.lower()):
                    best_suggestion = best_suggestion[len(prefix):].strip()

            print(f"    Gemini suggested search query: \"{best_suggestion}\"")
            return best_suggestion
        else:
            print("    Gemini returned empty suggestions after parsing. Using original query.")
            return user_query

    except Exception as e:
        print(f"    Error refining query with Gemini: {e}. Using original query.")
        return user_query  # Fallback to original query


def fetch_results_via_google_cse_api(query: str, num_to_fetch: int) -> list:
    """ Fetches search results using Google Custom Search JSON API. """
    print(f"\n🔍 Searching Google CSE API for: \"{query}\" (fetching up to {num_to_fetch} results)")
    results = []
    count = min(num_to_fetch, 10)

    url = "https://www.googleapis.com/customsearch/v1"
    params = {'key': CSE_API_KEY, 'cx': CSE_ID, 'q': query, 'num': count}
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        search_data = response.json()
        if 'items' in search_data:
            for item in search_data['items']:
                results.append({
                    'title': item.get('title', "No Title Provided by API"),
                    'link': item.get('link'),
                    'snippet': item.get('snippet', "No Snippet Provided by API")
                })
        else:
            print("    No 'items' found in Google CSE API response.")
            if 'error' in search_data:
                error_details = search_data.get('error', {})
                print(f"    API Error: {error_details.get('message')}")
            if 'spelling' in search_data and 'correctedQuery' in search_data['spelling']:
                print(f"    Did you mean: \"{search_data['spelling']['correctedQuery']}\"?")
    except Exception as e:
        print(f"    Error in fetch_results_via_google_cse_api: {e}")
    print(f"    Found {len(results)} results via CSE API.")
    return results


def fetch_page_content(url: str) -> str | None:
    """ Fetches textual content of a URL. """
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        for S in soup(["script", "style", "nav", "footer", "aside", "form", "button"]): S.extract()
        text = soup.get_text(separator='\n', strip=True)
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)
        return text[:MAX_CONTENT_CHARS_FOR_SUMMARY]
    except Exception as e:
        print(f"    Error fetching content for {url}: {e}")
    return None


def generate_description_with_llama_gemini(page_title: str, page_content: str, user_query: str,
                                           refined_query: str) -> str:
    """ Generates description using LlamaIndex Gemini, considering both original and refined query. """
    if not page_content and page_title:
        page_content = f"The page is titled '{page_title}'. More details are on the page."
    elif not page_content and not page_title:
        return "Content and title missing, cannot generate description."

    prompt = f"""
User's Original Intention: "{user_query}"
Refined Search Query Used: "{refined_query}"
Webpage Title: "{page_title}"
Webpage Content Snippet:
---
{page_content}
---
Based on the user's original intention, the refined search query used, the webpage title, and its content snippet,
generate a single, concise, and informative sentence (strictly 15-25 words) that describes
what this webpage is about and why it might be relevant to the user's original intention.
Focus on the most important information from the content.
Do not add conversational fluff. Just the single sentence.

One-sentence description:
"""
    try:
        response = llm.complete(prompt)
        description = response.text.strip()
        description = re.sub(r'\s+', ' ', description)
        if len(description.split()) < 5:
            return f"{page_title} - Visit the page for more details."
        return description
    except Exception as e:
        print(f"    Error generating description for '{page_title}': {e}")
        return "Could not generate description (API error)."


def get_domain(url: str) -> str:
    if not url: return ""
    try:
        return urlparse(url).netloc
    except:
        return ""


# --- Main Script ---
if __name__ == "__main__":
    user_initial_query = input("Enter your search query: ")

    if not user_initial_query:
        print("Search query cannot be empty.")
        exit()

    # Step 1: Refine the search query using Gemini
    # This call also involves an API call to Gemini, so ensure your quotas allow for it
    effective_search_query = refine_search_query_with_gemini(user_initial_query, NUM_QUERY_SUGGESTIONS)
    time.sleep(1.1)  # Pause after Gemini call for query refinement

    if not effective_search_query:  # Should default to original if failed
        effective_search_query = user_initial_query

    # Step 2: Fetch search results using the (potentially refined) query
    initial_search_results = fetch_results_via_google_cse_api(effective_search_query, NUM_INITIAL_SEARCH_RESULTS)

    if not initial_search_results:
        print(f"No search results found from Google CSE API for query: \"{effective_search_query}\"")
        exit()

    print(
        f"\n🤖 Processing {len(initial_search_results)} results for refined query \"{effective_search_query}\" to generate descriptions...")

    candidate_results = []
    for i, item in enumerate(initial_search_results):
        url = item.get('link')
        title_from_api = item.get('title', "Untitled Page")

        if not url:
            print(f"    Skipping item {i + 1} (no URL).")
            continue

        print(f"    Processing result {i + 1}/{len(initial_search_results)}: {title_from_api} ({url})")
        page_content_text = fetch_page_content(url)

        # Pass both original user query and the effective search query to help Gemini contextualize
        description = generate_description_with_llama_gemini(
            title_from_api,
            page_content_text or "",
            user_initial_query,  # Original intention
            effective_search_query  # Query actually used for search
        )

        candidate_results.append({
            'title': title_from_api,
            'link': url,
            'description': description,
            'domain': get_domain(url)
        })
        time.sleep(1.1)  # Pause for Gemini description generation (60 QPM limit)

    # ... (Rest of the result diversification and printing logic remains the same) ...
    if not candidate_results:
        print("\nNo results could be processed to generate descriptions.")
        exit()

    print(f"\n✅ Generated descriptions for {len(candidate_results)} potential results.")
    print("✨ Selecting and diversifying top results...")

    final_results = []
    seen_domains = set()
    for res in candidate_results:
        if len(final_results) >= NUM_FINAL_RESULTS: break
        if res['domain'] and res['domain'] not in seen_domains:
            final_results.append(res);
            seen_domains.add(res['domain'])
    if len(final_results) < NUM_FINAL_RESULTS:
        for res in candidate_results:
            if len(final_results) >= NUM_FINAL_RESULTS: break
            if not any(f_res['link'] == res['link'] for f_res in final_results):
                final_results.append(res)
    final_results = final_results[:NUM_FINAL_RESULTS]

    print(
        f"\n🌟 Top {len(final_results)} Relevant Results for your intention '{user_initial_query}' (searched for '{effective_search_query}'):\n" + "=" * 50)
    if not final_results:
        print("No relevant results could be presented.")
    else:
        for i, result in enumerate(final_results):
            print(f"{i + 1}. Title: {result['title']}")
            print(f"   Link: {result['link']}")
            print(f"   Description: {result['description']}")
            print("-" * 30)