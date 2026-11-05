using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading.Tasks;

namespace BaleDesktop
{
    /// <summary>
    /// «اینترنت ملی»: a local-only HTTP proxy (same design as national.py). WebView2
    /// sends Bale's traffic here instead of the VPN's system proxy; each host is
    /// resolved with Iranian DNS and reached directly. TLS passes through untouched.
    /// </summary>
    public sealed class NationalProxy : IDisposable
    {
        // TCI (مخابرات), Shecan, Electro: reachable on the national network.
        static readonly string[] IranDns = { "217.218.155.155", "217.218.127.127", "178.22.122.100", "185.51.200.2", "78.157.42.100" };
        static readonly Encoding Latin1 = Encoding.GetEncoding(28591);
        static readonly Random Random = new Random();

        readonly TcpListener listener;
        readonly Dictionary<string, Tuple<IPAddress[], DateTime>> cache = new Dictionary<string, Tuple<IPAddress[], DateTime>>();

        public NationalProxy()
        {
            listener = new TcpListener(IPAddress.Loopback, 0);
            listener.Start();
            _ = AcceptLoop();
        }

        public int Port => ((IPEndPoint)listener.LocalEndpoint).Port;

        public void Dispose() => listener.Stop();

        async Task AcceptLoop()
        {
            while (true)
            {
                TcpClient client;
                try { client = await listener.AcceptTcpClientAsync(); }
                catch (ObjectDisposedException) { return; }
                catch (InvalidOperationException) { return; }
                catch (SocketException) { continue; }
                _ = Handle(client);
            }
        }

        // ---------- DNS ----------

        static byte[] BuildQuery(string host, ushort ident)
        {
            var packet = new List<byte> { (byte)(ident >> 8), (byte)ident, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0 };
            foreach (var label in host.TrimEnd('.').Split('.'))
            {
                var bytes = Encoding.ASCII.GetBytes(new System.Globalization.IdnMapping().GetAscii(label));
                if (bytes.Length == 0 || bytes.Length > 63) throw new ArgumentException("invalid host name");
                packet.Add((byte)bytes.Length);
                packet.AddRange(bytes);
            }
            packet.AddRange(new byte[] { 0, 0, 1, 0, 1 });
            return packet.ToArray();
        }

        static int SkipName(byte[] data, int offset)
        {
            while (true)
            {
                var length = data[offset];
                if (length == 0) return offset + 1;
                if ((length & 0xC0) == 0xC0) return offset + 2;
                offset += 1 + length;
            }
        }

        static ushort U16(byte[] d, int o) => (ushort)(d[o] << 8 | d[o + 1]);

        static Tuple<IPAddress[], int> ParseAnswer(byte[] data, ushort ident)
        {
            if (U16(data, 0) != ident || (data[2] & 0x80) == 0 || (data[3] & 0x0F) != 0)
                return Tuple.Create(new IPAddress[0], 0);
            int questions = U16(data, 4), answers = U16(data, 6), offset = 12, ttl = 3600;
            for (var i = 0; i < questions; i++) offset = SkipName(data, offset) + 4;
            var found = new List<IPAddress>();
            for (var i = 0; i < answers; i++)
            {
                offset = SkipName(data, offset);
                int type = U16(data, offset), klass = U16(data, offset + 2), length = U16(data, offset + 8);
                var recordTtl = (int)Math.Min(int.MaxValue, (uint)(data[offset + 4] << 24 | data[offset + 5] << 16 | data[offset + 6] << 8 | data[offset + 7]));
                offset += 10;
                if (type == 1 && klass == 1 && length == 4)
                {
                    found.Add(new IPAddress(new[] { data[offset], data[offset + 1], data[offset + 2], data[offset + 3] }));
                    ttl = Math.Min(ttl, recordTtl);
                }
                offset += length;
            }
            return Tuple.Create(found.ToArray(), Math.Max(ttl, 30));
        }

        static async Task<Tuple<IPAddress[], int>> Query(string server, string host)
        {
            ushort ident;
            lock (Random) ident = (ushort)Random.Next(1 << 16);
            using (var udp = new UdpClient(AddressFamily.InterNetwork))
            {
                var endpoint = new IPEndPoint(IPAddress.Parse(server), 53);
                var query = BuildQuery(host, ident);
                await udp.SendAsync(query, query.Length, endpoint);
                var deadline = DateTime.UtcNow.AddMilliseconds(1500);
                while (DateTime.UtcNow < deadline)
                {
                    var receive = udp.ReceiveAsync();
                    if (await Task.WhenAny(receive, Task.Delay(deadline - DateTime.UtcNow)) != receive) break;
                    var result = receive.Result;
                    if (result.RemoteEndPoint.Address.Equals(endpoint.Address)) return ParseAnswer(result.Buffer, ident);
                }
            }
            return Tuple.Create(new IPAddress[0], 0);
        }

