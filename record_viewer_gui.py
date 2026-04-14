import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import csv
from datetime import datetime

# Palette
BG       = "#0D1117"
SURFACE  = "#161B22"
CARD     = "#1C2128"
BORDER   = "#30363D"
ACCENT   = "#238636"
ACCENT_H = "#2EA043"
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

# File types script.py produces
KNOWN_PREFIXES = ("Devices_", "IPs_")
KNOWN_EXTS     = (".json", ".csv")


# Helpers
def _lbl(parent, text, size=9, bold=False, color=TEXT, font=SANS, **kw):
    w = "bold" if bold else "normal"
    return tk.Label(parent, text=text, font=(font, size, w),
                    bg=kw.pop("bg", parent["bg"]), fg=color, **kw)

def _btn(parent, text, color, cmd, pady=6, padx=0):
    return tk.Button(parent, text=text, font=(SANS, 9, "bold"),
                     bg=color, fg=WHITE, relief="flat", cursor="hand2",
                     bd=0, pady=pady, padx=padx or 12,
                     activebackground=color, activeforeground=WHITE,
                     command=cmd)

def _sep(parent, color=BORDER, pady=4):
    f = tk.Frame(parent, bg=color, height=1)
    f.pack(fill="x", pady=pady)

def _safe(value, *keys):
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k, "")
        else:
            return ""
    return str(value) if value else ""

def _apply_ttk_styles(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure("Treeview",
        background=CARD, foreground=TEXT, fieldbackground=CARD,
        borderwidth=0, rowheight=32, font=(MONO, 9))
    s.configure("Treeview.Heading",
        background=SURFACE, foreground=SUBTEXT,
        borderwidth=0, relief="flat", font=(SANS, 9, "bold"),
        padding=[0, 8])
    s.map("Treeview",
        background=[("selected", "#1F3A5F")],
        foreground=[("selected", TEXT)])
    s.map("Treeview.Heading",
        background=[("active", BORDER)],
        foreground=[("active", TEXT)])
    for sb in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        s.configure(sb, background=BORDER, troughcolor=SURFACE,
                    arrowcolor=SUBTEXT, borderwidth=0)
    s.configure("TNotebook", background=BG, borderwidth=0)
    s.configure("TNotebook.Tab",
        background=SURFACE, foreground=SUBTEXT,
        padding=[14, 6], font=(SANS, 9), borderwidth=0)
    s.map("TNotebook.Tab",
        background=[("selected", CARD)],
        foreground=[("selected", TEXT)])


# File scanning 
def scan_directory(directory: str) -> list[dict]:
    """
    Scan a directory for exported files matching Devices_* or IPs_* patterns.
    Returns a list of dicts sorted by modification time (newest first).
    """
    files = []
    if not os.path.isdir(directory):
        return files
    for fname in os.listdir(directory):
        _, ext = os.path.splitext(fname)
        if ext.lower() not in KNOWN_EXTS:
            continue
        if not any(fname.startswith(p) for p in KNOWN_PREFIXES):
            continue
        full = os.path.join(directory, fname)
        stat = os.stat(full)
        kind = "Devices" if fname.startswith("Devices_") else "IPs"
        fmt  = ext.upper().lstrip(".")
        files.append({
            "name":     fname,
            "path":     full,
            "kind":     kind,
            "format":   fmt,
            "size":     stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime),
        })
    files.sort(key=lambda f: f["modified"], reverse=True)
    return files


def _s(d, *keys):
    """Safely extract a nested value from a dict, return string."""
    v = d
    for k in keys:
        if isinstance(v, dict):
            v = v.get(k, "")
        else:
            return ""
    return str(v) if v else ""

DEVICE_SCHEMA = [
    ("ID",         lambda d: _s(d, "id")),
    ("Name",       lambda d: _s(d, "name")),
    ("Type",       lambda d: _s(d, "device_type", "display") or _s(d, "device_type.display")),
    ("Status",     lambda d: _s(d, "status", "value") or _s(d, "status.value")),
    ("Site",       lambda d: _s(d, "site", "name") or _s(d, "site.name")),
    ("Role",       lambda d: _s(d, "role", "name") or _s(d, "role.name")),
    ("Primary IP", lambda d: _s(d, "primary_ip", "address") or _s(d, "primary_ip.address")),
]

