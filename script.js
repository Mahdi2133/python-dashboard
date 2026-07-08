// --script.js
// --------------------- متغیر عمومی داده چاه‌ها ---------------------
// اجرای امن — اگر یک تابع خطا بدهد، بقیه متوقف نشوند
function safe(fn, name) {
    try {
        fn();
    } catch (e) {
        console.error(`❌ خطا در ${name}:`, e);
    }
}
let wellsData = [];
let charts = {};

// ثابت‌های فونت مشترک
const FA_FONT  = { family: "'BNazanin', Tahoma, Arial",                    size: 13 };
const NUM_FONT = { family: "'TimesNewRoman', 'Times New Roman', serif",     size: 12 };
const TOOLTIP_BASE = {
    rtl: true,
    backgroundColor: 'rgba(15,23,42,0.92)',
    titleColor: '#94a3b8',
    bodyColor:  '#e2e8f0',
    padding: 12,
    titleFont: FA_FONT,
    bodyFont:  NUM_FONT
};

// فونت‌های پیش‌فرض Chart.js — فقط اگر کتابخانه لود شده باشد
if (typeof Chart !== 'undefined') {
    Chart.defaults.font.family = FA_FONT.family;
    Chart.defaults.font.size   = FA_FONT.size;
    // ثبت پلاگین zoom اگر بارگذاری شده باشد
    if (typeof ChartZoom !== 'undefined') {
        Chart.register(ChartZoom);
    } else if (window.chartjsPluginZoom) {
        Chart.register(window.chartjsPluginZoom);
    }
}
// ========== مدیریت تم دارک/لایت ==========
function toggleTheme() {
    const body = document.body;
    const icon = document.getElementById("themeIcon");
    const label = document.getElementById("themeLabel");
    const isDark = body.getAttribute("data-theme") === "dark";

    if (isDark) {
        body.removeAttribute("data-theme");
        icon.className = "fa-solid fa-moon";
        label.textContent = "حالت تاریک";
        localStorage.setItem("theme", "light");
        applyChartTheme(false);
    } else {
        body.setAttribute("data-theme", "dark");
        icon.className = "fa-solid fa-sun";
        label.textContent = "حالت روشن";
        localStorage.setItem("theme", "dark");
        applyChartTheme(true);
    }
}

function applyChartTheme(isDark) {
    const textColor  = isDark ? "#e2e8f0" : "#444";
    const gridColor  = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)";

    Chart.defaults.color       = textColor;
    Chart.defaults.borderColor = gridColor;

    // آپدیت همه نمودارهای ذخیره‌شده در آبجکت charts
    Object.values(charts).forEach(ch => {
        if (!ch) return;
        updateChartColors(ch, textColor, gridColor);
    });

    // نمودارهایی که در متغیر جداگانه ذخیره شده‌اند
    [
        groupFlowTrendChart,
        groupFlowChangeChart,
        groupExpectedVsActualChart,
        groupProductionTrendChart,
        groupYearlyProductionTrendChart,
        contractorAvgFlowChartInstance
    ].forEach(ch => {
        if (!ch) return;
        updateChartColors(ch, textColor, gridColor);
    });
}

function updateChartColors(ch, textColor, gridColor) {
    // رنگ legend
    if (ch.options.plugins?.legend?.labels) {
        ch.options.plugins.legend.labels.color = textColor;
    }

    // رنگ تیک‌های محورها
    if (ch.options.scales) {
        Object.values(ch.options.scales).forEach(scale => {
            if (scale.ticks)  scale.ticks.color  = textColor;
            if (scale.grid)   scale.grid.color   = gridColor;
            if (scale.title)  scale.title.color  = textColor;
        });
    }

    ch.update("none"); // "none" = بدون انیمیشن برای سرعت بیشتر
}

function loadSavedTheme() {
    const saved = localStorage.getItem("theme");
    if (saved === "dark") {
        document.body.setAttribute("data-theme", "dark");
        const icon  = document.getElementById("themeIcon");
        const label = document.getElementById("themeLabel");
        if (icon)  icon.className   = "fa-solid fa-sun";
        if (label) label.textContent = "حالت روشن";
    }
}


// تابع کمکی برای انیمیشن متناسب با نوع نمودار
// ========== انیمیشن نمودارها ==========
function getAnimConfig(type) {
    if (type === "line") {
        return {
            duration: 1000,
            easing: "easeInOutQuart"
        };
    }

    if (type === "bar") {
        return {
            duration: 900,
            easing: "easeInOutQuart"
        };
    }

    if (type === "pie" || type === "doughnut") {
        return {
            duration: 1000,
            easing: "easeInOutQuart",
            animateRotate: true,
            animateScale: true
        };
    }

    if (type === "radar") {
        return {
            duration: 1000,
            easing: "easeInOutQuart"
        };
    }

    if (type === "scatter") {
        return {
            duration: 700,
            easing: "easeInOutQuart"
        };
    }

    return { duration: 800, easing: "easeInOutQuart" };
}



// ==========================================
const MONTHS = [

"فروردین",
"اردیبهشت",
"خرداد",
"تیر",
"مرداد",
"شهریور",
"مهر",
"آبان",
"آذر",
"دی",
"بهمن",
"اسفند"

];

const ALL_YEARS = [1399, 1400, 1401, 1402, 1403, 1404, 1405];

// --------------------- صفحه لندینگ (index.html) -------------------
const fileInput = document.getElementById("excelFile");
const dropZone = document.getElementById("dropZone");

// ---------- پشتیبانی کامل DropZone ----------
if (dropZone && fileInput) {

    dropZone.addEventListener("click", () => {
        fileInput.click();
    });

    dropZone.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            fileInput.click();
        }
    });

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("dragover");
    });

    dropZone.addEventListener("drop", (e) => {

        e.preventDefault();
        dropZone.classList.remove("dragover");

        const files = e.dataTransfer.files;

        if (files && files.length > 0) {

            const file = files[0];

            const allowed = [
                ".xlsx",
                ".xls",
                ".csv"
            ];

            const lowerName = file.name.toLowerCase();

            const valid = allowed.some(ext => lowerName.endsWith(ext));

            if (!valid) {
                alert("فقط فایل‌های Excel یا CSV مجاز هستند.");
                return;
            }

            fileInput.files = files;
            fileInput.dispatchEvent(new Event("change"));
        }
    });
}

// مقدار سالانه را خودکار از ماه‌های موجود همان سال می‌سازد
// تولید/کارکرد → مجموع ماه‌ها ، دبی/فشار → میانگین ماه‌ها
// اگر ستون سالانه آماده وجود داشت، اول آن را ترجیح می‌دهد
function yearlyValue(row, fieldType, year) {
    // ابتدا تلاش برای خواندن ستون سالانهٔ آماده
    let directKey;
    if (fieldType === "تولید")       directKey = `تولید سال ${year}`;
    else if (fieldType === "کارکرد") directKey = `کارکرد سال ${year}`;
    else if (fieldType === "دبی")    directKey = `دبی متوسط سال ${year}`;
    else if (fieldType === "فشار")   directKey = `فشار سال ${year}`;

    const direct = parseNum(row[directKey]);
    if (!isNaN(direct)) return direct;

    // اگر ستون سالانه نبود، از ماه‌ها بساز
    let sum = 0, cnt = 0;
    MONTHS.forEach(m => {
        let key;
        if (fieldType === "کارکرد")      key = `کارکرد ${m} ${year}`;
        else if (fieldType === "تولید")  key = `تولید ${year}(${m})`;
        else if (fieldType === "دبی")    key = `دبی متوسط ${year}(${m})`;
        else if (fieldType === "فشار")   key = `فشار چاه ${year}(${m})`;

        const v = parseNum(row[key]);
        if (!isNaN(v)) { sum += v; cnt++; }
    });

    if (cnt === 0) return NaN;

    // تولید و کارکرد جمع می‌شوند، دبی و فشار میانگین
    if (fieldType === "تولید" || fieldType === "کارکرد") return sum;
    return sum / cnt;
}

// ---------- انتخاب فایل ----------
if (fileInput) {

    fileInput.addEventListener("change", function () {

        if (this.files.length === 0) return;

        const file = this.files[0];

        const lowerName = file.name.toLowerCase();

        if (
            !lowerName.endsWith(".xlsx") &&
            !lowerName.endsWith(".xls") &&
            !lowerName.endsWith(".csv")
        ) {
            alert("فرمت فایل معتبر نیست.");
            return;
        }

        sessionStorage.setItem("excelFileName", file.name);

        const reader = new FileReader();

        reader.onload = function (e) {
            try {
                sessionStorage.setItem("excelFileData", e.target.result);
            } catch (err) {
                alert("حجم فایل برای ذخیره موقت زیاد است (سقف ~۵ مگابایت). ستون‌های اضافی یا شیت‌های اضافه را حذف کن و دوباره امتحان کن.");
                return;
            }
            window.location.href = "dashboard.html";
        };

        reader.readAsDataURL(file);
    });
}


// --------------------- صفحه داشبورد (dashboard.html) ----------------
document.addEventListener("DOMContentLoaded", () => {

    if (!document.body.classList.contains("dashboard-body")) return;

    // داده به‌جای فایل اکسل، از دیتابیس سامانه (جدول production_trend) خوانده می‌شود.
    // مسیر API از data-api روی body تعیین می‌شود تا با هر url_prefix کار کند.
    const apiUrl = document.body.getAttribute("data-api") || "api/data";

    const fileNameShow = document.getElementById("excelFileNameShow");
    if (fileNameShow) {
        fileNameShow.textContent = "منبع داده: پایگاه‌داده سامانه";
    }

    fetch(apiUrl, { cache: "no-store" })
        .then(resp => {
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            return resp.json();
        })
        .then(rows => {
            loadFromDatabase(rows);
        })
        .catch(err => {
            console.error("خطا در دریافت داده از پایگاه‌داده:", err);
            alert("خطا در دریافت داده از پایگاه‌داده: " + err.message);
        });
});

// جایگزین processExcelData: داده‌ی آماده (با کلیدهای فارسی) را در wellsData می‌ریزد
// و همان توابع راه‌اندازیِ داشبورد را صدا می‌زند.
function loadFromDatabase(rows) {
    try {
        wellsData = (rows || []).filter(r =>
            r && r["نام چاه"] && String(r["نام چاه"]).trim() !== ""
        );

        if (wellsData.length === 0) {
            alert("هیچ ردیف معتبری در پایگاه‌داده پیدا نشد.");
            return;
        }

        initDashboard();
        safe(() => initDrillingFilters(wellsData), "initDrillingFilters");
        safe(() => updateDrillingDashboard(wellsData), "updateDrillingDashboard");
        safe(() => updateContractorRanking(wellsData), "updateContractorRanking");

    } catch (error) {
        console.error("جزئیات خطا:", error);
        alert("خطا در پردازش داده: " + error.message);
    }
}

// تبدیل تاریخ شمسی متنی مثل 1404/10/05 به {year, month, day}
// تبدیل تاریخ شمسی به {year, month, day}
// هم فرمت 1404/11/10 و هم فرمت عددی چسبیده 14041110 را می‌فهمد
function parseJalaliDate(val) {
    if (val === undefined || val === null) return null;
    const s = String(val).trim();

    // حالت اول: با جداکننده مثل 1404/11/10 یا 1404-11-10
    let m = s.match(/(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})/);
    if (m) {
        return { year: +m[1], month: +m[2], day: +m[3] };
    }

    // حالت دوم: عدد ۸ رقمی چسبیده مثل 14041110
    const digits = s.replace(/\D/g, "");
    if (digits.length === 8) {
        return {
            year:  +digits.slice(0, 4),
            month: +digits.slice(4, 6),
            day:   +digits.slice(6, 8)
        };
    }

    return null;
}

// گرفتن ستون بر اساس کلمات کلیدی (مقاوم به اختلاف فاصله/پرانتز)
function getColByContains(row, ...needles) {
    const key = Object.keys(row).find(k =>
        needles.every(n => k.includes(n))
    );
    return key ? row[key] : undefined;
}

// --------------------- پردازش اکسل ---------------------
function processExcelData(base64Data) {
    try {
        const arrayBuffer = base64ToArrayBuffer(base64Data);
        const workbook = XLSX.read(arrayBuffer, { type: "array" });
        const firstSheet = workbook.Sheets[workbook.SheetNames[0]];

        const raw = XLSX.utils.sheet_to_json(firstSheet, { defval: null });

        // حذف ردیف‌های خالی یا بدون «نام چاه»
        wellsData = raw.filter(r =>
            r && r["نام چاه"] && String(r["نام چاه"]).trim() !== ""
        );

        if (wellsData.length === 0) {
            alert("هیچ ردیف معتبری پیدا نشد. ستون «نام چاه» را بررسی کنید.");
            return;
        }

        initDashboard();
        safe(() => initDrillingFilters(wellsData), "initDrillingFilters");
        safe(() => updateDrillingDashboard(wellsData), "updateDrillingDashboard");
        safe(() => updateContractorRanking(wellsData), "updateContractorRanking");

    } catch (error) {
        console.error("جزئیات خطا:", error);
        alert("خطا در خواندن فایل اکسل: " + error.message);
    }
}

// --------------------- مقداردهی داشبورد ---------------------
function initDashboard() {
    _latestYMCache = null;
    _contractorStatsCache = null;
    // ۱. تنظیمات ظاهری که به داده نیاز ندارند (همیشه اجرا شوند)
    setupTabs();
    loadSavedTheme(); // ✅ اضافه کن
    setupFiltersListeners();
    
    // ۲. اگر هنوز فایلی انتخاب نشده، بقیه تابع (رسم نمودارها) متوقف شود
    if (!wellsData || wellsData.length === 0) return;

        // فراخوانی امن توابع
    if (document.getElementById("chartWellStatus")) {
        drawWellStatusChart();
    }

    // ۳. کارهایی که فقط بعد از انتخاب فایل اکسل باید انجام شوند
    safe(() => drawWellStatusChart(), "drawWellStatusChart");
    safe(() => renderKPIs(), "renderKPIs");
    safe(() => setupYearFilter(), "setupYearFilter");
    safe(() => drawWellsByOffice(), "drawWellsByOffice");
    safe(() => drawOfficeRanking(), "drawOfficeRanking");
    safe(() => drawCompareCharts(), "drawCompareCharts");
    safe(() => drawZoneWellsChart(), "drawZoneWellsChart");
    safe(() => drawCompareEfficiency(), "drawCompareEfficiency");
    safe(() => setupOfficeFilter(), "setupOfficeFilter");
    safe(() => fillWellFilter(), "fillWellFilter");
    safe(() => initGroupFilters(), "initGroupFilters");
    safe(() => updateOverviewStats(), "updateOverviewStats");
    safe(() => updateCharts(), "updateCharts");
    safe(() => fillWellTypeWellList(), "fillWellTypeWellList");
    safe(() => restoreWellTypePanelState(), "restoreWellTypePanelState");
    safe(() => renderStatsTable(), "renderStatsTable");
    safe(() => initPumpTestDashboard(), "initPumpTestDashboard");
    updateContractorRanking(wellsData);
    safe(() => initHeatmapTab(), "initHeatmapTab");
    safe(() => initClusterTab(), "initClusterTab");
    safe(() => initAlertsTab(), "initAlertsTab");
    safe(() => renderContractorPerfTable(), "renderContractorPerfTable");
    safe(() => renderOpenInstallWarnings(), "renderOpenInstallWarnings");
    safe(() => renderEquipmentAnalyses(), "renderEquipmentAnalyses");
    safe(() => initPermitTable(), "initPermitTable");
}

function initHeatmapTab() {
    const ySel = document.getElementById("hmYear");
    if (ySel && !ySel.options.length) {
        ALL_YEARS.forEach(y => ySel.innerHTML += `<option value="${y}">${y}</option>`);
        ySel.value = ALL_YEARS[ALL_YEARS.length - 1];
    }
    fillOfficeSelect("hmOffice", "دانشجو");
    fillWellSelectByOffice("hmWell", "hmOffice");
    attachWellSearch("hmWellSearch", "hmWell");

    document.getElementById("hmOffice")?.addEventListener("change", () => {
        fillWellSelectByOffice("hmWell", "hmOffice");
        renderHeatmap();
    });
    document.getElementById("hmWell")?.addEventListener("change", renderHeatmap);
    document.getElementById("hmMetric")?.addEventListener("change", renderHeatmap);
    document.getElementById("hmYear")?.addEventListener("change", renderHeatmap);
    renderHeatmap();
}

function initClusterTab() {
    const ySel = document.getElementById("clusterYear");
    if (ySel && !ySel.options.length) {
        ALL_YEARS.forEach(y => ySel.innerHTML += `<option value="${y}">${y}</option>`);
        ySel.value = ALL_YEARS[ALL_YEARS.length - 1];
    }
    fillOfficeSelect("clOffice", "دانشجو");
    fillWellSelectByOffice("clWell", "clOffice");
    attachWellSearch("clWellSearch", "clWell");

    document.getElementById("clOffice")?.addEventListener("change", () => {
        fillWellSelectByOffice("clWell", "clOffice");
        renderCluster();
    });
    document.getElementById("clWell")?.addEventListener("change", renderCluster);
    document.getElementById("clusterYear")?.addEventListener("change", renderCluster);
    document.getElementById("clusterK")?.addEventListener("change", renderCluster);
    renderCluster();
}

function initAlertsTab() {
    // پر کردن دو دراپ‌داون سال (دیفالت: دو سال آخر)
    const yp = document.getElementById("alYearPrev");
    const yl = document.getElementById("alYearLast");
    if (yp && !yp.options.length) {
        ALL_YEARS.forEach(y => {
            yp.innerHTML += `<option value="${y}">${y}</option>`;
            yl.innerHTML += `<option value="${y}">${y}</option>`;
        });
        const [defPrev, defLast] = lastTwoYears();
        yp.value = defPrev;
        yl.value = defLast;
    }

    fillOfficeSelect("alOffice", "دانشجو");
    fillWellSelectByOffice("alWell", "alOffice");
    attachWellSearch("alWellSearch", "alWell");

    document.getElementById("alOffice")?.addEventListener("change", () => {
        fillWellSelectByOffice("alWell", "alOffice");
        renderRiskAlerts();
    });
    document.getElementById("alWell")?.addEventListener("change", renderRiskAlerts);
    document.getElementById("alYearPrev")?.addEventListener("change", renderRiskAlerts);
    document.getElementById("alYearLast")?.addEventListener("change", renderRiskAlerts);
    renderRiskAlerts();
}
    





// --------------------- فیلتر اداره ---------------------
function setupOfficeFilter() {

    const select = document.getElementById("filterOffice");

    if (!select || !wellsData.length) return;

    select.innerHTML =
        '<option value="all">همه ادارات</option>';

    const offices = [
        ...new Set(
            wellsData
                .map(row => row["اداره"])
                .filter(Boolean)
        )
    ];

    offices.forEach(off => {

        const opt = document.createElement("option");

        opt.value = off;
        opt.textContent = off;

        select.appendChild(opt);
    });
}


// --------------------- فیلتر چاه ---------------------
function fillWellFilter() {

    const select = document.getElementById("filterWell");
    if (!select) return;

    const office =
        document.getElementById("filterOffice")?.value || "all";

    const year =
        document.getElementById("filterYear")?.value || "all";

    select.innerHTML = '<option value="all">همه چاه‌ها</option>';

    const wells = wellsData.filter(r => {

        if (office !== "all" && r["اداره"] !== office) return false;

        if (year !== "all") {
            const y = Number(year);
            const hasData =
                !isNaN(parseNum(r[`تولید سال ${y}`])) ||
                !isNaN(parseNum(r[`دبی متوسط سال ${y}`]));
            if (!hasData) return false;
        }

        return true;

    }).map(r => r["نام چاه"])
      .filter(Boolean);

    [...new Set(wells)].forEach(w => {
        const opt = document.createElement("option");
        opt.value = w;
        opt.textContent = w;
        select.appendChild(opt);
    });
}

// --------------------- فیلتر سال ---------------------
function setupYearFilter() {

    const select = document.getElementById("filterYear");
    if (!select) return;

    select.innerHTML = '<option value="all">همه سال‌ها</option>';

    ALL_YEARS.forEach(y => {
        const opt = document.createElement("option");
        opt.value = y;
        opt.textContent = y;
        select.appendChild(opt);
    });
}


// --------------------- تب‌ها ---------------------
// --------------------- تب‌ها ---------------------
function setupTabs() {

    const tabs = document.querySelectorAll(".tab");
    const panels = document.querySelectorAll(".tab-panel");

    tabs.forEach(tab => {

        tab.addEventListener("click", function () {

            const tabName = this.getAttribute("data-tab");
            if (!tabName) return;

            tabs.forEach(t => t.classList.remove("active"));
            panels.forEach(p => p.classList.remove("active"));

            this.classList.add("active");

            const targetPanel = document.getElementById("tab-" + tabName);

            if (targetPanel) {
                targetPanel.classList.add("active");
            }

            if (tabName === "drilling") {

                setTimeout(() => {

                    const panel = document.getElementById("tab-drilling");
                    const canvas = document.getElementById("contractorAvgFlowChart");

                    console.log("panel active:", panel.classList.contains("active"));
                    console.log("panel width:", panel.offsetWidth);

                    if (panel.offsetWidth > 0 && canvas) {
                        //drawContractorAverageFlow(wellsData);
                    }

                }, 400);
            }

        });

    });
    document.addEventListener("DOMContentLoaded", () => {
    setupTabs();
});


}





// --------------------- لیسنر فیلترها ---------------------
function setupFiltersListeners() {

    const effYear =
document.getElementById("effYearFilter");

if(effYear){
effYear.addEventListener("change",()=>{
drawCompareEfficiency();
});
}

const pressYear =
document.getElementById("pressureDropYearFilter");

if(pressYear){
pressYear.addEventListener("change",()=>{
drawPressureDrop();
});
}


    const yearSelect =
        document.getElementById("filterYear");

    const officeSelect =
        document.getElementById("filterOffice");

    const wellSelect =
        document.getElementById("filterWell");


    if (yearSelect) {
        yearSelect.addEventListener("change", () => {
            fillWellFilter();  // ← اضافه شود
            drawOfficeRanking();
            updateOverviewStats();
            updateCharts();
            renderKPIs();
            

            updateOverviewStats();
            updateCharts();

        });
    }

    if (officeSelect) {
        officeSelect.addEventListener("change", () => {

            updateOverviewStats();
            updateCharts();
            fillWellFilter();
            renderStatsTable();

        });
    }

    if (wellSelect) {
        wellSelect.addEventListener("change", () => {

            updateOverviewStats();
            updateCharts();
            renderStatsTable();


        });
    }
 
const wellSearch =
document.getElementById("wellSearch");

if(wellSearch){

wellSearch.addEventListener("input",()=>{

const txt =
wellSearch.value.trim();

const select =
document.getElementById("filterWell");

const options =
select.querySelectorAll("option");

options.forEach(op=>{

const show =
op.textContent.includes(txt);

op.style.display =
show ? "block" : "none";

});

});

}
const rankingYear =
document.getElementById("rankingYearFilter");

if(rankingYear){

rankingYear.addEventListener("change",()=>{

drawOfficeRanking();

});

}
const zoneYear = document.getElementById("zoneYearFilter");

if(zoneYear){
    zoneYear.addEventListener("change", drawZoneWellsChart);
}
document.querySelectorAll(".ov-year").forEach(cb => {
        cb.addEventListener("change", updateCharts);
    });
    // چک‌باکس «همه سال‌ها»: تیک زدن/برداشتن همه‌ی سال‌ها یکجا
    const ovYearAll = document.getElementById("ovYearAll");
    if (ovYearAll) {
        ovYearAll.addEventListener("change", () => {
            document.querySelectorAll(".ov-year").forEach(cb => {
                cb.checked = ovYearAll.checked;
            });
            updateCharts();
            updateOverviewStats();
            renderKPIs();
        });
        // اگر کاربر تک‌تک سال‌ها را دستی عوض کرد، وضعیت «همه» هم هماهنگ شود
        document.querySelectorAll(".ov-year").forEach(cb => {
            cb.addEventListener("change", () => {
                const all = document.querySelectorAll(".ov-year");
                const checked = document.querySelectorAll(".ov-year:checked");
                ovYearAll.checked = (all.length === checked.length);
                updateOverviewStats();
                renderKPIs();
            });
        });
    }
    // دکمه‌ی بازگشت zoom همه‌ی نمودارهای نمای کلی
    const resetZoomBtn = document.getElementById("resetZoomBtn");
    if (resetZoomBtn) {
        resetZoomBtn.addEventListener("click", () => {
            ["chartProduction", "chartFlow", "chartRuntime", "chartPressure"].forEach(id => {
                if (charts[id] && charts[id].resetZoom) charts[id].resetZoom();
            });
        });
    }
// دکمه‌ی «حالت اصلی» مخصوص هر نمودار نمای کلی
    document.querySelectorAll(".chart-reset-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const id = btn.getAttribute("data-chart");
            if (id && charts[id] && charts[id].resetZoom) charts[id].resetZoom();
        });
    });    
    // فیلتر ماه: اتصال چک‌باکس‌ها
    const ovMonthAll = document.getElementById("ovMonthAll");
    function refreshOnMonth() {
        updateCharts();
        updateOverviewStats();
        renderKPIs();
    }
    if (ovMonthAll) {
        ovMonthAll.addEventListener("change", () => {
            // «همه» یعنی هیچ ماهی تیک نباشد (تابع بالا خودش همه را برمی‌گرداند)
            if (ovMonthAll.checked) {
                document.querySelectorAll(".ov-month").forEach(cb => { cb.checked = false; });
            }
            refreshOnMonth();
        });
    }
    document.querySelectorAll(".ov-month").forEach(cb => {
        cb.addEventListener("change", () => {
            // اگر کاربر ماه خاصی زد، تیک «همه» برداشته شود
            if (ovMonthAll && cb.checked) ovMonthAll.checked = false;
            refreshOnMonth();
        });
    });

}
// ------------------ آمار نمای کلی ----------------------
function updateOverviewStats() {

    const year   = document.getElementById("filterYear")?.value   || "all";
    const office = document.getElementById("filterOffice")?.value || "all";
    const well   = document.getElementById("filterWell")?.value   || "all";

    const filteredRows = wellsData.filter(row =>
        (office === "all" || row["اداره"] === office) &&
        (well   === "all" || row["نام چاه"] === well) &&
        (typeof _selectedWellType === "undefined" || _selectedWellType === "all" || getWellType(row) === _selectedWellType)
    );

    // سال‌ها از چک‌باکس‌های نمودار (.ov-year) خوانده می‌شوند تا کارت‌ها و نمودارها یکی باشند.
    // اگر هیچ چک‌باکسی تیک نبود، به filterYear برمی‌گردیم.
    let years = getSelectedChartYears().map(Number);
    if (years.length === 0) {
        years = (year === "all") ? ALL_YEARS : [Number(year)];
    }

    let pressureSum = 0, pressureCount = 0;
    let prodSum = 0;
    let flowSum = 0, flowCount = 0;
    let runSum = 0;

const selMonths = getSelectedChartMonths();
    const allMonthsSelected = (selMonths.length === 12);

    filteredRows.forEach(row => {
        years.forEach(y => {
            if (allMonthsSelected) {
                // حالت عادی: مقدار کل سال (مثل قبل)
                const p = yearlyValue(row, "فشار", y);
                if (!isNaN(p)) { pressureSum += p; pressureCount++; }
                const prod = yearlyValue(row, "تولید", y);
                if (!isNaN(prod)) prodSum += prod;
                const f = yearlyValue(row, "دبی", y);
                if (!isNaN(f)) { flowSum += f; flowCount++; }
                const r = yearlyValue(row, "کارکرد", y);
                if (!isNaN(r)) runSum += r;
            } else {
                // فیلتر ماه فعال: فقط ماه‌های انتخابی جمع/میانگین شوند
                selMonths.forEach(mNum => {
                    const m = MONTHS[mNum - 1];
                    // فشار (میانگین)
                    const p = parseNum(row[`فشار چاه ${y}(${m})`]);
                    if (!isNaN(p)) { pressureSum += p; pressureCount++; }
                    // تولید (جمع)
                    const prod = parseNum(row[`تولید ${y}(${m})`]);
                    if (!isNaN(prod)) prodSum += prod;
                    // دبی (میانگین)
                    const f = parseNum(row[`دبی متوسط ${y}(${m})`]);
                    if (!isNaN(f)) { flowSum += f; flowCount++; }
                    // کارکرد (جمع)
                    const r = parseNum(row[`کارکرد ${m} ${y}`]);
                    if (!isNaN(r)) runSum += r;
                });
            }
        });
    });

    const set = (id, val, d) => {
        const el = document.getElementById(id);
        if (el) el.textContent = fNum(val, d);
    };

    set("avgPressureValue",     pressureCount ? pressureSum / pressureCount : NaN, 1);
    set("totalProductionValue", prodSum, 0);
    set("avgFlowrateValue",     flowCount ? flowSum / flowCount : NaN, 1);
    set("avgRuntimeValue",      runSum, 0);
    

    // معادل ماهِ جمع کارکرد: ساعت ÷ ۲۴ ÷ ۳۰
    const months = runSum / 24 / 30;
    const monthsEl = document.getElementById("runtimeMonthsValue");
    if (monthsEl) monthsEl.textContent = "معادل: " + (isNaN(months) ? "-" : months.toFixed(2)) + " ماه";
}

