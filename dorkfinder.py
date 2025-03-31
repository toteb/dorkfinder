import platform
import argparse
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import tempfile
import random
import os
import sys
from datetime import datetime
import undetected_chromedriver as uc
uc.Chrome.__del__ = lambda self: None
import json
from utils import (
    minimize_chrome_window, minimize_chrome_macos, minimize_chrome_linux, get_search_engines,
    find_chrome_binary, is_tor_installed, log, start_tor, stop_tor, rotate_tor_ip, get_current_tor_ip, ensure_sudo_alive,
    cleanup, kill_existing_uc_chrome
)

COMPLETED_SUCCESSFULLY = False
ensure_sudo_alive()
CAPTCHA_THRESHOLD = 5

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

# === PARSING STUFF ===
args = parser.parse_args()

# === RESUME STUFF ===
TEMP_DIR = tempfile.gettempdir()
LAST_TARGET_FILE = os.path.join(TEMP_DIR, "dorkfinder_last_target.json")

def get_progress_file(target=None):
    safe_target = target.replace(' ', '_').replace('.', '_') if target else "default"
    return os.path.join(TEMP_DIR, f"resume_{safe_target.lower()}.json")

# Determine the target
if args.resume and not args.target:
    if os.path.exists(LAST_TARGET_FILE):
        with open(LAST_TARGET_FILE, 'r') as f:
            args.target = json.load(f).get("target")
        if not args.target:
            print("[!] Cannot resume: target unknown.")
            sys.exit(1)
else:
    # Save target to pointer file
    with open(LAST_TARGET_FILE, 'w') as f:
        json.dump({"target": args.target.split(',')[0]}, f)

if args.target:
    PROGRESS_FILE = get_progress_file(args.target)
    if args.debug:
        logging.debug(f"Using progress file: {PROGRESS_FILE}")
else:
    print("[!] Cannot determine target for progress file.")
    sys.exit(1)
# === END RESUME STUFF ===

if args.debug:
    import json_log_formatter
    class CustomJSONFormatter(json_log_formatter.JSONFormatter):
        def json_record(self, message, extra, record):
            extra['level'] = record.levelname
            extra['timestamp'] = self.formatTime(record, self.datefmt)
            extra['message'] = message
            return extra

    formatter = CustomJSONFormatter()
    json_handler = logging.FileHandler("debug.json")
    json_handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(json_handler)
    logging.debug("Debug mode enabled. Logging started.")


# === ENFORCE -t only if -r is not used ===
if not args.resume and not args.target:
    parser.error("the following arguments are required: -t (unless using --resume)")

# === PROGRESS LOADING + TARGET RESUME ===
progress = {}
if args.resume:
    args.output = True
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            try:
                progress = json.load(f)
            except json.JSONDecodeError:
                print("[!] Progress file found but empty. Please provide a target with -t.")
                sys.exit(1)

        if not args.target:
            args.target = list(progress.keys())[0]
            if args.target:
                PROGRESS_FILE = get_progress_file(args.target)
                if args.debug:
                    logging.debug(f"Using progress file: {PROGRESS_FILE}")
            else:
                print("[!] Cannot determine target for progress file.")
                sys.exit(1)
            completed_queries = list(progress.get(args.target, {}).values())
        completed_queries = list(progress.get(args.target, {}).values())
        if 'sleep_time' in progress and not any(arg.startswith('--sleep') for arg in sys.argv):
            args.sleep = progress['sleep_time']
        if args.debug:
            logging.debug(f"Resuming with saved sleep time: {args.sleep}")
        if completed_queries and isinstance(completed_queries[0], dict):
            if not any(arg.startswith('-e') or arg.startswith('--engine') for arg in sys.argv):
                args.engine = completed_queries[0].get("engine", args.engine)
                if args.debug:
                    logging.debug(f"Resuming with saved engine: {args.engine}")
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
        print("[!] --resume flag used, but no progress file found.")
        print("[!] Either remove --resume or run with -t to start fresh.")
        sys.exit(1)

def save_progress():
    progress['use_tor'] = args.tor
    progress['last_updated'] = datetime.now().isoformat()
    progress['sleep_time'] = args.sleep
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)
    if args.debug:
        logging.debug(f"Progress saved: {progress}")

# === SEARCH ENGINES ===
SEARCH_ENGINES = get_search_engines()
ENABLED_ENGINES = [args.engine]
targets = list(set(t.strip() for t in args.target.split(','))) if args.target else [] 

# === Load Queries ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
queries_path = os.path.join(SCRIPT_DIR, 'queries.txt')
with open(queries_path, 'r', encoding='utf-8') as f:
    RAW_QUERIES = [line.strip() for line in f if line.strip() and not line.startswith('#')]

kill_existing_uc_chrome()

# === Browser Setup ===
options = uc.ChromeOptions()

use_real_profile = args.engine == 'google'
headless_mode = args.engine != 'google'

