from __future__ import annotations
import os
import sqlite3
from typing import Dict, Any, List
from datetime import date

DB_PATH_DEFAULT = os.path.join("data", "app.db")

def _connect(db_path: str = DB_PATH_DEFAULT) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str = DB_PATH_DEFAULT) -> None:
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        contact_name TEXT,
        email TEXT,
        phone TEXT,
        address1 TEXT,
        address2 TEXT,
        zip TEXT,
        city TEXT,
        country TEXT DEFAULT 'France',
        siret TEXT,
        vat TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT NOT NULL UNIQUE,
        issue_date TEXT NOT NULL,
        due_text TEXT NOT NULL,
        operation_type TEXT NOT NULL,
        client_id INTEGER NOT NULL,
        description TEXT NOT NULL,
        qty REAL NOT NULL,
        unit TEXT NOT NULL,
        unit_price REAL NOT NULL,
        vat_rate REAL NOT NULL,
        total_ht REAL NOT NULL,
        total_vat REAL NOT NULL,
        total_ttc REAL NOT NULL,
        currency TEXT NOT NULL,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS counters (
        year INTEGER PRIMARY KEY,
        seq INTEGER NOT NULL
    );
    """)
    conn.commit()
    conn.close()

def upsert_client(data: Dict[str, Any], db_path: str = DB_PATH_DEFAULT) -> int:
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO clients (name, contact_name, email, phone, address1, address2, zip, city, country, siret, vat)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        (data.get("name") or "").strip(),
        (data.get("contact_name") or "").strip() or None,
        (data.get("email") or "").strip() or None,
        (data.get("phone") or "").strip() or None,
        (data.get("address1") or "").strip() or None,
        (data.get("address2") or "").strip() or None,
        (data.get("zip") or "").strip() or None,
        (data.get("city") or "").strip() or None,
        ((data.get("country") or "France")).strip(),
        (data.get("siret") or "").strip() or None,
        (data.get("vat") or "").strip() or None,
    ))
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return int(cid)

def list_clients(limit: int = 10, q: str = "", db_path: str = DB_PATH_DEFAULT) -> List[Dict[str, Any]]:
    conn = _connect(db_path)
    cur = conn.cursor()
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        cur.execute("""
            SELECT * FROM clients
            WHERE name LIKE ? OR email LIKE ? OR phone LIKE ?
            ORDER BY id DESC
            LIMIT ?
        """, (like, like, like, limit))
    else:
        cur.execute("SELECT * FROM clients ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_client(client_id: int, db_path: str = DB_PATH_DEFAULT) -> Dict[str, Any]:
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise ValueError("Client introuvable")
    return dict(row)

def next_invoice_number(prefix: str, issue_date: date, db_path: str = DB_PATH_DEFAULT) -> str:
    year = issue_date.year
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT seq FROM counters WHERE year = ?", (year,))
    row = cur.fetchone()
    if row:
        seq = int(row["seq"]) + 1
        cur.execute("UPDATE counters SET seq = ? WHERE year = ?", (seq, year))
    else:
        seq = 1
        cur.execute("INSERT INTO counters (year, seq) VALUES (?, ?)", (year, seq))
    conn.commit()
    conn.close()
    return f"{prefix}-{year}-{seq:03d}"

def create_invoice(data: Dict[str, Any], db_path: str = DB_PATH_DEFAULT) -> int:
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO invoices
        (number, issue_date, due_text, operation_type, client_id, description, qty, unit, unit_price, vat_rate,
         total_ht, total_vat, total_ttc, currency)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["number"],
        data["issue_date"],
        data["due_text"],
        data["operation_type"],
        data["client_id"],
        data["description"],
        data["qty"],
        data["unit"],
        data["unit_price"],
        data["vat_rate"],
        data["total_ht"],
        data["total_vat"],
        data["total_ttc"],
        data["currency"],
    ))
    conn.commit()
    inv_id = cur.lastrowid
    conn.close()
    return int(inv_id)
