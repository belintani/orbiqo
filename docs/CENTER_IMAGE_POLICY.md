# Política de imagem central remota

O campo opcional `centerImageUrl` aceita somente URLs **HTTPS** de até 2.048 caracteres. A obtenção acontece no bridge Python, nunca diretamente no navegador. A URL é validada antes de cada solicitação e de cada redirecionamento; hosts locais, endereços privados, loopback, link-local, multicast e reservados são recusados.

O bridge segue no máximo três redirecionamentos HTTPS, usa timeouts de conexão e leitura, aceita apenas resposta `200`, limita o download a 2 MiB e valida a imagem com Pillow. São aceitos PNG, JPEG e WebP efetivamente decodificáveis, com até 2.048 px por lado e quatro milhões de pixels. O asset é centralizado, convertido para PNG RGBA de 256 × 256 px e incorporado aos dois artefatos de saída.

| Aspecto | Regra |
| --- | --- |
| Rede | HTTPS público, três redirecionamentos no máximo |
| Download | 2 MiB, timeout de conexão de 3 s e leitura de 7 s |
| Imagem | PNG/JPEG/WebP decodificável, até 2.048 px por lado e 4 MP |
| Saída | PNG normalizado incorporado no SVG e no PNG Orbiqo |
| Privacidade | Metadados guardam apenas o host de origem, nunca a URL completa |
| Decodificação | A arte fica dentro do círculo central não funcional; payload e células não mudam |

Para a validação manual ponta a ponta do bridge foi usada uma imagem PNG pública em `https://raw.githubusercontent.com/github/explore/main/topics/python/python.png`. O bridge incorporou o PNG, reportou apenas o host `raw.githubusercontent.com` e manteve a geometria Small e o payload intactos.

## Experiência no gerador

Após uma geração bem-sucedida, o gerador exibe uma miniatura do PNG já normalizado pelo bridge e o host de origem, sem repetir a URL completa. A limpeza do campo não altera um artefato já gerado; uma nova geração aplica a remoção.

O campo valida HTTPS no cliente e mostra mensagens seguras para host privado ou bloqueado, arquivo não PNG/JPEG/WebP, imagem inalcançável e limites de arquivo ou pixels. Erros de rede e formato continuam validados pelo bridge; o navegador não busca a imagem remota diretamente.

Na validação manual, a imagem pública acima exibiu a miniatura e `raw.githubusercontent.com` como origem. Em seguida, `https://nonexistent-center-image.invalid/mark.png` foi encaminhada ao bridge e o gerador mostrou a mensagem específica: “The image could not be reached. Check that the public HTTPS URL is available.”

Em viewport móvel de 375 px, o deep-link da imagem válida preservou campo, host, miniatura, ação de limpeza e símbolo gerado com a imagem no centro. A captura foi mantida fora do projeto em `webdev-static-assets/orbiqo-validation/center-image-mobile-valid.png`.

O deep-link de origem inalcançável exibiu a mensagem controlada também em 375 px; a captura correspondente é `webdev-static-assets/orbiqo-validation/center-image-mobile-unreachable.png`. A ação **Clear** foi corrigida e validada no navegador: remove URL, miniatura e alerta sem regenerar o símbolo.

Para revisões reproduzíveis, o gerador aceita opcionalmente `centerImageUrl` na query string. A URL apenas pré-preenche o campo; a geração inicial continua passando pela validação e pelos limites do bridge. Os deep-links usados nas capturas cobriram uma imagem válida, erro de origem inalcançável e o fluxo completo **prévia válida → Clear**.

A captura móvel do estado limpo está em `webdev-static-assets/orbiqo-validation/center-image-mobile-cleared.png`: após **Clear**, o campo volta ao placeholder e a miniatura normalizada desaparece, sem alterar o símbolo já gerado.

O campo interrompe entradas com mais de 2.048 caracteres antes da geração e mostra a mensagem específica de limite. Essa regra foi validada no DOM do gerador com uma URL de 2.078 caracteres, além da regressão UI e da validação tRPC.
