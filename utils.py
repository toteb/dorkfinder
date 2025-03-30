import platform
import os
import sys
import time
import subprocess
import shutil
import requests
import threading
import urllib.request

shutdown_flag = False

# Ensure sudo for darwin/linux
def ensure_sudo_alive():
    """
    On Linux/macOS, request sudo access once and keep it alive.
    On Windows, this function does nothing.
    """

    if platform.system() not in ['Linux', 'Darwin']:
        return  # No sudo needed on Windows

    result = subprocess.run("sudo -n true", shell=True)
    if result.returncode != 0:
        # We don’t have sudo; ask for it interactively
        try:
            subprocess.run("sudo -v", shell=True, check=True)
        except subprocess.CalledProcessError:
            print("[!] Sudo privileges are required but could not be obtained.")
            sys.exit(1)

    def keep_sudo_alive():
        global shutdown_flag
        while not shutdown_flag:
            try:
                subprocess.run("sudo -v", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                time.sleep(60)
            except Exception:
                break

    threading.Thread(target=keep_sudo_alive, daemon=True).start()

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

# Silent
def log(msg, silent=False, **kwargs):
    if not silent:
        print(msg, **kwargs)

def get_search_engines():
    return {
        'brave': "https://search.brave.com/search?q=",
        'bing': "https://www.bing.com/search?q=",
        'ddg': "https://duckduckgo.com/?q=",
        'google': "https://www.google.com/search?q=",
    }

# Minimize on windows
def minimize_chrome_window(timeout=10):
    if platform.system() != 'Windows':
        return

    try:
        print("[DEBUG] Waiting for Chrome window to appear...")
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