# -*- coding: utf-8 -*-
"""外から届くようにする (ポート開放を手でやらずに済ませる)。

友達に共有するには、家の中だけで見えていても足りない。やり方は 2 つ。

    Cloudflare トンネル   ホストから外へ出ていく接続だけで済む。
                          https://〜.trycloudflare.com が貰える。
                          ルーターは一切いじらない。友達は URL を貼るだけ。
                          cloudflared (Cloudflare 製の実行ファイル) が要る。

    UPnP                  ルーターに「このポートを通して」と自動で頼む。
                          追加のソフトは要らないが、**ポートが世界に見える**。
                          ルーターを再起動すると転送が消える。

どちらも合言葉で守る前提。合言葉なしで外に出してはいけない。
"""
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from urllib.request import Request, urlopen

QUICK_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# winget での入れ方 (画面に出す用)
CLOUDFLARED_INSTALL = "winget install --id Cloudflare.cloudflared"


def local_ip():
    """ルーターから見たこの PC のアドレス。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))       # 実際には送らない
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# ---- Cloudflare トンネル -----------------------------------------------


def find_cloudflared():
    """cloudflared の場所。無ければ None。"""
    got = shutil.which("cloudflared")
    if got:
        return got
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", ""),
                 os.environ.get("LOCALAPPDATA", "")):
        if not base:
            continue
        for sub in ("cloudflared\\cloudflared.exe", "cloudflared.exe"):
            path = os.path.join(base, sub)
            if os.path.isfile(path):
                return path
    return None


class CloudflareTunnel(object):
    """cloudflared を子プロセスで動かして、貰った URL を拾う。

    ``cloudflared tunnel --url http://127.0.0.1:8787`` を動かすと、標準
    エラーに ``https://〜.trycloudflare.com`` が出てくる。それを読む。
    """

    def __init__(self, port, on_url=None, exe=None):
        self.port = int(port)
        self.on_url = on_url
        self.exe = exe or find_cloudflared()
        self.proc = None
        self.url = ""
        self.error = ""
        self.lines = []
        self._thread = None

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        if self.running:
            return True
        if not self.exe:
            self.error = ("cloudflared が見つかりません。\n%s"
                          % CLOUDFLARED_INSTALL)
            return False
        cmd = [self.exe, "tunnel", "--no-autoupdate", "--url",
               "http://127.0.0.1:%d" % self.port]
        kw = {}
        if os.name == "nt":
            # 黒い窓を出さない
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                universal_newlines=True, errors="replace", bufsize=1, **kw)
        except OSError as e:
            self.error = "cloudflared を起動できません (%s)" % e
            self.proc = None
            return False
        self.error = ""
        self.url = ""
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()
        return True

    def _read(self):
        proc = self.proc
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip()
            self.lines.append(line)
            del self.lines[:-60]
            if not self.url:
                m = QUICK_URL_RE.search(line)
                if m:
                    self.url = m.group(0)
                    if self.on_url:
                        try:
                            self.on_url(self.url)
                        except Exception:
                            pass
        if proc.poll() not in (0, None) and not self.url:
            self.error = "cloudflared が落ちました。\n" + "\n".join(self.lines[-5:])

    def wait_for_url(self, timeout=25.0):
        end = time.time() + timeout
        while time.time() < end:
            if self.url:
                return self.url
            if not self.running:
                break
            time.sleep(0.2)
        if not self.error:
            self.error = "URL が返ってきませんでした"
        return ""

    def stop(self):
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None
        self.url = ""


# ---- UPnP (ルーターに自動で頼む) ----------------------------------------

SSDP_ADDR = ("239.255.255.250", 1900)
SSDP_SEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    "HOST: 239.255.255.250:1900\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 2\r\n"
    "ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n"
    "\r\n"
)

WAN_SERVICES = ("urn:schemas-upnp-org:service:WANIPConnection:1",
                "urn:schemas-upnp-org:service:WANPPPConnection:1",
                "urn:schemas-upnp-org:service:WANIPConnection:2")


def all_ipv4():
    """この PC の IPv4 アドレスを全部。

    Hyper-V の仮想スイッチなどがあると、何もしないと**そちらに向かって**
    探しに行ってしまってルーターが見つからない。だから 1 枚ずつ試す。
    LAN につながっていそうな方を先に並べる。
    """
    out = []
    mine = local_ip()
    if mine and not mine.startswith("127."):
        out.append(mine)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None,
                                       socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127.") or ip in out:
                continue
            out.append(ip)
    except OSError:
        pass
    return out


def discover_gateway(timeout=3.0):
    """ルーター (IGD) を探して説明 URL を返す。見つからなければ None。"""
    for ip in (all_ipv4() or [""]):
        got = _search_from(ip, timeout)
        if got:
            return got
    return None


def _search_from(bind_ip, timeout):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.settimeout(min(1.0, timeout))
    try:
        if bind_ip:
            s.bind((bind_ip, 0))
            # この網から出ていくようにする
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                         socket.inet_aton(bind_ip))
    except OSError:
        s.close()
        return None
    try:
        payload = SSDP_SEARCH.encode("ascii")
        for _ in range(2):               # 取りこぼしがあるので 2 回投げる
            s.sendto(payload, SSDP_ADDR)
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, _addr = s.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            for line in data.decode("ascii", "replace").splitlines():
                if line.lower().startswith("location:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        return None
    finally:
        s.close()
    return None


def _control_url(desc_url):
    """説明 XML から、ポート転送を頼む窓口の URL を探す。"""
    try:
        with urlopen(desc_url, timeout=5) as r:
            xml = r.read()
    except OSError:
        return None, None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None, None
    ns = "{urn:schemas-upnp-org:device-1-0}"
    for service in root.iter(ns + "service"):
        stype = (service.findtext(ns + "serviceType") or "").strip()
        if stype not in WAN_SERVICES:
            continue
        control = (service.findtext(ns + "controlURL") or "").strip()
        if not control:
            continue
        base = urlparse(desc_url)
        if control.startswith("http"):
            return control, stype
        return "%s://%s%s" % (base.scheme, base.netloc,
                              control if control.startswith("/")
                              else "/" + control), stype
    return None, None


def _soap(control, service, action, args):
    body = "".join("<%s>%s</%s>" % (k, v, k) for k, v in args)
    envelope = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        '<s:Body><u:%s xmlns:u="%s">%s</u:%s></s:Body></s:Envelope>'
        % (action, service, body, action)).encode("utf-8")
    req = Request(control, data=envelope, headers={
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPAction": '"%s#%s"' % (service, action)})
    with urlopen(req, timeout=8) as r:
        return r.read().decode("utf-8", "replace")


class UpnpMapping(object):
    """ルーターに「このポートを通して」と頼む。

    ルーターを再起動すると転送は消える。アプリを立ち上げ直せばまた頼む。
    """

    def __init__(self, port, description="ARK Library"):
        self.port = int(port)
        self.description = description
        self.control = None
        self.service = None
        self.external_ip = ""
        self.error = ""
        self.mapped = False

    def start(self):
        desc = discover_gateway()
        if not desc:
            self.error = ("ルーターが見つかりませんでした "
                          "(UPnP が切られているかもしれません)")
            return False
        self.control, self.service = _control_url(desc)
        if not self.control:
            self.error = "ルーターがポート転送に対応していません"
            return False
        me = local_ip()
        try:
            _soap(self.control, self.service, "AddPortMapping", [
                ("NewRemoteHost", ""),
                ("NewExternalPort", self.port),
                ("NewProtocol", "TCP"),
                ("NewInternalPort", self.port),
                ("NewInternalClient", me),
                ("NewEnabled", 1),
                ("NewPortMappingDescription", self.description),
                ("NewLeaseDuration", 0)])
        except Exception as e:
            self.error = "ルーターに断られました (%s)" % e
            return False
        self.mapped = True
        self.error = ""
        try:
            got = _soap(self.control, self.service, "GetExternalIPAddress", [])
            m = re.search(r"<NewExternalIPAddress>([^<]*)<", got)
            if m:
                self.external_ip = m.group(1).strip()
        except Exception:
            pass
        return True

    def stop(self):
        if not self.mapped or not self.control:
            return
        try:
            _soap(self.control, self.service, "DeletePortMapping", [
                ("NewRemoteHost", ""),
                ("NewExternalPort", self.port),
                ("NewProtocol", "TCP")])
        except Exception:
            pass
        self.mapped = False

    @property
    def url(self):
        return "http://%s:%d" % (self.external_ip, self.port) \
            if self.external_ip else ""
