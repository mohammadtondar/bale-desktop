using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Windows.Forms;

namespace BaleDesktop
{
    static class Program
    {
        [STAThread]
        static int Main(string[] args)
        {
            var user = Environment.UserName;
            using (var mutex = new Mutex(false, @"Local\BaleDesktop-" + user))
            using (var show = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\BaleDesktop-Show-" + user))
            {
                bool first;
                // After a settings restart, wait for the previous instance to exit.
                try { first = mutex.WaitOne(args.Contains("--restart") ? 15000 : 0); }
                catch (AbandonedMutexException) { first = true; }
                // A bale:// or ble.ir link from Windows (browser, another app).
                var link = args.FirstOrDefault(a => Links.BaleLinkTarget(a) != null);
                if (!first)
                {
                    // Running again opens the window of the instance already running,
                    // at the link if one was given.
                    if (link != null)
                    {
                        try
                        {
                            Directory.CreateDirectory(MainForm.DataRootPath);
                            File.AppendAllLines(MainForm.LinkQueuePath, new[] { link });
                        }
                        catch (Exception error) when (error is IOException || error is UnauthorizedAccessException) { }
                    }
                    show.Set();
                    return 0;
                }
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                MainForm form;
                try
                {
                    form = new MainForm(args.Contains("--background"), link);
                }
                catch (Exception error)
                {
                    MessageBox.Show(error.Message, "بله دسکتاپ", MessageBoxButtons.OK, MessageBoxIcon.Error,
                        MessageBoxDefaultButton.Button1, MessageBoxOptions.RtlReading | MessageBoxOptions.RightAlign);
                    return 1;
                }
                var listener = new Thread(() =>
                {
                    while (show.WaitOne())
                    {
                        try { form.BeginInvoke((Action)(() => { form.ShowMain(); form.OpenQueuedLinks(); })); }
                        catch (InvalidOperationException) { return; }
                    }
                }) { IsBackground = true };
                listener.Start();
                Application.Run(form);
                mutex.ReleaseMutex();
                return 0;
            }
        }
    }
}
