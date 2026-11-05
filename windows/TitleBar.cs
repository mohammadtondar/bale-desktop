using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Win32;

namespace BaleDesktop
{
    /// <summary>
    /// One slim top bar, in the style of an installed web app: the native caption
    /// is removed (resize, snap, shadow and the system menu stay native) and the
    /// bar acts as the title bar. Its colour follows Bale's own theme
    /// (white / near-black) or Bale green; accounts switch from an avatar menu.
    /// </summary>
    public sealed partial class MainForm
    {
        const int WM_NCCALCSIZE = 0x0083, WM_NCHITTEST = 0x0084;
        const int HTTRANSPARENT = -1, HTCLIENT = 1, HTCAPTION = 2, HTTOP = 12, HTTOPLEFT = 13, HTTOPRIGHT = 14;
        const string Glyphs = "Segoe MDL2 Assets";
        const int BarHeight = 40;
        static readonly Color BaleLight = Color.White;                       // Bale: background.chat (light)
        static readonly Color BaleDark = Color.FromArgb(0x1A, 0x1B, 0x1C);   // Bale: background.chat (dark)
        static readonly Color CloseRed = Color.FromArgb(0xC4, 0x2B, 0x1C);
        static readonly Color[] AvatarColors =
        {
            Color.FromArgb(0x00, 0xB6, 0x98), Color.FromArgb(0x4F, 0xC3, 0xF7), Color.FromArgb(0xF0, 0x62, 0x92),
            Color.FromArgb(0xFF, 0xA7, 0x26), Color.FromArgb(0x95, 0x75, 0xCD), Color.FromArgb(0x26, 0xA6, 0x9A),
            Color.FromArgb(0xEF, 0x53, 0x50),
        };

        [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }
        [StructLayout(LayoutKind.Sequential)] struct NCCALCSIZE_PARAMS { public RECT Proposed, Old, OldClient; public IntPtr Position; }

