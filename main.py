import os
import io
import csv
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = os.getenv("GUILD_ID", "").strip()
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")
DB_PATH = os.getenv("DB_PATH", "irmandade.db")
TZ = ZoneInfo(TIMEZONE)

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

def now():
    return datetime.now(TZ)

def iso(dt=None):
    return (dt or now()).isoformat(timespec="seconds")

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS sessions(
            guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, state TEXT NOT NULL,
            started_at TEXT NOT NULL, break_started_at TEXT, break_seconds INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(guild_id,user_id))""")
        con.execute("""CREATE TABLE IF NOT EXISTS time_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            event TEXT NOT NULL, created_at TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS deliveries(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            driver_id INTEGER, description TEXT NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS fleet(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, vehicle TEXT NOT NULL,
            plate TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Disponível', notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            category TEXT NOT NULL, amount REAL NOT NULL, description TEXT NOT NULL, created_at TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS warnings(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            staff_id INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, actor_id INTEGER NOT NULL,
            action TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL)""")

def manager(interaction):
    return isinstance(interaction.user, discord.Member) and (
        interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
    )

def event(gid, uid, action):
    with db() as con:
        con.execute("INSERT INTO time_events(guild_id,user_id,event,created_at) VALUES(?,?,?,?)",
                    (gid, uid, action, iso()))

def audit(gid, uid, action, details):
    with db() as con:
        con.execute("INSERT INTO audit_log(guild_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)",
                    (gid, uid, action, details[:500], iso()))

def session(gid, uid):
    with db() as con:
        return con.execute("SELECT * FROM sessions WHERE guild_id=? AND user_id=?", (gid, uid)).fetchone()

def seconds(start, end=None):
    a = datetime.fromisoformat(start)
    b = end or now()
    if a.tzinfo is None:
        a = a.replace(tzinfo=TZ)
    return max(0, int((b-a).total_seconds()))

def duration(value):
    h, rem = divmod(max(0, int(value)), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}min"

async def reply(interaction, content=None, *, embed=None, view=None, ephemeral=True):
    if interaction.response.is_done():
        await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral)

async def punch(interaction, action):
    if not interaction.guild:
        return await reply(interaction, "Use este painel dentro do servidor.")
    gid, uid = interaction.guild.id, interaction.user.id
    s = session(gid, uid)
    t = now()
    if action == "entrada":
        if s:
            return await reply(interaction, "Você já tem um expediente aberto.")
        with db() as con:
            con.execute("INSERT INTO sessions(guild_id,user_id,state,started_at) VALUES(?,?,?,?)",
                        (gid, uid, "trabalhando", iso(t)))
        event(gid, uid, "entrada")
        return await reply(interaction, f"🟢 Entrada registrada às **{t:%H:%M:%S}**.")
    if not s:
        return await reply(interaction, "Você precisa registrar a entrada primeiro.")
    if action == "intervalo":
        if s["state"] != "trabalhando":
            return await reply(interaction, "Você não está em expediente ativo.")
        with db() as con:
            con.execute("UPDATE sessions SET state='intervalo',break_started_at=? WHERE guild_id=? AND user_id=?",
                        (iso(t), gid, uid))
        event(gid, uid, "inicio_intervalo")
        return await reply(interaction, f"☕ Intervalo iniciado às **{t:%H:%M:%S}**.")
    if action == "retorno":
        if s["state"] != "intervalo" or not s["break_started_at"]:
            return await reply(interaction, "Você não está em intervalo.")
        br = seconds(s["break_started_at"], t)
        with db() as con:
            con.execute("""UPDATE sessions SET state='trabalhando',break_started_at=NULL,
                break_seconds=break_seconds+? WHERE guild_id=? AND user_id=?""", (br, gid, uid))
        event(gid, uid, "retorno_intervalo")
        return await reply(interaction, f"🔵 Retorno registrado. Intervalo: **{duration(br)}**.")
    if action == "saida":
        br = s["break_seconds"]
        if s["state"] == "intervalo" and s["break_started_at"]:
            br += seconds(s["break_started_at"], t)
        total = seconds(s["started_at"], t)
        worked = max(0, total-br)
        event(gid, uid, "saida")
        with db() as con:
            con.execute("DELETE FROM sessions WHERE guild_id=? AND user_id=?", (gid, uid))
        return await reply(interaction,
            f"🔴 Expediente encerrado.\nTempo total: **{duration(total)}**\n"
            f"Intervalos: **{duration(br)}**\nTempo trabalhado: **{duration(worked)}**.")

class PunchPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Entrada", style=discord.ButtonStyle.success, emoji="🟢", custom_id="irmandade:ponto:entrada")
    async def entry(self, interaction, button):
        await punch(interaction, "entrada")
    @discord.ui.button(label="Intervalo", style=discord.ButtonStyle.secondary, emoji="☕", custom_id="irmandade:ponto:intervalo")
    async def break_start(self, interaction, button):
        await punch(interaction, "intervalo")
    @discord.ui.button(label="Retorno", style=discord.ButtonStyle.primary, emoji="🔵", custom_id="irmandade:ponto:retorno")
    async def break_end(self, interaction, button):
        await punch(interaction, "retorno")
    @discord.ui.button(label="Saída", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="irmandade:ponto:saida")
    async def exit(self, interaction, button):
        await punch(interaction, "saida")

@bot.event
async def on_ready():
    init_db()
    bot.add_view(PunchPanel())
    try:
        if GUILD_ID.isdigit():
            guild_obj = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild_obj)
            synced = await bot.tree.sync(guild=guild_obj)
        else:
            synced = await bot.tree.sync()
        print(f"Comandos sincronizados: {len(synced)}")
    except Exception as e:
        print("Erro ao sincronizar comandos:", e)
    print(f"Conectado como {bot.user}")

@bot.tree.command(name="painel_ponto", description="Publica o painel de ponto.")
@app_commands.guild_only()
async def painel_ponto(interaction: discord.Interaction):
    if not manager(interaction):
        return await reply(interaction, "Somente administradores podem publicar o painel.")
    embed = discord.Embed(title="🛣️ IRMANDADE TRANSPORTADORA | CONTROLE DE PONTO",
        description="Use os botões para registrar seu expediente.\n\n🟢 Entrada • ☕ Intervalo • 🔵 Retorno • 🔴 Saída",
        color=discord.Color.dark_gold())
    embed.set_footer(text="Registre os horários corretamente. Não compartilhe sua conta.")
    await interaction.response.send_message(embed=embed, view=PunchPanel())

@bot.tree.command(name="meuponto", description="Consulta seu expediente aberto.")
@app_commands.guild_only()
async def meuponto(interaction: discord.Interaction):
    s = session(interaction.guild.id, interaction.user.id)
    if not s:
        return await reply(interaction, "Você não possui expediente aberto.")
    total = seconds(s["started_at"])
    br = s["break_seconds"]
    if s["state"] == "intervalo" and s["break_started_at"]:
        br += seconds(s["break_started_at"])
    await reply(interaction, f"Estado: **{s['state']}**\nEntrada: **{s['started_at'][11:19]}**\n"
        f"Tempo decorrido: **{duration(total)}**\nIntervalos: **{duration(br)}**\n"
        f"Tempo trabalhado estimado: **{duration(max(0,total-br))}**")

@bot.tree.command(name="relatorio_ponto", description="Mostra registros recentes de ponto.")
@app_commands.describe(funcionario="Funcionário para consultar")
@app_commands.guild_only()
async def relatorio_ponto(interaction: discord.Interaction, funcionario: discord.Member = None):
    if not manager(interaction):
        return await reply(interaction, "Você não tem permissão para consultar relatórios de terceiros.")
    m = funcionario or interaction.user
    with db() as con:
        rows = con.execute("SELECT event,created_at FROM time_events WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 20",
                           (interaction.guild.id, m.id)).fetchall()
    if not rows:
        return await reply(interaction, f"Nenhum registro encontrado para {m.mention}.")
    emb = discord.Embed(title=f"📋 Ponto — {m.display_name}",
        description="\n".join(f"• **{r['event'].replace('_',' ').title()}** — {r['created_at'].replace('T',' ')}" for r in rows),
        color=discord.Color.gold())
    await reply(interaction, embed=emb)

@bot.tree.command(name="frete_criar", description="Cria um registro de frete/entrega.")
@app_commands.describe(descricao="Pedido, carga, destino ou observação", motorista="Motorista responsável")
@app_commands.guild_only()
async def frete_criar(interaction: discord.Interaction, descricao: str, motorista: discord.Member = None):
    if not manager(interaction):
        return await reply(interaction, "Somente a administração pode criar fretes.")
    if len(descricao) > 250:
        return await reply(interaction, "A descrição deve ter no máximo 250 caracteres.")
    with db() as con:
        cur = con.execute("INSERT INTO deliveries(guild_id,user_id,driver_id,description,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (interaction.guild.id, interaction.user.id, motorista.id if motorista else None, descricao, "Pendente", iso(), iso()))
        fid = cur.lastrowid
    audit(interaction.guild.id, interaction.user.id, "frete_criar", f"Frete #{fid}: {descricao}")
    await reply(interaction, f"📦 Frete **#{fid}** criado como **Pendente**." + (f" Motorista: {motorista.mention}" if motorista else ""), ephemeral=False)

@bot.tree.command(name="frete_status", description="Atualiza o status de um frete.")
@app_commands.describe(frete_id="Número do frete", status="Novo status")
@app_commands.choices(status=[
    app_commands.Choice(name="Em andamento", value="Em andamento"),
    app_commands.Choice(name="Concluído", value="Concluído"),
    app_commands.Choice(name="Cancelado", value="Cancelado"),
    app_commands.Choice(name="Pendente", value="Pendente")])
@app_commands.guild_only()
async def frete_status(interaction: discord.Interaction, frete_id: int, status: app_commands.Choice[str]):
    if not manager(interaction):
        return await reply(interaction, "Somente a administração pode alterar status.")
    with db() as con:
        cur = con.execute("UPDATE deliveries SET status=?,updated_at=? WHERE id=? AND guild_id=?",
                          (status.value, iso(), frete_id, interaction.guild.id))
    if not cur.rowcount:
        return await reply(interaction, "Frete não encontrado.")
    audit(interaction.guild.id, interaction.user.id, "frete_status", f"Frete #{frete_id}: {status.value}")
    await reply(interaction, f"Frete **#{frete_id}** atualizado para **{status.value}**.", ephemeral=False)

@bot.tree.command(name="fretes", description="Lista os fretes recentes.")
@app_commands.guild_only()
async def fretes(interaction: discord.Interaction):
    if not manager(interaction):
        return await reply(interaction, "Somente a administração pode consultar todos os fretes.")
    with db() as con:
        rows = con.execute("SELECT * FROM deliveries WHERE guild_id=? ORDER BY id DESC LIMIT 10",
                           (interaction.guild.id,)).fetchall()
    if not rows:
        return await reply(interaction, "Nenhum frete cadastrado.")
    lines = []
    for r in rows:
        driver = f"<@{r['driver_id']}>" if r["driver_id"] else "Não atribuído"
        lines.append(f"**#{r['id']}** · {r['status']} · {driver}\n{r['description']}")
    await reply(interaction, embed=discord.Embed(title="📦 Central de fretes", description="\n\n".join(lines), color=discord.Color.gold()))

@bot.tree.command(name="frota_adicionar", description="Cadastra um veículo.")
@app_commands.describe(veiculo="Modelo/tipo", placa="Placa ou identificador", observacoes="Observações opcionais")
@app_commands.guild_only()
async def frota_adicionar(interaction: discord.Interaction, veiculo: str, placa: str, observacoes: str = ""):
    if not manager(interaction):
        return await reply(interaction, "Somente a administração pode cadastrar veículos.")
    with db() as con:
        cur = con.execute("INSERT INTO fleet(guild_id,vehicle,plate,status,notes,created_at) VALUES(?,?,?,?,?,?)",
            (interaction.guild.id, veiculo[:100], placa[:20], "Disponível", observacoes[:250], iso()))
        vid = cur.lastrowid
    audit(interaction.guild.id, interaction.user.id, "frota_adicionar", f"Veículo #{vid} {veiculo} / {placa}")
    await reply(interaction, f"🚚 Veículo **#{vid}** cadastrado: **{veiculo}** · Identificação **{placa}**.", ephemeral=False)

@bot.tree.command(name="frota_status", description="Atualiza a situação de um veículo.")
@app_commands.describe(veiculo_id="ID do veículo", status="Situação atual")
@app_commands.choices(status=[
    app_commands.Choice(name="Disponível", value="Disponível"),
    app_commands.Choice(name="Em rota", value="Em rota"),
    app_commands.Choice(name="Em manutenção", value="Em manutenção"),
    app_commands.Choice(name="Indisponível", value="Indisponível")])
@app_commands.guild_only()
async def frota_status(interaction: discord.Interaction, veiculo_id: int, status: app_commands.Choice[str]):
    if not manager(interaction):
        return await reply(interaction, "Somente a administração pode alterar a frota.")
    with db() as con:
        cur = con.execute("UPDATE fleet SET status=? WHERE id=? AND guild_id=?",
                          (status.value, veiculo_id, interaction.guild.id))
    if not cur.rowcount:
        return await reply(interaction, "Veículo não encontrado.")
    audit(interaction.guild.id, interaction.user.id, "frota_status", f"Veículo #{veiculo_id}: {status.value}")
    await reply(interaction, f"Veículo **#{veiculo_id}**: **{status.value}**.", ephemeral=False)

@bot.tree.command(name="frota", description="Lista os veículos cadastrados.")
@app_commands.guild_only()
async def frota(interaction: discord.Interaction):
    if not manager(interaction):
        return await reply(interaction, "Somente a administração pode consultar a frota.")
    with db() as con:
        rows = con.execute("SELECT * FROM fleet WHERE guild_id=? ORDER BY id DESC LIMIT 20", (interaction.guild.id,)).fetchall()
    if not rows:
        return await reply(interaction, "A frota está vazia. Use `/frota_adicionar`.")
    lines = [f"**#{r['id']}** · {r['vehicle']} · `{r['plate']}` · **{r['status']}**" + (f"\n{r['notes']}" if r['notes'] else "") for r in rows]
    await reply(interaction, embed=discord.Embed(title="🚚 Frota da Irmandade", description="\n".join(lines), color=discord.Color.gold()))

@bot.tree.command(name="despesa_registrar", description="Registra uma despesa operacional.")
@app_commands.describe(categoria="Ex.: combustível, manutenção, pedágio", valor="Valor numérico", descricao="Detalhes")
@app_commands.guild_only()
async def despesa_registrar(interaction: discord.Interaction, categoria: str, valor: app_commands.Range[float, 0.01, 100000000], descricao: str):
    if not manager(interaction):
        return await reply(interaction, "Somente a administração pode registrar despesas.")
    with db() as con:
        cur = con.execute("INSERT INTO expenses(guild_id,user_id,category,amount,description,created_at) VALUES(?,?,?,?,?,?)",
            (interaction.guild.id, interaction.user.id, categoria[:60], float(valor), descricao[:250], iso()))
        eid = cur.lastrowid
    audit(interaction.guild.id, interaction.user.id, "despesa_registrar", f"Despesa #{eid}: {valor} - {categoria}")
    await reply(interaction, f"💸 Despesa **#{eid}** registrada: **R$ {valor:.2f}** · {categoria}.", ephemeral=False)

@bot.tree.command(name="financeiro_resumo", description="Mostra resumo das despesas registradas.")
@app_commands.guild_only()
async def financeiro_resumo(interaction: discord.Interaction):
    if not manager(interaction):
        return await reply(interaction, "Somente a administração pode consultar o financeiro.")
    with db() as con:
        rows = con.execute("SELECT category, SUM(amount) total, COUNT(*) qtd FROM expenses WHERE guild_id=? GROUP BY category ORDER BY total DESC",
                           (interaction.guild.id,)).fetchall()
        grand = con.execute("SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE guild_id=?", (interaction.guild.id,)).fetchone()["total"]
    desc = "\n".join(f"• {r['category']}: **R$ {r['total']:.2f}** ({r['qtd']} lançamento(s))" for r in rows) or "Nenhuma despesa registrada."
    await reply(interaction, embed=discord.Embed(title=f"💰 Resumo financeiro · Total R$ {grand:.2f}", description=desc, color=discord.Color.gold()))

@bot.tree.command(name="advertir", description="Registra uma advertência administrativa.")
@app_commands.describe(funcionario="Funcionário advertido", motivo="Motivo da advertência")
@app_commands.guild_only()
async def advertir(interaction: discord.Interaction, funcionario: discord.Member, motivo: str):
    if not manager(interaction):
        return await reply(interaction, "Somente a administração pode registrar advertências.")
    with db() as con:
        cur = con.execute("INSERT INTO warnings(guild_id,user_id,staff_id,reason,created_at) VALUES(?,?,?,?,?)",
                          (interaction.guild.id, funcionario.id, interaction.user.id, motivo[:500], iso()))
        wid = cur.lastrowid
    audit(interaction.guild.id, interaction.user.id, "advertir", f"Advertência #{wid} para {funcionario.id}")
    await reply(interaction, f"⚠️ Advertência **#{wid}** registrada para {funcionario.mention}. Motivo: {motivo}", ephemeral=False)

@bot.tree.command(name="advertencias", description="Consulta advertências de um funcionário.")
@app_commands.describe(funcionario="Funcionário para consultar")
@app_commands.guild_only()
async def advertencias(interaction: discord.Interaction, funcionario: discord.Member):
    if not manager(interaction):
        return await reply(interaction, "Somente a administração pode consultar advertências.")
    with db() as con:
        rows = con.execute("SELECT * FROM warnings WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 15",
                           (interaction.guild.id, funcionario.id)).fetchall()
    if not rows:
        return await reply(interaction, f"Nenhuma advertência registrada para {funcionario.mention}.")
    lines = [f"**#{r['id']}** · {r['created_at'].replace('T',' ')} · por <@{r['staff_id']}>\n{r['reason']}" for r in rows]
    await reply(interaction, embed=discord.Embed(title=f"⚠️ Advertências — {funcionario.display_name}", description="\n\n".join(lines), color=discord.Color.orange()))

@bot.tree.command(name="exportar_ponto", description="Exporta os registros de ponto para CSV.")
@app_commands.guild_only()
async def exportar_ponto(interaction: discord.Interaction):
    if not manager(interaction):
        return await reply(interaction, "Somente a administração pode exportar registros.")
    with db() as con:
        rows = con.execute("SELECT user_id,event,created_at FROM time_events WHERE guild_id=? ORDER BY id DESC", (interaction.guild.id,)).fetchall()
    if not rows:
        return await reply(interaction, "Não há registros para exportar.")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["discord_user_id", "evento", "data_hora"])
    for r in rows:
        writer.writerow([r["user_id"], r["event"], r["created_at"]])
    file = discord.File(io.BytesIO(buffer.getvalue().encode("utf-8-sig")), filename="relatorio_ponto_irmandade.csv")
    await interaction.response.send_message(content="📄 Exportação de ponto gerada.", file=file, ephemeral=True)

@bot.tree.command(name="painel_ajuda", description="Mostra os comandos do bot.")
async def painel_ajuda(interaction: discord.Interaction):
    embed = discord.Embed(title="🚛 IRMANDADE TRANSPORTADORA | Central do Bot",
        description=(
            "**Ponto**\n`/painel_ponto` · `/meuponto` · `/relatorio_ponto` · `/exportar_ponto`\n\n"
            "**Fretes**\n`/frete_criar` · `/frete_status` · `/fretes`\n\n"
            "**Frota**\n`/frota_adicionar` · `/frota_status` · `/frota`\n\n"
            "**Financeiro**\n`/despesa_registrar` · `/financeiro_resumo`\n\n"
            "**RH**\n`/advertir` · `/advertencias`\n\n"
            "Comandos administrativos exigem permissão de Administrador ou Gerenciar Servidor."
        ), color=discord.Color.dark_gold())
    await reply(interaction, embed=embed)

if not TOKEN:
    raise RuntimeError("Token ausente. Preencha DISCORD_TOKEN no arquivo .env.")
init_db()
bot.run(TOKEN)
