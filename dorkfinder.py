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
parser.add_argument('-sl', type=int, default=60, help='Sleep time between requests (in seconds)', dest='sleep')
parser.add_argument('-si', action='store_true', default=False, help='Keeps everything nice and quiet', dest='silent')
parser.add_argument('--tor', action='store_true', help='Enable Tor routing')
parser.add_argument('--notor', action='store_true', help='Disables Tor routing for --resume')
parser.add_argument('--resume', action='store_true', help='Resume from last progress')

# FIRE HERE
args = parser.parse_args()

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
            completed_engines = list(progress.get(args.target, {}).values())
            if completed_engines:
                args.engine = completed_engines[0]
            print(f"[INFO] Resuming previous target from progress: {args.target}")
            # If previous run used Tor but --tor not provided, restore it, but check if --notor is provided first.
            if args.notor:
                args.tor = False
                log("[INFO] Skipping Tor for resume...", silent=args.silent)
            else:
                if progress.get('use_tor') and not args.tor:
                    log("[INFO] Previous session used Tor. Enabling Tor for resume...", silent=args.silent)
                    args.tor = True
        else:
            print("[!] Progress file found but empty. Please provide a target with -t.")
            sys.exit(1)
    else:
        print("[!] --resume flag used, but no progress file found.")
        print("[!] Either remove --resume or run with -t to start fresh.")
        sys.exit(1)

def save_progress():
    progress['use_tor'] = args.tor
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

# SEARCH ENGINES
SEARCH_ENGINES = get_search_engines()
# Use selected engine
ENABLED_ENGINES = [args.engine]
targets = [t.strip() for t in args.target.split(',')] if args.target else [] 

# === Load Queries ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
queries_path = os.path.join(SCRIPT_DIR, 'queries.txt')
with open(queries_path, 'r', encoding='utf-8') as f:
    RAW_QUERIES = [line.strip() for line in f if line.strip() and not line.startswith('#')]

# === Browser Setup ===
options = uc.ChromeOptions()

use_real_profile = ()
if args.engine == 'google':
    use_real_profile == True
else:
    use_real_profile = False

# On Linux, avoid using real profile when running headless with non-Google engines
headless_mode = args.engine != 'google'

#profiles and executables  
if platform.system() == 'Darwin':
    profile = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default")
    options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
elif platform.system() == 'Linux':
    profile = os.path.expanduser("~/.config/google-chrome/Default")
    options.binary_location = "/usr/bin/google-chrome"
else:
    profile = os.path.join(os.environ['LOCALAPPDATA'], "Google\\Chrome\\User Data")
    options.binary_location = find_chrome_binary()

# use real profile specs
if use_real_profile:
    options.add_argument(f"--user-data-dir={profile}")
if platform.system() == 'Windows':
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

if args.tor:
    if not start_tor():
        log("[!] Could not start Tor. Exiting.", silent=args.silent)
        sys.exit(1)
    options.add_argument('--proxy-server=socks5://127.0.0.1:9050')
    tor_ip = get_current_tor_ip()
    log(f"[INFO] Tor is active. Current Tor IP: {tor_ip}")
    if "Error" in tor_ip:
        log(f"[!] {tor_ip}", silent=args.silent)

try:
    browser = uc.Chrome(options=options, version_main=134, headless=headless_mode)
except Exception as e:
    log(f"[!] Failed to start browser: {e}", silent=args.silent)
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
    log(f"Browser version: {browser.capabilities['browserVersion']}", silent=args.silent)
    log(f"Undetected driver version: {uc.__version__}", silent=args.silent)

output_file = None
if args.output or args.silent:
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe = '_'.join(t.replace('.', '_') for t in targets)
    output_file = open(f'dorkfinder_results_{safe}_{ts}.txt', 'w', encoding='utf-8')

