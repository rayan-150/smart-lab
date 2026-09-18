import os
import sqlite3
from flask import Flask, render_template_string, request, redirect, url_for, session

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = "lab_maintenance_smart_system_secure_key_2026"

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
            status TEXT DEFAULT 'جديد',
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

# --- قوالب الواجهات الاحترافية ---

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>تسجيل الدخول | النظام الذكي لإدارة صيانة المعامل</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Tajawal', sans-serif; }
    .neon-border { box-shadow: 0 0 25px rgba(6, 182, 212, 0.25); }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
  <div class="absolute -top-40 -right-40 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>
  <div class="absolute -bottom-40 -left-40 w-96 h-96 bg-blue-600/10 rounded-full blur-3xl pointer-events-none"></div>

  <div class="w-full max-w-md bg-slate-900/90 border border-slate-800 rounded-3xl p-8 backdrop-blur-xl neon-border relative z-10">
    <div class="text-center mb-8">
      <div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 text-3xl mb-4">
        <i class="fa-solid fa-microchip"></i>
      </div>
      <h1 class="text-2xl font-extrabold text-white tracking-wide">منصة صيانة المعامل الذكية</h1>
      <p class="text-xs text-cyan-400/90 font-medium mt-1">مبادرة نوعية | قسم الحاسب الآلي</p>
    </div>

    {% if error %}
    <div class="mb-5 p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-400 text-xs flex items-center gap-2">
      <i class="fa-solid fa-circle-exclamation text-sm"></i>
      <span>{{ error }}</span>
    </div>
    {% endif %}

    <form method="POST" class="space-y-4">
      <div>
        <label class="block text-xs font-semibold text-slate-300 mb-1.5">اسم المستخدم</label>
        <div class="relative">
          <span class="absolute inset-y-0 right-0 flex items-center pr-3.5 text-slate-500"><i class="fa-regular fa-user"></i></span>
          <input type="text" name="username" value="admin" required class="w-full bg-slate-950/60 border border-slate-700/80 rounded-xl py-2.5 pr-10 pl-4 text-sm text-white focus:outline-none focus:border-cyan-400 transition">
        </div>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-300 mb-1.5">كلمة المرور</label>
        <div class="relative">
          <span class="absolute inset-y-0 right-0 flex items-center pr-3.5 text-slate-500"><i class="fa-solid fa-lock"></i></span>
          <input type="password" name="password" value="123" required class="w-full bg-slate-950/60 border border-slate-700/80 rounded-xl py-2.5 pr-10 pl-4 text-sm text-white focus:outline-none focus:border-cyan-400 transition">
        </div>
      </div>

      <button type="submit" class="w-full mt-2 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-bold py-3 rounded-xl transition duration-200 shadow-lg shadow-cyan-500/20 text-sm flex items-center justify-center gap-2">
        <i class="fa-solid fa-arrow-right-to-bracket"></i>
        <span>تسجيل الدخول للنظام</span>
      </button>
    </form>

    <div class="mt-6 pt-5 border-t border-slate-800 text-center">
      <span class="text-xs text-slate-500">الحسابات التجريبية المتاحة:</span>
      <div class="flex justify-center gap-3 mt-2 text-[11px] text-cyan-400/90 font-mono">
        <span>admin : 123</span>
        <span>•</span>
        <span>tech : 123</span>
      </div>
    </div>
  </div>
