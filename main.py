#!/usr/bin/env python3
"""
Local Browser Automation Agent
A stealth, human-like browser automation framework powered by local LLMs.

Usage:
    python main.py --task "Search for Python tutorials on Google"
    python main.py --url "https://example.com" --task "Fill out the contact form"
    python main.py --interactive

Requirements:
    - LM Studio running locally with a model loaded
    - Google Chrome installed
    - Python 3.11+
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config import config, load_config_from_env
from src.browser.controller import BrowserController
from src.agent.llm import LMStudioClient
from src.agent.orchestrator import AgentOrchestrator, TaskConfig, create_agent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent")


def print_banner():
    """Print startup banner."""
    banner = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   🌐 Local Browser Automation Agent                              ║
║   ─────────────────────────────────────────────────────────      ║
║   Human-like browsing powered by local LLMs                      ║
║   Stealth mode: Evades MS Clarity, Hotjar, etc.                  ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""
    print(banner)


async def check_prerequisites():
    """Check that all prerequisites are met."""
    issues = []

    # Check LM Studio
    llm = LMStudioClient(
        base_url=config.lm_studio.base_url,
        model=config.lm_studio.model,
    )

    print("Checking LM Studio connection...", end=" ")
    if await llm.check_health():
        models = await llm.list_models()
        print(f"OK ({len(models)} models available)")
        if models:
            print(f"  Available models: {', '.join(models[:5])}")
    else:
        print("FAILED")
        issues.append(
            f"LM Studio not available at {config.lm_studio.base_url}. "
            "Please start LM Studio and load a model."
        )

    await llm.close()

    # Check Chrome
    print("Checking Chrome installation...", end=" ")
    browser = BrowserController()
    try:
        chrome_path = browser.chrome_path
        if Path(chrome_path).exists() or chrome_path == "chrome":
            print(f"OK ({chrome_path})")
        else:
            print("FAILED")
            issues.append("Chrome not found. Please install Google Chrome.")
    except FileNotFoundError as e:
        print("FAILED")
        issues.append(str(e))

    if issues:
        print("\n⚠️  Prerequisites not met:")
        for issue in issues:
            print(f"  • {issue}")
        return False

    print("\n✅ All prerequisites met!")
    return True


async def run_task(
    task: str,
    url: str = None,
    max_actions: int = 50,
    verbose: bool = True,
):
    """Run a single automation task."""
    browser = None
    llm = None

    try:
        # Create agent
        browser, llm, agent = await create_agent(
            lm_studio_url=config.lm_studio.base_url,
            model=config.lm_studio.model,
        )

        # Navigate to URL if provided
        if url:
            print(f"\n📍 Navigating to: {url}")
            await browser.navigate(url)
            await asyncio.sleep(2)  # Wait for page load

        # Run task
        print(f"\n🎯 Task: {task}")
        print("─" * 60)

        task_config = TaskConfig(
            max_actions=max_actions,
            verbose=verbose,
            screenshot_on_action=True,
            use_vision=True,
            use_dom=True,
            on_action=lambda action, result: print(
                f"  {'✓' if result.success else '✗'} {action}"
            ),
        )

        result = await agent.run_task(task, task_config)

        print("─" * 60)

        if result.success:
            print(f"\n✅ Task completed successfully!")
            print(f"   Actions taken: {result.actions_taken}")
            print(f"   Duration: {result.duration:.1f}s")
            print(f"   Final URL: {result.final_url}")
        else:
            print(f"\n❌ Task failed: {result.message}")
            print(f"   Actions taken: {result.actions_taken}")
            print(f"   Duration: {result.duration:.1f}s")

        return result

    finally:
        if browser:
            await browser.stop()
        if llm:
            await llm.close()


async def interactive_mode():
    """Run in interactive mode."""
    print("\n🎮 Interactive Mode")
    print("Type tasks to execute, 'quit' to exit\n")

    browser = None
    llm = None
    agent = None

    try:
        # Create agent
        browser, llm, agent = await create_agent(
            lm_studio_url=config.lm_studio.base_url,
            model=config.lm_studio.model,
        )

        while True:
            try:
                # Get task from user
                task = input("\n🎯 Enter task (or 'quit'): ").strip()

                if task.lower() in ('quit', 'exit', 'q'):
                    print("Goodbye!")
                    break

                if not task:
                    continue

                # Check for URL navigation
                if task.lower().startswith("go to ") or task.lower().startswith("navigate to "):
                    url = task.split(" ", 2)[-1]
                    print(f"📍 Navigating to: {url}")
                    await browser.navigate(url)
                    continue

                if task.lower().startswith("http"):
                    print(f"📍 Navigating to: {task}")
                    await browser.navigate(task)
                    continue

                # Run task
                print("─" * 60)

                task_config = TaskConfig(
                    max_actions=30,
                    verbose=True,
                    on_action=lambda action, result: print(
                        f"  {'✓' if result.success else '✗'} {action}"
                    ),
                )

                result = await agent.run_task(task, task_config)

                print("─" * 60)

                if result.success:
                    print(f"✅ Done! ({result.actions_taken} actions, {result.duration:.1f}s)")
                else:
                    print(f"❌ Failed: {result.message}")

            except KeyboardInterrupt:
                print("\n\nInterrupted. Type 'quit' to exit.")
                continue

            except Exception as e:
                print(f"❌ Error: {e}")
                continue

    finally:
        if browser:
            await browser.stop()
        if llm:
            await llm.close()


async def demo_mode():
    """Run a demo to show capabilities."""
    print("\n🎬 Demo Mode - Showing agent capabilities\n")

    tasks = [
        ("https://www.google.com", "Search for 'Python programming tutorials'"),
        ("https://news.ycombinator.com", "Scroll down and read the first few article titles"),
    ]

    for url, task in tasks:
        print(f"\n{'='*60}")
        print(f"Demo: {task}")
        print(f"URL: {url}")
        print(f"{'='*60}")

        input("Press Enter to start this demo...")

        await run_task(task, url, max_actions=20)

        print("\n")
        input("Press Enter to continue to next demo...")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Local Browser Automation Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --check
  python main.py --task "Search for Python tutorials" --url "https://google.com"
  python main.py --interactive
  python main.py --demo

Environment Variables:
  LM_STUDIO_URL     LM Studio API URL (default: http://localhost:1234/v1)
  LM_STUDIO_MODEL   Model name to use (default: gemma-3-12b)
  CHROME_PATH       Path to Chrome executable
        """,
    )

    parser.add_argument(
        "--task", "-t",
        help="Task to execute",
    )

    parser.add_argument(
        "--url", "-u",
        help="URL to start at",
    )

    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo mode",
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Check prerequisites only",
    )

    parser.add_argument(
        "--max-actions",
        type=int,
        default=50,
        help="Maximum actions per task (default: 50)",
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Reduce output verbosity",
    )

    parser.add_argument(
        "--lm-studio-url",
        help="LM Studio API URL",
    )

    parser.add_argument(
        "--model",
        help="Model name in LM Studio",
    )

    args = parser.parse_args()

    # Load config from environment
    load_config_from_env()

    # Override config with CLI args
    if args.lm_studio_url:
        config.lm_studio.base_url = args.lm_studio_url
    if args.model:
        config.lm_studio.model = args.model

    # Set logging level
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    print_banner()

    # Run appropriate mode
    if args.check:
        asyncio.run(check_prerequisites())

    elif args.demo:
        if asyncio.run(check_prerequisites()):
            asyncio.run(demo_mode())

    elif args.interactive:
        if asyncio.run(check_prerequisites()):
            asyncio.run(interactive_mode())

    elif args.task:
        if asyncio.run(check_prerequisites()):
            asyncio.run(run_task(
                task=args.task,
                url=args.url,
                max_actions=args.max_actions,
                verbose=not args.quiet,
            ))

    else:
        parser.print_help()
        print("\n💡 Try: python main.py --interactive")


if __name__ == "__main__":
    main()
