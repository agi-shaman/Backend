import re
import time
import subprocess
from playwright.sync_api import sync_playwright, Playwright, TimeoutError as PlaywrightTimeoutError

# --- Configuration ---
DEFAULT_URL = "https://www.google.com"
SCREENSHOT_FILENAME = "playwright_ai_task_screenshot.png"
BROWSER_SLOW_MO = 500  # Milliseconds, to make actions visible. Set to 0 for faster execution.
ACTION_TIMEOUT = 15000 # Milliseconds for Playwright actions (e.g., click, fill)
NAVIGATION_TIMEOUT = 30000 # Milliseconds for page navigation

# --- "AI" (Gemini Model Simulation) ---
# This function will parse the user's prompt and generate Playwright code lines.
# For a real LLM, this would involve API calls and more sophisticated NLP.
def generate_playwright_code_from_prompt(user_prompt: str) -> tuple[list[str], str | None, str | None]:
    """
    Parses the user prompt and generates a list of Playwright Python code lines.
    Returns: (list_of_code_lines, target_url, text_to_fill)
    """
    generated_code_lines = []
    target_url = None
    text_to_fill = None

    # Example 1: "write 'some text' in the search bar on example.com"
    # Example 2: "go to example.com and take a screenshot"
    # Example 3: "on example.com, click the button 'Submit'"

    prompt_lower = user_prompt.lower()

    # --- 1. Determine Target URL ---
    url_match = re.search(r"\b(on|to|at)\s+(https?://[^\s]+|[^\s]+\.(com|org|net|dev|io|co|us|uk)\b/?([^\s]*))", user_prompt, re.IGNORECASE)
    if url_match:
        raw_url = url_match.group(2) # The full URL part
        if not raw_url.startswith("http"):
            target_url = "https://" + raw_url
        else:
            target_url = raw_url
        print(f"🤖 AI: Identified target URL: {target_url}")
        generated_code_lines.append(f'print(f"Navigating to {target_url}...")')
        generated_code_lines.append(f'page.goto("{target_url}", timeout={NAVIGATION_TIMEOUT})')
        generated_code_lines.append(f'page.wait_for_load_state("domcontentloaded", timeout={NAVIGATION_TIMEOUT}) # Wait for basic page structure')
        generated_code_lines.append(f'print("Page navigation complete.")')
    else:
        print(f"🤖 AI: No specific URL found in prompt, will use default or ask.")
        # Could ask user for URL here or use a default
        target_url = DEFAULT_URL
        generated_code_lines.append(f'print(f"Navigating to default URL: {target_url}...")')
        generated_code_lines.append(f'page.goto("{target_url}", timeout={NAVIGATION_TIMEOUT})')
        generated_code_lines.append(f'page.wait_for_load_state("domcontentloaded", timeout={NAVIGATION_TIMEOUT})')
        generated_code_lines.append(f'print("Page navigation complete.")')


    # --- 2. Parse Action: Write Text ---
    write_match = re.search(r"write\s+['\"]([^'\"]+)['\"]", user_prompt, re.IGNORECASE)
    if write_match:
        text_to_fill = write_match.group(1)
        print(f"🤖 AI: Identified text to write: '{text_to_fill}'")

        # Try to find a target element for writing (e.g., "search bar", "input field")
        target_element_phrase = "search bar" # Default if not specified
        if "in the search bar" in prompt_lower:
            target_element_phrase = "search bar"
        elif "in the input field" in prompt_lower: # Add more phrases as needed
            target_element_phrase = "input field"
        elif "in the text area" in prompt_lower:
            target_element_phrase = "text area"
        # More sophisticated: "in the field named 'username'"

        print(f"🤖 AI: Will try to write in a '{target_element_phrase}'.")

        # Generic selectors for input/text areas
        # Prioritize more specific ones if the phrase allows
        selectors = [
            'textarea[name*="q"]', 'input[name*="q"]',  # Common for search (q)
            'textarea[name*="search"]', 'input[name*="search"]',
            'input[type="search"]',
            'textarea[aria-label*="search" i]', 'input[aria-label*="search" i]', # Case-insensitive aria-label
            'textarea', 'input[type="text"]', 'input:not([type="submit"]):not([type="button"]):not([type="hidden"]):not([type="checkbox"]):not([type="radio"])' # General inputs
        ]
        generated_code_lines.append(f'print(f"Attempting to find element for \'{target_element_phrase}\' to fill...")')
        generated_code_lines.append(f'element_to_fill = None')
        generated_code_lines.append(f'for selector in {selectors}:')
        generated_code_lines.append(f'    try:')
        generated_code_lines.append(f'        print(f"  Trying selector: {{selector}}")')
        generated_code_lines.append(f'        element_to_fill = page.query_selector(selector)')
        generated_code_lines.append(f'        if element_to_fill and element_to_fill.is_visible() and element_to_fill.is_editable():')
        generated_code_lines.append(f'            print(f"  Found visible and editable element with selector: {{selector}}")')
        generated_code_lines.append(f'            break') # Found a suitable element
        generated_code_lines.append(f'        else: element_to_fill = None') # Reset if not suitable
        generated_code_lines.append(f'    except PlaywrightTimeoutError:')
        generated_code_lines.append(f'        print(f"  Timeout with selector: {{selector}}")')
        generated_code_lines.append(f'        element_to_fill = None') # Ensure reset on timeout
        generated_code_lines.append(f'    except Exception as e_sel:')
        generated_code_lines.append(f'        print(f"  Error with selector {{selector}}: {{e_sel}}")')
        generated_code_lines.append(f'        element_to_fill = None') # Ensure reset on other errors

        generated_code_lines.append(f'if element_to_fill:')
        generated_code_lines.append(f'    print(f"Filling element with text: \'{text_to_fill}\'")')
        generated_code_lines.append(f'    element_to_fill.fill("{text_to_fill}", timeout={ACTION_TIMEOUT})')
        # Optional: Press Enter after filling
        if "press enter" in prompt_lower or "submit" in prompt_lower and not "button" in prompt_lower:
             generated_code_lines.append(f'    print("Pressing Enter...")')
             generated_code_lines.append(f'    element_to_fill.press("Enter")')
             generated_code_lines.append(f'    page.wait_for_load_state("domcontentloaded", timeout={NAVIGATION_TIMEOUT}) # Wait for potential navigation')
        generated_code_lines.append(f'else:')
        generated_code_lines.append(f'    print(f"🤖 AI Error: Could not find a suitable input/text field for \'{target_element_phrase}\'.")')
        generated_code_lines.append(f'    # raise Exception("Could not find element to fill") # Optionally raise error')

    # --- 3. Parse Action: Click Button ---
    click_match = re.search(r"(click|press)\s+(?:the\s+)?button\s+['\"]([^'\"]+)['\"]", user_prompt, re.IGNORECASE)
    if click_match:
        button_text_or_label = click_match.group(2)
        print(f"🤖 AI: Identified click action for button with text/label: '{button_text_or_label}'")
        # Using Playwright's text selector and role selector
        generated_code_lines.append(f'print(f"Attempting to click button: \'{button_text_or_label}\'...")')
        generated_code_lines.append(f'button_to_click = None')
        generated_code_lines.append(f'try:')
        generated_code_lines.append(f'    # Try by role and name (more robust)')
        generated_code_lines.append(f'    button_to_click = page.get_by_role("button", name=re.compile(r"{re.escape(button_text_or_label)}", re.IGNORECASE)).first')
        generated_code_lines.append(f'    if not button_to_click.is_visible(): button_to_click = None')
        generated_code_lines.append(f'except PlaywrightTimeoutError:')
        generated_code_lines.append(f'    pass # Will try next selector')
        generated_code_lines.append(f'except Exception:')
        generated_code_lines.append(f'    pass # Will try next selector')

        generated_code_lines.append(f'if not button_to_click:')
        generated_code_lines.append(f'    try:')
        generated_code_lines.append(f'        # Try by text content (less robust but common)')
        generated_code_lines.append(f'        button_to_click = page.get_by_text(re.compile(r"^{re.escape(button_text_or_label)}$", re.IGNORECASE), exact=False).first')
        generated_code_lines.append(f'        if not button_to_click.is_visible(): button_to_click = None')
        generated_code_lines.append(f'    except PlaywrightTimeoutError:')
        generated_code_lines.append(f'        pass')
        generated_code_lines.append(f'    except Exception:')
        generated_code_lines.append(f'        pass')

        generated_code_lines.append(f'if button_to_click:')
        generated_code_lines.append(f'    print("Button found. Clicking...")')
        generated_code_lines.append(f'    button_to_click.click(timeout={ACTION_TIMEOUT})')
        generated_code_lines.append(f'    page.wait_for_load_state("domcontentloaded", timeout={NAVIGATION_TIMEOUT}) # Wait for potential navigation')
        generated_code_lines.append(f'else:')
        generated_code_lines.append(f'    print(f"🤖 AI Error: Could not find a clickable button with text/label \'{button_text_or_label}\'.")')


    # --- 4. Default Action: Take Screenshot ---
    if not generated_code_lines or "screenshot" in prompt_lower or not (write_match or click_match): # Add screenshot if no other major action or if explicitly asked
        if not any("page.screenshot" in line for line in generated_code_lines): # Avoid duplicate screenshot commands
            generated_code_lines.append(f'print("Taking a screenshot...")')
            generated_code_lines.append(f'page.screenshot(path="{SCREENSHOT_FILENAME}", full_page=True)')
            generated_code_lines.append(f'print(f"Screenshot saved as {SCREENSHOT_FILENAME}")')

    return generated_code_lines, target_url, text_to_fill


