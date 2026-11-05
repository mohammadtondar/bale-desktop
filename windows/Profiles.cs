using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace BaleDesktop
{
    public sealed class Profile
    {
        public string id { get; set; }
        public string name { get; set; }
    }

    sealed class ProfileFile
    {
        public List<Profile> profiles { get; set; }
        public string active { get; set; }
    }

    /// <summary>Profile names and the active profile; same rules as profiles.py.</summary>
    public sealed class ProfileStore
    {
        static readonly Regex IdPattern = new Regex("^[a-f0-9]{32}$");
        readonly string path;
        public List<Profile> Items { get; private set; }
        public string Active { get; private set; }

        public ProfileStore(string dataRoot)
        {
            Directory.CreateDirectory(dataRoot);
            path = Path.Combine(dataRoot, "profiles.json");
            if (!File.Exists(path))
            {
                Items = new List<Profile> { new Profile { id = "default", name = "حساب اصلی" } };
                Active = "default";
                Save();
                return;
            }
            try
            {
                var config = new JavaScriptSerializer().Deserialize<ProfileFile>(File.ReadAllText(path, Encoding.UTF8));
                var ids = config.profiles.Select(p => p.id).ToList();
                if (ids.Count == 0 || ids.Distinct().Count() != ids.Count || !ids.Contains("default")
                    || !ids.Contains(config.active) || ids.Any(i => !ValidId(i))
                    || config.profiles.Any(p => string.IsNullOrWhiteSpace(p.name) || p.name.Length > 32))
                    throw new FormatException();
                Items = config.profiles;
                Active = config.active;
            }
            catch (Exception error) when (error is FormatException || error is ArgumentException
                                          || error is InvalidOperationException || error is NullReferenceException)
            {
                throw new InvalidDataException("فهرست پروفایل‌ها قابل خواندن نیست؛ فایل profiles.json را بررسی کنید.\n" + path);
            }
        }

        static bool ValidId(string value) => value == "default" || (value != null && IdPattern.IsMatch(value));

        public Profile Get(string id) => Items.First(p => p.id == id);

        public string CheckName(string name, string excluding = null)
        {
            name = (name ?? "").Trim();
            if (name.Length == 0 || name.Length > 32 || name.Any(c => c < 32))
                throw new ArgumentException("نام پروفایل باید بین ۱ تا ۳۲ نویسه باشد.");
            if (Items.Any(p => p.id != excluding && string.Equals(p.name, name, StringComparison.CurrentCultureIgnoreCase)))
                throw new ArgumentException("این نام قبلاً استفاده شده است.");
            return name;
        }

        public string Add(string name)
        {
            var item = new Profile { id = Guid.NewGuid().ToString("N"), name = CheckName(name) };
            Items.Add(item);
            try { Save(); }
            catch { Items.Remove(item); throw; }
            return item.id;
        }

        public void Rename(string id, string name)
        {
            var item = Get(id);
            var old = item.name;
            item.name = CheckName(name, id);
            try { Save(); }
            catch { item.name = old; throw; }
        }

        public void Select(string id)
        {
            Get(id);
            var previous = Active;
            Active = id;
            try { Save(); }
            catch { Active = previous; throw; }
        }

        void Save()
        {
            var temporary = path + ".tmp";
            var json = new JavaScriptSerializer().Serialize(new ProfileFile { profiles = Items, active = Active });
            File.WriteAllText(temporary, json, new UTF8Encoding(false));
            if (File.Exists(path)) File.Replace(temporary, path, null);
            else File.Move(temporary, path);
        }
    }
}
