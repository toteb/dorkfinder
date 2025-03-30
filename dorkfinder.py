import platform
import argparse
import logging
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
from utils import minimize_chrome_window, minimize_chrome_macos, minimize_chrome_linux, get_search_engines, find_chrome_binary, is_tor_installed, log, start_tor, stop_tor, rotate_tor_ip, get_current_tor_ip, ensure_sudo_alive

# Request sudo only once
ensure_sudo_alive()

CAPTCHA_THRESHOLD = 5
PROGRESS_FILE = 'progress.json'

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
                            Simple DorkFinder by @mcn1k
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
    description='Simple dorkfinder by @mcn1k',
    usage='dorkfinder.py -t example.com [-o] [-e {brave,bing,ddg,google}] [--debug] [-sl 60] [--si]'
)
parser.add_argument('-t', metavar='example.com', help='Target domain (or comma-separated list)', dest='target', type=str)
parser.add_argument('-o', action='store_true', help='Write output to a timestamped file', dest='output')
parser.add_argument('-e', choices=['brave', 'bing', 'ddg', 'google'], default='google', help='Search engine to use. Default: Google Chrome', dest='engine')
parser.add_argument('-d', action='store_true', help='Enable debug output (page source snippet)', dest='debug')
parser.add_argument('-r', action='store_true', help='Resume from last progress', dest='resume')
parser.add_argument('-s', action='store_true', default=False, help='Keeps everything nice and quiet', dest='silent')
parser.add_argument('--sleep', type=int, default=60, help='Sleep time between requests (in seconds)', dest='sleep')
parser.add_argument('--tor', action='store_true', help='Enable Tor routing')
parser.add_argument('--notor', action='store_true', help='Disables Tor routing for --resume')

# FIRE HERE
args = parser.parse_args()

if args.debug:
    logging.basicConfig(
        filename="debug.log",
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filemode="w"
    )
    logging.debug("Debug mode enabled. Logging started.")

# Enforce -t only if --resume is not used
if not args.resume and not args.target:
    parser.error("the following arguments are required: -t (unless using --resume)")

# === PROGRESS LOADING + TARGET RESUME ===
progress = {}
if args.resume:
    args.output = True
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            progress = json.load(f)
        if not args.target:
            args.target = list(progress.keys())[0]
            completed_queries = list(progress.get(args.target, {}).values())
            if completed_queries and isinstance(completed_queries[0], dict):
                args.engine = completed_queries[0].get("engine", args.engine)
            print(f"[INFO] Resuming previous target from progress: {args.target}")
            if args.notor:
                args.tor = False
                log("[INFO] Skipping Tor for resume...", silent=args.silent)
                if args.debug:
                    logging.debug(f"Skipping Tor for resume for target: {args.target}")
            else:
                if progress.get('use_tor') and not args.tor:
                    log("[INFO] Previous session used Tor. Enabling Tor for resume...", silent=args.silent)
                    args.tor = True
                    if args.debug:
                        logging.debug(f"Enabling Tor for resume for target: {args.target}")
        else:
            print("[!] Progress file found but empty. Please provide a target with -t.")
            sys.exit(1)
    else:
        print("[!] --resume flag used, but no progress file found.")
        print("[!] Either remove --resume or run with -t to start fresh.")
        sys.exit(1)

def save_progress():
    progress['use_tor'] = args.tor
    progress['last_updated'] = datetime.now().isoformat()
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)
    if args.debug:
        logging.debug(f"Progress saved: {progress}")

# === SEARCH ENGINES ===
SEARCH_ENGINES = get_search_engines()
ENABLED_ENGINES = [args.engine]
targets = [t.strip() for t in args.target.split(',')] if args.target else [] 

# === Load Queries ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
queries_path = os.path.join(SCRIPT_DIR, 'queries.txt')
with open(queries_path, 'r', encoding='utf-8') as f:
    RAW_QUERIES = [line.strip() for line in f if line.strip() and not line.startswith('#')]

# === Browser Setup ===
options = uc.ChromeOptions()

use_real_profile = args.engine == 'google'
headless_mode = args.engine != 'google'

if platform.system() == 'Darwin':
    profile = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default")
    options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
elif platform.system() == 'Linux':
    profile = os.path.expanduser("~/.config/google-chrome/Default")
    options.binary_location = "/usr/bin/google-chrome"
