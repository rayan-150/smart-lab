import os
import sqlite3
import csv
from io import BytesIO, StringIO
from urllib.parse import urlsplit
from collections import Counter
from datetime import datetime

import qrcode
from flask import Flask, abort, render_template_string, request, redirect, send_file, url_for, session, Response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = "smart_lab_secret_key_2026_super_safe"

def init_db():
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'maintenance.db'))
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_num INTEGER,
            seat_num INTEGER,
            reporter_name TEXT,
            issue_category TEXT,
            issue TEXT,
            status TEXT DEFAULT 'مفتوح',
            replaced_parts TEXT DEFAULT 'لا يوجد',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

USERS = {
    "admin": {"password": "123", "role": "مشرف الصيانة التقنية", "name": "محمد الدوخي"},
    "tech": {"password": "123", "role": "فني دعم المعامل", "name": "الدعم الفني"},
    "trainer": {"password": "123", "role": "مدرب قسم الحاسب", "name": "مدرب حاسب"}
}

LAB_NUMBERS = (1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 22, 23, 24, 26, 27)
ISSUE_CATEGORIES = ('أجهزة', 'برامج', 'شبكة', 'أخرى')

# --- صفحة تسجيل الدخول بالهوية المتقدمة ---
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تسجيل الدخول | نظام صيانة حواسيب المعامل</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800;900&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Tajawal', sans-serif;
            background-color: #040711;
            background-image: 
                radial-gradient(circle at 50% 30%, rgba(6, 182, 212, 0.16) 0%, transparent 65%),
                radial-gradient(rgba(14, 165, 233, 0.08) 1px, transparent 1px),
                linear-gradient(rgba(14, 165, 233, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(14, 165, 233, 0.03) 1px, transparent 1px);
            background-size: 100% 100%, 24px 24px, 12px 12px, 12px 12px;
        }
        .glass-card {
            background: rgba(13, 21, 41, 0.7);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(34, 211, 238, 0.28);
            box-shadow: 0 0 50px rgba(6, 182, 212, 0.12), inset 0 0 20px rgba(34, 211, 238, 0.03);
            transition: all 0.3s ease;
        }
        .glass-card:hover { border-color: rgba(34, 211, 238, 0.45); }
    </style>
</head>
<body class="min-h-screen text-slate-200 flex flex-col justify-between items-center p-4">
    <div></div>

    <div class="max-w-md w-full glass-card rounded-3xl p-7 md:p-8 relative">
        <div class="text-center mb-6">
            <div class="w-14 h-14 bg-gradient-to-tr from-cyan-600/30 to-blue-500/20 border border-cyan-400/50 rounded-2xl flex items-center justify-center mx-auto text-cyan-400 text-2xl mb-3 shadow-[0_0_25px_rgba(6,182,212,0.3)]">
                <i class="fa-solid fa-microchip"></i>
            </div>
            <h2 class="text-xl font-black text-white tracking-wide">نظام إدارة صيانة المعامل</h2>
            <p class="text-xs text-cyan-400 font-semibold mt-1">قسم الحاسب الآلي وتقنية المعلومات</p>
        </div>

        {% if error %}
        <div class="bg-red-950/60 border border-red-800/80 text-red-300 text-xs p-3 rounded-xl mb-4 text-center flex items-center justify-center gap-2">
            <i class="fa-solid fa-circle-exclamation text-red-400"></i>
            <span>{{ error }}</span>
        </div>
        {% endif %}

        <form id="login-form" method="POST" action="/login" class="space-y-4" onsubmit="handleLoginSubmit()">
            <div>
                <label class="block text-xs font-semibold text-slate-300 mb-1.5">اسم المستخدم</label>
                <div class="relative">
                    <span class="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-slate-500">
                        <i class="fa-solid fa-user text-xs"></i>
                    </span>
                    <input type="text" id="username-input" name="username" required placeholder="admin" class="w-full bg-slate-950/90 border border-slate-700/80 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/40 rounded-xl py-2.5 pr-9 pl-3 text-xs text-white focus:outline-none transition">
                </div>
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-300 mb-1.5">كلمة المرور</label>
                <div class="relative">
                    <span class="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-slate-500">
                        <i class="fa-solid fa-lock text-xs"></i>
                    </span>
                    <input type="password" id="password-input" name="password" required placeholder="••••••" class="w-full bg-slate-950/90 border border-slate-700/80 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/40 rounded-xl py-2.5 pr-9 pl-10 text-xs text-white focus:outline-none transition">
                    <button type="button" onclick="togglePasswordVisibility()" class="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400 hover:text-cyan-300 transition">
                        <i id="eye-icon" class="fa-solid fa-eye text-xs"></i>
                    </button>
                </div>
            </div>

            <button type="submit" id="submit-btn" class="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold rounded-xl text-xs shadow-lg shadow-cyan-500/25 transition duration-200 flex items-center justify-center gap-2">
                <span id="btn-text">تسجيل الدخول</span>
                <i id="btn-spinner" class="fa-solid fa-circle-notch fa-spin hidden"></i>
            </button>
        </form>

        <div class="mt-6 pt-4 border-t border-slate-800/80">
            <p class="text-[11px] text-slate-400 text-center mb-2.5 flex items-center justify-center gap-1.5">
                <i class="fa-solid fa-bolt text-amber-400 text-xs"></i> تجربة سريعة وتعبئة بنقرة واحدة:
            </p>
            <div class="grid grid-cols-3 gap-2">
                <button type="button" onclick="fastFill('admin', '123')" class="bg-cyan-950/40 hover:bg-cyan-900/50 border border-cyan-800/50 hover:border-cyan-400/60 text-cyan-300 text-[10px] py-1.5 px-1 rounded-lg text-center transition font-semibold">
                    مشرف الصيانة
                </button>
                <button type="button" onclick="fastFill('tech', '123')" class="bg-slate-950/50 hover:bg-slate-800/60 border border-slate-700/60 hover:border-slate-500 text-slate-300 text-[10px] py-1.5 px-1 rounded-lg text-center transition font-semibold">
                    الدعم الفني
                </button>
                <button type="button" onclick="fastFill('trainer', '123')" class="bg-slate-950/50 hover:bg-slate-800/60 border border-slate-700/60 hover:border-slate-500 text-slate-300 text-[10px] py-1.5 px-1 rounded-lg text-center transition font-semibold">
                    مدرب القسم
                </button>
            </div>
        </div>
    </div>

    <footer class="my-4 text-center">
        <div class="bg-slate-900/60 border border-slate-800/80 backdrop-blur-md px-5 py-2 rounded-full text-xs text-slate-400 inline-flex flex-wrap items-center justify-center gap-2 shadow-lg">
            <span class="font-bold text-slate-200">قسم الحاسب الآلي وتقنية المعلومات</span>
            <span class="text-cyan-500/60">•</span>
            <span>إشراف: <span class="text-slate-300 font-semibold">أ. محمد الدوخي</span></span>
            <span class="text-cyan-500/60">•</span>
            <span>إعداد: <span class="text-cyan-400 font-semibold">ريان المحيطيب</span></span>
        </div>
    </footer>

    <script>
        function fastFill(user, pass) {
            document.getElementById('username-input').value = user;
            document.getElementById('password-input').value = pass;
        }

        function togglePasswordVisibility() {
            const passInput = document.getElementById('password-input');
            const eyeIcon = document.getElementById('eye-icon');
            if (passInput.type === 'password') {
                passInput.type = 'text';
                eyeIcon.classList.remove('fa-eye');
                eyeIcon.classList.add('fa-eye-slash');
            } else {
                passInput.type = 'password';
                eyeIcon.classList.remove('fa-eye-slash');
                eyeIcon.classList.add('fa-eye');
            }
        }

        function handleLoginSubmit() {
            const btn = document.getElementById('submit-btn');
            const btnText = document.getElementById('btn-text');
            const spinner = document.getElementById('btn-spinner');
            btnText.innerText = "جاري التحقق والدخول...";
            spinner.classList.remove('hidden');
            btn.classList.add('opacity-80', 'cursor-not-allowed');
        }
    </script>
</body>
</html>
"""

# --- صفحة لوحة العمليات ومخطط الرادار التفاعلي مع تقارير المعامل المنفصلة ---
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>غرفة المراقبة والعمليات (NOC) | صيانة المعامل</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Tajawal', sans-serif; background-color: #050811; color: #f1f5f9; }
        .blueprint-container {
            background-color: #070d1e;
            background-image: 
                radial-gradient(rgba(14, 165, 233, 0.12) 1px, transparent 1px),
                linear-gradient(rgba(14, 165, 233, 0.04) 1px, transparent 1px),
                linear-gradient(90deg, rgba(14, 165, 233, 0.04) 1px, transparent 1px);
            background-size: 20px 20px, 10px 10px, 10px 10px;
        }
        .svg-room {
            fill: #0c162d;
            stroke: #1e3a6a;
            stroke-width: 1.5;
            transition: all 0.25s ease;
        }
        .svg-lab {
            fill: #082847;
            stroke: #0284c7;
            stroke-width: 1.8;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .svg-lab:hover {
            fill: #0369a1;
            stroke: #38bdf8;
            filter: drop-shadow(0 0 8px rgba(56, 189, 248, 0.5));
        }
        .svg-lab.active-lab {
            fill: #0284c7 !important;
            stroke: #38bdf8 !important;
            stroke-width: 2.5 !important;
            filter: drop-shadow(0 0 12px rgba(56, 189, 248, 0.8));
        }
        .svg-lab.status-danger {
            fill: rgba(185, 28, 28, 0.7) !important;
            stroke: #ef4444 !important;
            stroke-width: 2.5 !important;
            animation: lab-pulse-red 1.8s infinite;
        }
        .svg-lab.status-warning {
            fill: rgba(180, 83, 9, 0.7) !important;
            stroke: #f59e0b !important;
            stroke-width: 2.5 !important;
            animation: lab-pulse-yellow 2s infinite;
        }
        @keyframes lab-pulse-red {
            0%, 100% { filter: drop-shadow(0 0 4px rgba(239, 68, 68, 0.5)); }
            50% { filter: drop-shadow(0 0 14px rgba(239, 68, 68, 0.9)); stroke-width: 3.5; }
        }
        @keyframes lab-pulse-yellow {
            0%, 100% { filter: drop-shadow(0 0 4px rgba(245, 158, 11, 0.5)); }
            50% { filter: drop-shadow(0 0 12px rgba(245, 158, 11, 0.9)); stroke-width: 3.5; }
        }
        .svg-text-title {
            fill: #e0f2fe;
            font-size: 11px;
            font-weight: 700;
            text-anchor: middle;
            pointer-events: none;
            font-family: 'Tajawal', sans-serif;
        }
        .svg-text-sub {
            fill: #38bdf8;
            font-size: 9px;
            font-weight: 500;
            text-anchor: middle;
            pointer-events: none;
            font-family: 'Tajawal', sans-serif;
        }
        .svg-facility-text {
            fill: #94a3b8;
            font-size: 10px;
            text-anchor: middle;
            pointer-events: none;
            font-family: 'Tajawal', sans-serif;
        }
        body.noc-active {
            padding: 12px !important;
            background-color: #020409 !important;
        }
        body.noc-active header {
            padding: 10px 16px !important;
            margin-bottom: 12px !important;
        }
    </style>
</head>
<body id="main-body" class="min-h-screen flex flex-col p-4 md:p-6 space-y-5">

    <header class="flex flex-wrap justify-between items-center px-6 py-4 bg-slate-900/80 border border-slate-800 rounded-2xl backdrop-blur gap-3">
        <div class="flex items-center gap-2.5">
            <a href="/logout" class="bg-red-950/40 hover:bg-red-900/60 border border-red-800/60 text-red-400 px-3 py-1.5 rounded-xl text-xs flex items-center gap-1.5 transition">
                <i class="fa-solid fa-power-off"></i> خروج
            </a>
            <div class="flex items-center gap-2 bg-slate-800/60 border border-slate-700/60 px-3 py-1.5 rounded-xl text-xs">
                <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span class="font-bold text-slate-200">{{ session.get('name', 'محمد الدوخي') }}</span>
                <span class="text-cyan-400 text-[10px]">({{ session.get('role', 'مشرف الصيانة التقنية') }})</span>
            </div>
            <button onclick="toggleNocMode()" id="noc-toggle-btn" class="bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/40 text-cyan-300 text-xs px-3 py-1.5 rounded-xl flex items-center gap-2 transition font-bold shadow-sm">
                <i class="fa-solid fa-tv"></i> <span id="noc-btn-label">شاشة المراقبة (NOC)</span>
            </button>
            <div id="noc-status-badge" class="hidden items-center gap-2 bg-emerald-950/50 border border-emerald-500/40 text-emerald-300 px-3 py-1.5 rounded-xl text-xs font-semibold">
                <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                <span>بث حي مباشر (تحديث بعد: <span id="countdown-timer">30</span>ث)</span>
            </div>
        </div>

        <div class="flex items-center gap-3">
            <a href="{{ url_for('export_csv') }}" class="bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/40 text-emerald-300 text-xs px-3 py-1.5 rounded-xl flex items-center gap-2 transition font-bold">
                <i class="fa-solid fa-file-excel"></i> تصدير التقرير العام لكل المعامل
            </a>
            <div class="text-left">
                <h1 class="font-black text-base text-white">النظام الذكي لإدارة ومتابعة صيانة حواسيب المعامل</h1>
                <p class="text-[11px] text-cyan-400">قسم الحاسب الآلي | إشراف: أ. محمد الدوخي • إعداد: ريان المحيطيب</p>
            </div>
            <div class="w-10 h-10 rounded-xl bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center text-cyan-400 text-lg">
                <i class="fa-solid fa-microchip"></i>
            </div>
        </div>
    </header>

    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="bg-slate-900/70 border border-slate-800 p-4 rounded-2xl flex justify-between items-center">
            <div>
                <span class="text-xs text-slate-400">إجمالي البلاغات</span>
                <div class="text-2xl font-black text-white mt-1">{{ total_tickets }}</div>
            </div>
            <i class="fa-solid fa-clipboard-list text-cyan-400 text-2xl"></i>
        </div>
        <div class="bg-slate-900/70 border border-slate-800 p-4 rounded-2xl flex justify-between items-center">
            <div>
                <span class="text-xs text-slate-400">أعطال نشطة</span>
                <div class="text-2xl font-black text-red-400 mt-1">{{ active_tickets }}</div>
            </div>
            <i class="fa-solid fa-triangle-exclamation text-red-400 text-2xl"></i>
        </div>
        <div class="bg-slate-900/70 border border-slate-800 p-4 rounded-2xl flex justify-between items-center">
            <div>
                <span class="text-xs text-slate-400">قيد الإصلاح</span>
                <div class="text-2xl font-black text-amber-400 mt-1">{{ pending_tickets }}</div>
            </div>
            <i class="fa-solid fa-screwdriver-wrench text-amber-400 text-2xl"></i>
        </div>
        <div class="bg-slate-900/70 border border-slate-800 p-4 rounded-2xl flex justify-between items-center">
            <div>
                <span class="text-xs text-slate-400">الجاهزية التشغيلية</span>
                <div class="text-2xl font-black text-emerald-400 mt-1">{{ operational_rate }}%</div>
            </div>
            <i class="fa-solid fa-shield-halved text-emerald-400 text-2xl"></i>
        </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <!-- لوحة الأجهزة للمعمل المحدد مع أزرار تقارير المعمل المنفصلة -->
        <div class="lg:col-span-4 bg-slate-900/70 border border-slate-800 rounded-2xl p-5 flex flex-col justify-between">
            <div>
                <div class="flex justify-between items-center mb-3">
                    <a href="{{ url_for('qr_labels') }}" class="bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 text-xs px-2.5 py-1.5 rounded-lg flex items-center gap-1 transition">
                        <i class="fa-solid fa-print"></i> ملصقات QR
                    </a>
                    <div class="text-right">
                        <h2 class="font-bold text-sm text-white flex items-center gap-1.5">
                            <span id="active-lab-title">توزيع أجهزة معمل (1)</span>
                            <i class="fa-solid fa-network-wired text-cyan-400"></i>
                        </h2>
                        <span class="text-[10px] text-slate-400">27 جهاز حاسب + جهاز المدرب</span>
                    </div>
                </div>

                <!-- أزرار استخراج وطباعة تقرير هذا المعمل المحدد -->
                <div class="grid grid-cols-2 gap-2 mb-3">
                    <a id="lab-export-btn" href="{{ url_for('export_csv', lab_num=1) }}" class="bg-emerald-950/50 hover:bg-emerald-900/60 border border-emerald-500/40 text-emerald-300 text-[11px] py-1.5 px-2 rounded-xl text-center font-bold transition flex items-center justify-center gap-1.5 shadow-sm">
                        <i class="fa-solid fa-file-excel"></i> <span id="lab-export-text">إكسل معمل (1)</span>
                    </a>
                    <a id="lab-sheet-btn" href="{{ url_for('lab_report_sheet', lab_num=1) }}" target="_blank" class="bg-cyan-950/50 hover:bg-cyan-900/60 border border-cyan-500/40 text-cyan-300 text-[11px] py-1.5 px-2 rounded-xl text-center font-bold transition flex items-center justify-center gap-1.5 shadow-sm">
                        <i class="fa-solid fa-file-invoice"></i> <span id="lab-sheet-text">تقرير معمل (1) A4</span>
                    </a>
                </div>

                <div id="trainer-seat-box" onclick="inspectDevice(currentLabId, 0)" class="p-2 mb-3 bg-cyan-950/40 border border-cyan-800/50 rounded-xl text-center text-xs text-cyan-300 font-semibold flex items-center justify-center gap-2 cursor-pointer hover:border-cyan-400 transition">
                    <i class="fa-solid fa-chalkboard-user"></i> <span id="trainer-seat-text">منصة جهاز المدرب والشاشة الرئيسية</span>
                </div>

                <div class="grid grid-cols-3 gap-2" id="seats-container"></div>
                <a id="lab-report-link" href="{{ url_for('lab_report', lab_num=1) }}" target="_blank" class="mt-4 block rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-2.5 text-center text-xs font-bold text-cyan-300 hover:bg-cyan-500/20 transition">
                    <i class="fa-solid fa-qrcode ml-1"></i> فتح نموذج البلاغ المباشر لمعمل (1)
                </a>
            </div>
        </div>

        <div class="lg:col-span-8 bg-slate-900/70 border border-slate-800 rounded-2xl p-5 flex flex-col">
            <div class="flex justify-between items-center mb-3">
                <div class="flex items-center gap-3 text-[11px]">
                    <span class="flex items-center gap-1 text-slate-300"><span class="w-2.5 h-2.5 rounded-full bg-cyan-600"></span> سليم</span>
                    <span class="flex items-center gap-1 text-amber-400"><span class="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse"></span> قيد الإصلاح</span>
                    <span class="flex items-center gap-1 text-red-400"><span class="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping"></span> عطل نشط</span>
                </div>
                <h2 class="font-bold text-sm text-white flex items-center gap-2">
                    المخطط المعماري لجناح قسم الحاسب (رادار حي ومباشر) <i class="fa-solid fa-compass-drafting text-cyan-400"></i>
                </h2>
            </div>

            <div class="blueprint-container rounded-xl p-3 border border-cyan-950/80 overflow-x-auto flex justify-center">
                <svg viewBox="0 0 850 960" class="w-full max-w-[750px] h-auto select-none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="70" y="30" width="710" height="900" fill="none" stroke="#172554" stroke-width="3" rx="8" />

                    <!-- 1. الضلع العلوي الخارجي -->
                    <rect x="235" y="35" width="80" height="75" class="svg-room" />
                    <text x="275" y="72" class="svg-facility-text">شبكات</text><text x="275" y="87" class="svg-facility-text">الحاسب</text>

                    <g onclick="switchLab(26)" id="lab-node-26" class="cursor-pointer">
                        <rect x="320" y="35" width="85" height="75" class="svg-lab" rx="4" />
                        <text x="362" y="72" class="svg-text-title">معمل (26)</text><text x="362" y="88" class="svg-text-sub">الحوسبة</text>
                    </g>

                    <rect x="410" y="35" width="85" height="75" class="svg-room" />
                    <text x="452" y="72" class="svg-facility-text">أساسيات</text><text x="452" y="87" class="svg-facility-text">الكهرباء</text>

                    <g onclick="switchLab(24)" id="lab-node-24" class="cursor-pointer">
                        <rect x="500" y="35" width="85" height="75" class="svg-lab" rx="4" />
                        <text x="542" y="72" class="svg-text-title">معمل (24)</text><text x="542" y="88" class="svg-text-sub">الأساسيات</text>
                    </g>

                    <rect x="590" y="35" width="65" height="75" class="svg-room" /><text x="622" y="78" class="svg-facility-text">مستودع</text>
                    <rect x="660" y="35" width="80" height="75" class="svg-room" /><text x="700" y="72" class="svg-facility-text">أساسيات</text><text x="700" y="86" class="svg-facility-text">الإلكترونيات</text>

                    <g>
                        <rect x="745" y="35" width="30" height="75" fill="#1e293b" stroke="#475569" stroke-width="1.2" />
                        <line x1="745" y1="48" x2="775" y2="48" stroke="#64748b" /><line x1="745" y1="60" x2="775" y2="60" stroke="#64748b" /><line x1="745" y1="72" x2="775" y2="72" stroke="#64748b" /><line x1="745" y1="84" x2="775" y2="84" stroke="#64748b" /><line x1="745" y1="96" x2="775" y2="96" stroke="#64748b" />
                    </g>

                    <!-- 2. الضلع الأيسر الخارجي -->
                    <rect x="75" y="115" width="125" height="70" class="svg-room" /><text x="137" y="155" class="svg-facility-text">مستودع</text>
                    <rect x="75" y="190" width="125" height="75" class="svg-room" /><text x="137" y="232" class="svg-facility-text">دورة مياه المتدربين</text>

                    <g>
                        <rect x="75" y="270" width="125" height="75" fill="#854d0e" stroke="#eab308" stroke-width="2" rx="4" />
                        <line x1="85" y1="285" x2="165" y2="285" stroke="#facc15" stroke-width="3" /><line x1="85" y1="298" x2="165" y2="298" stroke="#facc15" stroke-width="3" /><line x1="85" y1="311" x2="165" y2="311" stroke="#facc15" stroke-width="3" /><line x1="85" y1="324" x2="165" y2="324" stroke="#facc15" stroke-width="3" /><line x1="85" y1="337" x2="165" y2="337" stroke="#facc15" stroke-width="3" />
                        <path d="M 180 330 L 180 280 L 175 290 M 180 280 L 185 290" stroke="#fef08a" stroke-width="2.5" fill="none" stroke-linecap="round" />
                    </g>

                    <g>
                        <rect x="70" y="380" width="130" height="95" fill="rgba(16, 185, 129, 0.08)" stroke="#10b981" stroke-width="1.8" stroke-dasharray="4" rx="4" />
                        <path d="M 70 410 A 30 30 0 0 1 100 440" stroke="#10b981" stroke-width="1.5" fill="none" /><line x1="70" y1="410" x2="70" y2="440" stroke="#10b981" stroke-width="2" />
                        <path d="M 70 470 A 30 30 0 0 0 100 440" stroke="#10b981" stroke-width="1.5" fill="none" /><line x1="70" y1="470" x2="70" y2="440" stroke="#10b981" stroke-width="2" />
                        <text x="135" y="425" fill="#34d399" font-size="11" font-weight="bold" text-anchor="middle">المدخل الرئيسي</text><text x="135" y="445" fill="#6ee7b7" font-size="9" text-anchor="middle">المزدوج</text>
                    </g>

                    <rect x="75" y="520" width="125" height="90" class="svg-room" /><text x="137" y="572" class="svg-facility-text" font-weight="bold">منسق رايات</text>

                    <g onclick="switchLab(1)" id="lab-node-1" class="cursor-pointer">
                        <rect x="75" y="620" width="125" height="90" class="svg-lab active-lab" rx="4" />
                        <text x="137" y="665" class="svg-text-title" font-size="12">معمل (1)</text><text x="137" y="682" class="svg-text-sub">الشبكات والأنظمة</text>
                    </g>

                    <!-- 3. المبنى الداخلي وقسم الحاسب -->
                    <rect x="250" y="200" width="415" height="490" fill="#040814" stroke="#1e3a8a" stroke-width="1.8" rx="6" />

                    <g onclick="switchLab(27)" id="lab-node-27" class="cursor-pointer">
                        <rect x="255" y="205" width="95" height="80" class="svg-lab" rx="3" /><text x="302" y="250" class="svg-text-title">معمل (27)</text>
                    </g>
                    <rect x="355" y="205" width="90" height="80" class="svg-room" />
                    <text x="400" y="245" fill="#fbbf24" font-size="10" font-weight="bold" text-anchor="middle">غرفة صيانة</text><text x="400" y="260" fill="#f59e0b" font-size="8" text-anchor="middle">⚙ صيانة الأجهزة</text>

                    <g onclick="switchLab(23)" id="lab-node-23" class="cursor-pointer">
                        <rect x="450" y="205" width="100" height="80" class="svg-lab" rx="3" /><text x="500" y="250" class="svg-text-title">معمل (23)</text>
                    </g>
                    <g onclick="switchLab(22)" id="lab-node-22" class="cursor-pointer">
                        <rect x="555" y="205" width="105" height="80" class="svg-lab" rx="3" /><text x="607" y="250" class="svg-text-title">معمل (22)</text>
                    </g>

                    <rect x="255" y="290" width="70" height="35" class="svg-room" /><text x="290" y="312" class="svg-facility-text" font-size="9">تهوية</text>
                    <rect x="255" y="330" width="70" height="75" class="svg-room" /><text x="290" y="365" class="svg-facility-text">مكتب التدريب</text><text x="290" y="380" class="svg-facility-text">الإلكتروني</text>
                    <rect x="255" y="410" width="70" height="80" class="svg-room" stroke="#38bdf8" /><text x="290" y="445" fill="#7dd3fc" font-size="10" font-weight="bold" text-anchor="middle">مكتب</text><text x="290" y="460" fill="#7dd3fc" font-size="10" font-weight="bold" text-anchor="middle">رئيس القسم</text>
                    <rect x="255" y="495" width="70" height="75" class="svg-room" /><text x="290" y="532" class="svg-facility-text">شؤون</text><text x="290" y="547" class="svg-facility-text">المتدربين</text>
                    <rect x="255" y="575" width="70" height="35" class="svg-room" /><text x="290" y="597" class="svg-facility-text" font-size="9">تهوية</text>

                    <!-- قسم الحاسب الوسطي -->
                    <g>
                        <rect x="335" y="295" width="235" height="295" fill="rgba(8, 47, 73, 0.25)" stroke="#0e7490" stroke-dasharray="5 5" stroke-width="1.5" rx="8" />
                        <circle cx="355" cy="315" r="7" fill="#047857" stroke="#10b981" stroke-width="1.5" />
                        <circle cx="550" cy="315" r="7" fill="#047857" stroke="#10b981" stroke-width="1.5" />
                        <circle cx="355" cy="570" r="7" fill="#047857" stroke="#10b981" stroke-width="1.5" />
                        <circle cx="550" cy="570" r="7" fill="#047857" stroke="#10b981" stroke-width="1.5" />
                        <text x="452" y="440" fill="#93c5fd" font-size="15" font-weight="bold" text-anchor="middle">قسم الحاسب</text>
                        <text x="452" y="462" fill="#3b82f6" font-size="10" font-family="monospace" letter-spacing="2" text-anchor="middle">COMPUTER DEPT</text>
                    </g>

                    <rect x="580" y="290" width="80" height="30" class="svg-room" /><text x="620" y="310" class="svg-facility-text" font-size="9">تهوية</text>
                    <rect x="580" y="325" width="80" height="28" class="svg-room" /><text x="620" y="343" class="svg-facility-text" font-size="9">مستودع 3</text>
                    <rect x="580" y="357" width="80" height="28" class="svg-room" /><text x="620" y="375" class="svg-facility-text" font-size="9">مستودع 2</text>
                    <rect x="580" y="389" width="80" height="28" class="svg-room" /><text x="620" y="407" class="svg-facility-text" font-size="9">مستودع 1</text>
                    
                    <g onclick="switchLab(14)" id="lab-node-14" class="cursor-pointer">
                        <rect x="580" y="423" width="80" height="75" class="svg-lab" rx="3" /><text x="620" y="465" class="svg-text-title">معمل (14)</text>
                    </g>
                    <g onclick="switchLab(12)" id="lab-node-12" class="cursor-pointer">
                        <rect x="580" y="503" width="80" height="75" class="svg-lab" rx="3" /><text x="620" y="545" class="svg-text-title">معمل (12)</text>
                    </g>
                    <rect x="580" y="582" width="80" height="30" class="svg-room" /><text x="620" y="602" class="svg-facility-text" font-size="9">تهوية</text>

                    <!-- الضلع السفلي الداخلي بالمقاسات الهندسية المضبوطة -->
                    <g onclick="switchLab(4)" id="lab-node-4" class="cursor-pointer">
                        <rect x="255" y="600" width="98" height="85" class="svg-lab" rx="4" /><text x="304" y="648" class="svg-text-title">معمل (4)</text>
                    </g>
                    <g onclick="switchLab(6)" id="lab-node-6" class="cursor-pointer">
                        <rect x="357" y="600" width="98" height="85" class="svg-lab" rx="4" /><text x="406" y="648" class="svg-text-title">معمل (6)</text>
                    </g>
                    <rect x="459" y="600" width="100" height="85" class="svg-room" />
                    <text x="509" y="635" class="svg-facility-text">كيابل</text><text x="509" y="651" class="svg-facility-text">الألياف</text><text x="509" y="667" class="svg-facility-text">الضوئية</text>

                    <g onclick="switchLab(10)" id="lab-node-10" class="cursor-pointer">
                        <rect x="563" y="600" width="100" height="85" class="svg-lab" rx="4" /><text x="613" y="648" class="svg-text-title">معمل (10)</text>
                    </g>

                    <!-- 4. الضلع الأيمن الخارجي -->
                    <rect x="715" y="140" width="60" height="90" class="svg-room" stroke="#059669" /><text x="745" y="190" fill="#6ee7b7" font-size="10" font-weight="bold" text-anchor="middle">مصلى</text>
                    <rect x="715" y="235" width="60" height="40" class="svg-room" /><text x="745" y="260" class="svg-facility-text" font-size="9">مستودع</text>
                    <rect x="715" y="280" width="60" height="100" class="svg-room" /><text x="745" y="325" class="svg-facility-text">قاعة</text><text x="745" y="340" class="svg-facility-text font-bold text-slate-300">نظري 1</text>
                    <rect x="715" y="385" width="60" height="40" class="svg-room" /><text x="745" y="410" class="svg-facility-text" font-size="9">مستودع</text>

                    <g onclick="switchLab(13)" id="lab-node-13" class="cursor-pointer">
                        <rect x="715" y="430" width="60" height="90" class="svg-lab" rx="3" /><text x="745" y="480" class="svg-text-title">معمل (13)</text>
                    </g>
                    <g onclick="switchLab(11)" id="lab-node-11" class="cursor-pointer">
                        <rect x="715" y="525" width="60" height="90" class="svg-lab" rx="3" /><text x="745" y="575" class="svg-text-title">معمل (11)</text>
                    </g>
                    <rect x="715" y="620" width="60" height="60" class="svg-room" /><text x="745" y="645" class="svg-facility-text" font-size="9">دورة مياه</text><text x="745" y="660" class="svg-facility-text" font-size="9">المتدربين</text>

                    <g>
                        <rect x="715" y="685" width="60" height="45" fill="#1e293b" stroke="#475569" />
                        <line x1="715" y1="696" x2="775" y2="696" stroke="#64748b" /><line x1="715" y1="707" x2="775" y2="707" stroke="#64748b" /><line x1="715" y1="718" x2="775" y2="718" stroke="#64748b" />
                    </g>

                    <!-- 5. الضلع السفلي الخارجي -->
                    <g onclick="switchLab(2)" id="lab-node-2" class="cursor-pointer">
                        <rect x="200" y="740" width="80" height="85" class="svg-lab" rx="4" /><text x="240" y="788" class="svg-text-title">معمل (2)</text>
                    </g>
                    <g onclick="switchLab(3)" id="lab-node-3" class="cursor-pointer">
                        <rect x="285" y="740" width="80" height="85" class="svg-lab" rx="4" /><text x="325" y="788" class="svg-text-title">معمل (3)</text>
                    </g>
                    <g onclick="switchLab(5)" id="lab-node-5" class="cursor-pointer">
                        <rect x="370" y="740" width="80" height="85" class="svg-lab" rx="4" /><text x="410" y="788" class="svg-text-title">معمل (5)</text>
                    </g>
                    <g onclick="switchLab(7)" id="lab-node-7" class="cursor-pointer">
                        <rect x="455" y="740" width="80" height="85" class="svg-lab" rx="4" /><text x="495" y="788" class="svg-text-title">معمل (7)</text>
                    </g>
                    <g onclick="switchLab(9)" id="lab-node-9" class="cursor-pointer">
                        <rect x="540" y="740" width="80" height="85" class="svg-lab" rx="4" /><text x="580" y="788" class="svg-text-title">معمل (9)</text>
                    </g>
                    <rect x="625" y="740" width="85" height="85" class="svg-room" /><text x="667" y="778" class="svg-facility-text font-bold text-slate-200">الكيابل</text><text x="667" y="794" class="svg-facility-text font-bold text-slate-200">النحاسية</text>
                    <rect x="715" y="740" width="60" height="85" class="svg-room" /><text x="745" y="788" class="svg-facility-text">مستودع</text>
                </svg>
            </div>
        </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div class="md:col-span-1 bg-slate-900/70 border border-slate-800 rounded-2xl p-5">
            <h3 class="font-bold text-sm text-white mb-3 flex items-center gap-2">
                <i class="fa-solid fa-boxes-stacked text-amber-400"></i> إحصائيات القطع المستهلكة
            </h3>
            <p class="text-[11px] text-slate-400 mb-3">تتبع قطع الغيار المستبدلة أثناء الصيانة الميدانية للأجهزة:</p>
            <div class="space-y-2">
                {% for part, count in parts_stats.items() %}
                <div class="flex justify-between items-center bg-slate-950/70 border border-slate-800/80 px-3 py-2 rounded-xl text-xs">
                    <span class="text-slate-200"><i class="fa-solid fa-screwdriver text-cyan-400 ml-1.5"></i> {{ part }}</span>
                    <span class="bg-cyan-500/10 text-cyan-400 font-bold px-2 py-0.5 rounded-lg border border-cyan-500/20">{{ count }} قطعة</span>
                </div>
                {% else %}
                <p class="text-xs text-slate-500 text-center py-4">لم يتم استهلاك أي قطع غيار حتى الآن.</p>
                {% endfor %}
            </div>
        </div>

        <div class="md:col-span-2 bg-slate-900/70 border border-slate-800 rounded-2xl p-5 flex flex-col justify-between">
            <div>
                <h3 class="font-bold text-sm text-white mb-3 flex items-center gap-2">
                    <i class="fa-solid fa-list-check text-cyan-400"></i> تذاكر الأعطال ومسار الصيانة الرقمي
                </h3>
                <div class="overflow-x-auto">
                    <table class="w-full text-right text-xs text-slate-300">
                        <thead class="bg-slate-950 text-slate-400 uppercase font-semibold border-b border-slate-800">
                            <tr>
                                <th class="p-2.5">رقم التذكرة</th>
                                <th class="p-2.5">الموقع</th>
                                <th class="p-2.5">المُبلّغ</th>
                                <th class="p-2.5">النوع والتفاصيل</th>
                                <th class="p-2.5">القطع المستبدلة</th>
                                <th class="p-2.5">الحالة</th>
                                <th class="p-2.5">إجراء الفني</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800/60">
                            {% for t in tickets %}
                            <tr class="hover:bg-slate-800/40">
                                <td class="p-2.5 font-mono font-bold text-cyan-400">#{{ t[0] }}</td>
                                <td class="p-2.5 font-semibold">معمل ({{ t[1] }}) - {% if t[2] == 0 %}منصة المدرب{% else %}جهاز {{ t[2] }}{% endif %}</td>
                                <td class="p-2.5">{{ t[3] }}</td>
                                <td class="p-2.5">{{ t[4] }} - <span class="text-slate-400">{{ t[5] }}</span></td>
                                <td class="p-2.5 text-amber-300">{{ t[7] }}</td>
                                <td class="p-2.5">
                                    {% if t[6] == 'مفتوح' %}
                                    <span class="bg-red-500/10 text-red-400 border border-red-500/30 px-2 py-0.5 rounded-full font-bold">مفتوح</span>
                                    {% elif t[6] == 'قيد الإصلاح' %}
                                    <span class="bg-amber-500/10 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-full font-bold">قيد الإصلاح</span>
                                    {% else %}
                                    <span class="bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-full font-bold">تم الحل</span>
                                    {% endif %}
                                </td>
                                <td class="p-2.5">
                                    <button onclick='inspectDevice({{ t[1] }}, {{ t[2] }})' class="bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 px-2.5 py-1 rounded-lg transition text-[11px]">
                                        <i class="fa-solid fa-pen-to-square"></i> إدارة وسجل الجهاز
                                    </button>
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="7" class="text-center p-6 text-xs text-slate-500">لا توجد بلاغات مسجلة حالياً في النظام. جميع الحواسيب والمعامل تعمل بكفاءة.</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- نافذة تفاصيل الجهاز والسجل التاريخي -->
    <div id="quick-modal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
        <div class="bg-slate-900 border border-slate-700/80 rounded-3xl max-w-xl w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                <h3 class="font-bold text-base text-white flex items-center gap-2">
                    <i class="fa-solid fa-computer text-cyan-400"></i> بطاقة الجهاز وسجل الصيانة: <span id="modal-device-name" class="text-cyan-400"></span>
                </h3>
                <button onclick="closeModal()" class="text-slate-400 hover:text-white text-lg"><i class="fa-solid fa-xmark"></i></button>
            </div>

            <div id="active-ticket-box" class="space-y-2 text-xs bg-slate-950/70 p-3.5 rounded-xl border border-red-500/40">
                <div class="flex justify-between items-center mb-1">
                    <span class="text-red-400 font-bold flex items-center gap-1.5"><i class="fa-solid fa-triangle-exclamation"></i> يوجد بلاغ صيانة نشط حالياً</span>
                    <span id="modal-ticket-id" class="text-cyan-400 font-mono font-bold"></span>
                </div>
                <div class="flex justify-between"><span class="text-slate-400">اسم المُبلّغ:</span> <span id="modal-reporter" class="text-slate-200"></span></div>
                <div class="flex justify-between"><span class="text-slate-400">نوع العطل:</span> <span id="modal-category" class="text-slate-200"></span></div>
                <div>
                    <span class="text-slate-400 block mb-1">وصف العطل:</span>
                    <p id="modal-desc" class="text-slate-300 bg-slate-900 p-2 rounded border border-slate-800 leading-relaxed"></p>
                </div>
            </div>

            <div id="no-active-ticket-box" class="hidden p-3 bg-emerald-950/30 border border-emerald-500/40 rounded-xl text-center text-xs text-emerald-300 font-semibold">
                <i class="fa-solid fa-circle-check ml-1"></i> هذا الجهاز يعمل بكفاءة تامة ولا توجد عليه أي بلاغات نشطة حالياً.
            </div>

            <form id="modal-form" method="POST" action="" class="space-y-3 pt-1">
                <div>
                    <label class="block text-xs font-semibold text-slate-300 mb-1">تحديث حالة التذكرة</label>
                    <select id="modal-status" name="status" class="w-full bg-slate-950 border border-slate-700 text-xs rounded-xl p-2.5 text-white focus:outline-none focus:border-cyan-400">
                        <option value="مفتوح">مفتوح (بانتظار الصيانة)</option>
                        <option value="قيد الإصلاح">قيد الإصلاح (جاري العمل عليه)</option>
                        <option value="تم الحل">تم الحل (الجهاز جاهز للعمل)</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-300 mb-1">القطع المستبدلة</label>
                    <input id="modal-parts" type="text" name="replaced_parts" placeholder="مثال: كابل باور، فأرة USB، كيبورد، رامات 8GB" class="w-full bg-slate-950 border border-slate-700 text-xs rounded-xl p-2.5 text-white focus:outline-none focus:border-cyan-400">
                </div>
                <div class="flex gap-2 pt-1">
                    <button type="submit" class="flex-1 py-2.5 bg-cyan-600 hover:bg-cyan-500 font-bold text-white text-xs rounded-xl transition shadow-lg shadow-cyan-600/20">
                        حفظ التعديل
                    </button>
                    <button type="button" onclick="closeModal()" class="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded-xl transition">
                        إغلاق
                    </button>
                </div>
            </form>

            <div class="border-t border-slate-800 pt-3">
                <h4 class="text-xs font-bold text-slate-300 mb-2 flex items-center gap-1.5">
                    <i class="fa-solid fa-clock-rotate-left text-cyan-400"></i> السجل التاريخي للبلاغات السابقة لهذا الجهاز:
                </h4>
                <div id="device-history-container" class="space-y-1.5 max-h-36 overflow-y-auto pr-1"></div>
            </div>
        </div>
    </div>

    <script>
        const allTickets = {{ tickets|tojson }};
        const labStatuses = {{ lab_statuses|tojson }};
        let currentLabId = 1;
        let nocInterval = null;
        let countdown = 30;

        function applyDynamicColors() {
            for (const [labNum, status] of Object.entries(labStatuses)) {
                const labGroup = document.getElementById(`lab-node-${labNum}`);
                if (labGroup) {
                    const rect = labGroup.querySelector('rect');
                    if (rect) {
                        rect.classList.remove('status-danger', 'status-warning');
                        if (status === 'danger') rect.classList.add('status-danger');
                        else if (status === 'warning') rect.classList.add('status-warning');
                    }
                }
            }
        }

        function renderSeatsGrid(labId) {
            currentLabId = labId;
            const container = document.getElementById('seats-container');
            container.innerHTML = '';

            const trainerTicket = allTickets.find(t => t[1] == labId && t[2] == 0 && t[6] !== 'تم الحل');
            const trainerBox = document.getElementById('trainer-seat-box');
            const trainerText = document.getElementById('trainer-seat-text');
            if (trainerTicket) {
                trainerBox.className = 'p-2 mb-3 bg-red-950/60 border border-red-500 rounded-xl text-center text-xs text-red-300 font-semibold flex items-center justify-center gap-2 cursor-pointer hover:border-red-400 transition shadow-lg shadow-red-500/20';
                trainerText.innerText = `منصة المدرب (عطل: ${trainerTicket[4]}) - انقر للسجل`;
            } else {
                trainerBox.className = 'p-2 mb-3 bg-cyan-950/40 border border-cyan-800/50 rounded-xl text-center text-xs text-cyan-300 font-semibold flex items-center justify-center gap-2 cursor-pointer hover:border-cyan-400 transition';
                trainerText.innerText = 'منصة جهاز المدرب والشاشة الرئيسية (سليم)';
            }

            for (let i = 1; i <= 27; i++) {
                const activeTicket = allTickets.find(t => t[1] == labId && t[2] == i && t[6] !== 'تم الحل');
                const seat = document.createElement('div');
                seat.onclick = () => inspectDevice(labId, i);
                
                if (activeTicket) {
                    const isFixing = activeTicket[6] === 'قيد الإصلاح';
                    seat.className = `${isFixing ? 'bg-amber-950/50 border-amber-500 text-amber-300' : 'bg-red-950/60 border-red-500 text-red-300 animate-pulse'} border p-2 rounded-xl text-center flex flex-col justify-between h-14 transition cursor-pointer hover:scale-105 shadow-md`;
                    seat.innerHTML = `
                        <div class="flex justify-between items-center text-[10px]">
                            <i class="fa-solid fa-triangle-exclamation"></i>
                            <span class="font-mono font-bold">#${i}</span>
                        </div>
                        <div class="text-[11px] font-bold">جهاز ${i}</div>
                        <div class="text-[9px] font-semibold">${activeTicket[6]}</div>
                    `;
                } else {
                    seat.className = 'bg-slate-950/80 border border-slate-800 hover:border-cyan-500/40 p-2 rounded-xl text-center flex flex-col justify-between h-14 transition cursor-pointer hover:scale-105';
                    seat.innerHTML = `
                        <div class="flex justify-between items-center text-[10px] text-slate-500">
                            <i class="fa-solid fa-display text-[9px]"></i>
                            <span class="font-mono">#${i}</span>
                        </div>
                        <div class="text-[11px] font-bold text-slate-200">جهاز ${i}</div>
                        <div class="text-[9px] text-emerald-400 font-semibold">جاهز</div>
                    `;
                }
                container.appendChild(seat);
            }
        }

        function switchLab(num) {
            document.getElementById('active-lab-title').innerText = `توزيع أجهزة معمل (${num})`;
            
            // تحديث روابط وأزرار التقرير المخصص للمعمل المختار
            document.getElementById('lab-export-btn').href = `/export_csv/${num}`;
            document.getElementById('lab-export-text').innerText = `إكسل معمل (${num})`;
            document.getElementById('lab-sheet-btn').href = `/lab/${num}/report-sheet`;
            document.getElementById('lab-sheet-text').innerText = `تقرير معمل (${num}) A4`;

            const reportLink = document.getElementById('lab-report-link');
            reportLink.href = `/lab/${num}/report`;
            reportLink.textContent = `بلاغ جديد في معمل (${num}) — نفس الرابط الموجود في QR المعمل`;

            document.querySelectorAll('.svg-lab').forEach(el => el.classList.remove('active-lab'));
            const labGroup = document.getElementById(`lab-node-${num}`);
            if (labGroup) {
                const rect = labGroup.querySelector('rect');
                if (rect) rect.classList.add('active-lab');
            }
            renderSeatsGrid(num);
        }

        function inspectDevice(labNum, seatNum) {
            const devTitle = seatNum === 0 ? `معمل (${labNum}) - منصة المدرب` : `معمل (${labNum}) - جهاز (${seatNum})`;
            document.getElementById('modal-device-name').innerText = devTitle;

            const activeTicket = allTickets.find(t => t[1] == labNum && t[2] == seatNum && t[6] !== 'تم الحل');
            const activeBox = document.getElementById('active-ticket-box');
            const noActiveBox = document.getElementById('no-active-ticket-box');
            const modalForm = document.getElementById('modal-form');

            if (activeTicket) {
                activeBox.classList.remove('hidden');
                noActiveBox.classList.add('hidden');
                modalForm.classList.remove('hidden');

                document.getElementById('modal-ticket-id').innerText = `#${activeTicket[0]}`;
                document.getElementById('modal-reporter').innerText = activeTicket[3];
                document.getElementById('modal-category').innerText = activeTicket[4];
                document.getElementById('modal-desc').innerText = activeTicket[5];
                document.getElementById('modal-status').value = activeTicket[6];
                document.getElementById('modal-parts').value = activeTicket[7] === 'لا يوجد' ? '' : activeTicket[7];
                modalForm.action = `/update_status/${activeTicket[0]}`;
            } else {
                activeBox.classList.add('hidden');
                noActiveBox.classList.remove('hidden');
                modalForm.classList.add('hidden');
            }

            const historyContainer = document.getElementById('device-history-container');
            historyContainer.innerHTML = '';
            const historyTickets = allTickets.filter(t => t[1] == labNum && t[2] == seatNum && t[6] === 'تم الحل');

            if (historyTickets.length > 0) {
                historyTickets.forEach(t => {
                    const row = document.createElement('div');
                    row.className = 'bg-slate-950/80 border border-slate-800 p-2 rounded-lg text-[11px] flex justify-between items-center';
                    row.innerHTML = `
                        <div>
                            <span class="text-cyan-400 font-bold font-mono">#${t[0]}</span>
                            <span class="text-slate-300 mr-1.5">${t[4]} (${t[5]})</span>
                            ${t[7] !== 'لا يوجد' ? `<span class="text-amber-400 block text-[10px]">القطع المستبدلة: ${t[7]}</span>` : ''}
                        </div>
                        <span class="text-emerald-400 font-semibold bg-emerald-500/10 px-2 py-0.5 rounded text-[10px]">تم الإصلاح</span>
                    `;
                    historyContainer.appendChild(row);
                });
            } else {
                historyContainer.innerHTML = '<p class="text-slate-500 text-[11px] text-center py-2">لا توجد بلاغات صيانة سابقة مسجلة لهذا الجهاز.</p>';
            }

            document.getElementById('quick-modal').classList.remove('hidden');
        }

        function closeModal() {
            document.getElementById('quick-modal').classList.add('hidden');
        }

        function toggleNocMode() {
            const body = document.getElementById('main-body');
            const badge = document.getElementById('noc-status-badge');
            const btnLabel = document.getElementById('noc-btn-label');

            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(() => {});
                body.classList.add('noc-active');
                badge.classList.remove('hidden');
                badge.classList.add('flex');
                btnLabel.innerText = "إنهاء وضع NOC";

                countdown = 30;
                nocInterval = setInterval(() => {
                    countdown--;
                    document.getElementById('countdown-timer').innerText = countdown;
                    if (countdown <= 0) {
                        location.reload();
                    }
                }, 1000);
            } else {
                if (document.exitFullscreen) document.exitFullscreen();
                body.classList.remove('noc-active');
                badge.classList.add('hidden');
                badge.classList.remove('flex');
                btnLabel.innerText = "شاشة المراقبة (NOC)";
                clearInterval(nocInterval);
            }
        }

        document.addEventListener('DOMContentLoaded', () => {
            applyDynamicColors();
            renderSeatsGrid(1);
        });
    </script>
</body>
</html>
"""

# --- صفحة التقرير الرسمي المطبوع A4 لكل معمل منفصل ---
LAB_REPORT_SHEET_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>تقرير الصيانة الرسمي | معمل ({{ lab_num }})</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800;900&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Tajawal', Tahoma, Arial, sans-serif; margin: 0; padding: 25px; color: #0f172a; background: #f8fafc; }
        .sheet { max-width: 900px; margin: 0 auto; background: white; padding: 35px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #0284c7; padding-bottom: 15px; margin-bottom: 25px; }
        .header h1 { margin: 0; font-size: 22px; color: #0369a1; }
        .header p { margin: 4px 0 0; font-size: 13px; color: #64748b; }
        .meta-box { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 25px; }
        .card { background: #f0fdf4; border: 1px solid #bbf7d0; padding: 14px; border-radius: 12px; text-align: center; }
        .card.warning { background: #fffbeb; border-color: #fde68a; }
        .card.danger { background: #fef2f2; border-color: #fecaca; }
        .card.info { background: #f0f9ff; border-color: #bae6fd; }
        .card span { font-size: 11px; color: #475569; display: block; margin-bottom: 4px; }
        .card strong { font-size: 20px; font-weight: 900; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 12px; }
        th, td { border: 1px solid #e2e8f0; padding: 10px; text-align: right; }
        th { background: #0f172a; color: white; font-weight: 700; }
        tr:nth-child(even) { background: #f8fafc; }
        .badge { padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 11px; }
        .badge-danger { background: #fee2e2; color: #991b1b; }
        .badge-warning { background: #fef3c7; color: #92400e; }
        .badge-success { background: #dcfce7; color: #166534; }
        .signatures { display: flex; justify-content: space-between; margin-top: 50px; padding-top: 20px; border-top: 1px dashed #cbd5e1; }
        .sign-block { text-align: center; width: 220px; }
        .sign-block p { margin: 0 0 45px; font-size: 13px; font-weight: bold; }
        .sign-line { border-bottom: 1.5px dotted #64748b; }
        .print-btn { display: inline-block; background: #0284c7; color: white; padding: 10px 20px; border-radius: 8px; font-weight: bold; text-decoration: none; cursor: pointer; border: 0; margin-bottom: 20px; }
        @media print {
            body { background: white; padding: 0; }
            .sheet { box-shadow: none; padding: 0; max-width: 100%; }
            .print-btn { display: none; }
        }
    </style>
</head>
<body>
    <div style="max-width: 900px; margin: 0 auto; text-align: left;">
        <button onclick="window.print()" class="print-btn">🖨️️ طباعة التقرير الرسمي (A4)</button>
    </div>

    <div class="sheet">
        <div class="header">
            <div>
                <h1>المعهد الصناعي الثانوي الأول بالأحساء</h1>
                <p>قسم الحاسب الآلي وتقنية المعلومات • تقرير الحالة التشغيلية والصيانة</p>
            </div>
            <div style="text-align: left;">
                <h2 style="margin: 0; color: #0284c7; font-size: 24px;">معمل ({{ lab_num }})</h2>
                <p>تاريخ الاستخراج: {{ report_date }}</p>
            </div>
        </div>

        <div class="meta-box">
            <div class="card info">
                <span>إجمالي محطات المعمل</span>
                <strong>28 جهاز</strong>
            </div>
            <div class="card">
                <span>الجاهزية التشغيلية</span>
                <strong style="color: #16a34a;">{{ op_rate }}%</strong>
            </div>
            <div class="card danger">
                <span>أعطال بانتظار الإصلاح</span>
                <strong style="color: #dc2626;">{{ active_count }}</strong>
            </div>
            <div class="card warning">
                <span>أعطال قيد الإصلاح</span>
                <strong style="color: #d97706;">{{ pending_count }}</strong>
            </div>
        </div>

        <h3 style="font-size: 15px; margin: 20px 0 10px; color: #0f172a;">سجل بلاغات الصيانة لجميع أجهزة معمل ({{ lab_num }}):</h3>
        <table>
            <thead>
                <tr>
                    <th style="width: 70px;">رقم التذكرة</th>
                    <th style="width: 110px;">الجهاز</th>
                    <th style="width: 120px;">المُبلّغ</th>
                    <th style="width: 90px;">نوع العطل</th>
                    <th>وصف المشكلة</th>
                    <th style="width: 120px;">القطع المستبدلة</th>
                    <th style="width: 80px;">الحالة</th>
                </tr>
            </thead>
            <tbody>
                {% for t in tickets %}
                <tr>
                    <td style="font-family: monospace; font-weight: bold;">#{{ t[0] }}</td>
                    <td style="font-weight: bold;">{% if t[2] == 0 %}منصة المدرب{% else %}جهاز {{ t[2] }}{% endif %}</td>
                    <td>{{ t[3] }}</td>
                    <td>{{ t[4] }}</td>
                    <td>{{ t[5] }}</td>
                    <td style="color: #d97706; font-weight: bold;">{{ t[7] }}</td>
                    <td>
                        {% if t[6] == 'مفتوح' %}
                        <span class="badge badge-danger">مفتوح</span>
                        {% elif t[6] == 'قيد الإصلاح' %}
                        <span class="badge badge-warning">قيد الإصلاح</span>
                        {% else %}
                        <span class="badge badge-success">تم الحل</span>
                        {% endif %}
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="7" style="text-align: center; padding: 25px; color: #64748b;">
                        لا توجد أي بلاغات صيانة مسجلة لمعمل ({{ lab_num }}). جميع الحواسيب تعمل بكفاءة تشغيلية 100%.
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <div class="signatures">
            <div class="sign-block">
                <p>فني دعم المعامل</p>
                <div class="sign-line"></div>
            </div>
            <div class="sign-block">
                <p>مشرف الصيانة التقنية<br><span style="font-size: 12px; color: #64748b;">أ. محمد الدوخي</span></p>
                <div class="sign-line"></div>
            </div>
            <div class="sign-block">
                <p>إعداد المنظومة التقنية<br><span style="font-size: 12px; color: #0284c7;">ريان المحيطيب</span></p>
                <div class="sign-line"></div>
            </div>
        </div>
    </div>
</body>
</html>
"""

# --- نموذج باركودات QR الموحدة (مقاس 15×15 سم على A4) ---
QR_LABELS_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>طباعة باركودات المعامل (A4 - 15x15 سم)</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800;900&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Tajawal', Tahoma, Arial, sans-serif; margin: 0; padding: 20px; color: #0f172a; background: #f8fafc; }
        .tools { max-width: 850px; margin: 0 auto 24px; padding: 18px 24px; background: white; border-radius: 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.06); }
        .tools h1 { margin: 0 0 6px; font-size: 20px; color: #0369a1; }
        .tools p { font-size: 13px; color: #64748b; margin: 0 0 14px; }
        .tools form { display: flex; gap: 10px; align-items: end; flex-wrap: wrap; }
        .tools label { flex: 1; min-width: 260px; font-size: 13px; font-weight: bold; }
        .tools input { width: 100%; margin-top: 6px; padding: 9px 12px; direction: ltr; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; }
        .tools button, .tools a { padding: 10px 18px; border: 0; border-radius: 8px; background: #0284c7; color: white; cursor: pointer; text-decoration: none; font-weight: bold; font-size: 13px; }
        .tools a.btn-back { background: #64748b; }
        .error { color: #b91c1c !important; font-size: 13px; margin-top: 8px; }

        .pages-container { display: flex; flex-direction: column; align-items: center; gap: 20px; }

        .a4-sheet {
            width: 210mm;
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
            width: 150mm;
            height: 150mm;
            border: 3.5px solid #0369a1;
            outline: 1.5px dashed #38bdf8;
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

        .qr-card-header .dept-title { font-size: 11px; font-weight: 700; color: #0284c7; margin: 0 0 3px; letter-spacing: 0.5px; }
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
    <div class="tools">
        <h1>طباعة باركودات المعامل (A4 - مقاس 15 × 15 سم)</h1>
        <p>تم ضبط كل باركود ليُطبع تلقائياً في ورقة A4 مستقلة بمقاس 15 × 15 سم في المنتصف تماماً مع إطار رسمي.</p>
        <form method="GET">
            <label>رابط النظام (الذي يفتحه جوال المتدرب عند المسح)
                <input name="base" type="url" required value="{{ base_url }}" placeholder="https://smart-lab-k5r2.onrender.com">
            </label>
            <button type="submit">تحديث الرابط</button>
            {% if not error %}
            <button type="button" onclick="window.print()">طباعة المعامل الـ 18 (كل معمل بورقة A4)</button>
            {% endif %}
            <a href="{{ url_for('dashboard') }}" class="btn-back">العودة للوحة التحكم</a>
        </form>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
    </div>

    {% if not error %}
    <div class="pages-container">
        {% for lab in labs %}
        <div class="a4-sheet">
            <div class="qr-card-15cm">
                <div class="qr-card-header">
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

# --- نموذج البلاغ الذكي بالواجهة الزجاجية ---
REPORT_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تقديم بلاغ صيانة | معمل ({{ lab_num }})</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800;900&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Tajawal', sans-serif;
            background-color: #040711;
            background-image: 
                radial-gradient(circle at 50% 18%, rgba(6, 182, 212, 0.18) 0%, transparent 60%),
                radial-gradient(rgba(14, 165, 233, 0.08) 1px, transparent 1px),
                linear-gradient(rgba(14, 165, 233, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(14, 165, 233, 0.03) 1px, transparent 1px);
            background-size: 100% 100%, 24px 24px, 12px 12px, 12px 12px;
        }
        .report-glass-card {
            background: rgba(13, 21, 41, 0.75);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border: 1px solid rgba(34, 211, 238, 0.28);
            box-shadow: 0 0 50px rgba(6, 182, 212, 0.12), inset 0 0 20px rgba(34, 211, 238, 0.03);
            transition: all 0.3s ease;
        }
    </style>
</head>
<body class="min-h-screen text-slate-200 flex flex-col justify-between items-center p-4">
    <div></div>

    <main class="max-w-lg w-full report-glass-card rounded-3xl p-7 md:p-8 relative my-auto shadow-2xl">
        <div class="text-center mb-6">
            <div class="w-14 h-14 bg-gradient-to-tr from-cyan-600/30 to-blue-500/20 border border-cyan-400/50 rounded-2xl flex items-center justify-center mx-auto text-cyan-400 text-2xl mb-3 shadow-[0_0_25px_rgba(6,182,212,0.3)]">
                <i class="fa-solid fa-headset"></i>
            </div>
            
            <div class="inline-flex items-center gap-2 bg-cyan-950/60 border border-cyan-500/40 px-3 py-1 rounded-full text-xs text-cyan-300 font-bold mb-2">
                <span class="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
                <span>معمل ({{ lab_num }})</span>
            </div>

            <h1 class="text-xl font-black text-white tracking-wide">تسجيل بلاغ صيانة حاسب آلي</h1>
            <p class="text-xs text-slate-400 mt-1">حدد رقم الجهاز بدقة وسيتحقق النظام من حالته فورياً</p>
        </div>

        {% if success %}
        <div class="bg-emerald-950/70 border border-emerald-500/50 p-6 rounded-2xl text-center space-y-3">
            <div class="w-12 h-12 bg-emerald-500/20 text-emerald-400 rounded-2xl flex items-center justify-center mx-auto text-2xl">
                <i class="fa-solid fa-check-double"></i>
            </div>
            <h3 class="text-base font-bold text-white">تم استلام البلاغ رقم #{{ success }} بنجاح!</h3>
            <p class="text-xs text-emerald-300/90 leading-relaxed">
                تم تسجيل البلاغ في الرادار المركزي لقسم الحاسب وجارٍ توجيه الفني لموقع الجهاز فوراً.
            </p>
            <div class="pt-2">
                <a href="{{ url_for('lab_report', lab_num=lab_num) }}" class="inline-block w-full py-2.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold rounded-xl text-xs shadow-lg shadow-emerald-500/25 transition">
                    تسجيل بلاغ جديد لنفس المعمل
                </a>
            </div>
        </div>
        {% else %}

        {% if error %}
        <div class="bg-red-950/60 border border-red-800/80 text-red-300 text-xs p-3 rounded-xl mb-4 text-center flex items-center justify-center gap-2">
            <i class="fa-solid fa-circle-exclamation text-red-400 text-sm"></i>
            <span>{{ error }}</span>
        </div>
        {% endif %}

        <form method="POST" class="space-y-4" onsubmit="handleSubmitBtn()">
            <div>
                <label for="seat" class="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
                    <i class="fa-solid fa-display text-cyan-400 text-[11px]"></i> موقع الجهاز المتعطل
                </label>
                <div class="relative">
                    <select id="seat" name="seat_num" required class="w-full bg-slate-950/90 border border-slate-700/80 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/40 rounded-xl py-2.5 px-3 text-xs text-white focus:outline-none transition cursor-pointer">
                        <option value="" disabled {% if not values.get('seat_num') %}selected{% endif %}>-- اختر الجهاز --</option>
                        
                        <option value="0" {% if 0 in occupied_seats %}disabled style="color: #f87171; background-color: #1e1b4b;"{% endif %} {% if values.get('seat_num') == '0' %}selected{% endif %}>
                            منصة المدرب والشاشة الرئيسية {% if 0 in occupied_seats %}(تم الإبلاغ عنه مسبقاً ⏳){% endif %}
                        </option>

                        {% for seat in seats %}
                        <option value="{{ seat }}" {% if seat in occupied_seats %}disabled style="color: #f87171; background-color: #1e1b4b;"{% endif %} {% if values.get('seat_num') == seat|string %}selected{% endif %}>
                            جهاز {{ seat }} {% if seat in occupied_seats %}(تم الإبلاغ عنه مسبقاً - قيد الصيانة ⏳){% endif %}
                        </option>
                        {% endfor %}
                    </select>
                </div>
            </div>

            <div>
                <label for="reporter" class="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
                    <i class="fa-solid fa-user text-cyan-400 text-[11px]"></i> اسم المُبلّغ (مدرب / متدرب)
                </label>
                <input id="reporter" name="reporter_name" maxlength="80" required value="{{ values.get('reporter_name', '') }}" placeholder="اكتب اسمك الثلاثي" class="w-full bg-slate-950/90 border border-slate-700/80 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/40 rounded-xl py-2.5 px-3 text-xs text-white focus:outline-none transition">
            </div>

            <div>
                <label for="category" class="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
                    <i class="fa-solid fa-tags text-cyan-400 text-[11px]"></i> تصنيف نوع العطل
                </label>
                <select id="category" name="issue_category" required class="w-full bg-slate-950/90 border border-slate-700/80 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/40 rounded-xl py-2.5 px-3 text-xs text-white focus:outline-none transition cursor-pointer">
                    {% for category in categories %}
                    <option value="{{ category }}" {% if values.get('issue_category') == category %}selected{% endif %}>{{ category }}</option>
                    {% endfor %}
                </select>
            </div>

            <div>
                <label for="issue" class="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
                    <i class="fa-solid fa-pen-nib text-cyan-400 text-[11px]"></i> وصف العطل بدقة
                </label>
                <textarea id="issue" name="issue" maxlength="1000" minlength="5" required placeholder="مثال: الجهاز لا يقلع، كابل الشاشة لا يعمل، الفأرة لا تستجيب..." class="w-full min-h-[95px] bg-slate-950/90 border border-slate-700/80 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/40 rounded-xl py-2.5 px-3 text-xs text-white focus:outline-none transition resize-none"></textarea>
            </div>

            <button type="submit" id="submit-report-btn" class="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold rounded-xl text-xs shadow-lg shadow-cyan-500/25 transition duration-200 flex items-center justify-center gap-2">
                <span id="btn-text">إرسال البلاغ فوراً</span>
                <i id="btn-spinner" class="fa-solid fa-paper-plane text-xs"></i>
            </button>
        </form>
        {% endif %}
    </main>

    <footer class="my-4 text-center">
        <div class="bg-slate-900/60 border border-slate-800/80 backdrop-blur-md px-5 py-2 rounded-full text-xs text-slate-400 inline-flex flex-wrap items-center justify-center gap-2 shadow-lg">
            <span class="font-bold text-slate-200">قسم الحاسب الآلي وتقنية المعلومات</span>
            <span class="text-cyan-500/60">•</span>
            <span>إشراف: <span class="text-slate-300 font-semibold">أ. محمد الدوخي</span></span>
            <span class="text-cyan-500/60">•</span>
            <span>إعداد: <span class="text-cyan-400 font-semibold">ريان المحيطيب</span></span>
        </div>
    </footer>

    <script>
        function handleSubmitBtn() {
            const btn = document.getElementById('submit-report-btn');
            const btnText = document.getElementById('btn-text');
            const icon = document.getElementById('btn-spinner');
            if (btn) {
                btnText.innerText = "جاري إرسال البلاغ وتوجيه الفني...";
                icon.className = "fa-solid fa-circle-notch fa-spin text-xs";
                btn.classList.add('opacity-85', 'cursor-not-allowed');
            }
        }
    </script>
</body>
</html>
"""

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
    requested_base = request.args.get('base', request.url_root.rstrip('/'))
    base_url = qr_base_url(requested_base)
    return render_template_string(
        QR_LABELS_TEMPLATE,
        base_url=requested_base,
        labs=LAB_NUMBERS,
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

    conn = sqlite3.connect(os.path.join(BASE_DIR, 'maintenance.db'))
    cursor = conn.cursor()
    cursor.execute("SELECT seat_num FROM tickets WHERE lab_num = ? AND status != 'تم الحل'", (lab_num,))
    occupied_seats = [row[0] for row in cursor.fetchall()]
    conn.close()

    error = None
    values = request.form.to_dict(flat=True) if request.method == 'POST' else {}
    if request.method == 'POST':
        seat_raw = values.get('seat_num', '')
        reporter = values.get('reporter_name', '').strip()
        category = values.get('issue_category', '')
        issue = values.get('issue', '').strip()
        
        if not seat_raw.isdigit() or not 0 <= int(seat_raw) <= 27:
            error = 'اختر جهازًا صحيحًا أو منصة المدرب.'
        elif int(seat_raw) in occupied_seats:
            error = 'عذراً! هذا الجهاز مسجل عليه بلاغ نشط بالفعل وهو قيد متابعة فريق الصيانة حالياً.'
        elif not 1 <= len(reporter) <= 80:
            error = 'اكتب اسم المبلّغ (حتى 80 حرفًا).'
        elif category not in ISSUE_CATEGORIES:
            error = 'اختر نوع العطل من القائمة.'
        elif not 5 <= len(issue) <= 1000:
            error = 'اكتب وصفًا للعطل من 5 إلى 1000 حرف.'
        else:
            with sqlite3.connect(os.path.join(BASE_DIR, 'maintenance.db')) as conn:
                cursor = conn.execute(
                    'INSERT INTO tickets (lab_num, seat_num, reporter_name, issue_category, issue) VALUES (?, ?, ?, ?, ?)',
                    (lab_num, int(seat_raw), reporter, category, issue)
                )
                ticket_id = cursor.lastrowid
            return redirect(url_for('lab_report', lab_num=lab_num, success=ticket_id))

    success_raw = request.args.get('success', '')
    success = int(success_raw) if success_raw.isdigit() else None
    return render_template_string(
        REPORT_TEMPLATE, lab_num=lab_num, seats=range(1, 28),
        occupied_seats=occupied_seats,
        categories=ISSUE_CATEGORIES, values=values, error=error, success=success
    )

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(os.path.join(BASE_DIR, 'maintenance.db'))
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tickets ORDER BY id DESC')
    tickets = cursor.fetchall()
    conn.close()

    total = len(tickets)
    active = sum(1 for t in tickets if t[6] == 'مفتوح')
    pending = sum(1 for t in tickets if t[6] == 'قيد الإصلاح')
    op_rate = 100.0 if total == 0 else round(((total - active) / total) * 100, 1)

    lab_statuses = {}
    for lab in LAB_NUMBERS:
        lab_tickets = [t for t in tickets if t[1] == lab and t[6] != 'تم الحل']
        if any(t[6] == 'مفتوح' for t in lab_tickets):
            lab_statuses[lab] = 'danger'
        elif any(t[6] == 'قيد الإصلاح' for t in lab_tickets):
            lab_statuses[lab] = 'warning'
        else:
            lab_statuses[lab] = 'ok'

    all_parts = []
    for t in tickets:
        part_text = t[7].strip() if len(t) > 7 and t[7] else ''
        if part_text and part_text != 'لا يوجد':
            for p in part_text.replace('،', ',').split(','):
                cleaned = p.strip()
                if cleaned:
                    all_parts.append(cleaned)
    parts_stats = dict(Counter(all_parts).most_common(5))

    return render_template_string(
        DASHBOARD_TEMPLATE,
        tickets=tickets,
        total_tickets=total,
        active_tickets=active,
        pending_tickets=pending,
        operational_rate=op_rate,
        lab_statuses=lab_statuses,
        parts_stats=parts_stats
    )

@app.route('/update_status/<int:ticket_id>', methods=['POST'])
def update_status(ticket_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    new_status = request.form.get('status')
    replaced_parts = request.form.get('replaced_parts', '').strip() or 'لا يوجد'
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'maintenance.db'))
    cursor = conn.cursor()
    cursor.execute('UPDATE tickets SET status = ?, replaced_parts = ? WHERE id = ?', (new_status, replaced_parts, ticket_id))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# مسار تصدير تقرير Excel (العام أو لكل معمل منفصل)
@app.route('/export_csv')
@app.route('/export_csv/<int:lab_num>')
def export_csv(lab_num=None):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    selected_lab = request.args.get('lab', type=int) or lab_num
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'maintenance.db'))
    cursor = conn.cursor()
    
    if selected_lab:
        cursor.execute('SELECT id, lab_num, seat_num, reporter_name, issue_category, issue, status, replaced_parts, created_at FROM tickets WHERE lab_num = ? ORDER BY id DESC', (selected_lab,))
        download_name = f"maintenance_report_lab_{selected_lab}.csv"
    else:
        cursor.execute('SELECT id, lab_num, seat_num, reporter_name, issue_category, issue, status, replaced_parts, created_at FROM tickets ORDER BY id DESC')
        download_name = "smart_lab_maintenance_report_all.csv"
        
    tickets = cursor.fetchall()
    conn.close()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['رقم التذكرة', 'رقم المعمل', 'موقع الجهاز', 'اسم المُبلّغ', 'تصنيف العطل', 'وصف العطل', 'حالة التذكرة', 'القطع المستبدلة', 'تاريخ ووقت البلاغ'])
    for t in tickets:
        seat_name = "منصة المدرب" if t[2] == 0 else f"جهاز {t[2]}"
        writer.writerow([t[0], f"معمل {t[1]}", seat_name, t[3], t[4], t[5], t[6], t[7], t[8]])

    output = si.getvalue().encode('utf-8-sig')
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={download_name}"}
    )

# مسار التقرير الرسمي المطبوع A4 لكل معمل منفصل
@app.route('/lab/<int:lab_num>/report-sheet')
def lab_report_sheet(lab_num):
    if 'user' not in session:
        return redirect(url_for('login'))
    if lab_num not in LAB_NUMBERS:
        abort(404)

    conn = sqlite3.connect(os.path.join(BASE_DIR, 'maintenance.db'))
    cursor = conn.cursor()
    cursor.execute('SELECT id, lab_num, seat_num, reporter_name, issue_category, issue, status, replaced_parts, created_at FROM tickets WHERE lab_num = ? ORDER BY id DESC', (lab_num,))
    tickets = cursor.fetchall()
    conn.close()

    total_seats = 28  # 27 جهاز متدرب + جهاز المدرب
    active_count = sum(1 for t in tickets if t[6] == 'مفتوح')
    pending_count = sum(1 for t in tickets if t[6] == 'قيد الإصلاح')
    
    # حساب نسبة جاهزية هذا المعمل بالتحديد
    unusable_devices = active_count + pending_count
    op_rate = round(max(0, (total_seats - unusable_devices) / total_seats) * 100, 1)

    now_str = datetime.now().strftime('%Y-%m-%d %I:%M %p')

    return render_template_string(
        LAB_REPORT_SHEET_TEMPLATE,
        lab_num=lab_num,
        tickets=tickets,
        op_rate=op_rate,
        active_count=active_count,
        pending_count=pending_count,
        report_date=now_str
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
