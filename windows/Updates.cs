using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace BaleDesktop
{
    /// <summary>Background and manual update checks, and the «درباره» dialog.</summary>
    public sealed partial class MainForm
    {
        readonly Timer updateTimer = new Timer();
        bool updateBusy;
        ReleaseInfo availableRelease;

        bool AutoUpdate => !(LoadSettings().TryGetValue("auto_update", out var value) && value is bool on && !on);

        void StartUpdateChecks()
        {
            // First check shortly after start, then every six hours.
            updateTimer.Interval = 30 * 1000;
            updateTimer.Tick += (s, e) =>
            {
                updateTimer.Interval = (int)Updater.Interval.TotalMilliseconds;
                _ = CheckUpdates(false, null);
            };
            updateTimer.Start();
        }

        async Task CheckUpdates(bool manual, Label status)
        {
            if ((!manual && !AutoUpdate) || updateBusy) return;
            updateBusy = true;
            if (status != null) status.Text = "در حال بررسی…";
            ReleaseInfo release;
            try { release = await Updater.FetchLatest(); }
            catch (Exception)
            {
                if (manual) Report(status, "بررسی نشد؛ اتصال به گیت‌هاب برقرار نشد.");
                return;
            }
            finally { updateBusy = false; }

            if (!Updater.IsNewer(release))
            {
                if (manual) Report(status, "آخرین نسخه را دارید (" + Updater.CurrentText + ").");
                return;
            }
            availableRelease = release;
            var version = release.Version.ToString(3);
            if (status != null) status.Text = "نسخهٔ " + version + " آمده است.";
            if (!manual && LoadSettings().TryGetValue("skipped_version", out var skipped) && skipped as string == version) return;
            if (manual || (Visible && WindowState != FormWindowState.Minimized)) UpdatePrompt(release);
            else Balloon("نسخهٔ تازهٔ بله دسکتاپ: " + version, "برای به‌روزرسانی کلیک کنید.", () =>
            {
                ShowMain();
                if (availableRelease != null) UpdatePrompt(availableRelease);
            });
        }

        void Report(Label status, string text)
        {
            if (status != null && !status.IsDisposed) status.Text = text;
            else MessageBox.Show(this, text, "بله دسکتاپ", MessageBoxButtons.OK, MessageBoxIcon.Information,
                MessageBoxDefaultButton.Button1, MessageBoxOptions.RtlReading | MessageBoxOptions.RightAlign);
        }

        void UpdatePrompt(ReleaseInfo release)
        {
            var version = release.Version.ToString(3);
            var automatic = Updater.Installed && release.Asset("_windows-setup.exe") != null;
            using (var dialog = SmallDialog("به‌روزرسانی بله دسکتاپ", S(400), S(170)))
            {
                var title = new Label { Text = "نسخهٔ " + version + " بله دسکتاپ آمده است", Font = new Font(Font.FontFamily, 11f, FontStyle.Bold),
                                        Location = new Point(S(16), S(14)), Size = new Size(S(368), S(26)) };
                var body = new Label
                {
                    Text = "نسخهٔ فعلی: " + Updater.CurrentText + "\n" +
                           (automatic ? "نسخهٔ جدید دریافت و بررسی و نصب می‌شود و بله دوباره باز می‌شود؛ حساب‌ها حفظ می‌شوند."
                                      : "صفحهٔ دانلود نسخهٔ جدید در گیت‌هاب باز می‌شود."),
                    Location = new Point(S(16), S(44)), Size = new Size(S(368), S(64)), ForeColor = Color.DimGray,
                };
                var update = new Button { Text = automatic ? "به‌روزرسانی" : "دریافت از گیت‌هاب", DialogResult = DialogResult.OK,
                                          Location = new Point(S(16), S(124)), Size = new Size(S(130), S(30)) };
                var later = new Button { Text = "بعداً", DialogResult = DialogResult.Cancel, Location = new Point(S(152), S(124)), Size = new Size(S(90), S(30)) };
                var skip = new Button { Text = "رد کردن این نسخه", DialogResult = DialogResult.Ignore, Location = new Point(S(248), S(124)), Size = new Size(S(136), S(30)) };
                dialog.Controls.AddRange(new Control[] { title, body, update, later, skip });
                dialog.AcceptButton = update;
                dialog.CancelButton = later;
                var answer = dialog.ShowDialog(this);
                if (answer == DialogResult.Ignore) SaveSetting("skipped_version", version);
                else if (answer == DialogResult.OK)
                {
                    if (automatic) _ = InstallUpdate(release);
                    else OpenExternal(release.Page);
                }
            }
        }

        async Task InstallUpdate(ReleaseInfo release)
        {
            ShowToast("در حال دریافت به‌روزرسانی…", 600, false);
            var progress = new Progress<double>(f => toastText.Text = "در حال دریافت به‌روزرسانی… " + (int)(f * 100) + "٪");
            string setup;
            try
            {
                setup = await Updater.Download(release.Asset("_windows-setup.exe"),
                                               Path.Combine(Path.GetTempPath(), "BaleDesktopUpdate"), progress);
            }
            catch (Exception error)
            {
                toast.Visible = false;
                ShowError("به‌روزرسانی انجام نشد: " + error.Message);
                return;
            }
            ShowToast("در حال نصب نسخهٔ " + release.Version.ToString(3) + "…", 30, false);
            try
            {
                // The installer closes Bale, updates it in place and starts it again.
                Process.Start(new ProcessStartInfo(setup, "/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS") { UseShellExecute = true });
            }
            catch (Exception error)
            {
                ShowError("نصب‌کننده اجرا نشد: " + error.Message);
                return;
            }
            Quit();
        }

        Form SmallDialog(string title, int width, int height) => new Form
        {
            Text = title,
            RightToLeft = RightToLeft.Yes,
            RightToLeftLayout = true,
            FormBorderStyle = FormBorderStyle.FixedDialog,
            StartPosition = FormStartPosition.CenterParent,
            MinimizeBox = false,
            MaximizeBox = false,
            ShowInTaskbar = false,
            ClientSize = new Size(width, height),
            Icon = Icon,
            Font = SystemFonts.MessageBoxFont,
        };

        void AboutDialog()
        {
            using (var dialog = SmallDialog("درباره بله دسکتاپ", S(420), S(300)))
            {
                var logo = new PictureBox { Image = new Bitmap(Icon.ToBitmap(), S(48), S(48)), SizeMode = PictureBoxSizeMode.CenterImage,
                                            Location = new Point(S(186), S(16)), Size = new Size(S(48), S(48)) };
                var name = new Label { Text = "بله دسکتاپ", Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 13f, FontStyle.Bold),
                                       TextAlign = ContentAlignment.MiddleCenter, Location = new Point(S(16), S(70)), Size = new Size(S(388), S(28)) };
                var version = new Label { Text = "نسخهٔ " + Updater.CurrentText, ForeColor = Color.DimGray,
                                          TextAlign = ContentAlignment.MiddleCenter, Location = new Point(S(16), S(98)), Size = new Size(S(388), S(20)) };
                var about = new Label
                {
                    Text = "برنامهٔ غیررسمی پیام‌رسان بله برای ویندوز و لینوکس. ساختهٔ شرکت بله نیست؛ ورود و پیام‌ها مستقیم در سایت بله انجام می‌شود. متن‌باز با گواهی MIT.",
                    TextAlign = ContentAlignment.MiddleCenter, Location = new Point(S(16), S(122)), Size = new Size(S(388), S(48)),
                };
                var link = new LinkLabel { Text = "صفحهٔ پروژه در گیت‌هاب", TextAlign = ContentAlignment.MiddleCenter,
                                           Location = new Point(S(16), S(172)), Size = new Size(S(388), S(20)) };
                link.LinkClicked += (s, e) => OpenExternal("https://github.com/" + Updater.Repo);
                var check = new Button { Text = "بررسی به‌روزرسانی", Location = new Point(S(16), S(206)), Size = new Size(S(150), S(30)) };
                var status = new Label { Location = new Point(S(172), S(206)), Size = new Size(S(232), S(30)), TextAlign = ContentAlignment.MiddleLeft };
                check.Click += async (s, e) => await CheckUpdates(true, status);
                var automatic = new CheckBox { Text = "بررسی خودکار به‌روزرسانی در پس‌زمینه", Checked = AutoUpdate,
                                               Location = new Point(S(16), S(246)), Size = new Size(S(290), S(24)) };
                automatic.CheckedChanged += (s, e) => SaveSetting("auto_update", automatic.Checked);
                var close = new Button { Text = "بستن", DialogResult = DialogResult.Cancel, Location = new Point(S(314), S(256)), Size = new Size(S(90), S(30)) };
                dialog.Controls.AddRange(new Control[] { logo, name, version, about, link, check, status, automatic, close });
                dialog.CancelButton = close;
                dialog.ShowDialog(this);
            }
        }
    }
}