else:
    profile = os.path.join(os.environ['LOCALAPPDATA'], "Google\\Chrome\\User Data")
    options.binary_location = find_chrome_binary()

if use_real_profile:
    options.add_argument(f"--user-data-dir={profile}")

if platform.system() == 'Windows':
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

if platform.system() == 'Linux' and use_real_profile:
    options.add_argument("--user-data-dir=/tmp/chrome-profile-dorkfinder")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

if args.tor:
    if not start_tor():
        log("[!] Could not start Tor. Exiting.", silent=args.silent)
        if args.debug:
            logging.debug("Could not start Tor.")
        sys.exit(1)
    options.add_argument('--proxy-server=socks5://127.0.0.1:9050')
    tor_ip = get_current_tor_ip()
    log(f"[INFO] Tor is active. Current Tor IP: {tor_ip}")
    if "Error" in tor_ip:
        log(f"[!] {tor_ip}", silent=args.silent)
        if args.debug:
            logging.debug(f"Tor IP error: {tor_ip}")

failed_queries = []
retry_tracker = {}

try:
    browser = uc.Chrome(options=options, version_main=134, headless=headless_mode)
    if args.debug:
        logging.debug(f"Browser started with headless={headless_mode}, profile={use_real_profile}")
    time.sleep(1)
except Exception as e:
    log(f"[!] Failed to start browser: {e}", silent=args.silent)
    if args.debug:
        logging.debug(f"Exception occurred: {str(e)}")
    log(f"[DEBUG] Binary path: {options.binary_location}", silent=args.silent)
    log(f"[DEBUG] Headless: {headless_mode} | Real profile: {use_real_profile}", silent=args.silent)
    stop_tor()
    sys.exit(1)

if not headless_mode:
    if platform.system() == 'Windows':
        minimize_chrome_window()
    elif platform.system() == 'Darwin':
        minimize_chrome_macos()
    else:
        minimize_chrome_linux()

if args.debug:
    log(f"[DEBUG] Browser version: {browser.capabilities['browserVersion']}", silent=args.silent)
    log(f"[DEBUG] Undetected driver version: {uc.__version__}", silent=args.silent)

output_file = None
if args.output or args.silent:
    safe = '_'.join(t.replace('.', '_') for t in targets)
    output_filename = f'dorkfinder_results_{safe}.txt'
    output_file = open(output_filename, 'a', encoding='utf-8')

