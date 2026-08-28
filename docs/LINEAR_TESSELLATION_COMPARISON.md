# Comparação de tesselações lineares do Orbiqo

**Objetivo:** remover a aparência de escamas sobrepostas e criar linhas radiais deliberadas sem esconder custos de capacidade ou decode.

![Current, linear, terraced, and constant-column variants](/manus-storage/linear_tessellation_contact_sheet_276b3b6e.png)

Os quatro candidatos foram gerados com o mesmo payload em Small, Medium, Large e XL. O experimento end-to-end aplicou cada geometria de modo consistente no encoder, mask layout, renderer e decoder, exigindo igualdade exata do payload nos perfis limpo, blur 1,2, JPEG 55, downsample 0,55 e ruído sigma 7.

| Variante | Alinhamento entre fronteiras adjacentes | Capacidade Small / Medium / Large / XL | Ensaios digitais exatos | Avaliação visual | Compatibilidade |
| --- | ---: | --- | ---: | --- | --- |
| Draft 0.3 atual | 2,45–2,93% | 183 / 410 / 762 / 1.252 B | 20/20 | Escamas interligadas; problema visual apontado pelo proprietário | Formato atual |
| Fase linear | 24,18–27,27% | 183 / 410 / 762 / 1.252 B | 20/20 | Emenda superior mais limpa, mas a maioria das fronteiras ainda deriva | Exigiria novo layout apesar das contagens iguais |
| Terraced | 100% | 183 / 406 / 756 / 1.200 B | 20/20 | Colunas alinhadas com uma divisão exata 1:2 na região externa | Candidato não selecionado |
| Constant Columns inicial | 100% | 86 / 250 / 462 / 746 B | 20/20 | Mais linear e calmo, porém excessivamente grosseiro | Protótipo inicial |
| **Constant Columns otimizado** | **100%** | **334 / 546 / 734 / 922 B** | **96/96 em capacidade máxima; Small 28/28 no gate de produto não oclusivo** | **Colunas contínuas com caps planos escolhidas pelo proprietário** | **Draft 0.4 selecionado** |

A fração pintada permaneceu aproximadamente em 48–50% no experimento inicial porque fill ratios e paleta foram mantidos. A diferença observada decorre da geometria de endereçamento, não de opacidade, saturação ou de um skin mais denso.

> **Decisão do proprietário:** selecionar **Constant Columns**, o último layout da comparação visual, por ser o mais linear e não produzir a aparência de sobreposição. A recomendação técnica anterior por Terraced fica preservada apenas como registro histórico; ela foi superada pela decisão estética explícita e pela otimização posterior de capacidade.

Constant Columns altera o endereçamento físico e não pode ser rotulado como Draft 0.3. A implementação correta exige versão de formato Draft 0.4, nova construção de geometria, cache keys próprias, tabelas de capacidade, roteamento do encoder/decoder pela versão do header, texto normativo, novos golden vectors e decode retrocompatível com Draft 0.2/0.3. Os parâmetros e a validação final estão em [`CONSTANT_COLUMNS_SELECTION.md`](./CONSTANT_COLUMNS_SELECTION.md).
