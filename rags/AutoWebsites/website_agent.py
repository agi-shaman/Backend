from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager # For Chrome
# from webdriver_manager.firefox import GeckoDriverManager # For Firefox
# from selenium.webdriver.firefox.service import Service as FirefoxService # For Firefox

import time # To allow page to load (optional, but good practice)

# --- Configuration ---
URL_TO_OPEN = "https://www.google.com"
SCREENSHOT_FILENAME = "google_homepage_screenshot.png"
BROWSER_WAIT_TIME = 3 # Seconds to wait for page to potentially load more content

# --- Initialize WebDriver ---
# For Chrome
driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))

# For Firefox (uncomment if you want to use Firefox)
# driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()))

print(f"Opening {URL_TO_OPEN}...")

try:
    # 1. Open the URL
    driver.get(URL_TO_OPEN)

    # Optional: Maximize the browser window for a fuller screenshot
    driver.maximize_window()

    # Optional: Wait for a few seconds to ensure the page is fully loaded
    # For more complex pages, you'd use explicit waits (e.g., WebDriverWait)
    print(f"Waiting for {BROWSER_WAIT_TIME} seconds for page to load...")
    time.sleep(BROWSER_WAIT_TIME)

    # 2. Take a screenshot
    success = driver.save_screenshot(SCREENSHOT_FILENAME)

    if success:
        print(f"Screenshot saved as {SCREENSHOT_FILENAME}")
    else:
        print(f"Failed to save screenshot as {SCREENSHOT_FILENAME}")

except Exception as e:
    print(f"An error occurred: {e}")

finally:
    # 3. Close the browser
    # driver.close() # Closes the current tab
    if 'driver' in locals() and driver: # Check if driver was initialized
        driver.quit() # Closes the entire browser window and quits the driver
        print("Browser closed.")