</body>
</html>
"""

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
    .pulse-danger {
      animation: pulse-ring 1.8s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }
    @keyframes pulse-ring {
      0%, 100% { opacity: 1; transform: scale(1); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
      50% { opacity: 0.85; transform: scale(1.02); box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
    }
    .custom-scroll::-webkit-scrollbar { width: 5px; height: 5px; }
    .custom-scroll::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
  </style>
</head>
<body class="bg-slate-950 text-slate-200 min-h-screen flex flex-col">

  <!-- الشريط العلوي الفخم -->
  <header class="bg-slate-900/80 border-b border-slate-800 sticky top-0 z-50 backdrop-blur-md px-6 py-3 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center text-white text-lg shadow-md shadow-cyan-500/20">
        <i class="fa-solid fa-microchip"></i>
      </div>
      <div>
        <h1 class="text-base font-bold text-white leading-tight">النظام الذكي لإدارة ومتابعة صيانة حواسيب المعامل</h1>
        <p class="text-[11px] text-cyan-400 font-medium">قسم الحاسب الآلي | إشراف: أ. محمد الدوخي • إعداد: ريان المحيطيب</p>
      </div>
    </div>

    <div class="flex items-center gap-4">
      <div class="flex items-center gap-2.5 bg-slate-800/80 border border-slate-700/60 px-3.5 py-1.5 rounded-full text-xs">
        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
        <span class="text-slate-300 font-medium">{{ user.name }} ({{ user.role }})</span>
      </div>
      <a href="/logout" class="bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 px-3 py-1.5 rounded-xl text-xs font-semibold transition flex items-center gap-1.5">
        <i class="fa-solid fa-power-off"></i>
        <span>خروج</span>
      </a>
    </div>
  </header>

  <main class="flex-1 p-6 space-y-6 max-w-[1700px] w-full mx-auto">

    <!-- كروت المؤشرات الحيوية KPI -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-slate-900/90 border border-slate-800/80 rounded-2xl p-4 flex items-center justify-between">
        <div>
          <span class="text-xs text-slate-400">إجمالي بلاغات المعامل</span>
          <h2 class="text-2xl font-black text-white mt-1">{{ stats.total }}</h2>
        </div>
        <div class="w-12 h-12 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 flex items-center justify-center text-xl">
          <i class="fa-solid fa-clipboard-list"></i>
        </div>
      </div>

      <div class="bg-slate-900/90 border border-rose-500/20 rounded-2xl p-4 flex items-center justify-between">
        <div>
          <span class="text-xs text-rose-400">أعطال نشطة حالياً</span>
          <h2 class="text-2xl font-black text-rose-400 mt-1">{{ stats.active }}</h2>
        </div>
        <div class="w-12 h-12 rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/20 flex items-center justify-center text-xl">
          <i class="fa-solid fa-triangle-exclamation"></i>
        </div>
      </div>

      <div class="bg-slate-900/90 border border-amber-500/20 rounded-2xl p-4 flex items-center justify-between">
        <div>
          <span class="text-xs text-amber-400">قيد الفحص والإصلاح</span>
          <h2 class="text-2xl font-black text-amber-400 mt-1">{{ stats.in_progress }}</h2>
        </div>
        <div class="w-12 h-12 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center justify-center text-xl">
          <i class="fa-solid fa-screwdriver-wrench"></i>
        </div>
      </div>

      <div class="bg-slate-900/90 border border-emerald-500/20 rounded-2xl p-4 flex items-center justify-between">
        <div>
          <span class="text-xs text-emerald-400">الجاهزية التشغيلية</span>
          <h2 class="text-2xl font-black text-emerald-400 mt-1">{{ stats.readiness }}%</h2>
        </div>
        <div class="w-12 h-12 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center justify-center text-xl">
          <i class="fa-solid fa-shield-halved"></i>
        </div>
      </div>
    </div>

    <!-- المخطط المعماري وخريطة المقاعد التفاعلية -->
    <div class="grid grid-cols-1 xl:grid-cols-3 gap-6">

      <!-- المخطط المعماري الكامل للقسم -->
      <div class="xl:col-span-2 bg-slate-900/90 border border-slate-800 rounded-3xl p-5 shadow-xl flex flex-col">
        <div class="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
          <div class="flex items-center gap-2">
            <i class="fa-regular fa-map text-cyan-400 text-lg"></i>
            <h2 class="font-bold text-base text-white">المخطط المعماري لجناح قسم الحاسب (رادار الطابق)</h2>
          </div>
          <span class="text-xs text-slate-400">اضغط على أي معمل لعرض شبكة مقاعده الـ 27</span>
        </div>

        <!-- تمثيل هندسي لجناح القسم مطابق للمخطط الحقيقي -->
        <div class="flex-1 bg-slate-950 border border-slate-800/80 rounded-2xl p-4 flex flex-col justify-between gap-3 text-xs">
          
          <!-- الجناح الشمالي: معمل 1 ومكاتب الإدارة والتهوية -->
          <div class="grid grid-cols-6 gap-2">
            {% for room in [
              {'name': 'معمل (1)', 'lab': 1, 'is_lab': True},
              {'name': 'منسق رايات', 'lab': 0, 'is_lab': False},
              {'name': 'شؤون المتدربين', 'lab': 0, 'is_lab': False},
              {'name': 'مكتب رئيس القسم', 'lab': 0, 'is_lab': False},
              {'name': 'التدريب الإلكتروني', 'lab': 0, 'is_lab': False},
              {'name': 'معمل (27)', 'lab': 27, 'is_lab': True}
            ] %}
              {% if room.is_lab %}
                {% set has_bug = room.lab in active_labs %}
                <a href="/dashboard?lab={{ room.lab }}" class="p-3 text-center rounded-xl border transition flex flex-col justify-center items-center gap-1 font-bold {{ 'bg-rose-500/20 border-rose-500 text-rose-300 pulse-danger' if has_bug else 'bg-slate-900 hover:bg-slate-800 border-slate-700/60 text-slate-200' }} {{ 'ring-2 ring-cyan-400' if current_lab == room.lab }}">
                  <span>{{ room.name }}</span>
                  <span class="text-[10px] {{ 'text-rose-400 font-black' if has_bug else 'text-emerald-400' }}">
                    {{ '⚠️ به عطل!' if has_bug else '✓ سليم' }}
                  </span>
                </a>
              {% else %}
                <div class="p-3 text-center rounded-xl bg-slate-900/40 border border-dashed border-slate-800 text-slate-500 flex items-center justify-center font-medium">
                  {{ room.name }}
                </div>
              {% endif %}
            {% endfor %}
          </div>

          <!-- الجناح الأوسط (الممرات والفناء الداخلي) -->
          <div class="grid grid-cols-6 gap-2 py-4">
            <!-- معامل الجناح الغربي (معامل 2, 3, 5, 7, 9) -->
            <div class="col-span-2 grid grid-cols-2 gap-2">
              {% for l in [2, 3, 5, 7, 9] %}
                {% set has_bug = l in active_labs %}
                <a href="/dashboard?lab={{ l }}" class="p-2.5 text-center rounded-xl border transition flex flex-col justify-center items-center font-bold {{ 'bg-rose-500/20 border-rose-500 text-rose-300 pulse-danger' if has_bug else 'bg-slate-900 hover:bg-slate-800 border-slate-700/60 text-slate-200' }} {{ 'ring-2 ring-cyan-400' if current_lab == l }}">
                  <span>معمل ({{ l }})</span>
                  <span class="text-[9px] {{ 'text-rose-400' if has_bug else 'text-emerald-400' }}">{{ 'عطل!' if has_bug else 'سليم' }}</span>
                </a>
              {% endfor %}
              <div class="p-2 text-center rounded-xl bg-slate-900/40 border border-dashed border-slate-800 text-slate-500 flex items-center justify-center text-[10px]">مستودع</div>
            </div>

            <!-- الفناء المفتوح الداخلي ومكاتب الوسط -->
            <div class="col-span-2 bg-slate-900/20 border border-slate-800/40 rounded-xl p-3 flex flex-col items-center justify-center text-center">
              <span class="text-slate-600 font-bold tracking-wider text-xs">الفناء والممر الرئيسي للقسم</span>
              <div class="mt-2 grid grid-cols-2 gap-1.5 w-full">
                <span class="bg-slate-900/60 border border-slate-800 py-1 px-2 rounded text-[10px] text-slate-500">معمل (4)</span>
                <span class="bg-slate-900/60 border border-slate-800 py-1 px-2 rounded text-[10px] text-slate-500">معمل (6)</span>
              </div>
            </div>

            <!-- معامل الجناح الشرقي (معامل 22, 23, 24, 26 ومستودعات) -->
            <div class="col-span-2 grid grid-cols-2 gap-2">
              {% for l in [22, 23, 24, 26] %}
                {% set has_bug = l in active_labs %}
                <a href="/dashboard?lab={{ l }}" class="p-2.5 text-center rounded-xl border transition flex flex-col justify-center items-center font-bold {{ 'bg-rose-500/20 border-rose-500 text-rose-300 pulse-danger' if has_bug else 'bg-slate-900 hover:bg-slate-800 border-slate-700/60 text-slate-200' }} {{ 'ring-2 ring-cyan-400' if current_lab == l }}">
                  <span>معمل ({{ l }})</span>
                  <span class="text-[9px] {{ 'text-rose-400' if has_bug else 'text-emerald-400' }}">{{ 'عطل!' if has_bug else 'سليم' }}</span>
                </a>
              {% endfor %}
              <div class="p-2 text-center rounded-xl bg-slate-900/40 border border-dashed border-slate-800 text-slate-500 flex items-center justify-center text-[10px]">مستودع 1</div>
              <div class="p-2 text-center rounded-xl bg-slate-900/40 border border-dashed border-slate-800 text-slate-500 flex items-center justify-center text-[10px]">مستودع 2</div>
            </div>
          </div>

          <!-- الجناح الجنوبي: معامل 10, 12, 14, 11, 13 -->
          <div class="grid grid-cols-5 gap-2">
            {% for l in [10, 12, 14, 11, 13] %}
              {% set has_bug = l in active_labs %}
              <a href="/dashboard?lab={{ l }}" class="p-2.5 text-center rounded-xl border transition flex flex-col justify-center items-center font-bold {{ 'bg-rose-500/20 border-rose-500 text-rose-300 pulse-danger' if has_bug else 'bg-slate-900 hover:bg-slate-800 border-slate-700/60 text-slate-200' }} {{ 'ring-2 ring-cyan-400' if current_lab == l }}">
                <span>معمل ({{ l }})</span>
                <span class="text-[9px] {{ 'text-rose-400' if has_bug else 'text-emerald-400' }}">{{ 'عطل!' if has_bug else 'سليم' }}</span>
              </a>
            {% endfor %}
          </div>
        </div>
      </div>

      <!-- خريطة المقاعد التفاعلية للمعمل المحدد (1 حتى 27) -->
      <div class="bg-slate-900/90 border border-slate-800 rounded-3xl p-5 shadow-xl flex flex-col">
        <div class="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
          <div class="flex items-center gap-2">
            <i class="fa-solid fa-network-wired text-cyan-400 text-lg"></i>
            <div>
              <h2 class="font-bold text-base text-white">توزيع مقاعد معمل ({{ current_lab }})</h2>
              <p class="text-[10px] text-slate-400">إجمالي 27 مقعد تدريبي + منصة المدرب</p>
            </div>
          </div>
          <a href="/qr_batch?lab={{ current_lab }}" target="_blank" class="px-2.5 py-1 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 rounded-lg text-xs font-semibold flex items-center gap-1 transition">
            <i class="fa-solid fa-qrcode"></i>
            <span>طباعة QR</span>
          </a>
        </div>

        <!-- منصة المدرب بالأمام -->
        <div class="mb-3 p-2 bg-slate-800/80 border border-slate-700/80 rounded-xl text-center text-xs font-bold text-cyan-300 flex items-center justify-center gap-2">
          <i class="fa-solid fa-chalkboard-user"></i>
          <span>منصة جهاز المدرب والشاشة الرئيسية</span>
        </div>

        <!-- شبكة المقاعد 1 إلى 27 -->
        <div class="flex-1 grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 xl:grid-cols-3 gap-2 overflow-y-auto max-h-[360px] custom-scroll p-1">
          {% for seat in range(1, 28) %}
            {% set is_broken = seat in broken_seats %}
            {% set is_repair = seat in repair_seats %}
            <div class="p-2.5 rounded-xl border text-center transition flex flex-col items-center justify-between {{ 'bg-rose-500/20 border-rose-500 text-rose-300 pulse-danger' if is_broken else ('bg-amber-500/20 border-amber-500 text-amber-300' if is_repair else 'bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-700') }}">
              <div class="flex items-center justify-between w-full text-[10px] opacity-75">
                <i class="fa-solid fa-desktop"></i>
                <span class="font-mono">#{{ seat }}</span>
              </div>
              <span class="text-xs font-bold mt-1">مقعد {{ seat }}</span>
              <span class="text-[9px] mt-1 px-1.5 py-0.5 rounded-full {{ 'bg-rose-500/30 text-rose-300' if is_broken else ('bg-amber-500/30 text-amber-300' if is_repair else 'bg-emerald-500/20 text-emerald-400') }}">
                {{ 'عطل نشط' if is_broken else ('قيد الفحص' if is_repair else 'جاهز') }}
              </span>
            </div>
          {% endfor %}
        </div>
      </div>
    </div>

    <!-- جدول البلاغات وسجل الصيانة التاريخي -->
    <div class="bg-slate-900/90 border border-slate-800 rounded-3xl p-5 shadow-xl">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 pb-3 border-b border-slate-800">
        <div class="flex items-center gap-2">
          <i class="fa-solid fa-list-check text-cyan-400 text-lg"></i>
          <h2 class="font-bold text-base text-white">تذاكر الأعطال ومسار الصيانة الرقمي</h2>
        </div>
        <div class="text-xs text-slate-400">
          تتبع لحظي للبلاغات والقطع المستبدلة لتوثيق السجل التاريخي للأجهزة
        </div>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-right text-xs">
          <thead class="bg-slate-950/60 text-slate-400 uppercase text-[11px] border-b border-slate-800">
            <tr>
              <th class="py-3 px-3">رقم التذكرة</th>
              <th class="py-3 px-3">الموقع</th>
              <th class="py-3 px-3">النوع والتفاصيل</th>
              <th class="py-3 px-3">المبلّغ</th>
              <th class="py-3 px-3">الحالة الحالية</th>
              <th class="py-3 px-3">القطع المستبدلة (الأرشيف)</th>
              <th class="py-3 px-3 text-center">إجراء الفني</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800/60">
            {% for t in tickets %}
            <tr class="hover:bg-slate-800/30 transition">
              <td class="py-3 px-3 font-mono font-bold text-cyan-400">#{{ t[0] }}</td>
              <td class="py-3 px-3 font-semibold text-white">معمل {{ t[1] }} <span class="text-cyan-400">/ مقعد {{ t[2] }}</span></td>
              <td class="py-3 px-3">
                <span class="inline-block px-2 py-0.5 rounded-md bg-slate-800 text-[10px] text-slate-300 mb-0.5">{{ t[4] }}</span>
                <p class="text-slate-300 font-medium">{{ t[5] }}</p>
              </td>
              <td class="py-3 px-3 text-slate-400">{{ t[3] }}</td>
              <td class="py-3 px-3">
                <span class="px-2.5 py-1 rounded-full text-[10px] font-bold {{ 'bg-rose-500/20 text-rose-400 border border-rose-500/30' if t[6] == 'جديد' else ('bg-amber-500/20 text-amber-400 border border-amber-500/30' if t[6] == 'قيد الفحص' else 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30') }}">
                  {{ t[6] }}
                </span>
              </td>
              <td class="py-3 px-3 text-slate-300 font-mono text-[11px]">{{ t[7] }}</td>
              <td class="py-3 px-3 text-center">
                {% if t[6] != 'مكتمل' %}
                <form action="/resolve/{{ t[0] }}" method="POST" class="inline-flex gap-1.5 items-center">
                  <input type="text" name="parts" placeholder="القطعة المستبدلة..." required class="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-white focus:outline-none focus:border-cyan-400 w-36">
                  <button type="submit" class="bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-3 py-1 rounded-lg text-xs transition">
                    إغلاق
                  </button>
                </form>
                {% else %}
                <span class="text-slate-500 font-medium">✓ مؤرشفة</span>
                {% endif %}
              </td>
            </tr>
            {% else %}
            <tr>
              <td colspan="7" class="py-8 text-center text-slate-500">لا توجد بلاغات مسجلة حالياً في النظام.</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </main>
</body>
</html>
"""

