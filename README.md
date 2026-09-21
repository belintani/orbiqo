# Orbiqo

**Orbiqo** é um protocolo e uma demonstração de código 2D radial para *touchpoints* circulares: broches, crachás, perfis, selos e superfícies redondas. Em vez de impor um quadrado sobre uma face circular, o símbolo mantém um centro reservado para uma marca, foto ou estado, com os dados nos anéis periféricos.

> **Estado do protocolo:** Draft 0.6 (`format_version = 5`). O repositório contém validação digital reproduzível; não faz alegações de leitura física, capacidade superior universal ou tolerância geral à oclusão.

## O que há neste repositório

| Área | Conteúdo |
|---|---|
| `client/` e `server/` | Orbiqo Lab: criação, leitura, comparação e benchmarks por tRPC. |
| `server/python/native/` | Codec, renderer, decoder e visão C++17 usados pelo runtime de produção. |
| `server/orbiqoNative.ts` | Adapter Node que chama os executáveis nativos sem iniciar Python. |
| `server/python/vendor/radialcode/` | Implementação de referência RadialCode, usada como oráculo de compatibilidade e auditoria. |
| `benchmark/` | Runners, fixtures, resultados e metodologia de benchmarks digitais reproduzíveis. |
| `docs/` | Decisões de produto, método de oclusão, perfis de proteção e avaliação da migração nativa. |
| `spec/` | Materiais de protocolo, vetores e licença da especificação. |

## Princípios de produto

O Orbiqo não se apresenta como substituto universal de QR, Aztec ou JAB. A proposta é de composição e identidade: usar a forma circular já disponível, preservar o sujeito no centro e oferecer uma ação digital nos anéis.

O centro reservado é uma área não funcional do formato. Quando utilizado, ele não esconde payload sob uma logo. A paleta também é parte do contrato do símbolo; não há promessa de que qualquer combinação de cores será decodificável.

## Início rápido

O Lab requer Node.js 22+, um compilador C++17 e as bibliotecas nativas usadas pelo runtime: zlib, PNG, JPEG, WebP, FreeType e ZXing-C++. Para executar os gates de compatibilidade, benchmarks e visão da referência, use Python 3.11+ em um ambiente virtual.

```bash
pnpm install
pnpm dev
```

Para preparar também a referência e os gates locais:

```bash
python3 -m venv .ci-venv
.ci-venv/bin/pip install -e "server/python/vendor/radialcode[vision]" requests zxing-cpp
export PATH="$PWD/.ci-venv/bin:$PATH"

pnpm install --frozen-lockfile
pnpm check
pnpm test
pnpm build
```

O `Dockerfile` compila o runtime C++17, os adapters externos QR/Aztec/JAB e o runtime oficial JAB. A imagem de produção não instala Python, o venv ou bindings Python.

## Runtime de produção e referência

O runtime de produção é **exclusivamente C++17**. O Node chama diretamente `orbiqo_native` para geração, renderização, leitura, sizing e catálogo de identidades. O comparador chama `orbiqo_external_compare` para QR, Aztec e JAB. As rotas de produção não importam nem iniciam o bridge Python.

O C++ implementa o framing do Draft 0.6, CRC32C, BCH, Reed–Solomon, interleaving, máscaras, paletas, geometrias Micro 1–4 e Small–XL, SVG, PNG, centros textuais e imagens PNG/JPEG/WebP, além de decode canônico e visão digital frontal/perspectiva.

A implementação Python vendorizada permanece no repositório como **oráculo de compatibilidade**. Ela gera fixtures, executa gates de equivalência e sustenta auditorias e benchmarks. Python não é fallback silencioso do produto e não faz parte da imagem de produção.

A decisão, os contratos Node–C++ e os limites da migração estão em [`docs/NATIVE_CODEC_MIGRATION.md`](docs/NATIVE_CODEC_MIGRATION.md).

## Benchmarks e evidências

