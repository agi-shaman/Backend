import time
import asyncio
import os
import random
import math
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException,
    MoveTargetOutOfBoundsException
)
from llama_index.core.tools import FunctionTool
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.agent.workflow import FunctionAgent
from selenium.webdriver.common.action_chains import ActionChains

# Import selenium-stealth
from selenium_stealth import stealth

from ..rate_limited_gemini import RateLimitedGemini

from dotenv import load_dotenv

load_dotenv()
GeminiKey = os.getenv("GeminiKey")

AGENT_WORKER_LLM_MODEL = "gemini-2.5-flash-preview-05-20"
print(f"Using LLM Model: {AGENT_WORKER_LLM_MODEL}")

try:
    llm = RateLimitedGemini(
        model_name=AGENT_WORKER_LLM_MODEL,
        api_key=GeminiKey,
    )
except Exception as e:
    print(f"Error initializing RateLimitedGemini: {e}")
    print("Falling back to a placeholder LLM for structure.")
    from llama_index.llms.openai import OpenAI # Example fallback
    try:
        llm = OpenAI(model="gpt-3.5-turbo")
        print("Warning: Using OpenAI GPT-3.5-Turbo as a fallback LLM.")
    except Exception as e_openai:
        print(f"Failed to initialize fallback OpenAI LLM: {e_openai}")
        llm = None

SCREENSHOT_DIR = "screenshots"
if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

