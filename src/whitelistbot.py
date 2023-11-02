#
# Written by @Sentennial
# Discord ID: 177189581060308992
# TODO: should players be able to freely link to any steamID? Would this be abused? Use an in-game chat verification code method instead?
# TODO: optionally warn players when they join with their seed points/days? Need option with default - seed_ingamewarn
# TODO: add discord logging for actions
# TODO: option for monthly point wipe, delete all from seeding_Users - seed_monthlywipe
# TODO: Create front-end panel with status and buttons
#       Show on embed: threshold, pointworth, adminsaccrue, minplayers, maxplayers, pointcap
#       Automatically update the embed when settings are changed 
#       Buttons:
#           Status: Show user's points and worth in days, and if they're banking
#           Link: link discordID to steamID
#           AutoRedeem: toggle user's isBanking
#           Redeem: If user's points are > threshold, allow to redeem X days worth of points and apply to whitelist

import discord
import os
import sqlite3
import re
import requests
import asyncio
import time
import traceback
import aiocron
import patreon
import random
import socket
import math
from typing import List
from rcon.source import Client as rClient
from discord import app_commands
from discord import ui
from contextlib import closing
from datetime import datetime, timedelta
import aiohttp
from ast import literal_eval
import logging

# For settings configurable via Discord commands, these are the defaults if no value is set.
Defaults = {
    'seed_autoredeem': False,
    'seed_trackadmins': True,
    'seed_threshold': 360,
    'seed_pointworth': 0.0833333,
    'seed_adminsaccrue': False,
    'seed_minplayers': 2,
    'seed_maxplayers': 50,
    'seed_pointcap': 0,
}
regex_SingleID = "^[0-9]{17}$"
nl = "\n"
cookieJar = aiohttp.CookieJar()
PayPalAuthToken = ''
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

class MyGroup(app_commands.Group):
    ...
group_SquadGroups = MyGroup(name="groups", description="Manage Squad in-game group permissions", default_permissions=discord.Permissions())
group_PayPal = MyGroup(name="paypal", description="Commands for managing the PayPal integration.", default_permissions=discord.Permissions())
group_MultiWL = MyGroup(name="multiwl", description="Commands for managing the Multi-WL feature.", default_permissions=discord.Permissions())
group_Clans = MyGroup(name="clans", description="Commands for managing the Clans whitelist feature.", default_permissions=discord.Permissions())
group_Seeding= MyGroup(name="seeding", description="Commands for managing the Seeding whitelist reward feature.", default_permissions=discord.Permissions())

