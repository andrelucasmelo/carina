"""Renderizador OpenGL 3.3 core (PyOpenGL) usado pelo SkyWidget.

Três programas:
  - points: sprites circulares suaves com tamanho por vértice (estrelas/planetas)
  - lines:  linhas com cor por vértice (grades, constelações, horizonte)
  - fill:   cor uniforme, usado com o truque de stencil-invert para preencher
            polígonos côncavos (Via Láctea) sem triangulação.
"""

from __future__ import annotations

import ctypes

import numpy as np
import OpenGL

# O PyOpenGL embrulha CADA chamada GL com glGetError — custava ~1 s a cada
# 13 s de renderização (medido no --bench). Em produção a validação já foi
# feita durante o desenvolvimento; desligar antes de importar OpenGL.GL
# remove o embrulho por completo.
OpenGL.ERROR_CHECKING = False
from OpenGL import GL  # noqa: E402

_POINTS_VS = """
#version 330 core
layout(location=0) in vec2 a_pos;
layout(location=1) in float a_size;
layout(location=2) in vec4 a_color;
uniform vec2 u_viewport;
out vec4 v_color;
void main() {
    vec2 ndc = vec2(a_pos.x / u_viewport.x * 2.0 - 1.0,
                    1.0 - a_pos.y / u_viewport.y * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
    gl_PointSize = a_size;
    v_color = a_color;
}
"""

_POINTS_FS = """
#version 330 core
in vec4 v_color;
uniform float u_hard;   // 0 = brilho suave (tela); 1 = disco firme (papel)
out vec4 frag;
void main() {
    vec2 d = gl_PointCoord - vec2(0.5);
    float r = length(d) * 2.0;
    float soft = pow(clamp(1.0 - r, 0.0, 1.0), 1.4);
    float disc = 1.0 - smoothstep(0.78, 1.0, r);
    float alpha = mix(soft, disc, u_hard);
    frag = vec4(v_color.rgb, v_color.a * alpha);
}
"""

_LINES_VS = """
#version 330 core
layout(location=0) in vec2 a_pos;
layout(location=1) in vec4 a_color;
uniform vec2 u_viewport;
out vec4 v_color;
void main() {
    vec2 ndc = vec2(a_pos.x / u_viewport.x * 2.0 - 1.0,
                    1.0 - a_pos.y / u_viewport.y * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
    v_color = a_color;
}
"""

_LINES_FS = """
#version 330 core
in vec4 v_color;
out vec4 frag;
void main() { frag = v_color; }
"""

_FILL_VS = """
#version 330 core
layout(location=0) in vec2 a_pos;
uniform vec2 u_viewport;
void main() {
    vec2 ndc = vec2(a_pos.x / u_viewport.x * 2.0 - 1.0,
                    1.0 - a_pos.y / u_viewport.y * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
}
"""

_FILL_FS = """
#version 330 core
uniform vec4 u_color;
out vec4 frag;
void main() { frag = u_color; }
"""

_TEX_VS = """
#version 330 core
layout(location=0) in vec2 a_pos;
layout(location=1) in vec2 a_uv;
uniform vec2 u_viewport;
out vec2 v_uv;
void main() {
    vec2 ndc = vec2(a_pos.x / u_viewport.x * 2.0 - 1.0,
                    1.0 - a_pos.y / u_viewport.y * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
    v_uv = a_uv;
}
"""

_TEX_FS = """
#version 330 core
in vec2 v_uv;
uniform sampler2D u_tex;
uniform float u_alpha;
out vec4 frag;
void main() {
    vec3 c = texture(u_tex, v_uv).rgb;
    // alpha proporcional ao brilho: regiões escuras da textura ficam
    // transparentes (o céu de fundo aparece), a banda ganha corpo
    float lum = dot(c, vec3(0.299, 0.587, 0.114));
    frag = vec4(c, clamp(lum * 2.2, 0.0, 1.0) * u_alpha);
}
"""


