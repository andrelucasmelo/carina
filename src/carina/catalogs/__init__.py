"""Catálogos de dados do Carina, todos carregados de bases LOCAIS.

Estrelas (HYG + catálogo profundo ATHYG/Tycho-2), objetos de céu profundo
(SQLite com Messier, Caldwell, NGC/IC, SH2, Barnard, Melotte, LDN,
Collinder, VdB e Abell), geometria do céu (linhas/limites de constelação,
Via Láctea, grades), imagens de levantamento, equipamentos do usuário e
nomes de constelações. Nada aqui acessa a rede em tempo de execução — os
downloads acontecem nos scripts de build (ADR-012).
"""
