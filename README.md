# DesktopKeeper

Automatic desktop organizer for macOS and Windows that keeps your workspace clean without manual effort.

![Build Status](https://github.com/sap112233/Clear_My_PC/actions/workflows/build.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Features

### 🖼️ Smart Screenshot Management
- Automatically renames screenshots with meaningful names (application name + window title + timestamp)
- Moves screenshots to a dedicated folder with clean naming convention
- Real-time monitoring: new screenshots are processed instantly

### 📁 Intelligent File Organization
- Sorts files by type into categorized folders (Images, Videos, Documents, Code, Archives, etc.)
- Customizable folder structure and file type mappings
- Preserves folder hierarchy and prevents conflicts

### 🔗 Application Shortcuts by Category
- Creates shortcuts/aliases for applications organized by category (Browsers, Social, Programming, Games, etc.)
- Interactive categorization for unknown applications
- Remembers your preferences for future use

### 🗑️ Automatic Cleanup
- Removes installers (.dmg, .pkg, .exe, .msi) after successful installation
- Sends files to system Trash (safe and reversible)
- Undo functionality: restore files from the last cleanup operation

### 🖥️ Cross-Platform
- **macOS**: Full integration with Finder aliases, AppleScript automation, LaunchAgent for autostart
- **Windows**: Native shortcuts (.lnk), Registry-based autostart, PowerShell notifications

## Installation

### Download
Grab the latest release for your platform:
- **Windows**: `DesktopKeeper.exe` (single executable, no Python required)
- **macOS**: `DesktopKeeper.app` or `DesktopKeeper` (standalone binary)

Download from [Releases](https://github.com/sap112233/Clear_My_PC/releases)

### First Run
1. Launch the application
2. Follow the onboarding wizard (4 steps)
3. Grant necessary permissions:
   - **macOS**: Allow access to Desktop, Downloads, and Automation
   - **Windows**: Allow through SmartScreen if prompted
4. Click "Scan System" to preview proposed actions
5. Review and apply selected actions

## Usage

### Main Interface
- **Scan System**: Analyzes desktop, downloads, and installed applications
- **Apply Selected**: Executes only checked actions with confirmation
- **Undo Last**: Reverts files moved in the previous cleanup
- **Monitoring**: Toggle real-time screenshot processing
- **Autostart**: Launch DesktopKeeper on system boot

### Categories
- Add custom categories for applications
- Interactive prompts for uncategorized apps
- Editable through GUI or `config.json`

### Configuration
Settings are stored in:
- **macOS**: `~/.desktop-keeper/config.json`
- **Windows**: `%USERPROFILE%\.desktop-keeper\config.json`

You can customize:
- Folder names (Trash, Apps, Files)
- Enabled features
- File type mappings
- Application categories

## Updates

DesktopKeeper checks for updates once per day. When a new version is available, you'll receive a system notification with a link to download.

## Development

### Requirements
- Python 3.12+
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
- Every push triggers builds for Windows (.exe) and macOS (.app)
- Releases are created automatically with version tags
- Binaries are uploaded to GitHub Releases

## Project Structure
```
desktop-keeper/
├── gui.py                  # Main GUI (CustomTkinter)
├── app_handler.py          # Application detection and shortcuts
├── screenshot_handler.py   # Screenshot processing
├── file_sorter.py          # File type sorting
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
This is an early-stage project. Issues and pull requests are welcome!

## License
MIT License - see [LICENSE](LICENSE) file for details.

---

**Status**: 🚧 Early development — first public release. Feedback appreciated!

**Author**: [@sap112233](https://github.com/sap112233)