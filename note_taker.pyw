import ctypes
import json
import os
import re
import struct
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


root = tk.Tk()
root.title("Nota rápida")
root.iconbitmap(default=Path(__file__).with_name("manga.ico"))
root.update_idletasks()
id_na_barra(root, "Fran.NotaRapida")
root.geometry("380x360")
root.attributes("-topmost", True)

tipo = ttk.Combobox(root, values=list(TIPOS), state="readonly")
tipo.current(0)
tipo.pack(fill="x", padx=8, pady=(8, 4))

quadro = ttk.Frame(root)
quadro.pack(fill="x", padx=8)
quadro.columnconfigure(1, weight=1)
widgets = {}
for i, (campo, (rotulo, sugestoes)) in enumerate(CAMPOS.items()):
    lbl = ttk.Label(quadro, text=rotulo)
    ent = ttk.Combobox(quadro, values=sugestoes) if sugestoes is not None else ttk.Entry(quadro)
    lbl.grid(row=i, column=0, sticky="w", pady=2)
    ent.grid(row=i, column=1, sticky="ew", padx=(6, 0), pady=2)
    widgets[campo] = (lbl, ent)


def trocar_tipo(_=None):
    visiveis = TIPOS[tipo.get()][2]
    for campo, (lbl, ent) in widgets.items():
        for w in (lbl, ent):
            w.grid() if campo in visiveis else w.grid_remove()


tipo.bind("<<ComboboxSelected>>", trocar_tipo)
trocar_tipo()


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


# botão empacotado antes do texto para não ser espremido para fora da janela
ttk.Button(root, text="Enviar (Ctrl+Enter)", command=enviar).pack(side="bottom", fill="x", padx=8, pady=8)
texto = tk.Text(root, wrap="word", font=("Segoe UI", 10), undo=True)
texto.pack(fill="both", expand=True, padx=8, pady=(4, 0))
texto.bind("<Control-Return>", enviar)

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
