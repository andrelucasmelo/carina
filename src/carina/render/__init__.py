"""Camada de renderização OpenGL do Carina.

O :mod:`glrenderer` encapsula os shaders e buffers (pontos, linhas,
polígonos por stencil e triângulos texturizados); o :mod:`dsoimages`
gerencia o cache de texturas das imagens de levantamento com
decodificação assíncrona. Nenhum módulo daqui conhece astronomia — eles
recebem coordenadas de tela prontas.
"""
