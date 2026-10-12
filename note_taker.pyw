import ctypes
import functools
import json
import math
import os
import random
import re
import struct
import time
import tkinter as tk
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

VAULT = Path(os.environ.get("VAULT", r"C:\Users\franh\OneDrive - Grupo Marista\OneDriveProjects"))
INBOX = VAULT / "00-Inbox"
# rótulo: (tipo, status inicial do template, campos extras)
TIPOS = {
    "Anotação": ("captura", "nova", ["projeto"]),
    "Task": ("task", "rascunho", ["projeto", "prazo"]),
    "Lembrete": ("lembrete", "ativo", ["prazo", "relacionado"]),
    "Estudo/Aula": ("aula", "rascunho", ["disciplina", "semestre"]),
    "Prova": ("prova", "agendada", ["disciplina", "semestre", "prazo"]),
    "Trabalho": ("trabalho", "a-fazer", ["disciplina", "semestre", "prazo", "projeto"]),
}


def pastas(p):
    return sorted(d.name for d in p.iterdir() if d.is_dir() and not d.name.startswith("_")) if p.is_dir() else []


# campo: (rótulo, sugestões ou None para campo livre)
CAMPOS = {
    "projeto": ("Projeto", pastas(VAULT / "40-Projetos")),
    "disciplina": ("Disciplina", pastas(VAULT / "35-Faculdade")),
    "semestre": ("Semestre", None),
    "prazo": ("Prazo (dd/mm/aaaa)", None),
    "relacionado": ("Relacionado", None),
}


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:50] or "nota"


def data(s):
    """Aceita dd/mm, dd/mm/aa, dd/mm/aaaa ou aaaa-mm-dd; devolve aaaa-mm-dd."""
    if s.count("/") == 1:
        s += f"/{datetime.now().year}"
    for f in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"Prazo inválido: {s}")


def valor(campo, v):
    if campo == "projeto":
        v = f"[[Projeto-{v}]]"
    elif campo == "disciplina":
        v = f"[[Disciplina-{v}]]"
    elif campo == "prazo":
        v = data(v)
    return json.dumps(v, ensure_ascii=False)  # string YAML segura (aspas, dois-pontos)


def salvar(rotulo, texto, extras):
    tipo, status, _ = TIPOS[rotulo]
    agora = datetime.now()
    titulo = texto.splitlines()[0].strip()[:80]
    linhas = "".join(f"{k}: {valor(k, v)}\n" for k, v in extras.items() if v)
    arq = INBOX / f"{agora:%Y-%m-%d-%H%M}-{slug(titulo)}.md"
    while arq.exists():
        arq = arq.with_stem(arq.stem + "-2")
    arq.write_text(
        f"---\ntipo: {tipo}\nstatus: {status}\nautor: fran\n"
        f"criado: {agora:%Y-%m-%d}\natualizado: {agora:%Y-%m-%d}\nhora: {agora:%H:%M}\n"
        f"tags: []\nfontes: []\n{linhas}---\n# {titulo}\n\n{texto}\n",
        encoding="utf-8")


def id_na_barra(janela, aumid):
    """Grava System.AppUserModel.ID na janela, igual ao do atalho (atalho.py). O Python da Store é app
    empacotado e ignora SetCurrentProcessExplicitAppUserModelID: sem isto a barra mostra o ícone do Python."""
    hwnd = ctypes.windll.user32.GetParent(janela.winfo_id())
    loja = ctypes.c_void_p()
    iid = uuid.UUID("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99").bytes_le  # IPropertyStore
    ctypes.windll.shell32.SHGetPropertyStoreForWindow(hwnd, iid, ctypes.byref(loja))
    vtbl = ctypes.cast(loja, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    set_value = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p)(vtbl[6])
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
    chave = uuid.UUID("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3").bytes_le + struct.pack("<I", 5)
    texto = ctypes.c_wchar_p(aumid)
    valor = struct.pack("<H6xQQ", 31, ctypes.cast(texto, ctypes.c_void_p).value, 0)  # PROPVARIANT VT_LPWSTR
    set_value(loja, chave, valor)
    release(loja)