try:
    if not args.resume:
        parser.print_banner()
    log("\n[*] Starting simple dork search...", silent=args.silent)
    if args.debug:
        log(f"[DEBUG] Engine: {', '.join(ENABLED_ENGINES).capitalize()}", silent=args.silent)
        logging.debug(f"Engine: {', '.join(ENABLED_ENGINES)}")
        log(f"[DEBUG] Headless mode: {'enabled' if headless_mode else 'disabled'}", silent=args.silent)

    CAPTCHA_COUNT = 0
    SKIP = ["google.com", "support.google.com", "bing.com", "microsoft.com", "duckduckgo.com", "duck.ai", "apple.com"]

    for cli in targets:
        log(f"[+] Target: {cli}", silent=args.silent)
        QUERIES = [q.replace('{cli}', cli) for q in RAW_QUERIES]
        
        if cli not in progress:
            progress[cli] = {}

        for query in QUERIES:
            normalized_query = query.strip()
            query_index = QUERIES.index(query) + 1
            if args.debug:
                logging.debug(f"Executing query: {normalized_query} for target: {cli}")

            for engine_key in ENABLED_ENGINES:
                is_already_done = (
                    normalized_query in progress[cli]
                    and progress[cli][normalized_query]['engine'] == engine_key
                )
                status_msg = "Skipped" if is_already_done else f"Searching Q{query_index}"
                log(f"[+] {status_msg}: {query} [Engine: {engine_key}]", silent=args.silent)

                if normalized_query in progress[cli] and progress[cli][normalized_query]['engine'] == engine_key:
                    if args.debug:
                        logging.debug(f"Skipping already completed query: {normalized_query} [{engine_key}]")
                    continue

                if cli in progress and normalized_query in progress[cli] and progress[cli][normalized_query]['engine'] == engine_key:
                    continue

                url = SEARCH_ENGINES[engine_key] + query.replace(' ', '+')
                browser.get(url)
                time.sleep(random.randint(3, 6))
                source = browser.page_source

                if args.debug:
                    log("[DEBUG] Page snippet:", silent=args.silent)
                    print(source[:2000])

                if engine_key == 'google' and ('captcha' in source.lower() or 'unusual traffic' in source.lower()):
                    CAPTCHA_COUNT += 1
                    retry_tracker.setdefault(cli, {}).setdefault(query, 0)
                    retry_tracker[cli][query] += 1

                    log("[!] CAPTCHA detected.", silent=args.silent)
                    if args.debug:
                        logging.debug(f"Detected CAPTCHA. Retry count: {retry_tracker[cli][query]}")
                    if retry_tracker[cli][query] > 5:
                        failed_queries.append({
                            "timestamp": datetime.now().isoformat(),
                            "target": cli,
                            "query": query,
                            "engine": engine_key,
                            "query_number": query_index,
                            "reason": "CAPTCHA - max retries"
                        })
                        log("[!] Max retries exceeded for this query. Logging as failed.", silent=args.silent)
                        if args.debug:
                            logging.debug(f"Failed query added: {failed_queries[-1]}")
                        continue
                    if args.tor:
                        tor_ip = get_current_tor_ip()
                        log(f"[*] Rotating Tor IP: {tor_ip}")
                        continue
                    else:
                        log("[!] Waiting 30 mins before retry...", silent=args.silent)
                        time.sleep(1800)
                        continue
                    
                found_links = set()
                for link in browser.find_elements(By.XPATH, '//a[contains(@href, "http")]'):
                    href = link.get_attribute('href')
                    if href and not any(domain in href for domain in SKIP):
                        found_links.add(href)

                if found_links:
                    for href in sorted(found_links):
                        log(f"   -> {href}", silent=args.silent)
                        if output_file:
                            output_file.write(f"{href}\n")
                            output_file.flush()
                        if args.debug:
                            logging.debug(f"Found link: {href}")
                    found = True
                else:
                    found = False

                if not found:
                    log("   -> No relevant links found.", silent=args.silent)
                    if args.debug:
                        logging.debug("No relevant links found.")

                if cli not in progress:
                    progress[cli] = {}
                progress[cli][normalized_query] = {
                    "engine": engine_key,
                    "query_number": query_index,
                    "added": datetime.now().isoformat()
                }
                save_progress()
                
                for remaining in range(args.sleep, 0, -1):
                    sys.stdout.write(f'\r   -> Sleeping {remaining}s ')
                    sys.stdout.flush()
                    time.sleep(1)
                log(' -> Back to work.', silent=args.silent)

    ensure_sudo_alive()
    browser.quit()
    stop_tor()
    if output_file:
        output_file.close()
    
    if failed_queries:
        with open("failed_queries.json", "w", encoding="utf-8") as fq:
            json.dump(failed_queries, fq, indent=2)
    
    log("\n[+] Finished all queries.", silent=args.silent)

except KeyboardInterrupt:
    log("\n[!] Interrupted by user. Saving progress and exiting...", silent=args.silent)
    if args.debug:
        logging.debug("Interrupted by user.")
    try:
        save_progress()
    except Exception as e:
        log(f"[!] Failed to save progress: {e}", silent=args.silent)
        if args.debug:
            logging.debug(f"Exception occurred: {str(e)}")
    try:
        if browser:
            browser.quit()
            os._exit(0)
    except Exception as e:
        log(f"[!] Failed to quit browser: {e}", silent=args.silent)
        if args.debug:
            logging.debug(f"Exception occurred: {str(e)}")

except Exception as e:
    log(f"[!] An error occurred: {e}", silent=args.silent)
    if args.debug:
        logging.debug(f"Exception occurred: {str(e)}")
    try:
        save_progress()
    except Exception as se:
        log(f"[!] Failed to save progress: {se}", silent=args.silent)
        if args.debug:
            logging.debug(f"Exception occurred: {str(se)}")
    try:
        if browser:
            browser.quit()
    except Exception:
        pass
    try:
        stop_tor()
    except Exception:
        pass
    try:
        if output_file:
            output_file.close()
    except Exception:
        pass
    os._exit(1)