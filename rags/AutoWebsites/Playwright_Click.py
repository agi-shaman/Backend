import re
import subprocess
import tempfile
import os
import asyncio
from pathlib import Path
import sys

# --- Configuration ---
GENERATED_SCRIPT_FILENAME = "_temp_playwright_script.py"
SCREENSHOT_AFTER_ACTION = "action_screenshot.png"
ACTION_TIMEOUT_MS = 15000
NAVIGATION_TIMEOUT_MS = 30000

# --- "AI" (Gemini Model Simulation) ---
def generate_playwright_script_from_prompt(url: str, user_prompt: str) -> str | None:
    print(f"🤖 AI: Analyzing prompt: '{user_prompt}' for URL: '{url}'")
    script_lines = [
        "import asyncio",
        "from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError",
        "import re",
        "import sys",
        "",
        f"URL = '{url}'",
        f"SCREENSHOT_PATH = '{SCREENSHOT_AFTER_ACTION}'",
        f"ACTION_TIMEOUT = {ACTION_TIMEOUT_MS}",
        f"NAVIGATION_TIMEOUT = {NAVIGATION_TIMEOUT_MS}",
        "",
        "async def perform_action():",
        "    async with async_playwright() as p:",
        "        browser = None",
        "        context = None", # Initialize context
        "        try:",
        "            browser_type_to_try = p.chromium",
        "            print(f'Attempting to launch {{browser_type_to_try.name}}...')",
        "            browser = await browser_type_to_try.launch(headless=False, slow_mo=500)",
        "            print(f'{{browser_type_to_try.name}} launched successfully.')",
        "        except Exception as e_launch:",
        "            print(f'Error launching preferred browser {{browser_type_to_try.name}}: {{e_launch}}')",
        "            print('This often means the browser binaries are missing or mismatched with the Playwright library.')",
        "            print('Please ensure you have run: playwright install --with-deps {{browser_type_to_try.name}}')",
        "            if 'Executable doesnt exist' in str(e_launch) or \"Executable doesn't exist\" in str(e_launch):",
        "                 print('Exiting due to missing browser executable.')",
        "                 sys.exit(1)",
        "",
        "        if not browser:",
        "            print('Failed to launch any browser. Cannot continue.')",
        "            return",
        "",
        "        context = await browser.new_context(no_viewport=True)",
        "        page = await context.new_page()",
        "        page.set_default_timeout(ACTION_TIMEOUT)",
        "        print(f'Navigating to {URL}...')",
        "        try:",
        "            await page.goto(URL, timeout=NAVIGATION_TIMEOUT, wait_until='domcontentloaded')",
        "            print('Navigation complete.')",
        "        except PlaywrightTimeoutError:",
        "            print(f'Timeout navigating to {URL}. Proceeding with caution.')",
        "        except Exception as e_goto:",
        "            print(f'Error navigating to {URL}: {e_goto}')",
        "            if context: await context.close()", # Close context
        "            if browser: await browser.close()",
        "            return",
        "",
        "        # --- Attempt to handle Google Consent/Pop-ups ---",
        "        if 'google.com' in URL:",
        "            print('Checking for Google consent/pop-ups...')",
        "            try:",
        "                consent_buttons_data = [", # Store text too for better matching
        "                    {'role': 'button', 'name_regex': r'Accept all|I agree|Alles accepteren|Ich stimme zu|Tout accepter|Accetta tutto', 'priority': 1},",
        "                    {'role': 'button', 'name_regex': r'Reject all|Alles ablehnen|Tout refuser|Rifiuta tutto', 'priority': 2},",
        "                    {'role': 'button', 'name_regex': r'Customize|Anpassen|Personalizar|Personnaliser', 'priority': 3}",
        "                ]",
        "                clicked_consent = False",
        "                for _ in range(2):", # Try for a couple of seconds
        "                    for btn_data in sorted(consent_buttons_data, key=lambda x: x['priority']):", # Try priority buttons first
        "                        try:",
        "                            button_to_click = page.get_by_role(btn_data['role'], name=re.compile(btn_data['name_regex'], re.IGNORECASE)).first",
        "                            if await button_to_click.is_visible(timeout=500):",
        "                                btn_text_content = (await button_to_click.text_content() or '').strip()",
        "                                print(f'  Found potential consent button: \"{btn_text_content}\"')",
        "                                if btn_data['priority'] == 1: # If it's an accept type button",
        "                                    await button_to_click.click(timeout=2000)",
        "                                    print(f'Clicked consent button: \"{btn_text_content}\".')",
        "                                    await page.wait_for_timeout(1000)",
        "                                    clicked_consent = True",
        "                                    break", # Exit inner loop (btn_data)
        "                        except PlaywrightTimeoutError: pass",
        "                        except Exception as e_consent_btn: print(f'  Minor error checking consent button: {{e_consent_btn}}')",
        "                    if clicked_consent: break", # Exit outer loop (_)
        "                    if not clicked_consent: await page.wait_for_timeout(500)",
        "",
        "                if not clicked_consent:",
        "                    print('No obvious consent button clicked or found quickly. Proceeding...')",
        "            except Exception as e_consent_handling:",
        "                print(f'Error during consent handling: {{e_consent_handling}}. Proceeding anyway.')",
        "        # --- End of Consent Handling ---",
        "        print('Pausing briefly after consent check/navigation...')", # NEW
        "        await page.wait_for_timeout(1000) # NEW: Wait 1 second for page to settle",
        "",
        "        # --- Action Parsing and Code Generation ---",
    ]

    prompt_lower = user_prompt.lower()
    action_generated = False

    # 1. Handle "click" or "press" actions
    click_match = re.search(r"(click|press|tap)\s*(?:on|the)?\s*(.+)", prompt_lower)
    if click_match:
        target_description_from_prompt = click_match.group(2).strip()
        script_lines.append(f"        # Original target description from prompt: \"{target_description_from_prompt}\"")
        script_lines.append(f"        print(f'Attempting to click on: \"{target_description_from_prompt}\"')")
        locator_code = ""
        if "button" in target_description_from_prompt:
            btn_name_match = re.search(r"(?:button)?\s*['\"]([^'\"]+)['\"]|(\w+)\s+button", target_description_from_prompt)
            if btn_name_match:
                btn_name = btn_name_match.group(1) or btn_name_match.group(2)
                locator_code = f"page.get_by_role('button', name=re.compile(r'{re.escape(btn_name)}', re.IGNORECASE)).first"
            else:
                text_for_button = target_description_from_prompt.replace("button", "").strip()
                locator_code = f"page.get_by_role('button').filter(has_text=re.compile(r'{re.escape(text_for_button)}', re.IGNORECASE)).first"
        elif "link" in target_description_from_prompt:
            link_name_match = re.search(r"(?:link)?\s*['\"]([^'\"]+)['\"]", target_description_from_prompt)
            if link_name_match:
                link_name = link_name_match.group(1)
                locator_code = f"page.get_by_role('link', name=re.compile(r'{re.escape(link_name)}', re.IGNORECASE)).first"
            else:
                text_for_link = target_description_from_prompt.replace("link", "").strip()
                locator_code = f"page.get_by_role('link').filter(has_text=re.compile(r'{re.escape(text_for_link)}', re.IGNORECASE)).first"
        elif ("search bar" in target_description_from_prompt or "search input" in target_description_from_prompt) and 'google.com' in URL:
             script_lines.append(f"        print('Using Google-specific search bar selectors for CLICK.')")
             locator_code = f"page.locator('[name=\"q\"], [aria-label*=\"Search\"i], [aria-label*=\"Cerca\"i], [aria-label*=\"Buscar\"i], [aria-label*=\"Rechercher\"i], textarea[title*=\"Search\"i], input[title*=\"Search\"i]).first"
        elif "search bar" in target_description_from_prompt or "search input" in target_description_from_prompt:
            script_lines.append(f"        print('Using generic search bar selectors for CLICK.')")
            locator_code = f"page.locator('input[name*=\"q\" i], input[name*=\"search\" i], input[type=\"search\" i], [aria-label*=\"search\" i]').first"
        else:
            locator_code = f"page.get_by_text(re.compile(r'{re.escape(target_description_from_prompt)}', re.IGNORECASE), exact=False).first"

        script_lines.append(f"        target_element = {locator_code}")
        script_lines.extend([
            "        try:",
            "            await target_element.wait_for(state='visible', timeout=ACTION_TIMEOUT//2)", # Increased timeout
            "            await target_element.click(timeout=ACTION_TIMEOUT//2)",
            "            print('Click action performed.')",
            "            await page.wait_for_load_state('domcontentloaded', timeout=5000)",
            "        except PlaywrightTimeoutError as e_timeout_click:",
            f"            print(f'Timeout trying to click or find visible element for: \"{target_description_from_prompt}\". Error: {{e_timeout_click}}')",
            "        except Exception as e_click:",
            f"            print(f'Error clicking \"{target_description_from_prompt}\": {{e_click}}')",
        ])
        action_generated = True


    # 2. Handle "write", "type", or "fill" actions
    fill_match = re.search(r"(write|type|fill)\s+['\"]([^'\"]+)['\"]\s*(?:in|into|on)?\s*(.+)", prompt_lower)
    if not action_generated and fill_match:
        text_to_fill = fill_match.group(2)
        target_description_from_prompt = fill_match.group(3).strip()
        script_lines.append(f"        # Original target description from prompt: \"{target_description_from_prompt}\"")
        script_lines.append(f"        print(f'Attempting to fill \"{target_description_from_prompt}\" with \"{text_to_fill}\"')")

        locator_code_var_name = "target_element_for_fill"
        locator_code_definition = ""

        if ("search bar" in target_description_from_prompt or "search input" in target_description_from_prompt) and 'google.com' in url:
            script_lines.append(f"        print('Using Google-specific search bar selectors for FILL.')") # Debug
            # Common Google search inputs: name="q", or aria-label containing "Search" (localized)
            # Also textarea with title "Search" is common.
            locator_code_definition = f"page.locator('[name=\"q\"], [aria-label*=\"Search\"i], [aria-label*=\"Cerca\"i], [aria-label*=\"Buscar\"i], [aria-label*=\"Rechercher\"i], textarea[title*=\"Search\"i], input[title*=\"Search\"i]).first"
        elif "search bar" in target_description_from_prompt or "search input" in target_description_from_prompt:
             script_lines.append(f"        print('Using generic search bar selectors for FILL.')") # Debug
             locator_code_definition = f"page.locator('input[name*=\"q\" i], input[name*=\"search\" i], input[type=\"search\" i], [aria-label*=\"search\" i]').first"
        elif "field labeled" in target_description_from_prompt or "input labeled" in target_description_from_prompt:
            label_match = re.search(r"labeled\s+['\"]([^'\"]+)['\"]", target_description_from_prompt)
            if label_match:
                label_text = label_match.group(1)
                locator_code_definition = f"page.get_by_label(re.compile(r'{re.escape(label_text)}', re.IGNORECASE)).first"
            else:
                clean_desc = target_description_from_prompt.replace('field labeled','').replace('input labeled','').strip()
                locator_code_definition = f"page.locator('input, textarea').filter(has_text=re.compile(r'{re.escape(clean_desc)}', re.IGNORECASE)).first"
        else:
            keywords = target_description_from_prompt.replace("field", "").replace("input", "").replace("area", "").replace("box", "").strip().split()
            main_keyword = re.escape(keywords[-1] if keywords else target_description_from_prompt)
            script_lines.append(f"        # Using multi-selector approach for: \"{target_description_from_prompt}\" with keyword '{main_keyword}'")
            script_lines.append(f"        {locator_code_var_name} = None")
            script_lines.append(f"        possible_selectors = [")
            script_lines.append(f"            f'[aria-label*=\"{main_keyword}\" i]',")
            script_lines.append(f"            f'input[name*=\"{main_keyword}\" i]',")
            script_lines.append(f"            f'textarea[name*=\"{main_keyword}\" i]',")
            script_lines.append(f"            f'input[placeholder*=\"{main_keyword}\" i]',")
            script_lines.append(f"            f'textarea[placeholder*=\"{main_keyword}\" i]',")
            script_lines.append(f"            'input[type=\"text\"]:visible', 'input[type=\"email\"]:visible', 'input[type=\"search\"]:visible', 'textarea:visible'")
            script_lines.append(f"        ]")
            script_lines.append(f"        for sel_idx, sel_val in enumerate(possible_selectors):")
            script_lines.append(f"            try:")
            script_lines.append(f"                # print(f'  Trying selector {{sel_idx + 1}}: {{sel_val}}')")
            script_lines.append(f"                el = page.locator(sel_val).first")
            script_lines.append(f"                await el.wait_for(state='attached', timeout=500)")
            script_lines.append(f"                if await el.is_editable(timeout=500):")
            script_lines.append(f"                    {locator_code_var_name} = el")
            script_lines.append(f"                    print(f'  Found suitable editable element with selector: {{sel_val}}')")
            script_lines.append(f"                    break")
            script_lines.append(f"            except PlaywrightTimeoutError: pass")
            script_lines.append(f"            except Exception: pass")
            locator_code_definition = ""

        if locator_code_definition:
             script_lines.append(f"        {locator_code_var_name} = {locator_code_definition}")

        script_lines.extend([
            "        try:",
            f"            if {locator_code_var_name}:",
            f"                print(f'  Waiting for element {{ {locator_code_var_name} }} to be editable...')",
            f"                await {locator_code_var_name}.wait_for(state='editable', timeout=ACTION_TIMEOUT//2)",
            f"                print(f'  Element is editable. Filling with text: \"{text_to_fill}\"')",
            f"                await {locator_code_var_name}.fill('{text_to_fill}', timeout=ACTION_TIMEOUT//2)",
            "                print('Fill action performed.')",
            f"                if 'search' in \"{target_description_from_prompt}\" or 'submit' in {repr(user_prompt.lower())} or 'enter' in {repr(user_prompt.lower())}:",
            "                    print('Pressing Enter...')",
            f"                    await {locator_code_var_name}.press('Enter')",
            "                    await page.wait_for_load_state('domcontentloaded', timeout=5000)",
            f"            elif {locator_code_var_name} is not None:",
            f"                print(f'Element for \"{target_description_from_prompt}\" found but not editable.')",
            "            else:",
            f"                print(f'Could not find a suitable editable element for \"{target_description_from_prompt}\".')",
            "        except PlaywrightTimeoutError as e_timeout_fill:",
            f"            print(f'Timeout trying to fill or find/wait for editable element for: \"{target_description_from_prompt}\". Error: {{e_timeout_fill}}')",
            "        except Exception as e_fill:",
            f"            print(f'Error filling \"{target_description_from_prompt}\": {{e_fill}}')",
        ])
        action_generated = True

    if not action_generated:
        script_lines.append("        print('AI could not determine a specific action from the prompt.')")

    script_lines.extend([
        "",
        "        print(f'Taking a screenshot: {SCREENSHOT_PATH}')",
        "        try:",
        "            await page.screenshot(path=SCREENSHOT_PATH, full_page=True)",
        "            print(f'Screenshot saved to {SCREENSHOT_PATH}')",
        "        except Exception as e_ss:",
        "            print(f'Could not take screenshot: {e_ss}')",
        "        print('Waiting a few seconds before closing...')",
        "        await asyncio.sleep(3)",
        "        if context: await context.close()",
        "        if browser: await browser.close()",
        "        print('Browser closed.')",
        "",
        "if __name__ == '__main__':",
        "    asyncio.run(perform_action())"
    ])

    final_script = "\n".join(script_lines)
    print("🤖 AI: Generated Playwright script.")
    return final_script

