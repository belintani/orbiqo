# Auto dimensionamento do Orbiqo

O modo **Auto fit** transforma o payload usando o mesmo framing e a mesma compressão solicitados para a geração. Em seguida, seleciona a menor geometria cujo canal comporta o frame sob o ECC escolhido. No Protocol Draft 0.6 / `format_version=5`, a ordem é Micro 1 (16 mm), Micro 2 (16 mm), Micro 4 (18 mm), Small (30 mm), Medium (40 mm), Large (50 mm) e XL (70 mm). Micro 1 transporta até 16 B somente em Fast ECC; nos demais perfis sua capacidade é zero e ele é ignorado.

O modo **Manual** permite selecionar Micro 1, Micro 2, Micro 4, Small, Medium, Large ou XL e diâmetro entre 10 e 300 mm. Selecionar Micro 1 aplica Fast ECC na interface. A geração retorna `sizing_mode`, `requested_geometry`, geometria resolvida, diâmetro usado, diâmetro recomendado e o motivo da decisão.

## Verificação da interface

O gerador inicia em Auto fit e exibe geometria, diâmetro, bytes de payload, bytes do frame, compressão e margem nominal antes da geração. A alternância para Manual foi verificada no preview local: os seletores de geometria e diâmetro aparecem, enquanto o painel de recomendação é removido.

Payloads acima da capacidade XL são rejeitados com `CAPACITY_EXCEEDED`; o botão de geração é desativado enquanto a recomendação estiver em erro.