Os benchmarks são **digitais e reproduzíveis**. Eles separam encode lógico, produção completa de PNG, decode, capacidade e degradações. Perfis de proteção são comparados internamente antes do contexto externo com QR, Aztec e JAB; os perfis e toolchains não são equivalentes.

No benchmark lógico por ECC e geometria, 23 das 28 combinações do Draft 0.6 foram medidas. Cinco são impossíveis por capacidade normativa nas geometrias Micro 1 e Micro 2. Entre as combinações válidas, a mediana observada do C++ foi **−49,01% no encode lógico** e **−97,69% no decode lógico**. Esses números excluem PNG, SVG, processo externo e visão.

Na produção completa com processo incluído, a medição anterior registrou **−51,98%** no tempo de encode mais PNG em Small e **−56,32%** em Medium. O decode canônico ficou **−85,23%** e **−73,90%**, respectivamente. São números de uma máquina, uma resolução e um corpus específicos; não são garantias de dispositivo.

A matriz visual digital final passou em **26/26 casos** nativos no corpus principal e em **44/44 casos** na matriz ampliada com blur, downsample, brilho, rotação, compressão e oclusões localizadas. A nova matriz sintética de câmera passou em **20/20 casos nativos** com reamostragem, resposta de cor, vinheta, ruído, JPEG, brilho difuso e oclusões circulares, elípticas e arredondadas. A referência Python passou 19/20 nessa última matriz, com um limite conhecido no caso Small com oclusão circular de 6%. Esses resultados são digitais e específicos dos corpora; não equivalem a uma garantia geral de câmera, impressão ou qualquer ângulo.

Consulte [`docs/NATIVE_CODEC_MIGRATION.md`](docs/NATIVE_CODEC_MIGRATION.md) para os parâmetros completos, resultados por geometria e as limitações declaradas.

## CI pública

O workflow [`Orbiqo CI`](.github/workflows/ci.yml) instala dependências nativas, compila JAB e C++, executa os adapters externos, compara o codec C++ com a referência Python, roda as matrizes visuais e fecha com typecheck, Vitest e build de produção.

A referência Python é instalada em `.ci-venv` e esse ambiente é exportado para o `PATH` da execução. Isso é necessário porque alguns testes Node iniciam o bridge Python apenas para validar contratos legados; esse caminho de teste não altera o runtime de produção C++.

A publicação do runtime nativo foi feita no commit `30d8ff5`. O primeiro run remoto confirmou que todos os gates nativos passaram e revelou apenas a ausência de `requests` no `python3` usado pelos testes Node. O workflow foi corrigido para usar o venv correto. O segundo run, no commit `f7e157a`, terminou com sucesso.

## Próximos passos

1. Criar a primeira tag de release mantendo explícito o estado Draft 0.6.
2. Ampliar o corpus de visão C++ com capturas físicas ou imagens de câmera reais, sem misturar essa evidência com a matriz sintética digital.
3. Repetir o benchmark Python versus C++ em mais máquinas e resoluções, mantendo separadas as medições lógicas e de produção completa.
4. Só depois avaliar otimizações de visão ou mudanças normativas; o Python continuará como oracle até que novos gates de compatibilidade sejam aprovados.

## Licenças e atribuição

O código da implementação de referência RadialCode está sob **Apache License 2.0**. Os avisos obrigatórios estão em [`LICENSE`](LICENSE), [`NOTICE`](NOTICE) e [`ATTRIBUTION.md`](ATTRIBUTION.md). O contrato atual está em [`spec/RADIALCODE-DRAFT-0.6.md`](spec/RADIALCODE-DRAFT-0.6.md), sob a licença própria em [`spec/LICENSE`](spec/LICENSE).

Ao redistribuir ou modificar a referência, preserve esses arquivos e seus termos. O nome **Orbiqo** identifica o produto e protocolo neste repositório; **RadialCode** identifica a implementação de referência técnica.

## Referências

[1]: https://github.com/belintani/orbiqo "Orbiqo repository"
[2]: https://github.com/belintani/orbiqo/actions "Orbiqo GitHub Actions"
