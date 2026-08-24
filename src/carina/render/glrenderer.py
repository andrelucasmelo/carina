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
from OpenGL import GL

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
out vec4 frag;
void main() {
    vec2 d = gl_PointCoord - vec2(0.5);
    float r = length(d) * 2.0;
    float alpha = pow(clamp(1.0 - r, 0.0, 1.0), 1.4);
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


def _compile(vs_src: str, fs_src: str) -> int:
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
        data = np.ascontiguousarray(data, dtype=np.float32)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_STREAM_DRAW)


class GLRenderer:
    def __init__(self) -> None:
        self._ready = False

    def initialize(self) -> None:
        self.prog_points = _compile(_POINTS_VS, _POINTS_FS)
        self.prog_lines = _compile(_LINES_VS, _LINES_FS)
        self.prog_fill = _compile(_FILL_VS, _FILL_FS)
        self.batch_points = _Batch(self.prog_points, [(0, 2), (1, 1), (2, 4)])
        self.batch_lines = _Batch(self.prog_lines, [(0, 2), (1, 4)])
        self.batch_fill = _Batch(self.prog_fill, [(0, 2)])
        self.u_vp_points = GL.glGetUniformLocation(self.prog_points, "u_viewport")
        self.u_vp_lines = GL.glGetUniformLocation(self.prog_lines, "u_viewport")
        self.u_vp_fill = GL.glGetUniformLocation(self.prog_fill, "u_viewport")
        self.u_color_fill = GL.glGetUniformLocation(self.prog_fill, "u_color")
        GL.glEnable(GL.GL_PROGRAM_POINT_SIZE)
        size_range = GL.glGetFloatv(GL.GL_ALIASED_POINT_SIZE_RANGE)
        self.max_point_size = float(size_range[1])
        self._ready = True

    # ------------------------------------------------------------------
    def begin_frame(self, width: int, height: int, clear_rgb) -> None:
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
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

    # ------------------------------------------------------------------
    def draw_points(self, interleaved: np.ndarray) -> None:
        """interleaved: (N,7) = x, y, tamanho_px, r, g, b, a"""
        if len(interleaved) == 0:
            return
        GL.glUseProgram(self.prog_points)
        GL.glUniform2f(self.u_vp_points, self._w, self._h)
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
