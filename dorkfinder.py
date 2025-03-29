import platform
import argparse
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import random
import os
import sys
from datetime import datetime
import undetected_chromedriver as uc
uc.Chrome.__del__ = lambda self: None
import json
from utils import minimize_chrome_window, minimize_chrome_macos, minimize_chrome_linux, find_chrome_binary

# === CLI ARGUMENTS ===
class SilentArgumentParser(argparse.ArgumentParser):
    def print_banner(self):
        banner = r"""
██████╗  ██████╗ ██████╗ ██╗  ██╗███████╗██╗███╗   ██╗██████╗ ███████╗██████╗ 
██╔══██╗██╔═══██╗██╔══██╗██║ ██╔╝██╔════╝██║████╗  ██║██╔══██╗██╔════╝██╔══██╗
██║  ██║██║   ██║██████╔╝█████╔╝ █████╗  ██║██╔██╗ ██║██║  ██║█████╗  ██████╔╝
██║  ██║██║   ██║██╔══██╗██╔═██╗ ██╔══╝  ██║██║╚██╗██║██║  ██║██╔══╝  ██╔══██╗
██████╔╝╚██████╔╝██║  ██║██║  ██╗██║     ██║██║ ╚████║██████╔╝███████╗██║  ██║
╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═══╝╚═════╝ ╚══════╝╚═╝  ╚═╝
                            Basic dorkfinder by @mcn1k
"""
        print(banner)

    def error(self, message):
        self.print_banner()
        print(f"\n[!] {message}")
        print("[!] Missing required arguments. Use -h for help.\n")
        self.exit(2)

    def print_help(self):
        self.print_banner()
        super().print_help()

parser = SilentArgumentParser(
    description='Headless DorkFinder by @mcn1k',
    usage='dorkfinder.py -t example.com [-o] [--engine {brave,bing,ddg,google}] [--multi-engine] [--debug] [--sleep 60] [--silent]'
)
parser.add_argument('-t', metavar='example.com', help='Target domain (or comma-separated list)', dest='target', type=str, required=True)
parser.add_argument('-o', action='store_true', help='Write output to a timestamped file', dest='output')
parser.add_argument('--engine', choices=['brave', 'bing', 'ddg', 'google'], default='google', help='Search engine to use. Default: Google Chrome')
parser.add_argument('--multi-engine', action='store_true', help='Use all search engines', dest='multi_engine')
parser.add_argument('--debug', action='store_true', help='Enable debug output (page source snippet)', dest='debug')
parser.add_argument('--sleep', type=int, default=60, help='Sleep time between requests (in seconds)', dest='tsleep')
parser.add_argument('--silent', action='store_true', default=False, help='Keeps everything nice and quiet', dest='silent')

args = parser.parse_args()
targets = [t.strip() for t in args.target.split(',') if t.strip()]

# silent function
def log(msg, **kwargs):
    if not args.silent:
        print(msg, **kwargs)

# === Search Engine Map ===
SEARCH_ENGINES = {
    'brave': "https://search.brave.com/search?q=",
    'bing': "https://www.bing.com/search?q=",
    'ddg': "https://duckduckgo.com/?q=",
    'google': "https://www.google.com/search?q=",
}

# Use all engines if multi-engine is enabled, otherwise just selected one
ENABLED_ENGINES = list(SEARCH_ENGINES.keys()) if args.multi_engine else [args.engine]

# === Load Queries from File ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
queries_path = os.path.join(SCRIPT_DIR, 'queries.txt')

with open(queries_path, 'r', encoding='utf-8') as f:
    RAW_QUERIES = [
        line.strip() for line in f
        if line.strip() and not line.strip().startswith('#')
    ]
    
# === Set up browser with real profile ===
options = uc.ChromeOptions()

if platform.system() == 'Darwin':  # macOS
    user_profile_path = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default")
    options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
elif platform.system() == 'Linux': # Linux
    user_profile_path = os.path.expanduser("~/.config/google-chrome/Default")
    options.binary_location = "/usr/bin/google-chrome"
else:  # Windows
    username = os.getlogin()
    user_profile_path = os.path.join(
    os.environ['LOCALAPPDATA'],
    "Google\\Chrome\\User Data"
)
    options.binary_location = find_chrome_binary()