        [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
        [DllImport("user32.dll")] static extern int GetSystemMetrics(int index);
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

        TitleStrip header;
        ToolStripButton maximizeButton, closeButton;
        ToolStripDropDownButton accountButton, menuButton;
        string headerMode = "auto";               // "auto" = follow Bale's theme, "green"
        Color headerBack = BaleLight, headerFore = Color.Black, menuBack = Color.White, menuFore = Color.Black;
        ToolStripMenuItem modeAuto, modeGreen;
        MenuRenderer menuRenderer;

        int S(int value) => (int)Math.Round(value * DeviceDpi / 96f);

        // ---------- the bar ----------

        void BuildHeader()
        {
            headerMode = LoadSettings().TryGetValue("header", out var mode) && mode as string == "green" ? "green" : "auto";
            menuRenderer = new MenuRenderer(this);
            header = new TitleStrip(this)
            {
                Dock = DockStyle.Top,
                AutoSize = false,
                Height = S(BarHeight),
                GripStyle = ToolStripGripStyle.Hidden,
                Padding = Padding.Empty,
                RightToLeft = RightToLeft.No,      // window buttons on the right, as everywhere in Windows
                Renderer = new BarRenderer(this),
                ShowItemToolTips = true,
                ImageScalingSize = new Size(S(24), S(24)),
            };

            // Left: app icon, then the account switcher as the window title.
            var logo = new ToolStripLabel
            {
                Image = new Bitmap(Icon.ToBitmap(), S(20), S(20)),
                ImageScaling = ToolStripItemImageScaling.None,
                Margin = new Padding(S(12), 0, S(6), 0),
                ToolTipText = "بله دسکتاپ",
            };
            accountButton = new ToolStripDropDownButton
            {
                ShowDropDownArrow = false,
                ImageScaling = ToolStripItemImageScaling.None,
                TextImageRelation = TextImageRelation.ImageBeforeText,
                Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 10f),
                Margin = new Padding(0, S(4), 0, S(4)),
                Padding = new Padding(S(6), 0, S(8), 0),
            };
            Themed(accountButton.DropDown, RightToLeft.Yes);
            accountButton.DropDown.ImageScalingSize = new Size(S(28), S(28));

            // Right side, listed from the window edge inwards.
            var minimize = Caption("\uE921", "کوچک کردن", (s, e) => WindowState = FormWindowState.Minimized);
            maximizeButton = Caption("\uE922", "بزرگ کردن", (s, e) =>
                WindowState = WindowState == FormWindowState.Maximized ? FormWindowState.Normal : FormWindowState.Maximized);
            closeButton = Caption("\uE8BB", "بستن (بله در کنار ساعت فعال می‌ماند)", (s, e) => Close());

            menuButton = new ToolStripDropDownButton("\uE700")
            {
                ShowDropDownArrow = false,
                Font = new Font(Glyphs, 10.5f),
                AutoSize = false,
                Size = new Size(S(42), S(BarHeight)),
                Margin = new Padding(0, 0, S(6), 0),
                ToolTipText = "منو",
                Alignment = ToolStripItemAlignment.Right,
            };
            Themed(menuButton.DropDown, RightToLeft.Yes);
            menuButton.DropDownItems.Add("باز کردن پوشهٔ دانلودها", null, (s, e) => OpenDownloads());
            var colors = new ToolStripMenuItem("رنگ نوار بالا");
            modeAuto = new ToolStripMenuItem("هماهنگ با تم بله (سفید / مشکی)", null, (s, e) => SetHeaderMode("auto"));
            modeGreen = new ToolStripMenuItem("سبز بله", null, (s, e) => SetHeaderMode("green"));
            colors.DropDownItems.AddRange(new ToolStripItem[] { modeAuto, modeGreen });
            Themed(colors.DropDown, RightToLeft.Yes);
            menuButton.DropDownItems.Add(colors);
            menuButton.DropDownItems.Add(new ToolStripSeparator());
            menuButton.DropDownItems.Add(new ToolStripMenuItem("خروج کامل", null, (s, e) => Quit()) { ShortcutKeyDisplayString = "Ctrl+Q" });

            var reload = Glyph("\uE72C", "تازه‌سازی حساب فعلی (F5)", (s, e) => ReloadActive());
            reload.Alignment = ToolStripItemAlignment.Right;

            nationalButton = new ToolStripButton("اینترنت ملی")
            {
                CheckOnClick = true,
                Checked = nationalOn,
                Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9f),
                Margin = new Padding(S(6), S(8), S(6), S(8)),
                Padding = new Padding(S(8), 0, S(8), 0),
                Alignment = ToolStripItemAlignment.Right,
                ToolTipText = "اینترنت ملی: اتصال مستقیم بله با DNS ایران، بدون عبور از پروکسی فیلترشکن.\n"
                              + "وقتی فیلترشکن بله را مختل می‌کند روشن کنید.",
            };
            nationalButton.CheckedChanged += (s, e) => { ApplyHeaderTheme(); NationalToggled(); };

            header.Items.AddRange(new ToolStripItem[] { logo, accountButton,
                                                        closeButton, maximizeButton, minimize, menuButton, reload, nationalButton });
            ApplyHeaderTheme();
        }

        void Themed(ToolStripDropDown dropDown, RightToLeft direction)
        {
            dropDown.Renderer = menuRenderer;
            dropDown.RightToLeft = direction;
            dropDown.Padding = new Padding(S(4));
            if (dropDown is ToolStripDropDownMenu menu) menu.ShowCheckMargin = false;
        }