class BrowserAutomation:
    def __init__(self, headless: bool = True, chromium_binary_path: Optional[str] = None):
        self.driver = None
        options = Options()
        if headless:
            # For selenium-stealth, it's often recommended to avoid the new headless mode
            # if maximum stealth is required, as some stealth features might work better
            # with the older headless or fully headed mode. Test what works best.
            # options.add_argument("--headless=new")
            options.add_argument("--headless") # Using older headless for potentially better stealth compatibility
        if chromium_binary_path:
            options.binary_location = chromium_binary_path

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080") # Common desktop resolution
        options.add_argument("--disable-gpu")
        options.add_argument("--log-level=0")
        options.add_argument("--start-maximized") # Start maximized
        options.add_argument("--disable-infobars") # Disable "Chrome is being controlled..."
        options.add_argument("--disable-extensions") # Disable extensions

        # Experimental options for stealth (some are handled by selenium-stealth too)
        options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--disable-blink-features=AutomationControlled')

        user_agent = ( # A common, recent User-Agent
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        options.add_argument(f'user-agent={user_agent}')

        try:
            # Ensure chromedriver is in PATH or specify service
            # service = Service(executable_path="/path/to/your/chromedriver_binary")
            # self.driver = webdriver.Chrome(service=service, options=options)
            self.driver = webdriver.Chrome(options=options)

            # --- APPLY SELENIUM-STEALTH ---
            print("Applying selenium-stealth patches...")
            stealth(
                self.driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32", # Common platform, can be "MacIntel", "Linux x86_64"
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine", # Or other common renderers
                fix_hairline=True,
                run_on_insecure_origins=False, # Set to True if needed for specific sites
            )
            print("Selenium-stealth patches applied.")
            # --- END OF SELENIUM-STEALTH ---

            self.driver.implicitly_wait(5) # General wait
            print(f"BrowserAutomation (with Selenium-Stealth) initialized. Using: {self.driver.capabilities.get('browserName')} {self.driver.capabilities.get('browserVersion')}")
            if chromium_binary_path:
                print(f"Attempted to use Chromium binary at: {chromium_binary_path}")

        except WebDriverException as e:
            print(f"Error initializing WebDriver: {e}")
            # ... (rest of error handling) ...
            print("Please ensure ChromeDriver is installed and in your PATH, or specify its executable_path.")
            if chromium_binary_path:
                print(f"Also check that the Chromium binary path is correct: {chromium_binary_path}")
            raise
    # ... (The rest of the BrowserAutomation class methods:
    # _get_by_type, _get_element, _human_like_delay, _scroll_element_into_view,
    # _move_mouse_human_like, navigate, click, type, get_text, get_attribute,
    # get_current_url, get_page_source, scroll_page, take_screenshot, close
    # remain IDENTICAL to the previous version with human-like mouse movements)

    def _get_by_type(self, locator_type: str) -> By:
        locator_type = locator_type.lower()
        if locator_type == 'xpath': return By.XPATH
        elif locator_type == 'css': return By.CSS_SELECTOR
        elif locator_type == 'id': return By.ID
        elif locator_type == 'name': return By.NAME
        elif locator_type == 'class_name': return By.CLASS_NAME
        elif locator_type == 'link_text': return By.LINK_TEXT
        elif locator_type == 'partial_link_text': return By.PARTIAL_LINK_TEXT
        elif locator_type == 'tag_name': return By.TAG_NAME
        else: raise ValueError(f"Invalid locator type: {locator_type}.")


    def _get_element(self, locator_type: str, locator_value: str, timeout: int = 10, condition=EC.presence_of_element_located):
        if not self.driver: raise Exception("Driver not initialized.")
        by_type = self._get_by_type(locator_type)
        try:
            element = WebDriverWait(self.driver, timeout).until(condition((by_type, locator_value)))
            return element
        except TimeoutException:
            self.take_screenshot(f"error_element_not_found_{locator_type}_{int(time.time())}")
            raise TimeoutException(f"Element not found or condition not met using {locator_type}='{locator_value}' within {timeout} seconds.")


    def _human_like_delay(self, min_s: float = 0.1, max_s: float = 0.5):
        time.sleep(random.uniform(min_s, max_s))

    def _scroll_element_into_view(self, element):
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center', inline: 'center'});", element
            )
            self._human_like_delay(0.3, 0.7)
        except Exception as e:
            print(f"Warning: JavaScript scrollIntoView failed: {e}. Falling back to ActionChains move.")
            try:
                ActionChains(self.driver).move_to_element(element).perform()
                self._human_like_delay(0.2, 0.5)
            except Exception as e2:
                print(f"Warning: ActionChains move_to_element for scrolling also failed: {e2}")


    def _move_mouse_human_like(self, element, target_x_offset=None, target_y_offset=None):
        actions = ActionChains(self.driver)
        self._scroll_element_into_view(element)

        element_width = element.size.get('width', 1)
        element_height = element.size.get('height', 1)

        if target_x_offset is None:
            target_x_offset = random.randint(max(1, int(element_width * 0.2)), max(1,int(element_width * 0.8)))
        if target_y_offset is None:
            target_y_offset = random.randint(max(1, int(element_height * 0.2)), max(1,int(element_height * 0.8)))

        target_x_offset = min(target_x_offset, element_width -1 if element_width > 0 else 0)
        target_y_offset = min(target_y_offset, element_height -1 if element_height > 0 else 0)
        target_x_offset = max(0, target_x_offset)
        target_y_offset = max(0, target_y_offset)

        initial_approach_x = random.choice([0, element_width // 4, element_width // 2])
        initial_approach_y = random.choice([0, element_height // 4, element_height // 2])
        initial_approach_x = min(initial_approach_x, element_width -1 if element_width > 0 else 0)
        initial_approach_y = min(initial_approach_y, element_height -1 if element_height > 0 else 0)

        try:
            actions.move_to_element_with_offset(element, initial_approach_x, initial_approach_y)
            actions.perform()
            self._human_like_delay(0.2, 0.6)
        except MoveTargetOutOfBoundsException:
            print("Warning: Initial mouse approach was out of bounds, moving to element center instead.")
            actions.reset_actions()
            actions.move_to_element(element).perform()
            self._human_like_delay(0.2, 0.6)
        except Exception as e:
            print(f"Error during initial mouse approach: {e}")
            actions.reset_actions() # Ensure clean state

        try:
            actions.reset_actions()
            actions.move_to_element_with_offset(element, target_x_offset, target_y_offset)
            actions.perform()
            print(f"  Mouse moved to target offset: x={target_x_offset}, y={target_y_offset} on element.")
            self._human_like_delay(0.1, 0.3)
        except MoveTargetOutOfBoundsException:
            print(f"Warning: Final target move to offset ({target_x_offset},{target_y_offset}) out of bounds. Clicking element center.")
            actions.reset_actions()
            actions.move_to_element(element).perform()
            self._human_like_delay(0.1, 0.3)
        except Exception as e:
            print(f"Error during final mouse move: {e}")
            actions.reset_actions() # Ensure clean state
        
        return actions


    def navigate(self, url: str):
        if not self.driver: return "Browser not initialized."
        print(f"Navigating to {url}")
        self._human_like_delay(0.5, 1.5)
        self.driver.get(url)
        self._human_like_delay(1.0, 2.5)
        self.take_screenshot(f"navigate_{url.replace('://', '_').replace('/', '_')}_{int(time.time())}")
        return f"Successfully navigated to {url}"

    def click(self, locator_type: str, locator_value: str):
        if not self.driver: return "Browser not initialized."
        print(f"Attempting 'human-like path + stealth' click on element with {locator_type}='{locator_value}'")
        element = self._get_element(locator_type, locator_value, condition=EC.element_to_be_clickable)
        
        actions = self._move_mouse_human_like(element)
        actions.click()
        actions.perform()

        self._human_like_delay(0.2, 0.5)
        print("Human-like path + stealth click successful.")
        self.take_screenshot(f"click_stealth_path_{locator_type}_{int(time.time())}")
        return f"Successfully performed human-like path + stealth click on element with {locator_type}='{locator_value}'"

    def type(self, locator_type: str, locator_value: str, text: str):
        if not self.driver: return "Browser not initialized."
        print(f"Attempting 'human-like path + stealth' type '{text}' into element with {locator_type}='{locator_value}'")
        element = self._get_element(locator_type, locator_value, condition=EC.visibility_of_element_located)

        element_width = element.size.get('width', 1)
        element_height = element.size.get('height', 1)
        target_x = element_width // 2
        target_y = element_height // 2

        actions = self._move_mouse_human_like(element, target_x_offset=target_x, target_y_offset=target_y)
        actions.click() # Click to focus
        actions.perform()
        self._human_like_delay(0.1, 0.3)

        if not (element.tag_name.lower() in ["input", "textarea"] or element.get_attribute("contenteditable") == "true"):
            print(f"Warning: Element {locator_type}='{locator_value}' may not be a standard typable field (tag: {element.tag_name}).")

        # Check if element is focused, sometimes click doesn't take immediately
        # This is a bit advanced and might not always be necessary.
        # if self.driver.switch_to.active_element != element:
        #     print("Element not focused after click, attempting JS focus.")
        #     self.driver.execute_script("arguments[0].focus();", element)
        #     self._human_like_delay(0.1, 0.2)
            
        element.clear()
        self._human_like_delay(0.1, 0.4)

        for char_idx, char_val in enumerate(text):
            element.send_keys(char_val)
            if char_idx < 5 :
                 self._human_like_delay(0.03, 0.08)
            else:
                 self._human_like_delay(0.05, 0.15)

        print("Human-like path + stealth type successful.")
        self.take_screenshot(f"type_stealth_path_{locator_type}_{int(time.time())}")
        return f"Successfully typed '{text}' human-like (with path + stealth) into element with {locator_type}='{locator_value}'"

    def get_text(self, locator_type: str, locator_value: str) -> str:
        if not self.driver: return "Browser not initialized."
        print(f"Attempting to get text from element with {locator_type}='{locator_value}'")
        element = self._get_element(locator_type, locator_value, condition=EC.visibility_of_element_located)
        text = element.text
        print(f"Retrieved text: '{text[:100]}...'")
        return text

    def get_attribute(self, locator_type: str, locator_value: str, attribute_name: str) -> str:
        if not self.driver: return "Browser not initialized."
        print(f"Attempting to get attribute '{attribute_name}' from element with {locator_type}='{locator_value}'")
        element = self._get_element(locator_type, locator_value)
        attr_value = element.get_attribute(attribute_name)
        print(f"Retrieved attribute '{attribute_name}': '{attr_value}'")
        return attr_value if attr_value is not None else ""

    def get_current_url(self) -> str:
        if not self.driver: return "Browser not initialized."
        current_url = self.driver.current_url
        print(f"Current URL: {current_url}")
        return current_url

    def get_page_source(self) -> str:
        if not self.driver: return "Browser not initialized."
        source = self.driver.page_source
        print(f"Retrieved page source (length: {len(source)}).")
        return source

    def scroll_page(self, direction: str = "down", pixels: Optional[int] = None,
                    element_locator_type: Optional[str] = None, element_locator_value: Optional[str] = None):
        if not self.driver: return "Browser not initialized."
        if element_locator_type and element_locator_value:
            print(f"Scrolling to element {element_locator_type}='{element_locator_value}'")
            element = self._get_element(element_locator_type, element_locator_value)
            self._scroll_element_into_view(element)
            print("Scrolled to element.")
            return "Scrolled to element."
        else:
            current_scroll_position = self.driver.execute_script("return window.pageYOffset;")
            if pixels:
                scroll_amount = pixels if direction == "down" else -pixels
            else:
                page_height = self.driver.execute_script("return document.body.scrollHeight")
                scroll_amount = page_height if direction == "down" else -page_height
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            self._human_like_delay(0.5, 1.0)
            new_scroll_position = self.driver.execute_script("return window.pageYOffset;")
            scrolled_by = new_scroll_position - current_scroll_position
            print(f"Scrolled window {direction} by approximately {abs(scrolled_by)} pixels.")
            return f"Scrolled window {direction} by approximately {abs(scrolled_by)} pixels."


    def take_screenshot(self, name: str):
        if not self.driver: return
        safe_name = "".join(c if c.isalnum() or c in ('_','-') else '_' for c in name)
        timestamp = int(time.time())
        filename = os.path.join(SCREENSHOT_DIR, f"{safe_name}_{timestamp}.png")
        try:
            self.driver.save_screenshot(filename)
            print(f"Screenshot saved to {filename}")
        except Exception as e:
            print(f"Failed to take screenshot: {e}")


    def close(self):
        if self.driver:
            print("Closing browser.")
            self.driver.quit()
            self.driver = None
            print("Browser closed.")
        else:
            print("No browser instance to close.")


browser_instance: Optional[BrowserAutomation] = None

def initialize_browser_tool_func(headless: bool = True, chromium_path: Optional[str] = None) -> str:
    """
    Initializes the global browser instance with selenium-stealth (Chromium if path specified)
    and navigates to Google.com.
    Args:
        headless (bool): Run headless. Defaults to True.
        chromium_path (str, optional): Absolute path to the Chromium binary.
    """
    global browser_instance
    if browser_instance and browser_instance.driver:
        current_url_msg = "Could not retrieve current URL directly."
        try:
            current_url = browser_instance.driver.current_url
            current_url_msg = f"Current URL: {current_url}"
        except Exception: pass
        return f"Browser is already initialized. {current_url_msg}"
    try:
        browser_instance = BrowserAutomation(headless=headless, chromium_binary_path=chromium_path)
        nav_status = browser_instance.navigate("https://www.google.com")
        return f"Browser initialized with stealth. {nav_status}"
    except Exception as e:
        if browser_instance:
            try: browser_instance.close()
            except Exception as close_e: print(f"Error during cleanup: {close_e}")
            finally: browser_instance = None
        return f"Failed to initialize stealth browser: {e}"

def close_browser_tool_func() -> str:
    """Closes the global browser instance. Call this when all browser tasks are complete."""
    global browser_instance
    if browser_instance:
        browser_instance.close()
        browser_instance = None
        return "Browser closed successfully."
    else:
        return "No browser instance to close."

def navigate_tool_func(url: str) -> str:
    if browser_instance and browser_instance.driver:
        try:
            return browser_instance.navigate(url)
        except Exception as e:
            return f"Error during navigation: {e}"
    return "Browser not initialized. Call initialize_browser_tool_func first."

def click_tool_func(locator_type: str, locator_value: str) -> str:
    if browser_instance and browser_instance.driver:
        try: return browser_instance.click(locator_type, locator_value)
        except Exception as e: return f"Error clicking element ({locator_type}='{locator_value}'): {e}"
    return "Browser not initialized. Call initialize_browser_tool_func first."

def type_tool_func(locator_type: str, locator_value: str, text: str) -> str:
    if browser_instance and browser_instance.driver:
        try: return browser_instance.type(locator_type, locator_value, text)
        except Exception as e: return f"Error typing into element ({locator_type}='{locator_value}'): {e}"
    return "Browser not initialized. Call initialize_browser_tool_func first."

def get_text_tool_func(locator_type: str, locator_value: str) -> str:
    if browser_instance and browser_instance.driver:
        try: return browser_instance.get_text(locator_type, locator_value)
        except Exception as e: return f"Error getting text from element ({locator_type}='{locator_value}'): {e}"
    return "Browser not initialized. Call initialize_browser_tool_func first."

def get_attribute_tool_func(locator_type: str, locator_value: str, attribute_name: str) -> str:
    if browser_instance and browser_instance.driver:
        try: return browser_instance.get_attribute(locator_type, locator_value, attribute_name)
        except Exception as e: return f"Error getting attribute '{attribute_name}' from element ({locator_type}='{locator_value}'): {e}"
    return "Browser not initialized. Call initialize_browser_tool_func first."

def get_current_url_tool_func() -> str:
    if browser_instance and browser_instance.driver:
        try: return browser_instance.get_current_url()
        except Exception as e: return f"Error getting current URL: {e}"
    return "Browser not initialized. Call initialize_browser_tool_func first."

def get_page_source_tool_func() -> str:
    if browser_instance and browser_instance.driver:
        try: return browser_instance.get_page_source()
        except Exception as e: return f"Error getting page source: {e}"
    return "Browser not initialized. Call initialize_browser_tool_func first."

def scroll_page_tool_func(direction: str = "down", pixels: Optional[int] = None,
                           element_locator_type: Optional[str] = None, element_locator_value: Optional[str] = None) -> str:
    if browser_instance and browser_instance.driver:
        try: return browser_instance.scroll_page(direction, pixels, element_locator_type, element_locator_value)
        except Exception as e: return f"Error scrolling page: {e}"
    return "Browser not initialized. Call initialize_browser_tool_func first."


close_browser_tool = FunctionTool.from_defaults(fn=close_browser_tool_func, description="Closes the browser. MUST be called when all browser tasks are completed.")


# --- Update FunctionTool descriptions for tools that benefit from stealth ---
initialize_browser_tool = FunctionTool.from_defaults(
    fn=initialize_browser_tool_func,
    description="Initializes a stealthy browser (Chromium if path specified) with human-like settings, and navigates to Google.com. "
                "MUST be called first. Args: headless (bool, opt), chromium_path (str, opt)."
)
browser_navigate_tool = FunctionTool.from_defaults(fn=navigate_tool_func, description="Navigates the stealthy browser to a URL with human-like delays. Args: url (str).")
browser_click_tool = FunctionTool.from_defaults(
    fn=click_tool_func,
    description="Performs a human-like click in the stealthy browser, including simulated mouse path/settling. Args: locator_type (str), locator_value (str)."
)
browser_type_tool = FunctionTool.from_defaults(
    fn=type_tool_func,
    description="Types text into a web element in the stealthy browser with human-like mouse movement and keystroke delays. Args: locator_type (str), locator_value (str), text (str)."
)
browser_get_text_tool = FunctionTool.from_defaults(fn=get_text_tool_func, description="Extracts text from a web element. Args: locator_type (str), locator_value (str).")
browser_get_attribute_tool = FunctionTool.from_defaults(fn=get_attribute_tool_func, description="Gets an attribute's value from a web element. Args: locator_type (str), locator_value (str), attribute_name (str).")
browser_get_current_url_tool = FunctionTool.from_defaults(fn=get_current_url_tool_func, description="Returns the current URL.")
browser_get_page_source_tool = FunctionTool.from_defaults(fn=get_page_source_tool_func, description="Returns the full HTML source of the current page.")
browser_scroll_page_tool = FunctionTool.from_defaults(fn=scroll_page_tool_func, description="Scrolls the stealthy browser page with human-like delays. Args: direction (str, opt), pixels (int, opt), element_locator_type (str, opt), element_locator_value (str, opt).")


all_tools = [
    initialize_browser_tool, close_browser_tool, browser_navigate_tool, browser_click_tool,
    browser_type_tool, browser_get_text_tool, browser_get_attribute_tool,
    browser_get_current_url_tool, browser_get_page_source_tool, browser_scroll_page_tool,
]

async def run_agent():
    global browser_instance
    try:
        worker = FunctionAgent(
            llm=llm,
            tools=all_tools,
            system_prompt="""
You are a highly advanced web automation assistant employing stealth techniques. Your objective is to answer user queries by interacting with web pages in a way that closely mimics human behavior and avoids common bot detection, including mouse movement paths and browser properties.

Follow these instructions METICULOUSLY:
1.  **Initialization**:
    *   Call `initialize_browser_tool_func` first. This sets up a browser with stealth modifications. You can specify `headless=False` to see it or provide a `chromium_path`. It opens Google.com.

2.  **Performing a Search**:
    *   On Google.com, use `type_tool_func` (simulates human typing path and speed in the stealth browser) to enter the search query into the search bar (locator: `name="q"`).
    *   Use `click_tool_func` (simulates human mouse path and click in the stealth browser) for the search button (e.g., locator: `name="btnK"`).

3.  **Processing Search Results Page (CRITICAL FOR EFFICIENCY & STEALTH)**:
    *   (Keep the detailed instructions from the previous version about analyzing search results efficiently)
    *   Action Plan: `get_page_source_tool_func()`, internal reasoning, targeted `get_text_tool_func` / `get_attribute_tool_func`, decide on links.

4.  **Navigating to Promising Links and Extracting Details**:
    *   Use `navigate_tool_func` (human-like delays in stealth browser) for promising URLs.
    *   Use targeted `get_text_tool_func` or `get_page_source_tool_func` if necessary.
    *   Use `scroll_page_tool_func` (human-like delays in stealth browser) if needed.

5.  **Information Extraction and Summarization (THE GOAL)**:
    *   (Same as before: concise summary)

6.  **Tool Usage Notes**:
    *   All interaction tools (`click`, `type`, `navigate`, `scroll`) now incorporate more human-like delays and movements within a stealth-configured browser.

7.  **Cleanup**:
    *   Call `close_browser_tool_func` ONLY after formulating the final answer.

8.  **Error Handling & Quotas**:
    *   (Same as before: analyze errors, be mindful of quotas)

User's Request is Key. Your advanced stealth and interaction capabilities should help you navigate more effectively and discreetly.
""",
            verbose=True
        )
        memory = ChatMemoryBuffer.from_defaults(token_limit=390000)
        user_query = "Find me the best rated pizza place in NYC. Summarize the top 3 results if possible, including their names and any rating information you can find."
        print(f"\n--- Starting Agent with query: '{user_query}' ---")

        response = await worker.run(user_msg=user_query, memory=memory)

        print("\n--- Agent's Final Response ---")
        print(response)

    except Exception as e:
        print(f"An error occurred during agent execution: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n--- Ensuring browser is closed (if initialized) ---")
        if browser_instance:
            browser_instance.close()
            browser_instance = None

if __name__ == "__main__":
    if not llm:
        print("LLM not available. Exiting example execution.")
        exit(1)

    print(f"Number of tools available to agent: {len(all_tools)}")
    asyncio.run(run_agent())