        async Task<IPAddress[]> Resolve(string host)
        {
            if (IPAddress.TryParse(host, out var literal)) return new[] { literal };
            host = host.ToLowerInvariant().TrimEnd('.');
            lock (cache)
                if (cache.TryGetValue(host, out var entry) && entry.Item2 > DateTime.UtcNow) return entry.Item1;
            foreach (var server in IranDns)
            {
                try
                {
                    var answer = await Query(server, host);
                    if (answer.Item1.Length == 0) continue;
                    lock (cache)
                    {
                        cache[host] = Tuple.Create(answer.Item1, DateTime.UtcNow.AddSeconds(answer.Item2));
                        if (cache.Count > 500) cache.Remove(cache.Keys.First());
                    }
                    return answer.Item1;
                }
                catch (Exception error) when (error is SocketException || error is ArgumentException
                                              || error is IndexOutOfRangeException || error is ObjectDisposedException) { }
            }
            // Iranian DNS unreachable: still connect directly, with the system resolver.
            try { return (await Dns.GetHostAddressesAsync(host)).Where(a => a.AddressFamily == AddressFamily.InterNetwork).ToArray(); }
            catch (SocketException) { return new IPAddress[0]; }
        }

        // ---------- proxy ----------

        static int HeadEnd(byte[] buffer, int length)
        {
            for (var i = 3; i < length; i++)
                if (buffer[i - 3] == 13 && buffer[i - 2] == 10 && buffer[i - 1] == 13 && buffer[i] == 10) return i - 3;
            return -1;
        }

        static async Task Fail(Stream stream, int code)
        {
            var reply = Latin1.GetBytes("HTTP/1.1 " + code + " Proxy Error\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
            try { await stream.WriteAsync(reply, 0, reply.Length); } catch (IOException) { }
        }

        static async Task Pump(NetworkStream from, NetworkStream to, Socket target)
        {
            try { await from.CopyToAsync(to, 65536); }
            catch (Exception error) when (error is IOException || error is ObjectDisposedException) { }
            try { target.Shutdown(SocketShutdown.Send); }
            catch (Exception error) when (error is SocketException || error is ObjectDisposedException) { }
        }

        async Task Handle(TcpClient client)
        {
            using (client)
            {
                var stream = client.GetStream();
                var buffer = new byte[32768];
                int length = 0, end;
                string method, host;
                int port;
                byte[] payload;
                try
                {
                    while ((end = HeadEnd(buffer, length)) < 0)
                    {
                        if (length == buffer.Length) return;
                        var read = await stream.ReadAsync(buffer, length, buffer.Length - length);
                        if (read == 0) return;
                        length += read;
                    }
                    var lines = Latin1.GetString(buffer, 0, end).Split(new[] { "\r\n" }, StringSplitOptions.None);
                    var first = lines[0].Split(' ');
                    if (first.Length != 3) { await Fail(stream, 400); return; }
                    method = first[0];
                    var target = first[1];
                    var rest = buffer.Skip(end + 4).Take(length - end - 4);
                    if (method == "CONNECT")
                    {
                        var colon = target.LastIndexOf(':');
                        host = target.Substring(0, colon);
                        port = int.Parse(target.Substring(colon + 1));
                        payload = rest.ToArray();
                    }
                    else
                    {
                        if (!target.StartsWith("http://")) { await Fail(stream, 400); return; }
                        var slash = target.IndexOf('/', 7);
                        var authority = slash < 0 ? target.Substring(7) : target.Substring(7, slash - 7);
                        var path = slash < 0 ? "/" : target.Substring(slash);
                        var colon = authority.LastIndexOf(':');
                        host = colon < 0 ? authority : authority.Substring(0, colon);
                        port = colon < 0 ? 80 : int.Parse(authority.Substring(colon + 1));
                        var kept = lines.Skip(1).Where(l => !l.StartsWith("proxy-", StringComparison.OrdinalIgnoreCase));
                        var head = method + " " + path + " " + first[2] + "\r\n" + string.Join("\r\n", kept) + "\r\n\r\n";
                        payload = Latin1.GetBytes(head).Concat(rest).ToArray();
                    }
                    host = host.Trim('[', ']');
                    // Web ports only, so this is never a general-purpose relay.
                    if ((port != 80 && port != 443) || host.Length == 0) { await Fail(stream, 403); return; }
                }
                catch (Exception error) when (error is IOException || error is FormatException
                                              || error is ArgumentException || error is OverflowException)
                {
                    await Fail(stream, 400);
                    return;
                }

                TcpClient upstream = null;
                foreach (var address in await Resolve(host))
                {
                    var candidate = new TcpClient(address.AddressFamily);
                    var connect = candidate.ConnectAsync(address, port);
                    if (await Task.WhenAny(connect, Task.Delay(10000)) == connect && !connect.IsFaulted)
                    {
                        upstream = candidate;
                        break;
                    }
                    candidate.Dispose();
                }
                if (upstream == null) { await Fail(stream, 502); return; }
                using (upstream)
                {
                    var remote = upstream.GetStream();
                    try
                    {
                        if (method == "CONNECT")
                        {
                            var ok = Latin1.GetBytes("HTTP/1.1 200 Connection Established\r\n\r\n");
                            await stream.WriteAsync(ok, 0, ok.Length);
                        }
                        if (payload.Length > 0) await remote.WriteAsync(payload, 0, payload.Length);
                    }
                    catch (IOException) { return; }
                    await Task.WhenAll(Pump(stream, remote, upstream.Client), Pump(remote, stream, client.Client));
                }
            }
        }
    }
}