if platform.system() == 'Darwin':
    options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
elif platform.system() == 'Linux':
    options.binary_location = "/usr/bin/google-chrome"
else:
    options.binary_location = find_chrome_binary()

# === USE real_profile with GOOGLE only ===
use_temp_profile = args.engine == 'google'
if use_temp_profile:
    temp_dir = tempfile.gettempdir()
    profile = os.path.join(temp_dir, "chrome-profile-dorkfinder")
    os.makedirs(profile, exist_ok=True)
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
else:
    try:
        import urllib.request
        ip = urllib.request.urlopen('https://api.ipify.org').read().decode()
        log(f"[INFO] Public IP: {ip}", silent=args.silent)
        if args.debug:
            logging.debug(f"Public IP: {ip}")
    except Exception as e:
        log(f"[!] Failed to retrieve public IP: {e}", silent=args.silent)
        if args.debug:
            logging.debug(f"Failed to retrieve public IP: {e}")

failed_queries = []
retry_tracker = {}

try:
    import atexit
    atexit.register(cleanup)
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
    last_logged_engine = None
    if os.path.exists(output_filename):
        with open(output_filename, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("### ENGINE :"):
                    last_logged_engine = line.strip().split(":")[1].strip()

try:
    if not args.resume:
        parser.print_banner()
    log("\n[*] Starting simple dork search...", silent=args.silent)
    if args.debug:
        log(f"[DEBUG] Engine: {', '.join(ENABLED_ENGINES).capitalize()}", silent=args.silent)
        logging.debug(f"Engine: {', '.join(ENABLED_ENGINES)}")
    CAPTCHA_COUNT = 0
    SKIP = [".google.", "bing.com", "mozilla.org", "microsoft.com", "duckduckgo.com", "duck.ai", "apple.com", "google.", "windows.net", "live.com", "wikipedia.org", "youtube.com"]

    if output_file and args.engine != last_logged_engine:
        output_file.write(f"\n### ENGINE : {args.engine.upper()}\n")
        output_file.flush()

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
                if is_already_done:
                    status_msg = "Skipped"
                else:
                    if args.debug:
                        status_msg = f"Searching Q{query_index}"
                    else:
                        status_msg = f"Searching"
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
                    print(source[:1000])

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
                log('-> Back to work.', silent=args.silent)

    ensure_sudo_alive()

    cleanup() 
    
    if failed_queries:
        with open("failed_queries.json", "w", encoding="utf-8") as fq:
            json.dump(failed_queries, fq, indent=2)

    if args.debug:
        logging.debug("All queries processed. Preparing to exit.")
    log(f"\n[+] Summary: {len(progress.get(args.target, {}))} queries recorded for target '{args.target}'", silent=args.silent)
    if args.debug:
        logging.debug(f"Summary: {len(progress.get(args.target, {}))} queries recorded for target '{args.target}'")

    log("\n[+] Finished all queries.", silent=args.silent)
    COMPLETED_SUCCESSFULLY = True
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        if args.debug:
            logging.debug(f"Deleted {PROGRESS_FILE} after successful completion.")
    if use_temp_profile:
        try:
            import shutil
            if os.path.exists(profile):
                shutil.rmtree(profile)
                if args.debug:
                    logging.debug(f"Deleted temporary Chrome profile directory: {profile}")
        except Exception as e:
            if args.debug:
                logging.debug(f"Failed to delete Chrome profile directory: {e}")
    sys.exit(0)

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
    cleanup(browser=browser, output_file=output_file, args=args)
    if use_temp_profile:
        try:
            import shutil
            if os.path.exists(profile):
                shutil.rmtree(profile)
                if args.debug:
                    logging.debug(f"Deleted temporary Chrome profile directory: {profile}")
        except Exception as e:
            if args.debug:
                logging.debug(f"Failed to delete Chrome profile directory: {e}")
    os._exit(2)

except Exception as e:
    if COMPLETED_SUCCESSFULLY:
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
            if args.debug:
                logging.debug(f"Deleted {PROGRESS_FILE} after successful completion.")
        sys.exit(0)
    log(f"[!] An error occurred: {e}", silent=args.silent)
    if args.debug:
        logging.debug(f"Exception occurred: {str(e)}")
    try:
        save_progress()
    except Exception as se:
        log(f"[!] Failed to save progress: {se}", silent=args.silent)
        if args.debug:
            logging.debug(f"Exception occurred: {str(se)}")
    cleanup(browser=browser, output_file=output_file, args=args)
    if use_temp_profile:
        try:
            import shutil
            if os.path.exists(profile):
                shutil.rmtree(profile)
                if args.debug:
                    logging.debug(f"Deleted temporary Chrome profile directory: {profile}")
        except Exception as e:
            if args.debug:
                logging.debug(f"Failed to delete Chrome profile directory: {e}")
    os._exit(1)