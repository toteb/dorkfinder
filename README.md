# 🕵️‍♂️ DorkFinder — Simple Dorking Automation Tool

**DorkFinder** is a cross-platform, headless-capable* Python tool for automating Google dork-style searches across multiple engines. 
It's designed for red teamers, pentesters, and OSINT practitioners who need to search public files, assets, or misconfigured buckets quickly and quietly. 
Feel free to contibute by sending pull requests or issues.

Built by @mcn1k

---

## ✨ Features

- 🔍 Supports Google, DuckDuckGo, Bing, and Brave and can be customized to support more.
- ✅ Smart resume support (`--resume`) — continues where it left off
- 🧠 Tracks query progress per target and engine
- 🧼 Silent & debug modes for automation or analysis
- 🔁 Supports Tor integration and IP rotation
- 💾 Outputs findings per target to reusable flat files
- 💡 Supports templated dorks with `{cli}` replacement
- 🪄 Real Chrome profile usage for better detection evasion (Google only). 
	*Currently Chrome does not support headless.

---

## 🚀 Usage

```bash
python3 dorkfinder.py -t <target> [options]


### 🔧 Options

```
-t <target>        Target domain or search phrase (e.g., example.com)
-o                 Write output to dorkfinder_results_<target>.txt
-e <engine>        Search engine to use: google, ddg, bing, brave (default: google)
--sleep <seconds>  Time to sleep between queries (default: 60s)
--tor              Enable Tor routing with IP rotation
--notor            Disable Tor when resuming, even if used previously
-r                 Resume previous run for a target
-d                 Enable debug mode (verbose logs and page source)
-s                 Silent mode — suppresses non-result output
-h                 Show help menu
```

### 📂 Dork Template Format

Your `queries.txt` should contain one dork per line, using `{cli}` as a placeholder for the target.

```
site:s3.amazonaws.com "{cli}"
site:drive.google.com "{cli}"
site:pastebin.com "{cli}"
intitle:"index of" "{cli}"
site:github.com "{cli}"
```

When running with:

```
python3 dorkfinder.py -t acme
```

These are transformed into:

```
site:s3.amazonaws.com "acme"
site:drive.google.com "acme"
...
```

📑 Output
dorkfinder_results_<target>.txt
### ENGINE : GOOGLE
https://s3.amazonaws.com/somefile...
...

🔁 Resume Support
python3 dorkfinder.py -r
It will:
 • Resume the last target
 • Use previously saved sleep time and engine (unless overridden)
 • Skip completed queries per-engine

🌐 Tor Support
Enable Tor for anonymized searching:
python3 dorkfinder.py -t target.com --tor

It will:
 • Route traffic via Tor SOCKS5 proxy
 • Automatically rotate IP on CAPTCHA
 • Detect and avoid common anti-bot pages

📦 Dependencies
 • Python 3.8+
 • undetected_chromedriver
 • selenium
 • webdriver_manager
pip install -r requirements.txt

📁 Example
python3 dorkfinder.py -t tesla.com -o -e ddg --sleep 45
python3 dorkfinder.py -e --sleep 60
python3 dorkfinder.py -e --sleep 60 --tor


⚠️ Disclaimer

This tool is provided for educational and authorized security testing purposes only.
The developers assume no liability or responsibility for any misuse, damage,
or legal consequences resulting from the use of this software.

Do not deploy this tool against systems you do not own or have explicit permission to test. 
Unauthorized use is strictly prohibited.
