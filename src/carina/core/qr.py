"""Gerador de QR code em Python puro (v0.19 T5) — sem dependências.

Suficiente para o endereço do companheiro no celular: modo **byte**,
versões 1 a 5 (até 106 bytes no nível L) e correção de erros **L** ou
**M**. Implementa o padrão ISO/IEC 18004: codificação, Reed–Solomon em
GF(256), entrelaçamento de blocos, padrões de localização/alinhamento/
sincronismo, as oito máscaras com a escolha pela penalidade e a
informação de formato (BCH 15,5).

``decode`` é um leitor mínimo da mesma família de símbolos, usado nos
testes para conferir a ida e a volta (formato, máscara, ordem dos módulos,
blocos e síndromes de Reed–Solomon).
"""

from __future__ import annotations

# (total de codewords, {nível: (ec por bloco, [dados por bloco...])})
VERSIONS = {
    1: (26, {"L": (7, [19]), "M": (10, [16])}),
    2: (44, {"L": (10, [34]), "M": (16, [28])}),
    3: (70, {"L": (15, [55]), "M": (26, [44])}),
    4: (100, {"L": (20, [80]), "M": (18, [32, 32])}),
    5: (134, {"L": (26, [108]), "M": (24, [43, 43])}),
}
# conferência da tabela: dados + correção = total de codewords
for _v, (_total, _lv) in VERSIONS.items():
    for _ec, _sizes in _lv.values():
        assert sum(_sizes) + _ec * len(_sizes) == _total, (_v, _ec, _sizes)
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30]}
REMAINDER = {1: 0, 2: 7, 3: 7, 4: 7, 5: 7}
EC_BITS = {"L": 0b01, "M": 0b00, "Q": 0b11, "H": 0b10}

# --------------------------------------------------------------------------
# GF(256) com o polinômio 0x11D
EXP = [0] * 512
LOG = [0] * 256
_x = 1
for _i in range(255):
    EXP[_i] = _x
    LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]


def rs_generator(n: int) -> list[int]:
    g = [1]
    for i in range(n):
        out = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            out[j] ^= c
            out[j + 1] ^= gf_mul(c, EXP[i])
        g = out
    return g


def rs_encode(data: list[int], n_ec: int) -> list[int]:
    """Codewords de correção (divisão polinomial pelo gerador)."""
    gen = rs_generator(n_ec)
    rem = list(data) + [0] * n_ec
    for i in range(len(data)):
        coef = rem[i]
        if coef:
            for j in range(1, len(gen)):
                rem[i + j] ^= gf_mul(gen[j], coef)
    return rem[len(data):]


def rs_syndromes(codeword: list[int], n_ec: int) -> list[int]:
    out = []
    for i in range(n_ec):
        s = 0
        for c in codeword:
            s = gf_mul(s, EXP[i]) ^ c
        out.append(s)
    return out


# --------------------------------------------------------------------------
def _capacity(version: int, level: str) -> int:
    _total, levels = VERSIONS[version]
    return sum(levels[level][1])


def choose_version(data: bytes, level: str = "M") -> int:
    for v in VERSIONS:
        bits = 4 + 8 + 8 * len(data)
        if bits <= _capacity(v, level) * 8:
            return v
    raise ValueError("texto longo demais para o gerador de QR (até 5-L)")


def _data_codewords(data: bytes, version: int, level: str) -> list[int]:
    cap = _capacity(version, level)
    bits = [0, 1, 0, 0]                                     # modo byte
    bits += [int(b) for b in f"{len(data):08b}"]
    for byte in data:
        bits += [int(b) for b in f"{byte:08b}"]
    bits += [0] * min(4, cap * 8 - len(bits))               # terminador
    bits += [0] * ((8 - len(bits) % 8) % 8)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = [0xEC, 0x11]
    k = 0
    while len(words) < cap:
        words.append(pad[k % 2])
        k += 1
    return words


def _interleave(words: list[int], version: int, level: str) -> list[int]:
    _total, levels = VERSIONS[version]
    n_ec, sizes = levels[level]
    blocks, k = [], 0
    for s in sizes:
        blocks.append(words[k:k + s])
        k += s
    ecs = [rs_encode(b, n_ec) for b in blocks]
    out = []
    for i in range(max(sizes)):
        for b in blocks:
            if i < len(b):
                out.append(b[i])
    for i in range(n_ec):
        for e in ecs:
            out.append(e[i])
    return out


def _function_mask(version: int) -> list[list[bool]]:
    n = 17 + 4 * version
    f = [[False] * n for _ in range(n)]
    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
        for r in range(-1, 8):
            for c in range(-1, 8):
                if 0 <= r0 + r < n and 0 <= c0 + c < n:
                    f[r0 + r][c0 + c] = True
    for i in range(n):
        f[6][i] = f[i][6] = True
    pos = ALIGN[version]
    for r in pos:
        for c in pos:
            if (r, c) in ((6, 6), (6, n - 7), (n - 7, 6)):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    f[r + dr][c + dc] = True
    for i in range(9):
        f[8][i] = f[i][8] = True
    for i in range(8):
        f[8][n - 1 - i] = f[n - 1 - i][8] = True
    f[4 * version + 9][8] = True                             # módulo escuro
    return f


