# Identidades visuais do Orbiqo

## Escopo

O gerador do Orbiqo Lab oferece **templates registrados**, não um seletor RGB livre. Cada identidade combina uma paleta funcional COLOR4 com um perfil de preenchimento do renderer. A paleta é gravada no header pelo `palette_id`; o perfil visual altera apenas a apresentação das células e não muda payload, ECC, geometria ou endereçamento.

| Template | `palette_id` | Paleta | Perfil | Cores | Estado |
| --- | ---: | --- | --- | --- | --- |
| Reference | 0 | C4-PRINT-1 | Reference | `#111111`, `#00A6D6`, `#D81B60`, `#F0C808` | Validado digitalmente |
| Pulse | 0 | C4-PRINT-1 | Pulse | `#111111`, `#00A6D6`, `#D81B60`, `#F0C808` | Validado digitalmente |
| Nocturne | 1 | C4-NOCTURNE-1 | Pulse | `#111111`, `#4CC9F0`, `#F72585`, `#A7C957` | Validado digitalmente |
| Terra | 2 | C4-TERRA-1 | Pulse | `#111111`, `#2A9D8F`, `#E76F51`, `#FFD60A` | Validado digitalmente |
| Signal | 3 | C4-SIGNAL-1 | Pulse | `#111111`, `#219EBC`, `#FF4D6D`, `#80ED99` | Validado digitalmente |

## Regras

As quatro cores de uma paleta registrada mantêm associação estável com os estados `0..3`. As dezesseis células de referência COLOR4 continuam sendo a fonte de calibração observada durante o decode, mas um encoder conforme não deve substituir as cores de um ID por valores arbitrários. Os IDs `4..7` permanecem reservados.

O perfil **Reference** usa preenchimento angular/radial `0,88/0,72`. O perfil **Pulse** usa `0,82/0,80`. Ambos preservam as colunas constantes e os caps planos dos formatos 3, 4 e 5.

## Evidência atual

As quatro paletas passam critérios nominais automatizados de cardinalidade, separação entre estados e distância do fundo branco. Elas também passam round-trip limpo, JPEG 55 e ruído sintético. Os cinco templates passaram geração e decode pelo bridge real; a seleção foi verificada no componente e no contrato tRPC. O Draft 0.6 preserva os mesmos `palette_id` nas sete geometrias registradas.

O detector agora possui um fast path sem reamostragem para símbolos já frontais e canônicos. Imagens em perspectiva continuam usando a retificação existente. Esse ajuste evita degradar o header ao redimensionar desnecessariamente arquivos exportados pelo próprio gerador.

> Esta validação é exclusivamente digital. Impressão, substratos, iluminação e câmeras físicas continuam fora do escopo do gate atual.

## Personalização futura

Novas identidades devem receber um `palette_id` registrado ou reutilizar uma paleta existente com outro perfil visual. Um modo de cores totalmente livres só deve ser considerado após definir limites cromáticos normativos, política de compatibilidade e uma bateria física de validação.
