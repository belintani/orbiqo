# Posicionamento de produto — Orbiqo

## Tese

> **Orbiqo é um código circular para os momentos em que o código faz parte da composição.**

O produto não deve ser apresentado como substituto universal de QR, Aztec ou JAB, nem como superior em capacidade, velocidade ou transparência. Esses formatos continuam adequados quando seus perfis técnicos são a prioridade.

Orbiqo é indicado quando o símbolo precisa ser também um elemento de identidade: em embalagens, materiais editoriais, produtos, convites, campanhas e interfaces em que o código permanece visível em vez de ser apenas um utilitário discreto.

| Pilar | Promessa verificável | Limite explícito |
| --- | --- | --- |
| Composição circular | Forma radial e colunas polares contínuas | Não promete superioridade de leitura sobre outros formatos |
| Centro reservado | Texto, marca ou imagem no centro sem cobrir células de payload | A área é limitada ao centro não funcional atual |
| Identidade registrada | Paletas COLOR4 e perfis visuais validados no codec | Não há seletor RGB livre sem validação |
| Escala adaptativa | Auto fit escolhe de Micro 1 a XL conforme frame e ECC | Micro 1 exige ECC Fast e comporta apenas 16 B |
| Implementação rastreável | Codec, reader, diagnósticos e benchmarks locais | Não é uma alegação de que concorrentes sejam opacos |

## Linguagem recomendada

O hero deve falar de **composição**, não de uma confiança que outros códigos supostamente não merecem:

> **“A code that belongs in the composition.”**

O texto de apoio deve descrever o centro reservado, a identidade registrada e a geometria adaptativa. A palavra “occlusion” não deve ser usada como benefício atual; o centro reservado não é recuperação de dano.

## Decisão de oclusão

A avaliação de `OCCLUSION_FEASIBILITY.md` adia o logo sobre a área de dados. Esse recurso exigiria uma revisão de formato e uma nova validação completa. O diferencial atual é mais honesto: a marca entra no **centro não funcional já reservado**, sem consumir capacidade nem depender de correção de dano.
