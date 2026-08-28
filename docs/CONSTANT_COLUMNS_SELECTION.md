# Seleção Constant Columns — Orbiqo Draft 0.4

O proprietário escolheu **Constant Columns** por apresentar a linguagem visual mais linear entre os protótipos: todas as fronteiras angulares permanecem no mesmo raio ao atravessar os anéis de dados. A seleção abaixo maximiza a capacidade útil dentro dessa direção estética, sob o proxy digital de área ocupada de **900 × 900 px** e pitch mínimo de **7 px**.

![Parâmetros finais Constant Columns](/manus-storage/selected_constant_columns_d2fb6986.png)

| Geometria | Anéis | Colunas constantes | Raio interno dos dados | Células COLOR4 | Pitch mínimo | Capacidade Balanced | Variação contra Draft 0.3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Small | 12 | 160 | 0,41 | 1.920 | 7,61 px | 334 B | +151 B (+82,5%) |
| Medium | 18 | 168 | 0,41 | 3.024 | 7,13 px | 546 B | +136 B (+33,2%) |
| Large | 24 | 168 | 0,41 | 4.032 | 7,08 px | 734 B | −28 B (−3,7%) |
| XL | 30 | 168 | 0,41 | 5.040 | 7,04 px | 922 B | −330 B (−26,4%) |

> **Decisão visual:** a redução de capacidade em Large e principalmente XL é aceita como consequência explícita da identidade Constant Columns. O layout mantém **100% de alinhamento entre fronteiras angulares adjacentes** e elimina a progressão de larguras e fases que criava a aparência de escamas no Draft 0.3.

## Validação rigorosa

A busca preliminar com caps arredondados indicou 96/156/168/168 colunas, mas revelou uma causa estrutural: os caps invadiam células angulares vizinhas e recriavam a sobreposição que o redesenho deveria remover. O renderer Draft 0.4 passou então a usar pontas planas (`butt`) apenas em Constant Columns, preservando formatos legados. Com a sobreposição eliminada, o gate de capacidade máxima aprovou 172 colunas no Small. O gate de produto, porém, mostrou perda em JPEG 40 e ruído 8; por isso o parâmetro final recuou para **160 colunas**, o maior candidato que passou 28/28 cenários não oclusivos e 24/24 cenários de capacidade máxima. Medium/Large/XL permanecem em **168/168/168**.

Cada geometria final foi testada com quatro padrões determinísticos de bytes — aritmético, zeros, `0xFF` e alternado `0xAA/0x55` — em seis perfis digitais: limpo, blur 1,2, JPEG 55, downsample 0,55 e ruído sigma 7 com duas seeds. Todos os casos passaram por detecção completa de imagem e exigiram igualdade exata do payload.

| Geometria | Bytes por tentativa | Padrões | Perfis | Resultado exato |
| --- | ---: | ---: | ---: | ---: |
| Small | 183 | 4 | 6 | 24/24 |
| Medium | 420 | 4 | 6 | 24/24 |
| Large | 734 | 4 | 6 | 24/24 |
| XL | 922 | 4 | 6 | 24/24 |
| **Total** | — | — | — | **96/96** |

Os resultados brutos estão em [`validation_results.json`](../benchmark/results/constant_columns/validation_results.json). A busca preliminar permanece disponível em [`column_search.json`](../benchmark/results/constant_columns/column_search.json), e as tentativas do recuo rigoroso de Small/Medium estão em [`strict_search.json`](../benchmark/results/constant_columns/strict_search.json).

## Consequência normativa

Constant Columns não é um skin. Ele altera a quantidade e o endereço físico das células, portanto precisa de uma nova versão de formato no header. O Draft 0.4 deve emitir **format version 3**, selecionar parâmetros normativos por geometria e manter o decoder capaz de reconstruir os layouts legados dos formats 1 e 2. Os raios e números de colunas não serão aceitos como parâmetros livres do header.

Esta validação é **somente digital**. Ela não sustenta alegações sobre impressão, câmera física, substratos, iluminação real ou equivalência perfeita de ECC com QR, Aztec ou JAB. A comparação com esses formatos será atualizada somente após a implementação canônica do Draft 0.4 e a reexecução integral do benchmark normalizado.
