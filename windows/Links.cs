using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace BaleDesktop
{
    /// <summary>
    /// Which links stay in the app and which go to the browser (mirrors links.py):
    /// Bale links (ble.ir/…, bale://…, ble://…, web.bale.ai/…) open inside the app
    /// at the address Bale Web understands; all other links open in the browser.
    /// </summary>
    public static class Links
    {
        const string Web = "https://web.bale.ai/";
        static readonly Regex Nick = new Regex("^[A-Za-z0-9][A-Za-z0-9_]{3,}$");
        static readonly Regex Number = new Regex(@"^-?\d+$");
        static readonly Regex Phone = new Regex(@"^\+\d{8,15}$");
        static readonly HashSet<string> Reserved = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "post", "join", "share", "download", "app", "apps", "privacy", "terms", "about", "blog",
            "contact", "faq", "help", "support", "banking-my-bank-page", "static", "api", "_next",
        };

        static Dictionary<string, string> Query(string query)
        {
            var result = new Dictionary<string, string>();
            foreach (var pair in (query ?? "").TrimStart('?').Split(new[] { '&' }, StringSplitOptions.RemoveEmptyEntries))
            {
                var parts = pair.Split(new[] { '=' }, 2);
                var key = Uri.UnescapeDataString(parts[0].Replace('+', ' '));
                if (!result.ContainsKey(key))
                    result[key] = parts.Length > 1 ? Uri.UnescapeDataString(parts[1].Replace('+', ' ')) : "";
            }
            return result;
        }

        static bool IsWebBale(Uri url) => url.Scheme == Uri.UriSchemeHttps && url.Host == "web.bale.ai"
                                          && url.Port == 443 && string.IsNullOrEmpty(url.UserInfo);

        /// <summary>The in-app web.bale.ai address for a Bale link, or null for other links.</summary>
        public static string BaleLinkTarget(string uri)
        {
            if (string.IsNullOrEmpty(uri)) return null;
            string path, query;
            var scheme = uri.Split(':')[0].ToLowerInvariant();
            if (scheme == "bale" || scheme == "ble")
            {
                // bale://join/token, ble://nick: the "host" is the first path segment.
                var rest = uri.Substring(scheme.Length + 1).TrimStart('/');
                var q = rest.IndexOf('?');
                path = "/" + (q < 0 ? rest : rest.Substring(0, q));
                query = q < 0 ? "" : rest.Substring(q + 1);
            }
            else
            {
                if (!Uri.TryCreate(uri, UriKind.Absolute, out var url)) return null;
                if (IsWebBale(url)) return uri;
                if (url.Scheme != Uri.UriSchemeHttp && url.Scheme != Uri.UriSchemeHttps || !string.IsNullOrEmpty(url.UserInfo)) return null;
                var host = url.Host.ToLowerInvariant();
                if (host == "l.ble.ir")
                {
                    // Bale's link-safety redirect: l.ble.ir?l=<target>
                    return Query(url.Query).TryGetValue("l", out var inner) && inner.Length > 0 ? BaleLinkTarget(inner) : null;
                }
                if (host != "ble.ir" && host != "www.ble.ir") return null;
                path = url.AbsolutePath;
                query = url.Query;
            }

            var segments = path.Split(new[] { '/' }, StringSplitOptions.RemoveEmptyEntries).Select(Uri.UnescapeDataString).ToArray();
            if (segments.Length == 0) return Web;
            var first = segments[0];
            if (first.Equals("join", StringComparison.OrdinalIgnoreCase) && segments.Length >= 2)
                return Web + "join/" + Uri.EscapeDataString(segments[1]);
            if (Phone.IsMatch(first)) return Web + first;
            if (Nick.IsMatch(first) && !Reserved.Contains(first))
            {
                var parameters = new List<string>();
                if (segments.Length >= 3 && Number.IsMatch(segments[1]) && Number.IsMatch(segments[2]))
                {
                    parameters.Add("rid=" + segments[1]);      // link to one message
                    parameters.Add("date=" + segments[2]);
                }
                if (Query(query).TryGetValue("start", out var start)) parameters.Add("start=" + Uri.EscapeDataString(start));
                return Web + "@" + first + (parameters.Count > 0 ? "?" + string.Join("&", parameters) : "");
            }
            return null;
        }

        /// <summary>True for links that belong in the user's browser or mail/phone app.</summary>
        public static bool External(string uri)
        {
            if (!Uri.TryCreate(uri ?? "", UriKind.Absolute, out var url)) return false;
            var external = url.Scheme == Uri.UriSchemeHttp || url.Scheme == Uri.UriSchemeHttps
                           || url.Scheme == Uri.UriSchemeMailto || url.Scheme == "tel";
            return external && BaleLinkTarget(uri) == null;
        }

        /// <summary>
        /// Let bale:// and ble:// links from browsers and other apps open this app.
        /// The installer registers them; the portable copy registers itself.
        /// </summary>
        public static void RegisterProtocols(string exe)
        {
            foreach (var scheme in new[] { "bale", "ble" })
            {
                try
                {
                    using (var key = Registry.CurrentUser.CreateSubKey(@"Software\Classes\" + scheme))
                    {
                        var existing = key.OpenSubKey(@"shell\open\command")?.GetValue("") as string;
                        var registeredExe = existing?.Split('"').Skip(1).FirstOrDefault();
                        if (registeredExe != null && File.Exists(registeredExe)) continue;   // keep a working registration
                        key.SetValue("", "URL:Bale");
                        key.SetValue("URL Protocol", "");
                        using (var icon = key.CreateSubKey("DefaultIcon")) icon.SetValue("", "\"" + exe + "\",0");
                        using (var command = key.CreateSubKey(@"shell\open\command")) command.SetValue("", "\"" + exe + "\" \"%1\"");
                    }
                }
                catch (Exception error) when (error is UnauthorizedAccessException || error is IOException
                                              || error is System.Security.SecurityException) { }
            }
        }
    }

    /// <summary>
    /// Bale opens outside links asynchronously (after its link-safety check), so
    /// there is no user gesture to rely on. Allow them, but never a burst of tabs
    /// and never the same link twice in a row.
    /// </summary>
    public sealed class OpenLimiter
    {
        readonly int burst;
        readonly TimeSpan window, repeat;
        readonly List<DateTime> recent = new List<DateTime>();
        readonly Dictionary<string, DateTime> last = new Dictionary<string, DateTime>();

        public OpenLimiter(int burst = 3, double windowSeconds = 10, double repeatSeconds = 2)
        {
            this.burst = burst;
            window = TimeSpan.FromSeconds(windowSeconds);
            repeat = TimeSpan.FromSeconds(repeatSeconds);
        }

        public bool Allow(string uri, DateTime? at = null)
        {
            var now = at ?? DateTime.UtcNow;
            recent.RemoveAll(t => now - t >= window);
            if (recent.Count >= burst || (last.TryGetValue(uri, out var previous) && now - previous < repeat)) return false;
            recent.Add(now);
            last[uri] = now;
            if (last.Count > 50)
                foreach (var stale in last.Where(p => now - p.Value >= window).Select(p => p.Key).ToList()) last.Remove(stale);
            return true;
        }
    }
}
