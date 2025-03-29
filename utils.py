import platform
import os
import sys
import time
import subprocess
import shutil
import requests
import threading

shutdown_flag = False

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

# check if tor is installed.
def is_tor_installed():
    if platform.system() == 'Windows':
        return shutil.which("tor") is not None
    else:
        return shutil.which("tor") is not None or os.path.exists("/usr/bin/tor")


def rotate_tor_ip():
    import socket
    import socks
    import requests

    try:
        with socket.create_connection(("127.0.0.1", 9051)) as s:
            s.send(b'AUTHENTICATE\r\n')
            s.send(b'SIGNAL NEWNYM\r\n')
            s.send(b'QUIT\r\n')
    except Exception as e:
        print(f"[!] Failed to rotate Tor IP: {e}")


# Start tor
def start_tor():
    if not is_tor_installed():
        print("[!] Tor is not installed. Please install Tor before using this feature.")
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
            subprocess.run(["systemctl", "start", "tor"], check=True)
            print("[INFO] Tor service started.")
            return True
    except Exception as e:
        print(f"[!] Failed to start Tor: {e}")
        return False

# stop tor
def stop_tor():
    try:
        if platform.system() == 'Windows':
            global tor_process
            if tor_process:
                tor_process.terminate()
                tor_process.wait()
                print("[INFO] Tor process terminated.")
        else:
            # Refresh sudo session to avoid password prompt
            subprocess.run("sudo -v", shell=True, check=True)
            subprocess.run(["sudo", "systemctl", "stop", "tor"], check=True)
            print("[INFO] Tor service stopped.")
    except Exception as e:
        print(f"[!] Failed to stop Tor: {e}")


def get_current_tor_ip():
    try:
        response = requests.get("https://api.ipify.org", proxies={
            'http': 'socks5h://127.0.0.1:9050',
            'https': 'socks5h://127.0.0.1:9050'
        }, timeout=10)

        if response.status_code == 200:
            return response.text.strip()
        else:
            return "Unknown (non-200 response)"
    except Exception as e:
        return f"Error retrieving IP: {e}"

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
        print("[INFO] Waiting for Chrome window to appear...")
        from pywinauto import Desktop
        for _ in range(timeout * 2):
            try:
                
                windows = Desktop(backend="uia").windows()
                for win in windows:
                    if "chrome" in win.window_text().lower():
                        win.minimize()
                        print("[INFO] Chrome window minimized.")
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
        print("[INFO] Chrome minimize keystroke sent (macOS).")

    except Exception as e:
        print(f"[!] Failed to minimize Chrome on macOS: {e}")

#Minimize on Linux
def minimize_chrome_linux():
    if platform.system() != "Linux":
        return

    try:
        subprocess.run(["wmctrl", "-r", "Google Chrome", "-b", "add,hidden"])
        print("[INFO] Chrome window minimized (Linux).")

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