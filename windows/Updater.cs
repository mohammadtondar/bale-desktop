using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace BaleDesktop
{
    /// <summary>A GitHub release: version, page and its files with SHA-256 digests.</summary>
    public sealed class ReleaseInfo
    {
        public Version Version;
        public string Tag, Page, Notes;
        public List<Dictionary<string, object>> Assets = new List<Dictionary<string, object>>();

        public Dictionary<string, object> Asset(string suffix) =>
            Assets.FirstOrDefault(a => a.TryGetValue("name", out var name) && name is string text
                                       && text.EndsWith(suffix, StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>
    /// Checks GitHub Releases (same logic as updater.py). Only release metadata is
    /// requested; downloads must match the SHA-256 GitHub publishes before use.
    /// </summary>
    public static class Updater
    {
        public const string Repo = "mohammadtondar/bale-desktop";
        public static readonly TimeSpan Interval = TimeSpan.FromHours(6);
        static readonly HttpClient Http = CreateClient();

        static HttpClient CreateClient()
        {
            var client = new HttpClient { Timeout = TimeSpan.FromMinutes(10) };
            client.DefaultRequestHeaders.UserAgent.ParseAdd("bale-desktop/" + CurrentText);
            return client;
        }

        static Version Normalize(Version v) => new Version(v.Major, v.Minor, Math.Max(v.Build, 0), Math.Max(v.Revision, 0));

        public static Version Current => Normalize(Assembly.GetExecutingAssembly().GetName().Version);

        public static string CurrentText => Current.ToString(3);

        public static bool TryParse(string tag, out Version version)
        {
            version = null;
            var core = (tag ?? "").Trim().TrimStart('v', 'V').Split('-', '+')[0];
            if (!Version.TryParse(core.Contains(".") ? core : core + ".0", out var parsed)) return false;
            version = Normalize(parsed);
            return true;
        }

        public static bool IsNewer(ReleaseInfo release) => release?.Version != null && release.Version > Current;

        /// <summary>Installed with the setup program (can update itself), not the portable zip.</summary>
        public static bool Installed => File.Exists(Path.Combine(Path.GetDirectoryName(Application.ExecutablePath), "unins000.exe"));

        public static async Task<ReleaseInfo> FetchLatest()
        {
            using (var request = new HttpRequestMessage(HttpMethod.Get, "https://api.github.com/repos/" + Repo + "/releases/latest"))
            {
                request.Headers.Accept.ParseAdd("application/vnd.github+json");
                using (var cancel = new System.Threading.CancellationTokenSource(TimeSpan.FromSeconds(20)))
                using (var response = await Http.SendAsync(request, cancel.Token))
                {
                    response.EnsureSuccessStatusCode();
                    var data = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(await response.Content.ReadAsStringAsync());
                    var release = new ReleaseInfo
                    {
                        Tag = data["tag_name"] as string,
                        Page = data["html_url"] as string,
                        Notes = data.TryGetValue("body", out var body) ? body as string ?? "" : "",
                    };
                    if (TryParse(release.Tag, out var version)) release.Version = version;
                    if (data.TryGetValue("assets", out var assets) && assets is System.Collections.ArrayList list)
                        release.Assets = list.OfType<Dictionary<string, object>>().ToList();
                    return release;
                }
            }
        }

        /// <summary>Download a release file into directory and verify its SHA-256.</summary>
        public static async Task<string> Download(Dictionary<string, object> asset, string directory, IProgress<double> progress)
        {
            var name = Path.GetFileName(asset["name"] as string);
            var url = asset["browser_download_url"] as string;
            var digest = asset.TryGetValue("digest", out var d) ? d as string ?? "" : "";
            if (!digest.StartsWith("sha256:")) throw new InvalidDataException("فایل نسخهٔ جدید امضای SHA-256 ندارد؛ نصب نمی‌شود.");
            Directory.CreateDirectory(directory);
            var target = Path.Combine(directory, name);
            var partial = target + ".part";
            try
            {
                using (var response = await Http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead))
                {
                    response.EnsureSuccessStatusCode();
                    var total = response.Content.Headers.ContentLength ?? 0;
                    using (var input = await response.Content.ReadAsStreamAsync())
                    using (var output = new FileStream(partial, FileMode.Create, FileAccess.Write))
                    using (var sha = SHA256.Create())
                    {
                        var buffer = new byte[65536];
                        long done = 0;
                        int read;
                        while ((read = await input.ReadAsync(buffer, 0, buffer.Length)) > 0)
                        {
                            await output.WriteAsync(buffer, 0, read);
                            sha.TransformBlock(buffer, 0, read, null, 0);
                            done += read;
                            if (total > 0) progress?.Report((double)done / total);
                        }
                        sha.TransformFinalBlock(buffer, 0, 0);
                        var actual = BitConverter.ToString(sha.Hash).Replace("-", "").ToLowerInvariant();
                        if (actual != digest.Substring(7).ToLowerInvariant())
                            throw new InvalidDataException("فایل دریافت‌شده با امضای منتشرشده یکی نیست؛ نصب نمی‌شود.");
                    }
                }
                if (File.Exists(target)) File.Delete(target);
                File.Move(partial, target);
                return target;
            }
            catch
            {
                try { File.Delete(partial); } catch (IOException) { }
                throw;
            }
        }
    }
}
