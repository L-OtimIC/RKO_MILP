# Teste de sensibilidade (n = 10000)

BRKGA em uma thread, uma execução por instância, nas instâncias kp015 a kp019 de
`Instances/KP/00Uncorrelated/n10000`. Para cada instância, a versão com cortes roda
com MAXTIME de 3600 s e, em seguida, a versão original roda com MAXTIME igual ao
tempo que a versão com cortes levou para encontrar sua melhor solução.

As cinco instâncias rodam ao mesmo tempo, cada uma presa a um núcleo (`--jobs 5 --pin`).
Duração estimada: até 2 h.

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
python3 -u run_experiment_cuts.py --mh BRKGA --runs 1 --time 3600 --sensitivity \
  --n 10000 --instances kp015 kp016 kp017 kp018 kp019 --jobs 5 --pin \
  --out teste_sensibilidade_03 | tee sens03.log \
  && python3 make_table_cuts.py --sensitivity ../Results/teste_sensibilidade_03
```

`Ctrl-A D` sai do screen sem interromper; `screen -r rko_sens` volta.

Os resultados ficam em `Results/teste_sensibilidade_03` (`summary.csv`, `runs.csv` e,
ao final, `table_sensitivity.tex`).

## Retomar após interrupção

Mesmo comando, trocando `--out teste_sensibilidade_03` por
`--resume ../Results/teste_sensibilidade_03`. As instâncias já concluídas são puladas.

## Testes anteriores

- `teste_sensibilidade_01`: n = 50 a 10000, 10 execuções, cortes com 10× o MAXTIME padrão.
- `teste_sensibilidade_02`: as 10 instâncias n = 10000, 10 execuções, cortes com 1000 s.
