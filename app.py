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

# --- قالب تسجيل الدخول ---
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تسجيل الدخول | نظام إدارة صيانة المعامل</title>
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
            <h2 class="text-xl font-black text-white">نظام صيانة حواسيب المعامل</h2>
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
                <div class="relative">
                    <span class="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-slate-500"><i class="fa-solid fa-user"></i></span>
                    <input type="text" name="username" required placeholder="admin" class="w-full bg-slate-950/80 border border-slate-700 focus:border-cyan-400 rounded-xl py-2.5 pr-10 pl-3 text-xs text-white focus:outline-none transition">
                </div>
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-300 mb-1">كلمة المرور</label>
                <div class="relative">
                    <span class="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-slate-500"><i class="fa-solid fa-lock"></i></span>
                    <input type="password" name="password" required placeholder="123" class="w-full bg-slate-950/80 border border-slate-700 focus:border-cyan-400 rounded-xl py-2.5 pr-10 pl-3 text-xs text-white focus:outline-none transition">
                </div>
            </div>
            <button type="submit" class="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold rounded-xl text-xs shadow-lg shadow-cyan-500/20 transition duration-200 mt-2">
                دخول إلى لوحة التحكم
            </button>
        </form>
    </div>
</body>
</html>
"""

# --- قالب لوحة التحكم بالمخطط المعماري الواقعي ---
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة التحكم والعمليات | صيانة المعامل الذكية</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Tajawal', sans-serif; }
        .blueprint-canvas {
            background-color: #070d1e;
            background-image: 
                radial-gradient(rgba(6, 182, 212, 0.12) 1px, transparent 1px),
                linear-gradient(rgba(14, 165, 233, 0.04) 1px, transparent 1px),
                linear-gradient(90deg, rgba(14, 165, 233, 0.04) 1px, transparent 1px);
            background-size: 24px 24px, 12px 12px, 12px 12px;
        }
        .lab-card {
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid rgba(6, 182, 212, 0.35);
            background: rgba(11, 23, 48, 0.75);
            cursor: pointer;
        }
        .lab-card:hover, .lab-card.active-lab {
            border-color: #22d3ee;
            background: rgba(8, 47, 73, 0.85);
            box-shadow: 0 0 15px rgba(34, 211, 238, 0.3);
            transform: translateY(-2px);
        }
        .facility-card {
            border: 1px dashed rgba(148, 163, 184, 0.25);
            background: rgba(15, 23, 42, 0.45);
            color: #64748b;
        }
    </style>
</head>
<body class="bg-slate-950 text-slate-200 min-h-screen flex flex-col">

    <!-- شريط الرأس العلوي -->
    <header class="flex justify-between items-center px-6 py-4 bg-slate-900/60 border-b border-slate-800 backdrop-blur sticky top-0 z-50">
        <div class="flex items-center gap-3">
            <a href="/logout" class="bg-red-950/40 hover:bg-red-900/60 border border-red-800/60 text-red-400 px-3 py-1.5 rounded-xl text-xs flex items-center gap-2 transition">
                <i class="fa-solid fa-power-off"></i> خروج
            </a>
            <div class="flex items-center gap-2 bg-slate-800/60 border border-slate-700/60 px-3 py-1.5 rounded-xl text-xs">
                <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span class="font-bold text-slate-200">{{ session.get('name', 'ريان المحيطيب') }} ({{ session.get('role', 'مشرف') }})</span>
            </div>
        </div>
        <div class="text-left flex items-center gap-3">
            <div>
                <h1 class="font-black text-base text-white">النظام الذكي لإدارة ومتابعة صيانة حواسيب المعامل</h1>
                <p class="text-[11px] text-cyan-400">قسم الحاسب الآلي | إشراف: أ. محمد الدوخي • إعداد: ريان المحيطيب</p>
            </div>
            <div class="w-9 h-9 rounded-xl bg-cyan-500/20 border border-cyan-400/40 flex items-center justify-center text-cyan-400 text-lg">
                <i class="fa-solid fa-microchip"></i>
            </div>
        </div>
    </header>

    <main class="flex-1 p-6 space-y-6 max-w-[1600px] mx-auto w-full">

        <!-- مؤشرات الأداء السريعة -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="bg-slate-900/60 border border-slate-800/80 p-4 rounded-2xl flex justify-between items-center">
                <div class="text-right">
                    <span class="text-xs text-slate-400 font-medium">إجمالي بلاغات المعامل</span>
                    <div class="text-2xl font-black text-white mt-1">{{ total_tickets }}</div>
                </div>
                <div class="w-10 h-10 rounded-xl bg-cyan-950/60 border border-cyan-500/30 flex items-center justify-center text-cyan-400"><i class="fa-solid fa-clipboard-list"></i></div>
            </div>
            <div class="bg-slate-900/60 border border-slate-800/80 p-4 rounded-2xl flex justify-between items-center">
                <div class="text-right">
                    <span class="text-xs text-slate-400 font-medium">أعطال نشطة حالياً</span>
                    <div class="text-2xl font-black text-red-400 mt-1">{{ active_tickets }}</div>
                </div>
                <div class="w-10 h-10 rounded-xl bg-red-950/60 border border-red-500/30 flex items-center justify-center text-red-400"><i class="fa-solid fa-triangle-exclamation"></i></div>
            </div>
            <div class="bg-slate-900/60 border border-slate-800/80 p-4 rounded-2xl flex justify-between items-center">
                <div class="text-right">
                    <span class="text-xs text-slate-400 font-medium">قيد الفحص والإصلاح</span>
                    <div class="text-2xl font-black text-amber-400 mt-1">{{ pending_tickets }}</div>
                </div>
                <div class="w-10 h-10 rounded-xl bg-amber-950/60 border border-amber-500/30 flex items-center justify-center text-amber-400"><i class="fa-solid fa-screwdriver-wrench"></i></div>
            </div>
            <div class="bg-slate-900/60 border border-slate-800/80 p-4 rounded-2xl flex justify-between items-center">
                <div class="text-right">
                    <span class="text-xs text-slate-400 font-medium">الجاهزية التشغيلية</span>
                    <div class="text-2xl font-black text-emerald-400 mt-1">{{ operational_rate }}%</div>
                </div>
                <div class="w-10 h-10 rounded-xl bg-emerald-950/60 border border-emerald-500/30 flex items-center justify-center text-emerald-400"><i class="fa-solid fa-shield-halved"></i></div>
            </div>
        </div>

        <!-- شبكة المقاعد + المخطط الهندسي التفاعلي -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">

            <!-- مقاعد المعمل الـ 27 -->
            <div class="lg:col-span-4 bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 flex flex-col justify-between">
                <div>
                    <div class="flex justify-between items-center mb-4">
                        <button onclick="window.print()" class="bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 text-xs px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition">
                            <i class="fa-solid fa-print"></i> طباعة QR
                        </button>
                        <div class="text-right">
                            <h2 class="font-bold text-sm text-white flex items-center gap-2">
                                <span id="active-lab-title">توزيع مقاعد معمل (1)</span>
                                <i class="fa-solid fa-network-wired text-cyan-400"></i>
                            </h2>
                            <span class="text-[10px] text-slate-400">إجمالي 27 مقعد تدريبي + منصة المدرب</span>
                        </div>
                    </div>

                    <div class="p-2 mb-3 bg-cyan-950/30 border border-cyan-800/40 rounded-xl text-center text-xs text-cyan-300 font-semibold flex items-center justify-center gap-2">
                        <i class="fa-solid fa-chalkboard-user"></i> منصة جهاز المدرب والشاشة الرئيسية
                    </div>

                    <div class="grid grid-cols-3 gap-2" id="seats-container"></div>
                </div>
            </div>

            <!-- المخطط المعماري الكامل للقسم (المطابق للورقة) -->
            <div class="lg:col-span-8 bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 flex flex-col">
                <div class="flex justify-between items-center mb-4">
                    <span class="text-[11px] text-slate-400">اضغط على أي معمل لعرض شبكة مقاعده الـ 27 المباشرة</span>
                    <h2 class="font-bold text-sm text-white flex items-center gap-2">
                        المخطط المعماري لجناح قسم الحاسب (رادار الطابق الواقعي) <i class="fa-solid fa-map-location-dot text-cyan-400"></i>
                    </h2>
                </div>

                <!-- إطار المخطط الهندسي -->
                <div class="blueprint-canvas rounded-xl p-4 border border-cyan-950 flex-1 flex flex-col justify-between gap-2 overflow-x-auto min-w-[700px]">

                    <!-- 1. الحلقة الخارجية: الضلع العلوي (الشمالي) -->
                    <div class="grid grid-cols-7 gap-1.5 text-center text-xs">
                        <div class="facility-card p-2 rounded-lg">شبكات الحاسب</div>
                        <div onclick="switchLab(26)" id="lab-node-26" class="lab-card p-2 rounded-lg"><div class="font-bold text-cyan-300">معمل (26)</div><div class="text-[9px] text-emerald-400 font-semibold">✓ سليم</div></div>
                        <div class="facility-card p-2 rounded-lg">أساسيات الكهرباء</div>
                        <div onclick="switchLab(24)" id="lab-node-24" class="lab-card p-2 rounded-lg"><div class="font-bold text-cyan-300">معمل (24)</div><div class="text-[9px] text-emerald-400 font-semibold">✓ سليم</div></div>
                        <div class="facility-card p-2 rounded-lg">مستودع</div>
                        <div class="facility-card p-2 rounded-lg">أساسيات الإلكترونيات</div>
                        <div class="facility-card p-2 rounded-lg text-amber-300"><i class="fa-solid fa-stairs"></i> درج</div>
                    </div>

                    <!-- 2. الجزء الأوسط: الضلع الأيسر + الفناء المفتوح + الضلع الأيمن -->
                    <div class="grid grid-cols-12 gap-2 my-1">
                        <!-- الضلع الأيسر الخارجي (المدخل ومعمل 1) -->
                        <div class="col-span-2 flex flex-col gap-1.5 text-center text-xs">
                            <div class="facility-card p-1.5 rounded">مستودع</div>
                            <div class="facility-card p-1.5 rounded"><i class="fa-solid fa-restroom"></i> دورة مياه</div>
                            <div class="facility-card p-1.5 rounded text-amber-300"><i class="fa-solid fa-stairs"></i> درج</div>
                            <div class="facility-card p-1.5 rounded">منسق رايات</div>
                            <div onclick="switchLab(1)" id="lab-node-1" class="lab-card active-lab p-2.5 rounded-lg flex-1 flex flex-col justify-center"><div class="font-bold text-cyan-300">معمل (1)</div><div class="text-[9px] text-emerald-400 font-semibold">✓ سليم</div></div>
                            <div class="facility-card p-2 rounded border-emerald-500/40 text-emerald-400 font-bold text-[11px]"><i class="fa-solid fa-door-open"></i> المدخل</div>
                        </div>

                        <!-- الحلقة الداخلية المحيطة بالفناء المفتوح -->
                        <div class="col-span-8 border border-cyan-900/60 rounded-xl p-2.5 bg-slate-950/70 flex flex-col justify-between gap-2">
                            <!-- علوي داخلي -->
                            <div class="grid grid-cols-4 gap-1.5 text-center text-xs">
                                <div onclick="switchLab(27)" id="lab-node-27" class="lab-card p-1.5 rounded"><div class="font-bold text-cyan-300">معمل (27)</div><div class="text-[9px] text-emerald-400">✓ سليم</div></div>
                                <div class="facility-card p-1.5 rounded text-amber-300/90 font-medium">غرفة صيانة</div>
                                <div onclick="switchLab(23)" id="lab-node-23" class="lab-card p-1.5 rounded"><div class="font-bold text-cyan-300">معمل (23)</div><div class="text-[9px] text-emerald-400">✓ سليم</div></div>
                                <div onclick="switchLab(22)" id="lab-node-22" class="lab-card p-1.5 rounded"><div class="font-bold text-cyan-300">معمل (22)</div><div class="text-[9px] text-emerald-400">✓ سليم</div></div>
                            </div>

                            <!-- وسط الفناء -->
                            <div class="grid grid-cols-12 gap-1.5 items-stretch py-1">
                                <div class="col-span-3 flex flex-col gap-1 text-[10px] text-center">
                                    <div class="facility-card p-1 rounded">تهوية</div>
                                    <div class="facility-card p-1 rounded">التدريب الإلكتروني</div>
                                    <div class="facility-card p-1 rounded font-bold text-slate-300">مكتب رئيس القسم</div>
                                    <div class="facility-card p-1 rounded">شؤون المتدربين</div>
                                    <div class="facility-card p-1 rounded">تهوية</div>
                                </div>
                                <div class="col-span-6 rounded-lg border border-dashed border-cyan-800/40 bg-slate-900/40 flex flex-col items-center justify-center text-center p-3">
                                    <span class="text-xs font-bold text-slate-300">الفناء الأوسط والممر الرئيسي</span>
                                    <span class="text-[10px] text-slate-500 font-mono">COURTYARD</span>
                                </div>
                                <div class="col-span-3 flex flex-col gap-1 text-[10px] text-center">
                                    <div class="facility-card p-1 rounded">تهوية</div>
                                    <div class="grid grid-cols-3 gap-0.5"><div class="facility-card p-0.5 rounded text-[8px]">م 3</div><div class="facility-card p-0.5 rounded text-[8px]">م 2</div><div class="facility-card p-0.5 rounded text-[8px]">م 1</div></div>
                                    <div onclick="switchLab(14)" id="lab-node-14" class="lab-card p-1 rounded"><div class="font-bold text-cyan-300 text-[10px]">معمل (14)</div><div class="text-[8px] text-emerald-400">✓ سليم</div></div>
                                    <div onclick="switchLab(12)" id="lab-node-12" class="lab-card p-1 rounded"><div class="font-bold text-cyan-300 text-[10px]">معمل (12)</div><div class="text-[8px] text-emerald-400">✓ سليم</div></div>
                                    <div class="facility-card p-1 rounded">تهوية</div>
                                </div>
                            </div>

                            <!-- سفلي داخلي -->
                            <div class="grid grid-cols-3 gap-1.5 text-center text-xs">
                                <div onclick="switchLab(4)" id="lab-node-4" class="lab-card p-1.5 rounded"><div class="font-bold text-cyan-300">معمل (4)</div><div class="text-[9px] text-emerald-400">✓ سليم</div></div>
                                <div onclick="switchLab(6)" id="lab-node-6" class="lab-card p-1.5 rounded"><div class="font-bold text-cyan-300">معمل (6)</div><div class="text-[9px] text-emerald-400">✓ سليم</div></div>
                                <div onclick="switchLab(10)" id="lab-node-10" class="lab-card p-1.5 rounded"><div class="font-bold text-cyan-300">معمل (10)</div><div class="text-[9px] text-cyan-400">كيابل الألياف الضوئية</div></div>
                            </div>
                        </div>

                        <!-- الضلع الأيمن الخارجي -->
                        <div class="col-span-2 flex flex-col gap-1.5 text-center text-xs">
                            <div class="facility-card p-1.5 rounded text-emerald-300"><i class="fa-solid fa-mosque"></i> مصلى</div>
                            <div class="facility-card p-1 rounded text-[10px]">مستودع</div>
                            <div class="facility-card p-1.5 rounded">قاعة نظري 1</div>
                            <div class="facility-card p-1 rounded text-[10px]">مستودع</div>
                            <div onclick="switchLab(13)" id="lab-node-13" class="lab-card p-1.5 rounded"><div class="font-bold text-cyan-300">معمل (13)</div><div class="text-[9px] text-emerald-400">✓ سليم</div></div>
                            <div onclick="switchLab(11)" id="lab-node-11" class="lab-card p-1.5 rounded"><div class="font-bold text-cyan-300">معمل (11)</div><div class="text-[9px] text-emerald-400">✓ سليم</div></div>
                            <div class="facility-card p-1.5 rounded"><i class="fa-solid fa-restroom"></i> دورة مياه</div>
                            <div class="facility-card p-1 rounded text-amber-300 text-[10px]"><i class="fa-solid fa-stairs"></i> درج سفلي</div>
                        </div>
                    </div>

                    <!-- 3. الحلقة الخارجية: الضلع السفلي (الجنوبي) -->
                    <div class="grid grid-cols-7 gap-1.5 text-center text-xs">
                        <div onclick="switchLab(2)" id="lab-node-2" class="lab-card p-2 rounded-lg"><div class="font-bold text-cyan-300">معمل (2)</div><div class="text-[9px] text-emerald-400 font-semibold">✓ سليم</div></div>
                        <div onclick="switchLab(3)" id="lab-node-3" class="lab-card p-2 rounded-lg"><div class="font-bold text-cyan-300">معمل (3)</div><div class="text-[9px] text-emerald-400 font-semibold">✓ سليم</div></div>
                        <div onclick="switchLab(5)" id="lab-node-5" class="lab-card p-2 rounded-lg"><div class="font-bold text-cyan-300">معمل (5)</div><div class="text-[9px] text-emerald-400 font-semibold">✓ سليم</div></div>
                        <div onclick="switchLab(7)" id="lab-node-7" class="lab-card p-2 rounded-lg"><div class="font-bold text-cyan-300">معمل (7)</div><div class="text-[9px] text-emerald-400 font-semibold">✓ سليم</div></div>
                        <div onclick="switchLab(9)" id="lab-node-9" class="lab-card p-2 rounded-lg"><div class="font-bold text-cyan-300">معمل (9)</div><div class="text-[9px] text-emerald-400 font-semibold">✓ سليم</div></div>
                        <div class="facility-card p-2 rounded-lg">الكيابل النحاسية</div>
                        <div class="facility-card p-2 rounded-lg">مستودع</div>
                    </div>

                </div>
            </div>

        </div>

        <!-- جدول تذاكر الصيانة الرقمي -->
        <div class="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5">
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

    </main>

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
            document.querySelectorAll('.lab-card').forEach(el => el.classList.remove('active-lab'));
            const node = document.getElementById(`lab-node-${num}`);
            if (node) node.classList.add('active-lab');
            renderSeatsGrid(num);
        }

        renderSeatsGrid(1);
    </script>
</body>
</html>
"""

# --- المسارات والوظائف (Routes) ---

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
