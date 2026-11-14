# DesktopKeeper

Automatic desktop organizer for macOS and Windows, with initial Linux support.

![Build Status](https://github.com/sap112233/Clear_My_PC/actions/workflows/build.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
[![Stars](https://img.shields.io/github/stars/sap112233/Clear_My_PC?style=social)](https://github.com/sap112233/Clear_My_PC)
[![Forks](https://img.shields.io/github/forks/sap112233/Clear_My_PC?style=social)](https://github.com/sap112233/Clear_My_PC)
[![Issues](https://img.shields.io/github/issues/sap112233/Clear_My_PC)](https://github.com/sap112233/Clear_My_PC/issues)

## Features

### 🖼️ Smart Screenshot Management
- Automatically renames screenshots with meaningful names (application name + window title + timestamp)
- Moves screenshots to a dedicated folder with clean naming convention
- Real-time monitoring: each new screenshot is previewed and requires approval before moving
- Optional retention timer moves expired screenshots to a private, reversible archive (disabled by default)
- Optional background monitoring can notify about detected new apps/installers after permission is enabled; detected items are revalidated before follow-up
- Optional installer timer starts only after a matching newly installed app is detected and moves the installer to the reversible archive

### 📁 Intelligent File Organization
- Sorts files by type into categorized folders (Images, Graphic Projects, Videos, Documents, Code, Archives, etc.)
- Keeps SVG and common vector/design project files in a separate Graphic Projects folder
- Choose automatic Desktop folders or select separate destination folders inside your user home
- Protect selected folders so scans, moves, and rollbacks leave them untouched
- Enable only the file types you want, or add custom extension-to-folder rules
- Prevents path traversal and avoids overwriting existing destinations

### 🔗 Application Shortcuts by Category
- Creates shortcuts/aliases for applications organized by category (Browsers, Social, Programming, Games, etc.)
- Scans nested application groups inside standard macOS Applications folders and nested Windows Start Menu folders
- Assign categories to installed applications and adjust individual choices in the action preview
- Search and filter installed applications, assign categories or favorite folders in bulk, and preview each exact shortcut destination
- Choose an individual shortcut folder for an app or exclude it from future scans; custom folders must stay inside your home folder
- Reclassify existing shortcuts through a previewed, reversible move
- Remembers application category choices for future scans
- Organizes shortcuts only; installed application bundles are never moved

### 🧰 Work Profiles
- Create named profiles containing installed applications and websites
- Start a profile with one click to launch its apps and open its links in your default browser
- Optionally arrange the profile's app windows side by side, in a 1/3 + 2/3 split, or in a 2×2 grid
- Window arrangement affects only matched profile apps; macOS may require Accessibility permission, and Linux requires X11 with `wmctrl`
- Profiles are saved locally and can be edited or deleted at any time

### 🗑️ Automatic Cleanup
- Finds common installers (.dmg, .pkg, .exe, .msi, .deb, .rpm, .AppImage, .zip)
- Moves installers to a private, reversible quarantine instead of deleting them
- Selectively rolls back individual actions or all reversible recorded changes

### 🖥️ Cross-Platform
- **macOS**: Full integration with Finder aliases, AppleScript automation, LaunchAgent for autostart
- **Windows**: Native shortcuts (.lnk), Registry-based autostart, PowerShell notifications
- **Linux (initial support)**: Scans standard XDG application-entry folders, creates categorized `.desktop` launcher copies, supports XDG autostart, and uses `notify-send` for system notifications when installed. System screenshot-location integration is not yet available.

## Installation

### Download
Grab the latest release for your platform:
- **Windows**: `DesktopKeeper.exe` (single executable, no Python required)
- **macOS**: `DesktopKeeper.app` or `DesktopKeeper` (standalone binary)
- **Linux**: `DesktopKeeper-Linux.tar.gz` (built on Ubuntu 22.04; extract and run `DesktopKeeper`. Compatibility with older distributions depends on their system libraries. System screenshot-location integration is not available.)

Download from [Releases](https://github.com/sap112233/Clear_My_PC/releases)

### First Run
1. Launch the application
2. Follow the onboarding wizard, choose a screenshot destination, or leave screenshots in place
   (destination folders are created only after you confirm an action)
3. Grant necessary permissions:
   - **macOS**: Allow access to Desktop, Downloads, and Automation
   - **Windows**: Allow through SmartScreen if prompted
4. Click "Scan System" to preview proposed actions
5. Review and apply selected actions
6. Enable "Background monitoring" only if you want DesktopKeeper to watch existing Desktop, Downloads, and application directories. The app asks before enabling and saves this permission for next launch; autostart is a separate opt-in.

Installer auto-archiving is disabled by default. Choose a delay in Settings; after a newly detected app matches a downloaded installer, that installer is moved to the private reversible archive when the delay expires. Protected folders, missing files, and installers no longer matching an installed app are skipped. The automatic match uses the installer filename and app display name; it is deliberately conservative and cannot prove which installer actually installed an app.

### Platform and monitoring limitations
- Background watching is opt-in and runs only while DesktopKeeper is running in the signed-in user's session. It is not a system daemon and cannot watch while the computer is off, the user is logged out, or the app is closed. Enable autostart separately if you want it to start at login.
- Monitoring covers existing standard Desktop, Downloads, and OS application/Start Menu locations. It does not observe every package manager, browser cache, custom install path, removable drive, or application registry. A notification is best-effort, not proof that an installation completed.
- New app detection is based on supported launchers/bundles: macOS `.app` bundles, Windows Start Menu `.lnk` shortcuts, and Linux XDG `.desktop` entries. Apps installed outside those locations may not be detected.
- Screenshot detection watches the Desktop and configured screenshot destination and recognizes common filename prefixes and image extensions. It cannot reliably identify screenshots saved elsewhere or screenshots with custom names.
- Linux screenshot save-location control varies by desktop environment and capture app and is not changed by DesktopKeeper. Linux app organization is initial XDG `.desktop` support; `notify-send` and `gio` must be available for their respective integrations.
- Installer timers move matching files only into the local reversible archive; they do not uninstall applications or permanently erase files. Keep the timer off if filename-based matching is not appropriate for your installers.

## Usage

### Main Interface
- **Scan System**: Shows progress while preparing proposed actions grouped by type
- **Apply**: Shows concrete source and destination paths, then executes checked actions after confirmation and revalidates the paths
- **Theme**: Switch between light and dark mode; your choice is saved
- **Rollback Actions**: Restores selected files or all reversible recorded changes; generated shortcuts are archived, not permanently deleted
- **Monitoring**: Preview and approve each new screenshot before it is moved
- **Autostart**: Launch DesktopKeeper on system boot
- **Folders and Types**: Select destinations, enable file groups, and define custom extension rules
- **Work Profiles**: Create or edit profiles, choose installed apps, add `http://` or `https://` websites, optionally choose a window layout, and launch the selected set together. Unsupported window control or missing permissions are reported without preventing the profile from launching.

### Categories
- Add custom categories for applications
- Use **Applications** to search and filter apps, select several at once, assign categories or favorite folders, choose per-app shortcut folders, and exclude apps from scanning
- Shortcut-folder changes appear with their full destination in the next action preview; installed application bundles are never moved
- Editable through GUI or `config.json`

### Work Profiles
- Open **Work Profiles** and create a named profile
- Select applications from the installed-app list and add websites with their full `https://` or `http://` addresses
- Use **Launch** to open every selected app and site; if an item is unavailable, the app reports it while continuing with the rest
- Profiles are stored in the local `work_profiles` setting in `config.json`

### Configuration
Settings are stored in:
- **macOS**: `~/.desktop-keeper/config.json`
- **Windows**: `%USERPROFILE%\.desktop-keeper\config.json`
- **Linux**: `~/.desktop-keeper/config.json`

You can customize:
- Automatic Desktop folder names or separate destinations inside your user home folder
- Enabled features
- Enabled file groups and custom extension-to-folder mappings
- Application categories

The local history, configuration, and quarantine are stored in `~/.desktop-keeper`
with restricted permissions on supported systems. Corrupt history files are reported
instead of silently replaced. CLI operations display their proposed changes and ask
for confirmation before applying them.

## Updates

DesktopKeeper checks for updates once per day. When a new version is available, you'll receive a system notification with a link to download.

## Development

### Requirements
- Python 3.9+
- `pip install -r requirements.txt`

### Run Locally
```bash
git clone https://github.com/sap112233/Clear_My_PC.git
cd Clear_My_PC
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python gui.py
```

### Build from Source
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name DesktopKeeper gui.py
```

### GitHub Actions
The repository includes automated CI/CD:
- Every push triggers builds for Windows (.exe), macOS (.app), and Linux (tar.gz)
- Releases are created automatically with version tags
- Binaries are uploaded to GitHub Releases

## Project Structure
```
desktop-keeper/
├── gui.py                  # Main GUI (CustomTkinter)
├── app_handler.py          # Application detection and shortcuts
├── screenshot_handler.py   # Screenshot processing
├── file_sorter.py          # File type sorting
├── organization.py         # Destination validation and classification rules
├── platform_tools.py       # Cross-platform utilities
├── updater.py              # GitHub Releases update checker
├── version.py              # Current version
├── requirements.txt        # Dependencies
└── .github/workflows/      # CI/CD configuration
```

## Privacy
- All data is stored locally on your machine
- No telemetry or data collection
- Update checks only query GitHub API for version information
- Configuration files are user-editable and never sent anywhere

## Contributing
Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md)
for development and review guidance, and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
for community expectations. Please report security vulnerabilities using
[SECURITY.md](SECURITY.md), not a public issue. Accessibility barriers can be
reported as described in [ACCESSIBILITY.md](ACCESSIBILITY.md).

## License
MIT License - see [LICENSE](LICENSE) file for details.

---

**Status**: 🚧 Early development — first public release. Feedback appreciated!

**Author**: [@sap112233](https://github.com/sap112233)