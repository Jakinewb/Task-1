import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import json
import queue
import sys
from datetime import datetime
from dotenv import load_dotenv, set_key

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

load_dotenv()

# Colors, fonts, and styles
BG       = "#0D1117"
SURFACE  = "#161B22"
CARD     = "#1C2128"
BORDER   = "#30363D"
ACCENT   = "#238636"      
ACCENT_H = "#2EA043"
ACCENT_B = "#1A6E2C"
BLUE     = "#388BFD"
YELLOW   = "#E3B341"
RED      = "#F85149"
TEXT     = "#E6EDF3"
SUBTEXT  = "#7D8590"
MUTED    = "#484F58"
WHITE    = "#FFFFFF"
MONO     = "Consolas"
SANS     = "Segoe UI"

STATUS_OK   = "#3FB950"
STATUS_WARN = "#E3B341"
STATUS_ERR  = "#F85149"
STATUS_INFO = "#388BFD"

# Helper widgets
def _lbl(parent, text, size=9, bold=False, color=TEXT, font=SANS, **kw):
    weight = "bold" if bold else "normal"
    return tk.Label(parent, text=text, font=(font, size, weight),
                    bg=kw.pop("bg", parent["bg"]), fg=color, **kw)

def _sep(parent, color=BORDER, pady=6):
    f = tk.Frame(parent, bg=color, height=1)
    f.pack(fill="x", pady=pady)
    return f

