# Perfil Robust de oclusão — Orbiqo Protocol Draft 0.6

## Escopo

Este documento descreve uma validação **digital-only** e reproduzível do Orbiqo `format_version=5`. Ela existe separadamente do benchmark normalizado de capacidade e latência, que continua usando o perfil Balanced. Seu objetivo limitado é medir como o formato 5 se comporta sob uma oclusão digital localizada, sem transformar o resultado em uma alegação geral sobre QR, Aztec ou JAB.

> O resultado aplica-se apenas ao corpus, ao raster e aos perfis abaixo. Ele não representa impressão, captura por câmera, superfícies curvas, iluminação real, nem suporte genérico a logo sobre células de dados.

## Método

| Parâmetro | Valor |
| --- | --- |
| Implementação | RadialCode `0.1.0a6` local |
| Protocolo | Orbiqo Protocol Draft 0.6 / `format_version=5` |
| Alfabeto | COLOR4 |
| Payload por ensaio | 64 bytes |
| Padrões | `benchmark`, `counter`, `periodic` |
| Oclusão | 6% digital, sem blur, ruído, JPEG, downsample ou ajuste de cor |
| Posições | quatro posicionamentos determinísticos, seeds 101–104 |
| Critério de sucesso | igualdade exata do payload decodificado |
| Perfis avaliados | Balanced RS(255,191), Robust RS(255,159), Extreme RS(255,127) |

O script [`benchmark/validate_format5_occlusion.py`](../benchmark/validate_format5_occlusion.py) produz o artefato bruto [`benchmark/results/format5_occlusion_validation.json`](../benchmark/results/format5_occlusion_validation.json). O renderer e decoder usados são os da implementação Python real; não há geração ou leitura simulada no Lab.

## Resultados do Orbiqo

| ECC | Padrão | Sucessos | Ensaios |
| --- | --- | ---: | ---: |
| Balanced | benchmark | 1 | 4 |
| Balanced | counter | 0 | 4 |
| Balanced | periodic | 1 | 4 |
| Robust | benchmark | 3 | 4 |
| Robust | counter | 3 | 4 |
| Robust | periodic | 3 | 4 |
| Extreme | benchmark | 0 | 4 |
| Extreme | counter | 0 | 4 |
| Extreme | periodic | 0 | 4 |

No perfil Robust, cada um dos três padrões atingiu **3/4**. Isso mostra uma margem observada maior que Balanced neste corpus, ao custo do perfil RS(255,159) mais redundante. O perfil Extreme não superou Robust; portanto, não se presume monotonicidade entre níveis de ECC nesse caminho de visão e o resultado Extreme deve continuar visível como limitação.

## Relação com as linhas de base

O benchmark de oclusão original, Balanced e de payload único, registrou QR em 3/4 e Aztec/JAB em 0/4. A validação Robust acima usa um perfil ECC diferente e três padrões, por isso não deve ser fundida à tabela principal de capacidade ou apresentada como comparação ECC-equivalente.

A formulação permitida é a seguinte:

> No corpus digital controlado de 6% de oclusão, com o perfil Orbiqo Robust e três padrões de 64 B, o Orbiqo registrou 3/4 por padrão; as linhas de base Aztec e JAB haviam registrado 0/4 e QR 3/4 na avaliação Balanced original.

Não são permitidas inferências de que Orbiqo seja superior de forma geral, de que a redundância seja gratuita, ou de que imagens/logotipos arbitrários possam cobrir dados sem validação específica.

## Limitações e próximos ensaios

Os resultados usam um único canvas digital e somente quatro posições por padrão. A melhoria do formato 5 é redundância de header e tratamento de erasures, não um mecanismo de reserva de área para logomarca. Qualquer próximo ciclo deve manter a validação física separada e só ampliar a afirmação após ensaios reprodutíveis de impressão/câmera aprovados.