# Esfera lunar (v0.17): um quadrado na tela coberto por coordenadas locais
# (a, b) do disco; o fragmento reconstrói o ponto da esfera, gira para o
# referencial selenográfico MOON_ME, amostra cor e normais e sombreia com
# a direção do Sol (Lommel–Seeliger: a Lua cheia fica "chapada", como é).
_MOON_VS = """
#version 330 core
layout(location=0) in vec2 a_pos;
layout(location=1) in vec2 a_loc;
uniform vec2 u_viewport;
out vec2 v_loc;
void main() {
    vec2 ndc = vec2(a_pos.x / u_viewport.x * 2.0 - 1.0,
                    1.0 - a_pos.y / u_viewport.y * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
    v_loc = a_loc;
}
"""

_MOON_FS = """
#version 330 core
in vec2 v_loc;
uniform mat3 u_v2b;        // (a, b, c) locais -> MOON_ME
uniform vec3 u_sun;        // direção do Sol no MOON_ME
uniform vec3 u_view;       // direção do observador no MOON_ME
uniform sampler2D u_color;
uniform sampler2D u_normal;
uniform float u_gain;
uniform float u_earthshine;
uniform float u_alpha;
uniform float u_relief;    // 0 = sem normais; 1 = relevo completo
out vec4 frag;
const float PI = 3.14159265358979;
void main() {
    float r2 = dot(v_loc, v_loc);
    if (r2 > 1.0) discard;
    float c = sqrt(1.0 - r2);
    vec3 p = normalize(u_v2b * vec3(v_loc, c));
    float lon = atan(p.y, p.x);
    float lat = asin(clamp(p.z, -1.0, 1.0));
    vec2 uv = vec2(lon / (2.0 * PI) + 0.5, 0.5 - lat / PI);
    vec3 albedo = texture(u_color, uv).rgb;
    vec3 nm = texture(u_normal, uv).rgb * 2.0 - 1.0;
    vec3 east = vec3(-p.y, p.x, 0.0);
    float le = length(east);
    east = le > 1e-5 ? east / le : vec3(0.0, 1.0, 0.0);
    vec3 north = cross(p, east);
    vec3 n = normalize(mix(p, nm.x * east + nm.y * north + nm.z * p, u_relief));
    float mu0 = max(dot(n, u_sun), 0.0);
    float mu = max(dot(n, u_view), 0.05);
    float geo = smoothstep(-0.015, 0.02, dot(p, u_sun));
    // Lommel–Seeliger com teto: sem ele o limbo do lado do Sol satura
    float lit = min(2.0 * mu0 / (mu0 + mu), 1.25) * geo;
    float edge = 1.0 - smoothstep(0.985, 1.0, r2);      // limbo suave
    vec3 col = albedo * (lit * u_gain + u_earthshine * (1.0 - geo));
    // o lado noturno deixa passar um pouco do brilho do céu: sem isso a
    // Lua fina vira um "buraco" mais escuro que o fundo
    float body = mix(0.80, 1.0, clamp(lit * 4.0, 0.0, 1.0));
    frag = vec4(col, u_alpha * edge * body);
}
"""


def _compile(vs_src: str, fs_src: str) -> int:
    """Compila e linka um par vertex+fragment; erros viram RuntimeError com
    o log do driver (é onde os typos de GLSL aparecem)."""
    def shader(src, kind):
        s = GL.glCreateShader(kind)
        GL.glShaderSource(s, src)
        GL.glCompileShader(s)
        if not GL.glGetShaderiv(s, GL.GL_COMPILE_STATUS):
            raise RuntimeError(GL.glGetShaderInfoLog(s).decode())
        return s

    prog = GL.glCreateProgram()
    vs = shader(vs_src, GL.GL_VERTEX_SHADER)
    fs = shader(fs_src, GL.GL_FRAGMENT_SHADER)
    GL.glAttachShader(prog, vs)
    GL.glAttachShader(prog, fs)
    GL.glLinkProgram(prog)
    if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
        raise RuntimeError(GL.glGetProgramInfoLog(prog).decode())
    GL.glDeleteShader(vs)
    GL.glDeleteShader(fs)
    return prog


class _Batch:
    """VAO + VBO dinâmico com layout intercalado."""

    def __init__(self, program: int, attribs: list[tuple[int, int]]) -> None:
        # attribs: lista de (location, n_floats)
        self.program = program
        self.vao = GL.glGenVertexArrays(1)
        self.vbo = GL.glGenBuffers(1)
        stride = 4 * sum(n for _, n in attribs)
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        offset = 0
        for loc, n in attribs:
            GL.glEnableVertexAttribArray(loc)
            GL.glVertexAttribPointer(
                loc, n, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(offset)
            )
            offset += 4 * n
        GL.glBindVertexArray(0)

    def upload(self, data: np.ndarray) -> None:
        """Envia os vértices do quadro (STREAM_DRAW: dados descartáveis)."""
        data = np.ascontiguousarray(data, dtype=np.float32)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_STREAM_DRAW)