# --- Script Execution ---
def execute_generated_playwright_script(script_content: str, script_filename: str) -> bool:
    script_file_path = Path(script_filename)
    try:
        script_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(script_file_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        print(f"\n▶️ Executing generated Playwright script: {script_file_path.resolve()}")

        python_executable = sys.executable
        process = subprocess.run(
            [python_executable, str(script_file_path)],
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace"
        )

        print("\n--- Script Output ---")
        if process.stdout:
            print(process.stdout.strip())
        if process.stderr:
            print("--- Script Errors (if any) ---")
            print(process.stderr.strip())
        print("--- End of Script Output ---")

        if process.returncode == 0:
            print(f"✅ Generated script executed successfully.")
            if Path(SCREENSHOT_AFTER_ACTION).exists():
                 print(f"📷 Screenshot (if action was successful) should be at: {Path(SCREENSHOT_AFTER_ACTION).resolve()}")
            return True
        else:
            print(f"❌ Generated script failed with exit code {process.returncode}.")
            if "Executable doesnt exist" in process.stderr or "Executable doesn't exist" in process.stderr :
                print("\n❗❗❗ ERROR: Playwright browser executable not found or version mismatch! ❗❗❗")
                pip_path = Path(sys.executable).parent / 'pip'
                playwright_cli_path = Path(sys.executable).parent / 'playwright'
                print("This usually means Playwright browsers are not installed correctly for the current Playwright library.")
                print("Please run the following commands in your terminal and then try again:")
                print(f"   1. {pip_path} install playwright --upgrade")
                print(f"   2. {playwright_cli_path} install --with-deps chromium")
            return False

    except Exception as e:
        print(f"An error occurred while trying to execute the script: {e}")
        return False
    finally:
        if script_file_path.exists():
            try:
                os.remove(script_file_path)
            except Exception as e_del:
                print(f"Warning: Could not remove temporary script {script_file_path.name}: {e_del}")

# --- Main Application ---
if __name__ == "__main__":
    print("--- Playwright AI Task Executor (Simulated) ---")
    pip_path = Path(sys.executable).parent / 'pip'
    playwright_cli_path = Path(sys.executable).parent / 'playwright'
    print("IMPORTANT: Ensure Playwright is correctly installed with its browsers.")
    print("If you encounter browser launch errors, run in your terminal (ensure venv is active):")
    print(f"  {pip_path} install playwright --upgrade")
    print(f"  {playwright_cli_path} install --with-deps chromium (or just 'playwright install --with-deps')")
    print("-" * 50)

    target_url = input("Enter the URL (e.g., https://www.google.com): ").strip()
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = "https://" + target_url

    action_prompt = input("Enter the single action to perform (e.g., 'press the search button', 'write \"hello world\" in the search bar'): ").strip()

    if not target_url or not action_prompt:
        print("URL and action prompt are required. Exiting.")
    else:
        generated_script = generate_playwright_script_from_prompt(target_url, action_prompt)

        if generated_script:
            print(f"\n🤖 AI has generated a Playwright script. Preview (first 50 lines):") # Increased preview
            for i, line in enumerate(generated_script.splitlines()):
                if i < 50: print(line)
                elif i == 50: print("...")
            print(f"(Full script will be saved to {Path(GENERATED_SCRIPT_FILENAME).resolve()} temporarily before execution)")

            if input("Proceed with executing this script? (yes/no): ").strip().lower() == 'yes':
                execute_generated_playwright_script(generated_script, GENERATED_SCRIPT_FILENAME)
            else:
                print("Execution cancelled by user.")
        else:
            print("Could not generate a script for the given prompt.")