# Cena em pixel art no estilo das praias de jogos 2D: céu em faixas pontilhadas, sol (ou lua) no horizonte com
# reflexo no mar, montanhas, palmeiras e pedras com luz de borda, nuvens e pássaros passando, um barquinho e
# ondas que sobem e descem na areia, deixando uma faixa molhada que seca aos poucos. Três fases: dia, pôr do
# sol (6h–8h e 17h–19h) e noite. A máquina de escrever fica numa mesinha na areia; a folha sai do rolo.
P = 3  # tamanho de cada "pixel" da cena, em pixels de tela (recalculado pela largura da janela)
Q = 6  # unidade das medidas da mesinha e da máquina, em pixels de tela
# areia: clara, base, grão, brilho | mar: longe, meio, perto | traco: claro, escuro, cor do céu
# montanha: longe, perto, borda | pedra: base, meio, borda, brilho | barco: casco, vela
# luz: cor e força que tingem a mesa e a máquina, para combinarem com a fase
PAPEL, CAMPO, TINTA, LARANJA, REALCE = "#FFF8E7", "#F7EBD0", "#2B1D14", "#E8743B", "#F2A541"
FASES = {
    "sol": dict(
        ceu=("#7E2448", "#A3304F", "#C93F55", "#E45A52", "#F27A4B", "#F99A4C", "#FCBA5C", "#FDD37A"),
        halo="#FFE3A3", astro=("#FFF6C8", "#FFD75E", "#FCA23F"), lua=False, alto=0, raio=.11,
        nuvem=("#FFD3B0", "#F5A68E", "#D9767C"), montanha=("#5A7A88", "#2F5468", "#E08A70"),
        mar=("#5C8E98", "#2F7A84", "#256673"), raso="#3E9A96", traco=("#6CB5AB", "#1B4C5A", "#F6A86A"),
        reflexo=("#FFF1A8", "#FFC85E", "#F58A4A"), espuma="#FFF3DC",
        areia=("#EDB878", "#D99A5E", "#B97A47", "#FFD08A"), molhada=("#BE7F55", "#A36A48"),
        folha=("#142235", "#22364E"), tronco=("#152438", "#E3836A"),
        pedra=("#231F3A", "#3A2A4E", "#D9675A", "#F7A27A"), barco=("#142235", "#142235"), passaro="#4A1F38",
        mesa=("#9A6A4A", "#7A5038", "#4E3426"), luz=("#FF8A50", .08), papel="#FFF0DA", relogio="#FFF2DC", sombra="#8E2A4A"),
    "dia": dict(
        ceu=("#2B6FD0", "#3483DE", "#4596E8", "#5AABEF", "#74BFF3", "#93D2F6", "#B4E2F8", "#D4F0FA"),
        halo="#FFFBE0", astro=("#FFFFF4", "#FFF6B8", "#FFE680"), lua=False, alto=.6, raio=.065,
        nuvem=("#FFFFFF", "#E8F3FC", "#BCD6EC"), montanha=("#8DB3CE", "#5F8FB0", "#C4DDEC"),
        mar=("#7CC3E8", "#2F8FD2", "#1F74BC"), raso="#46C6D2", traco=("#A8E0F7", "#18609E", "#D4F0FA"),
        reflexo=("#FFFFFF", "#E3F7FF", "#B5E3FA"), espuma="#FFFFFF",
        areia=("#F8E2A6", "#EFCF8C", "#DDB673", "#FFF4D0"), molhada=("#D2AE70", "#BE985E"),
        folha=("#2C8A3C", "#5BBE52"), tronco=("#7A5230", "#B5854F"),
        pedra=("#5E5A66", "#7A7682", "#A9A4B0", "#D6D2DA"), barco=("#7A3B2A", "#FFFFFF"), passaro="#2B3A4A",
        mesa=("#B98552", "#8A5A2B", "#6B4423"), luz=("#FFFFFF", 0), papel=PAPEL, relogio="#FFFFFF", sombra="#1F4F80"),
    "noite": dict(
        ceu=("#04071A", "#070C26", "#0C1232", "#121A40", "#19224E", "#222C5C", "#2D376A", "#3A4478"),
        halo="#3C4785", astro=("#FFFDEB", "#F2EECB", "#CFCBA6"), lua=True, alto=.62, raio=.055,
        nuvem=("#3A4478", "#2B3466", "#1C2350"), montanha=("#1C2450", "#121A3C", "#2E3A70"),
        mar=("#26306A", "#17235A", "#101A48"), raso="#22407A", traco=("#3A4C92", "#0A1236", "#4A5590"),
        reflexo=("#FFFDEB", "#D4D6F2", "#8E95C8"), espuma="#B8C2EE",
        areia=("#5E5A76", "#524E6A", "#46425C", "#77739A"), molhada=("#3E3B58", "#34314C"),
        folha=("#070B1E", "#111836"), tronco=("#070B1E", "#2C3772"),
        pedra=("#0A0E22", "#151B38", "#2E3870", "#4A56A0"), barco=("#070B1E", "#070B1E"), passaro=None,
        mesa=("#7A6A75", "#5A4A55", "#3A2D36"), luz=("#141C48", .4), papel="#ECEAF4", relogio="#F4F1D0", sombra="#000000"),
}
MAQUINA, MAQUINA_LUZ, TECLA, TECLA_SOMBRA, ROLO = "#2F4858", "#4A6B7C", "#EDE6D3", "#1C2C36", "#1A1A1A"
PASSARO = (["x...x", ".x.x.", "..x.."], [".....", "xx.xx", "..x.."])  # asas para cima e para baixo
BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
DIGITOS = {  # fonte 3x5
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
    "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001001001001",
    "8": "111101111101111", "9": "111101111001111", ":": "000010000010000",
}
FONTE = "Courier New"

root = tk.Tk()
root.title("Nota rápida")
root.iconbitmap(default=Path(__file__).with_name("manga.ico"))
root.update_idletasks()
id_na_barra(root, "Fran.NotaRapida")
L, A = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry(f"{int(L * .8)}x{int(A * .8)}+{int(L * .1)}+{int(A * .06)}")
root.minsize(760, 560)

estilo = ttk.Style()
estilo.theme_use("clam")  # o tema nativo do Windows ignora cores de campo
for w in ("TEntry", "TCombobox"):
    estilo.configure(w, fieldbackground=CAMPO, background=REALCE, bordercolor="#D8C8A8",
                     lightcolor=CAMPO, darkcolor=CAMPO, arrowcolor=TINTA, foreground=TINTA, padding=2)
estilo.map("TCombobox", fieldbackground=[("readonly", CAMPO)])

fundo = tk.Canvas(root, highlightthickness=0, bg="black")
fundo.pack(fill="both", expand=True)

# Folha: cabeçalho, tipos (abas pequenas), campos extras e o texto.
papel = tk.Frame(fundo, bg=PAPEL, padx=16, pady=10, highlightthickness=3, highlightbackground="#D8C8A8")
folha_id = fundo.create_window(0, 0, window=papel, anchor="nw")
cab = tk.Frame(papel, bg=PAPEL)
cab.pack(fill="x")
icone = tk.PhotoImage(file=Path(__file__).with_name("manga.png"))
icone_mini = icone.subsample(3)
tk.Label(cab, image=icone_mini, bg=PAPEL).pack(side="left")
tk.Label(cab, text="nota rápida", font=(FONTE, 12, "bold"), fg=TINTA, bg=PAPEL).pack(side="left", padx=6)

tipo = tk.StringVar(value=next(iter(TIPOS)))
abas = tk.Frame(papel, bg=PAPEL)
abas.pack(fill="x", pady=(6, 0))
for r in TIPOS:
    tk.Radiobutton(abas, text=r, value=r, variable=tipo, command=lambda: trocar_tipo(), indicatoron=False,
                   font=(FONTE, 8, "bold"), fg=TINTA, bg=PAPEL, selectcolor=REALCE, activebackground=CAMPO,
                   relief="flat", offrelief="flat", bd=0, padx=5, pady=2, cursor="hand2").pack(side="left", padx=(0, 2))

