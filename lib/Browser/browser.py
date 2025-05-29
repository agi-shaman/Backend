import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from llama_index.core.tools import FunctionTool
from typing import List, Dict, Any, Optional
from llama_index.core.agent.workflow import FunctionAgent
from ..rate_limited_gemini import RateLimitedGemini
from dotenv import load_dotenv

load_dotenv()
GeminiKey = os.getenv("GeminiKey")

AGENT_WORKER_LLM_MODEL = "gemini-2.5-flash-preview-05-20"

llm = RateLimitedGemini(
    model=AGENT_WORKER_LLM_MODEL,
    api_key=GeminiKey,
)

# Ensure the screenshots directory exists
SCREENSHOT_DIR = "screenshots"
if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

class BrowserAutomation:
    """
    Handles browser automation using Selenium and Chromium.
    """
    def __init__(self, headless: bool = True):
        """
        Initializes the Chrome WebDriver.

        Args:
            headless (bool): Whether to run the browser in headless mode.
        """
        options = Options()
        if headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080") # Set a default window size

        # Assuming chromedriver is in the system's PATH or specify the path
        # service = Service('/path/to/chromedriver') # Uncomment and specify path if needed
        self.driver = webdriver.Chrome(options=options)
        self.driver.implicitly_wait(10) # Implicit wait

    def _get_element(self, locator_type: str, locator_value: str, timeout: int = 10):
        """
        Finds an element using the specified locator type and value, waiting for it to be present.

        Args:
            locator_type (str): The type of locator (e.g., 'xpath', 'css').
            locator_value (str): The value of the locator.
            timeout (int): The maximum time to wait for the element in seconds.

        Returns:
            WebElement: The found element.

        Raises:
            TimeoutException: If the element is not found within the timeout.
            ValueError: If an invalid locator type is provided.
        """
        by_type = None
        if locator_type.lower() == 'xpath':
            by_type = By.XPATH
        elif locator_type.lower() == 'css':
            by_type = By.CSS_SELECTOR
        # Add more locator types as needed (e.g., 'id', 'name', 'class name')
        # elif locator_type.lower() == 'id':
        #     by_type = By.ID
        # elif locator_type.lower() == 'name':
        #     by_type = By.NAME
        # elif locator_type.lower() == 'class name':
        #     by_type = By.CLASS_NAME
        # elif locator_type.lower() == 'link text':
        #     by_type = By.LINK_TEXT
        # elif locator_type.lower() == 'partial link text':
        #     by_type = By.PARTIAL_LINK_TEXT
        # elif locator_type.lower() == 'tag name':
        #     by_type = By.TAG_NAME

        if by_type is None:
            raise ValueError(f"Invalid locator type: {locator_type}. Supported types: 'xpath', 'css'.")

        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by_type, locator_value))
            )
            return element
        except TimeoutException:
            raise TimeoutException(f"Element not found using {locator_type}='{locator_value}' within {timeout} seconds.")

    def navigate(self, url: str):
        """
        Navigates the browser to a given URL.

        Args:
            url (str): The URL to navigate to.
        """
        print(f"Navigating to {url}")
        self.driver.get(url)
        self.take_screenshot(f"navigate_{int(time.time())}")

    def click(self, locator_type: str, locator_value: str):
        """
        Clicks on an element identified by the locator.

        Args:
            locator_type (str): The type of locator (e.g., 'xpath', 'css').
            locator_value (str): The value of the locator.
        """
        print(f"Attempting to click element with {locator_type}='{locator_value}'")
        element = self._get_element(locator_type, locator_value)
        element.click()
        print("Click successful.")
        self.take_screenshot(f"click_{int(time.time())}")

    def type(self, locator_type: str, locator_value: str, text: str):
        """
        Types text into an element identified by the locator.

        Args:
            locator_type (str): The type of locator (e.g., 'xpath', 'css').
            locator_value (str): The value of the locator.
            text (str): The text to type.
        """
        print(f"Attempting to type into element with {locator_type}='{locator_value}'")
        element = self._get_element(locator_type, locator_value)
        element.clear() # Clear existing text
        element.send_keys(text)
        print("Type successful.")
        self.take_screenshot(f"type_{int(time.time())}")

    def take_screenshot(self, name: str):
        """
        Takes a screenshot of the current browser view.

        Args:
            name (str): The base name for the screenshot file.
        """
        timestamp = int(time.time())
        filename = os.path.join(SCREENSHOT_DIR, f"{name}_{timestamp}.png")
        self.driver.save_screenshot(filename)
        print(f"Screenshot saved to {filename}")

    def close(self):
        """
        Closes the browser.
        """
        print("Closing browser.")
        self.driver.quit()

# Initialize the browser automation instance
# You might want to manage the lifecycle of this instance in your agent
browser_instance = None

def initialize_browser(headless: bool = True):
    """Initializes the global browser instance."""
    global browser_instance
    if browser_instance is None:
        browser_instance = BrowserAutomation(headless=headless)
        print("Browser instance initialized.")
    else:
        print("Browser instance already exists.")

def close_browser():
    """Closes the global browser instance."""
    global browser_instance
    if browser_instance:
        browser_instance.close()
        browser_instance = None
        print("Browser instance closed.")
    else:
        print("No browser instance to close.")

def navigate_tool(url: str):
    """
    Navigates the browser to a given URL.

    Args:
        url (str): The URL to navigate to.
    """
    if browser_instance:
        browser_instance.navigate(url)
        return f"Navigated to {url}"
    else:
        return "Browser not initialized. Call initialize_browser first."

def click_tool(locator_type: str, locator_value: str):
    """
    Clicks on an element in the browser identified by the locator.

    Args:
        locator_type (str): The type of locator (e.g., 'xpath', 'css').
        locator_value (str): The value of the locator.
    """
    if browser_instance:
        try:
            browser_instance.click(locator_type, locator_value)
            return f"Clicked element with {locator_type}='{locator_value}'"
        except (TimeoutException, NoSuchElementException, ValueError) as e:
            return f"Error clicking element: {e}"
    else:
        return "Browser not initialized. Call initialize_browser first."

def type_tool(locator_type: str, locator_value: str, text: str):
    """
    Types text into an element in the browser identified by the locator.

    Args:
        locator_type (str): The type of locator (e.g., 'xpath', 'css').
        locator_value (str): The value of the locator.
        text (str): The text to type.
    """
    if browser_instance:
        try:
            browser_instance.type(locator_type, locator_value, text)
            return f"Typed '{text}' into element with {locator_type}='{locator_value}'"
        except (TimeoutException, NoSuchElementException, ValueError) as e:
            return f"Error typing into element: {e}"
    else:
        return "Browser not initialized. Call initialize_browser first."

# Define LlamaIndex FunctionTools
browser_navigate_tool = FunctionTool.from_defaults(fn=navigate_tool, description="Navigates the browser to a specified URL.")
browser_click_tool = FunctionTool.from_defaults(fn=click_tool, description="Clicks on a web element identified by locator type and value (e.g., xpath, css).")
browser_type_tool = FunctionTool.from_defaults(fn=type_tool, description="Types text into a web element identified by locator type and value (e.g., xpath, css).")

# Example usage (for testing purposes, typically used by an agent)
if __name__ == "__main__":
    initialize_browser(headless=False) # Set to False to see the browser
    try:
        tools = []
        worker = FunctionAgent(
            tools=tools,
            llm=llm,)
        worker.run(user_msg="Find me the best rated pizza place in NYC")
    finally:
        close_browser()