function renderStatsTable(){

const year =
document.getElementById("filterYear").value;

const rows =
year === "all"
? wellsData
: wellsData;

const offices =
[...new Set(rows.map(r => r["اداره"]))];

const tbody =
document.querySelector("#statsTable tbody");

tbody.innerHTML="";

let index=1;

offices.forEach(office=>{

const officeRows =
rows.filter(r => r["اداره"]===office);

let prod=[];
let flow=[];
let runtime=[];
let pressure=[];

officeRows.forEach(r=>{

const years =
year==="all" ? ALL_YEARS : [Number(year)];

years.forEach(y=>{

prod.push(parseNum(r[`تولید سال ${y}`])||0);

flow.push(parseNum(r[`دبی متوسط سال ${y}`])||0);

runtime.push(parseNum(r[`کارکرد سال ${y}`])||0);

pressure.push(parseNum(r[`فشار سال ${y}`])||0);

});

});

if(!prod.length) return;

const prodAvg =
prod.reduce((a,b)=>a+b,0)/prod.length;

const flowAvg =
flow.reduce((a,b)=>a+b,0)/flow.length;

const runtimeAvg =
runtime.reduce((a,b)=>a+b,0)/runtime.length;

const pressureAvg =
pressure.reduce((a,b)=>a+b,0)/pressure.length;

const tr =
document.createElement("tr");

tr.innerHTML=`

<td>${index}</td>
<td>${office}</td>

<td>${Math.round(prodAvg)}</td>
<td>${Math.round(std(prod))}</td>

<td>${Math.round(flowAvg)}</td>
<td>${Math.round(std(flow))}</td>

<td>${Math.round(runtimeAvg)}</td>
<td>${Math.round(std(runtime))}</td>




`;

tbody.appendChild(tr);

index++;

});
// ===== Heatmap رنگی جدول =====

const rowsArr = [...tbody.querySelectorAll("tr")];

const colIndexes = [2,3,4,5,6,7];

colIndexes.forEach(col => {

    let values =
    rowsArr.map(r => parseFloat(r.children[col].textContent));

    let min = Math.min(...values);
    let max = Math.max(...values);

    rowsArr.forEach(r => {

        const td = r.children[col];

        const val =
        parseFloat(td.textContent);

        colorizeCell(td, val, min, max);

    });

});

}

// ------------------ محاسبه KPI ها ----------------------
function calculateKPIs() {

    const year =
        document.getElementById("filterYear")?.value || "all";

    const office =
        document.getElementById("filterOffice")?.value || "all";

    const wellFilter =
        document.getElementById("filterWell")?.value || "all";


    const rows = wellsData.filter(r =>
        (office === "all" || r["اداره"] === office) &&
        (wellFilter === "all" || r["نام چاه"] === wellFilter)
    );

    let maxProdWell = null;
    let minPressureWell = null;
    let criticalWells = [];

    let maxProduction = -Infinity;
    let minPressure = Infinity;

    rows.forEach(row => {

        const wellName = row["نام چاه"];
        if (!wellName) return;

        const years =
            year === "all"
                ? ALL_YEARS
                : [Number(year)];

        // -------- بیشترین تولید --------
        let prodSum = 0;

        years.forEach(y => {
            prodSum +=
                parseNum(row[`تولید سال ${y}`]) || 0;
        });

        if (prodSum > maxProduction) {
            maxProduction = prodSum;
            maxProdWell = wellName;
        }

        // -------- کمترین فشار --------
        const pressureCols =
            getPressureColumnsFromData([row], year);

        pressureCols.forEach(col => {

            const p = parseNum(row[col]);

            if (!isNaN(p) && p < minPressure) {
                minPressure = p;
                minPressureWell = wellName;
            }
        });

        // -------- چاه بحرانی --------
        if (!isNaN(minPressure) && minPressure < 20) {
            criticalWells.push(wellName);
        }

    });

    return {
        maxProdWell,
        minPressureWell,
        criticalWells
    };
}
// ------------------ نمایش KPI ها ----------------------
function renderKPIs() {

    const kpis = calculateKPIs();

    const maxProdEl =
        document.getElementById("kpiMaxProd");

    const minPressureEl =
        document.getElementById("kpiMinPressure");

    const criticalCountEl =
        document.getElementById("kpiCritical");

    if (maxProdEl)
        maxProdEl.textContent =
            kpis.maxProdWell || "-";

    if (minPressureEl)
        minPressureEl.textContent =
            kpis.minPressureWell || "-";

    if (criticalCountEl)
        criticalCountEl.textContent =
            kpis.criticalWells.length;
}
// ------------------ نمایش هشدارها ----------------------
function renderAlerts() {

    const kpis = calculateKPIs();

    const alertList =
        document.getElementById("alertList");

    if (!alertList) return;

    alertList.innerHTML = "";

    if (!kpis.criticalWells.length) {
        alertList.innerHTML =
            "<li>✅ چاه بحرانی وجود ندارد</li>";
        return;
    }

    kpis.criticalWells.forEach(name => {

        const li = document.createElement("li");
        li.textContent = `⚠️ ${name} - افت فشار`;
        alertList.appendChild(li);

    });
}

// ------------------ ستون‌های فشار ----------------------
function getPressureColumnsFromData(dataRows, year) {

    if (!dataRows || !dataRows.length) return [];

    const keys = Object.keys(dataRows[0]);

    let cols = keys.filter(k =>

        typeof k === "string" &&
        k.trim().startsWith("فشار چاه")

    );

    if (year !== "all") {

        const prefix = `فشار چاه ${year}(`;

        cols = cols.filter(k =>
            k.startsWith(prefix)
        );
    }

    return cols;
}


// ------------------ نمودارها ----------------------
function buildMonthlySeries(rows, year, fieldPrefix) {

    const months = [
        "فروردین","اردیبهشت","خرداد","تیر",
        "مرداد","شهریور","مهر","آبان",
        "آذر","دی","بهمن","اسفند"
    ];

    let values = new Array(12).fill(0);
    let counts = new Array(12).fill(0);

    rows.forEach(r => {

        months.forEach((m, i) => {

            let key;

            if(fieldPrefix==="کارکرد"){
                key = `کارکرد ${m} ${year}`;
            }
            else{
                key = `${fieldPrefix} ${year}(${m})`;
            }

            const v = parseNum(r[key]);

            if (!isNaN(v)) {

                values[i] += v;
                counts[i]++;

            }
        });

    });

    return values.map((v, i) =>
        counts[i]
            ? v / counts[i]
            : null
    );
}


const yearColors = {
    "1399": "#e60049",
    "1400": "#0bb4ff",
    "1401": "#50e991",
    "1402": "#e6d800",
    "1403": "#9b19f5",
    "1404": "#ffa300",
    "1405": "#00bfa0"
};


// ---------------------------------------------------------
// رسم نمودار عمومی
// ---------------------------------------------------------
function drawChart(id, datasets) {
    const canvas = document.getElementById(id);
    if (!canvas) return;

    if (charts[id]) {
        charts[id].destroy();
    }

    charts[id] = new Chart(canvas, {
        type: "line",
        data: {
            labels: [
                "فروردین","اردیبهشت","خرداد","تیر",
                "مرداد","شهریور","مهر","آبان",
                "آذر","دی","بهمن","اسفند"
            ],
            datasets: datasets
        },
        options: {
            responsive: true,
            animation: getAnimConfig("line"),   // ✅
            plugins: {
                legend: { position: "top" }
            },
            scales: { y: { beginAtZero: true } }
        }
    });
}


// ماه‌های انتخاب‌شده (۱..۱۲). اگر هیچ‌کدام تیک نبود یا «همه» تیک بود، همه‌ی ماه‌ها.
function getSelectedChartMonths() {
    const checks = document.querySelectorAll(".ov-month:checked");
    if (checks.length === 0) return [1,2,3,4,5,6,7,8,9,10,11,12];
    return [...checks].map(c => Number(c.value)).sort((a, b) => a - b);
}

// ---------------------------------------------------------
// آپدیت نمودارها (اصلاح‌شده با 1399 تا 1404)
// ---------------------------------------------------------
// ---------- خواندن سال‌های انتخاب‌شده از چک‌باکس‌ها ----------
function getSelectedChartYears() {
    const checks = document.querySelectorAll(".ov-year:checked");
    return [...checks].map(c => c.value).sort((a, b) => Number(a) - Number(b));
}

// ---------- ساخت سری پیوسته ماهانه در طول چند سال ----------
function buildContinuousSeries(rows, years, fieldPrefix, useSum) {
        const labels = [], data = [], pointYears = [];

    years.forEach(y => {
        // تشخیص خودکار ماه‌های موجود هر سال: فقط ماه‌هایی که حداقل یک چاه داده دارد
        const monthsForYear = MONTHS.filter(m => {
            const key = `${fieldPrefix} ${y}(${m})`;
            const keyRun = `کارکرد ${m} ${y}`;
            return rows.some(r =>
                (r[key] !== undefined && r[key] !== null && r[key] !== "") ||
                (r[keyRun] !== undefined && r[keyRun] !== null && r[keyRun] !== "")
            );
        });
        // فیلتر ماه: فقط ماه‌های انتخاب‌شده نگه داشته شوند
        const selMonths = getSelectedChartMonths();
        const monthsFiltered = monthsForYear.filter(m => selMonths.includes(MONTHS.indexOf(m) + 1));

        monthsFiltered.forEach(m => {
            let key;
            if (fieldPrefix === "کارکرد") key = `کارکرد ${m} ${y}`;
            else key = `${fieldPrefix} ${y}(${m})`;

            let sum = 0, cnt = 0;
            rows.forEach(r => {
                const v = parseNum(r[key]);
                if (!isNaN(v)) { sum += v; cnt++; }
            });

            const mNum = String(MONTHS.indexOf(m) + 1).padStart(2, "0");
            labels.push(`${y}/${mNum}`);
            const val = cnt ? (useSum ? sum : sum / cnt) : null;
            data.push((val === null || val === 0) ? null : val);
            pointYears.push(String(y));
        });
    });

    return { labels, data, pointYears };
}

// ---------- آپشن‌های مشترک ----------
// ---------- آپشن‌های مشترک ----------
function overviewOptions(type, annotations, hideXLabels) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: getAnimConfig(type),
        layout: { padding: { top: 70 } },   // ✅ فضای بالا برای باکس
        plugins: {
            legend: { display: false },
            tooltip: {
                ...TOOLTIP_BASE,
                callbacks: hideXLabels ? {
                    title: function () { return ""; }
                } : {}
            },
            annotation: { annotations: annotations || {} },
            zoom: {
                pan: { enabled: true, mode: 'x', modifierKey: null },
                zoom: {
                    wheel: { enabled: true },
                    pinch: { enabled: true },
                    drag: { enabled: true, backgroundColor: 'rgba(37,99,235,0.15)' },
                    mode: 'x'
                },
                limits: { x: { minRange: 2 } }
            }
        },
        scales: {
            x: { ticks: { autoSkip: true, maxRotation: 60, font: FA_FONT }, grid: { display: false } },

            // محور عمودی سمت چپ (اصلی، دیتاست‌ها به این وصل‌اند)
            y: {
                beginAtZero: true,
                position: "left",
                ticks: { font: NUM_FONT }
            },

            // محور عمودی سمت راست (آینه‌ی همان اعداد، فقط نمایشی)
            yRight: {
                beginAtZero: true,
                position: "right",
                ticks: { font: NUM_FONT },
                grid: { drawOnChartArea: false },   // خطوط شبکه دوبار کشیده نشود
                afterDataLimits(scale) {
                    const left = scale.chart.scales.y;
                    if (left) {
                        scale.min = left.min;
                        scale.max = left.max;
                    }
                }
            }
        }
    };
}

// ---------- آپدیت یا ساخت نمودار (برای انیمیشن نرم بدون پرش) ----------
function upsertOverviewChart(id, type, labels, data, pointYears, annotations) {
    const canvas = document.getElementById(id);
    if (!canvas) return;

    const ptColors = pointYears.map(y => yearColors[y] || "#64748b");

    let dataset;
    if (type === "bar") {
        dataset = {
            label: "تولید",
            data: data,
            backgroundColor: ptColors,
            borderColor: ptColors,
            borderWidth: 0,
            categoryPercentage: 1.0,
            barPercentage: 1.0
        };
    } else {
        dataset = {
            label: "",
            data: data,
            fill: true,
            spanGaps: false,
            tension: 0.35,
            borderWidth: 2.5,
            pointRadius: 2.5,
            pointHoverRadius: 6,
            pointBackgroundColor: ptColors,
            borderColor: "#2563eb",
            backgroundColor: "rgba(37,99,235,0.10)",
            segment: {
                borderColor: ctx => yearColors[pointYears[ctx.p1DataIndex]] || "#2563eb"
            }
        };
    }

    if (charts[id]) {
        charts[id].data.labels = labels;
        charts[id].data.datasets = [dataset];
        if (charts[id].options.plugins.annotation) {
            charts[id].options.plugins.annotation.annotations = annotations || {};
        }
        charts[id].update();
    } else {
        charts[id] = new Chart(canvas, {
            type: type,
            data: { labels: labels, datasets: [dataset] },
            options: overviewOptions(type, annotations, id === "chartFlow")
        });
    }
}
// فونت‌های پررنگ برای باکس annotation
const FA_FONT_B  = { family: "'BNazanin', Tahoma, Arial", size: 13, weight: "bold" };
const NUM_FONT_B = { family: "'TimesNewRoman', 'Times New Roman', serif", size: 13, weight: "bold" };

function buildFlowAnnotations(rows, labels) {
    const annotations = {};

    // ✅ فقط وقتی یک چاه انتخاب شده، لیبل بزن
    if (rows.length !== 1) return annotations;

    const r = rows[0];
    let idx = 0;
    const ym = p => `${p.year}${String(p.month).padStart(2, "0")}`;

    function addLine(dateRaw, color, lines) {
        const parsed = parseJalaliDate(dateRaw);
        if (!parsed) return;
        
        function labelToYM(lbl) {
            let m = String(lbl).match(/^(\d{4})\/(\d{1,2})$/);
            if (m) return m[1] * 12 + (+m[2]);
            const parts = String(lbl).trim().split(/\s+/);
            if (parts.length === 2) {
                const midx = MONTHS.indexOf(parts[0]);
                if (midx !== -1 && /^\d{4}$/.test(parts[1])) return (+parts[1]) * 12 + (midx + 1);
            }
            return null;
        }
        
        const evVal = parsed.year * 12 + parsed.month;
        let labelIndex = -1, firstVal = Infinity, lastVal = -Infinity, firstIdx = 0, lastIdx = labels.length - 1;
        
        labels.forEach((lbl, i) => {
            const v = labelToYM(lbl);
            if (v == null) return;
            if (v < firstVal) { firstVal = v; firstIdx = i; }
            if (v > lastVal)  { lastVal = v;  lastIdx = i; }
            if (v === evVal) labelIndex = i;
        });
        
        if (labelIndex === -1) {
            if (evVal < firstVal) labelIndex = firstIdx;
            else if (evVal > lastVal) labelIndex = lastIdx;
            else return;
        }

        const title = Array.isArray(lines) ? lines[0] : String(lines);

        annotations["line" + idx] = {
            type: "line",
            scaleID: "x",
            value: labelIndex,
            borderColor: color,
            borderWidth: 3,
            _title: title,
            display: false,
            label: {
                display: false,
                position: idx % 2 === 0 ? "start" : "end",
                yAdjust: 8,
                backgroundColor: "rgba(255,255,255,0.92)",
                borderColor: color,
                borderWidth: 1.5,
                borderRadius: 6,
                color: color,
                padding: { top: 4, bottom: 4, left: 8, right: 8 },
                textAlign: "center",
                font: { family: "'TimesNewRoman', 'Times New Roman', serif", size: 13, weight: "bold" },
                content: lines
            }
        };
        idx++;
    }

    // ۱) دبی مجاز پیشنهادی (آبی) — با تاریخ پایان آزمایش
    const allowedRaw = getColByContains(r, "دبی", "پیشنهادی");
    const allowed = parseNum(allowedRaw);
    if (!isNaN(allowed) && allowed > 0) {
        const testRaw = getColByContains(r, "تاریخ پایان");  // دقیق تر: فقط "تاریخ پایان"
        if (testRaw) {
            const testParsed = parseJalaliDate(testRaw);
            if (testParsed) {
                addLine(testRaw, "#1d4ed8", [`آزمایش پمپاژ حفاری: ${allowed}`, ym(testParsed)]);
            }
        }
    }

    // ۲) تاریخ نصب الکتروپمپ (سبز)
    const pumpRaw = getColByContains(r, "نصب", "الکتروپمپ");
    if (pumpRaw) {
        const pumpParsed = parseJalaliDate(pumpRaw);
        if (pumpParsed) {
            addLine(pumpRaw, "#16a34a", ["نصب الکتروپمپ", ym(pumpParsed)]);
        }
    }

    // ۳) تاریخ آخرین بهسازی (نارنجی)
    const renovRaw = getColByContains(r, "تاریخ", "بهسازی");
    if (renovRaw) {
        const renovParsed = parseJalaliDate(renovRaw);
        if (renovParsed) {
            addLine(renovRaw, "#ea580c", ["بهسازی", ym(renovParsed)]);
        }
    }

    // ۴) دبی‌سنجی سالانه (تاریخ آزمایش + فشار + آبدهی)
    for (let y = 1400; y <= 1405; y++) {
        const dRaw = getColByContains(r, "تاریخ آزمایش", String(y));  // دقیقاً "تاریخ آزمایش {y}"
        if (!dRaw) continue;
        
        const dParsed = parseJalaliDate(dRaw);
        if (!dParsed) continue;
        
        const pres = parseNum(getColByContains(r, "فشار (atm)", String(y)));
        const yield_ = parseNum(getColByContains(r, "آبدهی", String(y)));

        const lines = [`دبی‌سنجی ${y}`, ym(dParsed)];
        if (!isNaN(yield_)) lines.push(`آبدهی: ${yield_} l/s`);
        if (!isNaN(pres))   lines.push(`فشار: ${pres} atm`);

        addLine(dRaw, "#7c3aed", lines);
    }

    return annotations;
}
// ---------- آپدیت چهار نمودار نمای کلی ----------
function updateCharts() {
    const office = document.getElementById("filterOffice")?.value || "all";
    const well   = document.getElementById("filterWell")?.value   || "all";

    const rows = wellsData.filter(r =>
        (office === "all" || r["اداره"] === office) &&
        (well   === "all" || normalizeFa(r["نام چاه"]) === normalizeFa(well)) &&
        (typeof _selectedWellType === "undefined" || _selectedWellType === "all" || getWellType(r) === _selectedWellType)
    );
    // متن باکس پروانه: فقط وقتی دقیقاً یک چاه انتخاب شده
    if (rows.length === 1) {
        const p = getColByContains(rows[0], "پروانه", "چاه");
        _permitBoxText = (p === undefined || p === null || String(p).trim() === "") ? "" : normalizeFa(p);
    } else {
        _permitBoxText = "";
    }
    const permitBadge = document.getElementById("permitBadge");
    if (permitBadge) {
        if (_permitBoxText) {
            permitBadge.textContent = "پروانه چاه: " + _permitBoxText;
            permitBadge.style.display = "inline-flex";
        } else {
            permitBadge.style.display = "none";
        }
    }

    const years = getSelectedChartYears();

    const prod = buildContinuousSeries(rows, years, "تولید", well === "all");
    const flow = buildContinuousSeries(rows, years, "دبی متوسط");
    const run  = buildContinuousSeries(rows, years, "کارکرد");
    const pres = buildContinuousSeries(rows, years, "فشار چاه");
    const flowAnnotations = buildFlowAnnotations(rows, flow.labels);

    upsertOverviewChart("chartProduction", "bar",  prod.labels, prod.data, prod.pointYears);
    upsertOverviewChart("chartFlow", "line", flow.labels, flow.data, flow.pointYears, flowAnnotations);
    applyFlowLabelVisibility();
    upsertOverviewChart("chartRuntime",    "line", run.labels,  run.data,  run.pointYears);
    upsertOverviewChart("chartPressure",   "line", pres.labels, pres.data, pres.pointYears);
    renderWellInfoBox();
    renderWellTimeline();
    renderContractorPerfTable();
}



// ---------------------------------------------------------
// گرادیان مشترک برای همه دیتاست‌ها
// ---------------------------------------------------------
function generateGradient(ctx) {
    const chart = ctx.chart;
    const { ctx: c, chartArea } = chart;

    if (!chartArea) return null;

    const gradient = c.createLinearGradient(
        0, chartArea.top,
        0, chartArea.bottom
    );

    gradient.addColorStop(0, "rgba(0,123,255,0.35)");
    gradient.addColorStop(1, "rgba(255,255,255,0)");

    return gradient;
}

// ------------------ توابع کمکی ----------------------
function base64ToArrayBuffer(base64) {

    const parts = base64.split(',');

    const binaryString = atob(parts[1]);

    const len = binaryString.length;

    const bytes = new Uint8Array(len);

    for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }

    return bytes.buffer;
}


function parseNum(v) {

    if (v === undefined || v === null)
        return NaN;

    const str =
        String(v).replace(/,/g, '');

    const num = parseFloat(str);

    return isNaN(num)
        ? NaN
        : num;
}
function std(values){

const avg =
values.reduce((a,b)=>a+b,0)/values.length;

const squareDiffs =
values.map(v => Math.pow(v-avg,2));

const avgSquareDiff =
squareDiffs.reduce((a,b)=>a+b,0)/values.length;

return Math.sqrt(avgSquareDiff);

}

function colorizeCell(td, value, min, max){
    if(isNaN(value)) return;

    const ratio = (value - min) / (max - min + 0.00001);

    const r = Math.floor(255 * ratio);
    const g = Math.floor(255 * (1 - ratio));

    td.style.backgroundColor = `rgb(${r}, ${g}, 80, 0.3)`;
}


function fNum(v, d) {

    if (
        v === undefined ||
        v === null ||
        isNaN(v)
    ) {
        return "-";
    }

    return v.toLocaleString("fa-IR", {

        minimumFractionDigits: d,

        maximumFractionDigits: d

    });
}
document.querySelectorAll("#statsTable th").forEach((th, i)=>{
    th.addEventListener("click", ()=>{
        sortTable(i);
    });
});

function sortTable(col){
    const table = document.getElementById("statsTable");
    const tbody = table.tBodies[0];

    const rows = Array.from(tbody.querySelectorAll("tr"));

    const sorted = rows.sort((a,b)=>{
        const A = parseFloat(a.children[col].textContent) || a.children[col].textContent;
        const B = parseFloat(b.children[col].textContent) || b.children[col].textContent;
        return A > B ? 1 : -1;
    });

    sorted.forEach(r => tbody.appendChild(r));
}
function downloadStatsExcel(){

    const table = document.getElementById("statsTable");

    let wb = XLSX.utils.book_new();
    let ws = XLSX.utils.table_to_sheet(table);

    XLSX.utils.book_append_sheet(wb, ws, "آمار مراکز");

    XLSX.writeFile(wb, "خلاصه آماری مراکز.xlsx");
}
function downloadFlowChangeExcel() {

    const table = document.getElementById("groupFlowTable");

    if (!table) {
        alert("❌ جدول تحلیل تغییرات دبی پیدا نشد");
        return;
    }

    const wb = XLSX.utils.book_new();
    const ws = XLSX.utils.table_to_sheet(table);

    XLSX.utils.book_append_sheet(wb, ws, "تغییرات دبی");

    XLSX.writeFile(wb, "جدول_تحلیل_تغییرات_دبی.xlsx");
}

function downloadDrillingExcel(){

    const table = document.getElementById("drillResultsTable");
    const wb = XLSX.utils.table_to_book(table, {sheet:"Drilling"});
    XLSX.writeFile(wb, "گزارش_حفاری.xlsx");
}

