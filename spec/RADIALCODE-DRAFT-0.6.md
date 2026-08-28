# RadialCode Protocol Draft 0.6

## 1. Status e escopo

Este draft define o **`format_version=5`**. Ele é emitido pela implementação de referência `0.1.0a6` e preserva os caminhos de decode dos formatos 1–4. As geometrias Constant Columns, os IDs Micro e o framing de payload permanecem compatíveis com o Draft 0.5; a alteração normativa concentra-se na redundância de bootstrap e no tratamento de amostras ocluídas.

O Draft 0.6 é validado apenas em raster digital. Não define desempenho de impressão, câmera física, cor de substrato, iluminação, superfície curva, assinatura, criptografia ou autenticação.

## 2. Registro de formato

| Campo | Valor Draft 0.6 |
| --- | --- |
| `format_version` | `5` |
| Layout de dados | Constant Columns, igual ao Draft 0.5 |
| Geometrias registradas | Micro 1, Micro 2, Micro 4, Small, Medium, Large, XL |
| Header BCH | BCH(63,45), três cópias internas e uma cópia externa |
| Faixa radial da cópia externa | `0.345 ≤ r/R ≤ 0.365` |
| Retrodecode obrigatório | formatos `1`, `2`, `3`, `4` e `5` |

Os campos semânticos do header BCH continuam descrevendo a versão física, a geometria, o alfabeto, a paleta, o perfil ECC, a máscara e o comprimento. O guard preto externo permanece um elemento de detecção e pose; ele não codifica a geometria.

## 3. Quarta cópia BCH externa

O formato 5 mantém as três cópias BCH internas já usadas pelos formatos anteriores. A quarta cópia é renderizada exclusivamente na faixa radial externa registrada acima e tem rotação física própria, para que não reutilize as mesmas posições angulares das cópias internas.

Após a retificação, o leitor deve amostrar a cópia externa com uma pequena família de candidatos radiais em torno da faixa nominal. Essa tolerância é necessária porque a visão pode deslocar alguns milésimos de raio mesmo em uma tomada quase frontal. A escolha do candidato deve ser determinística e só pode aceitar um header BCH válido.

As cópias internas continuam sendo o caminho preferencial. Quando há cópias internas válidas, o leitor vota por bit entre as cópias rotacionadas disponíveis. Quando o conjunto interno não fornece um header utilizável, uma cópia externa BCH válida pode recuperar os campos de formato, geometria, ECC, paleta e máscara antes da decodificação do payload. Uma cópia externa inválida nunca autoriza um decode de payload sem header válido.

## 4. Amostras ocluídas e erasures

No caminho Constant Columns dos formatos 4 e 5, o leitor pode classificar uma célula como erasure quando ela não representa uma amostra COLOR4 confiável. As duas classes definidas nesta revisão são:

| Condição observada | Tratamento |
| --- | --- |
| Amostra branco-neutro fora da paleta registrada | erasure independente da calibração COLOR4 |
| Componente preto-neutro contínuo anormalmente grande | erasure, sem remover células pretas isoladas legítimas |

Erasures são encaminhadas ao decodificador Reed–Solomon. Elas não devem ser substituídas silenciosamente por um estado COLOR4. A classificação é deliberadamente conservadora: falsos positivos que eliminem células válidas são um risco, e por isso os limiares permanecem responsabilidade da implementação de referência e de seus testes de regressão.

## 5. Centro editorial e oclusão

O centro não funcional até `0.20 R` continua disponível para composição editorial. O Draft 0.6 **não** reserva ou protege células de dados para logotipos. A cópia BCH externa e o caminho de erasures fornecem apenas redundância de header e uma estratégia de correção para o corpus digital controlado.

Na validação de referência, três padrões de payload de 64 B, quatro posicionamentos determinísticos e oclusão digital de 6% atingiram 3/4 por padrão com RS(255,159) Robust. Balanced variou entre 0/4 e 1/4 e Extreme obteve 0/4 nesse corpus. Esses números não são parâmetros normativos de aceitação, nem estabelecem monotonicidade entre ECC, equivalência com outras simbologias ou suporte a oclusão arbitrária.

## 6. Regressões e vetores

Os vetores Draft 0.6 são armazenados em `vectors/draft-0.6/`; os vetores anteriores permanecem imutáveis. A implementação deve cobrir, no mínimo:

1. round-trip canônico de cada vetor Draft 0.6;
2. decode de todos os formatos 1–5;
3. recuperação do header quando as três cópias internas estão indisponíveis e a cópia externa é válida;
4. rejeição quando nenhuma cópia BCH válida existe; e
5. preservação das regressões Draft 0.5 em `format_version=4`.

## 7. Não alegações

O formato 5 não torna a oclusão gratuita, não torna o perfil Extreme automaticamente melhor e não estabelece superioridade geral sobre QR, Aztec ou JAB. Resultados comparativos só podem declarar parâmetros, ECC, corpus e condição de captura efetivamente medidos.
