# Migração nativa C++ — runtime de produção

## Status atual

O Orbiqo agora possui um runtime de produção **exclusivamente nativo em C++17** para geração, renderização, leitura, sizing, catálogo de identidades e comparação externa. O Node chama diretamente `orbiqo_native` e `orbiqo_external_compare`; o router não importa nem executa o bridge Python.

A implementação Python vendorizada permanece no repositório apenas como **oráculo de compatibilidade, gerador de fixtures e ferramenta de benchmark/auditoria**. Ela não é fallback de produção, não é instalada na imagem Docker final e não é iniciada pelas rotas `generate`, `decode`, `recommendSizing`, `health`, `identities`, `capacities` ou `compareSymbols`.

## Escopo nativo

O núcleo C++ preserva o contrato do Draft 0.6 e dos formatos históricos suportados:

- framing com byte de controle, comprimento original de 24 bits e CRC32C;
- DEFLATE opcional via zlib;
- BCH(63,45,t=3), cópias físicas e voto bit a bit entre cópias;
- RS GF(256), interleaving/deinterleaving e posições de erasure;
- máscaras, paletas registradas, COLOR4 e MONO2;
- geometrias legadas dos formatos 1–2 e Constant Columns dos formatos 3–5;
- Micro 1, Micro 2, Micro 4, Small, Medium, Large e XL;
- geração de SVG e PNG, com quiet zone, guard, clock track, âncoras, células e centros;
- texto central via FreeType e imagens centrais PNG, JPEG ou WebP;
- decode direto de PNG, JPEG e WebP, incluindo modo canônico e visão frontal/perspectiva experimental;
- QR, Aztec e JAB no comparador externo, usando ZXing-C++ e o runtime oficial JAB.

O modelo geométrico compartilhado é produzido pelo codec C++ e consumido pelo renderer e pelo decoder. Isso evita manter uma tabela de geometria independente no caminho de produção.

## Contrato Node–C++

O adapter `server/orbiqoNative.ts` inicia somente os executáveis nativos. O protocolo textual é limitado a linhas ASCII, hex e base64 e usa os marcadores `ORBIQO_NATIVE_RESULT_V1` e `ORBIQO_EXTERNAL_RESULT_V1`.

As entradas públicas de backend aceitam apenas `native-cpp`. Valores históricos como `reference` e `native-experimental` não são mais opções válidas do produto. A seleção visual de renderer foi removida da tela Create: gerar, renderizar e ler são responsabilidades do runtime C++.

O comparador nativo normaliza cada símbolo para canvas de 1024×1024 px, com área ocupada de 900×900 px e interpolação nearest-neighbor, preservando o método usado no benchmark anterior. QR e Aztec são gerados e lidos por ZXing-C++; JAB é gerado e lido pelos binários oficiais vendorizados. Os perfis são explicitamente toolchain-specific e não são equivalentes entre si.

## Gates de compatibilidade

Os gates Python continuam sendo executados em desenvolvimento e CI para comparar o C++ com a referência, mas não fazem parte da imagem ou do caminho de produção.

`benchmark/test_native_codec.py` verifica 11 vetores cross-format, framing, RS concatenado e interleaved, channel packed, máscara, header BCH e corrupção controlada de símbolos e bits.

`benchmark/test_native_full.py` verifica as sete geometrias do formato 5 e o caso histórico do formato 1, incluindo SVG, PNG, decode nativo exato, centros textuais e imagens centrais. O decoder Python, quando usado nesse gate, é somente uma verificação independente do artefato C++.

`benchmark/validate_native_visual_matrix.py` continua registrando a matriz digital de Small e Medium com frontal, perspectiva, ruído, JPEG, WebP e oclusões localizadas. Na execução final desta fase, o resultado foi de **26/26 casos nativos recuperados**, igualando 26/26 na referência Python para esse corpus específico. A matriz ampliada em `benchmark/validate_native_visual_extended.py` acrescentou blur, downsample, brilho, rotação, compressão mais agressiva e quatro posições de oclusão. Ela também passou em **44/44 casos nativos e 44/44 casos da referência**. Isso é evidência digital local, não garantia geral de câmera, impressão ou qualquer ângulo.

O novo `benchmark/validate_native_visual_camera.py` acrescenta uma matriz sintética de câmera com reamostragem, resposta de cor quente e fria, gama, vinheta, ruído de sensor, pipeline combinado com JPEG, brilho difuso e três oclusões não retangulares. Foram executados 20 casos em Small e Medium. O C++ recuperou **20/20**. A referência recuperou 19/20 porque falhou no caso Micro 2/Small com oclusão circular de 6%; esse caso é registrado como limite conhecido da referência neste corpus e não como regressão do C++. A diferença não deve ser transformada em claim geral de robustez. O corpus continua sendo sintético e digital.

O comparador externo possui ainda um smoke test C++ próprio para QR, Aztec e JAB, exigindo round-trip binário exato e PNG válido. Esse teste não usa bindings Python.

## Desempenho

O benchmark de produção completa permanece separado do benchmark lógico in-process. A medição anterior, em Small e Medium, 600 DPI, payload binário de 67 bytes e inicialização do processo incluída, registrou:

| Geometria | Python encode + PNG | C++ encode + PNG | Variação C++ | Python decode | C++ decode | Variação C++ |
|---|---:|---:|---:|---:|---:|---:|
| Small, 30 mm | 172,86 ms | 83,01 ms | −51,98% | 144,77 ms | 21,38 ms | −85,23% |
| Medium, 40 mm | 318,23 ms | 138,99 ms | −56,32% | 139,16 ms | 36,32 ms | −73,90% |

