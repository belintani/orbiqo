# RadialCode

**RadialCode** é uma simbologia 2D radial open source para transportar URLs, texto UTF-8 e dados binários. O projeto combina bootstrap monocromático, payload COLOR4, correção Reed–Solomon, referências cromáticas internas e renderização vetorial em diâmetro parametrizado.

> **Estado:** `0.1.0a6`, Protocol Draft 0.6 / `format_version=5`. Esta é uma versão de pesquisa e interoperabilidade, não uma recomendação de substituir QR Code em produção sem ensaios físicos próprios.

![Exemplo RadialCode COLOR4 Micro 2](vectors/draft-0.5/color4_url_micro2.png)

## Características

A implementação inclui encoder e decoder de referência em Python, saída SVG/PNG, seis geometrias registradas, diâmetro arbitrário, payload COLOR4 com fallback MONO2, BCH no header, Reed–Solomon com erasures, CRC32C, máscaras visuais, golden vectors e pipeline OpenCV para guard, pose e homografia.

| Perfil | Anéis de dados | Diâmetro sugerido | Capacidade COLOR4 Balanced | Pitch no diâmetro sugerido |
| --- | ---: | ---: | ---: | ---: |
| Micro 1 | 1 | 16 mm | 0 bytes (16 bytes em Fast) | 4,00 mm |
| Micro 2 | 2 | 16 mm | 26 bytes | 2,00 mm |
| Micro 4 | 4 | 18 mm | 106 bytes | 1,125 mm |
| Small | 12 | 30 mm | 334 bytes | 0,625 mm |
| Medium | 18 | 40 mm | 546 bytes | 0,556 mm |
| Large | 24 | 50 mm | 734 bytes | 0,521 mm |
| XL | 30 | 70 mm | 922 bytes | 0,583 mm |

As capacidades acima incluem o frame interno, CRC e redundância do perfil Balanced. Qualquer diâmetro positivo pode ser solicitado; o encoder emite um aviso quando o pitch nominal fica abaixo do limite provisório de impressão de 0,50 mm.

## Instalação

```bash
python -m pip install -e .
```

Para habilitar detecção e homografia em imagens de câmera, instale o extra de visão:

```bash
python -m pip install -e '.[vision]'
```

Para desenvolvimento e testes:

```bash
python -m pip install -e '.[dev,vision]'
pytest -q
```

## Linha de comando

O gerador aceita texto, URLs, arquivos binários e dados enviados por `stdin`. O exemplo abaixo cria SVG e PNG COLOR4 em 40 mm:

```bash
radialcode-generate \
  --text 'https://example.org/demo' \
  --payload-type url \
  --geometry medium \
  --diameter-mm 40 \
  --ecc balanced \
  --center-text RC \
  --output demo \
  --format both
```

Para decodificar uma fotografia ou cena com perspectiva:

```bash
radialcode-decode demo.png --json
```

Quando a imagem já está perfeitamente centralizada e frontal, a detecção pode ser ignorada:

```bash
radialcode-decode demo.png --canonical --geometry 2
```

A tabela de capacidade pode ser consultada sem gerar um símbolo:

```bash
radialcode-inspect --alphabet color4 --ecc balanced
```

## API Python

```python
from radialcode import EccLevel, RenderOptions, encode, save_png, save_svg
from radialcode.vision import decode_image

symbol = encode(
    "https://example.org/demo",
    geometry="auto",
    diameter_mm=42.0,
    ecc_level=EccLevel.BALANCED,
)
save_svg(symbol, "demo.svg", RenderOptions(center_text="RC"))
save_png(symbol, "demo.png", dpi=300, options=RenderOptions(center_text="RC"))

result = decode_image("demo.png")
print(result.decoded.text())
```

## Arquitetura

O bootstrap permanece monocromático para evitar dependência circular da calibração COLOR4. Um clock track espesso de 64 slots fornece sincronização angular. As três cópias internas do header BCH(63,45) descrevem versão física, geometria, alfabeto, paleta, ECC, máscara e comprimento; no `format_version=5`, uma quarta cópia BCH externa ocupa a faixa radial registrada 0,345–0,365 como redundância adicional de header. O guard preto externo detecta o símbolo e seus quatro entalhes informam a pose; ele não armazena a geometria. No Draft 0.6, os IDs Micro registram 1, 2 ou 4 anéis e o Auto fit os testa antes de Small–XL. O payload mantém frame versionado com CRC32C, Reed–Solomon GF(256), interleaving e permutação espacial.

![Arquitetura do encoder e decoder](assets/architecture.png)

A ampliação abaixo mostra o clock Draft 0.3 imediatamente ao redor do centro livre, agora com 64 slots claramente segmentados:

![Ampliação do clock track no símbolo Small de 30 mm](assets/clock_track_30mm_closeup.png)

## Validação atual

A suíte cobre os golden vectors dos Drafts 0.2, 0.3, 0.4, 0.5 e 0.6, além de header, geometria, capacidade, canal, renderer, framing, ECC, fuzzing e visão. O Draft 0.6 também testa a recuperação do header pela cópia BCH externa quando as três cópias internas estão indisponíveis. O benchmark de visão mantém duas regressões `xfail` para a pose sintética mais foreshortened. Consulte [`docs/SYNTHETIC_BENCHMARK.md`](docs/SYNTHETIC_BENCHMARK.md) e [`docs/PERSPECTIVE_BENCHMARK.md`](docs/PERSPECTIVE_BENCHMARK.md).

Fotografias reais em diferentes impressoras, papéis, iluminações e câmeras ainda são necessárias antes de declarar um envelope operacional físico. Falhas são explícitas: BCH, header inconsistente, RS irrecuperável, CRC inválido ou confiança insuficiente nunca devem ser tratadas como decode válido.

## Especificação e vetores

A especificação normativa atual está em [`spec/RADIALCODE-DRAFT-0.6.md`](spec/RADIALCODE-DRAFT-0.6.md). Os vetores correspondentes estão em [`vectors/draft-0.6/`](vectors/draft-0.6/). O decoder mantém compatibilidade de leitura com os vetores históricos de [`draft-0.2`](vectors/draft-0.2/), [`draft-0.3`](vectors/draft-0.3/), [`draft-0.4`](vectors/draft-0.4/) e [`draft-0.5`](vectors/draft-0.5/).

## Licenças e atribuição

O código é distribuído sob **Apache License 2.0**. A especificação e os diagramas autorais são distribuídos sob **CC BY 4.0**, cuja licença oficial exige atribuição razoável, indicação de alterações e referência à licença quando o material é compartilhado.[1]

A forma preferida de crédito é:

> Built with RadialCode — an open radial 2D code project.

Consulte [`ATTRIBUTION.md`](ATTRIBUTION.md), [`NOTICE`](NOTICE) e [`docs/LICENSE_POLICY.md`](docs/LICENSE_POLICY.md). Os símbolos gerados incluem metadados SVG de origem por padrão; o payload decodificado não depende dessa informação.

## Contribuição e segurança

Mudanças no formato exigem novo número de Design Draft, atualização dos golden vectors e testes de interoperabilidade. Consulte [`CONTRIBUTING.md`](CONTRIBUTING.md). Para vulnerabilidades ou formas de provocar decode incorreto, siga [`SECURITY.md`](SECURITY.md) em vez de abrir uma discussão pública com payloads sensíveis.

## Referências

[1]: https://creativecommons.org/licenses/by/4.0/legalcode.en "Creative Commons Attribution 4.0 International — Legal Code"
