import os
import sqlite3
import csv
import base64
import re
from copy import deepcopy
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET
from io import BytesIO, StringIO
from urllib.parse import urlsplit
from collections import Counter
from contextlib import contextmanager, closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from math import ceil
import secrets

import qrcode
from flask import Flask, abort, jsonify, render_template, render_template_string, request, redirect, send_file, url_for, session, Response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ON_RENDER = os.environ.get('RENDER') == 'true'
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
USE_POSTGRES = bool(DATABASE_URL)
if USE_POSTGRES:
    import psycopg
    from psycopg import sql as pg_sql
app = Flask(__name__)
app.secret_key = "smart_lab_secret_key_2026_super_safe"

LAB_NUMBERS = (1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 22, 23, 24, 26, 27)
TRAINING_SEATS = range(1, 31)
ISSUE_CATEGORIES = ('أجهزة', 'برامج', 'شبكة', 'أخرى')
TICKET_STATUSES = ('مفتوح', 'قيد الإصلاح', 'تم الحل')
STATUS_TONES = dict(zip(TICKET_STATUSES, ('danger', 'warning', 'ok')))
REPORT_INTERVAL = timedelta(days=30)
RIYADH_TZ = timezone(timedelta(hours=3))
DATA_DIR = os.path.realpath(os.environ.get('SMART_LAB_DATA_DIR') or os.path.join(BASE_DIR, 'lab_databases'))
LEGACY_DB_PATH = os.environ.get('SMART_LAB_LEGACY_DB', os.path.join(BASE_DIR, 'maintenance.db'))
TICKET_COLUMNS = 'id, lab_num, seat_num, reporter_name, issue_category, issue, status, replaced_parts, created_at'

# شعار المؤسسة الرسمي
# Source: https://tvtc.gov.sa/Style%20Library/tvtc/images/logo.svg

@app.context_processor
def inject_institution_logo():
    return {'institution_logo': url_for('static', filename='institution-logo.svg')}

def utc_now():
    # Databases store UTC; only the dates shown to the user use Riyadh time.
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def db_time(value):
    return value.strftime('%Y-%m-%d %H:%M:%S')


def parse_time(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def local_time(value):
    return parse_time(value).replace(tzinfo=timezone.utc).astimezone(RIYADH_TZ).strftime('%Y-%m-%d %H:%M')


class LabDatabase:
    """Keep lab-scoped queries portable between local SQLite and PostgreSQL."""

    def __init__(self, connection, lab_num, postgres=False):
        self.connection = connection
        self.lab_num = lab_num
        self.postgres = postgres

    def execute(self, statement, parameters=()):
        if self.postgres:
            if statement.strip().upper() == 'BEGIN IMMEDIATE':
                # Serialize a lab's writes, including rechecks after waiting.
                return self.connection.execute(
                    'SELECT pg_catalog.pg_advisory_xact_lock(%s, %s)',
                    (1397506370, self.lab_num)
                )
            # All SQL here is application-owned; question marks are parameters.
            statement = statement.replace('?', '%s')
        return self.connection.execute(statement, parameters)

    def executemany(self, statement, rows):
        if self.postgres:
            with self.connection.cursor() as cursor:
                cursor.executemany(statement.replace('?', '%s'), rows)
        else:
            self.connection.executemany(statement, rows)

    def insert_id(self, statement, parameters):
        if self.postgres:
            return self.execute(statement + ' RETURNING id', parameters).fetchone()[0]
        return self.execute(statement, parameters).lastrowid

    def reset_identity(self, table):
        if table not in ('tickets', 'report_exports'):
            raise ValueError('Invalid identity table')
        if self.postgres:
            self.execute(
                f"SELECT setval(pg_get_serial_sequence(?, 'id'), "
                f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table}", (table,)
            )


def select_lab_schema(connection, lab_num, initialize=False):
    if lab_num not in LAB_NUMBERS:
        raise ValueError('رقم المعمل غير صحيح')
    schema = pg_sql.Identifier(f'smart_lab_{lab_num}')
    if initialize:
        connection.execute(pg_sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(schema))
    # LOCAL works with Neon's transaction pooler and resets at commit/rollback.
    connection.execute(pg_sql.SQL('SET LOCAL search_path TO {}').format(schema))


@contextmanager
def lab_connection(lab_num, initialize=False):
    if lab_num not in LAB_NUMBERS:
        raise ValueError('رقم المعمل غير صحيح')
    if USE_POSTGRES:
        with psycopg.connect(DATABASE_URL, connect_timeout=15, prepare_threshold=None) as connection:
            database = LabDatabase(connection, lab_num, postgres=True)
            if initialize:
                database.execute('BEGIN IMMEDIATE')
            select_lab_schema(connection, lab_num, initialize=initialize)
            yield database
    else:
        connection = sqlite3.connect(os.path.join(DATA_DIR, f'lab_{lab_num}.db'), timeout=30)
        try:
            with connection:
                yield LabDatabase(connection, lab_num)
        finally:
            connection.close()


def ensure_report_anchor(conn):
    first = conn.execute('SELECT MIN(created_at) FROM tickets').fetchone()[0]
    if first:
        conn.execute("INSERT INTO settings (key, value) VALUES ('report_anchor', ?) ON CONFLICT (key) DO NOTHING", (db_time(parse_time(first)),))


def prepare_storage():
    if USE_POSTGRES:
        return
    if ON_RENDER:
        raise RuntimeError(
            'Set DATABASE_URL in Render Environment to an external PostgreSQL '
            'connection URL (for example, Neon Free). No paid Render disk is required.'
        )
    os.makedirs(DATA_DIR, exist_ok=True)


