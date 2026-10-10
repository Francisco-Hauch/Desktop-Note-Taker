import ctypes
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


# Cena em pixel art: praia de dia (6h–18h) ou de noite, mar animado, relógio no topo e uma máquina de
# escrever numa mesinha; a folha (onde se escreve) sai do rolo.
P = 6  # tamanho de cada "pixel" da cena, em pixels de tela
CENA = {
    True: dict(ceu=("#3A8EE6", "#A8DDF7"), mar=("#1E6FB8", "#2884CF", "#3A9BE0", "#55B4EA"), crista="#D6F1FF",
               areia="#F2D48B", grao="#DDB566", molhada="#D9B36A", espuma="#FFFFFF", astro="#FFD84A",
               brilho="#FFF3A6", tronco=("#8A5A2B", "#5E3B1A"), folha=("#3FA34D", "#22702F"),
               mesa=("#B98552", "#8A5A2B", "#6B4423"), relogio="#FFFFFF", sombra="#1F4F80"),
    False: dict(ceu=("#070B24", "#2A2F6B"), mar=("#0B1638", "#10204D", "#172B60", "#203873"), crista="#7D8FD0",
                areia="#6E6A7E", grao="#58556B", molhada="#55526A", espuma="#A9B4E0", astro="#F4F1D0",
                brilho="#C9CDF0", tronco=("#3E3040", "#2A2030"), folha=("#1E3E3A", "#132A28"),
                mesa=("#5A4A55", "#43363F", "#2F252C"), relogio="#F4F1D0", sombra="#000000"),
}
MAQUINA, MAQUINA_LUZ, TECLA, TECLA_SOMBRA, ROLO = "#2F4858", "#4A6B7C", "#EDE6D3", "#1C2C36", "#1A1A1A"
PALMEIRA = [  # g/G folhas, b/B tronco, . transparente
    "......gg....gg......",
    "....ggGGg..gGGgg....",
    "..ggG...gggg...Ggg..",
    ".gG....gGGGGg....Gg.",
    "gG....gG.bb.Gg....Gg",
    "G....gG..bB..Gg....G",
    "....gG...bB...Gg....",
    "....G....bB....G....",
    ".........bB.........",
    "........bB..........",
    "........bB..........",
    "........bB..........",
    ".......bB...........",
    ".......bB...........",
    ".......bB...........",
    ".......bB...........",
    "......bbBB..........",
]
DIGITOS = {  # fonte 3x5
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
    "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001001001001",
    "8": "111101111101111", "9": "111101111001111", ":": "000010000010000",
}
PAPEL, CAMPO, TINTA, LARANJA, REALCE = "#FFF8E7", "#F7EBD0", "#2B1D14", "#E8743B", "#F2A541"
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


