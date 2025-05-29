import re
import subprocess
import tempfile
import os
import asyncio # Required if the generated script uses async Playwright
from pathlib import Path

# --- Configuration ---
GENERATED_SCRIPT_FILENAME = "_temp_playwright_script.py"
SCREENSHOT_AFTER_ACTION = "action_screenshot.png"
ACTION_TIMEOUT_MS = 10000  # Timeout for Playwright actions in milliseconds
NAVIGATION_TIMEOUT_MS = 30000 # Timeout for page navigation

# --- "AI" (Gemini Model Simulation) ---
def generate_playwright_script_from_prompt(url: str, user_prompt: str) -> str | None:
    """
    Simulates an AI (like Gemini) to generate a Playwright Python script
    based on a URL and a single action prompt.

    Returns:
        A string containing the Playwright Python script, or None if parsing fails.
    """
    print(f"🤖 AI: Analyzing prompt: '{user_prompt}' for URL: '{url}'")
    script_lines = [
        "import asyncio",
        "from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError",
        "import re # For potential regex in locators",
        "",
        f"URL = '{url}'",
        f"SCREENSHOT_PATH = '{SCREENSHOT_AFTER_ACTION}'",
        f"ACTION_TIMEOUT = {ACTION_TIMEOUT_MS}",
        f"NAVIGATION_TIMEOUT = {NAVIGATION_TIMEOUT_MS}",
        "",
        "async def perform_action():",
        "    async with async_playwright() as p:",
        "        # browser = await p.chromium.launch(headless=False, slow_mo=500)",
        "        # Try to launch with a preferred browser, fallback if needed",
        "        browser_type_to_try = p.chromium # or p.firefox or p.webkit",
        "        try:",
        "            browser = await browser_type_to_try.launch(headless=False, slow_mo=500)",
        "        except Exception as e:",
        "            print(f'Error launching preferred browser: {{e}}. Trying default.')",
        "            browser = await p.chromium.launch(headless=False, slow_mo=500) # Fallback",
        "",
        "        page = await browser.new_page()",
        "        page.set_default_timeout(ACTION_TIMEOUT)", # Default timeout for actions
        "        print(f'Navigating to {URL}...')",
        "        try:",
        "            await page.goto(URL, timeout=NAVIGATION_TIMEOUT, wait_until='domcontentloaded')",
        "            print('Navigation complete.')",
        "        except PlaywrightTimeoutError:",
        "            print(f'Timeout navigating to {URL}. Proceeding with caution.')",
        "        except Exception as e:",
        "            print(f'Error navigating to {URL}: {e}')",
        "            await browser.close()",
        "            return",
        "",
        "        # --- Action Parsing and Code Generation ---",
    ]

    prompt_lower = user_prompt.lower()
    action_generated = False

    # 1. Handle "click" or "press" actions
    # Example: "press the search button", "click on the link 'About Us'", "click the element with id 'submit-btn'"
    click_match = re.search(r"(click|press|tap)\s*(?:on|the)?\s*(.+)", prompt_lower)
    if click_match:
        target_description = click_match.group(2).strip()
        script_lines.append(f"        print(f'Attempting to click on: \"{target_description}\"')")

        # Try to be more specific with Playwright locators
        if "button" in target_description:
            # "button 'Search'" or "search button"
            btn_name_match = re.search(r"(?:button)?\s*['\"]([^'\"]+)['\"]|(\w+)\s+button", target_description)
            if btn_name_match:
                btn_name = btn_name_match.group(1) or btn_name_match.group(2)
                script_lines.append(f"        # Using get_by_role for button: '{btn_name}'")
                script_lines.append(f"        target_element = page.get_by_role('button', name=re.compile(r'{re.escape(btn_name)}', re.IGNORECASE)).first")
            else: # Generic button
                script_lines.append(f"        # Using generic role 'button' selector")
                script_lines.append(f"        target_element = page.get_by_role('button').filter(has_text=re.compile(r'{re.escape(target_description)}', re.IGNORECASE)).first")
        elif "link" in target_description:
            link_name_match = re.search(r"(?:link)?\s*['\"]([^'\"]+)['\"]", target_description)
            if link_name_match:
                link_name = link_name_match.group(1)
                script_lines.append(f"        # Using get_by_role for link: '{link_name}'")
                script_lines.append(f"        target_element = page.get_by_role('link', name=re.compile(r'{re.escape(link_name)}', re.IGNORECASE)).first")
            else:
                script_lines.append(f"        target_element = page.get_by_role('link').filter(has_text=re.compile(r'{re.escape(target_description)}', re.IGNORECASE)).first")
        elif "search bar" in target_description or "search input" in target_description:
            script_lines.append(f"        # Trying common selectors for a search bar/input")
            script_lines.append(f"        target_element = page.locator('input[name*=\"q\" i], input[name*=\"search\" i], input[type=\"search\" i], [aria-label*=\"search\" i]').first")
        else: # Generic fallback using text or a more general locator
            script_lines.append(f"        # Using a general text-based locator or placeholder for: \"{target_description}\"")
            script_lines.append(f"        # Consider get_by_text, get_by_label, or a CSS/XPath locator if this fails.")
            script_lines.append(f"        target_element = page.get_by_text(re.compile(r'{re.escape(target_description)}', re.IGNORECASE), exact=False).first")
            # A more robust AI would try multiple selector strategies here.

        script_lines.extend([
            "        try:",
            "            if await target_element.is_visible(timeout=5000):", # Check visibility briefly
            "                await target_element.click(timeout=ACTION_TIMEOUT)",
            "                print('Click action performed.')",
            "                await page.wait_for_load_state('domcontentloaded', timeout=5000) # Brief wait for potential navigation",
            "            else:",
            "                print(f'Element for \"{target_description}\" found but not visible.')",
            "        except PlaywrightTimeoutError:",
            "            print(f'Timeout trying to click or find visible element for: \"{target_description}\"')",
            "        except Exception as e_click:",
            "            print(f'Error clicking \"{target_description}\": {{e_click}}')",
        ])
        action_generated = True

    # 2. Handle "write", "type", or "fill" actions
    # Example: "write 'test@example.com' into the email field", "type 'password123' in the password input"
    fill_match = re.search(r"(write|type|fill)\s+['\"]([^'\"]+)['\"]\s*(?:in|into|on)?\s*(.+)", prompt_lower)
    if not action_generated and fill_match: # Process only if click wasn't processed
        text_to_fill = fill_match.group(2)
        target_description = fill_match.group(3).strip()
        script_lines.append(f"        print(f'Attempting to fill \"{target_description}\" with \"{text_to_fill}\"')")

        if "search bar" in target_description or "search input" in target_description:
            script_lines.append(f"        # Trying common selectors for a search bar/input")
            script_lines.append(f"        target_element = page.locator('input[name*=\"q\" i], input[name*=\"search\" i], input[type=\"search\" i], [aria-label*=\"search\" i]').first")
        elif "field labeled" in target_description or "input labeled" in target_description:
            label_match = re.search(r"labeled\s+['\"]([^'\"]+)['\"]", target_description)
            if label_match:
                label_text = label_match.group(1)
                script_lines.append(f"        target_element = page.get_by_label(re.compile(r'{re.escape(label_text)}', re.IGNORECASE)).first")
            else: # Fallback
                script_lines.append(f"        target_element = page.locator('input, textarea').filter(has_text=re.compile(r'{re.escape(target_description.replace('field','').replace('input','').strip())}', re.IGNORECASE)).first")
        else: # Generic input/textarea
            script_lines.append(f"        # Using a general locator for input/textarea based on description: \"{target_description}\"")
            script_lines.append(f"        # Consider get_by_placeholder, or more specific CSS/XPath.")
            # Try to find an input or textarea that might match the description
            script_lines.append(f"        possible_selectors = [")
            script_lines.append(f"            f'input[placeholder*=\"{target_description}\" i]',")
            script_lines.append(f"            f'textarea[placeholder*=\"{target_description}\" i]',")
            script_lines.append(f"            f'input[name*=\"{target_description.split()[-1] if target_description.split() else ''}\" i]',") # last word as potential name
            script_lines.append(f"            f'textarea[name*=\"{target_description.split()[-1] if target_description.split() else ''}\" i]',")
            script_lines.append(f"            'input[type=\"text\"]:visible', 'textarea:visible'") # General visible inputs
            script_lines.append(f"        ]")
            script_lines.append(f"        target_element = None")
            script_lines.append(f"        for sel in possible_selectors:")
            script_lines.append(f"            try:")
            script_lines.append(f"                el = page.locator(sel).first")
            script_lines.append(f"                if await el.is_visible(timeout=1000) and await el.is_editable(timeout=1000):")
            script_lines.append(f"                    target_element = el")
            script_lines.append(f"                    print(f'  Found suitable element with selector: {{sel}}')")
            script_lines.append(f"                    break")
            script_lines.append(f"            except: pass")


        script_lines.extend([
            "        try:",
            "            if target_element and await target_element.is_editable(timeout=5000):",
            f"                await target_element.fill('{text_to_fill}', timeout=ACTION_TIMEOUT)",
            "                print('Fill action performed.')",
            "                # Optional: Press Enter if it's a search-like action",
            f"                if 'search' in \"{target_description}\" or 'submit' in \"{user_prompt.lower()}\":", # Check original prompt too
            "                    print('Pressing Enter...')",
            "                    await target_element.press('Enter')",
            "                    await page.wait_for_load_state('domcontentloaded', timeout=5000) # Brief wait",
            "            elif target_element:",
            "                print(f'Element for \"{target_description}\" found but not editable.')",
            "            else:",
            "                print(f'Could not find a suitable editable element for \"{target_description}\".')",
            "        except PlaywrightTimeoutError:",
            "            print(f'Timeout trying to fill or find editable element for: \"{target_description}\"')",
            "        except Exception as e_fill:",
            "            print(f'Error filling \"{target_description}\": {{e_fill}}')",
        ])
        action_generated = True

    if not action_generated:
        print("🤖 AI: Could not understand the action or find a suitable way to perform it from the prompt.")
        script_lines.append("        print('AI could not determine a specific action from the prompt.')")


    # --- End of Action ---
    script_lines.extend([
        "",
        "        print(f'Taking a screenshot: {SCREENSHOT_PATH}')",
        "        await page.screenshot(path=SCREENSHOT_PATH, full_page=True)",
        "        print('Waiting a few seconds before closing...')",
        "        await asyncio.sleep(3) # Keep browser open for a moment",
        "        await browser.close()",
        "        print('Browser closed.')",
        "",
        "if __name__ == '__main__':",
        "    asyncio.run(perform_action())"
    ])

    final_script = "\n".join(script_lines)
    print("🤖 AI: Generated Playwright script.")
    # print("-" * 30 + " Generated Script " + "-" * 30)
    # print(final_script)
    # print("-" * (60 + len(" Generated Script ")))
    return final_script

