# RadialCode Design Draft 0.3

**Status:** especificação experimental de interoperabilidade  
**Autor:** RadialCode contributors  
**Licença deste documento:** CC BY 4.0  
**Implementação de referência:** RadialCode `0.1.0a2`

## 1. Escopo

Este documento define a geometria, o bootstrap, o frame, a proteção de canal, o alfabeto visual, a renderização e o fluxo mínimo de decode do **RadialCode Design Draft 0.3**. Uma implementação é interoperável quando produz os mesmos streams intermediários dos golden vectors e recupera seus payloads sem depender de metadados externos.

As palavras **DEVE**, **NÃO DEVE**, **DEVERIA**, **PODE** e **RESERVADO** são normativas. COLOR4 e MONO2 são definidos neste draft; COLOR8 permanece reservado.

## 2. Convenções

A unidade geométrica normalizada é `R`, o raio funcional do símbolo. O centro é `(0,0)`. Ângulo zero aponta para 12 horas e os ângulos crescem no sentido horário. Bits em campos e bytes são serializados do mais significativo para o menos significativo. Inteiros multibyte usam big-endian.

| Identificador | Valor |
| --- | ---: |
| Magic do formato | `0xD7` |
| Versão de formato | `2` |
| Versão deste documento | Design Draft 0.3 |
| Alfabeto padrão | COLOR4 |
| Paleta padrão | C4-PRINT-1, ID `0` |
| Perfil ECC padrão | Balanced |

## 3. Layout radial

| Região | Limite interno | Limite externo | Função |
| --- | ---: | ---: | --- |
| Centro livre | `0,00 R` | `0,20 R` | logotipo ou texto não funcional |
| Separador interno | `0,20 R` | `0,22 R` | isolamento visual |
| Clock track | `0,22 R` | `0,255 R` | fase e sincronização angular |
| Header A | `0,260 R` | `0,280 R` | bootstrap BCH |
| Header B | `0,285 R` | `0,305 R` | bootstrap BCH |
| Header C | `0,310 R` | `0,330 R` | bootstrap BCH |
| Payload | `0,38 R` | `0,91 R` | células COLOR4 ou MONO2 |
| Separador externo | `0,91 R` | `0,93 R` | isolamento do payload |
| Guard e lacunas de pose | `0,93 R` | `0,97 R` | detecção, escala, pose |
| Quiet zone | `0,97 R` | `1,05 R` | margem mínima |

O conteúdo do centro NÃO DEVE alterar nenhuma região funcional. Um decoder NÃO DEVE depender do texto ou logotipo central.

## 4. Geometrias e tesselação

| Versão | Nome | Anéis de dados | Diâmetro sugerido | COLOR4 Balanced | MONO2 Balanced |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Small | 12 | 30 mm | 183 bytes | 63 bytes |
| 2 | Medium | 18 | 40 mm | 410 bytes | 183 bytes |
| 3 | Large | 24 | 50 mm | 762 bytes | 374 bytes |
| 4 | XL | 30 | 70 mm | 1.252 bytes | 592 bytes |

O pitch radial normalizado é:

```text
p = (0,91 - 0,38) / número_de_anéis
```

Para o anel `r`, indexado de zero para fora, o raio de centro é `0,38 + (r + 0,5)p`. A contagem ideal de setores é `2π × raio / p`; o resultado DEVE ser arredondado para o múltiplo de oito mais próximo, nunca abaixo de 24.

O anel `r` recebe offset angular fracionário `((3r) mod 8) / 8` de uma célula. Os endereços são `(anel, setor)`, em ordem de anel crescente e setor crescente.

Vinte e quatro células são reservadas para extensões futuras. Elas são escolhidas por índices uniformemente espaçados no vetor completo de células. Em COLOR4, dezesseis células adicionais são referências: os quatro estados aparecem em quatro anéis distribuídos radialmente. Células reservadas e de referência NÃO transportam payload.

O diâmetro é parâmetro de renderização. O pitch físico é `p × diâmetro / 2`. A implementação de referência avisa abaixo de `0,50 mm`, mas este valor é provisório e não constitui limite normativo de impressão.

## 5. Clock track

A clock track tem 64 slots. O slot zero é um marcador de fase escuro. Os 63 slots restantes recebem uma m-sequence gerada por LFSR de seis bits, estado inicial `111111₂`, tap mask `100001₂` e polinômio característico `x⁶ + x⁵ + 1` sob a convenção de deslocamento deste documento.

A cada passo, o bit mais significativo é emitido, o feedback é a paridade do estado AND `100001₂`, e o registrador desloca à esquerda, inserindo o feedback no bit menos significativo. O período DEVE ser 63, com 32 chips escuros e 31 claros. No diâmetro Small de 30 mm, o pitch angular nominal é aproximadamente `0,350 mm` e a banda radial nominal mede `0,525 mm`.

