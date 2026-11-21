#!/usr/bin/env python3
"""MVP Client - launcher Minecraft 1.21.11 (Fabric) focado em FPS, com navegador Modrinth + CurseForge."""
import ctypes
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import customtkinter as ctk
import minecraft_launcher_lib as mll
import requests
from PIL import Image

MC_VERSION = "1.21.11"
ROOT = Path.home() / ".mvp-client"
GAME = ROOT / "game"
CFG_FILE = ROOT / "config.json"
REG_FILE = GAME / "mvp-installed.json"
UA = {"User-Agent": "MVP-Client/1.0 (launcher minecraft)"}
MR = "https://api.modrinth.com/v2"
CF = "https://api.curseforge.com/v1"
REDIRECT = "http://localhost:8765"
PAGE = 12
AZURE_URL = "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade"
MOJANG_FORM = "https://aka.ms/mce-reviewappid"

BG, PANEL, CARD, CARD2 = "#0A0C11", "#10131A", "#171B25", "#1E2330"
ACCENT, ACCENT_H, CYAN, MUTED, OK, ERR = "#8B5CF6", "#7C3AED", "#22D3EE", "#8A93A6", "#34D399", "#F87171"

# Pack de FPS (slugs do Modrinth). Os que nao existirem para 1.21.11 sao ignorados sem parar a instalacao.
FPS_PACK = ["fabric-api", "sodium", "lithium", "ferrite-core", "entityculling", "immediatelyfast",
            "modernfix", "sodium-extra", "reeses-sodium-options", "dynamic-fps", "moreculling", "mod-menu"]

KINDS = {"Mods": "mod", "Shaders": "shader", "Resource Packs": "resourcepack"}
FOLDER = {"mod": "mods", "shader": "shaderpacks", "resourcepack": "resourcepacks"}
LOADERS = {"mod": ["fabric"], "shader": ["iris"], "resourcepack": ["minecraft"]}
MR_SORT = {"Relevância": "relevance", "Downloads": "downloads", "Atualizados": "updated", "Novos": "newest"}
CF_SORT = {"Relevância": 2, "Downloads": 6, "Atualizados": 3, "Novos": 11}
CF_CLASS = {"mod": 6, "resourcepack": 12, "shader": 6552}

AIKAR = ["-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200", "-XX:+UnlockExperimentalVMOptions",
         "-XX:+DisableExplicitGC", "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40", "-XX:G1HeapRegionSize=8M",
         "-XX:G1ReservePercent=20", "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4",
         "-XX:InitiatingHeapOccupancyPercent=15", "-XX:G1MixedGCLiveThresholdPercent=90",
         "-XX:G1RSetUpdatingPauseTimePercent=5", "-XX:SurvivorRatio=32", "-XX:+PerfDisableSharedMem",
         "-XX:MaxTenuringThreshold=1"]
JVM_PRESETS = {"FPS máximo (G1 otimizado)": AIKAR, "Padrão": ["-XX:+UseG1GC"]}

FPS_OPTIONS = {"maxFps": "260", "enableVsync": "false", "renderDistance": "10", "simulationDistance": "8",
               "entityDistanceScaling": "0.75", "particles": "1", "biomeBlendRadius": "2", "entityShadows": "false",
               "renderClouds": '"false"', "mipmapLevels": "2"}

DEFAULTS = {"username": "Player", "ram_mb": 0, "jvm_preset": "FPS máximo (G1 otimizado)", "profile": "FPS Máximo",
            "curseforge_key": "", "ms_client_id": "", "accounts": [], "active": 0, "java_path": "", "close_on_launch": False,
            "iris": False, "options_applied": False}

BUNDLES = {
    "Menu principal personalizado": {
        "desc": "FancyMenu: botões do menu à esquerda, a tua skin 3D grande à direita (elemento Player Entity) e fundo à tua escolha (imagem, vídeo, panorama).",
        "mods": ["fancymenu", "konkrete", "melody"], "keys": {}},
    "Menu no jogo (Right Shift)": {
        "desc": "Mod Menu com todos os mods e configs, Zoomify, Freelook (perspetiva livre), F3 melhorado e HUD de armadura/comida.",
        "mods": ["modmenu", "yacl", "cloth-config", "zoomify", "freelook", "betterf3", "appleskin"],
        "keys": {"key_key.modmenu.open_menu": "key.keyboard.right.shift"}},
    "Visuais": {
        "desc": "Shaders (Iris), luz dinâmica e texturas conectadas.",
        "mods": ["iris", "lambdynamiclights", "continuity"], "keys": {}},
    "Cosméticos 3D": {
        "desc": "Avatares e modelos 3D (Figura) e camadas 3D da skin. Funcionam também em contas offline (só tu os vês).",
        "mods": ["figura", "skin-layers-3d"], "keys": {}},
}

S = requests.Session()
S.headers.update(UA)