quadro = tk.Frame(papel, bg=PAPEL)
quadro.pack(fill="x", pady=(6, 0))
quadro.columnconfigure(1, weight=1)
widgets = {}
for i, (campo, (rotulo, sugestoes)) in enumerate(CAMPOS.items()):
    lbl = tk.Label(quadro, text=rotulo, font=(FONTE, 9), fg=TINTA, bg=PAPEL)
    ent = (ttk.Combobox(quadro, values=sugestoes, font=(FONTE, 10)) if sugestoes is not None
           else ttk.Entry(quadro, font=(FONTE, 10)))
    lbl.grid(row=i, column=0, sticky="w", pady=1)
    ent.grid(row=i, column=1, sticky="ew", padx=(8, 0), pady=1)
    widgets[campo] = (lbl, ent)


def trocar_tipo():
    visiveis = TIPOS[tipo.get()][2]
    for campo, (lbl, ent) in widgets.items():
        for w in (lbl, ent):
            w.grid() if campo in visiveis else w.grid_remove()


trocar_tipo()

texto = tk.Text(papel, wrap="word", font=(FONTE, 11), undo=True, bg=PAPEL, fg=TINTA, insertbackground=TINTA,
                insertwidth=2, selectbackground=REALCE, selectforeground=TINTA, relief="flat", bd=0,
                highlightthickness=0, padx=4, pady=4, spacing1=2, spacing3=2)
texto.pack(fill="both", expand=True, pady=(6, 0))


def enviar(_=None):
    t = texto.get("1.0", "end").strip()
    if not t:
        return "break"
    extras = {c: widgets[c][1].get().strip() for c in TIPOS[tipo.get()][2]}
    try:
        salvar(tipo.get(), t, extras)
    except (OSError, ValueError) as e:
        messagebox.showerror("Erro ao salvar", str(e))  # texto fica no campo, nada se perde
        return "break"
    texto.delete("1.0", "end")
    for _, ent in widgets.values():
        ent.delete(0, "end")
    minimizar()
    return "break"


texto.bind("<Control-Return>", enviar)
borda = tk.Frame(fundo, bg=TECLA_SOMBRA, padx=3, pady=3)  # botão na frente da máquina
tk.Button(borda, text="ENVIAR · Ctrl+Enter", command=enviar, font=(FONTE, 10, "bold"), fg="white", bg=LARANJA,
          activebackground="#C85A26", activeforeground="white", relief="flat", bd=0, padx=16, pady=3,
          cursor="hand2").pack()
botao_id = fundo.create_window(0, 0, window=borda)


def fase_atual():
    f = os.environ.get("NOTA_FASE")  # força uma fase (sol, dia, noite) para testar sem esperar o horário
    if f in FASES:
        return f
    h = datetime.now().hour
    return "dia" if 8 <= h < 17 else "sol" if 6 <= h < 19 else "noite"


@functools.lru_cache(maxsize=None)
def mistura(c1, c2, k):
    a, b = ([int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in (c1, c2))
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * k) for x, y in zip(a, b))


def faixa(cores, f, x, y):
    """Degradê em faixas: cada faixa é lisa e só a passagem para a próxima é pontilhada (Bayer 4x4)."""
    i = max(0, min(int(f), len(cores) - 2))
    return cores[i + 1] if (f - i - .5) * 32 > BAYER[y % 4][x % 4] + .5 else cores[i]