Esses números são medianas de uma máquina e execução específicas. Eles medem PNG digital e decode canônico; não medem publicação, câmera, impressão nem uma garantia de dispositivo. O benchmark lógico in-process anterior não deve ser misturado com essa tabela.

Para verificar a dependência da resolução, `benchmark/benchmark_native_full_resolutions.py` repetiu cinco vezes cada combinação Small/Medium em 300, 450 e 600 DPI. O encode mais renderização C++ ficou entre **−22,82% e −54,22%** em relação ao Python. O decode canônico C++ ficou entre **−69,30% e −92,13%**. Os seis casos passaram round-trip exato. Os resultados são de uma máquina local com seis CPUs; a resolução nativa aceita atualmente vai de 72 a 600 DPI.

| DPI | Geometria | Encode/render C++ | Decode C++ |
|---:|---|---:|---:|
| 300 | Small | −22,82% | −92,13% |
| 300 | Medium | −24,57% | −80,81% |
| 450 | Small | −44,15% | −88,18% |
| 450 | Medium | −42,95% | −73,90% |
| 600 | Small | −50,24% | −84,00% |
| 600 | Medium | −54,22% | −69,30% |

### Codec lógico por ECC e geometria

`benchmark/benchmark_native_codec_profiles.py` mediu 28 combinações do Draft 0.6 com 500 repetições por combinação. **23 combinações foram medidas** e cinco foram registradas como impossíveis por capacidade normativa: Micro 2 com Robust e Extreme, e Micro 1 com Balanced, Robust e Extreme. Entre as combinações válidas, o C++ apresentou mediana de **−49,01% no encode lógico**, com intervalo de −22,92% a −82,32%, e **−97,69% no decode lógico**, com intervalo de −96,45% a −98,37%. Essa medição exclui PNG, SVG, processo externo e visão; por isso ela não substitui a tabela de produção completa.

## Build e distribuição

O Docker de produção instala apenas as bibliotecas necessárias ao runtime nativo: zlib, libpng, libjpeg, libwebp, FreeType e ZXing-C++. Ele compila `server/python/native`, `benchmark/native` e o runtime C11 do JAB. Não instala Python, venv, bindings Python ou o bridge.

A CI mantém uma etapa separada para instalar a referência Python e executar os gates de equivalência. Ela agora também executa o benchmark de perfis e a matriz visual ampliada. Essa separação permite que o C++ seja o runtime entregue enquanto a implementação Python continua disponível para detectar regressões de protocolo.

## Limites declarados

A migração de runtime está concluída, mas a equivalência científica não deve ser confundida com a remoção do processo Python. A visão nativa ainda precisa de evolução independente para ampliar perspectiva, oclusão, diagnósticos e cobertura de identidades/resoluções. Esses trabalhos podem usar a referência Python como oracle sem reintroduzi-la no produto.

O Orbiqo não reivindica superioridade geral sobre QR, Aztec ou JAB. As comparações devem sempre informar corpus, perfil, toolchain, método de normalização e a natureza digital da medição.

## CI pública

O primeiro run público foi disparado pelo commit `30d8ff5` e executou com sucesso todos os gates nativos: compilação do JAB, targets C++, adapters externos, paridade lógica, paridade full-path, matriz visual principal, benchmark por perfil e matriz visual ampliada. A única falha ocorreu na etapa `Typecheck and JavaScript tests`: os testes Node iniciaram `server/python/orbiqo_bridge.py` com o `python3` do sistema, enquanto `requests` havia sido instalado somente em `.ci-venv`.

O workflow foi corrigido para adicionar `.ci-venv/bin` ao `GITHUB_PATH` depois da instalação da referência. Assim, quando um teste Node precisar exercitar o bridge Python como oracle, ele usa o mesmo interpretador e as mesmas dependências instaladas pela CI. Essa correção não reintroduz Python no runtime de produção, que continua chamando apenas os executáveis C++.

O segundo run, no commit `f7e157a`, confirmou a correção do ambiente Python. O terceiro run, no commit `aaa9554`, também terminou com sucesso depois de incluir a matriz sintética de câmera. A tag anotada `v0.6.0-draft` aponta para esse commit validado.

## Próximos passos

O runner `benchmark/run_camera_corpus.py` está pronto para receber um corpus privado de imagens capturadas por celular ou webcam. O manifest de exemplo e o protocolo de captura estão em `benchmark/camera-corpus/`. O runner compara diretamente o executável C++ com o oracle Python, registra hashes das imagens e dos payloads, dimensões, formatos, tempos e divergências, mas não copia imagens nem payloads para o relatório.

O smoke test local do runner passou em **1/1 caso** com round-trip exato nos dois decoders. Isso valida a infraestrutura, não constitui evidência de câmera real: ainda não há imagens físicas fornecidas neste workspace. O próximo gate precisa usar arquivos originais de câmera, preservados sem resize ou melhoria, e manter esses arquivos fora do Git.

Depois do corpus real, novas medições de desempenho devem cobrir mais máquinas, mantendo separadas as medições lógicas, de produção completa e de visão. Mudanças normativas e otimizações adicionais de visão devem aguardar esses gates.

## Referências

[1]: https://github.com/belintani/orbiqo "Orbiqo repository"
[2]: https://api.github.com/repos/belintani/orbiqo/actions/runs?per_page=10 "Public GitHub Actions runs for Orbiqo"
