import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import sqlite3
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

# ==================== KEEP ALIVE ====================
app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot Discord Sanction en ligne ! ✅"

@app.route('/ping')
def ping():
    return "pong", 200

Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

# ==================== SQLITE DATABASE ====================
def init_db():
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sanctions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT NOT NULL,
                  user_name TEXT NOT NULL,
                  moderator_id TEXT NOT NULL,
                  moderator_name TEXT NOT NULL,
                  sanction_type TEXT NOT NULL,
                  reason TEXT,
                  duration_seconds INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  is_active BOOLEAN DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (guild_id TEXT PRIMARY KEY,
                  log_channel_id TEXT,
                  mod_role_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS niveaux_permission
                 (guild_id TEXT NOT NULL,
                  niveau INTEGER NOT NULL,
                  role_id TEXT NOT NULL,
                  role_name TEXT NOT NULL,
                  PRIMARY KEY (guild_id, niveau, role_id))''')
    conn.commit()
    conn.close()
    print("✅ Base de données initialisée")

def log_sanction(user_id, user_name, moderator_id, moderator_name, 
                 sanction_type, reason=None, duration=None):
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    c.execute('''INSERT INTO sanctions 
                 (user_id, user_name, moderator_id, moderator_name, 
                  sanction_type, reason, duration_seconds, is_active)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (str(user_id), user_name, str(moderator_id), moderator_name,
               sanction_type, reason, duration, 1))
    sanction_id = c.lastrowid
    conn.commit()
    conn.close()
    return sanction_id

def delete_sanction(sanction_id):
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    c.execute('DELETE FROM sanctions WHERE id = ?', (sanction_id,))
    conn.commit()
    conn.close()
    return c.rowcount > 0

def get_sanction_by_id(sanction_id):
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM sanctions WHERE id = ?''', (sanction_id,))
    sanction = c.fetchone()
    conn.close()
    return sanction

def get_user_sanctions(user_id, page=1, limit=10):
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    offset = (page - 1) * limit
    c.execute('''SELECT * FROM sanctions 
                 WHERE user_id = ? 
                 ORDER BY created_at DESC
                 LIMIT ? OFFSET ?''',
              (str(user_id), limit, offset))
    sanctions = c.fetchall()
    conn.close()
    return sanctions

def get_total_user_sanctions(user_id):
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    c.execute('''SELECT COUNT(*) FROM sanctions WHERE user_id = ?''',
              (str(user_id),))
    total = c.fetchone()[0]
    conn.close()
    return total

def get_active_sanctions(sanction_type=None):
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    if sanction_type:
        c.execute('''SELECT * FROM sanctions 
                     WHERE sanction_type = ? AND is_active = 1''',
                  (sanction_type,))
    else:
        c.execute('''SELECT * FROM sanctions WHERE is_active = 1''')
    sanctions = c.fetchall()
    conn.close()
    return sanctions

def deactivate_sanction(user_id, sanction_type):
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    c.execute('''UPDATE sanctions SET is_active = 0 
                 WHERE user_id = ? AND sanction_type = ? AND is_active = 1''',
              (str(user_id), sanction_type))
    conn.commit()
    conn.close()

def get_niveau_roles(guild_id, niveau):
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    c.execute('''SELECT role_id, role_name FROM niveaux_permission
                 WHERE guild_id = ? AND niveau = ?''',
              (str(guild_id), niveau))
    roles = c.fetchall()
    conn.close()
    return roles

def add_niveau_roles(guild_id, niveau, roles_list):
    """Ajoute des rôles à un niveau sans supprimer les existants"""
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()

    # Récupérer les rôles existants
    c.execute('''SELECT role_id FROM niveaux_permission 
                 WHERE guild_id = ? AND niveau = ?''',
              (str(guild_id), niveau))
    existing_role_ids = {row[0] for row in c.fetchall()}

    # Ajouter uniquement les nouveaux rôles
    added_count = 0
    for role in roles_list:
        role_id_str = str(role.id)
        if role_id_str not in existing_role_ids:
            c.execute('''INSERT INTO niveaux_permission 
                         (guild_id, niveau, role_id, role_name)
                         VALUES (?, ?, ?, ?)''',
                      (str(guild_id), niveau, role_id_str, role.name))
            added_count += 1

    conn.commit()
    conn.close()
    return added_count

def remove_niveau_role(guild_id, niveau, role_id):
    """Retire un rôle spécifique d'un niveau"""
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    c.execute('''DELETE FROM niveaux_permission 
                 WHERE guild_id = ? AND niveau = ? AND role_id = ?''',
              (str(guild_id), niveau, str(role_id)))
    conn.commit()
    conn.close()

def set_log_channel(guild_id, channel_id):
    """Définit le salon de logs"""
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO settings (guild_id, log_channel_id)
                 VALUES (?, ?)''', (str(guild_id), str(channel_id)))
    conn.commit()
    conn.close()