def degrade(c1, c2, n):
    a, b = ([int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in (c1, c2))
    return ["#%02x%02x%02x" % tuple(int(x + (y - x) * i / (n - 1)) for x, y in zip(a, b)) for i in range(n)]


def imagem(linhas):
    img = tk.PhotoImage(width=len(linhas[0]), height=len(linhas))
    img.put(" ".join("{" + " ".join(l) + "}" for l in linhas))
    return img.zoom(P)


def bloco(x1, y1, x2, y2, cor):
    fundo.create_rectangle(x1, y1, x2, y2, fill=cor, width=0, tags="cena")


cena = {}


def montar(_=None):
    """Recria a parte fixa da cena (céu, sol/lua, estrelas, areia, palmeira, mesa, máquina) para o tamanho e o
    período atuais. O mar é redesenhado à parte em animar()."""
    w, h = fundo.winfo_width(), fundo.winfo_height()
    dia = 6 <= datetime.now().hour < 18
    c = CENA[dia]
    W, H = w // P + 1, h // P + 1
    hz, costa = int(H * .45), int(H * .68)  # horizonte e linha da praia, em pixels da cena
    rnd = random.Random(W * H)  # mesma cena enquanto o tamanho não muda
    faixas = degrade(*c["ceu"], 6)  # céu em faixas, sem degradê suave
    sx, sy, r = int(W * .84), int(H * .14), 5
    linhas = []
    for y in range(H):
        if y < hz:
            ceu = faixas[y * 6 // hz]
            linha = [ceu] * W
            for x in range(sx - r, min(sx + r + 1, W)):
                if (x - sx) ** 2 + (y - sy) ** 2 <= r * r:
                    lua = not dia and (x - sx + 3) ** 2 + (y - sy + 2) ** 2 <= r * r  # recorte da lua crescente
                    linha[x] = ceu if lua else c["astro"]
        else:
            linha = [c["grao"] if rnd.random() < .06 else c["areia"] for _ in range(W)]
        linhas.append(linha)

    fundo.delete("cena")
    cena.update(base=imagem(linhas), W=W, hz=hz, costa=costa, c=c, dia=dia, sx=sx, estrelas=[])
    fundo.create_image(0, 0, image=cena["base"], anchor="nw", tags="cena")
    cena["mar"] = fundo.create_image(0, hz * P, anchor="nw", tags="cena")
    if not dia:
        for _ in range(W * hz // 140):
            x, y = rnd.randrange(W), rnd.randrange(hz - 3)
            if (x - sx) ** 2 + (y - sy) ** 2 > (r + 2) ** 2:
                bloco(x * P, y * P, x * P + P, y * P + P, "white")
                cena["estrelas"].append(fundo.find_all()[-1])
    cores = {"g": c["folha"][0], "G": c["folha"][1], "b": c["tronco"][0], "B": c["tronco"][1]}
    ox, oy = int(W * .05), H - 4 - len(PALMEIRA)
    for j, fila in enumerate(PALMEIRA):
        for i, ch in enumerate(fila):
            if ch in cores:
                bloco((ox + i) * P, (oy + j) * P, (ox + i + 1) * P, (oy + j + 1) * P, cores[ch])

    # mesinha: tampo com borda escura e duas pernas
    tampo, dentro, perna = c["mesa"]
    my = (h - 130) // P * P
    mx1, mx2 = (w // 2 - 330) // P * P, (w // 2 + 330) // P * P
    bloco(mx1, my, mx2, my + 2 * P, tampo)
    bloco(mx1, my + 2 * P, mx2, my + 4 * P, dentro)
    for x in (mx1 + 3 * P, mx2 - 6 * P):
        bloco(x, my + 4 * P, x + 3 * P, h, perna)

    # máquina de escrever: corpo com cantos em degrau, duas fileiras de teclas, rolo com botões
    bx1, bx2 = (w // 2 - 270) // P * P, (w // 2 + 270) // P * P
    by = my - 16 * P
    bloco(bx1 + P, by, bx2 - P, my, MAQUINA)
    bloco(bx1, by + P, bx2, my - P, MAQUINA)
    bloco(bx1 + 2 * P, by + P, bx2 - 2 * P, by + 2 * P, MAQUINA_LUZ)
    for fila in range(2):
        y = by + 4 * P + fila * 3 * P
        for x in range(bx1 + (5 + fila) * P, bx2 - 6 * P, 4 * P):
            bloco(x, y, x + 2 * P, y + 2 * P, TECLA)
            bloco(x, y + 2 * P, x + 2 * P, y + 2 * P + P // 2, TECLA_SOMBRA)
    ry = by - 3 * P
    bloco(bx1 + 4 * P, ry, bx2 - 4 * P, by, ROLO)
    bloco(bx1 + P, ry - P, bx1 + 4 * P, by + P, ROLO)
    bloco(bx2 - 4 * P, ry - P, bx2 - P, by + P, ROLO)
    fundo.coords(botao_id, w // 2, by + 13 * P)

    # folha saindo do rolo
    alt, larg = min(340, ry - 64), 480
    fundo.coords(folha_id, w // 2 - larg // 2, ry + P - alt)
    fundo.itemconfig(folha_id, width=larg, height=alt)
    relogio()


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


def animar():
    if cena and root.state() != "withdrawn":
        t, c, W, hz, costa, sx = time.monotonic(), cena["c"], cena["W"], cena["hz"], cena["costa"], cena["sx"]
        onda = [costa + round(1.5 * math.sin(t * .9) + math.sin(x * .12 + t * 1.3)) for x in range(W)]
        linhas = []
        for j in range(costa + 4 - hz):
            y, base = hz + j, c["mar"][min(j * 4 // (costa - hz), 3)]
            linha = []
            for x in range(W):
                if y > onda[x]:
                    linha.append(c["areia"] if y > onda[x] + 1 else c["molhada"])
                elif y == onda[x]:
                    linha.append(c["espuma"])
                elif math.sin(x * .45 - t * 2.2 + j * 1.9) * math.sin(x * .05 + j * .7) > .9:  # cristas esparsas
                    linha.append(c["crista"])
                elif abs(x - sx) < 2 + j // 6 and (x * 7 + j * 13 + int(t * 6)) % 5 < 2:  # reflexo do sol/lua
                    linha.append(c["brilho"])
                else:
                    linha.append(base)
            linhas.append(linha)
        cena["img_mar"] = imagem(linhas)
        fundo.itemconfig(cena["mar"], image=cena["img_mar"])
        for e in random.sample(cena["estrelas"], min(3, len(cena["estrelas"]))):
            fundo.itemconfig(e, fill=random.choice(("white", "#8890C0", "#4A5290")))
        if datetime.now().strftime("%H:%M") != cena["min"]:
            montar() if (6 <= datetime.now().hour < 18) != cena["dia"] else relogio()
    root.after(120, animar)


fundo.bind("<Configure>", montar)
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
