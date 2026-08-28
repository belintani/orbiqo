# Revisão local — Orbiqo Protocol Draft 0.6

**Data:** 26 de agosto de 2026  
**Escopo:** revisão local, sem publicação.

## Verificação visual

A workspace **Benchmarks** foi revisada no preview local em desktop e viewport móvel de 375 × 812 px. O cabeçalho, a conclusão normalizada e o rodapé exibem Draft 0.6. O card de oclusão aparece como um bloco separado, após o limite de foreshortening, com o texto `3/4 por padrão`, perfil Robust, 64 B e quatro posicionamentos determinísticos.

O layout móvel empilha os cards e gráficos sem overflow lateral observado. A matriz Balanced de degradação continua exibindo Orbiqo em 1/4 para a coluna de oclusão, enquanto o card Robust declara explicitamente que se trata de um perfil ECC separado, não de uma alegação de capacidade equivalente ou resultado físico.

## Registros de execução

Os logs recentes não registraram novo aviso de Fast Refresh depois do ajuste que removeu a exportação incompatível de `Home.tsx`; os avisos encontrados às 14:20–14:26 são históricos. Os únicos erros posteriores registrados são tentativas intencionais da URL de imagem central com host inexistente, que retornam a mensagem esperada de host não resolvido e não afetam o dashboard.
