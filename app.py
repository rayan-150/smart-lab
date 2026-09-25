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

# --- لوحة التحكم بمخطط الورقة المعماري الدقيق ---
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
        body { font-family: 'Tajawal', sans-serif; background-color: #060913; color: #e2e8f0; }
        .blueprint-canvas {
            background-color: #080e1e;
            background-image: 
                radial-gradient(rgba(14, 165, 233, 0.15) 1px, transparent 1px),
                linear-gradient(rgba(14, 165, 233, 0.05) 1px, transparent 1px),
                linear-gradient(90deg, rgba(14, 165, 233, 0.05) 1px, transparent 1px);
            background-size: 28px 28px, 14px 14px, 14px 14px;
        }
        .arch-room {
            border: 1px solid rgba(148, 163, 184, 0.3);
            background: rgba(15, 23, 42, 0.65);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            border-radius: 6px;
            transition: all 0.2s ease;
        }
        .arch-lab {
            border: 1.5px solid rgba(6, 182, 212, 0.5);
            background: rgba(8, 47, 73, 0.45);
            cursor: pointer;
        }
        .arch-lab:hover, .arch-lab.active-lab {
            border-color: #22d3ee;
            background: rgba(14, 116, 144, 0.65);
            box-shadow: 0 0 12px rgba(34, 211, 238, 0.4);
            transform: scale(1.02);
        }
        .arch-stairs {
            background: repeating-linear-gradient(45deg, #1e293b, #1e293b 4px, #334155 4px, #334155 8px);
            border-color: #f59e0b;
            color: #fbbf24;
        }
    </style>
</head>
<body class="min-h-screen flex flex-col p-4 md:p-6 space-y-6">

    <!-- شريط الرأس -->
    <header class="flex justify-between items-center px-6 py-4 bg-slate-900/70 border border-slate-800 rounded-2xl backdrop-blur">
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
        <div class="bg-slate-900/60 border border-slate-800/80 p-4 rounded-2xl flex justify-between items-center">
            <div>
                <span class="text-xs text-slate-400">إجمالي البلاغات</span>
                <div class="text-2xl font-black text-white mt-1">{{ total_tickets }}</div>
            </div>
            <i class="fa-solid fa-clipboard-list text-cyan-400 text-2xl"></i>
        </div>
        <div class="bg-slate-900/60 border border-slate-800/80 p-4 rounded-2xl flex justify-between items-center">
            <div>
                <span class="text-xs text-slate-400">أعطال نشطة</span>
                <div class="text-2xl font-black text-red-400 mt-1">{{ active_tickets }}</div>
            </div>
            <i class="fa-solid fa-triangle-exclamation text-red-400 text-2xl"></i>
        </div>
        <div class="bg-slate-900/60 border border-slate-800/80 p-4 rounded-2xl flex justify-between items-center">
            <div>
                <span class="text-xs text-slate-400">قيد الإصلاح</span>
                <div class="text-2xl font-black text-amber-400 mt-1">{{ pending_tickets }}</div>
            </div>
            <i class="fa-solid fa-screwdriver-wrench text-amber-400 text-2xl"></i>
        </div>
        <div class="bg-slate-900/60 border border-slate-800/80 p-4 rounded-2xl flex justify-between items-center">
            <div>
                <span class="text-xs text-slate-400">الجاهزية التشغيلية</span>
                <div class="text-2xl font-black text-emerald-400 mt-1">{{ operational_rate }}%</div>
            </div>
            <i class="fa-solid fa-shield-halved text-emerald-400 text-2xl"></i>
        </div>
    </div>

    <!-- شبكة المقاعد + المخطط الهندسي المطابق للورقة -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">

        <!-- لوحة المقاعد الـ 27 للمعمل النشط (اليسار) -->
        <div class="lg:col-span-4 bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 flex flex-col justify-between">
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

                <div class="p-2 mb-3 bg-cyan-950/30 border border-cyan-800/40 rounded-xl text-center text-xs text-cyan-300 font-semibold flex items-center justify-center gap-2">
                    <i class="fa-solid fa-chalkboard-user"></i> منصة جهاز المدرب والشاشة الرئيسية
                </div>

                <div class="grid grid-cols-3 gap-2" id="seats-container"></div>
            </div>
        </div>

        <!-- المخطط المعماري الكامل للقسم (المطابق لورقة المعهد تماماً) -->
        <div class="lg:col-span-8 bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 flex flex-col">
            <div class="flex justify-between items-center mb-3">
                <span class="text-[11px] text-slate-400">اضغط على أي معمل بالخريطة لتحديد مقاعده</span>
                <h2 class="font-bold text-sm text-white flex items-center gap-2">
                    المخطط المعماري لجناح قسم الحاسب (مطابق للرسم الهندسي) <i class="fa-solid fa-compass-drafting text-cyan-400"></i>
                </h2>
            </div>

            <!-- لوحة المخطط الهندسي -->
            <div class="blueprint-canvas rounded-xl p-4 border border-cyan-950/80 overflow-x-auto min-w-[760px] flex flex-col gap-2">

                <!-- 1. المحيط الخارجي: الضلع العلوي (الشمالي) -->
                <div class="grid grid-cols-7 gap-1.5 h-16">
                    <div class="arch-room text-xs text-slate-400">مستودع</div>
                    <div onclick="switchLab(26)" id="lab-node-26" class="arch-room arch-lab"><span class="font-bold text-cyan-300 text-xs">معمل (26)</span><span class="text-[9px] text-slate-400">الحوسبة</span></div>
                    <div class="arch-room text-xs text-slate-300">شبكات الحاسب</div>
                    <div onclick="switchLab(24)" id="lab-node-24" class="arch-room arch-lab"><span class="font-bold text-cyan-300 text-xs">معمل (24)</span><span class="text-[9px] text-slate-400">أساسيات</span></div>
                    <div class="arch-room text-xs text-slate-400">مستودع</div>
                    <div class="arch-room text-xs text-slate-300 leading-tight">أساسيات الإلكترونيات</div>
                    <div class="arch-room arch-stairs text-xs font-bold"><i class="fa-solid fa-stairs mb-0.5"></i> درج</div>
                </div>

                <!-- 2. الجزء الأوسط المزدوج -->
                <div class="grid grid-cols-12 gap-2 min-h-[360px]">

                    <!-- الضلع الأيسر الخارجي (الواجهة والمدخل الرئيسي كما بالورقة) -->
                    <div class="col-span-2 flex flex-col gap-1.5">
                        <div class="arch-room h-12 text-xs text-slate-400">مستودع</div>
                        <div class="arch-room h-12 text-xs text-slate-300"><i class="fa-solid fa-restroom text-[10px] mb-0.5"></i>دورة مياه</div>
                        <div class="arch-room arch-stairs h-12 text-xs font-bold"><i class="fa-solid fa-stairs mb-0.5"></i> درج</div>
                        <div class="arch-room flex-1 text-xs border-emerald-500/50 bg-emerald-950/20 text-emerald-300 font-bold leading-tight">
                            <i class="fa-solid fa-door-open text-base mb-1"></i>المدخل الرئيسي المزدوج
                        </div>
                        <div class="arch-room h-14 text-xs font-semibold text-slate-200">منسق رايات</div>
                        <div onclick="switchLab(1)" id="lab-node-1" class="arch-room arch-lab active-lab h-16"><span class="font-bold text-cyan-300 text-xs">معمل (1)</span><span class="text-[9px] text-emerald-400 font-semibold">جاهز</span></div>
                    </div>

                    <!-- الحلقة الداخلية (تطل على الفناء الأوسط المفتوح) -->
                    <div class="col-span-8 border border-cyan-900/60 rounded-xl p-2.5 bg-slate-950/70 flex flex-col justify-between gap-1.5">

                        <!-- الضلع العلوي الداخلي -->
                        <div class="grid grid-cols-4 gap-1.5 h-14">
                            <div onclick="switchLab(27)" id="lab-node-27" class="arch-room arch-lab"><span class="font-bold text-cyan-300 text-xs">معمل (27)</span></div>
                            <div class="arch-room text-xs text-amber-300 font-medium">غرفة صيانة</div>
                            <div onclick="switchLab(23)" id="lab-node-23" class="arch-room arch-lab"><span class="font-bold text-cyan-300 text-xs">معمل (23)</span></div>
                            <div onclick="switchLab(22)" id="lab-node-22" class="arch-room arch-lab"><span class="font-bold text-cyan-300 text-xs">معمل (22)</span></div>
                        </div>

                        <!-- وسط الفناء -->
                        <div class="grid grid-cols-12 gap-1.5 flex-1 items-stretch py-1">
                            <!-- الجدار الأيسر الداخلي -->
                            <div class="col-span-3 flex flex-col gap-1 text-[10px]">
                                <div class="arch-room p-1 text-slate-500">تهوية</div>
                                <div class="arch-room p-1.5 text-slate-300">مكتب التدريب الإلكتروني</div>
                                <div class="arch-room p-1.5 font-bold text-cyan-300 border-cyan-700/50">مكتب رئيس القسم</div>
                                <div class="arch-room p-1.5 text-slate-300">شؤون المتدربين</div>
                                <div class="arch-room p-1 text-slate-500">تهوية</div>
                            </div>

                            <!-- بهو الفناء الأوسط (Courtyard) -->
                            <div class="col-span-6 rounded-lg border border-dashed border-cyan-800/40 bg-slate-900/40 flex flex-col items-center justify-center text-center p-2">
                                <i class="fa-solid fa-tree text-emerald-500/30 text-2xl mb-1"></i>
                                <span class="text-xs font-bold text-slate-300">الفناء الأوسط والممر المفتوح</span>
                                <span class="text-[9px] text-slate-500 font-mono tracking-widest">COURTYARD</span>
                            </div>

                            <!-- الجدار الأيمن الداخلي -->
                            <div class="col-span-3 flex flex-col gap-1 text-[10px]">
                                <div class="arch-room p-1 text-slate-500">تهوية</div>
                                <div class="grid grid-cols-3 gap-0.5"><div class="arch-room p-0.5 text-[8px]">م 3</div><div class="arch-room p-0.5 text-[8px]">م 2</div><div class="arch-room p-0.5 text-[8px]">م 1</div></div>
                                <div onclick="switchLab(14)" id="lab-node-14" class="arch-room arch-lab p-1"><span class="font-bold text-cyan-300 text-[10px]">معمل (14)</span></div>
                                <div onclick="switchLab(12)" id="lab-node-12" class="arch-room arch-lab p-1"><span class="font-bold text-cyan-300 text-[10px]">معمل (12)</span></div>
                                <div class="arch-room p-1 text-slate-500">تهوية</div>
                            </div>
                        </div>

                        <!-- الضلع السفلي الداخلي -->
                        <div class="grid grid-cols-3 gap-1.5 h-14">
                            <div onclick="switchLab(4)" id="lab-node-4" class="arch-room arch-lab"><span class="font-bold text-cyan-300 text-xs">معمل (4)</span></div>
                            <div onclick="switchLab(6)" id="lab-node-6" class="arch-room arch-lab"><span class="font-bold text-cyan-300 text-xs">معمل (6)</span></div>
                            <div onclick="switchLab(10)" id="lab-node-10" class="arch-room arch-lab border-cyan-400"><span class="font-bold text-cyan-300 text-xs">معمل (10)</span><span class="text-[9px] text-cyan-400">ألياف ضوئية</span></div>
                        </div>

                    </div>

                    <!-- الضلع الأيمن الخارجي (الشرقي كما بالورقة) -->
                    <div class="col-span-2 flex flex-col gap-1.5">
                        <div class="arch-room h-12 text-xs font-semibold text-emerald-300"><i class="fa-solid fa-mosque mb-0.5"></i> مصلى</div>
                        <div class="arch-room h-8 text-[10px] text-slate-400">مستودع</div>
                        <div class="arch-room h-12 text-xs text-slate-200">قاعة نظري (1)</div>
                        <div class="arch-room h-8 text-[10px] text-slate-400">مستودع</div>
                        <div onclick="switchLab(13)" id="lab-node-13" class="arch-room arch-lab h-12"><span class="font-bold text-cyan-300 text-xs">معمل (13)</span></div>
                        <div onclick="switchLab(11)" id="lab-node-11" class="arch-room arch-lab h-12"><span class="font-bold text-cyan-300 text-xs">معمل (11)</span></div>
                        <div class="arch-room h-10 text-xs text-slate-300"><i class="fa-solid fa-restroom text-[10px] mb-0.5"></i>دورة مياه</div>
                        <div class="arch-room arch-stairs h-10 text-xs font-bold"><i class="fa-solid fa-stairs mb-0.5"></i> درج سفلي</div>
                    </div>

                </div>

                <!-- 3. المحيط الخارجي: الضلع السفلي (الجنوبي) -->
                <div class="grid grid-cols-7 gap-1.5 h-16">
                    <div onclick="switchLab(2)" id="lab-node-2" class="arch-room arch-lab"><span class="font-bold text-cyan-300 text-xs">معمل (2)</span></div>
                    <div onclick="switchLab(3)" id="lab-node-3" class="arch-room arch-lab"><span class="font-bold text-cyan-300 text-xs">معمل (3)</span></div>
                    <div onclick="switchLab(5)" id="lab-node-5" class="arch-room arch-lab"><span class="font-bold text-cyan-300 text-xs">معمل (5)</span></div>
                    <div onclick="switchLab(7)" id="lab-node-7" class="arch-room arch-lab"><span class="font-bold text-cyan-300 text-xs">معمل (7)</span></div>
                    <div onclick="switchLab(9)" id="lab-node-9" class="arch-room arch-lab"><span class="font-bold text-cyan-300 text-xs">معمل (9)</span></div>
                    <div class="arch-room text-xs text-slate-200 font-medium">الكيابل النحاسية</div>
                    <div class="arch-room text-xs text-slate-400">مستودع</div>
                </div>

            </div>
        </div>

    </div>

    <!-- جدول تذاكر الصيانة -->
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
            document.querySelectorAll('.arch-lab').forEach(el => el.classList.remove('active-lab'));
            const node = document.getElementById(`lab-node-${num}`);
            if (node) node.classList.add('active-lab');
            renderSeatsGrid(num);
        }

        renderSeatsGrid(1);
    </script>
</body>
</html>
"""

# --- المسارات البرمجية (Routes) ---

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
