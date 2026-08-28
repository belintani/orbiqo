# Oclusão e posicionamento do Orbiqo

## Diferença honesta de produto

Orbiqo não deve ser apresentado como mais transparente que QR, Aztec ou JAB. A proposta observável é outra: um símbolo **circular**, com **colunas polares contínuas**, identidades COLOR4 registradas, geometria Micro para cargas pequenas, centro editorial e uma implementação de referência aberta para o próprio protocolo.

O centro não funcional já é uma escolha relevante de produto: texto ou uma imagem podem ocupar o círculo interno sem sobrepor células de dados. Isso oferece uma integração de marca que não depende de “danificar e recuperar” o payload.

## Oclusão no formato atual

QR Code foi projetado com níveis de Reed–Solomon para restaurar dados após dano; a DENSO documenta quatro níveis e aproximadamente 7%, 15%, 25% e 30% de restauração sobre os codewords totais. [1]

O Orbiqo atual também usa Reed–Solomon e pode encaminhar células de baixa confiança como *erasures*. Contudo, isso **não é um recurso de oclusão de marca**. Os metadados críticos ocupam os anéis de header entre os raios 0,26–0,33, enquanto a área de dados começa no raio 0,41. Logo, o centro seguro atual (raio 0,20) não cobre dados; ampliar uma oclusão circular central além de aproximadamente 0,33 alcançaria o header antes de alcançar apenas o payload.

| Forma de marca | Estado atual | Custo esperado |
| --- | --- | --- |
| Texto ou imagem dentro do centro de raio 0,20 | Suportado | Nenhuma perda de capacidade |
| Logo central maior que o centro reservado | Não suportado | Pode destruir header e impedir a leitura antes do RS |
| Janela lateral sobre dados | Não suportado como recurso | Requer reserva explícita ou erasures confiáveis |

O benchmark canônico atual apresenta uma indicação, não uma garantia física: em Small/30 mm/300 dpi, cinco posições sintéticas tiveram 100% de sucesso até 3% de oclusão da imagem, 80% a 4% e 20% a 6%. A medição de oclusão deliberada por tipo e posição será registrada abaixo antes de qualquer decisão de formato.

## Medição controlada — 2026-08-26

O teste `tools/assess_occlusion_layout.py` usou Small/30 mm, COLOR4, ECC Balanced, 600 dpi e três payloads determinísticos. Ele mede somente a imagem canônica frontal; não é uma alegação para câmera, impressão ou perspectiva. Os dados brutos estão em `benchmark/results/occlusion_layout_assessment.json`.

| Cenário | Resultado | Leitura |
| --- | --- | --- |
| Círculo central até raio 0,20 | 3/3 | Centro reservado permanece seguro; nenhum RS corrigido |
| Círculo até raio 0,28 | 3/3 | Toca a borda inicial do header neste raster, mas não é uma área a ser prometida |
| Círculo até raio 0,34 | 0/3 | O header perde separação luminosa antes de o payload poder ser recuperado |
| Janela de dados de 10°, 20° e 30° | 3/3 em cada | O RS recupera 7–40 bytes de erasure em imagens canônicas limpas |

Esses resultados mostram que existe margem de ECC, mas **não uma feature de logo sobre dados**. A janela lateral é conhecida apenas pelo experimento; no formato atual o decoder não recebe uma abertura normativa no header, e ruído, JPEG, impressão, câmera e perspectiva diminuiriam a margem disponível.

## Decisão deste ciclo

**Adiar a oclusão sobre dados.** A alternativa robusta exigiria uma nova revisão de formato para reservar uma abertura conhecida, sinalizá-la antes da leitura do payload e revalidar encoder, decoder, visão, capacidades, golden vectors e benchmarks. Isso não é uma alteração cosmética.

O posicionamento atual deve enfatizar o que já é verdadeiro: o Orbiqo foi desenhado com um centro editorial que recebe marca ou imagem **sem encobrir células de payload**. O produto não deve prometer logo sobre a área de dados nem comparar essa escolha à recuperação por dano de outros códigos.

## Referências

[1]: https://www.qrcode.com/en/about/error_correction.html "DENSO WAVE — QR Code Error Correction Feature"