function drawWellsByOffice(){

const offices=[...new Set(wellsData.map(r=>r["اداره"]))];

const counts=[];

const colors=[
"#e74c3c",
"#3498db",
"#2ecc71",
"#f39c12",
"#9b59b6",
"#1abc9c",
"#e67e22",
"#34495e",
"#fd79a8",
"#6c5ce7"
];

offices.forEach(o=>{

const c=wellsData.filter(r=>r["اداره"]===o).length;

counts.push(c);

});

if(charts["chartWellsByOffice"])
charts["chartWellsByOffice"].destroy();

charts["chartWellsByOffice"]=new Chart(

document.getElementById("chartWellsByOffice"),

{
type:"bar",

data:{
labels:offices,

datasets:[{

label:"تعداد چاه",

data:counts,

backgroundColor:offices.map((_,i)=>
colors[i % colors.length]
)

}]
},

options:{
    responsive: true,
    maintainAspectRatio: false,
    animation: getAnimConfig("bar"),
    plugins:{
        legend: { labels: { font: FA_FONT } },
        tooltip: { ...TOOLTIP_BASE }
    },
    scales:{
        x: { ticks: { font: NUM_FONT }, beginAtZero: true },
        y: { ticks: { font: FA_FONT } }
    }
}

}

);

}
function drawProductionRanking(){

const year=
document.getElementById("boxYearFilter").value;

const offices=
[...new Set(wellsData.map(r=>r["اداره"]))];

const officeTotals=[];

offices.forEach(o=>{

const rows=
wellsData.filter(r=>r["اداره"]===o);

let total=0;

rows.forEach(r=>{

total+=
parseNum(r[`تولید سال ${year}`])||0;

});

officeTotals.push(total);

});

if(charts["chartBoxProduction"])
charts["chartBoxProduction"].destroy();

charts["chartBoxProduction"]=new Chart(

document.getElementById("chartBoxProduction"),

{
type:"bar",

data:{

labels:offices,

datasets:[{

label:`تولید ${year}`,

data:officeTotals,

backgroundColor:offices.map((_,i)=>[
"#ff6b6b",
"#4ecdc4",
"#45b7d1",
"#96ceb4",
"#feca57",
"#5f27cd",
"#54a0ff",
"#10ac84"
][i % 8])


}]

},

options:{

responsive:true,

plugins:{
legend:{
labels:{
font:{
family:"BNazanin"
}
}
}
},

scales:{

x:{
ticks:{
font:{
family:"BNazanin",
size:13
}
}
},

y:{
ticks:{
font:{
family:"Times New Roman",
size:12
}
}
}

}

}

}

);

}
function drawOfficeRanking() {
    const year = document.getElementById("rankingYearFilter")?.value || "1404";
    const offices = [...new Set(wellsData.map(r => r["اداره"]))];
    let data = [];

    offices.forEach(o => {
        const rows = wellsData.filter(r => r["اداره"] === o);
        let total = 0, cnt = 0;
        rows.forEach(r => {
            const v = parseNum(r[`کارکرد سال ${year}`]);
            if (!isNaN(v)) { total += v; cnt++; }
        });
        // میانگین کارکرد هر چاه (نرمال‌شده نسبت به تعداد چاه)
        data.push({ office: o, total: cnt ? total / cnt : 0 });
    });

    data.sort((a, b) => b.total - a.total);

    if (charts["chartOfficeRanking"]) charts["chartOfficeRanking"].destroy();
    charts["chartOfficeRanking"] = new Chart(document.getElementById("chartOfficeRanking"), {
        type: "bar",
        data: {
            labels: data.map(d => d.office),
            datasets: [{
                label: "میانگین کارکرد هر چاه",
                data: data.map(d => d.total),
                backgroundColor: data.map((_, i) => ["#e74c3c", "#3498db", "#2ecc71", "#f1c40f", "#9b59b6", "#1abc9c", "#e67e22", "#34495e"][i % 8])
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            animation: getAnimConfig("bar"),
            plugins:{
                legend: { labels: { font: FA_FONT } },
                tooltip: { ...TOOLTIP_BASE }
            },
            scales:{
                x: { ticks: { font: NUM_FONT }, beginAtZero: true },
                y: { ticks: { font: FA_FONT } }
            }
        }
    });
}

function drawCompareCharts(){

const offices =
[...new Set(wellsData.map(r=>r["اداره"]))];

const colors=[
"#e74c3c",
"#3498db",
"#2ecc71",
"#f39c12",
"#9b59b6",
"#1abc9c",
"#e67e22",
"#34495e"
];

const years = ALL_YEARS.map(String);

const configs=[

{
id:"compareProduction",
field:"تولید سال ",
label:"تولید"
},

{
id:"compareRuntime",
field:"کارکرد سال ",
label:"کارکرد"
},

{
id:"comparePressure",
field:"فشار سال ",
label:"فشار"
},

{
id:"compareFlow",
field:"دبی متوسط سال ",
label:"دبی متوسط"
}

];

configs.forEach(cfg=>{

const datasets=[];

offices.forEach((office,index)=>{

const rows =
wellsData.filter(r=>r["اداره"]===office);

const data=[];

years.forEach(y=>{

let total=0;
let count=0;

rows.forEach(r=>{
const ft = cfg.label === "تولید" ? "تولید"
         : cfg.label === "کارکرد" ? "کارکرد"
         : cfg.label === "فشار" ? "فشار" : "دبی";
const v = yearlyValue(r, ft, y);
if(!isNaN(v)){ total+=v; count++; }
});

data.push(
count ? total/count : null
);

});

datasets.push({

label:office,

data:data,

borderColor:colors[index % colors.length],

backgroundColor:"rgba(255,255,255,0.05)",

fill:true,

tension:0.45,

borderWidth:3,

pointRadius:3

});

});

if(charts[cfg.id])
charts[cfg.id].destroy();

charts[cfg.id]=new Chart(

document.getElementById(cfg.id),

{

type:"line",

data:{
labels:years,
datasets:datasets
},

options:{
    responsive: true,
    maintainAspectRatio: false,
    animation: getAnimConfig("line"),
    plugins:{
        legend:{
            position: 'top',
            labels: { font: FA_FONT }
        },
        tooltip: {
            ...TOOLTIP_BASE,
            mode: 'index',
            intersect: false
        }
    },
    scales:{
        x: { ticks: { font: FA_FONT } },
        y: { beginAtZero: true, ticks: { font: NUM_FONT } }
    }
}

}

);

});

}


function drawCompareEfficiency() {
    const year = document.getElementById("effYearFilter")?.value || "1404";
    const years = year === "all" ? ALL_YEARS : [Number(year)];
    const offices = [...new Set(wellsData.map(r => r["اداره"]))];
    let data = [];

    // ۱. تعریف پالت رنگی برای استفاده در نمودار
    const uniqueColors = [
        "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", 
        "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe"
    ];

    offices.forEach(o => {
        const rows = wellsData.filter(r => r["اداره"] === o);
        let prod = 0;
        let runtime = 0;
        rows.forEach(r => {
            years.forEach(y => {
                prod += parseNum(r[`تولید سال ${y}`]) || 0;
                runtime += parseNum(r[`کارکرد سال ${y}`]) || 0;
            });
        });
        data.push(runtime ? prod / runtime : 0);
    });

    if (charts["compareEfficiency"]) charts["compareEfficiency"].destroy();

    charts["compareEfficiency"] = new Chart(
        document.getElementById("compareEfficiency"),
        {
            type: "bar",
            data: {
                labels: offices,
                datasets: [{
                    label: "راندمان",
                    data: data,
                    // ۲. نگاشت رنگ‌ها به هر میله (استفاده از باقی‌مانده تقسیم برای تکرار رنگ‌ها اگر تعداد ادارات بیشتر بود)
                    backgroundColor: offices.map((_, i) => uniqueColors[i % uniqueColors.length])
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: getAnimConfig("bar"),
                plugins: {
                    legend: { labels: { font: FA_FONT } },
                    tooltip: { ...TOOLTIP_BASE }
                },
                scales: {
                    x: { ticks: { font: FA_FONT } },
                    y: { beginAtZero: true, ticks: { font: NUM_FONT } }
                }
            }
        }
    );
}


function getPressureValue(row, year) {

    const keys = Object.keys(row);

    const pressureKey = keys.find(k =>
        k.includes(`فشار چاه ${year}`)
    );

    if (!pressureKey) return NaN;

    return parseNum(row[pressureKey]);
}

function drawPressureDrop(){

const year =
document.getElementById("pressureDropYearFilter")?.value || "1404";

const years =
year==="all" ? ALL_YEARS : [Number(year)];

const offices=[...new Set(wellsData.map(r=>r["اداره"]))];

let data=[];

offices.forEach(o=>{

const rows=wellsData.filter(r=>r["اداره"]===o);

let pStart=0;
let pEnd=0;
let c1=0;
let c2=0;

rows.forEach(r=>{

const first = getPressureValue(r, 1399);

years.forEach(y=>{

const current = getPressureValue(r, y);

if(!isNaN(first)){pStart+=first;c1++;}
if(!isNaN(current)){pEnd+=current;c2++;}

});

});

pStart=c1?pStart/c1:0;
pEnd=c2?pEnd/c2:0;

data.push(pEnd-pStart);

});

if(charts["comparePressureDrop"])
charts["comparePressureDrop"].destroy();

charts["comparePressureDrop"]=new Chart(

document.getElementById("comparePressureDrop"),

{

type:"bar",

data:{
labels:offices,
datasets:[{
label:"افت فشار",
data:data,
backgroundColor:"#ea09f1"
}]
},

options:{
    responsive: true,
    maintainAspectRatio: false,
    animation: getAnimConfig("bar"),
    plugins:{
        legend: { labels: { font: FA_FONT } },
        tooltip: { ...TOOLTIP_BASE }
    },
    scales:{
        x: { ticks: { font: FA_FONT } },
        y: { beginAtZero: true, ticks: { font: NUM_FONT } }
    }
}

}

);

}



/* =========================================
   GROUP TAB
========================================= */

function initGroupFilters(){
    fillGroupYear();
    fillGroupOffice();

    updateDependentFilters(); // ✅ فقط این

    setupGroupListeners();
    updateGroupSection();
    renderPostTestSection();
}


function fillGroupYear(){

const select =
document.getElementById("groupYear");

if(!select) return;

select.innerHTML =
'<option value="all">همه سال‌ها</option>';

ALL_YEARS.forEach(y=>{

const op=document.createElement("option");

op.value=y;
op.textContent=y;

select.appendChild(op);

});

}

function fillGroupOffice(){

if (!wellsData) return;    

const select =
document.getElementById("groupOffice");

if(!select) return;

select.innerHTML =
'<option value="all">همه ادارات</option>';

const offices=[
...new Set(
wellsData.map(r=>r["اداره"])
)
];

offices.forEach(o=>{

const op=document.createElement("option");

op.value=o;
op.textContent=o;

select.appendChild(op);

});

}

function fillGroupWell() {
    if (!wellsData) return;
    const select = document.getElementById("groupWell");
    if (!select) return;

    const office   = document.getElementById("groupOffice")?.value   || "all";
    const mainZone = document.getElementById("groupMainZone")?.value || "all";
    const subZone  = document.getElementById("groupSubZone")?.value  || "all";

    let data = wellsData.filter(r => {
        const matchOffice   = (office   === "all" || r["اداره"]      === office);
        const matchMainZone = (mainZone === "all" || r["پهنه اصلی"]  === mainZone);
        const matchSubZone  = (subZone  === "all" || r["زیر پهنه"]   === subZone);
        return matchOffice && matchMainZone && matchSubZone;
    });

    select.innerHTML = '<option value="all">همه چاه‌ها</option>';

    const wells = [...new Set(data.map(r => r["نام چاه"]).filter(Boolean))];

    wells.forEach(w => {
        const op = document.createElement("option");
        op.value = w;
        op.textContent = w;
        select.appendChild(op);
    });
}


function setupGroupListeners() {

    // 1) لیسنرهای ساده که فقط updateGroupSection را صدا می‌کنند
    const ids = [
        "groupYear",
        "groupMonth",
        "groupWell",
        "statusFilter",
        "groupYearPerf",
        "groupYearProd",
        "groupYearPress",
        // "groupMainZone",  // حذف شد، چون لیسنر اختصاصی دارد
        // "groupSubZone",   // حذف شد، چون لیسنر اختصاصی دارد
        "groupYearRank"
    ];  

    ids.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener("change", updateGroupSection);
    });

    // 2) لیسنر فیلتر اداره
    const officeEl = document.getElementById("groupOffice");
    if (officeEl) {
        officeEl.addEventListener("change", () => {
            updateDependentFilters();  // اگر قبلاً داشتی، همان بماند
            fillGroupWell();          // چاه‌ها بر اساس اداره + پهنه + زیرپهنه
            updateGroupSection();
        });
    }

    // 3) لیسنر پهنه اصلی
    const mainZoneEl = document.getElementById("groupMainZone");
    if (mainZoneEl) {
        mainZoneEl.addEventListener("change", () => {
            updateSubZoneFilter();     // زیرپهنه‌ها را بر اساس پهنه اصلی آپدیت کن
            fillGroupWell();          // چاه‌ها را بعد از تغییر پهنه آپدیت کن
            updateGroupSection();
        });
    }

    // 4) لیسنر زیرپهنه
    const subZoneEl = document.getElementById("groupSubZone");
    if (subZoneEl) {
        subZoneEl.addEventListener("change", () => {
            fillGroupWell();          // چاه‌ها بر اساس زیرپهنه آپدیت شوند
            updateGroupSection();
        });
    }
}

function calculateFlowChanges(data){

function calcPercent(base,current){

if(isNaN(base) || base === 0 || isNaN(current)){
return NaN;
}

return ((current - base) / base) * 100;

}

return data.map(row=>{

const flow1399 =
parseNum(row["دبی متوسط سال 1399"]);

const flow1400 =
parseNum(row["دبی متوسط سال 1400"]);

const flow1401 =
parseNum(row["دبی متوسط سال 1401"]);

const flow1402 =
parseNum(row["دبی متوسط سال 1402"]);

const flow1403 =
parseNum(row["دبی متوسط سال 1403"]);

const flow1404 =
parseNum(row["دبی متوسط سال 1404"]);

const change1400 =
calcPercent(flow1399,flow1400);

const change1401 =
calcPercent(flow1399,flow1401);

const change1402 =
calcPercent(flow1399,flow1402);

const change1403 =
calcPercent(flow1399,flow1403);

const change1404 =
calcPercent(flow1399,flow1404);

let status = "نامشخص";

if(!isNaN(change1404)){

status = "پایدار";

if(change1404 <= -20){

status = "بحرانی";

}
else if(change1404 >= 10){

status = "بهبود یافته";

}

}

return{

well:row["نام چاه"],

flow1399:flow1399,
flow1400:flow1400,
flow1401:flow1401,
flow1402:flow1402,
flow1403:flow1403,
flow1404:flow1404,

change1400:change1400,
change1401:change1401,
change1402:change1402,
change1403:change1403,
change1404:change1404,

status:status

};

});

}



function getGroupFilteredData(){

if (!wellsData || wellsData.length === 0) return []; 

const office =
document.getElementById("groupOffice")?.value || "all";

const well =
document.getElementById("groupWell")?.value || "all";

const mainZone =
document.getElementById("groupMainZone")?.value || "all";

const subZone =
document.getElementById("groupSubZone")?.value || "all";

return wellsData.filter(r=>{

return(

(office==="all" || r["اداره"]===office)

&&

(well==="all" || r["نام چاه"]===well)

&&

(mainZone==="all" || r["پهنه اصلی"]===mainZone)

&&

(subZone==="all" || r["زیر پهنه"]===subZone)

&&

(typeof _selectedWellType === "undefined" || _selectedWellType === "all" || getWellType(r) === _selectedWellType)

);

});

}


function updateGroupSection(){

const data =
getGroupFilteredData();

const results =
calculateFlowChanges(data);

drawGroupFlowTrend(data);

drawFlowChangeChart(results);

renderFlowTable(results);

renderStatusSummary(results);


drawGroupQuadrant(data);
drawGroupExpectedVsActual(data);
drawGroupProductionTrend(data);
drawGroupYearlyProductionTrend(data); // <-- خط جدید اینجا اضافه شد
drawGroupPressureTrend(data);
drawGroupPressureLoss(data);
drawGroupRadar(data);
drawGroupRanking(data);

}


let groupFlowTrendChart = null;

function drawGroupFlowTrend(data){

const ctx =
document.getElementById("groupFlowTrend");

if(!ctx) return;

const years=[1400,1401,1402,1403,1404];

const values = years.map(y=>{

let changes=[];

data.forEach(r=>{

const base =
parseNum(r["دبی متوسط سال 1399"]);

const current =
parseNum(r[`دبی متوسط سال ${y}`]);

if(!isNaN(base) && base!==0 && !isNaN(current)){

const change =
((current-base)/base)*100;

changes.push(change);

}

});

if(!changes.length) return 0;

return changes.reduce((a,b)=>a+b,0)/changes.length;

});

if(groupFlowTrendChart){
groupFlowTrendChart.destroy();
}

groupFlowTrendChart = new Chart(ctx,{

type:"line",

data:{
labels:years,

datasets:[{

label:"میانگین درصد تغییر دبی",

data:values,

borderColor:"#2563eb",

backgroundColor:"rgba(37,99,235,0.2)",

fill:true,

tension:0.4,

borderWidth:3,

pointRadius:5

}]

},

options:{
    responsive: true,
    maintainAspectRatio: false,
    animation: getAnimConfig("line"),
    plugins:{
        legend: { labels: { font: FA_FONT } },
        tooltip: { ...TOOLTIP_BASE, mode:'index', intersect:false }
    },
    scales:{
        x: { ticks: { font: FA_FONT } },
        y: {
            ticks: { font: NUM_FONT, callback: v => v + "%" }
        }
    }
}

});

}


let groupFlowChangeChart = null;

function drawFlowChangeChart(results){

const ctx =
document.getElementById("groupFlowChange");

if(!ctx) return;

const sorted = [...results]
.filter(r => !isNaN(r.change1404))
.sort((a,b)=>b.change1404-a.change1404)



if(groupFlowChangeChart){
groupFlowChangeChart.destroy();
}

groupFlowChangeChart = new Chart(ctx,{

type:"bar",

data:{

labels:sorted.map(r=>r.well),

datasets:[{

label:"درصد تغییر دبی",

data:sorted.map(r=>r.change1404),

backgroundColor:sorted.map(r=>
r.change1404 < 0

? "#ef4444"
: "#16a34a"
),

borderRadius:6

}]

},

options:{
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: "y",
    animation: { duration: 1500 },
    plugins:{
        legend: { display: false },
        tooltip: { ...TOOLTIP_BASE }
    },
    scales:{
        x: { ticks: { font: NUM_FONT, callback: v => v + "%" } },
        y: { ticks: { font: FA_FONT } }
    }
}

});

}

function renderFlowTable(results){

const tbody =
document.querySelector(
"#groupFlowTable tbody"
);

if(!tbody) return;
const statusFilter =
document.getElementById("statusFilter")?.value || "all";

tbody.innerHTML = "";
let filtered = results;

if(statusFilter === "بحرانی۷۰"){

filtered = results.filter(r => {

const flow1399 = r.flow1399;
const flow1404 = r.flow1404;

if(!isNaN(flow1399) && flow1399 !== 0 && !isNaN(flow1404)){

        const change = ((flow1404 - flow1399) / flow1399) * 100;

        return change <= -70;
    }

return false;

});

}
else if(statusFilter !== "all"){

filtered =
results.filter(r => r.status === statusFilter);

}


filtered.forEach((r,index)=>{

let color = "#16a34a";
let bg = "#dcfce7";

if(r.status==="بحرانی"){

color="#b91c1c";
bg="#fee2e2";

}
else if(r.status==="پایدار"){

color="#92400e";
bg="#fef3c7";

}
else if(r.status==="بهبود یافته"){

color="#166534";
bg="#dcfce7";

}
else{

color="#374151";
bg="#f3f4f6";

}

tbody.innerHTML += `

<tr style="
background:${bg};
transition:0.3s;
">
<td>${r.well || "-"}</td>

<td>${r.flow1399?.toFixed(1) || "-"}</td>

<td>${r.flow1400?.toFixed(1) || "-"}</td>
<td style="font-weight:bold;color:${color};">
${isNaN(r.change1400) ? "-" : r.change1400.toFixed(1)+"%"}
</td>

<td>${r.flow1401?.toFixed(1) || "-"}</td>
<td style="font-weight:bold;color:${color};">
${isNaN(r.change1401) ? "-" : r.change1401.toFixed(1)+"%"}
</td>

<td>${r.flow1402?.toFixed(1) || "-"}</td>
<td style="font-weight:bold;color:${color};">
${isNaN(r.change1402) ? "-" : r.change1402.toFixed(1)+"%"}
</td>

<td>${r.flow1403?.toFixed(1) || "-"}</td>
<td style="font-weight:bold;color:${color};">
${isNaN(r.change1403) ? "-" : r.change1403.toFixed(1)+"%"}
</td>

<td>${r.flow1404?.toFixed(1) || "-"}</td>
<td style="font-weight:bold;color:${color};">
${isNaN(r.change1404) ? "-" : r.change1404.toFixed(1)+"%"}
</td>


<td style="
color:${color};
font-weight:bold;
">

${r.status}

</td>

</tr>

`;

});

}

// =========================
// دکمه نمایش / مخفی جدول
// =========================

document.addEventListener("DOMContentLoaded", () => {

const btn =
document.getElementById("toggleFlowTable");

const box =
document.getElementById("flowTableContainer");

if(btn && box){

btn.addEventListener("click", () => {

box.classList.toggle("active");

if(box.classList.contains("active")){

btn.textContent = "مخفی کردن جدول";

}else{

btn.textContent = "نمایش جدول";

}

});

}

});
function renderStatusSummary(results) {

    const summary = {
    "بحرانی": 0,
    "بحرانی۷۰": 0,
    "پایدار": 0,
    "بهبود یافته": 0,
    "نامشخص": 0
};


    results.forEach(r => {
        if (summary[r.status] !== undefined) {
            summary[r.status]++;
        }
        if (!isNaN(r.change1404) && r.change1404 <= -70) {
    summary["بحرانی۷۰"]++;
}

    /* محاسبه درصد تغییر واقعی */
const flow1399 = r.flow1399;
const flow1404 = r.flow1404;

if(!isNaN(flow1399) && flow1399 !== 0 && !isNaN(flow1404)){
    const change = ((flow1404 - flow1399) / flow1399) * 100;
    if(change <= -70){
        summary["بحرانی۷۰"]++;
    }

/* اگر افت بیشتر از 70 درصد باشد */
if(change <= -70){
summary["بحرانی۷۰"]++;
}

}
    });
    

    const container = document.getElementById("statusSummary");

    container.innerHTML = `
    <div class="status-box status-critical">بحرانی: ${summary["بحرانی"]}</div>
    <div class="status-box status-orange">بحرانی ۷۰٪+: ${summary["بحرانی۷۰"]}</div>
    <div class="status-box status-stable">پایدار: ${summary["پایدار"]}</div>
    <div class="status-box status-improved">بهبود یافته: ${summary["بهبود یافته"]}</div>
    <div class="status-box status-unknown">نامشخص: ${summary["نامشخص"]}</div>
`;

}


function drawGroupQuadrant(data) {
  const canvas = document.getElementById("groupQuadrant");
  if (!canvas) return;

  const selectedYear =
    document.getElementById("groupYearPerf")?.value || "1404";

  if (selectedYear === "all") return;

  const year = Number(selectedYear);
  // تعداد ماه‌های دارای داده در همین سال (برای سال ناقص مثل ۱۴۰۵)
  let monthsWithData = 0;
  MONTHS.forEach(m => {
      const has = data.some(r => {
          const v = parseNum(r[`تولید ${year}(${m})`]);
          return !isNaN(v) && v > 0;
      });
      if (has) monthsWithData++;
  });
  if (monthsWithData === 0) monthsWithData = 12;   // اگر داده‌ی ماهانه نبود، فرض سال کامل
  const yearFraction = monthsWithData / 12;        // کسری از سال که داده دارد

  let points = [];
  let flows = [];
  let hoursList = [];

  data.forEach(r => {
    const flow = parseNum(r[`دبی متوسط سال ${year}`]);
    const production = parseNum(r[`تولید سال ${year}`]);
    const hours = parseNum(r[`کارکرد سال ${year}`]); // <-- اگر نام ستون فرق دارد اینجا را عوض کنید

    if (!isNaN(flow) && !isNaN(production) && flow > 0) {
      points.push({
        x: flow,
        y: production,
        label: r["نام چاه"],
        hours: hours
      });

      flows.push(flow);
      if (!isNaN(hours)) hoursList.push(hours);
    }
  });

  if (points.length === 0 || flows.length === 0) return;

  // -------------------------------------------------
  // محاسبه hbar
  // -------------------------------------------------
  const hbar = hoursList.length > 0
    ? hoursList.reduce((a, b) => a + b, 0) / hoursList.length
    : 0;

  // -------------------------------------------------
  // شیب خط‌ها
  // -------------------------------------------------
  const A_GREEN = 3.6 * 24 * 365 * yearFraction;   // متناسب با ماه‌های موجود
  const A_YELLOW = 3.6 * hbar;

  // -------------------------------------------------
  // بازه x و خطوط
  // -------------------------------------------------
  const xMax = Math.max(...flows) * 1.1;
  const lineX = [0, xMax];

  const greenLine = lineX.map(x => A_GREEN * x);
  const yellowLine = lineX.map(x => A_YELLOW * x);

  // -------------------------------------------------
  // انتگرال‌ها
  // -------------------------------------------------
  // ∫0..xMax a*x dx = a*xMax^2 / 2
  const areaGreen = (A_GREEN * xMax * xMax) / 2;
  const areaYellow = (A_YELLOW * xMax * xMax) / 2;

  const overallGapPercent = areaGreen !== 0
    ? ((areaYellow - areaGreen) / areaGreen) * 100
    : 0;

  // -------------------------------------------------
  // حذف نمودار قبلی
  // -------------------------------------------------
  if (charts["groupQuadrant"]) charts["groupQuadrant"].destroy();

  // -------------------------------------------------
  // پلاگین باکس رنگی گوشه نمودار
  // -------------------------------------------------
  const gapBoxPlugin = {
    id: "gapBoxPlugin",
    afterDraw(chart) {
      const { ctx } = chart;
      const { top, right } = chart.chartArea;

      const boxW = 140;
      const boxH = 70;
      const x = right - boxW - 440;
      const y = top ;

      ctx.save();

      // باکس
      ctx.fillStyle = "rgba(255,255,255,0.92)";
      ctx.strokeStyle = "#94a3b8";
      ctx.lineWidth = 1;

      if (ctx.roundRect) {
        ctx.beginPath();
        ctx.roundRect(x, y, boxW, boxH, 8);
        ctx.fill();
        ctx.stroke();
      } else {
        ctx.fillRect(x, y, boxW, boxH);
        ctx.strokeRect(x, y, boxW, boxH);
      }

      // متن
      ctx.textAlign = "right";

      ctx.fillStyle = "#0f172a";
      ctx.font = "bold 12px Vazir, Tahoma, Arial";
      ctx.fillText("اختلاف انتگرالی کل", x + boxW - 14, y + 22);

      ctx.fillStyle = overallGapPercent >= 0 ? "#eab308" : "#ef4444";
      ctx.font = "bold 13px Vazir, Tahoma, Arial";
      ctx.fillText(`${overallGapPercent.toFixed(1)}%`, x + boxW - 14, y + 46);

      ctx.fillStyle = "#334155";
      ctx.font = "11px Vazir, Tahoma, Arial";
      ctx.fillText("(زرد - سبز) / سبز", x + boxW - 14, y + 62);

      ctx.restore();
    }
  };

  // -------------------------------------------------
  // ساخت نمودار
  // -------------------------------------------------
  charts["groupQuadrant"] = new Chart(canvas, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "چاه‌ها",
          data: points,
          backgroundColor: "#0703f0",
          pointRadius: 5,
          zIndex: 10
        },
        {
          type: "line",
          label: "خط سبز (ایده‌آل)",
          data: lineX.map((x, i) => ({ x, y: greenLine[i] })),
          borderColor: "#22c55e",
          borderWidth: 3,
          fill: false,
          pointRadius: 0
        },
        {
          type: "line",
          label: "خط زرد (واقعی)",
          data: lineX.map((x, i) => ({ x, y: yellowLine[i] })),
          borderColor: "#facc15",
          borderWidth: 3,
          borderDash: [6, 4],
          fill: false,
          pointRadius: 0
        }
      ]
    },
    options: {
      responsive: true,
      plugins: {
        gapBoxPlugin: {},
        tooltip: {
          rtl: true,
          callbacks: {
            label: function(ctx) {
              if (ctx.dataset.type === "line") return "";

              const x = ctx.raw.x;
              const y = ctx.raw.y;
              const label = ctx.raw.label;

              // مقدار خط‌ها در همان x
              const yGreen = A_GREEN * x;
              const yYellow = A_YELLOW * x;

              // درصد اختلاف انتگرالی کل
              const gapText = `اختلاف انتگرالی کل: ${overallGapPercent.toFixed(1)}%`;

              // درصد فاصله نقطه از خط سبز
              const localDiff = yGreen !== 0 ? ((y - yGreen) / yGreen) * 100 : 0;

              return [
                `چاه: ${label}`,
                `دبی: ${x.toFixed(1)} L/s`,
                `تولید سال ${year}: ${y.toLocaleString()} m³`,
                `فاصله از خط سبز: ${localDiff.toFixed(1)}%`,
                gapText
              ];
            }
          }
        },
        legend: {
          labels: {
            font: { family: "Vazir, Tahoma, Arial" }
          }
        }
      },
      scales: {
        x: {
          title: { display: true, text: "دبی (L/s)" },
          beginAtZero: true
        },
        y: {
          title: { display: true, text: `تولید سال ${year} (m³)` },
          beginAtZero: true
        }
      }
    },
    plugins: [gapBoxPlugin]
  });
}


