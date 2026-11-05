using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Win32;

namespace BaleDesktop
{
    /// <summary>
    /// One top bar instead of the Windows title bar plus a toolbar: the caption
    /// is removed from the native frame (resize, snap, shadow and the system menu
    /// stay native) and the toolbar acts as the title bar. Its colour follows
    /// Bale's own theme (white / near-black) or Bale green.
    /// </summary>
    public sealed partial class MainForm
    {
        const int WM_NCCALCSIZE = 0x0083, WM_NCHITTEST = 0x0084;
        const int HTTRANSPARENT = -1, HTCLIENT = 1, HTCAPTION = 2, HTTOP = 12, HTTOPLEFT = 13, HTTOPRIGHT = 14;
        const string Glyphs = "Segoe MDL2 Assets";
        static readonly Color BaleLight = Color.White;                       // Bale: background.chat (light)
        static readonly Color BaleDark = Color.FromArgb(0x1A, 0x1B, 0x1C);   // Bale: background.chat (dark)
        static readonly Color CloseRed = Color.FromArgb(0xC4, 0x2B, 0x1C);

        [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }
        [StructLayout(LayoutKind.Sequential)] struct NCCALCSIZE_PARAMS { public RECT Proposed, Old, OldClient; public IntPtr Position; }

        [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
        [DllImport("user32.dll")] static extern int GetSystemMetrics(int index);
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

        TitleStrip header;
        ToolStripButton maximizeButton, closeButton;
        string headerMode = "auto";               // "auto" = follow Bale's theme, "green"
        Color headerBack = BaleLight, headerFore = Color.Black;
        ToolStripMenuItem modeAuto, modeGreen;

        int S(int value) => (int)Math.Round(value * DeviceDpi / 96f);

        // ---------- the bar ----------

        void BuildHeader()
        {
            headerMode = LoadSettings().TryGetValue("header", out var mode) && mode as string == "green" ? "green" : "auto";
            header = new TitleStrip(this)
            {
                Dock = DockStyle.Top,
                AutoSize = false,
                Height = S(38),
                GripStyle = ToolStripGripStyle.Hidden,
                Padding = Padding.Empty,
                RightToLeft = RightToLeft.No,      // window buttons on the right, as everywhere in Windows
                Renderer = new BarRenderer(this),
                ShowItemToolTips = true,
            };

            var logo = new ToolStripLabel("بله")
            {
                Image = Icon.ToBitmap(),
                ImageScaling = ToolStripItemImageScaling.None,
                Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 10.5f, FontStyle.Bold),
                Margin = new Padding(S(10), 0, S(6), 0),
            };
            logo.Image = new Bitmap(logo.Image, S(20), S(20));
            var reload = Glyph("\uE72C", "تازه‌سازی حساب فعلی (F5)", (s, e) => ReloadActive());
            status.Margin = new Padding(S(2), 0, S(6), 0);
            status.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9f);

            nationalButton = new ToolStripButton("اینترنت ملی")
            {
                CheckOnClick = true,
                Checked = nationalOn,
                Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9f, FontStyle.Bold),
                Margin = new Padding(S(4), S(7), S(4), S(7)),
                Padding = new Padding(S(6), 0, S(6), 0),
                ToolTipText = "اینترنت ملی: اتصال مستقیم بله با DNS ایران، بدون عبور از پروکسی فیلترشکن.\n"
                              + "وقتی فیلترشکن بله را مختل می‌کند روشن کنید.",
            };
            nationalButton.CheckedChanged += (s, e) => { ApplyHeaderTheme(); NationalToggled(); };

            // Right side, listed from the window edge inwards.
            var minimize = Caption("\uE921", "کوچک کردن", (s, e) => WindowState = FormWindowState.Minimized);
            maximizeButton = Caption("\uE922", "بزرگ کردن", (s, e) =>
                WindowState = WindowState == FormWindowState.Maximized ? FormWindowState.Normal : FormWindowState.Maximized);
            closeButton = Caption("\uE8BB", "بستن (بله در کنار ساعت فعال می‌ماند)", (s, e) => Close());
            var gap = new ToolStripLabel { AutoSize = false, Width = S(8), Alignment = ToolStripItemAlignment.Right };

            var menu = new ToolStripDropDownButton("\uE700")
            {
                ShowDropDownArrow = false,
                Font = new Font(Glyphs, 10f),
                AutoSize = false,
                Size = new Size(S(40), S(38)),
                Margin = Padding.Empty,
                ToolTipText = "منو",
                Alignment = ToolStripItemAlignment.Right,
            };
            menu.DropDown.RightToLeft = RightToLeft.Yes;
            menu.DropDownItems.Add("افزودن حساب", null, (s, e) => ProfileDialog(false));
            menu.DropDownItems.Add("تغییر نام پروفایل", null, (s, e) => ProfileDialog(true));
            menu.DropDownItems.Add("باز کردن پوشهٔ دانلودها", null, (s, e) => OpenDownloads());
            var colors = new ToolStripMenuItem("رنگ نوار بالا");
            modeAuto = new ToolStripMenuItem("هماهنگ با تم بله (سفید / مشکی)", null, (s, e) => SetHeaderMode("auto"));
            modeGreen = new ToolStripMenuItem("سبز بله", null, (s, e) => SetHeaderMode("green"));
            colors.DropDownItems.AddRange(new ToolStripItem[] { modeAuto, modeGreen });
            colors.DropDown.RightToLeft = RightToLeft.Yes;
            menu.DropDownItems.Add(colors);
            menu.DropDownItems.Add(new ToolStripSeparator());
            menu.DropDownItems.Add(new ToolStripMenuItem("خروج کامل", null, (s, e) => Quit()) { ShortcutKeys = Keys.Control | Keys.Q });