# --- Main Execution Logic ---
def run_playwright_task(generated_code_lines: list[str]):
    if not generated_code_lines:
        print("No Playwright code was generated to execute.")
        return

    # Combine lines into a single string of code
    # We'll execute this within the Playwright context
    code_to_execute_str = "\n    ".join(generated_code_lines) # Indent for function body

    # Prepare the execution script string
    # We define a function dynamically and then call it.
    # This ensures 'page' and other Playwright objects are in scope.
    script_to_run = f"""
def dynamic_playwright_actions(page, re, PlaywrightTimeoutError):
    # Variables like NAVIGATION_TIMEOUT, ACTION_TIMEOUT, SCREENSHOT_FILENAME
    # are available from the outer scope if not shadowed.
    # For safety, we can pass them or define them here if needed.
    print("--- Starting dynamically generated Playwright actions ---")
    time.sleep(0.5) # Small pause before actions
    {code_to_execute_str}
    print("--- Dynamically generated Playwright actions finished ---")
    time.sleep(2) # Keep browser open for a bit to see result
"""
    print("\n🤖 AI: Generated the following Playwright script to execute:")
    print("="*60)
    print(script_to_run)
    print("="*60)

    with sync_playwright() as p:
        # browser = p.chromium.launch(headless=False, slow_mo=BROWSER_SLOW_MO)
        # Try Firefox or Webkit if you prefer
        browser_type = p.chromium # or p.firefox or p.webkit
        try:
            browser = browser_type.launch(headless=False, slow_mo=BROWSER_SLOW_MO)
        except Exception as e:
            print(f"Error launching browser {browser_type.name}: {e}")
            print(f"Attempting to install {browser_type.name} browser for Playwright...")
            try:
                subprocess.run(["playwright", "install", browser_type.name], check=True, capture_output=True)
                print(f"{browser_type.name} installed. Please try running the script again.")
            except Exception as install_e:
                print(f"Failed to install {browser_type.name}: {install_e}")
                print("Please ensure Playwright is installed and browsers are set up (e.g., run 'pip install playwright' and 'playwright install').")
            return

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            viewport={'width': 1280, 'height': 720} # Default viewport size
        )
        context.set_default_timeout(ACTION_TIMEOUT)
        page = context.new_page()

        try:
            # Define a dictionary for the local scope of exec
            # This makes 'page', 'time', 're', 'PlaywrightTimeoutError' available to the executed code
            exec_scope = {
                "page": page,
                "time": time,
                "re": re, # For regex in generated code if any (e.g. get_by_role with regex)
                "PlaywrightTimeoutError": PlaywrightTimeoutError, # Make timeout error available
                "NAVIGATION_TIMEOUT": NAVIGATION_TIMEOUT,
                "ACTION_TIMEOUT": ACTION_TIMEOUT,
                "SCREENSHOT_FILENAME": SCREENSHOT_FILENAME,
                "print": print # Allow generated code to print
            }
            # Execute the script definition
            exec(script_to_run, exec_scope)
            # Call the dynamically defined function
            exec_scope['dynamic_playwright_actions'](page, re, PlaywrightTimeoutError)

            print("\n✅ Task execution attempt complete.")

        except PlaywrightTimeoutError as e_timeout:
            print(f"\n❌ Playwright Timeout Error during execution: {e_timeout}")
            page.screenshot(path="playwright_timeout_error.png")
            print("Screenshot of error state saved to playwright_timeout_error.png")
        except Exception as e_exec:
            print(f"\n❌ An error occurred during Playwright execution: {e_exec}")
            try:
                page.screenshot(path="playwright_execution_error.png")
                print("Screenshot of error state saved to playwright_execution_error.png")
            except Exception as e_ss:
                print(f"Could not take error screenshot: {e_ss}")
        finally:
            print("Closing browser in 5 seconds...")
            time.sleep(5)
            browser.close()
            print("Browser closed.")