try:
    parser.print_banner()
    log("\n[*] Starting simple dork search...", silent=args.silent)
    if args.debug:
        log(f"[INFO] Engine: {', '.join(ENABLED_ENGINES).capitalize()}", silent=args.silent)
        log(f"[INFO] Headless mode: {'enabled' if headless_mode else 'disabled'}", silent=args.silent)

    CAPTCHA_COUNT = 0
    SKIP = ["google.com", "support.google.com", "bing.com", "microsoft.com", "duckduckgo.com", "duck.ai", "apple.com"]

    for cli in targets:
        log(f"[+] Target: {cli}", silent=args.silent)
        QUERIES = [q.replace('{cli}', cli) for q in RAW_QUERIES]
        
        if cli not in progress:
            progress[cli] = {}

        for query in QUERIES:
            for engine_key in ENABLED_ENGINES:
                if progress[cli].get(query) == engine_key:
                    if args.debug:
                        log(f"[DEBUG] Skipping already completed query: {query} [{engine_key}]", silent=args.silent)
                    continue

            for engine_key in ENABLED_ENGINES:
                if progress.get(cli, {}).get(query, '') == engine_key:
                    continue  # already done

                url = SEARCH_ENGINES[engine_key] + query.replace(' ', '+')
                log(f"[+] Searching: {query} [Engine: {engine_key}]", silent=args.silent)
                browser.get(url)
                time.sleep(random.randint(3, 6))
                source = browser.page_source

                if args.debug:
                    log("[DEBUG] Page snippet:", silent=args.silent)
                    print(source[:1000])

                if engine_key == 'google' and ('captcha' in source.lower() or 'unusual traffic' in source.lower()):
                    CAPTCHA_COUNT += 1
                    log("[!] CAPTCHA detected.", silent=args.silent)
                    if CAPTCHA_COUNT >= CAPTCHA_THRESHOLD:
                        log("[!] CAPTCHA threshold reached. Exiting.", silent=args.silent)
                        save_progress()
                        browser.quit()
                        stop_tor()
                        sys.exit(1)
                    if args.tor:
                        log("[*] Rotating Tor IP...")
                        rotate_tor_ip()
                        time.sleep(5)  # brief wait for Tor to stabilize
                        tor_ip = get_current_tor_ip()
                        log(f"[INFO] New Tor IP: {tor_ip}")
                        continue
                    else:
                        log("[!] Waiting 5 mins before retry...", silent=args.silent)
                        time.sleep(300)
                        continue

                found = False
                for link in browser.find_elements(By.XPATH, '//a[contains(@href, "http")]'):
                    href = link.get_attribute('href')
                    if href and not any(domain in href for domain in SKIP):
                        log(f"   -> {href}")
                        if output_file:
                            output_file.write(f"{href}\n")
                            output_file.flush()
                        found = True

                if not found:
                    log("   -> No relevant links found.", silent=args.silent)

                if cli not in progress:
                    progress[cli] = {}
                progress[cli][query] = engine_key
                save_progress()

                log(f"   -> Sleeping {args.sleep}s ", end='', flush=True, silent=args.silent)
                for i in range(args.sleep):
                    for cursor in '|/-\\':
                        sys.stdout.write(f'\r   -> Sleeping {args.sleep}s {cursor}')
                        sys.stdout.flush()
                        time.sleep(0.25)
                log('\r   -> Done sleeping.', silent=args.silent)

    ensure_sudo_alive()
    browser.quit()
    stop_tor()
    if output_file:
        output_file.close()
    log("\n[+] Finished all queries.", silent=args.silent)

except KeyboardInterrupt:
    sys.exit(0)
    log("\n[!] Interrupted by user. Saving progress and exiting...", silent=args.silent)
    try:
        save_progress()
    except Exception as e:
        log(f"[!] Failed to save progress: {e}", silent=args.silent)

    try:
        if browser:
            browser.quit()
    except Exception as e:
        log(f"[!] Failed to quit browser: {e}", silent=args.silent)

    try:
        stop_tor()
    except Exception as e:
        log(f"[!] Failed to stop Tor: {e}", silent=args.silent)

    try:
        if output_file:
            output_file.close()
    except Exception as e:
        log(f"[!] Failed to close output file: {e}", silent=args.silent)

except Exception as e:
    log(f"[!] An error occurred: {e}", silent=args.silent)
    save_progress()
    if browser:
        browser.quit()
    stop_tor()
    if output_file:
        output_file.close()
    sys.exit(1)