        ToolStripButton Glyph(string glyph, string tip, EventHandler click)
        {
            var button = new ToolStripButton(glyph)
            {
                Font = new Font(Glyphs, 10.5f),
                AutoSize = false,
                Size = new Size(S(42), S(BarHeight)),
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
            button.Size = new Size(S(46), S(BarHeight));
            button.Alignment = ToolStripItemAlignment.Right;
            button.Overflow = ToolStripItemOverflow.Never;
            return button;
        }

        // ---------- accounts ----------

        /// <summary>A round avatar with the account's initial, and an optional status dot.</summary>
        Bitmap Avatar(Profile profile, int size, Color? dot)
        {
            var bitmap = new Bitmap(size, size);
            using (var g = Graphics.FromImage(bitmap))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
                var hash = profile.id.Aggregate(0, (sum, c) => sum * 31 + c);
                using (var fill = new SolidBrush(AvatarColors[(hash & int.MaxValue) % AvatarColors.Length]))
                    g.FillEllipse(fill, 0, 0, size - 1, size - 1);
                var initial = profile.name.Trim().Length > 0 ? profile.name.Trim().Substring(0, 1) : "؟";
                using (var font = new Font(SystemFonts.MessageBoxFont.FontFamily, size * 0.42f, FontStyle.Bold, GraphicsUnit.Pixel))
                using (var format = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
                    g.DrawString(initial, font, Brushes.White, new RectangleF(0, 0, size, size + 1), format);
                if (dot is Color status)
                {
                    var d = size * 0.36f;
                    using (var ring = new SolidBrush(headerBack)) g.FillEllipse(ring, size - d - 0.5f, size - d - 0.5f, d + 0.5f, d + 0.5f);
                    using (var brush = new SolidBrush(status)) g.FillEllipse(brush, size - d + 1, size - d + 1, d - 2.5f, d - 2.5f);
                }
            }
            return bitmap;
        }

        static Bitmap PlusAvatar(int size, Color color)
        {
            var bitmap = new Bitmap(size, size);
            using (var g = Graphics.FromImage(bitmap))
            using (var pen = new Pen(color, Math.Max(1.5f, size / 16f)))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                pen.DashStyle = DashStyle.Solid;
                g.DrawEllipse(pen, 1, 1, size - 3, size - 3);
                var c = size / 2f - 0.5f;
                var r = size * 0.2f;
                g.DrawLine(pen, c - r, c, c + r, c);
                g.DrawLine(pen, c, c - r, c, c + r);
            }
            return bitmap;
        }