# --- Entry Point ---
if __name__ == "__main__":
    # Ensure Playwright browsers are installed (optional, good for first run)
    try:
        print("Checking Playwright browser installations (Chromium)...")
        # Check if a browser is installed, playwright install can be slow
        # A more robust check would be to try launching a browser briefly
        # For now, we'll rely on the error handling in run_playwright_task
        # subprocess.run(["playwright", "install", "chromium"], check=True, capture_output=True, timeout=60)
        # print("Chromium browser for Playwright seems ready.")
        pass # Assuming user has run `playwright install` or handling it in launch
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Warning: Could not automatically ensure Playwright browsers. Error: {e}")
        print("Please ensure Playwright browsers are installed (e.g., run 'playwright install').")

    print("--- Playwright AI Task Automator ---")
    user_instruction = input(
        "🤖 Gemini (simulated): What task would you like me to perform with Playwright?\n"
        "   Examples:\n"
        "   - write 'Playwright automation' in the search bar on google.com\n"
        "   - go to playwright.dev and take a screenshot\n"
        "   - on wikipedia.org, write 'Python language' in the search bar and press enter\n"
        "   - on example.com, click the button 'More information'\n"
        "> "
    )

    if user_instruction:
        generated_code, _, _ = generate_playwright_code_from_prompt(user_instruction)
        run_playwright_task(generated_code)
    else:
        print("No task provided. Exiting.")
