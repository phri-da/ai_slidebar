# AI Slidebar 🚀

A sleek, auto-hiding sidebar for Windows that provides instant access to multiple AI chat services.

![Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-blue)
![Python](https://img.shields.io/badge/Python-3.10%2B-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## ✨ Features

- **Auto-Hide Sidebar** - Slides in from the screen edge when you move your cursor there
- **Multi-Monitor Support** - Works seamlessly across multiple displays
- **12 AI Services** - Quick access to:
  - ChatGPT
  - Claude
  - Gemini
  - Perplexity
  - Grok
  - Pi
  - HuggingChat
  - Mistral
  - Poe
  - Microsoft Copilot
  - Claude Code
  - You.com
- **Quick Prompts** - Save and inject frequently used prompts with one click
- **Customizable** - Choose which 3 AI services to display, adjust zoom, switch monitors
- **Pin Mode** - Keep the sidebar visible when needed
- **Dark/Light Mode** - Toggle UI theme to your preference
- **DPI Aware** - Crisp display on high-resolution monitors

## 📥 Installation (For Users)

### Option 1: Download the EXE (Easiest)
1. Go to [Releases](../../releases) and download `AI_Slidebar.zip`
2. Extract the ZIP to a dedicated folder (e.g., `C:\Tools\AI-Slidebar\`)
3. Run `AI_Slidebar.exe`

> ⚠️ **Important:** Do NOT run the EXE directly from your Downloads folder. The app creates configuration files in its directory.

### Option 2: Run from Source
See [For Developers](#-for-developers) section below.

## 🖥️ System Requirements

- **OS:** Windows 10 (version 1809+) or Windows 11
- **Runtime:** Microsoft Edge WebView2 Runtime (pre-installed on most systems)
- **RAM:** ~100MB
- **Disk:** ~50MB

## 🎮 How to Use

1. **Trigger the Sidebar:** Move your cursor to the right edge of your screen
2. **Switch AI Services:** Click the buttons at the top (ChatGPT, Claude, Gemini)
3. **Use Quick Prompts:** Select a prompt from the dropdown and click ▶ to inject it
4. **Pin the Sidebar:** Click 📌 to keep it visible
5. **Settings:** Click ⚙ to:
   - Change monitor
   - Switch sidebar side (left/right)
   - Adjust zoom level
   - Configure which AI services to show
   - Manage your prompt library

## 🛡️ Security & Transparency

### Why does Windows Defender show a warning?
The EXE is not digitally signed (code signing certificates cost ~$200-400/year). This triggers a "Windows protected your PC" message.

**To run anyway:**
1. Click "More info"
2. Click "Run anyway"

### Why you can trust this tool:
- ✅ **100% Open Source** - All code is visible in this repository
- ✅ **No Telemetry** - Zero data collection, no analytics, no tracking
- ✅ **No Network Calls** - Only connects to the AI services YOU choose to use
- ✅ **Local Storage Only** - Settings saved locally in JSON files
- ✅ **Verifiable Build** - You can compile the EXE yourself from source

### File Integrity (SHA-256)
Check the [Releases](../../releases) page for the SHA-256 hash of each release to verify your download.

## 🛠️ For Developers

### Prerequisites
- Python 3.10 or higher
- Windows 10/11

### Setup
```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/ai-slidebar.git
cd ai-slidebar

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run from source
python ai_slidebar.py
```

### Building the EXE
```bash
# Install PyInstaller
pip install pyinstaller

# Build using the spec file
pyinstaller AI_Slidebar.spec

# The EXE will be in the dist/AI_Slidebar/ folder
```

## 📁 Project Structure

```
ai-slidebar/
├── ai_slidebar.py        # Main application source code
├── AI_Slidebar.spec      # PyInstaller build configuration
├── requirements.txt      # Python dependencies
├── README.md             # This file
├── LICENSE               # MIT License
├── CHANGELOG.md          # Version history
└── .gitignore            # Git ignore rules
```

## 📝 Configuration Files

The app creates these files in its directory on first run:

| File | Purpose |
|------|---------|
| `ai_slidebar_settings.json` | User preferences (monitor, zoom, selected LLMs) |
| `ai_prompts.json` | Your saved quick prompts |
| `ai_slidebar.log` | Debug log (useful for troubleshooting) |

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Report bugs via [Issues](../../issues)
- Suggest features
- Submit pull requests

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This tool is a wrapper that provides convenient access to third-party AI services. You must comply with each service's terms of use. The author is not affiliated with OpenAI, Anthropic, Google, or any other AI provider.

---

**Made with ❤️ for the AI community**