# --- Script Execution ---
def execute_generated_playwright_script(script_content: str, script_filename: str) -> bool:
    """
    Saves the script content to a file and executes it using subprocess.
    """
    script_file_path = Path(script_filename)
    try:
        with open(script_file_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        print(f"\n▶️ Executing generated Playwright script: {script_file_path.name}...")

        # Ensure Python executable can be found, especially in virtual environments
        python_executable = "python" # Or sys.executable
        process = subprocess.run(
            [python_executable, str(script_file_path)],
            capture_output=True,
            text=True,
            check=False, # Don't raise exception for non-zero exit codes immediately
            encoding="utf-8"
        )

        print("\n--- Script Output ---")
        if process.stdout:
            print(process.stdout)
        if process.stderr:
            print("--- Script Errors (if any) ---")
            print(process.stderr)
        print("--- End of Script Output ---")

        if process.returncode == 0:
            print(f"✅ Generated script executed successfully.")
            print(f"📷 Screenshot (if action was successful) should be at: {SCREENSHOT_AFTER_ACTION}")
            return True
        else:
            print(f"❌ Generated script failed with exit code {process.returncode}.")
            return False

    except Exception as e:
        print(f"An error occurred while trying to execute the script: {e}")
        return False
    finally:
        # Clean up the temporary script file
        if script_file_path.exists():
            try:
                os.remove(script_file_path)
                # print(f"Temporary script {script_file_path.name} removed.")
            except Exception as e_del:
                print(f"Warning: Could not remove temporary script {script_file_path.name}: {e_del}")

# --- Main Application ---
if __name__ == "__main__":
    print("--- Playwright AI Task Executor (Simulated) ---")
    target_url = input("Enter the URL (e.g., https://www.google.com): ").strip()
    if not target_url.startswith("http"):
        target_url = "https://" + target_url

    action_prompt = input("Enter the single action to perform (e.g., 'press the search button', 'write \"hello world\" in the search bar'): ").strip()

    if not target_url or not action_prompt:
        print("URL and action prompt are required. Exiting.")
    else:
        generated_script = generate_playwright_script_from_prompt(target_url, action_prompt)

        if generated_script:
            print(f"\n🤖 AI has generated a Playwright script. Preview (first 20 lines):")
            for i, line in enumerate(generated_script.splitlines()):
                if i < 20: print(line)
                elif i == 20: print("...")
            print(f"(Full script will be saved to {GENERATED_SCRIPT_FILENAME} temporarily before execution)")

            if input("Proceed with executing this script? (yes/no): ").lower() == 'yes':
                execute_generated_playwright_script(generated_script, GENERATED_SCRIPT_FILENAME)
            else:
                print("Execution cancelled by user.")
        else:
            print("Could not generate a script for the given prompt.")