REPORT_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>تسجيل بلاغ عطل فني | قسم الحاسب</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>body { font-family: 'Tajawal', sans-serif; }</style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-4">
  <div class="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl relative">
    
    <div class="text-center mb-6">
      <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 text-2xl mb-3">
        <i class="fa-solid fa-triangle-exclamation"></i>
      </div>
      <h1 class="text-xl font-bold text-white">تسجيل عطل حاسب آلي</h1>
      <p class="text-xs text-slate-400 mt-1">يتم إرسال هذا البلاغ لحظياً إلى لوحة فني الصيانة</p>
    </div>

    <!-- معلومات موقع الجهاز الممسوح عبر QR -->
    <div class="grid grid-cols-2 gap-3 mb-5 p-3.5 bg-slate-950/80 border border-slate-800 rounded-2xl text-center">
      <div>
        <span class="text-[11px] text-slate-500">رقم المعمل</span>
        <div class="text-base font-extrabold text-cyan-400 mt-0.5">معمل {{ lab }}</div>
      </div>
      <div class="border-r border-slate-800">
        <span class="text-[11px] text-slate-500">رقم المقعد المستهدف</span>
        <div class="text-base font-extrabold text-cyan-400 mt-0.5">مقعد #{{ seat }}</div>
      </div>
    </div>

    <form action="/submit_ticket" method="POST" class="space-y-4 text-xs">
      <input type="hidden" name="lab" value="{{ lab }}">
      <input type="hidden" name="seat" value="{{ seat }}">

      <div>
        <label class="block font-semibold text-slate-300 mb-1">اسم المبلّغ (اختياري)</label>
        <input type="text" name="reporter_name" placeholder="مثال: أ. محمد / متدرب" class="w-full bg-slate-950 border border-slate-700/80 rounded-xl p-2.5 text-white focus:outline-none focus:border-cyan-400">
      </div>

      <div>
        <label class="block font-semibold text-slate-300 mb-1">تصنيف العطل</label>
        <select name="issue_category" class="w-full bg-slate-950 border border-slate-700/80 rounded-xl p-2.5 text-white focus:outline-none focus:border-cyan-400">
          <option value="عتادي (Hardware)">عتادي (شاشة، ماوس، كيبورد، مزود طاقة، رامات)</option>
          <option value="برمجي (Software)">برمجي (ويندوز، بطء، فيروس، تجمد النظام)</option>
          <option value="شبكة وإنترنت (Network)">مشكلة شبكة (عدم اتصال، كيبل تالف)</option>
        </select>
      </div>

      <div>
        <label class="block font-semibold text-slate-300 mb-1">وصف العطل بالتفصيل</label>
        <textarea name="issue" rows="3" required placeholder="اكتب وصفاً مختصراً للعطل الظاهر..." class="w-full bg-slate-950 border border-slate-700/80 rounded-xl p-2.5 text-white focus:outline-none focus:border-cyan-400"></textarea>
      </div>

      <button type="submit" class="w-full bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-bold py-3 rounded-xl transition shadow-lg shadow-cyan-500/20 text-sm flex items-center justify-center gap-2">
        <i class="fa-solid fa-paper-plane"></i>
        <span>إرسال البلاغ فوراً</span>
      </button>
    </form>
  </div>