if not options.binary_location or not os.path.exists(options.binary_location):
    if platform.system() == 'Darwin':  # macOS
        print("[!] Could not locate Google Chrome binary. Expected under:")
        print("    /Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    elif platform.system() == 'Linux':  # Linux
        print("[!] Could not locate Google Chrome binary. Expected under:")
        print("    /usr/bin/google-chrome")
    else:  # Windows
        print("[!] Could not locate Google Chrome binary. Expected under:")
        print("    C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
        print("    or LOCALAPPDATA\\Google\\Chrome\\Application\\chrome.exe")

    print("\n[!] Chrome not found — please install it or update binary path manually.")
    sys.exit(1)

if user_profile_path:
    options.add_argument(f"--user-data-dir={user_profile_path}")

if platform.system() == 'Windows':
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
else:
    options.add_argument("--start-minimized")

browser = uc.Chrome(
    options=options,
    version_main=134,
    headless=False  # must be False for real profile
)

    # minimize on windows
if platform.system() == 'Windows':
    minimize_chrome_window()
    # minimize on macos
elif platform.system() == 'Darwin':
    minimize_chrome_macos()
else:
    # minimize on windows
    minimize_chrome_linux()

if args.debug:
    print(browser.capabilities['browserVersion'])
    print(uc.__version__)


# === Output File Setup ===
output_file = None
if args.output:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_part = '_'.join(t.replace('.', '_') for t in targets)
    output_file = open(f'dorkfinder_results_{target_part}_{timestamp}.txt', 'w', encoding='utf-8')

try:
    if args.silent:
        args.output = True

    if not args.silent:
        parser.print_banner()
    log("\n[*] Starting headless dork search...\n")
    log(f"[INFO] Search engines in use: {', '.join(ENABLED_ENGINES).capitalize()}")

    SKIP_DOMAINS = [
        "google.com",
        "accounts.google.com",
        "support.google.com",
        "policies.google.com",
        "www.google.bg",
        "www.googleusercontent.com",
        "duckduckgo.com",
        "bing.com",
        "microsoft.com",
        "go.microsoft.com",
        "support.microsoft.com"
    ]

    for cli in targets:
        log(f"[+] Target: {cli}")
        QUERIES = [q.replace('{cli}', cli) for q in RAW_QUERIES]

        for query in QUERIES:
            for engine_key in ENABLED_ENGINES:
                engine_url = SEARCH_ENGINES[engine_key]
                encoded_query = query.replace(' ', '+')
                search_url = engine_url + encoded_query
                log(f"[+] Searching: {query} [Engine: {engine_key}]")
                browser.get(search_url)
                time.sleep(random.randint(3, 6))

                page_source = browser.page_source
                if args.debug:
                    log("[DEBUG] Page content snippet:")
                    print(page_source[:1000])

                if engine_key == 'google' and ('captcha' in page_source.lower() or 'unusual traffic' in page_source.lower()):
                    log("[!] CAPTCHA detected from Google. Please open the URL manually, solve the CAPTCHA, then export cookies to 'cookies_google.json'.")
                    log(f"[!] URL: {search_url}")
                    browser.quit()
                    sys.exit(1)

                links = browser.find_elements(By.XPATH, '//a[contains(@href, "http")]')
                found = False
                for link in links:
                    href = link.get_attribute('href')
                    if href and not any(skip in href for skip in SKIP_DOMAINS):
                        log(f"   -> {href}")
                        found = True
                        if output_file:
                            output_file.write(f"{href}\n")
                            output_file.flush()  # Force write to file immediately

                if not found:
                    log("   -> No relevant links found.")

                # Interactive sleep spinner
                log(f"   -> Sleeping for {args.tsleep} seconds ", end='', flush=True)
                for i in range(args.tsleep):
                    for cursor in '|/-\\':
                        sys.stdout.write(f'\r   -> Sleeping for {args.tsleep} seconds {cursor}')
                        sys.stdout.flush()
                        time.sleep(0.25)
                log('\r   -> Done sleeping. Back to work...                ')

    if output_file:
        output_file.close()

    browser.quit()
    print("\n[+] Finished all queries.")
    
except KeyboardInterrupt:
    log("\n[!] Interrupted by user. Exiting gracefully...")

finally:
    try:
        if browser:
            browser.quit()
    except Exception as e:
        print(f"[DEBUG] Error during browser quit: {e}")

    try:
        if output_file:
            output_file.close()
    except Exception:
        pass

    sys.exit(0)