#####################################
######### CLASS SquadClient #########
class SquadClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    
    isReady = False

    async def on_ready(self):
        logging.info(f'Logged on as {self.user}!')
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='Squad Permissions'))
        self.isReady = True
        logging.info("Syncing commands... Please wait.")
        try:
            MY_GUILD = discord.Object(id=cfg['DiscordServer_ID'])
            if (cfg.get('featureEnable_SquadGroups', False)): self.tree.add_command(group_SquadGroups)
            if (cfg.get('featureEnable_Paypal', False)): self.tree.add_command(group_PayPal)
            self.tree.add_command(group_MultiWL)
            if (cfg.get('featureClanWhitelists', False)): self.tree.add_command(group_Clans)
            if (cfg.get('featureEnable_Seeding', False)): self.tree.add_command(group_Seeding)
            self.tree.copy_global_to(guild=MY_GUILD)
            await self.tree.sync(guild=MY_GUILD)
        except Exception as e:
            logging.error(e)
            return
        logging.info("Commands sync complete.")
        logging.info("Re-listening to buttons... Please wait.")
        self.add_view(ButtonWhitelistGatherView())
        self.add_view(ClanWhitelistsView())
        self.add_view(PayPalWhitelistView())
        logging.info("Buttons are now active.")
        logging.info("Bot is ready!")

    ###### Methods ######
  
    async def updatePatreonWhitelists(self):
        if (client.isReady == False):
            return 0
        whitelistStr = 'Group=WhitelistBot:reserve\n\n'
        for validUser in await getSteamIDsForWhitelist():
            whitelistStr += f'Admin={validUser[0]}:WhitelistBot // {validUser[1]}\n'
        
        with open(cfg['multiwl_outputFile'], "w") as f:
            f.write(whitelistStr)

    async def updateClanWhitelists(self):
        if (client.isReady == False):
            return
        whitelistStr = 'Group=WhitelistBot:reserve\n\n'
        for validUser in await getSteamIDsForClanWhitelist():
            whitelistStr += f'Admin={validUser[0]}:WhitelistBot // {validUser[1]}\n'
        
        with open(cfg['pathToClanWhitelist'], "w") as f:
            f.write(whitelistStr)
    
    async def sendWhitelistModal(self, channelID: int):
        guild = client.get_guild(cfg['DiscordServer_ID'])
        channel = guild.get_channel(channelID)
        embed = discord.Embed(title="Manage your Whitelist(s)!", 
        description="""Click the ✏️ button below to view and edit the SteamIDs on your whitelist. 
        Separate multiple SteamIDs with commas.

        To see the SteamIDs on your whitelist, click the 🏆 button.
        To see if someone else has your SteamID on *their* whitelist, click the 🔎 button.
        
        You **must** have your Patreon linked to your Discord if you buy your whitelist via Patreon. *(use the Link button below)*""")
        embed.add_field(name="​", inline=False, value="Made with ♥ by <@177189581060308992>")
        try:
            view = ButtonWhitelistGatherView()
        except Exception as e:
            logging.error(str(e))
            return
        return (await channel.send(embed=embed, view=view))
    
    async def sendClanWhitelistPanel(self, channelID:int):
        guild = client.get_guild(cfg['DiscordServer_ID'])
        channel = guild.get_channel(channelID)
        embed = discord.Embed(title=f"Manage your {cfg['clanMoniker']} Whitelists!", 
        description=f"""Click the ✏️ button below to view and edit the SteamIDs on your {cfg['clanMoniker']} whitelist. 
        \nClick the 📝 button below to view your {cfg['clanMoniker']} whitelist. 
        \nSeparate multiple SteamIDs with commas.""")
        embed.add_field(name="​", inline=False, value="Made with ♥ by <@177189581060308992>")
        view = ClanWhitelistsView()
        await channel.send(embed=embed, view=view)
  
    def getDiscordUsersSteamID(self, discordID):
        # Get SteamID
        try:
            with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
                with closing(sqlite.cursor()) as sqlitecursor:
                    rows = sqlitecursor.execute("SELECT steamID FROM statsSteamIDs WHERE discordID = ?", (discordID,)).fetchone()
                    return rows[0]
        except:
            return None
  
    def getWhitelistIdsFromDiscordID(self, discordID):
        currentIDString = ''
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rows = sqlitecursor.execute("SELECT steamID FROM whitelistSteamIDs WHERE discordID = ?", (str(discordID),)).fetchall()
                if (len(rows) > 0):
                    for row in rows:
                        currentIDString += str(row[0]) + ', '
        return currentIDString.strip(', ')

    def searchWhitelistsForID(self, steamID):
        #"CREATE TABLE IF NOT EXISTS whitelistSteamIDs (discordID TEXT NOT NULL, steamID TEXT NOT NULL, discordName TEXT DEFAULT ' ', changedOnEpoch INTEGER NOT NULL DEFAULT 0 )"
        res = '(None)'
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rows = sqlitecursor.execute("SELECT discordID FROM whitelistSteamIDs WHERE steamID = ?", (str(steamID),)).fetchall()
                if (len(rows) > 0):
                    for row in rows:
                        if (res == '(None)'): res = ''
                        res += '<@'+str(row[0]) + '>, '
        return res.strip(', ')

    def recordSteamIDs(self, CSV_ofSteamIDs, discordID, discordName, force = False, thirdPerson = False):
        singleIDregex = "([0-9]{17})(.*)"
        stringRemaining = CSV_ofSteamIDs.strip("/").replace('\n', ' ')
        steamIDs = []
        numWhitelists = self.getMaxWhitelistsByDiscordID(int(discordID))
        while True:
            rematch = re.search(singleIDregex, stringRemaining)
            if (rematch is None):
                break
            steamIDs.append(rematch.group(1))
            stringRemaining = rematch.group(2)
            if (len(stringRemaining) <= 0):
                break

        if (len(steamIDs) >= 1): 
            # Add to DB
            with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
                with closing(sqlite.cursor()) as sqlitecursor:
                    todayEpoch = int(time.time())
                    
                    # Rate Limit, if debug=false, and user is not me
                    rows = sqlitecursor.execute("SELECT changedOnEpoch FROM whitelistSteamIDs WHERE discordID = ? LIMIT 1;", (discordID,)).fetchone()
                    if (rows is None):
                        pass
                    elif (len(rows) == 1):
                        changedOn = rows[0]
                        if ((todayEpoch - changedOn) < cfg['secondsBetweenWhitelistUpdates'] and force == False):# and DEBUG == False and discordID != 177189581060308992): 
                            # nextChangeIn = cfg['secondsBetweenWhitelistUpdates'] - (todayEpoch - changedOn)
                            nextChangeIn = todayEpoch + (cfg['secondsBetweenWhitelistUpdates'] - (todayEpoch - changedOn))
                            return "ERROR. In order to prevent abuse, you can only submit here once per day. You can next make a change to your whitelist after <t:" + str(nextChangeIn) + ":f>, or ask an Admin for a permit."

                    # Remove all IDs associated with discord user, then readd them all
                    # (discordID TEXT NOT NULL, steamID TEXT NOT NULL, discordName TEXT DEFAULT ' ', changedOnEpoch INTEGER NOT NULL )
                    sqlitecursor.execute("DELETE FROM whitelistSteamIDs WHERE discordID = ?", (str(discordID),))
                    for steamID in steamIDs:
                        sqlitecursor.execute("INSERT INTO whitelistSteamIDs(discordID,steamID,discordName,changedOnEpoch) VALUES (?,?,?,?)", (str(discordID), str(steamID), discordName, todayEpoch))
                sqlite.commit()
            
            description = "SUCCESS! "+ ("<@"+str(discordID)+">'s" if thirdPerson else "Your")+" whitelist has been updated.\n"
            if (numWhitelists != 0):
                description += "Changes to your whitelist will take effect on next map change on each server.\n"
            if (numWhitelists == 0):
                description += ("<@"+str(discordID)+"> doesn't " if thirdPerson else "You don't ") + "currently have any Discord roles that provide whitelist slots."
            elif (numWhitelists == 1):
                description += ("<@"+str(discordID)+"> has" if thirdPerson else "You have")+" the single whitelist tier, only the first steamID below will gain whitelist."
            elif (numWhitelists > 1):
                description += ("<@"+str(discordID)+"> has" if thirdPerson else "You have")+" the group whitelist tier, only the first ("+str(numWhitelists)+") steamIDs entered will gain whitelist."
            return description
        
        # There were no steamIDs in CSV_ofSteamIDs
        description = """Error, that doesn't seem to be a proper set of steamIDs
        \n**WHERE DO YOU GET STEAMID??** See gif 👇
        \nhttps://i.imgur.com/eau1SXw.mp4"""
        return description
    
    def getMaxWhitelistsByDiscordID(self, discordID):
        CDDiscordServer = client.get_guild(cfg['DiscordServer_ID'])
        try:
            member = CDDiscordServer.get_member(int(discordID))
            if (member is None):
                return 0
            membersRoles = member.roles
        except:
            return 0

        numWhitelists = 0
        if (cfg['whitelistsNeedThisDiscordRoleID'] != 0 and CDDiscordServer.get_role(cfg['whitelistsNeedThisDiscordRoleID']) not in membersRoles):
            return 0 # Member doesn't have the required role
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rolesRows = sqlitecursor.execute("SELECT roleID,numWhitelists FROM multiwl_RolesWhitelists").fetchall()
        rolesDict = {}
        for role,num in rolesRows:
            rolesDict.setdefault(role,num)
        for role in membersRoles:
            if str(role.id) in rolesDict:
                tmp = rolesDict[str(role.id)]
                if tmp > numWhitelists:
                    numWhitelists = tmp
        return numWhitelists
    
    def getWhitelistStatus(self, discordID, thirdPerson = False):
        maxWhitelists = client.getMaxWhitelistsByDiscordID(discordID)
        description = ""
        steamIDs = client.getWhitelistIdsFromDiscordID(discordID)
        if (maxWhitelists == 0):
            description += ("They" if thirdPerson else "You")+" don't currently have any Discord roles that provide whitelist slots."
            description +=" We still have the following steamIDs on record for when "+("they" if thirdPerson else "you")+" do subscribe."
            description += "" if thirdPerson else "\nIf you believe this to be an error, please contact an Admin"
        elif (maxWhitelists == 1):
            description += ("They" if thirdPerson else "You") + " have the single whitelist tier, only the first steamID below will be on your whitelist."
        elif (maxWhitelists > 1):
            description += ("They" if thirdPerson else "You")+f" have the group whitelist tier, the first ({str(maxWhitelists)}) out of the {str(len(steamIDs.split(', ')))} steamIDs below will get whitelist."
        try:
            steamApiReq = requests.get('http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key='+cfg['steam_API_key']+'&steamids=' + str(steamIDs))
            playersInfo = steamApiReq.json()
            steamIDsWithNames = ''
            lineNum = 1
            for steamID in steamIDs.split(', '):
                player = next((player for player in playersInfo['response']['players'] if player['steamid'] == steamID), None)
                if (player is None):
                    continue
                steamIDsWithNames += f"{lineNum}: {steamID} ({player['personaname']})\n"
                lineNum += 1
            description += f'\n```\n{steamIDsWithNames}\n```'
        except: 
            description += "\n`" + steamIDs + ' `'
        return description

    # Loops through every Patreon sub, creates a list of discord users with the corresponding role they should have
    # Then applies those roles and removes any others
    async def auditPatreonRoles(self):
        startSeconds = int(datetime.now().timestamp())
        logging.info("Starting full Patreon role audit")
        api_client = patreon.API(cfg['patreonAccessToken'])
        # Get the campaign ID
        campaign_response = api_client.fetch_campaign()
        api_client.fetch_user()
        campaign_id = campaign_response.data()[0].id()
        cursor = None

        # Loop through every Patreon subscriber (skipping declined payments)
        # Create Dict of discordIDs and the appropiate discordRoleID they should have
        discordIDsAndRoleIDs = {}
        while True:
            pledges_response = api_client.fetch_page_of_pledges(campaign_id, 25, cursor=cursor)
            pledges = pledges_response.data()
            for pledge in pledges:
                if pledge.json_data['attributes']['declined_since'] is not None: continue # Skip declined subs
                patron_id = pledge.relationship('patron').id()
                patron = pledges_response.find_resource_by_type_and_id('user', patron_id)
                disc = patron.json_data['attributes']['social_connections']['discord']
                discID = 0
                if (disc is not None): discID = disc['user_id']
                if (discID == 0): continue
      
                roleID = 0
                try: roleID = cfg['patreonTierID_DiscordRoleID'][pledge.json_data['relationships']['reward']['data']['id']]
                except: continue
                discordIDsAndRoleIDs[int(discID)] = roleID

            cursor = api_client.extract_cursor(pledges_response)
            if not cursor:
                break     

        guild = client.get_guild(cfg['DiscordServer_ID'])
        patreonRoles = []
        for patreonRoleID in cfg['patreonTierID_DiscordRoleID'].values():
            patreonRoles.append(guild.get_role(int(patreonRoleID)))

        extraFlavorRoles = []
        for extraRoleID in cfg['extraRolesForPatreonSubs']:
            extraFlavorRoles.append(guild.get_role(int(extraRoleID)))

        # We loop through all the discord members in the server
        # Check if that user is in discordIDsAndRoleIDs, which specifies which discord members should have which Patreon role
        async for member in guild.fetch_members(limit=None):
            # if yes: 
                #  Give user the correct role from discordIDsAndRoleIDs
                #  Give user any extra flavor roles from extraRolesForPatreonSubs
                #  Remove any OTHER roles from patreonTierID_DiscordRoleID that aren't the one they are supposed to have
            if member.id in discordIDsAndRoleIDs.keys():
                role = guild.get_role(discordIDsAndRoleIDs[member.id])
                #await member.add_roles(role, *extraFlavorRoles)
                #await member.remove_roles(*[r for r in patreonRoles if r != role])
                logging.info(f"For Discord User {member.display_name}, adding Patreon role {role.id}, removing any other Patreon roles, and adding all flavor roles")
                
            # if no: 
                # Remove any roles from patreonTierID_DiscordRoleID
                # Remove any extra flavor roles from extraRolesForPatreonSubs
            else:
                if any(x in member.roles for x in patreonRoles) or any(x in member.roles for x in extraFlavorRoles):
                    #await member.remove_roles(*patreonRoles, *extraFlavorRoles)
                    logging.info(f"For Discord User {member.display_name}, removing ALL Patreon roles and flavor roles")
            pass
        return f"Finished in {int(datetime.now().timestamp())-startSeconds} seconds"

    ## Loops through the declined Patreon subs, and removes that users' Discord roles
    # async def auditPatreonDeclined(self):
    #     api_client = patreon.API(cfg['patreonAccessToken'])
    #     # Get the campaign ID
    #     campaign_response = api_client.fetch_campaign()
    #     api_client.fetch_user()
    #     campaign_id = campaign_response.data()[0].id()

    #     # Fetch all pledges
    #     cursor = None
    #     declinedUsers = "Users with declined payments:\n"
    #     declinedUsersIDs = []
    #     while True:
    #         pledges_response = api_client.fetch_page_of_pledges(campaign_id, 25, cursor=cursor)
    #         pledges = pledges_response.data()

    #         for pledge in pledges:
    #             patron_id = pledge.relationship('patron').id()
    #             patron = pledges_response.find_resource_by_type_and_id('user', patron_id)

    #             disc = patron.json_data['attributes']['social_connections']['discord']
    #             discID = 0
    #             declined = False
    #             if (disc is not None): 
    #                 discID = disc['user_id']
    #             if pledge.json_data['attributes']['declined_since'] is not None: declined = True
                
    #             if (declined == True):
    #                 declinedUsers += "<@" + str(discID) + ">\n" 
    #                 if (discID != 0): declinedUsersIDs.append(discID)

    #         cursor = api_client.extract_cursor(pledges_response)
    #         if not cursor:
    #             break
    #     guild = client.get_guild(cfg['DiscordServer_ID'])
    #     rolesToRemove = []
    #     for roleID in list(cfg['whitelistDiscordRoleWhitelists'].keys()): 
    #         rolesToRemove.append(guild.get_role(int(roleID)))

    #     # for declinedUserID in declinedUsersIDs:
    #     #     try:
    #     #         declinedMember = guild.get_member(int(declinedUserID))
    #     #         # for roleToRemove in rolesToRemove:
    #                 #await declinedMember.remove_roles(roleToRemove)
    #     #     except: 
    #     #         # await self.logMsg("Patreon Audit", "Cannot remove roles from discord user <@" + str(declinedUserID) + ">")
    #     #         pass

    #     return declinedUsers

    def getClanMemberRole(self, discordMember: discord.Member):
        for role in discordMember.roles:
            if str(role.id) in cfg['clanWhitelists'].keys():
                return role
        return None
    
    def getClanWhitelistIDs(self, roleID: int):
        currentIDs = []
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rows = sqlitecursor.execute("SELECT steamID FROM clanSteamIDs WHERE roleID = ?", (str(roleID),)).fetchall()
                if (len(rows) > 0):
                    for row in rows:
                        currentIDs.append(str(row[0]))
        return currentIDs

    def recordClanSteamIDs(self, CSV_ofSteamIDs, clanRole:discord.Role, discordID):
        singleIDregex = "([0-9]{17})(.*)"
        stringRemaining = CSV_ofSteamIDs.strip("/").replace('\n', ' ')
        steamIDs = []
        numWhitelists = cfg['clanWhitelists'][str(clanRole.id)]['numWhitelists']
        while True:
            rematch = re.search(singleIDregex, stringRemaining)
            if (rematch is None):
                break
            steamIDs.append(rematch.group(1))
            stringRemaining = rematch.group(2)
            if (len(stringRemaining) <= 0):
                break

        if (len(steamIDs) >= 1): 
            # Add to DB
            with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
                with closing(sqlite.cursor()) as sqlitecursor:
                    # Remove all IDs associated with clan role, then readd them all
                    # clanSteamIDs (roleID TEXT NOT NULL, steamID TEXT NOT NULL, discordID TEXT NOT NULL )
                    sqlitecursor.execute("DELETE FROM clanSteamIDs WHERE roleID = ?", (str(clanRole.id),))
                    for steamID in steamIDs:
                        sqlitecursor.execute("INSERT INTO clanSteamIDs(roleID,steamID,discordID) VALUES (?,?,?)", (str(clanRole.id), str(steamID), str(discordID)))
                sqlite.commit()
            
            description = "SUCCESS! Whitelist updated.\n"
            if (numWhitelists != 0):
                description += f"Your {cfg['clanMoniker']} is alloted up to {numWhitelists} whitelists. \nThese changes to the {clanRole.name} whitelist will take effect on next map change.\n"
            if (numWhitelists == 0):
                description += "**WARNING** Your role doesn't appear to be alloted any whitelist slots. If you believe this to be an error please contact an admin."
            return description
        
        # There were no steamIDs in CSV_ofSteamIDs
        description = """Error, you didn't enter any valid SteamIDs.
        \n**WHERE DO YOU GET STEAMID??** See gif 👇
        \nhttps://i.imgur.com/eau1SXw.mp4"""
        return description

    def getClanWhitelistStatus(self, clanRole: discord.Role):
        maxWhitelists = 0
        try: maxWhitelists = cfg['clanWhitelists'][str(clanRole.id)]['numWhitelists']
        except: pass
        description = ""
        if (maxWhitelists == 0):
            description += f"**WARNING** Your clan doesn't appear to have any alloted whitelist slots. If you belive this to be an error, please contact an admin.\n"
        description += f"Your {clanRole.name} {cfg['clanMoniker']} is alloted up to {maxWhitelists} whitelists. The first {maxWhitelists} entries below are on the whitelist.\n"
        steamIDs = client.getClanWhitelistIDs(clanRole.id)
        try:
            steamApiReq = requests.get('http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key='+cfg['steam_API_key']+'&steamids=' + str(steamIDs))
            playersInfo = steamApiReq.json()
            steamIDsWithNames = ''
            for steamID in steamIDs:
                player = next((player for player in playersInfo['response']['players'] if player['steamid'] == steamID), None)
                if (player is None):
                    continue
                steamIDsWithNames += steamID + ' (' + player['personaname'] + ')\n'
            description += '\n```\n' + steamIDsWithNames + '\n```'
        except: 
            description += "\n`" + ', '.join(steamIDs) + ' `'
        return description    
    
    async def logMsg(self, title, message):
        if (cfg['do_log'] == False):
            logging.info(f"{title}: {message}")
            return
        CDDiscordServer = client.get_guild(cfg['DiscordServer_ID'])
        logCh = await (CDDiscordServer.fetch_channel(cfg['log_channel_ID']))
        logEmbed = discord.Embed(title=title, description=message)
        await logCh.send(embed=logEmbed)
   
    def is_me(self, m):
        return m.author == client.user
######### END CLASS SquadClient #########
#########################################

######### INTERACTION CLASSES #########
## User Whitelists ##
class ButtonWhitelistGatherView(discord.ui.View):
    def __init__(self,):
        super().__init__(timeout=None)
        self.add_item(ButtonWhitelistGatherButton())
        self.add_item(ButtonCheckPatreonButton())
        self.add_item(ButtonWhitelistSearchID())
        self.add_item(ButtonLinkPatreonButton())

class ButtonWhitelistGatherButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Edit Whitelists",style=discord.ButtonStyle.primary, emoji='✏️', custom_id="ButtonWhitelistGatherButton")

    async def callback(self, interaction: discord.Interaction):
        maxWhitelists = client.getMaxWhitelistsByDiscordID(interaction.user.id)
        currentSteamIDs = client.getWhitelistIdsFromDiscordID(interaction.user.id)
        modal = modal_EditWhitelists(maxWhitelists, currentSteamIDs)
        await interaction.response.send_modal(modal)

