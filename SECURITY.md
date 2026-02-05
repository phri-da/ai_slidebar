# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in AI Slidebar, please report it responsibly:

1. **Do NOT** open a public GitHub issue for security vulnerabilities
2. Send a detailed report to [your-email@example.com] or use GitHub's private vulnerability reporting
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Security Design

### What this tool does:
- Displays AI chat services in an embedded web view
- Stores user preferences locally in JSON files
- Injects user-defined prompts into chat input fields

### What this tool does NOT do:
- ❌ Collect or transmit any user data
- ❌ Access files outside its directory (except system DLLs)
- ❌ Run with elevated privileges
- ❌ Modify system settings
- ❌ Install any background services
- ❌ Connect to any servers other than the AI services you choose

### Data Storage
All data is stored locally in the application directory:
- `ai_slidebar_settings.json` - User preferences
- `ai_prompts.json` - Saved prompts
- `ai_slidebar.log` - Debug logs

No data is encrypted as it contains no sensitive information. Your AI service credentials are handled entirely by the embedded browser (Edge WebView2) and are never accessible to this application.

## Verifying the EXE

To verify the integrity of downloaded releases:

1. Download the EXE and note the SHA-256 hash from the release page
2. Open PowerShell and run:
   ```powershell
   Get-FileHash -Algorithm SHA256 "path\to\AI_Slidebar.exe"
   ```
3. Compare the output with the hash on the release page

## Building from Source

For maximum security, you can build the EXE yourself:

```bash
git clone https://github.com/YOUR_USERNAME/ai-slidebar.git
cd ai-slidebar
pip install -r requirements.txt
pip install pyinstaller
pyinstaller AI_Slidebar.spec
```

This ensures the executable matches the source code exactly.
