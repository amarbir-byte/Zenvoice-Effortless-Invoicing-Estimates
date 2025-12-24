# 🌐 Local Browser Automation Agent

A **stealth, human-like browser automation framework** powered by local LLMs. This is your personal Comet/Operator that runs entirely on your PC with no cloud dependencies.

## ✨ Features

- **🤖 Local LLM Powered**: Uses LM Studio with models like Gemma 3 12B for reasoning
- **🥷 Stealth Mode**: Evades detection by MS Clarity, Hotjar, FullStory, etc.
- **🎭 Human-like Behavior**: Bezier curve mouse movements, natural typing, organic scrolling
- **👁️ Hybrid Perception**: Combines DOM extraction with vision/OCR for robust element detection
- **🔒 Privacy First**: Everything runs locally - no data leaves your machine
- **🚀 No WebDriver Flags**: Uses Chrome DevTools Protocol without automation detection

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       YOUR PC (Local)                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐      ┌───────────────────────────────────┐│
│  │  LM Studio  │◄────►│         Agent Orchestrator        ││
│  │  Gemma 3    │      │  ┌─────────┐  ┌────────────────┐  ││
│  │  12B        │      │  │   LLM   │  │ Action Parser  │  ││
│  └─────────────┘      │  │ Client  │  │                │  ││
│                       │  └─────────┘  └────────────────┘  ││
│                       └──────────────────┬────────────────┘│
│                                          │                  │
│                       ┌──────────────────▼────────────────┐│
│                       │     Human Simulation Layer        ││
│                       │  ┌──────────┐  ┌──────────────┐   ││
│                       │  │  Mouse   │  │  Keyboard    │   ││
│                       │  │ (Bezier) │  │ (Natural)    │   ││
│                       │  └──────────┘  └──────────────┘   ││
│                       └──────────────────┬────────────────┘│
│                                          │                  │
│                       ┌──────────────────▼────────────────┐│
│                       │         Perception Layer          ││
│                       │  ┌──────────┐  ┌──────────────┐   ││
│                       │  │   DOM    │  │   Vision     │   ││
│                       │  │Extractor │  │   (OCR)      │   ││
│                       │  └──────────┘  └──────────────┘   ││
│                       └──────────────────┬────────────────┘│
│                                          │                  │
│  ┌─────────────┐      ┌──────────────────▼────────────────┐│
│  │   Chrome    │◄────►│          CDP Bridge               ││
│  │  Browser    │      │    (No webdriver flag!)           ││
│  └─────────────┘      └───────────────────────────────────┘│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 📋 Prerequisites

1. **Python 3.11+**
2. **Google Chrome** (latest version)
3. **LM Studio** with a model loaded (e.g., Gemma 3 12B, Llama 3, Mistral)

## 🚀 Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/browser-agent.git
cd browser-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Optional: Install OCR support
pip install easyocr  # Recommended for vision features
# OR
pip install pytesseract  # Lighter alternative (requires tesseract-ocr)
```

## ⚙️ Configuration

### 1. Start LM Studio

1. Download and install [LM Studio](https://lmstudio.ai/)
2. Load a model (recommended: Gemma 3 12B, Llama 3 8B, or Mistral 7B)
3. Start the local server (default: `http://localhost:1234`)

### 2. Environment Variables (Optional)

```bash
export LM_STUDIO_URL="http://localhost:1234/v1"
export LM_STUDIO_MODEL="gemma-3-12b"
export CHROME_PATH="/path/to/chrome"  # Only if not auto-detected
```

## 📖 Usage

### Check Prerequisites

```bash
python main.py --check
```

### Run a Task

```bash
# Simple task
python main.py --task "Search for Python tutorials on Google"

# With starting URL
python main.py --url "https://google.com" --task "Search for machine learning courses"

# Fill a form
python main.py --url "https://example.com/contact" --task "Fill the contact form with name John Doe and email john@example.com"
```

### Interactive Mode

```bash
python main.py --interactive
```

In interactive mode:
- Type tasks naturally: `"Click on the login button"`
- Navigate: `"go to https://github.com"` or just paste a URL
- Type `quit` to exit

### Demo Mode

```bash
python main.py --demo
```

## 🎮 Task Examples

```bash
# Web search
python main.py -t "Search for 'best Python frameworks 2024'"

# Form filling
python main.py -u "https://example.com/signup" -t "Create an account with email test@example.com"

# Navigation
python main.py -u "https://github.com" -t "Navigate to the trending repositories page"

# Data extraction
python main.py -u "https://news.ycombinator.com" -t "Scroll through and read the top 5 article titles"
```

## 🥷 Anti-Detection Features

This agent is designed to evade common analytics and bot detection tools:

| Detection Vector | Mitigation |
|-----------------|------------|
| `navigator.webdriver` | Removed via CDP injection |
| Mouse patterns | Bezier curve movements with Perlin noise |
| Click patterns | Randomized coordinates within elements |
| Typing cadence | Gaussian-distributed delays, occasional typos |
| Scroll behavior | Gradual scrolling with natural pauses |
| CDP detection | Stealth patches applied |
| Headless detection | Real Chrome window (not headless) |

## 📁 Project Structure

```
├── config/
│   ├── __init__.py
│   └── settings.py          # Configuration dataclasses
├── src/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── llm.py            # LM Studio integration
│   │   ├── actions.py        # Action definitions
│   │   └── orchestrator.py   # Main agent loop
│   ├── browser/
│   │   ├── __init__.py
│   │   ├── cdp_client.py     # Chrome DevTools Protocol
│   │   └── controller.py     # Browser lifecycle
│   ├── dom/
│   │   ├── __init__.py
│   │   ├── elements.py       # Element data structures
│   │   └── extractor.py      # DOM extraction
│   ├── human/
│   │   ├── __init__.py
│   │   ├── mouse.py          # Human-like mouse movement
│   │   ├── keyboard.py       # Natural typing
│   │   └── timing.py         # Delay distributions
│   └── vision/
│       ├── __init__.py
│       ├── screenshot.py     # Screenshot capture
│       └── processor.py      # OCR and image analysis
├── main.py                   # CLI entry point
├── requirements.txt
└── README.md
```

## 🔧 Programmatic Usage

```python
import asyncio
from src.agent.orchestrator import create_agent, TaskConfig

async def main():
    # Create agent
    browser, llm, agent = await create_agent(
        lm_studio_url="http://localhost:1234/v1",
        model="gemma-3-12b",
    )

    try:
        # Navigate to a page
        await browser.navigate("https://google.com")

        # Run a task
        result = await agent.run_task(
            task="Search for Python tutorials",
            config=TaskConfig(
                max_actions=30,
                verbose=True,
            ),
        )

        if result.success:
            print(f"Task completed in {result.duration:.1f}s")
        else:
            print(f"Task failed: {result.message}")

    finally:
        await browser.stop()
        await llm.close()

asyncio.run(main())
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## ⚠️ Disclaimer

This tool is for legitimate automation purposes only. Please:
- Respect website terms of service
- Don't use for malicious purposes
- Be mindful of rate limits
- Use responsibly

## 📄 License

MIT License - see LICENSE file for details.