def ruido(*v):
    """Número pseudoaleatório em [0, 1), sempre o mesmo para os mesmos inteiros."""
    h = 2166136261
    for n in v:
        h = ((h ^ (n & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    return ((h ^ h >> 15) & 0xFFFF) / 65536


def imagem(linhas):
    img = tk.PhotoImage(width=len(linhas[0]), height=len(linhas))
    img.put(" ".join("{" + " ".join(l) + "}" for l in linhas))
    return img.zoom(P)


def sprite(px):
    """Imagem transparente com os pixels de px ({(x, y): cor}); devolve (imagem ampliada, x0, y0)."""
    x0, y0 = min(x for x, _ in px), min(y for _, y in px)
    img = tk.PhotoImage(width=max(x for x, _ in px) - x0 + 1, height=max(y for _, y in px) - y0 + 1)
    filas = {}
    for (x, y), cor in px.items():
        filas.setdefault(y, {})[x] = cor
    for y, fila in filas.items():  # só os trechos pintados; o resto da imagem fica transparente
        xs = sorted(fila)
        ini = xs[0]
        for a, b in zip(xs, xs[1:] + [None]):
            if b != a + 1:
                img.put("{" + " ".join(fila[i] for i in range(ini, a + 1)) + "}", to=(ini - x0, y - y0))
                ini = b
    return img.zoom(P), x0, y0


def desenho(linhas, cores):
    return {(i, j): cores[ch] for j, fila in enumerate(linhas) for i, ch in enumerate(fila) if ch in cores}


def ampliar(px, k):
    """Cada pixel vira um bloco k x k (para os desenhos pequenos em texto, como os pássaros)."""
    return {(x * k + i, y * k + j): cor for (x, y), cor in px.items() for i in range(k) for j in range(k)}


def disco(px, cx, cy, r, cor):
    for y in range(math.floor(cy - r), math.ceil(cy + r) + 1):
        for x in range(math.floor(cx - r), math.ceil(cx + r) + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                px[x, y] = cor


def palmeira(px, bx, by, alt, incl, c, luz, rnd):
    """Tronco curvo com anéis e borda iluminada; folhas em arco caído com folíolos pendurados (luz = lado do sol)."""
    tronco, borda = c["tronco"]
    tx, ty = bx + incl * alt, by - alt
    cx, cy = bx + incl * alt * .1, by - alt * .55
    anel = max(2, round(3 * E))
    n = int(alt * 2)
    for i in range(n + 1):
        s = i / n
        x = (1 - s) ** 2 * bx + 2 * (1 - s) * s * cx + s * s * tx
        y = round((1 - s) ** 2 * by + 2 * (1 - s) * s * cy + s * s * ty)
        larg = (4.4 - 2.2 * s + (2 if s < .03 else 0)) * E
        x1, x2 = round(x - larg / 2), round(x + larg / 2)
        for xi in range(x1, x2):
            k = (xi - x1 + .5) / (x2 - x1)
            sol = k if luz > 0 else 1 - k  # 1 = do lado do sol
            px[xi, y] = tronco if y % anel == 0 else borda if sol > .74 or sol > .5 and (xi + y) % 2 else tronco
    folhas = set()
    for a in (-2.2, -1.75, -1.3, -.85, -.4, -.05, .35, .8, 1.25, 1.7, 2.15):
        a += rnd.uniform(-.1, .1)
        L = alt * rnd.uniform(.3, .37) * (.75 if abs(a) < .3 else 1)
        caida = rnd.uniform(.35, .55)  # as de cima sobem em arco; as do lado pendem na ponta
        passos = int(L * 3)
        for i in range(1, passos + 1):
            s = i / passos
            x = tx + math.sin(a) * L * s
            y = ty - math.cos(a) * L * s + caida * L * s * s
            for k in range(1 + (round(E) if s < .6 else 0)):  # talo mais grosso perto do tronco
                folhas.add((round(x), round(y) + k))
            if s < .1 or i % max(1, round(2.5 * E)):  # um folíolo a cada ~2 pixels: franja, não borrão
                continue
            # folíolos saem do talo na perpendicular, puxados para a ponta e para baixo
            dx, dy = math.sin(a), -math.cos(a) + 2 * caida * s
            k = math.hypot(dx, dy)
            dx, dy = dx / k, dy / k
            nx, ny = (-dy, dx) if dx >= 0 else (dy, -dx)  # normal do lado de baixo
            largura = math.sin(math.pi * min(1, s * 1.05)) * rnd.uniform(.6, 1)
            for sentido, comp in ((1, (1 + 5 * largura) * E), (-1, 2.2 * largura * E)):
                vx, vy = sentido * nx + dx * .6, sentido * ny + dy * .6 + (.5 if sentido > 0 else 0)
                k = math.hypot(vx, vy)
                for d in range(1, int(comp) + 1):
                    folhas.add((round(x + vx / k * d), round(y + vy / k * d)))
    esc, clara = c["folha"]
    meio = mistura(esc, clara, .5)
    for x, y in folhas:
        if (x, y - 1) not in folhas or (x + luz, y) not in folhas and (x + y) % 2:
            px[x, y] = clara
        else:
            px[x, y] = meio if (x, y - 2) not in folhas or (x + 2 * luz, y) not in folhas else esc
    for dx, dy in ((-1.6, 1.8), (1.6, 1.8), (0, 3)):  # cocos
        disco(px, tx + dx * E, ty + dy * E, 1.3 * E, tronco)
        px[round(tx + (dx + .5 * luz) * E), round(ty + (dy - .6) * E)] = borda


def pedras(px, cx, base, larg, alt, c, luz, rnd):
    """Elipses sobrepostas com o chão reto, borda iluminada no topo e do lado do sol, e algumas rachaduras."""
    escura, meio, borda, brilho = c["pedra"]
    e = max(1, round(E))
    m = set()
    for _ in range(max(2, int(larg / (4 * E)))):
        ex, rx, ry = cx + rnd.uniform(-.4, .4) * larg, rnd.uniform(.18, .32) * larg, rnd.uniform(.45, 1) * alt
        for y in range(int(base - ry), base + 1):
            for x in range(int(ex - rx), int(ex + rx) + 2):
                if ((x - ex) / rx) ** 2 + ((y - base) / ry) ** 2 <= 1:
                    m.add((x, y))
    for x, y in m:
        topo = next((k for k in range(1, 2 * e + 1) if (x, y - k) not in m), 0)
        if topo and topo <= e:
            cor = brilho if ruido(x // e, y // e) < .6 else borda
        elif topo or (x + luz * e, y) not in m and y < base - e:
            cor = borda
        elif (x - luz * 2 * e, y) not in m:
            cor = escura  # lado da sombra
        else:
            cor = meio if (x + y) % 2 and ruido(x // e, y // e, 5) < .45 else escura
        px[x, y] = cor
    for _ in range(len(m) // (45 * e * e)):  # rachaduras descendo na diagonal
        x, y = rnd.choice(sorted(m))
        for _ in range(rnd.randint(2, 4) * e):
            if (x, y - 1) in m and (x, y + 1) in m:
                px[x, y] = borda
            x, y = x - luz, y + 1


def nuvem(rnd, c):
    """Nuvem de base reta e topo em degraus: topo claro, miolo e uma faixa de sombra embaixo."""
    e = max(1, round(E))
    larg, alt = int(rnd.randint(14, 30) * E), int(rnd.randint(4, 7) * E)
    m = set()
    for _ in range(int(larg / (4 * E)) + 2):
        bx, r = rnd.uniform(.15, .85) * larg, rnd.uniform(.4, .9) * alt
        for y in range(-int(r) - 1, 1):
            for x in range(int(bx - r * 1.7) - 1, int(bx + r * 1.7) + 2):
                if ((x - bx) / (r * 1.7)) ** 2 + (y / r) ** 2 <= 1:
                    m.add((x, y))
    clara, miolo, sombra = c["nuvem"]
    px = {}
    for x, y in m:
        if any((x, y - k) not in m for k in range(1, e + 1)) or (x, y - 2 * e) not in m and (x + y) % 2:
            px[x, y] = clara
        elif any((x, y + k) not in m for k in range(1, e + 1)) or (x, y + 2 * e) not in m and (x + y) % 2:
            px[x, y] = sombra
        else:
            px[x, y] = miolo
    return px


def barco(c):
    """Veleiro: mastro, vela grande, bujarrona um tom mais escura e casco afinando no fundo."""
    casco, vela = c["barco"]
    sombra = mistura(vela, casco, .25)
    px, mx, topo = {}, round(4 * E), round(10 * E)
    for y in range(topo):
        for x in range(mx + 1, mx + 1 + int(y / topo * 6 * E)):
            px[x, y] = vela
        if y > 2 * E:
            for x in range(mx - int((y - 2 * E) / (topo - 2 * E) * 3.5 * E), mx):
                px[x, y] = sombra
        for x in range(mx, mx + max(1, round(E * .6))):
            px[x, y] = casco
    for j in range(round(2.5 * E)):
        for x in range(round(-E + j * .8), round(11 * E - j * .8)):
            px[x, topo + j] = casco
    return px


def mesa_e_maquina(px, w, h, c, luz):
    """Mesinha e máquina de escrever na mesma grade da cena, com sombreado e a luz da fase.
    As medidas são em pixels de tela (múltiplos de Q) e viram pixels da cena aqui."""
    def tom(cor):
        return mistura(cor, c["luz"][0], c["luz"][1])

    def ret(x1, y1, x2, y2, cor):
        for y in range(y1, y2):
            for x in range(x1, x2):
                px[x, y] = cor
    e = max(1, round(E))
    tampo, frente, perna = (tom(k) for k in c["mesa"])
    corpo, corpo_luz, corpo_sombra = tom(MAQUINA), tom(MAQUINA_LUZ), tom(mistura(MAQUINA, "#000000", .3))
    tecla, tecla_sombra, rolo = tom(TECLA), tom(TECLA_SOMBRA), tom(ROLO)
    my = (h - 130) // Q * Q
    mx1, mx2, bx1, bx2 = ((w // 2 + d) // Q * Q for d in (-330, 330, -270, 270))
    by = my - 16 * Q
    ry = by - 3 * Q
    S = lambda v: v // P  # noqa: E731
    papel_x1, papel_x2 = S(w // 2 - 240), S(w // 2 + 240)
    papel_y1 = S(ry + Q - min(340, ry - 64))
    H = -(-h // P)

    # mesa: tampo visto de cima, frente com veios, pernas com borda de luz
    X1, X2, Y, T = S(mx1), S(mx2), S(my), S(2 * Q)
    ret(X1, Y, X2, Y + T, tampo)
    ret(X1, Y, X2, Y + e, mistura(tampo, "#FFFFFF", .2))
    ret(X1, Y + T, X2, Y + 2 * T, frente)
    ret(X1, Y + 2 * T - e, X2, Y + 2 * T, perna)
    for x in range(X1, X2):
        if ruido(x // (3 * e), 21) < .35:
            px[x, Y + T + T // 2] = perna
    for x in (S(mx1 + 3 * Q), S(mx2 - 6 * Q)):
        L = S(3 * Q)
        ret(x, Y + 2 * T, x + L, H, perna)
        ret(x + (L - e if luz > 0 else 0), Y + 2 * T, x + (L if luz > 0 else e), H, frente)
    ret(S(bx1) - 5 * e if luz > 0 else S(bx1), Y, S(bx2) if luz > 0 else S(bx2) + 5 * e, Y + T,
        mistura(tampo, "#000000", .3))  # sombra da máquina no tampo, do lado oposto ao sol

    # sombra pontilhada da folha sobre a cena, do lado oposto ao sol
    d, sombra = 3 * e, tom("#1A1424")
    for y in range(papel_y1 + d, S(ry)):
        for x in range(papel_x1 - d * luz, papel_x2 - d * luz):
            if x % 2 and y % 2 and not papel_x1 <= x < papel_x2:
                px[x, y] = sombra
    for y in range(S(ry), S(ry) + d):
        for x in range(papel_x1 - d * luz, papel_x2 - d * luz):
            if x % 2 and y % 2:
                px[x, y] = sombra

    # corpo da máquina com cantos arredondados, luz em cima e do lado do sol
    X1, X2, Y1, Y2 = S(bx1), S(bx2), S(by), S(my)
    r = 2 * e
    for y in range(Y1, Y2):
        for x in range(X1, X2):
            dx, dy = max(X1 + r - x, x - (X2 - 1 - r), 0), max(Y1 + r - y, 0)
            if dx * dx + dy * dy > r * r:
                continue
            sol = (x - X1) / (X2 - X1) if luz > 0 else (X2 - x) / (X2 - X1)
            if y < Y1 + e or sol > .985:
                px[x, y] = corpo_luz
            elif y >= Y2 - e or sol < .015:
                px[x, y] = corpo_sombra
            else:
                px[x, y] = corpo
    ret(X1 + 2 * e, Y1 + 2 * e, X2 - 2 * e, Y1 + 3 * e, corpo_sombra)  # friso
    for fila in range(2):  # teclas redondas com brilho e sombra
        yk = S(by + 4 * Q + fila * 3 * Q)
        for xs in range(bx1 + (5 + fila) * Q, bx2 - 6 * Q, 4 * Q):
            k = S(2 * Q)
            cx, cy = S(xs) + k / 2 - .5, yk + k / 2 - .5
            disco(px, cx, cy + 1, k / 2 + .3, corpo_sombra)
            disco(px, cx, cy, k / 2 + .3, tecla_sombra)
            disco(px, cx, cy - .3, k / 2 - .3, tecla)
            px[round(cx - k / 5), round(cy - k / 4)] = "#FFFFFF"
    # rolo: cilindro com faixa de brilho; botões redondos nas pontas
    X1, X2, Y1, Y2 = S(bx1 + 4 * Q), S(bx2 - 4 * Q), S(ry), S(by)
    for y in range(Y1, Y2):
        v = (y - Y1) / max(1, Y2 - Y1 - 1)
        cor = mistura(rolo, "#9A9A9A", .55) if .2 < v < .45 else mistura(rolo, "#9A9A9A", .2) if v < .65 else rolo
        ret(X1, y, X2, y + 1, cor)
    for xa, xb in ((bx1 + Q, bx1 + 4 * Q), (bx2 - 4 * Q, bx2 - Q)):
        cx, cy, rr = (S(xa) + S(xb)) / 2, (S(ry - Q) + S(by + Q)) / 2, (S(xb) - S(xa)) / 2
        disco(px, cx, cy, rr, rolo)
        disco(px, cx + .3 * rr * luz, cy - .3 * rr, rr * .45, mistura(rolo, "#9A9A9A", .45))
    return by, ry


def tingir_papel(w, cor):
    """Pinta o fundo da folha e de tudo dentro dela com a cor do papel da fase (mais quente no pôr do sol,
    mais azulado à noite), para a folha parecer iluminada pela mesma luz da cena."""
    if isinstance(w, (tk.Frame, tk.Label, tk.Radiobutton, tk.Text)):
        w.configure(bg=cor)
        if isinstance(w, tk.Text):
            w.configure(insertbackground=TINTA)
    for filho in w.winfo_children():
        tingir_papel(filho, cor)


cena, pendente = {}, {}
E = 1  # escala dos detalhes: 1 para uma cena de 256 pixels de largura


def montar():
    """Recria a cena para o tamanho e a fase atuais. O mar e a beira da praia são redesenhados em quadro()."""
    global P, E
    w, h = fundo.winfo_width(), fundo.winfo_height()
    if w < 100 or h < 100:
        return
    nome = fase_atual()
    c = FASES[nome]
    P = max(2, round(w / 512))
    W, H = -(-w // P), -(-h // P)
    E = W / 256
    e = max(1, round(E))
    hz, praia = int(H * .42), int(H * .62)  # horizonte e linha da água parada, em pixels da cena
    A = max(6, int(H * .09))  # até onde a onda sobe na areia
    fim = min(H, praia + A + 3 * e)
    rnd = random.Random(W * 1000 + H)  # mesma cena enquanto o tamanho não muda
    r = max(4, round(H * c["raio"]))
    sx, sy = int(W * .74), round(hz * (1 - c["alto"]) - r * .55)

    tela = [[None] * W for _ in range(H)]
    ceu, n = c["ceu"], len(c["ceu"]) - 1
    for y in range(hz):
        f = y / (hz - 1) * n
        for x in range(W):
            cor = faixa(ceu, f, x, y)
            d = math.hypot(x - sx, y - sy)
            if d > r or c["lua"] and (x - sx + r * .5) ** 2 + (y - sy + r * .3) ** 2 <= (r * .9) ** 2:
                if d < r * 2.6:  # halo em anéis pontilhados
                    nivel = int((1 - (d - r) / (r * 1.6)) * 4 + BAYER[y % 4][x % 4] / 16)
                    cor = mistura(cor, c["halo"], .12 * min(nivel, 4)) if nivel > 0 else cor
            elif c["lua"]:
                cra = ruido(int(x / (2 * E)), int(y / (2 * E)), 9) < .16
                cor = c["astro"][2] if cra else c["astro"][0] if d > r - 1.3 * E else c["astro"][1]
            elif nome == "sol" and y > sy and int((y - sy) / E) % (3 if y - sy < r * .35 else 2) == 0:
                cor = mistura(cor, c["halo"], .45)  # faixas recortadas na parte de baixo do sol
            else:
                cor = faixa(c["astro"], (y - sy + r) / r, x, y)
            tela[y][x] = cor

    def serra(a, b, pico, alt, cor, borda):
        topos = []
        for x in range(max(0, int(a * W)), min(W, int(b * W) + 1)):
            u = (x / W - a) / (b - a)
            env = max(0, u / pico if u < pico else (1 - u) / (1 - pico))
            ondula = (.8 + .1 * math.sin(x * .31 / E + a * 9) + .07 * math.sin(x * .77 / E + b * 5)
                      + .03 * math.sin(x * 2.1 / E))
            topos.append((x, hz - max(0, round(alt * H * env ** .85 * ondula))))
        nevoa = mistura(cor, ceu[-1], .35)  # mais clara perto do horizonte, como se fosse névoa
        for (x, topo), (_, prox) in zip(topos, topos[1:] + topos[-1:]):
            encosta_sol = prox < topo if sx > x else prox > topo  # encosta virada para o sol
            for y in range(topo, hz):
                k = (y - topo) / max(1, hz - topo)
                if borda and y < topo + e and ruido(x // e, 3) < .7:
                    tela[y][x] = borda
                elif encosta_sol and k < .35 and (x + y) % 2:
                    tela[y][x] = mistura(cor, c["halo"], .18)
                else:
                    tela[y][x] = faixa((cor, nevoa), k * 1.6, x, y)
    m = c["montanha"]
    serra(-.02, .42, .38, .17, m[0], None)
    serra(.84, 1.04, .75, .15, m[0], None)
    serra(0, .28, .3, .09, m[1], m[2])
    serra(.91, 1.04, .7, .08, m[1], m[2])

    mar, tracos, reflexo = [], [], []
    for y in range(hz, praia):
        d = (y - hz) / max(1, praia - hz - 1)
        if y < hz + e:
            linha = [mistura(c["mar"][0], ceu[-1], .5)] * W  # linha clara do horizonte
        else:
            linha = [faixa(c["mar"], d ** 1.2 * 2.2, x, y) for x in range(W)]
            if y >= praia - 4 * E:
                linha = [faixa((cor, c["raso"]), (y - praia + 4 * E) / (3 * E), x, y) for x, cor in enumerate(linha)]
        mar.append(linha)
        tela[y] = linha[:]
        lst = []  # traços do mar: deslizam devagar e piscam
        for _ in range(int(W * (.03 + .07 * d))):
            comp = round((1 + d * 3 + rnd.random() * (1 + d * 3)) * E)
            cor = c["traco"][2] if d < .25 and rnd.random() < .6 else c["traco"][0 if rnd.random() < .6 else 1]
            lst.append((rnd.uniform(0, W), comp, cor, rnd.uniform(.3, 1.2) * E * (1 if y // e % 2 else -1),
                        rnd.uniform(0, 6.3)))
        tracos.append(lst)
        hw = r * (.5 + 1.1 * d)  # coluna de reflexo do sol/lua, mais larga perto de quem olha
        segs = []
        for _ in range(max(2, int(hw * (1.8 if y - hz < 2 * E else .8) / E))):
            dx = rnd.uniform(-1, 1)
            segs.append((dx, round((2 + rnd.random() * (2 + d * 5)) * E),
                         0 if abs(dx) < .3 else 1 if abs(dx) < .65 else 2, rnd.uniform(0, 6.3)))
        reflexo.append((hw, segs))

    areia = c["areia"]
    for y in range(praia, H):
        f = (y - praia) / max(1, H - praia - 1) * 1.6
        for x in range(W):
            g = ruido(x, y, 11)
            tela[y][x] = areia[2] if g < .05 else areia[3] if g < .065 else faixa(areia[:2], f, x, y)
    for _ in range(int(W * (H - praia) / (80 * E * E))):  # marcas de vento
        y, x, cor = rnd.randrange(praia + 2 * e, H), rnd.randrange(W), areia[2] if rnd.random() < .6 else areia[3]
        for k in range(round(rnd.randint(2, 5) * E)):
            tela[y][min(x + k, W - 1)] = cor

    frente = {}
    palmeira(frente, W * .07, int(H * .95), H * .66, .22, c, 1, rnd)
    palmeira(frente, W * .965, int(H * .93), H * .6, -.15, c, -1, rnd)
    pedras(frente, W * .1, H - 1, W * .12, H * .1, c, 1, rnd)
    pedras(frente, W * .93, H - 1, W * .1, H * .09, c, -1, rnd)
    pedras(frente, W * .22, praia + 5 * e, W * .035, H * .035, c, 1, rnd)
    pedras(frente, W * .845, praia + 3 * e, W * .03, H * .03, c, -1, rnd)
    by, ry = mesa_e_maquina(frente, w, h, c, 1)
    frente = {(x, y): cor for (x, y), cor in frente.items() if 0 <= x < W and 0 <= y < H}

    a1, a2 = rnd.uniform(0, 6.3), rnd.uniform(0, 6.3)
    escuro = nome != "dia"
    cena.clear()
    cena.update(
        c=c, nome=nome, W=W, hz=hz, praia=praia, fim=fim, A=A, sx=sx, B=max(3, (praia - hz) * .35),
        mar=mar, tracos=tracos, reflexo=reflexo, areia=[tela[y][:] for y in range(praia, fim)],
        umida=[[c["molhada"][1] if cor == areia[2] else c["molhada"][0] for cor in tela[y]] for y in range(praia, fim)],
        lamina=(mistura(c["raso"], areia[1], .5), mistura(c["raso"], areia[1], .2)),
        espuma2=mistura(c["espuma"], c["raso"], .45), molhado=[praia + .6 * E] * W,
        fase=[.07 * math.sin(x * .045 / E + a1) + .035 * math.sin(x * .13 / E + a2) + .015 * math.sin(x * .37 / E)
              for x in range(W)],
        amp=[.85 + .15 * math.sin(x * .05 / E + a2) for x in range(W)], hw_areia=r * 1.8,
        limiar=(-.5, 0, .4) if escuro else (.3, .6, .8), t=time.monotonic(), estrelas=[], nuvens=[], passaros=[])

    fundo.delete("cena")
    cena["base"] = imagem(tela)
    fundo.create_image(0, 0, image=cena["base"], anchor="nw", tags="cena")
    if nome == "noite":
        ceus = set(ceu)
        for _ in range(int(W * hz / (90 * E * E))):
            x, y = rnd.randrange(W), rnd.randrange(hz - 4 * e)
            if tela[y][x] in ceus:  # não desenha sobre a lua, o halo ou as montanhas
                t = e if rnd.random() < .25 else 1
                fundo.create_rectangle(x * P, y * P, (x + t) * P, (y + t) * P, fill="white", width=0, tags="cena")
                cena["estrelas"].append(fundo.find_all()[-1])
    for _ in range(3 if nome == "noite" else 5):
        img, _, _ = sprite(nuvem(rnd, c))
        x, y = rnd.uniform(-20 * E, W), rnd.uniform(2 * E, hz * .5)
        cena["nuvens"].append(dict(img=img, x=x, y=y, v=rnd.uniform(.25, .8) * E, larg=img.width() // P,
                                   id=fundo.create_image(round(x) * P, round(y) * P, image=img, anchor="nw", tags="cena")))
    if c["passaro"]:
        cena["asas"] = [sprite(ampliar(desenho(f, {"x": c["passaro"]}), e)) for f in PASSARO]
        cena["bando"] = dict(x=W * .6, y=hz * .45)
        for dx, dy in ((0, 0), (7, 2), (13, -1)):
            cena["passaros"].append((dx * E, dy * E, fundo.create_image(0, 0, anchor="nw", tags="cena")))
    cena["mar_id"] = fundo.create_image(0, hz * P, anchor="nw", tags="cena")
    cena["barco_img"], _, _ = sprite(barco(c))
    cena["barco"] = (int(W * .29), int(hz + (praia - hz) * .3 - 12 * E))
    cena["barco_id"] = fundo.create_image(0, 0, image=cena["barco_img"], anchor="nw", tags="cena")
    cena["frente"], _, _ = sprite(frente)
    x0, y0 = min(x for x, _ in frente), min(y for _, y in frente)
    fundo.create_image(x0 * P, y0 * P, image=cena["frente"], anchor="nw", tags="cena")

    fundo.coords(botao_id, w // 2, by + 13 * Q)
    tingir_papel(papel, c["papel"])
    alt, larg = min(340, ry - 64), 480  # folha saindo do rolo
    fundo.coords(folha_id, w // 2 - larg // 2, ry + Q - alt)
    fundo.itemconfig(folha_id, width=larg, height=alt)
    relogio()
    quadro(cena["t"], 0)


def relogio():
    """Horário em dígitos de pixel, sem fundo, centralizado no topo."""
    fundo.delete("relogio")
    s, q = datetime.now().strftime("%H:%M"), 4
    cena["min"] = s
    x0 = (fundo.winfo_width() - (len(s) * 4 - 1) * q) // 2
    for d, cor in ((q, cena["c"]["sombra"]), (0, cena["c"]["relogio"])):  # sombra primeiro, dígito por cima
        for k, ch in enumerate(s):
            for i, bit in enumerate(DIGITOS[ch]):
                if bit == "1":
                    X, Y = x0 + (k * 4 + i % 3) * q + d, 18 + i // 3 * q + d
                    fundo.create_rectangle(X, Y, X + q, Y + q, fill=cor, width=0, tags="relogio")


def quadro(t, dt):
    """Desenha o mar e a beira da praia no instante t. Cada coluna tem a sua fase, então a frente da água sai
    ondulada: a onda quebra, sobe rápido com espuma, perde força, desce devagar deixando a espuma em renda e a
    areia molhada, que vai secando até a próxima."""
    s, c = cena, cena["c"]
    W, hz, praia, fim, sx = s["W"], s["hz"], s["praia"], s["fim"], s["sx"]
    e = max(1, round(E))
    linhas = []
    for j, base in enumerate(s["mar"]):
        linha = base[:]
        for x0, comp, cor, vel, fase in s["tracos"][j]:
            if math.sin(t * 1.1 + fase) > -.4:
                xi = int(x0 + t * vel)
                for k in range(comp):
                    linha[(xi + k) % W] = cor
        hw, segs = s["reflexo"][j]
        ond = math.sin(t * 1.6 + j * .9 / E) * .8 * E
        for dx, comp, nivel, fase in segs:
            if math.sin(t * 2.7 + fase) > s["limiar"][nivel]:
                xi = round(sx + dx * hw + ond)
                for k in range(max(0, xi), min(W, xi + comp)):
                    linha[k] = c["reflexo"][nivel]
        linhas.append(linha)
    linhas += [l[:] for l in s["areia"]]
    espuma, espuma2, lamina, umida = c["espuma"], s["espuma2"], s["lamina"], s["umida"]
    molhado, brilho, reflexo = s["molhado"], int(t * 4), c["reflexo"]
    for x in range(W):
        q = t / 7.5 + s["fase"][x]
        n = math.floor(q)
        p = q - n
        amp = s["A"] * s["amp"][x] * (.55 + .45 * ruido(n, 7))  # cada onda chega com uma força
        if p < .28:
            subindo, u, alc = True, 0, math.sin(p / .28 * math.pi / 2)
        else:
            subindo, u = False, (p - .28) / .72
            alc = .5 + .5 * math.cos(u * math.pi)
        e_ = praia + .6 * E + amp * alc  # linhas acima de e_ estão debaixo d'água
        molhado[x] = max(molhado[x] - .9 * E * dt, e_)
        xe = x // e
        if p > .62:  # a próxima onda se formando e vindo para a praia
            u2 = (p - .62) / .38
            yb = int(praia - 1 - s["B"] * (1 - u2))
            if yb > hz + e:
                if ruido(xe, n, 3) < .35 + .55 * u2:
                    for k in range(e):
                        linhas[yb - hz + k][x] = espuma
                if ruido(xe, n, 4) < .5:
                    linhas[yb - hz - 1][x] = c["traco"][0]
        perto_sol = abs(x - sx) < s["hw_areia"]
        for y in range(praia, min(fim, int(max(e_, molhado[x])) + 2)):  # abaixo disso a areia está seca
            i = y - hz
            if y < e_:
                prof = e_ - y
                if prof < 1.4 * E and (subindo or ruido(xe, y // e, n) < .8 * (1 - u)) or \
                        not subindo and ruido(x // (3 * e), y // e, n, 1) < .14 * (1 - u):
                    linhas[i][x] = espuma  # frente da onda; na volta vira renda
                elif subindo and prof < 2.6 * E:
                    linhas[i][x] = espuma2  # espuma rala logo atrás da frente
                elif perto_sol and ruido(x, y // e, brilho) < .1:
                    linhas[i][x] = reflexo[1]
                else:
                    linhas[i][x] = lamina[0 if prof < 2.5 * E else 1]
            elif y < molhado[x] and (molhado[x] - y > E or (x + y) % 2):
                linhas[i][x] = reflexo[2] if perto_sol and ruido(x, y // e, brilho) < .06 else umida[y - praia][x]
    s["img_mar"] = imagem(linhas)
    fundo.itemconfig(s["mar_id"], image=s["img_mar"])


def animar():
    if cena.get("W") and root.state() != "withdrawn":
        t = time.monotonic()
        dt, cena["t"] = min(.5, t - cena["t"]), t
        quadro(t, dt)
        W = cena["W"]
        for nv in cena["nuvens"]:
            nv["x"] += nv["v"] * dt
            if nv["x"] > W:
                nv["x"] = -nv["larg"]
            fundo.coords(nv["id"], round(nv["x"]) * P, round(nv["y"]) * P)
        if cena["passaros"]:
            b = cena["bando"]
            b["x"] -= 2.2 * E * dt
            if b["x"] < -20 * E:
                b.update(x=W + random.uniform(20, 160) * E, y=random.uniform(cena["hz"] * .2, cena["hz"] * .6))
            for k, (dx, dy, item) in enumerate(cena["passaros"]):
                img, x0, y0 = cena["asas"][int(t * 3 + k) % 2]
                fundo.coords(item, round(b["x"] + dx + x0) * P, round(b["y"] + dy + y0 + math.sin(t + k) * .6 * E) * P)
                fundo.itemconfig(item, image=img)
        bx, by = cena["barco"]
        fundo.coords(cena["barco_id"], round(bx + math.sin(t * .15) * 2 * E) * P,
                     round(by + math.sin(t * 1.2) * .6 * E) * P)
        for e in random.sample(cena["estrelas"], min(3, len(cena["estrelas"]))):
            fundo.itemconfig(e, fill=random.choice(("white", "#8890C0", "#4A5290")))
        if datetime.now().strftime("%H:%M") != cena["min"]:
            montar() if fase_atual() != cena["nome"] else relogio()
    root.after(80, animar)


def agendar(_=None):
    """Remonta a cena só quando o redimensionamento para, em vez de a cada pixel arrastado."""
    if pendente.get("id"):
        root.after_cancel(pendente["id"])
    pendente["id"] = root.after(150, montar)


fundo.bind("<Configure>", agendar)
animar()


# Bolinha flutuante: aparece quando minimiza; arraste para mover, clique para abrir.
bolha = tk.Toplevel(root)
bolha.overrideredirect(True)
bolha.attributes("-topmost", True, "-transparentcolor", "white")
bolha.geometry(f"64x64+{root.winfo_screenwidth() - 100}+{root.winfo_screenheight() - 160}")
cv = tk.Canvas(bolha, width=64, height=64, bg="white", highlightthickness=0, cursor="hand2")
icone = tk.PhotoImage(file=Path(__file__).with_name("manga.png"))
cv.create_image(32, 32, image=icone)
cv.pack()
bolha.withdraw()
arrasto = {}


def pressionar(e):
    arrasto.update(x=e.x, y=e.y, moveu=False)


def mover(e):
    arrasto["moveu"] = True
    bolha.geometry(f"+{e.x_root - arrasto['x']}+{e.y_root - arrasto['y']}")


def soltar(_):
    if not arrasto["moveu"]:
        abrir()


def minimizar(_=None):
    root.withdraw()
    bolha.deiconify()


def abrir():
    bolha.withdraw()
    root.deiconify()
    root.lift()
    texto.focus_set()


cv.bind("<ButtonPress-1>", pressionar)
cv.bind("<B1-Motion>", mover)
cv.bind("<ButtonRelease-1>", soltar)
root.bind("<Unmap>", lambda e: e.widget is root and root.state() == "iconic" and minimizar())
root.bind("<Escape>", minimizar)

texto.focus_set()
root.mainloop()