let groupExpectedVsActualChart = null;

function drawGroupExpectedVsActual(data) {
    const ctx = document.getElementById("groupExpectedVsActual");
    if (!ctx) return;

    const selectedYear = document.getElementById("groupYearPerf")?.value || "all";
    
    // تعیین لیست سال‌هایی که باید نمایش داده شوند
    let yearsToShow = [];
    if (selectedYear === "all") {
        yearsToShow = ["1399","1400","1401", "1402", "1403", "1404"]; // لیست تمام سال‌ها
    } else {
        yearsToShow = [selectedYear]; // فقط سال انتخاب شده
    }

    const actualArr = [];
    const expectedArr = [];

    
    // محاسبه مقادیر برای هر سال به صورت مجزا
    yearsToShow.forEach(year => {
        let yearlyActual = 0;
        let yearlyExpected = 0;

        // تعداد ماه‌های دارای داده در همین سال (برای سال ناقص مثل ۱۴۰۵)
        let monthsWithData = 0;
        MONTHS.forEach(m => {
            const has = data.some(r => {
                const v = parseNum(r[`تولید ${year}(${m})`]);
                return !isNaN(v) && v > 0;
            });
            if (has) monthsWithData++;
        });
        if (monthsWithData === 0) monthsWithData = 12;   // اگر داده‌ی ماهانه نبود، فرض سال کامل
        const yearFraction = monthsWithData / 12;

        data.forEach(r => {
            const flow = parseNum(r[`دبی متوسط سال ${year}`]);
            const actual = parseNum(r[`تولید سال ${year}`]);

            if (!isNaN(actual)) yearlyActual += actual;
            if (!isNaN(flow)) {
                // فرمول تولید مورد انتظار، متناسب با ماه‌های موجود همان سال
                const exp = flow * 3.6 * 24 * 365 * yearFraction;
                yearlyExpected += exp;
            }
        });

        actualArr.push(yearlyActual);
        expectedArr.push(yearlyExpected);
    });

    // حذف نمودار قبلی برای جلوگیری از تداخل
    if (groupExpectedVsActualChart) groupExpectedVsActualChart.destroy();

    groupExpectedVsActualChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: yearsToShow, // سال‌ها در محور X قرار می‌گیرند
            datasets: [
                {
                    label: "تولید واقعی",
                    data: actualArr,
                    backgroundColor: "#22c55e",
                    borderRadius: 5
                },
                {
                    label: "تولید مورد انتظار",
                    data: expectedArr,
                    backgroundColor: "#94a3b8",
                    borderRadius: 5
                }
            ]
        },
        options: {
            responsive: true,
            animation: getAnimConfig("bar"),
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    rtl: true,
                    labels: { font: FA_FONT }
                },
                tooltip: {
                    ...TOOLTIP_BASE,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) label += ': ';
                            if (context.parsed.y !== null) {
                                label += new Intl.NumberFormat('fa-IR').format(Math.round(context.parsed.y)) + ' مترمکعب';
                            }
                            return label;
                        },
                        afterLabel: function (context) {
                            const index = context.dataIndex;
                            const actual = actualArr[index];
                            const expected = expectedArr[index];
                            if (expected > 0) {
                                const diff = ((actual - expected) / expected) * 100;
                                return `اختلاف: ${diff.toFixed(1)}%`;
                            }
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        font: NUM_FONT,
                        callback: function(value) {
                            return new Intl.NumberFormat('fa-IR').format(value);
                        }
                    }
                },
                x: {
                    ticks: { font: FA_FONT }
                }
            }
        }
    });
}

let groupProductionTrendChart = null;  // ✅ این خط را اضافه کن

function drawGroupProductionTrend(data) {
    const ctx = document.getElementById("groupProductionTrend");
    if (!ctx) return;

    const selectedYear = document.getElementById("groupYearProd")?.value || "1404";
    const yearsToDraw = selectedYear === "all" ? ALL_YEARS : [Number(selectedYear)];

    const months = MONTHS;
    const datasets = [];

    // رنگ‌های منحصر به فرد برای هر سال
    const colors = [
        '#3b82f6', '#ef4444', '#f59e0b', '#10b981', '#6366f1', '#a855f7'
    ];

    yearsToDraw.forEach((year, yearIndex) => {
        let monthlyTotals = new Array(12).fill(0);

        data.forEach(r => {
            months.forEach((m, i) => {
                const productionValue = parseNum(r[`تولید ${year}(${m})`]);
                if (!isNaN(productionValue)) {
                    monthlyTotals[i] += productionValue;
                }
            });
        });

        datasets.push({
            label: `مجموع تولید ${year}`,
            data: monthlyTotals,
            borderColor: colors[yearIndex % colors.length],
            backgroundColor: colors[yearIndex % colors.length] + '40', // 40% opacity
            fill: true,
            tension: 0.4,
            hidden: (selectedYear === "all" && year !== 1404) // بقیه سال‌ها مخفی باشند مگر اینکه روی all باشیم
        });
    });

    if (groupProductionTrendChart) {
        groupProductionTrendChart.destroy();
    }

    groupProductionTrendChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: months,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: getAnimConfig("line"),
            plugins: {
                legend: { labels: { font: FA_FONT } },
                tooltip: {
                    ...TOOLTIP_BASE,
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function(ctx) {
                            const val = ctx.parsed.y;
                            if (val === null || isNaN(val)) return '';
                            return ` ${ctx.dataset.label}: ${val.toLocaleString('fa-IR')} متر مکعب`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    title: { display: true, text: "ماه", font: FA_FONT },
                    ticks: { font: FA_FONT }
                },
                y: {
                    title: { display: true, text: "مجموع تولید (م.م)", font: FA_FONT },
                    ticks: { font: NUM_FONT },
                    beginAtZero: true
                }
            }
        }
    });
}


let groupYearlyProductionTrendChart = null; // برای مدیریت نمودار جدید

function drawGroupYearlyProductionTrend(data) {
    const ctx = document.getElementById("groupYearlyProductionTrend");
    if (!ctx) return;

    const years = ALL_YEARS.slice();
    let yearlyTotals = new Array(years.length).fill(0);

data.forEach(r => {
        years.forEach((year, i) => {
            const val = yearlyValue(r, "تولید", year);
            if (!isNaN(val)) yearlyTotals[i] += val;
        });
    });

    // رنگ‌های متمایز برای هر سال
    const barColors = [
        '#94a3b8', // 1399
        '#64748b', // 1400
        '#475569', // 1401
        '#0ea5e9', // 1402
        '#2563eb', // 1403
        '#8b5cf6', // 1404
        '#00bfa0'  // 1405
    ];

    if (groupYearlyProductionTrendChart) {
        groupYearlyProductionTrendChart.destroy();
    }

    groupYearlyProductionTrendChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: years.map(y => y.toString()),
            datasets: [{
                label: "مجموع تولید سالانه",
                data: yearlyTotals,
                backgroundColor: barColors,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: getAnimConfig("bar"),
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...TOOLTIP_BASE,
                    callbacks: {
                        label: function(ctx) {
                            return ` تولید: ${ctx.parsed.y.toLocaleString('fa-IR')} متر مکعب`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: "مجموع تولید (م.م)", font: FA_FONT },
                    ticks: { font: NUM_FONT }
                },
                x: {
                    title: { display: true, text: "سال", font: FA_FONT },
                    ticks: { font: FA_FONT }
                }
            }
        }
    });
}


function drawGroupPressureTrend(data){

const ctx=document.getElementById("groupPressureTrend");
if(!ctx) return;

const selectedYear = document.getElementById("groupYearPress")?.value || "1404";
const years = selectedYear === "all" ? [1399,1400,1401,1402,1403,1404] : [Number(selectedYear)];


const offices=[...new Set(data.map(r=>r["اداره"]))];

let datasets=[];

offices.forEach(o=>{

const rows=data.filter(r=>r["اداره"]===o);

let values=[];

ALL_YEARS.forEach(y=>{

let sum=0;
let count=0;

rows.forEach(r=>{

let ps = [];
years.forEach(y=>{
   const v=getPressureValue(r,y);
   if(!isNaN(v)) ps.push(v);
});
const p = ps.length ? ps.reduce((a,b)=>a+b,0)/ps.length : NaN;

if(!isNaN(p)){
sum+=p;
count++;
}

});

values.push(count?sum/count:null);

});

datasets.push({
label:o,
data:values,
tension:0.4
});

});

if(charts["groupPressureTrend"])
charts["groupPressureTrend"].destroy();

charts["groupPressureTrend"]=new Chart(ctx,{
type:"line",
data:{
labels:ALL_YEARS,
datasets:datasets
},
options:{
    responsive:true,
    maintainAspectRatio:false,
    plugins:{
        legend:{ labels:{ font: FA_FONT } },
        tooltip:{ ...TOOLTIP_BASE, mode:'index', intersect:false }
    },
    scales:{
        x:{ ticks:{ font: FA_FONT } },
        y:{ beginAtZero:true, ticks:{ font: NUM_FONT } }
    }
}
});

}
function drawGroupPressureLoss(data){

const ctx=document.getElementById("groupPressureLoss");
if(!ctx) return;

const selectedYear = document.getElementById("groupYearPress")?.value || "1404";
const years = selectedYear === "all" ? [1399,1400,1401,1402,1403,1404] : [Number(selectedYear)];


const offices=[...new Set(data.map(r=>r["اداره"]))];

let values=[];

offices.forEach(o=>{

const rows=data.filter(r=>r["اداره"]===o);

let p1=0,p2=0,c1=0,c2=0;

rows.forEach(r=>{

const a=getPressureValue(r,1399);
let ps = [];
years.forEach(y=>{
   const v=getPressureValue(r,y);
   if(!isNaN(v)) ps.push(v);
});
const p = ps.length ? ps.reduce((a,b)=>a+b,0)/ps.length : NaN;

if(!isNaN(a)){p1+=a;c1++;}
if(!isNaN(p)){p2+=p;c2++;}   // ← اصلاح اصلی

});

p1=c1?p1/c1:0;
p2=c2?p2/c2:0;

values.push(p2-p1);

});

if(charts["groupPressureLoss"])
charts["groupPressureLoss"].destroy();

charts["groupPressureLoss"]=new Chart(ctx,{
type:"bar",
data:{
labels:offices,
datasets:[{
label:"افت فشار",
data:values,
backgroundColor:"#f97316"
}]
},
options:{
    responsive:true,
    maintainAspectRatio:false,
    plugins:{
        legend:{ labels:{ font: FA_FONT } },
        tooltip:{ ...TOOLTIP_BASE }
    },
    scales:{
        x:{ ticks:{ font: FA_FONT } },
        y:{ beginAtZero:true, ticks:{ font: NUM_FONT } }
    }
}
});

}
function drawGroupRadar(data){

    const ctx=document.getElementById("groupRadar");
    if(!ctx) return;

    const selectedYear = document.getElementById("groupYearRank")?.value || "1404";
    const years = selectedYear === "all" ? [1399,1400,1401,1402,1403,1404] : [Number(selectedYear)];

    const offices=[...new Set(data.map(r=>r["اداره"]))];

    let prod=[];
    let flow=[];
    let runtime=[];
    let pressure=[];

    offices.forEach(o=>{

        const rows=data.filter(r=>r["اداره"]===o);

        let totalProd=0, totalFlow=0, totalRuntime=0, totalPressure=0, c=0;

        rows.forEach(r=>{

            let prodArr=[], flowArr=[], runArr=[], pressArr=[];

            years.forEach(y=>{
                const vProd = parseNum(r[`تولید سال ${y}`]);
                const vFlow = parseNum(r[`دبی متوسط سال ${y}`]);
                const vRun  = parseNum(r[`کارکرد سال ${y}`]);
                const vPres = getPressureValue(r, y);

                if(!isNaN(vProd)) prodArr.push(vProd);
                if(!isNaN(vFlow)) flowArr.push(vFlow);
                if(!isNaN(vRun))  runArr.push(vRun);
                if(!isNaN(vPres)) pressArr.push(vPres);
            });

            const avgProd = prodArr.length ? prodArr.reduce((a,b)=>a+b)/prodArr.length : 0;
            const avgFlow = flowArr.length ? flowArr.reduce((a,b)=>a+b)/flowArr.length : 0;
            const avgRun  = runArr.length ? runArr.reduce((a,b)=>a+b)/runArr.length : 0;
            const avgPres = pressArr.length ? pressArr.reduce((a,b)=>a+b)/pressArr.length : 0;

            totalProd     += avgProd;
            totalFlow     += avgFlow;
            totalRuntime  += avgRun;
            totalPressure += avgPres;

            c++;
        });

        prod.push(c ? totalProd/c : 0);
        flow.push(c ? totalFlow/c : 0);
        runtime.push(c ? totalRuntime/c : 0);
        pressure.push(c ? totalPressure/c : 0);

    });

    if(charts["groupRadar"])
        charts["groupRadar"].destroy();

    charts["groupRadar"]=new Chart(ctx,{
        type:"radar",
        data:{
            labels:offices,
            datasets:[
                {label:"تولید",data:prod,     borderColor:"#3b82f6"},
                {label:"دبی",  data:flow,     borderColor:"#ef4444"},
                {label:"کارکرد",data:runtime,borderColor:"#f59e0b"},
                {label:"فشار", data:pressure, borderColor:"#10b981"}
            ]
        },
        options:{
            responsive:true,
            maintainAspectRatio:false,
            animation: getAnimConfig("radar"),
            plugins:{
                legend:{ labels:{ font: FA_FONT } },
                tooltip:{ ...TOOLTIP_BASE }
            },
            scales:{
                r:{
                    ticks:{ font: NUM_FONT, backdropColor:'transparent' },
                    pointLabels:{ font: FA_FONT }
                }
            }
        }
    });

}

function drawGroupRanking(data){

const ctx=document.getElementById("groupRanking");
if(!ctx) return;

const selectedYear = document.getElementById("groupYearRank")?.value || "1404";
const years = selectedYear === "all" ? [1399,1400,1401,1402,1403,1404] : [Number(selectedYear)];


const offices=[...new Set(data.map(r=>r["اداره"]))];

let ranking=[];

offices.forEach(o=>{

const rows=data.filter(r=>r["اداره"]===o);

let score=0;

rows.forEach(r=>{

let vals=[];
years.forEach(y=>{
  const v=parseNum(r[`تولید سال ${y}`]);
  if(!isNaN(v)) vals.push(v);
});
const avgScore = vals.length? vals.reduce((a,b)=>a+b,0)/vals.length : 0;
score+=avgScore;

});

ranking.push({office:o,score:score});

});

ranking.sort((a,b)=>b.score-a.score);

if(charts["groupRanking"])
charts["groupRanking"].destroy();

charts["groupRanking"]=new Chart(ctx,{
type:"bar",
data:{
labels:ranking.map(r=>r.office),
datasets:[{
label:"امتیاز عملکرد",
data:ranking.map(r=>r.score),
backgroundColor:"#6366f1"
}]
},
options:{
    responsive:true,
    maintainAspectRatio:false,
    animation: getAnimConfig("bar"),
    indexAxis:"y",
    plugins:{
        legend:{ labels:{ font: FA_FONT } },
        tooltip:{ ...TOOLTIP_BASE }
    },
    scales:{
        x:{ ticks:{ font: NUM_FONT }, beginAtZero:true },
        y:{ ticks:{ font: FA_FONT } }
    }
}
});

}
function updateGroupRadar() {
  const selectedYear = document.getElementById("groupYearFilter").value;
  const selectedGroup = document.getElementById("groupFilter").value;

  const filteredData = allRows.filter(row => {
    const matchYear = !selectedYear || row.year == selectedYear;
    const matchGroup = !selectedGroup || row.group == selectedGroup;
    return matchYear && matchGroup;
  });

  renderGroupRadar(filteredData);
}

// --- اصلاح تابع رادار (جلوگیری از خطای allRows) ---
function updateGroupRadar() {
    const selectedYear = document.getElementById("groupYearRank")?.value || "all";
    
    // فیلتر کردن بر اساس داده‌های موجود
    const filteredData = getGroupFilteredData(); 
    drawGroupRadar(filteredData);
}

// --- اصلاح بخش لیسنرها و توابع ناموجود ---
document.addEventListener("DOMContentLoaded", () => {
    // چک کردن وجود دکمه خروجی اکسل قبل از افزودن لیسنر
    const exportBtn = document.getElementById("exportFlowExcel");
    if (exportBtn) {
        // چون تابع exportFlowTableToExcel را نداری، فعلاً از تابع دانلود قبلی استفاده می‌کنیم
        exportBtn.addEventListener("click", downloadFlowChangeExcel);
    }

    // اصلاح لیسنرهای فیلتر رادار (آیدی‌ها باید با HTML یکی باشند)
    const gyf = document.getElementById("groupYearRank");
    if (gyf) gyf.addEventListener("change", updateGroupRadar);
});

// این دو تابع را هم اضافه کن تا ارور ندهد
function fillMainZone(){
    if (!wellsData) return;
    const select = document.getElementById("groupMainZone");
    if(!select) return;
    select.innerHTML='<option value="all">همه</option>';
    const zones=[...new Set(wellsData.map(r=>r["پهنه اصلی"]).filter(Boolean))];
    zones.forEach(z=>{
        const op=document.createElement("option");
        op.value=z; op.textContent=z; select.appendChild(op);
    });
}

function fillSubZone(){
    if (!wellsData) return;
    const select = document.getElementById("groupSubZone");
    if(!select) return;
    select.innerHTML='<option value="all">همه</option>';
    const zones=[...new Set(wellsData.map(r=>r["زیر پهنه"]).filter(Boolean))];
    zones.forEach(z=>{
        const op=document.createElement("option");
        op.value=z; op.textContent=z; select.appendChild(op);
    });
}
function updateDependentFilters() {
    if (!wellsData) return;
    const office = document.getElementById("groupOffice").value;
    
    // فیلتر کردن داده‌ها بر اساس اداره
    const filtered = office === "all" ? wellsData : wellsData.filter(r => r["اداره"] === office);

    // به‌روزرسانی چاه‌ها
    const wellSelect = document.getElementById("groupWell");
    const currentWell = wellSelect.value;
    wellSelect.innerHTML = '<option value="all">همه چاه‌ها</option>';
    [...new Set(filtered.map(r => r["نام چاه"]))].forEach(w => {
        wellSelect.innerHTML += `<option value="${w}">${w}</option>`;
    });
    wellSelect.value = currentWell;

    // به‌روزرسانی پهنه اصلی
    const mainSelect = document.getElementById("groupMainZone");
    const currentMain = mainSelect.value;
    mainSelect.innerHTML = '<option value="all">همه</option>';
    [...new Set(filtered.map(r => r["پهنه اصلی"]))].forEach(z => {
        if(z) mainSelect.innerHTML += `<option value="${z}">${z}</option>`;
    });
    mainSelect.value = currentMain;

    // به‌روزرسانی زیر پهنه
    updateSubZoneFilter();
}
function updateSubZoneFilter() {
    if (!wellsData) return;

    const office = document.getElementById("groupOffice")?.value || "all";
    const main = document.getElementById("groupMainZone")?.value || "all";
    
    // فیلتر کردن داده‌ها برای پیدا کردن زیرپهنه‌های مربوطه
    let filtered = wellsData;
    if(office !== "all") filtered = filtered.filter(r => r["اداره"] === office);
    if(main !== "all") filtered = filtered.filter(r => r["پهنه اصلی"] === main);

    const subSelect = document.getElementById("groupSubZone");
    if(!subSelect) return;

    const currentSub = subSelect.value;
    subSelect.innerHTML = '<option value="all">همه</option>';
    
    // گرفتن مقادیر یونیک زیر پهنه
    const subZones = [...new Set(filtered.map(r => r["زیر پهنه"]).filter(Boolean))];
    
    subZones.forEach(s => {
        const op = document.createElement("option");
        op.value = s;
        op.textContent = s;
        subSelect.appendChild(op);
    });

    // برگرداندن انتخاب قبلی اگر هنوز در لیست جدید موجود باشد
    subSelect.value = subZones.includes(currentSub) ? currentSub : "all";
}
let contractorAvgFlowChartInstance = null;

const months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
const drillYears = ["1399","1400","1401","1402","1403","1404","1405"];

// ساخت لیبل‌های محور X برای همه سال‌ها
function buildAllYearLabels() {
    const labels = [];
    drillYears.forEach(year => {
        months.forEach(month => {
            labels.push(`${month} ${year}`);
        });
    });
    return labels;
}

// گرفتن مقادیر دبی یک چاه در همه سال‌ها
function getWellFlowsForAllYears(well) {
    const values = [];
    drillYears.forEach(year => {
        months.forEach(month => {
            values.push(parseFloat(well[`دبی متوسط ${year}(${month})`]) || 0);
        });
    });
    return values;
}

function renderDrillingTable(data) {
    const container = document.getElementById("drillResultsTableContainer");
    const tbody = document.querySelector("#drillResultsTable tbody");
    tbody.innerHTML = "";

    if (!data || data.length === 0) {
        container.style.display = "none";
        return;
    }

    data.forEach(row => {
        tbody.innerHTML += `
            <tr>
                <td>${row.well} - ${row.year}</td>
                <td>${row.contractor}</td>
                <td>${row.percentDrop}%</td>
                <td>${row.index}</td>
            </tr>
        `;
    });

    container.style.display = "block";
}

function downloadDrillingExcel() {
    const table = document.getElementById("drillResultsTable");
    if (!table || table.rows.length === 0) {
        alert("جدول حفاری خالی است!");
        return;
    }
    const wb = XLSX.utils.table_to_book(table, { sheet: "Drilling" });
    XLSX.writeFile(wb, "گزارش_حفاری.xlsx");
}

function initDrillingFilters(wellsData) {
    const contractorSelect = document.getElementById("drillFilterContractor");
    const wellSelect = document.getElementById("drillFilterWell");

    contractorSelect.innerHTML = `<option value="all">انتخاب پیمانکار...</option>`;
    wellSelect.innerHTML = `<option value="all">ابتدا پیمانکار را انتخاب کنید</option>`;

    const contractors = new Set();

    wellsData.forEach(w => {
        drillYears.forEach(year => {
            const c = w[`پیمانکار ${year}`];
            if (c && String(c).trim() !== "") {
                contractors.add(String(c).trim());
            }
        });
    });

    [...contractors].sort().forEach(c => {
        contractorSelect.innerHTML += `<option value="${c}">${c}</option>`;
    });

    contractorSelect.addEventListener("change", () => {
        const contractor = contractorSelect.value;

        wellSelect.innerHTML = `<option value="all">همه چاه‌ها</option>`;

        if (contractor === "all") {
            wellSelect.innerHTML = `<option value="all">ابتدا پیمانکار را انتخاب کنید</option>`;
            updateDrillingDashboard(wellsData);
            return;
        }

        const wells = new Set();

        wellsData.forEach(w => {
            const matched = drillYears.some(year => w[`پیمانکار ${year}`] === contractor);
            if (matched && w["نام چاه"]) {
                wells.add(w["نام چاه"]);
            }
        });

        [...wells].sort().forEach(wellName => {
            wellSelect.innerHTML += `<option value="${wellName}">${wellName}</option>`;
        });

        updateDrillingDashboard(wellsData);
    });

    wellSelect.addEventListener("change", () => updateDrillingDashboard(wellsData));
}

function calculateWellDrop(well, year) {
    // دبی‌های ۱۲ ماه همان سال
    let flows = months.map(m => {
        const val = parseFloat(well[`دبی متوسط ${year}(${m})`]);
        return isNaN(val) ? 0 : val;
    });

    // ایندکس ترخیص (۰ تا ۱۱)
    let dischargeIndex = getDischargeIndex(well, year);

    // اگر ترخیص تعریف نشده
    if (dischargeIndex === null || dischargeIndex < 0) {
        dischargeIndex = -1; // یعنی از اول سال شروع کنیم
    }

    // پیدا کردن اولین ماه با دبی مثبت بعد از ترخیص
    let startIndex = -1;
    for (let i = dischargeIndex + 1; i < flows.length; i++) {
        if (flows[i] > 0) {
            startIndex = i;
            break;
        }
    }

    // اگر از ترخیص به بعد هیچ دبی مثبتی پیدا نشد
    if (startIndex === -1) {
        return null;  // اینجا استثنا واقعی است
    }

    // از اولین ماه مثبت تا آخر
    const activeFlows = flows.slice(startIndex);

    // activeFlows ممکن است چند صفر وسطش داشته باشد، اینجا اشکالی ندارد
    const positiveFlows = activeFlows.filter(x => x > 0);

    // اگر بعد از اولین مقدار مثبت، هیچ مقدار مثبت دیگری هم نباشد (مثلاً فقط یک مقدار مثبت وجود دارد)
    if (positiveFlows.length === 0) {
        return null;
    }

    // محاسبات
    const maxFlow = Math.max(...positiveFlows);
    const idealArea = maxFlow * activeFlows.length;

    if (idealArea === 0) return null;

    const realArea = activeFlows.reduce((a, b) => a + b, 0);
    const index = (idealArea - realArea) / idealArea;
    const percentDrop = index * 100;

    return {
        percentDrop: percentDrop.toFixed(2),
        index: index.toFixed(3),
        startMonth: months[startIndex] // اطلاعات مفید برای دیباگ
    };
}




function drawDrillingChart(data, contractor, tableData) {
    const canvas = document.getElementById("contractorAvgFlowChart");
    if (!canvas) return;

    // این دو خط را حذف کن (الان سایز از CSS می‌آید)
    // canvas.style.width = "1400px";
    // canvas.style.height = "480px";

    const ctx = canvas.getContext("2d");

    if (contractorAvgFlowChartInstance) {
        contractorAvgFlowChartInstance.destroy();
        contractorAvgFlowChartInstance = null;
    }

    if (!data || data.length === 0) return;

    let dischargeIndex = null;
    for (let year of drillYears) {
        let idx = getDischargeIndex(data[0], year);
        if (idx !== null && idx !== -1) {
            dischargeIndex = idx;
            break;
        }
    }

    const labels = buildAllYearLabels();
    const values = drillYears.flatMap(year =>
        months.map(month => {
            const arr = data.map(w => parseFloat(w[`دبی متوسط ${year}(${month})`]) || 0);
            return arr.length ? (arr.reduce((a, b) => a + b, 0) / arr.length) : 0;
        })
    );

    contractorAvgFlowChartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [{
                label: `میانگین دبی - ${contractor}`,
                data: values,
                borderColor: "#00bcd4",
                backgroundColor: "rgba(0,188,212,0.18)",
                fill: true,
                borderWidth: 3,
                tension: 0.25,
                pointRadius: 3,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            animation: getAnimConfig("line"),
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true },
                tooltip: {
                    ...TOOLTIP_BASE,
                    enabled: true,
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function(ctx) {
                            const val = ctx.parsed.y;
                            if (val === null || isNaN(val)) return '';
                            return ` دبی: ${val.toLocaleString('fa-IR')} لیتر بر ثانیه`;
                        }
                    }
                },
                annotation: (dischargeIndex !== null && dischargeIndex !== -1) ? {
                    annotations: {
                        dischargeLine: {
                            type: "line",
                            scaleID: "x",
                            value: dischargeIndex,
                            borderColor: "orange",
                            borderWidth: 3,
                            label: {
                                display: true,
                                content: "ترخیص",
                                position: "start",
                                backgroundColor: "orange",
                                color: "white"
                            }
                        }
                    }
                } : undefined
            },
            scales: {
                x: {
                    ticks: { maxRotation: 45, minRotation: 45, font: FA_FONT },
                    grid: { display: false }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: "rgba(0,0,0,0.05)" },
                    ticks: { font: NUM_FONT }
                }
            }
        }
    });
}


function updateKPIBoxes(tableData) {
    const maxDropEl = document.getElementById("kpi-max-drop");
    const minDropEl = document.getElementById("kpi-min-drop");
    const maxIndexEl = document.getElementById("kpi-max-index");
    const minIndexEl = document.getElementById("kpi-min-index");

    if (!tableData || tableData.length === 0) {
        [maxDropEl, minDropEl, maxIndexEl, minIndexEl]
          .forEach(el => el.innerText = "نامشخص - 0");
        return;
    }

    // فقط ردیف‌های معتبر
    const valid = tableData.filter(r =>
        !isNaN(parseFloat(r.percentDrop)) && !isNaN(parseFloat(r.index))
    );
    if (valid.length === 0) {
        [maxDropEl, minDropEl, maxIndexEl, minIndexEl]
          .forEach(el => el.innerText = "نامشخص - 0");
        return;
    }

    const findBest = (arr, key, isMax) =>
        arr.reduce((prev, curr) => {
            const pVal = parseFloat(prev[key]);
            const cVal = parseFloat(curr[key]);
            return isMax ? (cVal > pVal ? curr : prev) : (cVal < pVal ? curr : prev);
        });

    const maxDrop = findBest(valid, 'percentDrop', true);
    const minDrop = findBest(valid, 'percentDrop', false);
    const maxIndex = findBest(valid, 'index', true);
    const minIndex = findBest(valid, 'index', false);

    maxDropEl.innerText = `${maxDrop.contractor} – ${maxDrop.percentDrop}%`;
    minDropEl.innerText = `${minDrop.contractor} – ${minDrop.percentDrop}%`;
    maxIndexEl.innerText = `${maxIndex.contractor} – ${maxIndex.index}`;
    minIndexEl.innerText = `${minIndex.contractor} – ${minIndex.index}`;
}

function updateContractorRanking(wellsData) {
    const container = document.getElementById("rankingCards");
    if (!container) return;

    const contractorStats = {};

    wellsData.forEach(w => {
        drillYears.forEach(year => {
            const contractor = w[`پیمانکار ${year}`];
            if (!contractor) return;

            if (!contractorStats[contractor]) {
                contractorStats[contractor] = { sum: 0, count: 0 };
            }

            const result = calculateWellDrop(w, year);
            if (result) {
                contractorStats[contractor].sum += parseFloat(result.index);
                contractorStats[contractor].count++;
            }
        });
    });

    console.log("contractorStats:", contractorStats);

    const ranking = Object.keys(contractorStats)
        .filter(k => contractorStats[k].count > 0)
        .map(k => ({
            name: k,
            avg: contractorStats[k].sum / contractorStats[k].count
        }))
        .sort((a, b) => a.avg - b.avg);

    console.log("ranking:", ranking);

    container.innerHTML = "";
    ranking.forEach((item, i) => {
        let cls = i === 0 ? "rank-1"
                 : i === 1 ? "rank-2"
                 : i === 2 ? "rank-3"
                 : "rank-other";

        container.innerHTML += `
            <div class="rank-card ${cls}">
                <h4>رتبه ${i + 1}</h4>
                <p>${item.name}</p>
                <p>میانگین شاخص: ${item.avg.toFixed(3)}</p>
            </div>
        `;
    });
}


function updateDrillingDashboard(wellsData) {
    const contractor = document.getElementById("drillFilterContractor").value;
    const well = document.getElementById("drillFilterWell").value;

    let filtered = wellsData.filter(w => {
        const contractorMatched = (contractor === "all" || drillYears.some(year => w[`پیمانکار ${year}`] === contractor));
        const wellMatched = (well === "all" || w["نام چاه"] === well);
        return contractorMatched && wellMatched;
    });

    console.log("filtered wells:", filtered.length);

    const tableData = [];
    filtered.forEach(w => {
        drillYears.forEach(year => {
            if (contractor === "all" || w[`پیمانکار ${year}`] === contractor) {
                const result = calculateWellDrop(w, year);
                if (result) {
                    tableData.push({
                        well: w["نام چاه"],
                        contractor: w[`پیمانکار ${year}`] || "نامشخص",
                        year: year,
                        percentDrop: result.percentDrop,
                        index: result.index
                    });
                }
            }
        });
    });

    console.log("tableData rows:", tableData.length);

    renderPrettyDrillingTable(tableData);
    updateKPIBoxes(tableData);
    drawDrillingChart(filtered, contractor === "all" ? "همه پیمانکاران" : contractor, tableData);
}

function getDischargeIndex(well, year) {
    // تمام کلیدهای مربوط به این سال که داخلشان "ترخیص" هست
    const keys = Object.keys(well).filter(k => k.includes("ترخیص") && k.includes(year));
    if (!keys.length) return null;

    // فعلاً اولین ترخیص را ملاک می‌گیریم (اگر چندتا باشند)
    const dischargeKey = keys[0];

    // استخراج نام ماه از ستون (مثل "ترخیص مرداد 1401")
    const match = dischargeKey.match(/(فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)/);
    if (!match) return null;

    const monthName = match[0];

    // ایندکس ماه داخل آرایه months (۰ تا ۱۱)
    const monthIndex = months.indexOf(monthName);
    if (monthIndex === -1) return null;

    // این تابع حالا ایندکس ماه در همان سال را می‌دهد، نه ایندکس کلی همه سال‌ها
    return monthIndex;
}

function renderPrettyDrillingTable(tableData) {
    const table = document.getElementById("drillPrettyTable");
    if (!table) return;
    
    // ۱. ساخت هدر
    const thead = table.querySelector("thead");
    thead.innerHTML = `<tr>
        <th>سال</th>
        <th>چاه</th>
        <th>پیمانکار</th>
        <th>درصد افت</th>
        <th>شاخص (p/m/w)</th>
    </tr>`;

    // ۲. ساخت بدنه اصلی جدول
    let tableHTML = tableData.map(r => `
        <tr>
            <td>${r.year}</td>
            <td>${r.well}</td>
            <td>${r.contractor}</td>
            <td>${r.percentDrop}%</td>
            <td>${r.index}</td>
        </tr>
    `).join("");

    // ۳. محاسبه میانگین‌ها
    const totalRows = tableData.length;
    if (totalRows > 0) {
        const sumDrop = tableData.reduce((acc, row) => acc + parseFloat(row.percentDrop), 0);
        const sumIndex = tableData.reduce((acc, row) => acc + parseFloat(row.index), 0);

        const avgDrop = (sumDrop / totalRows).toFixed(2);
        const avgIndex = (sumIndex / totalRows).toFixed(3);

        // ۴. اضافه کردن سطر میانگین به انتهای رشته HTML
        tableHTML += `
            <tr style="background-color: #e9ecef; font-weight: bold; border-top: 2px solid #dee2e6;">
                <td colspan="3" style="text-align: center;">میانگین کل</td>
                <td>${avgDrop}%</td>
                <td>${avgIndex}</td>
            </tr>
        `;
    }

    // ۵. درج نهایی در tbody
    const tbody = table.querySelector("tbody");
    tbody.innerHTML = tableHTML;
}

function toggleTable() {
    const wrapper = document.getElementById("drillingTableWrapper");
    const btn = document.getElementById("toggleTableBtn");
    if (!wrapper || !btn) return;

    const isHidden = (wrapper.style.display === "none" || wrapper.style.display === "");
    wrapper.style.display = isHidden ? "block" : "none";
    btn.textContent = isHidden ? "مخفی کردن جدول" : "نمایش جدول";
}

//..........پای چارت..............//
function drawWellStatusChart() {
    const canvas = document.getElementById("chartWellStatus");
    if (!canvas) return;
    
    if (!wellsData || wellsData.length === 0) return;
    
    const inOrbit = wellsData.filter(r => r["وضعیت چاه"] === "در مدار").length;
    const outOrbit = wellsData.filter(r => r["وضعیت چاه"] === "خارج از مدار").length;
   
    if (charts["chartWellStatus"]) charts["chartWellStatus"].destroy();

    charts["chartWellStatus"] = new Chart(canvas, {
        type: 'pie',
        data: {
            labels: ['در مدار', 'خارج از مدار'],
            datasets: [{
                data: [inOrbit, outOrbit],
                backgroundColor: ['#00fd2a', '#fa1900']
            }]
        },
        options: {
            responsive: true,
            animation: getAnimConfig("pie"),
            plugins: {
                legend: { position: 'bottom' },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.label || '';
                            let value = context.raw;
                            let total = inOrbit + outOrbit;
                            let percentage = ((value / total) * 100).toFixed(1);
                            return `${label}: ${value} چاه (${percentage}%)`;
                        }
                    }
                }
            },
            onClick: (event, elements) => {
                if (elements.length > 0) {
                    const index = elements[0].index;
                    const container = document.getElementById("offlineWellsContainer");
                    if (index === 1) { // اگر روی قرمز (خارج از مدار) کلیک شد
                        toggleOfflineTable();
                    } else {
                        container.style.display = "none"; // کلیک روی سبز کاری نکند/ببندد
                    }
                }
            }
        }
    });
}
function toggleOfflineTable() {
    const container = document.getElementById("offlineWellsContainer");
    const tbody = container.querySelector("tbody");
    
    if (container.style.display === "block") {
        container.style.display = "none";
    } else {
        const offlineWells = wellsData.filter(r => r["وضعیت چاه"] === "خارج از مدار");
        tbody.innerHTML = "";
        offlineWells.forEach((r, i) => {
            tbody.innerHTML += `<tr><td>${i+1}</td><td>${r["نام چاه"]}</td><td>${r["پهنه اصلی"] || '-'}</td></tr>`;
        });
        container.style.display = "block";
        container.scrollIntoView({ behavior: 'smooth' });
    }
}
//..........  نمای کلی، مقایسه پهنه ها..............//
//..........  نمای کلی، مقایسه پهنه ها..............//
let zoneChart = null;
let zoneTrendChart = null;
let activeZone = null; // این متغیر برای مدیریت وضعیت کلیک است

function drawZoneWellsChart(){
    // اضافه کردن این خط:
    document.getElementById("zoneWellsTableContainer").innerHTML = "";
    activeZone = null;
    if (zoneTrendChart) { zoneTrendChart.destroy(); zoneTrendChart = null; }  // ✅ اینجا

    const canvas = document.getElementById("chartZoneWells");
    if(!canvas) return;

    const year = document.getElementById("zoneYearFilter")?.value || "all";
    let data = wellsData;

    if(year !== "all"){
        data = data.filter(r => {
            const prod = parseNum(r[`تولید سال ${year}`]);
            return !isNaN(prod);
        });
    }

    const zones = [...new Set(data.map(r => r["پهنه اصلی"]).filter(Boolean))];
    const counts = zones.map(z => {
        return data.filter(r => r["پهنه اصلی"] === z).length;
    });

    const colors = zones.map((_, i) => `hsl(${i * 40}, 70%, 55%)`);

    if(zoneChart) zoneChart.destroy();

    zoneChart = new Chart(canvas, {
        type: "bar",
        data: {
            labels: zones,
            datasets: [{
                label: "تعداد چاه",
                data: counts,
                backgroundColor: colors,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            animation: getAnimConfig("bar"),
            plugins: { legend: { display: false } },
            onClick: (e, items) => {
                if(!items.length) return;

                const index = items[0].index;
                const zone = zones[index];

                // اگر روی همان پهنه قبلی کلیک شد، جدول را پاک کن
                if(activeZone === zone){
                    document.getElementById("zoneWellsTableContainer").innerHTML = "";
                    activeZone = null;
                    if (zoneTrendChart) { zoneTrendChart.destroy(); zoneTrendChart = null; }  // ✅ و اینجا
                    return;
                }

                // در غیر این صورت جدول پهنه جدید را نمایش بده
                activeZone = zone;
                renderZoneTable(zone);
            }
        }
    });
}
function renderZoneTable(zone){
    const container = document.getElementById("zoneWellsTableContainer");
    if(!container) return;

    if (zoneTrendChart) { zoneTrendChart.destroy(); zoneTrendChart = null; }

    const wells = wellsData.filter(r => r["پهنه اصلی"] === zone);

    // تولید کل پهنه برای هر سال
const trendData = ALL_YEARS.map(y => {
        let s = 0;
        wells.forEach(w => { const v = yearlyValue(w, "تولید", y); if(!isNaN(v)) s += v; });
        return s;
    });
    // دبی متوسط هر سال برای محور دوم
const flowData = ALL_YEARS.map(y => {
        let sum = 0, cnt = 0;
        wells.forEach(w => {
            const v = yearlyValue(w, "دبی", y);
            if (!isNaN(v)) { sum += v; cnt++; }
        });
        return cnt ? sum / cnt : null;
    });

    // کارت نمودار ترند (قبل از جدول)
    let html = `
        <div class="zone-trend-card">
             <h3>روند تولید کل پهنه ${zone}</h3>
            <div class="zone-trend-wrapper"><canvas id="zoneTrendCanvas"></canvas></div>
        </div>
        <div class="zone-table-title">&#x200F;چاه‌های پهنه ${zone}</div>
    `;

html += `<table class="pretty-table"><thead><tr><th>نام چاه</th>`;
    ALL_YEARS.forEach(y => { html += `<th>${y}</th>`; });
    html += `<th>مجموع</th><th>میانگین</th></tr></thead><tbody>`;

    let yearTotals = ALL_YEARS.map(() => 0);

    wells.forEach(w => {
        let rowTotal = 0;
        html += `<tr><td>${w["نام چاه"]}</td>`;
        ALL_YEARS.forEach((y, i) => {
            const val = yearlyValue(w, "تولید", y) || 0;
            yearTotals[i] += val;
            rowTotal += val;
            html += `<td>${Math.round(val).toLocaleString()}</td>`;
        });
        const avg = rowTotal / ALL_YEARS.length;
        html += `<td>${Math.round(rowTotal).toLocaleString()}</td>`;
        html += `<td>${Math.round(avg).toLocaleString()}</td></tr>`;
    });

    html += `<tr style="background:#e2e8f0; font-weight:bold;"><td>مجموع پهنه</td>`;
    let totalOfTotals = 0;
    yearTotals.forEach(t => { html += `<td>${Math.round(t).toLocaleString()}</td>`; totalOfTotals += t; });
    html += `<td>${Math.round(totalOfTotals).toLocaleString()}</td><td>-</td></tr>`;
    html += `</tbody></table>`;

    container.innerHTML = html;

    // رسم نمودار ترند بعد از درج DOM
    const ctx = document.getElementById("zoneTrendCanvas");
    if (ctx) {
            zoneTrendChart = new Chart(ctx, {
            type: "line",
            data: {
                labels: ALL_YEARS.map(String),
                datasets: [
                    {
                        label: `تولید کل پهنه ${zone}`,
                        data: trendData,
                        borderColor: "#7209b7",
                        backgroundColor: "rgba(114,9,183,0.15)",
                        fill: true,
                        tension: 0.4,
                        borderWidth: 3,
                        pointRadius: 6,
                        pointHoverRadius: 9,
                        pointBackgroundColor: "#7209b7",
                        yAxisID: "yProd"
                    },
                    {
                        label: `دبی متوسط پهنه ${zone}`,
                        data: flowData,
                        borderColor: "#06b6d4",
                        backgroundColor: "rgba(6,182,212,0.10)",
                        fill: false,
                        tension: 0.4,
                        borderWidth: 3,
                        borderDash: [6, 4],
                        pointRadius: 6,
                        pointHoverRadius: 9,
                        pointBackgroundColor: "#06b6d4",
                        spanGaps: true,
                        yAxisID: "yFlow"
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: getAnimConfig("line"),
                plugins: {
                    legend: { display: true, labels: { font: FA_FONT } },
                    tooltip: { ...TOOLTIP_BASE, mode: "index", intersect: false }
                },
                scales: {
                    yProd: {
                        position: "right",
                        beginAtZero: true,
                        title: { display: true, text: "تولید کل (م.م)", font: FA_FONT },
                        ticks: { font: NUM_FONT }
                    },
                    yFlow: {
                        position: "left",
                        beginAtZero: true,
                        grid: { drawOnChartArea: false },
                        title: { display: true, text: "دبی متوسط (l/s)", font: FA_FONT, color: "#06b6d4" },
                        ticks: { font: NUM_FONT, color: "#06b6d4" }
                    },
                    x: { ticks: { font: FA_FONT } }
                }
            }
        });
    }
}
/* =========================================
   تب عملکرد پیمانکاران (آزمایش پمپاژ)
========================================= */
let ptGapChart=null, ptUtilChart=null, ptDrawChart=null, ptScatterChart=null;
let ptComputed = [];

const PT_COLORS = [
    "#e74c3c","#3498db","#2ecc71","#f39c12","#9b59b6","#1abc9c",
    "#e67e22","#34495e","#fd79a8","#6c5ce7","#00bcd4","#8bc34a",
    "#ff5722","#607d8b","#795548","#009688","#cddc39","#ff9800",
    "#3f51b5","#e91e63"
];
// میانگین دبی ماهانه از ماهِ بعد از تاریخ آزمایش پمپاژ تا اسفند 1405
// میانگین دبی ماهانه از ماهِ بعد از تاریخ آزمایش تا آخرین ماه موجود
function avgFlowAfterPumpTest(row, testDate) {
    if (!testDate) return NaN;

    const startYear  = testDate.year;
    const startMonth = testDate.month;

    let sum = 0, cnt = 0;

    ALL_YEARS.forEach(y => {
        if (y < startYear) return;

        MONTHS.forEach((m, i) => {
            const monthNum = i + 1;
            if (y === startYear && monthNum <= startMonth) return;

            const v = parseNum(row[`دبی متوسط ${y}(${m})`]);
            if (!isNaN(v) && v !== 0) {
                sum += v;
                cnt++;
            }
        });
    });

    return cnt ? sum / cnt : NaN;
}

// محاسبه اصلی: برای هر چاه، دبی پیشنهادی را با دبی واقعی سالِ حفر مقایسه کن
function computePumpTest() {
    ptComputed = [];
    if (!wellsData || !wellsData.length) return;

    wellsData.forEach(r => {
        const contractor = (r["پیمانکار"] || "").toString().trim();
        if (!contractor) return;

        // ✅ کلیدواژه‌ها مطابق نام واقعی ستون‌ها در فایل
        const sug      = parseNum(getColByContains(r, "دبی", "پیشنهادی"));   // "دبی مجاز پیشنهادی (l/s)"
        const maxYield = parseNum(getColByContains(r, "حداکثر", "آبدهی"));
        const drawdown = parseNum(getColByContains(r, "افت"));
        const yearDrill = parseNum(r["سال حفر"]);

        // ✅ ستون تاریخ فقط "تاریخ پایان آزمایش" است
        const testDateRaw = getColByContains(r, "تاریخ", "آزمایش");
        const testDate = parseJalaliDate(testDateRaw);

        const actual = avgFlowAfterPumpTest(r, testDate);

        // اگر دبی پیشنهادی یا میانگین دبی صفر/خالی بود، نادیده بگیر
        if (isNaN(sug) || sug === 0 || isNaN(actual) || actual === 0) return;

        const gap = ((actual - sug) / sug) * 100;

        let util = NaN;
        if (!isNaN(maxYield) && maxYield !== 0) {
            util = (sug / maxYield) * 100;
        }

        ptComputed.push({
            well: r["نام چاه"] || "-",
            contractor,
            year: isNaN(yearDrill) ? "-" : yearDrill,
            testDate: testDate
                ? `${testDate.year}/${String(testDate.month).padStart(2,"0")}/${String(testDate.day).padStart(2,"0")}`
                : "-",
            sug, actual, gap, maxYield, util, drawdown
        });
    });
}

function initPumpTestFilters() {
    const cSel = document.getElementById("ptContractor");
    const ySel = document.getElementById("ptYear");
    if (!cSel || !ySel) return;

    const contractors = [...new Set(ptComputed.map(d => d.contractor).filter(Boolean))].sort();
    cSel.innerHTML = '<option value="all">همه پیمانکاران</option>';
    contractors.forEach(c => cSel.innerHTML += `<option value="${c}">${c}</option>`);

    const years = [...new Set(ptComputed.map(d => d.year).filter(y => y !== "-"))].sort();
    ySel.innerHTML = '<option value="all">همه سال‌ها</option>';
    years.forEach(y => ySel.innerHTML += `<option value="${y}">${y}</option>`);

    cSel.addEventListener("change", updatePumpTest);
    ySel.addEventListener("change", updatePumpTest);
}

function getPtFiltered() {
    const c = document.getElementById("ptContractor")?.value || "all";
    const y = document.getElementById("ptYear")?.value || "all";
    return ptComputed.filter(d =>
        (c === "all" || d.contractor === c) &&
        (y === "all" || String(d.year) === String(y))
    );
}

// تجمیع بر اساس پیمانکار
function aggregateByContractor(rows) {
    const map = {};
    rows.forEach(d => {
        if (!map[d.contractor]) {
            map[d.contractor] = { gap:[], util:[], draw:[], n:0 };
        }
        const m = map[d.contractor];
        if (!isNaN(d.gap))  m.gap.push(d.gap);
        if (!isNaN(d.util)) m.util.push(d.util);
        if (!isNaN(d.drawdown)) m.draw.push(d.drawdown);
        m.n++;
    });
    const avg = a => a.length ? a.reduce((x,y)=>x+y,0)/a.length : NaN;
    return Object.keys(map).map(k => ({
        contractor: k,
        avgGap:  avg(map[k].gap),
        avgUtil: avg(map[k].util),
        avgDraw: avg(map[k].draw),
        count: map[k].n
    }));
}

function updatePumpTest() {
    const rows = getPtFiltered();
    const agg = aggregateByContractor(rows);

    drawPtGap(agg);
    drawPtUtil(agg);
    drawPtDrawdown(agg);
    drawPtScatter(rows);
    renderPtRanking(agg);
    renderPtTable(rows);
    renderPtGapCounts(rows);
    updatePtKPIs(agg, rows);
}

function updatePtKPIs(agg, rows) {
    const valid = agg.filter(a => !isNaN(a.avgGap));
    const best  = valid.slice().sort((a,b)=>Math.abs(a.avgGap)-Math.abs(b.avgGap))[0];
    const worst = valid.slice().sort((a,b)=>Math.abs(b.avgGap)-Math.abs(a.avgGap))[0];

    const sugVals = rows.map(d=>d.sug).filter(v=>!isNaN(v));
    const utilVals = rows.map(d=>d.util).filter(v=>!isNaN(v));
    const avg = a => a.length ? a.reduce((x,y)=>x+y,0)/a.length : NaN;

    const set = (id, txt) => { const el=document.getElementById(id); if(el) el.textContent=txt; };
    set("pt-kpi-best",  best  ? `${best.contractor} (${best.avgGap.toFixed(1)}%)` : "-");
    set("pt-kpi-worst", worst ? `${worst.contractor} (${worst.avgGap.toFixed(1)}%)` : "-");
    set("pt-kpi-avgsug", isNaN(avg(sugVals)) ? "-" : avg(sugVals).toFixed(1) + " l/s");
    set("pt-kpi-util",   isNaN(avg(utilVals)) ? "-" : avg(utilVals).toFixed(1) + "%");
}

function drawPtGap(agg) {
    const ctx = document.getElementById("ptGapChart");
    if (!ctx) return;
    const data = agg.filter(a=>!isNaN(a.avgGap)).sort((a,b)=>a.avgGap-b.avgGap);
    if (ptGapChart) ptGapChart.destroy();
    ptGapChart = new Chart(ctx, {
        type:"bar",
        data:{
            labels: data.map(d=>d.contractor),
            datasets:[{
                label:"میانگین شکاف٪",
                data: data.map(d=>d.avgGap),
                backgroundColor: data.map(d=> d.avgGap < 0 ? "#ef4444" : "#16a34a"),
                borderRadius:5
            }]
        },
        options:{
            responsive:true, maintainAspectRatio:false, indexAxis:"y",
            animation:getAnimConfig("bar"),
            plugins:{ legend:{display:false}, tooltip:{...TOOLTIP_BASE,
                callbacks:{ label:c=> ` شکاف: ${c.parsed.x.toFixed(1)}%` } } },
            scales:{ x:{ ticks:{font:NUM_FONT, callback:v=>v+"%"} }, y:{ ticks:{font:FA_FONT} } }
        }
    });
}

function drawPtUtil(agg) {
    const ctx = document.getElementById("ptUtilChart");
    if (!ctx) return;
    const data = agg.filter(a=>!isNaN(a.avgUtil)).sort((a,b)=>b.avgUtil-a.avgUtil);
    if (ptUtilChart) ptUtilChart.destroy();
    ptUtilChart = new Chart(ctx, {
        type:"bar",
        data:{
            labels:data.map(d=>d.contractor),
            datasets:[{
                label:"ضریب بهره‌برداری٪",
                data:data.map(d=>d.avgUtil),
                backgroundColor:data.map((_,i)=>PT_COLORS[i%PT_COLORS.length]),
                borderRadius:5
            }]
        },
        options:{
            responsive:true, maintainAspectRatio:false,
            animation:getAnimConfig("bar"),
            plugins:{ legend:{display:false}, tooltip:{...TOOLTIP_BASE,
                callbacks:{ label:c=> ` بهره‌برداری: ${c.parsed.y.toFixed(1)}%` } } },
            scales:{ x:{ ticks:{font:FA_FONT} }, y:{ beginAtZero:true, ticks:{font:NUM_FONT, callback:v=>v+"%"} } }
        }
    });
}

function drawPtDrawdown(agg) {
    const ctx = document.getElementById("ptDrawdownChart");
    if (!ctx) return;
    const data = agg.filter(a=>!isNaN(a.avgDraw)).sort((a,b)=>b.avgDraw-a.avgDraw);
    if (ptDrawChart) ptDrawChart.destroy();
    ptDrawChart = new Chart(ctx, {
        type:"bar",
        data:{
            labels:data.map(d=>d.contractor),
            datasets:[{
                label:"میانگین افت آب",
                data:data.map(d=>d.avgDraw),
                backgroundColor:"#0ea5e9",
                borderRadius:5
            }]
        },
        options:{
            responsive:true, maintainAspectRatio:false,
            animation:getAnimConfig("bar"),
            plugins:{ legend:{display:false}, tooltip:{...TOOLTIP_BASE} },
            scales:{ x:{ ticks:{font:FA_FONT} }, y:{ beginAtZero:true, ticks:{font:NUM_FONT} } }
        }
    });
}

function drawPtScatter(rows) {
    const ctx = document.getElementById("ptScatter");
    if (!ctx) return;

    const pts = rows.filter(d=>!isNaN(d.sug) && !isNaN(d.actual) && d.sug>0)
                    .map(d=>({ x:d.sug, y:d.actual, label:d.well, contractor:d.contractor }));

    const maxV = pts.length ? Math.max(...pts.map(p=>Math.max(p.x,p.y)))*1.1 : 40;

    if (ptScatterChart) ptScatterChart.destroy();
    ptScatterChart = new Chart(ctx, {
        type:"scatter",
        data:{
            datasets:[
                {
                    label:"چاه‌ها",
                    data:pts,
                    backgroundColor:"#2563eb",
                    pointRadius:5
                },
                {
                    type:"line",
                    label:"خط تطابق کامل",
                    data:[{x:0,y:0},{x:maxV,y:maxV}],
                    borderColor:"#22c55e",
                    borderDash:[6,4],
                    borderWidth:2,
                    pointRadius:0,
                    fill:false
                }
            ]
        },
        options:{
            responsive:true, maintainAspectRatio:false,
            animation:getAnimConfig("scatter"),
            plugins:{
                legend:{ labels:{font:FA_FONT} },
                tooltip:{ ...TOOLTIP_BASE,
                    callbacks:{ label:ctx=>{
                        if(ctx.dataset.type==="line") return "";
                        const r=ctx.raw;
                        return [`چاه: ${r.label}`, `پیمانکار: ${r.contractor}`,
                                `آزمایش پمپاژ حفاری: ${r.x} l/s`, `واقعی: ${r.y.toFixed(1)} l/s`];
                    } } }
            },
            scales:{
                x:{ title:{display:true,text:"آزمایش پمپاژ حفاری (l/s)",font:FA_FONT}, beginAtZero:true, ticks:{font:NUM_FONT} },
                y:{ title:{display:true,text:"دبی واقعی (l/s)",font:FA_FONT}, beginAtZero:true, ticks:{font:NUM_FONT} }
            }
        }
    });
}

function renderPtRanking(agg) {
    const container = document.getElementById("ptRankingCards");
    if (!container) return;
    const ranking = agg.filter(a=>!isNaN(a.avgGap))
                       .sort((a,b)=>Math.abs(a.avgGap)-Math.abs(b.avgGap));
    container.innerHTML = "";
    ranking.forEach((item,i)=>{
        const cls = i===0?"rank-1":i===1?"rank-2":i===2?"rank-3":"rank-other";
        container.innerHTML += `
            <div class="rank-card ${cls}">
                <h4>رتبه ${i+1}</h4>
                <p>${item.contractor}</p>
                <p>شکاف میانگین: ${item.avgGap.toFixed(1)}%</p>
                <p style="font-size:12px;color:#888;">${item.count} چاه</p>
            </div>`;
    });
}

function renderPtTable(rows) {
    const table = document.getElementById("ptTable");
    if (!table) return;
    table.querySelector("thead").innerHTML = `<tr>
        <th>ردیف</th>
        <th>نام چاه</th><th>پیمانکار</th><th>سال حفر</th><th>تاریخ آزمایش</th>
        <th>آزمایش پمپاژ حفاری</th><th>میانگین دبی واقعی</th><th>شکاف٪</th>
        <th>بهره‌برداری٪</th><th>افت آب</th>
    </tr>`;
    table.querySelector("tbody").innerHTML = rows.map((d, i) => {
        const cls = isNaN(d.gap) ? "" : (d.gap >= 0 ? "pt-row-pos" : "pt-row-neg");
        return `
        <tr class="${cls}">
            <td>${i + 1}</td>
            <td>${d.well}</td>
            <td>${d.contractor}</td>
            <td>${d.year}</td>
            <td>${d.testDate}</td>
            <td>${isNaN(d.sug)?"-":d.sug}</td>
            <td>${isNaN(d.actual)?"-":d.actual.toFixed(1)}</td>
            <td>${isNaN(d.gap)?"-":d.gap.toFixed(1)+"%"}</td>
            <td>${isNaN(d.util)?"-":d.util.toFixed(1)+"%"}</td>
            <td>${isNaN(d.drawdown)?"-":d.drawdown}</td>
        </tr>`;
    }).join("");
}

function renderPtGapCounts(rows) {
    const box = document.getElementById("ptGapCounts");
    if (!box) return;

    let pos = 0, neg = 0;
    rows.forEach(d => {
        if (isNaN(d.gap)) return;
        if (d.gap >= 0) pos++; else neg++;
    });

    box.innerHTML = `
        <div class="pt-count-box pt-count-pos">
            <i class="fa-solid fa-arrow-trend-up"></i>
            شکاف مثبت: ${pos}
        </div>
        <div class="pt-count-box pt-count-neg">
            <i class="fa-solid fa-arrow-trend-down"></i>
            شکاف منفی: ${neg}
        </div>`;
}

function toggleWellInfo() {
    const content = document.getElementById("wellInfoContent");
    const btn = document.getElementById("wellInfoToggleBtn");
    if (!content || !btn) return;
    const hidden = (content.style.display === "none" || content.style.display === "");
    content.style.display = hidden ? "block" : "none";
    btn.textContent = hidden ? "عدم نمایش توضیحات" : "نمایش توضیحات";
}
// تطبیق دقیق نام ستون (بعد از یکسان‌سازی ی/ک و فاصله)
function getColExact(row, name) {
    const target = normalizeFa(name);
    const key = Object.keys(row).find(k => normalizeFa(k) === target);
    return key === undefined ? undefined : row[key];
}
function cleanStr(v) { return (v === undefined || v === null) ? "" : normalizeFa(v); }

// خواندن تجهیزات یک دوره؛ sfx یا "1".."5" است یا " (باز)"
function readCycleAttrs(row, sfx) {
    return {
        motor:        cleanStr(getColExact(row, `موتور${sfx}`)),
        motorType:    cleanStr(getColExact(row, `موتور نو/تعمیری${sfx}`)),
        pump:         cleanStr(getColExact(row, `پمپ${sfx}`)),
        manufacturer: cleanStr(getColExact(row, `سازنده${sfx}`)),
        pumpType:     cleanStr(getColExact(row, `پمپ نو/تعمیری${sfx}`)),
        stages:       parseNum(getColExact(row, `طبقه${sfx}`)),
        depth:        parseNum(getColExact(row, `عمق${sfx}`))
    };
}
// یکسان‌سازی حروف عربی/فارسی (ي→ی ، ك→ک) و حذف فاصله اضافی
function normalizeFa(s) {
    return String(s)
        .replace(/ي/g, "ی")
        .replace(/ك/g, "ک")
        .replace(/\u200c/g, " ")   // نیم‌فاصله → فاصله
        .replace(/\s+/g, " ")
        .trim();
}

// گرفتن ستون بر اساس کلمات کلیدی (مقاوم به ی/ک عربی و فاصله)
function getColByContains(row, ...needles) {
    const nNeedles = needles.map(normalizeFa);
    const key = Object.keys(row).find(k => {
        const nk = normalizeFa(k);
        return nNeedles.every(n => nk.includes(n));
    });
    return key ? row[key] : undefined;
}

function togglePtTable() {
    const w = document.getElementById("ptTableWrapper");
    const b = document.getElementById("ptToggleTableBtn");
    if (!w || !b) return;
    const hidden = (w.style.display==="none" || w.style.display==="");
    w.style.display = hidden ? "block" : "none";
    b.textContent = hidden ? "مخفی کردن جدول" : "نمایش/مخفی کردن جدول";
}

function downloadPumpTestExcel() {
    if (!ptComputed.length) { alert("داده‌ای برای خروجی نیست"); return; }
    const rows = getPtFiltered();
    const aoa = [[
        "نام چاه","پیمانکار","سال حفر","تاریخ آزمایش","آزمایش پمپاژ حفاری","میانگین دبی واقعی",
        "شکاف درصدی","حداکثر آبدهی","ضریب بهره‌برداری٪","افت آب"
    ]];
    rows.forEach(d=>aoa.push([
        d.well, d.contractor, d.year, d.testDate,
        isNaN(d.sug)?"":d.sug,
        isNaN(d.actual)?"":+d.actual.toFixed(1),
        isNaN(d.gap)?"":+d.gap.toFixed(1),
        isNaN(d.maxYield)?"":d.maxYield,
        isNaN(d.util)?"":+d.util.toFixed(1),
        isNaN(d.drawdown)?"":d.drawdown
    ]));
    const wb = XLSX.utils.book_new();
    const ws = XLSX.utils.aoa_to_sheet(aoa);
    XLSX.utils.book_append_sheet(wb, ws, "آزمایش پمپاژ");
    XLSX.writeFile(wb, "عملکرد_پیمانکاران_آزمایش_پمپاژ.xlsx");
}

function initPumpTestDashboard() {
    computePumpTest();
    initPumpTestFilters();
    updatePumpTest();
}

function renderWellInfoBox() {
    const box = document.getElementById("wellInfoBox");
    if (!box) return;

    const well = document.getElementById("filterWell")?.value || "all";

    // فقط وقتی یک چاه انتخاب شده
    if (well === "all") {
        box.style.display = "none";
        return;
    }

    const r = wellsData.find(x => x["نام چاه"] === well);
    if (!r) { box.style.display = "none"; return; }

    // ستون‌های توضیحی موردی
    const fields = [
        ["نام پهنه‌ای که تولید چاه به آن ارسال می‌شود", getColByContains(r, "ارسال")],
        ["علت کارکرد کمتر از انتظار", getColByContains(r, "علت", "کارکرد")],
        ["خرابی مشاهده‌شده طی آخرین بهسازی", getColByContains(r, "خرابی")],
        ["وضعیت تعیین محل چاه", getColByContains(r, "تعیین", "محل")]
    ];

    let rowsHtml = "";
    fields.forEach(([label, val]) => {
        const v = (val === undefined || val === null || String(val).trim() === "") ? "—" : val;
        rowsHtml += `
            <div class="well-info-row">
                <span class="well-info-label">${label}</span>
                <span class="well-info-value">${v}</span>
            </div>`;
    });

    box.querySelector(".well-info-content").innerHTML = rowsHtml;
    box.style.display = "block";
}
/* ============================================================
   توابع کمکی و رندر سه تب جدید (نسخه نهایی، یکتا)
============================================================ */

// --- توابع کمکی فیلتر ---
function fillOfficeSelect(selId, defaultOffice) {
    const sel = document.getElementById(selId);
    if (!sel) return;
    const offices = [...new Set(wellsData.map(r => r["اداره"]).filter(Boolean))];
    sel.innerHTML = '<option value="all">همه ادارات</option>';
    offices.forEach(o => sel.innerHTML += `<option value="${o}">${o}</option>`);
    if (defaultOffice && offices.includes(defaultOffice)) sel.value = defaultOffice;
}

// فیلتر کردن option های دراپ‌داون چاه بر اساس متن جستجو
function attachWellSearch(searchId, wellSelId) {
    const inp = document.getElementById(searchId);
    const sel = document.getElementById(wellSelId);
    if (!inp || !sel) return;
    inp.addEventListener("input", () => {
        const txt = inp.value.trim();
        [...sel.options].forEach(op => {
            if (op.value === "all") { op.style.display = "block"; return; }
            op.style.display = op.textContent.includes(txt) ? "block" : "none";
        });
    });
}

function fillWellSelectByOffice(wellSelId, officeSelId) {
    const wsel = document.getElementById(wellSelId);
    const osel = document.getElementById(officeSelId);
    if (!wsel || !osel) return;
    const office = osel.value;
    const wells = wellsData
        .filter(r => office === "all" || r["اداره"] === office)
        .map(r => r["نام چاه"]).filter(Boolean);
    wsel.innerHTML = '<option value="all">همه چاه‌ها</option>';
    [...new Set(wells)].forEach(w => wsel.innerHTML += `<option value="${w}">${w}</option>`);
}

function getTabFilteredWells(officeSelId, wellSelId) {
    const office = document.getElementById(officeSelId)?.value || "all";
    const well   = document.getElementById(wellSelId)?.value   || "all";
    return wellsData.filter(r =>
        r["نام چاه"] &&
        (office === "all" || r["اداره"] === office) &&
        (well   === "all" || r["نام چاه"] === well)
    );
}

function toggleGenericTable(wrapId, btn) {
    const w = document.getElementById(wrapId);
    if (!w) return;
    const hidden = (w.style.display === "none" || w.style.display === "");
    w.style.display = hidden ? "block" : "none";
}

// --- کمکی محاسبه ---
function lastTwoYears() {
    const ys = ALL_YEARS.slice().sort((a,b)=>a-b);
    return [ys[ys.length-2], ys[ys.length-1]];
}

function monthlyValue(row, fieldType, year, month) {
    let key;
    if (fieldType === "کارکرد")      key = `کارکرد ${month} ${year}`;
    else if (fieldType === "تولید")  key = `تولید ${year}(${month})`;
    else if (fieldType === "دبی")    key = `دبی متوسط ${year}(${month})`;
    else if (fieldType === "فشار")   key = `فشار چاه ${year}(${month})`;
    return parseNum(row[key]);
}

function kMeans(data, k, iters = 60) {
    if (data.length < k) k = Math.max(1, data.length);
    let centers = data.slice(0, k).map(d => [...d]);
    let labels = new Array(data.length).fill(0);
    for (let it = 0; it < iters; it++) {
        labels = data.map(d => {
            let best = 0, bestD = Infinity;
            centers.forEach((c, i) => {
                const dist = c.reduce((s, v, j) => s + (v - d[j]) ** 2, 0);
                if (dist < bestD) { bestD = dist; best = i; }
            });
            return best;
        });
        centers = Array.from({length: k}, (_, i) => {
            const pts = data.filter((_, j) => labels[j] === i);
            if (!pts.length) return centers[i];
            return pts[0].map((_, j) => pts.reduce((s, p) => s + p[j], 0) / pts.length);
        });
    }
    return labels;
}

// --- رندر نقشه حرارتی ---
function renderHeatmap() {
    const container = document.getElementById("heatmapContainer");
    if (!container) return;
    const metric = document.getElementById("hmMetric")?.value || "تولید";
    const year   = document.getElementById("hmYear")?.value || ALL_YEARS[ALL_YEARS.length-1];
    const rows = getTabFilteredWells("hmOffice", "hmWell");

// فقط برای بررسی خالی‌نبودن کل جدول
    let anyVal = false;
    rows.forEach(w => MONTHS.forEach(m => {
        const v = monthlyValue(w, metric, year, m);
        if (!isNaN(v) && v > 0) anyVal = true;
    }));
    if (!anyVal) { container.innerHTML = '<p style="padding:20px;color:#888;">داده‌ای برای این متریک/سال موجود نیست</p>'; return; }

    // میانگین ۱۲ ماهه‌ی هر چاه (فقط ماه‌های دارای داده‌ی همان چاه)
    function wellMean(w) {
        let s = 0, c = 0;
        MONTHS.forEach(m => {
            const v = monthlyValue(w, metric, year, m);
            if (!isNaN(v) && v > 0) { s += v; c++; }
        });
        return c ? s / c : NaN;
    }

    // رنگ بر اساس درصد انحراف مقدار ماه از میانگین خودِ همان چاه
    // dev% = (v - mean) / mean * 100
    function heatColor(v, mean) {
        if (isNaN(v) || v <= 0 || isNaN(mean) || mean <= 0) return "#f1f5f9";

        const dev = (v - mean) / mean * 100;   // درصد انحراف از میانگین خودِ چاه

        // نگاشت انحراف به بازه‌ی ۰..۱ : -40% یا کمتر = ۰ (قرمز)، ۰٪ = ۰.۵ (زرد)، +40% یا بیشتر = ۱ (سبز)
        const CAP = 40;
        let t = 0.5 + (dev / CAP) * 0.5;
        t = Math.max(0, Math.min(1, t));

        // برای فشار، بالا بودن بد است → جهت رنگ برعکس
        const tc = (metric === "فشار") ? (1 - t) : t;

        let r, g;
        if (tc < 0.5) {            // قرمز → زرد
            r = 220;
            g = Math.round(60 + (tc / 0.5) * 160);
        } else {                   // زرد → سبز
            r = Math.round(220 - ((tc - 0.5) / 0.5) * 190);
            g = Math.round(180 + ((tc - 0.5) / 0.5) * 20);
        }
        return `rgb(${r}, ${g}, 60)`;
    }
    function disp(v) {
        if (isNaN(v) || v <= 0) return "—";
        if (metric === "تولید") return Math.round(v/1000) + "k";
        if (metric === "فشار")  return v.toFixed(1);
        return Math.round(v);
    }

    let html = `<table class="heatmap-table"><thead><tr><th>چاه</th>`;
    MONTHS.forEach(m => html += `<th>${m}</th>`);
    html += `</tr></thead><tbody>`;
    rows.forEach(w => {
        const wMean = wellMean(w);
        html += `<tr><td class="hm-name">${w["نام چاه"]}</td>`;
        MONTHS.forEach(m => {
            const v = monthlyValue(w, metric, year, m);
            const bg = heatColor(v, wMean);
            const tc = (isNaN(v) || v <= 0) ? "#94a3b8" : "#06202b";
            html += `<td><div class="hm-cell" style="background:${bg};color:${tc};">${disp(v)}</div></td>`;
        });
        html += `</tr>`;
    });
    html += `</tbody></table>`;
    container.innerHTML = html;
}

// --- رندر خوشه‌بندی ---
function renderCluster() {
    const year = document.getElementById("clusterYear")?.value || ALL_YEARS[ALL_YEARS.length-1];
    const k = parseInt(document.getElementById("clusterK")?.value || "4");
    const wells = getTabFilteredWells("clOffice", "clWell");
    if (!wells.length) return;

    const flow = wells.map(w => yearlyValue(w, "دبی", year) || 0);
    const prod = wells.map(w => (yearlyValue(w, "تولید", year) || 0) / 1000);
    const hours = wells.map(w => yearlyValue(w, "کارکرد", year) || 0);
    const maxF = Math.max(...flow) || 1, maxP = Math.max(...prod) || 1, maxH = Math.max(...hours) || 1;
    const norm = wells.map((_, i) => [flow[i]/maxF, prod[i]/maxP, hours[i]/maxH]);
    const labels = kMeans(norm, k);
    const clColors = ["#06b6d4", "#16a34a", "#f59e0b", "#ec4899", "#8b5cf6"];
    const clNames = ["خوشه A: کم تولید", "خوشه B: متوسط", "خوشه C: پر تولید", "خوشه D: بی‌ثبات", "خوشه E"];

    const datasets = Array.from({length: k}, (_, ci) => {
        const pts = wells.map((w, i) => labels[i] === ci ? {x: +flow[i].toFixed(2), y: +prod[i].toFixed(1), name: w["نام چاه"]} : null).filter(Boolean);
        return { label: clNames[ci], data: pts, backgroundColor: clColors[ci] + "cc", pointRadius: 7, pointHoverRadius: 10, _names: pts.map(p => p.name) };
    });
    if (charts.clusterScatter) charts.clusterScatter.destroy();
    charts.clusterScatter = new Chart(document.getElementById("clusterScatter"), {
        type: "scatter", data: { datasets },
        options: { responsive: true, maintainAspectRatio: false, animation: getAnimConfig("scatter"),
            plugins: { legend: { labels: { font: FA_FONT } },
                tooltip: { ...TOOLTIP_BASE, callbacks: { label: ctx => {
                    const nm = ctx.dataset._names[ctx.dataIndex] || "";
                    return [`چاه: ${nm}`, `دبی: ${ctx.parsed.x} l/s`, `تولید: ${ctx.parsed.y}k م.م`];
                }}}},
            scales: { x: { title:{display:true,text:"دبی (l/s)",font:FA_FONT}, beginAtZero:true, ticks:{font:NUM_FONT} },
                y: { title:{display:true,text:"تولید (هزار م.م)",font:FA_FONT}, beginAtZero:true, ticks:{font:NUM_FONT} } } }
    });

    const radarData = Array.from({length: k}, (_, ci) => {
        const idxs = wells.map((_, i) => labels[i] === ci ? i : -1).filter(i => i >= 0);
        const mean = arr => arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : 0;
        return { flow: mean(idxs.map(i => flow[i])), prod: mean(idxs.map(i => prod[i])), hours: mean(idxs.map(i => hours[i]/100)) };
    });
    if (charts.clusterRadar) charts.clusterRadar.destroy();
    charts.clusterRadar = new Chart(document.getElementById("clusterRadar"), {
        type: "radar",
        data: { labels: ["دبی (l/s)", "تولید (×۱۰۰۰)", "کارکرد (×۱۰۰h)"],
            datasets: radarData.map((d, ci) => ({ label: clNames[ci].split(":")[0], data: [d.flow, d.prod, d.hours], borderColor: clColors[ci], backgroundColor: clColors[ci] + "22", pointRadius: 3 })) },
        options: { responsive: true, maintainAspectRatio: false, animation: getAnimConfig("radar"),
            plugins: { legend: { labels: { font: FA_FONT } }, tooltip: { ...TOOLTIP_BASE } },
            scales: { r: { ticks: { font: NUM_FONT, backdropColor: "transparent" }, pointLabels: { font: FA_FONT } } } }
    });

    const legend = document.getElementById("clusterLegend");
    legend.innerHTML = Array.from({length: k}, (_, ci) => {
        const members = wells.filter((_, i) => labels[i] === ci);
        return `<div class="cluster-card-box" style="border-top-color:${clColors[ci]};">
            <div class="cluster-card-title" style="color:${clColors[ci]};">${clNames[ci]} (${members.length} چاه)</div>
            <div class="cluster-chips">${members.map(w => `<span class="cluster-chip" style="background:${clColors[ci]}22;color:${clColors[ci]};">${w["نام چاه"]}</span>`).join("")}</div>
        </div>`;
    }).join("");

    const table = document.getElementById("clusterTable");
    table.querySelector("thead").innerHTML = `<tr><th>ردیف</th><th>نام چاه</th><th>خوشه</th><th>تولید ${year}</th><th>دبی ${year}</th><th>کارکرد ${year}</th></tr>`;
    table.querySelector("tbody").innerHTML = wells.map((w, i) => `<tr>
        <td>${i+1}</td><td>${w["نام چاه"]}</td>
        <td style="color:${clColors[labels[i]]};font-weight:bold;">${clNames[labels[i]].split(":")[0]}</td>
        <td>${Math.round(yearlyValue(w,"تولید",year)||0).toLocaleString()}</td>
        <td>${(yearlyValue(w,"دبی",year)||0).toFixed(1)}</td>
        <td>${Math.round(yearlyValue(w,"کارکرد",year)||0).toLocaleString()}</td></tr>`).join("");
}

// --- رندر هشدارها (اسم یکتا، بدون تداخل) ---
function renderRiskAlerts() {
    const yPrev = document.getElementById("alYearPrev")?.value || lastTwoYears()[0];
    const yLast = document.getElementById("alYearLast")?.value || lastTwoYears()[1];
    const wells = getTabFilteredWells("alOffice", "alWell");
    const container = document.getElementById("alertsContainer");
    const alerts = [];

    wells.forEach(w => {
        const p3 = yearlyValue(w, "تولید", yPrev), p4 = yearlyValue(w, "تولید", yLast);
        if (!isNaN(p3) && !isNaN(p4) && p3 > 0 && p4 < p3 * 0.7)
            alerts.push({type:"danger", icon:"📉", title:`افت شدید تولید: ${w["نام چاه"]}`, desc:`کاهش ${Math.round((1-p4/p3)*100)}٪ از ${yPrev} به ${yLast}`});
        if (!isNaN(p4) && p4 === 0)
            alerts.push({type:"danger", icon:"🔴", title:`چاه متوقف: ${w["نام چاه"]}`, desc:`تولید صفر در سال ${yLast}`});
        const presVals = MONTHS.map(m => monthlyValue(w, "فشار", yLast, m)).filter(v => !isNaN(v) && v > 0);
        if (presVals.length && Math.max(...presVals) > 8)
            alerts.push({type:"warning", icon:"⚠️", title:`فشار بالا: ${w["نام چاه"]}`, desc:`حداکثر فشار ${Math.max(...presVals).toFixed(1)} بار در ${yLast}`});
        const f3 = yearlyValue(w, "دبی", yPrev), f4 = yearlyValue(w, "دبی", yLast);
        if (!isNaN(f3) && !isNaN(f4) && f3 > 0 && f4 > f3 * 1.3)
            alerts.push({type:"success", icon:"📈", title:`بهبود دبی: ${w["نام چاه"]}`, desc:`افزایش ${Math.round((f4/f3-1)*100)}٪ از ${yPrev} به ${yLast}`});
    });

    container.innerHTML = alerts.length
        ? alerts.map(a => `<div class="alert-card ${a.type}"><div class="alert-card-icon">${a.icon}</div><div><div class="alert-card-title">${a.title}</div><div class="alert-card-desc">${a.desc}</div></div></div>`).join("")
        : `<div class="alert-card info"><div class="alert-card-icon">✅</div><div><div class="alert-card-title">هشداری یافت نشد</div></div></div>`;

    const declines = wells.map(w => {
        const p3 = yearlyValue(w, "تولید", yPrev), p4 = yearlyValue(w, "تولید", yLast);
        return (!isNaN(p3) && !isNaN(p4) && p3 > 0) ? +((p4-p3)/p3*100).toFixed(1) : null;
    });
    if (charts.declineChart) charts.declineChart.destroy();
    charts.declineChart = new Chart(document.getElementById("declineChart"), {
        type: "bar",
        data: { labels: wells.map(w => w["نام چاه"]), datasets: [{ label: "تغییر تولید٪", data: declines, backgroundColor: declines.map(v => v===null ? "#cbd5e1" : v>=0 ? "#16a34a" : "#ef4444"), borderRadius: 4 }] },
        options: { responsive: true, maintainAspectRatio: false, indexAxis: "y", animation: getAnimConfig("bar"),
            plugins: { legend:{display:false}, tooltip:{...TOOLTIP_BASE, callbacks:{label:c=> (c.parsed.x===null?"—":c.parsed.x.toFixed(1)+"%")}} },
            scales: { x:{ ticks:{font:NUM_FONT, callback:v=>v+"%"} }, y:{ ticks:{font:FA_FONT} } } }
    });

    const stability = wells.map(w => {
        const vals = MONTHS.map(m => monthlyValue(w, "تولید", yLast, m)).filter(v => !isNaN(v) && v > 0);
        if (vals.length < 2) return null;
        const mean = vals.reduce((a,b)=>a+b,0)/vals.length;
        const std = Math.sqrt(vals.reduce((a,b)=>a+(b-mean)**2,0)/vals.length);
        return mean > 0 ? +((std/mean*100).toFixed(1)) : null;
    });
    if (charts.stabilityChart) charts.stabilityChart.destroy();
    charts.stabilityChart = new Chart(document.getElementById("stabilityChart"), {
        type: "bar",
        data: { labels: wells.map(w => w["نام چاه"]), datasets: [{ label: "ضریب تغییرات٪", data: stability, backgroundColor: stability.map(v => v===null ? "#cbd5e1" : v<10 ? "#16a34a" : v<25 ? "#f59e0b" : "#ef4444"), borderRadius: 4 }] },
        options: { responsive: true, maintainAspectRatio: false, indexAxis: "y", animation: getAnimConfig("bar"),
            plugins: { legend:{display:false}, tooltip:{...TOOLTIP_BASE, callbacks:{label:c=> (c.parsed.x===null?"—":"CV: "+c.parsed.x.toFixed(1)+"%")}} },
            scales: { x:{ beginAtZero:true, ticks:{font:NUM_FONT, callback:v=>v+"%"} }, y:{ ticks:{font:FA_FONT} } } }
    });

    const table = document.getElementById("riskTable");
    table.querySelector("thead").innerHTML = `<tr><th>ردیف</th><th>نام چاه</th><th>تولید ${yPrev}</th><th>تولید ${yLast}</th><th>تغییر٪</th><th>CV٪</th><th>وضعیت</th></tr>`;
    table.querySelector("tbody").innerHTML = wells.map((w, i) => {
        const p3 = yearlyValue(w, "تولید", yPrev), p4 = yearlyValue(w, "تولید", yLast);
        const chg = (!isNaN(p3) && !isNaN(p4) && p3>0) ? ((p4-p3)/p3*100) : null;
        const cv = stability[i];
        let status = "🔵 پایدار";
        if (isNaN(p4) || p4 === 0) status = "🔴 متوقف";
        else if (chg !== null && chg < -30) status = "🟡 نگران‌کننده";
        else if (chg !== null && chg > 20) status = "🟢 بهبود";
        return `<tr><td>${i+1}</td><td>${w["نام چاه"]}</td>
            <td>${isNaN(p3)?"—":Math.round(p3).toLocaleString()}</td>
            <td>${isNaN(p4)?"—":Math.round(p4).toLocaleString()}</td>
            <td style="color:${chg===null?'#888':chg>=0?'#16a34a':'#ef4444'};font-weight:bold;">${chg===null?"—":chg.toFixed(1)+"%"}</td>
            <td>${cv===null?"—":cv.toFixed(1)+"%"}</td><td>${status}</td></tr>`;
    }).join("");
}

// --- خروجی اکسل سه تب ---
function downloadHeatmapExcel() {
    const metric = document.getElementById("hmMetric")?.value || "تولید";
    const year   = document.getElementById("hmYear")?.value || ALL_YEARS[ALL_YEARS.length-1];
    const rows = getTabFilteredWells("hmOffice", "hmWell");
    if (!rows.length) { alert("داده‌ای نیست"); return; }
    const aoa = [["نام چاه", ...MONTHS]];
    rows.forEach(w => {
        const r = [w["نام چاه"]];
        MONTHS.forEach(m => { const v = monthlyValue(w, metric, year, m); r.push(isNaN(v) ? "" : +v.toFixed(1)); });
        aoa.push(r);
    });
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(aoa), "نقشه حرارتی");
    XLSX.writeFile(wb, `نقشه_حرارتی_${metric}_${year}.xlsx`);
}
function downloadClusterExcel() {
    const table = document.getElementById("clusterTable");
    if (!table || !table.querySelector("tbody").innerHTML.trim()) { alert("ابتدا وارد تب خوشه‌بندی شوید"); return; }
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.table_to_sheet(table), "خوشه‌بندی");
    XLSX.writeFile(wb, "خوشه_بندی.xlsx");
}
function downloadRiskExcel() {
    const table = document.getElementById("riskTable");
    if (!table || !table.querySelector("tbody").innerHTML.trim()) { alert("ابتدا وارد تب هشدارها شوید"); return; }
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.table_to_sheet(table), "تحلیل ریسک");
    XLSX.writeFile(wb, "تحلیل_ریسک.xlsx");
}
/* ============================================================
   خط زمانی نصب/کشیدن + خلاصه عملکرد پیمانکاران
============================================================ */
let _latestYMCache = null;
let _contractorStatsCache = null;

// آخرین ماهِ دارای داده (به‌عنوان «امروز» برای نصب‌های باز)
function getLatestDataYM() {
    if (_latestYMCache) return _latestYMCache;
    let best = null;
    (wellsData || []).forEach(r => {
        ALL_YEARS.forEach(y => {
            MONTHS.forEach((m, i) => {
                const v = parseNum(r[`دبی متوسط ${y}(${m})`]);
                if (!isNaN(v)) {
                    const mn = i + 1;
                    if (!best || y > best.year || (y === best.year && mn > best.month)) best = { year: y, month: mn };
                }
            });
        });
    });
    _latestYMCache = best || { year: ALL_YEARS[ALL_YEARS.length - 1], month: 12 };
    return _latestYMCache;
}

function jToFloat(d) { return d ? d.year * 12 + (d.month - 1) + (d.day ? (d.day - 1) / 30 : 0) : NaN; }
function ymShort(d) { return `${d.year}/${String(d.month).padStart(2, "0")}`; }

// ستون پیمانکار(ها) — کل مقدار به‌عنوان یک پیمانکار در نظر گرفته می‌شود
function getWellContractor(row) {
    const raw = getColByContains(row, "پیمانکار", "ها");
    const s = (raw === undefined || raw === null) ? "" : normalizeFa(raw);
    return s || "نامشخص";
}

// استخراج دوره‌های نصب/کشیدن یک چاه
function getWellCycles(row, todayF) {
    const cycles = [];
    for (let i = 1; i <= 5; i++) {
        const instD = parseJalaliDate(getColExact(row, `نصب${i}`));
        if (!instD) continue;
        const pullD = parseJalaliDate(getColExact(row, `کشیدن${i}`));
        const gapCol = parseNum(getColByContains(row, `فاصله${i}`));
        const instF = jToFloat(instD);
        const attrs = readCycleAttrs(row, String(i));
        if (pullD) {
            const pullF = jToFloat(pullD);
            cycles.push({ idx: i, install: instD, pull: pullD, installF: instF, pullF, open: false,
                duration: !isNaN(gapCol) ? gapCol : (pullF - instF), ...attrs });
        } else {
            cycles.push({ idx: i, install: instD, pull: null, installF: instF, pullF: todayF, open: true,
                duration: todayF - instF, ...attrs });
        }
    }
    const openInstall = parseJalaliDate(getColExact(row, "نصب باز"));
    if (openInstall && !cycles.some(c => c.open)) {
        const instF = jToFloat(openInstall);
        const attrs = readCycleAttrs(row, " (باز)");
        cycles.push({ idx: cycles.length + 1, install: openInstall, pull: null, installF: instF,
            pullF: todayF, open: true, duration: todayF - instF, ...attrs });
    }
    return cycles;
}

function computeContractorStats() {
    if (_contractorStatsCache) return _contractorStatsCache;
    const ym = getLatestDataYM();
    const todayF = jToFloat({ year: ym.year, month: ym.month, day: 28 });
    const map = {};
    (wellsData || []).forEach(row => {
        const cyc = getWellCycles(row, todayF);
        if (!cyc.length) return;
        const c = getWellContractor(row);
        if (!map[c]) map[c] = { name: c, complete: [], open: [], wells: new Set() };
        map[c].wells.add(row["نام چاه"]);
        cyc.forEach(k => (k.open ? map[c].open : map[c].complete).push(k.duration));
    });
    const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : NaN;
    const list = Object.values(map).map(o => {
        const all = o.complete.concat(o.open);
        return {
            name: o.name, completeCount: o.complete.length, avgComplete: mean(o.complete),
            openCount: o.open.length, total: o.complete.length + o.open.length,
            avgTotalLife: mean(all), wellsCount: o.wells.size
        };
    });
    const maxLife = Math.max(0, ...list.map(o => isNaN(o.avgTotalLife) ? 0 : o.avgTotalLife));
    list.forEach(o => {
        o.score = (maxLife > 0 && !isNaN(o.avgTotalLife)) ? Math.round(o.avgTotalLife / maxLife * 100) : 0;
        o.adequacy = o.total >= 5 ? "کافی" : (o.total >= 3 ? "متوسط" : "کم");
    });
    list.sort((a, b) => b.score - a.score);
    _contractorStatsCache = list;
    return list;
}

function renderWellTimeline() {
    const card = document.getElementById("wellTimelineCard");
    if (!card) return;
    const hint = document.getElementById("wellTimelineHint");
    const wrap = document.getElementById("wellTimelineWrap");
    const well = document.getElementById("filterWell")?.value || "all";

    if (well === "all") { if (hint){hint.style.display="block";hint.textContent="برای نمایش خط زمانی، یک چاه را از فیلتر بالا انتخاب کنید.";} if (wrap) wrap.style.display="none"; return; }

    const ym = getLatestDataYM();
    const todayF = jToFloat({ year: ym.year, month: ym.month, day: 28 });
    const row = wellsData.find(r => r["نام چاه"] === well);
    const cycles = row ? getWellCycles(row, todayF) : [];
    if (!row || !cycles.length) { if (hint){hint.style.display="block";hint.textContent="برای این چاه اطلاعات نصب/کشیدن ثبت نشده است.";} if (wrap) wrap.style.display="none"; return; }

    if (hint) hint.style.display = "none";
    if (wrap) wrap.style.display = "block";

    const minF = Math.min(...cycles.map(c => c.installF));
    const maxF = Math.max(todayF, ...cycles.map(c => c.pullF));
    let span = maxF - minF; if (span <= 0) span = 1;
    const pad = Math.max(span * 0.05, 0.5);
    const start = minF - pad, end = maxF + pad, rng = end - start;
    const pct = v => ((v - start) / rng) * 100;

    let html = `<div class="tl-ruler"></div>`;
    cycles.forEach(c => {
        const l = pct(c.installF), r = pct(c.pullF);
        html += `<div class="tl-period ${c.open ? "open" : "complete"}" style="left:${l}%; width:${Math.max(r - l, 0.5)}%;"></div>`;
    });
    cycles.forEach(c => {
        const li = pct(c.installF);
        html += `<div class="tl-mark install" style="left:${li}%;"></div>`;
        html += `<div class="tl-label down" style="left:${li}%;">نصب${c.idx}<br>${ymShort(c.install)}</div>`;
        const lp = pct(c.pullF);
        if (!c.open) {
            html += `<div class="tl-mark pull" style="left:${lp}%;"></div>`;
            html += `<div class="tl-label up" style="left:${lp}%;">کشیدن${c.idx}<br>${ymShort(c.pull)}</div>`;
        } else {
            html += `<div class="tl-mark pull" style="left:${lp}%; background:#f59e0b;"></div>`;
            html += `<div class="tl-label up" style="left:${lp}%; color:#b45309;">تا امروز<br>${ymShort(ym)}</div>`;
        }
    });
    const yStart = Math.ceil(start / 12), yEnd = Math.floor(end / 12);
    for (let y = yStart; y <= yEnd; y++) {
        const p = pct(y * 12);
        if (p < 0 || p > 100) continue;
        html += `<div class="tl-tick" style="left:${p}%;"></div><div class="tl-tick-label" style="left:${p}%;">${y}</div>`;
    }
    document.getElementById("wellTimeline").innerHTML = html;

    document.getElementById("wellTimelineLegend").innerHTML = `
        <span><span class="dot" style="background:#15803d;"></span> نصب</span>
        <span><span class="dot" style="background:#b91c1c;"></span> کشیدن</span>
        <span><span class="dot" style="background:#22c55e;"></span> دوره کامل</span>
        <span><span class="dot" style="background:repeating-linear-gradient(45deg,#f59e0b,#f59e0b 4px,#fbbf24 4px,#fbbf24 8px);"></span> نصب باز (در حال کار)</span>`;

    renderContractorWellBox(row, cycles, ym);
}

function renderContractorWellBox(row, cycles, ym) {
    const box = document.getElementById("contractorWellBox");
    if (!box) return;
    const fmt = v => isNaN(v) ? "—" : (Math.round(v * 10) / 10).toLocaleString("fa-IR");
    const complete = cycles.filter(c => !c.open), open = cycles.filter(c => c.open);
    const totalLife = cycles.reduce((s, c) => s + (isNaN(c.duration) ? 0 : c.duration), 0);
    const avgComplete = complete.length ? complete.reduce((s, c) => s + c.duration, 0) / complete.length : NaN;
    const contractor = getWellContractor(row);
    const st = computeContractorStats().find(s => s.name === contractor);

    const wellRows = `
        <div class="cwb-row"><span class="cwb-label">نام چاه</span><span class="cwb-value">${row["نام چاه"] || "—"}</span></div>
        <div class="cwb-row"><span class="cwb-label">پیمانکار</span><span class="cwb-value">${contractor}</span></div>
        <div class="cwb-row"><span class="cwb-label">تعداد دوره کامل</span><span class="cwb-value">${complete.length}</span></div>
        <div class="cwb-row"><span class="cwb-label">تعداد نصب باز</span><span class="cwb-value">${open.length}</span></div>
        <div class="cwb-row"><span class="cwb-label">میانگین دوره کامل (ماه)</span><span class="cwb-value">${fmt(avgComplete)}</span></div>
        <div class="cwb-row"><span class="cwb-label">مجموع عمر مفید (ماه)</span><span class="cwb-value">${fmt(totalLife)}</span></div>
        <div class="cwb-row"><span class="cwb-label">وضعیت فعلی</span><span class="cwb-value">${open.length ? "در حال کار (نصب باز)" : "کشیده‌شده"}</span></div>`;
    const cRows = st ? `
        <div class="cwb-row"><span class="cwb-label">پیمانکار</span><span class="cwb-value">${st.name}</span></div>
        <div class="cwb-row"><span class="cwb-label">تعداد چاه</span><span class="cwb-value">${st.wellsCount}</span></div>
        <div class="cwb-row"><span class="cwb-label">دوره کامل</span><span class="cwb-value">${st.completeCount}</span></div>
        <div class="cwb-row"><span class="cwb-label">میانگین کامل (ماه)</span><span class="cwb-value">${fmt(st.avgComplete)}</span></div>
        <div class="cwb-row"><span class="cwb-label">نصب باز</span><span class="cwb-value">${st.openCount}</span></div>
        <div class="cwb-row"><span class="cwb-label">میانگین کل عمر مفید (ماه)</span><span class="cwb-value">${fmt(st.avgTotalLife)}</span></div>
        <div class="cwb-row"><span class="cwb-label">شاخص عملکرد</span><span class="cwb-value">${st.score} / 100</span></div>
        <div class="cwb-row"><span class="cwb-label">کفایت نمونه</span><span class="cwb-value">${st.adequacy}</span></div>`
        : `<div class="cwb-row"><span class="cwb-label">—</span><span class="cwb-value">اطلاعاتی موجود نیست</span></div>`;

    const eqRows = cycles.map(c => `
        <tr>
            <td>${c.idx}${c.open ? " (باز)" : ""}</td>
            <td>${ymShort(c.install)}</td>
            <td>${c.open ? "—" : ymShort(c.pull)}</td>
            <td>${fmt(c.duration)}</td>
            <td>${c.motor || "—"}</td>
            <td>${c.motorType || "—"}</td>
            <td>${c.pump || "—"}</td>
            <td>${c.manufacturer || "—"}</td>
            <td>${c.pumpType || "—"}</td>
            <td>${isNaN(c.stages) ? "—" : c.stages}</td>
            <td>${isNaN(c.depth) ? "—" : c.depth}</td>
        </tr>`).join("");
    const eqSection = `
        <div class="cwb-section" style="grid-column:1 / -1;">
            <h4><i class="fa-solid fa-gears"></i> جزئیات تجهیزات هر دوره</h4>
            <div style="overflow-x:auto;">
            <table class="drilling-pretty-table cwb-equip-table">
                <thead><tr><th>دوره</th><th>نصب</th><th>کشیدن</th><th>عمر (ماه)</th><th>موتور</th><th>نو/تعمیری موتور</th><th>پمپ</th><th>سازنده</th><th>نو/تعمیری پمپ</th><th>طبقه</th><th>عمق</th></tr></thead>
                <tbody>${eqRows}</tbody>
            </table></div>
        </div>`;

    box.innerHTML = `
        <div class="cwb-section"><h4><i class="fa-solid fa-circle-info"></i> خلاصه عملکرد چاه</h4>${wellRows}</div>
        <div class="cwb-section"><h4><i class="fa-solid fa-user-gear"></i> خلاصه عملکرد پیمانکار</h4>${cRows}</div>
        ${eqSection}`;
}

function renderContractorPerfTable() {
    const table = document.getElementById("contractorPerfTable");
    if (!table) return;

    const ym = getLatestDataYM();
    const todayF = jToFloat({ year: ym.year, month: ym.month, day: ym.day });
    const fmt = v => isNaN(v) ? "—" : (Math.round(v * 10) / 10).toLocaleString("fa-IR");

    // سرستون: نصب/کشیدن/فاصله برای ۵ دوره، کنار هم
    let head = `<tr><th>ردیف</th><th>نام پیمانکار</th><th>نام چاه</th>`;
    for (let i = 1; i <= 5; i++) {
        head += `<th>نصب${i}</th><th>کشیدن${i}</th><th>فاصله${i} (ماه)</th>`;
    }
    head += `<th>وضعیت فعلی</th><th>مجموع عمر مفید (ماه)</th></tr>`;
    table.querySelector("thead").innerHTML = head;

    let html = "";
    let rowNo = 1;

    const office = document.getElementById("filterOffice")?.value || "all";
    const well   = document.getElementById("filterWell")?.value   || "all";
    const rowsFiltered = (wellsData || []).filter(r =>
        (office === "all" || r["اداره"] === office) &&
        (well   === "all" || r["نام چاه"] === well)
    );

    rowsFiltered.forEach(row => {
        const cycles = getWellCycles(row, todayF);
        if (!cycles.length) return;

        const contractor = getWellContractor(row);
        const wellName = row["نام چاه"] || "—";

        // دوره‌ها را بر اساس idx در دسترس بگذار تا ستون درست پر شود
        const byIdx = {};
        cycles.forEach(c => { byIdx[c.idx] = c; });

        const hasOpen = cycles.some(c => c.open);
        const totalLife = cycles.reduce((s, c) => s + (isNaN(c.duration) ? 0 : c.duration), 0);

        let cellsHtml = "";
        for (let i = 1; i <= 5; i++) {
            const c = byIdx[i];
            if (!c) {
                cellsHtml += `<td>—</td><td>—</td><td>—</td>`;
            } else if (c.open) {
                cellsHtml += `<td>${ymShort(c.install)}</td>
                    <td style="color:#b45309;font-weight:bold;">نصب باز</td>
                    <td>${fmt(c.duration)}</td>`;
            } else {
                cellsHtml += `<td>${ymShort(c.install)}</td>
                    <td>${ymShort(c.pull)}</td>
                    <td>${fmt(c.duration)}</td>`;
            }
        }

        const statusTxt = hasOpen
            ? `<span style="color:#b45309;font-weight:bold;">در حال کار</span>`
            : `<span style="color:#15803d;">کشیده‌شده</span>`;

        html += `<tr>
            <td>${rowNo++}</td>
            <td>${contractor}</td>
            <td>${wellName}</td>
            ${cellsHtml}
            <td>${statusTxt}</td>
            <td>${fmt(totalLife)}</td>
        </tr>`;
    });

    table.querySelector("tbody").innerHTML = html ||
        `<tr><td colspan="20" style="color:#888;">داده‌ای موجود نیست</td></tr>`;
}
// هشدار: چاه‌هایی که آخرین کشیدن را دارند ولی بعد از آن دبی/تولید دارند
// (یعنی نصب مجدد انجام شده ولی تاریخ نصب باز ثبت نشده)
function renderOpenInstallWarnings() {
    const box = document.getElementById("openInstallWarnBox");
    if (!box) return;

    const suspects = [];

    (wellsData || []).forEach(row => {
        const cycles = getWellCycles(row, 0);
        if (!cycles.length) return;
        // فقط چاه‌هایی که هیچ نصبِ بازی ندارند (همه دوره‌ها کشیده شده‌اند)
        if (cycles.some(c => c.open)) return;

        // آخرین تاریخ کشیدن
        const lastPull = cycles.reduce((mx, c) => (c.pullF > mx ? c.pullF : mx), -Infinity);
        if (!isFinite(lastPull)) return;

        // آیا بعد از آخرین کشیدن، دبی یا تولید مثبت وجود دارد؟
        let lastActiveF = -Infinity;
        ALL_YEARS.forEach(y => {
            MONTHS.forEach((m, i) => {
                const f = parseNum(row[`دبی متوسط ${y}(${m})`]);
                const p = parseNum(row[`تولید ${y}(${m})`]);
                const active = (!isNaN(f) && f > 0) || (!isNaN(p) && p > 0);
                if (active) {
                    const cur = y * 12 + i;
                    if (cur > lastActiveF) lastActiveF = cur;
                }
            });
        });

        // اگر فعالیت بعد از کشیدن وجود دارد (با کمی حاشیه برای ماه کشیدن)
        if (lastActiveF > lastPull + 0.5) {
            const gapMonths = Math.round(lastActiveF - lastPull);
            suspects.push({
                well: row["نام چاه"] || "—",
                contractor: getWellContractor(row),
                lastPull: lastPull,
                months: gapMonths
            });
        }
    });

    if (!suspects.length) {
        box.innerHTML = `
            <div class="alert-card success">
                <div class="alert-card-icon">✅</div>
                <div><div class="alert-card-title">موردی یافت نشد</div>
                <div class="alert-card-desc">همه‌ی چاه‌های کشیده‌شده پس از آخرین کشیدن، فعالیتی ثبت نکرده‌اند.</div></div>
            </div>`;
        return;
    }

    // تبدیل عدد ماه پیوسته به سال/ماه برای نمایش
    const fToYM = f => {
        const y = Math.floor(f / 12);
        const mo = Math.round(f % 12) + 1;
        return `${y}/${String(mo).padStart(2, "0")}`;
    };

    const items = suspects.map(s => `
        <div class="alert-card warning">
            <div class="alert-card-icon">⚠️</div>
            <div>
                <div class="alert-card-title">${s.well} — پیمانکار: ${s.contractor}</div>
                <div class="alert-card-desc">
                    آخرین کشیدن حدود ${fToYM(s.lastPull)}، اما تا حدود ${s.months} ماه پس از آن دبی/تولید ثبت شده است.
                    احتمالاً نصب مجدد انجام شده ولی تاریخ «نصب باز» برای این چاه ثبت نشده.
                </div>
            </div>
        </div>`).join("");

    box.innerHTML = `
        <div style="color:#b45309; font-family:'BNazanin',Tahoma; margin-bottom:10px;">
            <i class="fa-solid fa-triangle-exclamation"></i> ${suspects.length} چاه مشکوک
        </div>
        ${items}`;
}
function collectCycleRecords(completedOnly) {
    const ym = getLatestDataYM();
    const todayF = jToFloat({ year: ym.year, month: ym.month, day: ym.day });
    const recs = [];
    (wellsData || []).forEach(row => {
        const well = row["نام چاه"] || "—";
        const contractor = getWellContractor(row);
        getWellCycles(row, todayF).forEach(c => {
            if (completedOnly && c.open) return;
            recs.push({ well, contractor, idx: c.idx, open: c.open, duration: c.duration,
                motor: c.motor, motorType: c.motorType, pump: c.pump,
                manufacturer: c.manufacturer, pumpType: c.pumpType, stages: c.stages, depth: c.depth });
        });
    });
    return recs;
}
function meanArr(a) { return a.length ? a.reduce((x, y) => x + y, 0) / a.length : NaN; }
function renderEquipmentAnalyses() {
    const recs = collectCycleRecords(false); // فقط دوره‌های کامل
    window._equipRecs = recs;
    renderLifeByStages(recs);
    renderLifeByEquipType(recs);
    renderLifeByManufacturer(recs);
    // renderLifeVsDepth(recs);
    renderManufacturerTable(recs);
    renderStagesTable(recs);
    renderCycleDetailTable();
}

function renderLifeByStages(recs) {
    const ctx = document.getElementById("lifeByStagesChart"); if (!ctx) return;
    const map = {};
    recs.forEach(r => { if (isNaN(r.stages) || r.stages <= 0 || isNaN(r.duration) || r.duration <= 0) return; (map[r.stages] = map[r.stages] || []).push(r.duration); });
    const keys = Object.keys(map).map(Number).sort((a, b) => a - b);
    const means = keys.map(k => +meanArr(map[k]).toFixed(1));
    const counts = keys.map(k => map[k].length);
    if (charts.lifeByStages) charts.lifeByStages.destroy();
    charts.lifeByStages = new Chart(ctx, {
        type: "bar",
        data: { labels: keys.map(k => k + " طبقه"), datasets: [{ label: "میانگین عمر (ماه)", data: means, backgroundColor: "#2563eb", borderRadius: 5 }] },
        options: { responsive: true, maintainAspectRatio: false, animation: getAnimConfig("bar"),
            plugins: { legend: { display: false }, tooltip: { ...TOOLTIP_BASE, callbacks: { afterLabel: c => `تعداد دوره: ${counts[c.dataIndex]}` } } },
            scales: { x: { ticks: { font: FA_FONT } }, y: { beginAtZero: true, ticks: { font: NUM_FONT } } } }
    });
}

function renderLifeByEquipType(recs) {
    const ctx = document.getElementById("lifeByEquipTypeChart"); if (!ctx) return;
    const sel = document.getElementById("equipTypeSelect");
    const field = sel ? sel.value : "موتور";   // "موتور" یا "پمپ"

    const map = {};
    recs.forEach(r => {
        const k = (field === "موتور") ? r.motor : r.pump;
        if (!k || k === "0" || k === "۰" || isNaN(r.duration) || r.duration <= 0) return;
        (map[k] = map[k] || []).push(r.duration);
    });

    const arr = Object.keys(map)
        .map(k => ({ name: k, mean: meanArr(map[k]), n: map[k].length }))
        .sort((a, b) => b.mean - a.mean);

    if (charts.lifeByEquipType) charts.lifeByEquipType.destroy();
    charts.lifeByEquipType = new Chart(ctx, {
        type: "bar",
        data: {
            labels: arr.map(d => d.name),
            datasets: [{
                label: `میانگین عمر (ماه) - تیپ ${field}`,
                data: arr.map(d => +d.mean.toFixed(1)),
                backgroundColor: arr.map((_, i) => PT_COLORS[i % PT_COLORS.length]),
                borderRadius: 5
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false, animation: getAnimConfig("bar"),
            plugins: {
                legend: { display: false },
                tooltip: { ...TOOLTIP_BASE, callbacks: { afterLabel: c => `تعداد دوره: ${arr[c.dataIndex].n}` } }
            },
            scales: {
                x: { ticks: { font: FA_FONT } },
                y: { beginAtZero: true, ticks: { font: NUM_FONT } }
            }
        }
    });
}

function renderLifeByManufacturer(recs) {
    const ctx = document.getElementById("lifeByManufacturerChart"); if (!ctx) return;
    const map = {};
    recs.forEach(r => { const k = r.manufacturer; if (!k || k === "0" || k === "۰" || isNaN(r.duration) || r.duration <= 0) return; (map[k] = map[k] || []).push(r.duration); });
    const arr = Object.keys(map).map(k => ({ name: k, mean: meanArr(map[k]), n: map[k].length })).sort((a, b) => b.mean - a.mean);
    if (charts.lifeByManufacturer) charts.lifeByManufacturer.destroy();
    charts.lifeByManufacturer = new Chart(ctx, {
        type: "bar",
        data: { labels: arr.map(d => d.name), datasets: [{ label: "میانگین عمر (ماه)", data: arr.map(d => +d.mean.toFixed(1)), backgroundColor: arr.map((_, i) => PT_COLORS[i % PT_COLORS.length]), borderRadius: 5 }] },
        options: { responsive: true, maintainAspectRatio: false, indexAxis: "y", animation: getAnimConfig("bar"),
            plugins: { legend: { display: false }, tooltip: { ...TOOLTIP_BASE, callbacks: { afterLabel: c => `تعداد دوره: ${arr[c.dataIndex].n}` } } },
            scales: { x: { beginAtZero: true, ticks: { font: NUM_FONT } }, y: { ticks: { font: FA_FONT } } } }
    });
}

function renderManufacturerTable(recs) {
    const table = document.getElementById("manufacturerTable"); if (!table) return;
    const map = {};
    recs.forEach(r => { const k = r.manufacturer || "نامشخص"; if (isNaN(r.duration)) return; (map[k] = map[k] || []).push(r.duration); });
    const fmt = v => isNaN(v) ? "—" : (Math.round(v * 10) / 10).toLocaleString("fa-IR");
    const rows = Object.keys(map).map(k => { const a = map[k]; return { name: k, n: a.length, mean: meanArr(a), min: Math.min(...a), max: Math.max(...a) }; }).sort((x, y) => y.mean - x.mean);
    table.querySelector("thead").innerHTML = `<tr><th>ردیف</th><th>سازنده</th><th>تعداد دوره کامل</th><th>میانگین عمر (ماه)</th><th>کمترین</th><th>بیشترین</th></tr>`;
    table.querySelector("tbody").innerHTML = rows.map((r, i) => `<tr><td>${i + 1}</td><td>${r.name}</td><td>${r.n}</td><td>${fmt(r.mean)}</td><td>${fmt(r.min)}</td><td>${fmt(r.max)}</td></tr>`).join("") || `<tr><td colspan="6" style="color:#888;">داده‌ای نیست</td></tr>`;
}

function renderStagesTable(recs) {
    const table = document.getElementById("stagesTable"); if (!table) return;
    const map = {};
    recs.forEach(r => { if (isNaN(r.stages) || isNaN(r.duration)) return; (map[r.stages] = map[r.stages] || []).push(r.duration); });
    const fmt = v => isNaN(v) ? "—" : (Math.round(v * 10) / 10).toLocaleString("fa-IR");
    const keys = Object.keys(map).map(Number).sort((a, b) => a - b);
    table.querySelector("thead").innerHTML = `<tr><th>تعداد طبقه</th><th>تعداد دوره کامل</th><th>میانگین عمر (ماه)</th><th>کمترین</th><th>بیشترین</th></tr>`;
    table.querySelector("tbody").innerHTML = keys.map(k => { const a = map[k]; return `<tr><td>${k}</td><td>${a.length}</td><td>${fmt(meanArr(a))}</td><td>${fmt(Math.min(...a))}</td><td>${fmt(Math.max(...a))}</td></tr>`; }).join("") || `<tr><td colspan="5" style="color:#888;">داده‌ای نیست</td></tr>`;
}

function renderCycleDetailTable() {
    const table = document.getElementById("cycleDetailTable"); if (!table) return;
    const recs = collectCycleRecords(false); // شامل نصب باز
    const fmt = v => isNaN(v) ? "—" : (Math.round(v * 10) / 10).toLocaleString("fa-IR");
    table.querySelector("thead").innerHTML = `<tr><th>ردیف</th><th>نام چاه</th><th>پیمانکار</th><th>دوره</th><th>موتور</th><th>نو/تعمیری موتور</th><th>پمپ</th><th>سازنده</th><th>نو/تعمیری پمپ</th><th>طبقه</th><th>عمق</th><th>عمر (ماه)</th><th>وضعیت</th></tr>`;
    table.querySelector("tbody").innerHTML = recs.map((r, i) => `<tr>
        <td>${i + 1}</td><td>${r.well}</td><td>${r.contractor}</td><td>${r.idx}</td>
        <td>${r.motor || "—"}</td><td>${r.motorType || "—"}</td><td>${r.pump || "—"}</td><td>${r.manufacturer || "—"}</td>
        <td>${r.pumpType || "—"}</td><td>${isNaN(r.stages) ? "—" : r.stages}</td><td>${isNaN(r.depth) ? "—" : r.depth}</td>
        <td>${fmt(r.duration)}</td><td>${r.open ? '<span style="color:#b45309;font-weight:bold;">نصب باز</span>' : '<span style="color:#15803d;">کامل</span>'}</td></tr>`).join("") || `<tr><td colspan="13" style="color:#888;">داده‌ای نیست</td></tr>`;
}
function downloadCycleAnalysisExcel() {
    const recs = collectCycleRecords(false);
    if (!recs.length) { alert("داده‌ای نیست"); return; }
    const aoa = [["نام چاه","پیمانکار","دوره","موتور","نو/تعمیری موتور","پمپ","سازنده","نو/تعمیری پمپ","طبقه","عمق","عمر (ماه)","وضعیت"]];
    recs.forEach(r => aoa.push([r.well, r.contractor, r.idx, r.motor, r.motorType, r.pump, r.manufacturer, r.pumpType,
        isNaN(r.stages) ? "" : r.stages, isNaN(r.depth) ? "" : r.depth, isNaN(r.duration) ? "" : +r.duration.toFixed(1), r.open ? "نصب باز" : "کامل"]));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(aoa), "تجهیزات دوره‌ها");
    XLSX.writeFile(wb, "تحلیل_تجهیزات_دوره_ها.xlsx");
}
function downloadManufacturerExcel() {
    const t = document.getElementById("manufacturerTable");
    if (!t || !t.querySelector("tbody").innerHTML.trim()) { alert("داده‌ای نیست"); return; }
    const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, XLSX.utils.table_to_sheet(t), "سازنده");
    XLSX.writeFile(wb, "تحلیل_سازنده.xlsx");
}
function downloadStagesExcel() {
    const t = document.getElementById("stagesTable");
    if (!t || !t.querySelector("tbody").innerHTML.trim()) { alert("داده‌ای نیست"); return; }
    const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, XLSX.utils.table_to_sheet(t), "طبقات");
    XLSX.writeFile(wb, "تحلیل_طبقات.xlsx");
}
function downloadContractorPerfExcel() {
    const t = document.getElementById("contractorPerfTable");
    if (!t || !t.querySelector("tbody").innerHTML.trim()) { alert("داده‌ای نیست"); return; }
    const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, XLSX.utils.table_to_sheet(t), "دوره‌های پیمانکاران");
    XLSX.writeFile(wb, "خلاصه_عملکرد_پیمانکاران.xlsx");
}
function toggleTimelineSection() {
    const sec = document.getElementById("timelineSection");
    const label = document.getElementById("timelineToggleLabel");
    const chev = document.getElementById("timelineToggleChevron");
    if (!sec) return;

    const hidden = (sec.style.display === "none" || sec.style.display === "");
    sec.style.display = hidden ? "block" : "none";

    if (label) label.textContent = hidden ? "مخفی کردن خط زمانی نصب و کشیدن" : "نمایش خط زمانی نصب و کشیدن";
    if (chev)  chev.className = hidden ? "fa-solid fa-chevron-up" : "fa-solid fa-chevron-down";

    // اگر نمودارهای داخل بخش، موقع مخفی‌بودن ساخته شده‌اند و اندازه‌شان درست نیست، رفرش کن
    if (hidden) {
        setTimeout(() => {
            ["lifeByStages","lifeNewVsRepair","lifeByManufacturer","lifeVsDepth"].forEach(k => {
                if (charts[k]) charts[k].resize();
            });
        }, 60);
    }
}
document.addEventListener("DOMContentLoaded", () => {
    const sel = document.getElementById("equipTypeSelect");
    if (sel) sel.addEventListener("change", () => {
        if (window._equipRecs) renderLifeByEquipType(window._equipRecs);
    });
});
// مجموعه‌ی عنوان لیبل‌هایی که کاربر تیک زده
let _visibleFlowLabels = new Set();

