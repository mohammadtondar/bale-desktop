# بله دسکتاپ: نسخهٔ کامپیوتر بله برای ویندوز و لینوکس

[![آخرین نسخه](https://img.shields.io/github/v/release/mohammadtondar/bale-desktop?label=%D8%A2%D8%AE%D8%B1%DB%8C%D9%86%20%D9%86%D8%B3%D8%AE%D9%87)](https://github.com/mohammadtondar/bale-desktop/releases/latest)
[![دانلودها](https://img.shields.io/github/downloads/mohammadtondar/bale-desktop/total?label=%D8%AF%D8%A7%D9%86%D9%84%D9%88%D8%AF)](https://github.com/mohammadtondar/bale-desktop/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**دانلود بله برای ویندوز و کامپیوتر:** «بله دسکتاپ» برنامه‌ای رایگان و متن‌باز برای استفاده از پیام‌رسان بله روی کامپیوتر است، روی **ویندوز ۱۰ و ۱۱** و **لینوکس** (اوبونتو، دبیان، فدورا، آرچ و دیگر توزیع‌ها). با آن می‌توانید بله را مثل یک برنامهٔ معمولی کامپیوتر اجرا کنید: در پنجرهٔ خودش، با اعلان پیام، با چند حساب بله هم‌زمان، و بدون نیاز به باز نگه داشتن مرورگر.

> این برنامه **غیررسمی** است و ساختهٔ شرکت بله نیست. ورود و پیام‌رسانی مستقیم در سایت اصلی بله (`web.bale.ai`) انجام می‌شود و برنامه رمز یا پیام‌های شما را جایی نمی‌فرستد.

## دانلود بله برای کامپیوتر

| سیستم‌عامل | فایل | حجم |
|---|---|---|
| **ویندوز ۱۰ و ۱۱** (نصب‌کننده) | [bale-desktop_0.2.6_windows-setup.exe](https://github.com/mohammadtondar/bale-desktop/releases/latest/download/bale-desktop_0.2.6_windows-setup.exe) | ۲٫۴ مگابایت |
| ویندوز (قابل‌حمل، بدون نصب) | [bale-desktop_0.2.6_windows-portable.zip](https://github.com/mohammadtondar/bale-desktop/releases/latest/download/bale-desktop_0.2.6_windows-portable.zip) | ۰٫۵ مگابایت |
| **لینوکس**، همهٔ توزیع‌ها (AppImage) | [bale-desktop_0.2.6_x86_64.AppImage](https://github.com/mohammadtondar/bale-desktop/releases/latest/download/bale-desktop_0.2.6_x86_64.AppImage) | ۱ مگابایت |
| اوبونتو و دبیان (`.deb`) | [bale-desktop_0.2.6_all.deb](https://github.com/mohammadtondar/bale-desktop/releases/latest/download/bale-desktop_0.2.6_all.deb) | ۵۵ کیلوبایت |

همهٔ نسخه‌ها و تغییرات در [صفحهٔ انتشارها](https://github.com/mohammadtondar/bale-desktop/releases) است.

## امکانات

- **بله روی ویندوز و لینوکس** در پنجرهٔ جدا و سبک؛ کل برنامهٔ ویندوز حدود ۱٫۵ مگابایت است.
- **چند حساب بله روی یک کامپیوتر:** مثلاً حساب شخصی و کاری، با جابه‌جایی سریع و بدون خروج از حساب.
- **اعلان پیام جدید** در ویندوز و لینوکس، حتی وقتی پنجره بسته است. برنامه کنار ساعت می‌ماند.
- **دانلود خودکار فایل‌ها** در پوشهٔ `Downloads\bale`، بدون پنجرهٔ ذخیره و بدون بازنویسی فایل‌های قبلی.
- **دکمهٔ «اینترنت ملی»:** اگر فیلترشکن یا VPN اتصال بله را مختل کند، بله را مستقیم و با DNS ایران وصل می‌کند.
- رعایت تنظیمات بی‌صدا و پیش‌نمایش خود بله؛ پشتیبانی از میکروفون و دوربین با اجازهٔ شما.
- رایگان، بدون تبلیغ، متن‌باز با گواهی MIT.

## نصب بله روی ویندوز

1. فایل [bale-desktop_0.2.6_windows-setup.exe](https://github.com/mohammadtondar/bale-desktop/releases/latest/download/bale-desktop_0.2.6_windows-setup.exe) را دانلود کنید.
2. اجرا کنید. نیازی به دسترسی مدیر (Administrator) نیست. اگر ویندوز هشدار SmartScreen داد، «More info» و سپس «Run anyway» را بزنید؛ این هشدار برای برنامه‌های تازه و بدون امضای تجاری معمول است.
3. در صورت تمایل گزینهٔ اجرای خودکار در پس‌زمینه را بزنید تا اعلان‌ها همیشه برسند.
4. «Bale Desktop» را از منوی Start باز کنید و مثل بلهٔ وب با شمارهٔ خود وارد شوید.

نسخهٔ قابل‌حمل (zip) را هم می‌توانید از حالت فشرده خارج کنید و `BaleDesktop.exe` را مستقیم اجرا کنید. نسخهٔ ویندوز با WebView2 (موتور Edge که روی ویندوز ۱۰ و ۱۱ از پیش نصب است) و .NET Framework 4.8 کار می‌کند و چیز دیگری لازم ندارد. داده‌ها در `%LOCALAPPDATA%\BaleDesktop` نگهداری می‌شوند.

## نصب بله روی لینوکس

### AppImage (همهٔ توزیع‌ها)

```sh
wget https://github.com/mohammadtondar/bale-desktop/releases/latest/download/bale-desktop_0.2.6_x86_64.AppImage
chmod +x bale-desktop_0.2.6_x86_64.AppImage
./bale-desktop_0.2.6_x86_64.AppImage
```

نسخهٔ AppImage از GTK 3 و WebKitGTK 4.1 خود سیستم استفاده می‌کند. این‌ها در بیشتر توزیع‌ها نصب‌اند؛ اگر نباشند، برنامه دستور نصب را نشان می‌دهد. دستورها در بخش [پیش‌نیازهای لینوکس](#linux-prerequisites) هم آمده‌اند. به‌روزرسانی با AppImageUpdate پشتیبانی می‌شود.

### اوبونتو و دبیان

```sh
wget https://github.com/mohammadtondar/bale-desktop/releases/latest/download/bale-desktop_0.2.6_all.deb
sudo apt install ./bale-desktop_0.2.6_all.deb
```

بستهٔ `.deb` پیش‌نیازها را خودش نصب می‌کند. برنامه با نام «بله دسکتاپ» در منوی برنامه‌ها قرار می‌گیرد. داده‌ها و حساب‌ها بین نسخهٔ `.deb` و AppImage مشترک‌اند.

<a id="linux-prerequisites"></a>

### پیش‌نیازهای لینوکس

فقط برای AppImage یا اجرا از کد منبع لازم است؛ بستهٔ `.deb` آن‌ها را خودش نصب می‌کند. ابتدا بررسی کنید که نصب‌اند یا نه:

```sh
python3 -c 'import gi; gi.require_version("Gtk", "3.0"); gi.require_version("WebKit2", "4.1")' && echo "پیش‌نیازها نصب‌اند"
```

اگر خطا داد، دستور توزیع خود را اجرا کنید:

**اوبونتو ۲۲٫۰۴ به بعد، دبیان ۱۲ به بعد، لینوکس مینت، پاپ‌اواس:**

```sh
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-ayatanaappindicator3-0.1
```

**فدورا:**

```sh
sudo dnf install python3-gobject gtk3 webkit2gtk4.1 libayatana-appindicator-gtk3
```

**آرچ، مانجارو، اندِوراواس:**

```sh
sudo pacman -S --needed python-gobject gtk3 webkit2gtk-4.1 libayatana-appindicator
```

**اوپن‌سوزه:**

```sh
sudo zypper install python3-gobject-Gdk typelib-1_0-Gtk-3_0 typelib-1_0-WebKit2-4_1 typelib-1_0-AyatanaAppIndicator3-0_1
```

بستهٔ AppIndicator فقط برای آیکون کنار ساعت است و برنامه بدون آن هم کار می‌کند. در گنوم (به‌جز اوبونتو که از پیش دارد) آیکون کنار ساعت به افزونهٔ AppIndicator نیاز دارد:

```sh
sudo apt install gnome-shell-extension-appindicator   # اوبونتو / دبیان
sudo dnf install gnome-shell-extension-appindicator   # فدورا
```

پس از نصب افزونه، یک بار از حساب کاربری خارج و دوباره وارد شوید.

## چند حساب بله روی یک کامپیوتر

- دکمهٔ «+» در نوار بالا: ساخت پروفایل جدید، مثلاً «کاری» یا «شخصی». سپس در همان پروفایل وارد حساب بله شوید.
- فهرست نام حساب‌ها در نوار بالا: تغییر پروفایل بدون خروج از حساب قبلی.
- منوی برنامه ← «تغییر نام پروفایل»: تغییر نام حساب فعلی.

هر پروفایل کوکی، حافظهٔ وب و کش جدا دارد. همهٔ پروفایل‌های ذخیره‌شده هنگام اجرای برنامه بارگذاری می‌شوند و با بستن پنجره در پس‌زمینه می‌مانند. مصرف حافظه با تعداد حساب‌ها بیشتر می‌شود. کلیک روی اعلان، پنجرهٔ پروفایل مربوط را باز می‌کند؛ پاسخ از اعلان و پنجره‌های اختصاصی پاسخ حذف شده‌اند.

نشست قبلی در «حساب اصلی» با همان مسیر قبلی حفظ می‌شود. اطلاعات پروفایل‌ها در `~/.local/share/bale-desktop/profiles.json` و دادهٔ حساب‌های جدید در زیرپوشهٔ `profiles` نگهداری می‌شود. نام پروفایل، صرفاً نام نمایشی است؛ حساب جدید بله ایجاد نمی‌کند و ورود هر حساب را خود کاربر انجام می‌دهد.

## اعلان پیام‌ها و محدودیت‌ها

اعلان‌های معمول سیستم حفظ شده‌اند. تنظیمات بی‌صدا و پیش‌نمایش بله رعایت می‌شوند. دریافت پیام در پس‌زمینه با آداپتور فقط‌خواندنی `bridge.js` انجام می‌شود؛ هیچ API ارسال پیام از اعلان وجود ندارد. آداپتور به‌جای تکیه بر هش ثابت نسخه، نمادهای مورد نیاز را در ماژول‌های زندهٔ بله پیدا می‌کند؛ اگر ساختار عوض شود اعلان به‌جای خطای نامرئی غیرفعال می‌شود و پیام هشدار نشان داده می‌شود. ورود و اعلان‌های واقعی هر حساب باید با حساب کاربر بررسی شوند؛ تست‌های محلی جای این بررسی را نمی‌گیرند.

دریافت اعلان به روشن بودن دستگاه، اجرای برنامه و اینترنت نیاز دارد. در لینوکس شروع خودکار با ورود به دسکتاپ تنظیم نشده است؛ در ویندوز می‌توانید آن را هنگام نصب فعال کنید.

## اینترنت ملی

دکمهٔ «اینترنت ملی» در نوار بالا برای وقتی است که فیلترشکن یا VPN اتصال بله را مختل می‌کند. با روشن کردن آن، ترافیک بله دیگر از پروکسی فیلترشکن عبور نمی‌کند: نام‌ها با DNS ایران (مخابرات، شکن، الکترو) پیدا می‌شوند، تا بله نشانی داخلی خود را بدهد، و اتصال مستقیم برقرار می‌شود. اگر DNS ایران در دسترس نباشد، از DNS سیستم استفاده می‌شود. فقط ترافیک خود برنامه تغییر می‌کند و بقیهٔ سیستم همچنان از فیلترشکن استفاده می‌کند. وضعیت دکمه ذخیره می‌شود.

این کار با یک پروکسی کوچک داخل برنامه انجام می‌شود که فقط روی `127.0.0.1` و فقط برای درگاه‌های ۸۰ و ۴۴۳ کار می‌کند. رمزنگاری HTTPS دست نمی‌خورد و پروکسی محتوای پیام‌ها را نمی‌بیند. در لینوکس تغییر فوراً اعمال می‌شود و صفحه‌ها تازه‌سازی می‌شوند. در ویندوز، برنامه یک بار دوباره باز می‌شود.

محدودیت: فیلترشکن‌هایی که با «پروکسی سیستم» کار می‌کنند (مثل v2rayN، Nekoray و Hiddify در حالت پروکسی) کاملاً دور زده می‌شوند. فیلترشکن‌های حالت TUN یا VPN کامل (مثل OpenVPN، WireGuard یا حالت TUN همان برنامه‌ها) همهٔ ترافیک سیستم را می‌گیرند و برنامه نمی‌تواند از آن‌ها خارج شود. با این دکمه فقط DNS ایران استفاده می‌شود، که اگر فیلترشکن نشانی‌های ایرانی را مستقیم بفرستد (Bypass Iran / geoip:ir) کافی است.

## دانلود فایل‌های بله

فایل‌های دریافتی از بله بدون باز کردن پنجرهٔ ذخیره دانلود می‌شوند و در پوشهٔ `Downloads/bale` (محل واقعی پوشهٔ دانلود کاربر) قرار می‌گیرند. هر دو مسیر دانلود پشتیبانی می‌شود: لینک فایلی که خود بله به آن هدایت می‌کند و دانلودهای `blob:` که با کلیک روی «<a download>» ساخته می‌شوند. نام فایل از `Content-Disposition` یا صفت `download` خوانده می‌شود. فایل‌های بزرگ یا کند که دریافتشان بیش از یک ثانیه طول می‌کشد هم ذخیره می‌شوند؛ لینک فایل بله که در زبانهٔ جدید یا مستقیم (مثل عکس یا PDF) باز شود نیز دانلود می‌شود. پس از پایان دانلود، یک اعلان کوچک «ذخیره شد» پایین گوشهٔ پنجره نمایش داده می‌شود؛ با دکمهٔ «نمایش» همان پوشه باز می‌شود. اگر فایل هم‌نام قبلی وجود داشته باشد، نسخهٔ جدید با شماره ذخیره می‌شود و فایل قبلی بازنویسی نمی‌شود. لینک‌های خارج از بله همچنان در مرورگر سیستم باز می‌شوند. از منو نیز می‌توان «باز کردن پوشهٔ دانلودها» را انتخاب کرد.

## پرسش‌های رایج

### آیا بله نسخهٔ ویندوز یا کامپیوتر دارد؟

بله به‌طور رسمی نسخهٔ وب (`web.bale.ai`) و اپ موبایل دارد. «بله دسکتاپ» همان بلهٔ وب را به شکل یک برنامهٔ واقعی ویندوز و لینوکس درمی‌آورد: پنجرهٔ جدا، آیکون در منوی Start و کنار ساعت، اعلان پیام و چند حساب.

### چطور بله را روی کامپیوتر نصب کنم؟

روی ویندوز فایل [نصب‌کنندهٔ ویندوز](https://github.com/mohammadtondar/bale-desktop/releases/latest/download/bale-desktop_0.2.6_windows-setup.exe) را دانلود و اجرا کنید. روی لینوکس از [AppImage یا بستهٔ deb](#نصب-بله-روی-لینوکس) استفاده کنید. سپس با شمارهٔ موبایل خود، مثل بلهٔ وب، وارد شوید.

### آیا رایگان و امن است؟

کاملاً رایگان و متن‌باز است و کد آن در همین صفحه در دسترس است. برنامه فقط سایت اصلی بله را باز می‌کند. رمز، کد ورود و پیام‌ها مستقیم بین کامپیوتر شما و بله رد و بدل می‌شوند و به هیچ سرور دیگری فرستاده نمی‌شوند. فایل‌های نصب در GitHub Actions مستقیم از همین کد ساخته می‌شوند.

### آیا می‌توانم دو یا چند حساب بله روی یک کامپیوتر داشته باشم؟

بله. با دکمهٔ «+» در نوار بالا حساب جدید بسازید. هر حساب جدا وارد می‌شود و همه هم‌زمان اعلان می‌گیرند.

### با روشن بودن فیلترشکن، بله وصل نمی‌شود. چه کنم؟

دکمهٔ «اینترنت ملی» را در نوار بالا روشن کنید تا بله بدون عبور از فیلترشکن و با DNS ایران وصل شود. جزئیات در بخش [اینترنت ملی](#اینترنت-ملی).

### روی ویندوز ۷ یا ۸ کار می‌کند؟

خیر؛ ویندوز ۱۰ یا ۱۱ لازم است.

## اجرا از کد منبع (برای توسعه‌دهندگان)

پس از نصب [پیش‌نیازها](#linux-prerequisites):

```sh
git clone https://github.com/mohammadtondar/bale-desktop.git
cd bale-desktop
./run.sh
```

نصب برای کاربر فعلی بدون رمز مدیر، پس از نصب وابستگی‌ها:

```sh
python3 packaging/install_user.py
```

برنامه با نام «بله دسکتاپ» در منوی برنامه‌ها در دسترس است. بستن پنجره، برنامه را فعال نگه می‌دارد. برای خروج کامل از منو یا Ctrl+Q استفاده کنید. اجرای دوباره، پنجرهٔ همان برنامه را باز می‌کند. نمایش آیکون سینی در GNOME به پشتیبانی AppIndicator دسکتاپ نیاز دارد.

```sh
./run.sh --background
./run.sh --demo
python3 packaging/build_deb.py
sudo apt install ./dist/bale-desktop_0.2.6_all.deb
python3 packaging/build_appimage.py   # dist/bale-desktop_0.2.6_x86_64.AppImage
```

حالت `--demo` پیش‌نمایش آفلاین است و به حساب متصل نمی‌شود. وضعیت اتصال در راهنمای شناور آیکون اتصال در نوار بالا قرار دارد.

## آزمون

```sh
python3 -m unittest discover -s tests -v
python3 tests/webkit_bridge_test.py
python3 tests/gtk_smoke_test.py
python3 tests/download_test.py
python3 tests/blob_download_test.py
python3 tests/link_download_test.py
python3 tests/delayed_blob_download_test.py
python3 tests/national_proxy_test.py
```

آزمون GTK سه نشست واقعی WebKit را با دادهٔ ساختگی اجرا می‌کند و جداسازی کوکی و localStorage، تغییر پروفایل، حفظ پس‌زمینه، مسیر اعلان و حذف پاسخ از اعلان را بررسی می‌کند. آزمون‌های گرافیکی به نشست دسکتاپ نیاز دارند و هیچ پیام واقعی ارسال نمی‌کنند.

## Bale Desktop (English)

**Bale messenger for Windows and Linux PC.** Bale Desktop is a free, open-source, *unofficial* desktop app for the Bale messenger (بله) on Windows 10/11 and Linux. It wraps the official Bale Web app in a lightweight native window, with multiple accounts, desktop notifications, a tray icon, automatic file downloads and a "national internet" mode that bypasses a VPN's proxy for Bale.
Downloads: [Windows installer](https://github.com/mohammadtondar/bale-desktop/releases/latest/download/bale-desktop_0.2.6_windows-setup.exe) · [Windows portable](https://github.com/mohammadtondar/bale-desktop/releases/latest/download/bale-desktop_0.2.6_windows-portable.zip) · [Linux AppImage](https://github.com/mohammadtondar/bale-desktop/releases/latest/download/bale-desktop_0.2.6_x86_64.AppImage) · [Ubuntu/Debian .deb](https://github.com/mohammadtondar/bale-desktop/releases/latest/download/bale-desktop_0.2.6_all.deb).
Not affiliated with Bale; the Bale name and logo belong to their owners.

## گواهی‌نامه

کد این پروژه تحت گواهی‌نامهٔ [MIT](LICENSE) منتشر شده است؛ می‌توانید استفاده، تغییر و بازتوزیع کنید، به شرط حفظ متن گواهی‌نامه. نرم‌افزار بدون هیچ ضمانتی ارائه می‌شود.

نام و لوگوی بله متعلق به صاحبان آن است و تحت گواهی MIT این پروژه قرار نمی‌گیرد؛ لوگو فقط برای شناسایی سرویسی که این کلاینت غیررسمی به آن وصل می‌شود استفاده شده است. جزئیات در `packaging/copyright` آمده است.
