"""
Desktop Overlay Agent Panel.
A floating, always-on-top window that shows agent reasoning while you browse.
"""

import asyncio
import threading
import queue
import tkinter as tk
from tkinter import ttk, scrolledtext
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class LogEntry:
    """Entry in the reasoning log."""
    timestamp: datetime
    entry_type: str  # thinking, action, status, error
    message: str
    details: Optional[str] = None
    success: Optional[bool] = None


class OverlayPanel:
    """
    Floating overlay panel for the browser agent.
    Shows reasoning and accepts task input.
    """

    def __init__(
        self,
        on_task: Callable[[str], None] = None,
        on_stop: Callable[[], None] = None,
        on_connect: Callable[[], None] = None,
    ):
        self.on_task = on_task
        self.on_stop = on_stop
        self.on_connect = on_connect

        self.root: Optional[tk.Tk] = None
        self.is_running = False
        self.is_connected = False
        self.is_task_running = False
        self.message_queue = queue.Queue()

        # UI elements
        self.status_label: Optional[tk.Label] = None
        self.log_text: Optional[scrolledtext.ScrolledText] = None
        self.task_entry: Optional[tk.Entry] = None
        self.run_button: Optional[tk.Button] = None
        self.connect_button: Optional[tk.Button] = None

        # Colors
        self.colors = {
            'bg': '#1a1b26',
            'panel': '#24283b',
            'accent': '#7aa2f7',
            'success': '#9ece6a',
            'warning': '#e0af68',
            'error': '#f7768e',
            'text': '#c0caf5',
            'muted': '#565f89',
            'border': '#414868',
        }

    def create_window(self):
        """Create the overlay window."""
        self.root = tk.Tk()
        self.root.title("🧠 Agent")

        # Window settings
        self.root.attributes('-topmost', True)  # Always on top
        self.root.attributes('-alpha', 0.95)    # Slight transparency
        self.root.overrideredirect(False)       # Keep title bar for dragging
        self.root.resizable(True, True)

        # Size and position (right side of screen)
        width = 380
        height = 500
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = screen_width - width - 20
        y = (screen_height - height) // 2
        self.root.geometry(f'{width}x{height}+{x}+{y}')

        # Configure colors
        self.root.configure(bg=self.colors['bg'])

        # Style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background=self.colors['bg'])
        style.configure('TLabel', background=self.colors['bg'], foreground=self.colors['text'])
        style.configure('TButton', background=self.colors['panel'], foreground=self.colors['text'])

        # Main container
        main_frame = tk.Frame(self.root, bg=self.colors['bg'], padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        header_frame = tk.Frame(main_frame, bg=self.colors['bg'])
        header_frame.pack(fill=tk.X, pady=(0, 10))

        title_label = tk.Label(
            header_frame,
            text="🧠 Browser Agent",
            font=('Segoe UI', 14, 'bold'),
            bg=self.colors['bg'],
            fg=self.colors['text'],
        )
        title_label.pack(side=tk.LEFT)

        self.status_label = tk.Label(
            header_frame,
            text="● Disconnected",
            font=('Segoe UI', 10),
            bg=self.colors['bg'],
            fg=self.colors['muted'],
        )
        self.status_label.pack(side=tk.RIGHT)

        # Connect button
        self.connect_button = tk.Button(
            main_frame,
            text="🔌 Connect to Chrome",
            font=('Segoe UI', 11),
            bg=self.colors['accent'],
            fg='white',
            activebackground=self.colors['accent'],
            activeforeground='white',
            relief=tk.FLAT,
            cursor='hand2',
            command=self._on_connect_click,
        )
        self.connect_button.pack(fill=tk.X, pady=(0, 10))

        # Task input
        input_frame = tk.Frame(main_frame, bg=self.colors['panel'], padx=8, pady=8)
        input_frame.pack(fill=tk.X, pady=(0, 10))

        task_label = tk.Label(
            input_frame,
            text="What should I do?",
            font=('Segoe UI', 10),
            bg=self.colors['panel'],
            fg=self.colors['muted'],
        )
        task_label.pack(anchor=tk.W)

        self.task_entry = tk.Entry(
            input_frame,
            font=('Segoe UI', 11),
            bg=self.colors['bg'],
            fg=self.colors['text'],
            insertbackground=self.colors['text'],
            relief=tk.FLAT,
            state=tk.DISABLED,
        )
        self.task_entry.pack(fill=tk.X, pady=(5, 8))
        self.task_entry.bind('<Return>', self._on_enter_pressed)

        # Buttons frame
        btn_frame = tk.Frame(input_frame, bg=self.colors['panel'])
        btn_frame.pack(fill=tk.X)

        self.run_button = tk.Button(
            btn_frame,
            text="▶ Run",
            font=('Segoe UI', 10, 'bold'),
            bg=self.colors['success'],
            fg='white',
            activebackground=self.colors['success'],
            activeforeground='white',
            relief=tk.FLAT,
            cursor='hand2',
            width=10,
            state=tk.DISABLED,
            command=self._on_run_click,
        )
        self.run_button.pack(side=tk.LEFT, padx=(0, 5))

        self.stop_button = tk.Button(
            btn_frame,
            text="⏹ Stop",
            font=('Segoe UI', 10),
            bg=self.colors['error'],
            fg='white',
            activebackground=self.colors['error'],
            activeforeground='white',
            relief=tk.FLAT,
            cursor='hand2',
            width=10,
            state=tk.DISABLED,
            command=self._on_stop_click,
        )
        self.stop_button.pack(side=tk.LEFT)

        # Reasoning log
        log_label = tk.Label(
            main_frame,
            text="Agent Reasoning",
            font=('Segoe UI', 10, 'bold'),
            bg=self.colors['bg'],
            fg=self.colors['text'],
        )
        log_label.pack(anchor=tk.W, pady=(5, 5))

        self.log_text = scrolledtext.ScrolledText(
            main_frame,
            font=('Consolas', 10),
            bg=self.colors['panel'],
            fg=self.colors['text'],
            relief=tk.FLAT,
            wrap=tk.WORD,
            state=tk.DISABLED,
            cursor='arrow',
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Configure text tags for colored output
        self.log_text.tag_configure('thinking', foreground=self.colors['accent'])
        self.log_text.tag_configure('action', foreground=self.colors['success'])
        self.log_text.tag_configure('status', foreground=self.colors['warning'])
        self.log_text.tag_configure('error', foreground=self.colors['error'])
        self.log_text.tag_configure('timestamp', foreground=self.colors['muted'])
        self.log_text.tag_configure('details', foreground=self.colors['muted'])

        # Footer
        footer = tk.Label(
            main_frame,
            text="Ctrl+Enter to run • Powered by LM Studio",
            font=('Segoe UI', 8),
            bg=self.colors['bg'],
            fg=self.colors['muted'],
        )
        footer.pack(pady=(5, 0))

        # Keyboard shortcuts
        self.root.bind('<Control-Return>', self._on_enter_pressed)
        self.root.bind('<Escape>', lambda e: self.root.iconify())

        # Handle close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_connect_click(self):
        """Handle connect button click."""
        if self.on_connect:
            self.connect_button.configure(text="Connecting...", state=tk.DISABLED)
            self.on_connect()

    def _on_run_click(self):
        """Handle run button click."""
        task = self.task_entry.get().strip()
        if task and self.on_task:
            self.on_task(task)

    def _on_stop_click(self):
        """Handle stop button click."""
        if self.on_stop:
            self.on_stop()

    def _on_enter_pressed(self, event=None):
        """Handle Enter key in task entry."""
        if self.is_connected and not self.is_task_running:
            self._on_run_click()

    def _on_close(self):
        """Handle window close."""
        self.is_running = False
        self.root.destroy()

    def set_connected(self, connected: bool):
        """Update connection status."""
        self.is_connected = connected

        if connected:
            self.status_label.configure(text="● Connected", fg=self.colors['success'])
            self.connect_button.configure(text="✓ Connected to Chrome", state=tk.DISABLED)
            self.task_entry.configure(state=tk.NORMAL)
            self.run_button.configure(state=tk.NORMAL)
        else:
            self.status_label.configure(text="● Disconnected", fg=self.colors['muted'])
            self.connect_button.configure(text="🔌 Connect to Chrome", state=tk.NORMAL)
            self.task_entry.configure(state=tk.DISABLED)
            self.run_button.configure(state=tk.DISABLED)

    def set_task_running(self, running: bool):
        """Update task running status."""
        self.is_task_running = running

        if running:
            self.status_label.configure(text="● Running...", fg=self.colors['accent'])
            self.run_button.configure(state=tk.DISABLED)
            self.stop_button.configure(state=tk.NORMAL)
            self.task_entry.configure(state=tk.DISABLED)
        else:
            self.status_label.configure(text="● Ready", fg=self.colors['success'])
            self.run_button.configure(state=tk.NORMAL)
            self.stop_button.configure(state=tk.DISABLED)
            self.task_entry.configure(state=tk.NORMAL)

    def add_log(self, entry_type: str, message: str, details: str = None):
        """Add entry to the reasoning log."""
        self.message_queue.put(LogEntry(
            timestamp=datetime.now(),
            entry_type=entry_type,
            message=message,
            details=details,
        ))

    def _process_messages(self):
        """Process queued messages (called from main thread)."""
        try:
            while True:
                entry = self.message_queue.get_nowait()
                self._add_log_entry(entry)
        except queue.Empty:
            pass

        if self.is_running:
            self.root.after(100, self._process_messages)

    def _add_log_entry(self, entry: LogEntry):
        """Add entry to log widget."""
        self.log_text.configure(state=tk.NORMAL)

        # Timestamp
        time_str = entry.timestamp.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{time_str}] ", 'timestamp')

        # Type indicator
        type_indicators = {
            'thinking': '💭 ',
            'action': '✓ ',
            'status': '→ ',
            'error': '✗ ',
        }
        indicator = type_indicators.get(entry.entry_type, '')
        self.log_text.insert(tk.END, indicator)

        # Message
        self.log_text.insert(tk.END, f"{entry.message}\n", entry.entry_type)

        # Details
        if entry.details:
            self.log_text.insert(tk.END, f"  {entry.details}\n", 'details')

        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def clear_log(self):
        """Clear the reasoning log."""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def run(self):
        """Run the overlay window (blocking)."""
        self.create_window()
        self.is_running = True
        self.root.after(100, self._process_messages)
        self.root.mainloop()

    def run_async(self):
        """Run the overlay in a separate thread."""
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread
