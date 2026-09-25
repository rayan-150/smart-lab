import os
import sqlite3
from flask import Flask, render_template_string, request, redirect, url_for, session

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
    "admin": {"password": "123", "role": "مشرف الصيانة التقنية", "name": "ريان المحيطيب"},
    "tech": {"password": "123", "role": "فني دعم المعامل", "name": "الدعم الفني"},
    "trainer": {"password": "123", "role": "مدرب قسم الحاسب", "name": "مدرب حاسب"}
}

# --- صفحة تسجيل الدخول ---
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تسجيل الدخول | نظام صيانة حواسيب المعامل</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
    <style>body { font-family: 'Tajawal', sans-serif; }</style>
</head>
<body class="bg-slate-950 text-slate-200 min-h-screen flex items-center justify-center p-4">
    <div class="max-w-md w-full bg-slate-900/80 border border-slate-800 rounded-3xl p-8 backdrop-blur shadow-2xl">
        <div class="text-center mb-6">
            <div class="w-14 h-14 bg-cyan-500/20 border border-cyan-400/40 rounded-2xl flex items-center justify-center mx-auto text-cyan-400 text-2xl mb-3 shadow-lg shadow-cyan-500/10">
                <i class="fa-solid fa-microchip"></i>
            </div>
            <h2 class="text-xl font-black text-white">نظام إدارة صيانة المعامل</h2>
            <p class="text-xs text-cyan-400 mt-1">قسم الحاسب الآلي وتقنية المعلومات</p>
        </div>

        {% if error %}
        <div class="bg-red-950/50 border border-red-800/80 text-red-300 text-xs p-3 rounded-xl mb-4 text-center">
            {{ error }}
        </div>
        {% endif %}

        <form method="POST" action="/login" class="space-y-4">
            <div>
                <label class="block text-xs font-semibold text-slate-300 mb-1">اسم المستخدم</label>
                <input type="text" name="username" required placeholder="admin" class="w-full bg-slate-950/80 border border-slate-700 focus:border-cyan-400 rounded-xl py-2.5 px-3 text-xs text-white focus:outline-none">
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-300 mb-1">كلمة المرور</label>
                <input type="password" name="password" required placeholder="123" class="w-full bg-slate-950/80 border border-slate-700 focus:border-cyan-400 rounded-xl py-2.5 px-3 text-xs text-white focus:outline-none">
            </div>
            <button type="submit" class="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold rounded-xl text-xs shadow-lg shadow-cyan-500/20 transition">
                تسجيل الدخول
            </button>
        </form>
    </div>
</body>
</html>
"""

# --- صفحة لوحة التحكم بالمخطط المعماري الهندسي المطابق للورقة ---
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة العمليات والمخطط المعماري | صيانة المعامل</title>
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
        /* أنماط غرف المخطط المعماري المتجه SVG */
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
    </style>
</head>
<body class="min-h-screen flex flex-col p-4 md:p-6 space-y-6">

    <!-- شريط الرأس -->
    <header class="flex justify-between items-center px-6 py-4 bg-slate-900/80 border border-slate-800 rounded-2xl backdrop-blur">
        <div class="flex items-center gap-3">
            <a href="/logout" class="bg-red-950/40 hover:bg-red-900/60 border border-red-800/60 text-red-400 px-3.5 py-1.5 rounded-xl text-xs flex items-center gap-2 transition">
                <i class="fa-solid fa-power-off"></i> خروج
            </a>
            <div class="flex items-center gap-2 bg-slate-800/60 border border-slate-700/60 px-3.5 py-1.5 rounded-xl text-xs">
                <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span class="font-bold text-slate-200">{{ session.get('name', 'ريان المحيطيب') }}</span>
                <span class="text-cyan-400 text-[10px]">({{ session.get('role', 'مشرف') }})</span>
            </div>
        </div>
        <div class="text-left flex items-center gap-3">
            <div>
                <h1 class="font-black text-base text-white">النظام الذكي لإدارة ومتابعة صيانة حواسيب المعامل</h1>
                <p class="text-[11px] text-cyan-400">قسم الحاسب الآلي | إشراف: أ. محمد الدوخي • إعداد: ريان المحيطيب</p>
            </div>
            <div class="w-10 h-10 rounded-xl bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center text-cyan-400 text-lg">
                <i class="fa-solid fa-microchip"></i>
            </div>
        </div>
    </header>

    <!-- إحصائيات المعامل -->
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

    <!-- شبكة المقاعد + المخطط الهندسي المطابق للورقة بالملي -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">

        <!-- لوحة المقاعد الـ 27 (يسار) -->
        <div class="lg:col-span-4 bg-slate-900/70 border border-slate-800 rounded-2xl p-5 flex flex-col justify-between">
            <div>
                <div class="flex justify-between items-center mb-4">
                    <button onclick="window.print()" class="bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 text-xs px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition">
                        <i class="fa-solid fa-print"></i> طباعة ملصقات QR
                    </button>
                    <div class="text-right">
                        <h2 class="font-bold text-sm text-white flex items-center gap-2">
                            <span id="active-lab-title">توزيع مقاعد معمل (1)</span>
                            <i class="fa-solid fa-network-wired text-cyan-400"></i>
                        </h2>
                        <span class="text-[10px] text-slate-400">27 محطة تدريبية + منصة المدرب</span>
                    </div>
                </div>

                <div class="p-2 mb-3 bg-cyan-950/40 border border-cyan-800/50 rounded-xl text-center text-xs text-cyan-300 font-semibold flex items-center justify-center gap-2">
                    <i class="fa-solid fa-chalkboard-user"></i> منصة جهاز المدرب والشاشة الرئيسية
                </div>

                <div class="grid grid-cols-3 gap-2" id="seats-container"></div>
            </div>
        </div>

        <!-- المخطط المعماري الكامل للقسم (رسم متجه مطابق 100% لورقة المخطط) -->
        <div class="lg:col-span-8 bg-slate-900/70 border border-slate-800 rounded-2xl p-5 flex flex-col">
            <div class="flex justify-between items-center mb-3">
                <span class="text-[11px] text-slate-400">انقر على أي معمل بالرسم الهندسي لفتح شبكة أجهزته</span>
                <h2 class="font-bold text-sm text-white flex items-center gap-2">
                    المخطط المعماري لجناح قسم الحاسب (مطابق للرسم الهندسي) <i class="fa-solid fa-compass-drafting text-cyan-400"></i>
                </h2>
            </div>

            <!-- إطار الرسم المعماري الهندسي -->
            <div class="blueprint-container rounded-xl p-3 border border-cyan-950/80 overflow-x-auto flex justify-center">
                <svg viewBox="0 0 850 960" class="w-full max-w-[750px] h-auto select-none" xmlns="http://www.w3.org/2000/svg">
                    
                    <!-- جدار المبنى الخارجي والداخلي -->
                    <rect x="70" y="30" width="710" height="900" fill="none" stroke="#172554" stroke-width="3" rx="8" />

                    <!-- ================= 1. الضلع العلوي الخارجي ================= -->
                    <!-- شبكات الحاسب -->
                    <rect x="235" y="35" width="80" height="75" class="svg-room" />
                    <text x="275" y="72" class="svg-facility-text">شبكات</text>
                    <text x="275" y="87" class="svg-facility-text">الحاسب</text>

                    <!-- معمل 26 -->
                    <g onclick="switchLab(26)" id="lab-node-26" class="cursor-pointer">
                        <rect x="320" y="35" width="85" height="75" class="svg-lab" rx="4" />
                        <text x="362" y="72" class="svg-text-title">معمل (26)</text>
                        <text x="362" y="88" class="svg-text-sub">الحوسبة</text>
                    </g>

                    <!-- أساسيات الكهرباء -->
                    <rect x="410" y="35" width="85" height="75" class="svg-room" />
                    <text x="452" y="72" class="svg-facility-text">أساسيات</text>
                    <text x="452" y="87" class="svg-facility-text">الكهرباء</text>

                    <!-- معمل 24 -->
                    <g onclick="switchLab(24)" id="lab-node-24" class="cursor-pointer">
                        <rect x="500" y="35" width="85" height="75" class="svg-lab" rx="4" />
                        <text x="542" y="72" class="svg-text-title">معمل (24)</text>
                        <text x="542" y="88" class="svg-text-sub">الأساسيات</text>
                    </g>

                    <!-- مستودع -->
                    <rect x="590" y="35" width="65" height="75" class="svg-room" />
                    <text x="622" y="78" class="svg-facility-text">مستودع</text>

                    <!-- أساسيات الإلكترونيات -->
                    <rect x="660" y="35" width="80" height="75" class="svg-room" />
                    <text x="700" y="72" class="svg-facility-text">أساسيات</text>
                    <text x="700" y="86" class="svg-facility-text">الإلكترونيات</text>

                    <!-- درج علوي يمين -->
                    <g>
                        <rect x="745" y="35" width="30" height="75" fill="#1e293b" stroke="#475569" stroke-width="1.2" />
                        <line x1="745" y1="48" x2="775" y2="48" stroke="#64748b" />
                        <line x1="745" y1="60" x2="775" y2="60" stroke="#64748b" />
                        <line x1="745" y1="72" x2="775" y2="72" stroke="#64748b" />
                        <line x1="745" y1="84" x2="775" y2="84" stroke="#64748b" />
                        <line x1="745" y1="96" x2="775" y2="96" stroke="#64748b" />
                    </g>

                    <!-- ================= 2. الضلع الأيسر الخارجي (الواجهة والمدخل الرئيسي) ================= -->
                    <!-- مستودع -->
                    <rect x="75" y="115" width="125" height="70" class="svg-room" />
                    <text x="137" y="155" class="svg-facility-text">مستودع</text>

                    <!-- دورة مياه المتدربين -->
                    <rect x="75" y="190" width="125" height="75" class="svg-room" />
                    <text x="137" y="232" class="svg-facility-text">دورة مياه المتدربين</text>

                    <!-- الدرج (الملون بالأصفر الفاقع كما بالورقة تماماً!) -->
                    <g>
                        <rect x="75" y="270" width="125" height="75" fill="#854d0e" stroke="#eab308" stroke-width="2" rx="4" />
                        <!-- درجات السلم الصفراء -->
                        <line x1="85" y1="285" x2="165" y2="285" stroke="#facc15" stroke-width="3" />
                        <line x1="85" y1="298" x2="165" y2="298" stroke="#facc15" stroke-width="3" />
                        <line x1="85" y1="311" x2="165" y2="311" stroke="#facc15" stroke-width="3" />
                        <line x1="85" y1="324" x2="165" y2="324" stroke="#facc15" stroke-width="3" />
                        <line x1="85" y1="337" x2="165" y2="337" stroke="#facc15" stroke-width="3" />
                        <!-- سهم الصعود -->
                        <path d="M 180 330 L 180 280 L 175 290 M 180 280 L 185 290" stroke="#fef08a" stroke-width="2.5" fill="none" stroke-linecap="round" />
                    </g>

                    <!-- المدخل الرئيسي المزدوج (بأبواب معمارية مفتوحة) -->
                    <g>
                        <rect x="70" y="380" width="130" height="95" fill="rgba(16, 185, 129, 0.08)" stroke="#10b981" stroke-width="1.8" stroke-dasharray="4" rx="4" />
                        <!-- قوس الباب المزدوج -->
                        <path d="M 70 410 A 30 30 0 0 1 100 440" stroke="#10b981" stroke-width="1.5" fill="none" />
                        <line x1="70" y1="410" x2="70" y2="440" stroke="#10b981" stroke-width="2" />
                        <path d="M 70 470 A 30 30 0 0 0 100 440" stroke="#10b981" stroke-width="1.5" fill="none" />
                        <line x1="70" y1="470" x2="70" y2="440" stroke="#10b981" stroke-width="2" />
                        <text x="135" y="425" fill="#34d399" font-size="11" font-weight="bold" text-anchor="middle">المدخل الرئيسي</text>
                        <text x="135" y="445" fill="#6ee7b7" font-size="9" text-anchor="middle">المزدوج</text>
                    </g>

                    <!-- منسق رايات -->
                    <rect x="75" y="520" width="125" height="90" class="svg-room" />
                    <text x="137" y="572" class="svg-facility-text" font-weight="bold">منسق رايات</text>

                    <!-- معمل 1 (الزاوية السفلية) -->
                    <g onclick="switchLab(1)" id="lab-node-1" class="cursor-pointer">
                        <rect x="75" y="620" width="125" height="90" class="svg-lab active-lab" rx="4" />
                        <text x="137" y="665" class="svg-text-title" font-size="12">معمل (1)</text>
                        <text x="137" y="682" class="svg-text-sub">الشبكات والأنظمة</text>
                    </g>

                    <!-- ================= 3. المبنى الداخلي والفناء الأوسط المفتوح ================= -->
                    <!-- حدود الفناء الداخلي والممرات -->
                    <rect x="250" y="200" width="415" height="490" fill="#040814" stroke="#1e3a8a" stroke-width="1.8" rx="6" />

                    <!-- صف القاعات العلوي الداخلي -->
                    <g onclick="switchLab(27)" id="lab-node-27" class="cursor-pointer">
                        <rect x="255" y="205" width="95" height="80" class="svg-lab" rx="3" />
                        <text x="302" y="250" class="svg-text-title">معمل (27)</text>
                    </g>
                    <!-- غرفة الصيانة -->
                    <rect x="355" y="205" width="90" height="80" class="svg-room" />
                    <text x="400" y="245" fill="#fbbf24" font-size="10" font-weight="bold" text-anchor="middle">غرفة صيانة</text>
                    <text x="400" y="260" fill="#f59e0b" font-size="8" text-anchor="middle">⚙ صيانة الأجهزة</text>

                    <!-- معمل 23 -->
                    <g onclick="switchLab(23)" id="lab-node-23" class="cursor-pointer">
                        <rect x="450" y="205" width="100" height="80" class="svg-lab" rx="3" />
                        <text x="500" y="250" class="svg-text-title">معمل (23)</text>
                    </g>

                    <!-- معمل 22 -->
                    <g onclick="switchLab(22)" id="lab-node-22" class="cursor-pointer">
                        <rect x="555" y="205" width="105" height="80" class="svg-lab" rx="3" />
                        <text x="607" y="250" class="svg-text-title">معمل (22)</text>
                    </g>

                    <!-- الجهة الغربية للفناء: تهوية، شؤون المتدربين، مكتب رئيس القسم، مكتب التدريب الإلكتروني، تهوية -->
                    <rect x="255" y="290" width="70" height="35" class="svg-room" /><text x="290" y="312" class="svg-facility-text" font-size="9">تهوية</text>
                    <rect x="255" y="330" width="70" height="75" class="svg-room" /><text x="290" y="365" class="svg-facility-text">شؤون</text><text x="290" y="380" class="svg-facility-text">المتدربين</text>
                    <rect x="255" y="410" width="70" height="80" class="svg-room" stroke="#38bdf8" /><text x="290" y="445" fill="#7dd3fc" font-size="10" font-weight="bold" text-anchor="middle">مكتب</text><text x="290" y="460" fill="#7dd3fc" font-size="10" font-weight="bold" text-anchor="middle">رئيس القسم</text>
                    <rect x="255" y="495" width="70" height="75" class="svg-room" /><text x="290" y="532" class="svg-facility-text">مكتب التدريب</text><text x="290" y="547" class="svg-facility-text">الإلكتروني</text>
                    <rect x="255" y="575" width="70" height="35" class="svg-room" /><text x="290" y="597" class="svg-facility-text" font-size="9">تهوية</text>

                    <!-- الفناء الأوسط المفتوح (Courtyard / بهو) -->
                    <g>
                        <rect x="335" y="295" width="235" height="295" fill="rgba(8, 47, 73, 0.25)" stroke="#0e7490" stroke-dasharray="5 5" stroke-width="1.5" rx="8" />
                        <!-- النباتات الأربعة في زوايا الفناء (كما بالورقة!) -->
                        <!-- أعلى يسار -->
                        <circle cx="355" cy="315" r="7" fill="#047857" stroke="#10b981" stroke-width="1.5" />
                        <!-- أعلى يمين -->
                        <circle cx="550" cy="315" r="7" fill="#047857" stroke="#10b981" stroke-width="1.5" />
                        <!-- أسفل يسار -->
                        <circle cx="355" cy="570" r="7" fill="#047857" stroke="#10b981" stroke-width="1.5" />
                        <!-- أسفل يمين -->
                        <circle cx="550" cy="570" r="7" fill="#047857" stroke="#10b981" stroke-width="1.5" />

                        <text x="452" y="440" fill="#93c5fd" font-size="14" font-weight="bold" text-anchor="middle">الفناء الأوسط</text>
                        <text x="452" y="462" fill="#3b82f6" font-size="10" font-family="monospace" letter-spacing="2" text-anchor="middle">COURTYARD</text>
                    </g>

                    <!-- الجدار الداخلي الأيمن (المستودعات ومعامل 14 و 12) -->
                    <rect x="580" y="290" width="80" height="30" class="svg-room" /><text x="620" y="310" class="svg-facility-text" font-size="9">تهوية</text>
                    <rect x="580" y="325" width="80" height="28" class="svg-room" /><text x="620" y="343" class="svg-facility-text" font-size="9">مستودع 3</text>
                    <rect x="580" y="357" width="80" height="28" class="svg-room" /><text x="620" y="375" class="svg-facility-text" font-size="9">مستودع 2</text>
                    <rect x="580" y="389" width="80" height="28" class="svg-room" /><text x="620" y="407" class="svg-facility-text" font-size="9">مستودع 1</text>
                    
                    <!-- معمل 14 -->
                    <g onclick="switchLab(14)" id="lab-node-14" class="cursor-pointer">
                        <rect x="580" y="423" width="80" height="75" class="svg-lab" rx="3" />
                        <text x="620" y="465" class="svg-text-title">معمل (14)</text>
                    </g>

                    <!-- معمل 12 -->
                    <g onclick="switchLab(12)" id="lab-node-12" class="cursor-pointer">
                        <rect x="580" y="503" width="80" height="75" class="svg-lab" rx="3" />
                        <text x="620" y="545" class="svg-text-title">معمل (12)</text>
                    </g>
                    <rect x="580" y="582" width="80" height="30" class="svg-room" /><text x="620" y="602" class="svg-facility-text" font-size="9">تهوية</text>

                    <!-- صف القاعات السفلي الداخلي -->
                    <!-- معمل 4 -->
                    <g onclick="switchLab(4)" id="lab-node-4" class="cursor-pointer">
                        <rect x="300" y="600" width="105" height="85" class="svg-lab" rx="3" />
                        <text x="352" y="648" class="svg-text-title">معمل (4)</text>
                    </g>

                    <!-- معمل 6 -->
                    <g onclick="switchLab(6)" id="lab-node-6" class="cursor-pointer">
                        <rect x="410" y="600" width="105" height="85" class="svg-lab" rx="3" />
                        <text x="462" y="648" class="svg-text-title">معمل (6)</text>
                    </g>

                    <!-- معمل 10 (كيابل الألياف الضوئية) -->
                    <g onclick="switchLab(10)" id="lab-node-10" class="cursor-pointer">
                        <rect x="520" y="600" width="140" height="85" class="svg-lab" rx="3" />
                        <text x="590" y="637" class="svg-text-title">معمل (10)</text>
                        <text x="590" y="652" class="svg-text-sub">كيابل الألياف</text>
                        <text x="590" y="666" class="svg-text-sub">الضوئية</text>
                    </g>

                    <!-- ================= 4. الضلع الأيمن الخارجي ================= -->
                    <!-- مصلى -->
                    <rect x="715" y="140" width="60" height="90" class="svg-room" stroke="#059669" />
                    <text x="745" y="190" fill="#6ee7b7" font-size="10" font-weight="bold" text-anchor="middle">مصلى</text>

                    <!-- مستودع -->
                    <rect x="715" y="235" width="60" height="40" class="svg-room" />
                    <text x="745" y="260" class="svg-facility-text" font-size="9">مستودع</text>

                    <!-- نظري 1 -->
                    <rect x="715" y="280" width="60" height="100" class="svg-room" />
                    <text x="745" y="325" class="svg-facility-text">قاعة</text>
                    <text x="745" y="340" class="svg-facility-text font-bold text-slate-300">نظري 1</text>

                    <!-- مستودع -->
                    <rect x="715" y="385" width="60" height="40" class="svg-room" />
                    <text x="745" y="410" class="svg-facility-text" font-size="9">مستودع</text>

                    <!-- معمل 13 -->
                    <g onclick="switchLab(13)" id="lab-node-13" class="cursor-pointer">
                        <rect x="715" y="430" width="60" height="90" class="svg-lab" rx="3" />
                        <text x="745" y="480" class="svg-text-title">معمل (13)</text>
                    </g>

                    <!-- معمل 11 -->
                    <g onclick="switchLab(11)" id="lab-node-11" class="cursor-pointer">
                        <rect x="715" y="525" width="60" height="90" class="svg-lab" rx="3" />
                        <text x="745" y="575" class="svg-text-title">معمل (11)</text>
                    </g>

                    <!-- دورة مياه المتدربين -->
                    <rect x="715" y="620" width="60" height="60" class="svg-room" />
                    <text x="745" y="645" class="svg-facility-text" font-size="9">دورة مياه</text>
                    <text x="745" y="660" class="svg-facility-text" font-size="9">المتدربين</text>

                    <!-- درج سفلي -->
                    <g>
                        <rect x="715" y="685" width="60" height="45" fill="#1e293b" stroke="#475569" />
                        <line x1="715" y1="696" x2="775" y2="696" stroke="#64748b" />
                        <line x1="715" y1="707" x2="775" y2="707" stroke="#64748b" />
                        <line x1="715" y1="718" x2="775" y2="718" stroke="#64748b" />
                    </g>

                    <!-- ================= 5. الضلع السفلي الخارجي ================= -->
                    <!-- معمل 2 -->
                    <g onclick="switchLab(2)" id="lab-node-2" class="cursor-pointer">
                        <rect x="200" y="740" width="80" height="85" class="svg-lab" rx="4" />
                        <text x="240" y="788" class="svg-text-title">معمل (2)</text>
                    </g>

                    <!-- معمل 3 -->
                    <g onclick="switchLab(3)" id="lab-node-3" class="cursor-pointer">
                        <rect x="285" y="740" width="80" height="85" class="svg-lab" rx="4" />
                        <text x="325" y="788" class="svg-text-title">معمل (3)</text>
                    </g>

                    <!-- معمل 5 -->
                    <g onclick="switchLab(5)" id="lab-node-5" class="cursor-pointer">
                        <rect x="370" y="740" width="80" height="85" class="svg-lab" rx="4" />
                        <text x="410" y="788" class="svg-text-title">معمل (5)</text>
                    </g>

                    <!-- معمل 7 -->
                    <g onclick="switchLab(7)" id="lab-node-7" class="cursor-pointer">
                        <rect x="455" y="740" width="80" height="85" class="svg-lab" rx="4" />
                        <text x="495" y="788" class="svg-text-title">معمل (7)</text>
                    </g>

                    <!-- معمل 9 -->
                    <g onclick="switchLab(9)" id="lab-node-9" class="cursor-pointer">
                        <rect x="540" y="740" width="80" height="85" class="svg-lab" rx="4" />
                        <text x="580" y="788" class="svg-text-title">معمل (9)</text>
                    </g>

                    <!-- الكيابل النحاسية -->
                    <rect x="625" y="740" width="85" height="85" class="svg-room" />
                    <text x="667" y="778" class="svg-facility-text font-bold text-slate-200">الكيابل</text>
                    <text x="667" y="794" class="svg-facility-text font-bold text-slate-200">النحاسية</text>

                    <!-- مستودع -->
                    <rect x="715" y="740" width="60" height="85" class="svg-room" />
                    <text x="745" y="788" class="svg-facility-text">مستودع</text>

                </svg>
            </div>
        </div>

    </div>

    <!-- جدول تذاكر الصيانة الرقمي -->
    <div class="bg-slate-900/70 border border-slate-800 rounded-2xl p-5">
        <h3 class="font-bold text-sm text-white mb-4 flex items-center gap-2">
            تذاكر الأعطال ومسار الصيانة الرقمي <i class="fa-solid fa-list-check text-cyan-400"></i>
        </h3>
        <div class="overflow-x-auto">
            <table class="w-full text-right text-xs text-slate-300">
                <thead class="bg-slate-950 text-slate-400 uppercase font-semibold border-b border-slate-800">
                    <tr>
                        <th class="p-3">رقم التذكرة</th>
                        <th class="p-3">الموقع</th>
                        <th class="p-3">المُبلّغ</th>
                        <th class="p-3">النوع والتفاصيل</th>
                        <th class="p-3">الحالة الحالية</th>
                        <th class="p-3">إجراء الفني</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800/60">
                    {% for t in tickets %}
                    <tr class="hover:bg-slate-800/40">
                        <td class="p-3 font-mono font-bold text-cyan-400">#{{ t[0] }}</td>
                        <td class="p-3 font-semibold">معمل ({{ t[1] }}) - مقعد {{ t[2] }}</td>
                        <td class="p-3">{{ t[3] }}</td>
                        <td class="p-3">{{ t[4] }} - <span class="text-slate-400">{{ t[5] }}</span></td>
                        <td class="p-3">
                            {% if t[6] == 'مفتوح' %}
                            <span class="bg-red-500/10 text-red-400 border border-red-500/30 px-2 py-0.5 rounded-full font-bold">مفتوح</span>
                            {% elif t[6] == 'قيد الإصلاح' %}
                            <span class="bg-amber-500/10 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-full font-bold">قيد الإصلاح</span>
                            {% else %}
                            <span class="bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-full font-bold">تم الحل</span>
                            {% endif %}
                        </td>
                        <td class="p-3">
                            <form method="POST" action="/update_status/{{ t[0] }}" class="inline-flex gap-1.5">
                                <select name="status" onchange="this.form.submit()" class="bg-slate-950 border border-slate-700 text-[11px] rounded px-2 py-1 text-slate-300">
                                    <option value="مفتوح" {% if t[6] == 'مفتوح' %}selected{% endif %}>مفتوح</option>
                                    <option value="قيد الإصلاح" {% if t[6] == 'قيد الإصلاح' %}selected{% endif %}>قيد الإصلاح</option>
                                    <option value="تم الحل" {% if t[6] == 'تم الحل' %}selected{% endif %}>تم الحل</option>
                                </select>
                            </form>
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="6" class="text-center p-8 text-xs text-slate-500">لا توجد بلاغات مسجلة حالياً في النظام. جميع الحواسيب والمعامل تعمل بكفاءة.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        function renderSeatsGrid(labId) {
            const container = document.getElementById('seats-container');
            container.innerHTML = '';
            for (let i = 1; i <= 27; i++) {
                const seat = document.createElement('div');
                seat.className = 'bg-slate-950/80 border border-slate-800 hover:border-cyan-500/40 p-2 rounded-xl text-center flex flex-col justify-between h-14 transition';
                seat.innerHTML = `
                    <div class="flex justify-between items-center text-[10px] text-slate-500">
                        <i class="fa-solid fa-display text-[9px]"></i>
                        <span class="font-mono">#${i}</span>
                    </div>
                    <div class="text-[11px] font-bold text-slate-200">مقعد ${i}</div>
                    <div class="text-[9px] text-emerald-400 font-semibold">جاهز</div>
                `;
                container.appendChild(seat);
            }
        }

        function switchLab(num) {
            document.getElementById('active-lab-title').innerText = `توزيع مقاعد معمل (${num})`;
            // إزالة التحديد القديم
            document.querySelectorAll('.svg-lab').forEach(el => el.classList.remove('active-lab'));
            // تحديد المعمل الجديد
            const labGroup = document.getElementById(`lab-node-${num}`);
            if (labGroup) {
                const rect = labGroup.querySelector('rect');
                if (rect) rect.classList.add('active-lab');
            }
            renderSeatsGrid(num);
        }

        // تشغيل معمل 1 تلقائياً عند الفتح
        renderSeatsGrid(1);
    </script>
</body>
</html>
"""

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

    return render_template_string(
        DASHBOARD_TEMPLATE,
        tickets=tickets,
        total_tickets=total,
        active_tickets=active,
        pending_tickets=pending,
        operational_rate=op_rate
    )

@app.route('/update_status/<int:ticket_id>', methods=['POST'])
def update_status(ticket_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    new_status = request.form.get('status')
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'maintenance.db'))
    cursor = conn.cursor()
    cursor.execute('UPDATE tickets SET status = ? WHERE id = ?', (new_status, ticket_id))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