function toggleFlowLabelsMenu() {
    const menu = document.getElementById("flowLabelsMenu");
    if (!menu) return;
    const open = menu.style.display === "block";
    menu.style.display = open ? "none" : "block";
    if (!open) buildFlowLabelsMenu();
}

// ساخت محتوای منو بر اساس annotationهای نمودار دبی فعلی
function buildFlowLabelsMenu() {
    const menu = document.getElementById("flowLabelsMenu");
    if (!menu) return;
    const ch = charts["chartFlow"];
    const anns = ch?.options?.plugins?.annotation?.annotations || {};
    const keys = Object.keys(anns);

    if (!keys.length) {
        menu.innerHTML = `<div class="flm-empty">برای این انتخاب، لیبلی موجود نیست. (یک چاه را انتخاب کنید)</div>`;
        return;
    }

    let html = `<div class="flm-actions">
        <button class="flm-all" onclick="setAllFlowLabels(true)">همه</button>
        <button class="flm-none" onclick="setAllFlowLabels(false)">هیچ‌کدام</button>
    </div>`;

    keys.forEach(k => {
        const title = anns[k]._title || k;
        const checked = _visibleFlowLabels.has(title) ? "checked" : "";
        html += `<label class="flm-item">
            <input type="checkbox" ${checked} onchange="toggleFlowLabel('${title.replace(/'/g, "\\'")}', this.checked)">
            <span>${title}</span>
        </label>`;
    });
    menu.innerHTML = html;
}

