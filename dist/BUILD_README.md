# Knowledge-Base Distribution

## Quick Start

### Option 1: Using PowerShell

1. Run setup (first time only):
   `powershell
   .\setup.ps1
   `

2. Start the server:
   `powershell
   .\run.ps1
   `

### Option 2: Using Command Prompt

1. Run setup (first time only):
   `cmd
   setup.ps1
   `
   Or use PowerShell to run setup first

2. Start the server:
   `cmd
   run.bat
   `

## Requirements

- Python 3.8 or later
- Windows 7/8/10/11 or Server 2016+

## Configuration

Edit config.json to configure:
- Database settings (MySQL/PostgreSQL)
- Redis session store
- Model paths and cache
- Chat model settings
- LM Studio connection

## Server Access

Once started, the server listens on: http://127.0.0.1:5000

- Web UI: http://127.0.0.1:5000/ui/
- API Docs: http://127.0.0.1:5000/docs/

## Project Structure

`
├── src/                  # Source code
├── web/                  # Web UI files
├── config.json          # Configuration file
├── requirements.txt     # Python dependencies
├── run.ps1             # PowerShell startup script
├── run.bat             # Command prompt startup script
└── setup.ps1           # Setup/initialization script
`

## Troubleshooting

### Virtual Environment Issues
- Ensure Python is in PATH: python --version
- Delete .venv folder and run setup.ps1 again

### Dependencies
- If pip install fails, check internet connection
- Try: pip install --upgrade pip

### Port Already in Use
- Edit config.json to change the port
- Or stop other applications using port 5000

## Support

For more information, see README.md and docs/ directory.