</body>
</html>
"""

# --- مسارات النظام ---

@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        user_input = request.form.get('username')
        pass_input = request.form.get('password')
        if user_input in USERS and USERS[user_input]['password'] == pass_input:
            session['user'] = {
                'username': user_input,
                'name': USERS[user_input]['name'],
                'role': USERS[user_input]['role']
            }
            return redirect(url_for('dashboard'))
        error = "اسم المستخدم أو كلمة المرور غير صحيحة"
    return render_template_string(LOGIN_TEMPLATE, error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    current_lab = request.args.get('lab', default=1, type=int)

    conn = sqlite3.connect(os.path.join(BASE_DIR, 'maintenance.db'))
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tickets ORDER BY id DESC")
    tickets = cursor.fetchall()

    # استخراج المعامل النشطة ذات الأعطال
    cursor.execute("SELECT DISTINCT lab_num FROM tickets WHERE status != 'مكتمل'")
    active_labs = [row[0] for row in cursor.fetchall()]

    # استخراج المقاعد المتعطلة للمعمل الحالي
    cursor.execute("SELECT seat_num FROM tickets WHERE lab_num = ? AND status = 'جديد'", (current_lab,))
    broken_seats = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT seat_num FROM tickets WHERE lab_num = ? AND status = 'قيد الفحص'", (current_lab,))
    repair_seats = [row[0] for row in cursor.fetchall()]

    # حساب الإحصائيات الحيوية
    total = len(tickets)
    active = len([t for t in tickets if t[6] == 'جديد'])
    in_progress = len([t for t in tickets if t[6] == 'قيد الفحص'])
    
    total_department_seats = 27 * 14  # تقدير مقاعد معامل القسم
    readiness = round(((total_department_seats - (active + in_progress)) / total_department_seats) * 100, 1) if total_department_seats > 0 else 100.0

    conn.close()

    return render_template_string(
        DASHBOARD_TEMPLATE,
        user=session['user'],
        tickets=tickets,
        active_labs=active_labs,
        current_lab=current_lab,
        broken_seats=broken_seats,
        repair_seats=repair_seats,
        stats={'total': total, 'active': active, 'in_progress': in_progress, 'readiness': readiness}
    )

@app.route('/report')
def report_page():
    lab = request.args.get('lab', default=1, type=int)
    seat = request.args.get('seat', default=1, type=int)
    return render_template_string(REPORT_TEMPLATE, lab=lab, seat=seat)

@app.route('/submit_ticket', methods=['POST'])
def submit_ticket():
    lab = request.form['lab']
    seat = request.form['seat']
    reporter = request.form.get('reporter_name', 'غير محدد')
    category = request.form.get('issue_category', 'عام')
    issue = request.form['issue']

    conn = sqlite3.connect(os.path.join(BASE_DIR, 'maintenance.db'))
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tickets (lab_num, seat_num, reporter_name, issue_category, issue, status)
        VALUES (?, ?, ?, ?, ?, 'جديد')
    """, (lab, seat, reporter, category, issue))
    conn.commit()
    conn.close()

    return """
    <div style="font-family:'Tajawal',sans-serif; text-align:center; padding:50px; background:#020617; color:#f8fafc; min-height:100vh;">
      <h2 style="color:#38bdf8; font-size:24px;">✓ تم تسجيل البلاغ بنجاح!</h2>
      <p style="color:#94a3b8; font-size:14px; margin-top:10px;">تم توجيه التذكرة فورياً لخريطة فني الصيانة بقسم الحاسب.</p>
      <a href="/report?lab=""" + str(lab) + """&seat=""" + str(seat) + """" style="display:inline-block; margin-top:20px; color:#38bdf8; text-decoration:none; border:1px solid #0284c7; padding:8px 16px; border-radius:8px;">إرسال بلاغ آخر</a>
    </div>
    """

