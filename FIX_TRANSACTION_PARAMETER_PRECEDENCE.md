# Transaction parameter precedence fix

Correção para a regressão em que uma resposta curta que preenchia um parâmetro pendente (ex.: `R$ 71,99` para `valor`) era classificada pelo LLM Router como uma nova intent e interrompia a transação.

## Regra aplicada

Durante `COLLECTING_PARAMETERS` a ordem passa a ser:

1. resposta compatível com parâmetro pendente -> mantém a política de estado e continua a transação;
2. cancelamento explícito -> cancela a transação;
3. nova intenção clara/pergunta explícita -> interrompe a transação e volta ao roteamento normal;
4. caso ambíguo -> permanece em clarificação.

Exemplo corrigido:

```text
não fiz essa contratação TIM CTRL Redes Sociais 8.0
-> informe valor
R$ 71,99
-> valor=71.99; continua contestar_cobranca; executa pré-validação
```

A mensagem `R$ 71,99` não pode mais virar `contas_invoice_explanation` enquanto `valor` estiver pendente.

## Testes

Foram adicionados testes para:

- valor monetário com LLM sugerindo outra intent;
- entidade curta como resposta de parâmetro;
- pergunta clara durante coleta ainda interrompendo a transação;
- regressões existentes de intent-shift e transactional tool flow.
