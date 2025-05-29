# test_google_search.py
from googlesearch import search
import time

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
queries_to_test = ["pizza", "weather today", "python programming"]  # Use very common queries
num_results_to_fetch = 3  # Fetch fewer results to be less aggressive
pause_duration = 5.0  # Increased pause significantly

print(f"--- Testing googlesearch-python standalone ---")
print(f"User agent: {USER_AGENT}")
print(f"Pause between requests: {pause_duration} seconds")
print(f"Number of results to fetch per query: {num_results_to_fetch}\n")

for query in queries_to_test:
    print(f"Attempting query: '{query}'")
    urls_found = []
    try:
        # Adding tld and lang might help, remove if they cause issues for your region
        # You can also try 'num' instead of 'stop' for some versions/forks, but 'stop' is standard.
        for url in search(query, tld="com", lang="en", stop=num_results_to_fetch, pause=pause_duration,
                          user_agent=USER_AGENT):
            print(f"  Found: {url}")
            urls_found.append(url)

        if not urls_found:
            print(f"  No URLs found for query: '{query}'")
        else:
            print(f"  Successfully found {len(urls_found)} URLs for '{query}'.")

    except Exception as e:
        print(f"  An error occurred while searching for '{query}': {e}")
        import traceback

        traceback.print_exc()
    print("-" * 30)
    time.sleep(2)  # Small pause between different queries