def get_log_channel(guild_id):
    """Récupère le salon de logs"""
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    c.execute('''SELECT log_channel_id FROM settings WHERE guild_id = ?''',
              (str(guild_id),))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def get_user_niveau(guild, user_id):
    """Récupère le niveau de permission d'un utilisateur"""
    conn = sqlite3.connect('sanctions.db')
    c = conn.cursor()
    member = guild.get_member(int(user_id))
    if not member:
        return 0

    # Vérifier si c'est le propriétaire du serveur
    if member.id == guild.owner_id:
        return 999  # Niveau maximum pour le propriétaire

    user_role_ids = [str(role.id) for role in member.roles]
    if not user_role_ids:
        return 0

    placeholders = ','.join('?' * len(user_role_ids))
    query = f'''SELECT MAX(niveau) FROM niveaux_permission
                WHERE guild_id = ? AND role_id IN ({placeholders})'''
    c.execute(query, (str(guild.id),) + tuple(user_role_ids))
    result = c.fetchone()[0]
    conn.close()
    return result if result else 0

def can_use_command(guild, user_id, required_niveau):
    """Vérifie si un utilisateur peut utiliser une commande"""
    user_niveau = get_user_niveau(guild, user_id)

    # Le propriétaire a tous les droits
    if user_id == guild.owner_id:
        return True

    # Les niveaux supérieurs peuvent utiliser les commandes des niveaux inférieurs
    return user_niveau >= required_niveau

# ==================== BOT SETUP ====================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)
unmute_tasks = {}

@bot.event
async def on_ready():
    print(f"✅ {bot.user} est connecté !")
    init_db()
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur sync: {e}")

async def schedule_unmute(member, duration_seconds, reason):
    await asyncio.sleep(duration_seconds)
    try:
        if member.guild.get_member(member.id):
            await member.timeout(None, reason=f"Fin du tempmute pour: {reason}")
            deactivate_sanction(str(member.id), 'tempmute')
            print(f"✅ {member} a été automatiquement démute")
    except Exception as e:
        print(f"❌ Erreur lors du démute auto: {e}")

# ==================== COMMANDE /HELP ====================
class HelpView(discord.ui.View):
    def __init__(self, current_page=1):
        super().__init__(timeout=60)
        self.current_page = current_page

    @discord.ui.button(label="←", style=discord.ButtonStyle.gray)
    async def left_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = self.current_page - 1 if self.current_page > 1 else 3
        await self.update_help(interaction, new_page)

    @discord.ui.button(label="→", style=discord.ButtonStyle.gray)
    async def right_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = self.current_page + 1 if self.current_page < 3 else 1
        await self.update_help(interaction, new_page)

    async def update_help(self, interaction: discord.Interaction, page: int):
        page = max(1, min(3, page))
        if page == 1:
            embed = discord.Embed(
                title="COMMANDES DU BOT SANCTION",
                description="Page 1/3 - Commandes de modération",
                color=discord.Color.from_str("#FFFFFF")
            )
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1466627343710683198/1467976169260454053/AnimeGif.gif")
            moderation_text = """
**📌 MODÉRATION**
`/tempmute` - Mute temporaire un utilisateur
-# *Utilisation: `/tempmute @user raison`*
`/unmute` - Retire le mute d'un utilisateur  
-# *Utilisation: `/unmute @user [raison]`*
`/to` - Timeout personnalisé
-# *Utilisation: `/to @user raison durée`*
`/unto` - Retire le timeout
-# *Utilisation: `/unto @user [raison]`*
`/ban` - Bannir un utilisateur
-# *Utilisation: `/ban @user raison`*
`/unban` - Débannir un utilisateur
-# *Utilisation: `/unban user_id`*
`/warn` - Avertir un utilisateur
-# *Utilisation: `/warn @user raison`*
"""
            embed.description = moderation_text
        elif page == 2:
            embed = discord.Embed(
                title="COMMANDES DU BOT SANCTION",
                description="Page 2/3 - Commandes de gestion",
                color=discord.Color.from_str("#FFFFFF")
            )
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1466627343710683198/1467976169260454053/AnimeGif.gif")
            gestion_text = """
**📊 GESTION**
`/delsanction` - Voir les sanctions
-# *Utilisation: `/delsanction @user [page]`*
`/mutelist` - Liste des mutes actifs
-# *Utilisation: `/mutelist`*
`/unmuteall` - Démute tout le monde
-# *Utilisation: `/unmuteall`*
"""
            embed.description = gestion_text
        else:
            embed = discord.Embed(
                title="COMMANDES DU BOT SANCTION",
                description="Page 3/3 - Configuration",
                color=discord.Color.from_str("#FFFFFF")
            )
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1466627343710683198/1467976169260454053/AnimeGif.gif")
            config_text = """
**⚙️ CONFIGURATION**
`/setniv` - Configurer les niveaux de permission (Propriétaire uniquement)
`/setlogs` - Définir le salon de logs (Propriétaire uniquement)
"""
            embed.description = config_text

        self.current_page = page
        for child in self.children:
            if child.label == "←":
                child.disabled = (page == 1)
            elif child.label == "→":
                child.disabled = (page == 3)

        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="help", description="Affiche toutes les commandes disponibles")
async def help_slash(interaction: discord.Interaction, page: int = 1):
    view = HelpView(current_page=page)
    await view.update_help(interaction, page)