@app.route('/resolve/<int:ticket_id>', methods=['POST'])
def resolve_ticket(ticket_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    parts = request.form.get('parts', 'تم الإصلاح')
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'maintenance.db'))
    cursor = conn.cursor()
    cursor.execute("UPDATE tickets SET status = 'مكتمل', replaced_parts = ? WHERE id = ?", (parts, ticket_id))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/qr_batch')
def qr_batch():
    lab = request.args.get('lab', default=1, type=int)
    host = request.host
    qr_cards = ""
    for s in range(1, 28):
        url = f"http://{host}/report?lab={lab}&seat={s}"
        qr_cards += f"""
        <div style="border:2px dashed #0284c7; padding:12px; border-radius:12px; text-align:center; width:160px; font-family:'Tajawal',sans-serif; background:white; color:#0f172a;">
          <div style="font-size:11px; font-weight:bold; color:#0284c7;">قسم الحاسب الآلي</div>
          <div style="font-size:13px; font-weight:800; margin:2px 0;">معمل {lab} - مقعد {s}</div>
          <img src="https://api.qrserver.com/v1/create-qr-code/?size=110x110&data={url}" style="margin:auto; display:block;" />
          <div style="font-size:9px; color:#64748b; margin-top:4px;">امسح للإبلاغ الفوري</div>
        </div>
        """
    return f"""
    <!DOCTYPE html>
    <html dir="rtl">
    <head><meta charset="UTF-8"><title>ملصقات QR معمل {lab}</title></head>
    <body onload="window.print()" style="display:flex; flex-wrap:wrap; gap:12px; justify-content:center; padding:20px; background:#f8fafc;">
      {qr_cards}
    </body>
    </html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)