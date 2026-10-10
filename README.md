# IRMANDADE TRANSPORTADORA — Bot para Discord

Bot em Python com ponto, fretes, frota, despesas, advertências, relatórios e exportação CSV.

## Incluído
- Painel de ponto com botões: entrada, intervalo, retorno e saída.
- Consulta de expediente atual.
- Histórico de ponto e exportação CSV.
- Criação, atualização e consulta de fretes.
- Cadastro e status de veículos.
- Registro e resumo de despesas.
- Advertências administrativas.
- SQLite persistente em `irmandade.db`.
- Permissões básicas para comandos administrativos.

## 1. Criar o bot no Discord
1. Acesse https://discord.com/developers/applications
2. Clique em **New Application** e dê um nome, por exemplo `Irmandade Transportadora`.
3. Abra **Bot** e clique em **Add Bot** se necessário.
4. Em **Reset Token** / **View Token**, copie o token. Não envie para ninguém e não publique prints dele.
5. Em **OAuth2 > URL Generator**, marque `bot` e `applications.commands`.
6. Em permissões do bot, selecione pelo menos `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History` e `Use Application Commands`.
7. Abra o link gerado, selecione seu servidor e autorize o bot.
8. Se os comandos não aparecerem, confira se o bot foi convidado com `applications.commands` e se `GUILD_ID` está correto.

## 2. Preparar o projeto no computador
Necessário Python 3.10+.
1. Extraia o ZIP.
2. Renomeie `.env.example` para `.env`.
3. Abra `.env` e preencha:
   - `DISCORD_TOKEN`: token do bot.
   - `GUILD_ID`: ID numérico do seu servidor Discord.
   - `TIMEZONE`: `America/Sao_Paulo` ou seu fuso desejado.
4. Para copiar o ID do servidor: Discord > Configurações > Avançado > ative **Modo desenvolvedor**; clique com o botão direito/toque e segure o servidor e escolha **Copiar ID**. No celular, a opção pode aparecer no menu do servidor.
5. Abra um terminal dentro da pasta extraída e execute:

   ```bash
   python -m venv .venv
   ```

   Windows:
   ```bash
   .venv\Scripts\activate
   ```

   macOS/Linux:
   ```bash
   source .venv/bin/activate
   ```

6. Instale:
   ```bash
   pip install -r requirements.txt
   ```
7. Inicie:
   ```bash
   python main.py
   ```
8. Mantenha o terminal aberto enquanto quiser que o bot fique online.

## 3. Usar no Discord
- `/painel_ajuda` — lista de comandos.
- `/painel_ponto` — administrador publica o painel no canal atual.
- Funcionários clicam em Entrada, Intervalo, Retorno e Saída.
- `/meuponto` — funcionário consulta o próprio expediente.
- `/frete_criar` — administração cadastra frete.
- `/frete_status` — administração muda status.
- `/fretes` — lista fretes.
- `/frota_adicionar`, `/frota_status`, `/frota` — controla veículos.
- `/despesa_registrar`, `/financeiro_resumo` — controle simples de despesas.
- `/advertir`, `/advertencias` — histórico disciplinar.
- `/relatorio_ponto`, `/exportar_ponto` — relatórios de ponto.

## 4. Manter 24 horas online
Executar no seu computador funciona apenas enquanto ele estiver ligado e o processo estiver rodando. Para ficar online 24/7, hospede o projeto em um VPS ou serviço de hospedagem que suporte Python, configure as variáveis de ambiente e mantenha `irmandade.db` em armazenamento persistente. Não suba o token para repositórios públicos.

## Avisos importantes
- Este é um projeto funcional inicial, não um sistema de folha de pagamento ou RH certificado.
- O bot não calcula salário, não confirma quilometragem/GPS e não integra com sistemas externos de transporte.
- O banco SQLite fica na máquina onde o bot roda. Faça backups regulares.
- Para uso real, defina regras internas, acesso aos relatórios, retenção de dados e política de privacidade.
- Não compartilhe o token do bot; se vazar, regenere-o no Developer Portal.
