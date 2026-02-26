import os
import re
import sqlite3
from pathlib import Path
from datetime import date, datetime

def data_dir() -> Path:
    # Railway Volume conseillé: /data
    base = os.getenv("DATA_DIR", "/data")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p

DB_PATH = data_dir() / "app.db"

def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS clients (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT DEFAULT '',
      phone TEXT DEFAULT '',
      address1 TEXT DEFAULT '',
      address2 TEXT DEFAULT '',
      zip TEXT DEFAULT '',
      city TEXT DEFAULT '',
      country TEXT DEFAULT 'France',
      siret TEXT DEFAULT '',
      tva TEXT DEFAULT '',
      created_at TEXT NOT NULL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      client_id INTEGER NOT NULL,
      number TEXT NOT NULL,
      issue_date TEXT NOT NULL,
      due TEXT NOT NULL,
      operation_type TEXT NOT NULL,
      description TEXT NOT NULL,
      qty REAL NOT NULL,
      unit TEXT NOT NULL,
      unit_price REAL NOT NULL,
      tax_rate REAL NOT NULL,
      total_ht REAL NOT NULL,
      total_tva REAL NOT NULL,
      total_ttc REAL NOT NULL,
      pdf_path TEXT NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY(client_id) REFERENCES clients(id)
    )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_invoices_client ON invoices(client_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_invoices_number ON invoices(number)")

    conn.commit()
    conn.close()

def set_setting(key: str, value: str):
    conn = _conn()
    c = conn.cursor()
    c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()
    conn.close()

def get_setting(key: str, default: str = "") -> str:
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    if not row:
        return default
    return row["value"]

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "client"

def add_client(
    name: str,
    email: str = "",
    phone: str = "",
    address1: str = "",
    address2: str = "",
    zip_code: str = "",
    city: str = "",
    country: str = "France",
    siret: str = "",
    tva: str = ""
) -> int:
    conn = _conn()
    c = conn.cursor()
    c.execute("""
      INSERT INTO clients(name,email,phone,address1,address2,zip,city,country,siret,tva,created_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?)
    """, (
        name.strip(),
        (email or "").strip(),
        (phone or "").strip(),
        (address1 or "").strip(),
        (address2 or "").strip(),
        (zip_code or "").strip(),
        (city or "").strip(),
        (country or "France").strip(),
        (siret or "").strip(),
        (tva or "").strip(),
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    cid = c.lastrowid
    conn.close()
    return int(cid)

def update_client(client_id: int, fields: dict):
    allowed = {"name","email","phone","address1","address2","zip","city","country","siret","tva"}
    parts = []
    vals = []
    for k,v in fields.items():
        if k in allowed:
            parts.append(f"{k}=?")
            vals.append((v or "").strip())
    if not parts:
        return
    vals.append(client_id)
    conn = _conn()
    c = conn.cursor()
    c.execute(f"UPDATE clients SET {', '.join(parts)} WHERE id=?", vals)
    conn.commit()
    conn.close()

def get_client(client_id: int):
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT * FROM clients WHERE id=?", (client_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def search_clients(q: str, limit: int = 20):
    q = (q or "").strip()
    conn = _conn()
    c = conn.cursor()
    like = f"%{q}%"
    c.execute("""
      SELECT * FROM clients
      WHERE name LIKE ? OR email LIKE ? OR phone LIKE ?
      ORDER BY name ASC
      LIMIT ?
    """, (like, like, like, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def list_clients(limit: int = 200):
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT * FROM clients ORDER BY name ASC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def next_invoice_number(prefix: str, issue: date, use_year: bool = True) -> str:
    if use_year:
        year = issue.year
        key = f"next_seq_{year}"
        forced = get_setting(key, "")
        if forced.isdigit():
            seq = int(forced)
        else:
            conn = _conn()
            c = conn.cursor()
            c.execute(
                "SELECT number FROM invoices WHERE number LIKE ? ORDER BY id DESC LIMIT 50",
                (f"{prefix}-{year}-%",)
            )
            rows = c.fetchall()
            conn.close()

            mx = 0
            for (num,) in rows:
                try:
                    mx = max(mx, int(str(num).split("-")[-1]))
                except:
                    pass
            seq = mx + 1

        set_setting(key, str(seq + 1))
        return f"{prefix}-{year}-{seq:03d}"

    # fallback sans année
    key = "next_seq"
    forced = get_setting(key, "")
    seq = int(forced) if forced.isdigit() else 1
    set_setting(key, str(seq + 1))
    return f"{prefix}-{seq:03d}"

def invoices_root() -> Path:
    p = data_dir() / "invoices"
    p.mkdir(parents=True, exist_ok=True)
    return p

def client_folder(client: dict) -> Path:
    slug = slugify(client["name"])
    p = invoices_root() / f"{slug}_{client['id']}"
    p.mkdir(parents=True, exist_ok=True)
    return p

def save_invoice(
    client_id: int,
    number: str,
    issue_date: date,
    due: str,
    operation_type: str,
    description: str,
    qty: float,
    unit: str,
    unit_price: float,
    tax_rate: float,
    total_ht: float,
    total_tva: float,
    total_ttc: float,
    pdf_path: str
) -> int:
    conn = _conn()
    c = conn.cursor()
    c.execute("""
      INSERT INTO invoices(
        client_id, number, issue_date, due, operation_type, description, qty, unit,
        unit_price, tax_rate, total_ht, total_tva, total_ttc, pdf_path, created_at
      )
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        client_id,
        number,
        issue_date.isoformat(),
        due,
        operation_type,
        description,
        float(qty),
        unit,
        float(unit_price),
        float(tax_rate),
        float(total_ht),
        float(total_tva),
        float(total_ttc),
        pdf_path,
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    iid = c.lastrowid
    conn.close()
    return int(iid)
