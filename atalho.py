"""Gera manga.ico/manga.png e cria o atalho "Nota rápida" na Área de Trabalho e no Menu Iniciar.
Rode uma vez: python atalho.py  (depois fixe o atalho na barra de tarefas pelo botão direito)."""
import math
import struct
import subprocess
import sys
import zlib
from pathlib import Path

PASTA = Path(__file__).resolve().parent
ICO = PASTA / "manga.ico"
PNG_BOLHA = PASTA / "manga.png"  # bolinha flutuante do app

# degradê da manga, do cabo para a ponta: verde, amarelo, laranja, vermelho
CORES = [(0.0, (46, 125, 50)), (0.3, (124, 179, 66)), (0.45, (251, 192, 45)),
         (0.58, (245, 124, 0)), (0.75, (211, 47, 47)), (1.0, (165, 25, 35))]


def degrade(t):
    for (t0, c0), (t1, c1) in zip(CORES, CORES[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return tuple(a + (b - a) * k for a, b in zip(c0, c1))
    return CORES[-1][1]


def elipse(x, y, cx, cy, rx, ry, ang):
    c, s = math.cos(ang), math.sin(ang)
    dx, dy = x - cx, y - cy
    u, v = dx * c + dy * s, -dx * s + dy * c
    return (u / rx) ** 2 + (v / ry) ** 2, u / rx, v / ry


FUNDO = (255, 214, 170)  # laranja pastel
ZOOM = 0.85  # >1 aumenta a manga dentro do fundo


def pixel(x, y):
    """Cor de um ponto em coordenadas 0..1 (None = transparente): manga sobre quadrado arredondado."""
    cor = manga(0.51 + (x - 0.5) / ZOOM, 0.545 + (y - 0.5) / ZOOM)
    if cor:
        return cor
    r = 0.3  # raio dos cantos
    dx, dy = max(abs(x - 0.5) - (0.5 - r), 0), max(abs(y - 0.5) - (0.5 - r), 0)
    return FUNDO if dx * dx + dy * dy <= r * r else None


def manga(x, y):
    # folha
    d, u, v = elipse(x, y, 0.70, 0.17, 0.20, 0.075, -0.5)
    if d <= 1:
        return (27, 94, 32) if abs(v) < 0.12 and u > -0.9 else (67, 160, 71)
    # cabo
    if 0.47 <= x <= 0.53 and 0.10 <= y <= 0.24:
        return (93, 64, 55)
    # corpo: elipse inclinada, mais gorda embaixo (formato de rim)
    d, u, v = elipse(x, y, 0.48, 0.58, 0.33, 0.40, -0.45)
    d -= 0.18 * max(v, 0) * max(-u, 0)
    if d <= 1:
        cor = degrade(min(max((v + 1) / 2, 0), 1))
        brilho = max(0, 1 - ((u + 0.4) ** 2 + (v + 0.5) ** 2) / 0.12) * 0.5
        return tuple(c + (255 - c) * brilho for c in cor)
    return None


def png(n, amostras=4):
    linhas = bytearray()
    for py in range(n):
        linhas.append(0)
        for px in range(n):
            soma, cobertos = [0, 0, 0], 0
            for sy in range(amostras):
                for sx in range(amostras):
                    c = pixel((px + (sx + 0.5) / amostras) / n, (py + (sy + 0.5) / amostras) / n)
                    if c:
                        cobertos += 1
                        soma = [a + b for a, b in zip(soma, c)]
            k = max(cobertos, 1)
            linhas += bytes([round(soma[0] / k), round(soma[1] / k), round(soma[2] / k),
                             round(255 * cobertos / amostras ** 2)])

    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados))
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + bloco(b"IDAT", zlib.compress(bytes(linhas), 9)) + bloco(b"IEND", b""))


def gerar_ico():
    imagens = [(n, png(n)) for n in (16, 20, 24, 32, 40, 48, 64, 256)]  # ICO aceita PNG dentro (Windows Vista+)
    cab = struct.pack("<HHH", 0, 1, len(imagens))
    pos = 6 + 16 * len(imagens)
    for n, dados in imagens:
        cab += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(dados), pos)
        pos += len(dados)
    ICO.write_bytes(cab + b"".join(d for _, d in imagens))
    PNG_BOLHA.write_bytes(png(64))
    assert struct.unpack("<HHH", ICO.read_bytes()[:6]) == (0, 1, 8)


# Grava System.AppUserModel.ID no .lnk (WScript não sabe), para o atalho fixado agrupar com a janela do app.
AUMID_CS = """
using System; using System.Runtime.InteropServices;
[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPropertyStore { void GetCount(out uint c); void GetAt(uint i, out PK k);
  void GetValue(ref PK k, IntPtr v); void SetValue(ref PK k, ref PV v); void Commit(); }
[StructLayout(LayoutKind.Sequential)] public struct PK { public Guid f; public uint p; }
[StructLayout(LayoutKind.Explicit, Size = 24)] public struct PV { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr s; }
public static class Aumid {
  [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
  static extern void SHGetPropertyStoreFromParsingName(string p, IntPtr b, int f, ref Guid g, out IPropertyStore s);
  public static void Gravar(string lnk, string id) {
    Guid g = typeof(IPropertyStore).GUID; IPropertyStore s;
    SHGetPropertyStoreFromParsingName(lnk, IntPtr.Zero, 2, ref g, out s);
    PK k = new PK { f = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), p = 5 };
    PV v = new PV { vt = 31, s = Marshal.StringToCoTaskMemUni(id) };
    s.SetValue(ref k, ref v); s.Commit(); Marshal.FreeCoTaskMem(v.s); Marshal.ReleaseComObject(s);
  }
}"""


def criar_atalhos():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    ps = f"""
Add-Type -TypeDefinition @'
{AUMID_CS}
'@
$w = New-Object -ComObject WScript.Shell
foreach ($p in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {{
  $a = $w.CreateShortcut((Join-Path $p 'Nota rápida.lnk'))
  $a.TargetPath = '{pythonw}'
  $a.Arguments = '"{PASTA / "note_taker.pyw"}"'
  $a.WorkingDirectory = '{PASTA}'
  $a.IconLocation = '{ICO},0'
  $a.Save()
  [Aumid]::Gravar($a.FullName, 'Fran.NotaRapida')  # mesmo ID que note_taker.pyw grava na janela
  Write-Output "Atalho criado: $p"
}}"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


if __name__ == "__main__":
    gerar_ico()
    criar_atalhos()
