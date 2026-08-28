# Comparação visual: Orbiqo, QR, Aztec e JAB

A workspace **Compare** gera simultaneamente quatro símbolos a partir dos mesmos bytes de payload. Não são imagens demonstrativas pré-calculadas: Orbiqo usa o encoder RadialCode; QR e Aztec usam ZXing-C++; JAB usa o writer oficial em C11 já incorporado ao benchmark local.

| Formato | Perfil exibido | Toolchain |
| --- | --- | --- |
| Orbiqo | COLOR4, geometria automática, Balanced RS | RadialCode 0.1.0a4 |
| QR | Geometria automática, nível Q solicitado | ZXing-C++ |
| Aztec | Geometria automática, 25% solicitado | ZXing-C++ |
| JAB | COLOR4, nível 3 | JAB Code CLI 2.0.0 |

Cada símbolo completo, incluindo sua quiet zone exigida, é ajustado a uma área ocupada de 900 × 900 px sobre canvas de 1024 × 1024 px. Essa normalização serve para inspeção visual; não altera os bytes codificados e não implica equivalência de ECC.

Os perfis não são diretamente equivalentes. A interface mostra essa limitação junto dos quatro cards, além do tamanho lógico/nativo, perfil reportado e toolchain. O endpoint tRPC verifica que os quatro PNGs usam o mesmo payload e retornam canvas 1024 × 1024.