# Main application class
class NetBoxGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Device & IP Lookup")
        self.geometry("1120x720")
        self.minsize(900, 580)
        self.configure(bg=BG)
        self.resizable(True, True)

        self._log_queue = queue.Queue()
        self._fetch_thread = None
        self._results = {"devices": [], "ips": []}

        self._build_styles()
        self._build_ui()
        self._poll_log_queue()
        self._check_env()

    # Styles and themes
    def _build_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview",
            background=CARD, foreground=TEXT, fieldbackground=CARD,
            borderwidth=0, rowheight=28, font=(MONO, 9))
        s.configure("Treeview.Heading",
            background=SURFACE, foreground=SUBTEXT, borderwidth=0,
            relief="flat", font=(SANS, 8, "bold"))
        s.map("Treeview",
            background=[("selected", "#264F78")],
            foreground=[("selected", WHITE)])
        s.map("Treeview.Heading",
            background=[("active", BORDER)])
        for sb in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            s.configure(sb, background=BORDER, troughcolor=SURFACE,
                        arrowcolor=SUBTEXT, borderwidth=0)
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab",
            background=SURFACE, foreground=SUBTEXT, padding=[14, 6],
            font=(SANS, 9), borderwidth=0)
        s.map("TNotebook.Tab",
            background=[("selected", CARD)],
            foreground=[("selected", TEXT)])

    # Maste Layout
    def _build_ui(self):
        # Header Bar
        hdr = tk.Frame(self, bg=SURFACE, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="■", font=(SANS, 18), bg=SURFACE,
                 fg=ACCENT).pack(side="left", padx=(16, 6), pady=8)
        tk.Label(hdr, text="Device & IP", font=(SANS, 14, "bold"),
                 bg=SURFACE, fg=WHITE).pack(side="left", pady=8)
        tk.Label(hdr, text="Lookup", font=(SANS, 10),
                 bg=SURFACE, fg=SUBTEXT).pack(side="left", padx=8, pady=8)

        # Connection status dot
        self._conn_dot = tk.Label(hdr, text="●", font=(SANS, 14),
                                  bg=SURFACE, fg=MUTED)
        self._conn_dot.pack(side="right", padx=(0, 8))
        self._conn_lbl = tk.Label(hdr, text="Not connected",
                                  font=(SANS, 9), bg=SURFACE, fg=SUBTEXT)
        self._conn_lbl.pack(side="right")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Main horizontal split: left sidebar + right content 
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # Left sidebar
        sidebar = tk.Frame(body, bg=SURFACE, width=240)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")
        self._build_sidebar(sidebar)

        # Right content
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self._build_content(right)

    # Sidebar
    def _build_sidebar(self, parent):
        pad = dict(padx=16, pady=4)

        _lbl(parent, "CONNECTION", size=8, bold=True, color=SUBTEXT,
             bg=SURFACE).pack(anchor="w", padx=16, pady=(16, 6))

        # URL
        _lbl(parent, "NetBox URL", size=9, color=SUBTEXT,
             bg=SURFACE).pack(anchor="w", **pad)
        self._url_var = tk.StringVar(value=os.getenv("NETBOX_URL", ""))
        url_entry = tk.Entry(parent, textvariable=self._url_var,
                             font=(MONO, 9), bg=CARD, fg=TEXT,
                             insertbackground=TEXT, relief="flat",
                             highlightthickness=1, highlightbackground=BORDER,
                             highlightcolor=ACCENT)
        url_entry.pack(fill="x", padx=16, pady=(0, 6))

        # Token
        _lbl(parent, "API Token", size=9, color=SUBTEXT,
             bg=SURFACE).pack(anchor="w", **pad)
        self._token_var = tk.StringVar(value=os.getenv("NETBOX_TOKEN", ""))
        token_entry = tk.Entry(parent, textvariable=self._token_var,
                               font=(MONO, 9), bg=CARD, fg=TEXT,
                               insertbackground=TEXT, relief="flat",
                               highlightthickness=1, highlightbackground=BORDER,
                               highlightcolor=ACCENT, show="●")
        token_entry.pack(fill="x", padx=16, pady=(0, 6))

        self._show_token = False
        def toggle_token():
            self._show_token = not self._show_token
            token_entry.config(show="" if self._show_token else "●")
            tog_btn.config(text="Hide" if self._show_token else "Show")
        tog_btn = tk.Button(parent, text="Show", font=(SANS, 8),
                            bg=CARD, fg=SUBTEXT, relief="flat",
                            activebackground=BORDER, activeforeground=TEXT,
                            cursor="hand2", bd=0, command=toggle_token)
        tog_btn.pack(anchor="e", padx=16)

        self._btn(parent, "Test Connection", BLUE, self._test_connection,
                  pady=8).pack(fill="x", padx=16, pady=(8, 4))
        self._btn(parent, "Save to .env", MUTED, self._save_env,
                  pady=6).pack(fill="x", padx=16, pady=(0, 8))

        _sep(parent, pady=4)

        # Export options
        _lbl(parent, "EXPORT OPTIONS", size=8, bold=True, color=SUBTEXT,
             bg=SURFACE).pack(anchor="w", padx=16, pady=(8, 6))

        self._exp_json = tk.BooleanVar(value=True)
        self._exp_csv  = tk.BooleanVar(value=True)
        for var, label in [(self._exp_json, "Export JSON"),
                           (self._exp_csv,  "Export CSV")]:
            cb = tk.Checkbutton(parent, text=label, variable=var,
                                font=(SANS, 9), bg=SURFACE, fg=TEXT,
                                selectcolor=CARD, activebackground=SURFACE,
                                activeforeground=TEXT, cursor="hand2",
                                highlightthickness=0)
            cb.pack(anchor="w", padx=16, pady=2)

        _lbl(parent, "Output Directory", size=9, color=SUBTEXT,
             bg=SURFACE).pack(anchor="w", padx=16, pady=(8, 2))
        dir_row = tk.Frame(parent, bg=SURFACE)
        dir_row.pack(fill="x", padx=16, pady=(0, 8))
        self._outdir_var = tk.StringVar(value=os.getcwd())
        tk.Entry(dir_row, textvariable=self._outdir_var, font=(MONO, 8),
                 bg=CARD, fg=TEXT, insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side="left", fill="x", expand=True)
        tk.Button(dir_row, text="…", font=(SANS, 9), bg=BORDER, fg=TEXT,
                  relief="flat", cursor="hand2", bd=0,
                  command=self._browse_dir).pack(side="left", padx=(4, 0))

        _sep(parent, pady=4)

        # Fetch buttons
        _lbl(parent, "FETCH & EXPORT", size=8, bold=True, color=SUBTEXT,
             bg=SURFACE).pack(anchor="w", padx=16, pady=(8, 6))

        self._btn(parent, "⬇  Fetch Devices", ACCENT, self._fetch_devices,
                  pady=8).pack(fill="x", padx=16, pady=(0, 6))
        self._btn(parent, "⬇  Fetch IP Addresses", ACCENT, self._fetch_ips,
                  pady=8).pack(fill="x", padx=16, pady=(0, 6))
        self._btn(parent, "⬇  Fetch Both", ACCENT_B, self._fetch_both,
                  pady=8).pack(fill="x", padx=16, pady=(0, 6))

        self._progress = ttk.Progressbar(parent, mode="indeterminate",
                                         length=180)
        self._progress.pack(padx=16, pady=(8, 4))

        # Spacer + version
        tk.Frame(parent, bg=SURFACE).pack(fill="both", expand=True)
        _lbl(parent, "gui.py  ·  Task-1", size=8, color=MUTED,
             bg=SURFACE).pack(anchor="w", padx=16, pady=(0, 10))

    def _btn(self, parent, text, color, cmd, pady=6):
        b = tk.Button(parent, text=text, font=(SANS, 9, "bold"),
                      bg=color, fg=WHITE, relief="flat", cursor="hand2",
                      bd=0, pady=pady, activebackground=ACCENT_H,
                      activeforeground=WHITE, command=cmd)
        return b

    # Right content (notebook tabs) 
    def _build_content(self, parent):
        self._nb = ttk.Notebook(parent)
        self._nb.pack(fill="both", expand=True, padx=0, pady=0)

        self._tab_devices = self._make_table_tab("Devices", [
            ("id", "ID", 50), ("name", "Name", 200),
            ("device_type", "Type", 160), ("status", "Status", 90),
            ("site", "Site", 140), ("role", "Role", 140),
            ("primary_ip", "Primary IP", 140),
        ])
        self._tab_ips = self._make_table_tab("IP Addresses", [
            ("id", "ID", 50), ("address", "Address", 160),
            ("status", "Status", 90), ("dns_name", "DNS Name", 180),
            ("vrf", "VRF", 120), ("assigned_object", "Assigned To", 200),
            ("description", "Description", 200),
        ])
        self._tab_log = self._make_log_tab()

    def _make_table_tab(self, title, columns):
        tab = tk.Frame(self._nb, bg=BG)
        self._nb.add(tab, text=f"  {title}  ")

        # Toolbar
        tb = tk.Frame(tab, bg=SURFACE, height=38)
        tb.pack(fill="x")
        tb.pack_propagate(False)

        _lbl(tb, "🔍", size=11, bg=SURFACE,
             color=SUBTEXT).pack(side="left", padx=(10, 4), pady=6)
        search_var = tk.StringVar()
        search_e = tk.Entry(tb, textvariable=search_var,
                            font=(MONO, 9), bg=CARD, fg=TEXT,
                            insertbackground=TEXT, relief="flat",
                            highlightthickness=0, width=30)
        search_e.pack(side="left", ipady=4, pady=5)
        _lbl(tb, f"Search {title.lower()}…", size=9, bg=SURFACE,
             color=MUTED).pack(side="left", padx=4)

        # Record count
        count_var = tk.StringVar(value="0 records")
        _lbl(tb, "", size=9, bg=SURFACE, color=SUBTEXT,
             textvariable=count_var).pack(side="right", padx=14)

        tk.Frame(tab, bg=BORDER, height=1).pack(fill="x")

        # Table
        tbl_frame = tk.Frame(tab, bg=BG)
        tbl_frame.pack(fill="both", expand=True)

        col_ids = [c[0] for c in columns]
        tree = ttk.Treeview(tbl_frame, columns=col_ids,
                            show="headings", selectmode="browse")
        for cid, clabel, cwidth in columns:
            tree.heading(cid, text=clabel, anchor="center")
            tree.column(cid, width=cwidth, minwidth=40, anchor="center")

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tbl_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        tree.pack(fill="both", expand=True)

        tree.tag_configure("odd",    background="#161B22")
        tree.tag_configure("even",   background=CARD)
        tree.tag_configure("active", foreground=STATUS_OK)
        tree.tag_configure("deprecated", foreground=STATUS_ERR)
        tree.tag_configure("reserved", foreground=STATUS_WARN)

        # Live search filter
        all_rows = []
        def _filter(*_):
            q = search_var.get().lower()
            tree.delete(*tree.get_children())
            shown = [r for r in all_rows
                     if not q or any(q in str(v).lower() for v in r)]
            for i, row in enumerate(shown):
                tag = "odd" if i % 2 else "even"
                tree.insert("", "end", values=row, tags=(tag,))
            count_var.set(f"{len(shown)} records")
        search_var.trace_add("write", _filter)

        return {"tree": tree, "all_rows": all_rows,
                "filter": _filter, "count_var": count_var,
                "col_ids": col_ids}

    def _make_log_tab(self):
        tab = tk.Frame(self._nb, bg=BG)
        self._nb.add(tab, text="  Log  ")

        tb = tk.Frame(tab, bg=SURFACE, height=38)
        tb.pack(fill="x")
        tb.pack_propagate(False)
        _lbl(tb, "Activity Log", size=9, bold=True, bg=SURFACE,
             color=TEXT).pack(side="left", padx=14, pady=8)
        tk.Button(tb, text="Clear", font=(SANS, 8), bg=CARD, fg=SUBTEXT,
                  relief="flat", cursor="hand2", bd=0, padx=10,
                  command=self._clear_log).pack(side="right", padx=10, pady=6)

        tk.Frame(tab, bg=BORDER, height=1).pack(fill="x")

        self._log_text = tk.Text(tab, bg=CARD, fg=TEXT,
                                 font=(MONO, 9), relief="flat",
                                 wrap="word", state="disabled",
                                 insertbackground=TEXT,
                                 highlightthickness=0)
        vsb = ttk.Scrollbar(tab, orient="vertical",
                            command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True, padx=0, pady=0)

        # Tag colors for log levels
        self._log_text.tag_configure("INFO",    foreground=STATUS_INFO)
        self._log_text.tag_configure("SUCCESS", foreground=STATUS_OK)
        self._log_text.tag_configure("WARNING", foreground=STATUS_WARN)
        self._log_text.tag_configure("ERROR",   foreground=STATUS_ERR)
        self._log_text.tag_configure("DIM",     foreground=SUBTEXT)

    # Logging
    def _log(self, message, level="INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_queue.put((ts, level, message))

    def _poll_log_queue(self):
        try:
            while True:
                ts, level, msg = self._log_queue.get_nowait()
                self._log_text.configure(state="normal")
                self._log_text.insert("end", f"[{ts}] ", "DIM")
                self._log_text.insert("end", f"{level:<8}", level)
                self._log_text.insert("end", f" {msg}\n")
                self._log_text.configure(state="disabled")
                self._log_text.see("end")
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _clear_log(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    # Connection helpers 
    def _get_headers(self):
        token = self._token_var.get().strip()

        if (token.startswith("'") and token.endswith("'")) or \
           (token.startswith('"') and token.endswith('"')):
            token = token[1:-1].strip()

        if token.lower().startswith("token "):
            auth_value = token         
        else:
            auth_value = f"Token {token}" 
        return {
            "Authorization": auth_value,
            "Content-Type": "application/json",
        }

    def _check_env(self):
        url   = self._url_var.get().strip()
        token = self._token_var.get().strip()
        if url and token:
            self._set_conn_status("Ready", YELLOW)
        else:
            self._set_conn_status("No credentials", MUTED)

    def _set_conn_status(self, text, color):
        self._conn_dot.config(fg=color)
        self._conn_lbl.config(text=text)

    def _test_connection(self):
        if not HAS_REQUESTS:
            messagebox.showerror("Missing dependency",
                                 "requests is not installed.")
            return
        url   = self._url_var.get().strip().rstrip("/")
        token = self._token_var.get().strip()
        if not url or not token:
            messagebox.showwarning("Missing fields",
                                   "Please fill in URL and Token.")
            return
        self._log("Testing connection…")
        self._set_conn_status("Connecting…", YELLOW)

        def _do():
            try:
                r = requests.get(f"{url}/api/", headers=self._get_headers(),
                                 timeout=8)
                r.raise_for_status()
                self._log(f"Connected to {url}  (HTTP {r.status_code})",
                          "SUCCESS")
                self.after(0, lambda: self._set_conn_status(
                    "Connected", STATUS_OK))
            except Exception as e:
                self._log(f"Connection failed: {e}", "ERROR")
                self.after(0, lambda: self._set_conn_status(
                    "Failed", STATUS_ERR))

        threading.Thread(target=_do, daemon=True).start()

    def _save_env(self):
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        try:
            set_key(env_path, "NETBOX_URL",   self._url_var.get().strip())
            set_key(env_path, "NETBOX_TOKEN", self._token_var.get().strip())
            self._log(f".env updated at {env_path}", "SUCCESS")
        except Exception as e:
            self._log(f"Could not save .env: {e}", "ERROR")

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Select output directory")
        if d:
            self._outdir_var.set(d)

    # Fetch helpers
    def _start_progress(self):
        self._progress.start(12)

    def _stop_progress(self):
        self._progress.stop()

    def _fetch_all_pages(self, endpoint_path):
        """Paginate through NetBox API, return list of result dicts."""
        if not HAS_REQUESTS:
            raise RuntimeError("requests is not installed.")
        url   = self._url_var.get().strip().rstrip("/") + "/" + endpoint_path.lstrip("/")
        hdrs  = self._get_headers()
        results = []
        page = 1
        while url:
            self._log(f"Fetching page {page}: {url}")
            r = requests.get(url, headers=hdrs, timeout=15)
            r.raise_for_status()
            data = r.json()
            results.extend(data.get("results", []))
            url = data.get("next")
            page += 1
        self._log(f"Fetched {len(results)} total records", "SUCCESS")
        return results

    # Save helpers
    def _save_files(self, data, prefix):
        outdir = self._outdir_var.get().strip() or os.getcwd()
        stamp  = datetime.now().strftime("%Y-%m-%d_%H-%M")
        saved  = []

        if self._exp_json.get():
            path = os.path.join(outdir, f"{prefix}_{stamp}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            self._log(f"Saved JSON → {path}", "SUCCESS")
            saved.append(path)

        if self._exp_csv.get():
            if not HAS_PANDAS:
                self._log("pandas not installed — CSV skipped.", "WARNING")
            else:
                import pandas as pd
                path = os.path.join(outdir, f"{prefix}_{stamp}.csv")
                pd.json_normalize(data).to_csv(path, index=False)
                self._log(f"Saved CSV  → {path}", "SUCCESS")
                saved.append(path)

        return saved

    # Table population
    def _safe(self, value, *keys):
        """Drill into nested dicts safely, return string."""
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, "")
            else:
                return ""
        return str(value) if value else ""

    def _populate_devices(self, data):
        tab = self._tab_devices
        tab["all_rows"].clear()
        for d in data:
            row = (
                self._safe(d, "id"),
                self._safe(d, "name"),
                self._safe(d, "device_type", "display"),
                self._safe(d, "status", "value"),
                self._safe(d, "site", "name"),
                self._safe(d, "role", "name"),
                self._safe(d, "primary_ip", "address"),
            )
            tab["all_rows"].append(row)
        tab["filter"]()
        tab["count_var"].set(f"{len(data)} records")

    def _populate_ips(self, data):
        tab = self._tab_ips
        tab["all_rows"].clear()
        for d in data:
            assigned = (self._safe(d, "assigned_object", "name") or
                        self._safe(d, "assigned_object", "display") or "—")
            row = (
                self._safe(d, "id"),
                self._safe(d, "address"),
                self._safe(d, "status", "value"),
                self._safe(d, "dns_name"),
                self._safe(d, "vrf", "name"),
                assigned,
                self._safe(d, "description"),
            )
            tab["all_rows"].append(row)
        tab["filter"]()
        tab["count_var"].set(f"{len(data)} records")

    # Fetch action
    def _guard(self):
        if not self._url_var.get().strip():
            messagebox.showwarning("Missing URL", "Enter the NetBox URL first.")
            return False
        if not self._token_var.get().strip():
            messagebox.showwarning("Missing Token", "Enter your API token first.")
            return False
        if self._fetch_thread and self._fetch_thread.is_alive():
            messagebox.showinfo("Busy", "A fetch is already in progress.")
            return False
        return True

    def _fetch_devices(self):
        if not self._guard():
            return
        self._log("Starting device export…")
        self._start_progress()
        self._nb.select(0)

        def _do():
            try:
                data = self._fetch_all_pages("api/dcim/devices/")
                self._results["devices"] = data
                self.after(0, lambda: self._populate_devices(data))
                self._save_files(data, "Devices")
            except Exception as e:
                self._log(f"Devices fetch failed: {e}", "ERROR")
            finally:
                self.after(0, self._stop_progress)

        self._fetch_thread = threading.Thread(target=_do, daemon=True)
        self._fetch_thread.start()

    def _fetch_ips(self):
        if not self._guard():
            return
        self._log("Starting IP address export…")
        self._start_progress()
        self._nb.select(1)

        def _do():
            try:
                data = self._fetch_all_pages("api/ipam/ip-addresses/")
                self._results["ips"] = data
                self.after(0, lambda: self._populate_ips(data))
                self._save_files(data, "IPs")
            except Exception as e:
                self._log(f"IPs fetch failed: {e}", "ERROR")
            finally:
                self.after(0, self._stop_progress)

        self._fetch_thread = threading.Thread(target=_do, daemon=True)
        self._fetch_thread.start()

    def _fetch_both(self):
        if not self._guard():
            return
        self._log("Starting full export (devices + IPs)…")
        self._start_progress()

        def _do():
            try:
                self._log("Fetching devices…")
                dev_data = self._fetch_all_pages("api/dcim/devices/")
                self._results["devices"] = dev_data
                self.after(0, lambda: self._populate_devices(dev_data))
                self._save_files(dev_data, "Devices")

                self._log("Fetching IP addresses…")
                ip_data = self._fetch_all_pages("api/ipam/ip-addresses/")
                self._results["ips"] = ip_data
                self.after(0, lambda: self._populate_ips(ip_data))
                self._save_files(ip_data, "IPs")

                self._log("Full export completed ✓", "SUCCESS")
            except Exception as e:
                self._log(f"Export failed: {e}", "ERROR")
            finally:
                self.after(0, self._stop_progress)

        self._fetch_thread = threading.Thread(target=_do, daemon=True)
        self._fetch_thread.start()


# Entry point 
if __name__ == "__main__":
    app = NetBoxGUI()
    app.mainloop()