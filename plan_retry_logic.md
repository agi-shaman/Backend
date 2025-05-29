# Plan to Add Retry Logic with Exponential Backoff for Gemini API Calls

This plan outlines the steps to implement retry logic with exponential backoff for failed Gemini API requests in the project, using the `tenacity` library.

**1. Add `tenacity` Dependency:**

*   Add the `tenacity` library to your project's `Requirements.txt` file. This library provides a convenient way to add retry behavior to functions.

**2. Create a Wrapper Module:**

*   Create a new Python file named `lib/api_wrappers.py`. This module will contain functions or classes that wrap the core Gemini API calls with retry logic.

**3. Implement Retry Logic:**

*   Within `lib/api_wrappers.py`, define a function or a method that takes a Gemini API call (like `self._model.generate_content` or `self._model.send_message`) and its arguments as input.
*   Use the `@tenacity.retry` decorator with appropriate parameters to configure the retry strategy:
    *   `wait=tenacity.wait_exponential(multiplier=1, min=10, max=60)`: This sets the wait strategy to exponential backoff, starting with a 10-second wait (`min=10`), doubling the wait time on subsequent failures (`multiplier=1`), and capping the maximum wait time at 60 seconds (`max=60`).
    *   `stop=tenacity.stop_after_attempt(5)`: This will stop retrying after a maximum of 5 attempts (1 initial attempt + 4 retries).
    *   `retry=tenacity.retry_if_exception_type(...)`: This will specify which types of exceptions should trigger a retry (e.g., network errors, API rate limits, or specific Gemini API errors). The specific exceptions will need to be identified during implementation.

**4. Integrate Wrapper in `lib/agent.py`:**

*   Import the necessary retry logic from `lib/api_wrappers.py` into `lib/agent.py`.
*   Modify the methods within the `Agent` class (and potentially the `_ensure_pdf_settings_configured` method) where the `Gemini` LLM is used to wrap the API calls with the retry mechanism. This might involve passing the core API call method to the wrapper function or applying the decorator directly if the structure allows.

**Mermaid Diagram:**

```mermaid
graph TD
    A[lib/agent.py] --> B(Instantiate Gemini LLM)
    B --> C{API Call Methods in<br>.venv/lib/python3.9/site-packages/llama_index/llms/gemini/base.py}
    C --> D{Attempt API Call}
    D -- Failure --> E(Retry Logic in<br>lib/api_wrappers.py)
    E -- Wait (Exponential Backoff) --> D
    E -- Max Retries Exceeded --> F(Handle Persistent Failure)
    D -- Success --> G(Process Response)
    G --> A