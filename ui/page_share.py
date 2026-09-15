# -*- coding: utf-8 -*-
"""ほかの PC / 友達とライブラリを共有する画面。

1 台を**共有元**にして、ほかは数秒おきに読み書きしに行く。各 PC は自分の
データを持ったまま動くので、つながらないときもいつも通り使える。

友達に配るときは家の外に出す必要がある。ルーターを手でいじらずに済む道が
2 つあって、ここで選ぶ (Cloudflare トンネル / UPnP)。
"""
import subprocess
import tkinter as tk
from tkinter import messagebox

from arklib import sync, tunnel

from . import theme
from .share import (MODE_CLIENT, MODE_OFF, MODE_SERVER, OPEN_CLOUDFLARE,
                    OPEN_JA, OPEN_LAN, OPEN_UPNP)
from .table import Col, Table

ROLE_LABEL = {sync.ROLE_ADMIN: "管理者", sync.ROLE_MEMBER: "メンバー"}


class SharePage(tk.Frame):
    def __init__(self, master, app):
        tk.Frame.__init__(self, master, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.share = app.share

        self.mode = tk.StringVar(value=self.share.mode)
        self.opening = tk.StringVar(value=self.share.opening)
        self.port = tk.StringVar(value=str(self.share.port))
        self.token = tk.StringVar(value=self.share.token)
        self.url = tk.StringVar(value=self.share.url)
        self.interval = tk.StringVar(value=str(int(self.share.interval)))

        self._build()
        self.reload()

    # ---- 組み立て ------------------------------------------------------

    def _build(self):
        tk.Label(self, text="共有", bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("head")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(self,
                 text="1 台を共有元にして、他の PC はそこへ接続します。"
                      "個体・メモ・理想個体・サーバー倍率が同期されます。\n"
                      "取り込みフォルダとテーマは各 PC 固有の設定です。",
                 bg=theme.BG, fg=theme.INK_SUB, font=theme.F.get("small"),
                 justify="left").pack(anchor="w", padx=16)

        # ---- どちらにするか ----
        card = theme.Card(self, bg=theme.BG)
        card.pack(fill="x", padx=16, pady=(8, 4))
        b = card.body
        for key, label_text, note in (
                (MODE_OFF, "共有しない", "この PC 単体で使用"),
                (MODE_SERVER, "この PC を共有元にする",
                 "常時起動する側。サーバー用 PC 推奨"),
                (MODE_CLIENT, "共有元へ接続する",
                 "ゲーム用 PC・招待された側はこちら")):
            row = tk.Frame(b, bg=theme.CARD)
            row.pack(fill="x", pady=1)
            tk.Radiobutton(row, text=label_text, variable=self.mode, value=key,
                           command=self._on_mode, bg=theme.CARD, fg=theme.INK,
                           selectcolor=theme.FIELD, activebackground=theme.CARD,
                           activeforeground=theme.INK, font=theme.F.get("ui"),
                           bd=0, highlightthickness=0,
                           anchor="w").pack(side="left")
            tk.Label(row, text=note, bg=theme.CARD, fg=theme.INK_SUB,
                     font=theme.F.get("small")).pack(side="left", padx=10)

        self._build_server_card()
        self._build_client_card()

        # ---- 状態 ----
        foot = tk.Frame(self, bg=theme.BG)
        foot.pack(fill="x", padx=16, pady=(8, 4))
        theme.RoundButton(foot, "保存して適用", self._save, kind="primary",
                          bg=theme.BG).pack(side="left")
        self.state_label = tk.Label(foot, text="", bg=theme.BG, fg=theme.INK_SUB,
                                    font=theme.F.get("small"), anchor="w",
                                    justify="left", wraplength=780)
        self.state_label.pack(side="left", padx=12)

    def _build_server_card(self):
        self.server_card = theme.Card(self, bg=theme.BG)
        sb = self.server_card.body

        row = tk.Frame(sb, bg=theme.CARD)
        row.pack(fill="x")
        tk.Label(row, text="公開範囲", bg=theme.CARD, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(side="left")
        tk.Label(row, text="ポート", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=(16, 4))
        theme.soft_entry(row, textvariable=self.port, width=7,
                         bg=theme.CARD).pack(side="left")

        for key, note in (
                (OPEN_LAN, "同一 LAN 内の PC のみ。最も安全"),
                (OPEN_CLOUDFLARE,
                 "外部公開。ルーター設定は不要。cloudflared が必要"),
                (OPEN_UPNP,
                 "外部公開。ルーターへ自動でポート転送を要求。再起動で解除")):
            r = tk.Frame(sb, bg=theme.CARD)
            r.pack(fill="x", pady=1)
            tk.Radiobutton(r, text=OPEN_JA[key], variable=self.opening,
                           value=key, command=self._on_open, bg=theme.CARD,
                           fg=theme.INK, selectcolor=theme.FIELD,
                           activebackground=theme.CARD,
                           activeforeground=theme.INK, font=theme.F.get("ui"),
                           bd=0, highlightthickness=0, width=22,
                           anchor="w").pack(side="left")
            tk.Label(r, text=note, bg=theme.CARD, fg=theme.INK_SUB,
                     font=theme.F.get("small")).pack(side="left", padx=6)

        self.cf_note = tk.Frame(sb, bg=theme.CARD)
        self.cf_label = tk.Label(self.cf_note, text="", bg=theme.CARD,
                                 fg=theme.RED, font=theme.F.get("small"),
                                 justify="left", anchor="w")
        self.cf_label.pack(side="left")
        theme.RoundButton(self.cf_note, "winget で導入", self._install_cf,
                          kind="soft", bg=theme.CARD).pack(side="left", padx=8)

        self.addr_head = tk.Label(sb, text="接続先アドレス", bg=theme.CARD,
                                  fg=theme.INK_SUB, font=theme.F.get("small"))
        self.addr_head.pack(anchor="w", pady=(8, 2))
        self.addr = tk.Label(sb, text="", bg=theme.FIELD, fg=theme.INK,
                             font=theme.F.get("ui"), padx=10, pady=6,
                             anchor="w", justify="left")
        self.addr.pack(fill="x")
        theme.RoundButton(sb, "アドレスをコピー", self._copy_addr, kind="ghost",
                          bg=theme.CARD).pack(anchor="w", pady=(4, 0))

        # ---- 合言葉 ----
        head = tk.Frame(sb, bg=theme.CARD)
        head.pack(fill="x", pady=(12, 2))
        tk.Label(head, text="アクセスキー", bg=theme.CARD, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(side="left")
        tk.Label(head, text="管理者は読み書き可 / メンバーは閲覧のみ。"
                            "個別に発行すれば、個別に失効できます",
                 bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=10)
        theme.RoundButton(head, "メンバーキー発行",
                          lambda: self._issue(sync.ROLE_MEMBER), kind="soft",
                          bg=theme.CARD).pack(side="right", padx=3)
        theme.RoundButton(head, "管理者キー発行",
                          lambda: self._issue(sync.ROLE_ADMIN), kind="soft",
                          bg=theme.CARD).pack(side="right", padx=3)

        cols = [Col("name", "名前", 150),
                Col("role", "種類", 80, align="center"),
                Col("token", "アクセスキー", 190),
                Col("made", "発行日", 110)]
        self.token_table = Table(sb, cols, bg=theme.CARD, min_rows=4,
                                 on_row_menu=self._token_menu)
        self.token_table.pack(fill="x", pady=(2, 0))
        bar = tk.Frame(sb, bg=theme.CARD)
        bar.pack(fill="x", pady=(4, 0))
        theme.RoundButton(bar, "キーをコピー", self._copy_token, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=(0, 4))
        theme.RoundButton(bar, "招待文をコピー", self._copy_invite,
                          kind="primary", bg=theme.CARD).pack(side="left", padx=4)
        theme.RoundButton(bar, "失効", self._revoke, kind="danger",
                          bg=theme.CARD).pack(side="left", padx=4)

    def _build_client_card(self):
        self.client_card = theme.Card(self, bg=theme.BG)
        cb = self.client_card.body
        tk.Label(cb, text="共有元へ接続", bg=theme.CARD, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(anchor="w")
        row = tk.Frame(cb, bg=theme.CARD)
        row.pack(fill="x", pady=(6, 2))
        tk.Label(row, text="アドレス", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small"), width=8, anchor="w").pack(side="left")
        theme.soft_entry(row, textvariable=self.url, width=34,
                         bg=theme.CARD).pack(side="left")
        tk.Label(row, text="アクセスキー", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=(16, 6))
        theme.soft_entry(row, textvariable=self.token, width=20,
                         bg=theme.CARD).pack(side="left")
        row2 = tk.Frame(cb, bg=theme.CARD)
        row2.pack(fill="x", pady=(2, 2))
        tk.Label(row2, text="間隔", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small"), width=8, anchor="w").pack(side="left")
        theme.soft_entry(row2, textvariable=self.interval, width=6,
                         bg=theme.CARD).pack(side="left")
        tk.Label(row2, text="秒間隔で同期", bg=theme.CARD,
                 fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=6)
        theme.RoundButton(row2, "招待文から取り込む", self._paste_invite,
                          kind="soft", bg=theme.CARD).pack(side="left",
                                                           padx=(16, 4))
        theme.RoundButton(row2, "接続テスト", self._test, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=4)
        theme.RoundButton(row2, "今すぐ同期", self._sync_now, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=4)

    # ---- データ --------------------------------------------------------

    def on_show(self):
        self.reload()

    def reload(self):
        self.mode.set(self.share.mode)
        self.opening.set(self.share.opening)
        self.port.set(str(self.share.port))
        self.url.set(self.share.url)
        self.interval.set(str(int(self.share.interval)))
        if self.share.mode != MODE_SERVER:
            self.token.set(self.share.token)
        self._fill_tokens()
        self._on_mode()

    def _fill_tokens(self):
        import time as _t
        rows = []
        for t in self.share.tokens:
            rows.append({
                "_obj": t,
                "name": t.get("name") or "",
                "role": ROLE_LABEL.get(t.get("role"), t.get("role") or ""),
                "token": t.get("token") or "",
                "made": _t.strftime("%Y-%m-%d",
                                    _t.localtime(t.get("created_at") or 0))
                if t.get("created_at") else "",
            })
        self.token_table.set_rows(rows, keep_sort=False)

    def _on_mode(self):
        mode = self.mode.get()
        self.server_card.pack_forget()
        self.client_card.pack_forget()
        if mode == MODE_SERVER:
            self.server_card.pack(fill="x", padx=16, pady=4, before=self._anchor())
        elif mode == MODE_CLIENT:
            self.client_card.pack(fill="x", padx=16, pady=4, before=self._anchor())
        self._on_open()
        self._refresh_state()

    def _anchor(self):
        return self.state_label.master

    def _on_open(self):
        self.cf_note.pack_forget()
        if self.opening.get() == OPEN_CLOUDFLARE:
            exe = tunnel.find_cloudflared()
            if exe is None:
                self.cf_label.configure(
                    text="cloudflared 未導入:  %s"
                         % tunnel.CLOUDFLARED_INSTALL)
                # ラジオのすぐ下に出す (あとから pack すると一番下に行く)
                self.cf_note.pack(fill="x", pady=(4, 0),
                                  before=self.addr_head)
        self._refresh_state()

    def _refresh_state(self):
        self.state_label.configure(text=self.share.describe())
        addrs = self.share.addresses()
        if self.mode.get() == MODE_SERVER and self.share.server is None:
            addrs = ["(未公開。「保存して適用」を押してください)"]
        self.addr.configure(text="\n".join(addrs) or "(アドレス不明)")

    # ---- ボタン --------------------------------------------------------

    def _collect(self):
        try:
            port = int(self.port.get().strip() or sync.DEFAULT_PORT)
        except ValueError:
            port = sync.DEFAULT_PORT
        try:
            interval = max(2.0, float(self.interval.get().strip() or 5))
        except ValueError:
            interval = sync.DEFAULT_INTERVAL
        return {"mode": self.mode.get(), "port": port,
                "token": self.token.get().strip(),
                "url": self.url.get().strip(), "interval": interval,
                "opening": self.opening.get()}

    def _save(self):
        self.share.configure(**self._collect())
        ok, message = self.share.restart()
        self.reload()
        if not ok:
            detail = self.share.open_error or ""
            messagebox.showwarning("共有", "%s\n\n%s" % (message, detail),
                                   parent=self)
        else:
            self.app.refresh_status()

    def _issue(self, role):
        entry = self.share.issue(role)
        self._fill_tokens()
        if self.share.server is not None:
            self.share.restart()          # 新しい合言葉をすぐ効かせる
            self._refresh_state()
        messagebox.showinfo(
            "共有", "%s のアクセスキーを発行しました。\n\n%s\n\n"
                    "「招待文をコピー」で相手に渡せます。"
            % (ROLE_LABEL.get(role, role), entry["token"]), parent=self)

    def _selected_token(self):
        row = self.token_table.selected_row()
        if row is None:
            messagebox.showinfo("共有", "アクセスキーを選択してください。", parent=self)
            return None
        return row.get("_obj")

    def _token_menu(self, row, event):
        m = tk.Menu(self, tearoff=0, bg=theme.CARD, fg=theme.INK,
                    activebackground=theme.PINK,
                    activeforeground=theme.ON_ACCENT,
                    font=theme.F.get("ui"), bd=0)
        m.add_command(label="キーをコピー", command=self._copy_token)
        m.add_command(label="招待文をコピー", command=self._copy_invite)
        m.add_separator()
        m.add_command(label="失効", command=self._revoke)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _copy(self, text, note):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.state_label.configure(text=note)

    def _copy_addr(self):
        addrs = self.share.addresses()
        if not addrs:
            return
        self._copy(addrs[0], "アドレスをコピーしました: %s" % addrs[0])

    def _copy_token(self):
        t = self._selected_token()
        if t:
            self._copy(t.get("token", ""), "アクセスキーをコピーしました")

    def _copy_invite(self):
        """相手にそのまま渡せる案内文。"""
        t = self._selected_token()
        if not t:
            return
        addrs = self.share.addresses()
        outside = [a for a in addrs if "trycloudflare" in a
                   or not a.startswith("http://192.168.")]
        addr = (outside or addrs or ["(アドレス不明)"])[0]
        text = ("ARK ライブラリ 共有への招待\n"
                "1. アプリの「共有」→「共有元へ接続する」を選択\n"
                "2. アドレス: %s\n"
                "3. アクセスキー: %s\n"
                "   (権限: %s)\n"
                "4.「保存して適用」を押す" % (addr, t.get("token", ""),
                                            ROLE_LABEL.get(t.get("role"), "")))
        self._copy(text, "招待文をコピーしました。そのまま送信できます")

    def _revoke(self):
        t = self._selected_token()
        if not t:
            return
        if not messagebox.askyesno(
                "アクセスキーの失効",
                "%s (%s) のアクセスキーを失効します。\n"
                "このキーを使用中の相手は接続できなくなります。"
                % (t.get("name") or "", ROLE_LABEL.get(t.get("role"), "")),
                parent=self):
            return
        self.share.revoke(t.get("token"))
        self._fill_tokens()
        if self.share.server is not None:
            self.share.restart()
            self._refresh_state()

    def _install_cf(self):
        if not messagebox.askyesno(
                "cloudflared を入れる",
                "winget で Cloudflare 製 cloudflared を導入します。\n\n"
                "  %s\n\n実行しますか？" % tunnel.CLOUDFLARED_INSTALL,
                parent=self):
            return
        try:
            subprocess.Popen(["winget", "install", "--id",
                              "Cloudflare.cloudflared", "-e",
                              "--accept-package-agreements",
                              "--accept-source-agreements"])
        except OSError as e:
            messagebox.showwarning("共有", "winget を起動できませんでした。\n%s" % e,
                                   parent=self)
            return
        messagebox.showinfo("共有",
                            "導入完了後に「保存して適用」を押してください。",
                            parent=self)

    def _paste_invite(self):
        """相手から貰った案内文からアドレスと合言葉を拾う。"""
        try:
            text = self.clipboard_get()
        except tk.TclError:
            text = ""
        import re
        m = re.search(r"https?://[^\s]+", text or "")
        if m:
            self.url.set(m.group(0).rstrip("/"))
        m = re.search(r"合言葉[:：]\s*([A-Za-z0-9]{8,})", text or "")
        if m:
            self.token.set(m.group(1))
        if not (self.url.get() and self.token.get()):
            messagebox.showinfo("共有",
                                "クリップボードから取得できませんでした。\n"
                                "アドレスとキーを直接入力してください。", parent=self)
            return
        self.state_label.configure(text="取り込みました。「保存して適用」を押してください")

    def _test(self):
        d = self._collect()
        if not d["url"]:
            messagebox.showinfo("共有", "共有元のアドレスを入力してください。",
                                parent=self)
            return
        try:
            got = sync.ping(d["url"], d["token"])
        except Exception as e:
            messagebox.showwarning("共有", "接続できませんでした。\n\n%s" % e,
                                   parent=self)
            return
        role = got.get("role")
        messagebox.showinfo(
            "共有", "接続に成功しました。\n\n権限: %s"
            % (sync.ROLE_JA.get(role, "未認証 (アクセスキーが必要)")),
            parent=self)

    def _sync_now(self):
        self.share.configure(**self._collect())
        n = self.share.sync_now()
        if isinstance(n, str):
            messagebox.showwarning("共有", n, parent=self)
        else:
            pulled, pushed = n
            messagebox.showinfo("共有", "受信 %d 件 / 送信 %d 件"
                                % (pulled, pushed), parent=self)
            self.app.reload_pages()
        self._refresh_state()
