import platform
import os
import sys
import time
import subprocess
import shutil
import requests
import re
import threading
import psutil
import urllib.request
import getpass
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Color constants
def init_colors():
    if platform.system().lower() == "windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return {
                "RESET": "\033[0m",
                "GREEN": "\033[92m",
                "RED": "\033[91m",
                "YELLOW": "\033[93m",
                "BLUE": "\033[94m",
                "MAGENTA": "\033[95m",
                "CYAN": "\033[96m",
                "WHITE": "\033[97m",
                "BOLD": "\033[1m"
            }
        except Exception:
            return {
                "RESET": "",
                "GREEN": "",
                "RED": "",
                "YELLOW": "",
                "BLUE": "",
                "MAGENTA": "",
                "CYAN": "",
                "WHITE": "",
                "BOLD": ""
            }
    else:
        return {
            "RESET": "\033[0m",
            "GREEN": "\033[92m",
            "RED": "\033[91m",
            "YELLOW": "\033[93m",
            "BLUE": "\033[94m",
            "MAGENTA": "\033[95m",
            "CYAN": "\033[96m",
            "WHITE": "\033[97m",
            "BOLD": "\033[1m"
        }

# Initialize colors
colors = init_colors()
RESET = colors["RESET"]
GREEN = colors["GREEN"]
RED = colors["RED"]
YELLOW = colors["YELLOW"]
BLUE = colors["BLUE"]
MAGENTA = colors["MAGENTA"]
CYAN = colors["CYAN"]
WHITE = colors["WHITE"]
BOLD = colors["BOLD"]

shutdown_flag = False

def get_output_streams(args=None):
    """Get appropriate output streams based on debug mode"""
    if args and getattr(args, 'debug', False):
        return sys.stdout, sys.stderr
    return subprocess.DEVNULL, subprocess.DEVNULL

