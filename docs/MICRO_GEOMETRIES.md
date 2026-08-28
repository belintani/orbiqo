# Geometrias Micro do Orbiqo

O Protocol Draft 0.6 / `format_version=5` registra três contagens fixas de anéis coloridos para payloads pequenos. A geometria não fica no guard preto externo; ela é codificada no campo de três bits das cópias BCH do header monocromático. O formato 5 conserva as três cópias internas e acrescenta uma quarta cópia BCH externa como redundância de header.

| Geometria | ID | Anéis | Colunas | Capacidade COLOR4 Balanced | Diâmetro recomendado |
| --- | ---: | ---: | ---: | ---: | ---: |
| Micro 1 | 6 | 1 | 266 | 0 B (16 B Fast) | 16 mm |
| Micro 2 | 0 | 2 | 216 | 26 B | 16 mm |
| Micro 4 | 5 | 4 | 188 | 106 B | 18 mm |
| Small | 1 | 12 | 160 | 334 B | 30 mm |

O Auto fit calcula o frame após compressão e tenta Micro 1, Micro 2, Micro 4, Small, Medium, Large e XL nessa ordem, ignorando capacidades zero. Micro 1 é válido somente em COLOR4 Fast e transporta até 16 bytes. IDs não são ordenados numericamente porque Small–XL já ocupavam `1..4`.

Micro 1 passou 20/20 cenários de capacidade máxima Fast; Micro 2 e Micro 4 passaram 40/40 cenários. O gate de diâmetro usou quatro padrões de payload e cinco perfis digitais — clean, blur 1.2, JPEG 55, downsample 0.55 e ruído sigma 7 — a 600 dpi. Os primeiros diâmetros integralmente aprovados foram 16 mm para Micro 1/2 e 18 mm para Micro 4. Esses números não são um limite físico de impressão.

O guard externo é uma circunferência contínua com quatro entalhes funcionais de pose. O SVG já é vetorial; o raster rápido passou a antialiasar o guard mesmo quando o restante da cena usa 1×. As células Micro são setores anulares preenchidos, evitando artefatos diagonais de traços muito espessos.