Novos encoders DEVEM emitir `format_version=2`. Decoders PODEM aceitar `format_version=1` para ler símbolos Draft 0.2, cujo clock tinha 128 slots; essa compatibilidade não autoriza um encoder Draft 0.3 a produzir a geometria antiga.

## 6. Lacunas de pose

O guard é um anel escuro entre `0,93 R` e `0,97 R`. Quatro lacunas claras são cortadas no centro radial do guard, preservando trilhos escuros interno e externo contínuos.

| ID | Centro em slots de 128 | Largura nominal em slots |
| ---: | ---: | ---: |
| 0 | 0 | 3 |
| 1 | 19 | 5 |
| 2 | 46 | 7 |
| 3 | 81 | 9 |

As larguras crescentes identificam cada correspondência; os espaçamentos circulares entre IDs consecutivos são 19, 27, 35 e 47 slots. O decoder PODE detectar as lacunas como ilhas claras ou por correlação angular no guard. As quatro correspondências definem a homografia para o plano canônico.

## 7. Header de bootstrap

O header lógico tem 45 bits, na ordem abaixo.

| Campo | Bits | Semântica |
| --- | ---: | --- |
| magic | 8 | `0xD7` |
| format_version | 3 | `2` para novos símbolos; `1` aceito como legado |
| geometry_version | 3 | `1..4` |
| alphabet | 2 | `0=MONO2`, `1=COLOR4`, `2=COLOR8 reservado` |
| palette_id | 3 | `0` definido neste draft |
| ecc_scheme | 2 | `0=RS_GF256` |
| ecc_level | 2 | `0=Fast`, `1=Balanced`, `2=Robust`, `3=Extreme` |
| mask_id | 3 | `0..7` |
| encoded_payload_length | 16 | comprimento do frame antes do RS |
| flags | 3 | zero neste draft |

Os 45 bits são codificados sistematicamente por BCH(63,45,t=3). O código é primitive narrow-sense sobre GF(2⁶), polinômio primitivo `x⁶ + x + 1`, e polinômio gerador:

```text
g(x) = x¹⁸ + x¹⁷ + x¹⁶ + x¹⁵ + x⁹ + x⁷ + x⁶ + x³ + x² + x + 1
hex(g) = 0x782CF
```

O codeword de 63 bits aparece em cada um dos três anéis físicos de 64 slots. Os slots reservados são 0, 17 e 43 para as cópias A, B e C, com bits reservados 1, 0 e 1. O primeiro bit do codeword ocupa o slot seguinte ao reservado; o mapeamento continua circularmente.

Cada cópia é decodificada separadamente. Um decoder DEVE rejeitar o símbolo quando nenhuma cópia é corrigível. Quando mais de uma cópia for válida, os valores semânticos DEVEM concordar; valores incompatíveis são erro explícito.

## 8. Frame do payload

O frame antes do ECC é:

| Campo | Tamanho | Descrição |
| --- | ---: | --- |
| Control | 1 byte | versão, tipo, compressão, flags |
| Original length | 3 bytes | comprimento do payload após descompressão |
| Stored payload | variável | bytes crus ou DEFLATE |
| CRC32C | 4 bytes | checksum de `Control || Original length || Stored payload` |

O byte de controle usa: versão nos bits 7–6, tipo nos bits 5–4, compressão nos bits 3–2 e flags nos bits 1–0. A versão do frame é `1`. Tipos: `0=binary`, `1=UTF-8`, `2=URL`. Compressão: `0=none`, `1=DEFLATE`.

Em modo automático, DEFLATE nível 9 é usado somente quando reduz o tamanho. CRC32C usa o polinômio refletido `0x82F63B78`, inicialização e XOR final com `0xFFFFFFFF`. O decoder DEVE validar CRC, comprimento original e UTF-8 antes de declarar sucesso.

## 9. Reed–Solomon e interleaving

O payload frame é dividido em blocos Reed–Solomon encurtados sobre GF(256). Parâmetros: polinômio primitivo `0x11D`, elemento gerador `2`, first consecutive root `0` e tamanho máximo 255.

| Nível | Bytes de dados por bloco | Paridade por bloco | Taxa nominal |
| --- | ---: | ---: | ---: |
| Fast | 223 | 32 | 0,875 |
| Balanced | 191 | 64 | 0,749 |
| Robust | 159 | 96 | 0,624 |
| Extreme | 127 | 128 | 0,498 |

O último bloco PODE ser encurtado e sempre recebe a paridade integral do perfil. Após RS, os blocos são intercalados por coluna: primeiro byte de cada bloco disponível, segundo byte de cada bloco disponível, e assim por diante.

O decoder COLOR4 DEVERIA calcular confiança por célula. Células abaixo do limiar local podem ser convertidas em erasures; a posição física DEVE ser revertida pela permutação e pelo interleaving antes de chegar ao bloco RS.

## 10. Permutação espacial e padding

Bytes de canal são serializados MSB-first. MONO2 consome um bit por célula; COLOR4 consome dois bits por célula. O último símbolo incompleto recebe zeros nos bits menos significativos.

