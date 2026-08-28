# Refinamento pontual dos setores coloridos

O afunilamento dos risquinhos em direção ao centro é inerente à geometria polar e foi preservado. A irregularidade removível vinha da aproximação dos setores Micro por arcos com segmentos de até 3 px, seguida da redução do raster.

O raster rápido passou a usar segmentos de no máximo 0,75 px nas bordas interna e externa dos setores Micro e supersampling 3× apenas nas geometrias de até quatro anéis. Endereços, estados COLOR4, ângulos, raios e formato permanecem inalterados.

A comparação visual mostra contornos mais uniformes, especialmente nas extremidades interna e externa dos setores. O efeito continua deliberadamente radial; o objetivo não é transformar setores polares em retângulos.