# ==================== COMMANDE /MUTELIST ====================
@bot.tree.command(name="mutelist", description="Affiche la liste des utilisateurs mute")
async def mutelist(interaction: discord.Interaction):
    # Vérification des permissions
    user_niveau = get_user_niveau(interaction.guild, interaction.user.id)
    if user_niveau < 1 and not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission !", ephemeral=True)
        return

    try:
        active_mutes = get_active_sanctions('tempmute')
        if not active_mutes:
            embed = discord.Embed(
                description="Aucun utilisateur n'est actuellement mute.",
                color=discord.Color.from_str("#FFFFFF")
            )
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1466627343710683198/1467976169260454053/AnimeGif.gif")
            await interaction.response.send_message(embed=embed)
            return

        embed = discord.Embed(
            title="LISTE DES UTILISATEURS MUTE",
            color=discord.Color.from_str("#FFFFFF")
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1466627343710683198/1467976169260454053/AnimeGif.gif")

        list_text = ""
        for i, sanction in enumerate(active_mutes, 1):
            user_id = sanction[1]
            user_name = sanction[2]
            moderator_name = sanction[4]
            reason = sanction[6] or "Raison inconnue"
            member = interaction.guild.get_member(int(user_id))

            if member and member.is_timed_out():
                timeout_end = member.timed_out_until
                if timeout_end:
                    now = discord.utils.utcnow()
                    time_left = timeout_end - now
                    if time_left.total_seconds() > 0:
                        minutes_left = int(time_left.total_seconds() // 60)
                        hours_left = minutes_left // 60
                        days_left = hours_left // 24

                        if days_left > 0:
                            time_text = f"{days_left}j {hours_left % 24}h"
                        elif hours_left > 0:
                            time_text = f"{hours_left}h {minutes_left % 60}min"
                        else:
                            time_text = f"{minutes_left}min"

                        list_text += f"{i}. {user_name} ({user_id})\n"
                        list_text += f"   Temps restant: {time_text}\n"
                        list_text += f"   Raison: {reason}\n"
                        list_text += f"   Mute par: {moderator_name}\n\n"

        if not list_text:
            embed.description = "Aucun utilisateur n'est actuellement mute."
        else:
            embed.description = list_text

        embed.set_footer(text=f"Total: {len(active_mutes)} utilisateur(s) mute")
        await interaction.response.send_message(embed=embed)
        print(f"Mutelist affichée par {interaction.user}")

    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {str(e)}", ephemeral=True)
        print(f"Erreur mutelist: {e}")

# ==================== COMMANDE /UNMUTEALL ====================
@bot.tree.command(name="unmuteall", description="Unmute tous les utilisateurs mute")
async def unmuteall(interaction: discord.Interaction):
    # Vérification des permissions
    user_niveau = get_user_niveau(interaction.guild, interaction.user.id)
    if user_niveau < 2 and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Tu n'as pas la permission !", ephemeral=True)
        return

    try:
        for task in unmute_tasks.values():
            task.cancel()
        unmute_tasks.clear()

        muted_count = 0
        failed_count = 0

        async for member in interaction.guild.fetch_members(limit=None):
            if member.is_timed_out():
                try:
                    await member.timeout(None, reason=f"Unmute all par {interaction.user}")
                    deactivate_sanction(str(member.id), 'tempmute')
                    muted_count += 1
                    print(f"Unmuteall: {member} démute")
                except:
                    failed_count += 1

        embed = discord.Embed(
            description=f"Unmute all terminé\n\n{muted_count} utilisateur(s) démute(s)\n{failed_count} échec(s)",
            color=discord.Color.from_str("#FFFFFF")
        )
        await interaction.response.send_message(embed=embed)
        print(f"Unmuteall exécuté par {interaction.user}")

    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {str(e)}", ephemeral=True)

# ==================== COMMANDE /TEMPMUTE ====================
@bot.tree.command(name="tempmute", description="Mute temporairement un utilisateur")
@app_commands.describe(membre="Utilisateur à mute", raison="Raison du mute")
@app_commands.choices(raison=[
    app_commands.Choice(name="Troll - 10 min", value="troll"),
    app_commands.Choice(name="Spam - 10 min", value="spam"),
    app_commands.Choice(name="Profil inapproprié - 15 min", value="profil"),
    app_commands.Choice(name="Propos déplacé - 15 min", value="propos"),
    app_commands.Choice(name="Insulte - 20 min", value="insulte"),
    app_commands.Choice(name="Menace - 30 min", value="menace"),
    app_commands.Choice(name="Contenu sensible - 30 min", value="contenu_sensible"),
    app_commands.Choice(name="Contenu terroriste - 30 min", value="terroriste"),
])
async def tempmute(interaction: discord.Interaction, membre: discord.Member, raison: app_commands.Choice[str]):
    # Vérification des permissions
    user_niveau = get_user_niveau(interaction.guild, interaction.user.id)
    if user_niveau < 1 and not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission !", ephemeral=True)
        return

    durees = {
        "troll": 600, "spam": 600, "profil": 900, "propos": 900,
        "insulte": 1200, "menace": 1800, "contenu_sensible": 1800, "terroriste": 1800
    }

    duree_secondes = durees.get(raison.value, 600)
    duree_minutes = duree_secondes // 60

    try:
        await membre.timeout(
            discord.utils.utcnow() + timedelta(seconds=duree_secondes),
            reason=raison.name
        )

        raison_nom = raison.name.split(" - ")[0]
        log_sanction(
            user_id=membre.id,
            user_name=str(membre),
            moderator_id=interaction.user.id,
            moderator_name=str(interaction.user),
            sanction_type='tempmute',
            reason=raison_nom,
            duration_seconds=duree_secondes
        )

        embed = discord.Embed(
            description=f"{membre.mention} a été tempmute pendant {duree_minutes} minutes pour {raison_nom}",
            color=discord.Color.from_str("#FFFFFF")
        )

        await interaction.response.send_message(embed=embed)

        task = asyncio.create_task(schedule_unmute(membre, duree_secondes, raison.name))
        unmute_tasks[membre.id] = task

        print(f"Tempmute: {membre} pour {duree_minutes}min ({raison_nom})")

    except discord.Forbidden:
        await interaction.response.send_message("❌ Je n'ai pas la permission.", ephemeral=True)

# ==================== COMMANDE /UNMUTE ====================
@bot.tree.command(name="unmute", description="Retire le mute d'un utilisateur")
@app_commands.describe(membre="Utilisateur à unmute", raison="Raison (facultatif)")
async def unmute(interaction: discord.Interaction, membre: discord.Member, raison: str = None):
    # Vérification des permissions
    user_niveau = get_user_niveau(interaction.guild, interaction.user.id)
    if user_niveau < 1 and not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission !", ephemeral=True)
        return

    try:
        if membre.id in unmute_tasks:
            unmute_tasks[membre.id].cancel()
            del unmute_tasks[membre.id]

        await membre.timeout(None, reason=raison or "Unmute manuel")
        deactivate_sanction(str(membre.id), 'tempmute')

        reason_text = f" pour {raison}" if raison else ""
        embed = discord.Embed(
            description=f"{membre.mention} a été unmute{reason_text}",
            color=discord.Color.from_str("#FFFFFF")
        )

        await interaction.response.send_message(embed=embed)
        print(f"Unmute: {membre}")

    except discord.Forbidden:
        await interaction.response.send_message("❌ Je n'ai pas la permission.", ephemeral=True)

# ==================== COMMANDE /TO ====================
@bot.tree.command(name="to", description="Timeout un utilisateur")
@app_commands.describe(membre="Utilisateur à timeout", raison="Raison du timeout", temps="Durée")
@app_commands.choices(temps=[
    app_commands.Choice(name="5 minutes", value="5"),
    app_commands.Choice(name="10 minutes", value="10"),
    app_commands.Choice(name="15 minutes", value="15"),
    app_commands.Choice(name="30 minutes", value="30"),
    app_commands.Choice(name="1 heure", value="60"),
    app_commands.Choice(name="3 heures", value="180"),
    app_commands.Choice(name="6 heures", value="360"),
    app_commands.Choice(name="12 heures", value="720"),
    app_commands.Choice(name="1 jour", value="1440"),
    app_commands.Choice(name="3 jours", value="4320"),
    app_commands.Choice(name="7 jours", value="10080"),
])
async def to(interaction: discord.Interaction, membre: discord.Member, raison: str, temps: app_commands.Choice[str]):
    # Vérification des permissions
    user_niveau = get_user_niveau(interaction.guild, interaction.user.id)
    if user_niveau < 2 and not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission !", ephemeral=True)
        return

    try:
        duree_minutes = int(temps.value)
        duree_secondes = duree_minutes * 60

        await membre.timeout(
            discord.utils.utcnow() + timedelta(seconds=duree_secondes),
            reason=raison
        )

        if duree_minutes < 60:
            duree_texte = f"{duree_minutes} minutes"
        elif duree_minutes < 1440:
            heures = duree_minutes // 60
            duree_texte = f"{heures} heure{'s' if heures > 1 else ''}"
        else:
            jours = duree_minutes // 1440
            duree_texte = f"{jours} jour{'s' if jours > 1 else ''}"

        log_sanction(
            user_id=membre.id,
            user_name=str(membre),
            moderator_id=interaction.user.id,
            moderator_name=str(interaction.user),
            sanction_type='timeout',
            reason=raison,
            duration_seconds=duree_secondes
        )

        embed = discord.Embed(
            description=f"{membre.mention} a été timeout pour {raison} pendant {duree_texte}",
            color=discord.Color.from_str("#FFFFFF")
        )

        await interaction.response.send_message(embed=embed)

        task = asyncio.create_task(schedule_unmute(membre, duree_secondes, raison))
        unmute_tasks[membre.id] = task

        print(f"Timeout: {membre} pour {duree_texte} ({raison})")

    except ValueError:
        await interaction.response.send_message("❌ Durée invalide.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Je n'ai pas la permission.", ephemeral=True)

# ==================== COMMANDE /UNTO ====================
@bot.tree.command(name="unto", description="Retire le timeout d'un utilisateur")
@app_commands.describe(membre="Utilisateur", raison="Raison (facultatif)")
async def unto(interaction: discord.Interaction, membre: discord.Member, raison: str = None):
    # Vérification des permissions
    user_niveau = get_user_niveau(interaction.guild, interaction.user.id)
    if user_niveau < 2 and not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission !", ephemeral=True)
        return

    try:
        if membre.id in unmute_tasks:
            unmute_tasks[membre.id].cancel()
            del unmute_tasks[membre.id]

        await membre.timeout(None, reason=raison or "Fin du timeout")
        deactivate_sanction(str(membre.id), 'timeout')

        reason_text = f" pour {raison}" if raison else ""
        embed = discord.Embed(
            description=f"{membre.mention} n'est plus timeout{reason_text}",
            color=discord.Color.from_str("#FFFFFF")
        )

        await interaction.response.send_message(embed=embed)
        print(f"Untimeout: {membre}")

    except discord.Forbidden:
        await interaction.response.send_message("❌ Je n'ai pas la permission.", ephemeral=True)

# ==================== COMMANDE /BAN ====================
@bot.tree.command(name="ban", description="Bannir un utilisateur")
@app_commands.describe(membre="Utilisateur à bannir", raison="Raison du ban")
async def ban(interaction: discord.Interaction, membre: discord.Member, raison: str):
    # Vérification des permissions
    user_niveau = get_user_niveau(interaction.guild, interaction.user.id)
    if user_niveau < 3 and not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission de bannir !", ephemeral=True)
        return

    try:
        await membre.ban(reason=raison, delete_message_days=0)

        log_sanction(
            user_id=membre.id,
            user_name=str(membre),
            moderator_id=interaction.user.id,
            moderator_name=str(interaction.user),
            sanction_type='ban',
            reason=raison
        )

        embed = discord.Embed(
            description=f"{membre.mention} a été banni pour {raison}",
            color=discord.Color.from_str("#FFFFFF")
        )

        await interaction.response.send_message(embed=embed)
        print(f"Ban: {membre} pour {raison}")

    except discord.Forbidden:
        await interaction.response.send_message("❌ Je n'ai pas la permission de bannir.", ephemeral=True)

# ==================== COMMANDE /UNBAN ====================
@bot.tree.command(name="unban", description="Débannir un utilisateur")
@app_commands.describe(user="ID ou nom de l'utilisateur à débannir")
async def unban(interaction: discord.Interaction, user: str):
    # Vérification des permissions
    user_niveau = get_user_niveau(interaction.guild, interaction.user.id)
    if user_niveau < 3 and not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission de débannir !", ephemeral=True)
        return

    try:
        banned_users = [ban_entry async for ban_entry in interaction.guild.bans()]

        for ban_entry in banned_users:
            if user in (str(ban_entry.user.id), ban_entry.user.name, str(ban_entry.user)):
                await interaction.guild.unban(ban_entry.user)
                deactivate_sanction(str(ban_entry.user.id), 'ban')

                embed = discord.Embed(
                    description=f"{ban_entry.user.mention} a été débanni",
                    color=discord.Color.from_str("#FFFFFF")
                )

                await interaction.response.send_message(embed=embed)
                print(f"Unban: {ban_entry.user}")
                return

        await interaction.response.send_message("❌ Utilisateur non trouvé dans les bannis.", ephemeral=True)

    except discord.Forbidden:
        await interaction.response.send_message("❌ Je n'ai pas la permission de débannir.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {str(e)}", ephemeral=True)

# ==================== COMMANDE /WARN ====================
@bot.tree.command(name="warn", description="Avertir un utilisateur")
@app_commands.describe(membre="Utilisateur à warn", raison="Raison du warn")
async def warn(interaction: discord.Interaction, membre: discord.Member, raison: str):
    # Vérification des permissions
    user_niveau = get_user_niveau(interaction.guild, interaction.user.id)
    if user_niveau < 1 and not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission !", ephemeral=True)
        return

    log_sanction(
        user_id=membre.id,
        user_name=str(membre),
        moderator_id=interaction.user.id,
        moderator_name=str(interaction.user),
        sanction_type='warn',
        reason=raison
    )

    embed = discord.Embed(
        description=f"{membre.mention} a été warn pour {raison}",
        color=discord.Color.from_str("#FFFFFF")
    )

    await interaction.response.send_message(embed=embed)
    print(f"Warn: {membre} pour {raison}")

# ==================== COMMANDE /DELSANCTION ====================
class DeleteSanctionModal(discord.ui.Modal, title="Supprimer une sanction"):
    def __init__(self, member, current_page):
        super().__init__(timeout=60)
        self.member = member
        self.current_page = current_page

        self.sanction_id = discord.ui.TextInput(
            label="Numéro de la sanction",
            placeholder="Exemple: 15 pour la sanction #15",
            required=True,
            max_length=10
        )
        self.add_item(self.sanction_id)

    async def on_submit(self, interaction: discord.Interaction):
        # Vérification des permissions
        user_niveau = get_user_niveau(interaction.guild, interaction.user.id)
        if user_niveau < 3 and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Tu n'as pas la permission !", ephemeral=True)
            return

        try:
            sanction_num = int(self.sanction_id.value)

            # Vérifier si la sanction existe
            sanction = get_sanction_by_id(sanction_num)
            if not sanction:
                await interaction.response.send_message(
                    f"❌ La sanction #{sanction_num} n'existe pas.",
                    ephemeral=True
                )
                return

            # Vérifier si la sanction appartient au bon membre
            if str(sanction[1]) != str(self.member.id):
                await interaction.response.send_message(
                    f"❌ La sanction #{sanction_num} n'appartient pas à {self.member.mention}.",
                    ephemeral=True
                )
                return

            # Supprimer la sanction
            if delete_sanction(sanction_num):
                # Message public de confirmation
                confirmation_embed = discord.Embed(
                    title="✅ SUPPRESSION RÉUSSIE",
                    description=f"La sanction **#{sanction_num}** a bien été supprimée !",
                    color=discord.Color.green()
                )
                confirmation_embed.add_field(name="Utilisateur", value=self.member.mention, inline=True)
                confirmation_embed.add_field(name="Type", value=sanction[5], inline=True)
                confirmation_embed.add_field(name="Supprimé par", value=interaction.user.mention, inline=True)

                await interaction.response.send_message(embed=confirmation_embed)

                # Envoyer les logs dans le salon configuré
                log_channel_id = get_log_channel(str(interaction.guild.id))
                if log_channel_id:
                    log_channel = interaction.guild.get_channel(int(log_channel_id))
                    if log_channel:
                        log_embed = discord.Embed(
                            title="📝 LOGS DE SUPPRESSION",
                            color=discord.Color.orange(),
                            timestamp=datetime.now()
                        )
                        log_embed.add_field(name="Utilisateur", value=self.member.mention, inline=False)
                        log_embed.add_field(name="Sanction supprimée", value=f"#{sanction_num} ({sanction[5]})", inline=False)
                        log_embed.add_field(name="Raison", value=sanction[6] or "Non spécifiée", inline=False)
                        log_embed.add_field(name="Supprimé par", value=interaction.user.mention, inline=False)

                        await log_channel.send(embed=log_embed)

                # CORRECTION ICI : Ligne 804 corrigée
                print(f"Sanction #{sanction_num} supprimée par {interaction.user}")
            else:
                await interaction.response.send_message(
                    f"❌ Erreur lors de la suppression de la sanction #{sanction_num}.",
                    ephemeral=True
                )

        except ValueError:
            await interaction.response.send_message(
                "❌ Veuillez entrer un numéro valide.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Erreur: {str(e)}",
                ephemeral=True
            )

class DelSanctionView(discord.ui.View):
    def __init__(self, member, page, total_pages, sanctions):
        super().__init__(timeout=60)
        self.member = member
        self.page = page
        self.total_pages = total_pages
        self.sanctions = sanctions

        left_button = discord.ui.Button(label="←", style=discord.ButtonStyle.gray, disabled=(page == 1))
        left_button.callback = self.left_callback
        self.add_item(left_button)

        indicator_button = discord.ui.Button(
            label=f"{page}/{total_pages}", 
            style=discord.ButtonStyle.blurple,
            disabled=True
        )
        self.add_item(indicator_button)

        right_button = discord.ui.Button(label="→", style=discord.ButtonStyle.gray, disabled=(page == total_pages))
        right_button.callback = self.right_callback
        self.add_item(right_button)

        delete_button = discord.ui.Button(
            label="Supprimer une sanction", 
            style=discord.ButtonStyle.danger,
            row=1,
            emoji="🗑️"
        )
        delete_button.callback = self.delete_callback
        self.add_item(delete_button)

    async def left_callback(self, interaction: discord.Interaction):
        if self.page > 1:
            await self.update_view(interaction, self.page - 1)

    async def right_callback(self, interaction: discord.Interaction):
        if self.page < self.total_pages:
            await self.update_view(interaction, self.page + 1)

    async def delete_callback(self, interaction: discord.Interaction):
        modal = DeleteSanctionModal(self.member, self.page)
        await interaction.response.send_modal(modal)

    async def update_view(self, interaction: discord.Interaction, new_page):
        sanctions = get_user_sanctions(str(self.member.id), page=new_page)
        total_sanctions = get_total_user_sanctions(str(self.member.id))
        total_pages = max(1, (total_sanctions + 9) // 10)

        embed = discord.Embed(
            title=f"📜 Historique des sanctions de {self.member.name}",
            color=discord.Color.from_str("#FFFFFF")
        )
        embed.set_thumbnail(url=self.member.display_avatar.url)

        if not sanctions:
            embed.description = "Aucune sanction enregistrée."
        else:
            sanctions_texte = ""
            for sanction in sanctions:
                sanction_id = sanction[0]
                sanction_type = sanction[5]
                reason = sanction[6] or "Non spécifiée"
                moderator = sanction[4]
                date = datetime.strptime(sanction[8], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M') if sanction[8] else "Date inconnue"
                sanctions_texte += f"**{sanction_type.upper()}** #{sanction_id}\n"
                sanctions_texte += f"> {reason}\n"
                sanctions_texte += f"> Par {moderator} • {date}\n\n"
            embed.description = sanctions_texte
            embed.set_footer(text=f"Page {new_page}/{total_pages}")

        self.page = new_page
        self.total_pages = total_pages

        for child in self.children:
            if child.label == "←":
                child.disabled = (new_page == 1)
            elif child.label == f"{self.page}/{self.total_pages}":
                child.label = f"{new_page}/{total_pages}"
            elif child.label == "→":
                child.disabled = (new_page == total_pages)

        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="delsanction", description="Voir les sanctions d'un utilisateur")
@app_commands.describe(membre="Utilisateur concerné", page="Page à afficher")
async def delsanction(interaction: discord.Interaction, membre: discord.Member, page: int = 1):
    # Vérification des permissions
    user_niveau = get_user_niveau(interaction.guild, interaction.user.id)
    if user_niveau < 1 and not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission !", ephemeral=True)
        return

    sanctions = get_user_sanctions(str(membre.id), page=page)
    total_sanctions = get_total_user_sanctions(str(membre.id))
    total_pages = max(1, (total_sanctions + 9) // 10)

    embed = discord.Embed(
        title=f"📜 Historique des sanctions de {membre.name}",
        color=discord.Color.from_str("#FFFFFF")
    )
    embed.set_thumbnail(url=membre.display_avatar.url)

    if not sanctions:
        embed.description = "Aucune sanction enregistrée."
    else:
        sanctions_texte = ""
        for sanction in sanctions:
            sanction_id = sanction[0]
            sanction_type = sanction[5]
            reason = sanction[6] or "Non spécifiée"
            moderator = sanction[4]
            date = datetime.strptime(sanction[8], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M') if sanction[8] else "Date inconnue"
            sanctions_texte += f"**{sanction_type.upper()}** #{sanction_id}\n"
            sanctions_texte += f"> {reason}\n"
            sanctions_texte += f"> Par {moderator} • {date}\n\n"
        embed.description = sanctions_texte
        embed.set_footer(text=f"Page {page}/{total_pages}")

    view = DelSanctionView(membre, page, total_pages, sanctions)
    await interaction.response.send_message(embed=embed, view=view)
    print(f"Delsanction: {membre} page {page}")

# ==================== COMMANDE /SETNIV ====================
class NiveauSelect(discord.ui.Select):
    def __init__(self, guild):
        options = [
            discord.SelectOption(label="Niveau 1", value="1", description="Niveau de permission 1"),
            discord.SelectOption(label="Niveau 2", value="2", description="Niveau de permission 2"),
            discord.SelectOption(label="Niveau 3", value="3", description="Niveau de permission 3"),
            discord.SelectOption(label="Niveau 4", value="4", description="Niveau de permission 4"),
        ]
        super().__init__(
            placeholder="Sélectionner le niveau de permission à modifier",
            min_values=1,
            max_values=1,
            options=options
        )
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        # Vérifier que l'utilisateur est propriétaire du serveur
        if interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                "❌ Seul le propriétaire du serveur peut configurer les niveaux de permission.",
                ephemeral=True
            )
            return

        niveau = int(self.values[0])
        embed = discord.Embed(
            title=f"# Configuration niveau {niveau}",
            description="**Les niveaux supérieurs peuvent utiliser les commandes des niveaux inférieurs**\n\nNiveau 4 > Niveau 3 > Niveau 2 > Niveau 1",
            color=discord.Color.from_str("#FFFFFF")
        )

        current_roles = get_niveau_roles(str(interaction.guild.id), niveau)
        if current_roles:
            roles_text = ""
            for role_id, role_name in current_roles:
                role = interaction.guild.get_role(int(role_id))
                if role:
                    roles_text += f"• {role.mention} ({role_name})\n"
            embed.add_field(name="Rôles actuels", value=roles_text or "Aucun rôle", inline=False)
        else:
            embed.add_field(name="Rôles actuels", value="Aucun rôle configuré", inline=False)

        view = discord.ui.View(timeout=60)

        # Bouton pour ajouter des rôles
        add_roles_button = discord.ui.Button(
            label="Ajouter des rôles",
            style=discord.ButtonStyle.primary,
            emoji="➕"
        )

        async def add_roles_callback(interaction: discord.Interaction):
            await self.show_add_roles(interaction, niveau)
        add_roles_button.callback = add_roles_callback
        view.add_item(add_roles_button)

        # Bouton pour retirer des rôles (si il y en a)
        if current_roles:
            remove_roles_button = discord.ui.Button(
                label="Retirer des rôles",
                style=discord.ButtonStyle.danger,
                emoji="➖"
            )

            async def remove_roles_callback(interaction: discord.Interaction):
                await self.show_remove_roles(interaction, niveau)
            remove_roles_button.callback = remove_roles_callback
            view.add_item(remove_roles_button)

        await interaction.response.edit_message(embed=embed, view=view)

    async def show_add_roles(self, interaction: discord.Interaction, niveau):
        # Message d'instructions
        await interaction.response.edit_message(
            content="**📝 Mentionnez les rôles que vous voulez ajouter au niveau :**\n\nVous pouvez mentionner plusieurs rôles en les séparant par un espace.\nExemple: `@Modérateur @Admin @Staff`",
            embed=None,
            view=None
        )

        # Attendre que l'utilisateur mentionne des rôles
        def check(msg):
            return msg.author == interaction.user and msg.channel == interaction.channel

        try:
            msg = await bot.wait_for('message', timeout=60.0, check=check)

            # Récupérer les rôles mentionnés
            selected_roles = []
            for role_mention in msg.mentions:
                if role_mention not in selected_roles:
                    selected_roles.append(role_mention)

            # Ajouter également les rôles par ID
            for word in msg.content.split():
                if word.startswith('<@&') and word.endswith('>'):
                    role_id = word[3:-1]
                    role = interaction.guild.get_role(int(role_id))
                    if role and role not in selected_roles:
                        selected_roles.append(role)

            if not selected_roles:
                await interaction.followup.send(
                    "❌ Aucun rôle valide mentionné.",
                    ephemeral=True
                )
                return

            # Ajouter les rôles au niveau
            added_count = add_niveau_roles(str(interaction.guild.id), niveau, selected_roles)

            # Supprimer le message de l'utilisateur
            try:
                await msg.delete()
            except:
                pass

            embed = discord.Embed(
                title="✅ RÔLES AJOUTÉS",
                color=discord.Color.green()
            )

            roles_text = ""
            for role in selected_roles:
                roles_text += f"• {role.mention}\n"

            embed.add_field(name="Niveau:", value=str(niveau), inline=False)
            embed.add_field(name="Rôles ajoutés:", value=roles_text or "Aucun rôle", inline=False)
            embed.add_field(name="Total ajouté:", value=f"{added_count} rôle(s)", inline=False)
            embed.set_footer(text="Les niveaux supérieurs peuvent utiliser les commandes des niveaux inférieurs")

            await interaction.edit_original_response(content=None, embed=embed, view=None)
            print(f"Setniv: {added_count} rôles ajoutés au niveau {niveau} par {interaction.user}")

        except asyncio.TimeoutError:
            await interaction.edit_original_response(
                content="⏱️ Temps écoulé. Veuillez réessayer.",
                embed=None,
                view=None
            )

    async def show_remove_roles(self, interaction: discord.Interaction, niveau):
        # Récupérer les rôles actuels de ce niveau
        current_roles = get_niveau_roles(str(interaction.guild.id), niveau)

        if not current_roles:
            await interaction.response.send_message(
                "❌ Aucun rôle à retirer pour ce niveau.",
                ephemeral=True
            )
            return

        # Convertir en objets Role
        roles_to_remove = []
        for role_id, role_name in current_roles:
            role = interaction.guild.get_role(int(role_id))
            if role:
                roles_to_remove.append(role)

        if not roles_to_remove:
            await interaction.response.send_message(
                "❌ Aucun rôle valide à retirer.",
                ephemeral=True
            )
            return

        # Créer un menu déroulant pour sélectionner les rôles à retirer
        options = []
        for role in roles_to_remove[:25]:
            display_name = role.name[:25] if len(role.name) > 25 else role.name
            options.append(
                discord.SelectOption(
                    label=display_name,
                    value=str(role.id),
                    description=f"ID: {role.id}",
                    emoji="⚙️"
                )
            )

        role_select = discord.ui.Select(
            placeholder=f"Sélectionner les rôles à retirer ({len(roles_to_remove)})",
            min_values=0,
            max_values=len(options),
            options=options
        )

        async def role_select_callback(interaction: discord.Interaction):
            selected_role_ids = role_select.values

            if not selected_role_ids:
                await interaction.response.send_message(
                    "❌ Aucun rôle sélectionné.",
                    ephemeral=True
                )
                return

            # Retirer les rôles
            removed_count = 0
            removed_roles = []
            for role_id in selected_role_ids:
                role = interaction.guild.get_role(int(role_id))
                if role:
                    remove_niveau_role(str(interaction.guild.id), niveau, role.id)
                    removed_count += 1
                    removed_roles.append(role)

            embed = discord.Embed(
                title="✅ RÔLES RETIRÉS",
                color=discord.Color.orange()
            )

            roles_text = ""
            for role in removed_roles:
                roles_text += f"• {role.mention}\n"

            embed.add_field(name="Niveau:", value=str(niveau), inline=False)
            embed.add_field(name="Rôles retirés:", value=roles_text or "Aucun rôle", inline=False)
            embed.add_field(name="Total retiré:", value=f"{removed_count} rôle(s)", inline=False)

            await interaction.response.edit_message(content=None, embed=embed, view=None)
            print(f"Setniv: {removed_count} rôles retirés du niveau {niveau} par {interaction.user}")

        role_select.callback = role_select_callback

        view = discord.ui.View(timeout=60)
        view.add_item(role_select)

        # Bouton retour
        back_button = discord.ui.Button(
            label="Retour",
            style=discord.ButtonStyle.gray,
            emoji="⬅️"
        )

        async def back_callback(interaction: discord.Interaction):
            await self.callback(interaction)
        back_button.callback = back_callback
        view.add_item(back_button)

        await interaction.response.edit_message(
            content="**Sélectionnez les rôles à retirer du niveau :**",
            embed=None,
            view=view
        )

@bot.tree.command(name="setniv", description="Configurer les niveaux de permission")
async def setniv(interaction: discord.Interaction):
    # Vérifier que l'utilisateur est propriétaire du serveur
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message(
            "❌ Seul le propriétaire du serveur peut configurer les niveaux de permission.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="# CONFIGURATION NIVEAU",
        description="**Sélectionnez un niveau pour ajouter ou retirer des rôles.**\n\nLes niveaux supérieurs peuvent utiliser les commandes des niveaux inférieurs.",
        color=discord.Color.from_str("#FFFFFF")
    )
    niveau_select = NiveauSelect(interaction.guild)
    view = discord.ui.View(timeout=60)
    view.add_item(niveau_select)
    await interaction.response.send_message(embed=embed, view=view)
    print(f"Setniv utilisé par {interaction.user}")

# ==================== COMMANDE /SETLOGS ====================
@bot.tree.command(name="setlogs", description="Définir le salon de logs")
@app_commands.describe(salon="Salon où envoyer les logs de suppression")
async def setlogs(interaction: discord.Interaction, salon: discord.TextChannel):
    # Vérifier que l'utilisateur est propriétaire du serveur
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message(
            "❌ Seul le propriétaire du serveur peut configurer les logs.",
            ephemeral=True
        )
        return

    set_log_channel(str(interaction.guild.id), str(salon.id))

    embed = discord.Embed(
        title="✅ SALON DE LOGS DÉFINI",
        description=f"Les logs de suppression seront envoyés dans {salon.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)
    print(f"Salon de logs défini: {salon.name} par {interaction.user}")

# ==================== LANCE LE BOT ====================
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ DISCORD_TOKEN non défini !")
    print("⚠️  Ajoute-le dans les Secrets (clé 🗝️ à gauche)")