function applyFlowLabelVisibility() {
    const ch = charts["chartFlow"];
    if (!ch) return;
    const anns = ch.options.plugins.annotation.annotations || {};
    Object.keys(anns).forEach(k => {
        const show = _visibleFlowLabels.has(anns[k]._title);
        anns[k].display = show;            // خود خط عمودی
        if (anns[k].label) anns[k].label.display = show;  // لیبل
    });
    ch.update("none");
}

function toggleFlowLabel(title, checked) {
    if (checked) _visibleFlowLabels.add(title);
    else _visibleFlowLabels.delete(title);
    applyFlowLabelVisibility();
}

function setAllFlowLabels(on) {
    const ch = charts["chartFlow"];
    const anns = ch?.options?.plugins?.annotation?.annotations || {};
    _visibleFlowLabels = new Set();
    if (on) Object.keys(anns).forEach(k => _visibleFlowLabels.add(anns[k]._title));
    applyFlowLabelVisibility();
    buildFlowLabelsMenu();
}

// بستن منو با کلیک بیرون از آن
document.addEventListener("click", (e) => {
    const menu = document.getElementById("flowLabelsMenu");
    const btn = document.getElementById("flowLabelsBtn");
    if (!menu || !btn) return;
    if (menu.style.display === "block" && !menu.contains(e.target) && !btn.contains(e.target)) {
        menu.style.display = "none";
    }
});
// ستون نوع چاه را با getColByContains می‌خوانیم تا به اختلاف فاصله/حروف مقاوم باشد
function getWellType(row) {
    const v = getColByContains(row, "نوع", "چاه");
    return (v === undefined || v === null) ? "" : normalizeFa(v);
}

// باز/بسته کردن پنل (با حفظ وضعیت)
function toggleWellTypePanel() {
    const body = document.getElementById("wellTypeBody");
    const chev = document.getElementById("wellTypeChevron");
    if (!body) return;
    const collapsed = body.classList.toggle("collapsed");
    if (chev) chev.className = collapsed ? "fa-solid fa-chevron-left" : "fa-solid fa-chevron-down";
    try { localStorage.setItem("wellTypePanelCollapsed", collapsed ? "1" : "0"); } catch (e) {}
}

function restoreWellTypePanelState() {
    const body = document.getElementById("wellTypeBody");
    const chev = document.getElementById("wellTypeChevron");
    if (!body) return;
    const collapsed = (function(){ try { return localStorage.getItem("wellTypePanelCollapsed") === "1"; } catch(e){ return false; } })();
    if (collapsed) { body.classList.add("collapsed"); if (chev) chev.className = "fa-solid fa-chevron-left"; }
}

let _selectedWellType = "all";

// انتخاب نوع چاه → لیست چاه‌های همان نوع
function selectWellType(type, btn) {
    _selectedWellType = type;
    document.querySelectorAll("#wellTypeButtons .wt-btn").forEach(b => b.classList.remove("active"));
    if (btn) btn.classList.add("active");
    fillWellTypeWellList();
    applyWellTypeToCharts();   // تغییر نوع، بدون انتخاب چاه خاص → کل گروه
}

function fillWellTypeWellList() {
    const box = document.getElementById("wellTypeWellList");
    if (!box) return;
    const wells = (wellsData || [])
        .filter(r => _selectedWellType === "all" || getWellType(r) === _selectedWellType)
        .map(r => r["نام چاه"]).filter(Boolean);
    const uniq = [...new Set(wells)];
    if (!uniq.length) { box.innerHTML = `<span class="welltype-empty">چاهی برای این نوع یافت نشد</span>`; return; }
    box.innerHTML = uniq.map(w =>
        `<button class="wt-well" data-well="${w}" onclick="selectWellTypeWell('${w.replace(/'/g, "\\'")}', this)">${w}</button>`
    ).join("");
}

// انتخاب تک‌مقداری یک چاه
function selectWellTypeWell(wellName, btn) {
    const already = btn.classList.contains("selected");
    document.querySelectorAll("#wellTypeWellList .wt-well").forEach(b => b.classList.remove("selected"));
    if (already) {
        // اگر روی همان چاه دوباره زد → لغو انتخاب
        syncMainWellFilter("all");
    } else {
        btn.classList.add("selected");
        syncMainWellFilter(wellName);
    }
}

// همگام‌سازی با فیلتر اصلی چاه + اداره و رفرش همه‌ی نمودارها
function syncMainWellFilter(wellName) {
    const wellSel = document.getElementById("filterWell");
    if (wellSel) {
        // مطمئن شو option موجود است
        if (wellName !== "all" && ![...wellSel.options].some(o => o.value === wellName)) {
            const op = document.createElement("option");
            op.value = wellName; op.textContent = wellName;
            wellSel.appendChild(op);
        }
        wellSel.value = wellName;
    }
    updateOverviewStats();
    updateCharts();
    renderStatsTable();
}

// وقتی فقط نوع انتخاب شده (نه یک چاه خاص)، نمودارها گروهِ آن نوع را نشان دهند
function applyWellTypeToCharts() {
    // انتخاب چاه را پاک کن
    const wellSel = document.getElementById("filterWell");
    if (wellSel) wellSel.value = "all";
    document.querySelectorAll("#wellTypeWellList .wt-well").forEach(b => b.classList.remove("selected"));
    updateOverviewStats();
    updateCharts();
    renderStatsTable();
    if (typeof updateGroupSection === "function") safe(() => updateGroupSection(), "updateGroupSection");
}
// متن پروانه‌ی چاهِ انتخاب‌شده (وقتی یک چاه فیلتر شده)؛ خالی = نمایش نده
let _permitBoxText = "";

const permitBoxPlugin = {
    id: "permitBoxPlugin",
    afterDraw(chart) {
        return;   // باکس روی نمودار کشیده نشود؛ به‌جای آن در HTML کنار دکمه نمایش داده می‌شود
        if (chart.canvas.id !== "chartFlow") return;
        if (!_permitBoxText) return;
        const { ctx, chartArea } = chart;
        if (!chartArea) return;

        const label = "پروانه چاه";
        const value = _permitBoxText;

        ctx.save();
        ctx.font = "bold 13px 'BNazanin', Tahoma, Arial";
        const valW = ctx.measureText(value).width;
        const labW = ctx.measureText(label).width;
        const boxW = Math.max(valW, labW) + 28;
        const boxH = 48;
        // گوشه‌ی بالا-چپ ناحیه‌ی نمودار، کمی تورفته
        const x = chartArea.left + 12;
        const y = chartArea.top + 12;

        // پس‌زمینه
        ctx.fillStyle = "rgba(124,58,237,0.10)";
        ctx.strokeStyle = "#7c3aed";
        ctx.lineWidth = 1.5;
        if (ctx.roundRect) {
            ctx.beginPath(); ctx.roundRect(x, y, boxW, boxH, 10); ctx.fill(); ctx.stroke();
        } else {
            ctx.fillRect(x, y, boxW, boxH); ctx.strokeRect(x, y, boxW, boxH);
        }

        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        // عنوان
        ctx.fillStyle = "#6d28d9";
        ctx.font = "12px 'BNazanin', Tahoma, Arial";
        ctx.fillText(label, x + boxW / 2, y + 15);
        // مقدار
        ctx.fillStyle = "#4c1d95";
        ctx.font = "bold 14px 'BNazanin', Tahoma, Arial";
        ctx.fillText(value, x + boxW / 2, y + 33);
        ctx.restore();
    }
};

// ثبت plugin (یک‌بار)
if (typeof Chart !== "undefined" && !Chart.registry.plugins.get("permitBoxPlugin")) {
    Chart.register(permitBoxPlugin);
}
let postTestProdChartInstance = null;

// آخرین ماهِ دارای داده (سال/ماه) برای محاسبه‌ی تعداد ماه‌های سپری‌شده
function postTest_latestYM() {
    const ym = getLatestDataYM();   // از قبل موجود است: تاریخ امروز شمسی
    return { year: ym.year, month: ym.month };
}

// تعداد ماه‌های کامل از (afterY/afterM) تا آخرین تاریخ، فقط ماه‌هایی که <= آخرین داده‌اند
function monthsSince(afterY, afterM) {
    const last = postTest_latestYM();
    let cnt = 0;
    ALL_YEARS.forEach(y => {
        MONTHS.forEach((m, i) => {
            const mn = i + 1;
            // فقط ماه‌های بعد از تاریخ آزمایش و تا آخرین تاریخ
            const afterStart = (y > afterY) || (y === afterY && mn > afterM);
            const beforeEnd  = (y < last.year) || (y === last.year && mn <= last.month);
            if (afterStart && beforeEnd) cnt++;
        });
    });
    return cnt;
}

function computePostTestData() {
    const data = getGroupFilteredData();
    const recs = [];

    data.forEach(r => {
        const testRaw = getColByContains(r, "تاریخ پایان آزمایش");
        const testDate = parseJalaliDate(testRaw);
        if (!testDate) return;

        const sug = parseNum(getColByContains(r, "دبی", "پیشنهادی"));
        if (isNaN(sug) || sug <= 0) return;

        // تولید واقعی: جمع تولید ماهانه از ماهِ بعد از آزمایش تا آخرین داده
        const last = postTest_latestYM();
        let actual = 0, flowSum = 0, flowCnt = 0, monthsCounted = 0;
        ALL_YEARS.forEach(y => {
            MONTHS.forEach((m, i) => {
                const mn = i + 1;
                const afterStart = (y > testDate.year) || (y === testDate.year && mn > testDate.month);
                const beforeEnd  = (y < last.year) || (y === last.year && mn <= last.month);
                if (!afterStart || !beforeEnd) return;
                const pv = parseNum(r[`تولید ${y}(${m})`]);
                if (!isNaN(pv)) { actual += pv; monthsCounted++; }
                const fv = parseNum(r[`دبی متوسط ${y}(${m})`]);
                if (!isNaN(fv) && fv > 0) { flowSum += fv; flowCnt++; }
            });
        });

        // تعداد ماه برای مورد انتظار (year-fraction پویا)
        const nMonths = monthsSince(testDate.year, testDate.month);
        // مورد انتظار (m³) = دبی(l/s) × 3.6 (→ m³/h) × 24 × 30 × تعداد ماه
        const expected = sug * 3.6 * 24 * 30 * nMonths;

        const avgFlow = flowCnt ? flowSum / flowCnt : NaN;
        const diff = actual - expected;

        recs.push({
            well: r["نام چاه"] || "—",
            testStr: `${testDate.year}/${String(testDate.month).padStart(2,"0")}`,
            actual, expected, diff, avgFlow, sug
        });
    });

    return recs;
}

function renderPostTestSection() {
    const recs = computePostTestData();
    const fmt0 = v => isNaN(v) ? "—" : Math.round(v).toLocaleString("fa-IR");
    const fmt1 = v => isNaN(v) ? "—" : (Math.round(v*10)/10).toLocaleString("fa-IR");

    // جدول
    const table = document.getElementById("postTestTable");
    if (table) {
        table.querySelector("thead").innerHTML = `<tr>
            <th>ردیف</th><th>نام چاه</th><th>تاریخ پایان آزمایش</th>
            <th>تولید واقعی (م³)</th><th>تولید مورد انتظار (م³)</th>
            <th>اختلاف (م³)</th><th>دبی میانگین تا امروز (l/s)</th></tr>`;
        table.querySelector("tbody").innerHTML = recs.map((d, i) => {
            const diffColor = d.diff >= 0 ? "#16a34a" : "#ef4444";
            return `<tr>
                <td>${i+1}</td><td>${d.well}</td><td>${d.testStr}</td>
                <td>${fmt0(d.actual)}</td><td>${fmt0(d.expected)}</td>
                <td style="color:${diffColor};font-weight:bold;">${fmt0(d.diff)}</td>
                <td>${fmt1(d.avgFlow)}</td></tr>`;
        }).join("") || `<tr><td colspan="7" style="color:#888;">چاهی با تاریخ پایان آزمایش یافت نشد</td></tr>`;
    }

    // نمودار (واقعی در برابر مورد انتظار)
    const ctx = document.getElementById("postTestProdChart");
    if (ctx) {
        if (postTestProdChartInstance) postTestProdChartInstance.destroy();
        postTestProdChartInstance = new Chart(ctx, {
            type: "bar",
            data: {
                labels: recs.map(d => d.well),
                datasets: [
                    { label: "تولید واقعی", data: recs.map(d => Math.round(d.actual)), backgroundColor: "#22c55e", borderRadius: 4 },
                    { label: "تولید مورد انتظار", data: recs.map(d => Math.round(d.expected)), backgroundColor: "#94a3b8", borderRadius: 4 }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false, animation: getAnimConfig("bar"),
                plugins: {
                    legend: { labels: { font: FA_FONT } },
                    tooltip: { ...TOOLTIP_BASE, callbacks: {
                        label: c => ` ${c.dataset.label}: ${c.parsed.y.toLocaleString("fa-IR")} م³`,
                        afterLabel: c => {
                            const d = recs[c.dataIndex];
                            if (!d || d.expected <= 0) return "";
                            return `اختلاف: ${Math.round((d.actual-d.expected)/d.expected*100)}%`;
                        }
                    } }
                },
                scales: {
                    x: { ticks: { font: FA_FONT, maxRotation: 60 } },
                    y: { beginAtZero: true, ticks: { font: NUM_FONT, callback: v => v.toLocaleString("fa-IR") } }
                }
            }
        });
    }
}
// مرجع: 1405/04/01  | آستانه هشدار: 3 ماه
const PERMIT_REF = { year: 1405, month: 4, day: 1 };

function togglePermitPanel() {
    const body = document.getElementById("permitPanelBody");
    const chev = document.getElementById("permitPanelChevron");
    if (!body) return;
    const collapsed = body.classList.toggle("collapsed");
    if (chev) chev.className = collapsed ? "fa-solid fa-chevron-left" : "fa-solid fa-chevron-down";
    try { localStorage.setItem("permitPanelCollapsed", collapsed ? "1" : "0"); } catch (e) {}
}
function restorePermitPanelState() {
    const body = document.getElementById("permitPanelBody");
    const chev = document.getElementById("permitPanelChevron");
    if (!body) return;
    const collapsed = (function(){ try { return localStorage.getItem("permitPanelCollapsed") === "1"; } catch(e){ return false; } })();
    if (collapsed) { body.classList.add("collapsed"); if (chev) chev.className = "fa-solid fa-chevron-left"; }
}

// اختلاف بر حسب ماه بین دو تاریخ شمسی (a منهای b)
function monthDiff(a, b) {
    return (a.year * 12 + (a.month - 1)) - (b.year * 12 + (b.month - 1));
}
// نمایش بازه به سال و ماه
function humanDuration(totalMonths) {
    const t = Math.abs(totalMonths);
    const y = Math.floor(t / 12), m = t % 12;
    if (y && m) return `${y} سال و ${m} ماه`;
    if (y) return `${y} سال`;
    return `${m} ماه`;
}

function buildPermitRecords() {
    const recs = [];
    (wellsData || []).forEach(r => {
        const raw = getColByContains(r, "اعتبار", "پروانه");
        const d = parseJalaliDate(raw);
        if (!d) return;
        const diff = monthDiff(d, PERMIT_REF);   // مثبت = هنوز مانده، منفی = گذشته
        recs.push({
            well: r["نام چاه"] || "—",
            dateStr: `${d.year}/${String(d.month).padStart(2,"0")}/${String(d.day).padStart(2,"0")}`,
            diff,
            valid: diff >= 0,
            past: diff < 0 ? humanDuration(diff) : "—",
            remain: diff >= 0 ? humanDuration(diff) : "—",
            soon: diff >= 0 && diff <= 3   // ۳ ماه یا کمتر مانده
        });
    });
    return recs;
}

function renderPermitTable() {
    const table = document.getElementById("permitTable");
    if (!table) return;
    const search = (document.getElementById("permitSearch")?.value || "").trim();
    const cat = document.getElementById("permitCategory")?.value || "all";

    let recs = buildPermitRecords();
    if (search) recs = recs.filter(d => d.well.includes(search));
    if (cat === "soon")  recs = recs.filter(d => d.soon);
    if (cat === "other") recs = recs.filter(d => !d.soon);

    // مرتب‌سازی: نزدیک‌ترین به انقضا (و منقضی‌ها) اول
    recs.sort((a, b) => a.diff - b.diff);

    table.querySelector("thead").innerHTML = `<tr>
        <th>ردیف</th><th>نام چاه</th><th>تاریخ اعتبار پروانه</th>
        <th>گذشته از تاریخ</th><th>مانده تا تاریخ</th><th>وضعیت</th></tr>`;

    table.querySelector("tbody").innerHTML = recs.map((d, i) => {
        // رنگ سلول نام: منقضی شدید قرمز، نزدیک انقضا نارنجی، معتبر سبز
        let nameBg, nameColor = "#0f172a";
        if (d.diff < -12)      { nameBg = "#fecaca"; }        // بیش از یک سال گذشته
        else if (d.diff < 0)   { nameBg = "#fed7aa"; }        // منقضی (کمتر از یک سال)
        else if (d.soon)       { nameBg = "#fef08a"; }        // ۳ ماه یا کمتر مانده
        else                   { nameBg = "#bbf7d0"; }        // معتبر
        const statusIcon = d.valid
            ? `<span style="color:#16a34a;font-weight:bold;">✔ دارد</span>`
            : `<span style="color:#dc2626;font-weight:bold;">✘ ندارد</span>`;
        return `<tr>
            <td>${i+1}</td>
            <td style="background:${nameBg};color:${nameColor};font-weight:bold;border-radius:6px;">${d.well}</td>
            <td>${d.dateStr}</td>
            <td>${d.past}</td>
            <td>${d.remain}</td>
            <td>${statusIcon}</td></tr>`;
    }).join("") || `<tr><td colspan="6" style="color:#888;">چاهی با تاریخ اعتبار پروانه یافت نشد</td></tr>`;
}

function initPermitTable() {
    document.getElementById("permitSearch")?.addEventListener("input", renderPermitTable);
    document.getElementById("permitCategory")?.addEventListener("change", renderPermitTable);
    renderPermitTable();
    restorePermitPanelState();
}