using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace BaleDesktop
{
    sealed class Session
    {
        public string ProfileId;
        public WebView2 View;
        public CoreWebView2 Core;
        public bool Ready;
        public string Status = "در حال اتصال…";
    }

    public sealed class MainForm : Form
    {
        const string HomeUrl = "https://web.bale.ai/";
        static readonly Color Green = Color.FromArgb(0x00, 0xb6, 0x98);
        static readonly HttpClient Http = new HttpClient();

        readonly bool startBackground;
        readonly string dataRoot;
        readonly ProfileStore profiles;
        readonly Dictionary<string, Session> sessions = new Dictionary<string, Session>();
        readonly HashSet<string> notified = new HashSet<string>();
        readonly Queue<string> notifiedOrder = new Queue<string>();
        readonly string bridge;
        Task<CoreWebView2Environment> environment;
        readonly bool nationalOn;
        NationalProxy national;
        ToolStripButton nationalButton;

        readonly ToolStrip header = new ToolStrip();
        readonly ToolStripComboBox picker = new ToolStripComboBox();
        readonly ToolStripLabel status = new ToolStripLabel("●");
        readonly Panel host = new Panel { Dock = DockStyle.Fill };
        readonly Panel toast = new Panel();
        readonly Label toastText = new Label();
        LinkLabel toastLink;
        readonly Timer toastTimer = new Timer();
        readonly NotifyIcon tray = new NotifyIcon();
        Action balloonClick;
        bool quitting, updatingPicker, hiddenTipShown;

        public MainForm(bool background)
        {
            startBackground = background;
            dataRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BaleDesktop");
            profiles = new ProfileStore(dataRoot);
            nationalOn = LoadSettings().TryGetValue("national", out var value) && value is bool on && on;
            using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("bridge.js"))
            using (var reader = new StreamReader(stream))
                bridge = reader.ReadToEnd();
            using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("bale.ico"))
                Icon = new Icon(stream);

            Text = "بله دسکتاپ";
            RightToLeft = RightToLeft.Yes;
            RightToLeftLayout = true;
            AutoScaleMode = AutoScaleMode.Dpi;
            ClientSize = new Size(1120, 780);
            MinimumSize = new Size(480, 400);
            StartPosition = FormStartPosition.CenterScreen;
            if (startBackground) { Opacity = 0; ShowInTaskbar = false; }

            BuildHeader();
            BuildToast();
            Controls.Add(host);
            Controls.Add(header);
            BuildTray();

            foreach (var profile in profiles.Items) EnsureSession(profile.id);
            RefreshPicker();
            SwitchProfile(profiles.Active);
        }

        // ---------- window, header and tray ----------

        void BuildHeader()
        {
            header.Dock = DockStyle.Top;
            header.GripStyle = ToolStripGripStyle.Hidden;
            header.BackColor = Green;
            header.ForeColor = Color.White;
            header.Padding = new Padding(4, 2, 4, 2);
            header.RenderMode = ToolStripRenderMode.System;
            header.Renderer = new FlatRenderer();

            var logo = new ToolStripLabel("بله") { Font = new Font(Font.FontFamily, 10f, FontStyle.Bold), Image = Icon.ToBitmap() };
            logo.ImageScaling = ToolStripItemImageScaling.SizeToFit;
            var reload = Button("⟳", "تازه‌سازی حساب فعلی (F5)", (s, e) => ReloadActive());
            nationalButton = new ToolStripButton("اینترنت ملی")
            {
                CheckOnClick = true,
                Checked = nationalOn,
                ForeColor = nationalOn ? Green : Color.White,
                Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9f, FontStyle.Bold),
                ToolTipText = "اینترنت ملی: اتصال مستقیم بله با DNS ایران، بدون عبور از پروکسی فیلترشکن.\n"
                              + "وقتی فیلترشکن بله را مختل می‌کند روشن کنید.",
            };
            nationalButton.CheckedChanged += (s, e) => NationalToggled();
            status.ToolTipText = "در حال اتصال…";
            status.ForeColor = Color.FromArgb(255, 235, 150);

            picker.DropDownStyle = ComboBoxStyle.DropDownList;
            picker.ToolTipText = "تغییر پروفایل";
            picker.Alignment = ToolStripItemAlignment.Right;
            picker.ComboBox.Width = 150;
            picker.SelectedIndexChanged += (s, e) =>
            {
                if (!updatingPicker && picker.SelectedItem is ProfileItem item) SwitchProfile(item.Id);
            };
            var add = Button("+", "افزودن حساب", (s, e) => ProfileDialog(false));
            add.Alignment = ToolStripItemAlignment.Right;

            var menu = new ToolStripDropDownButton("☰") { ShowDropDownArrow = false, Alignment = ToolStripItemAlignment.Right };
            menu.ForeColor = Color.White;
            menu.DropDownItems.Add("افزودن حساب", null, (s, e) => ProfileDialog(false));
            menu.DropDownItems.Add("تغییر نام پروفایل", null, (s, e) => ProfileDialog(true));
            menu.DropDownItems.Add("باز کردن پوشهٔ دانلودها", null, (s, e) => OpenDownloads());
            menu.DropDownItems.Add(new ToolStripSeparator());
            menu.DropDownItems.Add(new ToolStripMenuItem("خروج کامل", null, (s, e) => Quit()) { ShortcutKeys = Keys.Control | Keys.Q });

            header.Items.AddRange(new ToolStripItem[] { logo, reload, status, nationalButton, menu, picker, add });
        }

        static ToolStripButton Button(string text, string tip, EventHandler click)
        {
            var button = new ToolStripButton(text) { ToolTipText = tip, ForeColor = Color.White };
            button.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 11f, FontStyle.Bold);
            button.Click += click;
            return button;
        }

        sealed class FlatRenderer : ToolStripProfessionalRenderer
        {
            protected override void OnRenderToolStripBorder(ToolStripRenderEventArgs e) { }
            protected override void OnRenderToolStripBackground(ToolStripRenderEventArgs e)
            {
                using (var brush = new SolidBrush(Green)) e.Graphics.FillRectangle(brush, e.AffectedBounds);
            }
            protected override void OnRenderButtonBackground(ToolStripItemRenderEventArgs e)
            {
                if (e.Item is ToolStripButton toggle && toggle.Checked)
                {
                    e.Graphics.FillRectangle(Brushes.White, new Rectangle(1, 2, e.Item.Width - 2, e.Item.Height - 4));
                    return;
                }
                if (!e.Item.Selected && !e.Item.Pressed) return;
                using (var brush = new SolidBrush(Color.FromArgb(46, 255, 255, 255)))
                    e.Graphics.FillRectangle(brush, new Rectangle(Point.Empty, e.Item.Size));
            }
            protected override void OnRenderDropDownButtonBackground(ToolStripItemRenderEventArgs e) => OnRenderButtonBackground(e);
        }

        sealed class ProfileItem
        {
            public string Id, Name;
            public override string ToString() => Name;
        }

        void BuildTray()
        {
            var menu = new ContextMenuStrip { RightToLeft = RightToLeft.Yes };
            menu.Items.Add("نمایش بله", null, (s, e) => ShowMain());
            menu.Items.Add("باز کردن پوشهٔ دانلودها", null, (s, e) => OpenDownloads());
            menu.Items.Add("خروج کامل", null, (s, e) => Quit());
            tray.Icon = Icon;
            tray.Text = "بله • فعال در پس‌زمینه";
            tray.ContextMenuStrip = menu;
            tray.Visible = true;
            tray.MouseClick += (s, e) => { if (e.Button == MouseButtons.Left) ShowMain(); };
            tray.BalloonTipClicked += (s, e) => { var action = balloonClick; balloonClick = null; action?.Invoke(); };
        }

        void Balloon(string title, string body, Action click, ToolTipIcon icon = ToolTipIcon.Info)
        {
            balloonClick = click;
            tray.ShowBalloonTip(5000, title, body, icon);
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            if (startBackground)
            {
                Hide();
                Opacity = 1;
                ShowInTaskbar = true;
                UpdateBackground();
            }
        }

        public void ShowMain()
        {
            Show();
            if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
            Activate();
            UpdateBackground();
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            // Closing the window keeps Bale running in the tray, like the Linux build.
            if (!quitting && e.CloseReason == CloseReason.UserClosing)
            {
                e.Cancel = true;
                Hide();
                UpdateBackground();
                if (!hiddenTipShown)
                {
                    hiddenTipShown = true;
                    Balloon("بله در پس‌زمینه فعال است", "برای خروج کامل از منوی آیکون کنار ساعت استفاده کنید.", ShowMain);
                }
                return;
            }
            tray.Visible = false;
            base.OnFormClosing(e);
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            if (WindowState == FormWindowState.Minimized || Visible) UpdateBackground();
        }

        protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
        {
            if (keyData == (Keys.Control | Keys.Q)) { Quit(); return true; }
            if (keyData == Keys.F5) { ReloadActive(); return true; }
            return base.ProcessCmdKey(ref msg, keyData);
        }

        void Quit()
        {
            quitting = true;
            tray.Visible = false;
            Close();
            Application.Exit();
        }

        void ReloadActive()
        {
            if (sessions.TryGetValue(profiles.Active, out var session)) session.Core?.Reload();
        }

        // ---------- profiles ----------

        void RefreshPicker()
        {
            updatingPicker = true;
            picker.Items.Clear();
            foreach (var p in profiles.Items)
            {
                var item = new ProfileItem { Id = p.id, Name = p.name };
                picker.Items.Add(item);
                if (p.id == profiles.Active) picker.SelectedItem = item;
            }
            updatingPicker = false;
        }

        void SwitchProfile(string id)
        {
            try { profiles.Select(id); }
            catch (IOException) { /* still switch; the choice just is not remembered */ }
            EnsureSession(id);
            foreach (var session in sessions.Values) session.View.Visible = session.ProfileId == id;
            sessions[id].View.BringToFront();
            toast.BringToFront();
            if (!(picker.SelectedItem is ProfileItem item) || item.Id != id) RefreshPicker();
            Text = "بله — " + profiles.Get(id).name;
            status.ToolTipText = sessions[id].Status;
            UpdateBackground();
        }

        void ProfileDialog(bool rename)
        {
            using (var dialog = new Form())
            {
                dialog.Text = rename ? "تغییر نام پروفایل" : "افزودن حساب";
                dialog.RightToLeft = RightToLeft.Yes;
                dialog.RightToLeftLayout = true;
                dialog.FormBorderStyle = FormBorderStyle.FixedDialog;
                dialog.StartPosition = FormStartPosition.CenterParent;
                dialog.MinimizeBox = dialog.MaximizeBox = false;
                dialog.ShowInTaskbar = false;
                dialog.AutoScaleMode = AutoScaleMode.Dpi;
                dialog.ClientSize = new Size(340, 130);
                var entry = new TextBox { Left = 16, Top = 16, Width = 308, MaxLength = 32 };
                if (rename) entry.Text = profiles.Get(profiles.Active).name;
                var cue = new Label { Left = 16, Top = 44, Width = 308, Height = 36, ForeColor = Color.DimGray,
                                      Text = "نام پروفایل؛ مثلاً شخصی یا کاری" };
                var ok = new Button { Text = rename ? "ذخیره" : "ایجاد", Left = 16, Top = 88, Width = 90 };
                var cancel = new Button { Text = "انصراف", Left = 112, Top = 88, Width = 90, DialogResult = DialogResult.Cancel };
                dialog.Controls.AddRange(new Control[] { entry, cue, ok, cancel });
                dialog.AcceptButton = ok;
                dialog.CancelButton = cancel;
                ok.Click += (s, e) =>
                {
                    try
                    {
                        if (rename)
                        {
                            profiles.Rename(profiles.Active, entry.Text);
                            RefreshPicker();
                            Text = "بله — " + profiles.Get(profiles.Active).name;
                        }
                        else
                        {
                            var id = profiles.Add(entry.Text);
                            EnsureSession(id);
                            RefreshPicker();
                            SwitchProfile(id);
                        }
                        dialog.DialogResult = DialogResult.OK;
                    }
                    catch (ArgumentException problem) { cue.ForeColor = Color.Firebrick; cue.Text = problem.Message; }
                    catch (IOException) { cue.ForeColor = Color.Firebrick; cue.Text = "ذخیره نشد؛ فضای دیسک و دسترسی پوشه را بررسی کنید."; }
                };
                dialog.ShowDialog(this);
            }
        }

        // ---------- WebView2 sessions ----------

        Task<CoreWebView2Environment> Environment2()
        {
            // One browser process serves every account; each account is a separate
            // WebView2 profile with its own cookies, storage and cache.
            if (environment != null) return environment;
            var options = new CoreWebView2EnvironmentOptions { Language = "fa" };
            if (nationalOn)
            {
                // The browser's proxy is fixed at start, so toggling restarts the app.
                national = new NationalProxy();
                options.AdditionalBrowserArguments = "--proxy-server=http://127.0.0.1:" + national.Port;
            }
            return environment = CoreWebView2Environment.CreateAsync(null, Path.Combine(dataRoot, "WebView2"), options);
        }

        // ---------- اینترنت ملی ----------

        Dictionary<string, object> LoadSettings()
        {
            try
            {
                return new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(
                    File.ReadAllText(Path.Combine(dataRoot, "settings.json"))) ?? new Dictionary<string, object>();
            }
            catch (Exception error) when (error is IOException || error is ArgumentException
                                          || error is InvalidOperationException || error is UnauthorizedAccessException)
            {
                return new Dictionary<string, object>();
            }
        }

        void NationalToggled()
        {
            var enabled = nationalButton.Checked;
            nationalButton.ForeColor = enabled ? Green : Color.White;
            if (enabled == nationalOn) return;
            try
            {
                var settings = LoadSettings();
                settings["national"] = enabled;
                File.WriteAllText(Path.Combine(dataRoot, "settings.json"), new JavaScriptSerializer().Serialize(settings));
            }
            catch (Exception error) when (error is IOException || error is UnauthorizedAccessException)
            {
                ShowError("تنظیم ذخیره نشد: " + error.Message);
                return;
            }
            var answer = MessageBox.Show(this,
                (enabled ? "اینترنت ملی روشن می‌شود: بله مستقیم و با DNS ایران وصل می‌شود." :
                           "اینترنت ملی خاموش می‌شود: اتصال از تنظیمات سیستم انجام می‌شود.")
                + "\n\nبرای اعمال، بله دوباره باز شود؟", "بله دسکتاپ", MessageBoxButtons.YesNo, MessageBoxIcon.Question,
                MessageBoxDefaultButton.Button1, MessageBoxOptions.RtlReading | MessageBoxOptions.RightAlign);
            if (answer != DialogResult.Yes)
            {
                ShowToast("با اجرای بعدی بله اعمال می‌شود", 5, false);
                return;
            }
            try { Process.Start(new ProcessStartInfo(Application.ExecutablePath, "--restart") { UseShellExecute = false }); }
            catch (Exception error) { ShowError("اجرای دوباره نشد: " + error.Message); return; }
            Quit();
        }

        void EnsureSession(string id)
        {
            if (sessions.ContainsKey(id)) return;
            var view = new WebView2 { Dock = DockStyle.Fill, Visible = false, DefaultBackgroundColor = Color.White };
            var session = new Session { ProfileId = id, View = view };
            sessions[id] = session;
            host.Controls.Add(view);
            _ = StartSession(session);
        }

        async Task StartSession(Session session)
        {
            try
            {
                var env = await Environment2();
                var options = env.CreateCoreWebView2ControllerOptions();
                options.ProfileName = session.ProfileId;
                await session.View.EnsureCoreWebView2Async(env, options);
            }
            catch (WebView2RuntimeNotFoundException)
            {
                SetStatus(session, "WebView2 نصب نیست");
                if (session.ProfileId == profiles.Active)
                    ShowError("برای اجرای بله، «Microsoft Edge WebView2 Runtime» لازم است. آن را از سایت مایکروسافت نصب کنید.");
                return;
            }
            catch (Exception error)
            {
                SetStatus(session, "موتور وب اجرا نشد: " + error.Message);
                return;
            }
            var core = session.Core = session.View.CoreWebView2;
            var settings = core.Settings;
            settings.AreDevToolsEnabled = false;
            settings.IsStatusBarEnabled = false;
            settings.IsGeneralAutofillEnabled = false;
            settings.IsPasswordAutosaveEnabled = false;
            core.Profile.DefaultDownloadFolderPath = DownloadDirectory();

            await core.AddScriptToExecuteOnDocumentCreatedAsync(bridge);
            core.WebMessageReceived += (s, e) => BridgeMessage(session, e);
            core.NavigationStarting += (s, e) => NavigationStarting(session, e);
            core.NavigationCompleted += (s, e) =>
            {
                if (!e.IsSuccess && e.WebErrorStatus != CoreWebView2WebErrorStatus.OperationCanceled)
                    SetStatus(session, "اتصال برقرار نشد؛ دوباره تازه‌سازی کنید.");
                else if (!session.Ready) SetStatus(session, "بله وب");
                UpdateBackground();
            };
            core.NewWindowRequested += (s, e) => NewWindowRequested(e);
            core.PermissionRequested += (s, e) => PermissionRequested(session, e);
            core.NotificationReceived += (s, e) => NativeNotification(session, e);
            core.DownloadStarting += (s, e) => DownloadStarting(e);
            core.ProcessFailed += (s, e) =>
            {
                session.Ready = false;
                SetStatus(session, "موتور وب متوقف شد؛ تازه‌سازی کنید.");
            };
            core.Navigate(HomeUrl);
        }

        void SetStatus(Session session, string text)
        {
            session.Status = text;
            if (session.ProfileId == profiles.Active) status.ToolTipText = text;
            if (session.ProfileId == profiles.Active)
                status.ForeColor = session.Ready ? Color.White : Color.FromArgb(255, 235, 150);
        }

        void UpdateBackground()
        {
            var hidden = !Visible || WindowState == FormWindowState.Minimized;
            foreach (var session in sessions.Values)
            {
                if (session.Core == null) continue;
                var background = hidden || session.ProfileId != profiles.Active;
                // Hidden accounts keep receiving messages but give memory back.
                session.Core.MemoryUsageTargetLevel = background
                    ? CoreWebView2MemoryUsageTargetLevel.Low : CoreWebView2MemoryUsageTargetLevel.Normal;
                if (TrustedUrl(session.Core.Source))
                    _ = session.Core.ExecuteScriptAsync("window.BaleDesktop && window.BaleDesktop.background(" + (background ? "true" : "false") + ")");
            }
        }

        // ---------- notifications ----------

        void BridgeMessage(Session session, CoreWebView2WebMessageReceivedEventArgs e)
        {
            if (!TrustedUrl(e.Source)) return;
            try
            {
                var item = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(e.TryGetWebMessageAsString());
                switch (item.TryGetValue("kind", out var kind) ? kind as string : null)
                {
                    case "notification":
                        if (item.TryGetValue("id", out var id) && id is string idText
                            && item.TryGetValue("title", out var title) && title is string titleText
                            && item.TryGetValue("body", out var body) && body is string bodyText)
                            Notify(session.ProfileId, idText, titleText, bodyText);
                        break;
                    case "ready":
                        session.Ready = true;
                        SetStatus(session, "متصل");
                        UpdateBackground();
                        break;
                    case "adapter-error":
                        session.Ready = false;
                        SetStatus(session, item.TryGetValue("error", out var error) && error is string text
                            ? text : "دریافت اعلان نیاز به بررسی دارد.");
                        break;
                }
            }
            catch (Exception error) when (error is ArgumentException || error is InvalidOperationException) { }
        }

        void Notify(string profileId, string id, string title, string body)
        {
            var key = profileId + ":" + id;
            if (!notified.Add(key)) return;
            notifiedOrder.Enqueue(key);
            while (notifiedOrder.Count > 200) notified.Remove(notifiedOrder.Dequeue());
            var name = profiles.Get(profileId).name;
            Balloon(Clip(name + " · " + title, 63), Clip(body, 255), () =>
            {
                if (profiles.Items.Any(p => p.id == profileId)) SwitchProfile(profileId);
                ShowMain();
            });
        }

        static string Clip(string text, int length) => text.Length <= length ? text : text.Substring(0, length - 1) + "…";

        void NativeNotification(Session session, CoreWebView2NotificationReceivedEventArgs e)
        {
            // The bridge already reports messages; use the page's own notification
            // only while the bridge is not connected.
            e.Handled = true;
            if (!session.Ready)
                Notify(session.ProfileId, "native-" + e.Notification.Title + "\n" + e.Notification.Body,
                       e.Notification.Title ?? "بله", e.Notification.Body ?? "پیام جدید");
        }

        void PermissionRequested(Session session, CoreWebView2PermissionRequestedEventArgs e)
        {
            if (!TrustedUrl(e.Uri)) { e.State = CoreWebView2PermissionState.Deny; return; }
            switch (e.PermissionKind)
            {
                case CoreWebView2PermissionKind.Notifications:
                case CoreWebView2PermissionKind.ClipboardRead:
                    e.State = CoreWebView2PermissionState.Allow;
                    break;
                case CoreWebView2PermissionKind.Microphone:
                case CoreWebView2PermissionKind.Camera:
                    var deferral = e.GetDeferral();
                    BeginInvoke((Action)(() =>
                    {
                        {
                            var answer = MessageBox.Show(this, "بله — " + profiles.Get(session.ProfileId).name + ": اجازهٔ میکروفون / دوربین؟",
                                "بله دسکتاپ", MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2,
                                MessageBoxOptions.RtlReading | MessageBoxOptions.RightAlign);
                            e.State = answer == DialogResult.Yes ? CoreWebView2PermissionState.Allow : CoreWebView2PermissionState.Deny;
                            deferral.Complete();
                        }
                    }));
                    break;
                default:
                    e.State = CoreWebView2PermissionState.Deny;
                    break;
            }
        }

        // ---------- navigation policy ----------

        static bool UrlIs(string uri, params string[] hosts)
        {
            return Uri.TryCreate(uri, UriKind.Absolute, out var url) && url.Scheme == Uri.UriSchemeHttps
                && hosts.Contains(url.Host) && url.Port == 443 && string.IsNullOrEmpty(url.UserInfo);
        }

        static bool TrustedUrl(string uri) => UrlIs(uri, "web.bale.ai");
        static bool FileHost(string uri) => UrlIs(uri, "assets.bale.ai");

        static void OpenExternal(string uri)
        {
            if (Uri.TryCreate(uri, UriKind.Absolute, out var url)
                && (url.Scheme == Uri.UriSchemeHttp || url.Scheme == Uri.UriSchemeHttps
                    || url.Scheme == Uri.UriSchemeMailto || url.Scheme == "tel"))
            {
                try { Process.Start(new ProcessStartInfo(url.AbsoluteUri) { UseShellExecute = true }); }
                catch (Exception) { /* no handler for this link type */ }
            }
        }

        void NavigationStarting(Session session, CoreWebView2NavigationStartingEventArgs e)
        {
            var uri = e.Uri;
            if (TrustedUrl(uri) || uri.StartsWith("blob:") || uri.StartsWith("data:") || uri == "about:blank") return;
            e.Cancel = true;
            if (FileHost(uri)) _ = DownloadUrl(uri);   // a Bale file must be saved, not replace the app
            else if (e.IsUserInitiated) OpenExternal(uri);
        }

        void NewWindowRequested(CoreWebView2NewWindowRequestedEventArgs e)
        {
            e.Handled = true;   // never open a second, unmanaged browser window
            if (FileHost(e.Uri)) _ = DownloadUrl(e.Uri);
            else if (e.IsUserInitiated && !TrustedUrl(e.Uri)) OpenExternal(e.Uri);
        }

        // ---------- downloads ----------

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        static extern int SHGetKnownFolderPath([MarshalAs(UnmanagedType.LPStruct)] Guid id, uint flags, IntPtr token, out string path);

        static string DownloadDirectory()
        {
            string root;
            if (SHGetKnownFolderPath(new Guid("374DE290-123F-4565-9164-39C4925E467B"), 0, IntPtr.Zero, out root) != 0)
                root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
            var directory = Path.Combine(root, "bale");
            Directory.CreateDirectory(directory);
            return directory;
        }

        static string SafeName(string suggested)
        {
            var name = Path.GetFileName((suggested ?? "").Replace('/', '\\')).Trim().TrimEnd('.');
            foreach (var c in Path.GetInvalidFileNameChars()) name = name.Replace(c, '_');
            return name.Length == 0 ? "bale-file" : name;
        }

        static string UniquePath(string directory, string suggested)
        {
            var name = SafeName(suggested);
            var path = Path.Combine(directory, name);
            if (!File.Exists(path)) return path;
            var stem = Path.GetFileNameWithoutExtension(name);
            var suffix = Path.GetExtension(name);
            for (var number = 1; number < 10000; number++)
            {
                var candidate = Path.Combine(directory, stem + " (" + number + ")" + suffix);
                if (!File.Exists(candidate)) return candidate;
            }
            throw new IOException("نام فایل تکراری است");
        }

        void DownloadStarting(CoreWebView2DownloadStartingEventArgs e)
        {
            // Save straight to Downloads\bale without a dialog; never overwrite.
            string path;
            try { path = UniquePath(DownloadDirectory(), e.ResultFilePath); }
            catch (Exception error) when (error is IOException || error is UnauthorizedAccessException)
            {
                ShowError("پوشهٔ دانلود آماده نشد: " + error.Message);
                e.Cancel = true;
                return;
            }
            e.ResultFilePath = path;
            e.Handled = true;
            ShowToast("در حال دانلود · " + Path.GetFileName(path), 4);
            var operation = e.DownloadOperation;
            operation.StateChanged += (s, args) =>
            {
                if (operation.State == CoreWebView2DownloadState.Completed)
                    DownloadDone(operation.ResultFilePath);
                else if (operation.State == CoreWebView2DownloadState.Interrupted
                         && operation.InterruptReason != CoreWebView2DownloadInterruptReason.UserCanceled)
                    ShowError("دانلود کامل نشد: " + operation.InterruptReason);
            };
        }

        async Task DownloadUrl(string uri)
        {
            try
            {
                using (var response = await Http.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead))
                {
                    response.EnsureSuccessStatusCode();
                    var disposition = response.Content.Headers.ContentDisposition;
                    var name = disposition?.FileNameStar ?? disposition?.FileName?.Trim('"')
                               ?? Uri.UnescapeDataString(new Uri(uri).Segments.Last());
                    var path = UniquePath(DownloadDirectory(), name);
                    ShowToast("در حال دانلود · " + Path.GetFileName(path), 4);
                    using (var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write))
                        await response.Content.CopyToAsync(output);
                    DownloadDone(path);
                }
            }
            catch (Exception error) when (error is HttpRequestException || error is IOException
                                          || error is UnauthorizedAccessException || error is TaskCanceledException)
            {
                ShowError("دانلود کامل نشد: " + error.Message);
            }
        }

        void DownloadDone(string path)
        {
            status.ToolTipText = "دانلود شد: " + path;
            ShowToast("ذخیره شد · " + Path.GetFileName(path), 6);
            if (!Visible || !ContainsFocus)
                Balloon("فایل بله دانلود شد", Path.GetFileName(path), OpenDownloads);
        }

        void OpenDownloads()
        {
            try { Process.Start(new ProcessStartInfo(DownloadDirectory()) { UseShellExecute = true }); }
            catch (Exception error) { ShowError("پوشهٔ دانلود باز نشد: " + error.Message); }
        }

        void ShowError(string message)
        {
            MessageBox.Show(Visible ? this : null, message, "بله دسکتاپ", MessageBoxButtons.OK, MessageBoxIcon.Error,
                MessageBoxDefaultButton.Button1, MessageBoxOptions.RtlReading | MessageBoxOptions.RightAlign);
        }

        // ---------- in-window toast ----------

        void BuildToast()
        {
            toast.Visible = false;
            toast.BackColor = Color.FromArgb(0, 40, 33);
            toast.Padding = new Padding(10, 6, 10, 6);
            toast.Size = new Size(330, 34);
            toastText.AutoEllipsis = true;
            toastText.ForeColor = Color.White;
            toastText.Dock = DockStyle.Fill;
            toastText.TextAlign = ContentAlignment.MiddleRight;
            toastText.RightToLeft = RightToLeft.Yes;
            var show = toastLink = new LinkLabel { Text = "نمایش", Dock = DockStyle.Left, AutoSize = true, LinkColor = Color.FromArgb(0x7f, 0xf0, 0xd2),
                                       ActiveLinkColor = Color.White, LinkBehavior = LinkBehavior.HoverUnderline, TextAlign = ContentAlignment.MiddleLeft };
            show.LinkClicked += (s, e) => OpenDownloads();
            toast.Controls.Add(toastText);
            toast.Controls.Add(show);
            host.Controls.Add(toast);
            host.Resize += (s, e) => PlaceToast();
            toastTimer.Tick += (s, e) => { toastTimer.Stop(); toast.Visible = false; };
        }

        void PlaceToast()
        {
            toast.Location = new Point(12, host.ClientSize.Height - toast.Height - 12);
        }

        void ShowToast(string message, int seconds, bool downloads = true)
        {
            if (InvokeRequired) { BeginInvoke((Action)(() => ShowToast(message, seconds, downloads))); return; }
            toastText.Text = message;
            toastLink.Visible = downloads;
            PlaceToast();
            toast.Visible = true;
            toast.BringToFront();
            toastTimer.Stop();
            toastTimer.Interval = seconds * 1000;
            toastTimer.Start();
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                tray.Dispose();
                toastTimer.Dispose();
                national?.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}