def _base_matrix(version: int) -> list[list[int]]:
    n = 17 + 4 * version
    m = [[0] * n for _ in range(n)]
    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
        for r in range(7):
            for c in range(7):
                ring = max(abs(r - 3), abs(c - 3))
                m[r0 + r][c0 + c] = 1 if ring != 2 else 0
    for i in range(8, n - 8):
        m[6][i] = m[i][6] = 1 if i % 2 == 0 else 0
    pos = ALIGN[version]
    for r in pos:
        for c in pos:
            if (r, c) in ((6, 6), (6, n - 7), (n - 7, 6)):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    m[r + dr][c + dc] = 1 if max(abs(dr), abs(dc)) != 1 else 0
    m[4 * version + 9][8] = 1
    return m


def _zigzag(n: int, func):
    """Ordem de leitura/escrita dos módulos de dados."""
    col = n - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(n - 1, -1, -1) if upward else range(n)
        for r in rows:
            for c in (col, col - 1):
                if not func[r][c]:
                    yield r, c
        upward = not upward
        col -= 2


MASKS = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]


def format_bits(level: str, mask: int) -> int:
    data = (EC_BITS[level] << 3) | mask
    v = data << 10
    for i in range(14, 9, -1):
        if v & (1 << i):
            v ^= 0b10100110111 << (i - 10)
    return ((data << 10) | v) ^ 0b101010000010010


def _place_format(m, level: str, mask: int) -> None:
    n = len(m)
    bits = format_bits(level, mask)
    b = [(bits >> i) & 1 for i in range(15)]                 # b[0] = menos significativo
    # cópia 1, perto do localizador de cima à esquerda
    for i in range(6):
        m[8][i] = b[14 - i]
    m[8][7] = b[8]
    m[8][8] = b[7]
    m[7][8] = b[6]
    for i in range(6):                     # linhas 0..5 da coluna 8: b[0..5]
        m[i][8] = b[i]
    # cópia 2
    for i in range(7):
        m[n - 1 - i][8] = b[14 - i]
    for i in range(8):
        m[8][n - 8 + i] = b[7 - i]
    m[4 * ((n - 17) // 4) + 9][8] = 1


def _penalty(m) -> int:
    n = len(m)
    score = 0
    for line in list(m) + [list(col) for col in zip(*m)]:
        run, prev = 0, None
        for v in line:
            if v == prev:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run, prev = 1, v
        if run >= 5:
            score += run - 2
        s = "".join(map(str, line))
        score += 40 * (s.count("10111010000") + s.count("00001011101"))
    for r in range(n - 1):
        for c in range(n - 1):
            v = m[r][c]
            if v == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    dark = sum(map(sum, m))
    score += 10 * (abs(dark * 100 // (n * n) - 50) // 5)
    return score


def encode(text: str, level: str = "M") -> list[list[int]]:
    """Matriz de módulos (1 = escuro) do texto, sem a zona de silêncio."""
    data = text.encode("utf-8")
    version = choose_version(data, level)
    words = _interleave(_data_codewords(data, version, level), version, level)
    bits = [int(b) for w in words for b in f"{w:08b}"] + [0] * REMAINDER[version]
    func = _function_mask(version)
    best = None
    for mask in range(8):
        m = _base_matrix(version)
        k = 0
        for r, c in _zigzag(len(m), func):
            v = bits[k] if k < len(bits) else 0
            k += 1
            m[r][c] = v ^ (1 if MASKS[mask](r, c) else 0)
        _place_format(m, level, mask)
        p = _penalty(m)
        if best is None or p < best[0]:
            best = (p, m)
    return best[1]


def decode(m: list[list[int]]) -> str:
    """Leitor mínimo (testes): lê o formato da cópia 1 e devolve o texto."""
    n = len(m)
    version = (n - 17) // 4
    b = [0] * 15
    for i in range(6):
        b[14 - i] = m[8][i]
    b[8], b[7], b[6] = m[8][7], m[8][8], m[7][8]
    for i in range(6):
        b[i] = m[i][8]
    raw = sum(bit << i for i, bit in enumerate(b))
    level = mask = None
    for lv in ("L", "M"):
        for mk in range(8):
            if format_bits(lv, mk) == raw:
                level, mask = lv, mk
    if level is None:
        raise ValueError("formato ilegível")
    func = _function_mask(version)
    bits = [m[r][c] ^ (1 if MASKS[mask](r, c) else 0) for r, c in _zigzag(n, func)]
    total, levels = VERSIONS[version]
    words = [int("".join(map(str, bits[i * 8:i * 8 + 8])), 2) for i in range(total)]
    n_ec, sizes = levels[level]
    blocks = [[] for _ in sizes]
    k = 0
    for i in range(max(sizes)):
        for j, s in enumerate(sizes):
            if i < s:
                blocks[j].append(words[k])
                k += 1
    ecs = [[] for _ in sizes]
    for i in range(n_ec):
        for j in range(len(sizes)):
            ecs[j].append(words[k])
            k += 1
    for blk, ec in zip(blocks, ecs):
        if any(rs_syndromes(blk + ec, n_ec)):
            raise ValueError("Reed–Solomon não confere")
    data = [w for blk in blocks for w in blk]
    bitstr = "".join(f"{w:08b}" for w in data)
    if bitstr[:4] != "0100":
        raise ValueError("só o modo byte é suportado")
    length = int(bitstr[4:12], 2)
    out = bytes(int(bitstr[12 + 8 * i:20 + 8 * i], 2) for i in range(length))
    return out.decode("utf-8")
