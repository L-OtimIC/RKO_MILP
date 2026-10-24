# Teste de sensibilidade (n = 10000)

BRKGA em uma thread, 10 execuções por instância, nas 10 instâncias de
`Instances/KP/00Uncorrelated/n10000`. Para cada instância, a versão com cortes roda
com MAXTIME de 1000 s e, em seguida, a versão original roda com MAXTIME igual ao
tempo médio que a versão com cortes levou para encontrar sua melhor solução.

Cinco instâncias rodam ao mesmo tempo, cada uma presa a um núcleo (`--jobs 5 --pin`).
Duração estimada: ~11 h.

## Requisitos

- g++ com OpenMP
- Python 3 com pandas (`pip install pandas`)
- screen e taskset (util-linux)

## Compilação

```bash
cd Program
make clean && make OMP_CFLAGS=-fopenmp OMP_LDFLAGS=-fopenmp
```

Em `Program/config/config_tests.conf`, a opção `debug` precisa estar em `0`.

## Execução

```bash
cd Scripts
screen -S rko_sens
set -o pipefail
python3 -u run_experiment_cuts.py --mh BRKGA --runs 10 --cuts-time-factor 10 \
  --sensitivity --n 10000 --jobs 5 --pin --out teste_sensibilidade_02 | tee sens02.log \
  && python3 make_table_cuts.py --sensitivity ../Results/teste_sensibilidade_02
```

`Ctrl-A D` sai do screen sem interromper; `screen -r rko_sens` volta.

Os resultados ficam em `Results/teste_sensibilidade_02` (`summary.csv`, `runs.csv` e,
ao final, `table_sensitivity.tex`).

## Retomar após interrupção

Mesmo comando, trocando `--out teste_sensibilidade_02` por
`--resume ../Results/teste_sensibilidade_02`. As instâncias já concluídas são puladas.