class ButtonWhitelistSearchID(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Search My ID",style=discord.ButtonStyle.primary, emoji='🔎', custom_id="ButtonWhitelistSearchID")

    async def callback(self, interaction: discord.Interaction):
        try:
            modal = modal_SearchWhitelistForID()
            await interaction.response.send_modal(modal)
        except Exception as e: # work on python 3.x
            logging.error(e)
            traceback.print_stack()
            return

class ButtonCheckPatreonButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Whitelist Status",style=discord.ButtonStyle.success, emoji='🏆', custom_id="ButtonCheckPatreonButton")
    async def callback(self, interaction: discord.Interaction):
        description = client.getWhitelistStatus(interaction.user.id)
        await interaction.response.send_message(f'{description}', ephemeral=True)

class ButtonLinkPatreonButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Link Patreon to Discord",style=discord.ButtonStyle.link, url="https://patreon.com/auth/discord/connect")


## Clan Whitelists ##
class ClanWhitelistsView(discord.ui.View):
    def __init__(self,):
        super().__init__(timeout=None)
        self.add_item(ClanWhitelistsEditButton())
        self.add_item(ClanWhitelistsStatusButton())

class ClanWhitelistsEditButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Edit Whitelists",style=discord.ButtonStyle.primary, emoji='✏️', custom_id="ClanWhitelistsEditButton")

    async def callback(self, interaction: discord.Interaction):
        maxWhitelists = 0
        role = client.getClanMemberRole(interaction.user)
        if role is None:
            await interaction.response.send_message(content=f"Error. You don't appear to have a {cfg['clanMoniker']} role.", ephemeral=True)
            return
        maxWhitelists = cfg['clanWhitelists'][str(role.id)]['numWhitelists']
        currentSteamIDs = ', '.join(client.getClanWhitelistIDs(role.id))
        modal = modal_EditClan(maxWhitelists, currentSteamIDs, role)
        modal.title = f"{role.name} {cfg['clanMoniker']} Whitelists"
        await interaction.response.send_modal(modal)

class ClanWhitelistsStatusButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Whitelist Status",style=discord.ButtonStyle.success, emoji='📝', custom_id="ClanWhitelistsStatusButton")
    async def callback(self, interaction: discord.Interaction):
        role = client.getClanMemberRole(interaction.user)
        if role is None:
            await interaction.response.send_message(content=f"Error. You don't appear to have a {cfg['clanMoniker']} role.", ephemeral=True)
            return
        description = client.getClanWhitelistStatus(role)
        await interaction.response.send_message(f'{description}', ephemeral=True)


## PayPal Whitelists ##
class PayPalWhitelistView(discord.ui.View):
    def __init__(self,):
        super().__init__(timeout=None)
        self.add_item(PayPalWhitelist_PayPalLink())
        self.add_item(PayPalWhitelist_LinkSteamID())
        self.add_item(PayPalWhitelist_ConfirmPayment())
        self.add_item(PayPalWhitelist_Status())

class PayPalWhitelist_PayPalLink(discord.ui.Button):
    def __init__(self):
        super().__init__(label="1: Buy a Whitelist",style=discord.ButtonStyle.link, url=cfg['paypal_checkoutLink'])

class PayPalWhitelist_LinkSteamID(discord.ui.Button):
    def __init__(self):
        super().__init__(label="2: Link SteamID",style=discord.ButtonStyle.primary, emoji='🔗', custom_id="PayPalWhitelist_LinkSteamID")

    async def callback(self, interaction: discord.Interaction):
        try:
            steamID = ''
            with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
                with closing(sqlite.cursor()) as sqlitecursor:
                    rows = sqlitecursor.execute("SELECT steamID FROM paypal_SteamIDs WHERE discordID = ?", (str(interaction.user.id),)).fetchone()
                    if (rows != None and len(rows) > 0):
                        steamID = rows[0]
            modal = modal_PayPal_LinkSteamID(steamID=steamID)
            await interaction.response.send_modal(modal)
        except Exception as e:
            await interaction.response.send_message(str(e))

class PayPalWhitelist_ConfirmPayment(discord.ui.Button):
    def __init__(self):
        super().__init__(label="3: Confirm a Payment",style=discord.ButtonStyle.green, emoji='✔️', custom_id="PayPalWhitelist_ConfirmPayment")

    async def callback(self, interaction: discord.Interaction):
        modal = modal_PayPal_ConfirmPayment()
        await interaction.response.send_modal(modal)

class PayPalWhitelist_Status(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Check Status",style=discord.ButtonStyle.secondary, emoji='❔', custom_id="PayPalWhitelist_Status")

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title='PayPal Whitelist Status', description=getPayPalStatus(discordID=interaction.user.id))
        await interaction.response.send_message(content=f"Todo", embed=embed, ephemeral=True)

######### END INTERACTION CLASSES #########


intents = discord.Intents.default()
intents.members = True
intents.message_content = True
client = SquadClient(intents=intents)

######### CONFIG #########
cfg={}
cfg['CommunityName']=os.getenv('CommunityName', 'No Name Set')
cfg['CommunityLogoUrlPNG']=os.getenv('CommunityLogoUrlPNG', 'No Logo Set')
cfg['DiscordServer_ID']=int(os.getenv('DiscordServer_ID', 0))
cfg['discord_token']=os.getenv('discord_token', 'No Token Set')
cfg['sqlite_db_file']=os.path.join(os.getenv('container_db_folder', ''), os.getenv('sqlite_db_file', 'sqlite.db'))
cfg['steam_API_key']=os.getenv('steam_API_key', 'No Steam API Key Set')
cfg['do_log']=os.getenv('do_log', 'False').lower() in ('true', '1', 'y')
cfg['log_channel_ID']=int(os.getenv('log_channel_ID', '0'))
cfg['featureEnable_Paypal']=os.getenv('featureEnable_Paypal', 'False').lower() in ('true', '1', 'y')
cfg['paypal_clientID']=os.getenv('paypal_clientID', '')
cfg['paypal_clientSecret']=os.getenv('paypal_clientSecret', '')
cfg['paypal_checkoutLink']=os.getenv('paypal_checkoutLink', '')
cfg['paypal_singleWhitelistCosts']=os.getenv('paypal_singleWhitelistCosts', '5')
cfg['paypal_currency']=os.getenv('paypal_currency', 'USD')
cfg['paypal_roles']=literal_eval(os.getenv('paypal_roles', '[]'))
cfg['featureEnable_PickMonthlyWhitelists']=os.getenv('featureEnable_PickMonthlyWhitelists', 'False').lower() in ('true', '1', 'y')
cfg['featureClanWhitelists']=os.getenv('featureClanWhitelists', 'False').lower() in ('true', '1', 'y')
cfg['featureEnable_SquadGroups']=os.getenv('featureEnable_SquadGroups', 'False').lower() in ('true', '1', 'y')
cfg['featureEnable_WhitelistAutoUpdate']=os.getenv('featureEnable_WhitelistAutoUpdate', 'False').lower() in ('true', '1', 'y')
cfg['featurePatreonAudit']=os.getenv('featurePatreonAudit', 'False').lower() in ('true', '1', 'y')
cfg['featureEnable_PatreonAutoAudit']=os.getenv('featureEnable_PatreonAutoAudit', 'False').lower() in ('true', '1', 'y')
cfg['featureEnable_Seeding']=os.getenv('featureEnable_Seeding', 'False').lower() in ('true', '1', 'y')

cfg['paypal_outputFile']=os.path.join(os.getenv('container_cfg_folder', ''), os.getenv('paypal_outputFile', 'paypalWLs.cfg'))
cfg['monthlyWhitelists_outputFile']=os.path.join(os.getenv('container_cfg_folder', ''), os.getenv('monthlyWhitelists_outputFile', 'monthlyWLs.cfg'))
cfg['squadGroups_outputFile']=os.path.join(os.getenv('container_cfg_folder', ''), os.getenv('squadGroups_outputFile', 'squadadmins.cfg'))
cfg['multiwl_outputFile']=os.path.join(os.getenv('container_cfg_folder', ''), os.getenv('multiwl_outputFile', 'multiWLs.cfg'))
cfg['seeding_outputFile']=os.path.join(os.getenv('container_cfg_folder', ''), os.getenv('seeding_outputFile', 'seedingWLs.cfg'))

cfg['clanMoniker']=os.getenv('clanMoniker', 'Clan')
cfg['pathToClanWhitelist']=os.getenv('pathToClanWhitelist', 'clanWLs.cfg')
cfg['clanWhitelists']=literal_eval(os.getenv('clanWhitelists', '{}'))
cfg['squadGroups_updateCron']=os.getenv('squadGroups_updateCron', '* * * * * */30')
cfg['secondsBetweenWhitelistUpdates']=int(os.getenv('secondsBetweenWhitelistUpdates', '86400'))
cfg['whitelistUpdateFreqCron']=os.getenv('whitelistUpdateFreqCron', '* * * * *')
cfg['patreonAuditFreqCron']=os.getenv('patreonAuditFreqCron', '0 6 1 * *')
cfg['whitelistDiscordRoleWhitelists']=literal_eval(os.getenv('whitelistDiscordRoleWhitelists', '{}'))
cfg['patreonTierID_DiscordRoleID']=literal_eval(os.getenv('patreonTierID_DiscordRoleID', '{}'))
cfg['whitelistsNeedThisDiscordRoleID']=int(os.getenv('whitelistsNeedThisDiscordRoleID', '0'))
cfg['extraRolesForPatreonSubs']=literal_eval(os.getenv('extraRolesForPatreonSubs', '[]'))
cfg['patreonAccessToken']=os.getenv('patreonAccessToken', '')

################ MODALS ################
## User Whitelists ##
class modal_EditWhitelists(ui.Modal, title='Edit your Whitelists!'):
    maxWhitelists = 0
    currentSteamIDs = 'none'
    isAdminEditing = False
    adminIsEditingID = 0
    def __init__(self, maxWhitelists, currentSteamIDs, isAdminEditing = False, adminIsEditingID = 0):
        super().__init__()
        self.maxWhitelists = maxWhitelists
        self.currentSteamIDs = currentSteamIDs
        self.isAdminEditing = isAdminEditing
        self.adminIsEditingID = adminIsEditingID
        if (isAdminEditing):
            self.title="Admin Editing Whitelist"
        self.whitelists = ui.TextInput(label='Enter up to '+str(maxWhitelists)+' SteamIDs (comma separated)', style=discord.TextStyle.paragraph, default=str(currentSteamIDs))
        self.add_item(self.whitelists)

    async def on_submit(self, interaction: discord.Interaction):
        steamIDStr = str(self.whitelists).replace('\n', ',')
        if (self.isAdminEditing):
            res = client.recordSteamIDs(steamIDStr, self.adminIsEditingID, "Admin: "+interaction.user.name, force=self.isAdminEditing, thirdPerson=self.isAdminEditing)
        else:
            res = client.recordSteamIDs(steamIDStr, interaction.user.id, interaction.user.name, force=self.isAdminEditing)
        await interaction.response.send_message(res, ephemeral=not self.isAdminEditing)
        if(self.isAdminEditing):
            await client.logMsg("MultiWhitelist", "<@"+str(interaction.user.id)+"> edited the whitelist for " +"<@"+str(self.adminIsEditingID)+ "> and entered `" + str(self.whitelists) + "` and got msg: \n`" + str(res)+"`")
        else:
            await client.logMsg("MultiWhitelist", "<@"+str(interaction.user.id) +"> ("+str(interaction.user.name)+ ") entered `" + str(self.whitelists) + "` and got msg: \n`" + str(res)+"`")

class modal_SearchWhitelistForID(ui.Modal, title='Enter the SteamID to search for'):
    def __init__(self):
        super().__init__()
        self.steamID = ui.TextInput(label='SteamID to search for:', style=discord.TextStyle.short, default='')
        self.add_item(self.steamID)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.steamID.value.strip()

        if(not re.match(regex_SingleID, str(val))):
            await interaction.response.send_message(content='Error, `' + val + '` is not a valid SteamID. \n\n**WHERE DO YOU GET STEAMID??** See gif 👇\nhttps://i.imgur.com/eau1SXw.mp4', ephemeral=True)
            return
        try:
            res = client.searchWhitelistsForID(steamID=val)
            await interaction.response.send_message(content="Your steamID was found on the following users' whitelists: "+res, ephemeral=True)
        except Exception as e: # work on python 3.x
            logging.error(e)
            traceback.print_stack()

## Clan Whitelists ##
class modal_EditClan(ui.Modal, title='Edit your Whitelists!'):
    maxWhitelists = 0
    currentSteamIDs = 'none'
    clanRole = 0
    def __init__(self, maxWhitelists, currentSteamIDs, clanRole: discord.Role):
        super().__init__()
        self.maxWhitelists = maxWhitelists
        self.currentSteamIDs = currentSteamIDs
        self.clanRole = clanRole
        self.whitelists = ui.TextInput(label=f'Enter up to {maxWhitelists} SteamIDs (comma separated)', style=discord.TextStyle.paragraph, default=str(currentSteamIDs))
        self.add_item(self.whitelists)

    async def on_submit(self, interaction: discord.Interaction):
        steamIDStr = str(self.whitelists).replace('\n', ',')
        res = client.recordClanSteamIDs(steamIDStr, self.clanRole, interaction.user.id)
        await interaction.response.send_message(res, ephemeral=True)
        await client.logMsg(f"{cfg['clanMoniker']} Whitelist", f"<@{interaction.user.id}> ({interaction.user.name}) entered `{self.whitelists}` and got msg: \n`{res}`")

## Admin Groups ##
class modal_EditGroupPermissions(ui.Modal, title='Edit Group Permissions'):
    groupname = ''
    def __init__(self, groupname, currentPermissions):
        super().__init__()
        self.groupname = groupname
        if len(currentPermissions) == 0:
            currentPermissions = 'UNCONFIGURED'
        self.permissions = ui.TextInput(label='Separate by commas, NO SPACES', style=discord.TextStyle.short, default=str(currentPermissions))
        self.add_item(self.permissions)

    async def on_submit(self, interaction: discord.Interaction):
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rows = sqlitecursor.execute("SELECT groupName FROM squadGroups_Groups WHERE groupName = ?", (self.groupname,)).fetchall()
                if (rows != None and len(rows) > 0):
                    await interaction.response.send_message(f"Permissions for group {self.groupname} updated.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} updated permissions for group `{self.groupname}` to `{str(self.permissions)}`")
                    sqlitecursor.execute("UPDATE squadGroups_Groups SET permissions = ? WHERE groupName = ?", (str(self.permissions), self.groupname))
                    sqlite.commit()
                else:
                    await interaction.response.send_message(f"ERROR. Group `{self.groupname}` doesn't exist. Cannot edit permissions.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} attempted to update permissions for group `{self.groupname}` but the group doesn't exist.")

class modal_EditManualPermissions(ui.Modal, title='Manual Permissions'):
    def __init__(self, current):
        super().__init__()
        if len(current) == 0:
            current = 'NONE'
        self.permissions = ui.TextInput(label='Enter full whitelist lines', style=discord.TextStyle.long, default=str(current))
        self.add_item(self.permissions)

    async def on_submit(self, interaction: discord.Interaction):
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                sqlitecursor.execute("DELETE FROM squadGroups_ManualEntry")
                for line in str(self.permissions).split('\n'):
                    sqlitecursor.execute("INSERT INTO squadGroups_ManualEntry(entry) VALUES (?)", (str(line),))
                await interaction.response.send_message(f"Manual permissions updated.")
                await client.logMsg("SquadGroups", f"{interaction.user.mention} edited the manual permissions.")
                sqlite.commit()

## PayPal Whitelists ##
class modal_PayPal_LinkSteamID(ui.Modal, title='Provide your SteamID'):
    def __init__(self, steamID):
        super().__init__()
        if (len(steamID) > 0):
            self.steamID_Input = ui.TextInput(label='SteamID is exactly 17 numbers.', style=discord.TextStyle.short, default=str(steamID))
        else:
            self.steamID_Input = ui.TextInput(label='SteamID is exactly 17 numbers.', style=discord.TextStyle.short)
        self.add_item(self.steamID_Input)

    async def on_submit(self, interaction: discord.Interaction):
        steamID = str(self.steamID_Input).strip()
        if(not re.match(regex_SingleID, str(steamID))):
            await interaction.response.send_message(f"ERROR. `{steamID}` is not a valid SteamID. Please try again.", ephemeral=True)
            return
        await interaction.response.send_message(f"I have recorded your SteamID as `{steamID}`.", ephemeral=True)
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                sqlitecursor.execute("DELETE FROM paypal_SteamIDs WHERE discordID = ?", (str(interaction.user.id),))
                sqlitecursor.execute("INSERT INTO paypal_SteamIDs(discordID, steamID) VALUES (?,?)", (str(interaction.user.id), str(steamID)))
            sqlite.commit()
        await client.logMsg("PayPal WL", f"{interaction.user.mention} set their SteamID to `{steamID}`.")

class modal_PayPal_ConfirmPayment(ui.Modal, title='Verify your email.'):
    def __init__(self):
        super().__init__()
        self.email_Input = ui.TextInput(label='Enter your Email', style=discord.TextStyle.short)
        self.add_item(self.email_Input)

    async def on_submit(self, interaction: discord.Interaction):
        email = str(self.email_Input).strip()
        if(len(email) < 2 or '@' not in email):
            await interaction.response.send_message(f"ERROR. I really doubt `{email}` is your email address. Please try again.", ephemeral=True)
            return
        await interaction.response.send_message(f"I have recorded your email as `{email}`. Once the payment comes through I will apply your whitelist using the SteamID you provided in __Step 2__. ", ephemeral=True)
        
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                sqlitecursor.execute("DELETE FROM paypal_PendingTransactions WHERE discordID = ?", (str(interaction.user.id),))
                sqlitecursor.execute("INSERT INTO paypal_PendingTransactions(discordID, email, timestamp) VALUES (?,?,?)", ( str(interaction.user.id), email, int(time.time()) ))
            sqlite.commit()
        await client.logMsg("PayPal WL", f"{interaction.user.mention} entered their email as `{email}`. Adding to the processing queue.")

################ COMMANDS ################

if (cfg.get('featureEnable_Paypal', False)):
    
    @group_PayPal.command()
    @app_commands.describe(expires='This must be a number of seconds since Jan 1st 1970 of when this WL expires.')
    async def addwhitelist(interaction: discord.Interaction, user:discord.User, steamid:str, expires:str):
        expires = expires.strip()
        steamid = steamid.strip()
        try:
            expiresI = int(expires)
        except:
            await interaction.response.send_message(content=f"Error. {expires} is not a valid number of seconds since Jan 1st 1970. To determine this number, go [hammertime.cyou](https://hammertime.cyou/), enter a date and time, then use the number from the </> row at the bottom.", ephemeral=True)
            return
        if(not re.match(regex_SingleID, str(steamid))):
            await interaction.response.send_message(content=f"Error. `{steamid}` is not a valid SteamID. Please try again.", ephemeral=True)
            return
        await interaction.response.send_message(content=f"Whitelist for {user.mention} using steamID `{steamid}` which will expire on <t:{expiresI}:f> added successfully.", ephemeral=True)
        await client.logMsg("PayPal WL", f"{interaction.user.mention} manually added a whitelist for {user.mention} using steamID `{steamid}` which is set to expire on <t:{expiresI}:f>.")
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                existingWL = sqlitecursor.execute("SELECT discordID, steamID, expires FROM paypal_Whitelists WHERE discordID = ?", (user.id,)).fetchall()
                if (len(existingWL) > 0):
                    sqlitecursor.execute("UPDATE paypal_Whitelists SET steamID = ?, expires = ? WHERE discordID = ?", (steamid, expiresI, user.id))
                else:
                    sqlitecursor.execute("INSERT INTO paypal_Whitelists (discordID, steamID, expires) VALUES (?, ?, ?)", (user.id, steamid, expiresI))
            sqlite.commit()

    @group_PayPal.command()
    async def removewhitelist(interaction: discord.Interaction, user:discord.User):
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                existingWL = sqlitecursor.execute("SELECT discordID, steamID, expires FROM paypal_Whitelists WHERE discordID = ?", (user.id,)).fetchall()
                if (len(existingWL) > 0):
                    await interaction.response.send_message(content=f"Whitelist for {user.mention} deleted.", ephemeral=True)
                    await client.logMsg("PayPal WL", f"{interaction.user.mention} manually deleted a whitelist for {user.mention}. ")
                    sqlitecursor.execute("DELETE FROM paypal_Whitelists WHERE discordID = ?", (user.id, ))
                else:
                    await interaction.response.send_message(content=f"Error. No whitelist found for {user.mention}", ephemeral=True)
            sqlite.commit()
    
    @group_PayPal.command()
    async def lookup(interaction: discord.Interaction, user:discord.User):
        embed = discord.Embed(title='PayPal Whitelist Status', description=f"__Status for {user.mention}__\n"+getPayPalStatus(discordID=user.id))
        await interaction.response.send_message(content=f"", embed=embed, ephemeral=False)

    @group_PayPal.command()
    async def sendpanel(interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.send_message("Panel created", ephemeral=True)
        try:
            embed = discord.Embed(title="Manage your PayPal Whitelist!", 
            description=f"""
            Please follow the steps below to purchase and confirm your whitelist automatically:
1. Use button 1 below to send a payment to us. Use multiples of ${cfg['paypal_singleWhitelistCosts']} {cfg['paypal_currency']} to buy multiple months at once.
            
2. Use button 2 below to link your SteamID. This is the SteamID that will receive whitelist.
            
3. Use button 3 below to provide the email address used to make your PayPal purchase. 

            **IMPORTANT:** It can take up to 3 hours for the payment to complete and show up in the bot. After completing __Step 3__, the bot will automatically keep looking for your payment. Once the bot receives your payment, we will automatically apply your whitelist using the SteamID you provided in __Step 2__. 
            
            **IMPORTANT:** Once the bot verifies your payment and applies your whitelist, you CANNOT CHANGE THE STEAMID. So make sure your SteamID is correct in __Step 2__ before doing __Step 3__.
            
            **You need to repeat __Step 3__ every time you submit a new payment**

            To check the current status of your whitelist, please use the Status button below.
            """)
            embed.add_field(name="​", inline=False, value="Made with ♥ by <@177189581060308992>")
            view = PayPalWhitelistView()
            await channel.send(embed=embed, view=view)
        except Exception as e:
            logging.error(e)

    @group_PayPal.command()
    async def sync(interaction: discord.Interaction):
        await interaction.response.send_message(content=f"Running backend sync", ephemeral=False)
        await autoPayPal()

if (cfg.get('featureEnable_PickMonthlyWhitelists', False)):
    @client.tree.command()
    @app_commands.default_permissions(moderate_members=True)
    async def pickmonthlywhitelists(interaction: discord.Interaction, howmany:int):
        """Picks a number of steamIDs from the current thread and automatically gives them whitelist on the server. """
        try:
            CDDiscordServer = client.get_guild(cfg['DiscordServer_ID'])
            channelUsed = await (CDDiscordServer.fetch_channel(interaction.channel.id))
            if (isinstance(channelUsed, discord.Thread) == False):
                await interaction.response.send_message(f"Error. You can only run this command from within a thread with steamIDs.")
                return
        except Exception as e:
            await interaction.response.send_message(f"Error. {e}")
            return

        await interaction.response.defer()
        responseMsg = await (interaction.followup.send("Gathering SteamIDs...", ephemeral=False, wait=True))

        messages = [message async for message in interaction.channel.history()]
        entriesIDs = []
        entriesNames = []
        winnerIDs = []
        winnerNames = []
        for aMessage in messages:
            if (aMessage.is_system() or aMessage.author == client.user):
                continue
            
            lines = aMessage.content.split('\n')
            for line in lines:
                match = re.match("(^.*)([0-9]{17})(.*$)", line)
                if (match is None):
                    continue
                entryID = match.group(2)
                entryName = match.group(1) + match.group(3)
                entryName = entryName.strip()

                if (entryID not in entriesIDs):
                    entriesIDs.append(entryID)
                    entriesNames.append(entryName.strip().strip('@').strip('CD |').strip())

        if (howmany >= len(entriesIDs)):
            winnerIDs = entriesIDs
            winnerNames = entriesNames
        else:
            while True:
                r = random.randint(0,len(entriesIDs)-1)
                possibleID = entriesIDs[r]
                possibleName = entriesNames[r]
                if (possibleID not in winnerIDs):
                    winnerIDs.append(possibleID)
                    winnerNames.append(possibleName)
                
                if (len(winnerIDs) == howmany):
                    break
        winnersTuple = zip(winnerNames, winnerIDs)
        await responseMsg.edit(content=f"The {howmany} winners are: `" + '`, `'.join(winnerNames) + '`\nThe winners have automatically been given Whitelist on the server!')
        winnerWL = 'Group=MonthlyWL:reserve\n'
        for winnerName, winnerID in winnersTuple:
            winnerWL += 'Admin=' + winnerID + ':MonthlyWL // ' + winnerName + '\n'

        with open(cfg['monthlyWhitelists_outputFile'], "w") as f:
            f.write(winnerWL)

if (cfg.get('featureEnable_SquadGroups', False)):
    @client.tree.command()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(steamid='Your Steam64_ID, it should be exactly 17 numbers long.')
    async def adminlink(interaction: discord.Interaction, steamid: str):
        """Link your SteamID for Squad in-game permissions."""
        if(not re.match(regex_SingleID, str(steamid))):
            await interaction.response.send_message(f"ERROR: `{steamid}`. is not a valid SteamID. It must be exactly 17 numbers long.", ephemeral=True)
            return
        
        await interaction.response.send_message(f"Your SteamID is now `{steamid}`. Changes will permeate within 60s. If you're in-game you will need to leave & rejoin.", ephemeral=True)
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                sqlitecursor.execute("DELETE FROM squadGroups_SteamIDs WHERE discordID = ?", (str(interaction.user.id),))
                sqlitecursor.execute("INSERT INTO squadGroups_SteamIDs(discordID, steamID) VALUES (?,?)", (str(interaction.user.id), str(steamid)))
            sqlite.commit()
        await client.logMsg("SquadGroups", f"{interaction.user.mention} linked their steamID to `{steamid}`")

    @client.tree.command()
    @app_commands.default_permissions(moderate_members=True)
    async def adminunlink(interaction: discord.Interaction):
        """Unlink your SteamID, you will lose in-game permissions."""
        await interaction.response.send_message(f"Your SteamID is has been unlinked, in-game permissions will be lost on map swap.", ephemeral=True)
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                sqlitecursor.execute("DELETE FROM squadGroups_SteamIDs WHERE discordID = ?", (str(interaction.user.id),))
            sqlite.commit()
        await client.logMsg("SquadGroups", f"{interaction.user.mention} unlinked their steamID.")

    @group_SquadGroups.command()
    @app_commands.describe(name='The group name. It must be unique. ')
    async def create(interaction: discord.Interaction, name: str):
        """Create a new permission group. WARNING: New groups require a server restart to apply."""
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rows = sqlitecursor.execute("SELECT groupName FROM squadGroups_Groups WHERE groupName = ?", (name,)).fetchone()
                if (rows != None and len(rows) > 0):
                    await interaction.response.send_message(f"ERROR. That group already exists.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} attempted to create group `{name}` but it already exists.")
                else:
                    await interaction.response.send_message(f"Group {name} created.")
                    sqlitecursor.execute("INSERT INTO squadGroups_Groups(groupName) VALUES (?)", (str(name),))
                    sqlite.commit()
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} created group `{name}`.")
    
    @group_SquadGroups.command()
    @app_commands.describe(name='The group name to delete. ')
    async def remove(interaction: discord.Interaction, name:str):
        """Remove a permissions group. WARNING: Cannot be undone."""
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rows = sqlitecursor.execute("SELECT groupName FROM squadGroups_Groups WHERE groupName = ?", (name,)).fetchone()
                if (rows != None and len(rows) > 0):
                    await interaction.response.send_message(f"Group {name} deleted.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} deleted group `{name}`.")
                    sqlitecursor.execute("DELETE FROM squadGroups_Groups WHERE groupName = ?", (str(name),))
                    sqlitecursor.execute("DELETE FROM squadGroups_RoleGroupLinks WHERE groupName = ?", (str(name),))
                    sqlite.commit()
                else:
                    await interaction.response.send_message(f"ERROR. {name} doesn't exist.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} attempted to deleted group `{name}` but it doesn't exist.")

    @group_SquadGroups.command()
    async def list(interaction: discord.Interaction):
        """Lists all groups"""
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rows = sqlitecursor.execute("SELECT groupName FROM squadGroups_Groups").fetchall()
                rowStr = 'Groups:\n'
                for row in rows:
                    rowStr = rowStr + row[0] + '\n'
                rowStr = rowStr.strip('\n')
                await interaction.response.send_message(f"```{rowStr} \n```")
        await client.logMsg("SquadGroups", f"{interaction.user.mention} listed all groups.")

    @group_SquadGroups.command()
    @app_commands.describe(group='The group name to link role to.', role='The role to link to the group.')
    async def link(interaction: discord.Interaction, group:str, role:discord.Role):
        """Link a Discord role to a group. Any user with that role will receive the group permissions. """
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rows = sqlitecursor.execute("SELECT groupName FROM squadGroups_Groups WHERE groupName = ?", (group,)).fetchall()
                if (rows == None or len(rows) == 0):
                    await interaction.response.send_message(f"ERROR. Group {group} doesn't exist.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} attempted to link role {role.mention} to group `{group}` but the group doesn't exist.")
                    return
                rows = sqlitecursor.execute("SELECT roleID FROM squadGroups_RoleGroupLinks WHERE groupName = ? AND roleID = ?", (str(group),str(role.id))).fetchall()
                if (rows != None and len(rows) > 0):
                    await interaction.response.send_message(f"ERROR. Role {role.name} is already linked to group `{group}`.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} attempted to link role {role.mention} to group `{group}` but it is already linked to that group.")
                else:
                    await interaction.response.send_message(f"Role {role.name} is now linked to group `{group}`.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} linked role {role.mention} to group `{group}`.")
                    sqlitecursor.execute("INSERT INTO squadGroups_RoleGroupLinks(groupName, roleID) VALUES (?,?)", (str(group),str(role.id)))
                    sqlite.commit()

    @group_SquadGroups.command()
    @app_commands.describe(group='The group name to unlink role from.', role='The role to unlink from the group.')
    async def unlink(interaction: discord.Interaction, group:str, role:discord.Role):
        """Unlink a Discord role from a group. Any user with that role will no longer receive the group permissions. """
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rows = sqlitecursor.execute("SELECT groupName FROM squadGroups_Groups WHERE groupName = ?", (group,)).fetchall()
                if (rows == None or len(rows) == 0):
                    await interaction.response.send_message(f"ERROR. Group {group} doesn't exist.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} attempted to unlink role {role.mention} from group `{group}` but the group doesn't exist.")
                    return
                rows = sqlitecursor.execute("SELECT roleID FROM squadGroups_RoleGroupLinks WHERE groupName = ? AND roleID = ?", (str(group),str(role.id))).fetchall()
                if (rows != None and len(rows) > 0):
                    await interaction.response.send_message(f"Role {role.name} is unlinked from group `{group}`.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} unlinked role {role.mention} from group `{group}`.")
                    sqlitecursor.execute("DELETE FROM squadGroups_RoleGroupLinks WHERE groupName = ? AND roleID = ? ", (str(group),str(role.id)))
                    sqlite.commit()
                else:
                    await interaction.response.send_message(f"ERROR. Role {role.name} is not linked to group `{group}`.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} attempted to unlink role {role.mention} from group `{group}` but it isn't linked.")
                    
    @group_SquadGroups.command()
    async def viewsteamid(interaction: discord.Interaction, user: discord.User):
        """View the SteamID linked to a Discord user. """
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rows = sqlitecursor.execute("SELECT steamID FROM squadGroups_SteamIDs WHERE discordID = ?", (user.id,)).fetchone()
                if (rows != None and len(rows) > 0):
                    await interaction.response.send_message(f"{user.mention} is linked to SteamID: `{rows[0]}`")
                else:
                    await interaction.response.send_message(f"ERROR: {user.mention} does not have a SteamID linked. They need to use /admin_link, or you can use /set_admin_steamid")
        await client.logMsg("SquadGroups", f"{interaction.user.mention} requested {user.mention}'s steamID")

    @group_SquadGroups.command()
    async def setsteamid(interaction: discord.Interaction, user: discord.User, steamid: str):
        """Set the SteamID linked for a Discord user. """
        if(not re.match(regex_SingleID, str(steamid))):
            await interaction.response.send_message(f"ERROR: `{steamid}`. is not a valid SteamID. It must be exactly 17 numbers long.")
            return
        
        await interaction.response.send_message(f"{user.mention}'s SteamID is now `{steamid}`. Changes will permeate within 60s. If they're in-game they will need to leave & rejoin.")
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                sqlitecursor.execute("DELETE FROM squadGroups_SteamIDs WHERE discordID = ?", (str(user.id),))
                sqlitecursor.execute("INSERT INTO squadGroups_SteamIDs(discordID, steamID) VALUES (?,?)", (str(user.id), str(steamid)))
            sqlite.commit()
        
        await client.logMsg("SquadGroups", f"{interaction.user.mention} set {user.mention}'s steamID to `{steamid}`")

    @group_SquadGroups.command()
    @app_commands.describe(groupname='The group name to view.')
    async def view(interaction: discord.Interaction, groupname:str):
        """View the permissions for a group, and the roles linked to the group. """
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rowsGroups = sqlitecursor.execute("SELECT groupName, permissions FROM squadGroups_Groups WHERE groupName = ?", (groupname, )).fetchall()
                groupsStr = ''
                if (rowsGroups != None and len(rowsGroups) > 0):
                    for group in rowsGroups:
                        groupsStr = groupsStr + '\nGROUP: `' + group[0] + '`\nPerms: `' + group[1] + '`'
                        rowsLinked = sqlitecursor.execute("SELECT roleID FROM squadGroups_RoleGroupLinks WHERE groupName = ?", (group[0],)).fetchall()
                        linkedStr = ''
                        for linked in rowsLinked:
                            linkedStr = linkedStr + f"<@&{linked[0]}>, "
                        groupsStr = groupsStr + '\nLinked to: ' + linkedStr.strip(', ')

                    await interaction.response.send_message(f"{groupsStr}")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} viewed info for group {groupname}")
                else:
                    await interaction.response.send_message(f"ERROR: That group doesn't exist.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} attempted to view info for group {groupname} but it doesn't exist.")

    @group_SquadGroups.command()
    @app_commands.describe(groupname='The group name to edit permissions for.')
    async def edit(interaction: discord.Interaction, groupname:str):
        """Edit the permissions for a group. """
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rows = sqlitecursor.execute("SELECT permissions FROM squadGroups_Groups WHERE groupName = ?", (groupname,)).fetchall()
                if (rows != None and len(rows) > 0):
                    modal = modal_EditGroupPermissions(groupname=groupname, currentPermissions=rows[0][0])
                    await interaction.response.send_modal(modal)
                else:
                    await interaction.response.send_message(f"ERROR. {groupname} doesn't exist.")
                    await client.logMsg("SquadGroups", f"{interaction.user.mention} attempted to edit permissions for group `{groupname}` but it doesn't exist.")

    @group_SquadGroups.command()
    async def allpermissions(interaction: discord.Interaction):
        """List all the valid squad permissions"""
        await interaction.response.send_message("""```
changemap
pause            - Pause server gameplay
cheat            - Use server cheat commands
private          - Password protect server
balance          - Group Ignores server team balance
chat             - Admin chat and Server broadcast
kick
ban
config           - Change server config
cameraman        - Admin spectate mode
immune           - Cannot be kicked / banned
manageserver     - Shutdown server
featuretest      - Any features added for testing by dev team
reserve          - Reserve slot
debug            - show admin stats command and other debugging info
teamchange       - No timer limits on team change
forceteamchange  - Can issue the ForceTeamChange command
canseeadminchat  - This group can see the admin chat and teamkill/admin join notifications
```""")

    @group_SquadGroups.command()
    async def manualentries(interaction: discord.Interaction):
        """Edit one-off manual permissions"""
        manualPermissions = ""
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                rows = sqlitecursor.execute("SELECT entry FROM squadGroups_ManualEntry").fetchall()
                for row in rows:
                    manualPermissions = manualPermissions + f"{row[0]}\n"
        modal = modal_EditManualPermissions(current=manualPermissions.strip('\n'))
        await interaction.response.send_modal(modal)

