# -*- coding: utf-8 -*-
"""ほかの PC とライブラリを共有する画面。

ゲーム用 PC で取り込んだ個体を、サーバー用 PC からも同じように見たい。
1 台を**共有元**にして、ほかの PC はそこへ数秒おきに読み書きしに行く。

各 PC は自分のデータを持ったまま動く。つながらないときもいつも通り使えて、
つながったら差分だけをやり取りする。
"""
import tkinter as tk
from tkinter import messagebox

from arklib import sync

from . import theme

MODE_OFF = "off"
MODE_SERVER = "server"
MODE_CLIENT = "client"


class SharePage(tk.Frame):
    def __init__(self, master, app):
        tk.Frame.__init__(self, master, bg=theme.BG)
        self.app = app
        self.st = app.state_obj
        self.share = app.share

        self.mode = tk.StringVar(value=self.share.mode)
        self.port = tk.StringVar(value=str(self.share.port))
        self.token = tk.StringVar(value=self.share.token)
        self.url = tk.StringVar(value=self.share.url)
        self.interval = tk.StringVar(value=str(int(self.share.interval)))

        self._build()
        self.reload()

    # ---- 組み立て ------------------------------------------------------

    def _build(self):
        tk.Label(self, text="ほかの PC と共有", bg=theme.BG, fg=theme.INK,
                 font=theme.F.get("head")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(self,
                 text="1 台を「共有元」にして、ほかの PC はそこへつなぎに行きます。\n"
                      "取り込んだ個体・メモ・理想個体・サーバー倍率が両方の PC に"
                      "揃います。\n"
                      "取り込みフォルダや画面の色はその PC のままです。",
                 bg=theme.BG, fg=theme.INK_SUB, font=theme.F.get("small"),
                 justify="left").pack(anchor="w", padx=16)

        # ---- どちらにするか ----
        card = theme.Card(self, bg=theme.BG)
        card.pack(fill="x", padx=16, pady=(10, 6))
        b = card.body
        for key, label_text, note in (
                (MODE_OFF, "共有しない", "この PC だけで使う"),
                (MODE_SERVER, "この PC を共有元にする",
                 "ずっと起動しておく側。サーバー用 PC におすすめ"),
                (MODE_CLIENT, "共有元につなぎに行く",
                 "ゲーム用 PC はこちら")):
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

        # ---- 共有元の設定 ----
        self.server_card = theme.Card(self, bg=theme.BG)
        sb = self.server_card.body
        tk.Label(sb, text="共有元として配る", bg=theme.CARD, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(anchor="w")
        row = tk.Frame(sb, bg=theme.CARD)
        row.pack(fill="x", pady=(6, 2))
        tk.Label(row, text="ポート", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small"), width=8, anchor="w").pack(side="left")
        theme.soft_entry(row, textvariable=self.port, width=8,
                         bg=theme.CARD).pack(side="left")
        tk.Label(row, text="合言葉", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=(16, 6))
        theme.soft_entry(row, textvariable=self.token, width=18,
                         bg=theme.CARD).pack(side="left")
        theme.RoundButton(row, "作り直す", self._new_token, kind="ghost",
                          bg=theme.CARD).pack(side="left", padx=6)

        self.addr = tk.Label(sb, text="", bg=theme.FIELD, fg=theme.INK,
                             font=theme.F.get("ui"), padx=10, pady=6,
                             anchor="w", justify="left")
        self.addr.pack(fill="x", pady=(8, 0))
        tk.Label(sb, text="ゲーム用 PC の「共有元のアドレス」にこれを入れてください。"
                          "ファイアウォールでこのポートを通す必要があります。",
                 bg=theme.CARD, fg=theme.INK_SUB, font=theme.F.get("small"),
                 justify="left").pack(anchor="w", pady=(4, 0))

        # ---- つなぎに行く設定 ----
        self.client_card = theme.Card(self, bg=theme.BG)
        cb = self.client_card.body
        tk.Label(cb, text="共有元につなぐ", bg=theme.CARD, fg=theme.INK,
                 font=theme.F.get("cute_b")).pack(anchor="w")
        row = tk.Frame(cb, bg=theme.CARD)
        row.pack(fill="x", pady=(6, 2))
        tk.Label(row, text="アドレス", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small"), width=8, anchor="w").pack(side="left")
        theme.soft_entry(row, textvariable=self.url, width=28,
                         bg=theme.CARD).pack(side="left")
        tk.Label(row, text="合言葉", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=(16, 6))
        theme.soft_entry(row, textvariable=self.token, width=18,
                         bg=theme.CARD).pack(side="left")
        row2 = tk.Frame(cb, bg=theme.CARD)
        row2.pack(fill="x", pady=(2, 2))
        tk.Label(row2, text="間隔", bg=theme.CARD, fg=theme.INK_SUB,
                 font=theme.F.get("small"), width=8, anchor="w").pack(side="left")
        theme.soft_entry(row2, textvariable=self.interval, width=6,
                         bg=theme.CARD).pack(side="left")
        tk.Label(row2, text="秒おきにやり取りします", bg=theme.CARD,
                 fg=theme.INK_SUB,
                 font=theme.F.get("small")).pack(side="left", padx=6)
        theme.RoundButton(row2, "つながるか試す", self._test, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=(16, 4))
        theme.RoundButton(row2, "いますぐ同期", self._sync_now, kind="soft",
                          bg=theme.CARD).pack(side="left", padx=4)

        # ---- 状態 ----
        foot = tk.Frame(self, bg=theme.BG)
        foot.pack(fill="x", padx=16, pady=(10, 4))
        theme.RoundButton(foot, "保存して反映", self._save, kind="primary",
                          bg=theme.BG).pack(side="left")
        self.state_label = tk.Label(foot, text="", bg=theme.BG, fg=theme.INK_SUB,
                                    font=theme.F.get("small"), anchor="w",
                                    justify="left")
        self.state_label.pack(side="left", padx=12)

        tk.Label(self,
                 text="つながらないときも、この PC のライブラリはそのまま使えます。\n"
                      "同じ個体を両方でいじったときは、あとから書いた方が残ります。",
                 bg=theme.BG, fg=theme.INK_SUB, font=theme.F.get("small"),
                 justify="left").pack(anchor="w", padx=16, pady=(10, 0))

    # ---- 中身 ----------------------------------------------------------

    def on_show(self):
        self.reload()

    def reload(self):
        self.mode.set(self.share.mode)
        self.port.set(str(self.share.port))
        self.token.set(self.share.token)
        self.url.set(self.share.url)
        self.interval.set(str(int(self.share.interval)))
        self._on_mode()
        self._refresh_state()

    def _on_mode(self):
        mode = self.mode.get()
        self.server_card.pack_forget()
        self.client_card.pack_forget()
        if mode == MODE_SERVER:
            self.server_card.pack(fill="x", padx=16, pady=6)
        elif mode == MODE_CLIENT:
            self.client_card.pack(fill="x", padx=16, pady=6)
        self._refresh_state()

    def _refresh_state(self):
        self.state_label.configure(text=self.share.describe())
        ports = self.port.get()
        addrs = sync.local_addresses()
        if addrs:
            self.addr.configure(
                text="\n".join("http://%s:%s" % (a, ports) for a in addrs))
        else:
            self.addr.configure(text="この PC のアドレスが分かりませんでした")

    def _new_token(self):
        self.token.set(sync.make_token())

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
                "url": self.url.get().strip(), "interval": interval}

    def _save(self):
        self.share.configure(**self._collect())
        ok, message = self.share.restart()
        self.reload()
        if not ok:
            messagebox.showwarning("共有", message, parent=self)
        else:
            self.app.refresh_status()

    def _test(self):
        d = self._collect()
        if not d["url"]:
            messagebox.showinfo("共有", "共有元のアドレスを入れてください。",
                                parent=self)
            return
        try:
            got = sync.ping(d["url"], d["token"])
        except Exception as e:
            messagebox.showwarning("共有", "つながりませんでした。\n\n%s" % e,
                                   parent=self)
            return
        messagebox.showinfo(
            "共有", "つながりました。\n\n相手: %s (やり取りの版 %s)%s"
            % (got.get("app"), got.get("protocol"),
               "\n合言葉が要ります。合っていないと弾かれます。"
               if got.get("needs_token") else ""), parent=self)

    def _sync_now(self):
        self.share.configure(**self._collect())
        n = self.share.sync_now()
        if isinstance(n, str):
            messagebox.showwarning("共有", n, parent=self)
        else:
            pulled, pushed = n
            messagebox.showinfo("共有", "受け取り %d 件 / 送り出し %d 件"
                                % (pulled, pushed), parent=self)
            self.app.reload_pages()
        self._refresh_state()