def init_db():
    prepare_storage()
    identity = 'BIGSERIAL PRIMARY KEY' if USE_POSTGRES else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    timestamp_default = "(to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))" if USE_POSTGRES else 'CURRENT_TIMESTAMP'
    archive_binary = 'BYTEA' if USE_POSTGRES else 'BLOB'
    for lab_num in LAB_NUMBERS:
        with lab_connection(lab_num, initialize=True) as conn:
            # The CHECK also prevents accidentally writing another lab's ticket here.
            conn.execute(f'''
                CREATE TABLE IF NOT EXISTS tickets (
                    id {identity},
                    lab_num INTEGER NOT NULL CHECK (lab_num = {lab_num}),
                    seat_num INTEGER,
                    reporter_name TEXT,
                    issue_category TEXT,
                    issue TEXT,
                    status TEXT DEFAULT 'مفتوح',
                    replaced_parts TEXT DEFAULT 'لا يوجد',
                    created_at TEXT DEFAULT {timestamp_default}
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS ticket_dates ON tickets (created_at)')
            conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            conn.execute(f'''CREATE TABLE IF NOT EXISTS report_exports (
                id {identity},
                start_at TEXT NOT NULL UNIQUE,
                end_at TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                generated_by TEXT NOT NULL,
                csv_data {archive_binary} NOT NULL
            )''')
            conn.execute('BEGIN IMMEDIATE')
            migrated = conn.execute("SELECT 1 FROM settings WHERE key = 'legacy_migrated_v1'").fetchone()
            if not migrated and os.path.isfile(LEGACY_DB_PATH):
                # Copy once, transactionally, leaving maintenance.db untouched.
                legacy_uri = Path(LEGACY_DB_PATH).resolve().as_uri() + '?mode=ro'
                with closing(sqlite3.connect(legacy_uri, uri=True)) as legacy:
                    rows = legacy.execute(f'SELECT {TICKET_COLUMNS} FROM tickets WHERE lab_num = ?', (lab_num,)).fetchall()
                conn.executemany(f'INSERT INTO tickets ({TICKET_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', rows)
                conn.reset_identity('tickets')
                conn.execute("INSERT INTO settings (key, value) VALUES ('legacy_migrated_v1', 'done')")
            ensure_report_anchor(conn)


def all_tickets(lab_num=None):
    rows = []
    for number in LAB_NUMBERS if lab_num is None else (lab_num,):
        with lab_connection(number) as conn:
            rows.extend(conn.execute(f'SELECT {TICKET_COLUMNS} FROM tickets').fetchall())
    return sorted(rows, key=lambda row: (row[8], row[0], row[1]), reverse=True)


def report_window(conn, now=None):
    anchor = conn.execute("SELECT value FROM settings WHERE key = 'report_anchor'").fetchone()
    if not anchor:
        return None
    previous = conn.execute('SELECT end_at FROM report_exports ORDER BY end_at DESC LIMIT 1').fetchone()
    start = parse_time(previous[0] if previous else anchor[0])
    end = start + REPORT_INTERVAL
    now = utc_now() if now is None else now
    due_count = max(0, (now - start) // REPORT_INTERVAL)
    count = conn.execute('SELECT COUNT(*) FROM tickets WHERE created_at >= ? AND created_at < ?', (db_time(start), db_time(end))).fetchone()[0]
    return {
        'start': db_time(start), 'end': db_time(end),
        'start_label': local_time(db_time(start)), 'end_label': local_time(db_time(end)),
        'due': now >= end, 'due_count': due_count,
        'days_left': max(0, ceil((end - now).total_seconds() / 86400)),
        'ticket_count': count,
        'filename': f'lab_report_{start:%Y%m%d}_{end:%Y%m%d}.xlsx'
    }


def report_summaries(now=None):
    summaries = []
    now = utc_now() if now is None else now
    for lab_num in LAB_NUMBERS:
        with lab_connection(lab_num) as conn:
            window = report_window(conn, now)
            archives = conn.execute('SELECT id, start_at, end_at, generated_at FROM report_exports ORDER BY start_at DESC').fetchall()
        summaries.append({'lab_num': lab_num, 'window': window, 'archives': archives})
    return summaries

init_db()

USERS = {
    "admin": {"password": "123", "role": "مشرف الصيانة التقنية", "name": "محمد الدوخي"},
    "tech": {"password": "123", "role": "فني دعم المعامل", "name": "الدعم الفني"},
    "trainer": {"password": "123", "role": "رئيس قسم الحاسب", "name": "رئيس القسم"}
}

# --- صفحة تسجيل الدخول (اسم المستخدم مخفي افتراضياً + زر رئيس القسم) ---
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#071523">
    <title>تسجيل الدخول | نظام صيانة حواسيب المعامل</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800;900&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        [hidden] { display: none !important; }
        :root { color-scheme: light; --ink: #142f42; --teal: #087f8b; --muted: #64748b; }
        body {
            margin: 0;
            min-height: 100vh;
            min-height: 100svh;
            padding: 32px 24px 22px;
            display: flex;
            flex-direction: column;
            gap: 24px;
            font-family: 'Tajawal', 'Noto Sans Arabic', Tahoma, Arial, sans-serif;
            background: radial-gradient(ellipse at 12% 20%, #123c49 0, transparent 48%),
                        radial-gradient(ellipse at 90% 85%, #122f49 0, transparent 46%), #071523;
            color: var(--ink);
        }
        body::before {
            content: '';
            position: fixed;
            inset: 0;
            pointer-events: none;
            background-image: linear-gradient(#ffffff05 1px, transparent 1px),
                              linear-gradient(90deg, #ffffff05 1px, transparent 1px);
            background-size: 64px 64px;
        }
        button, input { font: inherit; }
        button { cursor: pointer; }
        button:focus-visible { outline: 3px solid #16afbe; outline-offset: 3px; }
        .icon { width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
        .icon-definitions { position: absolute; width: 0; height: 0; overflow: hidden; }
        .login-shell {
            position: relative;
            z-index: 1;
            width: min(100%, 980px);
            margin: auto;
            display: grid;
            grid-template-columns: minmax(0, 440px) minmax(0, 1fr);
            gap: clamp(40px, 6vw, 90px);
            align-items: center;
        }
        .login-card {
            grid-column: 1;
            grid-row: 1;
            width: 100%;
            border-radius: 26px;
            background: #ffffff;
            border: 1px solid #ffffffb3;
            overflow: hidden;
            box-shadow: 0 32px 90px #00000040, 0 1px 0 #ffffff80 inset;
        }
        .brand-header { padding: 20px 30px 12px; border-bottom: 1px solid #edf1f5; }
        .institution-brand { width: min(100%, 320px); aspect-ratio: 10 / 3; margin: 0 auto; overflow: hidden; background: white; }
        .institution-brand img { display: block; width: 100%; height: 100%; object-fit: contain; object-position: center; }
        .card-content { padding: 25px 30px 28px; }
        .eyebrow { display: flex; align-items: center; gap: 6px; margin: 0 0 9px; color: var(--teal); font-size: 12px; font-weight: 700; }
        .eyebrow .icon { width: 15px; height: 15px; }
        .card-content h2 { font-size: 23px; line-height: 1.4; font-weight: 800; margin: 0 0 6px; letter-spacing: -0.3px; }
        .card-subtitle { font-size: 13px; line-height: 1.7; color: var(--muted); margin: 0 0 24px; }
        .error-message { padding: 12px 14px; margin-bottom: 18px; border: 1px solid #fecaca; border-radius: 12px; background: #fff5f5; color: #b42318; font-size: 13px; line-height: 1.7; }
        .field + .field { margin-top: 18px; }
        .field label { display: block; margin-bottom: 8px; font-size: 13px; font-weight: 700; color: #334155; }
        .input-wrap { position: relative; }
        .input-wrap input {
            width: 100%;
            height: 50px;
            padding: 0 44px 0 50px;
            border: 1px solid #dbe3eb;
            border-radius: 12px;
            background: #f8fafc;
            color: #142f42;
            font-size: 14px;
            text-align: right;
            direction: ltr;
            outline: none;
            transition: border-color .18s, background .18s, box-shadow .18s;
        }
        .input-wrap input::placeholder { color: #a0acb9; opacity: 1; letter-spacing: 2px; }
        .input-wrap input:focus { border-color: #098c9a; background: #ffffff; box-shadow: 0 0 0 3px #098c9a1a; }
        .field-icon { position: absolute; right: 15px; top: 15px; width: 19px; height: 19px; color: #788a9a; pointer-events: none; }
        .visibility-button { position: absolute; left: 3px; top: 3px; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; background: transparent; color: #64748b; border: none; border-radius: 9px; }
        .visibility-button:hover { color: #087f8b; background: #eaf5f6; }
        .submit-button {
            width: 100%;
            height: 50px;
            margin-top: 23px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            border: 0;
            border-radius: 12px;
            color: #ffffff;
            background: linear-gradient(105deg, #17577c, #087f8b);
            box-shadow: 0 7px 18px #087f8b24;
            font-size: 15px;
            font-weight: 800;
            transition: filter .18s, transform .18s, box-shadow .18s;
        }
        .submit-button:hover { filter: brightness(1.08); transform: translateY(-1px); box-shadow: 0 9px 22px #087f8b33; }
        .submit-button:active { transform: translateY(0); }
        .submit-button:disabled { opacity: .75; cursor: wait; transform: none; }
        .button-spinner { width: 17px; height: 17px; border: 2px solid #ffffff55; border-top-color: #ffffff; border-radius: 50%; animation: spin .8s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .quick-login { margin-top: 25px; padding-top: 19px; border-top: 1px solid #e9eef3; }
        .quick-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
        .quick-heading strong { font-size: 12px; color: #334155; }
        .quick-heading span { font-size: 11px; color: var(--muted); }
        .role-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
        .role-button { min-height: 65px; padding: 11px 4px 9px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; border: 1px solid #dfe7ef; border-radius: 11px; color: #475569; background: #f8fafc; font-size: 11px; font-weight: 700; transition: border-color .18s, background .18s, color .18s; }
        .role-button .icon { width: 19px; height: 19px; color: #648198; }
        .role-button:hover, .role-button[aria-pressed="true"] { border-color: #8fc7cc; background: #edf8f8; color: #0a6c76; }
        .role-button:hover .icon, .role-button[aria-pressed="true"] .icon { color: #087f8b; }
        .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
        .intro-panel { grid-column: 2; grid-row: 1; color: #ffffff; padding-bottom: 10px; }
        .product-kicker { display: inline-flex; align-items: center; gap: 9px; margin: 0 0 26px; color: #a6c4d1; font-size: 13px; font-weight: 500; }
        .product-kicker .icon { color: #6bd3cd; }
        .intro-panel h1 { font-size: clamp(34px, 3.4vw, 44px); line-height: 1.5; margin: 0 0 18px; font-weight: 800; letter-spacing: -.5px; }
        .intro-panel h1 span { color: #73d9d0; }
        .intro-description { max-width: 400px; color: #adc3d0; font-size: 15px; line-height: 1.95; margin: 0 0 34px; }
        .feature-list { display: flex; flex-direction: column; gap: 21px; }
        .feature { display: flex; gap: 14px; align-items: center; }
        .feature-mark { width: 43px; height: 43px; display: flex; align-items: center; justify-content: center; border: 1px solid #8dcee326; border-radius: 12px; background: #ffffff06; color: #77d6d3; }
        .feature h3 { margin: 0 0 4px; font-size: 14px; font-weight: 700; }
        .feature p { margin: 0; color: #97b4c4; font-size: 12px; line-height: 1.7; }
        .page-footer { position: relative; z-index: 1; text-align: center; color: #8fa9ba; font-size: 11px; line-height: 1.9; }
        .page-footer p { margin: 0; }
        .page-footer strong { color: #c5d7e3; font-weight: 500; }
        .credit-separator { margin: 0 7px; color: #527584; }
        @media (max-width: 800px) {
            body { padding: 22px 16px 18px; gap: 20px; }
            .login-shell { display: block; max-width: 430px; }
            .intro-panel { display: none; }
            .card-content { padding: 23px 28px 25px; }
            .brand-header { padding: 17px 28px 11px; }
        }
        @media (max-width: 380px) {
            body { padding: 16px 12px; }
            .card-content { padding: 21px 21px 23px; }
            .brand-header { padding: 15px 21px 10px; }
            .card-content h2 { font-size: 21px; }
            .card-subtitle { font-size: 12px; }
            .quick-heading span { font-size: 10px; }
            .role-grid { gap: 6px; }
            .role-button { font-size: 10px; }
        }
        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { transition: none !important; animation: none !important; }
        }
    </style>
</head>
<body>
    <svg class="icon-definitions" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
        <symbol id="icon-user" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/></symbol>
        <symbol id="icon-lock" viewBox="0 0 24 24"><rect x="5" y="10" width="14" height="11" rx="2.5"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/></symbol>
        <symbol id="icon-eye" viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></symbol>
        <symbol id="icon-eye-off" viewBox="0 0 24 24"><path d="m3 3 18 18M10.6 5.1A12 12 0 0 1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-3.1 4.1M6 6.6A20 20 0 0 0 2 12s3.5 7 10 7a11 11 0 0 0 5.4-1.4M10 10a3 3 0 0 0 4 4"/></symbol>
        <symbol id="icon-arrow" viewBox="0 0 24 24"><path d="M20 12H4m6-6-6 6 6 6"/></symbol>
        <symbol id="icon-wrench" viewBox="0 0 24 24"><path d="M14.7 6.3a5 5 0 0 0-6.4 6.4l-5 5a2.1 2.1 0 0 0 3 3l5-5a5 5 0 0 0 6.4-6.4l-3 3-3-3 3-3Z"/></symbol>
        <symbol id="icon-headset" viewBox="0 0 24 24"><path d="M4 13V11a8 8 0 0 1 16 0v2M20 17v1a3 3 0 0 1-3 3h-4"/><rect x="3" y="12" width="4" height="7" rx="2"/><rect x="17" y="12" width="4" height="7" rx="2"/></symbol>
        <symbol id="icon-building" viewBox="0 0 24 24"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h1m4 0h1M9 11h1m4 0h1M10 21v-5h4v5"/></symbol>
        <symbol id="icon-monitor" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="13" rx="2"/><path d="M12 16v5m-5 0h10M7 7h5m-5 4h9"/></symbol>
        <symbol id="icon-ticket" viewBox="0 0 24 24"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2h6v2M9 10h6m-6 4h6m-6 4h3"/></symbol>
        <symbol id="icon-chart" viewBox="0 0 24 24"><path d="M4 3v18h17M8 17v-5m5 5V7m5 10v-8"/></symbol>
    </svg>

    <main class="login-shell">
        <section class="login-card" aria-labelledby="login-title">
            <header class="brand-header">
                <div class="institution-brand">
                    <img src="{{ institution_logo }}" alt="المؤسسة العامة للتدريب التقني والمهني" decoding="async" fetchpriority="high">
                </div>
            </header>
            <div class="card-content">
                <p class="eyebrow"><svg class="icon" aria-hidden="true"><use href="#icon-lock"/></svg> بوابة فريق الصيانة</p>
                <h2 id="login-title">نظام إدارة صيانة المعامل</h2>
                <p class="card-subtitle">سجّل الدخول لمتابعة البلاغات وإدارة المعامل.</p>

                {% if error %}
                <div class="error-message" role="alert">{{ error }}</div>
                {% endif %}

                <form id="login-form" method="POST" action="/login" onsubmit="handleLoginSubmit()">
                    <div class="field">
                        <label for="username-input">اسم المستخدم</label>
                        <div class="input-wrap">
                            <svg class="icon field-icon" aria-hidden="true"><use href="#icon-user"/></svg>
                            <input type="password" id="username-input" name="username" required placeholder="••••••" autocomplete="username" autocapitalize="none" spellcheck="false">
                            <button type="button" id="username-toggle" class="visibility-button" onclick="toggleUsernameVisibility()" aria-label="إظهار اسم المستخدم" aria-controls="username-input" aria-pressed="false">
                                <svg id="user-eye-icon" class="icon" aria-hidden="true"><use href="#icon-eye"/></svg>
                            </button>
                        </div>
                    </div>
                    <div class="field">
                        <label for="password-input">كلمة المرور</label>
                        <div class="input-wrap">
                            <svg class="icon field-icon" aria-hidden="true"><use href="#icon-lock"/></svg>
                            <input type="password" id="password-input" name="password" required placeholder="••••••" autocomplete="current-password">
                            <button type="button" id="password-toggle" class="visibility-button" onclick="togglePasswordVisibility()" aria-label="إظهار كلمة المرور" aria-controls="password-input" aria-pressed="false">
                                <svg id="pass-eye-icon" class="icon" aria-hidden="true"><use href="#icon-eye"/></svg>
                            </button>
                        </div>
                    </div>
                    <button type="submit" id="submit-btn" class="submit-button">
                        <span id="btn-text">تسجيل الدخول</span>
                        <svg id="submit-arrow" class="icon" aria-hidden="true"><use href="#icon-arrow"/></svg>
                        <span id="btn-spinner" class="button-spinner" aria-hidden="true" hidden></span>
                    </button>
                </form>

                <div class="quick-login">
                    <div class="quick-heading"><strong>دخول سريع</strong><span>تعبئة البيانات حسب الدور</span></div>
                    <div class="role-grid">
                        <button type="button" class="role-button" data-user="admin" aria-pressed="false" onclick="fastFill('admin', '123')"><svg class="icon" aria-hidden="true"><use href="#icon-wrench"/></svg><span>مشرف الصيانة</span></button>
                        <button type="button" class="role-button" data-user="tech" aria-pressed="false" onclick="fastFill('tech', '123')"><svg class="icon" aria-hidden="true"><use href="#icon-headset"/></svg><span>الدعم الفني</span></button>
                        <button type="button" class="role-button" data-user="trainer" aria-pressed="false" onclick="fastFill('trainer', '123')"><svg class="icon" aria-hidden="true"><use href="#icon-building"/></svg><span>رئيس القسم</span></button>
                    </div>
                    <p id="fill-notice" class="sr-only" role="status" aria-live="polite"></p>
                </div>
            </div>
        </section>

        <aside class="intro-panel" aria-label="عن النظام">
            <p class="product-kicker"><svg class="icon" aria-hidden="true"><use href="#icon-monitor"/></svg> قسم الحاسب الآلي وتقنية المعلومات</p>
            <h1>صيانة منظّمة.<br><span>معامل جاهزة للتدريب.</span></h1>
            <p class="intro-description">بلاغات الأعطال، حالة الأجهزة، وتقارير الصيانة في مكان واحد، لمتابعة أوضح وعمل أكثر تنظيمًا.</p>
            <div class="feature-list">
                <div class="feature"><div class="feature-mark"><svg class="icon" aria-hidden="true"><use href="#icon-ticket"/></svg></div><div><h3>متابعة البلاغات</h3><p>من تسجيل العطل حتى إتمام الإصلاح.</p></div></div>
                <div class="feature"><div class="feature-mark"><svg class="icon" aria-hidden="true"><use href="#icon-monitor"/></svg></div><div><h3>رصد حالة الأجهزة</h3><p>نظرة واضحة على الأجهزة والمعامل.</p></div></div>
                <div class="feature"><div class="feature-mark"><svg class="icon" aria-hidden="true"><use href="#icon-chart"/></svg></div><div><h3>تقارير الصيانة</h3><p>توثيق الأعطال والقطع المستبدلة.</p></div></div>
            </div>
        </aside>
    </main>

    <footer class="page-footer">
        <p>قسم الحاسب الآلي وتقنية المعلومات</p>
        <p>إشراف: <strong>أ. محمد الدوخي</strong><span class="credit-separator">•</span>إعداد: <strong>ريان المحيطيب</strong></p>
    </footer>

    <script>
        function fastFill(user, pass) {
            document.getElementById('username-input').value = user;
            document.getElementById('password-input').value = pass;
            document.querySelectorAll('.role-button').forEach(function(button) {
                button.setAttribute('aria-pressed', String(button.dataset.user === user));
            });
            const selected = document.querySelector('.role-button[aria-pressed="true"]');
            document.getElementById('fill-notice').textContent = selected ? 'تمت تعبئة بيانات ' + selected.textContent.trim() : '';
        }

        function toggleFieldVisibility(inputId, buttonId, iconId, label) {
            const input = document.getElementById(inputId);
            const button = document.getElementById(buttonId);
            const showing = input.type === 'password';
            input.type = showing ? 'text' : 'password';
            button.setAttribute('aria-pressed', String(showing));
            button.setAttribute('aria-label', (showing ? 'إخفاء ' : 'إظهار ') + label);
            document.getElementById(iconId).querySelector('use').setAttribute('href', showing ? '#icon-eye-off' : '#icon-eye');
        }

        function toggleUsernameVisibility() {
            toggleFieldVisibility('username-input', 'username-toggle', 'user-eye-icon', 'اسم المستخدم');
        }

        function togglePasswordVisibility() {
            toggleFieldVisibility('password-input', 'password-toggle', 'pass-eye-icon', 'كلمة المرور');
        }

        function handleLoginSubmit() {
            const button = document.getElementById('submit-btn');
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');
            document.getElementById('btn-text').textContent = 'جاري تسجيل الدخول...';
            document.getElementById('submit-arrow').setAttribute('hidden', '');
            document.getElementById('btn-spinner').hidden = false;
        }

        window.addEventListener('pageshow', function() {
            const button = document.getElementById('submit-btn');
            button.disabled = false;
            button.removeAttribute('aria-busy');
            document.getElementById('btn-text').textContent = 'تسجيل الدخول';
            document.getElementById('submit-arrow').removeAttribute('hidden');
            document.getElementById('btn-spinner').hidden = true;
        });
    </script>
</body>
</html>
"""

# --- صفحة لوحة العمليات ومخطط الرادار التفاعلي ---
# --- نموذج باركودات QR الموحدة (مقاس 15×15 سم على A4) ---
QR_LABELS_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>طباعة باركودات المعامل (A4 - 15x15 سم)</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='dashboard.css') }}">
    <style>
        .institution-brand {
            width: min(100%, 320px);
            aspect-ratio: 10 / 3;
            margin: 0 auto 12px;
            background: #ffffff;
            border-radius: 10px;
            overflow: hidden;
            flex-shrink: 0;
        }
        .institution-brand img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: contain;
            object-position: center;
        }
        body { padding: clamp(12px, 3vw, 30px); }
        .tools { max-width: 850px; margin: 0 auto 24px; padding: clamp(14px, 3vw, 24px); }
        .tools h1 { margin: 0 0 6px; font-size: clamp(19px, 4vw, 23px); }
        .tools p { font-size: 13px; color: var(--muted); margin: 0 0 14px; }
        .tools form { display: flex; gap: 10px; align-items: end; flex-wrap: wrap; }
        .tools label { flex: 1; min-width: min(260px, 100%); font-size: 13px; font-weight: bold; }
        .tools input { width: 100%; margin-top: 6px; padding: 8px 11px; direction: ltr; }
        .tools .error { color: var(--danger); margin: 8px 0 0; }

        .pages-container { display: flex; flex-direction: column; align-items: center; gap: 20px; }

        .a4-sheet {
            width: min(210mm, 100%);
            min-height: 297mm;
            background: white;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            display: flex;
            align-items: center;
            justify-content: center;
            box-sizing: border-box;
            page-break-after: always;
            break-after: page;
        }

        .qr-card-15cm {
            width: min(150mm, calc(100% - 20px));
            height: 150mm;
            border: 3px solid #0a6c65;
            outline: 1.5px dashed #6bb9ab;
            outline-offset: -7px;
            border-radius: 16px;
            padding: 9mm 7mm 7mm;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            align-items: center;
            text-align: center;
            box-sizing: border-box;
            background: #ffffff;
        }

        .qr-card-header .dept-title { font-size: 11px; font-weight: 700; color: #0a6c65; margin: 0 0 3px; }
        .qr-card-header .lab-title { font-size: 26px; font-weight: 900; color: #0f172a; margin: 0; }

        .qr-image-wrapper {
            width: 82mm;
            height: 82mm;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 2mm;
        }
        .qr-image-wrapper img { width: 100%; height: 100%; object-fit: contain; }

        .qr-card-footer .instruction { font-size: 12px; font-weight: 800; color: #0f172a; margin: 0 0 3px; }
        .qr-card-footer .meta { font-size: 9px; color: #64748b; margin: 0; }

        @media screen and (max-width: 600px) {
            .a4-sheet { min-height: 0; padding-block: 14px; }
            .qr-card-15cm { height: auto; padding: 18px 12px 14px; gap: 12px; }
            .qr-image-wrapper { width: min(82mm, 100%); height: auto; aspect-ratio: 1; }
        }

        @page {
            size: A4 portrait;
            margin: 0;
        }
        @media print {
            body { margin: 0; padding: 0; background: white; }
            .tools { display: none !important; }
            .pages-container { gap: 0; }
            .a4-sheet {
                width: 210mm;
                height: 297mm;
                margin: 0;
                box-shadow: none;
                page-break-after: always !important;
                break-after: page !important;
            }
        }
    </style>
</head>
<body>
    <div class="tools card">
        <h1>{% if selected_lab %}طباعة رمز QR لمعمل ({{ selected_lab }}){% else %}طباعة رموز QR للمعامل{% endif %}</h1>
        <p>يُطبع كل رمز في منتصف ورقة A4 بمقاس 15 × 15 سم.</p>
        <form method="GET">
            {% if selected_lab %}<input type="hidden" name="lab" value="{{ selected_lab }}">{% endif %}
            <label>رابط النظام (الذي يفتحه جوال المتدرب عند المسح)
                <input name="base" type="url" required value="{{ base_url }}" placeholder="https://smart-lab-k5r2.onrender.com">
            </label>
            <button class="button" type="submit">تحديث الرابط</button>
            {% if not error %}
            <button class="button button-primary" type="button" onclick="window.print()">{% if selected_lab %}طباعة الرمز{% else %}طباعة الرموز{% endif %}</button>
            {% endif %}
            {% if selected_lab %}<a class="button" href="{{ url_for('qr_labels', base=base_url) }}">عرض كل المعامل</a>{% endif %}
            <a class="button" href="{{ url_for('dashboard', lab=selected_lab, _anchor='labs' if selected_lab else none) }}">العودة للوحة المتابعة</a>
        </form>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
    </div>

    {% if not error %}
    <div class="pages-container">
        {% for lab in labs %}
        <div class="a4-sheet">
            <div class="qr-card-15cm">
                <div class="qr-card-header">
                    <div class="institution-brand" style="width:75mm;max-width:100%;margin:0 auto 1.5mm;">
                        <img src="{{ institution_logo }}" alt="شعار المؤسسة العامة للتدريب التقني والمهني">
                    </div>
                    <p class="dept-title">قسم الحاسب الآلي وتقنية المعلومات</p>
                    <h2 class="lab-title">معمل ({{ lab }})</h2>
                </div>

                <div class="qr-image-wrapper">
                    <img src="{{ url_for('lab_qr', lab_num=lab, base=base_url) }}" alt="باركود صيانة معمل {{ lab }}">
                </div>

                <div class="qr-card-footer">
                    <p class="instruction">امسح الرمز بكاميرا الجوال للإبلاغ الفوري عن أي عطل</p>
                    <p class="meta">النظام الذكي لصيانة المعامل • إشراف: أ. محمد الدوخي • إعداد: ريان المحيطيب</p>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
    {% endif %}
</body>
</html>
"""

REPORTS_TEMPLATE = """
{% from 'icons.html' import icon, sprite %}
{% macro preview_button(url, label) -%}
<button class="button icon-button report-eye" type="button" data-preview-url="{{ url }}"
        aria-label="{{ label }}" title="{{ label }}" aria-haspopup="dialog" aria-controls="report-preview">
    <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6-10-6-10-6Z"/>
        <circle cx="12" cy="12" r="2.5"/>
    </svg>
</button>
{%- endmacro %}
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>تقارير المعامل | كل ٣٠ يومًا</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='dashboard.css') }}">
    <style>
        main { max-width: 1200px; margin: auto; padding: 28px 20px; }
        header { display: flex; gap: 16px; align-items: center; justify-content: space-between; flex-wrap: wrap; margin-bottom: 20px; }
        h1 { font-size: clamp(22px, 4vw, 28px); } h2 { font-size: 17px; } p { margin: 6px 0; }
        .logo { width: 205px; max-width: 100%; border-radius: 10px; background: white; padding: 8px; }
        .intro, .report-summary { padding: 17px; }
        .intro { border: 1px solid #c6e2df; border-radius: 15px; background: #eaf5f3; margin-bottom: 18px; }
        .muted, dt, footer { color: var(--muted); }
        .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
        .report-summary { scroll-margin-top: 18px; display: flex; flex-direction: column; gap: 11px; }
        .due { border-color: #d6a662; }
        .heading { display: flex; justify-content: space-between; align-items: center; gap: 7px; }
        .badge { padding: 3px 9px; border-radius: 20px; background: var(--accent-tint); color: var(--accent-dark); font-size: 11px; font-weight: 700; }
        .due .badge { background: var(--warning-tint); color: var(--warning); }
        dd { margin: 0 0 7px; } time { font-variant-numeric: tabular-nums; display: inline-block; direction: ltr; }
        .report-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
        .report-actions > a { min-width: 0; overflow-wrap: anywhere; }
        .report-eye { flex: none; width: 44px; min-height: 44px; color: var(--accent-dark); }
        .export-form .button-primary { flex: 1; min-width: 0; white-space: normal; }
        .export-form button:disabled { opacity: .6; cursor: wait; }
        details { border-top: 1px solid var(--border); padding-top: 11px; } summary { cursor: pointer; }
        .archive-list { padding: 0; list-style: none; }
        .archive-list li { margin-top: 7px; }
        .message { color: var(--danger); }
        .report-summary a { color: var(--accent-dark); text-decoration: underline; text-underline-offset: 3px; }
        .report-summary > .report-actions { margin-top: auto; }
        footer { text-align: center; margin-top: 24px; }
        html:has(.report-preview[open]) { overflow: hidden; }
        .report-preview {
            width: min(1080px, calc(100% - 24px));
            max-height: calc(100vh - 30px);
            max-height: calc(100dvh - 30px);
            overscroll-behavior: contain;
        }
        .report-preview-heading {
            position: sticky;
            top: 0;
            z-index: 1;
            padding: 13px 16px;
            background: var(--surface);
            border-bottom: 1px solid var(--border);
        }
        .report-preview-heading p { color: var(--muted); margin: 4px 0 0; }
        .report-preview-heading .button { flex: none; width: 40px; min-height: 40px; }
        .report-preview-body { padding: 12px 16px 16px; }
        #preview-message { color: var(--muted); margin: 0; }
        #preview-message[data-state="error"] { color: var(--danger); }
        .preview-table-wrap {
            margin-top: 10px;
            border: 1px solid var(--border);
            border-radius: 10px;
            overflow-x: auto;
        }
        .preview-table { width: 100%; min-width: 820px; border-collapse: collapse; }
        .preview-table th, .preview-table td {
            text-align: start;
            vertical-align: top;
            padding: 8px 10px;
            border-bottom: 1px solid var(--border);
            overflow-wrap: anywhere;
        }
        .preview-table th { background: var(--subtle); color: var(--muted); font-weight: 700; }
        .preview-table td { white-space: pre-wrap; }
        .preview-table tbody tr:last-child td { border-bottom: 0; }
        .preview-table td[data-format="issue"] { min-width: 150px; }
        .preview-table bdi { font-variant-numeric: tabular-nums; }
        @media (max-width: 950px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
        @media (max-width: 860px) {
            .preview-table, .preview-table tbody { display: block; min-width: 0; }
            .preview-table thead {
                position: absolute;
                width: 1px;
                height: 1px;
                overflow: hidden;
                clip-path: inset(50%);
            }
            .preview-table tbody tr {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                padding: 5px;
                border-bottom: 1px solid var(--border);
            }
            .preview-table tbody tr:last-child { border-bottom: 0; }
            .preview-table td { display: block; border: 0; padding: 5px 7px; }
            .preview-table td::before {
                display: block;
                color: var(--muted);
                font-size: 11px;
                content: attr(data-label);
            }
            .preview-table td[data-format="issue"] { grid-column: 1 / -1; min-width: 0; }
        }
        @media (max-width: 600px) { main { padding: 20px 14px; } .grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
{{ sprite() }}
<main>
    <header>
        <div><img class="logo" src="{{ institution_logo }}" alt="شعار المؤسسة"><h1>تقارير صيانة المعامل</h1></div>
        <a class="button" href="{{ url_for('dashboard') }}">العودة للوحة المتابعة</a>
    </header>
    <section class="intro">
        <h2>تقرير مستقل لكل معمل، كل ٣٠ يومًا</h2>
        <p>يبدأ العدّ من أول بلاغ في المعمل. عند اكتمال الفترة يظهر طلب استخراج تقريرها، وتستمر الفترات بالتتابع دون حذف البلاغات.</p>
        <p class="muted">يشمل التقرير البلاغات المسجلة خلال الفترة، بحالتها وقت استخراج التقرير. البداية شاملة والنهاية غير شاملة، وجميع المواعيد بتوقيت الرياض.</p>
        <p class="muted">عند تأخر استخراج التقارير، يستمر طلب كل فترة مكتملة على حدة. تُحفظ نسخة كل تقرير ويمكن تحميلها مجددًا.</p>
    </section>
    <div class="grid">
    {% for report in reports %}
        {% set window = report.window %}
        <article id="lab-{{ report.lab_num }}" class="card report-summary{% if window and window.due %} due{% endif %}">
            <div class="heading"><h2>معمل {{ report.lab_num }}</h2><span class="badge">{% if window and window.due %}التقرير مطلوب{% elif window %}الفترة جارية{% else %}بانتظار أول بلاغ{% endif %}</span></div>
            {% if window %}
            <dl>
                <dt>بداية الفترة</dt><dd><time>{{ window.start_label }}</time></dd>
                <dt>موعد اكتمال ٣٠ يومًا</dt><dd><time>{{ window.end_label }}</time></dd>
                <dt>بلاغات هذه الفترة</dt><dd>{{ window.ticket_count }} بلاغ</dd>
            </dl>
            {% if window.due %}
                <p class="muted">التقارير المستحقة: {{ window.due_count }}. استخرج أقدم فترة أولًا.</p>
                <form class="export-form" method="post" action="{{ url_for('generate_lab_report', lab_num=report.lab_num) }}" data-filename="lab_{{ report.lab_num }}_{{ window.filename }}">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                    <input type="hidden" name="period_start" value="{{ window.start }}">
                    <div class="report-actions">
                        <button type="submit" class="button button-primary">استخراج تقرير ٣٠ يومًا وتنزيله (Excel)</button>
                        {{ preview_button(url_for('preview_lab_report', lab_num=report.lab_num, period_start=window.start), 'معاينة تقرير ٣٠ يومًا لمعمل ' ~ report.lab_num) }}
                    </div>
                    <div class="message" role="status" aria-live="polite"></div>
                </form>
            {% else %}
                <p class="muted">متبقي {{ window.days_left }} يوم حتى موعد طلب التقرير.</p>
            {% endif %}
            {% else %}
                <p class="muted">لا توجد بلاغات لهذا المعمل. تبدأ أول فترة من وقت تسجيل أول بلاغ.</p>
            {% endif %}
            <div class="report-actions">
                <a href="{{ url_for('export_excel', lab=report.lab_num) }}">تنزيل جميع بلاغات هذا المعمل (Excel)</a>
                {{ preview_button(url_for('preview_lab_report', lab_num=report.lab_num), 'معاينة جميع بلاغات معمل ' ~ report.lab_num) }}
            </div>
            <details>
                <summary>التقارير السابقة ({{ report.archives|length }})</summary>
                <ul class="archive-list">{% for archive in report.archives %}
                    <li class="report-actions">
                        <a href="{{ url_for('download_lab_report_excel', lab_num=report.lab_num, report_id=archive[0]) }}"><time>{{ local_time(archive[1]) }}</time> إلى <time>{{ local_time(archive[2]) }}</time> (Excel)</a>
                        {{ preview_button(url_for('preview_lab_report', lab_num=report.lab_num, report_id=archive[0]), 'معاينة تقرير معمل ' ~ report.lab_num ~ ' للفترة التي تبدأ في ' ~ local_time(archive[1])) }}
                    </li>
                    {% else %}<li class="muted">لم يُستخرج أي تقرير بعد.</li>{% endfor %}
                </ul>
            </details>
        </article>
    {% endfor %}
    </div>
    <footer>قسم الحاسب الآلي وتقنية المعلومات · إشراف: أ. محمد الدوخي · إعداد: ريان المحيطيب</footer>
</main>
<dialog id="report-preview" class="device-dialog report-preview" aria-labelledby="preview-title">
    <div class="panel-header report-preview-heading">
        <div>
            <h2 id="preview-title">معاينة التقرير</h2>
            <p id="preview-period" hidden>الفترة من <bdi dir="ltr"></bdi> إلى <bdi dir="ltr"></bdi> بتوقيت الرياض</p>
            <p id="preview-generated" hidden>وقت استخراج التقرير <bdi dir="ltr"></bdi></p>
        </div>
        <form method="dialog">
            <button class="button icon-button" type="submit" aria-label="إغلاق المعاينة" autofocus>{{ icon('close') }}</button>
        </form>
    </div>
    <div class="report-preview-body">
        <p id="preview-message" role="status"></p>
        <div class="preview-table-wrap" id="preview-table-wrap" tabindex="0" aria-label="جدول البلاغات" hidden>
            <table class="preview-table">
                <thead>
                    <tr>
                        <th scope="col" data-format="ltr">رقم البلاغ</th>
                        <th scope="col">المعمل</th>
                        <th scope="col">موقع الجهاز</th>
                        <th scope="col">المبلّغ</th>
                        <th scope="col">نوع العطل</th>
                        <th scope="col" data-format="issue">وصف العطل</th>
                        <th scope="col" data-format="status">الحالة</th>
                        <th scope="col">القطع المستبدلة</th>
                        <th scope="col" data-format="ltr">وقت البلاغ (الرياض)</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
    </div>
</dialog>
<script>
const reportPreview = document.getElementById('report-preview');
const previewTitle = document.getElementById('preview-title');
const previewMessage = document.getElementById('preview-message');
const previewPeriod = document.getElementById('preview-period');
const previewGenerated = document.getElementById('preview-generated');
const previewTable = document.getElementById('preview-table-wrap');
const previewRows = previewTable.querySelector('tbody');
const previewHeaders = [...previewTable.querySelectorAll('th')];
const statusTones = {{ status_tones|tojson }};
let pendingPreview;

function previewRow(values) {
    const row = document.createElement('tr');
    previewHeaders.forEach((header, index) => {
        const cell = row.insertCell();
        const format = header.dataset.format;
        const value = values[index];
        cell.dataset.label = header.textContent;
        if (format) cell.dataset.format = format;
        const content = document.createElement(format === 'ltr' ? 'bdi' : 'span');
        content.textContent = value ?? '';
        if (!content.textContent) content.textContent = '—';
        if (format === 'ltr') content.dir = 'ltr';
        if (format === 'status') {
            content.className = 'status-pill';
            content.dataset.tone = statusTones[value] || 'neutral';
        }
        cell.appendChild(content);
    });
    return row;
}

document.querySelectorAll('[data-preview-url]').forEach(button => {
    button.addEventListener('click', async () => {
        pendingPreview?.abort();
        const request = new AbortController();
        pendingPreview = request;
        previewTitle.textContent = button.getAttribute('aria-label');
        previewMessage.textContent = 'جارٍ تحميل المعاينة…';
        previewMessage.removeAttribute('data-state');
        previewPeriod.hidden = true;
        previewGenerated.hidden = true;
        previewTable.hidden = true;
        previewRows.replaceChildren();
        reportPreview.showModal();
        try {
            const response = await fetch(button.dataset.previewUrl, {signal: request.signal});
            if (request.signal.aborted) return;
            if (!response.ok || response.redirected) {
                let message = 'تعذّرت معاينة التقرير.';
                if (response.redirected) message = 'سجّل الدخول من جديد ثم أعد المحاولة.';
                else if (response.status === 409) message = 'تغيّرت فترة التقرير. حدّث الصفحة ثم أعد المحاولة.';
                previewMessage.dataset.state = 'error';
                previewMessage.textContent = message;
                return;
            }
            const preview = await response.json();
            if (request.signal.aborted) return;
            previewTitle.textContent = preview.title;
            if (preview.period) {
                previewPeriod.querySelectorAll('bdi').forEach((date, index) => {
                    date.textContent = preview.period[index];
                });
                previewPeriod.hidden = false;
            }
            if (preview.generated_at) {
                previewGenerated.querySelector('bdi').textContent = preview.generated_at;
                previewGenerated.hidden = false;
            }
            const rows = document.createDocumentFragment();
            for (const values of preview.rows) rows.appendChild(previewRow(values));
            previewRows.appendChild(rows);
            previewTable.hidden = !preview.rows.length;
            previewMessage.textContent = preview.rows.length
                ? `${preview.rows.length} بلاغ`
                : 'لا توجد بلاغات في هذا التقرير.';
        } catch (error) {
            if (request.signal.aborted) return;
            previewMessage.dataset.state = 'error';
            previewMessage.textContent = 'تعذّر تحميل المعاينة. أعد المحاولة.';
        }
    });
});
reportPreview.addEventListener('close', () => {
    if (!reportPreview.open) pendingPreview?.abort();
});
reportPreview.addEventListener('click', event => {
    if (event.target === reportPreview) reportPreview.close();
});

document.querySelectorAll('.export-form').forEach(form => {
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const button = form.querySelector('button[type="submit"]');
        const message = form.querySelector('.message');
        if (button.disabled) return;
        button.disabled = true;
        message.textContent = '';
        try {
            const response = await fetch(form.action, {method: 'POST', body: new FormData(form)});
            if (!response.ok || !(response.headers.get('Content-Type') || '').includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) {
                throw new Error('تعذّر استخراج التقرير. حدّث الصفحة وتحقق من تسجيل الدخول ثم أعد المحاولة.');
            }
            const blob = await response.blob();
            const address = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = address;
            link.download = form.dataset.filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            message.textContent = 'تم حفظ التقرير، وبدأ تنزيله. يمكنك إعادة تنزيله من التقارير السابقة.';
            setTimeout(() => { URL.revokeObjectURL(address); location.reload(); }, 1000);
        } catch (error) {
            message.textContent = error.message || 'تعذّر الاتصال. أعد المحاولة.';
            button.disabled = false;
        }
    });
});
</script>
</body></html>
"""


def csv_cell(value):
    text = '' if value is None else str(value)
    # Spreadsheet apps must treat descriptions and names as text, not formulas.
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text


def ticket_csv(tickets, lab_num=None, window=None, generated_at=None):
    output = StringIO()
    writer = csv.writer(output)
    if window:
        writer.writerow(['التقرير', f'تقرير صيانة معمل {lab_num} لمدة 30 يومًا'])
        writer.writerow(['بداية الفترة (شاملة، بتوقيت الرياض)', window['start_label']])
        writer.writerow(['نهاية الفترة (غير شاملة، بتوقيت الرياض)', window['end_label']])
        writer.writerow(['وقت استخراج التقرير (بتوقيت الرياض)', local_time(generated_at)])
        writer.writerow(['إجمالي بلاغات الفترة', len(tickets)])
        for status in TICKET_STATUSES:
            writer.writerow([status, sum(ticket[6] == status for ticket in tickets)])
        writer.writerow([])
    writer.writerow(['رقم التذكرة', 'رقم المعمل', 'موقع الجهاز', 'اسم المُبلّغ', 'تصنيف العطل', 'وصف العطل', 'حالة التذكرة وقت الاستخراج', 'القطع المستبدلة', 'وقت البلاغ (بتوقيت الرياض)'])
    writer.writerows(ticket_report_rows(tickets, escape_csv=True))
    return output.getvalue().encode('utf-8-sig')


def csv_response(data, filename):
    return Response(data, mimetype='text/csv', headers={
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Cache-Control': 'no-store'
    })


EXCEL_MIMETYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
_EXCEL_TEMPLATE_B64 = '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'
_EXCEL_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
_XML_INVALID = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]')


def _xlsx_tag(name):
    return f'{{{_EXCEL_NS}}}{name}'


def _xlsx_value(cell, value):
    for child in list(cell):
        cell.remove(child)
    cell.attrib.pop('t', None)
    if value is None:
        return
    if isinstance(value, (int, float)):
        ET.SubElement(cell, _xlsx_tag('v')).text = str(value)
    else:
        # Explicit text cells keep identifiers intact and never run user input as formulas.
        cell.set('t', 'inlineStr')
        text = ET.SubElement(ET.SubElement(cell, _xlsx_tag('is')), _xlsx_tag('t'))
        text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        text.text = _XML_INVALID.sub('', str(value))[:32767]


def _xlsx_formula(cell, formula, cached_value):
    _xlsx_value(cell, None)
    ET.SubElement(cell, _xlsx_tag('f')).text = formula
    ET.SubElement(cell, _xlsx_tag('v')).text = str(cached_value)


def excel_report(rows, lab_num=None, period=None, generated_at=None):
    """Bind report data to the embedded, styled workbook without extra dependencies."""
    with ZipFile(BytesIO(base64.b64decode(_EXCEL_TEMPLATE_B64))) as template:
        parts = {name: template.read(name) for name in template.namelist()}
    sheet = ET.fromstring(parts['xl/worksheets/sheet1.xml'])
    sheet_data = sheet.find(_xlsx_tag('sheetData'))
    cells = {cell.get('r'): cell for row in sheet_data for cell in row}
    body = deepcopy(sheet_data.find(f"{_xlsx_tag('row')}[@r='11']"))
    empty_note = deepcopy(sheet_data.find(f"{_xlsx_tag('row')}[@r='13']"))
    title = 'تقرير صيانة حواسيب المعامل' if lab_num is None else f'تقرير صيانة معمل {lab_num}'
    _xlsx_value(cells['A3'], title + (' لمدة ٣٠ يومًا' if period else ''))
    _xlsx_value(cells['A5'], f'تاريخ استخراج التقرير: {local_time(generated_at or db_time(utc_now()))} (بتوقيت الرياض)')
    _xlsx_value(cells['A6'], f'الفترة: من {local_time(period[0])} (شاملة) إلى {local_time(period[1])} (غير شاملة)، بتوقيت الرياض.' if period else None)
    sheet_data.find(f"{_xlsx_tag('row')}[@r='6']").set('ht', '30' if period else '14')
    if period:
        _xlsx_value(cells['G10'], 'حالة التذكرة وقت الاستخراج')

    for row in list(sheet_data):
        if int(row.get('r')) >= 11:
            sheet_data.remove(row)
    last_row = 10 + max(1, len(rows))
    for number, values in enumerate(rows or [[None] * 9], start=11):
        row = deepcopy(body)
        row.set('r', str(number))
        lines = 1
        for column, (cell, value) in enumerate(zip(row, values)):
            cell.set('r', f'{chr(65 + column)}{number}')
            if column == 8 and value:
                try:
                    stamp = datetime.strptime(str(value), '%Y-%m-%d %H:%M')
                    value = (stamp - datetime(1899, 12, 30)).total_seconds() / 86400
                except ValueError:
                    pass
            if column in (3, 5, 7) and value:
                width = {3: 24, 5: 42, 7: 28}[column]
                lines = max(lines, sum(max(1, ceil(len(line) / width)) for line in str(value).split('\n')))
            _xlsx_value(cell, value)
        row.set('ht', str(min(409, max(38, lines * 18 + 10))))
        sheet_data.append(row)

    merges = sheet.find(_xlsx_tag('mergeCells'))
    for merged in list(merges):
        if merged.get('ref') == 'A13:I13':
            merges.remove(merged)
    if not rows:
        _xlsx_value(empty_note[0], 'لا توجد بلاغات مسجلة خلال هذه الفترة.' if period else 'لا توجد بلاغات صيانة مسجلة حتى الآن.')
        sheet_data.append(empty_note)
        ET.SubElement(merges, _xlsx_tag('mergeCell'), {'ref': 'A13:I13'})
    merges.set('count', str(len(merges)))
    _xlsx_formula(cells['A8'], f'COUNTA(A11:A{last_row})', len(rows))
    for address, status in zip(('D8', 'F8', 'H8'), TICKET_STATUSES):
        _xlsx_formula(cells[address], f'COUNTIFS(G11:G{last_row},"{status}")', sum(row[6] == status for row in rows))
    for conditional in sheet.findall(_xlsx_tag('conditionalFormatting')):
        conditional.set('sqref', f'G11:G{last_row}')
    table = ET.fromstring(parts['xl/tables/table1.xml'])
    table.set('ref', f'A10:I{last_row}')
    table.find(_xlsx_tag('autoFilter')).set('ref', f'A10:I{last_row}')

    # Preserve Arabic sheet direction and print settings when populating the template.
    sheet.find(f"{_xlsx_tag('sheetViews')}/{_xlsx_tag('sheetView')}").set('rightToLeft', '1')
    dimension = ET.Element(_xlsx_tag('dimension'), {'ref': f'A1:I{last_row if rows else 13}'})
    sheet.insert(1, dimension)
    ET.SubElement(sheet.find(_xlsx_tag('sheetPr')), _xlsx_tag('pageSetUpPr'), {'fitToPage': '1'})
    margins = sheet.find(_xlsx_tag('pageMargins'))
    margins.attrib.update(left='0.25', right='0.25', top='0.4', bottom='0.4', header='0.2', footer='0.2')
    setup = ET.Element(_xlsx_tag('pageSetup'), {'paperSize': '9', 'orientation': 'landscape', 'fitToWidth': '1', 'fitToHeight': '0'})
    sheet.insert(list(sheet).index(margins) + 1, setup)
    styles = ET.fromstring(parts['xl/styles.xml'])
    formats = styles.find(_xlsx_tag('cellXfs'))
    for style in formats:
        alignment = style.find(_xlsx_tag('alignment'))
        if alignment is not None:
            alignment.set('readingOrder', '2')
    for cell in (body[0], body[8]):
        alignment = formats[int(cell.get('s'))].find(_xlsx_tag('alignment'))
        if alignment is not None:
            alignment.set('readingOrder', '1')
    workbook = ET.fromstring(parts['xl/workbook.xml'])
    names = ET.SubElement(workbook, _xlsx_tag('definedNames'))
    ET.SubElement(names, _xlsx_tag('definedName'), {'name': '_xlnm.Print_Area', 'localSheetId': '0'}).text = f"'تقرير الصيانة'!$A$1:$I${last_row if rows else 13}"
    ET.SubElement(names, _xlsx_tag('definedName'), {'name': '_xlnm.Print_Titles', 'localSheetId': '0'}).text = "'تقرير الصيانة'!$10:$10"
    ET.SubElement(workbook, _xlsx_tag('calcPr'), {'calcMode': 'auto', 'fullCalcOnLoad': '1', 'forceFullCalc': '1'})
    for path, root in (('xl/worksheets/sheet1.xml', sheet), ('xl/tables/table1.xml', table), ('xl/styles.xml', styles), ('xl/workbook.xml', workbook)):
        parts[path] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as document:
        for name, content in parts.items():
            document.writestr(name, content)
    return output.getvalue()


def ticket_report_rows(tickets, escape_csv=False):
    text_field = csv_cell if escape_csv else lambda value: value
    return [[f'{ticket[1]}-{ticket[0]}', f'معمل {ticket[1]}',
             'منصة المدرب' if ticket[2] == 0 else f'جهاز {ticket[2]}',
             *[text_field(value) for value in ticket[3:8]], local_time(ticket[8])] for ticket in tickets]


def ticket_excel(tickets, lab_num=None):
    return excel_report(ticket_report_rows(tickets), lab_num)


def archived_report_rows(data):
    # Format the immutable snapshot, rather than rereading tickets that may have changed.
    source = list(csv.reader(StringIO(bytes(data).decode('utf-8-sig'))))
    header = next(index for index, row in enumerate(source) if row and row[0] == 'رقم التذكرة')
    rows = [row for row in source[header + 1:] if row]
    if any(len(row) != 9 for row in rows):
        raise ValueError('Invalid archived report columns')
    return rows


def archived_ticket_excel(data, lab_num, start_at, end_at, generated_at):
    return excel_report(archived_report_rows(data), lab_num, (start_at, end_at), generated_at)


def excel_response(data, filename):
    return Response(data, mimetype=EXCEL_MIMETYPE, headers={
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Cache-Control': 'no-store'
    })


def qr_base_url(raw_url):
    base = raw_url.strip().rstrip('/')
    try:
        parsed = urlsplit(base)
        valid_port = parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        return None
    if (len(base) > 200 or parsed.scheme not in ('http', 'https') or
            not parsed.hostname or not valid_port or parsed.username or
            parsed.password or parsed.path or parsed.query or parsed.fragment):
        return None
    return base

# --- المسارات والروابط (Routes) ---

@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        user = request.form.get('username')
        pwd = request.form.get('password')
        if user in USERS and USERS[user]['password'] == pwd:
            session['user'] = user
            session['name'] = USERS[user]['name']
            session['role'] = USERS[user]['role']
            return redirect(url_for('dashboard'))
        else:
            error = "اسم المستخدم أو كلمة المرور غير صحيحة"
    return render_template_string(LOGIN_TEMPLATE, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/qr-labels')
def qr_labels():
    if 'user' not in session:
        return redirect(url_for('login'))
    selected_lab = request.args.get('lab', type=int)
    if 'lab' in request.args and selected_lab not in LAB_NUMBERS:
        abort(400)
    requested_base = request.args.get('base', request.url_root.rstrip('/'))
    base_url = qr_base_url(requested_base)
    return render_template_string(
        QR_LABELS_TEMPLATE,
        base_url=requested_base,
        labs=(selected_lab,) if selected_lab is not None else LAB_NUMBERS,
        selected_lab=selected_lab,
        error=None if base_url else 'أدخل رابطًا يبدأ بـ http:// أو https:// ويتضمن عنوان الجهاز والمنفذ فقط.'
    )

@app.route('/qr/lab/<int:lab_num>.png')
def lab_qr(lab_num):
    if lab_num not in LAB_NUMBERS:
        abort(404)
    base_url = qr_base_url(request.args.get('base', request.url_root.rstrip('/')))
    if base_url is None:
        abort(400)
    target = base_url + url_for('lab_report', lab_num=lab_num)
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=4)
    qr.add_data(target)
    qr.make(fit=True)
    output = BytesIO()
    qr.make_image(fill_color='black', back_color='white').save(output, format='PNG')
    output.seek(0)
    return send_file(output, mimetype='image/png', max_age=0)

@app.route('/lab/<int:lab_num>/report', methods=['GET', 'POST'])
def lab_report(lab_num):
    if lab_num not in LAB_NUMBERS:
        abort(404)

    with lab_connection(lab_num) as conn:
        occupied_seats = [row[0] for row in conn.execute("SELECT seat_num FROM tickets WHERE status != 'تم الحل'")]

    error = None
    values = request.form.to_dict(flat=True) if request.method == 'POST' else {}
    if request.method == 'GET':
        selected_seat = request.args.get('seat', type=int)
        if (selected_seat == 0 or selected_seat in TRAINING_SEATS) and selected_seat not in occupied_seats:
            values['seat_num'] = str(selected_seat)
    if request.method == 'POST':
        seat_raw = values.get('seat_num', '')
        seat = request.form.get('seat_num', type=int) if seat_raw.isdecimal() else None
        valid_seat = seat == 0 or seat in TRAINING_SEATS
        values['seat_num'] = str(seat) if valid_seat else ''
        reporter = values.get('reporter_name', '').strip()
        category = values.get('issue_category', '')
        issue = values.get('issue', '').strip()

        if not valid_seat:
            error = 'اختر جهازًا صحيحًا أو منصة المدرب.'
        elif seat in occupied_seats:
            error = 'عذراً! هذا الجهاز مسجل عليه بلاغ نشط بالفعل وهو قيد متابعة فريق الصيانة حالياً.'
        elif not 1 <= len(reporter) <= 80:
            error = 'اكتب اسم المبلّغ (حتى 80 حرفًا).'
        elif category not in ISSUE_CATEGORIES:
            error = 'اختر نوع العطل من القائمة.'
        elif not 5 <= len(issue) <= 1000:
            error = 'اكتب وصفًا للعطل من 5 إلى 1000 حرف.'
        else:
            with lab_connection(lab_num) as conn:
                conn.execute('BEGIN IMMEDIATE')
                # Check again under the write lock if two reports arrive together.
                duplicate = conn.execute("SELECT 1 FROM tickets WHERE seat_num = ? AND status != 'تم الحل'", (seat,)).fetchone()
                if duplicate:
                    occupied_seats.append(seat)
                    error = 'هذا الجهاز مسجل عليه بلاغ نشط بالفعل.'
                else:
                    ticket_id = conn.insert_id(
                        'INSERT INTO tickets (lab_num, seat_num, reporter_name, issue_category, issue, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                        (lab_num, seat, reporter, category, issue, db_time(utc_now()))
                    )
                    ensure_report_anchor(conn)
                    return redirect(url_for('lab_report', lab_num=lab_num, success=ticket_id))

    success = request.args.get('success', type=int)
    return render_template(
        'report.html', lab_num=lab_num, seats=TRAINING_SEATS,
        occupied_seats=occupied_seats,
        categories=ISSUE_CATEGORIES, values=values, error=error,
        success=success if success and success > 0 else None,
    )

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    initial_lab = request.args.get('lab', type=int)
    if initial_lab not in LAB_NUMBERS:
        initial_lab = LAB_NUMBERS[0]
    tickets = all_tickets()
    due_reports = [report for report in report_summaries() if report['window'] and report['window']['due']]

    total = len(tickets)
    active = sum(1 for t in tickets if t[6] == 'مفتوح')
    pending = sum(1 for t in tickets if t[6] == 'قيد الإصلاح')
    op_rate = 100.0 if total == 0 else round(((total - active) / total) * 100, 1)

    lab_statuses = dict.fromkeys(LAB_NUMBERS, 'ok')
    all_parts = []
    device_states = {lab: {} for lab in LAB_NUMBERS}
    dashboard_tickets = []
    for t in tickets:
        ticket_id, lab, seat, reporter, category, issue, status, parts, created = t
        is_active = status != 'تم الحل'
        tone = STATUS_TONES.get(status, 'danger')
        if tone == 'danger' or (tone == 'warning' and lab_statuses[lab] == 'ok'):
            lab_statuses[lab] = tone
        if is_active and (seat == 0 or seat in TRAINING_SEATS):
            device_states[lab].setdefault(seat, tone)
        dashboard_tickets.append({
            'id': ticket_id, 'lab': lab, 'seat': seat, 'reporter': reporter,
            'category': category, 'issue': issue, 'status': status, 'parts': parts,
            'created': created,
            'updateUrl': url_for('update_status', lab_num=lab, ticket_id=ticket_id) if is_active else None,
        })
        part_text = parts.strip() if parts else ''
        if part_text and part_text != 'لا يوجد':
            for p in part_text.replace('،', ',').split(','):
                cleaned = p.strip()
                if cleaned:
                    all_parts.append(cleaned)
    parts_stats = dict(Counter(all_parts).most_common(5))
    lab_labels = {'ok': 'سليم', 'warning': 'قيد الإصلاح', 'danger': 'عطل نشط'}
    device_labels = {**lab_labels, 'ok': 'جاهز'}
    lab_links = {
        lab: {'qr': url_for('qr_labels', lab=lab), 'report': url_for('lab_report', lab_num=lab)}
        for lab in LAB_NUMBERS
    }
    initial_device_states = device_states[initial_lab]

    return render_template(
        'dashboard.html',
        tickets=tickets,
        total_tickets=total,
        active_tickets=active,
        pending_tickets=pending,
        operational_rate=op_rate,
        lab_statuses=lab_statuses,
        parts_stats=parts_stats,
        due_reports=due_reports,
        statuses=TICKET_STATUSES,
        status_tones=STATUS_TONES,
        lab_numbers=LAB_NUMBERS,
        lab_labels=lab_labels,
        device_labels=device_labels,
        seats=TRAINING_SEATS,
        initial_lab=initial_lab,
        initial_device_states=initial_device_states,
        initial_ready=sum(seat not in initial_device_states for seat in TRAINING_SEATS),
        lab_links=lab_links,
        dashboard_data={
            'initialLab': initial_lab,
            'labLinks': lab_links,
            'labStates': lab_statuses,
            'labLabels': lab_labels,
            'deviceStates': device_states,
            'deviceLabels': device_labels,
            'statusTones': STATUS_TONES,
            'tickets': dashboard_tickets,
        },
    )

@app.route('/update_status/<int:lab_num>/<int:ticket_id>', methods=['POST'])
def update_status(lab_num, ticket_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    if lab_num not in LAB_NUMBERS:
        abort(404)
    new_status = request.form.get('status')
    if new_status not in TICKET_STATUSES:
        abort(400)
    replaced_parts = request.form.get('replaced_parts', '').strip() or 'لا يوجد'
    with lab_connection(lab_num) as conn:
        conn.execute('BEGIN IMMEDIATE')
        ticket = conn.execute('SELECT seat_num FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
        if ticket is None:
            abort(404)
        if new_status != 'تم الحل' and conn.execute("SELECT 1 FROM tickets WHERE seat_num = ? AND id != ? AND status != 'تم الحل'", (ticket[0], ticket_id)).fetchone():
            abort(409, description='يوجد بلاغ نشط آخر على الجهاز.')
        conn.execute('UPDATE tickets SET status = ?, replaced_parts = ? WHERE id = ?', (new_status, replaced_parts, ticket_id))
    selected_lab = request.form.get('dashboard_lab', type=int)
    if selected_lab in LAB_NUMBERS:
        return redirect(url_for('dashboard', lab=selected_lab, _anchor='labs'))
    return redirect(url_for('dashboard'))

@app.route('/export_csv')
def export_csv():
    if 'user' not in session:
        return redirect(url_for('login'))
    lab_raw = request.args.get('lab')
    if lab_raw is not None and (not lab_raw.isascii() or not lab_raw.isdigit() or int(lab_raw) not in LAB_NUMBERS):
        abort(400)
    lab_num = int(lab_raw) if lab_raw is not None else None
    filename = f'lab_{lab_num}_all_tickets.csv' if lab_num is not None else 'smart_lab_maintenance_report.csv'
    return csv_response(ticket_csv(all_tickets(lab_num)), filename)


@app.route('/export_excel')
def export_excel():
    if 'user' not in session:
        return redirect(url_for('login'))
    lab_raw = request.args.get('lab')
    if lab_raw is not None and (not lab_raw.isascii() or not lab_raw.isdigit() or int(lab_raw) not in LAB_NUMBERS):
        abort(400)
    lab_num = int(lab_raw) if lab_raw is not None else None
    filename = f'lab_{lab_num}_all_tickets.xlsx' if lab_num is not None else 'smart_lab_maintenance_report.xlsx'
    return excel_response(ticket_excel(all_tickets(lab_num), lab_num), filename)


@app.route('/reports')
def reports():
    if 'user' not in session:
        return redirect(url_for('login'))
    if 'report_csrf' not in session:
        session['report_csrf'] = secrets.token_urlsafe(32)
    return render_template_string(REPORTS_TEMPLATE, reports=report_summaries(),
                                  csrf_token=session['report_csrf'], local_time=local_time,
                                  status_tones=STATUS_TONES)


def period_tickets(conn, start_at, end_at):
    return conn.execute(
        f'SELECT {TICKET_COLUMNS} FROM tickets WHERE created_at >= ? AND created_at < ? ORDER BY created_at, id',
        (start_at, end_at),
    ).fetchall()


@app.route('/reports/lab/<int:lab_num>/preview')
def preview_lab_report(lab_num):
    if 'user' not in session:
        return redirect(url_for('login'))
    if lab_num not in LAB_NUMBERS:
        abort(404)
    report_id = request.args.get('report_id', type=int)
    period_start = request.args.get('period_start')
    if 'report_id' in request.args:
        if report_id is None or not 0 < report_id < 2**63 or period_start is not None:
            abort(400)

    preview = {'title': f'جميع بلاغات معمل {lab_num}', 'period': None, 'generated_at': None}
    if report_id is None and period_start is None:
        preview['rows'] = ticket_report_rows(all_tickets(lab_num))
    else:
        with lab_connection(lab_num) as conn:
            if report_id is not None:
                saved = conn.execute(
                    'SELECT start_at, end_at, csv_data, generated_at FROM report_exports WHERE id = ?',
                    (report_id,),
                ).fetchone()
                if saved is None:
                    abort(404)
            else:
                saved = conn.execute(
                    'SELECT start_at, end_at, csv_data, generated_at FROM report_exports WHERE start_at = ?',
                    (period_start,),
                ).fetchone()

            if saved is not None:
                start_at, end_at, data, generated_at = saved
                preview['rows'] = archived_report_rows(data)
                preview['generated_at'] = local_time(generated_at)
            else:
                window = report_window(conn)
                if not window or not window['due'] or period_start != window['start']:
                    abort(409, description='الفترة لم تكتمل أو تغيّرت حالة التقرير.')
                start_at, end_at = window['start'], window['end']
                preview['rows'] = ticket_report_rows(period_tickets(conn, start_at, end_at), escape_csv=True)
        preview['title'] = f'تقرير ٣٠ يومًا لمعمل {lab_num}'
        preview['period'] = [local_time(start_at), local_time(end_at)]
    response = jsonify(preview)
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/reports/lab/<int:lab_num>/export', methods=['POST'])
def generate_lab_report(lab_num):
    if 'user' not in session:
        return redirect(url_for('login'))
    if lab_num not in LAB_NUMBERS:
        abort(404)
    token = session.get('report_csrf', '')
    supplied = request.form.get('csrf_token', '')
    if not token or not secrets.compare_digest(token.encode(), supplied.encode()):
        abort(400)
    period_start = request.form.get('period_start', '')
    with lab_connection(lab_num) as conn:
        conn.execute('BEGIN IMMEDIATE')
        # A retried download returns the same snapshot instead of consuming a later period.
        saved = conn.execute('SELECT start_at, end_at, csv_data, generated_at FROM report_exports WHERE start_at = ?', (period_start,)).fetchone()
        if saved:
            start_at, end_at, data, generated_at = saved
        else:
            now = utc_now()
            window = report_window(conn, now)
            if not window or not window['due'] or period_start != window['start']:
                abort(409, description='الفترة لم تكتمل أو تغيّرت حالة التقرير. حدّث صفحة التقارير.')
            start_at, end_at = window['start'], window['end']
            tickets = period_tickets(conn, start_at, end_at)
            generated_at = db_time(now)
            data = ticket_csv(tickets, lab_num, window, generated_at)
            conn.execute('INSERT INTO report_exports (start_at, end_at, generated_at, generated_by, csv_data) VALUES (?, ?, ?, ?, ?)',
                         (start_at, end_at, db_time(now), session['user'], data))
    filename = f'lab_{lab_num}_{parse_time(start_at):%Y%m%d}_{parse_time(end_at):%Y%m%d}.xlsx'
    return excel_response(archived_ticket_excel(data, lab_num, start_at, end_at, generated_at), filename)


@app.route('/reports/lab/<int:lab_num>/archive/<int:report_id>.xlsx')
def download_lab_report_excel(lab_num, report_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    if lab_num not in LAB_NUMBERS:
        abort(404)
    with lab_connection(lab_num) as conn:
        saved = conn.execute('SELECT start_at, end_at, csv_data, generated_at FROM report_exports WHERE id = ?', (report_id,)).fetchone()
    if saved is None:
        abort(404)
    start_at, end_at, data, generated_at = saved
    filename = f'lab_{lab_num}_{parse_time(start_at):%Y%m%d}_{parse_time(end_at):%Y%m%d}.xlsx'
    return excel_response(archived_ticket_excel(data, lab_num, start_at, end_at, generated_at), filename)


@app.route('/reports/lab/<int:lab_num>/archive/<int:report_id>.csv')
def download_lab_report(lab_num, report_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    if lab_num not in LAB_NUMBERS:
        abort(404)
    with lab_connection(lab_num) as conn:
        saved = conn.execute('SELECT start_at, end_at, csv_data FROM report_exports WHERE id = ?', (report_id,)).fetchone()
    if saved is None:
        abort(404)
    filename = f'lab_{lab_num}_{parse_time(saved[0]):%Y%m%d}_{parse_time(saved[1]):%Y%m%d}.csv'
    return csv_response(saved[2], filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')), debug=False)