def ensure_sudo_alive(args):
    """
    On Linux/macOS, request sudo access once and keep it alive.
    On Windows, this function does nothing.
    """
    pid = os.getpid()
    plat = platform.system()
    sudo_check_required = plat in ['Linux', 'Darwin']
    
    if args and getattr(args, 'debug', False):
        logging.debug(f"Platform is {plat}. Sudo check required: {sudo_check_required}")

    if not sudo_check_required:
        return  # No sudo needed on Windows

    try:
        # Attempt non-interactive sudo check
        if args and getattr(args, 'debug', False):
            logging.debug("Attempting non-interactive sudo check with 'sudo -n true'")
        result = subprocess.run(["sudo", "-n", "true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode != 0:
            # Prompt user for password with clearer message
            if args and getattr(args, 'debug', False):
                logging.debug("Non-interactive sudo check failed, prompting for password...")
            try:
                mode = "INFO"
                password = getpass.getpass(f"[{mode}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Sudo access is required. Enter password: ")
                result = subprocess.run(["sudo", "-S", "-v"], input=password + "\n", text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if args and getattr(args, 'debug', False):
                    logging.debug(f"Sudo password accepted: {result.returncode == 0}")
                if result.returncode != 0:
                    if args and getattr(args, 'debug', False):
                        logging.debug("Invalid sudo password. Exiting.")
                    sys.exit(1)
            except KeyboardInterrupt:
                print()
                if args and getattr(args, 'debug', False):
                    logging.debug("Sudo password prompt cancelled by user.")
                sys.exit(1)
    except subprocess.CalledProcessError:
        if args and getattr(args, 'debug', False):
            logging.debug("Sudo privileges could not be obtained. Exiting.")
        sys.exit(1)

    def keep_sudo_alive():
        global shutdown_flag
        while not shutdown_flag:
            try:
                stdout, stderr = get_output_streams(args)
                subprocess.run(["sudo", "-n", "true"], stdout=stdout, stderr=stderr)
                time.sleep(60)
            except Exception as e:
                if args and getattr(args, 'debug', False):
                    logging.debug(f"Exception in keep_sudo_alive thread: {e}")
                break

    threading.Thread(target=keep_sudo_alive, daemon=True).start()

# refresh sudo
def keep_sudo_alive_interval(interval_minutes=15):
    """
    Starts a background thread that refreshes sudo timestamp every `interval_minutes`.
    """
    #logging.debug("keep_sudo_alive_interval() called")
    def refresh_sudo():
        #logging.debug("refresh_sudo() called")
        while not shutdown_flag:
            try:
                stdout, stderr = get_output_streams()
                #logging.debug("Attempting to refresh sudo timestamp")
                res = subprocess.run(["sudo", "-n", "true"], stdout=stdout, stderr=stdout)
                #logging.debug(f"Refreshed sudo timestamp at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (return code: {res.returncode})")
            except subprocess.CalledProcessError as e:
                print()
                logging.debug(f"Failed to refresh sudo timestamp. Return code: {e.returncode}", level="error")
            except Exception as e:
                print()
                logging.debug(f"Exception while refreshing sudo timestamp: {e}", level="error")
            time.sleep(interval_minutes * 60)

    if platform.system() in ["Linux", "Darwin"]:
        threading.Thread(target=refresh_sudo, daemon=True).start()


def log(msg, level="info", silent=False, **kwargs):
    """Enhanced logging function with levels and colors"""
    if silent:
        return
        
    color = {
        "info": BLUE,
        "debug": YELLOW,
        "error": RED
    }.get(level, BLUE)
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{color}[{level.upper()}] {timestamp}{RESET} {msg}", **kwargs)

# Track Tor process if needed (Windows/manual)
tor_process = None

# find TOR executable on windows
def find_tor_executable():
    # Common install paths
    candidates = [
        os.path.join(os.path.expanduser("~"), "Desktop", "Tor Browser", "Browser", "TorBrowser", "Tor.exe"),
        r"C:\Tor Browser\Browser\TorBrowser\Tor.exe",
        r"C:\Program Files\Tor Browser\Browser\TorBrowser\Tor.exe",
        r"C:\Program Files (x86)\Tor Browser\Browser\TorBrowser\Tor.exe"
    ]

    for path in candidates:
        if os.path.exists(path):
            return path

    return None

# Check if Tor is installed
tor_path = find_tor_executable()  # <-- call it here
def is_tor_installed():
    paths = [
        "/usr/bin/tor",
        "/opt/homebrew/bin/tor",
        tor_path
    ]
    return shutil.which("tor") is not None or any(os.path.exists(p) for p in paths if p)

# Rotate TOR 
def rotate_tor_ip():
    import socket
    import socks
    import requests

    try:
        with socket.create_connection(("127.0.0.1", 9051)) as s:
            s.send(b'AUTHENTICATE\r\n')
            time.sleep(3)
            s.send(b'SIGNAL NEWNYM\r\n')
            time.sleep(5)
            s.send(b'QUIT\r\n')
    except Exception as e:
        print(f"[!] Failed to rotate Tor IP: {e}")

# Start tor
def start_tor():
    import signal
    if not is_tor_installed():
        print("[!] Tor is not installed on this system.")
        answer = None
        def ask_input():
            nonlocal answer
            try:
                answer = input().strip().lower()
            except Exception:
                answer = None

        print("[?] Would you like to install Tor now? (yes/no): ", end='', flush=True)

        if platform.system() in ['Linux', 'Darwin']:
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(60)

            try:
                answer = input().strip().lower()
            finally:
                signal.alarm(0)

        else:
            # Windows alternative using threading
            timer = threading.Timer(60, lambda: sys.stdin.close())
            try:
                timer.start()
                ask_input()
            except Exception:
                print("\n[!] Timed out waiting for user input.")
                return False
            finally:
                timer.cancel()

        if answer in ['y', 'yes']:
            if platform.system() == 'Linux':
                subprocess.run(["sudo", "apt-get", "update", "-y"])
                subprocess.run(["sudo", "apt-get", "install", "-y", "tor"])
            elif platform.system() == 'Darwin':
                subprocess.run(["brew", "install", "tor"])
            else:
                print("[*] Attempting Tor installation on Windows...")
                tor_url = "https://www.torproject.org/dist/torbrowser/14.0.8/tor-browser-windows-x86_64-portable-14.0.8.exe"
                installer_path = os.path.join(os.getenv("TEMP", "."), "tor_install.exe")

                try:
                    import urllib.request
                    print(f"[INFO] Downloading Tor from: {tor_url}")
                    urllib.request.urlretrieve(tor_url, installer_path)
                    print("[INFO] Running installer...")
                    subprocess.run([installer_path], check=True)
                    print("[INFO] Once Tor is installed, open a terminal and run:")
                    print("       tor.exe --service install")
                    print("Then restart the script.")
                    return False
                except Exception as e:
                    print(f"[!] Failed to download or run installer: {e}")
                    return False

        elif answer in ['n', 'no']:
            print("[!] Tor installation declined by user.")
            return False
        else:
            print("[!] Invalid input. Expected 'yes' or 'no'.")
            return False

    try:
        if platform.system() == 'Windows':
            global tor_process
            tor_path = shutil.which("tor")
            if tor_path:
                tor_process = subprocess.Popen([tor_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("[INFO] Tor process started on Windows.")
                return True
            else:
                print("[!] Could not locate tor.exe")
                return False
        else:
            if platform.system() == 'Darwin':
                # Use brew path to run Tor manually in background
                tor_path = "/opt/homebrew/opt/tor/bin/tor"
                if os.path.exists(tor_path):
                    subprocess.Popen([tor_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print("[INFO] Tor started manually on macOS.")
                    return True
                else:
                    print("[!] Tor binary not found at expected Homebrew location.")
                    return False
            else:
                # Check if Tor is already active
                result = subprocess.run(["systemctl", "is-active", "--quiet", "tor"])
                if result.returncode == 0:
                    print("[INFO] Tor is already running.")
                else:
                    subprocess.run(["sudo", "systemctl", "start", "tor"], check=True)
                    print("[INFO] Tor service started.")
            return True
    except Exception as e:
        print(f"[!] Failed to start Tor: {e}")
        return False

# stop tor
def stop_tor():
    from dorkfinder import args
    if not getattr(args, 'tor', False):
        return

    try:
        if platform.system() == 'Windows':
            global tor_process
            if tor_process:
                tor_process.terminate()
                tor_process.wait()
                print("[INFO] Tor process terminated.")
        else:
            if platform.system() == 'Darwin':
                try:
                    subprocess.run(["sudo", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    brew_services_path = "/opt/homebrew/bin/brew"
                    if os.path.exists(brew_services_path):
                        subprocess.run(["sudo", brew_services_path, "services", "stop", "tor"], check=True)
                        print("[INFO] Tor service stopped using Homebrew.")
                    else:
                        print("[!] Could not find Homebrew service manager to stop Tor.")
                except Exception as e:
                    print(f"[!] Failed to stop Tor with Homebrew: {e}")
            else:
                try:
                    subprocess.run(["sudo", "-n", "true"], check=True)
                    subprocess.run(["sudo", "-n", "systemctl", "stop", "tor"], check=True)
                    print("[INFO] Tor service stopped.")
                except Exception as e:
                    print(f"[!] Failed to stop Tor: {e}")
    except Exception as e:
        print(f"[!] Failed to stop Tor: {e}")

# Get current TOR IP
def get_current_tor_ip(retries=5, delay=2):
    """
    Attempts to fetch the current Tor IP with retry logic.

    Args:
        retries (int): Number of attempts before giving up.
        delay (int): Delay between retries in seconds.

    Returns:
        str: Tor IP or an error message.
    """
    for attempt in range(retries):
        try:
            response = requests.get("https://api.ipify.org", proxies={
                'http': 'socks5h://127.0.0.1:9050',
                'https': 'socks5h://127.0.0.1:9050'
            }, timeout=10)
            if response.status_code == 200:
                return response.text.strip()
        except requests.RequestException:
            time.sleep(delay)
    return "Tor not ready (connection refused)"

# get current chrome version
def get_chrome_major_version():
    try:
        if platform.system() == "Windows":
            command = r'reg query "HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon" /v version'
            output = subprocess.check_output(command, shell=True).decode()
            version = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", output).group(1)
        elif platform.system() == "Darwin":
            output = subprocess.check_output(
                ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"]
            ).decode()
            version = re.search(r"Google Chrome (\d+)", output).group(1)
        else:  # Assume Linux
            output = subprocess.check_output(["google-chrome", "--version"]).decode()
            version = re.search(r"Google Chrome (\d+)", output).group(1)
        return int(version)
    except Exception as e:
        print(f"Could not detect Chrome version: {e}")
        return None

def get_search_engines():
    return {
        'brave': "https://search.brave.com/search?q=",
        'bing': "https://www.bing.com/search?q=",
        'ddg': "https://duckduckgo.com/?q=",
        'google': "https://www.google.com/search?q=",
    }

def modify_queries_for_exclusions(queries, excluded_extensions):
    """
    Modify queries to exclude specified extensions.
    
    Args:
        queries (list): List of dork queries
        excluded_extensions (list): List of extensions to exclude
        
    Returns:
        list: Modified queries with excluded extensions
    """
    if not excluded_extensions:
        return queries
    
    modified_queries = []
    for query in queries:
        # Skip if it's a comment
        if query.startswith('#'):
            modified_queries.append(query)
            continue
            
        # Check if query contains ext: or extension:
        if 'ext:' in query or 'extension:' in query:
            # Split the query into parts
            parts = query.split('ext:')
            if len(parts) > 1:
                # Get the extensions part
                extensions_part = parts[1].split()[0]
                # Split extensions by | and remove excluded ones
                extensions = [ext.strip() for ext in extensions_part.split('|')]
                filtered_extensions = [ext for ext in extensions if ext not in excluded_extensions]
                
                if filtered_extensions:
                    # Reconstruct the query with filtered extensions
                    new_query = parts[0] + 'ext:' + '|'.join(filtered_extensions) + ' ' + ' '.join(parts[1].split()[1:])
                    modified_queries.append(new_query)
                else:
                    # Skip the query if all extensions were excluded
                    continue
            else:
                modified_queries.append(query)
        else:
            # For queries without extensions, add exclusion
            if 'site:' in query:
                # Split at site: to preserve the site part
                site_parts = query.split('site:')
                if len(site_parts) > 1:
                    # Add exclusions after the site part
                    new_query = f"{site_parts[0]}site:{site_parts[1]} -ext:{' -ext:'.join(excluded_extensions)}"
                    modified_queries.append(new_query)
                else:
                    modified_queries.append(query)
            else:
                # For queries without site:, add exclusions at the end
                new_query = f"{query} -ext:{' -ext:'.join(excluded_extensions)}"
                modified_queries.append(new_query)
    
    return modified_queries

# Minimize on windows
def minimize_chrome_window(timeout=10):
    if platform.system() != 'Windows':
        return

    try:
        #print("[INFO] Waiting for Chrome window to appear...")
        from pywinauto import Desktop
        for _ in range(timeout * 2):
            try:
                
                windows = Desktop(backend="uia").windows()
                for win in windows:
                    if "chrome" in win.window_text().lower():
                        win.minimize()
                        #print("[DEBUG] Chrome window minimized.")
                        return
            except Exception:
                pass
            time.sleep(0.5)

        print("[!] Chrome window not found within timeout. Skipping minimize.")

    except Exception as e:
        print(f"[!] Failed to minimize Chrome window: {e}")

# Minimize on macOS
def minimize_chrome_macos():
    if platform.system() != "Darwin":
        return

    try:
        script = '''
        tell application "System Events"
            tell process "Google Chrome"
                keystroke "m" using {command down}
            end tell
        end tell
        '''
        subprocess.run(["osascript", "-e", script])
        #print("[DEBUG] Chrome minimize keystroke sent (macOS).")

    except Exception as e:
        print(f"[!] Failed to minimize Chrome on macOS: {e}")

#Minimize on Linux
def minimize_chrome_linux():
    if platform.system() != "Linux":
        return

    try:
        subprocess.run(["wmctrl", "-r", "Google Chrome", "-b", "add,hidden"])
        #print("[INFO] Chrome window minimized (Linux).")

    except Exception as e:
        print(f"[!] Failed to minimize Chrome on Linux: {e}")

# Grab google chrome for windows
def find_chrome_binary():
    """
    Finds the Chrome executable path in common locations.

    Returns:
        str: The path to chrome.exe, or None if not found.
    """
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.getenv("LOCALAPPDATA"), r"Google\Chrome\Application\chrome.exe"),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

# Cleanup 
def cleanup(browser=None, output_file=None, args=None):
    """Cleanup function to properly handle resource cleanup"""
    global shutdown_flag
    shutdown_flag = True  # Signal all threads to stop
    
    try:
        if browser:
            try:
                browser.quit()
            except Exception as e:
                if args and getattr(args, "debug", False):
                    logging.debug(f"browser.quit() failed: {e}")

        # Fallback: Kill any Chrome processes started by uc
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if 'chrome' in proc.info['name'].lower() and any('undetected_chromedriver' in cmd for cmd in proc.info['cmdline']):
                    proc.kill()
                    if args and getattr(args, "debug", False):
                        logging.debug(f"Force-killed leftover Chrome: PID {proc.pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if args and getattr(args, "tor", False):
            stop_tor()

        if output_file:
            try:
                output_file.flush()
                output_file.close()
            except Exception as e:
                if args and getattr(args, "debug", False):
                    logging.debug(f"Failed to close output file: {e}")

        # Clean up multiprocessing resources
        import multiprocessing
        import atexit
        import signal
        
        # Clean up active children
        for p in multiprocessing.active_children():
            try:
                p.terminate()
                p.join(timeout=1)
            except Exception:
                pass

        # Reset multiprocessing
        if hasattr(multiprocessing, 'resource_tracker'):
            try:
                # Get the current process
                current = multiprocessing.current_process()
                if current.name == 'MainProcess':
                    # Clear the resource tracker
                    multiprocessing.resource_tracker._resource_tracker.clear()
                    # Reset the resource tracker
                    multiprocessing.resource_tracker._resource_tracker = multiprocessing.resource_tracker.ResourceTracker()
            except Exception as e:
                if args and getattr(args, "debug", False):
                    logging.debug(f"Failed to reset resource tracker: {e}")

    except Exception as e:
        if args and getattr(args, "debug", False):
            logging.debug(f"Cleanup exception: {e}")
    finally:
        # Force cleanup of any remaining resources
        if platform.system() in ['Linux', 'Darwin']:
            try:
                subprocess.run(['pkill', '-f', 'undetected-chromedriver'], 
                             stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL)
            except Exception:
                pass

def kill_existing_uc_chrome():
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'chrome' in proc.info['name'].lower() and any('undetected_chromedriver' in cmd for cmd in proc.info['cmdline']):
                proc.kill()
                if args.debug:
                    logging.debug(f"Killed existing undetected_chromedriver Chrome process: PID {proc.pid}")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