            picker.DropDownStyle = ComboBoxStyle.DropDownList;
            picker.FlatStyle = FlatStyle.Flat;
            picker.ToolTipText = "تغییر پروفایل";
            picker.Alignment = ToolStripItemAlignment.Right;
            picker.ComboBox.Width = S(150);
            picker.ComboBox.RightToLeft = RightToLeft.Yes;
            picker.Margin = new Padding(S(4), 0, S(4), 0);
            picker.SelectedIndexChanged += (s, e) =>
            {
                if (!updatingPicker && picker.SelectedItem is ProfileItem item) SwitchProfile(item.Id);
            };
            var add = Glyph("\uE710", "افزودن حساب", (s, e) => ProfileDialog(false));
            add.Alignment = ToolStripItemAlignment.Right;

            header.Items.AddRange(new ToolStripItem[] { logo, reload, status, nationalButton,
                                                        closeButton, maximizeButton, minimize, gap, menu, picker, add });
            ApplyHeaderTheme();
        }

        ToolStripButton Glyph(string glyph, string tip, EventHandler click)
        {
            var button = new ToolStripButton(glyph)
            {
                Font = new Font(Glyphs, 10f),
                AutoSize = false,
                Size = new Size(S(40), S(38)),
                Margin = Padding.Empty,
                ToolTipText = tip,
            };
            button.Click += click;
            return button;
        }

        ToolStripButton Caption(string glyph, string tip, EventHandler click)
        {
            var button = Glyph(glyph, tip, click);
            button.Font = new Font(Glyphs, 7.5f);
            button.Size = new Size(S(46), S(38));
            button.Alignment = ToolStripItemAlignment.Right;
            button.Overflow = ToolStripItemOverflow.Never;
            return button;
        }

        // ---------- colours ----------

        static bool IsLight(Color c) => (0.299 * c.R + 0.587 * c.G + 0.114 * c.B) / 255 > 0.6;

        static Color SystemGuess()
        {
            try
            {
                using (var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"))
                    return key?.GetValue("AppsUseLightTheme") is int light && light == 0 ? BaleDark : BaleLight;
            }
            catch (Exception) { return BaleLight; }
        }

        internal void ApplyHeaderTheme()
        {
            if (header == null) return;
            Color? bale = sessions.TryGetValue(profiles.Active, out var session) ? session.Theme : null;
            headerBack = headerMode == "green" ? Green : bale ?? SystemGuess();
            var light = IsLight(headerBack);
            headerFore = light ? Color.FromArgb(0x1F, 0x23, 0x28) : Color.White;
            header.BackColor = headerBack;
            foreach (ToolStripItem item in header.Items) item.ForeColor = headerFore;
            if (nationalButton.Checked) nationalButton.ForeColor = headerBack;   // inverted "on" pill
            picker.ComboBox.BackColor = headerBack;
            picker.ComboBox.ForeColor = headerFore;
            status.ForeColor = StatusColor();
            if (modeAuto != null) { modeAuto.Checked = headerMode == "auto"; modeGreen.Checked = headerMode == "green"; }
            if (IsHandleCreated)
            {
                // Dark frame/system menu with a dark bar; Windows 11 border in the bar's colour.
                var dark = light ? 0 : 1;
                DwmSetWindowAttribute(Handle, 20, ref dark, 4);
                var border = headerBack.R | headerBack.G << 8 | headerBack.B << 16;
                DwmSetWindowAttribute(Handle, 34, ref border, 4);
            }
            header.Invalidate();
        }

        Color StatusColor()
        {
            var ready = sessions.TryGetValue(profiles.Active, out var session) && session.Ready;
            if (headerMode == "green") return ready ? Color.White : Color.FromArgb(255, 235, 150);
            return ready ? Color.FromArgb(0x04, 0xCC, 0x83) : Color.FromArgb(0xE0, 0x9B, 0x00);
        }

        void SetHeaderMode(string mode)
        {
            headerMode = mode;
            SaveSetting("header", mode);
            ApplyHeaderTheme();
        }

        void ThemeMessage(Session session, Dictionary<string, object> item)
        {
            if (!(item.TryGetValue("color", out var value) && value is string text)) return;
            try { session.Theme = ColorTranslator.FromHtml(text); }
            catch (Exception) { return; }
            if (session.ProfileId == profiles.Active) ApplyHeaderTheme();
        }

        sealed class BarRenderer : ToolStripProfessionalRenderer
        {
            readonly MainForm form;
            public BarRenderer(MainForm form) { this.form = form; RoundedEdges = false; }

            protected override void OnRenderToolStripBorder(ToolStripRenderEventArgs e) { }

            protected override void OnRenderToolStripBackground(ToolStripRenderEventArgs e)
            {
                if (!(e.ToolStrip is TitleStrip)) { base.OnRenderToolStripBackground(e); return; }
                using (var brush = new SolidBrush(form.headerBack)) e.Graphics.FillRectangle(brush, e.AffectedBounds);
            }

            protected override void OnRenderButtonBackground(ToolStripItemRenderEventArgs e)
            {
                if (!(e.ToolStrip is TitleStrip)) { base.OnRenderButtonBackground(e); return; }
                var bounds = new Rectangle(Point.Empty, e.Item.Size);
                if (e.Item == form.nationalButton && form.nationalButton.Checked)
                {
                    using (var brush = new SolidBrush(form.headerFore)) e.Graphics.FillRectangle(brush, bounds);
                    return;
                }
                if (!e.Item.Selected && !e.Item.Pressed) return;
                var color = e.Item == form.closeButton ? CloseRed
                          : Color.FromArgb(e.Item.Pressed ? 46 : 28, form.headerFore);
                using (var brush = new SolidBrush(color)) e.Graphics.FillRectangle(brush, bounds);
            }

            protected override void OnRenderDropDownButtonBackground(ToolStripItemRenderEventArgs e) => OnRenderButtonBackground(e);

            protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
            {
                if (e.Item == form.closeButton && (e.Item.Selected || e.Item.Pressed)) e.TextColor = Color.White;
                base.OnRenderItemText(e);
            }
        }

        // ---------- caption-less native frame ----------

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            const uint SWP_NOSIZE = 0x1, SWP_NOMOVE = 0x2, SWP_NOZORDER = 0x4, SWP_FRAMECHANGED = 0x20;
            SetWindowPos(Handle, IntPtr.Zero, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER);
            ApplyHeaderTheme();
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            if (maximizeButton != null)
            {
                var maximized = WindowState == FormWindowState.Maximized;
                maximizeButton.Text = maximized ? "\uE923" : "\uE922";
                maximizeButton.ToolTipText = maximized ? "برگرداندن اندازه" : "بزرگ کردن";
            }
            if (WindowState == FormWindowState.Minimized || Visible) UpdateBackground();
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == WM_NCCALCSIZE && m.WParam != IntPtr.Zero)
            {
                // Let Windows compute the side and bottom borders, then give the
                // caption's space to the client area.
                var before = (NCCALCSIZE_PARAMS)Marshal.PtrToStructure(m.LParam, typeof(NCCALCSIZE_PARAMS));
                base.WndProc(ref m);
                var after = (NCCALCSIZE_PARAMS)Marshal.PtrToStructure(m.LParam, typeof(NCCALCSIZE_PARAMS));
                after.Proposed.Top = before.Proposed.Top;
                // A maximized window hangs past the screen edge by its frame width.
                if (WindowState == FormWindowState.Maximized)
                    after.Proposed.Top += GetSystemMetrics(33 /* SM_CYFRAME */) + GetSystemMetrics(92 /* SM_CXPADDEDBORDER */);
                Marshal.StructureToPtr(after, m.LParam, false);
                m.Result = IntPtr.Zero;
                return;
            }
            if (m.Msg == WM_NCHITTEST)
            {
                base.WndProc(ref m);
                if ((int)m.Result != HTCLIENT) return;
                var point = PointToClient(ScreenPoint(m.LParam));
                var edge = S(6);
                if (WindowState == FormWindowState.Normal && point.Y < edge)
                    m.Result = (IntPtr)(point.X < edge * 2 ? HTTOPLEFT : point.X >= ClientSize.Width - edge * 2 ? HTTOPRIGHT : HTTOP);
                else if (header != null && point.Y < header.Height)
                    m.Result = (IntPtr)HTCAPTION;   // drag, double-click to maximize, Aero snap, system menu
                return;
            }
            base.WndProc(ref m);
        }

        static Point ScreenPoint(IntPtr lParam)
        {
            var value = lParam.ToInt64();
            return new Point((short)(value & 0xFFFF), (short)((value >> 16) & 0xFFFF));
        }

        /// <summary>Empty parts of the bar, and its labels, belong to the window caption.</summary>
        sealed class TitleStrip : ToolStrip
        {
            readonly MainForm form;
            public TitleStrip(MainForm form) { this.form = form; }

            protected override void WndProc(ref Message m)
            {
                if (m.Msg == WM_NCHITTEST && !DesignMode)
                {
                    var point = PointToClient(ScreenPoint(m.LParam));
                    var item = GetItemAt(point);
                    var topEdge = form.WindowState == FormWindowState.Normal && point.Y < form.S(6);
                    if (topEdge || item == null || (item is ToolStripLabel && item != form.status))
                    {
                        m.Result = (IntPtr)HTTRANSPARENT;   // let the form answer: caption or resize edge
                        return;
                    }
                }
                base.WndProc(ref m);
            }
        }
    }
}