if (cfg.get('featureClanWhitelists', False)):
    @group_Clans.command()
    async def whiteliststatus(interaction: discord.Interaction, role: discord.Role):
        """Check the whitelist status for a Role."""
        if str(role.id) not in cfg['clanWhitelists'].keys():
            await interaction.response.send_message(f"Error. {role.name} is not a valid {cfg['clanMoniker']} role.")
            return
        description = f"**Whitelist Status for {role.name}**\n"+client.getClanWhitelistStatus(role)
        await interaction.response.send_message(description)

    @group_Clans.command()
    async def editwhitelist(interaction: discord.Interaction, role: discord.Role):
        """Make changes to a user's whitelist"""
        try:
            maxWhitelists = 0
            if str(role.id) not in cfg['clanWhitelists'].keys():
                await interaction.response.send_message(f"Error. {role.name} is not a valid {cfg['clanMoniker']} role.")
                return
            maxWhitelists = cfg['clanWhitelists'][str(role.id)]['numWhitelists']
            currentSteamIDs = ', '.join(client.getClanWhitelistIDs(role.id))
            modal = modal_EditClan(maxWhitelists, currentSteamIDs, role)
            modal.title = f"{role.name} {cfg['clanMoniker']} Whitelists"
            await interaction.response.send_modal(modal)
        except Exception as e: # work on python 3.x
            logging.error(e)
            traceback.print_stack()

    @group_Clans.command()
    async def sync(interaction: discord.Interaction):
        """Forces the clan whitelists on the server to update."""
        await interaction.response.send_message("Syncing clan whitelists.")
        await client.updateClanWhitelists()

    @group_Clans.command()
    async def sendpanel(interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.send_message("Panel created", ephemeral=True)
        await client.sendClanWhitelistPanel(channel.id)

if (cfg.get('featurePatreonAudit', False)):
    @group_MultiWL.command()
    async def auditpatreon(interaction:discord.Interaction):
        """Combs through all the patreon subscribers, removes roles from those with declinded payments."""

        await interaction.response.defer()
        message = await (interaction.followup.send("Audit underway...", ephemeral=False, wait=True))

        declinedUsers = await client.auditPatreonRoles()
        logging.info(declinedUsers)
        await message.edit(content=declinedUsers)  

@group_MultiWL.command()
@app_commands.describe(user_to_permit='User to permit.')
async def permit(interaction: discord.Interaction, user_to_permit: discord.Member):
    """Allow a user to make another whitelist submission on the same day."""
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            CDDiscordServer = client.get_guild(cfg['DiscordServer_ID'])
            rows = sqlitecursor.execute("SELECT steamID FROM whitelistSteamIDs WHERE discordID = ?", (user_to_permit.id,)).fetchall()
            # user has a steamID recorded
            if (len(rows) >= 1):
                # set the changedOn to a day ago
                sqlitecursor.execute("UPDATE whitelistSteamIDs SET changedOnEpoch = ? WHERE discordID = ?", (int(time.time()) - cfg['secondsBetweenWhitelistUpdates'], str(user_to_permit.id)))
                await interaction.response.send_message(user_to_permit.mention + " is now permitted to make an additional whitelist submission today.")
            else:
                # user hasn't made a submission yet
                await interaction.response.send_message(user_to_permit.mention + " hasn't made a submission yet, no permit needed.")
        sqlite.commit()

@group_MultiWL.command()
async def sync(interaction: discord.Interaction):
    """Forces the whitelists on the server to update. Use sparingly."""
    await interaction.response.send_message("Syncing Patreon whitelists.")
    await client.updatePatreonWhitelists()

@group_MultiWL.command()
async def sendpanel(interaction: discord.Interaction, channel: discord.TextChannel):
    """Sends the Multi-Whitelist Control Panel to the selected channel"""
    await interaction.response.send_message("Panel created", ephemeral=True)
    await client.sendWhitelistModal(channelID=channel.id)

@group_MultiWL.command()
async def whiteliststatus(interaction: discord.Interaction, user_to_check: discord.Member):
    """Check the whitelist status for a discord user."""
    description = "**Whitelist Status for Discord Member " + user_to_check.name + "**\n"+client.getWhitelistStatus(user_to_check.id, thirdPerson=True)
    await interaction.response.send_message(description)

@group_MultiWL.command()
async def editwhitelist(interaction: discord.Interaction, user_to_edit: discord.Member):
    """Make changes to a user's whitelist"""
    try:
        maxWhitelists = client.getMaxWhitelistsByDiscordID(user_to_edit.id)
        currentSteamIDs = client.getWhitelistIdsFromDiscordID(user_to_edit.id)
        modal = modal_EditWhitelists(maxWhitelists, currentSteamIDs, isAdminEditing=True, adminIsEditingID=user_to_edit.id)
        await interaction.response.send_modal(modal)
    except Exception as e: # work on python 3.x
        logging.error(e)
        traceback.print_stack()

@group_MultiWL.command()
async def linkrole(interaction: discord.Interaction, role: discord.Role, maxwhitelists: int):
    """Give a role a number of Whitelists users can self-manage."""
    if (maxwhitelists < 1):
        await interaction.response.send_message(f"Error: `{maxwhitelists}` must be greater than zero.", ephemeral=True)
        return
    await interaction.response.send_message(f"Members with {role.mention} can now put up to `{maxwhitelists}` steamIDs on their personal whitelist.", ephemeral=True)
    await client.logMsg("MultiWhitelist", f"{interaction.user.mention} updated {role.mention} to max of `{maxwhitelists}` WLs.")
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            sqlitecursor.execute("INSERT INTO multiwl_RolesWhitelists(roleID,numWhitelists) VALUES(?,?) ON CONFLICT(roleID) DO UPDATE SET numWhitelists=?", (str(role.id),maxwhitelists,maxwhitelists))
        sqlite.commit()

@group_MultiWL.command()
async def listroles(interaction: discord.Interaction):
    """List all roles with configured multi-whitelist slots."""
    rolesStr = '__All Roles with multi-whitelist slots:__\n'
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            for roleID,numWhitelists in sqlitecursor.execute("SELECT roleID,numWhitelists FROM multiwl_RolesWhitelists").fetchall():
                rolesStr += f"<@&{roleID}>: max `{numWhitelists}` SteamIDs\n"
    await interaction.response.send_message(content=rolesStr.strip('\n'))

@group_MultiWL.command()
async def unlinkrole(interaction: discord.Interaction, role: discord.Role):
    """Unlink a role from having any whitelists."""
    await interaction.response.send_message(f"Members with {role.mention} will no longer receive any whitelist slots.", ephemeral=True)
    await client.logMsg("MultiWhitelist", f"{interaction.user.mention} unlinked {role.mention}. ")
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            sqlitecursor.execute("DELETE FROM multiwl_RolesWhitelists WHERE roleID=?", (str(role.id), ))
        sqlite.commit()

if (cfg.get('featureEnable_Seeding', False)):
    @group_Seeding.command()
    async def addserver(interaction: discord.Interaction, ipaddress: str, rconport: int, rconpassword: str):
        """Add a server to retrieve seeders from."""
        try:
            socket.inet_aton(ipaddress)
        except:
            await interaction.response.send_message(f"Error. {ipaddress} is not a valid IP address.", ephemeral=True)
            return
        if (len(rconpassword) == 0):
            await interaction.response.send_message(f"Error. RCON password cannot be blank", ephemeral=True)
            return
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                sqlitecursor.execute("INSERT INTO seeding_Servers(ipandport,password) VALUES(?,?) ON CONFLICT(ipandport) DO UPDATE SET password=?", (f"{ipaddress}:{rconport}", rconpassword, rconpassword))
            sqlite.commit()
        await interaction.response.send_message(f"Server {ipaddress}:{rconport} added.", ephemeral=True)

    @group_Seeding.command()
    async def removeserver(interaction: discord.Interaction, ipaddress: str, rconport: int):
        """Remove a server from the seeding check."""
        try:
            socket.inet_aton(ipaddress)
        except:
            await interaction.response.send_message(f"Error. {ipaddress} is not a valid IP address.", ephemeral=True)
            return
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                if (len(sqlitecursor.execute("SELECT ipandport FROM seeding_Servers WHERE ipandport = ?", (f"{ipaddress}:{rconport}", )).fetchall()) == 0):
                    await interaction.response.send_message(f"Error. {ipaddress}:{rconport} isn't in the list of servers.", ephemeral=True)
                    return
                sqlitecursor.execute("DELETE FROM seeding_Servers WHERE ipandport=?", (f"{ipaddress}:{rconport}",))
            sqlite.commit()
        await interaction.response.send_message(f"Server {ipaddress}:{rconport} removed.", ephemeral=True)

    @group_Seeding.command()
    async def listservers(interaction: discord.Interaction):
        """Lists all active seeding servers."""
        servers = '__Active Servers:__\n'
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                for ipandport in sqlitecursor.execute("SELECT ipandport FROM seeding_Servers").fetchall():
                    servers += f"`{ipandport[0]}`{nl}"
        await interaction.response.send_message(f"{servers.strip(nl)}", ephemeral=True)

    @group_Seeding.command()
    async def autoredeem(interaction: discord.Interaction, autoredeem:bool):
        """Should whitelists auto-redeem when they hit the threshold?"""
        await interaction.response.send_message(f"autoredeem is now {autoredeem}.", ephemeral=True)
        setSetting('seed_autoredeem', str(autoredeem))

    @group_Seeding.command()
    async def threshold(interaction: discord.Interaction, points:int):
        """How many points until a user can redeem?"""
        await interaction.response.send_message(f"threshold is now {points} points.", ephemeral=True)
        setSetting('seed_threshold', str(points))

    @group_Seeding.command()
    async def pointworth(interaction: discord.Interaction, worth:float):
        """How many days is a single point(minute) worth? Default 0.083"""
        await interaction.response.send_message(f"A point is now worth {worth} days.", ephemeral=True)
        setSetting('seed_pointworth', str(worth))

    @group_Seeding.command()
    async def adminsaccrue(interaction: discord.Interaction, accrue:bool):
        """Should admins accrue points? Only works if you use this bot's /group feature. Default False"""
        await interaction.response.send_message(f"adminsaccrue is now {accrue}.", ephemeral=True)
        setSetting('seed_adminsaccrue', str(accrue))

    @group_Seeding.command()
    async def minplayers(interaction: discord.Interaction, players:int):
        """What is the minimum number of players needed in the server for players to accrue points?"""
        await interaction.response.send_message(f"minplayers is now {abs(players)}.", ephemeral=True)
        setSetting('seed_minplayers', str(abs(players)))

    @group_Seeding.command()
    async def maxplayers(interaction: discord.Interaction, players:int):
        """What is the maximum number of players in the server for players to accrue points?"""
        await interaction.response.send_message(f"maxplayers is now {abs(players)}.", ephemeral=True)
        setSetting('seed_maxplayers', str(abs(players)))

    @group_Seeding.command()
    async def pointcap(interaction: discord.Interaction, pointcap:int):
        """Should we cap seeding points to a value? Set to 0 for no cap"""
        await interaction.response.send_message(f"pointcap is now {abs(pointcap)}.", ephemeral=True)
        setSetting('seed_pointcap', str(abs(pointcap)))

    @group_Seeding.command()
    async def deduct(interaction: discord.Interaction, user:discord.User, points:int):
        """Deduct seeding points from a user."""
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                pointsRow = sqlitecursor.execute("SELECT points FROM seeding_Users WHERE discordID = ?", (user.id,)).fetchone()
                if (not pointsRow):
                    await interaction.response.send_message(f"Error, {user.mention} has not linked their steamID to the Seeding Feature.", ephemeral=True)
                    return
                finalpoints = pointsRow[0] - abs(points)
                if finalpoints < 0: finalpoints = 0
                sqlitecursor.execute("UPDATE seeding_Users SET points = ? WHERE discordID = ?", (finalpoints, user.id))
            sqlite.commit()
        await interaction.response.send_message(f"{user.mention}'s points are now `{finalpoints}`", ephemeral=True)

    @group_Seeding.command()
    async def trackadmins(interaction: discord.Interaction, track:bool):
        """Keep track of admin time on Jensens, seed, live. Default True"""
        await interaction.response.send_message(f"trackadmins is now {track}.", ephemeral=True)
        setSetting('seed_trackadmins', str(track))

    @group_Seeding.command()
    async def debug(interaction: discord.Interaction, ):
        await interaction.response.send_message(f"boop", ephemeral=True)
        await autoSeeding()
################ END COMMANDS ################

def getSettingS(key:str, default = None):
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            try:
                return sqlitecursor.execute("SELECT value FROM keyvals WHERE key=?", (key,)).fetchall()[0][0]
            except:
                return default
def getSettingB(key:str, default = None):
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            try:
                return 'True' in sqlitecursor.execute("SELECT value FROM keyvals WHERE key=?", (key,)).fetchall()[0][0]
            except:
                return default
def getSettingI(key:str, default = None):
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            try:
                return int(sqlitecursor.execute("SELECT value FROM keyvals WHERE key=?", (key,)).fetchall()[0][0])
            except:
                return default
def getSettingF(key:str, default = None):
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            try:
                return float(sqlitecursor.execute("SELECT value FROM keyvals WHERE key=?", (key,)).fetchall()[0][0])
            except:
                return default
def setSetting(key:str, val):
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            sqlitecursor.execute("INSERT INTO keyvals(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=?", (key,str(val),str(val)))
        sqlite.commit()

rconClients = {}
def rconcmd(cmd:str,hostandport:str,passwd:str, *args):
    """Creates a persistent RCON client if one doesn't exist, and runs the command using the client"""
    MAXTRIES = 2
    ip, port = hostandport.split(':')

    for i in range(0,MAXTRIES):
        try:
            if hostandport not in rconClients:
                rconClients[hostandport] = rClient(ip, int(port))
                rconClients[hostandport].connect()
                rconClients[hostandport].login(passwd=passwd)
        except Exception as e:
            logging.error(e)
            continue
        try:
            return rconClients[hostandport].run(cmd, *args)
        except Exception as e:
            logging.error(e)
            rconClients[hostandport].close()
            rconClients.pop(hostandport, None)
    return None
    
currentPlayers = []
def seedingAssignPoints():
    """Assign 1 point to every player on each server if that server meets the seeding requirements."""
    global currentPlayers
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            # Check each server to see if they're seeding
            for ipandport,password in sqlitecursor.execute("SELECT ipandport,password FROM seeding_Servers").fetchall():
                try:
                    currentmapResp = rconcmd('showcurrentmap', hostandport=ipandport, passwd=password)
                    seedSteamIDsAll = None
                    if currentmapResp is None: continue
                    # Check if we're currently on a seed map
                    if 'Jensen' in currentmapResp or 'Seed' in currentmapResp:
                        seedSteamIDs = getSteamIDsFromRconResp(rconcmd('listplayers', hostandport=ipandport, passwd=password))
                        if seedSteamIDs is None: continue
                        seedSteamIDsAll = seedSteamIDs.copy()
                        # Check if Admins can accrue, if they cannot, check if player is admin, if they are then skip them.
                        if (cfg.get('featureEnable_SquadGroups', False) and getSettingB('seed_adminsaccrue', Defaults['seed_adminsaccrue']) == False):
                            seedSteamIDs = removeAdmins(seedSteamIDs)
                        # If the playercount is outside the threshold of min and max players, don't assign any points
                        if ( not( getSettingI('seed_minplayers', Defaults['seed_minplayers']) < len(seedSteamIDs) < getSettingI('seed_maxplayers', Defaults['seed_maxplayers']) )):
                            logging.info(f"We're on a seed layer but player count outside of range")
                            continue
                        logging.info(f"Current seeders: {seedSteamIDs}")
                        ## Give all players 1 seeding point
                        for steamID in seedSteamIDs:
                            pointRow = sqlitecursor.execute("SELECT points FROM seeding_Users WHERE steamID=?", (steamID,)).fetchone()
                            if (not pointRow):
                                isBanking = 0 if getSettingB('seed_autoredeem', Defaults['seed_autoredeem']) else 1
                                sqlitecursor.execute("INSERT INTO seeding_Users(steamID,discordID,isBanking,points) VALUES(?,?,?,?)", (steamID,None,isBanking,1))
                            else:
                                pointCap = getSettingI('seed_pointcap', Defaults['seed_pointcap'])
                                if (pointCap == 0 or pointRow[0] < pointCap):
                                    sqlitecursor.execute("UPDATE seeding_Users SET points=points+1 WHERE steamID=?", (steamID,))
                            # if steamID not in currentPlayers:
                            #     rconcmd(f'warnplayer', steamID, f'Thank you for joining the seed! You currently have {points} seeding points! See our Discord for more info.', hostandport=ipandport, passwd=password)
                        currentPlayers = seedSteamIDsAll.copy()
                    
                    ## Track Admin time ##
                    if (cfg.get('featureEnable_SquadGroups', False) and getSettingI('seed_trackadmins', Defaults['seed_trackadmins'])):
                        if (seedSteamIDsAll is None):
                            seedSteamIDsAll = getSteamIDsFromRconResp(rconcmd('listplayers', hostandport=ipandport, passwd=password))
                        steamIDsAdmins = filterAdmins(seedSteamIDsAll)

                        for steamID in steamIDsAdmins:
                            if 'Jensen' in currentmapResp:
                                sqlitecursor.execute("INSERT INTO adminTracking(steamID,minutesOnJensens) VALUES (?,?) ON CONFLICT (steamID) DO UPDATE SET minutesOnJensens = minutesOnJensens + 1", (steamID,1))
                            elif 'Seed' in currentmapResp:
                                sqlitecursor.execute("INSERT INTO adminTracking(steamID,minutesOnSeed) VALUES (?,?) ON CONFLICT (steamID) DO UPDATE SET minutesOnSeed = minutesOnSeed + 1", (steamID,1))
                            else:
                                sqlitecursor.execute("INSERT INTO adminTracking(steamID,minutesOnLive) VALUES (?,?) ON CONFLICT (steamID) DO UPDATE SET minutesOnLive = minutesOnLive + 1", (steamID,1))
                except Exception as e: 
                    logging.error(e)
                    continue
        sqlite.commit()

def seedingPurgeExpiredWLs():
    """Look through the seeding whitelists and remove any expired ones"""
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            sqlitecursor.execute("DELETE FROM seeding_Whitelists WHERE expires < ?", (int(datetime.now().timestamp()),))
        sqlite.commit()

def seedingAutoRedeem():
    """Get all users where points > seed_threshold and isBanking is 0, and redeem their WL."""
    seed_threshold = getSettingI('seed_threshold', Defaults['seed_threshold'])
    seed_pointworth = getSettingI('seed_pointworth', Defaults['seed_pointworth'])
    ts_now = int(datetime.now().timestamp())
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            rows = sqlitecursor.execute("SELECT steamID,discordID,isBanking,points FROM seeding_Users WHERE points >= ? AND isBanking = 0", (seed_threshold,)).fetchall()
            for steamID,discordID,isBanking,points in rows:
                secondsToAdd = int((datetime.now() + timedelta(days= points*seed_pointworth )).timestamp()) - int(datetime.now().timestamp())
                sqlitecursor.execute("INSERT INTO seeding_Whitelists(steamID,expires) VALUES (?,?) ON CONFLICT (steamID) DO UPDATE SET expires = expires + ?", (steamID, ts_now + secondsToAdd,secondsToAdd))
                sqlitecursor.execute("UPDATE seeding_Users SET points = 0 WHERE steamID = ?", (steamID,))
        sqlite.commit()

def seedingGenerateCFG():
    whitelistStr = 'Group=SeedingWL:reserve\n'
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            for steamID,expires in sqlitecursor.execute("SELECT steamID,expires FROM seeding_Whitelists").fetchall():
                whitelistStr += f"Admin={steamID}:SeedingWL // Expires on TS {expires}\n"
        
    with open(cfg['seeding_outputFile'], "w") as f:
        f.write(whitelistStr)

def getPayPalStatus(discordID:int):
    description = ''
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            steamID = sqlitecursor.execute("SELECT steamID FROM paypal_SteamIDs WHERE discordID = ?", (str(discordID),)).fetchall()
            if (len(steamID) > 0):
                steamID = steamID[0][0]
            else:
                steamID = ''
            
            if (len(steamID) > 0):
                description += f"I currently have your steamID recorded as `{steamID}`. I will use this steamID to apply any new or pending whitelist payments.\n------\n"
            else:
                description += f"HEY! I don't know your SteamID! I cannot apply any whitelist payments until you provide it to me. Use button 2 and provide your SteamID.\n------\n"
            pendingTransaction = sqlitecursor.execute("SELECT email, timestamp FROM paypal_PendingTransactions WHERE discordID = ?", (str(discordID),)).fetchall()
            if (len(pendingTransaction) > 0):
                description += f"You have a pending transaction that I am still waiting to clear with PayPal. The email I am looking for is `{pendingTransaction[0][0]}`. You told me about this payment <t:{pendingTransaction[0][1]}:R>. \n"
                ts3hrs = int(datetime.now().timestamp())
                if (abs(ts3hrs - pendingTransaction[0][1]) > 10800 ): #ts3hrs < pendingTransaction[0][1]):
                    # it's been pending for > 3 hours
                    description += f"**Warning:** It has been longer than 3 hours and I haven't received confirmation from PayPal that your transaction came through. Please double check the email address you entered in __Step 3__, you can redo __Step 3__ if you want me to look up a different email.\n"
            else:
                description += f"You do not have any pending transactions.\n"
            description += '------\n'
            whitelistEntry = sqlitecursor.execute("SELECT steamID, expires FROM paypal_Whitelists WHERE discordID = ?", (str(discordID),)).fetchall()
            if (len(whitelistEntry) > 0):
                description += f"You currently have an active whitelist linked to SteamID `{whitelistEntry[0][0]}`. It will expire <t:{whitelistEntry[0][1]}:R> on <t:{whitelistEntry[0][1]}:f>. If you would like to extend your whitelist, please make a new payment with button 1, and verify it with button 3.\n"
            else:
                description += f"You do not currently have an active whitelist."
    return description

async def getPayPalTransactions():
    transactions = []
    try:
        transactionDetails = await getPayPalTransactionsJson()
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                for transaction in transactionDetails.get('transaction_details', []):
                    usedTransaction = sqlitecursor.execute("SELECT discordID FROM paypal_UsedTransactions WHERE transactionID = ?", (transaction['transaction_info']['transaction_id'], )).fetchall()
                    if (len(usedTransaction) == 0):
                        transactions.append(transaction)
    except:
        return transactions
    return transactions

async def getPayPalTransactionsJson(attempt:int = 0):
    if (attempt > 3):
        return {}
    headers = {'accept': '*/*', 'Authorization': f"Bearer {PayPalAuthToken}"}
    async with aiohttp.ClientSession(cookie_jar=cookieJar, headers=headers) as session:
        nowS = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        _29DaysAgoS = (datetime.utcnow() + timedelta(days=-29)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        data = {
            'fields': 'transaction_info,payer_info,shipping_info,auction_info,cart_info,incentive_info,store_info',
            'start_date': _29DaysAgoS,
            'end_date': nowS,
            'transaction_status': 'S',
            'balance_affecting_records_only': 'Y'
            }
        async with session.get(url="https://api-m.paypal.com/v1/reporting/transactions", params=data) as response:
            if (response.status == 401):
                await getPayPalAccessToken()
                return await getPayPalTransactionsJson(attempt+1)
            return await response.json()
    
async def getPayPalAccessToken():
    async with aiohttp.ClientSession(cookie_jar=cookieJar, auth=aiohttp.BasicAuth(cfg['paypal_clientID'], cfg['paypal_clientSecret'])) as session:
        data = {'grant_type': 'client_credentials', 'ignoreCache': 'true', 'return_authn_schemes': 'true', 'return_client_metadata': 'true', 'return_unconsented_scopes': 'true'}
        async with session.post(url="https://api-m.paypal.com/v1/oauth2/token", data=data) as response:
            if (response.status != 200):
                logging.error("Error during PayPal authorization flow.")
                return False
            respJson = await response.json()
            global PayPalAuthToken
            PayPalAuthToken = respJson['access_token']
            return True

# Get SteamIDs+Names of discord users with single Patreon role, as well as any SteamIDs of their friends if they have the group Patreon role.
async def getSteamIDsForWhitelist():
    steamIDs = []
    #(discordID TEXT NOT NULL, steamID TEXT NOT NULL, discordName TEXT DEFAULT ' ', changedOnEpoch INTEGER NOT NULL DEFAULT 0 )
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            allDiscordIDs = sqlitecursor.execute("SELECT discordID, discordName FROM whitelistSteamIDs GROUP BY discordID").fetchall()
            
            # Loop through all discord users with recorded steamIDs
            for rowDiscordID in allDiscordIDs:
                discordID = rowDiscordID[0]
                discordName = rowDiscordID[1]
                maxWhitelists = client.getMaxWhitelistsByDiscordID(discordID)
                steamIDsForUser = sqlitecursor.execute("SELECT steamID, changedOnEpoch FROM whitelistSteamIDs WHERE discordID = ?", (discordID, )).fetchall()
                if (maxWhitelists == 0 or len(steamIDsForUser) <= 0):
                    continue
                elif (maxWhitelists == 1):
                    steamIDs.append( (steamIDsForUser[0][0], 'Single Whitelist Tier. Linked to Discord: ' + str(discordName) + '('+str(discordID)+')'))
                elif (maxWhitelists > 1):
                    i = 0
                    for rowSteamID in steamIDsForUser:
                        if (i >= maxWhitelists): break
                        steamID = rowSteamID[0]
                        steamIDs.append( (steamID, 'Group Whitelist Tier. Linked to Discord: '+str(discordName)+'('+str(discordID)+')'))
                        i += 1
    
    return steamIDs

async def getSteamIDsForClanWhitelist():
    steamIDs = []
    allRoles = await client.get_guild(cfg['DiscordServer_ID']).fetch_roles()
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            allRoleIDs = sqlitecursor.execute("SELECT roleID, discordID FROM clanSteamIDs GROUP BY roleID").fetchall()
            
            # Loop through all role IDs with recorded steamIDs
            for row in allRoleIDs:
                roleID = row[0]
                roleName = "Unknown"
                try: roleName = next((x for x in allRoles if str(x.id) == str(roleID)), "Unknown")
                except: pass
                discordID = row[1]
                maxWhitelists = 0
                maxWhitelists = cfg['clanWhitelists'][str(roleID)]['numWhitelists']
                steamIDsForRole = sqlitecursor.execute("SELECT steamID FROM clanSteamIDs WHERE roleID = ?", (roleID, )).fetchall()
                if (maxWhitelists == 0 or len(steamIDsForRole) <= 0):
                    continue
                else:
                    i = 0
                    for rowSteamID in steamIDsForRole:
                        if (i >= maxWhitelists): break
                        steamID = rowSteamID[0]
                        steamIDs.append( (steamID, f'{roleName} {cfg["clanMoniker"]}'))
                        i += 1
    
    return steamIDs

def getSteamIDsFromRconResp(rconResp:str):
    steamIDlist = []
    if rconResp is None:
        return None
    for line in rconResp.splitlines():
        if (line == '----- Recently Disconnected Players [Max of 15] -----'): 
            break
        try:
            steamIDlist.append(re.search(r'SteamID: ([0-9]{17})', line)[1])
        except: pass
    return steamIDlist

def removeAdmins(listOfSteamIDs:List[str]) -> List[str]:
    filteredList = []
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            for sid in listOfSteamIDs:
                if (sqlitecursor.execute("SELECT discordID FROM squadGroups_SteamIDs WHERE steamID=?", (sid,)).fetchone()):
                    continue
                filteredList.append(sid)
    return filteredList

def filterAdmins(listOfSteamIDs:List[str]) -> List[str]:
    filteredList = []
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            for sid in listOfSteamIDs:
                if (sqlitecursor.execute("SELECT discordID FROM squadGroups_SteamIDs WHERE steamID=?", (sid,)).fetchone()):
                    filteredList.append(sid)
    return filteredList

if (cfg['featureEnable_WhitelistAutoUpdate']):
    @aiocron.crontab(cfg['whitelistUpdateFreqCron'])
    async def autoPatreon():
        await client.updatePatreonWhitelists()
        if (cfg['featureClanWhitelists']):
            await client.updateClanWhitelists()

if (cfg['featureEnable_PatreonAutoAudit']):
    @aiocron.crontab(cfg['patreonAuditFreqCron'])
    async def autoPatreonAudit():
        declinedUsers = await client.auditPatreonRoles()
        await client.logMsg("Auto Patreon Audit", "Audit ran successfully.\n" + declinedUsers)

if (cfg.get('featureEnable_SquadGroups', False)):
    @aiocron.crontab(cfg['squadGroups_updateCron'])
    async def autoAdminGroups():
        if (client.isReady == False):
            return
        outputStr = ''
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
                linkRows = sqlitecursor.execute("SELECT groupName, roleID FROM squadGroups_RoleGroupLinks").fetchall()
                groupRows = sqlitecursor.execute("SELECT groupName, permissions FROM squadGroups_Groups").fetchall()
                for groupRow in groupRows:
                    outputStr = outputStr + f"\nGroup={groupRow[0]}:{groupRow[1]}"

                steamIdRows = sqlitecursor.execute("SELECT discordID, steamID FROM squadGroups_SteamIDs").fetchall()
                for steamIdRow in steamIdRows:
                    discordID = steamIdRow[0]
                    steamID = steamIdRow[1]
                    # Check if their current roles are in squadGroups_RoleGroupLinks, if so, apply the correct group
                    
                    CDDiscordServer = client.get_guild(cfg['DiscordServer_ID'])
                    try:
                        member = CDDiscordServer.get_member(int(discordID))
                        if (member is None):
                            continue
                        membersRoles = member.roles
                    except:
                        continue

                    for linkRow in linkRows:
                        if CDDiscordServer.get_role(int(linkRow[1])) in membersRoles:
                            outputStr = outputStr + f"\nAdmin={steamID}:{linkRow[0]}    // {member.name} ({member.id})"
                
                manualRows = sqlitecursor.execute("SELECT entry FROM squadGroups_ManualEntry").fetchall()
                for manualRow in manualRows:
                    outputStr = outputStr + f"\n{manualRow[0]}"

        with open(cfg['squadGroups_outputFile'], "w") as f:
            f.write(outputStr)

if (cfg.get('featureEnable_Paypal', False)):
    @aiocron.crontab('* * * * * */45')
    async def autoPayPal():
        ts_40DaysAgo = int((datetime.now() + timedelta(days=-40)).timestamp())
        ts_now = int(datetime.now().timestamp())
        guild = client.get_guild(cfg['DiscordServer_ID'])
        allTransactions = []
        
        # check all pending transactions
        with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
            with closing(sqlite.cursor()) as sqlitecursor:
        # remove any old pending transactions older than 40 days ago. 
                sqlitecursor.execute("DELETE FROM paypal_PendingTransactions WHERE timestamp < ?", (ts_40DaysAgo,))
                sqlite.commit()
                pendingTransactions = sqlitecursor.execute("SELECT discordID, email, timestamp FROM paypal_PendingTransactions").fetchall()
                if (len(pendingTransactions) > 0):
                    allTransactions = await getPayPalTransactions()
                for pending in pendingTransactions:
                    p_discordID = pending[0]
                    p_email = pending[1]
                    p_steamID = sqlitecursor.execute("SELECT discordID, steamID FROM paypal_SteamIDs WHERE discordID = ?", (p_discordID,)).fetchall()
                    if (len(p_steamID) > 0):
                        p_steamID = p_steamID[0][1]
                    else:
                        continue # don't process pending transaction if we don't have their SteamID

                    for transaction in allTransactions:
                        if (transaction['payer_info']['email_address'] == p_email):
                            paidAmt = 0.0
                            try:
                                paidAmt = float(transaction['transaction_info']['transaction_amount']['value'])
                            except: pass
                            monthsToAdd = int(paidAmt/int(cfg['paypal_singleWhitelistCosts']))
                            secondsToAdd = int((datetime.now() + timedelta(days=30*monthsToAdd)).timestamp()) - int(datetime.now().timestamp())
        # add user's whitelist or extend it
        # put their transaction ID into the usedTransactions table
                            sqlitecursor.execute("DELETE FROM paypal_PendingTransactions WHERE discordID = ?", (p_discordID,))
                            sqlitecursor.execute("INSERT INTO paypal_UsedTransactions(discordID,transactionID,timestamp) VALUES (?,?,?)", (p_discordID, transaction['transaction_info']['transaction_id'], ts_now))
                            existingWL = sqlitecursor.execute("SELECT discordID, steamID, expires FROM paypal_Whitelists WHERE discordID = ?", (p_discordID,)).fetchall()
                            if (len(existingWL) > 0):
                                sqlitecursor.execute("UPDATE paypal_Whitelists SET steamID = ?, expires = ? WHERE discordID = ?", (p_steamID, existingWL[0][2]+secondsToAdd, p_discordID))
                                await client.logMsg("PayPal WL", f"Verified new transaction (`{transaction['transaction_info']['transaction_id']}`), ${paidAmt}. Whitelist for <@{p_discordID}> 's steamID `{p_steamID}` EXTENDED, will now expire on <t:{existingWL[0][2]+secondsToAdd}:f>")
                            else:
                                sqlitecursor.execute("INSERT INTO paypal_Whitelists (discordID, steamID, expires) VALUES (?, ?, ?)", (p_discordID, p_steamID, int(time.time())+secondsToAdd))
                                await client.logMsg("PayPal WL", f"Verified new transaction (`{transaction['transaction_info']['transaction_id']}`), ${paidAmt}. Whitelist for <@{p_discordID}> 's steamID `{p_steamID}` ADDED, will expire on <t:{int(time.time())+secondsToAdd}:f>")
                            
                            sqlite.commit()
        # give them their roles
                            try:
                                member = guild.get_member(int(p_discordID))
                                for roleIdToGive in cfg['paypal_roles']:
                                    await member.add_roles(guild.get_role(roleIdToGive))
                            except Exception as e:
                                await client.logMsg("PayPal WL", f"There was an error giving discord user @<{p_discordID}> their roles. Did they leave?\n{e}")

        # check whitelist table
        # remove the roles from the users whose whitelists expired
                expiredWhitelists = sqlitecursor.execute("SELECT discordID, steamID, expires FROM paypal_Whitelists WHERE expires < ?", (ts_now,)).fetchall()
                for expiredWL in expiredWhitelists:
                    await client.logMsg("PayPal WL", f"<@{expiredWL[0]}> 's whitelist for steamID {expiredWL[1]} expired on <t:{expiredWL[2]}:f>, removing their WL and roles.")
                    try:
                        member = guild.get_member(int(expiredWL[0]))
                        for roleIdToRemove in cfg['paypal_roles']:
                            await member.remove_roles(guild.get_role(roleIdToRemove))
                    except Exception as e:
                        await client.logMsg("PayPal WL", f"There was an error removing discord user @<{p_discordID}> roles. Did they leave?\n{e}")                  
        # delete any whitelists from table that have expired
                sqlitecursor.execute("DELETE FROM paypal_Whitelists WHERE expires < ?", (ts_now,))
                sqlite.commit()
        # generate the new whitelist file
                validWhitelists = sqlitecursor.execute("SELECT discordID, steamID, expires FROM paypal_Whitelists").fetchall()
                whitelistsStr = 'Group=PayPalWL:reserve'
                for validWL in validWhitelists:
                    whitelistsStr += f"\nAdmin={validWL[1]}:PayPalWL // discordID {validWL[0]} expires {validWL[2]}"
        
        with open(cfg['paypal_outputFile'], "w") as f:
            f.write(whitelistsStr)

if (cfg.get('featureEnable_Seeding', False)):
    @aiocron.crontab("* * * * * 15") # Runs every 15th second of every minute
    async def autoSeeding():
        seedingAssignPoints()
        # seedingAutoRedeem()
        # seedingPurgeExpiredWLs()
        # seedingGenerateCFG()


async def main():
    with closing(sqlite3.connect(cfg['sqlite_db_file'])) as sqlite:
        with closing(sqlite.cursor()) as sqlitecursor:
            # Create database if it doesn't exist
            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS multiwl_RolesWhitelists (roleID TEXT NOT NULL PRIMARY KEY, numWhitelists INTEGER NOT NULL )")

            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS whitelistSteamIDs (discordID TEXT NOT NULL, steamID TEXT NOT NULL, discordName TEXT DEFAULT ' ', changedOnEpoch INTEGER NOT NULL DEFAULT 0 )")
            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS clanSteamIDs (roleID TEXT NOT NULL, steamID TEXT NOT NULL, discordID TEXT NOT NULL )")
            
            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS squadGroups_SteamIDs (discordID TEXT NOT NULL PRIMARY KEY, steamID TEXT NOT NULL )")
            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS squadGroups_Groups (groupName TEXT NOT NULL PRIMARY KEY, permissions TEXT DEFAULT '' )")
            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS squadGroups_RoleGroupLinks (groupName TEXT NOT NULL, roleID TEXT NOT NULL )")
            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS squadGroups_ManualEntry (entry TEXT NOT NULL )")

            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS paypal_SteamIDs (discordID TEXT NOT NULL PRIMARY KEY, steamID TEXT NOT NULL )")
            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS paypal_Whitelists ( discordID TEXT NOT NULL PRIMARY KEY, steamID TEXT NOT NULL, expires INTEGER NOT NULL )")
            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS paypal_PendingTransactions ( discordID TEXT NOT NULL PRIMARY KEY, email TEXT NOT NULL, timestamp INTEGER NOT NULL )")
            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS paypal_UsedTransactions ( discordID TEXT NOT NULL, transactionID TEXT NOT NULL PRIMARY KEY, timestamp INTEGER NOT NULL )")

            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS seeding_Servers (ipandport TEXT NOT NULL PRIMARY KEY, password TEXT NOT NULL )")
            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS seeding_Users (steamID TEXT NOT NULL PRIMARY KEY, discordID TEXT, isBanking INTEGER NOT NULL, points INTEGER NOT NULL DEFAULT 0 )")
            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS seeding_Whitelists (steamID TEXT NOT NULL PRIMARY KEY, expires INTEGER NOT NULL )")
            
            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS adminTracking (steamID TEXT NOT NULL PRIMARY KEY, discordID TEXT, minutesOnJensens INTEGER NOT NULL DEFAULT 0, minutesOnSeed INTEGER NOT NULL DEFAULT 0, minutesOnLive INTEGER NOT NULL DEFAULT 0 )")

            sqlitecursor.execute("CREATE TABLE IF NOT EXISTS keyvals (key TEXT NOT NULL PRIMARY KEY, value TEXT NOT NULL )")
            
            # If there's an ENV var for the whitelist role, and there aren't any records in the DB, migrate the ENV var to the DB.
            if (len(cfg['whitelistDiscordRoleWhitelists']) > 0):
                if (len(sqlitecursor.execute("SELECT roleID FROM multiwl_RolesWhitelists").fetchall()) == 0):
                    logging.info("Migrating MultiWL roles to database.")
                    for roleID,numWL in cfg['whitelistDiscordRoleWhitelists'].items():
                        sqlitecursor.execute("INSERT INTO multiwl_RolesWhitelists(roleID,numWhitelists) VALUES(?,?)", (str(roleID),numWL))
        sqlite.commit()

    logging.info('database loaded')
    async with client:
        try:
            await client.start(cfg['discord_token'])
        except Exception as e:
            logging.error(e)
            traceback.print_stack()

loop.call_later(1, asyncio.create_task, main())
loop.run_forever()