        /// <summary>Rebuild the account button and its menu (names, active account, status).</summary>
        void RefreshPicker()
        {
            if (accountButton == null) return;
            var active = profiles.Get(profiles.Active);
            sessions.TryGetValue(active.id, out var session);
            accountButton.Text = active.name + "  ▾";
            accountButton.Image?.Dispose();
            accountButton.Image = Avatar(active, S(24), StatusColor());
            accountButton.ToolTipText = active.name + " — " + (session?.Status ?? "در حال اتصال…") + "\nتغییر حساب";

            var items = accountButton.DropDownItems;
            foreach (ToolStripItem old in items) old.Image?.Dispose();
            items.Clear();
            var title = new ToolStripLabel("حساب‌ها") { ForeColor = Color.Gray, Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 8f), Margin = new Padding(S(8), S(2), S(8), S(2)) };
            items.Add(title);
            foreach (var profile in profiles.Items)
            {
                var id = profile.id;
                var isActive = id == profiles.Active;
                var ready = sessions.TryGetValue(id, out var s) && s.Ready;
                var item = new ToolStripMenuItem(profile.name, Avatar(profile, S(28), ready ? Color.FromArgb(0x04, 0xCC, 0x83) : (Color?)null))
                {
                    Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9.5f, isActive ? FontStyle.Bold : FontStyle.Regular),
                    ImageScaling = ToolStripItemImageScaling.None,
                    Padding = new Padding(0, S(4), 0, S(4)),
                    Tag = isActive ? "active" : null,
                    ToolTipText = s?.Status,
                };
                item.Click += (sender, e) => { if (id != profiles.Active) SwitchProfile(id); };
                items.Add(item);
            }
            items.Add(new ToolStripSeparator());
            items.Add(new ToolStripMenuItem("افزودن حساب", PlusAvatar(S(28), Color.FromArgb(0x00, 0xB6, 0x98)), (sender, e) => ProfileDialog(false))
            {
                ImageScaling = ToolStripItemImageScaling.None,
                Padding = new Padding(0, S(4), 0, S(4)),
                Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9.5f),
            });
            items.Add(new ToolStripMenuItem("تغییر نام «" + active.name + "»", null, (sender, e) => ProfileDialog(true)));
            ApplyMenuColors(accountButton.DropDown);
            this.header.Invalidate();
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
            var baleTheme = bale ?? SystemGuess();
            headerBack = headerMode == "green" ? Green : baleTheme;
            var light = IsLight(headerBack);
            headerFore = light ? Color.FromArgb(0x1F, 0x23, 0x28) : Color.FromArgb(0xE8, 0xEA, 0xED);
            // Menus follow Bale's light/dark theme even when the bar is green.
            var darkMenus = !IsLight(baleTheme);
            menuBack = darkMenus ? Color.FromArgb(0x2B, 0x2C, 0x2E) : Color.White;
            menuFore = darkMenus ? Color.FromArgb(0xE8, 0xEA, 0xED) : Color.FromArgb(0x1F, 0x23, 0x28);

            header.BackColor = headerBack;
            foreach (ToolStripItem item in header.Items) item.ForeColor = headerFore;
            if (nationalButton.Checked) nationalButton.ForeColor = headerBack;   // inverted "on" pill
            if (modeAuto != null) { modeAuto.Checked = headerMode == "auto"; modeGreen.Checked = headerMode == "green"; }
            ApplyMenuColors(menuButton.DropDown);
            RefreshPicker();
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

        void ApplyMenuColors(ToolStripDropDown dropDown)
        {
            dropDown.BackColor = menuBack;
            foreach (ToolStripItem item in dropDown.Items)
            {
                if (!(item is ToolStripLabel)) item.ForeColor = menuFore;
                if (item is ToolStripMenuItem sub && sub.HasDropDownItems) ApplyMenuColors(sub.DropDown);
            }
        }

        Color StatusColor()
        {
            var ready = sessions.TryGetValue(profiles.Active, out var session) && session.Ready;
            return ready ? Color.FromArgb(0x04, 0xCC, 0x83) : Color.FromArgb(0xF0, 0xA2, 0x02);
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

        // ---------- painting ----------

        static GraphicsPath Rounded(RectangleF r, float radius)
        {
            var path = new GraphicsPath();
            var d = radius * 2;
            path.AddArc(r.X, r.Y, d, d, 180, 90);
            path.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            path.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            path.CloseFigure();
            return path;
        }

        static void FillRounded(Graphics g, Color color, RectangleF r, float radius)
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            using (var path = Rounded(r, radius))
            using (var brush = new SolidBrush(color))
                g.FillPath(brush, path);
        }

        sealed class BarRenderer : ToolStripProfessionalRenderer
        {
            readonly MainForm form;
            public BarRenderer(MainForm form) { this.form = form; RoundedEdges = false; }

            protected override void OnRenderToolStripBorder(ToolStripRenderEventArgs e) { }

            protected override void OnRenderToolStripBackground(ToolStripRenderEventArgs e)
            {
                using (var brush = new SolidBrush(form.headerBack)) e.Graphics.FillRectangle(brush, e.AffectedBounds);
            }

            protected override void OnRenderButtonBackground(ToolStripItemRenderEventArgs e)
            {
                var bounds = new Rectangle(Point.Empty, e.Item.Size);
                var caption = e.Item.Alignment == ToolStripItemAlignment.Right && e.Item.Overflow == ToolStripItemOverflow.Never;
                if (e.Item == form.nationalButton)
                {
                    var pill = new RectangleF(0.5f, 0.5f, bounds.Width - 1, bounds.Height - 1);
                    if (form.nationalButton.Checked) FillRounded(e.Graphics, form.headerFore, pill, pill.Height / 2);
                    else
                    {
                        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
                        using (var path = Rounded(pill, pill.Height / 2))
                        using (var pen = new Pen(Color.FromArgb(e.Item.Selected ? 160 : 90, form.headerFore)))
                            e.Graphics.DrawPath(pen, path);
                    }
                    return;
                }
                if (!e.Item.Selected && !e.Item.Pressed && !(e.Item is ToolStripDropDownItem dd && dd.Pressed)) return;
                var color = e.Item == form.closeButton ? CloseRed : Color.FromArgb(e.Item.Pressed ? 40 : 24, form.headerFore);
                if (caption) using (var brush = new SolidBrush(color)) e.Graphics.FillRectangle(brush, bounds);
                else FillRounded(e.Graphics, color, new RectangleF(1, 2, bounds.Width - 2, bounds.Height - 4), form.S(4));
            }

            protected override void OnRenderDropDownButtonBackground(ToolStripItemRenderEventArgs e) => OnRenderButtonBackground(e);

            protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
            {
                if (e.Item == form.closeButton && (e.Item.Selected || e.Item.Pressed)) e.TextColor = Color.White;
                base.OnRenderItemText(e);
            }
        }

        /// <summary>Flat, rounded menus in Bale's light or dark colours.</summary>
        sealed class MenuRenderer : ToolStripProfessionalRenderer
        {
            readonly MainForm form;
            public MenuRenderer(MainForm form) { this.form = form; RoundedEdges = false; }

            protected override void OnRenderToolStripBackground(ToolStripRenderEventArgs e)
            {
                using (var brush = new SolidBrush(form.menuBack)) e.Graphics.FillRectangle(brush, e.AffectedBounds);
            }

            protected override void OnRenderToolStripBorder(ToolStripRenderEventArgs e)
            {
                using (var pen = new Pen(Color.FromArgb(40, form.menuFore)))
                    e.Graphics.DrawRectangle(pen, 0, 0, e.ToolStrip.Width - 1, e.ToolStrip.Height - 1);
            }

            protected override void OnRenderImageMargin(ToolStripRenderEventArgs e) { }

            protected override void OnRenderMenuItemBackground(ToolStripItemRenderEventArgs e)
            {
                var r = new RectangleF(form.S(2), 1, e.Item.Width - form.S(4), e.Item.Height - 2);
                if (Equals(e.Item.Tag, "active")) FillRounded(e.Graphics, Color.FromArgb(40, 0x00, 0xB6, 0x98), r, form.S(6));
                if (e.Item.Selected && e.Item.Enabled) FillRounded(e.Graphics, Color.FromArgb(24, form.menuFore), r, form.S(6));
            }

            protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
            {
                e.TextColor = e.Item is ToolStripLabel ? Color.FromArgb(140, form.menuFore) : form.menuFore;
                base.OnRenderItemText(e);
            }

            protected override void OnRenderItemCheck(ToolStripItemImageRenderEventArgs e)
            {
                using (var font = new Font(Glyphs, 8f))
                using (var brush = new SolidBrush(Color.FromArgb(0x00, 0xB6, 0x98)))
                using (var format = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
                    e.Graphics.DrawString("\uE73E", font, brush, e.ImageRectangle, format);
            }

            protected override void OnRenderSeparator(ToolStripSeparatorRenderEventArgs e)
            {
                using (var pen = new Pen(Color.FromArgb(36, form.menuFore)))
                    e.Graphics.DrawLine(pen, form.S(8), e.Item.Height / 2, e.Item.Width - form.S(8), e.Item.Height / 2);
            }

            protected override void OnRenderArrow(ToolStripArrowRenderEventArgs e)
            {
                e.ArrowColor = form.menuFore;
                base.OnRenderArrow(e);
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