class GLRenderer:
    """Todas as chamadas OpenGL do aplicativo passam por aqui.

    A API é imediata e em pixels: o SkyWidget projeta tudo para coordenadas
    de tela e entrega arrays intercalados; este renderizador só faz upload
    e dispara os draw calls. Quatro programas: pontos (sprites redondos),
    linhas, preenchimento por stencil (polígonos côncavos sem triangulação)
    e triângulos texturizados (Via Láctea, imagens de levantamento).
    """

    def __init__(self) -> None:
        self._ready = False

    def initialize(self) -> None:
        """Compila os shaders e cria os batches — requer contexto GL atual
        (chamado a partir do initializeGL do widget)."""
        self.prog_points = _compile(_POINTS_VS, _POINTS_FS)
        self.prog_lines = _compile(_LINES_VS, _LINES_FS)
        self.prog_fill = _compile(_FILL_VS, _FILL_FS)
        self.prog_tex = _compile(_TEX_VS, _TEX_FS)
        self.batch_points = _Batch(self.prog_points, [(0, 2), (1, 1), (2, 4)])
        self.batch_lines = _Batch(self.prog_lines, [(0, 2), (1, 4)])
        self.batch_fill = _Batch(self.prog_fill, [(0, 2)])
        self.batch_tex = _Batch(self.prog_tex, [(0, 2), (1, 2)])
        self.u_vp_tex = GL.glGetUniformLocation(self.prog_tex, "u_viewport")
        self.u_tex_sampler = GL.glGetUniformLocation(self.prog_tex, "u_tex")
        self.u_tex_alpha = GL.glGetUniformLocation(self.prog_tex, "u_alpha")
        self.mw_texture = 0
        self.u_vp_points = GL.glGetUniformLocation(self.prog_points, "u_viewport")
        self.u_hard_points = GL.glGetUniformLocation(self.prog_points, "u_hard")
        self.u_vp_lines = GL.glGetUniformLocation(self.prog_lines, "u_viewport")
        self.u_vp_fill = GL.glGetUniformLocation(self.prog_fill, "u_viewport")
        self.u_color_fill = GL.glGetUniformLocation(self.prog_fill, "u_color")
        self.prog_moon = _compile(_MOON_VS, _MOON_FS)
        self.batch_moon = _Batch(self.prog_moon, [(0, 2), (1, 2)])
        self.u_moon = {
            name: GL.glGetUniformLocation(self.prog_moon, name)
            for name in ("u_viewport", "u_v2b", "u_sun", "u_view", "u_color",
                         "u_normal", "u_gain", "u_earthshine", "u_alpha", "u_relief")
        }
        self.moon_color_tex = 0
        self.moon_normal_tex = 0
        GL.glEnable(GL.GL_PROGRAM_POINT_SIZE)
        size_range = GL.glGetFloatv(GL.GL_ALIASED_POINT_SIZE_RANGE)
        self.max_point_size = float(size_range[1])
        self._ready = True

    # ------------------------------------------------------------------
    def begin_frame(self, width: int, height: int, clear_rgb) -> None:
        """Abre o quadro: viewport, blending alfa e limpeza de cor/stencil."""
        self._w, self._h = float(width), float(height)
        GL.glViewport(0, 0, int(width), int(height))
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_STENCIL_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glClearColor(clear_rgb[0], clear_rgb[1], clear_rgb[2], 1.0)
        GL.glClearStencil(0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_STENCIL_BUFFER_BIT)

    def end_frame(self) -> None:
        """Solta VAO/programa para o QPainter do overlay assumir o estado."""
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

    # ------------------------------------------------------------------
    def draw_points(self, interleaved: np.ndarray, hard: bool = False) -> None:
        """interleaved: (N,7) = x, y, tamanho_px, r, g, b, a.

        ``hard``: disco sólido de borda nítida (cartas em papel) em vez do
        brilho suave da tela.
        """
        if len(interleaved) == 0:
            return
        GL.glUseProgram(self.prog_points)
        GL.glUniform2f(self.u_vp_points, self._w, self._h)
        GL.glUniform1f(self.u_hard_points, 1.0 if hard else 0.0)
        self.batch_points.upload(interleaved)
        GL.glBindVertexArray(self.batch_points.vao)
        GL.glDrawArrays(GL.GL_POINTS, 0, len(interleaved))

    def draw_lines(self, interleaved: np.ndarray) -> None:
        """interleaved: (2S,6) = x, y, r, g, b, a — pares consecutivos formam segmentos"""
        if len(interleaved) == 0:
            return
        GL.glUseProgram(self.prog_lines)
        GL.glUniform2f(self.u_vp_lines, self._w, self._h)
        self.batch_lines.upload(interleaved)
        GL.glBindVertexArray(self.batch_lines.vao)
        GL.glDrawArrays(GL.GL_LINES, 0, len(interleaved))

    def create_texture(self, rgb: np.ndarray, wrap_s=None) -> int:
        """Cria uma textura RGB8 na GPU e devolve seu identificador."""
        h, w, _ = rgb.shape
        rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
        tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        prev_align = int(GL.glGetIntegerv(GL.GL_UNPACK_ALIGNMENT))
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D, 0, GL.GL_RGB8, w, h, 0,
            GL.GL_RGB, GL.GL_UNSIGNED_BYTE, rgb,
        )
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, prev_align)
        GL.glGenerateMipmap(GL.GL_TEXTURE_2D)
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER,
            GL.GL_LINEAR_MIPMAP_LINEAR,
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR
        )
        wrap = wrap_s if wrap_s is not None else GL.GL_CLAMP_TO_EDGE
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, wrap)
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE
        )
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        return int(tex)

    def max_texture_size(self) -> int:
        return int(GL.glGetIntegerv(GL.GL_MAX_TEXTURE_SIZE) or 4096)

    def set_moon_textures(self, color: np.ndarray, normal: np.ndarray) -> None:
        """Sobe as texturas da Lua (cor e normais), reduzindo se a placa
        não aceitar a largura (8192 px na cor)."""
        limit = self.max_texture_size()
        for arr_name in ("color", "normal"):
            arr = color if arr_name == "color" else normal
            step = 1
            while arr.shape[1] // step > limit:
                step *= 2
            if step > 1:
                arr = arr[::step, ::step]
            tex = self.create_texture(arr, wrap_s=GL.GL_REPEAT)
            old = self.moon_color_tex if arr_name == "color" else self.moon_normal_tex
            self.delete_texture(old)
            if arr_name == "color":
                self.moon_color_tex = tex
            else:
                self.moon_normal_tex = tex

    def mip_texture(self, levels: list) -> int:
        """Textura com a cadeia de mipmaps já pronta (gerada na CPU).

        Evita o ``glGenerateMipmap`` — 55 ms para a cor de 8k, um soluço
        visível — e permite subir os níveis numa ordem qualquer. Níveis
        mais largos que o limite da placa são descartados.
        """
        limit = self.max_texture_size()
        levels = [lv for lv in levels if lv.shape[1] <= limit]
        tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        prev_align = int(GL.glGetIntegerv(GL.GL_UNPACK_ALIGNMENT))
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        for i, lv in enumerate(levels):
            h, w, _ = lv.shape
            GL.glTexImage2D(GL.GL_TEXTURE_2D, i, GL.GL_RGB8, w, h, 0, GL.GL_RGB,
                            GL.GL_UNSIGNED_BYTE, np.ascontiguousarray(lv, dtype=np.uint8))
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, prev_align)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_BASE_LEVEL, 0)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAX_LEVEL, len(levels) - 1)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR_MIPMAP_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        return int(tex)

    def begin_strip_texture(self, levels: list) -> dict:
        """Começa uma textura grande em faixas: aloca o nível 0 vazio e
        sobe já os demais níveis (pequenos). Ver :meth:`continue_strip_texture`."""
        limit = self.max_texture_size()
        levels = [lv for lv in levels if lv.shape[1] <= limit]
        tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        prev_align = int(GL.glGetIntegerv(GL.GL_UNPACK_ALIGNMENT))
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        h0, w0, _ = levels[0].shape
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGB8, w0, h0, 0, GL.GL_RGB,
                        GL.GL_UNSIGNED_BYTE, None)
        for i, lv in enumerate(levels[1:], start=1):
            h, w, _ = lv.shape
            GL.glTexImage2D(GL.GL_TEXTURE_2D, i, GL.GL_RGB8, w, h, 0, GL.GL_RGB,
                            GL.GL_UNSIGNED_BYTE, np.ascontiguousarray(lv))
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, prev_align)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_BASE_LEVEL, 0)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAX_LEVEL, len(levels) - 1)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR_MIPMAP_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        return {"tex": int(tex), "data": levels[0], "row": 0}

    def continue_strip_texture(self, job: dict, rows: int = 512) -> bool:
        """Sobe a próxima faixa do nível 0; True quando terminou."""
        data = job["data"]
        r0 = job["row"]
        r1 = min(r0 + rows, data.shape[0])
        GL.glBindTexture(GL.GL_TEXTURE_2D, job["tex"])
        prev_align = int(GL.glGetIntegerv(GL.GL_UNPACK_ALIGNMENT))
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, 0, r0, data.shape[1], r1 - r0, GL.GL_RGB,
                           GL.GL_UNSIGNED_BYTE, np.ascontiguousarray(data[r0:r1]))
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, prev_align)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        job["row"] = r1
        if r1 >= data.shape[0]:
            job["data"] = None
            return True
        return False

    def adopt_moon_texture(self, kind: str, job: dict) -> None:
        attr = "moon_color_tex" if kind == "color" else "moon_normal_tex"
        self.delete_texture(getattr(self, attr, 0))
        setattr(self, attr, job["tex"])

    def set_moon_level_chain(self, kind: str, levels: list) -> None:
        """Troca a textura ``kind`` ('color' | 'normal') por uma cadeia nova."""
        tex = self.mip_texture(levels)
        attr = "moon_color_tex" if kind == "color" else "moon_normal_tex"
        self.delete_texture(getattr(self, attr, 0))
        setattr(self, attr, tex)

    @property
    def moon_ready(self) -> bool:
        return bool(getattr(self, "moon_color_tex", 0) and self.moon_normal_tex)

    def draw_moon_sphere(self, center, radius: float, e_scr, n_scr,
                         v2b: np.ndarray, sun_body, view_body,
                         gain: float = 1.0, earthshine: float = 0.0,
                         alpha: float = 1.0, relief: float = 1.0) -> None:
        """Desenha a Lua texturizada e sombreada.

        ``e_scr``/``n_scr``: direções do leste e do norte celestes na tela
        (pixels por unidade de raio); ``v2b``: matriz 3×3 que leva o ponto
        local (a, b, c) — a para leste, b para norte, c para o observador —
        ao referencial MOON_ME.
        """
        if not self.moon_ready:
            return
        cx, cy = float(center[0]), float(center[1])
        e = np.asarray(e_scr, np.float64) * radius * 1.03
        n = np.asarray(n_scr, np.float64) * radius * 1.03
        corners = [(-1.03, -1.03), (1.03, -1.03), (1.03, 1.03),
                   (-1.03, -1.03), (1.03, 1.03), (-1.03, 1.03)]
        data = np.array([[cx + a / 1.03 * e[0] + b / 1.03 * n[0],
                          cy + a / 1.03 * e[1] + b / 1.03 * n[1], a, b]
                         for a, b in corners], dtype=np.float32)
        prev_unit = int(GL.glGetIntegerv(GL.GL_ACTIVE_TEXTURE))
        GL.glActiveTexture(GL.GL_TEXTURE1)
        prev1 = int(GL.glGetIntegerv(GL.GL_TEXTURE_BINDING_2D))
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.moon_normal_tex)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        prev0 = int(GL.glGetIntegerv(GL.GL_TEXTURE_BINDING_2D))
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.moon_color_tex)
        u = self.u_moon
        GL.glUseProgram(self.prog_moon)
        GL.glUniform2f(u["u_viewport"], self._w, self._h)
        GL.glUniformMatrix3fv(u["u_v2b"], 1, GL.GL_TRUE,
                              np.ascontiguousarray(v2b, dtype=np.float32))
        GL.glUniform3f(u["u_sun"], *[float(x) for x in sun_body])
        GL.glUniform3f(u["u_view"], *[float(x) for x in view_body])
        GL.glUniform1i(u["u_color"], 0)
        GL.glUniform1i(u["u_normal"], 1)
        GL.glUniform1f(u["u_gain"], float(gain))
        GL.glUniform1f(u["u_earthshine"], float(earthshine))
        GL.glUniform1f(u["u_alpha"], float(alpha))
        GL.glUniform1f(u["u_relief"], float(relief))
        self.batch_moon.upload(data)
        GL.glBindVertexArray(self.batch_moon.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(data))
        GL.glBindTexture(GL.GL_TEXTURE_2D, prev0)
        GL.glActiveTexture(GL.GL_TEXTURE1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, prev1)
        GL.glActiveTexture(prev_unit)

    def delete_texture(self, tex: int) -> None:
        """Libera uma textura da GPU (usado pela evicção do cache LRU)."""
        if tex:
            GL.glDeleteTextures([tex])

    def set_mw_texture(self, rgb: np.ndarray) -> None:
        """Envia a textura da Via Láctea (H,W,3 uint8) para a GPU.

        Placas com limite de textura menor que a imagem (6144 px desde a
        v0.16) recebem uma versão reduzida por amostragem.
        """
        limit = int(GL.glGetIntegerv(GL.GL_MAX_TEXTURE_SIZE) or 4096)
        step = 1
        while rgb.shape[1] // step > limit:
            step += 1
        if step > 1:
            rgb = rgb[::step, ::step]
        h, w, _ = rgb.shape
        rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
        if self.mw_texture:
            GL.glDeleteTextures([self.mw_texture])
        self.mw_texture = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.mw_texture)
        # GL_UNPACK_ALIGNMENT é estado GLOBAL do contexto: deixá-lo em 1
        # corrompe o upload do atlas de glifos do QPainter (rótulos ilegíveis).
        prev_align = int(GL.glGetIntegerv(GL.GL_UNPACK_ALIGNMENT))
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glTexImage2D(
            GL.GL_TEXTURE_2D, 0, GL.GL_RGB8, w, h, 0,
            GL.GL_RGB, GL.GL_UNSIGNED_BYTE, rgb,
        )
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, prev_align)
        GL.glGenerateMipmap(GL.GL_TEXTURE_2D)
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER,
            GL.GL_LINEAR_MIPMAP_LINEAR,
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT
        )
        GL.glTexParameteri(
            GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE
        )
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

    def draw_textured_triangles(self, pos: np.ndarray, uv: np.ndarray,
                                alpha: float, texture: int | None = None,
                                additive: bool = False) -> None:
        """Triângulos texturizados.

        pos (3T,2) px · uv (3T,2) — trincas consecutivas formam triângulos.
        ``additive`` soma luz ao fundo (usado nas imagens de céu profundo,
        onde o preto do levantamento simplesmente não contribui).
        """
        tex_id = self.mw_texture if texture is None else texture
        if len(pos) == 0 or not tex_id:
            return
        data = np.concatenate(
            [pos.astype(np.float32), uv.astype(np.float32)], axis=1
        )
        # O QPainter do Qt mantém o atlas de glifos ligado na unidade ativa;
        # trocar o binding sem restaurar apaga o texto dos rótulos.
        prev_unit = int(GL.glGetIntegerv(GL.GL_ACTIVE_TEXTURE))
        GL.glActiveTexture(GL.GL_TEXTURE0)
        prev_tex = int(GL.glGetIntegerv(GL.GL_TEXTURE_BINDING_2D))

        GL.glUseProgram(self.prog_tex)
        GL.glUniform2f(self.u_vp_tex, self._w, self._h)
        GL.glUniform1i(self.u_tex_sampler, 0)
        GL.glUniform1f(self.u_tex_alpha, float(alpha))
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
        if additive:
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE)
        self.batch_tex.upload(data)
        GL.glBindVertexArray(self.batch_tex.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(data))
        if additive:
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        GL.glBindTexture(GL.GL_TEXTURE_2D, prev_tex)
        GL.glActiveTexture(prev_unit)

    def fill_triangles(self, verts: np.ndarray, color) -> None:
        """Desenha triângulos preenchidos com cor uniforme.

        verts: (3T, 2) em pixels — trincas consecutivas formam triângulos.
        """
        if len(verts) == 0:
            return
        GL.glUseProgram(self.prog_fill)
        GL.glUniform2f(self.u_vp_fill, self._w, self._h)
        GL.glUniform4f(self.u_color_fill, color[0], color[1], color[2], color[3])
        self.batch_fill.upload(np.ascontiguousarray(verts, dtype=np.float32))
        GL.glBindVertexArray(self.batch_fill.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(verts))

    def draw_colored_triangles(self, verts: np.ndarray, colors: np.ndarray) -> None:
        """Triângulos com cor por vértice (gradiente do céu no crepúsculo).

        Usa o programa das linhas (posição + cor) com ``GL_TRIANGLES``.
        verts: (3T, 2) em pixels; colors: (3T, 4).
        """
        if len(verts) == 0:
            return
        data = np.empty((len(verts), 6), dtype=np.float32)
        data[:, :2] = verts
        data[:, 2:] = colors
        GL.glUseProgram(self.prog_lines)
        GL.glUniform2f(self.u_vp_lines, self._w, self._h)
        self.batch_lines.upload(data)
        GL.glBindVertexArray(self.batch_lines.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(data))

    def multiply_screen(self, width: int, height: int, rgb) -> None:
        """Multiplica todo o framebuffer por ``rgb`` (canal a canal).

        É o modo noturno: ``(1, 0, 0)`` mantém só o vermelho de tudo o que
        já foi desenhado — céu, estrelas e rótulos — sem tocar em nenhuma
        das rotinas de desenho. Blending padrão (``GL_ZERO, GL_SRC_COLOR``),
        suportado em qualquer driver.
        """
        self._w, self._h = float(width), float(height)
        GL.glViewport(0, 0, int(width), int(height))
        GL.glDisable(GL.GL_STENCIL_TEST)
        GL.glDisable(GL.GL_SCISSOR_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ZERO, GL.GL_SRC_COLOR)
        quad = np.array([[0, 0], [self._w, 0], [self._w, self._h],
                         [0, 0], [self._w, self._h], [0, self._h]], dtype=np.float32)
        self.fill_triangles(quad, (rgb[0], rgb[1], rgb[2], 1.0))
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

    def fill_polygons(self, rings: list[np.ndarray], color) -> None:
        """Preenche a união (com paridade) dos anéis dados em pixels.

        Duas passadas: (1) desenha leques por anel invertendo o stencil, sem
        escrever cor; (2) pinta um quad de tela inteira onde o stencil == 1.
        Funciona para polígonos côncavos e com buracos, sem triangulação.
        """
        rings = [r for r in rings if len(r) >= 3]
        if not rings:
            return
        verts = np.concatenate(rings).astype(np.float32)

        GL.glEnable(GL.GL_STENCIL_TEST)
        GL.glClear(GL.GL_STENCIL_BUFFER_BIT)
        GL.glColorMask(GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE)
        GL.glStencilFunc(GL.GL_ALWAYS, 0, 1)
        GL.glStencilOp(GL.GL_KEEP, GL.GL_KEEP, GL.GL_INVERT)
        GL.glStencilMask(0xFF)

        GL.glUseProgram(self.prog_fill)
        GL.glUniform2f(self.u_vp_fill, self._w, self._h)
        GL.glUniform4f(self.u_color_fill, 0, 0, 0, 0)
        self.batch_fill.upload(verts)
        GL.glBindVertexArray(self.batch_fill.vao)
        offset = 0
        for r in rings:
            GL.glDrawArrays(GL.GL_TRIANGLE_FAN, offset, len(r))
            offset += len(r)

        # passada 2: quad de tela inteira
        GL.glColorMask(GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE)
        GL.glStencilFunc(GL.GL_EQUAL, 1, 1)
        GL.glStencilOp(GL.GL_KEEP, GL.GL_KEEP, GL.GL_KEEP)
        quad = np.array(
            [[0, 0], [self._w, 0], [self._w, self._h], [0, self._h]],
            dtype=np.float32,
        )
        GL.glUniform4f(self.u_color_fill, color[0], color[1], color[2], color[3])
        self.batch_fill.upload(quad)
        GL.glDrawArrays(GL.GL_TRIANGLE_FAN, 0, 4)
        GL.glDisable(GL.GL_STENCIL_TEST)
