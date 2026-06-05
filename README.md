# Google Antigravity Linux Helper

A unified, self-installing launch wrapper script and auto-updater for both **Google Antigravity Hub** (`antigravity`) and **Google Antigravity IDE** (`antigravity-ide`).

Written in pure Python with zero external dependencies to ensure out-of-the-box compatibility on all mainstream Linux distributions and ChromeOS (Crostini).

## Features

- **Single Unified Script**: A single script handles both `antigravity` and `antigravity-ide` automatically using name detection (`sys.argv[0]`).
- **Heuristics-Based Auto-Update**: Scraping heuristics dynamically scan the official download website to resolve the latest releases and construct download URLs for your machine's CPU architecture (`linux-x64` or `linux-arm`).
- **Atomic Folder Swapping**: Package extraction is isolated under a temporary `.new` directory. The installation directory is updated atomically using file renames, ensuring your application is never left in a partially-downloaded or corrupt state.
- **Dynamic Path Searching**: Searches recursively within the installed files to locate binaries and logo assets, resilient to any structural changes in future releases.
- **Desktop Entry Integration**: Automatically generates `.desktop` shortcut files in `~/.local/share/applications/` so the applications immediately appear with high-quality icons in your desktop start menu (including the ChromeOS launcher).
- **1-Hour Rate Limiting**: Caches update checks for one hour to guarantee sub-millisecond local launch times, while still checking for new versions regularly in the background.

---

## Installation

### 1. Bootstrap Setup

Clone this repository and run the launcher script once with the `--update` flag. This will self-install the script to `~/.local/bin` and create the required symlinks:

```bash
git clone https://github.com/kzagar/antigravity-linux-helper.git
cd antigravity-linux-helper
./antigravity --update
```

### 2. Verify Your Environment Path

Make sure `~/.local/bin` is in your environment's `PATH`. If it isn't, add the following line to your shell configuration file (e.g., `~/.bashrc` or `~/.zshrc`):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Apply the changes to your current terminal session:

```bash
source ~/.bashrc
```

---

## Usage

Once bootstrapped, you can run the applications from anywhere in your terminal or click their icons in your desktop's start menu.

### Launch Google Antigravity Hub
```bash
antigravity
```

### Launch Google Antigravity IDE
```bash
antigravity-ide
```

### Force an Update Check
By default, the script checks for updates at most once per hour. You can bypass the rate limit and force an immediate update check by passing the `--update` flag:

```bash
antigravity --update
antigravity-ide --update
```
*(The `--update` flag updates the respective application in the background and exits immediately without launching the GUI)*

---

## Internals & File Paths

The script organizes itself inside the user's home directory space to prevent the need for `sudo`/root privileges:

- **Executables & Symlinks**:
  - Script: `~/.local/bin/antigravity`
  - Symlink: `~/.local/bin/antigravity-ide` -> `antigravity`
- **Application Binaries**:
  - Hub: `~/.local/opt/antigravity/`
  - IDE: `~/.local/opt/antigravity-ide/`
- **Desktop Launchers**:
  - Hub: `~/.local/share/applications/antigravity.desktop`
  - IDE: `~/.local/share/applications/antigravity-ide.desktop`
- **Rate-Limiting Cache**:
  - Hub: `~/.config/antigravity/last_check_antigravity`
  - IDE: `~/.config/antigravity/last_check_antigravity-ide`