O seed de 32 bits é:

```text
0x52414449
XOR (geometry_version << 24)
XOR (alphabet << 20)
XOR (ecc_level << 16)
XOR frame_length
```

A permutação usa XorShift32 determinístico. Células remanescentes recebem símbolos pseudoaleatórios do mesmo gerador com seed XOR `0xA5C31E27`. A permutação DEVE ser invertível e cobrir todas as posições exatamente uma vez.

## 11. Alfabetos e paleta

### 11.1 MONO2

MONO2 mapeia `0 → #FFFFFF` e `1 → #111111`. Não usa referências cromáticas.

### 11.2 COLOR4

COLOR4 mapeia dois bits para quatro estados. A paleta C4-PRINT-1 é:

| Estado | Bits | Cor nominal |
| ---: | --- | --- |
| 0 | `00` | `#111111` |
| 1 | `01` | `#00A6D6` |
| 2 | `10` | `#D81B60` |
| 3 | `11` | `#F0C808` |

As cores nominais são somente alvos de renderização. O decoder DEVE estimar os quatro centroides a partir das referências observadas na própria imagem. A implementação de referência usa distância de Mahalanobis regularizada e produz confiança normalizada pela razão entre a menor e a segunda menor distância.

## 12. Máscaras

Cada máscara produz um valor com um bit por plano de cor. Para anel `r`, setor `s` e plano `p`:

| ID | Bit de máscara |
| ---: | --- |
| 0 | `(r+s+p) mod 2` |
| 1 | `(r+p) mod 2` |
| 2 | `1 se (s+p) mod 3 = 0` |
| 3 | `1 se (r+s+p) mod 3 = 0` |
| 4 | `(⌊r/2⌋ + ⌊s/3⌋ + p) mod 2` |
| 5 | `1 se (q mod 2) + (q mod 3) = 0`, `q=(r+1)(s+1+p)` |
| 6 | `((q mod 2) + (q mod 3)) mod 2` |
| 7 | `(((r+s+p) mod 2) + (q mod 3)) mod 2` |

O símbolo lógico é XOR com o valor de máscara. O encoder avalia os oito candidatos por desequilíbrio de estados, runs angulares e repetição radial. Empates são resolvidos pelo menor ID. O ID escolhido é gravado no header.

## 13. Renderização

Células de payload são arcos arredondados, centralizados na célula lógica, com preenchimento radial e angular padrão de 0,78. Uma implementação alternativa PODE usar outra primitiva visual, desde que preserve centros, estados, quiet zone e capacidade de decode.

SVG DEVERIA incluir título, descrição e metadados de atribuição. Esses metadados não são parte do canal e NÃO DEVEM ser necessários para decode.

## 14. Fluxo do decoder

Um decoder de imagem arbitrária DEVERIA executar, nesta ordem: localizar candidato; ajustar guard externo; encontrar as quatro lacunas; estimar homografia; warp para plano canônico; ler e validar headers; reconstruir geometria; amostrar referências; classificar células com confiança; remover máscara; inverter permutação; reconstruir bytes; desfazer interleaving; executar RS com erasures; validar frame e CRC.

O decoder DEVE falhar de forma explícita quando: guard não é plausível; lacunas são insuficientes; headers não são corrigíveis ou concordantes; alfabeto/paleta são desconhecidos; RS não corrige algum bloco; CRC falha; comprimento é incompatível; ou texto não é UTF-8 válido.

## 15. Golden vectors e conformidade

Os vetores em `vectors/draft-0.3/manifest.json` congelam payload, frame, header, streams RS, interleaving, símbolos, máscara, SVG/PNG e hashes SHA-256. Uma implementação que reivindique conformidade com Draft 0.3 DEVE reproduzir os streams binários intermediários; diferenças apenas de rasterização são permitidas quando o SVG lógico e o decode permanecem equivalentes.

O conjunto mínimo inclui payload vazio COLOR4 Small, URL COLOR4 Small, UTF-8 COLOR4 Medium, binário COLOR4 Large e fallback MONO2 Small.

## 16. Estado experimental

Este draft foi validado com imagens canônicas e projeções sintéticas. O benchmark de visão atual decodifica 14 de 16 combinações de pose/perfil; a pose sintética mais foreshortened permanece fora do envelope. Ensaios físicos com impressoras, papéis, câmeras e iluminações diferentes são necessários antes de definir tolerâncias normativas.

## 17. Licença e atribuição

A especificação e os diagramas autorais são licenciados sob CC BY 4.0. Redistribuições e adaptações devem citar a origem, indicar alterações e referenciar a licença conforme seus termos.[1] O código de referência é Apache-2.0 e possui `NOTICE` próprio.

Crédito preferido:

> Built with RadialCode — an open radial 2D code project.

## Referências

[1]: https://creativecommons.org/licenses/by/4.0/legalcode.en "Creative Commons Attribution 4.0 International — Legal Code"