IP_SCHEMA = [
    ("ID",          lambda d: _s(d, "id")),
    ("Address",     lambda d: _s(d, "address")),
    ("Status",      lambda d: _s(d, "status", "value") or _s(d, "status.value")),
    ("DNS Name",    lambda d: _s(d, "dns_name")),
    ("VRF",         lambda d: _s(d, "vrf", "name") or _s(d, "vrf.name")),
    ("Assigned To", lambda d: _s(d, "assigned_object", "name")
                              or _s(d, "assigned_object", "display")
                              or _s(d, "assigned_object.name")),
    ("Description", lambda d: _s(d, "description")),
]

def _detect_kind(path: str) -> str:
    """Detect whether a file is a Devices or IPs export from its filename."""
    fname = os.path.basename(path)
    if fname.startswith("Devices_"):
        return "Devices"
    if fname.startswith("IPs_"):
        return "IPs"
    # Fallback: peek at the keys of the first JSON record
    if path.lower().endswith(".json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data and isinstance(data[0], dict):
                keys = set(data[0].keys())
                if "address" in keys:
                    return "IPs"
        except Exception:
            pass
    return "Devices"  # default


def load_file(path: str) -> tuple[list, list, str]:
    """
    Load a JSON or CSV export file, extracting only the columns
    that match the export GUI schema (Devices or IPs).

    Returns (column_labels, rows, kind) where:
        column_labels — list of display header strings
        rows          — list of row value lists (all strings)
        kind          — "Devices" or "IPs"
    """
    kind   = _detect_kind(path)
    schema = DEVICE_SCHEMA if kind == "Devices" else IP_SCHEMA
    labels = [col[0] for col in schema]
    ext    = os.path.splitext(path)[1].lower()

    if ext == ".json":
        rows = _load_json_schema(path, schema)
    elif ext == ".csv":
        rows = _load_csv_schema(path, schema, labels)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    return labels, rows, kind


def _load_json_schema(path: str, schema: list) -> list:
    """Load JSON and extract only the schema columns."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for record in data:
        if isinstance(record, dict):
            rows.append([extractor(record) for _, extractor in schema])
    return rows


def _load_csv_schema(path: str, schema: list, labels: list) -> list:
    """
    Load CSV and map flat column names to schema columns.
    CSV columns from pandas json_normalize use dot notation for nested fields
    e.g. status.value, site.name, device_type.display
    """
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader  = csv.DictReader(f)
        records = list(reader)

    rows = []
    for record in records:
        row = []
        for label, extractor in schema:

            val = extractor(record)
           
            if not val:

                dot_map = {
                    "ID": "id",
                    "Name": "name",
                    "Type": "device_type.display",
                    "Status": "status.value",
                    "Site": "site.name",
                    "Role": "role.name",
                    "Primary IP": "primary_ip.address",
                    "Address": "address",
                    "DNS Name": "dns_name",
                    "VRF": "vrf.name",
                    "Assigned To": "assigned_object.name",
                    "Description": "description",
                }
                val = str(record.get(dot_map.get(label, ""), "") or "")
            row.append(val)
        rows.append(row)
    return rows


# Main App
class RecordViewerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NetBox Export Viewer")
        self.geometry("1180x700")
        self.minsize(900, 560)
        self.configure(bg=BG)
        self.resizable(True, True)

        _apply_ttk_styles(self)

        self._scan_dir   = os.getcwd()
        self._all_files  = []
        self._active_rows: list[list] = []

        self._build_ui()
        self._refresh_file_list()

    # Layout
    def _build_ui(self):
        self._build_header()
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # Left panel — file browser
        left = tk.Frame(body, bg=SURFACE, width=280)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")
        self._build_file_panel(left)

        # Right panel — record viewer
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self._build_viewer_panel(right)

    # Header
    def _build_header(self):
        hdr = tk.Frame(self, bg=SURFACE, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="■", font=(SANS, 18), bg=SURFACE,
                 fg=ACCENT).pack(side="left", padx=(16, 6), pady=8)
        tk.Label(hdr, text="NetBox", font=(SANS, 14, "bold"),
                 bg=SURFACE, fg=WHITE).pack(side="left", pady=8)
        tk.Label(hdr, text="Export Viewer", font=(SANS, 10),
                 bg=SURFACE, fg=SUBTEXT).pack(side="left", padx=8, pady=8)

        self._status_lbl = tk.Label(hdr, text="No file loaded",
                                    font=(SANS, 9), bg=SURFACE, fg=SUBTEXT)
        self._status_lbl.pack(side="right", padx=16)

    # Left: file browser panel
    def _build_file_panel(self, parent):
        # Directory picker
        _lbl(parent, "DIRECTORY", size=8, bold=True,
             color=SUBTEXT, bg=SURFACE).pack(anchor="w", padx=14, pady=(14, 4))

        dir_row = tk.Frame(parent, bg=SURFACE)
        dir_row.pack(fill="x", padx=14, pady=(0, 6))
        self._dir_var = tk.StringVar(value=self._scan_dir)
        tk.Entry(dir_row, textvariable=self._dir_var,
                 font=(MONO, 8), bg=CARD, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side="left", fill="x",
                                             expand=True, ipady=3)
        tk.Button(dir_row, text="…", font=(SANS, 9),
                  bg=BORDER, fg=TEXT, relief="flat",
                  cursor="hand2", bd=0, padx=6,
                  command=self._browse_dir).pack(side="left", padx=(4, 0))

        # Filter row 1 — Type (All / Devices / IPs)
        _lbl(parent, "Type", size=8, color=SUBTEXT,
             bg=SURFACE).pack(anchor="w", padx=14, pady=(4, 0))
        kind_row = tk.Frame(parent, bg=SURFACE)
        kind_row.pack(fill="x", padx=14, pady=(2, 6))
        self._kind_var = tk.StringVar(value="All")
        for label in ("All", "Devices", "IPs"):
            tk.Radiobutton(
                kind_row, text=label, variable=self._kind_var, value=label,
                font=(SANS, 8), bg=SURFACE, fg=TEXT,
                selectcolor=CARD, activebackground=SURFACE,
                activeforeground=TEXT, cursor="hand2",
                highlightthickness=0,
                command=self._apply_file_filter
            ).pack(side="left", padx=(0, 8))

        # Filter row 2 — Format (All / JSON / CSV)
        _lbl(parent, "Format", size=8, color=SUBTEXT,
             bg=SURFACE).pack(anchor="w", padx=14, pady=(0, 0))
        fmt_row = tk.Frame(parent, bg=SURFACE)
        fmt_row.pack(fill="x", padx=14, pady=(2, 8))
        self._fmt_var = tk.StringVar(value="All")
        for label in ("All", "JSON", "CSV"):
            tk.Radiobutton(
                fmt_row, text=label, variable=self._fmt_var, value=label,
                font=(SANS, 8), bg=SURFACE, fg=TEXT,
                selectcolor=CARD, activebackground=SURFACE,
                activeforeground=TEXT, cursor="hand2",
                highlightthickness=0,
                command=self._apply_file_filter
            ).pack(side="left", padx=(0, 8))

        # Refresh + Open buttons
        btn_row = tk.Frame(parent, bg=SURFACE)
        btn_row.pack(fill="x", padx=14, pady=(0, 8))
        _btn(btn_row, "↻ Refresh", ACCENT,
             self._refresh_file_list, pady=5
             ).pack(side="left", padx=(0, 6))
        _btn(btn_row, "📂 Open File", BLUE,
             self._browse_file, pady=5
             ).pack(side="left")

        _sep(parent, pady=2)

        # File list label + count
        list_hdr = tk.Frame(parent, bg=SURFACE)
        list_hdr.pack(fill="x", padx=14, pady=(6, 4))
        _lbl(list_hdr, "EXPORT FILES", size=8, bold=True,
             color=SUBTEXT, bg=SURFACE).pack(side="left")
        self._file_count_var = tk.StringVar(value="")
        _lbl(list_hdr, "", size=8, color=MUTED, bg=SURFACE,
             textvariable=self._file_count_var).pack(side="right")

        # File listbox
        lb_frame = tk.Frame(parent, bg=BG)
        lb_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        self._file_lb = tk.Listbox(
            lb_frame,
            font=(MONO, 8), bg=CARD, fg=TEXT,
            selectbackground="#264F78", selectforeground=WHITE,
            relief="flat", highlightthickness=0,
            activestyle="none", cursor="hand2"
        )
        vsb = ttk.Scrollbar(lb_frame, orient="vertical",
                            command=self._file_lb.yview)
        self._file_lb.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._file_lb.pack(fill="both", expand=True)
        self._file_lb.bind("<<ListboxSelect>>", self._on_file_select)

        # File detail strip at bottom of panel
        _sep(parent, pady=2)
        self._file_detail_var = tk.StringVar(value="")
        _lbl(parent, "", size=8, color=SUBTEXT, bg=SURFACE,
             textvariable=self._file_detail_var,
             wraplength=240, justify="left").pack(
                 anchor="w", padx=14, pady=(4, 10))

    # Right: record viewer panel
    def _build_viewer_panel(self, parent):
        # Toolbar
        tb = tk.Frame(parent, bg=SURFACE, height=38)
        tb.pack(fill="x")
        tb.pack_propagate(False)

        tk.Label(tb, text="🔍", font=(SANS, 11), bg=SURFACE,
                 fg=SUBTEXT).pack(side="left", padx=(12, 4), pady=6)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_search())
        tk.Entry(tb, textvariable=self._search_var,
                 font=(MONO, 9), bg=CARD, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 highlightthickness=0, width=36
                 ).pack(side="left", ipady=4, pady=5)
        _lbl(tb, "Search records…", size=9, bg=SURFACE,
             color=MUTED).pack(side="left", padx=6)

        self._rec_count_var = tk.StringVar(value="")
        _lbl(tb, "", size=9, bg=SURFACE, color=SUBTEXT,
             textvariable=self._rec_count_var).pack(side="right", padx=14)

        # Column filter
        _lbl(tb, "Col:", size=9, bg=SURFACE,
             color=SUBTEXT).pack(side="right", padx=(0, 4))
        self._col_filter_var = tk.StringVar(value="All Columns")
        self._col_menu = tk.OptionMenu(tb, self._col_filter_var, "All Columns",
                                       command=lambda _: self._apply_search())
        self._col_menu.config(
            bg=CARD, fg=TEXT, relief="flat", font=(SANS, 8),
            highlightthickness=0, bd=0, cursor="hand2",
            activebackground=BORDER, activeforeground=TEXT)
        self._col_menu["menu"].config(
            bg=CARD, fg=TEXT, font=(SANS, 8),
            activebackground="#264F78", activeforeground=WHITE)
        self._col_menu.pack(side="right", padx=(0, 6))

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")

        # Table frame
        tbl_frame = tk.Frame(parent, bg=BG)
        tbl_frame.pack(fill="both", expand=True)

        self._tree = ttk.Treeview(tbl_frame, show="headings",
                                  selectmode="browse")
        vsb = ttk.Scrollbar(tbl_frame, orient="vertical",
                            command=self._tree.yview)
        hsb = ttk.Scrollbar(tbl_frame, orient="horizontal",
                            command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set,
                             xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True)

        self._tree.tag_configure("odd",  background="#13161E")
        self._tree.tag_configure("even", background="#1C2128")

        # Empty state label
        self._empty_lbl = _lbl(tbl_frame,
            "Select a file from the list or open one with  📂 Open File",
            size=10, color=MUTED, bg=BG)
        self._empty_lbl.place(relx=0.5, rely=0.5, anchor="center")

        # Detail panel at bottom
        self._build_detail_bar(parent)

    def _build_detail_bar(self, parent):
        bar = tk.Frame(parent, bg=SURFACE, height=30)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", side="bottom")

        self._detail_bar_var = tk.StringVar(value="")
        _lbl(bar, "", size=8, color=SUBTEXT, bg=SURFACE,
             textvariable=self._detail_bar_var).pack(
                 side="left", padx=14, pady=6)

    # File list helpers
    def _browse_dir(self):
        d = filedialog.askdirectory(title="Select export directory")
        if d:
            self._scan_dir = d
            self._dir_var.set(d)
            self._refresh_file_list()

    def _refresh_file_list(self):
        self._scan_dir = self._dir_var.get().strip() or os.getcwd()
        self._all_files = scan_directory(self._scan_dir)
        self._apply_file_filter()

    def _apply_file_filter(self):
        kind = self._kind_var.get()
        fmt  = self._fmt_var.get()
        filtered = [
            f for f in self._all_files
            if (kind == "All" or f["kind"] == kind)
            and (fmt  == "All" or f["format"] == fmt)
        ]
        self._file_lb.delete(0, "end")
        self._filtered_files = filtered
        for f in filtered:
            icon = "📄" if f["format"] == "JSON" else "📊"
            self._file_lb.insert(
                "end",
                f"  {icon}  {f['name']}"
            )
        self._file_count_var.set(f"{len(filtered)} file{'s' if len(filtered)!=1 else ''}")
        if not filtered:
            self._file_detail_var.set("No matching files found.")

    def _on_file_select(self, _event=None):
        sel = self._file_lb.curselection()
        if not sel:
            return
        idx  = sel[0]
        info = self._filtered_files[idx]
        size_kb = info["size"] / 1024
        self._file_detail_var.set(
            f"{info['kind']}  ·  {info['format']}  ·  "
            f"{size_kb:.1f} KB  ·  "
            f"{info['modified'].strftime('%Y-%m-%d  %H:%M')}"
        )
        self._load_and_display(info["path"])

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Open export file",
            filetypes=[
                ("All exports", "*.json *.csv"),
                ("JSON", "*.json"),
                ("CSV",  "*.csv"),
                ("All files", "*.*"),
            ]
        )
        if path:
            self._load_and_display(path)

    # Record viewer helpers
    def _load_and_display(self, path: str):
        try:
            cols, rows, kind = load_file(path)
        except Exception as e:
            messagebox.showerror("Load Error",
                                 f"Could not read file:\n{e}")
            return

        self._active_cols = cols
        self._active_rows = rows
        self._search_var.set("")

        # Rebuild column filter menu
        menu = self._col_menu["menu"]
        menu.delete(0, "end")
        menu.add_command(label="All Columns",
                         command=lambda: (
                             self._col_filter_var.set("All Columns"),
                             self._apply_search()))
        for c in cols:
            menu.add_command(
                label=c,
                command=lambda v=c: (
                    self._col_filter_var.set(v),
                    self._apply_search()))
        self._col_filter_var.set("All Columns")

        # Fixed column widths matching the export GUI exactly
        col_widths = {
            "ID": 50, "Name": 200, "Type": 160, "Status": 90,
            "Site": 140, "Role": 140, "Primary IP": 140,
            "Address": 160, "DNS Name": 180, "VRF": 120,
            "Assigned To": 200, "Description": 200,
        }
        self._tree.configure(columns=cols)
        for col in cols:
            w = col_widths.get(col, 120)
            self._tree.heading(col, text=col, anchor="center")
            self._tree.column(col, width=w, minwidth=50, anchor="center")

        self._empty_lbl.place_forget()
        self._apply_search()

        fname = os.path.basename(path)
        self._status_lbl.config(
            text=f"{fname}  ·  {kind}  ·  {len(rows)} records", fg=STATUS_OK)
        self._detail_bar_var.set(
            f"Loaded: {path}  ·  {len(cols)} columns  ·  {len(rows)} records")

    def _apply_search(self):
        if not self._active_rows:
            return

        query   = self._search_var.get().lower().strip()
        col_sel = self._col_filter_var.get()

        # Determine which column index to search (or all)
        if col_sel == "All Columns" or col_sel not in self._active_cols:
            col_idx = None
        else:
            col_idx = self._active_cols.index(col_sel)

        # Filter rows
        if query:
            if col_idx is not None:
                results = [r for r in self._active_rows
                           if col_idx < len(r) and
                           query in r[col_idx].lower()]
            else:
                results = [r for r in self._active_rows
                           if any(query in cell.lower() for cell in r)]
        else:
            results = self._active_rows

        # Repopulate tree
        self._tree.delete(*self._tree.get_children())
        for i, row in enumerate(results):
            tag = "odd" if i % 2 else "even"
            self._tree.insert("", "end", values=row, tags=(tag,))

        shown = len(results)
        total = len(self._active_rows)
        self._rec_count_var.set(
            f"{shown} of {total} records" if query
            else f"{total} records")


# Entry point
if __name__ == "__main__":
    app = RecordViewerApp()
    app.mainloop()