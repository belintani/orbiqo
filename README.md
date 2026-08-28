# Orbiqo

**Orbiqo** é um protocolo e uma demonstração de código 2D radial para *touchpoints* circulares: broches, crachás, perfis, selos e superfícies redondas. Em vez de impor um quadrado sobre uma face circular, o símbolo mantém um centro reservado não funcional para uma marca, foto ou estado, com dados nos anéis periféricos.

> **Estado do protocolo:** Draft 0.6 (`format_version = 5`). O Orbiqo Lab é uma demonstração técnica ativa; não faça alegações de leitura física, capacidade superior universal ou tolerância geral à oclusão a partir deste repositório.

## O que há neste repositório

| Área | Conteúdo |
|---|---|
| `client/` e `server/` | Orbiqo Lab: criação, leitura, comparação e benchmarks por tRPC. |
| `server/python/` | Bridge de produção e a implementação de referência vendorizada. |
| `server/python/vendor/radialcode/` | Implementação de referência RadialCode, sob Apache-2.0 e aviso preservado. |
| `benchmark/` | Runners, resultados e metodologia de benchmarks digitais reproduzíveis. |
| `docs/` | Decisões de produto, método de oclusão, perfis de proteção e avaliação nativa. |
| `spec/` | Materiais de protocolo e licença da especificação. |

## Princípios de produto

O Orbiqo não se apresenta como substituto universal de QR, Aztec ou JAB. A proposta é de composição e identidade: usar a forma circular já disponível, preservar o sujeito no centro e oferecer uma ação digital nos anéis.

O centro reservado não é uma área de payload oculta por um logo. Quando utilizado, ele é excluído da área funcional pelo formato. A escolha por uma paleta validada também é parte do símbolo, não uma promessa de que qualquer combinação de cores será decodificável.

## Início rápido

O Lab requer Node.js 22+, Python 3.11+ e as dependências Python declaradas na referência. Para o caminho C++ experimental de raster, o ambiente também requer compilador C++17 e `libpng`.

```bash
pnpm install
pnpm dev
```

O ambiente de produção é descrito no `Dockerfile`. Ele instala Python, a referência vendorizada, JAB para o modo Compare e o binário de raster C++ experimental.

## Implementação de referência e C++ experimental

A **referência** é Python: ela contém encoding, decoding, visão, SVG, suporte a centro de texto/imagem e as decisões de compatibilidade do formato. Há um rasterizador C++17 experimental e opcional para PNGs com centro vazio; ele não substitui a referência, não aparece como caminho público padrão e deve manter paridade de decode antes de qualquer promoção.

Os dados de comparação do raster são gerados em `benchmark/benchmark_native_renderer.py`. Consulte [`docs/NATIVE_RENDERER_EVALUATION.md`](docs/NATIVE_RENDERER_EVALUATION.md) para escopo, resultados e limites.

## Benchmarks e limites

Os benchmarks são **digitais e reproduzíveis**. Eles distinguem encoder puro, produção completa de raster, decode, capacidade e degradações. Perfis de proteção são comparados internamente antes do contexto externo com QR, Aztec e JAB.

O resultado de oclusão Robust é limitado ao corpus documentado: 64 bytes, 6% de oclusão digital, quatro posições determinísticas e três padrões de payload. Ele não estabelece tolerância a logos arbitrários, impressão, iluminação ou câmeras físicas. Consulte:

- [`docs/ECC_PROFILE_BENCHMARK.md`](docs/ECC_PROFILE_BENCHMARK.md)
- [`docs/OCCLUSION_ROBUST_PROFILE.md`](docs/OCCLUSION_ROBUST_PROFILE.md)
- [`docs/NATIVE_RENDERER_EVALUATION.md`](docs/NATIVE_RENDERER_EVALUATION.md)

## Validação

```bash
pnpm test
pnpm check
pnpm build

cd server/python/vendor/radialcode
PYTHONPATH=src pytest -q
```

## Licenças e atribuição

O código da implementação de referência RadialCode está sob **Apache License 2.0**. Os avisos obrigatórios estão em [`LICENSE`](LICENSE), [`NOTICE`](NOTICE) e [`ATTRIBUTION.md`](ATTRIBUTION.md). O contrato atual está em [`spec/RADIALCODE-DRAFT-0.6.md`](spec/RADIALCODE-DRAFT-0.6.md), sob a licença própria em [`spec/LICENSE`](spec/LICENSE).

Ao redistribuir ou modificar a referência, preserve esses arquivos e seus termos. O nome **Orbiqo** identifica o produto e protocolo neste repositório; **RadialCode** identifica a implementação de referência técnica.
