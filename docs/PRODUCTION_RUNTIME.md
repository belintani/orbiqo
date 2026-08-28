# Runtime de produção do bridge Python

O Orbiqo Lab mantém geração e leitura pelo pipeline Python real. A imagem de produção precisa, portanto, fornecer tanto `python3` quanto a implementação local do RadialCode e as dependências do modo Compare.

O `Dockerfile` do projeto parte de `node:22-slim`, instala Python 3 e cria o ambiente virtual `/opt/orbiqo-venv`. Ele instala a cópia empacotada de `server/python/vendor/radialcode` com o extra de visão, além de `requests` e `zxing-cpp`. A variável `PATH` faz o `spawn("python3")` do adaptador Node resolver o interpretador do ambiente virtual.

O build também recompila os binários JAB que o comparador chama a partir de `benchmark/jabcode-runtime`. `ORBIQO_JAB_ROOT` aponta para essa fonte empacotada e `ORBIQO_RADIALCODE_ROOT` aponta para a cópia de referência em `/app/server/python/vendor/radialcode`, em vez de depender de diretórios externos de desenvolvimento. Isso preserva os pipelines reais no runtime publicado.

> A imagem não usa mocks nem substitui o bridge por JavaScript. Caso a implantação falhe, os logs de build devem ser consultados antes de qualquer alteração no contrato de geração ou leitura.
