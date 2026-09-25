# Google Antigravity Linux Helper

A unified, self-installing launch wrapper script and auto-updater for both **Google Antigravity Hub** (`antigravity`) and **Google Antigravity IDE** (`antigravity-ide`).

Written in pure Python with zero external dependencies to ensure out-of-the-box compatibility on all mainstream Linux distributions and ChromeOS (Crostini).

## Features

- **Single Unified Script**: A single script handles both `antigravity` and `antigravity-ide` automatically using name detection (`sys.argv[0]`).
- **Heuristics-Based Auto-Update**: Scraping heuristics dynamically scan the official download website to resolve the latest releases and construct download URLs for your machine's CPU architecture (`linux-x64` or `linux-arm`).
- **Atomic Folder Swapping**: Package extraction is isolated under a temporary `.new` directory. The installation directory is updated atomically using file renames, ensuring your application is never left in a partially-downloaded or corrupt state.
- **Dynamic Path Searching**: Searches recursively within the installed files to locate binaries and logo assets, resilient to any structural changes in future releases.
- **Desktop Entry Integration**: Automatically generates `.desktop` shortcut files in `~/.local/share/applications/` (or `/usr/local/share/applications/`) so the applications immediately appear with high-quality icons in your desktop start menu (including the ChromeOS launcher).
- **Self-Updating Launcher**: Automatically checks GitHub on startup for updates to this launcher script and restarts seamlessly when a newer version is available.
- **Privileged /opt Installation & SUID Sandbox**: When `sudo` can be used (or when run with `--system`), installs globally under `/opt/` and `/usr/local/bin/` and configures `chrome-sandbox` with root SUID (4755) permissions so Chromium's full security sandbox is active out-of-the-box.
- **Keyring & Password Store Auto-Detection**: Automatically detects installed Linux desktop keyrings (`gnome-libsecret` for GNOME/libsecret/KeePassXC, `kwallet6`/`kwallet5`/`kwallet` for KDE, `basic` fallback) and configures runtime arguments (`argv.json` and `--password-store` CLI flag) to eliminate OS keyring encryption errors.
- **1-Hour Rate Limiting**: Caches application update checks for one hour to guarantee instant launches; when the cache expires the update check runs synchronously before the app starts.

---

## Quality Assurance

All QA tools must report zero issues before merging. Install them with:

```bash
uv sync --group dev
```

```bash
black --check antigravity tests/test_antigravity.py  # check formatting (use without --check to apply)
pylint antigravity tests/test_antigravity.py          # lint
pytype antigravity                                    # type-check
python -m unittest discover -s tests                 # run tests
```

---

## Installation

### Option A — Direct install (no git required)

Download and run the script in one command. It will self-install to `~/.local/bin` and create the required symlinks:

```bash
curl -sSLo /tmp/antigravity https://raw.githubusercontent.com/kzagar/antigravity-linux-helper/refs/heads/main/antigravity && python3 /tmp/antigravity --update
```

### Option B — Clone and run

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

### Disable Notifications (ChromeOS / Crostini)

On **ChromeOS** there is no system-level setting to silence Antigravity's desktop notifications. This is a problem in agent workflows because the notification banners can appear on top of and cover the interaction buttons.

The `--no-notifications` flag (or the `ANTIGRAVITY_NOTIFICATIONS=no` environment variable) works around this by wrapping the application launch in `dbus-run-session`, which gives it an isolated, transient D-Bus session so notifications never reach the real desktop session bus. This suppresses all desktop notifications without affecting any other functionality.

**One-time (current session only):**
```bash
antigravity --no-notifications
antigravity-ide --no-notifications
```

**Permanent (via environment variable — already added to `~/.bashrc` by the installer):**
```bash
export ANTIGRAVITY_NOTIFICATIONS=no
```

**Desktop launchers (start menu icons):**

The `.desktop` files generated in `~/.local/share/applications/` always include `--no-notifications` in their `Exec=` line, so launching either application from the desktop or application menu will have notifications disabled by default.

To re-enable notifications for a desktop launcher, edit the corresponding file and remove `--no-notifications` from the `Exec=` line:

```
~/.local/share/applications/antigravity.desktop
~/.local/share/applications/antigravity-ide.desktop
```

Change the line from:
```
Exec=/home/<user>/.local/bin/antigravity --no-notifications %U
```
to:
```
Exec=/home/<user>/.local/bin/antigravity %U
```

> **Note:** The `.desktop` files are regenerated on every update check. You will need to re-apply this change after each update.
 
### Password Store & Keyring Configuration

The script automatically detects the installed keyring service on your system and configures both the application runtime (`~/.antigravity-ide/argv.json`) and the launch arguments (`--password-store=...`):
- **GNOME / libsecret** (`gnome-libsecret`): Used when `gnome-keyring-daemon`, `secret-tool`, or `keepassxc` is detected, or when running under GNOME, XFCE, Cinnamon, MATE, Pantheon, or COSMIC.
- **KDE Plasma** (`kwallet6` / `kwallet5` / `kwallet`): Used when running under KDE or when `kwalletd*` is present.
- **Basic / Plaintext** (`basic`): Used as fallback in headless, containerized, or minimal window manager setups without a keyring daemon.

You can override the detected password store at any time:

**Via command line flag:**
```bash
antigravity-ide --password-store=basic
```

**Via environment variable:**
```bash
export ANTIGRAVITY_PASSWORD_STORE=gnome-libsecret
```

---

## Internals & File Paths

The script automatically selects between system-wide (`/opt`) and user-local (`~/.local`) installation paths based on privilege availability:

### System-Wide Mode (Default when `sudo` is available or `--system` is used)
- **Executables & Symlinks**:
  - Script: `/usr/local/bin/antigravity`
  - Symlink: `/usr/local/bin/antigravity-ide` -> `antigravity`
- **Application Binaries & SUID Sandbox**:
  - Hub: `/opt/antigravity/` (`/opt/antigravity/chrome-sandbox` with root SUID `4755`)
  - IDE: `/opt/antigravity-ide/` (`/opt/antigravity-ide/chrome-sandbox` with root SUID `4755`)
- **Desktop Launchers**:
  - Hub: `/usr/local/share/applications/antigravity.desktop`
  - IDE: `/usr/local/share/applications/antigravity-ide.desktop`

### User Mode (Used when `sudo` is not available or `--user` / `ANTIGRAVITY_INSTALL_MODE=user` is specified)
- **Executables & Symlinks**:
  - Script: `~/.local/bin/antigravity`
  - Symlink: `~/.local/bin/antigravity-ide` -> `antigravity`
- **Application Binaries**:
  - Hub: `~/.local/opt/antigravity/`
  - IDE: `~/.local/opt/antigravity-ide/`
- **Desktop Launchers**:
  - Hub: `~/.local/share/applications/antigravity.desktop`
  - IDE: `~/.local/share/applications/antigravity-ide.desktop`

### Configuration & Caches (Always in user home)
- **Rate-Limiting Cache**:
  - Hub: `~/.config/antigravity/last_check_antigravity`
  - IDE: `~/.config/antigravity/last_check_antigravity-ide`
- **Runtime Arguments**:
  - IDE: `~/.antigravity-ide/argv.json`