# ----------------------------------------------------------------- utilitarios
def resource(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return str(base / name)


def total_ram_mb():
    try:
        if os.name == "nt":
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            s = MS()
            s.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
            return int(s.ullTotalPhys / 1048576)
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1048576)
    except Exception:
        return 8192


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def auto_ram():
    return max(2048, min(6144, int(total_ram_mb() * 0.5) // 512 * 512))


def jvm_args(cfg):
    ram = cfg["ram_mb"] or auto_ram()
    return [f"-Xms{max(1024, ram // 2)}M", f"-Xmx{ram}M"] + JVM_PRESETS.get(cfg["jvm_preset"], AIKAR)


def merge_options(path, updates):
    """Atualiza chaves em options.txt sem apagar o resto."""
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    if p.exists():
        p.with_name("options.txt.mvpbak").write_text("\n".join(lines), encoding="utf-8")
    done = set()
    for i, ln in enumerate(lines):
        k = ln.split(":", 1)[0]
        if k in updates:
            lines[i] = f"{k}:{updates[k]}"
            done.add(k)
    lines += [f"{k}:{v}" for k, v in updates.items() if k not in done]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def offline_uuid(name):
    return str(uuid.uuid3(uuid.NAMESPACE_OID, "OfflinePlayer:" + name))


def fmt_num(n):
    n = int(n or 0)
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.1f}k" if n >= 1e3 else str(n)


def download(url, dest, sha1=None):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and sha1:
        h = hashlib.sha1(dest.read_bytes()).hexdigest()
        if h == sha1:
            return
    tmp = dest.with_suffix(dest.suffix + ".part")
    with S.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        h = hashlib.sha1()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                h.update(chunk)
    if sha1 and h.hexdigest() != sha1:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("ficheiro corrompido (sha1 não bate)")
    os.replace(tmp, dest)


def registry_set(key, filename, folder):
    reg = load_json(REG_FILE, {})
    old = reg.get(key)
    if old and old["file"] != filename:
        (GAME / old["folder"] / old["file"]).unlink(missing_ok=True)
        (GAME / old["folder"] / (old["file"] + ".disabled")).unlink(missing_ok=True)
    reg[key] = {"file": filename, "folder": folder}
    save_json(REG_FILE, reg)


# ----------------------------------------------------------------- Modrinth
def mr_search(query, kind, sort, offset):
    facets = [[f"versions:{MC_VERSION}"], [f"project_type:{kind}"]]
    if kind == "mod":
        facets.append(["categories:fabric"])
    r = S.get(f"{MR}/search", params={"query": query, "facets": json.dumps(facets), "index": MR_SORT[sort],
                                     "limit": PAGE, "offset": offset}, timeout=20)
    r.raise_for_status()
    return [{"source": "modrinth", "id": h["project_id"], "title": h["title"], "desc": h["description"],
             "icon": h.get("icon_url"), "downloads": h["downloads"], "author": h["author"], "kind": kind,
             "url": f"https://modrinth.com/{kind}/{h['slug']}"} for h in r.json()["hits"]]


def mr_install(pid, kind, seen, log):
    r = S.get(f"{MR}/project/{pid}/version", params={"game_versions": json.dumps([MC_VERSION]),
                                                    "loaders": json.dumps(LOADERS[kind])}, timeout=20)
    r.raise_for_status()
    vs = r.json()
    if not vs:
        raise RuntimeError(f"sem versão para {MC_VERSION}")
    v = vs[0]
    if v["project_id"] in seen:
        return
    seen.add(v["project_id"])
    f = next((x for x in v["files"] if x.get("primary")), v["files"][0])
    download(f["url"], GAME / FOLDER[kind] / f["filename"], f["hashes"].get("sha1"))
    registry_set("mr:" + v["project_id"], f["filename"], FOLDER[kind])
    log(f"✔ {f['filename']}")
    if kind == "mod":
        for d in v.get("dependencies", []):
            if d.get("dependency_type") == "required" and d.get("project_id"):
                try:
                    mr_install(d["project_id"], "mod", seen, log)
                except Exception as e:
                    log(f"⚠ dependência {d['project_id']}: {e}")


def mr_install_slug(slug, kind, seen, log):
    try:
        mr_install(slug, kind, seen, log)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            hits = mr_search(slug.replace("-", " "), kind, "Relevância", 0)
            if not hits:
                raise RuntimeError("não encontrado")
            mr_install(hits[0]["id"], kind, seen, log)
        else:
            raise


# ----------------------------------------------------------------- CurseForge
def cf_headers(key):
    return {"x-api-key": key, "Accept": "application/json"}


def cf_search(key, query, kind, sort, offset):
    if not key:
        raise RuntimeError("Falta a chave da API do CurseForge (Definições).")
    p = {"gameId": 432, "classId": CF_CLASS[kind], "gameVersion": MC_VERSION, "searchFilter": query,
         "sortField": CF_SORT[sort], "sortOrder": "desc", "pageSize": PAGE, "index": offset}
    if kind == "mod":
        p["modLoaderType"] = 4
    r = S.get(f"{CF}/mods/search", params=p, headers=cf_headers(key), timeout=20)
    r.raise_for_status()
    return [{"source": "curseforge", "id": m["id"], "title": m["name"], "desc": m["summary"],
             "icon": (m.get("logo") or {}).get("thumbnailUrl"), "downloads": m["downloadCount"],
             "author": (m.get("authors") or [{"name": "?"}])[0]["name"], "kind": kind,
             "url": m["links"]["websiteUrl"]} for m in r.json()["data"]]


def cf_install(key, mid, kind, seen, log):
    if mid in seen:
        return
    seen.add(mid)
    p = {"gameVersion": MC_VERSION, "pageSize": 10}
    if kind == "mod":
        p["modLoaderType"] = 4
    r = S.get(f"{CF}/mods/{mid}/files", params=p, headers=cf_headers(key), timeout=20)
    r.raise_for_status()
    files = sorted(r.json()["data"], key=lambda x: x["fileDate"], reverse=True)
    if not files:
        raise RuntimeError(f"sem versão para {MC_VERSION}")
    f = files[0]
    url = f.get("downloadUrl") or f"https://edge.forgecdn.net/files/{f['id'] // 1000}/{f['id'] % 1000}/{f['fileName']}"
    sha1 = next((h["value"] for h in f.get("hashes", []) if h["algo"] == 1), None)
    try:
        download(url, GAME / FOLDER[kind] / f["fileName"], sha1)
    except Exception:
        raise RuntimeError("o autor bloqueou o download fora do site do CurseForge (abre a página)")
    registry_set(f"cf:{mid}", f["fileName"], FOLDER[kind])
    log(f"✔ {f['fileName']}")
    if kind == "mod":
        for d in f.get("dependencies", []):
            if d.get("relationType") == 3:
                try:
                    cf_install(key, d["modId"], "mod", seen, log)
                except Exception as e:
                    log(f"⚠ dependência {d['modId']}: {e}")


# ----------------------------------------------------------------- app
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ROOT.mkdir(parents=True, exist_ok=True)
        GAME.mkdir(parents=True, exist_ok=True)
        self.cfg = {**DEFAULTS, **load_json(CFG_FILE, {})}
        self.cfg["accounts"] = list(self.cfg.get("accounts") or [])
        if not self.cfg["accounts"]:
            old = self.cfg.get("account")
            if old:
                self.cfg["accounts"] = [{"type": "microsoft", **{k: old[k] for k in ("id", "name", "access_token", "refresh_token")}}]
            else:
                n = self.cfg.get("username", "Player")
                self.cfg["accounts"] = [{"type": "offline", "name": n, "id": offline_uuid(n)}]
        ctk.set_appearance_mode("dark")
        self.title("MVP Client")
        self.geometry("1120x720")
        self.minsize(980, 640)
        self.configure(fg_color=BG)
        self.after(300, lambda: self._set_icon())
        self.pool = ThreadPoolExecutor(4)
        self.ipool = ThreadPoolExecutor(3)
        self.icons = {}
        self.pmax = 1
        self.busy = False
        self.mod_offset = 0
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.pages = {}
        for name, builder in [("Jogar", self._page_play), ("Mods", self._page_mods), ("Extras", self._page_extras),
                              ("Instalados", self._page_installed), ("Contas", self._page_accounts),
                              ("Desempenho", self._page_perf), ("Definições", self._page_settings)]:
            f = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
            f.grid(row=0, column=1, sticky="nsew", padx=24, pady=20)
            f.grid_remove()
            self.pages[name] = f
            builder(f)
        self.refresh_accounts()
        self.show("Jogar")

    # ---- helpers
    def ui(self, fn, *a):
        try:
            self.after(0, lambda: fn(*a))
        except Exception:
            pass

    def save(self):
        save_json(CFG_FILE, self.cfg)

    def _set_icon(self):
        try:
            self.iconbitmap(resource("mvp.ico"))
        except Exception:
            pass

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=210, fg_color=PANEL, corner_radius=0)
        sb.grid(row=0, column=0, sticky="ns")
        sb.grid_propagate(False)
        try:
            img = Image.open(resource("logo.png")).convert("RGB").resize((96, 96))
            self.logo_img = ctk.CTkImage(light_image=img, dark_image=img, size=(96, 96))
            ctk.CTkLabel(sb, text="", image=self.logo_img).pack(pady=(22, 2))
        except Exception:
            pass
        ctk.CTkLabel(sb, text="MVP", font=("Segoe UI Black", 34), text_color=ACCENT).pack(pady=(0, 0))
        ctk.CTkLabel(sb, text=f"CLIENT • {MC_VERSION}", font=("Segoe UI", 11, "bold"), text_color=CYAN).pack(pady=(0, 18))
        self.nav = {}
        for n in ["Jogar", "Mods", "Extras", "Instalados", "Contas", "Desempenho", "Definições"]:
            b = ctk.CTkButton(sb, text=n, height=38, anchor="w", corner_radius=10, fg_color="transparent",
                              hover_color=CARD2, font=("Segoe UI", 14, "bold"), command=lambda x=n: self.show(x))
            b.pack(fill="x", padx=14, pady=3)
            self.nav[n] = b
        ctk.CTkLabel(sb, text="Fabric • Modrinth • CurseForge", font=("Segoe UI", 10), text_color=MUTED).pack(side="bottom", pady=14)

    def show(self, name):
        for n, f in self.pages.items():
            f.grid() if n == name else f.grid_remove()
            self.nav[n].configure(fg_color=ACCENT if n == name else "transparent")
        if name == "Instalados":
            self.refresh_installed()
        if name == "Mods" and not self.mod_results_shown:
            self.do_search(reset=True)

    def head(self, parent, title, sub):
        ctk.CTkLabel(parent, text=title, font=("Segoe UI", 28, "bold")).pack(anchor="w")
        ctk.CTkLabel(parent, text=sub, font=("Segoe UI", 13), text_color=MUTED).pack(anchor="w", pady=(0, 14))

    # ---- JOGAR
    def _page_play(self, p):
        self.head(p, "Jogar", f"Minecraft {MC_VERSION} com Fabric, otimizado para FPS")
        card = ctk.CTkFrame(p, fg_color=CARD, corner_radius=16)
        card.pack(fill="x")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(22, 8))
        self.acc_menu = ctk.CTkOptionMenu(row, values=["—"], width=270, height=40, fg_color=CARD2, button_color=ACCENT,
                                          command=self.on_pick_account)
        self.acc_menu.pack(side="left")
        ctk.CTkButton(row, text="Contas", width=90, height=40, fg_color=CARD2, hover_color=CARD,
                      command=lambda: self.show("Contas")).pack(side="left", padx=8)
        self.profile = ctk.CTkOptionMenu(row, values=["FPS Máximo", "Vanilla + Fabric"], width=190, height=40,
                                         fg_color=CARD2, button_color=ACCENT, command=lambda v: self.cfg.update(profile=v))
        self.profile.set(self.cfg["profile"])
        self.profile.pack(side="right")
        self.play_btn = ctk.CTkButton(card, text="JOGAR", height=62, corner_radius=14, fg_color=ACCENT,
                                      hover_color=ACCENT_H, font=("Segoe UI Black", 22), command=self.on_play)
        self.play_btn.pack(fill="x", padx=22, pady=10)
        self.bar = ctk.CTkProgressBar(card, height=10, progress_color=CYAN, fg_color=CARD2)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=22, pady=(4, 2))
        self.status = ctk.CTkLabel(card, text="Pronto.", text_color=MUTED, anchor="w")
        self.status.pack(fill="x", padx=24, pady=(0, 18))
        self.logbox = ctk.CTkTextbox(p, fg_color=PANEL, corner_radius=12, font=("Consolas", 12), state="disabled")
        self.logbox.pack(fill="both", expand=True, pady=(14, 0))

    # ---- CONTAS
    def acc_label(self, a):
        return f"{a['name']}  •  {'ORIGINAL' if a['type'] == 'microsoft' else 'OFFLINE'}"

    def active_account(self):
        accs = self.cfg["accounts"]
        if not accs:
            return None
        self.cfg["active"] = max(0, min(self.cfg["active"], len(accs) - 1))
        return accs[self.cfg["active"]]

    def refresh_accounts(self):
        labels = [self.acc_label(a) for a in self.cfg["accounts"]] or ["—"]
        self.acc_menu.configure(values=labels)
        a = self.active_account()
        self.acc_menu.set(self.acc_label(a) if a else "—")
        if hasattr(self, "acc_list"):
            self.render_accounts()

    def on_pick_account(self, v):
        labels = [self.acc_label(a) for a in self.cfg["accounts"]]
        if v in labels:
            self.cfg["active"] = labels.index(v)
            self.save()
            self.render_accounts()

    def _page_accounts(self, p):
        self.head(p, "Contas", "Contas originais (Microsoft) e offline (pirata)")
        card = ctk.CTkFrame(p, fg_color=CARD, corner_radius=16)
        card.pack(fill="x")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=18)
        self.new_name = ctk.CTkEntry(row, width=240, height=40, placeholder_text="Nome da conta offline")
        self.new_name.pack(side="left")
        self.new_name.bind("<Return>", lambda e: self.add_offline())
        ctk.CTkButton(row, text="Adicionar offline", height=40, fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self.add_offline).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Adicionar conta Microsoft", height=40, fg_color=CARD2, command=self.ms_login).pack(side="left")
        ctk.CTkButton(row, text="Como ativar", height=40, fg_color=CARD2, command=self.ms_guide).pack(side="left", padx=8)
        self.acc_msg = ctk.CTkLabel(card, text="Offline funciona logo (não entra em servidores online-mode). "
                                    "Conta original: carrega em «Como ativar» (precisa de um Client ID aprovado pela Mojang).", text_color=MUTED,
                                    anchor="w", wraplength=760, justify="left")
        self.acc_msg.pack(fill="x", padx=22, pady=(0, 16))
        self.acc_list = ctk.CTkScrollableFrame(p, fg_color=PANEL, corner_radius=12)
        self.acc_list.pack(fill="both", expand=True, pady=12)
        self.refresh_accounts()

    def add_offline(self):
        n = self.new_name.get().strip()[:16]
        if not n:
            return
        self.cfg["accounts"].append({"type": "offline", "name": n, "id": offline_uuid(n)})
        self.cfg["active"] = len(self.cfg["accounts"]) - 1
        self.save()
        self.new_name.delete(0, "end")
        self.refresh_accounts()

    def render_accounts(self):
        for w in self.acc_list.winfo_children():
            w.destroy()
        for i, a in enumerate(self.cfg["accounts"]):
            r = ctk.CTkFrame(self.acc_list, fg_color=CARD, corner_radius=10)
            r.pack(fill="x", padx=6, pady=3)
            on = i == self.cfg["active"]
            ctk.CTkLabel(r, text=self.acc_label(a), font=("Segoe UI", 14, "bold"),
                         text_color=ACCENT if on else "white").pack(side="left", padx=14, pady=12)
            ctk.CTkButton(r, text="Remover", width=80, fg_color="#3B1D26", hover_color="#5A2634",
                          command=lambda i=i: self.remove_account(i)).pack(side="right", padx=10)
            if on:
                ctk.CTkLabel(r, text="ATIVA", text_color=OK).pack(side="right", padx=8)
            else:
                ctk.CTkButton(r, text="Usar", width=70, fg_color=ACCENT, hover_color=ACCENT_H,
                              command=lambda i=i: self.use_account(i)).pack(side="right", padx=4)

    def use_account(self, i):
        self.cfg["active"] = i
        self.save()
        self.refresh_accounts()

    def remove_account(self, i):
        self.cfg["accounts"].pop(i)
        self.save()
        self.refresh_accounts()

    def log(self, text):
        def w():
            self.logbox.configure(state="normal")
            self.logbox.insert("end", text + "\n")
            self.logbox.see("end")
            self.logbox.configure(state="disabled")
        self.ui(w)

    def set_status(self, t):
        self.status.configure(text=t)

    def cb(self):
        last = {"p": 0.0, "s": 0.0}

        def prog(v):
            now = time.monotonic()
            if now - last["p"] < 0.12 and v < self.pmax:
                return
            last["p"] = now
            self.ui(self.bar.set, min(1, v / self.pmax))

        def stat(t):
            now = time.monotonic()
            if now - last["s"] < 0.2:
                return
            last["s"] = now
            self.ui(self.set_status, t)
        return {"setStatus": stat, "setProgress": prog,
                "setMax": lambda m: setattr(self, "pmax", max(1, m))}

    def on_play(self):
        if self.busy:
            return
        self.save()
        self.busy = True
        self.play_btn.configure(state="disabled", text="A PREPARAR…")
        threading.Thread(target=self.play_worker, daemon=True).start()

    def play_worker(self):
        try:
            cfg = self.cfg
            loader = mll.fabric.get_latest_loader_version()
            vid = f"fabric-loader-{loader}-{MC_VERSION}"
            if not (GAME / "versions" / vid / f"{vid}.json").exists():
                self.log(f"A instalar Minecraft {MC_VERSION} + Fabric {loader}…")
                mll.fabric.install_fabric(MC_VERSION, str(GAME), loader_version=loader, callback=self.cb())
            if cfg["profile"] == "FPS Máximo":
                self.install_pack(self.log)
                if not cfg["options_applied"]:
                    merge_options(GAME / "options.txt", FPS_OPTIONS)
                    cfg["options_applied"] = True
                    self.save()
                    self.log("✔ Definições gráficas de FPS aplicadas (backup: options.txt.mvpbak)")
            opts = {"launcherName": "MVP", "launcherVersion": "1.0", "gameDirectory": str(GAME),
                    "jvmArguments": jvm_args(cfg)}
            acc = self.active_account()
            if not acc:
                raise RuntimeError("Adiciona uma conta no separador Contas.")
            if acc["type"] == "microsoft":
                if not cfg["ms_client_id"]:
                    raise RuntimeError("Falta o Azure Client ID nas Definições (conta Microsoft).")
                try:
                    r = mll.microsoft_account.complete_refresh(cfg["ms_client_id"], None, REDIRECT, acc["refresh_token"])
                    acc.update({k: r[k] for k in ("id", "name", "access_token", "refresh_token")})
                    self.save()
                except Exception as e:
                    raise RuntimeError(f"Sessão Microsoft expirou, volta a iniciar sessão em Contas ({e})")
                opts.update(username=acc["name"], uuid=acc["id"], token=acc["access_token"])
            else:
                opts.update(username=acc["name"], uuid=acc["id"], token="")
            exe = cfg["java_path"] or self.java_exec()
            if exe:
                opts["executablePath"] = exe
            cmd = mll.command.get_minecraft_command(vid, str(GAME), opts)
            (GAME / "logs").mkdir(exist_ok=True)
            logf = open(GAME / "logs" / "mvp-launch.log", "w")
            flags = 0x08000000 if os.name == "nt" else 0
            subprocess.Popen(cmd, cwd=str(GAME), stdout=logf, stderr=subprocess.STDOUT, creationflags=flags)
            self.log("🚀 Minecraft iniciado!")
            self.ui(self.set_status, "A jogar…")
            self.ui(self.bar.set, 1)
            self.ui(self.destroy if cfg["close_on_launch"] else self.iconify)
        except Exception as e:
            self.log(f"✖ Erro: {e}")
            self.ui(self.set_status, f"Erro: {e}")
        finally:
            self.busy = False
            self.ui(lambda: self.play_btn.configure(state="normal", text="JOGAR"))

    def java_exec(self):
        try:
            vj = load_json(GAME / "versions" / MC_VERSION / f"{MC_VERSION}.json", {})
            return mll.runtime.get_executable_path(vj["javaVersion"]["component"], str(GAME))
        except Exception:
            return None

    def install_pack(self, log):
        slugs = list(FPS_PACK) + (["iris"] if self.cfg["iris"] else [])
        seen = set()
        log("A verificar o pack de FPS…")
        for i, s in enumerate(slugs):
            self.ui(self.set_status, f"Pack de FPS: {s} ({i + 1}/{len(slugs)})")
            self.ui(self.bar.set, (i + 1) / len(slugs))
            try:
                mr_install_slug(s, "mod", seen, log)
            except Exception as e:
                log(f"⚠ {s}: {e}")

    # ---- MODS
    mod_results_shown = False

    def _page_mods(self, p):
        self.head(p, "Mods", f"Navegador Modrinth e CurseForge • filtrado para {MC_VERSION} Fabric")
        bar = ctk.CTkFrame(p, fg_color="transparent")
        bar.pack(fill="x")
        self.q = ctk.CTkEntry(bar, height=40, placeholder_text="Pesquisar… (sodium, shaders, etc.)")
        self.q.pack(side="left", fill="x", expand=True)
        self.q.bind("<Return>", lambda e: self.do_search(reset=True))
        self.src = ctk.CTkSegmentedButton(bar, values=["Modrinth", "CurseForge"], selected_color=ACCENT,
                                          selected_hover_color=ACCENT_H, command=lambda v: self.do_search(reset=True))
        self.src.set("Modrinth")
        self.src.pack(side="left", padx=8)
        self.kind = ctk.CTkOptionMenu(bar, values=list(KINDS), width=130, height=40, fg_color=CARD2, button_color=ACCENT,
                                      command=lambda v: self.do_search(reset=True))
        self.kind.pack(side="left")
        self.sort = ctk.CTkOptionMenu(bar, values=list(MR_SORT), width=130, height=40, fg_color=CARD2, button_color=ACCENT,
                                      command=lambda v: self.do_search(reset=True))
        self.sort.set("Downloads")
        self.sort.pack(side="left", padx=8)
        ctk.CTkButton(bar, text="Pesquisar", width=100, height=40, fg_color=ACCENT, hover_color=ACCENT_H,
                      command=lambda: self.do_search(reset=True)).pack(side="left")
        self.results = ctk.CTkScrollableFrame(p, fg_color=PANEL, corner_radius=12)
        self.results.pack(fill="both", expand=True, pady=(12, 6))
        self.mod_msg = ctk.CTkLabel(p, text="", text_color=MUTED, anchor="w")
        self.mod_msg.pack(fill="x")
        self.search_token = 0

    def do_search(self, reset=False):
        self.mod_results_shown = True
        if reset:
            self.mod_offset = 0
            for w in self.results.winfo_children():
                w.destroy()
        self.search_token += 1
        tok = self.search_token
        self.mod_msg.configure(text="A pesquisar…", text_color=MUTED)
        q, src, kind, sort, off = self.q.get().strip(), self.src.get(), KINDS[self.kind.get()], self.sort.get(), self.mod_offset

        def work():
            try:
                items = mr_search(q, kind, sort, off) if src == "Modrinth" else cf_search(self.cfg["curseforge_key"], q, kind, sort, off)
                if tok == self.search_token:
                    self.ui(self.render_results, items, tok)
            except Exception as e:
                self.ui(lambda: self.mod_msg.configure(text=f"Erro: {e}", text_color=ERR))
        self.pool.submit(work)

    def render_results(self, items, tok):
        for w in self.results.winfo_children():
            if getattr(w, "_more", False):
                w.destroy()
        self._reg = load_json(REG_FILE, {})
        self._queue = list(items)
        self._new = len(items)
        self._pump(tok)

    def _pump(self, tok):
        if tok != self.search_token:
            return
        for _ in range(3):
            if not self._queue:
                break
            self.add_card(self._queue.pop(0), self._reg)
        if self._queue:
            self.after(12, lambda: self._pump(tok))
            return
        self.mod_offset += self._new
        self.mod_msg.configure(text=f"{self.mod_offset} resultados" if self._new else "Sem resultados.", text_color=MUTED)
        if self._new >= PAGE:
            b = ctk.CTkButton(self.results, text="Carregar mais", fg_color=CARD2, hover_color=CARD,
                              command=lambda: self.do_search(reset=False))
            b._more = True
            b.pack(pady=10)

    def add_card(self, it, reg):
        c = ctk.CTkFrame(self.results, fg_color=CARD, corner_radius=10)
        c.pack(fill="x", padx=4, pady=3)
        c.grid_columnconfigure(1, weight=1)
        icon = ctk.CTkLabel(c, text="", width=52, height=52)
        icon.grid(row=0, column=0, rowspan=2, padx=10, pady=8)
        self.load_icon(it.get("icon"), icon)
        ctk.CTkLabel(c, text=f"{it['title']}    ⬇ {fmt_num(it['downloads'])} · {it['author']}",
                     font=("Segoe UI", 14, "bold"), anchor="w").grid(row=0, column=1, sticky="ew", pady=(8, 0))
        ctk.CTkLabel(c, text=(it["desc"] or "")[:130], text_color=MUTED, anchor="w", justify="left",
                     wraplength=560).grid(row=1, column=1, sticky="ew", pady=(0, 8))
        key = ("mr:" if it["source"] == "modrinth" else "cf:") + str(it["id"])
        done = key in reg
        btn = ctk.CTkButton(c, text="Instalado ✓" if done else "Instalar", width=104, height=36,
                            fg_color=CARD2 if done else ACCENT, hover_color=ACCENT_H)
        btn.configure(command=lambda: self.install_item(it, btn))
        btn.grid(row=0, column=2, rowspan=2, padx=10)

    def load_icon(self, url, label):
        if not url:
            return
        if url in self.icons:
            label.configure(image=self.icons[url])
            return

        def work():
            try:
                f = ROOT / "cache" / (hashlib.sha1(url.encode()).hexdigest() + ".png")
                if f.exists():
                    img = Image.open(f).convert("RGBA")
                else:
                    img = Image.open(io.BytesIO(S.get(url, timeout=15).content)).convert("RGBA").resize((52, 52))
                    f.parent.mkdir(parents=True, exist_ok=True)
                    img.save(f)

                def apply():
                    if url not in self.icons:
                        self.icons[url] = ctk.CTkImage(light_image=img, dark_image=img, size=(52, 52))
                    try:
                        label.configure(image=self.icons[url])
                    except Exception:
                        pass
                self.ui(apply)
            except Exception:
                pass
        self.ipool.submit(work)

    def install_item(self, it, btn):
        btn.configure(state="disabled", text="A instalar…")
        msgs = []

        def work():
            try:
                seen = set()
                if it["source"] == "modrinth":
                    mr_install(it["id"], it["kind"], seen, msgs.append)
                else:
                    cf_install(self.cfg["curseforge_key"], it["id"], it["kind"], seen, msgs.append)
                self.ui(lambda: btn.configure(text="Instalado ✓", fg_color=CARD2, state="normal"))
                self.ui(lambda: self.mod_msg.configure(text=" • ".join(msgs[-3:]), text_color=OK))
            except Exception as e:
                self.ui(lambda: btn.configure(text="Erro", state="normal"))
                self.ui(lambda: self.mod_msg.configure(text=f"{it['title']}: {e}", text_color=ERR))
                if "bloqueou" in str(e):
                    webbrowser.open(it["url"])
        self.pool.submit(work)

    # ---- INSTALADOS
    def _page_installed(self, p):
        self.head(p, "Instalados", "Ativa, desativa ou remove mods")
        top = ctk.CTkFrame(p, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkButton(top, text="Abrir pasta", fg_color=CARD2, width=120, command=lambda: self.open_dir(GAME / "mods")).pack(side="left")
        ctk.CTkButton(top, text="Atualizar lista", fg_color=CARD2, width=120, command=self.refresh_installed).pack(side="left", padx=8)
        self.inst = ctk.CTkScrollableFrame(p, fg_color=PANEL, corner_radius=12)
        self.inst.pack(fill="both", expand=True, pady=12)

    def open_dir(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(path)  # noqa
        else:
            subprocess.Popen(["open" if os.uname().sysname == "Darwin" else "xdg-open", str(path)])

    def refresh_installed(self):
        for w in self.inst.winfo_children():
            w.destroy()
        d = GAME / "mods"
        files = sorted([f for f in d.glob("*") if f.name.endswith((".jar", ".jar.disabled"))], key=lambda f: f.name.lower()) if d.exists() else []
        if not files:
            ctk.CTkLabel(self.inst, text="Ainda não há mods. Carrega em JOGAR (pack de FPS) ou vai a Mods.", text_color=MUTED).pack(pady=30)
        for f in files:
            r = ctk.CTkFrame(self.inst, fg_color=CARD, corner_radius=10)
            r.pack(fill="x", padx=6, pady=3)
            on = f.name.endswith(".jar")
            sw = ctk.CTkSwitch(r, text="", width=46, progress_color=ACCENT)
            sw.select() if on else sw.deselect()
            sw.configure(command=lambda f=f, sw=sw: self.toggle_mod(f, sw))
            sw.pack(side="left", padx=12, pady=10)
            ctk.CTkLabel(r, text=f.name.replace(".disabled", ""), anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(r, text="Remover", width=80, fg_color="#3B1D26", hover_color="#5A2634",
                          command=lambda f=f: (f.unlink(missing_ok=True), self.refresh_installed())).pack(side="right", padx=10)

    def toggle_mod(self, f, sw):
        new = f.with_name(f.name[:-9]) if f.name.endswith(".disabled") else f.with_name(f.name + ".disabled")
        f.rename(new)
        self.refresh_installed()

    # ---- DESEMPENHO
    def _page_perf(self, p):
        self.head(p, "Desempenho", "Tudo o que pesa nos FPS num só sítio")
        card = ctk.CTkFrame(p, fg_color=CARD, corner_radius=16)
        card.pack(fill="x")
        tot = total_ram_mb()
        mx = max(2048, min(16384, tot - 1024))
        cur = self.cfg["ram_mb"] or auto_ram()
        self.ram_lbl = ctk.CTkLabel(card, text="", font=("Segoe UI", 14, "bold"))
        self.ram_lbl.pack(anchor="w", padx=22, pady=(20, 4))
        self.ram = ctk.CTkSlider(card, from_=1024, to=mx, number_of_steps=max(1, (mx - 1024) // 512), progress_color=ACCENT,
                                 command=self.on_ram)
        self.ram.set(min(cur, mx))
        self.ram.pack(fill="x", padx=22)
        self.on_ram(min(cur, mx))
        ctk.CTkLabel(card, text="Flags da JVM", text_color=MUTED).pack(anchor="w", padx=22, pady=(14, 2))
        om = ctk.CTkOptionMenu(card, values=list(JVM_PRESETS), fg_color=CARD2, button_color=ACCENT, width=280,
                               command=lambda v: (self.cfg.update(jvm_preset=v), self.save()))
        om.set(self.cfg["jvm_preset"] if self.cfg["jvm_preset"] in JVM_PRESETS else list(JVM_PRESETS)[0])
        om.pack(anchor="w", padx=22)
        iris = ctk.CTkSwitch(card, text="Incluir Iris Shaders no pack de FPS", progress_color=ACCENT,
                             command=lambda: (self.cfg.update(iris=bool(iris.get())), self.save()))
        iris.select() if self.cfg["iris"] else iris.deselect()
        iris.pack(anchor="w", padx=22, pady=14)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(0, 22))
        ctk.CTkButton(row, text="Aplicar gráficos de FPS", fg_color=ACCENT, hover_color=ACCENT_H, command=self.apply_opts).pack(side="left")
        ctk.CTkButton(row, text="Atualizar pack de FPS", fg_color=CARD2, command=lambda: threading.Thread(
            target=lambda: (self.install_pack(self.log), self.ui(self.set_status, "Pack atualizado.")), daemon=True).start()).pack(side="left", padx=8)
        tips = ("O que o modo FPS Máximo faz:\n"
                "• Instala Sodium, Lithium, FerriteCore, EntityCulling, ImmediatelyFast, ModernFix, MoreCulling, Dynamic FPS e extras.\n"
                "• Usa flags de JVM afinadas para menos pausas do garbage collector.\n"
                "• Aplica gráficos leves (distância 10, nuvens/sombras off, sem V-Sync, FPS ilimitados).\n"
                "• Não dês mais RAM do que precisas: 4–6 GB chega e dá mais estabilidade.")
        ctk.CTkLabel(p, text=tips, justify="left", text_color=MUTED, anchor="w", wraplength=760).pack(anchor="w", pady=18)

    def on_ram(self, v):
        v = int(v) // 512 * 512
        self.cfg["ram_mb"] = v
        self.ram_lbl.configure(text=f"Memória RAM: {v / 1024:.1f} GB")
        self.save()

    def apply_opts(self):
        merge_options(GAME / "options.txt", FPS_OPTIONS)
        self.cfg["options_applied"] = True
        self.save()
        self.log("✔ Gráficos de FPS aplicados (backup: options.txt.mvpbak)")
        self.set_status("Gráficos de FPS aplicados.")

    # ---- EXTRAS
    def _page_extras(self, p):
        self.head(p, "Extras", "Cosméticos 3D e menu no jogo estilo Lunar (mods reais, instalados com 1 clique)")
        for name, b in BUNDLES.items():
            c = ctk.CTkFrame(p, fg_color=CARD, corner_radius=16)
            c.pack(fill="x", pady=6)
            c.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(c, text=name, font=("Segoe UI", 18, "bold"), anchor="w").grid(row=0, column=0, sticky="w", padx=22, pady=(16, 0))
            ctk.CTkLabel(c, text=b["desc"], text_color=MUTED, anchor="w", justify="left", wraplength=640).grid(
                row=1, column=0, sticky="w", padx=22)
            ctk.CTkLabel(c, text="Inclui: " + ", ".join(b["mods"]), text_color=CYAN, font=("Segoe UI", 11), anchor="w").grid(
                row=2, column=0, sticky="w", padx=22, pady=(2, 16))
            btn = ctk.CTkButton(c, text="Instalar", width=120, height=40, fg_color=ACCENT, hover_color=ACCENT_H)
            btn.configure(command=lambda n=name, bt=btn: self.install_bundle(n, bt))
            btn.grid(row=0, column=1, rowspan=3, padx=22)
        self.ex_msg = ctk.CTkLabel(p, text="", text_color=MUTED, anchor="w", justify="left", wraplength=800)
        self.ex_msg.pack(fill="x", pady=10)

    def install_bundle(self, name, btn):
        b = BUNDLES[name]
        btn.configure(state="disabled", text="A instalar…")

        def work():
            seen, ok, bad = set(), [], []
            for slug in b["mods"]:
                self.ui(lambda s=slug: self.ex_msg.configure(text=f"A instalar {s}…", text_color=MUTED))
                try:
                    mr_install_slug(slug, "mod", seen, lambda t: None)
                    ok.append(slug)
                except Exception as e:
                    bad.append(f"{slug} ({e})")
            if b["keys"]:
                merge_options(GAME / "options.txt", b["keys"])
            msg = f"✔ {len(ok)} instalados" + (f" • ⚠ sem versão para {MC_VERSION}: " + ", ".join(bad) if bad else "")
            self.ui(lambda: self.ex_msg.configure(text=msg, text_color=OK if not bad else MUTED))
            self.ui(lambda: btn.configure(state="normal", text="Instalado ✓"))
        self.pool.submit(work)

    # ---- DEFINICOES
    def _page_settings(self, p):
        self.head(p, "Definições", "Chaves de API e Java")
        card = ctk.CTkFrame(p, fg_color=CARD, corner_radius=16)
        card.pack(fill="x")

        def field(label, key, ph, show=None):
            ctk.CTkLabel(card, text=label, text_color=MUTED).pack(anchor="w", padx=22, pady=(16, 2))
            e = ctk.CTkEntry(card, height=38, placeholder_text=ph, show=show)
            e.insert(0, self.cfg[key] or "")
            e.pack(fill="x", padx=22)
            return e
        self.e_cf = field("Chave da API do CurseForge (grátis em console.curseforge.com)", "curseforge_key", "x-api-key", "•")
        self.e_ms = field("Azure Client ID (contas originais, ver Contas > Como ativar)", "ms_client_id", "xxxxxxxx-xxxx-…")
        self.e_java = field("Caminho do Java (vazio = automático)", "java_path", "C:\\...\\javaw.exe")
        sw = ctk.CTkSwitch(card, text="Fechar o launcher ao iniciar o jogo", progress_color=ACCENT,
                           command=lambda: self.cfg.update(close_on_launch=bool(sw.get())))
        sw.select() if self.cfg["close_on_launch"] else sw.deselect()
        sw.pack(anchor="w", padx=22, pady=14)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(0, 22))
        ctk.CTkButton(row, text="Guardar", fg_color=ACCENT, hover_color=ACCENT_H, command=self.save_settings).pack(side="left")
        ctk.CTkButton(row, text="Abrir pasta do jogo", fg_color=CARD2, command=lambda: self.open_dir(GAME)).pack(side="right")

    def save_settings(self):
        self.cfg.update(curseforge_key=self.e_cf.get().strip(), ms_client_id=self.e_ms.get().strip(), java_path=self.e_java.get().strip())
        self.save()
        self.set_status("Definições guardadas.")

    GUIDE = ("CONTA ORIGINAL (Microsoft) no MVP\n\n"
             "A Mojang só deixa launchers usarem contas originais com uma app registada e aprovada por eles. "
             "É grátis, mas feito uma vez só:\n\n"
             "1) Portal Azure > Registos de aplicações > Novo registo.\n"
             "   Tipo de conta: 'Apenas contas Microsoft pessoais'.\n"
             "   URI de redirecionamento: plataforma 'Cliente público/nativo (móvel e ambiente de trabalho)' = http://localhost\n"
             "2) Em Autenticação, ativa 'Permitir fluxos de cliente público' = Sim.\n"
             "3) Copia o 'ID da aplicação (cliente)' e cola em Definições > Azure Client ID.\n"
             "4) Preenche o formulário da Mojang (botão abaixo) a pedir aprovação desse ID. "
             "Pode demorar alguns dias; até lá o login dá erro 'Invalid app registration'.\n"
             "5) Volta aqui e carrega em 'Adicionar conta Microsoft': abre o browser, entras, e o MVP apanha o login sozinho.\n\n"
             "Entretanto podes jogar com contas offline.")

    def ms_guide(self):
        w = ctk.CTkToplevel(self)
        w.title("Ativar contas originais")
        w.geometry("660x500")
        w.configure(fg_color=BG)
        w.after(200, w.lift)
        t = ctk.CTkTextbox(w, fg_color=CARD, wrap="word", font=("Segoe UI", 13))
        t.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        t.insert("1.0", self.GUIDE)
        t.configure(state="disabled")
        row = ctk.CTkFrame(w, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(row, text="Abrir portal Azure", fg_color=ACCENT, hover_color=ACCENT_H,
                      command=lambda: webbrowser.open(AZURE_URL)).pack(side="left")
        ctk.CTkButton(row, text="Formulário da Mojang", fg_color=CARD2,
                      command=lambda: webbrowser.open(MOJANG_FORM)).pack(side="left", padx=8)

    def ms_login(self):
        self.save_settings()
        cid = self.cfg["ms_client_id"]
        if not cid:
            self.acc_msg.configure(text="Falta o Azure Client ID. Carrega em «Como ativar».", text_color=ERR)
            return
        self.acc_msg.configure(text="A abrir o browser… entra com a tua conta Microsoft.", text_color=MUTED)

        def work():
            try:
                url, state, verifier = mll.microsoft_account.get_secure_login_data(cid, REDIRECT)
                port = int(urlparse(REDIRECT).port or 8765)
                box = {}

                class H(BaseHTTPRequestHandler):
                    def do_GET(self):
                        q = parse_qs(urlparse(self.path).query)
                        box.update({k: v[0] for k, v in q.items()})
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write("<body style='background:#0A0C11;color:#fff;font-family:sans-serif;text-align:center;padding-top:80px'>"
                                         "<h1>MVP Client</h1><p>Sessão recebida. Podes fechar esta janela.</p></body>".encode("utf-8"))

                    def log_message(self, *a):
                        pass
                srv = HTTPServer(("127.0.0.1", port), H)
                srv.timeout = 240
                webbrowser.open(url)
                for _ in range(6):
                    srv.handle_request()
                    if "code" in box or "error" in box:
                        break
                srv.server_close()
                if "error" in box:
                    raise RuntimeError(box.get("error_description", box["error"]))
                if "code" not in box:
                    raise RuntimeError("tempo esgotado sem login")
                code = mll.microsoft_account.parse_auth_code_url(f"{REDIRECT}/?{urlencode(box)}", state)
                acc = mll.microsoft_account.complete_login(cid, None, REDIRECT, code, verifier)
                a = {"type": "microsoft", **{k: acc[k] for k in ("id", "name", "access_token", "refresh_token")}}
                accs = [x for x in self.cfg["accounts"] if x.get("id") != a["id"]]
                accs.append(a)
                self.cfg["accounts"] = accs
                self.cfg["active"] = len(accs) - 1
                self.save()
                self.ui(self.refresh_accounts)
                self.ui(lambda: self.acc_msg.configure(text=f"✔ Sessão iniciada como {a['name']}.", text_color=OK))
            except Exception as e:
                msg = str(e)
                if "Invalid app registration" in msg or "403" in msg:
                    msg += "  → o teu Client ID ainda não foi aprovado pela Mojang (ver «Como ativar»)."
                self.ui(lambda: self.acc_msg.configure(text=f"Login falhou: {msg}", text_color=ERR))
        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
